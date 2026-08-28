"""The two blocks a plan has to carry before anything can execute it.

`expects` is what the plan was costed against; `context` is what it was built
for. They are the only parts of a stored plan the race reads once it is
running, and they were built in exactly one place - the approval path for the
app's own optimiser. That was fine for as long as the optimiser was the only
author, and it is not: a plan from the race engineer at the desk arrived with
neither, armed, and ran blind.

Blind is the word. With no `expects` the race carries `planned_fuel_per_lap_l`
and `planned_lap_time_ms` as `None`, and every per-lap comparison then reports
nothing rather than reporting a problem - which is indistinguishable, from the
driver's seat, from a race going to plan.
"""
from __future__ import annotations

from pitcrew.strategy.execution import CONTRACT_KEYS, context_from_event, stamp

A_PLAN = {
    "stops": 1,
    "pit_laps": [10],
    "stints": [{"laps": 10, "compound": "RS", "fuel_l": 60.0, "start_lap": 1},
               {"laps": 10, "compound": "RS", "fuel_l": 60.0, "start_lap": 11}],
    "binding_constraint": "fuel",
}


def test_a_plan_from_anywhere_comes_back_with_both_blocks(store, event_id):
    stamped = stamp(store, event_id, A_PLAN)
    for key in CONTRACT_KEYS:
        assert key in stamped, f"{key} is what the race reads; it has to be there"


def test_the_context_is_the_event_it_was_built_for(store, event_id):
    stamped = stamp(store, event_id, A_PLAN)
    assert stamped["context"]["car"] == "Porsche 911 RSR"
    assert stamped["context"]["track"] == "Autodromo Nazionale Monza"
    assert stamped["context"]["race_laps"] == 20
    assert stamped["context"]["race_minutes"] is None


def test_a_timed_race_reads_its_overloaded_column_as_minutes(store):
    """`events.race_laps` holds MINUTES when `race_type` is `'time'`. One
    column, two meanings, and this is the place that sorts it out - a plan
    stamped with 30 laps for a 30-minute race would refuse to arm."""
    timed = store.create_event(
        name="Timed", track="Fuji", layout="GP", car_id=1, car_name="RSR",
        race_type="time", race_laps=30)
    context = context_from_event(store.get_event(timed))
    assert context.race_minutes == 30.0
    assert context.race_laps == 0
    assert context.is_timed


def test_it_does_not_change_the_plan_it_was_given(store, event_id):
    """A new dict, so an author can stamp a plan it does not own."""
    original = dict(A_PLAN)
    stamp(store, event_id, A_PLAN)
    assert A_PLAN == original


def test_an_existing_contract_is_left_alone(store, event_id):
    """**`expects` is a snapshot, not a reading.** It is what THIS plan was
    costed against, and re-stamping it would quietly swap those figures for
    today's - which is how "burning 8% under plan" was once said against a
    burn no plan ever held."""
    already = dict(A_PLAN)
    already["expects"] = {"expected_fuel_per_lap_l": 2.75,
                          "expected_lap_time_ms": 91_000}
    already["context"] = {"car": "something else", "track": "somewhere else",
                          "layout": None, "race_laps": 5, "race_minutes": None}
    stamped = stamp(store, event_id, already)
    assert stamped["expects"]["expected_fuel_per_lap_l"] == 2.75
    assert stamped["context"]["car"] == "something else"


def test_no_evidence_gives_nulls_and_never_zeroes(store, event_id):
    """CLAUDE.md §4.3. An event with no practice laps cannot say what the plan
    expects to burn, and `0.0` is the one answer that gets diagnosed as a real
    value - it would have every comparison reporting a car massively under
    plan. `certify` is what refuses the plan for it; this only has to not lie."""
    stamped = stamp(store, event_id, A_PLAN)
    expects = stamped["expects"]
    assert expects["expected_fuel_per_lap_l"] is None
    assert expects["expected_lap_time_ms"] is None
    assert expects["expected_wear_per_lap"] is None
    # And the sample count is a real zero, because that one IS measured.
    assert expects["expected_fuel_samples"] == 0


def test_it_refuses_an_event_that_does_not_exist(store):
    """Rather than stamping a context of empty strings, which would arm."""
    try:
        stamp(store, 9999, A_PLAN)
    except ValueError as exc:
        assert "9999" in str(exc)
    else:
        raise AssertionError("stamped a plan for an event that is not there")
