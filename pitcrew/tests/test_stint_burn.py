"""The burn that sizes the fill is this stint's, once it has three clean laps.

Deep Forest, 6 Sep 2026: stint 1 was driven lift-and-coasting (7.32 L/lap),
stint 2 was not (7.79, then 8.01 once the short-shifting stopped too). With
the hose in George said "Burning 6% less fuel than planned" off the
whole-race median, and sized the fill on it.
"""
from __future__ import annotations

from pitcrew.race.expectations import STINT_BURN_LAPS, ExpectationTracker
from pitcrew.telemetry.session_state import Lap


def _lap(num, used, *, pit=False, out=False, time_ms=88_000):
    return Lap(lap_num=num, lap_time_ms=time_ms, best_lap_ms=88_000,
               delta_ms=0, fuel_start=50.0 + used, fuel_end=50.0,
               fuel_used=used, position=3, is_pit_lap=pit, is_out_lap=out)


def _tracker(planned=7.83):
    return ExpectationTracker(planned_fuel_per_lap_l=planned,
                              planned_lap_time_ms=88_000)


def test_before_three_stint_laps_the_higher_of_race_and_stint_stands():
    """**Not the race figure alone** (Bathurst, 14 Sep 2026): the previous
    stint's lighter burn may not stand in silently for this one. Until the
    stint has three laps the higher of the two sizes the laps ahead, and the
    basis says which it is."""
    from pitcrew.race.expectations import FUEL_BASIS_HIGHER_STINT

    t = _tracker()
    for n in range(2, 8):
        t.note_lap(_lap(n, 7.32))
    t.note_lap(_lap(8, 0.9, pit=True))
    t.note_lap(_lap(9, 7.8, out=True))
    t.note_lap(_lap(10, 7.79))
    t.note_lap(_lap(11, 7.80))
    assert t.stint_green_laps() == 2
    assert t.stint_fuel_per_lap_l() is None
    assert t.race_fuel_per_lap_l() == 7.32
    assert t.current_fuel_basis() == (7.795, 2, FUEL_BASIS_HIGHER_STINT)


def test_from_three_stint_laps_the_stint_figure_takes_over():
    t = _tracker()
    for n in range(2, 8):
        t.note_lap(_lap(n, 7.32))
    t.note_lap(_lap(8, 0.9, pit=True))
    t.note_lap(_lap(9, 7.8, out=True))
    for n, used in ((10, 7.79), (11, 7.80), (12, 7.78)):
        t.note_lap(_lap(n, used))
    assert t.stint_green_laps() == STINT_BURN_LAPS
    assert t.stint_fuel_per_lap_l() == 7.79
    assert t.race_fuel_per_lap_l() < 7.5, "the race median still carries stint 1"
    assert t.current_fuel_per_lap_l() == 7.79


def test_burn_vs_plan_judges_the_stint_being_driven():
    """'6% under plan' with the hose in was stint 1's number."""
    t = _tracker(planned=7.83)
    for n in range(2, 8):
        t.note_lap(_lap(n, 7.32))
    under = t.burn_vs_plan()
    assert under is not None and under < -0.05
    t.note_lap(_lap(8, 0.9, pit=True))
    t.note_lap(_lap(9, 7.8, out=True))
    for n, used in ((10, 8.0), (11, 8.02), (12, 8.01)):
        t.note_lap(_lap(n, used))
    over = t.burn_vs_plan()
    assert over is not None and over > 0.01


def test_the_reference_load_follows_the_stint():
    t = _tracker()
    for n in range(2, 8):
        t.note_lap(Lap(lap_num=n, lap_time_ms=88_000, best_lap_ms=88_000,
                       delta_ms=0, fuel_start=90.0, fuel_end=82.0,
                       fuel_used=8.0, position=3, is_pit_lap=False,
                       is_out_lap=False))
    t.note_lap(_lap(8, 0.9, pit=True))
    t.note_lap(_lap(9, 7.8, out=True))
    for n in (10, 11, 12):
        t.note_lap(Lap(lap_num=n, lap_time_ms=88_000, best_lap_ms=88_000,
                       delta_ms=0, fuel_start=40.0, fuel_end=32.0,
                       fuel_used=8.0, position=3, is_pit_lap=False,
                       is_out_lap=False))
    assert t.current_fuel_reference_load_l() == 36.0
    assert t.race_fuel_reference_load_l() > 50.0


def test_a_saving_lap_in_the_stint_is_excluded_like_anywhere_else():
    t = _tracker()
    t.note_lap(_lap(2, 7.0))
    for n in (3, 4, 5):
        lap = _lap(n, 6.0)
        lap.short_shift_rpm = 7400.0
        t.note_lap(lap)
    t.note_lap(_lap(6, 7.0))
    t.note_lap(_lap(7, 7.1))
    assert t.stint_fuel_per_lap_l() == 7.0
