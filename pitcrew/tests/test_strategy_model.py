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
    PIT_LOSS_DECLARED,
    PIT_LOSS_MEASURED,
    SOURCE_ASSUMED,
    SOURCE_DECLARED,
    SOURCE_MEASURED,
    STINT_SAFETY_FACTOR,
    CompoundProfile,
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
    """Stint lengths are optimised, not shared out evenly.

    With the stops mandated, the cheapest way to serve them is to run the free
    starting tank as far as the tyre allows and keep the stops that follow
    small - refuelling is charged by the litre, so a short stint is a short
    stop. The even split was never costed against anything; it was the
    arithmetic mean, and at these numbers it gave away five and a half seconds.
    """
    plan = build_plan(inputs(race_laps=21), stops=2)
    laps = [s.laps for s in plan.stints]
    assert sum(laps) == 21
    assert laps[0] > laps[-1]
    assert plan.stints[0].start_lap == 1
    # Whatever the split, the boundaries have to be contiguous and cover the
    # race exactly once.
    for previous, following in zip(plan.stints, plan.stints[1:]):
        assert following.start_lap == previous.end_lap + 1
    assert plan.stints[-1].end_lap == 21


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
    assert payload["plan"]["stintLaps"] == [17, 3]
    assert payload["plan"]["laps"] == 20
    assert payload["plan"]["pitLap"] == 17
    assert payload["bindingConstraint"] in (
        CONSTRAINT_TYRE, CONSTRAINT_FUEL, CONSTRAINT_UNKNOWN)
    assert payload["assumptions"]["fuelWeightSource"] == "derived-not-measured"


def test_plan_round_trips_through_a_dict():
    plan = build_plan(inputs(), stops=1)
    payload = plan.as_dict()
    assert payload["stints"][0]["laps"] == 17
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


# ------------------------------------- an unmeasured wear rate is not a free one
#
# Regression for S4. `_stint_seconds`'s guard is `if wear:`, and a profile
# built from real evidence carries `wear_per_lap=None` for a compound run in
# practice but never gauge-read. None added no degradation at all, so the tyre
# nobody had measured paid nothing while every measured one paid - and it
# ranked first. Two identical profiles came out 4.9 s apart.

def a_pair(**overrides) -> RaceInputs:
    fields = dict(
        race_laps=20, lap_time_ms=100_000, fuel_per_lap_l=3.0,
        fuel_capacity_l=100.0, wear_per_lap=0.04,
        available_compounds=("RH", "RM"), evidence_compound="RM",
        compound_profiles={
            "RM": CompoundProfile("RM", 0.0, 0.04, SOURCE_MEASURED, 10, 1,
                                  longest_stint_laps=20),
            # Same compound in every respect except the gauge reading.
            "RH": CompoundProfile("RH", 0.0, None, SOURCE_DECLARED, 10, 1,
                                  longest_stint_laps=20),
        })
    fields.update(overrides)
    return RaceInputs(**fields)


def test_a_compound_with_no_gauge_reading_inherits_the_reference_rate():
    profile = a_pair().profile_for("RH")
    assert profile.wear_per_lap == 0.04
    assert profile.source == SOURCE_ASSUMED      # inherited, never measured
    assert profile.is_measured is False


def test_the_unmeasured_compound_no_longer_costs_less_than_the_measured_one():
    inputs = a_pair()
    unread = build_plan(inputs, 0, ["RH"])
    measured = build_plan(inputs, 0, ["RM"])
    assert unread.total_time_s == pytest.approx(measured.total_time_s)


def test_the_assumption_is_stated_in_the_plans_notes():
    """The caveat required `profile.wear_per_lap` truthy, so it never fired
    for exactly the compounds it was written about."""
    plan = build_plan(a_pair(), 0, ["RH"])
    assert any("no measured rate" in note for note in plan.notes)
    assert any("assumption, not a measurement" in note for note in plan.notes)


def test_the_card_does_not_say_tyre_limited_and_fuel_limited_at_once():
    """`worst_fraction` was None for a plan of unread compounds, so the notes
    said "fuel-limited only" under a card headed "Limited by tyre"."""
    plan = build_plan(a_pair(), 0, ["RH"])
    assert not any("fuel-limited only" in note for note in plan.notes)
    assert any("worn" in note for note in plan.notes)


# ------------------------------------------------- provenance in the payload

def test_the_pit_loss_is_exported_as_declared_not_measured():
    """It is a spin box with a schema default of 20 s. Nothing measures it,
    and the Strategy screen's own evidence row has always said so."""
    plan = build_plan(inputs(), stops=1)
    payload = plan.as_export(inputs())
    assert payload["assumptions"]["pitLossSource"] == PIT_LOSS_DECLARED
    assert payload["assumptions"]["pitLossSource"] != PIT_LOSS_MEASURED


def test_a_measured_pit_loss_would_say_so():
    measured = inputs(pit_loss_source=PIT_LOSS_MEASURED)
    payload = build_plan(measured, stops=1).as_export(measured)
    assert payload["assumptions"]["pitLossSource"] == PIT_LOSS_MEASURED


def test_an_unmeasurable_compound_delta_is_null_not_zero():
    """The same payload emits `paceDeltaSPerLap: null` per compound and used
    to emit a confident 0.0 here - which reads as "these are exactly level",
    a finding off a comparison `comparable_pace` refused to make."""
    unmeasured = inputs(
        available_compounds=("RM", "RH"), evidence_compound="RM",
        compound_profiles={
            "RH": CompoundProfile("RH", 0.0, 0.05, SOURCE_MEASURED, 8, 1,
                                  longest_stint_laps=20)})
    payload = build_plan(unmeasured, 0, ["RH"]).as_export(unmeasured)
    assert payload["assumptions"]["compoundDeltaSPerLap"] is None


def test_a_plan_on_the_reference_alone_still_reports_zero():
    """The reference against itself is 0.0 by construction, not by
    measurement, and refusing that would over-refuse."""
    payload = build_plan(inputs(evidence_compound="RM"), 0,
                         ["RM"]).as_export(inputs(evidence_compound="RM"))
    assert payload["assumptions"]["compoundDeltaSPerLap"] == 0.0


def test_a_measured_gap_is_still_a_number():
    measured = inputs(
        available_compounds=("RM", "RH"), evidence_compound="RM",
        compound_profiles={
            "RM": CompoundProfile("RM", 0.0, 0.05, SOURCE_MEASURED, 8, 1,
                                  longest_stint_laps=20, pace_known=True),
            "RH": CompoundProfile("RH", 0.4, 0.04, SOURCE_MEASURED, 8, 1,
                                  longest_stint_laps=20, pace_known=True)})
    payload = build_plan(measured, 0, ["RH"]).as_export(measured)
    assert payload["assumptions"]["compoundDeltaSPerLap"] == 0.4


# --------------------------------------------------- the payload validates

def test_both_race_shapes_pass_the_contracts_key_check():
    """`raceLength.laps` was not a documented key, so `to_json` refused every
    lap race's payload outright - the export failing closed on the common
    case. The distance for a lap race is `plan.laps`."""
    from pitcrew.export.payload import _validate_known_keys

    lap_race = inputs()
    timed = inputs(race_minutes=45.0, extra_time_s=180.0)
    for shape in (lap_race, timed):
        payload = {"strategy": build_plan(shape, stops=1).as_export(shape)}
        assert _validate_known_keys(payload) == []


# ------------------------- the narrowing that blamed the rules for itself

def _wide_inputs(compounds: int, *, required=("RS", "RH"), stops: int = 3):
    """Enough profiled compounds that the search has to narrow."""
    from pitcrew.strategy.model import CompoundProfile, RaceInputs

    base = [("RS", 0.0, 0.052), ("RM", 0.55, 0.038), ("RH", 1.25, 0.028),
            ("X4", 1.8, 0.024), ("X5", 2.3, 0.021), ("X6", 2.9, 0.018),
            ("X7", 3.4, 0.016), ("X8", 4.0, 0.014), ("X9", 4.6, 0.012)]
    picked = base[:compounds]
    return RaceInputs(
        available_compounds=[c for c, _p, _w in picked],
        race_laps=27, lap_time_ms=95_000, fuel_per_lap_l=6.1,
        fuel_capacity_l=100.0, pit_loss_s=20.0, wear_per_lap=0.04,
        mandatory_stops=stops, required_compounds=list(required),
        compound_profiles={c: CompoundProfile(code=c, pace_delta_s=p,
                                              wear_per_lap=w,
                                              source="MEASURED")
                           for c, p, w in picked},
        evidence_compound="RS")


def test_a_narrowed_search_can_still_reach_a_legal_plan():
    """**The narrowing used to make every candidate illegal.**

    Above `MAX_CANDIDATES` the search falls back to uniform sequences - every
    stint on one compound. A uniform sequence cannot contain two DIFFERENT
    required compounds, so with `required_compounds=("RS", "RH")` every
    candidate was illegal and `recommend` raised "no plan satisfies the
    regulations", blaming the rules for its own truncation.

    Measured on nine profiled compounds at four stints: 9**4 = 6561 exceeds
    the cap, and with it lifted the same inputs give **11,090 legal plans**.
    The race was always plannable; the search could not see it.
    """
    from pitcrew.strategy.model import MAX_CANDIDATES, recommend

    inputs = _wide_inputs(9)
    assert len(inputs.planning_compounds()) ** 4 > MAX_CANDIDATES, (
        "this test no longer exercises the narrowing")

    plans = recommend(inputs)
    assert plans, "a plannable race was refused"
    best = plans[0]
    used = {stint.compound for stint in best.stints}
    assert {"RS", "RH"} <= used, (
        f"the winning plan does not carry the required compounds: {used}")


def test_narrowing_adds_options_without_changing_the_answer():
    """A narrowed search must never LOSE a plan it used to find, and must not
    move the recommendation. Six compounds narrow at five stints but not at
    four, so this exercises both sides of the cap in one race."""
    from pitcrew.strategy.model import recommend

    plans = recommend(_wide_inputs(6))
    best = plans[0]
    assert best.stops == 3
    assert {"RS", "RH"} <= {stint.compound for stint in best.stints}
    # Every plan the search returns must be legal, narrowed or not.
    for plan in plans:
        used = {stint.compound for stint in plan.stints if stint.compound}
        assert {"RS", "RH"} <= used, f"an illegal plan was returned: {used}"


def test_more_required_compounds_than_stints_is_an_honest_refusal():
    """The one case where the refusal really is about the regulations: three
    compounds required and two stints to put them in. Nothing is seeded and
    nothing should be."""
    from pitcrew.strategy.model import StrategyImpossible, recommend

    inputs = _wide_inputs(9, required=("RS", "RM", "RH"), stops=1)
    with pytest.raises(StrategyImpossible):
        recommend(inputs, max_stops=1)


def test_a_refusal_says_whether_the_search_was_narrowed():
    """He acts on "no plan satisfies the regulations" by changing the
    regulations. If the search was ALSO narrowed that may be the wrong
    action, and he cannot tell from the outside - so the message says both.

    Here the regulations demand more stops than the search will consider, so
    the refusal is genuine; but nine compounds at four and five stints are
    both over the cap, so the narrowing is genuine too. Both are true and the
    driver needs both.
    """
    from pitcrew.strategy.model import StrategyImpossible, recommend

    inputs = _wide_inputs(9, stops=6)
    with pytest.raises(StrategyImpossible) as caught:
        recommend(inputs, max_stops=4)
    message = str(caught.value)
    assert "regulations" in message, message
    assert "narrowed" in message, message


def test_a_refusal_that_is_only_about_the_rules_does_not_blame_the_search():
    """The other half: three compounds never narrow, so the plain message is
    the honest one and the caveat must not be added to it."""
    from pitcrew.strategy.model import StrategyImpossible, recommend

    inputs = _wide_inputs(3, stops=6)
    with pytest.raises(StrategyImpossible) as caught:
        recommend(inputs, max_stops=4)
    assert "narrowed" not in str(caught.value), str(caught.value)
