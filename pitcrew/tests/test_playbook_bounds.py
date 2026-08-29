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
