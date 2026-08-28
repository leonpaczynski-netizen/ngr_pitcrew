"""Replay a recorded race through the engineer and print what he would say.

    python tools/replay_race_calls.py --event 6 [--every 1] [--quiet]

**The point is the calls, not the race.** Every lap that was actually driven is
fed to the real `RaceCoordinator`, with the real approved plan and the real
per-lap figures off `laps`, and what comes back is the call it would have made
at that crossing. `--every` sets the heartbeat interval - `1` is the driver's
every-lap setting, `5` is the default - so the same race can be read twice and
the difference is exactly what the setting buys.

It is a read of the archive and it writes nothing. `Store()` is opened
read-only-by-convention here: no method that writes is called, and the race is
replayed into a coordinator built in memory.

What this can and cannot show:

* **It can show the words**, the order, and which lap each one lands on.
* **It cannot show the re-planner.** `assess` runs in the controller, not the
  coordinator, and it is a different question from "what does the heartbeat
  say" - so a box call here is the coordinator's, off the plan, and nothing
  in this harness re-plans the race.
* Fuel per lap is the **race's own measured burn** once five green laps exist,
  exactly as the live path does it, and the plan's figure before that.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pitcrew.race.coordinator import RaceCoordinator, context_from_stored
from pitcrew.race.calls import STATUS
from pitcrew.store.db import Store
from pitcrew.strategy.execution import context_from_event
from pitcrew.telemetry.session_state import EventKind, Lap, SessionEvent


def race_runs(store: Store, event_id: int) -> list[dict]:
    return store._query(
        "SELECT * FROM race_runs WHERE event_id = ? ORDER BY started_at, id",
        (event_id,))


def race_laps(store: Store, run: dict) -> list[dict]:
    """One run's laps.

    **One run, never the event's.** An event accumulates a run per attempt -
    rehearsals, restarts, the race itself - and joining them all on `event_id`
    interleaves four races into one sequence with lap 17 appearing four times
    and the fuel jumping between tanks. That is not a race the engineer could
    ever have seen, and every call read off it would be an artefact.
    """
    return store._query(
        "SELECT * FROM laps WHERE session_id = ? ORDER BY lap_num",
        (run["session_id"],))


def as_event(row: dict) -> SessionEvent:
    return SessionEvent(EventKind.LAP_COMPLETED, {"lap": Lap(
        lap_num=row["lap_num"],
        lap_time_ms=int(row["lap_time_ms"] or 0),
        best_lap_ms=int(row["lap_time_ms"] or 0),
        delta_ms=0,
        fuel_start=row["fuel_start"] if row["fuel_start"] is not None else 0.0,
        fuel_end=row["fuel_end"] if row["fuel_end"] is not None else 0.0,
        fuel_used=row["fuel_used"] if row["fuel_used"] is not None else 0.0,
        position=int(row["position"] or 0),
        is_pit_lap=bool(row["is_pit_lap"]),
        is_out_lap=bool(row["is_out_lap"]))})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--event", type=int, required=True)
    ap.add_argument("--every", type=int, default=1,
                    help="heartbeat interval in laps; 1 is every lap")
    ap.add_argument("--run", type=int, default=None,
                    help="which race run; default is the longest on file")
    ap.add_argument("--quiet", action="store_true",
                    help="only print the laps he actually hears something on")
    args = ap.parse_args()

    store = Store()
    try:
        event = store.get_event(args.event)
        if event is None:
            print(f"no event {args.event}")
            return 1
        approved = store.get_approved_strategy(args.event)
        plan = approved["plan"] if approved else None
        runs = race_runs(store, args.event)
        if not runs:
            print(f"event {args.event} has no recorded race")
            return 1
        if args.run is None:
            # The longest, which is the one most likely to be the race rather
            # than a rehearsal that was stopped after three laps.
            run = max(runs, key=lambda r: len(race_laps(store, r)))
        else:
            run = next((r for r in runs if r["id"] == args.run), None)
            if run is None:
                print(f"event {args.event} has no run {args.run}; "
                      f"runs are {[r['id'] for r in runs]}")
                return 1
        rows = race_laps(store, run)
        if not rows:
            print(f"run {run['id']} recorded no laps")
            return 1

        expects = (plan or {}).get("expects") or {}
        # **The race clock has to advance with the laps, not with the wall.**
        # A replay runs in milliseconds, so a `RaceClock` reading real time
        # believes a 50-minute race has barely started: `laps_remaining()`
        # stays at its opening estimate all race, the fuel target never comes
        # down, and the transcript fills with "25 laps short" - an artefact of
        # the harness that reads exactly like a defect in the engineer. A lap
        # race counts laps and is immune; a timed race is not, and this is the
        # difference between showing the calls and inventing them.
        elapsed = {"s": 0.0}
        race = RaceCoordinator(
            plan,
            fuel_per_lap_l=expects.get("expected_fuel_per_lap_l"),
            fuel_capacity_l=100.0,
            planned_fuel_per_lap_l=expects.get("expected_fuel_per_lap_l"),
            planned_lap_time_ms=expects.get("expected_lap_time_ms"),
            now=lambda: elapsed["s"])
        actual = context_from_event(event)
        stored = (plan or {}).get("context")
        planned = context_from_stored(stored, event) if stored else None
        if not race.arm(planned, actual):
            print(f"plan refused on the grid: {race.refusal}")
            return 1
        race.state.status_every_laps = args.every

        stints = (plan or {}).get("stints") or []
        print(f"{event['name']} - {event['car_name']} - {event['track']}")
        print(f"run {run['id']} of {len(runs)} on file - {len(rows)} laps, "
              f"heartbeat every {args.every} lap"
              f"{'' if args.every == 1 else 's'}")
        print("plan: " + (" / ".join(
            f"{s.get('laps')} laps {s.get('compound') or '?'}"
            for s in stints) or "none"))
        print("-" * 72)

        race.handle(SessionEvent(EventKind.RACE_STARTED, {}))
        spoken = 0
        for row in rows:
            elapsed["s"] += (row["lap_time_ms"] or 0) / 1000.0
            if row["is_pit_lap"]:
                race.handle(SessionEvent(EventKind.PIT_ENTRY, {}))
            call = race.handle(as_event(row))
            if row["is_pit_lap"]:
                race.handle(SessionEvent(EventKind.PIT_EXIT,
                                         {"tyres_changed": True}))
            state = race.state
            fuel = f"{state.fuel_l:5.1f}L" if state.fuel_l is not None else "   --"
            if call is not None:
                spoken += 1
                mark = "heartbeat" if call.kind == STATUS else call.kind
                print(f"lap {row['lap_num']:>2}  {fuel}  {mark:>12} | "
                      f"{call.call} {call.reason}".strip())
                state.record(call)
            elif not args.quiet:
                print(f"lap {row['lap_num']:>2}  {fuel}  {'':>12} | -")
        print("-" * 72)
        print(f"{spoken} calls over {len(rows)} laps")
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main())
