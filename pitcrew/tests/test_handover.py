"""The plan Ludo writes and George runs, and the bounds George moves inside.

The driver's split, 25 Aug 2026: *"I want to remove the race planning from the
app and plan the race with Ludo. Ludo uploads the plan and George calls it to me
and adapts on the fly."*

A plan alone does not carry that. A race stops matching its plan and something
decides what happens next — and George left to re-run the optimiser mid-race is
silently re-planning against Ludo's intent, which is how a driver hears a call
nobody approved. So the handover is a plan **and** a playbook: what George may
do alone, each entry with a trigger, an action and a limit.
"""
from __future__ import annotations

import pytest

from pitcrew.strategy.handover import (
    ACTIONS,
    FORBIDDEN_ACTIONS,
    TRIGGERS,
    Handover,
    PlaybookEntry,
    from_dict,
)


def a_plan() -> dict:
    return {"stints": [{"laps": 14, "compound": "RS", "fuel_l": 90.0,
                        "start_lap": 1},
                       {"laps": 6, "compound": "RS", "fuel_l": 40.0,
                        "start_lap": 15}],
            "binding_constraint": "evidence"}


def an_entry(**over) -> PlaybookEntry:
    fields = dict(trigger="fuel_short", action="short_shift",
                  when="more than 1.0 lap short of the flag",
                  until="the deficit clears")
    fields.update(over)
    return PlaybookEntry(**fields)


# ------------------------------------------------------------ the playbook

def test_a_well_formed_entry_passes():
    assert an_entry().validate() == []


def test_a_trigger_george_cannot_act_on_is_refused():
    problems = an_entry(trigger="driver_feels_slow").validate()

    assert problems and "not a trigger" in problems[0]


def test_an_action_george_cannot_execute_is_refused():
    problems = an_entry(action="raise_the_rear_wing").validate()

    assert problems and "not something George can execute" in problems[0]


@pytest.mark.parametrize("action", FORBIDDEN_ACTIONS)
def test_a_standing_refusal_may_not_appear_in_a_playbook(action):
    """**The dangerous case.** A playbook entry is EXECUTED. Fuel map and
    forward brake bias are refusals the driver has stated outright, and a rule
    he believes is armed and is not is worse than no rule."""
    problems = an_entry(action=action).validate()

    assert problems
    assert "standing refusal" in problems[0]


def test_an_entry_with_no_condition_is_refused():
    """An adaptation that always fires is not an adaptation, it is the plan."""
    problems = an_entry(when="   ").validate()

    assert problems and "no condition" in problems[0]


def test_two_entries_for_one_trigger_are_refused():
    """George would have to choose, and choosing is not his half."""
    h = Handover(plan=a_plan(), playbook=[
        an_entry(action="short_shift"),
        an_entry(action="lift_and_coast"),
    ])

    problems = h.validate()

    assert any("two playbook entries" in p for p in problems)


# ------------------------------------------------------------- the handover

def test_a_plan_with_no_stints_is_refused():
    assert "the plan has no stints" in Handover(plan={}).validate()


def test_a_plan_with_no_playbook_is_allowed():
    """A short sprint with one stop and no weather in it needs no adaptations.
    What must not happen is the driver ASSUMING a playbook exists."""
    assert Handover(plan=a_plan()).validate() == []


def test_it_names_what_george_will_not_handle():
    """The half of the contract the driver actually has to know."""
    h = Handover(plan=a_plan(), playbook=[an_entry()])

    unhandled = h.unhandled()

    assert "fuel_short" not in unhandled
    assert "rain" in unhandled and "tyre_short" in unhandled
    assert "safety_car" not in unhandled, "retired 7 Sep 2026: no channel"


def test_unhandled_travels_on_the_stored_form():
    h = Handover(plan=a_plan(), playbook=[an_entry()])

    assert set(h.as_dict()["unhandled"]) == set(h.unhandled())


def test_it_round_trips():
    """**Through the stored shape**, which is the plan's own keys with the
    handover's alongside under one key. `as_dict` is now only the handover's
    half - the plan is not nested inside it, because nesting produced a row
    that saved cleanly and was then refused on the grid for naming no
    stints."""
    h = Handover(plan=a_plan(), playbook=[an_entry()],
                 assumptions=["burn measured at 3x, raced at 3x"])

    back = from_dict(h.as_stored(h.plan))

    assert back.plan == h.plan
    assert back.assumptions == h.assumptions
    assert [e.as_dict() for e in back.playbook] == [e.as_dict()
                                                    for e in h.playbook]


def test_an_unknown_key_is_ignored_rather_than_guessed_at():
    back = from_dict({"plan": a_plan(), "mood": "confident"})

    assert back.plan["stints"]
    assert back.playbook == []


# -------------------------------------------------- what the vocabulary is

def test_the_drivers_two_refusals_are_not_reachable_as_actions():
    for action in FORBIDDEN_ACTIONS:
        assert action not in ACTIONS


def test_every_trigger_is_something_the_app_can_detect():
    """A trigger the app cannot see is a rule that never fires, which is the
    silent-armed problem again."""
    assert set(TRIGGERS) >= {"fuel_short", "stop_missed", "incident",
                             "tyre_short"}
    assert "safety_car" not in TRIGGERS, \
        "no flag state in any packet, no lobby setting - retired 7 Sep 2026"


def test_a_stored_safety_car_entry_is_refused_not_crashed():
    """Strategies 15 and 16 on the live file carry one. They are raced and
    gone; loading them must name the problem, not raise."""
    problems = an_entry(trigger="safety_car").validate()
    assert problems and "safety_car" in problems[0]
