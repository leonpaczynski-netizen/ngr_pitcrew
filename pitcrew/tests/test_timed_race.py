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

from pitcrew.race.calls import STATUS, RaceState, next_call
from pitcrew.race.coordinator import (
    RaceCoordinator,
    context_from_event,
    context_from_stored,
)
from pitcrew.race.replan import _remaining_race, assess
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
from pitcrew.telemetry.session_state import EventKind, SessionEvent

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


def test_an_untested_compound_is_never_a_strategy():
    """Yas Marina, 16 Aug 2026: the night-race plan suggested RH and RM,
    neither of which had ever been run - an unprofiled compound inherits the
    reference's pace and rate, so the search saw identical tyres and chose
    on nothing. "It should only suggest tyres that have been tested."
    """
    inputs = an_input(compound_profiles={
        "RH": CompoundProfile("RH", 0.0, 0.0577, SOURCE_MEASURED,
                              laps_measured=25, stints_measured=2,
                              longest_stint_laps=15)})
    assert inputs.planning_compounds() == ("RH",)
    for plan in recommend(inputs):
        for stint in plan.stints:
            assert stint.compound == "RH", plan.notes


def test_a_required_compound_is_planned_even_when_untested():
    """The regulations outrank the evidence filter: every plan without a
    required compound is illegal, so an untested-but-required tyre stays
    plannable and the plan carries the assumption rather than hiding it."""
    inputs = an_input(
        required_compounds=("RM",),
        compound_profiles={
            "RH": CompoundProfile("RH", 0.0, 0.0577, SOURCE_MEASURED,
                                  laps_measured=25, stints_measured=2,
                                  longest_stint_laps=15)})
    assert "RM" in inputs.planning_compounds()
    for plan in recommend(inputs):
        assert "RM" in {stint.compound for stint in plan.stints}


def test_with_no_profiles_at_all_the_filter_stands_down():
    """No profile anywhere means the model cannot tell compounds apart, which
    is already said elsewhere - filtering every declared compound out on top
    of that would turn thin evidence into an empty search."""
    inputs = an_input(compound_profiles={}, evidence_compound=None)
    assert inputs.planning_compounds() == ("RH", "RM", "RS")


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


# ------------------------------------------------ comparing compounds at all

def test_a_pace_delta_needs_the_same_session():
    """Two compounds run on two evenings compare the evenings.

    At Monza the whole-session medians made a Racing Medium read 0.92 s/lap
    quicker than a Racing Hard and a Racing Soft only 0.56 s - the medium
    beating the soft, which is not a thing tyres do.
    """
    from pitcrew.strategy.evidence import comparable_pace
    from pitcrew.analysis.session import LapInput

    def lap(num, code, session, ms):
        return LapInput(lap_num=num, lap_time_ms=ms,
                        fuel_start=round(100.0 - 6.5 * ((num - 1) % 5), 2),
                        fuel_end=round(100.0 - 6.5 * (((num - 1) % 5) + 1), 2),
                        compound=code, session_id=session)

    apart = ([lap(n, "RS", 1, 108_000) for n in range(1, 5)]
             + [lap(n, "RH", 2, 109_000) for n in range(5, 9)])
    assert comparable_pace(apart, "RH") == {}

    together = ([lap(n, "RS", 1, 108_000) for n in range(1, 5)]
                + [lap(n, "RH", 1, 109_000) for n in range(5, 9)])
    measured = comparable_pace(together, "RH")
    assert measured["RS"]["deltaS"] == pytest.approx(-1.0)
    assert measured["RH"]["deltaS"] == 0.0


def test_an_unmeasurable_pace_is_null_not_zero():
    """Zero says the compounds are identical. Null says we cannot tell."""
    from pitcrew.strategy.model import CompoundProfile

    unknown = CompoundProfile("RS", 0.0, 0.1, SOURCE_MEASURED)
    assert unknown.as_export()["paceDeltaSPerLap"] is None
    known = CompoundProfile("RS", -0.4, 0.1, SOURCE_MEASURED, pace_known=True)
    assert known.as_export()["paceDeltaSPerLap"] == -0.4


def test_no_crossover_is_offered_without_a_measured_pace():
    """The crossover lap is where a pace gap gets eaten by degradation. With
    no measured gap there is nothing to eat, and a lap number would be
    invented."""
    from pitcrew.strategy.model import crossover_table

    measured = an_input(compound_profiles={
        "RH": CompoundProfile("RH", 0.0, 0.0577, SOURCE_MEASURED,
                              pace_known=True),
        "RS": CompoundProfile("RS", -0.85, 0.1725, SOURCE_MEASURED,
                              pace_known=True)})
    assert [row["crossesOnLap"] for row in crossover_table(measured)] == [5]

    # The same numbers with the pace unmeasured: 0.0 would read as a real gap.
    bare = an_input(compound_profiles={
        "RH": CompoundProfile("RH", 0.0, 0.0577, SOURCE_MEASURED),
        "RS": CompoundProfile("RS", -0.85, 0.1725, SOURCE_MEASURED)})
    assert crossover_table(bare) == []


# --------------------------------------------------- the live race, not the plan
#
# Regression for S3. `events.race_laps` holds MINUTES when `race_type` is
# `time` - the spin box is relabelled and saved to the same column, and
# `race_minutes` is never written. The strategy path compensates on read; the
# live race path took the figure as a lap count, so a 45-minute Monza was
# raced as a 45-lap one: "40 to go" with 19 left, and a fuel shortfall to
# match. GT7 cannot rescue it either - it sends `laps_in_race = -1` for a
# timed race and `session_state` clamps that to 0.

def a_timed_event(**overrides) -> dict:
    fields = dict(car_name="Porsche 911 RSR", track="Monza", layout="Full",
                  race_type="time", race_laps=45)
    fields.update(overrides)
    return fields


def a_timed_plan() -> dict:
    return {"stints": [
        {"laps": 12, "compound": "RH", "fuel_l": 80.0, "start_lap": 1},
        {"laps": 12, "compound": "RH", "fuel_l": 80.0, "start_lap": 13},
    ]}


def test_a_timed_events_minutes_are_not_read_as_laps():
    context = context_from_event(a_timed_event())
    assert context.is_timed
    assert context.race_minutes == 45.0
    assert context.race_laps == 0


def test_a_lap_event_is_unchanged():
    context = context_from_event(a_timed_event(race_type="laps", race_laps=20))
    assert context.is_timed is False
    assert context.race_laps == 20
    assert context.race_minutes is None


def test_a_timed_race_counts_down_the_plans_distance_not_the_minutes():
    race = RaceCoordinator(a_timed_plan())
    context = context_from_event(a_timed_event())
    assert race.arm(context, context) is True
    assert race.state.laps_total == 24          # the plan's distance, not 45

    race.handle(SessionEvent(EventKind.RACE_STARTED, {"laps_in_race": 0}))
    assert race.state.laps_total == 24
    assert race.snapshot()["raceMinutes"] == 45.0


def test_a_timed_race_says_its_lap_count_is_an_estimate():
    """The distance follows from the clock and the pace, so it is 'about'."""
    state = RaceState(lap=5, laps_total=24, race_minutes=45.0, position=3,
                      laps_estimate_firm=True)
    # The status call is a heartbeat now: it needs a stretch of silence
    # behind it rather than a lap number divisible by five.
    state.last_said_lap = 0
    # Past halfway of a 45-minute race, which is where he asked for the laps.
    state.race_remaining_s = 1200.0
    call = next_call(state)
    assert call.kind == STATUS
    assert "19 laps to go" in call.call, call.call
    assert "20 minutes" in call.call, "the clock is the measurement"


def test_an_unresolvable_lap_count_is_named_as_two_rather_than_dropped():
    """**This doctrine changed on 28 Aug 2026, and the reason is external.**

    It used to be: at the first crossings of a timed race the median only had
    to be wrong by 0.12-0.66 s to change the predicted lap count, against a
    2.04 s spread, so the answer was unresolvable and the honest output was
    the position and nothing else. That was right while GT7's HUD was showing
    him the lap and the clock - the app was declining to add noise to figures
    he already had.

    **He turned that HUD off.** Lap, position and time remaining now exist
    nowhere but in this call, so dropping the clause no longer means "I won't
    guess", it means he has no orientation at all and no way to tell that from
    an app that has died. `ceil` near a boundary is not unknown - it is one of
    two - so both are named, and the clock, which is a measurement rather than
    an inference, is said either way.
    """
    state = RaceState(lap=5, laps_total=24, race_minutes=45.0, position=3,
                      laps_to_go_estimate=19)
    state.race_remaining_s = 1200.0
    state.last_said_lap = 0
    call = next_call(state)
    assert call.kind == STATUS
    assert "19 or 20 laps to go" in call.call, call.call
    assert "20 minutes" in call.call
    assert "Lap 5" in call.call


def test_a_clock_it_does_not_have_is_said_out_loud():
    """With the HUD off, a race with no clause about its own length is
    indistinguishable from one with no end."""
    state = RaceState(lap=5, laps_total=24, race_minutes=45.0, position=3)
    state.last_said_lap = 0
    call = next_call(state)
    assert call is not None
    assert "I don't have the clock" in call.call


def test_with_no_position_there_is_still_the_lap_and_the_clock():
    """The other half of the same change: position was the only thing this
    call had left when the count was dropped, so with no position there was
    nothing at all. The lap number does not depend on either."""
    state = RaceState(lap=5, laps_total=24, race_minutes=45.0)
    state.race_remaining_s = 1200.0
    state.last_said_lap = 0
    call = next_call(state)
    assert call is not None and "Lap 5" in call.call


def test_a_timed_race_with_no_plan_counts_down_nothing():
    """No plan is no estimate. A minutes figure read as laps is worse."""
    race = RaceCoordinator(None)
    context = context_from_event(a_timed_event())
    assert race.arm(context, context) is True
    assert race.state.laps_total is None
    assert race.snapshot()["lapsRemaining"] is None


def test_a_timed_plan_is_refused_for_a_race_of_a_different_length():
    planned = context_from_event(a_timed_event(race_laps=45))
    actual = context_from_event(a_timed_event(race_laps=50))
    ok, why = planned.matches(actual)
    assert ok is False
    assert "45 minutes" in why


def test_a_timed_plan_is_refused_for_a_lap_race():
    planned = context_from_event(a_timed_event(race_laps=45))
    actual = context_from_event(a_timed_event(race_type="laps", race_laps=45))
    ok, why = planned.matches(actual)
    assert ok is False
    assert "timed race" in why


# ------------------------------------------- re-planning one mid-race (S6)

def test_the_rest_of_a_timed_race_is_a_shorter_timed_race():
    """`race_minutes` was left at the full limit while the laps came down, so
    the model planned another whole race inside the remainder of this one: ten
    laps left came back as stints of 14 and 11, and adopting that put the next
    stop on lap 29 of a 24-lap race - no box call was ever made again."""
    rest = _remaining_race(an_input(), 10, 6.6, 100.0)
    assert rest.race_laps == 10
    assert rest.is_timed                       # still paid for in laps
    # Ten laps of a 108 s circuit is 18 minutes, not the 50 it started with.
    assert rest.race_minutes == pytest.approx(18.0)
    assert sum(stint.laps for stint in recommend(rest)[0].stints) <= 11


def test_the_remainder_is_priced_on_what_the_race_has_shown():
    """*"At the end of every lap in a race the planner should be
    recalculating the plan for optimal based on what has and is happening in
    the race, current fuel usage, lap times."*

    Four figures come from the race and each falls back to the plan's only
    where the race has not produced one yet.
    """
    plan = an_input()
    rest = _remaining_race(plan, 10, 7.4, 100.0,
                           observed_fuel_sd=0.31, achieved_lap_ms=105_000,
                           lap_sigma_s=1.4)
    assert rest.fuel_per_lap_l == 7.4          # the race's burn, not 6.6
    assert rest.fuel_sd_l == 0.31              # sizes every fill from here
    assert rest.lap_time_ms == 105_000         # achieved, incidents in
    assert rest.lap_time_sd_s == 1.4           # this race's own noise floor


def test_the_distance_cannot_move_on_pace():
    """**The guard that lets the achieved lap be used at all.** The laps left
    are counted upstream against that same median and handed in, so turning
    them back into minutes round-trips exactly whatever the figure is - a
    faster median cannot invent or remove a lap of race."""
    plan = an_input()
    for achieved in (98_000, LAP_MS, 118_000):
        rest = _remaining_race(plan, 10, 6.6, 100.0,
                               achieved_lap_ms=achieved)
        assert rest.race_laps == 10
        assert rest.race_minutes == pytest.approx(
            10 * achieved / 1000.0 / 60.0)
        # minutes / lap returns exactly the laps that went in
        assert (rest.race_minutes * 60.0) / (rest.lap_time_ms / 1000.0) == \
            pytest.approx(10.0)


def test_the_plan_s_figures_stand_where_the_race_has_none_yet():
    """Lap one has shown nothing. Falling back is not the same as ignoring."""
    plan = an_input()
    rest = _remaining_race(plan, 20, None, None)
    assert rest.fuel_per_lap_l == plan.fuel_per_lap_l
    assert rest.lap_time_ms == plan.lap_time_ms
    assert rest.fuel_sd_l == plan.fuel_sd_l
    assert rest.fuel_capacity_l == plan.fuel_capacity_l


def test_a_mid_race_replan_never_plans_past_the_flag():
    replan = assess(laps_done=18, laps_total=28, fuel_l=60.0,
                    planned_fuel_per_lap=6.6, observed_fuel_per_lap_l=7.6,
                    lap_time_ms=LAP_MS, planned_lap_time_ms=LAP_MS,
                    current_stops=1, inputs=an_input(), fuel_capacity_l=100.0)
    assert sum(replan.stint_laps) <= 11


def test_no_gain_is_not_reported_as_zero_seconds():
    """`current` is None when nothing runnable has his stop count, and the
    gain then fell through as 0.0 - a measured-sounding nothing."""
    replan = assess(laps_done=18, laps_total=28, fuel_l=60.0,
                    planned_fuel_per_lap=6.6, observed_fuel_per_lap_l=7.6,
                    lap_time_ms=LAP_MS, planned_lap_time_ms=LAP_MS,
                    current_stops=9, inputs=an_input(), fuel_capacity_l=100.0)
    assert "0 seconds in it" not in replan.reason
    assert "no longer runnable" in replan.reason


def test_a_plan_approved_before_the_minutes_were_told_apart_still_arms():
    """Saved contexts carry the minutes in `race_laps`, exactly as the column
    does. Read literally they would refuse every timed plan ever approved -
    on race day, the one moment a refusal cannot be worked around."""
    event = a_timed_event()
    stored = {"car": event["car_name"], "track": event["track"],
              "layout": event["layout"], "race_laps": 45}
    planned = context_from_stored(stored, event)
    assert planned.race_minutes == 45.0
    ok, why = planned.matches(context_from_event(event))
    assert ok, why


def test_a_context_that_already_knows_its_minutes_is_read_as_written():
    event = a_timed_event()
    stored = {"car": event["car_name"], "track": event["track"],
              "layout": event["layout"], "race_laps": 0, "race_minutes": 45.0}
    assert context_from_stored(stored, event).race_minutes == 45.0


def test_adopting_a_re_plan_moves_a_timed_races_distance_with_it():
    """The distance is an output of the plan, so a new plan is a new one."""
    race = RaceCoordinator(a_timed_plan())
    context = context_from_event(a_timed_event())
    race.arm(context, context)
    race.handle(SessionEvent(EventKind.RACE_STARTED, {"laps_in_race": 0}))
    assert race.state.laps_total == 24

    race.state.lap = 10
    race.adopt((8, 8))
    assert race.state.laps_total == 26
