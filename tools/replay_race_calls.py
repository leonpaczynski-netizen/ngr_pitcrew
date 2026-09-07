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
* **It CAN show the in-box "Fuel to N" (since 7 Sep 2026).** The pit lap's and
  the out-lap's own frames are read off `lap_frames`, the fill is found where
  the tank rises at walking pace, and the real `RefuelWatch` is driven over
  those frames with the coordinator's state as it stood - in the order the
  line and the box actually came. At Daytona and Spa the crossing is inside
  the lane before the fill; at Deep Forest and Monza it is after. The harness
  used to hand PIT_ENTRY / lap / PIT_EXIT in one fixed order and could not
  see the difference, which is the one the fill depends on.
* **It CAN show the gap calls, from the next race on (7 Sep 2026).** The
  wall's readings are persisted in `gap_reads` with the road position each
  was taken at, and `--gaps` feeds them back lap by lap: the trend to the car
  ahead, and the lap's samples into the sector map, so `SECTOR_SPLIT` and
  the `UNDERCUT` replay exactly as they were - or were not - made. Races
  recorded before the table existed have nothing to replay, and the harness
  says so rather than running silent. The rival STOPS are still not fed.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pitcrew.analysis.resolve import circuit_key
from pitcrew.race.coordinator import RaceCoordinator, context_from_stored
from pitcrew.race.gaps import GapTrend
from pitcrew.race.calls import (STATUS, fuel_target_basis, fuel_target_l,
                                fuel_to_flag_l)
from pitcrew.race.refuel import FILL_MAX_KPH, RefuelWatch
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


def _frames(store: Store, row: dict) -> list[dict]:
    """The 60 Hz frames of one lap, or nothing where none were kept."""
    try:
        stored = store.get_lap_frames(row["id"])
    except Exception:                                        # noqa: BLE001
        return []
    return list((stored or {}).get("frames") or [])


def _fill_frames(frames: list[dict]) -> list[dict]:
    """The frames of a fill: walking pace, from the first rise in the tank."""
    slow = [f for f in frames
            if f.get("fuel_l") is not None
            and (f.get("speed_kph") or 0.0) <= FILL_MAX_KPH]
    if not slow:
        return []
    low = min(f["fuel_l"] for f in slow)
    rising = [f for f in slow if f["fuel_l"] > low + 0.05]
    return slow if rising else []


def replay_stop(race, watch: RefuelWatch, frames: list[dict], lap_num: int,
                out) -> None:
    """Drive the refuel watch over a fill's frames and print what it said."""
    for frame in frames:
        target = fuel_target_l(race.state)
        basis = fuel_target_basis(race.state)
        call = watch.note(frame.get("fuel_l"), speed_kph=frame.get("speed_kph"),
                          target_l=target, fuel_per_lap_l=race.state.fuel_per_lap_l,
                          to_flag_l=fuel_to_flag_l(race.state), basis=basis)
        if call is not None:
            out(f"lap {lap_num:>2}  {frame.get('fuel_l', 0):5.1f}L  "
                f"{'box':>12} | {call.call} {call.reason}".strip())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--event", type=int, required=True)
    ap.add_argument("--every", type=int, default=1,
                    help="heartbeat interval in laps; 1 is every lap")
    ap.add_argument("--run", type=int, default=None,
                    help="which race run; default is the longest on file")
    ap.add_argument("--quiet", action="store_true",
                    help="only print the laps he actually hears something on")
    ap.add_argument("--gaps", action="store_true",
                    help="feed the wall's persisted gap reads back, lap by lap")
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
            mandatory_stops=int(event["mandatory_stops"] or 0),
            now=lambda: elapsed["s"])
        actual = context_from_event(event)
        stored = (plan or {}).get("context")
        planned = context_from_stored(stored, event) if stored else None
        if not race.arm(planned, actual):
            print(f"plan refused on the grid: {race.refusal}")
            return 1
        race.state.status_every_laps = args.every

        reads_by_lap: dict[int, list[dict]] = {}
        if args.gaps:
            session_id = run["session_id"]
            reads = store.gap_reads(session_id, side="ahead") if session_id else []
            if not reads:
                print("no gap reads on file for this run - the wall kept none "
                      "(recorded before 7 Sep 2026?)")
            for read in reads:
                if read["lap"] is not None:
                    reads_by_lap.setdefault(int(read["lap"]), []).append(read)
            key = circuit_key(event["track"], event["layout"]) \
                if event["track"] else None
            model = store.sector_model(key) if key else None
            race.note_circuit(store.layout_length_m(key) if key else None,
                              sector_cuts_m=(model.lines_m if model else None))
        trend = GapTrend(side="ahead")

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
        by_num = {r["lap_num"]: r for r in rows}
        for row in rows:
            elapsed["s"] += (row["lap_time_ms"] or 0) / 1000.0
            # **Stored under laps COMPLETED**, so the reads taken while lap
            # N was being driven carry N-1 - and the trend's figure for the
            # lap is the LAST read, as the live wall overwrites per lap.
            #
            # **`lap_now()`, not `lap_num - 1`.** The counter the wall files
            # under carries `laps_missed()`, so a crossing lost in the pit
            # lane shifts every key after it and a fixed subtraction drifts
            # from there to the flag. Read off the coordinator before the
            # crossing is handed to it, this is the value the wall would have
            # been using. The coordinator re-keys it back the same way.
            key = race.state.lap_now()
            reads = reads_by_lap.get(int(key)) or []
            if reads:
                subject = reads[-1]["subject"]
                trend.note(int(key), reads[-1]["gap_s"], subject=subject)
                race.note_gaps(
                    ahead=trend, ahead_name=subject,
                    ahead_samples=[(r["track_m"], r["gap_s"]) for r in reads
                                   if r["track_m"] is not None])
            if row["is_pit_lap"]:
                # **The order the line and the box actually came.** A fill
                # inside the pit lap's own frames precedes the crossing (Deep
                # Forest, Monza); a fill inside the out-lap's frames follows
                # it (Daytona, Spa). The coordinator's `crossed_in_box` and
                # the fill's lap count depend on exactly this.
                pit_frames = _fill_frames(_frames(store, row))
                following = by_num.get(row["lap_num"] + 1)
                out_frames = (_fill_frames(_frames(store, following))
                              if following is not None else [])
                watch = RefuelWatch()
                race.handle(SessionEvent(EventKind.PIT_ENTRY,
                                         {"fuel": row["fuel_end"]}))
                if pit_frames:
                    replay_stop(race, watch, pit_frames, row["lap_num"], print)
                call = race.handle(as_event(row))
                if out_frames and not pit_frames:
                    replay_stop(race, watch, out_frames, row["lap_num"] + 1,
                                print)
                tyres = row["tyres_changed"] if "tyres_changed" in row.keys() \
                    else None
                race.handle(SessionEvent(EventKind.PIT_EXIT, {
                    "fuel_added": row["fuel_added_l"] or 0.0,
                    "tyres_changed": (None if tyres is None else bool(tyres)),
                }))
            else:
                call = race.handle(as_event(row))
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
