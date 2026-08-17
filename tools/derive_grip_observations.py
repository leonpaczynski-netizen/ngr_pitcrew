"""Derive grip observations from sessions already on disk.

    python tools/derive_grip_observations.py                 # report, change nothing
    python tools/derive_grip_observations.py --apply         # write the rows
    python tools/derive_grip_observations.py --session 19    # one session
    python tools/derive_grip_observations.py --event 1       # one event
    python tools/derive_grip_observations.py --db path       # against a copy first

**No new capture path. Nothing on the telemetry thread.** `CLAUDE.md` §6 kept
the raw stream on disk so a stored session could be re-aggregated after a
detector was fixed, and this is that: every figure the tyre model rests on was
computed from frames that were already there, with no extra laps driven.

**Idempotent and versioned.** A second run at the same `DERIVATION_VERSION`
replaces its own rows and leaves every other version untouched, so a fitted
model can always resolve the exact observations behind it. Change the
derivation and bump the version; never patch a stored row.

It reports before it writes, writes nothing without `--apply`, and touches no
existing table. In particular **`laps` is never written** - `lap_frames`
cascades off it, and this tool only ever reads.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pitcrew.analysis.grip import (                            # noqa: E402
    DERIVATION_VERSION,
    derive_event,
    event_car_key,
    event_circuit_key,
)
from pitcrew.store.db import DEFAULT_DB_PATH, Store            # noqa: E402


def _report(store, reports: list) -> None:
    for report in reports:
        print()
        for line in _describe(store, report):
            print(line)


def _describe(store, report) -> list[str]:
    lines: list[str] = []
    lap_rows = report.lap_rows
    if not lap_rows:
        return ["  nothing derivable"]

    by_session: dict[int, list[dict]] = defaultdict(list)
    for row in lap_rows:
        by_session[row["session_id"]].append(row)

    lines.append(f"  {report.summary()}")
    for circuit, anchors in report.anchors.items():
        moved = [a for a in anchors.values() if a.apex_m_observed is not None]
        unstable = [a.corner_id for a in anchors.values() if not a.stable]
        lines.append(
            f"  apex anchors, {circuit}: {len(moved)} of {len(anchors)} corners "
            f"re-anchored on the observed apex"
            + (f"; identity UNSTABLE at {', '.join(unstable)} "
               f"(observations written, not counted)" if unstable else ""))
    for session_id in sorted(by_session):
        rows = by_session[session_id]
        counted = [r for r in rows if r["counts_toward_fit"]]
        reasons = Counter(r["exclusion_reason"] for r in rows
                          if not r["counts_toward_fit"])
        grips = [r["grip_g"] for r in counted if r["grip_g"] is not None]
        level = (f"mean comb_p95 {sum(grips) / len(grips):.4f}"
                 if grips else "no observable")
        sources = sorted({r["yaw_source"] for r in rows})
        lines.append(
            f"    s{session_id}: {len(counted)}/{len(rows)} push laps, "
            f"{level}, yaw {'+'.join(sources)}"
            + (f", excluded {dict(reasons)}" if reasons else ""))
    for skip in report.skipped:
        lines.append(f"    skipped {skip}")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--apply", action="store_true",
                        help="write the observations; without it, report only")
    parser.add_argument("--event", type=int, action="append",
                        help="restrict to one event id; repeatable")
    parser.add_argument("--session", type=int, action="append",
                        help="restrict to one session id; repeatable")
    parser.add_argument("--derivation-version", type=int,
                        default=DERIVATION_VERSION)
    args = parser.parse_args()

    store = Store(args.db)
    sessions = set(args.session) if args.session else None
    events = [e for e in store.list_events()
              if args.event is None or e["id"] in set(args.event)]

    reports = []
    for event in events:
        if sessions is not None and not any(
                s["id"] in sessions for s in store.list_sessions(event["id"])):
            continue
        print(f"{event['name']} - {event_circuit_key(event)} / "
              f"{event_car_key(event)}", flush=True)
        report = derive_event(store, event, session_ids=sessions,
                              derivation_version=args.derivation_version)
        reports.append(report)
        _report(store, [report])

    total = sum(len(r.rows) for r in reports)
    laps = sum(len(r.lap_rows) for r in reports)
    counted = sum(len(r.counted_lap_rows) for r in reports)
    skipped = sum(len(r.skipped) for r in reports)
    print(f"\n{total} observation(s) from {laps} lap(s), {counted} counting "
          f"toward a fit, {skipped} lap(s) skipped for want of frames.")

    if not args.apply:
        print("Nothing written. Re-run with --apply.")
        return 0

    written = 0
    for report in reports:
        written += store.write_grip_observations(report.rows)
    print(f"{written} row(s) written to {args.db} at derivation version "
          f"{args.derivation_version}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
