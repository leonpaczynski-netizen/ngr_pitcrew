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


# ------------------------------------ the optimiser and the certifier agree
#
# Suzuka, 13 Sep 2026, event 13: "Build from practice" produced strategy 32 -
# 9 + 6 = 15 laps - and the driver approved it. On the grid `certify` refused
# it ("the clock allows about 14") three times, and he raced with no plan.
# The optimiser costed the last stop with a fill a lap smaller than the one
# it then wrote into the plan, and the certifier charged a declared pit loss
# the dead time a second time. Two expressions for one distance.

def suzuka_inputs(**overrides):
    from pitcrew.strategy.model import RaceInputs

    fields = dict(race_laps=14, race_minutes=30.0, lap_time_ms=125_032,
                  fuel_per_lap_l=9.116, fuel_capacity_l=100.0,
                  refuel_rate_lps=2.0, pit_loss_s=20.0, wear_per_lap=0.04861,
                  available_compounds=("RS",), evidence_compound="RS")
    fields.update(overrides)
    return RaceInputs(**fields)


def test_strategy_32s_inputs_build_a_plan_its_own_certifier_accepts():
    from pitcrew.strategy.certify import certify
    from pitcrew.strategy.model import recommend

    inputs = suzuka_inputs()
    plans = recommend(inputs)
    assert plans
    best = plans[0]
    certificate = certify(best.as_dict(), inputs)
    assert certificate.certified, certificate.describe()
    assert (best.as_export(inputs)["raceLength"]["lapsAtThisPace"]
            == best.laps_completed)


def test_no_timed_plan_the_optimiser_emits_is_refused_on_the_clock():
    """The invariant, swept across the boundary where a lap appears or goes:
    whatever the pace, the certifier's count is the plan's own distance."""
    from pitcrew.strategy.certify import certify
    from pitcrew.strategy.model import recommend

    for lap_ms in range(119_000, 131_001, 500):
        for pit_loss in (15.0, 20.0, 30.0):
            inputs = suzuka_inputs(lap_time_ms=lap_ms, pit_loss_s=pit_loss)
            for plan in recommend(inputs):
                if not plan.feasible:
                    continue
                certificate = certify(plan.as_dict(), inputs)
                clock = [r for r in certificate.refusals + certificate.warnings
                         if "clock allows" in r]
                assert not clock, (lap_ms, pit_loss, plan.label(),
                                   [s.laps for s in plan.stints], clock)


def test_a_declared_pit_loss_is_not_charged_the_dead_time_twice():
    """`stop_overhead_s`: a league-declared pit loss is the whole non-fuel
    cost of a stop. 17 laps of 105 s and a 10 s stop cross at 1795 s, so an
    18th lap is driven; charged a further 7.5 s it would not be."""
    from pitcrew.strategy.certify import certify

    inputs = suzuka_inputs(lap_time_ms=105_000, pit_loss_s=10.0,
                           fuel_per_lap_l=None, wear_per_lap=None,
                           fuel_weight_s_per_l_per_lap=0.0)
    plan = {"stops": 1, "stints": [
        {"laps": 9, "compound": "RS", "start_lap": 1},
        {"laps": 9, "compound": "RS", "start_lap": 10}]}
    certificate = certify(plan, inputs)
    assert not any("clock allows" in r for r in certificate.refusals), \
        certificate.describe()


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
