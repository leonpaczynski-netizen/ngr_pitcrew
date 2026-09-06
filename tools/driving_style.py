"""How a session was driven, lap by lap and per stint - coast share and upshift rpm.

    python tools/driving_style.py --session 138
    python tools/driving_style.py --session 138 --stints

The Deep Forest race (6 Sep 2026), decomposed after the fact, was the case
for this: stint 1 burned 7.32 L/lap with 8.3% of the lap off both pedals and
upshifts at 8298; stint 2 early 7.79 at 6.1% and 8297; stint 2 late 8.01 at
6.0% and 8694. Two clean steps, two different mechanisms, both in the
archive - and `laps.short_shift_rpm` read 0.0 throughout because it records
the app's switch, not his hand. Read-only.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pitcrew.analysis.driving import read_frames  # noqa: E402
from pitcrew.store.db import Store  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", type=int, required=True)
    ap.add_argument("--stints", action="store_true",
                    help="summarise per stint (a pit or out lap closes one)")
    args = ap.parse_args()

    store = Store()
    try:
        rows = store.list_laps(args.session)
        if not rows:
            print(f"session {args.session} has no laps")
            return 1
        print(f"session {args.session}: {len(rows)} laps")
        print(f"{'lap':>3} {'time':>8} {'burn':>6} {'coast%':>7} {'flat%':>6} "
              f"{'upshift':>8} {'n':>3}  note")
        stint, stints, prev_pit = 1, {}, False
        for row in rows:
            frames = store.get_lap_frames(row["id"])
            read = read_frames((frames or {}).get("frames") or [])
            pit = bool(row.get("is_pit_lap")) or bool(row.get("is_out_lap"))
            note = ("pit" if row.get("is_pit_lap") else
                    "out" if row.get("is_out_lap") else "")
            print(f"{row['lap_num']:>3} {(row['lap_time_ms'] or 0) / 1000:8.3f} "
                  f"{(row.get('fuel_used') or 0):6.2f} "
                  f"{'--' if read.coast_pct is None else read.coast_pct:>7} "
                  f"{'--' if read.full_throttle_pct is None else read.full_throttle_pct:>6} "
                  f"{'--' if read.upshift_rpm is None else read.upshift_rpm:>8} "
                  f"{read.upshifts:>3}  {note}")
            if pit:
                if row.get("is_pit_lap") or not prev_pit:
                    stint += 1
                prev_pit = True
                continue
            prev_pit = False
            if row["lap_num"] > 1 and read.coast_pct is not None:
                stints.setdefault(stint, []).append((row, read))
        if args.stints:
            print("-" * 60)
            print(f"{'stint':>5} {'laps':>4} {'burn':>6} {'coast%':>7} {'flat%':>6} "
                  f"{'upshift':>8}")
            for number, pairs in sorted(stints.items()):
                burns = [r.get("fuel_used") for r, _ in pairs if (r.get("fuel_used") or 0) > 0]
                ups = [d.upshift_rpm for _, d in pairs if d.upshift_rpm is not None]
                print(f"{number:>5} {len(pairs):>4} "
                      f"{median(burns) if burns else float('nan'):6.2f} "
                      f"{median(d.coast_pct for _, d in pairs):7.1f} "
                      f"{median(d.full_throttle_pct for _, d in pairs):6.1f} "
                      f"{median(ups) if ups else float('nan'):8.0f}")
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main())
