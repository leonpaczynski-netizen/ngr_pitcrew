"""THE RULE: in the same session, the lap after an in-lap is an out-lap.

The driver, 15 Sep 2026: *"A lap in the same session after an in lap has to
be an out lap."* On the archive it did not hold - eleven stored pit laps were
followed by a lap that was not an out-lap - and 56bf65f struck the lap after
a practice RESET as though the reset were a stop.

Two definitions, one place each:

* **in-lap** - `analysis/reaggregate`, off the frames through the one stop
  detector: the lap the car was driven into the pit lane on and serviced. A
  practice reset (the car moved to the box, the tank and tyres replaced in one
  frame) is not one.
* **out-lap** - `runs.out_lap_after_in_lap`, used by the live state, the rack,
  the export and the repair alike.

The real-frames tests read the owner's database READ-ONLY and skip where it
is absent. The archive repair has its own file, `test_repair_in_out_laps`.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from pitcrew.analysis.reaggregate import (
    IN_LAP_CROSSED,
    IN_LAP_STOP,
    in_lap_evidence,
    plan_session,
    read_lap,
    read_session,
    rule_violations,
)
from pitcrew.analysis.runs import (
    LOBBY,
    TIME_TRIAL,
    auto_out_laps,
    out_lap_after_in_lap,
    split_runs,
)
from pitcrew.analysis.session import LapInput
from pitcrew.telemetry.recorder import decode_frames

LIVE_DB = Path("C:/Projects/VR_Dashboard/data/pitcrew.db")
HZ = 60.0

needs_live_db = pytest.mark.skipif(
    not LIVE_DB.is_file(), reason="the owner's database is not on this machine")


# ------------------------------------------------------------------- the rule

def test_the_lap_after_an_in_lap_is_an_out_lap():
    in_lap = SimpleNamespace(is_pit_lap=True, session_id=7)
    assert out_lap_after_in_lap(in_lap, SimpleNamespace(session_id=7)) is True


def test_a_session_change_is_not_an_exception_to_make():
    """A session that ended in the pits does not strike the next session's
    first lap: that lap is judged by where the car started the session."""
    in_lap = SimpleNamespace(is_pit_lap=True, session_id=7)
    assert out_lap_after_in_lap(in_lap, SimpleNamespace(session_id=8)) is False


def lap(num, session, *, start=60.0, end=53.0, **fields) -> LapInput:
    values = dict(lap_num=num, lap_time_ms=101_000, fuel_start=start,
                  fuel_end=end, session_id=session)
    values.update(fields)
    return LapInput(**values)


def test_a_session_boundary_after_an_in_lap():
    """Session 1 ends on an in-lap; session 2 is a time trial, whose opener
    starts on track and is kept. Nothing reaches across."""
    laps = [lap(1, 1, practice_mode=LOBBY), lap(2, 1, practice_mode=LOBBY,
                                                is_pit_lap=True),
            lap(3, 2, start=100.0, end=93.0, practice_mode=TIME_TRIAL),
            lap(4, 2, start=93.0, end=86.0, practice_mode=TIME_TRIAL)]
    assert auto_out_laps(laps) == {1}


def test_a_race_grid_lap_is_not_an_out_lap():
    """Nothing comes before it, so THE RULE cannot make it one, and the
    opener's verdict says a race starts from the grid - even with the tank
    filling on the grid inside its frames."""
    laps = [SimpleNamespace(lap_num=n, session_id=5, session_kind="race",
                            practice_mode=None, standing_start_ms=12_000,
                            is_pit_lap=False)
            for n in (1, 2, 3)]
    assert auto_out_laps(laps) == set()
    assert [run.first_lap for run in split_runs(
        [lap(1, 5, start=49.9, end=91.5), lap(2, 5, start=91.5, end=84.0)])
    ] == [1]


def test_the_rule_holds_with_no_exception_inside_a_session():
    """Even where the in-lap row already carries an out-lap flag of its own
    (the exit came before the next crossing), the lap after it is struck."""
    laps = [lap(n, 3) for n in range(1, 6)]
    laps[1] = lap(2, 3, is_pit_lap=True, is_out_lap=True)
    assert 3 in auto_out_laps(laps)


def test_rule_violations_are_counted_per_session():
    rows = [dict(session_id=1, lap_num=1, is_pit_lap=0, is_out_lap=1),
            dict(session_id=1, lap_num=2, is_pit_lap=1, is_out_lap=1),
            dict(session_id=1, lap_num=3, is_pit_lap=0, is_out_lap=0),
            dict(session_id=1, lap_num=4, is_pit_lap=1, is_out_lap=0),
            dict(session_id=2, lap_num=1, is_pit_lap=0, is_out_lap=0)]
    assert rule_violations(rows) == [(1, 2, 3)]


def test_pit_loss_does_not_sum_a_flying_lap_into_a_merged_stop():
    """Session 53, Monza: the in-lap row holds the out-lap too (168.2 s on
    286 s of frames), and THE RULE now strikes the 110.6 s lap after it.
    Summing that lap in would take a whole lap off the stop."""
    from pitcrew.race.pit_loss import measure

    rows = [{"lap_num": n, "lap_time_ms": 110_400, "is_pit_lap": 0,
             "is_out_lap": 0, "fuel_added_l": None, "off_track_s": 0.0,
             "spin_s": 0.0} for n in range(1, 14)]
    rows.append({"lap_num": 14, "lap_time_ms": 168_208, "is_pit_lap": 1,
                 "is_out_lap": 1, "fuel_added_l": 48.37})
    rows.append({"lap_num": 15, "lap_time_ms": 110_600, "is_pit_lap": 0,
                 "is_out_lap": 1, "fuel_added_l": None})
    assert measure(rows, refuel_rate_lps=1.0) == []


# ------------------------------------------------ the in-lap, synthetic frames

def frame(speed, fuel, *, x=None, z=None, temps=(80.0, 78.0, 84.0, 83.0)):
    return {"speed_kph": speed, "fuel_l": fuel, "pos_x": x, "pos_z": z,
            "temp_fl": temps[0], "temp_fr": temps[1], "temp_rl": temps[2],
            "temp_rr": temps[3]}


def racing(seconds, fuel=30.0):
    return [frame(200.0, fuel) for _ in range(int(seconds * HZ))]


def served(seconds_dead=4.0, litres=20.0, fuel=10.0, *, rolling_in=False):
    """A driven stop: dead time, then fuel at 1 L/s."""
    out = []
    if rolling_in:
        out += [frame(60.0 - 60.0 * i / 120, fuel) for i in range(120)]
    out += [frame(0.0, fuel) for _ in range(int(seconds_dead * HZ))]
    for _ in range(int(litres * HZ)):
        fuel += 1.0 / HZ
        out.append(frame(0.0, fuel))
    out += [frame(0.0, fuel) for _ in range(int(2 * HZ))]
    return out


def rows_for(*frame_lists, session=9, times=None):
    rows, frames = [], {}
    for index, lap_frames in enumerate(frame_lists, start=1):
        lap_ms = (times[index - 1] if times
                  else int(len(lap_frames) / HZ * 1000))
        rows.append({"id": index, "session_id": session, "lap_num": index,
                     "sample_hz": HZ, "lap_time_ms": lap_ms,
                     "is_pit_lap": 0, "is_out_lap": 0})
        frames[index] = lap_frames
    return rows, frames


def test_a_box_before_the_line_makes_that_lap_the_in_lap():
    rows, frames = rows_for(racing(100), racing(60) + served() + racing(20),
                            racing(100))
    found = read_session(rows, frames.get)
    assert [(f.lap_num, f.is_pit_lap, f.is_out_lap) for f in found] == [
        (2, True, False), (3, False, True)]


def test_crossing_in_the_box_makes_the_lap_before_the_in_lap():
    """Daytona and Spa: the line is inside the pit lane before the box, so the
    stop lands at the start of the next lap's frames. The in-lap is the lap
    before; the lap holding the stop is the out-lap; the lap after is flying."""
    rows, frames = rows_for(
        racing(100), racing(100),
        served(rolling_in=True) + racing(80),       # opens in the pit lane
        racing(100))
    readings = [read_lap(row, frames[row["id"]]) for row in rows]
    assert in_lap_evidence(readings) == {2: IN_LAP_CROSSED}
    found = read_session(rows, frames.get)
    assert [(f.lap_num, f.is_pit_lap, f.is_out_lap) for f in found] == [
        (2, True, False), (3, False, True)]
    assert found[1].fuel_added_l == pytest.approx(20.0, abs=0.5)


def test_a_race_grid_fill_is_not_an_in_lap():
    """Every race opens stationary on the grid and fills there - there is no
    lap before it in the session to be the in-lap."""
    rows, frames = rows_for(served(seconds_dead=30.0, litres=50.0)
                            + racing(90), racing(100))
    assert read_session(rows, frames.get) == []


def test_a_practice_reset_is_not_a_stop():
    """The car is moved 168 m to the box at 265 km/h and handed a full tank in
    ONE frame (session 158 lap 11). No in-lap, no out-lap."""
    reset = ([frame(265.0, 31.08, x=-430.1, z=438.0)]
             + [frame(0.0, 100.0, x=-424.8, z=270.1,
                      temps=(70.0, 70.0, 70.0, 70.0))
                for _ in range(int(10 * HZ))])
    rows, frames = rows_for(racing(100), racing(3) + reset + racing(90),
                            racing(100))
    assert read_session(rows, frames.get) == []


def test_a_crash_to_a_standstill_is_not_an_in_lap():
    """Session 149 lap 7: 170 -> 5 km/h against a wall, reversed out and
    drove on. Stored as a pit lap by the live speed step; the frames cover
    the lap and show no stop and no pit-lane placement, so the flag clears."""
    stopped = [frame(0.0, 30.0) for _ in range(int(4 * HZ))]
    rows, frames = rows_for(racing(100), racing(50) + stopped + racing(50),
                            racing(100))
    rows[1]["is_pit_lap"] = 1
    rows[1]["is_out_lap"] = 1
    changes = plan_session(rows, frames.get)
    assert [(c.lap_num, c.column, c.target) for c in changes] == [
        (2, "is_pit_lap", 0)]


def test_a_stored_in_lap_the_recording_did_not_cover_is_kept():
    """45 s of frames for an 80.7 s lap (session 72 lap 5): silence about a
    stop from a recording that missed half the lap is not evidence."""
    rows, frames = rows_for(racing(80), racing(45), times=[80_000, 80_700])
    rows[1]["is_pit_lap"] = 1
    assert plan_session(rows, frames.get) == []


def test_the_repair_sets_out_laps_and_never_clears_one():
    rows, frames = rows_for(racing(100), racing(60) + served() + racing(20),
                            racing(100), racing(100))
    rows[0]["is_out_lap"] = 1
    rows[1]["is_out_lap"] = 1                # the live path's old placement
    changes = plan_session(rows, frames.get)
    assert [(c.lap_num, c.column, c.stored, c.target) for c in changes] == [
        (2, "is_pit_lap", 0, 1), (3, "is_out_lap", 0, 1)]


# ------------------------------------------------------------ the live path

def test_the_live_state_files_the_rule_on_the_lap_after_the_in_lap():
    from pitcrew.telemetry.session_state import SessionKind, SessionState

    from .conftest import make_packet

    state = SessionState(SessionKind.PRACTICE)
    packet_id = 0

    def feed(**spec):
        nonlocal packet_id
        packet_id += 1
        return state.update(make_packet(packet_id=packet_id, **spec))

    # Lap 1, then a speed step into the pits on lap 2, out before the line.
    feed(speed_ms=60.0, last_lap_ms=-1)
    feed(speed_ms=60.0, last_lap_ms=100_000)            # lap 1 filed
    feed(speed_ms=60.0, last_lap_ms=100_000)
    feed(speed_ms=0.0, last_lap_ms=100_000)             # taken into the box
    feed(speed_ms=40.0, last_lap_ms=100_000)            # released, > 120 kph
    feed(speed_ms=60.0, last_lap_ms=150_000)            # lap 2 filed: in-lap
    feed(speed_ms=60.0, last_lap_ms=101_000)            # lap 3 filed
    laps = state.laps
    assert [(l.is_pit_lap, l.is_out_lap) for l in laps[-2:]] == [
        (True, True), (False, True)]


def test_the_live_state_does_not_call_a_reset_a_pit_entry():
    from pitcrew.telemetry.session_state import EventKind, SessionKind, SessionState

    from .conftest import make_packet

    state = SessionState(SessionKind.PRACTICE)
    events = []
    for index, spec in enumerate([
            dict(speed_ms=73.7, pos_x=-430.0, pos_z=436.8),
            dict(speed_ms=73.7, pos_x=-430.1, pos_z=438.0),
            dict(speed_ms=0.0, pos_x=-424.8, pos_z=270.1)], start=1):
        events += state.update(make_packet(packet_id=index, **spec))
    assert not [e for e in events if e.kind is EventKind.PIT_ENTRY]


# ------------------------------------------------------- real frames, read-only

def live_rows(session_id: int, lap_nums) -> tuple[list[dict], dict]:
    conn = sqlite3.connect(f"file:{LIVE_DB.as_posix()}?mode=ro", uri=True)
    try:
        rows, frames = [], {}
        for num in lap_nums:
            row = conn.execute(
                "SELECT l.id, l.session_id, l.lap_num, l.lap_time_ms, "
                "       l.is_pit_lap, l.is_out_lap, f.sample_hz, f.blob "
                "FROM laps l LEFT JOIN lap_frames f ON f.lap_id = l.id "
                "WHERE l.session_id = ? AND l.lap_num = ?",
                (session_id, num)).fetchone()
            rows.append({"id": row[0], "session_id": row[1],
                         "lap_num": row[2], "lap_time_ms": row[3],
                         "is_pit_lap": row[4], "is_out_lap": row[5],
                         "sample_hz": row[6] or HZ})
            frames[row[0]] = decode_frames(row[7]) if row[7] else None
        return rows, frames
    finally:
        conn.close()


@needs_live_db
def test_session_158_lap_11_is_a_practice_reset_not_a_stop():
    """Sardegna, 10 Sep. 3.2 s into lap 11: 265.4 -> 0.0 km/h, moved 168 m to
    the lobby's own start spot, 31.08 -> 100.00 L and four tyres to 70.0 C in
    one frame. No in-lap, so lap 12 - 101.4 s, a flying lap - is not struck."""
    rows, frames = live_rows(158, [10, 11, 12])
    reading = read_lap(rows[1], frames[rows[1]["id"]])
    assert reading.stops == ()
    assert read_session(rows, frames.get) == []
    assert plan_session(rows, frames.get) == []


@needs_live_db
def test_session_19_lap_14_is_a_real_stop_and_lap_15_its_out_lap():
    """Monza, 14 Aug. Pit entry at 107.8 s (230 km/h to 0, the car frozen in
    place), 63 L at 1 L/s, all four tyres to 60.0 C, released at 189.9 s."""
    rows, frames = live_rows(19, [13, 14, 15])
    readings = [read_lap(row, frames[row["id"]]) for row in rows]
    assert in_lap_evidence(readings) == {rows[1]["id"]: IN_LAP_STOP}
    stop = readings[1].stops[0]
    assert stop.fuel_added_l == pytest.approx(63.2, abs=0.5)
    assert stop.changed_tyres is True
    changes = plan_session(rows, frames.get)
    assert [(c.lap_num, c.column, c.target) for c in changes] == [
        (14, "is_pit_lap", 1), (15, "is_out_lap", 1)]


@needs_live_db
def test_session_108_lap_5_is_a_practice_reset_not_a_stop():
    """31 Aug. 3.0 s into lap 5: 201 -> 0 km/h, moved 114 m to the lobby's
    start spot, 66.86 -> 100.00 L in one frame. Lap 6 (164.2 s) is slow for
    its own reasons, not because it followed an in-lap."""
    rows, frames = live_rows(108, [4, 5, 6])
    assert read_session(rows, frames.get) == []
    assert plan_session(rows, frames.get) == []


@needs_live_db
def test_a_real_crossing_in_the_box_daytona():
    """Session 127, Daytona race: the entry at 101.5 s of lap 12, the line
    crossed in the pit lane, 56 L taken at the start of lap 13."""
    rows, frames = live_rows(127, [11, 12, 13, 14])
    readings = [read_lap(row, frames[row["id"]]) for row in rows]
    assert in_lap_evidence(readings) == {rows[1]["id"]: IN_LAP_CROSSED}
    assert plan_session(rows, frames.get) == []     # stored right already

