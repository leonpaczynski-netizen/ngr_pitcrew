"""Re-cut stored laps into sectors after the catalogue changes.

**The caller the v15 migration could not be.** `Store._upgrade` skips any
migration at or below the file's `user_version`, so the back-fill that ran once
can never run again — which made the design's central promise false: adding two
numbers to `lap_sectors.SECTOR_LINES` did not make the stored laps at that
circuit appear on the rack, it only changed the laps recorded afterwards, and
the rack then held two stamps for one event with no path back.

Run it after editing `SECTOR_LINES`:

    python tools/derive_sectors.py                 # laps with no sectors yet
    python tools/derive_sectors.py --restamp       # also re-cut moved lines
    python tools/derive_sectors.py --dry-run       # say what would change

`--restamp` is what you want when you *improve* an entry rather than add one —
a circuit moving from `thirds` to a real timing line, or Spa's S2 getting the
published figure the catalogue note says it is still missing. Without it a lap
already carrying a stamp is left alone.

It decodes one 400 KB blob per lap it re-cuts, so a whole-archive restamp is
about 40 ms a lap. Without `--restamp` a lap whose stamp already matches the
current model is skipped without decoding; **with it every lap is decoded**,
because the stamp records the LINES and not the gate - tightening
`lap_sectors.SPAN_RATIO` leaves every stamp identical while changing which
laps are admissible. Only laps whose stored times actually change are counted
as written.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pitcrew.store.db import DEFAULT_DB_PATH, Store        # noqa: E402
from pitcrew.store.schema import derive_sectors            # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=str(DEFAULT_DB_PATH))
    parser.add_argument(
        "--restamp", action="store_true",
        help="also re-cut laps whose stored lines no longer match the model")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="report what would change and write nothing")
    args = parser.parse_args()

    store = Store(args.database)
    try:
        conn = store._conn                       # noqa: SLF001 - a tool
        before = conn.execute(
            "SELECT COUNT(*) FROM laps WHERE sector1_ms IS NOT NULL"
        ).fetchone()[0]
        total = conn.execute(
            "SELECT COUNT(*) FROM laps l JOIN lap_frames f ON f.lap_id = l.id"
        ).fetchone()[0]
        print(f"{before} of {total} laps with frames carry sector times")

        if args.dry_run:
            # **A dry run still has to do the work to know the answer** — a
            # lap is only written when the model actually cuts it, and whether
            # it cuts depends on the frames. So it runs inside a transaction
            # that is rolled back rather than being guessed at from the stamps.
            conn.execute("BEGIN")
            written = derive_sectors(conn, restamp=args.restamp)
            conn.execute("ROLLBACK")
            print(f"would write {written} laps (nothing was changed)")
            return 0

        with store._write() as writing:          # noqa: SLF001 - a tool
            written = derive_sectors(writing, restamp=args.restamp)
        after = conn.execute(
            "SELECT COUNT(*) FROM laps WHERE sector1_ms IS NOT NULL"
        ).fetchone()[0]
        print(f"wrote {written} laps; {after} of {total} now carry sectors")
        for stamp, count in conn.execute(
                "SELECT sector_model, COUNT(*) FROM laps "
                "WHERE sector_model IS NOT NULL "
                "GROUP BY sector_model ORDER BY COUNT(*) DESC"):
            print(f"  {count:5}  {stamp}")
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
