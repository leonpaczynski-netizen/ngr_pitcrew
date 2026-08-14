"""Does the feed actually work — asked out loud, answered with real packets.

CLAUDE.md 7: *"The connection must fail loudly. A decrypt failure, a wrong
port, or a stopped heartbeat must not degrade into a stream of zeros. Zeros
are the one failure mode that survives all the way into a setup
recommendation."*

Probing whether a port will bind does not answer that. A port can be free, the
listener can run, and nothing whatsoever can arrive on it — which is exactly
what a wrong port pair, an unasked console, or a game sitting in the menus all
look like. So this opens the socket for real, sends real heartbeats if it is
supposed to, waits for real packets, decrypts them, and reports what came out.

It also exists because CLAUDE.md 3.1 marks GT7's send/receive port pair as
**verify before building**: the widely used pair is a heartbeat to 33739 and
the stream back on 33740, but the assignment is not consistently documented
across parsers. This is how that gets checked against hardware rather than
assumed, and why the report names the ports it used.

Six distinguishable outcomes, because "no data" is not a diagnosis:

* the port would not bind — something else is holding it;
* the heartbeat could not be sent — no route to the console;
* nothing arrived at all — nothing is sending here;
* bytes arrived but would not decrypt — the wrong stream, or a changed key;
* packets decoded but the car is not on track — the console is in the menus;
* packets decoded and the car is moving — this works.
"""
from __future__ import annotations

import socket
import time
from dataclasses import dataclass, field

from pitcrew.telemetry.listener import (
    GT7_HEARTBEAT_PORT,
    HEARTBEAT_A,
    HEARTBEAT_C,
)
from pitcrew.telemetry.packet import parse_packet

# Long enough for a console that is streaming to deliver hundreds of packets at
# 60 Hz, short enough that nobody walks away from the button.
LISTEN_S = 4.0

# Formats to ask for, best first. `C` is the 368-byte superset and the only one
# carrying current-lap time in ms; `A` is the 296-byte base set every version
# has spoken.
FORMATS = (HEARTBEAT_C, HEARTBEAT_A)


@dataclass
class FeedReport:
    """What the socket actually saw."""
    ok: bool
    headline: str
    detail: str = ""
    port: int = 0
    heartbeat_to: str | None = None
    heartbeats_sent: int = 0
    datagrams: int = 0
    decoded: int = 0
    undecodable: int = 0
    packet_format: str | None = None
    packet_bytes: int | None = None
    on_track: bool = False
    samples: dict = field(default_factory=dict)

    @property
    def rate_hz(self) -> float:
        return self.decoded / LISTEN_S if self.decoded else 0.0

    def as_text(self) -> str:
        return f"{self.headline} {self.detail}".strip()


def check_feed(*, port: int, heartbeat_to: str | None = None,
               source_ip: str = "", listen_s: float = LISTEN_S) -> FeedReport:
    """Open the socket, ask if asking is required, and report what arrived.

    Blocking, and deliberately so — it is driven by a button the driver presses
    while sitting still, and a background version would report into a screen he
    has already left.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("0.0.0.0", port))
    except OSError as exc:
        sock.close()
        return FeedReport(
            ok=False, port=port, heartbeat_to=heartbeat_to,
            headline=f"Port {port} will not open.",
            detail=(f"{exc}. Nothing would ever arrive on it — another copy "
                    f"of Pit Crew, or another program, is holding it."))

    sock.settimeout(0.2)
    report = _listen(sock, port, heartbeat_to, source_ip, listen_s)
    sock.close()
    return report


def _listen(sock, port, heartbeat_to, source_ip, listen_s) -> FeedReport:
    report = FeedReport(ok=False, headline="", port=port,
                        heartbeat_to=heartbeat_to)
    filter_ip = (source_ip or "").strip() or None
    deadline = time.monotonic() + listen_s
    # Half the window on the preferred format, then the fallback. A console
    # that will not speak `C` says so by silence, and silence for the whole
    # window would be indistinguishable from one that is switched off.
    switch_at = time.monotonic() + listen_s / 2
    heartbeat = FORMATS[0]
    last_heartbeat = 0.0
    foreign = 0

    while time.monotonic() < deadline:
        now = time.monotonic()
        if heartbeat_to:
            if not report.decoded and now > switch_at and heartbeat is FORMATS[0]:
                heartbeat = FORMATS[1]
                last_heartbeat = 0.0
            if now - last_heartbeat >= 1.0:
                try:
                    sock.sendto(heartbeat, (heartbeat_to, GT7_HEARTBEAT_PORT))
                    report.heartbeats_sent += 1
                except OSError as exc:
                    return FeedReport(
                        ok=False, port=port, heartbeat_to=heartbeat_to,
                        headline=f"Cannot reach the PS5 at {heartbeat_to}.",
                        detail=(f"{exc}. The console streams only to an "
                                f"address that has asked it to, so nothing "
                                f"will arrive until this succeeds."))
                last_heartbeat = now

        try:
            data, sender = sock.recvfrom(4096)
        except socket.timeout:
            continue
        except OSError:
            break

        if filter_ip and sender[0] != filter_ip:
            foreign += 1
            continue

        report.datagrams += 1
        packet = parse_packet(data)
        if packet is None:
            report.undecodable += 1
            continue
        report.decoded += 1
        report.packet_bytes = len(data)
        report.packet_format = _format_of(len(data))
        if packet.car_on_track:
            report.on_track = True
            report.samples = {
                "speed_kph": round(packet.speed_kmh, 1),
                "rpm": round(packet.engine_rpm),
                "fuel_l": round(packet.fuel_level, 2),
                "gear": packet.current_gear,
            }

    return _verdict(report, foreign, filter_ip)


def _format_of(size: int) -> str:
    return {296: "A", 316: "B", 344: "~", 368: "C"}.get(size, f"{size} bytes")


def _verdict(report: FeedReport, foreign: int, filter_ip: str | None) -> FeedReport:
    """Turn what was seen into the one sentence that says what to do next."""
    where = (f"the PS5 at {report.heartbeat_to}" if report.heartbeat_to
             else "SimHub")

    if not report.datagrams:
        if foreign:
            report.headline = f"Nothing accepted on port {report.port}."
            report.detail = (
                f"{foreign} packets arrived and every one was refused: the "
                f"source filter is set to {filter_ip} and they came from "
                f"somewhere else. Clear the filter or correct it.")
            return report
        report.headline = f"Nothing arrived on port {report.port}."
        report.detail = (
            f"{report.heartbeats_sent} heartbeats sent to "
            f"{report.heartbeat_to}:{GT7_HEARTBEAT_PORT} and no reply. Check "
            f"the console's address, that GT7 is running, and that nothing "
            f"is blocking UDP."
            if report.heartbeat_to else
            f"Nothing is sending to it. Check that {where} is running and "
            f"relaying to this port.")
        return report

    if not report.decoded:
        report.headline = (f"{report.datagrams} packets arrived and none "
                           f"would decrypt.")
        report.detail = (
            "Something is sending to this port, but it is not GT7 — or GT7 "
            "has changed its key or packet layout. This is the failure that "
            "must never be allowed to read as a stream of zeros.")
        return report

    report.ok = True
    rate = f"{report.rate_hz:.0f} Hz"
    fmt = (f"format {report.packet_format}" if report.packet_format
           else "an unrecognised size")
    report.headline = (
        f"{report.decoded} packets from {where} on port {report.port}, "
        f"{rate}, {fmt} ({report.packet_bytes} bytes).")

    if report.on_track:
        report.detail = (
            "Car on track: " + ", ".join(
                f"{key} {value}" for key, value in report.samples.items())
            + ". These are live values, not zeros.")
    else:
        report.detail = (
            "The car is not on track, so every channel reads zero and that is "
            "correct rather than broken. Go out and test again to see real "
            "values.")

    if report.packet_format not in (None, "C"):
        report.detail += (
            f" Format {report.packet_format} does not carry current-lap time "
            f"in milliseconds, which live strategy needs — format C does.")
    if report.undecodable:
        report.detail += (
            f" {report.undecodable} packets did not decrypt; something else "
            f"is talking on this port.")
    return report
