"""Pour one race's rival and gap record into a checked-in test fixture.

    python tools/extract_race_comms_fixture.py --session 176

Writes `pitcrew/tests/fixtures/race_comms_s<session>.json`: the laps, every
`gap_reads` row with its moment on the race clock, the filed `rival_stops`,
the stored `board_positions`, the event's pit and stop rules and the approved
plan's stints. `test_race_comms_bathurst.py` replays George's volunteered
radio from it through the coordinator.

**Read-only against the database** (`mode=ro`), and the database is
gitignored, so the fixture is what makes the replay a test anybody can run
(CLAUDE.md §7: a recorded session file is the test fixture).

### The one conversion, and how it is made

`gap_reads.at_s` is the pit wall's monotonic clock; everything else on file is
wall-clock time. Each lap's readings were filed at the crossing that closed the
lap they were taken on, so every reading of read-key k lies between the
crossing that ended lap k and the one that ended lap k + 1. That bounds the
offset from both sides on every lap; the offset used is the midpoint of the
tightest pair, and the script refuses when the bounds cross (session 176:
39913.14-39913.77 s, so the moment of every reading is known to a third of a
second).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DB = REPO / "data" / "pitcrew.db"
OUT = REPO / "pitcrew" / "tests" / "fixtures"


def _clock(stamp: str) -> float:
    moment = datetime.fromisoformat(stamp)
    return moment.hour * 3600 + moment.minute * 60 + moment.second


def monotonic_offset(db, sid: int):
    """`(offset, lo, hi, green)` placing `gap_reads.at_s` on the wall clock.

    Wall-clock seconds of the day for a reading are `at_s + offset`; `green`
    is the race's green on the same clock. Raises `ValueError` saying why
    where it cannot be placed. Shared with `tools/split_slot_handles.py`, so
    the one conversion is made one way.
    """
    laps = [dict(zip(("lap_num", "race_elapsed_s", "recorded_at"), row))
            for row in db.execute(
                "SELECT lap_num, race_elapsed_s, recorded_at FROM laps "
                "WHERE session_id = ? ORDER BY lap_num", (sid,))]
    if not laps:
        raise ValueError(f"no laps for session {sid}")
    # The green, on the wall clock: each crossing's filing time less the race
    # clock at it. The earliest is the one least delayed by the filing.
    timed = [_clock(lap["recorded_at"]) - lap["race_elapsed_s"]
             for lap in laps if lap["race_elapsed_s"] is not None]
    if not timed:
        raise ValueError(f"no race clock on the laps of session {sid}")
    green = min(timed)
    crossing = {0: green}
    for lap in laps:
        if lap["race_elapsed_s"] is not None:
            crossing[lap["lap_num"]] = green + lap["race_elapsed_s"]

    lower, upper = [], []
    for key, first, last in db.execute(
            "SELECT lap, MIN(at_s), MAX(at_s) FROM gap_reads "
            "WHERE session_id = ? GROUP BY lap", (sid,)):
        if key in crossing and key + 1 in crossing:
            lower.append(crossing[key] - first)
            upper.append(crossing[key + 1] - last)
    if not lower:
        raise ValueError(f"no gap reads for session {sid}")
    lo, hi = max(lower), min(upper)
    if lo > hi:
        raise ValueError(f"the monotonic offset bounds cross ({lo:.2f} > "
                         f"{hi:.2f}) - the readings cannot be placed on the "
                         f"race clock")
    return (lo + hi) / 2.0, lo, hi, green


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", type=int, required=True)
    parser.add_argument("--db", default=str(DB))
    args = parser.parse_args()

    db = sqlite3.connect(f"file:{Path(args.db).as_posix()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    sid = args.session

    laps = [dict(row) for row in db.execute(
        "SELECT lap_num, lap_time_ms, fuel_start, fuel_end, fuel_used, "
        "position, is_pit_lap, is_out_lap, excluded, exclusion_reason, "
        "off_track_s, laps_completed, race_elapsed_s, recorded_at "
        "FROM laps WHERE session_id = ? ORDER BY lap_num", (sid,))]
    try:
        offset, lo, hi, green = monotonic_offset(db, sid)
    except ValueError as exc:
        print(exc)
        return 1

    reads = [{"race_s": round(row["at_s"] + offset - green, 3),
              "key": row["lap"], "side": row["side"], "gap_s": row["gap_s"],
              "subject": row["subject"], "row": row["position"]}
             for row in db.execute(
                 "SELECT at_s, lap, side, gap_s, subject, position "
                 "FROM gap_reads WHERE session_id = ? ORDER BY at_s", (sid,))]
    stops = [dict(row) for row in db.execute(
        "SELECT driver, lap, fuel_in_l, fuel_out_l, partial, recorded_at "
        "FROM rival_stops WHERE session_id = ? ORDER BY id", (sid,))]
    for stop in stops:
        stop["filed_race_s"] = round(_clock(stop.pop("recorded_at")) - green, 1)
    board = [dict(row) for row in db.execute(
        "SELECT lap, driver, position FROM board_positions "
        "WHERE session_id = ? ORDER BY lap, position", (sid,))]
    session = db.execute("SELECT event_id FROM sessions WHERE id = ?",
                         (sid,)).fetchone()
    event = dict(db.execute(
        "SELECT race_laps, mandatory_stops, pit_loss_secs, pit_loss_source, "
        "refuel_rate_lps FROM events WHERE id = ?",
        (session["event_id"],)).fetchone())
    run = db.execute("SELECT strategy_id FROM race_runs WHERE session_id = ?",
                     (sid,)).fetchone()
    stints = []
    if run is not None and run["strategy_id"] is not None:
        plan = json.loads(db.execute(
            "SELECT plan_json FROM strategies WHERE id = ?",
            (run["strategy_id"],)).fetchone()["plan_json"])
        stints = [{k: v for k, v in stint.items()
                   if k in ("laps", "start_lap", "compound", "fuel_l", "tyres")}
                  for stint in plan.get("stints") or ()]
    for lap in laps:
        lap.pop("recorded_at")

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"race_comms_s{sid}.json"
    path.write_text(json.dumps({
        "session": sid,
        "green_clock_s": round(green, 1),
        "monotonic_offset_s": round(offset, 3),
        "monotonic_offset_bounds_s": [round(lo, 3), round(hi, 3)],
        "event": event,
        "stints": stints,
        "laps": laps,
        "gap_reads": reads,
        "rival_stops": stops,
        "board_positions": board,
    }, indent=1) + "\n", encoding="utf-8")
    print(f"{path}: {len(laps)} laps, {len(reads)} gap reads, "
          f"{len(stops)} stops, {len(board)} board rows; offset "
          f"{offset:.3f} s in [{lo:.3f}, {hi:.3f}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
