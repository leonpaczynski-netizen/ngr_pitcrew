"""Ludo's briefing: what George cannot derive, written at the desk.

The driver settled three things on 29 Aug 2026 that between them leave exactly
one place for intelligence to enter a race. Ludo authors and the app
instruments; no model runs in the live loop; the playbook is a rail on four
structural actions rather than a briefing. So everything clever is
**precomputed numbers read by deterministic rules** - and this is where they
live.
"""
from __future__ import annotations

import pytest

from pitcrew.race import knowledge as kb
from pitcrew.race.calls import GREEN, RaceState, next_call
from pitcrew.race.coordinator import RaceCoordinator
from pitcrew.race.knowledge import NO_NOTES, Knowledge, KnowledgeError


def a_briefing(**over) -> Knowledge:
    fields = dict(circuit_key="watkins-glen-international-long-course",
                  pit_loss_s=15.7, refuel_l_per_s=1.001,
                  author="Ludo", written_at="2026-08-29T10:00:00")
    fields.update(over)
    return Knowledge(**fields)


# --- what a record may say --------------------------------------------------

def test_a_record_may_not_silence_a_call_that_does_not_exist():
    """A typo in `calls_off` is a call that quietly never happens, which is
    indistinguishable from an engineer with nothing to say."""
    with pytest.raises(KnowledgeError) as raised:
        a_briefing(calls_off=({"kind": "box-nwo", "why": "typo"},)).validate()
    assert "box-nwo" in str(raised.value)


def test_silencing_a_call_requires_a_reason():
    """A call turned off with no reason on file is one nobody can put back."""
    with pytest.raises(KnowledgeError):
        a_briefing(calls_off=({"kind": "box-soon"},)).validate()


def test_a_zero_pit_loss_is_refused():
    """It would price a stop at nothing, which is the arithmetic that decides
    whether he stops at all."""
    with pytest.raises(KnowledgeError):
        a_briefing(pit_loss_s=0.0).validate()


def test_a_measured_looking_record_is_still_declared():
    """Every field here is typed by a person. However carefully it was arrived
    at, it is not something the telemetry saw - CLAUDE.md rule 5."""
    assert a_briefing().as_export()["source"] == "race-engineer, declared"


# --- the wear rate carries its sample count ---------------------------------

def test_a_wear_rate_comes_back_with_how_many_stints_are_behind_it():
    briefing = a_briefing(wear_rates={"RS": {"perLap": 0.041, "samples": 6}})
    assert briefing.wear_per_lap("RS") == (0.041, 6)
    assert briefing.wear_per_lap("rs") == (0.041, 6)


def test_an_unmeasured_compound_is_none_and_not_zero():
    """Rule 3. A zero rate here is a tyre that never wears."""
    rate, samples = a_briefing().wear_per_lap("RH")
    assert rate is None and samples == 0


# --- the stop, measured, beats the one that was declared --------------------

def test_the_briefing_s_pit_loss_replaces_the_event_s():
    """Watkins: 15.7 s measured against 20 s declared, and nothing carried the
    measurement into the next race."""
    race = RaceCoordinator({}, pit_loss_s=20.0, knowledge=a_briefing())
    assert race.pit_loss_s == 15.7


def test_a_briefing_with_no_pit_loss_leaves_the_event_s_alone():
    race = RaceCoordinator({}, pit_loss_s=20.0,
                           knowledge=a_briefing(pit_loss_s=None))
    assert race.pit_loss_s == 20.0


def test_a_briefed_figure_is_not_marked_measured():
    """It is typed at a desk. `pit_loss_measured` is what tells the fuel path
    whether anybody actually timed a stop here."""
    race = RaceCoordinator({}, pit_loss_s=20.0, knowledge=a_briefing())
    assert race.pit_loss_measured is False


# --- calls Ludo does not want made here -------------------------------------

def a_race_with(briefing, **state) -> RaceCoordinator:
    race = RaceCoordinator({}, knowledge=briefing)
    for key, value in state.items():
        setattr(race.state, key, value)
    return race


def test_a_decision_the_briefing_turns_off_is_not_said():
    briefing = a_briefing(calls_off=(
        {"kind": "fuel-short", "why": "the straights are too short to pay"},))
    race = a_race_with(briefing)
    call = _a_fuel_short_call()

    assert race._within_the_briefing(call) is None


def test_an_event_the_briefing_turns_off_is_said_anyway():
    """**The green, the flag, an incident and the run-in are true exactly
    once.** Turning one off does not quiet the engineer, it deletes the only
    chance the driver had to hear it."""
    briefing = a_briefing(calls_off=(
        {"kind": GREEN, "why": "he can see the lights"},))
    race = a_race_with(briefing)
    green = next_call(RaceState(lap=0, laps_total=20))

    assert race._within_the_briefing(green) is green


def test_a_call_the_briefing_says_nothing_about_survives():
    race = a_race_with(a_briefing())
    call = _a_fuel_short_call()
    assert race._within_the_briefing(call) is call


def test_no_briefing_at_all_silences_nothing():
    race = a_race_with(None)
    call = _a_fuel_short_call()
    assert race._within_the_briefing(call) is call


# --- absent is announced, never papered over --------------------------------

def test_the_green_says_there_are_no_notes():
    """Silent fallback is the defect pattern that made the gauge ratchet
    invisible for a whole race: the number setting the bar never appeared
    anywhere the driver could see it."""
    call = next_call(RaceState(lap=0, laps_total=20, no_notes=True))
    assert call.kind == GREEN
    assert NO_NOTES in call.spoken()


def test_the_green_says_nothing_extra_when_a_briefing_exists():
    call = next_call(RaceState(lap=0, laps_total=20, no_notes=False))
    assert NO_NOTES not in call.spoken()


def test_it_is_said_at_the_green_or_not_at_all():
    """By lap two it is news about a decision already taken, and the green is
    the only crossing where nothing else is competing."""
    later = next_call(RaceState(lap=4, laps_total=20, no_notes=True,
                                fuel_l=40.0, fuel_per_lap_l=3.0))
    assert later is None or NO_NOTES not in later.spoken()


# --- the store round-trip ---------------------------------------------------

def test_the_event_s_own_record_wins_over_the_circuit_s(tmp_path):
    """Pit loss and the tow are track constants written once with a null
    event; rival tendencies belong to one race. Preferring the specific is
    what stops the constants being re-typed every round."""
    from pitcrew.store.db import Store

    store = Store(tmp_path / "t.db")
    try:
        event_id = store.create_event(
            name="r", track="Watkins Glen International",
            layout="Long Course", car_name="x")
        key = "watkins-glen-international-long-course"
        store.save_race_knowledge(Knowledge(circuit_key=key, pit_loss_s=15.7,
                                            author="Ludo"))
        store.save_race_knowledge(Knowledge(circuit_key=key, event_id=event_id,
                                            pit_loss_s=16.4, author="Ludo"))

        assert store.get_race_knowledge(key, event_id).pit_loss_s == 16.4
        assert store.get_race_knowledge(key, None).pit_loss_s == 15.7
        assert store.get_race_knowledge(key, 999).pit_loss_s == 15.7, \
            "another race at this circuit falls back to the track constants"
    finally:
        store.close()


def test_a_record_is_refused_on_the_way_in_and_not_half_stored(tmp_path):
    """`validate` runs in the store so no writer, including the MCP seam, can
    skip it."""
    from pitcrew.store.db import Store

    store = Store(tmp_path / "t.db")
    try:
        with pytest.raises(KnowledgeError):
            store.save_race_knowledge(Knowledge(
                circuit_key="x",
                calls_off=({"kind": "not-a-call", "why": "?"},)))
        assert store.get_race_knowledge("x") is None
    finally:
        store.close()


def test_saving_twice_replaces_rather_than_duplicates(tmp_path):
    from pitcrew.store.db import Store

    store = Store(tmp_path / "t.db")
    try:
        store.save_race_knowledge(Knowledge(circuit_key="x", tow_s_per_lap=0.3))
        store.save_race_knowledge(Knowledge(circuit_key="x", tow_s_per_lap=0.5))
        assert store.get_race_knowledge("x").tow_s_per_lap == 0.5
    finally:
        store.close()


def test_the_json_columns_round_trip(tmp_path):
    from pitcrew.store.db import Store

    store = Store(tmp_path / "t.db")
    try:
        store.save_race_knowledge(Knowledge(
            circuit_key="x",
            rivals=({"rival": "TommyTbone", "tendency": "stops early"},),
            calls_off=({"kind": "fuel-long", "why": "he never lifts here"},),
            wear_rates={"RS": {"perLap": 0.041, "samples": 6}}))
        back = store.get_race_knowledge("x")

        assert back.rivals[0]["rival"] == "TommyTbone"
        assert back.silences("fuel-long") == "he never lifts here"
        assert back.wear_per_lap("RS") == (0.041, 6)
    finally:
        store.close()


def _a_fuel_short_call():
    from pitcrew.race.calls import Call

    return Call("fuel-short", 8, "Short-shift.", "1.2 laps short.")
