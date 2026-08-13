"""A race run to the clock, and the two things that got planned into it.

Three defects, all from one strategy run against the Monza event:

* a plan **52 minutes long for a 50-minute race**, which is not a slow plan but
  an impossible one — the model treated a timed race as a fixed lap count, so
  every pit stop made the race longer instead of costing laps;
* **Intermediates and Heavy Wets in the plans**, ranked alongside measured
  rubber, for a race whose weather cannot be known and on tyres that have never
  turned a wheel;
* a stint planned **longer than any stint ever run** on that compound.
"""
from __future__ import annotations

import pytest

from pitcrew.strategy.model import (
    CONSTRAINT_EVIDENCE,
    SOURCE_MEASURED,
    CompoundProfile,
    RaceInputs,
    build_plan,
    is_wet_compound,
    recommend,
    stint_limit,
)

# The event as run: 50 minutes, 180 s of extra time, a 108 s lap.
LAP_MS = 108_000
MINUTES = 50.0


def an_input(**overrides) -> RaceInputs:
    fields = dict(
        race_laps=28,
        race_minutes=MINUTES,
        extra_time_s=180.0,
        lap_time_ms=LAP_MS,
        fuel_per_lap_l=6.6,
        fuel_capacity_l=100.0,
        refuel_rate_lps=1.0,
        pit_loss_s=19.0,
        wear_per_lap=0.0577,
        evidence_compound="RH",
        available_compounds=("RH", "RM", "RS", "IM", "HW"),
        compound_profiles={
            "RH": CompoundProfile("RH", 0.0, 0.0577, SOURCE_MEASURED,
                                  laps_measured=25, stints_measured=2,
                                  longest_stint_laps=15),
            "RM": CompoundProfile("RM", -0.9, 0.0764, SOURCE_MEASURED,
                                  laps_measured=9, stints_measured=1,
                                  longest_stint_laps=11),
            "RS": CompoundProfile("RS", -0.56, 0.1725, SOURCE_MEASURED,
                                  laps_measured=7, stints_measured=1,
                                  longest_stint_laps=4),
        },
    )
    fields.update(overrides)
    return RaceInputs(**fields)


# ---------------------------------------------------- the ceiling on the race

def test_the_race_cannot_last_longer_than_the_clock_plus_a_lap():
    """Cross the line a moment before the flag and you still owe one lap.

    50 minutes at 108 s a lap is 51:48, and never 52:00.
    """
    inputs = an_input()
    assert inputs.max_duration_s == pytest.approx(3000.0 + 108.0)


def test_a_lap_longer_than_the_allowance_is_cut_off_by_it():
    """On a circuit with an eight-minute lap, 180 s of extra time binds long
    before the lap does."""
    inputs = an_input(lap_time_ms=480_000, extra_time_s=180.0)
    assert inputs.max_duration_s == pytest.approx(3000.0 + 180.0)


def test_without_a_declared_allowance_the_lap_is_the_ceiling():
    inputs = an_input(extra_time_s=None)
    assert inputs.max_duration_s == pytest.approx(3000.0 + 108.0)


def test_no_recommended_plan_runs_past_the_flag():
    """The defect, stated as an invariant. Every plan the driver is offered
    has to describe a race that can actually happen."""
    inputs = an_input()
    for plan in recommend(inputs):
        assert plan.total_time_s <= inputs.max_duration_s + 1e-6, plan.notes


def test_stopping_is_paid_for_in_the_clock_not_charged_to_the_race():
    """The trade the old model could not see: it handed every plan the same
    lap count, so a stop cost nothing at all.

    Now the extra stops eat into the clock. They cost distance only when they
    eat enough of it to lose a whole lap - so the invariant is that stopping
    more never gets you further, and always gets you to the flag later.
    """
    inputs = an_input()
    one = build_plan(inputs, 1, ["RH", "RH"])
    three = build_plan(inputs, 3, ["RH", "RH", "RH", "RH"])
    assert three.laps_completed <= one.laps_completed
    assert three.total_time_s > one.total_time_s
    assert three.total_time_s <= inputs.max_duration_s + 1e-6


def test_a_timed_race_is_ranked_on_distance_not_elapsed_time():
    """Every plan ends when the clock does, so ranking on total time ranks
    them on where their last lap happened to fall. The car in front is the
    one that covered more laps."""
    ordered = recommend(an_input())
    laps = [plan.laps_completed for plan in ordered]
    assert laps == sorted(laps, reverse=True)
    assert ordered[0].delta_s == 0.0


def test_a_stop_scheduled_after_the_flag_is_not_runnable():
    """Nobody turns into the pits on the last lap of a timed race; they take
    the flag. A plan that schedules it is describing a race that does not
    happen."""
    inputs = an_input(race_minutes=4.0, race_laps=2, pit_loss_s=120.0)
    plans = [build_plan(inputs, stops, ["RH"] * (stops + 1))
             for stops in (0, 1, 2, 3)]
    for plan in plans:
        if not plan.feasible and any("after the" in note for note in plan.notes):
            break
    else:
        pytest.fail("a stop past the flag was never rejected")


def test_a_lap_race_is_untouched_by_any_of_this():
    """The clock model applies to timed races and to nothing else."""
    inputs = an_input(race_minutes=None, race_laps=20)
    assert inputs.is_timed is False
    assert inputs.max_duration_s is None
    assert build_plan(inputs, 1, ["RH", "RH"]).laps_completed == 20


# --------------------------------------------------------------- wet weather

def test_intermediate_and_heavy_wet_are_wet():
    assert is_wet_compound("IM") is True
    assert is_wet_compound("HW") is True
    assert is_wet_compound("RH") is False
    assert is_wet_compound(None) is False


def test_no_plan_is_ever_built_on_a_wet_tyre():
    """GT7's weather cannot be known before the race and no wet running has
    ever been done, so a stint on Intermediates is a stint on nothing.

    Worse, it *won*: a compound with no profile inherits the reference's rate,
    so an untested tyre is costed as the measured one and looks free.
    """
    for plan in recommend(an_input()):
        for stint in plan.stints:
            assert not is_wet_compound(stint.compound), plan.notes


def test_the_wets_are_still_declared_available_to_the_driver():
    """They are a live call, not a strategy. Filtering them out of planning
    must not quietly delete them from the regulations."""
    inputs = an_input()
    assert "IM" in inputs.available_compounds
    assert "IM" not in inputs.planning_compounds()


# ---------------------------------------------------- planning past evidence

def test_a_stint_is_never_planned_longer_than_one_that_has_been_run():
    """`0.85 / w` will happily extrapolate a stint nobody has completed. When
    the rate itself was understated, that is exactly what it did."""
    inputs = an_input(compound_profiles={
        "RS": CompoundProfile("RS", 0.0, 0.02, SOURCE_MEASURED,
                              laps_measured=4, stints_measured=1,
                              longest_stint_laps=4)},
        available_compounds=("RS",), evidence_compound="RS")
    laps, why = stint_limit(inputs, inputs.profile_for("RS"))
    assert laps == 4
    assert why == CONSTRAINT_EVIDENCE


def test_the_evidence_limit_yields_to_a_tighter_one():
    """It is a floor under the others, not a replacement for them: a tyre that
    dies at four laps is not rescued by having run fifteen."""
    inputs = an_input()
    laps, why = stint_limit(inputs, inputs.profile_for("RS"))
    assert laps == 4
    assert why == "tyre"


def test_a_compound_with_no_evidence_is_not_capped_to_zero():
    """An unrun compound is planned on the reference's rate and labelled
    assumed. Capping it at zero laps would refuse the plan outright."""
    inputs = an_input()
    laps, why = stint_limit(inputs, inputs.profile_for("XX"))
    assert laps and laps > 0
