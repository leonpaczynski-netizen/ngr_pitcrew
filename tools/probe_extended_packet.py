"""Probe the unparsed tail of the GT7 368-byte extended packet.

`telemetry/packet.py` parses only the first 296 bytes.  GT7 v1.42+ sends 368,
and the extra 72 bytes are believed to carry wheel rotation (steering angle),
filtered throttle/brake and body motion (sway/heave/surge).  Rather than trust
a community offset table, this measures it.

Run it with GT7 sending telemetry and the Pit Crew app CLOSED (both bind the
same UDP port).  Then, while it runs:

    1. sit still for a few seconds      -> establishes the resting value
    2. turn the wheel fully left        -> one float should swing negative
    3. turn the wheel fully right       -> the same float should swing positive
    4. squeeze throttle, then brake     -> filtered pedal fields should track

Every offset in the tail is shown as float / int32 / 4 raw bytes with the
running min and max.  Whatever moved with the wheel is the steering channel.

    python tools/probe_extended_packet.py --seconds 60
"""
from __future__ import annotations

import argparse
import math
import os
import socket
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telemetry.packet import (  # noqa: E402
    PACKET_SIZE,
    PACKET_SIZE_NEW,
    VALID_MAGIC,
    _decrypt,
    parse_packet,
)

TAIL_START = PACKET_SIZE          # 296
TAIL_END = PACKET_SIZE_NEW        # 368


class FieldTrace:
    """Running min/max/current for one 4-byte slot in the tail."""

    def __init__(self, offset: int) -> None:
        self.offset = offset
        self.min_f = math.inf
        self.max_f = -math.inf
        self.cur_f = 0.0
        self.cur_i = 0
        self.cur_raw = b"\x00\x00\x00\x00"
        self.samples = 0

    def update(self, chunk: bytes) -> None:
        self.cur_raw = chunk
        self.cur_i = struct.unpack("<i", chunk)[0]
        value = struct.unpack("<f", chunk)[0]
        self.cur_f = value
        self.samples += 1
        # NaN/inf appear when the slot is not really a float; keep them out of
        # the range so they don't swamp the display.
        if math.isfinite(value):
            self.min_f = min(self.min_f, value)
            self.max_f = max(self.max_f, value)

    @property
    def span(self) -> float:
        if not math.isfinite(self.min_f) or not math.isfinite(self.max_f):
            return 0.0
        return self.max_f - self.min_f

    def row(self) -> str:
        plausible = math.isfinite(self.cur_f) and abs(self.cur_f) < 1e6
        as_float = f"{self.cur_f:>12.5f}" if plausible else f"{'--':>12}"
        lo = f"{self.min_f:>11.4f}" if math.isfinite(self.min_f) else f"{'--':>11}"
        hi = f"{self.max_f:>11.4f}" if math.isfinite(self.max_f) else f"{'--':>11}"
        raw = " ".join(f"{b:02X}" for b in self.cur_raw)
        flag = "  <== MOVING" if self.span > 0.01 and plausible else ""
        return (
            f"  {self.offset:>4} 0x{self.offset:03X} {as_float} {lo} {hi} "
            f"{self.cur_i:>12} {raw}{flag}"
        )


def render(traces: list[FieldTrace], packets: int, ctx: str) -> None:
    lines = [
        "\x1b[H\x1b[2J" if os.name != "nt" else "",
        f"GT7 extended-packet tail probe   packets={packets}",
        f"  live: {ctx}",
        "",
        f"  {'off':>4} {'hex':>5} {'float':>12} {'min':>11} {'max':>11} "
        f"{'int32':>12} raw",
        "  " + "-" * 76,
    ]
    lines.extend(t.row() for t in traces)
    lines.append("")
    lines.append("  Turn the wheel lock to lock - the steering channel is the one marked MOVING")
    lines.append("  with a symmetric range around zero.  Ctrl+C to stop.")
    sys.stdout.write("\n".join(lines) + "\n")
    sys.stdout.flush()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=33741)
    ap.add_argument("--seconds", type=float, default=120.0)
    args = ap.parse_args()

    traces = [FieldTrace(off) for off in range(TAIL_START, TAIL_END, 4)]

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("0.0.0.0", args.port))
    except OSError as exc:
        print(f"bind failed on port {args.port}: {exc}")
        print("Close the Pit Crew app first — it holds the same port.")
        return 1
    sock.settimeout(2.0)

    print(f"listening on 0.0.0.0:{args.port} for {args.seconds:.0f}s ...")

    started = time.monotonic()
    last_render = 0.0
    packets = 0
    short_packets = 0
    ctx = "waiting for packets"

    try:
        while time.monotonic() - started < args.seconds:
            try:
                data, _ = sock.recvfrom(4096)
            except socket.timeout:
                continue

            if len(data) < TAIL_END:
                short_packets += 1
                continue

            if data[0:4] not in VALID_MAGIC:
                try:
                    data = _decrypt(data)
                except Exception:
                    continue
            if data[0:4] not in VALID_MAGIC:
                continue

            packets += 1
            for trace in traces:
                trace.update(data[trace.offset:trace.offset + 4])

            pkt = parse_packet(data)
            if pkt is not None:
                ctx = (
                    f"speed={pkt.speed_kmh:6.1f} km/h  thr={pkt.throttle:4.2f}  "
                    f"brk={pkt.brake:4.2f}  gear={pkt.current_gear}  "
                    f"yaw_rate={pkt.angvel_z:+7.4f}"
                )

            now = time.monotonic()
            if now - last_render > 0.4:
                last_render = now
                render(traces, packets, ctx)
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()

    render(traces, packets, ctx)
    if short_packets:
        print(f"\n  {short_packets} packets were shorter than {TAIL_END} bytes "
              "- this GT7/SimHub combination may not send the extended format.")
    if not packets:
        print("\n  No valid packets received.  Is GT7 sending and SimHub relaying?")
        return 1

    print("\n  Candidates (widest range first):")
    for trace in sorted(traces, key=lambda t: t.span, reverse=True)[:8]:
        print(f"    offset {trace.offset} (0x{trace.offset:03X})  "
              f"range {trace.min_f:+.4f} .. {trace.max_f:+.4f}  span {trace.span:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
