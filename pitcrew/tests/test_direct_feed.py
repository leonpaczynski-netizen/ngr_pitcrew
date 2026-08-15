"""Talking to the PS5 without SimHub in the middle.

Everything hard about this was already built: `telemetry/packet.py` has always
done the Salsa20 decryption, because SimHub relays GT7's raw encrypted bytes
rather than decoding them. The missing piece was the heartbeat — GT7 streams
to nobody until it is asked and stops when the asking stops, and the app never
asked. The "Only accept from" box looked like it might be the answer and never
was: it is an accept-filter on inbound packets, not a destination.

These drive a fake console: a socket that waits to be asked and then streams
real encrypted GT7 packets back to whoever asked. It proves the two things
that can only be got wrong once — that the heartbeat leaves, and that the
console's reply lands on a socket we are actually listening on.
"""
from __future__ import annotations

import socket
import struct
import threading
import time

import pytest

from pitcrew.telemetry.listener import (
    GT7_HEARTBEAT_PORT,
    HEARTBEAT_C,
    UDPListener,
    probe_port,
)
from pitcrew.telemetry.selftest import FeedReport, check_feed

from .conftest import raw_packet


def a_car_on_track(*, rpm: float = 7200.0, fuel: float = 42.5,
                   speed_ms: float = 55.0) -> bytes:
    """A decrypted 368-byte packet with a car actually doing something.

    Fields are written at the offsets `packet.py` documents rather than
    through `make_packet`, because what has to go over the wire here is bytes
    and the parser is the thing under test.
    """
    buffer = bytearray(raw_packet(extended=True))
    struct.pack_into("<f", buffer, 0x3C, rpm)          # engine_rpm
    struct.pack_into("<f", buffer, 0x44, fuel)         # fuel_level
    struct.pack_into("<f", buffer, 0x48, 100.0)        # fuel_capacity
    struct.pack_into("<f", buffer, 0x4C, speed_ms)     # speed_ms
    struct.pack_into("<H", buffer, 0x8E, 0x0001)       # flags: on track
    struct.pack_into("<B", buffer, 0x90, 0x04)         # gear_raw: 4th
    return bytes(buffer)


def encrypted(packet_bytes: bytes, iv1: int = 0x0BADC0DE) -> bytes:
    """A GT7 packet as it goes over the wire, so the test decrypts for real.

    The IV is written into the *ciphertext* at offset 64, after encryption,
    which is why the parser skips those four bytes rather than reading them as
    a field: decrypting turns them into noise. Encrypting over them instead
    produces a packet nothing can open, which is what the first version of
    this helper did.
    """
    from Crypto.Cipher import Salsa20

    nonce = struct.pack("<II", iv1 ^ 0xDEADBEEF, iv1)
    buffer = bytearray(Salsa20.new(key=b"Simulator Interface Packet GT7 v",
                                   nonce=nonce).encrypt(packet_bytes))
    struct.pack_into("<I", buffer, 64, iv1)
    return bytes(buffer)


class FakeConsole(threading.Thread):
    """Streams only to an address that has asked it to, like the real one."""

    def __init__(self, payload: bytes) -> None:
        super().__init__(daemon=True)
        self.payload = payload
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(0.1)
        self.port = self.sock.getsockname()[1]
        self.asked_by: tuple | None = None
        self.heartbeats: list[bytes] = []
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                data, sender = self.sock.recvfrom(64)
            except socket.timeout:
                if self.asked_by:
                    # Keep streaming to whoever asked, at a rate a test can
                    # wait for rather than 60 Hz.
                    for _ in range(5):
                        self.sock.sendto(self.payload, self.asked_by)
                continue
            except OSError:
                break
            self.heartbeats.append(data)
            self.asked_by = sender
        self.sock.close()

    def stop(self) -> None:
        self._stop.set()
        self.join(timeout=2.0)


@pytest.fixture()
def console(monkeypatch):
    """A fake PS5 on a free port, with GT7's heartbeat port pointed at it."""
    fake = FakeConsole(encrypted(a_car_on_track()))
    fake.start()
    # The real port is 33739 and cannot be bound in a test that may run
    # alongside anything else, so the constant is redirected in both places
    # that send to it.
    monkeypatch.setattr("pitcrew.telemetry.listener.GT7_HEARTBEAT_PORT",
                        fake.port)
    monkeypatch.setattr("pitcrew.telemetry.selftest.GT7_HEARTBEAT_PORT",
                        fake.port)
    yield fake
    fake.stop()


def free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def test_the_listener_asks_and_the_console_answers(console):
    received: list[bytes] = []
    listener = UDPListener("0.0.0.0", free_port(), received.append,
                           heartbeat_to="127.0.0.1")
    listener.start()
    try:
        deadline = time.monotonic() + 4.0
        while time.monotonic() < deadline and not received:
            time.sleep(0.05)
    finally:
        listener.stop()
        listener.join(timeout=2.0)

    assert console.heartbeats, "the console was never asked"
    assert console.heartbeats[0] == HEARTBEAT_C, "format C is the superset"
    assert received, "the console answered and nothing was listening"
    assert listener.heartbeats_sent >= 1


def test_a_relay_listener_never_asks_for_anything():
    """SimHub does the talking in relay mode, and a heartbeat sent into a
    network that is not expecting one is noise."""
    listener = UDPListener("0.0.0.0", free_port(), lambda data: None)
    assert listener.heartbeating is False
    listener.start()
    time.sleep(0.3)
    listener.stop()
    listener.join(timeout=2.0)
    assert listener.heartbeats_sent == 0


def test_the_self_test_reports_live_values_not_zeros(console):
    """The whole point of CLAUDE.md 7: a working feed has to be provable, and
    zeros are the failure that survives all the way into a recommendation."""
    report = check_feed(port=free_port(), heartbeat_to="127.0.0.1",
                        listen_s=2.0)
    assert report.ok is True
    assert report.decoded > 0
    assert report.on_track is True
    assert report.samples["rpm"] == 7200
    assert report.samples["fuel_l"] == 42.5
    assert "not zeros" in report.detail


def test_the_self_test_says_when_the_console_was_never_reached():
    """A port that binds and receives nothing used to report success."""
    report = check_feed(port=free_port(), heartbeat_to="127.0.0.1",
                        listen_s=0.5)
    assert report.ok is False
    assert "Nothing arrived" in report.headline
    assert report.heartbeats_sent >= 1


def test_the_self_test_refuses_a_port_it_cannot_open():
    holder = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    holder.bind(("0.0.0.0", 0))
    try:
        report = check_feed(port=holder.getsockname()[1], listen_s=0.2)
        assert report.ok is False
        assert "will not open" in report.headline
    finally:
        holder.close()


def test_a_second_copy_of_the_app_cannot_quietly_take_the_port():
    """SO_REUSEADDR made the "already running" diagnostic unreachable.

    Measured on Windows: two sockets that both set it bind the same UDP port
    without complaint and the *first* keeps every datagram, so a second copy of
    Pit Crew started cleanly and sat there receiving nothing -- which is the
    one failure CLAUDE.md 7 says must never be allowed to look like a console
    that is not streaming.  UDP has no TIME_WAIT, so the option bought nothing
    in exchange.
    """
    port = free_port()
    first = UDPListener("0.0.0.0", port, lambda data: None)
    first.start()
    try:
        time.sleep(0.3)
        assert first.bind_error is None

        second = UDPListener("0.0.0.0", port, lambda data: None)
        second.start()
        second.join(timeout=2.0)
        assert second.bind_error is not None
        assert probe_port(port) is not None
    finally:
        first.stop()
        first.join(timeout=2.0)


def test_the_rate_is_measured_over_the_window_actually_listened_for():
    """`listen_s=2.0` used to report a healthy 60 Hz feed as 30 Hz, in the one
    headline the driver reads as proof the feed is working."""
    assert FeedReport(ok=True, headline="", decoded=120,
                      listened_s=2.0).rate_hz == 60.0


def test_bytes_that_will_not_decrypt_are_never_reported_as_a_feed():
    """Something else talking on the port must not read as GT7 working."""
    port = free_port()
    noise = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def chatter():
        for _ in range(40):
            noise.sendto(b"x" * 296, ("127.0.0.1", port))
            time.sleep(0.02)

    thread = threading.Thread(target=chatter, daemon=True)
    thread.start()
    try:
        report = check_feed(port=port, listen_s=1.0)
        assert report.ok is False
        assert report.datagrams > 0
        assert report.decoded == 0
        assert "would decrypt" in report.headline
    finally:
        thread.join(timeout=2.0)
        noise.close()


# --------------------------------------------------------------- port pair

# CLAUDE.md 3.1 marks GT7's send/receive port pair "verify before building",
# and the tests above cannot: they monkeypatch the heartbeat port to an
# ephemeral one so two of them can run at once, which means the numbers that
# actually go over the wire in a race were the one thing never asserted.
#
# Measured against a live PS5 running GT7 v1.70 on 15 Aug 2026: a heartbeat of
# b"C" to 33739 produced 1,199 datagrams of 368 bytes on 33740 in 20 s, all
# decrypting, none lost. These pin the numbers that test proved.


@pytest.fixture()
def controller_direct():
    """The controller's own feed properties, read off real settings.

    Deliberately NOT a constructed `PitCrewController`: building one here
    brings up two Qt screens, and tearing those down mid-file segfaults on
    Windows/Py3.14 - a teardown-order crash in PyQt, nothing to do with the
    feed. The three properties under test read only `settings` and `port`, so
    they are invoked as the unbound descriptors they are. That runs the
    shipped implementation rather than a paraphrase of it.
    """
    import dataclasses
    from types import SimpleNamespace

    from pitcrew import settings as settings_mod
    from pitcrew.controller import PitCrewController

    def build(*, feed_source: str = "ps5", ps5_ip: str = "192.168.1.20",
              udp_port: int = 33741):
        values = dataclasses.replace(
            settings_mod.Settings(), feed_source=feed_source, ps5_ip=ps5_ip,
            udp_port=udp_port)
        stand_in = SimpleNamespace(settings=values, port=udp_port)
        # `feed_port` and `heartbeat_target` both read `self.direct`, so it is
        # resolved first and pinned onto the stand-in - which also means this
        # asserts the three agree with each other rather than in isolation.
        stand_in.direct = PitCrewController.direct.fget(stand_in)
        return SimpleNamespace(
            direct=stand_in.direct,
            feed_port=PitCrewController.feed_port.fget(stand_in),
            heartbeat_target=PitCrewController.heartbeat_target.fget(stand_in),
        )

    return build


def test_gt7_speaks_on_33739_out_and_33740_back():
    """Measured against the console, not copied from a parser."""
    from pitcrew.telemetry.listener import GT7_STREAM_PORT

    assert GT7_HEARTBEAT_PORT == 33739
    assert GT7_STREAM_PORT == 33740


def test_direct_mode_binds_gt7s_port_and_not_the_relays(controller_direct):
    """The configured port is SimHub's. Binding it in direct mode would wait
    on a port the console never sends to - so direct must override it."""
    from pitcrew.telemetry.listener import GT7_STREAM_PORT

    app = controller_direct(ps5_ip="172.16.10.36", udp_port=33741)
    assert app.direct is True
    assert app.feed_port == GT7_STREAM_PORT
    assert app.heartbeat_target == "172.16.10.36"


def test_relay_mode_binds_the_configured_port_and_asks_nobody(
        controller_direct):
    app = controller_direct(feed_source="simhub", udp_port=33741)
    assert app.direct is False
    assert app.feed_port == 33741
    assert app.heartbeat_target is None


def test_direct_without_an_address_is_not_direct(controller_direct):
    """Half-configured must not silently bind GT7's port and heartbeat
    nowhere - that looks exactly like a console that is switched off."""
    app = controller_direct(ps5_ip="   ", udp_port=33741)
    assert app.direct is False
    assert app.feed_port == 33741
    assert app.heartbeat_target is None


# --------------------------------------------------- the format fallback

def test_noise_on_the_port_does_not_suppress_the_format_fallback(monkeypatch):
    """The fallback used to trigger on "nothing ARRIVED", not "nothing
    DECODED".

    GT7's stream port is a well-known number and this app has never been the
    only thing able to bind it. One stray datagram from anything else made the
    arrival counter non-zero and pinned the listener to format `C` for the
    whole session - so a console that only speaks `A` sat silent while the log
    insisted packets were coming in. They were. None of them were telemetry.
    """
    from pitcrew.telemetry import listener as listener_mod

    monkeypatch.setattr(listener_mod, "FORMAT_PATIENCE_S", 0.3)
    port = free_port()
    monkeypatch.setattr(listener_mod, "GT7_HEARTBEAT_PORT", free_port())

    feed = UDPListener("0.0.0.0", port, lambda data: False,
                       heartbeat_to="127.0.0.1")
    feed.start()
    noise = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline:
            noise.sendto(b"not telemetry", ("127.0.0.1", port))
            time.sleep(0.05)
            if feed.heartbeat_format == "A":
                break

        assert feed.total_received > 0, "the noise never landed"
        assert feed.decoded == 0
        assert feed.heartbeat_format == "A", (
            "arrival was mistaken for a working feed, so C was never "
            "given up on")
    finally:
        noise.close()
        feed.stop()
        feed.join(timeout=2.0)


def test_a_decoding_feed_is_left_on_format_c(monkeypatch):
    """The other half of the same rule: do not throw away current-lap-ms
    because the patience window happened to elapse."""
    from pitcrew.telemetry import listener as listener_mod

    monkeypatch.setattr(listener_mod, "FORMAT_PATIENCE_S", 0.3)
    port = free_port()
    monkeypatch.setattr(listener_mod, "GT7_HEARTBEAT_PORT", free_port())

    feed = UDPListener("0.0.0.0", port, lambda data: True,
                       heartbeat_to="127.0.0.1")
    feed.start()
    sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            sender.sendto(b"telemetry", ("127.0.0.1", port))
            time.sleep(0.05)

        assert feed.decoded > 0
        assert feed.heartbeat_format == "C"
    finally:
        sender.close()
        feed.stop()
        feed.join(timeout=2.0)
