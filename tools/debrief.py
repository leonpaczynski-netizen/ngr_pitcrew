"""Print the practice debrief for an event.

    python tools/debrief.py 10
    python tools/debrief.py 10 --sessions 113 114 115

Reads only. Nothing here writes to the database.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Windows consoles default to cp1252 and this prints em dashes and arrows.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pitcrew.analysis.debrief import (  # noqa: E402
    CLEAN_OFF_TRACK_S,
    MIN_GEAR_ARM,
    from_store,
)
from pitcrew.store.db import Store  # noqa: E402

RULE = "-" * 72


def _ms(value) -> str:
    if value is None:
        return "—"
    return f"{value / 1000.0:.3f} s"


def _head(text: str) -> None:
    print(f"\n{text}\n{RULE}")


def render(debrief) -> None:
    _head("SESSION")
    print(f"  {debrief.census.describe()}")

    pace, burn = debrief.pace, debrief.burn
    print(f"  pace     median {_ms(pace.median_ms)}   best {_ms(pace.best_ms)}"
          f"   sd {_ms(pace.sd_ms)}   (n={pace.n})")
    if burn.median_l is not None:
        spread = f"± {burn.sd_l:.2f}" if burn.sd_l is not None else "spread —"
        print(f"  fuel     {burn.median_l:.2f} L/lap {spread}   (n={burn.n})")
    else:
        print("  fuel     — no lap burned a measurable amount")

    _head("CONSISTENCY — where you are least repeatable")
    if not debrief.scatter:
        print("  no corner was reached on enough laps to say.")
    for row in debrief.scatter:
        sd = f"{row.sd_kph:5.1f}" if row.sd_kph is not None else "    —"
        cov = f"{row.cov_pct:5.2f}%" if row.cov_pct is not None else "     —"
        print(f"  {row.corner_id:<4} {row.corner_name:<12} "
              f"min {row.mean_kph:6.1f} km/h   sd {sd} km/h  {cov}"
              f"   carries {row.carry_m:5.0f} m   (n={row.n})")
    worst = debrief.least_repeatable
    if worst is not None and worst.sd_kph is not None:
        print(f"\n  → {worst.corner_name} is your least repeatable corner "
              f"({worst.sd_kph:.1f} km/h). It carries {worst.carry_m:.0f} m.")
        print("    This needs no reference lap and no teammate: do the same "
              "thing there twice.")

    _head("GEAR — the A/Bs you have already run")
    if not debrief.gears:
        print("  you took every corner in the same gear on every lap. "
              "Nothing to compare.")
    for split in debrief.gears:
        best = split.quickest
        print(f"  {split.corner_id:<4} {split.corner_name}")
        for arm in split.arms:
            mark = " <-" if best is not None and arm.gear == best.gear else "  "
            print(f"      G{arm.gear}  n={arm.n:<3} "
                  f"min {arm.mean_min_kph:6.1f} km/h   "
                  f"lap {_ms(arm.mean_lap_ms)}{mark}")
        if split.balanced:
            print(f"      balanced — both arms have {MIN_GEAR_ARM}+ laps. "
                  "Worth acting on.")
        else:
            print("      UNBALANCED — a hypothesis to test, not a finding.")
    if debrief.gears:
        print("\n  Apex gear is partly an EFFECT of entry speed: arrive slowly "
              "and you\n  end up a gear lower, so the gear did not cause the "
              "slow lap. To break\n  that, choose the gear deliberately — five "
              "laps each way, same intent.")

    _head("CORNERS THAT PREDICT THE LAP")
    spoken = debrief.spoken
    if not spoken:
        print("  none clears significance. See SILENCES.")
    for found in spoken:
        way = "quicker when faster" if found.r < 0 else "quicker when slower"
        print(f"  {found.corner_id:<4} {found.corner_name:<12} "
              f"r={found.r:+.2f}  p={found.p:.3f}  n={found.n}   {way} here")

    if debrief.video:
        _head("VIDEO — where to look")
        # Grouped by file. An event spans several sessions and each has its own
        # capture, so a flat list under one filename sends you to the right
        # timecode in the wrong recording.
        by_file: dict[str, list] = {}
        for cue in debrief.video:
            by_file.setdefault(cue.path, []).append(cue)
        for path, cues in by_file.items():
            print(f"  {Path(path).name}")
            for cue in cues[:6]:
                mins, secs = divmod(max(0.0, cue.second), 60)
                print(f"    lap {cue.lap_num:<3} {cue.corner_id}   "
                      f"{int(mins):02d}:{secs:05.2f}")
            if len(cues) > 6:
                print(f"    … and {len(cues) - 6} more")
        print("\n  Seek rests on integrated lap distance, unreliable on 8-12% "
              "of laps.\n  Somewhere to look, not a frame-accurate claim.")

    _head("SILENCES — what I could not see")
    if not debrief.silences:
        print("  nothing was withheld.")
    for line in debrief.silences:
        print(f"  - {line}")
    for note in debrief.notes:
        print(f"\n  {note}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("event_id", type=int)
    parser.add_argument("--sessions", type=int, nargs="*", default=None,
                        help="limit to these session ids")
    args = parser.parse_args()

    debrief = from_store(Store(), args.event_id, session_ids=args.sessions)
    if debrief is None:
        print(f"No debrief for event {args.event_id}: no corner model for the "
              f"circuit, or no practice laps.\nA model is built from your own "
              f"laps — see pitcrew/analysis/resolve.py.")
        return 1
    render(debrief)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
