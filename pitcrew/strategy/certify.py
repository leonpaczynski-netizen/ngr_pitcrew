"""Whether a plan somebody else wrote can actually be driven.

The strategy engine used to be the author. It is becoming the **gate**: the
plan comes from the race engineer the driver is talking to, and this decides
whether the car can execute it.

**The argument for the gate is on file, and it is not hypothetical.** The
12 August strategy audit found the app ranking the most impossible plan
cheapest, and proposing *"Fuel to 510 litres"* into a hundred-litre tank. A
plan written in prose will produce that class of error more often, not less,
and far more fluently - it will be internally consistent, well argued and
undriveable. Prose cannot be trusted to have done arithmetic.

So every plan is checked against the same things the engine checks its own
against, and **an uncertified plan cannot be armed.**

### Refusals and warnings are different claims

A **refusal** means the car cannot do it: more fuel than the tank holds, a
stint past the tyre's life, a race that does not reach the flag. These are
arithmetic and they are not negotiable.

A **warning** means it is driveable and something about it is worth knowing:
a compound with no measured profile, a stint with no margin, evidence from
before a physics update. `CLAUDE.md` §4.5 - nothing derived is presented as
measured - so a warning says which it is rather than quietly hardening.

**Silence is never a pass.** A check that could not run says so, because a
plan certified by a gate that skipped half its tests is worse than one nobody
checked: it carries the authority without the arithmetic.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from pitcrew.strategy.model import (
    STINT_SAFETY_FACTOR,
    RaceInputs,
    tank_limited_laps,
    tyre_limited_laps,
)


@dataclass(frozen=True)
class Certificate:
    """The verdict, with everything it could and could not check."""

    refusals: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unchecked: list[str] = field(default_factory=list)

    @property
    def certified(self) -> bool:
        return not self.refusals

    def describe(self) -> str:
        if self.refusals:
            return ("This plan cannot be driven: "
                    + "; ".join(self.refusals) + ".")
        parts = []
        if self.warnings:
            parts.append("Driveable, with: " + "; ".join(self.warnings) + ".")
        else:
            parts.append("Driveable.")
        if self.unchecked:
            parts.append("Not checked: " + "; ".join(self.unchecked) + ".")
        return " ".join(parts)


def _stints(plan: dict) -> list[dict]:
    raw = plan.get("stints")
    return [s for s in raw if isinstance(s, dict)] if isinstance(raw, list) else []


def _clock_allows(inputs: RaceInputs, stints: list[dict],
                  laps: list[int]) -> int | None:
    """How many laps this plan's timed race can run, with its stops off the
    clock. None where there is no reference lap to count with.

    **`timed_race_laps`, the optimiser's own expression** (rule 12). This was
    a second one - a flat lap, and a declared pit loss charged the dead time
    again - and it refused strategy 32 on the grid a lap short of the count
    the optimiser had built it to. Each stop is charged the next stint's own
    load at the pump's rate: what goes through the hose is that load less
    whatever the previous stint left, unknown here, so the load is the
    ceiling, and a ceiling shortens the race, which is the safe direction.
    A stint that omits its fuel is charged the fill the model would give it.
    """
    from pitcrew.strategy.model import planned_fill_l, timed_race_laps

    profiles = [inputs.profile_for(stint.get("compound")) for stint in stints]
    fills: list[float | None] = []
    for stint, count in zip(stints, laps):
        load = stint.get("fuel_l")
        if isinstance(load, (int, float)) and not isinstance(load, bool):
            fills.append(float(load))
        else:
            fills.append(planned_fill_l(count, inputs)[0])
    flag = timed_race_laps(inputs, laps, profiles, fills)
    return None if flag is None else flag[0]


def certify(plan: dict, inputs: RaceInputs) -> Certificate:
    """Check a proposed plan against the car, the tank and the clock."""
    refusals: list[str] = []
    warnings: list[str] = []
    unchecked: list[str] = []

    from pitcrew.strategy.handover import LAP_CEILING, as_whole_number, short_value

    if not isinstance(plan, dict):
        return Certificate([f"the plan is {short_value(plan)}, not a plan"])
    # **A stint that is not a stint is refused by position, not skipped.**
    # `_stints` filters them out, so every check below ran over the survivors
    # and a plan with a corrupt middle stint certified as though it had one
    # stint fewer - the stop count, the race distance and every box lap after
    # it all computed without it.
    raw = plan.get("stints")
    if isinstance(raw, list):
        unreadable = [f"stint {index} is {short_value(stint)}, not a stint"
                      for index, stint in enumerate(raw, 1)
                      if not isinstance(stint, dict)]
        if unreadable:
            return Certificate(unreadable)

    stints = _stints(plan)
    if not stints:
        return Certificate(["the plan names no stints"])

    # **The same `isinstance`-on-a-JSON-number gate.** `{"laps": 10.0}` was
    # refused as "not a whole number of laps" while `{"stops": 1.0}` on the
    # same plan certified - two opposite verdicts on the same JSON number,
    # one file over from where that was fixed. It fails safe (a refusal, not
    # an accept), and it told the driver a plan lacked whole lap counts when
    # it had them.
    laps = [as_whole_number(s.get("laps"), LAP_CEILING, minimum=0)
            for s in stints]
    if any(n is None or n <= 0 for n in laps):
        refusals.append("every stint needs a positive whole number of laps")
        return Certificate(refusals)

    # **And its start lap, which nothing checked.** `stint_ends_on_lap` is
    # `start_lap + laps - 1`, so a `start_lap` of 1.5 passed both doors and
    # this gate and George said "Box in 8.5 laps." The door reads it as a
    # count where it can; a value it could not read reaches here unchanged,
    # and this is the place that refuses.
    #
    # **Each refusal names the constraint it broke** (rule 12). One sentence,
    # "needs a whole one", used to cover three: not a whole lap, before lap
    # one, and past any race - and the author fixing a `0` was told to make
    # it whole.
    starts = [as_whole_number(s.get("start_lap"), LAP_CEILING, minimum=1)
              if s.get("start_lap") is not None else None for s in stints]
    for index, stint in enumerate(stints, 1):
        value = stint.get("start_lap")
        if value is None or starts[index - 1] is not None:
            continue
        shown = short_value(value)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            refusals.append(f"stint {index}'s start lap is {shown}, which is "
                            f"not a lap number")
        elif isinstance(value, float) and not value.is_integer():
            refusals.append(f"stint {index} starts on lap {shown}, which is "
                            f"not a whole lap")
        elif value < 1:
            refusals.append(f"stint {index} starts on lap {shown}; laps count "
                            f"from 1")
        else:
            refusals.append(f"stint {index} starts on lap {shown}, past any "
                            f"race distance")
    if refusals:
        return Certificate(refusals)

    # **And the starts have to chain.** Two stints that overlap share a box
    # lap, which is the nine-box-calls defect `_with_start_laps` exists to
    # prevent; two with a gap between them leave laps that belong to no stint,
    # so the box call and the fill are both sized off a stint that is not the
    # one being driven. Both are arithmetic and neither is negotiable.
    def no_stint(first: int, last: int) -> str:
        return (f"lap {first} belongs" if first == last else
                f"laps {first} and {last} belong" if last == first + 1
                else f"laps {first} to {last} belong")

    # **Including the laps before stint 1** (critic 2 on the storage row). A
    # first stint on lap 5 certified: the page said "box lap 10" and George
    # boxed on 14 on a load sized for 10. `adopt`'s mid-race tail is the only
    # stint list that starts later, and it never passes through here.
    if starts[0] is not None and starts[0] > 1:
        refusals.append(
            f"stint 1 starts on lap {starts[0]}, so "
            f"{no_stint(1, starts[0] - 1)} to no stint")
    for index in range(1, len(stints)):
        before, after = starts[index - 1], starts[index]
        if before is None or after is None:
            continue
        ends = before + laps[index - 1] - 1
        if after <= ends:
            refusals.append(
                f"stint {index + 1} starts on lap {after}, inside stint "
                f"{index}, which runs to lap {ends}")
        elif after > ends + 1:
            refusals.append(
                f"stint {index + 1} starts on lap {after} but stint {index} "
                f"ends on lap {ends}, so {no_stint(ends + 1, after - 1)} to "
                f"no stint")

    # **And the plan's own box laps have to be the ones its stints box on.**
    # The Race page reads `pit_laps`; George boxes on `start_lap + laps - 1`.
    # Two figures for one stop is rule 13 with the two ends a glance apart.
    # Every stored plan agrees today; this keeps the next one honest.
    pit_laps = plan.get("pit_laps")
    if isinstance(pit_laps, list) and all(s is not None for s in starts):
        implied = [start + count - 1
                   for start, count in zip(starts[:-1], laps[:-1])]
        read = [as_whole_number(lap, LAP_CEILING, minimum=1)
                for lap in pit_laps]
        if read != implied:
            def laps_said(values) -> str:
                words = [str(v) for v in values]
                if not words:
                    return "no lap"
                if len(words) == 1:
                    return f"lap {words[0]}"
                return f"laps {', '.join(words[:-1])} and {words[-1]}"

            refusals.append(
                f"the plan's pit laps say "
                f"{laps_said(short_value(lap) for lap in pit_laps)} but its "
                f"stints box on {laps_said(implied)}")

    # ------------------------------------------------------------- the tank
    capacity = inputs.fuel_capacity_l
    if capacity is None:
        unchecked.append("fuel, because the tank's capacity is not known")
    elif capacity <= 0:
        # Electric cars report a zero tank and it is a real value, not an error.
        unchecked.append("fuel, because this car reports no fuel tank")
    else:
        for index, stint in enumerate(stints, 1):
            fuel = stint.get("fuel_l")
            if fuel is None:
                unchecked.append(f"stint {index}'s fuel, which the plan omits")
                continue
            if fuel < 0:
                refusals.append(f"stint {index} asks for {fuel:g} L")
            elif fuel > capacity:
                refusals.append(
                    f"stint {index} asks for {fuel:g} L into a "
                    f"{capacity:g} L tank")

    # ------------------------------------------------------------ the tyres
    per_lap = inputs.wear_per_lap
    if per_lap is None:
        unchecked.append("stint length, because no wear rate has been measured")
    else:
        limit = tyre_limited_laps(per_lap)
        if limit:
            # **A fuel-only stop keeps the set on** (the critic on row
            # 2.6). The stint after a `tyres: false` stop runs on the tyre
            # the stint before it wore, so the limit applies to the laps
            # summed across them - 10 + 10 on one set is twenty - and a
            # plan stating "no tyres" certified straight past the cliff.
            # Read through the coordinator's own `_tri`, so "false", 0 and
            # false are one answer everywhere.
            from pitcrew.race.coordinator import _tri

            on_set, first = 0, 1
            for index, (count, stint) in enumerate(zip(laps, stints), 1):
                if index > 1 and _tri(stint.get("tyres")) is False:
                    on_set += count
                else:
                    on_set, first = count, index
                span = (f"stint {index}" if first == index else
                        f"stints {first}-{index} (no tyres at the stop)")
                if on_set > limit:
                    refusals.append(
                        f"{span} runs {on_set} laps on a tyre good for "
                        f"{limit} at {STINT_SAFETY_FACTOR:g} of its life")
                elif on_set == limit:
                    warnings.append(
                        f"{span} runs the tyre to its full modelled "
                        f"life with no margin")

    # ------------------------------------------------------------- the race
    total = sum(laps)
    if inputs.is_timed:
        # **Checked against the clock, with this plan's own stops taken off
        # it.** It used to be listed as unchecked by design, and the one plan
        # that was a lap long armed on that. The distance IS an output of the
        # plan - so it is computed from the plan: its stop count, its fills at
        # the pump's rate, the lane loss and the dead time.
        allowed = _clock_allows(inputs, stints, laps)
        if allowed is None:
            unchecked.append("the lap count against the clock, because no "
                             "reference lap time is known")
        elif total > allowed:
            refusals.append(
                f"the stints cover {total} laps but the clock allows about "
                f"{allowed} with {max(0, len(stints) - 1)} stop"
                f"{'' if len(stints) - 1 == 1 else 's'} taken off it - the "
                f"last stint would be filled for a lap that is never driven")
        elif total < allowed - 1:
            warnings.append(
                f"the stints cover {total} laps and the clock allows about "
                f"{allowed}; the last stint runs to the flag regardless, but "
                f"the fill call will size it by the clock, not the plan")
    elif inputs.race_laps:
        if total < inputs.race_laps:
            refusals.append(
                f"the stints cover {total} laps of a {inputs.race_laps}-lap "
                f"race and never reach the flag")
        elif total > inputs.race_laps:
            warnings.append(
                f"the stints cover {total} laps of a {inputs.race_laps}-lap "
                f"race, so the last one is longer than it needs to be")

    # --------------------------------------------------------- the compounds
    available = set(inputs.available_compounds or ())
    used = [s.get("compound") for s in stints]
    if not available:
        unchecked.append("the compounds, because none were declared for the event")
    else:
        for index, compound in enumerate(used, 1):
            if compound is None:
                unchecked.append(f"stint {index}'s compound, which the plan omits")
            elif compound not in available:
                refusals.append(
                    f"stint {index} runs {compound}, which is not available "
                    f"for this event ({', '.join(sorted(available))})")

    required = set(inputs.required_compounds or ())
    missing = required - {c for c in used if c}
    if missing:
        refusals.append(
            "the rules require " + ", ".join(sorted(missing))
            + " and the plan never runs it")

    # **A compound nobody has measured is a warning, not a refusal.** It can be
    # driven; what cannot be trusted is the time it was costed at.
    for index, compound in enumerate(used, 1):
        if not compound:
            continue
        profile = inputs.profile_for(compound)
        if profile is not None and not profile.is_measured:
            warnings.append(
                f"stint {index}'s {compound} has no measured profile, so its "
                f"pace and wear are assumed rather than taken")

    # ------------------------------------------------------------- the stops
    # **An integral float is a stop count.** JSON has no integer type and
    # `mcp.propose_strategy` stores arbitrary JSON, so `5.0` is what a
    # round-trip produces - and `isinstance(stops, int)` dropped it, so this
    # refusal could not fire and the Race page then said "No stop is planned"
    # over a plan whose own field said five (row 1.7, critic pass 12).
    from pitcrew.strategy.handover import as_stop_count, short_value

    stops = as_stop_count(plan.get("stops"))
    if plan.get("stops") is not None and stops is None:
        # Truncated by the same expression the standing orders use: this
        # refusal reaches a driver-facing status label, and a 400-digit
        # figure or a whole stint structure would go into it whole.
        refusals.append(
            f"the plan's stops field is {short_value(plan['stops'])}, which "
            f"is not a stop count")
    elif stops is not None and stops != len(stints) - 1:
        refusals.append(
            f"the plan says {stops} stop{'' if stops == 1 else 's'} but has "
            f"{len(stints)} stints")
    if inputs.mandatory_stops and len(stints) - 1 < inputs.mandatory_stops:
        refusals.append(
            f"the rules require {inputs.mandatory_stops} stop"
            f"{'' if inputs.mandatory_stops == 1 else 's'} and the plan makes "
            f"{len(stints) - 1}")

    # A fuel-limited check needs both the capacity and the burn; where either is
    # missing the tank check above has already said so.
    if capacity and inputs.fuel_per_lap_l:
        # The optimiser's own tank limit (`tank_limited_laps`, rule 12): a
        # certifier that measured the tank another way refused plans the
        # optimiser had built, which is how Suzuka's was refused on the grid.
        reach = tank_limited_laps(inputs)
        if reach:
            for index, count in enumerate(laps, 1):
                if count > reach:
                    refusals.append(
                        f"stint {index} runs {count} laps on a tank that "
                        f"reaches {reach}")

    return Certificate(refusals, warnings, unchecked)


def certify_for_event(store, event_id: int, plan: dict) -> Certificate:
    """Certify against the evidence this event actually has.

    A convenience for the callers that have a store and an event rather than
    a built `RaceInputs` - the MCP seam and the approval path. Where the
    evidence cannot be assembled at all the plan is **refused**, not passed:
    a gate that waves through what it could not read is worse than no gate.
    """
    from pitcrew.strategy.evidence import build_inputs

    try:
        inputs, _evidence = build_inputs(store, event_id)
    except Exception as exc:                                 # noqa: BLE001
        return Certificate(
            [f"the event's evidence could not be assembled, so nothing about "
             f"this plan could be checked ({exc})"])
    return certify(plan, inputs)
