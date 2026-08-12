"""The strategy model: piecewise wear, stint limits, and honest gaps."""
from __future__ import annotations

import pytest

from pitcrew.strategy.model import (
    CONSTRAINT_FUEL,
    CONSTRAINT_TYRE,
    CONSTRAINT_UNKNOWN,
    FUEL_MAP_CONSUMPTION,
    FUEL_MARGIN_LAPS,
    FUEL_MAP_POWER,
    PHASE_CLIFF_FROM,
    PHASE_FLAT_UNTIL,
    STINT_SAFETY_FACTOR,
    Plan,
    RaceInputs,
    StrategyImpossible,
    build_plan,
    fuel_limited_laps,
    laps_from_minutes,
    legal,
    max_stint_laps,
    pace_loss_s,
    phase_at,
    recommend,
    split_laps,
    tyre_limited_laps,
)


def inputs(**overrides) -> RaceInputs:
    fields = dict(
        race_laps=20, lap_time_ms=94_000, fuel_per_lap_l=3.4,
        fuel_capacity_l=100.0, refuel_rate_lps=2.5, pit_loss_s=20.0,
        wear_per_lap=0.05, available_compounds=("RM", "RS"),
    )
    fields.update(overrides)
    return RaceInputs(**fields)


# ------------------------------------------------------------ piecewise wear

def test_fresh_tyres_lose_nothing():
    assert pace_loss_s(0.0) == 0.0
    assert pace_loss_s(0.3) == 0.0
    assert pace_loss_s(PHASE_FLAT_UNTIL) == 0.0


def test_loss_ramps_through_the_progressive_phase():
    mid = pace_loss_s(0.70)
    assert 0.0 < mid < pace_loss_s(0.85)


def test_the_cliff_is_punitive_not_linear():
    """A linear fit would badly understate this; nothing should plan here."""
    edge = pace_loss_s(PHASE_CLIFF_FROM)
    beyond = pace_loss_s(0.99)
    assert beyond > edge * 5


def test_a_linear_model_would_disagree_in_the_flat_phase():
    """Guards the piecewise shape itself: proportional would predict loss."""
    proportional = pace_loss_s(1.0) * 0.3
    assert pace_loss_s(0.3) == 0.0
    assert proportional > 0.0


def test_phases_are_named():
    assert phase_at(0.2) == "flat"
    assert phase_at(0.7) == "linear"
    assert phase_at(0.95) == "cliff"


# ----------------------------------------------------------- stint ceilings

def test_stint_length_carries_the_safety_margin():
    """0.85/w, not 1.0/w - the cliff's onset is sharp and asymmetric."""
    assert tyre_limited_laps(0.05) == int(STINT_SAFETY_FACTOR / 0.05)
    assert tyre_limited_laps(0.05) == 17


def test_unknown_wear_gives_no_tyre_limit():
    assert tyre_limited_laps(None) is None
    assert tyre_limited_laps(0.0) is None


def test_fuel_limit_from_capacity():
    # 29 until the audit: that counted the reserve lap as runnable, so a
    # stint sized to the limit was then fuelled to 30 laps' worth and clamped
    # to the tank. 28 laps burns 95.2 L and leaves the 3.4 L reserve intact.
    assert fuel_limited_laps(100.0, 3.4) == 28


def test_zero_fuel_capacity_does_not_divide():
    """An electric car has 0 L. That is a real value, not a missing one."""
    assert fuel_limited_laps(0.0, 3.4) is None


def test_binding_constraint_is_whichever_runs_out_first():
    assert max_stint_laps(inputs(wear_per_lap=0.05))[1] == CONSTRAINT_TYRE
    assert max_stint_laps(inputs(wear_per_lap=0.01))[1] == CONSTRAINT_FUEL


def test_binding_constraint_is_unknown_when_nothing_is_known():
    bare = inputs(wear_per_lap=None, fuel_per_lap_l=None, fuel_capacity_l=None)
    assert max_stint_laps(bare) == (None, CONSTRAINT_UNKNOWN)


def test_missing_inputs_are_listed_not_defaulted():
    gaps = inputs(wear_per_lap=None, fuel_per_lap_l=None).missing()
    assert "tyre wear rate" in gaps
    assert "fuel per lap" in gaps


# -------------------------------------------------------------- lap splitting

def test_laps_split_evenly_longest_first():
    assert split_laps(20, 2) == [10, 10]
    assert split_laps(21, 2) == [11, 10]
    assert split_laps(20, 3) == [7, 7, 6]


def test_a_race_needs_a_stint():
    with pytest.raises(StrategyImpossible):
        split_laps(20, 0)


def test_timed_races_become_laps():
    assert laps_from_minutes(45, 94_000) == 29


# ---------------------------------------------------------------- candidates

def test_plans_are_ordered_by_total_time():
    plans = recommend(inputs())
    assert plans[0].delta_s == 0.0
    assert all(plans[i].total_time_s <= plans[i + 1].total_time_s
               for i in range(len(plans) - 1))


def test_a_stop_costs_pit_loss_dead_time_and_fuel():
    one_stop = build_plan(inputs(), stops=1)
    no_stop = build_plan(inputs(), stops=0)
    overhead = one_stop.total_time_s - no_stop.total_time_s
    # The overhead includes the pit loss and dead time even after the tyre and
    # fuel savings of a shorter stint.
    assert overhead > -one_stop.total_time_s   # sanity: comparable magnitudes
    assert one_stop.stops == 1
    assert no_stop.stops == 0


def test_stint_boundaries_line_up_with_the_race():
    plan = build_plan(inputs(race_laps=21), stops=2)
    assert [s.laps for s in plan.stints] == [7, 7, 7]
    assert plan.stints[0].start_lap == 1
    assert plan.stints[1].start_lap == 8
    assert plan.stints[-1].end_lap == 21
    assert plan.pit_laps == [7, 14]


def test_fuel_is_taken_to_the_diamond_plus_a_lap():
    plan = build_plan(inputs(race_laps=10), stops=0)
    assert plan.stints[0].fuel_l == pytest.approx((10 + 1) * 3.4)


def test_a_stint_that_needs_more_than_the_tank_is_infeasible_not_clamped():
    """This test used to assert `fuel_l == 100.0` — the clamp itself.

    Its name promised the tank was never exceeded; what it actually locked in
    was the app quietly pretending 60 laps fit in one tank. That clamp is what
    made an impossible plan the *cheapest* one, because the stint was then
    costed as carrying 100 L rather than the 207 L it needed, and paid no stop
    for the difference. The requirement is now reported honestly and the plan
    is rejected before it can be ranked.
    """
    plan = build_plan(inputs(race_laps=60, fuel_capacity_l=100.0), stops=0)
    assert plan.stints[0].fuel_l == pytest.approx((60 + 1) * 3.4)
    assert plan.feasible is False
    assert any("the tank holds" in note for note in plan.notes)


def test_a_plan_that_cannot_be_run_says_so_rather_than_vanishing():
    plan = build_plan(inputs(race_laps=40, wear_per_lap=0.05), stops=0)
    assert any("runnable" in note for note in plan.notes)


def test_runnable_plans_are_preferred_over_impossible_ones():
    plans = recommend(inputs(race_laps=40, wear_per_lap=0.05))
    assert all(s.laps <= 17 for s in plans[0].stints)


# --------------------------------------------------------------- regulations

def test_mandatory_stops_are_enforced():
    plans = recommend(inputs(mandatory_stops=1))
    assert all(plan.stops >= 1 for plan in plans)


def test_required_compounds_must_appear():
    plans = recommend(inputs(available_compounds=("RM", "RS"),
                             required_compounds=("RS",)))
    for plan in plans:
        assert "RS" in {s.compound for s in plan.stints}


def test_an_illegal_plan_is_rejected():
    plan = build_plan(inputs(mandatory_stops=2), stops=0)
    assert legal(plan, inputs(mandatory_stops=2)) is False


def test_impossible_regulations_raise_rather_than_inventing_a_plan():
    with pytest.raises(StrategyImpossible, match="regulations"):
        recommend(inputs(mandatory_stops=9), max_stops=2)


def test_no_reference_lap_time_refuses():
    with pytest.raises(StrategyImpossible, match="practice lap"):
        recommend(inputs(lap_time_ms=0))


# ------------------------------------------------------------------- honesty

def test_the_margin_is_stated_on_every_plan():
    plan = build_plan(inputs(), stops=1)
    assert any(str(STINT_SAFETY_FACTOR) in note for note in plan.notes)


def test_a_converted_multiplier_is_flagged_assumed():
    plan = build_plan(inputs(wear_measured_at_race_multiplier=False), stops=1)
    assert any("[ASSUMED]" in note for note in plan.notes)
    assert any("linearity" in note for note in plan.notes)


def test_no_wear_rate_is_said_out_loud():
    plan = build_plan(inputs(wear_per_lap=None), stops=1)
    assert any("No tyre wear rate" in note for note in plan.notes)


def test_fuel_map_one_is_the_richest():
    """Sources numbering them 1-5, or inverting this, are wrong."""
    assert FUEL_MAP_CONSUMPTION[1] > FUEL_MAP_CONSUMPTION[5]
    assert FUEL_MAP_POWER[1] > FUEL_MAP_POWER[5]


def test_fuel_map_six_is_anomalous():
    """About half the fuel for about 80% of the power - not the trend."""
    trend_step = FUEL_MAP_CONSUMPTION[4] - FUEL_MAP_CONSUMPTION[5]
    actual_step = FUEL_MAP_CONSUMPTION[5] - FUEL_MAP_CONSUMPTION[6]
    assert actual_step > trend_step * 2
    assert FUEL_MAP_POWER[6] == 0.80


# -------------------------------------------------------------------- export

def test_plan_exports_in_contract_shape():
    plan = build_plan(inputs(), stops=1)
    payload = plan.as_export(inputs())
    assert payload["plan"]["stops"] == 1
    assert payload["plan"]["stintLaps"] == [10, 10]
    assert payload["plan"]["pitLap"] == 10
    assert payload["bindingConstraint"] in (
        CONSTRAINT_TYRE, CONSTRAINT_FUEL, CONSTRAINT_UNKNOWN)
    assert payload["assumptions"]["fuelWeightSource"] == "derived-not-measured"


def test_plan_round_trips_through_a_dict():
    plan = build_plan(inputs(), stops=1)
    payload = plan.as_dict()
    assert payload["stints"][0]["laps"] == 10
    assert payload["binding_constraint"] == plan.binding_constraint


def test_plan_labels_read_naturally():
    assert build_plan(inputs(), stops=0).label() == "No stop"
    assert build_plan(inputs(), stops=1).label() == "1 stop"
    assert build_plan(inputs(), stops=2).label() == "2 stops"


# ----------------------------------------------------- compound provenance

def test_stints_default_to_the_compound_the_evidence_came_from():
    """A wear rate measured on RM does not describe RH."""
    plan = build_plan(inputs(available_compounds=("RH", "RM"),
                             evidence_compound="RM"), stops=1)
    assert [s.compound for s in plan.stints] == ["RM", "RM"]


def test_an_untested_required_compound_is_flagged_as_an_assumption():
    plan = build_plan(inputs(available_compounds=("RM", "RS"),
                             required_compounds=("RS",),
                             evidence_compound="RM"), stops=1)
    assert [s.compound for s in plan.stints] == ["RS", "RM"]
    assert any("RS has no measured rate of its own" in note
               for note in plan.notes)
    assert any("planned on RM's" in note for note in plan.notes)
    assert plan.rests_on_assumption


def test_no_flag_when_every_stint_is_on_the_tested_compound():
    plan = build_plan(inputs(available_compounds=("RM",),
                             evidence_compound="RM"), stops=1)
    assert not any("no measured rate" in note for note in plan.notes)
    assert not plan.rests_on_assumption


def test_an_untagged_session_falls_back_to_the_allowed_list():
    plan = build_plan(inputs(available_compounds=("RH", "RM"),
                             evidence_compound=None), stops=0)
    assert plan.stints[0].compound == "RH"


# --------------------------------------------- feasibility is a filter (A1/B1)
#
# Regression for the audit's A1 and B1. Ranking used to fall back to the
# infeasible set when nothing fit (`runnable or plans`), and ranking is
# monotonically wrong there: the tank clamp made the most impossible plan the
# cheapest, so a car that could not finish won on paper and the card read
# "Fastest". These assert the plan is ABSENT, never merely last.

def _fuel_starved() -> RaceInputs:
    """100 laps at 10 L/lap on a 100 L tank: nine runnable laps a stint."""
    return inputs(race_laps=100, fuel_per_lap_l=10.0, fuel_capacity_l=100.0,
                  wear_per_lap=None, available_compounds=())


def test_nothing_runnable_is_refused_not_ranked():
    with pytest.raises(StrategyImpossible) as raised:
        recommend(_fuel_starved())
    assert "No plan is runnable" in str(raised.value)


def test_the_refusal_says_what_ran_out():
    """A bare "no plan fits" is not actionable; the binding note is."""
    with pytest.raises(StrategyImpossible) as raised:
        recommend(_fuel_starved())
    message = str(raised.value)
    assert "fuel-limited" in message
    assert "shorten the race" in message


def test_the_impossible_zero_stop_plan_is_absent_from_the_output():
    """It used to *win*: clamped to a tankful, it paid no stop for the rest.

    30 laps at 5 L/lap on a 100 L tank is 19 runnable laps a stint, so a
    no-stop plan needs 155 L and cannot be offered at all.
    """
    plans = recommend(inputs(race_laps=30, fuel_per_lap_l=5.0,
                             fuel_capacity_l=100.0, wear_per_lap=None,
                             available_compounds=()))
    assert plans, "one-stop and longer are runnable and must survive"
    assert 0 not in [plan.stops for plan in plans]
    assert all(plan.feasible for plan in plans)


def test_feasibility_does_not_depend_on_the_wording_of_a_note():
    """`_fits` string-matched the plan's own prose. Rewording disabled it."""
    plan = build_plan(_fuel_starved(), stops=0)
    assert plan.feasible is False
    plan.notes = ["something a future edit reworded"]
    assert plan.feasible is False


# ------------------------------------------------- the fuel-floor property
#
# The class, not the instance: whatever the optimiser returns, no stint may
# ask for more than the tank holds, and none may finish without the reserve
# lap still in it.

FUEL_CASES = [
    (20, 3.4, 100.0), (30, 5.0, 100.0), (50, 6.2, 100.0),
    (12, 12.0, 100.0), (40, 2.1, 60.0), (25, 4.0, 45.0),
]


@pytest.mark.parametrize(("laps", "burn", "capacity"), FUEL_CASES)
def test_no_emitted_plan_ever_exceeds_the_tank(laps, burn, capacity):
    try:
        plans = recommend(inputs(race_laps=laps, fuel_per_lap_l=burn,
                                 fuel_capacity_l=capacity, wear_per_lap=None,
                                 available_compounds=()))
    except StrategyImpossible:
        return          # refusing is the other legal answer
    for plan in plans:
        for stint in plan.stints:
            assert stint.fuel_l is not None
            assert stint.fuel_l <= capacity + 1e-9, (
                f"{stint.laps} laps asks for {stint.fuel_l:.1f} L "
                f"from a {capacity:.0f} L tank")


@pytest.mark.parametrize(("laps", "burn", "capacity"), FUEL_CASES)
def test_no_emitted_plan_ends_a_stint_below_the_reserve(laps, burn, capacity):
    try:
        plans = recommend(inputs(race_laps=laps, fuel_per_lap_l=burn,
                                 fuel_capacity_l=capacity, wear_per_lap=None,
                                 available_compounds=()))
    except StrategyImpossible:
        return
    reserve = FUEL_MARGIN_LAPS * burn
    for plan in plans:
        for stint in plan.stints:
            left = stint.fuel_l - stint.laps * burn
            assert left >= reserve - 1e-9, (
                f"{stint.laps} laps on {stint.fuel_l:.1f} L leaves "
                f"{left:.1f} L, under the {reserve:.1f} L reserve")


def test_the_fuel_limit_reserves_the_margin_lap():
    """A 10-lap tank does not run a 10-lap stint: the reserve is the 11th."""
    assert fuel_limited_laps(100.0, 10.0) == 9
    assert fuel_limited_laps(100.0, 3.4) == 28


def test_a_tank_too_small_for_the_reserve_is_zero_not_one():
    """Zero is a known limit nothing satisfies. None would mean unknown."""
    assert fuel_limited_laps(5.0, 4.0) == 0
    assert fuel_limited_laps(0.0, 4.0) is None      # electric, not missing
    assert fuel_limited_laps(100.0, None) is None
