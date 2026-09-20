"""Short to the flag is said while there are laps left to save it.

Bathurst, 14 Sep 2026 (session 176): with 17 laps done, 24.67 L aboard and
three to go, the heartbeat said "Fuel good to the flag." Lap 19 closed on
7.70 L with a lap of about 8.4 still to run. Two things hid it:

* **The burn.** Stint 2 burned 8.37, 8.52, 8.63, 8.42 L, but two of those laps
  were more than 4% off the stint's best and the burn population was the pace
  population, so the stint never had three laps and the race median of 8.248
  - mostly stint 1 - was the burn.
* **The tolerance.** `min(0.5, 0.04 x laps)` shrinks to nothing only in
  proportion to the laps left, and against a burn that light the gap sat
  inside it until the last lap.

Replayed here off the live database, read-only, through the real
`ExpectationTracker` and the real calls.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from pitcrew.race import calls as C
from pitcrew.race.expectations import (FUEL_BASIS_HIGHER_STINT,
                                       FUEL_BASIS_STINT,
                                       ExpectationTracker)
from pitcrew.telemetry.session_state import Lap

LIVE_DB = Path("C:/Projects/VR_Dashboard/data/pitcrew.db")
RACE_LAPS = 20


def _lap(num, used, *, time_ms=122_000, pit=False, out=False, end=50.0):
    return Lap(lap_num=num, lap_time_ms=time_ms, best_lap_ms=0, delta_ms=0,
               fuel_start=end + used, fuel_end=end, fuel_used=used,
               position=5, is_pit_lap=pit, is_out_lap=out)


# ------------------------------------------------------------------ the burn

def test_a_slow_lap_is_still_a_lap_of_burn():
    t = ExpectationTracker(planned_fuel_per_lap_l=8.16)
    for n in range(2, 8):
        t.note_lap(_lap(n, 8.2))
    t.note_lap(_lap(8, 7.7, pit=True))
    t.note_lap(_lap(9, 7.8, out=True))
    t.note_lap(_lap(10, 8.37, time_ms=126_283))
    t.note_lap(_lap(11, 8.52, time_ms=122_432))
    t.note_lap(_lap(12, 8.63, time_ms=153_990))       # off, 26% slow
    assert t.stint_fuel_per_lap_l() == 8.52
    assert t.current_fuel_basis() == (8.52, 3, FUEL_BASIS_STINT)


def test_before_three_stint_laps_the_last_stints_burn_does_not_stand_in():
    t = ExpectationTracker(planned_fuel_per_lap_l=8.16)
    for n in range(2, 8):
        t.note_lap(_lap(n, 8.2))
    t.note_lap(_lap(8, 7.7, pit=True))
    t.note_lap(_lap(9, 7.8, out=True))
    t.note_lap(_lap(10, 8.45))
    burn, laps, basis = t.current_fuel_basis()
    assert (burn, laps, basis) == (8.45, 1, FUEL_BASIS_HIGHER_STINT)
    # And where the stint is running lighter, the race's figure holds.
    t2 = ExpectationTracker()
    for n in range(2, 8):
        t2.note_lap(_lap(n, 8.2))
    t2.note_lap(_lap(8, 7.7, pit=True))
    t2.note_lap(_lap(9, 7.8, out=True))
    t2.note_lap(_lap(10, 7.9))
    assert t2.current_fuel_basis()[0] == 8.2


def test_a_penalty_lap_is_out_of_the_stint_burn_as_it_is_the_race_one():
    t = ExpectationTracker()
    for n, used in ((2, 8.0), (3, 8.1), (4, 6.0), (5, 8.2)):
        t.note_lap(_lap(n, used))
    t.note_penalty(4)
    assert t.stint_green_laps() == 3
    assert t.stint_fuel_per_lap_l() == 8.1


# ------------------------------------------------------------ the one verdict

def _to_the_flag(done, fuel_l, burn, sd=0.13, burn_laps=4):
    return C.RaceState(lap=done, laps_total=RACE_LAPS, fuel_l=fuel_l,
                       fuel_per_lap_l=burn, fuel_sd_l=sd,
                       fuel_burn_laps=burn_laps, fuel_capacity_l=100.0)


def test_the_band_does_not_vanish_at_the_flag():
    """One lap to go still has one lap's scatter in it."""
    last = C._short_tolerance_laps(_to_the_flag(19, 8.0, 8.5))
    assert 0.02 < last < 0.1
    far = C._short_tolerance_laps(_to_the_flag(4, 90.0, 8.5))
    assert last < far < C.FUEL_SHORT_LAPS
    # Capped at the half lap it has always been, on a scatter that wide.
    wide = C._short_tolerance_laps(_to_the_flag(4, 90.0, 8.5, sd=0.4))
    assert wide == pytest.approx(C.FUEL_SHORT_LAPS)


def test_status_call_and_save_are_one_decision():
    """Lap 17 of session 176: 24.67 L, three to go, stint burn 8.47."""
    state = _to_the_flag(17, 24.67, 8.47, sd=0.116, burn_laps=4)
    verdict, gap, reference = C.fuel_verdict(state)
    assert verdict == C.FUEL_IS_SHORT and reference == C.TO_THE_FLAG
    assert C._fuel_standing(state).endswith("short to the flag on current burn.")
    call = C._fuel(state)
    assert call is not None and call.kind == C.FUEL_SHORT
    save = C.fuel_save_l(state)
    assert save is not None and call.call == (
        f"Save {C._litres_a_lap(save)} litres a lap to make the flag.")
    assert C.fuel_reaches_flag(state) is False


def test_inside_the_noise_is_good_and_nothing_else_speaks():
    state = _to_the_flag(10, 84.0, 8.5, sd=0.13, burn_laps=8)
    verdict, gap, _ = C.fuel_verdict(state)
    assert gap < 0 and verdict == C.FUEL_IS_GOOD
    assert C._fuel_standing(state) == "Fuel good to the flag."
    assert C._fuel(state) is None
    assert C.fuel_save_l(state) is None


# ------------------------------------------------------- session 176, replayed

def _replay_176():
    if not LIVE_DB.exists():
        pytest.skip("the live database is not on this machine")
    db = sqlite3.connect(f"file:{LIVE_DB.as_posix()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        rows = db.execute("SELECT * FROM laps WHERE session_id = 176 "
                          "ORDER BY lap_num").fetchall()
    finally:
        db.close()
    if len(rows) < 19:
        pytest.skip("session 176 is not on file")
    tracker = ExpectationTracker(planned_fuel_per_lap_l=8.164,
                                 planned_lap_time_ms=124_574)
    states = {}
    for row in rows:
        tracker.note_lap(Lap(
            lap_num=row["lap_num"], lap_time_ms=row["lap_time_ms"],
            best_lap_ms=0, delta_ms=0, fuel_start=row["fuel_start"],
            fuel_end=row["fuel_end"], fuel_used=row["fuel_used"],
            position=row["position"] or 0,
            is_pit_lap=bool(row["is_pit_lap"]),
            is_out_lap=bool(row["is_out_lap"])))
        burn, laps, _ = tracker.current_fuel_basis()
        sd = (tracker.stint_fuel_sd_l()
              if tracker.stint_fuel_per_lap_l() is not None
              else tracker.race_fuel_sd_l())
        if row["lap_num"] >= 13:                   # the last stint, no stop
            states[row["lap_num"]] = C.RaceState(
                lap=row["lap_num"], laps_total=RACE_LAPS,
                fuel_l=row["fuel_end"], fuel_per_lap_l=burn, fuel_sd_l=sd,
                fuel_burn_laps=laps, fuel_capacity_l=100.0, stint_index=1)
    return states


def test_session_176_warns_with_three_laps_or_more_to_go():
    states = _replay_176()
    for done in (16, 17):
        state = states[done]
        assert state.laps_remaining() >= 3
        assert C.fuel_verdict(state)[0] == C.FUEL_IS_SHORT, done
        assert "Fuel good" not in C._fuel_standing(state), done
        call = C._fuel(state)
        assert call is not None and call.kind == C.FUEL_SHORT, done


def test_session_176_lap_19_save_figure_is_the_shortfall_it_names():
    """One lap to go on 7.70 L at a stint burn of about 8.5: the saving named
    is the burn less the tank, and the status says short, not good."""
    state = _replay_176()[19]
    verdict, gap, _ = C.fuel_verdict(state)
    assert verdict == C.FUEL_IS_SHORT
    save = C.fuel_save_l(state)
    assert save == pytest.approx(state.fuel_per_lap_l - state.fuel_l)
    assert 0.6 < save < 1.0
    assert C._fuel_standing(state) == (
        f"{C._short_by(gap)} short to the flag on current burn.")


def test_session_176_a_save_asked_for_is_not_called_good_a_lap_later():
    """Lap 18: the stint median dips and the gap is back inside the band. One
    lap after "Save 0.3 litres a lap" the heartbeat may not say "Fuel good to
    the flag." about a tank still short on the point estimate."""
    states = _replay_176()
    first = C._fuel(states[16])
    assert first is not None and first.tag == C.FUEL_SAVE
    lap_18 = states[18]
    gap = C.fuel_verdict(lap_18)[1]
    assert gap < 0
    lap_18.record(first)
    assert lap_18.fuel_save_said is True
    assert C.fuel_verdict(lap_18)[0] == C.FUEL_IS_SHORT
    assert "Fuel good" not in C._fuel_standing(lap_18)
