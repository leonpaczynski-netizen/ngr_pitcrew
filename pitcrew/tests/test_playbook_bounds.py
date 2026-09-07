"""What the desk lets George do on his own.

**Rewritten 29 Aug 2026.** The rail used to gate whatever a playbook happened
to name and to gate nothing at all when there was no playbook - which is two
failure modes of one mechanism. A plan the app wrote itself left George
unbounded; a handover that omitted `short_shift` took the shift beep away from
a driver who had been told to short-shift, silently. Neither was a decision
anybody took.

The bound is now the **action**, in code, and it does not depend on a document
being present: four actions change the plan's SHAPE and are gated; everything
that changes only its TIMING is free. A stop is twenty seconds and cannot be
taken back. A lap either side of the box window is worth a second or two and
the next lap can revise it.
"""
from __future__ import annotations

import pytest

from pitcrew.race.calls import BOX_NOW, STAY_OUT, Call, RaceState
from pitcrew.race.coordinator import RaceCoordinator
from pitcrew.strategy.handover import (
    ACTIONS,
    STRUCTURAL_ACTIONS,
    Handover,
    PlaybookEntry,
)


def a_plan(playbook=None) -> dict:
    plan = {"stints": [{"laps": 10, "compound": "RM", "fuel_l": 60.0,
                        "start_lap": 1},
                       {"laps": 10, "compound": "RM", "fuel_l": 60.0,
                        "start_lap": 11}],
            "stops": 1, "pit_laps": [10], "binding_constraint": "fuel"}
    if playbook is None:
        return plan
    return Handover(plan=plan, playbook=playbook).as_stored(plan)


def an_entry(**over) -> PlaybookEntry:
    fields = dict(trigger="fuel_short", action="short_shift",
                  when="more than 0.5 laps short", until="the deficit clears")
    fields.update(over)
    return PlaybookEntry(**fields)


def ignoring_the_box(plan) -> RaceCoordinator:
    """Two laps past the planned stop, still out, fuel reaching the flag."""
    race = RaceCoordinator(plan)
    state = race.state
    state.lap, state.laps_total = 12, 20
    state.stint_ends_on_lap = 10
    state.fuel_l, state.fuel_per_lap_l = 60.0, 3.0
    state.said.append(BOX_NOW)
    return race


# ------------------------------------------------------- the free side

def test_a_timing_lever_is_free_with_no_playbook():
    race = RaceCoordinator(a_plan())
    assert race._may("fuel_short", "short_shift") is True
    assert race._may("fuel_short", "lift_and_coast") is True
    assert race._may("stop_missed", "offer_stay_out") is True


def test_a_timing_lever_is_free_even_when_a_playbook_omits_it():
    """**The change.** A playbook that names `incident` says nothing at all
    about whether he may short-shift, and reading omission as refusal is how
    a lever the driver was promised went missing without a word."""
    race = RaceCoordinator(a_plan([an_entry(trigger="incident",
                                            action="report_only")]))
    assert race._may("fuel_short", "short_shift") is True
    assert race._may("fuel_short", "lift_and_coast") is True
    assert race._may("fuel_long", "recost_to_flag") is True


def test_the_free_actions_are_everything_that_is_not_structural():
    free = set(ACTIONS) - STRUCTURAL_ACTIONS
    race = RaceCoordinator(a_plan())
    for action in free:
        assert race._may("fuel_short", action) is True, action


# ------------------------------------------------------- the gated four

def test_the_structural_four_are_refused_with_no_playbook():
    """The one place absence means no. George cannot put him in the pit lane
    on the strength of a file nobody wrote."""
    race = RaceCoordinator(a_plan())
    for action in STRUCTURAL_ACTIONS:
        assert race._may("fuel_short", action) is False, action


def test_the_structural_four_are_refused_when_the_playbook_omits_them():
    race = RaceCoordinator(a_plan([an_entry()]))
    for action in STRUCTURAL_ACTIONS:
        assert race._may("fuel_short", action) is False, action


def test_a_structural_action_the_desk_granted_is_allowed():
    race = RaceCoordinator(a_plan([an_entry(trigger="fuel_short",
                                            action="add_stop",
                                            when="the tank cannot reach")]))
    assert race._may("fuel_short", "add_stop") is True
    assert race._may("fuel_short", "drop_stop") is False, \
        "a different structural action for the same trigger is not the grant"
    assert race._may("incident", "add_stop") is False, \
        "a grant is for one trigger, not for the action everywhere"


def test_the_structural_set_is_the_four_and_only_the_four():
    assert STRUCTURAL_ACTIONS == {
        "add_stop", "drop_stop", "change_compound", "abandon_plan"}


# ------------------------------- the shortfall, and the lever riding on it

def test_the_shortfall_and_its_lever_both_reach_him_without_a_grant():
    """`short_shift` is a timing lever: it changes how a lap is driven, not
    what the plan is, and the next lap can revise it."""
    race = RaceCoordinator(a_plan([an_entry(trigger="incident",
                                            action="report_only")]))
    call = Call("fuel-short", 8, "Short-shift and lift into the slow corners.",
                "You're 1.2 laps short on fuel.", short_shift_drop_rpm=450.0)

    kept = race._within_the_playbook(call)

    assert kept.call == call.call
    assert kept.reason == call.reason
    assert kept.short_shift_drop_rpm == 450.0, \
        "the beep is the instruction when it is not spoken, and it is free"


def test_a_structural_instruction_is_stripped_and_the_words_are_not():
    race = RaceCoordinator(a_plan([an_entry()]))
    call = Call("fuel-short", 8, "Box this lap.", "The tank will not reach.",
                structural_action="add_stop")

    stripped = race._within_the_playbook(call)

    assert stripped.call == call.call, "the report is not the playbook's to take"
    assert stripped.reason == call.reason
    assert stripped.structural_action is None


def test_a_granted_structural_instruction_survives():
    race = RaceCoordinator(a_plan([an_entry(trigger="fuel_short",
                                            action="add_stop",
                                            when="the tank cannot reach")]))
    call = Call("fuel-short", 8, "Box this lap.", "The tank will not reach.",
                structural_action="add_stop")

    assert race._within_the_playbook(call).structural_action == "add_stop"


# ------------------------------------------- the calls that ride the rail

def _fuelled_to_the_flag(plan) -> RaceCoordinator:
    """Lap 8 of 20 with a fuel-bound stop planned at 10 and 60 L aboard
    against 3 L a lap: the stop is not needed."""
    race = RaceCoordinator(plan)
    state = race.state
    state.lap, state.laps_total = 8, 20
    state.stint_ends_on_lap = 10
    state.fuel_l, state.fuel_per_lap_l = 60.0, 3.0
    state.plan_binding_constraint = "fuel"
    return race


def test_stops_off_is_a_drop_stop_and_the_desk_can_withhold_it():
    """The Daytona handover says `fuel_long: report_only`. Executed, that is
    the litres without the instruction - and the stops stay in the plan."""
    from pitcrew.race.calls import STOPS_OFF, _stops_off

    race = _fuelled_to_the_flag(a_plan([an_entry(trigger="fuel_long",
                                                 action="report_only",
                                                 when="more than a lap over")]))
    call = _stops_off(race.state)
    assert call is not None and call.kind == STOPS_OFF
    assert call.structural_action == "drop_stop" and call.trigger == "fuel_long"

    heard = race._within_the_playbook(call)
    assert heard.call == "You're fuelled to the flag."
    assert heard.reason == call.reason, "the litres are the report"
    assert heard.structural_action is None


def test_a_withheld_drop_keeps_the_stop_in_the_plan():
    """Critic pass 5: the rail changed the sentence and not the behaviour -
    `stop_still_needed` was decided by fuel alone, so on the planned lap he
    heard "You can push" and never "Box this lap"."""
    from pitcrew.race.calls import BOX_NOW, _box_now, stop_still_needed

    race = _fuelled_to_the_flag(a_plan())
    assert race.state.drop_stop_granted is False
    assert stop_still_needed(race.state) is True
    race.state.lap = 10
    call = _box_now(race.state)
    assert call is not None and call.kind == BOX_NOW
    assert "dropping the stop was not granted" in call.reason

    granted = _fuelled_to_the_flag(a_plan([an_entry(trigger="fuel_long",
                                                     action="drop_stop",
                                                     when="over a lap")]))
    assert granted.state.drop_stop_granted is True
    assert stop_still_needed(granted.state) is False


def test_box_soon_says_why_too():
    """Critic pass 6, minor: `_box_soon` arrives BEFORE `_box_now` and had
    no clause saying why he is being boxed after "You're fuelled to the
    flag." - so the contradiction reached him first and unexplained."""
    from pitcrew.race.calls import BOX_SOON, _box_soon

    race = _fuelled_to_the_flag(a_plan())
    assert race.state.drop_stop_granted is False
    call = _box_soon(race.state)                 # lap 8, box on 10
    assert call is not None and call.kind == BOX_SOON
    assert call.call == "Box in 2."
    assert "dropping the stop was not granted" in call.reason

    granted = _fuelled_to_the_flag(a_plan([an_entry(trigger="fuel_long",
                                                    action="drop_stop",
                                                    when="over a lap")]))
    # Granted, the stop is gone and there is nothing to box for.
    assert _box_soon(granted.state) is None


def test_stops_off_granted_keeps_the_instruction():
    from pitcrew.race.calls import _stops_off

    race = _fuelled_to_the_flag(a_plan([an_entry(trigger="fuel_long",
                                                 action="drop_stop",
                                                 when="more than a lap over")]))
    heard = race._within_the_playbook(_stops_off(race.state))
    assert heard.call == "You're fuelled to the flag. No more stops on fuel."
    assert heard.structural_action == "drop_stop"


def test_stops_off_with_no_playbook_is_the_report_only():
    """Absence means no, in the one place it does."""
    from pitcrew.race.calls import _stops_off

    race = _fuelled_to_the_flag(a_plan())
    heard = race._within_the_playbook(_stops_off(race.state))
    assert heard.call == "You're fuelled to the flag."


def _at_the_cliff(plan, *, stop_planned: bool) -> RaceCoordinator:
    race = RaceCoordinator(plan)
    state = race.state
    state.lap, state.laps_total = 10, 20
    state.fuel_l, state.fuel_per_lap_l = 60.0, 5.0
    state.stint_ends_on_lap = 14 if stop_planned else None
    for step in range(4):
        worst = 0.70 + 0.08 * step
        state.note_wear(6 + step, {"fl": worst - 0.10, "fr": worst - 0.12,
                                   "rl": worst, "rr": worst - 0.05})
    return race


def test_the_wear_cliff_with_no_stop_planned_is_an_add_stop():
    from pitcrew.race.calls import WEAR, _wear

    race = _at_the_cliff(a_plan(), stop_planned=False)
    call = _wear(race.state)
    assert call is not None and call.kind == WEAR and call.tag == "cliff"
    assert call.structural_action == "add_stop" and call.trigger == "tyre_short"

    heard = race._within_the_playbook(call)
    assert heard.call == "Tyres past the stint limit.", \
        "no playbook: the reading reaches him, the pit lane does not"
    assert "measured at" in heard.reason


def test_the_wear_cliff_granted_under_tyre_short_boxes_him():
    from pitcrew.race.calls import _wear

    race = _at_the_cliff(a_plan([an_entry(trigger="tyre_short",
                                          action="add_stop",
                                          when="past the stint limit")]),
                         stop_planned=False)
    heard = race._within_the_playbook(_wear(race.state))
    assert heard.call == "Box this lap."
    assert heard.structural_action == "add_stop"


def test_the_wear_cliff_with_a_stop_ahead_brings_it_forward_for_free():
    """Timing, not shape: the stop exists and comes earlier."""
    from pitcrew.race.calls import _wear

    race = _at_the_cliff(a_plan(), stop_planned=True)
    call = _wear(race.state)
    assert call.structural_action is None
    assert race._within_the_playbook(call).call == "Box this lap."


def test_the_gate_is_still_wired_into_the_call_the_driver_gets():
    """**The mutant that survived the first draft of this file**, kept.

    Every gate test can pass while the gate reaches no race - which has been
    the defect twice in this area. This drives the real `_emit` and asserts on
    what the driver would actually be handed.
    """
    race = RaceCoordinator(a_plan([an_entry(trigger="incident",
                                            action="report_only")]))
    state = race.state
    state.lap, state.laps_total = 8, 20
    state.fuel_l, state.fuel_per_lap_l = 12.0, 3.0
    state.position, state.stint_ends_on_lap = 3, 18
    state.laps_since_stop = 8
    state.short_shift_l_per_1000rpm = 0.9

    call = race._emit()

    assert call is not None and call.kind == "fuel-short"
    assert "short" in (call.call + call.reason).lower()
    assert call.short_shift_drop_rpm, \
        "the lever is free now and must reach him through the real path"


# ----------------------------------------- the fold the driver made himself

def test_a_missed_stop_folds_the_plan_with_no_playbook():
    """The behaviour every race before the rail had, and the one the rail
    must not take away."""
    race = ignoring_the_box(a_plan())

    call = race._reconsider_ignored_box()

    assert call is not None and call.kind == STAY_OUT
    assert len(race._stints) == race.state.stint_index + 1


def test_a_missed_stop_folds_even_when_the_playbook_omits_it():
    """**It reads like `drop_stop` and it is the opposite.** The driver
    declined the stop with his hands two laps ago; George is recognising
    that, not taking it. Refusing to recognise it leaves a stop in the plan
    of record that will never happen - so the box call fires on the next lap,
    and the next, all the way to the flag.
    """
    race = ignoring_the_box(a_plan([an_entry()]))    # no stop_missed entry

    call = race._reconsider_ignored_box()

    assert call is not None and call.kind == STAY_OUT
    assert len(race._stints) == race.state.stint_index + 1, \
        "the fold is the driver's decision being recognised, not George's"
