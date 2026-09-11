"""Ludo writes a plan; it loads, certifies, approves and arms.

**This is the gap that cost the Fuji race.** Ludo wrote a one-stop plan with a
fifteen-lap opening stint. The app's optimiser would not offer one - the
evidence cap stood at six laps, because two six-lap practice runs deepest 24%
worn were all the gauge had seen and `0.85 / w` will happily extrapolate a
stint nobody has completed. The certifier would have ACCEPTED the plan: its
only tyre refusal is `0.85 / w`, which was 22 laps. But approval took an INDEX
into `recommend()`'s output, so a plan the app had not thought of could not be
chosen at all. He raced three stops.

Read back afterwards the same set was watched to 56%, the cap lifted, and the
optimiser now proposes 15 and 5 on one stop - Ludo's plan, arrived at
independently. The cap was right to guard extrapolation and wrong to bind a
plan a human had taken responsibility for, which is exactly `certify.py`'s own
split: refusals are arithmetic, warnings are claims.
"""
from __future__ import annotations

import json

from pitcrew.race.coordinator import RaceCoordinator, context_from_stored
from pitcrew.strategy.execution import context_from_event
from pitcrew.strategy.handover import (
    Handover,
    PlaybookEntry,
    accept,
    author_of,
    from_dict,
    playbook_of,
)


def a_handover(**over) -> Handover:
    # The fixture event requires RM and runs 20 laps, so the plan is Fuji's
    # shape against this event's rules: one stop, a long opening stint.
    plan = {"stints": [{"laps": 15, "compound": "RM", "fuel_l": 92.0,
                        "start_lap": 1},
                       {"laps": 5, "compound": "RM", "fuel_l": 32.0,
                        "start_lap": 16, "tyres": True}],
            "stops": 1, "pit_laps": [15], "binding_constraint": "fuel"}
    plan.update(over.pop("plan", {}))
    return Handover(plan=plan,
                    playbook=[PlaybookEntry(
                        trigger="fuel_short", action="short_shift",
                        when="more than 0.5 laps short to the flag",
                        until="the deficit clears")],
                    assumptions=["RS wear read off the HUD via OBS"],
                    **over)


def test_a_loaded_plan_carries_its_execution_contract(store, event_id):
    """Without `expects` and `context` a plan arms and then runs BLIND - both
    `planned_*` are None and every per-lap comparison reports nothing rather
    than reporting a problem, which from the seat is indistinguishable from a
    race going to plan."""
    strategy_id, problems = accept(store, event_id, a_handover())
    assert strategy_id is not None, problems

    stored = next(s for s in store.list_strategies(event_id)
                  if s["id"] == strategy_id)["plan"]
    assert stored["expects"] and stored["context"]
    assert stored["stints"], "the plan's own keys are at the top level"


def test_a_loaded_plan_arms(store, event_id):
    """**The whole point.** It stored cleanly before and was then refused on
    the grid for naming no stints, because the payload nested the plan under
    a `"plan"` key and `RaceCoordinator` reads it flat."""
    strategy_id, _ = accept(store, event_id, a_handover())
    store.approve_strategy(strategy_id)

    approved = store.get_approved_strategy(event_id)
    plan = approved["plan"]
    event = store.get_event(event_id)
    race = RaceCoordinator(plan)
    planned = context_from_stored(plan["context"], event)
    assert race.arm(planned, context_from_event(event)) is True, race.refusal
    assert [s["laps"] for s in plan["stints"]] == [15, 5]


def test_the_playbook_survives_the_round_trip(store, event_id):
    strategy_id, _ = accept(store, event_id, a_handover())
    stored = next(s for s in store.list_strategies(event_id)
                  if s["id"] == strategy_id)["plan"]

    assert author_of(stored) == "ludo"
    entries = playbook_of(stored)
    assert [e.trigger for e in entries] == ["fuel_short"]
    assert entries[0].action == "short_shift"


def test_it_is_stored_as_a_candidate_and_never_armed_on_the_way_in(store,
                                                                   event_id):
    """Approval stays the driver's. An engineer who could approve his own plan
    is not a second opinion."""
    accept(store, event_id, a_handover())
    assert store.get_approved_strategy(event_id) is None


def test_a_plan_that_collides_with_the_handover_s_own_keys_is_refused(
        store, event_id):
    """`assumptions` is the live collision: `Plan.as_export` emits a dict of
    that name and a handover's is a list of prose. Merging silently keeps one
    and a reader gets no warning."""
    bad = a_handover(plan={"playbook": ["not the plan's to carry"]})
    strategy_id, problems = accept(store, event_id, bad)

    assert strategy_id is None
    # Answered by its owner (storage row, 11 Sep): put beside the plan, not
    # "renamed" - renaming a playbook strips George's bounds without a word.
    assert any("it is the handover's - put it beside the plan" in p
               for p in problems), problems


def test_an_undriveable_plan_is_refused_in_the_certificate_s_own_words(
        store, event_id):
    """**Refusals are arithmetic.** A plan whose stints do not reach the flag
    cannot be driven whatever its author believes, and it is refused before it
    is stored rather than left to surprise him on the grid.

    Note what is NOT refused here: this fixture has no practice laps, so the
    tank's capacity is unknown and a 400-litre fill lands in `unchecked`
    instead - which is `certify`'s own doctrine working. Silence is never a
    pass, and a check that could not run says so.
    """
    short = a_handover(plan={"stints": [
        {"laps": 8, "compound": "RM", "fuel_l": 40.0, "start_lap": 1}],
        "stops": 0})
    strategy_id, problems = accept(store, event_id, short)

    assert strategy_id is None
    assert any("never reach the flag" in p for p in problems), problems


def test_the_json_ludo_writes_loads_without_a_wrapper(store, event_id):
    """Ludo writes the plan at the top with the playbook beside it. The stored
    form round-trips through the same reader, so one function reads both."""
    written = json.dumps({
        "stints": [{"laps": 20, "compound": "RM", "fuel_l": 92.0,
                    "start_lap": 1}],
        "stops": 0, "binding_constraint": "fuel",
        "playbook": [{"trigger": "incident", "action": "recost_to_flag",
                      "when": "more than 8 seconds lost"}],
        "assumptions": ["read off the HUD"]})

    handover = from_dict(json.loads(written))

    assert [s["laps"] for s in handover.plan["stints"]] == [20]
    assert [e.trigger for e in handover.playbook] == ["incident"]
    assert "playbook" not in handover.plan, "the handover's half is not the plan"
