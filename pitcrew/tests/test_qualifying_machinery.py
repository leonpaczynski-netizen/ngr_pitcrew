"""Qualifying, through the same machinery as the race.

The driver's decision on 29 Aug: quali uses the same plan, the same briefing
and the same certificate path rather than a second design. **No second plan
format and no second knowledge record shape** - a circuit's tow value, its
measured wear rate and the calls Ludo does not want made there are facts about
the circuit, not about the session type, and a second record would be a second
thing to keep in step.
"""
from __future__ import annotations

import pytest

from pitcrew.race.knowledge import Knowledge
from pitcrew.race.qualifying import QualifyingCoach
from pitcrew.store.db import Store


@pytest.fixture()
def store(tmp_path):
    one = Store(tmp_path / "t.db")
    try:
        yield one
    finally:
        one.close()


# --- one briefing, both session kinds ---------------------------------------

def a_coach(**over) -> QualifyingCoach:
    fields = dict(window=None, reference=None, speak=None)
    fields.update(over)
    return QualifyingCoach(**fields)


def test_the_briefing_can_turn_a_temperature_call_off_in_quali_too():
    """The same record and the same rule as in the race: a circuit where the
    temperature call is noise is a circuit where it is noise on a flying lap."""
    brief = Knowledge(circuit_key="x", calls_off=(
        {"kind": "tyre-temp", "why": "the out-lap is too short to matter"},))
    coach = a_coach(knowledge=brief)
    coach.said.clear()   # the coach announces its own missing reference first

    assert coach._say("Fronts are cold.", 100.0, temp_call=True) is False
    assert coach.said == []


def test_a_line_call_is_never_silenced():
    """**Events are true exactly once.** Turning one off does not quiet the
    engineer, it deletes the only chance he had to hear it."""
    brief = Knowledge(circuit_key="x", calls_off=(
        {"kind": "tyre-temp", "why": "noise here"},))
    coach = a_coach(knowledge=brief)
    coach.said.clear()

    assert coach._say("Out lap.", 100.0) is True
    assert coach.said == ["Out lap."]


def test_no_briefing_silences_nothing():
    coach = a_coach()
    assert coach._say("Fronts are cold.", 100.0, temp_call=True) is True


def test_there_is_no_qualifying_variant_of_the_briefing():
    """One record shape serves both. If a `quali_` field ever appears here,
    somebody has decided a circuit means two different things depending on
    what he is driving on it, and that decision should be visible."""
    from dataclasses import fields

    names = {field.name for field in fields(Knowledge)}
    assert not [name for name in names if name.startswith("quali")]


# --- a plan the app did not write -------------------------------------------

def test_a_written_qualifying_plan_round_trips(store):
    event_id = store.create_event(name="r", track="Monza", car_name="x")
    plan = {"fuel_l": 22.0, "runs": [{"laps": 3, "flying_laps": 1}],
            "assumptions": ["session is 10 minutes"]}

    store.save_qualifying_plan(event_id, plan)

    assert store.qualifying_plan(event_id) == plan


def test_no_written_plan_means_the_app_costs_it(store):
    """`build` stays as the fallback. It is the app authoring, which is what
    the architecture retired - so it is what happens when nobody wrote one,
    not what happens by default."""
    event_id = store.create_event(name="r", track="Monza", car_name="x")
    assert store.qualifying_plan(event_id) is None


def test_the_newest_written_plan_wins(store):
    event_id = store.create_event(name="r", track="Monza", car_name="x")
    store.save_qualifying_plan(event_id, {"fuel_l": 22.0})
    store.save_qualifying_plan(event_id, {"fuel_l": 18.0})

    assert store.qualifying_plan(event_id)["fuel_l"] == 18.0


def test_a_quali_plan_is_not_a_race_plan(store):
    """A distinct status rather than a distinct table, and `approved_strategy`
    filters on `'approved'` - so the two cannot collide."""
    event_id = store.create_event(name="r", track="Monza", car_name="x")
    store.save_qualifying_plan(event_id, {"fuel_l": 22.0})

    assert store.get_approved_strategy(event_id) is None


def test_a_race_plan_is_not_a_quali_plan(store):
    event_id = store.create_event(name="r", track="Monza", car_name="x")
    strategy_id = store.save_strategy(event_id, {"stints": []})
    store.approve_strategy(strategy_id)

    assert store.qualifying_plan(event_id) is None


def test_the_written_plan_is_preferred_by_the_screen():
    """The seam, asserted where it lives: a plan the app did not write wins,
    and the screen says which it is showing."""
    import inspect

    from pitcrew.controller import PitCrewController

    source = inspect.getsource(PitCrewController)
    assert "self.store.qualifying_plan(event[\"id\"])" in source
    assert "the app did not cost this one" in source


def test_a_quali_plan_has_to_say_how_much_fuel_goes_in():
    """Qualifying is the run where every litre is mass dragged round the only
    lap that counts. A plan that does not name the fuel has not answered the
    question it exists for."""
    import json

    from pitcrew.mcp.server import write_qualifying_plan

    reply = json.loads(write_qualifying_plan(1, json.dumps({"runs": []})))
    assert reply["written"] is False
    assert "fuel" in reply["error"]
