"""Bests and like-for-like gaps per compound, on the lap and each sector - plan row 5.22.

    python tools/compound_pace.py 11
    python tools/compound_pace.py 11 --reference RH
    python tools/compound_pace.py 11 14 --db copy.db     # one car and circuit, two events

Reads only - apart from the schema upgrade every `Store()` makes when it opens
a file (`references/mechanic.md`). Every rule the figures obey is in
`pitcrew/analysis/compound_pace.py`: a best is the fastest lap on the tyre and
is never subtracted to make a gap; a gap is off comparable laps only, or it is
refused with the reason.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pitcrew.analysis.compound_pace import (  # noqa: E402
    TIMINGS,
    compound_pace,
    sitting_line,
    sittings,
)
from pitcrew.export.build import event_lap_inputs, mark_incidents  # noqa: E402
from pitcrew.store.db import Store  # noqa: E402


def lap_clock(ms: int | None) -> str:
    if ms is None:
        return "-"
    minutes, rest = divmod(int(ms), 60_000)
    return f"{minutes}:{rest / 1000:06.3f}" if minutes else f"{rest / 1000:.3f}"


def load(store, event_ids: list[int]) -> tuple[list, dict, str | None]:
    """One car at one circuit in the order driven, its evenings - or a refusal."""
    laps, identity, evenings = [], None, {}
    for event_id in event_ids:
        event = store.get_event(event_id)
        if event is None:
            return [], {}, f"No event {event_id}."
        these = (event.get("car_name"), event.get("track"), event.get("layout"))
        if identity is not None and these != identity:
            return [], {}, (f"Event {event_id} is {these}, not {identity} - a best "
                        f"is one car at one circuit.")
        identity = these
        laps.extend(event_lap_inputs(store, event_id, hydrate=set()))
        evenings.update(sittings(store.list_sessions(event_id)))
    marked, _ = mark_incidents(laps)
    return marked, evenings, None


def render(pace) -> None:
    groups = []
    for best in pace.bests:
        key = (best.game_version, best.sector_model)
        if key not in groups:
            groups.append(key)
    for version, model in groups:
        print(f"\n== {version or 'unknown version'} - sectors {model}")
        print("  BESTS (the fastest lap on the tyre, n = laps it was the best of; "
              "each sector's best from any lap)")
        print(f"  {'tyre':<5}{'best lap':>10}{'n':>4}  {'best S1':>9}{'best S2':>9}"
              f"{'best S3':>9}   {'added up*':>12}")
        for best in sorted((b for b in pace.bests
                            if (b.game_version, b.sector_model) == (version, model)),
                           key=lambda b: b.lap_ms):
            # Sectors as seconds, as the Practice plate prints them - a 64 s
            # sector as 1:04.126 ran into the column before it (critic pass 3).
            s1, s2, s3 = (f"{value / 1000:.3f}" for value in best.sectors_ms)
            print(f"  {best.compound:<5}{lap_clock(best.lap_ms):>10}{best.laps:>4}  "
                  f"{s1:>9}{s2:>9}{s3:>9}   "
                  f"{lap_clock(best.theoretical_ms):>12}")
        print("  * derived: the three best sectors on that tyre added up - "
              "a lap nobody drove")
        these = [g for g in pace.gaps
                 if (g.game_version, g.sector_model) == (version, model)]
        if these:
            print("\n  GAPS on like-for-like laps - the first laps of each run, "
                  "one fuel band, back-to-back\n  sessions; the median against "
                  "the median, + is slower. Not used by the race plan.")
            for sitting in dict.fromkeys(g.sitting for g in these):
                on = [g for g in these if g.sitting == sitting]
                sessions = sorted({s for g in on for s in g.sessions},
                                  key=lambda s: (s is None, s or 0))
                print(f"\n  {sitting} (sessions "
                      f"{', '.join(str(s) for s in sessions)})")
                for code in sorted({g.compound for g in on}):
                    row = {g.timing: g for g in on if g.compound == code}
                    print(f"    {sitting_line(on, code, sitting)}")
                    for name in TIMINGS:
                        gap = row.get(name)
                        if gap is not None:
                            print(f"        {gap.describe()}")
    for line in pace.across_sittings():
        print(f"\n  replicated: {line}")
    for line in pace.refusals:
        print(f"\n  refused: {line}")
    print(f"\n  not in any row: {pace.untagged} counted lap"
          f"{'' if pace.untagged == 1 else 's'} with no compound, "
          f"{pace.without_sectors} tagged but without all three sectors")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("event_ids", type=int, nargs="+")
    parser.add_argument("--reference", default=None,
                        help="the compound gaps are measured against "
                             "(default: the hardest compound present)")
    parser.add_argument("--db", default=None, help="a different archive")
    args = parser.parse_args()
    store = Store(args.db) if args.db else Store()
    try:
        laps, evenings, refused = load(store, args.event_ids)
        if refused:
            print(refused)
            return 1
        render(compound_pace(laps, args.reference, sitting_of=evenings))
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
