"""The plan's per-lap targets: from Ludo's handover to George's heartbeat.

The driver, 16 Sep 2026: *"In a race with a plan we should have a lap time for
each compound and a fuel delta per lap we are trying to hit each lap based on
the optimal plan we have made. These figures should be displayed on the
dashboard and spoken by George if we are on target or not"* - and *"make sure
Ludo passes the lap time for each compound and fuel through to George and
it's all wired in."*

So the tests follow the figure end to end: the handover's `targets` block, the
gaps filled from practice at stamp, the doors that refuse a malformed one, the
lap-by-lap target (the optimiser's own expression), the verdict at the
crossing, the sentence in the heartbeat, and the board.
"""
from __future__ import annotations

import pytest

from pitcrew.race import calls as C
from pitcrew.race.coordinator import PlanContext, RaceCoordinator
from pitcrew.race.targets import (ON_TARGET_L, ON_TARGET_S, board_target_fields,
                                  burn_sentence, judge, pace_sentence,
                                  verdict_sentence)
from pitcrew.strategy.certify import certify
from pitcrew.strategy.handover import Handover, targets_not_passed
from pitcrew.strategy.model import (CompoundProfile, RaceInputs,
                                    _stint_seconds, planned_lap_s)
from pitcrew.strategy.targets import (SOURCE_AUTHOR, SOURCE_PRACTICE,
                                      LapTarget, PlanTargets, fill_targets,
                                      target_problems, targets_answered)
from pitcrew.telemetry.session_state import EventKind, Lap, SessionEvent


def _inputs(**over) -> RaceInputs:
    fields = dict(
        race_laps=20, lap_time_ms=90_000, fuel_per_lap_l=4.5,
        fuel_capacity_l=100.0, wear_per_lap=0.04, evidence_compound="RM",
        fuel_reference_load_l=40.0, available_compounds=("RM", "RH"),
        compound_profiles={
            "RM": CompoundProfile("RM", 0.0, 0.04, "measured", 30, 3,
                                  pace_known=True),
            "RH": CompoundProfile("RH", 0.8, 0.025, "measured", 20, 2,
                                  pace_known=True)})
    fields.update(over)
    return RaceInputs(**fields)


def _plan(**over) -> dict:
    plan = {"stops": 1, "stints": [
        {"laps": 10, "compound": "RM", "start_lap": 1, "fuel_l": 50.0},
        {"laps": 10, "compound": "RH", "start_lap": 11, "fuel_l": 50.0,
         "tyres": True}],
        "expects": {"expected_lap_time_ms": 90_000,
                    "expected_fuel_per_lap_l": 4.5}}
    plan.update(over)
    return plan


def _lap(num, ms, used, *, fuel_start=60.0, pit=False, out=False) -> Lap:
    return Lap(lap_num=num, lap_time_ms=ms, best_lap_ms=ms, delta_ms=0,
               fuel_start=fuel_start, fuel_end=fuel_start - used,
               fuel_used=used, position=3, is_pit_lap=pit, is_out_lap=out)


# ------------------------------------------------ one expression for a lap

def test_the_optimiser_costs_a_stint_as_the_sum_of_the_target_laps():
    """Rule 12: the plan is priced on the same lap the driver is judged on."""
    laps, base, wear, fuel, burn, weight = 14, 90.0, 0.06, 60.0, 4.5, 0.003
    summed = sum(planned_lap_s(i, base, wear, max(0.0, fuel - i * burn), weight)
                 for i in range(laps))
    assert _stint_seconds(laps, base, wear, fuel, burn, weight) == \
        pytest.approx(summed)


def test_the_target_slows_as_the_set_wears_past_its_flat_phase():
    targets = PlanTargets.from_plan({"targets": {"compounds": {
        "RM": {"lap_time_ms": 90_000, "wear_per_lap": 0.06}}}})
    fresh = targets.for_lap(compound="RM", saving=False, lap_on_set=1,
                            fuel_at_start_l=None)
    worn = targets.for_lap(compound="RM", saving=False, lap_on_set=13,
                           fuel_at_start_l=None)
    assert fresh.lap_ms == 90_000                 # 6% worn: the flat phase
    assert worn.lap_ms > fresh.lap_ms             # 78% worn: losing time


def test_the_fuel_term_is_taken_against_the_load_the_lap_time_carried():
    """A lap time set with 40 L aboard is not charged for those 40 L again."""
    targets = PlanTargets.from_plan({"targets": {"compounds": {
        "RM": {"lap_time_ms": 90_000, "reference_load_l": 40.0}}}})
    at_reference = targets.for_lap(compound="RM", saving=False, lap_on_set=1,
                                   fuel_at_start_l=40.0)
    heavier = targets.for_lap(compound="RM", saving=False, lap_on_set=1,
                              fuel_at_start_l=90.0)
    lighter = targets.for_lap(compound="RM", saving=False, lap_on_set=1,
                              fuel_at_start_l=10.0)
    assert at_reference.lap_ms == 90_000
    assert heavier.lap_ms == 90_000 + round(50 * 0.003 * 1000)
    assert lighter.lap_ms == 90_000 - round(30 * 0.003 * 1000)


def test_with_no_reference_load_the_target_carries_no_fuel_term():
    targets = PlanTargets.from_plan({"targets": {"compounds": {
        "RM": {"lap_time_ms": 90_000}}}})
    assert targets.for_lap(compound="RM", saving=False, lap_on_set=1,
                           fuel_at_start_l=95.0).lap_ms == 90_000


def test_a_saving_lap_is_judged_on_the_saving_time_and_burn():
    plan = {"targets": {"compounds": {
        "RM": {"lap_time_ms": 90_000, "save_lap_time_ms": 90_600}}},
        "fuel_burns": {"save": 4.0, "full": 4.8}}
    targets = PlanTargets.from_plan(plan)
    saving = targets.for_lap(compound="RM", saving=True, lap_on_set=1,
                             fuel_at_start_l=None)
    full = targets.for_lap(compound="RM", saving=False, lap_on_set=1,
                           fuel_at_start_l=None)
    assert (saving.lap_ms, saving.burn_l) == (90_600, 4.0)
    assert (full.lap_ms, full.burn_l) == (90_000, 4.8)


def test_no_saving_time_is_no_pace_target_and_says_why():
    targets = PlanTargets.from_plan({"targets": {"compounds": {
        "RM": {"lap_time_ms": 90_000}}}, "fuel_burns": {"save": 4.0,
                                                        "full": 4.8}})
    got = targets.for_lap(compound="RM", saving=True, lap_on_set=2,
                          fuel_at_start_l=None)
    assert got.lap_ms is None and got.why_no_lap == "no fuel-save RM target"
    assert got.burn_l == 4.0


def test_the_burn_target_is_the_plans_expected_burn_without_fuel_burns():
    targets = PlanTargets.from_plan(_plan())
    assert targets.burn_full_l == 4.5 and targets.burn_save_l is None


# ------------------------------------------- the handover: kept, filled, said

def test_ludos_figures_are_kept_and_every_gap_is_filled_from_practice():
    plan = _plan(targets={"reference_load_l": 55.0, "compounds": {
        "RM": {"lap_time_ms": 89_400}}})
    filled = fill_targets(plan, _inputs())["compounds"]
    rm, rh = filled["RM"], filled["RH"]
    # Ludo's lap time and his load stand, labelled his.
    assert (rm["lap_time_ms"], rm["lap_time_ms_source"]) == (89_400,
                                                             SOURCE_AUTHOR)
    assert (rm["reference_load_l"], rm["reference_load_l_source"]) == (
        55.0, SOURCE_AUTHOR)
    # Practice fills what he left: wear, and all of RH at practice's load.
    assert (rm["wear_per_lap"], rm["wear_per_lap_source"]) == (0.04,
                                                               SOURCE_PRACTICE)
    assert (rh["lap_time_ms"], rh["lap_time_ms_source"]) == (90_800,
                                                             SOURCE_PRACTICE)
    assert rh["reference_load_l"] == 55.0          # the top-level load
    # There is no practice figure for a saving lap, and none is invented.
    assert rh["save_lap_time_ms"] is None
    assert rh["save_lap_time_ms_source"] == SOURCE_PRACTICE


def test_practices_load_is_never_paired_with_ludos_lap_time():
    plan = _plan(targets={"compounds": {"RM": {"lap_time_ms": 89_400}}})
    filled = fill_targets(plan, _inputs())["compounds"]
    assert filled["RM"]["reference_load_l"] is None
    assert filled["RH"]["reference_load_l"] == 40.0   # practice under practice


def test_restamping_keeps_what_was_filled_before():
    """`stamp` runs again at approval; today's practice may not overwrite the
    figures the plan was written against."""
    first = _plan()
    first["targets"] = fill_targets(first, _inputs())
    assert targets_answered(first)
    again = fill_targets(first, _inputs(lap_time_ms=80_000))
    assert again["compounds"]["RM"]["lap_time_ms"] == 90_000


def test_the_desk_is_told_which_lap_targets_it_did_not_pass():
    plan = _plan(targets={"compounds": {"RM": {"lap_time_ms": 89_400}}})
    plan["targets"] = fill_targets(plan, _inputs())
    said = targets_not_passed(plan)
    assert said == ["the handover passed no RH target lap time - George "
                    "judges RH laps against practice's"]


@pytest.mark.parametrize("block, fragment", [
    ({"compounds": {"RM": {"lap_time": 90_000}}}, "lap_time is not a field"),
    ({"compounds": {"RM": {"lap_time_ms": 90.0}}}, "not a figure between"),
    ({"compounds": {"RM": {"lap_time_ms": 90_000, "save_lap_time_ms": 89_000}}},
     "cannot be the faster one"),
    ({"compounds": {"RM": {"wear_per_lap": 5}}}, "wear_per_lap is 5"),
    ({"compounds": ["RM"]}, "not a set of compounds"),
    ({"laps": {}}, "targets.laps is not a field"),
    ("fast", "targets is not a set of fields"),
])
def test_a_malformed_target_is_refused_by_name_at_the_door_and_the_gate(
        block, fragment):
    plan = _plan(targets=block)
    problems = target_problems(plan)
    assert any(fragment in problem for problem in problems), problems
    door = Handover(plan=plan, playbook=[]).validate()
    assert any(fragment in problem for problem in door), door
    gate = certify(plan, _inputs())
    assert any(fragment in refusal for refusal in gate.refusals), gate.refusals


def test_the_gate_warns_where_a_stint_has_no_lap_to_be_judged_against():
    plan = _plan(stints=[{"laps": 20, "compound": "RM", "start_lap": 1,
                          "fuel_l": 95.0, "fuel_save": True}],
                 stops=0, fuel_burns={"save": 4.0, "full": 4.5})
    plan["targets"] = fill_targets(plan, _inputs())
    got = certify(plan, _inputs())
    assert ("stint 1 has no fuel-save RM target lap time, so George gives no "
            "pace target on it") in got.warnings


def test_every_door_stamps_the_targets_and_keeps_ludos(store, event_id):
    """`stamp` is the one place every author's plan passes - the app's
    optimiser at approval, `write_strategy`, `propose_strategy`, the CLI."""
    from pitcrew.strategy.execution import stamp

    bare = {"stops": 0, "stints": [{"laps": 20, "compound": "RS",
                                    "fuel_l": 95.0, "start_lap": 1}]}
    stamped = stamp(store, event_id, bare)
    entry = stamped["targets"]["compounds"]["RS"]
    # No practice on this event: missing, sourced, never a zero (rule 3).
    assert entry["lap_time_ms"] is None
    assert entry["lap_time_ms_source"] == SOURCE_PRACTICE

    authored = dict(bare, targets={"compounds": {"RS": {"lap_time_ms": 88_800}}})
    stamped = stamp(store, event_id, authored)
    assert stamped["targets"]["compounds"]["RS"]["lap_time_ms"] == 88_800
    assert PlanTargets.from_plan(stamped).for_lap(
        compound="RS", saving=False, lap_on_set=1,
        fuel_at_start_l=None).lap_ms == 88_800


# ----------------------------------------------------------- the verdict

def _target(lap_ms=90_000, burn=4.5):
    return LapTarget(lap_ms=lap_ms, burn_l=burn, compound="RM", saving=False,
                     lap_on_set=3)


def test_a_lap_three_tenths_slow_burning_over_is_said_both_ways():
    verdict = judge(_lap(4, 90_300, 4.8), _target())
    assert verdict.lap_delta_s == pytest.approx(0.3)
    assert verdict.burn_delta_l == pytest.approx(0.3)
    assert verdict_sentence(verdict) == ("Pace three tenths slow. "
                                         "Burn 0.3 litres over.")


def test_inside_the_bands_it_is_on_target():
    verdict = judge(_lap(4, 90_150, 4.55), _target())
    assert verdict.pace_on_target and verdict.burn_on_target
    assert verdict_sentence(verdict) == "Pace on target. Burn on target."


def test_the_bands_are_the_finest_figures_the_sentences_say():
    assert pace_sentence(ON_TARGET_S) == "Pace two tenths slow."
    assert pace_sentence(-ON_TARGET_S + 0.01) == "Pace on target."
    assert burn_sentence(-ON_TARGET_L) == "Burn 0.1 litres under."
    assert pace_sentence(-1.4) == "Pace 1.4 seconds quick."


def test_a_lap_in_the_barrier_gets_no_pace_verdict_but_keeps_its_burn():
    verdict = judge(_lap(4, 96_000, 4.45), _target())    # 6.7% off
    assert verdict.lap_delta_s is None
    assert verdict_sentence(verdict) == "Burn on target."


def test_a_negative_burn_is_not_a_burn():
    """Rule 9: a reading whose reference is wrong is None, never clamped."""
    verdict = judge(_lap(4, 90_000, -2.0), _target())
    assert verdict.burn_delta_l is None
    assert verdict_sentence(verdict) == "Pace on target."


# ------------------------------------------------------- through the race

def _race(plan):
    race = RaceCoordinator(plan, fuel_per_lap_l=4.5, fuel_capacity_l=100.0,
                           planned_fuel_per_lap_l=4.5,
                           planned_lap_time_ms=90_000, mandatory_stops=0)
    context = PlanContext(car="Huracan", track="Daytona", layout="Road",
                          race_laps=20)
    assert race.arm(context, context)
    race.handle(SessionEvent(EventKind.RACE_STARTED, {"laps_in_race": 20}))
    # The driver's own setting: the heartbeat every lap.
    race.state.status_every_laps = 1
    return race


def _drive(race, laps):
    said = {}
    fuel = 95.0
    for num, ms, used in laps:
        lap = _lap(num, ms, used, fuel_start=fuel)
        fuel -= used
        call = race.handle(SessionEvent(EventKind.LAP_COMPLETED, {"lap": lap}))
        if call is not None:
            race.state.record(call)
            said[num] = call
    return said


def _one_stint_plan():
    plan = {"stops": 0, "stints": [{"laps": 20, "compound": "RM",
                                    "start_lap": 1, "fuel_l": 95.0}],
            "expects": {"expected_lap_time_ms": 90_000,
                        "expected_fuel_per_lap_l": 4.5},
            "targets": {"compounds": {"RM": {"lap_time_ms": 90_000,
                                             "lap_time_ms_source": "author"}}}}
    return plan


def test_the_heartbeat_says_each_lap_against_its_target():
    race = _race(_one_stint_plan())
    said = _drive(race, [(1, 93_000, 4.6), (2, 90_300, 4.8), (3, 89_900, 4.5)])
    # Lap 1 of a standing start is judged on nothing.
    assert "Pace" not in said[1].spoken() and "Burn" not in said[1].spoken()
    assert said[2].kind == C.STATUS
    assert "Pace three tenths slow. Burn 0.3 litres over." in said[2].spoken()
    assert "Pace on target. Burn on target." in said[3].spoken()
    # The target clause sits before the tank's, which stays last.
    assert said[3].spoken().index("Burn on target.") < \
        said[3].spoken().index("Fuel")


def test_the_board_shows_the_same_verdict_and_the_next_laps_target():
    race = _race(_one_stint_plan())
    _drive(race, [(1, 93_000, 4.6), (2, 90_300, 4.8)])
    fields = board_target_fields(race.state)
    assert fields["last_vs_target_s"] == pytest.approx(0.3)
    assert fields["last_burn_vs_target_l"] == pytest.approx(0.3)
    assert fields["target_lap_ms"] == 90_000 and fields["target_burn_l"] == 4.5


def test_a_race_with_no_plan_targets_says_nothing_about_them():
    plan = _one_stint_plan()
    plan.pop("targets")
    plan.pop("expects")
    race = _race(plan)
    said = _drive(race, [(1, 93_000, 4.6), (2, 90_300, 4.8)])
    assert race.targets is None
    assert all("Pace" not in c.spoken() for c in said.values())
    assert board_target_fields(race.state)["target_lap_ms"] is None


def test_a_pit_lap_and_its_out_lap_are_not_judged():
    race = _race(_one_stint_plan())
    race.handle(SessionEvent(EventKind.LAP_COMPLETED,
                             {"lap": _lap(1, 93_000, 4.6, fuel_start=95.0)}))
    race.handle(SessionEvent(EventKind.LAP_COMPLETED,
                             {"lap": _lap(2, 110_000, 4.6, pit=True)}))
    assert race.state.target_verdict is None
    assert race.state.lap_target is None           # the out lap is next
    race.handle(SessionEvent(EventKind.LAP_COMPLETED,
                             {"lap": _lap(3, 99_000, 4.6, out=True)}))
    assert race.state.target_verdict is None
    assert race.state.lap_target is not None


# ------------------------------------------------------------- the board

def test_the_lap_panel_trades_the_prediction_for_the_target_in_a_race(qt_app):
    from pitcrew.ui.driver_view import (DriverState, _LapTimePanel,
                                        target_burn_block, target_pace_block,
                                        TONE_GOOD, TONE_URGENT)

    panel = _LapTimePanel(value_px=58)
    race = DriverState(session_kind="race", target_lap_ms=90_000,
                       target_burn_l=4.5, last_vs_target_s=0.3,
                       last_burn_vs_target_l=-0.05)
    panel.show_state(race)
    assert not panel.vs_target.isHidden() and panel.pred.isHidden()
    assert panel.vs_target.value.text() == "+0.300"
    assert panel.burn.text() == "burn -0.05"
    assert panel.note.full_text().startswith("target 1:30.000")
    assert target_pace_block(race).tone == TONE_URGENT
    assert target_burn_block(race).tone == TONE_GOOD
    panel.show_state(DriverState(session_kind="practice"))
    assert panel.vs_target.isHidden() and not panel.pred.isHidden()


@pytest.fixture
def qt_app():
    pytest.importorskip("PyQt6.QtWidgets")
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])
