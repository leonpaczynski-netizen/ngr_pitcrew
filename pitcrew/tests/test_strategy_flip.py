"""Plan row 5.1 - flip points - and the two optimiser defects the flip search found.

**Found 14 Sep 2026 by running the flip search over Suzuka's own inputs.** As
the burn fell from 9.2 to 6.6 L/lap at strategy 32's lap time, the optimiser's
first choice went 1 stop, no runnable plan, 1, 4, 1, 3, 1, 2 - a decision that
cannot be right, because a lighter burn never makes a race need more stops or
none at all. Two causes, one shape (rule 12: the same question answered by two
expressions):

1. **The tank.** Stints were laid out against `fuel_limited_laps` (median burn,
   a flat lap of margin) and refused against `planned_fill_l` (load-integrated,
   the measured margin). At 7.13 L/lap a 13-lap stint passed the first and
   needed 101 L under the second.
2. **The stop.** A stop's refuelling was costed three ways: `stint_cost_s`
   with a flat lap of margin, `timed_race_laps` with the next stint's planned
   fill, and `build_plan` with the fill of the stint that had just ENDED. In a
   timed race the split chooser then picked 14 + 1, whose stop `build_plan`
   found after the flag - the one-stop vanished and 12 + 1 + 1 led; in lap
   races a faster 12 + 8 was reported 8.7 s slower than 11 + 9 (critic pass 1).
   A clock guard on the split was built for the first symptom and removed:
   with the stop costed one way it changed no plan in 840 timed races.

The fixture is event 13's inputs as `build_inputs` assembled them on 14 Sep,
copied by value so this runs without a database.
"""
from __future__ import annotations

import time
from dataclasses import replace

import pytest

from pitcrew.strategy import flip, model
from pitcrew.strategy.certify import certify
from pitcrew.strategy.model import (
    CompoundProfile,
    RaceInputs,
    build_plan,
    elapsed_for_s,
    fuel_limited_laps,
    max_stint_laps,
    planned_fill_l,
    recommend,
    tank_limited_laps,
)


def suzuka(**changes) -> RaceInputs:
    """Event 13 (Supercars Rd7, Suzuka, 30 min), strategy 32's lap and burn."""
    rs = CompoundProfile(
        code="RS", pace_delta_s=0.0, wear_per_lap=0.04861, source="measured",
        laps_measured=17, stints_measured=3, longest_stint_laps=14,
        pace_known=False, wear_confidence="assumed",
        deepest_observed_frac=0.6944444444444444)
    base = RaceInputs(
        race_laps=14, lap_time_ms=125032, race_minutes=30.0,
        start_hour=15.621, time_multiplier=1.0, extra_time_s=None,
        fuel_per_lap_l=9.116, fuel_sd_l=0.2315429930617396, fuel_samples=17,
        fuel_reference_load_l=39.576748840949115,
        lap_time_sd_s=5.352822227572848, fuel_capacity_l=100.0,
        refuel_rate_lps=2.0, pit_loss_s=20.0,
        pit_loss_source="declared-on-the-event-page", pit_dead_time_s=7.5,
        wear_per_lap=0.04861, wear_measured_at_race_multiplier=True,
        mandatory_stops=0, available_compounds=("RS", "RM", "RH"),
        required_compounds=(), fuel_weight_s_per_l_per_lap=0.003,
        evidence_compound="RS", compound_profiles={"RS": rs})
    return replace(base, **changes)


# --- the tank: one expression ----------------------------------------------

@pytest.mark.parametrize("burn,load", [(9.116, None), (7.206, None), (7.13, None),
                                       (6.58, None), (5.5, None),
                                       # A heavy reference load (critic pass 1, T2).
                                       (4.0, 90.0), (7.2, 90.0)])
def test_the_tank_limit_is_the_planned_fill_that_fits(burn, load):
    inputs = suzuka(fuel_per_lap_l=burn,
                    fuel_reference_load_l=load or 39.576748840949115)
    laps = tank_limited_laps(inputs)
    assert planned_fill_l(laps, inputs)[0] <= inputs.fuel_capacity_l
    assert planned_fill_l(laps + 1, inputs)[0] > inputs.fuel_capacity_l


def test_the_walk_goes_up_when_the_flat_estimate_is_short():
    """Critic pass 1, T2: with a light car (reference load well above the
    stint's average) the flat estimate is below the answer, and a walk that
    only goes down stops short."""
    for load in (90.0, 99.0):
        inputs = suzuka(fuel_per_lap_l=7.2, fuel_reference_load_l=load,
                        fuel_sd_l=0.05, race_minutes=None, race_laps=40)
        flat = int(inputs.fuel_capacity_l / inputs.fuel_per_lap_l)
        if tank_limited_laps(inputs) > flat:
            return
    pytest.fail("no fixture here puts the answer above the flat estimate - "
                "the upward walk is untested")


def test_the_tank_limit_keeps_unknown_apart_from_zero():
    assert tank_limited_laps(suzuka(fuel_per_lap_l=None)) is None
    assert tank_limited_laps(suzuka(fuel_capacity_l=None)) is None
    # An electric car has no fuel ceiling (CLAUDE.md 3.4) - not a ceiling of 0.
    assert tank_limited_laps(suzuka(fuel_capacity_l=0.0)) is None
    # A tank that cannot carry one lap and its margin is a known ceiling of 0.
    assert tank_limited_laps(suzuka(fuel_capacity_l=5.0)) == 0


def test_a_tiny_burn_does_not_walk_forever():
    """Critic pass 1: at 0.2 L/lap the load slope makes the fill shrink as laps
    rise, and an unbounded walk ran past 120 s."""
    started = time.monotonic()
    answer = tank_limited_laps(suzuka(fuel_per_lap_l=0.2))
    assert time.monotonic() - started < 10.0
    assert answer is None or answer <= model.TANK_WALK_LAPS


def test_the_cache_does_not_serve_one_burn_to_another():
    token = model._SCRATCH.set({"cost": {}, "split": {}})
    try:
        heavy = tank_limited_laps(suzuka(fuel_per_lap_l=9.116))
        light = tank_limited_laps(suzuka(fuel_per_lap_l=6.0))
    finally:
        model._SCRATCH.reset(token)
    assert light > heavy


def lap_race(**changes) -> RaceInputs:
    """A lap race whose measured burn scatter sizes a margin under a full lap,
    so the plan's own tank limit is ABOVE the flat-margin one - where the
    certifier and `max_stint_laps` disagreed with the optimiser (events 10, 12
    and 14 at HEAD: "stint 1 runs 12 laps on a tank that reaches 11")."""
    fields = dict(race_minutes=None, race_laps=20, fuel_per_lap_l=8.1,
                  fuel_sd_l=0.08)
    fields.update(changes)
    return suzuka(**fields)


def test_the_fixture_premise_the_plan_limit_is_above_the_flat_one():
    inputs = lap_race()
    assert tank_limited_laps(inputs) > fuel_limited_laps(inputs.fuel_capacity_l,
                                                        inputs.fuel_per_lap_l)


def test_max_stint_laps_uses_the_plan_tank_limit():
    inputs = lap_race(wear_per_lap=0.01)
    assert max_stint_laps(inputs)[0] == tank_limited_laps(inputs)


def test_the_certifier_accepts_a_stint_the_plan_tank_holds():
    inputs = lap_race()
    laps = tank_limited_laps(inputs)
    plan = {"stops": 1, "stints": [
        {"laps": laps, "compound": "RS", "fuel_l": planned_fill_l(laps, inputs)[0]},
        {"laps": inputs.race_laps - laps, "compound": "RS",
         "fuel_l": planned_fill_l(inputs.race_laps - laps, inputs)[0]}]}
    refusals = certify(plan, inputs).refusals
    assert not [r for r in refusals if "on a tank that reaches" in r], refusals


def test_a_lap_race_plan_costs_its_stops_with_the_next_stints_fill():
    """Critic pass 1: `build_plan` charged the stop with the fill of the stint
    that had just ended, so its total disagreed with the optimiser's own cost of
    the same split and a faster split was reported slower."""
    inputs = lap_race()
    for stops in (1, 2):
        plan = build_plan(inputs, stops, None)
        split = [stint.laps for stint in plan.stints]
        profiles = [inputs.profile_for(stint.compound) for stint in plan.stints]
        assert plan.total_time_s == pytest.approx(
            elapsed_for_s(inputs, split, profiles), abs=1e-6)


# --- the decision is monotone in burn ---------------------------------------

def test_a_lighter_burn_never_adds_a_stop_or_loses_the_plan():
    """The scan that exposed both defects. At strategy 32's lap time every burn
    from 9.2 down to 5.5 L/lap is a one-stop race on this evidence."""
    seen = {}
    burn = 9.2
    while burn > 5.49:
        decision = flip.decide(suzuka(fuel_per_lap_l=round(burn, 3)))
        seen[round(burn, 2)] = decision.words()
        burn -= 0.02
    wrong = {b: words for b, words in seen.items()
             if not words.startswith("1 stop")}
    assert not wrong, f"the first choice moved off one stop at {wrong}"


def test_the_re_solved_one_stop_keeps_the_lap_the_clock_allows():
    """At 6.58 L/lap the first split was 14 + 1 with its stop after the flag.
    Refused, the search lays fifteen laps out again as a legal one-stop - it
    must not settle for a lap less."""
    best = recommend(suzuka(fuel_per_lap_l=6.58))[0]
    assert best.stops == 1 and best.laps_completed == 15


@pytest.mark.parametrize("burn", [7.13, 6.58])
def test_no_timed_plan_is_laid_out_with_a_stop_after_the_flag(burn):
    inputs = suzuka(fuel_per_lap_l=burn)
    one_stop = build_plan(inputs, 1, None)
    assert one_stop.feasible, one_stop.notes[:2]
    assert not any("after the" in note and "flag" in note
                   for note in one_stop.notes)


def test_the_certifier_does_not_refuse_what_the_optimiser_built():
    """Rule 12 at the grid: Suzuka's plan was refused three times because the two
    measured the race differently."""
    for burn in (9.116, 7.13, 6.58):
        inputs = suzuka(fuel_per_lap_l=burn)
        best = recommend(inputs)[0]
        stored = {"stops": best.stops,
                  "stints": [{"laps": s.laps, "compound": s.compound,
                              "fuel_l": s.fuel_l} for s in best.stints]}
        refusals = certify(stored, inputs).refusals
        assert not [r for r in refusals if "on a tank that reaches" in r], refusals


# --- flip points --------------------------------------------------------------

def test_flip_points_name_the_input_and_what_it_becomes():
    report = flip.flip_points(suzuka())
    assert report.base.stops == 1
    burn_up = [f for f in report.for_input("fuel_per_lap_l") if f.direction == "up"]
    assert burn_up and burn_up[0].at is not None
    assert burn_up[0].at > 9.116
    assert burn_up[0].becomes != report.base


def test_an_unknown_input_is_not_searched_and_says_so():
    report = flip.flip_points(suzuka(wear_per_lap=None, compound_profiles={}),
                              names=("wear_scale",))
    assert any("tyre wear" in note and "not searched" in note
               for note in report.notes)


def test_the_suzuka_save_is_found_at_the_pace_the_race_actually_ran():
    """Session 166: 14 laps, 1809.4 s, 7.38 L/lap for twelve of them, then a save
    to the flag on zero stops with 2.73 L left. At the race's own mean lap the
    model wants one stop, and a saving of a few litres over the race removes it
    - which is what he did."""
    ran = suzuka(fuel_per_lap_l=7.38, lap_time_ms=129246)
    assert flip.decide(ran).stops == 1
    saving = flip.flip_on_saving(ran)
    assert saving is not None and saving.litres is not None
    assert 3.0 <= saving.litres <= 10.0
    assert saving.becomes.stops == 0
    assert "cost not priced" in saving.words()


def test_a_saving_as_big_as_the_burn_is_not_a_lever():
    assert flip.with_saving(suzuka(), save_l=200.0, laps=14, cost_s_per_l=None) is None


def test_two_refusals_are_the_same_decision():
    assert flip.Decision(None, impossible="a") == flip.Decision(None, impossible="b")


def test_describe_never_prints_a_bare_number():
    report = flip.flip_points(suzuka(), names=("fuel_per_lap_l",))
    text = "\n".join(flip.describe(report))
    assert "L/lap" in text and " up:" not in text and " down:" not in text


def test_a_plan_with_no_stop_has_no_saving_to_find():
    assert flip.flip_on_saving(suzuka(fuel_per_lap_l=5.0, lap_time_ms=135000)) is None
