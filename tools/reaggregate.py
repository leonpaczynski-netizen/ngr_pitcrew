"""Re-read stored sessions for the stops the app could not see when it recorded them.

    python tools/reaggregate.py              # report what it would change
    python tools/reaggregate.py --apply      # write the flags back
    python tools/reaggregate.py --db path    # against a copy first, if you like

Reports before it writes, and writes nothing without `--apply`. It sets flags
only: no lap is deleted, no lap time is touched, and no frame blob is
rewritten. See `pitcrew/analysis/reaggregate.py` for why this exists.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pitcrew.analysis.reaggregate import read_session          # noqa: E402
from pitcrew.store.db import DEFAULT_DB_PATH, Store            # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--apply", action="store_true",
                        help="write the flags back; without it, report only")
    args = parser.parse_args()

    store = Store(args.db)
    findings = []
    for event in store.list_events():
        for session in store.list_sessions(event["id"], "practice"):
            laps = store.list_laps(session["id"])
            if not laps:
                continue

            def frames_for(lap_id: int):
                stored = store.get_lap_frames(lap_id)
                return stored["frames"] if stored else None

            for lap in laps:
                stored = store.get_lap_frames(lap["id"])
                lap["sample_hz"] = stored["sample_hz"] if stored else 60.0
            findings.extend(read_session(laps, frames_for))

    if not findings:
        print("Nothing to change: no stop in any stored session.")
        return 0

    for finding in findings:
        print(" ", finding.describe())
    pits = sum(1 for f in findings if f.is_pit_lap)
    outs = sum(1 for f in findings if f.is_out_lap)
    print(f"\n{pits} pit lap(s), {outs} out-lap(s) across the stored sessions.")

    if not args.apply:
        print("Nothing written. Re-run with --apply.")
        return 0

    for finding in findings:
        store.set_lap_flags(finding.lap_id, **finding.changes)
    print(f"Written to {args.db}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
