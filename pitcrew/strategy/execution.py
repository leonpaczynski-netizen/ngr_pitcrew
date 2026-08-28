"""The contract a plan has to carry before anything can execute it.

A stored plan is two different documents wearing one name. Most of it is the
**plan**: stints, compounds, fuel, the stop laps, the binding constraint. Two
blocks of it are the **execution contract** - what the plan expects the car to
do (`expects`), and what it was built for (`context`) - and those are the only
parts the race actually reads once it is running.

They were built in one place, `controller.approve_strategy`, and that was fine
for exactly as long as the app's own optimiser was the only author. It is not
any more: `strategy/handover.py` exists so the race engineer at the desk can
write the plan, and a plan arriving from there had neither block. It would
store, certify, arm - and run blind, with `planned_fuel_per_lap_l` and
`planned_lap_time_ms` both `None`, which is the state in which every per-lap
comparison silently reports nothing rather than reporting a problem.

**So the contract is stamped here, by whoever accepts the plan, and there is
one implementation of it.** An author who does not go through `stamp` does not
get a plan that arms.

### Why `expects` is stamped at acceptance and never refreshed

It is a snapshot on purpose. `expects` is what THIS plan was costed against;
anything driven since changes what the app would plan now, not what this plan
is. Reading the fresh figure at race time instead is how *"burning 8% under
plan"* was once said against a burn no plan ever held.
"""
from __future__ import annotations

# `context_from_event` is the coordinator's, deliberately. It already reads
# the `events.race_laps` column overload - MINUTES when `race_type` is
# `'time'` - and a second implementation of that is a second thing to get
# wrong. There were two when this module was written; there is one now.
from pitcrew.race.coordinator import context_from_event
from pitcrew.race.expectations import PRACTICE, Expectation

# The keys `stamp` owns. Named so a caller can ask whether a plan has been
# through here without knowing what is inside them.
CONTRACT_KEYS = ("expects", "context")


def practice_lap_count(store, event_id: int) -> int:
    """How many counted practice laps stand behind the plan's two figures.

    Every aggregate carries its sample count (CLAUDE.md §4.4): a burn from
    three laps and one from fourteen are not the same claim, and the driver is
    about to be told one of them.

    `hydrate=set()` because this is a COUNT. The default decodes every practice
    lap's telemetry to produce one integer - 2.5 s on the active event and
    9.4 s on the largest, against 1.0 ms.
    """
    from pitcrew.analysis.session import counted_laps
    from pitcrew.export.build import event_lap_inputs

    return len(counted_laps(
        event_lap_inputs(store, event_id, "practice", hydrate=set())))


def expectation_for(inputs, samples: int) -> Expectation:
    """The two numbers the plan expects to execute, with their sample counts.

    The driver asked for exactly this: a median lap time and a fuel burn stored
    *with* the plan, so the engineer has something to reference lap to lap when
    deciding if and how the plan needs adjusting.
    """
    return Expectation(
        lap_time_ms=(inputs.lap_time_ms or None) if inputs else None,
        lap_time_samples=samples,
        lap_time_source=PRACTICE,
        fuel_per_lap_l=inputs.fuel_per_lap_l if inputs else None,
        fuel_samples=samples,
        fuel_source=PRACTICE,
        wear_per_lap=inputs.wear_per_lap if inputs else None)


def stamp(store, event_id: int, plan: dict, *, inputs=None,
          event=None) -> dict:
    """`plan` with its execution contract on it. A new dict; the input is left.

    `inputs` and `event` are accepted so the caller that already has them does
    not pay to rebuild them - `build_inputs` walks every practice lap - but
    neither is required, which is what lets an author outside the app use this.

    **An existing contract is not overwritten.** A plan that already carries
    `expects` was stamped when its author accepted it, and re-stamping it here
    would quietly replace the figures it was costed against with today's.
    """
    stamped = dict(plan)
    if event is None:
        event = store.get_event(event_id)
    if event is None:
        raise ValueError(f"no event with id {event_id}")

    if not stamped.get("context"):
        context = context_from_event(event)
        stamped["context"] = {
            "car": context.car, "track": context.track,
            "layout": context.layout, "race_laps": context.race_laps,
            "race_minutes": context.race_minutes,
        }

    if not stamped.get("expects"):
        if inputs is None:
            from pitcrew.strategy.evidence import build_inputs
            try:
                inputs, _evidence = build_inputs(store, event_id)
            except Exception:                                # noqa: BLE001
                # **Missing, not zero** (CLAUDE.md §4.3). A contract of zeroes
                # would have every per-lap comparison reporting a car massively
                # under plan; a contract of `None`s has them say nothing, which
                # is the truth. `certify` is what refuses the plan for it.
                inputs = None
        stamped["expects"] = expectation_for(
            inputs, practice_lap_count(store, event_id)).as_plan()

    return stamped
