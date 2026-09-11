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
from pitcrew.strategy.handover import LAP_CEILING, as_whole_number

# The keys `stamp` owns. Named so a caller can ask whether a plan has been
# through here without knowing what is inside them.
CONTRACT_KEYS = ("expects", "context")

# The keys the race actually reads out of `expects`. `None` is a legitimate
# value for each - it means nobody measured it - but the KEY has to be there,
# because a missing key and a null one are indistinguishable to `.get` and
# only one of them is an author's mistake.
REQUIRED_EXPECTS = ("expected_lap_time_ms", "expected_fuel_per_lap_l")
# And what a context has to name for `arm` to compare it against the event.
REQUIRED_CONTEXT = ("car", "track", "race_laps")


def _is_execution_contract(expects) -> bool:
    return (isinstance(expects, dict)
            and all(key in expects for key in REQUIRED_EXPECTS))


def _is_context(context) -> bool:
    return (isinstance(context, dict)
            and all(key in context for key in REQUIRED_CONTEXT))


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


def _with_start_laps(stints) -> list:
    """Every stint carrying the lap it begins on, derived where it is absent.

    **`or 1` on a missing `start_lap` is a plausible default standing in for
    "the author did not say", and it produces the worst call this app can
    make.** `_apply_stint` reads `start = stint.get("start_lap") or 1`, so a
    handover written in the shape the CLI documents - stints, compounds, fuel,
    no start laps - puts every stint's end at `1 + laps - 1`. Driven through
    the real coordinator on a Spa plan: the box call fires on the lap after
    the stop and then **every lap to the flag**, "2 laps overdue", "3 laps
    overdue", twelve in a row. That is the nine-box-calls defect, worse, on
    the path this whole feature exists for - and `_reconsider_ignored_box`
    cannot rescue it, because `stay_out_call` returns None exactly when the
    fuel cannot reach, which is that state.

    Derived rather than refused because it is not a judgement: stints run
    back to back and the arithmetic has one answer. An author's own value is
    kept - a plan may legitimately start at a lap other than one - and only
    the gaps are filled.

    **Only where the arithmetic HAS one answer.** This used to drop a stint
    that was not a dict and derive the rest over the survivors, and rewrite a
    start of `0` to the running lap, and call `int()` on whatever `laps`
    held. So a garbage stint vanished from the plan with the laps after it
    re-numbered as if it had never been there, a start the gate should refuse
    was quietly replaced, and `"ten"` raised `int()`'s own message out of the
    MCP door. `whole_numbers` states the rule for this layer - what cannot be
    read is passed through for `certify` to refuse by name - and this is now
    the same rule: every stint stays where it was, as it was, and derivation
    stops at the first stint whose start or length cannot be read, because
    past it the running lap is not known.
    """
    if not isinstance(stints, list):
        return stints
    filled, next_start = [], 1
    for stint in stints:
        if not isinstance(stint, dict):
            filled.append(stint)
            next_start = None
            continue
        row = dict(stint)
        if row.get("start_lap") is None:
            if next_start is not None:
                row["start_lap"] = next_start
            start = next_start
        else:
            start = as_whole_number(row["start_lap"], LAP_CEILING, minimum=1)
        laps = as_whole_number(row.get("laps"), LAP_CEILING, minimum=1)
        next_start = (start + laps
                      if start is not None and laps is not None else None)
        filled.append(row)
    return filled


def contract_gaps(plan) -> list[str]:
    """What a stored plan lacks for the race to execute it, in words.

    Empty for a plan that has been through `stamp`. **Every gap is named, not
    the first** (rule 12): a plan with no context arms at any circuit and a
    plan with no expects arms and then compares nothing, and those are two
    different things to have been told.
    """
    if not isinstance(plan, dict):
        return ["a plan the app can read"]
    gaps = []
    if not _is_context(plan.get("context")):
        gaps.append("what it was built for, so it would arm at any circuit")
    if not _is_execution_contract(plan.get("expects")):
        gaps.append("what it expects to execute, so no lap would be compared "
                    "against it")
    stints = plan.get("stints")
    if isinstance(stints, list) and any(
            isinstance(s, dict) and s.get("start_lap") is None
            for s in stints):
        gaps.append("the lap each stint starts on, so its box laps are not "
                    "known")
    return gaps


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
    stamped["stints"] = _with_start_laps(stamped.get("stints"))
    if event is None:
        event = store.get_event(event_id)
    if event is None:
        raise ValueError(f"no event with id {event_id}")

    supplied_context = stamped.get("context")
    if supplied_context is not None and not _is_context(supplied_context):
        raise ValueError(
            "the plan's `context` does not name "
            f"{', '.join(REQUIRED_CONTEXT)} - `arm` compares it against the "
            f"event and would refuse a good plan or accept a wrong one")
    if not stamped.get("context"):
        context = context_from_event(event)
        stamped["context"] = {
            "car": context.car, "track": context.track,
            "layout": context.layout, "race_laps": context.race_laps,
            "race_minutes": context.race_minutes,
        }

    # **An author's `expects` has to be the right shape, or it is not one.**
    # It is left alone when present - it is what THAT plan was costed against
    # - which means a typo in a handover file passed straight through: keys
    # nothing reads, `expected_fuel_per_lap_l` absent, and the race arms and
    # runs blind on every per-lap comparison. That is the exact failure this
    # module's docstring says it exists to prevent, reachable by a typo.
    supplied = stamped.get("expects")
    if supplied is not None and not _is_execution_contract(supplied):
        raise ValueError(
            "the plan's `expects` does not carry "
            f"{', '.join(REQUIRED_EXPECTS)} - a plan whose expectations "
            f"cannot be read arms and then reports nothing, which from the "
            f"driver's seat is a race going to plan")
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
