"""Read an M0 capture and emit the constants it supports.

    python tools/analyse_m0.py capture.pcap
    python tools/analyse_m0.py capture.pcap --out data/m0_constants.json

Offline, deterministic and pure: same file in, same bytes out, no wall clock
and no randomness anywhere in the path. Run it twice and diff if you doubt it.

It writes a constants file and prints a summary. **It does not wire anything
into the strategy model** - that is Stage 1 and wants its own review. A
constant this produces is evidence; using it is a decision.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pitcrew.analysis.m0 import analyse, write_constants          # noqa: E402
from pitcrew.telemetry.capture import read_datagrams, read_metadata  # noqa: E402
from pitcrew.telemetry.packet import parse_packet                 # noqa: E402
from pitcrew.telemetry.pit_detect import Sample                   # noqa: E402


def samples_from_capture(path):
    """Parse every datagram, and say so loudly when they do not parse.

    A capture that silently yields nothing looks exactly like a race with no
    pit stops, and would produce an empty constants file rather than an error.
    """
    samples, capacity, seen, failed = [], None, set(), 0
    for datagram in read_datagrams(path):
        packet = parse_packet(datagram.data)
        if packet is None:
            failed += 1
            continue
        seen.add(packet.packet_format or f"{len(datagram.data)}B")
        if capacity is None and packet.fuel_capacity:
            capacity = packet.fuel_capacity
        samples.append(Sample(
            t_s=datagram.t_s,
            speed_kph=packet.speed_kmh,
            fuel_l=packet.fuel_level,
            on_track=packet.car_on_track,
            lap=packet.laps_completed,
            temps=packet.tyre_temps,
            road_distance_m=packet.road_distance,
            position=packet.current_position,
        ))
    return samples, capacity, seen, failed


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--out", type=Path, default=None,
                        help="where to write the constants (default: "
                             "alongside the capture)")
    args = parser.parse_args(argv)

    metadata = read_metadata(args.capture)
    samples, capacity, formats, failed = samples_from_capture(args.capture)

    if not samples:
        print(f"No packet in {args.capture} parsed. Nothing to measure.",
              file=sys.stderr)
        return 2
    if failed:
        print(f"WARNING: {failed} of {failed + len(samples)} datagrams failed "
              f"to parse.", file=sys.stderr)
    if len(formats) > 1:
        print(f"WARNING: mixed packet formats in one capture: "
              f"{sorted(formats)}", file=sys.stderr)

    result = analyse(samples, capacity_l=capacity)
    out = args.out or args.capture.with_suffix(".m0.json")
    write_constants(result, out)

    print(f"capture:  {args.capture}  ({len(samples)} packets, "
          f"format {'/'.join(sorted(formats))})")
    if metadata:
        print(f"recorded: {metadata}")
    print()
    print(result.summary())
    print()
    print(f"constants written to {out}")
    print("NOT wired into the strategy model - that is Stage 1.")
    return 1 if result.void else 0


if __name__ == "__main__":
    raise SystemExit(main())
