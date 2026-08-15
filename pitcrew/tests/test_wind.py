"""The wind simulator's framing and its link, without an Arduino.

The device is a Sector 17 / Redion WSP whose firmware source SimHub deleted on
its way out, so the framing here is reconstructed and one constant - the CRC
polynomial - could not be verified at all. These tests pin the shape of the
protocol and, more importantly, prove the two behaviours that exist precisely
because of that uncertainty: the handshake determines the checksum by asking
the device, and a write failure never closes the port from inside the write.

Nothing here opens a serial port.
"""
from __future__ import annotations

import threading
import time

import pytest

from pitcrew.rig import arq, wind


# ------------------------------------------------------------------ framing

def test_a_frame_is_header_id_length_payload_checksum():
    frame = arq.build_frame(7, b"\x03V", arq.DEFAULT_CRC)
    assert frame[:2] == arq.FRAME_HEADER
    assert frame[2] == 7            # packet id
    assert frame[3] == 2            # length
    assert frame[4:6] == b"\x03V"
    assert len(frame) == 7          # + one checksum byte


def test_the_checksum_covers_the_body_and_not_the_header():
    """Including the two header bytes is the obvious mistake, and it produces
    a device that rejects everything with reason 4."""
    frame = arq.build_frame(7, b"\x03V", arq.DEFAULT_CRC)
    body = frame[2:-1]
    assert frame[-1] == arq.DEFAULT_CRC(body)
    assert frame[-1] != arq.DEFAULT_CRC(frame[:-1])


def test_every_channel_goes_every_time():
    """The firmware reads exactly `motorCount()` raw bytes with no framing, so
    a short write leaves it waiting mid-command for bytes that never come."""
    payload = arq.motors_payload([10, 20, 0, 0])
    assert payload == bytes([arq.MESSAGE_HEADER]) + b"VS" + bytes([10, 20, 0, 0])


def test_a_payload_over_the_firmware_limit_is_refused_here():
    """Better a ValueError than a NACK reason 2 from a fan controller."""
    with pytest.raises(ValueError):
        arq.build_frame(1, b"x" * (arq.MAX_PAYLOAD + 1))


def test_a_channel_value_outside_a_byte_is_refused():
    with pytest.raises(ValueError):
        arq.motors_payload([300])


def test_the_sequence_wraps_at_127_and_never_becomes_the_broadcast_id():
    assert arq.next_id(0) == 1
    assert arq.next_id(126) == 127
    assert arq.next_id(127) == 0
    assert arq.BROADCAST_ID not in {arq.next_id(i) for i in range(128)}


# ------------------------------------------------------------------ replies

def test_an_ack_is_recognised():
    reply = arq.parse_reply(bytes([arq.REPLY_ACK, 12]))
    assert reply.acknowledged is True
    assert reply.packet_id == 12


def test_a_bad_checksum_nack_is_distinguishable_from_every_other_refusal():
    """This is what makes the polynomial knowable rather than guessable."""
    bad_crc = arq.parse_reply(bytes([arq.REPLY_NACK, 3, arq.NACK_BAD_CRC]))
    bad_length = arq.parse_reply(bytes([arq.REPLY_NACK, 3, 2]))
    assert bad_crc.bad_checksum is True
    assert bad_length.bad_checksum is False
    assert "checksum did not match" in bad_crc.describe()


def test_a_truncated_reply_is_not_guessed_at():
    assert arq.parse_reply(bytes([arq.REPLY_ACK])) is None
    assert arq.parse_reply(b"") is None


# ------------------------------------------------------------- fake device

class FakeSerial:
    """An Arduino that accepts exactly one checksum, and says so when wrong."""

    def __init__(self, *, speaks: arq.CrcVariant, dead: bool = False,
                 silent: bool = False) -> None:
        self.speaks = speaks
        self.dead = dead
        self.silent = silent
        self.is_open = True
        self.written: list[bytes] = []
        self.closed = False
        self._pending = b""
        self.dtr_before_open: bool | None = None

    def write(self, data: bytes) -> int:
        if self.dead:
            import serial
            raise serial.SerialException("device stopped functioning")
        self.written.append(data)
        packet_id, length = data[2], data[3]
        body = data[2:-1]
        if self.silent:
            self._pending = b""
        elif data[-1] == self.speaks(body):
            self._pending = bytes([arq.REPLY_ACK, packet_id])
        else:
            self._pending = bytes([arq.REPLY_NACK, packet_id,
                                   arq.NACK_BAD_CRC])
        assert length == len(data) - 5
        return len(data)

    def read(self, size: int = 1) -> bytes:
        out, self._pending = self._pending[:size], self._pending[size:]
        return out

    def flush(self) -> None:
        pass

    def reset_input_buffer(self) -> None:
        pass

    def reset_output_buffer(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True
        self.is_open = False


@pytest.fixture()
def no_reset_delay(monkeypatch):
    monkeypatch.setattr(wind, "RESET_SETTLE_S", 0.0)


def link_onto(fake: FakeSerial) -> wind.WindLink:
    link = wind.WindLink("COM_TEST")
    link._serial = fake
    return link


# --------------------------------------------------------------- handshake

@pytest.mark.parametrize("variant", arq.CRC_VARIANTS)
def test_the_handshake_finds_whichever_checksum_the_device_speaks(variant):
    """SimHub deleted the firmware source before the polynomial could be read
    off it. The device distinguishes a bad checksum from every other fault, so
    the answer is asked for rather than assumed."""
    link = link_onto(FakeSerial(speaks=variant))
    assert link.handshake() is True
    assert link.crc.name == variant.name


def test_a_device_that_rejects_everything_is_reported_not_driven():
    """Guessing on past four rejections would mean sending fan commands the
    firmware will not accept, into hardware, hoping."""
    class RejectsAll(arq.CrcVariant):
        pass

    unknown = RejectsAll("nothing-we-know", 0x9B, reflected=False)
    link = link_onto(FakeSerial(speaks=unknown))
    assert link.handshake() is False


def test_silence_is_not_treated_as_a_wrong_checksum():
    """A board still resetting answers nothing, and trying three more
    polynomials at it neither helps nor tells you anything."""
    fake = FakeSerial(speaks=arq.DEFAULT_CRC, silent=True)
    link = link_onto(fake)
    assert link.handshake() is False
    assert len(fake.written) == 1, "it kept asking a device that was not there"


def test_the_handshake_opens_on_the_broadcast_id():
    """There is no way to know where the sequence stands on a board that has
    been talking to something else all week."""
    fake = FakeSerial(speaks=arq.DEFAULT_CRC)
    link_onto(fake).handshake()
    assert fake.written[0][2] == arq.BROADCAST_ID


# ------------------------------------------------------- the deadlock rule

def test_a_failed_write_does_not_close_the_port():
    """The exact shape of the deadlock that wedged SimHub: a failing write
    called Close() on a handle whose reader was parked in EndRead, and the
    process then survived a force-kill in an unkillable kernel wait."""
    fake = FakeSerial(speaks=arq.DEFAULT_CRC, dead=True)
    link = link_onto(fake)
    with pytest.raises(Exception):
        link.send((0, 0, 0, 0))
    assert fake.closed is False, "closed the port from inside the write"


def test_the_owning_thread_closes_and_stops_the_fans_doing_it():
    fake = FakeSerial(speaks=arq.DEFAULT_CRC)
    link = link_onto(fake)
    link.send((200, 200, 0, 0))
    link.close()
    assert fake.closed is True
    last = fake.written[-1]
    assert last[4:7] == bytes([arq.MESSAGE_HEADER]) + b"VS"
    assert last[7:11] == bytes([0, 0, 0, 0]), "let go without stopping the fans"


# ------------------------------------------------------------- the layer

def test_setting_an_output_never_blocks_and_supersedes_what_is_waiting():
    """A fan command from four seconds ago describes a corner the driver has
    already left. Last wins; nothing queues."""
    sim = wind.WindSim()
    sim.set_output((10, 10, 0, 0))
    sim.set_output((90, 90, 0, 0))
    assert sim._wanted == (90, 90, 0, 0)


def test_values_are_clamped_and_padded_to_the_channel_count():
    sim = wind.WindSim()
    sim.set_output((999, -5))
    assert sim._wanted == (255, 0, 0, 0)


def test_missing_pyserial_disables_the_fans_and_nothing_else(monkeypatch):
    """CLAUDE.md: the app observes and advises. An output that cannot start
    must never be able to stop a session being recorded."""
    monkeypatch.setattr(wind, "available", lambda: False)
    sim = wind.WindSim()
    sim.start()
    assert sim._thread is None
    assert "pyserial" in sim.state.error
    sim.shutdown()


def test_no_device_found_is_reported_rather_than_raised(monkeypatch):
    monkeypatch.setattr(wind, "find_port", lambda: None)
    sim = wind.WindSim()
    assert sim._connect() is False
    assert "not connected" in sim.state.describe().lower() \
        or "no wind simulator" in sim.state.error.lower()


def test_the_thread_keeps_sending_a_value_that_has_not_changed(monkeypatch):
    """The firmware zeroes every channel after 1000 ms without a motors read,
    so send-on-change would make the fans stutter whenever the driver held a
    steady speed."""
    fake = FakeSerial(speaks=arq.DEFAULT_CRC)
    monkeypatch.setattr(wind, "find_port", lambda: "COM_TEST")
    monkeypatch.setattr(wind, "SEND_INTERVAL_S", 0.01)
    monkeypatch.setattr(wind, "RESET_SETTLE_S", 0.0)

    def fake_open(self):
        self._serial = fake

    monkeypatch.setattr(wind.WindLink, "open", fake_open)

    sim = wind.WindSim()
    sim.set_output((120, 120, 0, 0))
    sim.start()
    try:
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and sim.state.frames_sent < 5:
            time.sleep(0.01)
    finally:
        sim.shutdown()

    assert sim.state.frames_sent >= 5, (
        "the value never changed, so nothing was resent, and the firmware "
        "deadman would have stopped the fans")
    assert sim.state.crc_name == arq.DEFAULT_CRC.name


def test_the_link_is_rebuilt_after_it_dies(monkeypatch):
    """Windows can hand back a different COM number after a replug, so
    discovery runs again rather than reusing the old one."""
    looked_up: list[int] = []

    def counting_find():
        looked_up.append(1)
        return None

    monkeypatch.setattr(wind, "find_port", counting_find)
    monkeypatch.setattr(wind, "RECONNECT_S", 0.01)
    sim = wind.WindSim()
    sim.start()
    try:
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and len(looked_up) < 3:
            time.sleep(0.01)
    finally:
        sim.shutdown()
    assert len(looked_up) >= 3, "gave up after the first failure"


def test_shutdown_joins_the_thread(monkeypatch):
    monkeypatch.setattr(wind, "find_port", lambda: None)
    monkeypatch.setattr(wind, "RECONNECT_S", 0.01)
    sim = wind.WindSim()
    sim.start()
    thread = sim._thread
    sim.shutdown()
    assert thread is not None
    assert not thread.is_alive()
    assert threading.active_count() >= 1
