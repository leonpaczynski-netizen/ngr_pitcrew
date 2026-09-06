"""A timed race's distance has the stops taken off the clock, and is checked.

Deep Forest, 6 Sep 2026: 30 min / 88.9 s = ceil(20.24) = 21. The certifier
listed the count as unchecked by design; George said "21 laps" at the green;
the flag fell on lap 20, because a 52 s stop covers no ground. The plan was
one lap long, and the fill at the stop was sized for a lap never driven.
"""
from __future__ import annotations

from pitcrew.race.calls import GREEN, RaceState, _green
from pitcrew.strategy.model import laps_from_minutes, timed_race_stop_s


def test_the_naive_count_is_the_old_answer():
    assert laps_from_minutes(30, 88_900) == 21


def test_one_stop_of_fifty_two_seconds_takes_the_lap_off():
    assert laps_from_minutes(30, 88_900, stops=1, stop_s=52.0) == 20


def test_no_stops_changes_nothing():
    assert laps_from_minutes(30, 88_900, stops=0, stop_s=52.0) == 21


def test_the_stop_count_and_cost_follow_from_the_tank_and_the_pump():
    # 21 laps at 7.55 L = 158.6 L against a 100 L tank: one stop, ~58.6 L
    # through a 2 L/s hose = 29.3 s, plus 20 s lane loss and 7 s dead time.
    stops, seconds = timed_race_stop_s(
        laps=21, fuel_per_lap_l=7.55, capacity_l=100.0, refuel_rate_lps=2.0,
        pit_loss_s=20.0, dead_time_s=7.0)
    assert stops == 1
    assert 55 < seconds < 58


def test_a_mandatory_stop_counts_even_when_the_tank_would_not_force_one():
    stops, seconds = timed_race_stop_s(
        laps=10, fuel_per_lap_l=5.0, capacity_l=100.0, refuel_rate_lps=2.0,
        pit_loss_s=20.0, dead_time_s=7.0, mandatory_stops=1)
    assert stops == 1
    assert seconds == 27.0, "nothing to add, so lane loss and dead time only"


def test_no_stop_needed_costs_nothing():
    assert timed_race_stop_s(laps=10, fuel_per_lap_l=5.0, capacity_l=100.0,
                             refuel_rate_lps=2.0, pit_loss_s=20.0,
                             dead_time_s=7.0) == (0, 0.0)


# ------------------------------------------------------------- the certifier

def test_a_plan_a_lap_longer_than_the_clock_allows_is_refused():
    from pitcrew.strategy.certify import certify
    from pitcrew.strategy.model import RaceInputs

    inputs = RaceInputs(race_laps=21, lap_time_ms=88_900, race_minutes=30.0,
                        fuel_per_lap_l=7.55, fuel_capacity_l=100.0,
                        refuel_rate_lps=2.0, pit_loss_s=20.0)
    plan = {"stops": 1, "stints": [
        {"laps": 11, "compound": "RS", "fuel_l": 100.0, "start_lap": 1},
        {"laps": 10, "compound": "RS", "fuel_l": 82.0, "start_lap": 12}]}
    certificate = certify(plan, inputs)
    assert any("clock allows about 20" in r for r in certificate.refusals)
    assert not any("lap count" in u for u in certificate.unchecked)


def test_a_plan_that_fits_the_clock_certifies():
    from pitcrew.strategy.certify import certify
    from pitcrew.strategy.model import RaceInputs

    inputs = RaceInputs(race_laps=20, lap_time_ms=88_900, race_minutes=30.0,
                        fuel_per_lap_l=7.55, fuel_capacity_l=100.0,
                        refuel_rate_lps=2.0, pit_loss_s=20.0)
    plan = {"stops": 1, "stints": [
        {"laps": 11, "compound": "RS", "fuel_l": 100.0, "start_lap": 1},
        {"laps": 9, "compound": "RS", "fuel_l": 75.0, "start_lap": 12}]}
    certificate = certify(plan, inputs)
    assert not any("clock allows" in r for r in certificate.refusals)


def test_without_a_reference_lap_the_check_is_named_as_unchecked():
    from pitcrew.strategy.certify import certify
    from pitcrew.strategy.model import RaceInputs

    inputs = RaceInputs(race_laps=20, lap_time_ms=0, race_minutes=30.0)
    plan = {"stops": 0, "stints": [
        {"laps": 20, "compound": "RS", "fuel_l": 100.0, "start_lap": 1}]}
    certificate = certify(plan, inputs)
    assert any("lap count" in u for u in certificate.unchecked)


# ------------------------------------------------------------------ George

def test_the_green_says_about_on_the_clock_for_a_timed_race():
    call = _green(RaceState(lap=0, laps_total=20, race_minutes=30.0))
    assert call is not None and call.kind == GREEN
    assert call.reason == "About 20 laps on the clock."


def test_the_green_keeps_the_plain_count_for_a_lap_race():
    call = _green(RaceState(lap=0, laps_total=20))
    assert call.reason == "20 laps."
