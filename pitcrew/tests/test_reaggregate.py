"""Re-reading sessions recorded before the app could see a stop.

Every one of the 132 laps on disk carries `is_pit_lap = 0`, including one that
stood still for 81 s and took 63 L, because the live gate asked for a fuel
rise three times larger than GT7 delivers. The frames were kept, so the stops
are still in there to be found — which is the whole reason `CLAUDE.md` §6 says
to persist the raw stream and aggregate afterwards.
"""
from __future__ import annotations

import pytest

from pitcrew.analysis.reaggregate import LapFinding, read_session, samples_from
from pitcrew.store.db import Store

HZ = 60.0
HOT = (73.8, 67.6, 82.9, 79.8)
FITTED = (60.0, 60.0, 60.0, 60.0)


def frame(speed: float, fuel: float, temps=HOT) -> dict:
    return {"speed_kph": speed, "fuel_l": fuel,
            "temp_fl": temps[0], "temp_fr": temps[1],
            "temp_rl": temps[2], "temp_rr": temps[3]}


def green(seconds: float, fuel: float = 40.0) -> list[dict]:
    return [frame(200.0, fuel) for _ in range(int(seconds * HZ))]


def a_stop(*, litres: float = 0.0, tyres: bool = False,
           dead_s: float = 6.0) -> list[dict]:
    """A stop as GT7 actually renders one: dead time, then the work."""
    fuel = 20.0
    out = [frame(0.0, fuel) for _ in range(int(dead_s * HZ))]
    temps = HOT
    if tyres:
        temps = FITTED
        out.append(frame(0.0, fuel, FITTED))
    for _ in range(int(litres / 0.0167)):          # 1 L/s at 60 Hz
        fuel += 0.0167
        out.append(frame(0.0, fuel, temps))
    out.extend(frame(0.0, fuel, temps) for _ in range(int(3 * HZ)))
    return out


def laps_of(*frame_lists) -> tuple[list[dict], dict]:
    rows, frames = [], {}
    for index, lap_frames in enumerate(frame_lists, start=1):
        rows.append({"id": index, "session_id": 7, "lap_num": index,
                     "sample_hz": HZ})
        frames[index] = lap_frames
    return rows, frames


def findings_for(*frame_lists) -> list[LapFinding]:
    rows, frames = laps_of(*frame_lists)
    return read_session(rows, frames.get)


def test_the_real_stop_is_found_and_the_lap_after_it_is_an_out_lap():
    found = findings_for(green(100), green(50) + a_stop(litres=51, tyres=True),
                         green(100), green(100))
    assert [(f.lap_num, f.is_pit_lap, f.is_out_lap) for f in found] == [
        (2, True, False), (3, False, True)]
    stop = found[0]
    assert stop.tyres_changed is True
    assert stop.fuel_added_l == pytest.approx(51.0, abs=0.5)


def test_a_tyres_only_stop_is_a_pit_lap_with_no_fuel():
    found = findings_for(green(100), green(50) + a_stop(tyres=True), green(100))
    assert found[0].is_pit_lap is True
    assert found[0].tyres_changed is True
    assert found[0].fuel_added_l == 0.0


def test_a_clean_session_is_left_completely_alone():
    assert findings_for(green(100), green(100), green(100)) == []


def test_sitting_in_the_garage_is_not_a_stop():
    """Session 16 opens with 80 s of it, and it is not a pit stop."""
    waiting = [frame(0.0, 100.0) for _ in range(int(80 * HZ))]
    assert findings_for(waiting + green(100), green(100)) == []


def test_a_lap_with_no_frames_is_skipped_rather_than_called_clean():
    """Not measured is not the same as nothing happened."""
    rows, frames = laps_of(green(100), green(100))
    frames[1] = None
    assert read_session(rows, frames.get) == []


def test_a_lap_with_no_stop_makes_no_claim_about_the_tyres():
    found = findings_for(green(100), green(50) + a_stop(litres=20), green(100))
    assert "tyres_changed" not in found[1].changes      # the out-lap
    assert found[0].changes["tyres_changed"] == 0       # the stop: set stayed on


# --------------------------------------------------------------- writing back

def test_flags_are_written_and_nothing_else_can_be(store, event_id):
    session_id = store.start_session(event_id, "practice")
    from pitcrew.telemetry.session_state import Lap
    lap_id = store.add_lap(session_id, Lap(
        lap_num=1, lap_time_ms=110_000, best_lap_ms=110_000, delta_ms=0,
        fuel_start=40.0, fuel_end=34.0, fuel_used=6.0, position=1,
        is_pit_lap=False, is_out_lap=False))

    store.set_lap_flags(lap_id, is_pit_lap=1, tyres_changed=1, fuel_added_l=63.2)
    row = store.list_laps(session_id)[0]
    assert (row["is_pit_lap"], row["tyres_changed"], row["fuel_added_l"]) == (1, 1, 63.2)

    with pytest.raises(ValueError, match="not a lap flag"):
        store.set_lap_flags(lap_id, lap_time_ms=1)
