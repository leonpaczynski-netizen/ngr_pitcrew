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
    fuel_limited_laps,
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


def certify(plan: dict, inputs: RaceInputs) -> Certificate:
    """Check a proposed plan against the car, the tank and the clock."""
    refusals: list[str] = []
    warnings: list[str] = []
    unchecked: list[str] = []

    stints = _stints(plan)
    if not stints:
        return Certificate(["the plan names no stints"])

    laps = [s.get("laps") for s in stints]
    if any(not isinstance(n, int) or n <= 0 for n in laps):
        refusals.append("every stint needs a positive whole number of laps")
        return Certificate(refusals)

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
            for index, count in enumerate(laps, 1):
                if count > limit:
                    refusals.append(
                        f"stint {index} runs {count} laps on a tyre good for "
                        f"{limit} at {STINT_SAFETY_FACTOR:g} of its life")
                elif count == limit:
                    warnings.append(
                        f"stint {index} runs the tyre to its full modelled "
                        f"life with no margin")

    # ------------------------------------------------------------- the race
    total = sum(laps)
    if inputs.is_timed:
        unchecked.append("the lap count, because a timed race's distance is an "
                         "output of the plan rather than a target")
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
    stops = plan.get("stops")
    if isinstance(stops, int) and stops != len(stints) - 1:
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
        reach = fuel_limited_laps(capacity, inputs.fuel_per_lap_l)
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
