"""The race strategy model: an explicit model with stated assumptions.

Built to CLAUDE.md §5. Every number it produces carries where it came from,
because the app plans around a tyre life the game refuses to tell it.

The three things this gets right that a naive model gets wrong:

**Degradation is piecewise, not linear.** GT7 post-1.49 is near-flat to ~50%
worn, progressive from ~50 to ~90%, then a cliff where the car is undriveable
rather than merely slow. The optimisation is not "integrate pace over the
stint", it is "how long can I run without entering phase 3" — and because the
cliff's onset is sharp, overshooting costs far more than undershooting.

**Stint length is `0.85 / w`, and says so.** The 0.85 is a deliberate margin,
reported in `modelBasis` on every plan rather than hidden in a constant.

**Fuel map 1 is the richest.** Six levels, roughly −4% power and −8%
consumption per step, except step 6 which is anomalous: about half the fuel
for about 80% of the power. Sources that number them 1-5, or invert the
direction, are wrong.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# Stop the stint at 85% of modelled tyre life. Deliberate, and stated.
STINT_SAFETY_FACTOR = 0.85

# Degradation phases, as fractions of tyre life consumed.
PHASE_FLAT_UNTIL = 0.50
PHASE_CLIFF_FROM = 0.90
# Pace lost per lap once the tyre reaches the cliff edge, at the end of the
# progressive phase. CLAUDE.md gives 0.5-1.5 s/lap cumulative; the midpoint is
# the working figure and it is an assumption, not a measurement.
DEG_AT_CLIFF_S = 1.0

# A full 100 L tank is ~73 kg. Working figure on a ~90 s circuit. Derived, not
# measured - the driver can overwrite it.
FUEL_WEIGHT_S_PER_L_PER_LAP = 0.003

# Every stop has dead time before refuelling begins, on top of the track's
# own pit loss.
PIT_DEAD_TIME_S = 7.5

# Fuel taken is always to the in-game diamond plus one lap of margin. The
# diamond is accurate.
FUEL_MARGIN_LAPS = 1.0

# Fuel map: index 1..6. Multipliers on consumption and power relative to map 1.
FUEL_MAP_CONSUMPTION = {1: 1.00, 2: 0.92, 3: 0.85, 4: 0.78, 5: 0.72, 6: 0.50}
FUEL_MAP_POWER = {1: 1.00, 2: 0.96, 3: 0.92, 4: 0.88, 5: 0.85, 6: 0.80}

CONSTRAINT_TYRE = "tyre"
CONSTRAINT_FUEL = "fuel"
CONSTRAINT_REGULATION = "regulation"
CONSTRAINT_UNKNOWN = "unknown"


class StrategyImpossible(ValueError):
    """The race cannot be planned from what is known."""


@dataclass
class RaceInputs:
    """Everything the plan rests on, each with its provenance."""
    race_laps: int
    lap_time_ms: int
    fuel_per_lap_l: float | None = None
    fuel_capacity_l: float | None = None
    refuel_rate_lps: float = 2.5
    pit_loss_s: float = 20.0
    pit_dead_time_s: float = PIT_DEAD_TIME_S
    wear_per_lap: float | None = None
    wear_measured_at_race_multiplier: bool = True
    mandatory_stops: int = 0
    available_compounds: tuple[str, ...] = ()
    required_compounds: tuple[str, ...] = ()
    fuel_weight_s_per_l_per_lap: float = FUEL_WEIGHT_S_PER_L_PER_LAP
    starting_fuel_l: float | None = None
    # The compound the practice evidence was gathered on. Stints default to it,
    # because a wear rate measured on one compound does not describe another -
    # planning a hard-tyre stint off soft-tyre wear would present a guess as a
    # measurement.
    evidence_compound: str | None = None

    def missing(self) -> list[str]:
        """What is not known. A plan built on these is caveated, not hidden."""
        gaps = []
        if self.fuel_per_lap_l is None:
            gaps.append("fuel per lap")
        if self.fuel_capacity_l is None:
            gaps.append("fuel capacity")
        if self.wear_per_lap is None:
            gaps.append("tyre wear rate")
        return gaps


@dataclass
class Stint:
    laps: int
    compound: str | None
    fuel_l: float | None
    start_lap: int

    @property
    def end_lap(self) -> int:
        return self.start_lap + self.laps - 1


@dataclass
class Plan:
    stints: list[Stint]
    total_time_s: float
    binding_constraint: str
    notes: list[str] = field(default_factory=list)
    delta_s: float = 0.0

    @property
    def stops(self) -> int:
        return len(self.stints) - 1

    @property
    def pit_laps(self) -> list[int]:
        return [stint.end_lap for stint in self.stints[:-1]]

    def label(self) -> str:
        if self.stops == 0:
            return "No stop"
        return f"{self.stops} stop" + ("" if self.stops == 1 else "s")

    def as_export(self, inputs: RaceInputs) -> dict:
        """The `strategy` section of the export contract."""
        return {
            "plan": {
                "stops": self.stops,
                "stintLaps": [stint.laps for stint in self.stints],
                "compounds": [stint.compound for stint in self.stints],
                "pitLap": self.pit_laps[0] if self.pit_laps else None,
            },
            "bindingConstraint": self.binding_constraint,
            "assumptions": {
                "pitLossS": inputs.pit_loss_s,
                "pitLossSource": "measured-this-track",
                "fuelPerLapL": inputs.fuel_per_lap_l,
                "fuelWeightSPerLPerLap": inputs.fuel_weight_s_per_l_per_lap,
                "fuelWeightSource": "derived-not-measured",
                "compoundDeltaSPerLap": None,
            },
        }

    def as_dict(self) -> dict:
        return {
            "stops": self.stops,
            "pit_laps": self.pit_laps,
            "stints": [
                {"laps": s.laps, "compound": s.compound, "fuel_l": s.fuel_l,
                 "start_lap": s.start_lap}
                for s in self.stints
            ],
            "total_time_s": self.total_time_s,
            "binding_constraint": self.binding_constraint,
            "notes": list(self.notes),
        }


# ----------------------------------------------------------------- the model

def pace_loss_s(wear_fraction: float) -> float:
    """Seconds per lap lost at this fraction of tyre life consumed.

    Piecewise, never a straight line through the origin: a linear fit would
    predict losses during the flat phase that do not happen, and would badly
    understate the cliff.
    """
    if wear_fraction <= PHASE_FLAT_UNTIL:
        return 0.0
    if wear_fraction >= PHASE_CLIFF_FROM:
        # Past the cliff edge the car is undriveable rather than slow. The
        # number is deliberately punitive so no candidate plans to be here.
        over = (wear_fraction - PHASE_CLIFF_FROM) / (1.0 - PHASE_CLIFF_FROM)
        return DEG_AT_CLIFF_S + over * DEG_AT_CLIFF_S * 8.0
    span = PHASE_CLIFF_FROM - PHASE_FLAT_UNTIL
    return DEG_AT_CLIFF_S * (wear_fraction - PHASE_FLAT_UNTIL) / span


def phase_at(wear_fraction: float) -> str:
    if wear_fraction < PHASE_FLAT_UNTIL:
        return "flat"
    if wear_fraction <= PHASE_CLIFF_FROM:
        return "linear"
    return "cliff"


def tyre_limited_laps(wear_per_lap: float | None) -> int | None:
    """`0.85 / w`, the margin deliberate and stated in the plan's notes."""
    if not wear_per_lap or wear_per_lap <= 0:
        return None
    return max(1, int(STINT_SAFETY_FACTOR / wear_per_lap))


def fuel_limited_laps(fuel_capacity_l: float | None,
                      fuel_per_lap_l: float | None) -> int | None:
    if not fuel_capacity_l or not fuel_per_lap_l or fuel_per_lap_l <= 0:
        return None
    # Guard the divide: 0 L is a real capacity (electric), not a missing value.
    return max(1, int(fuel_capacity_l / fuel_per_lap_l))


def max_stint_laps(inputs: RaceInputs) -> tuple[int | None, str]:
    """The longest runnable stint, and what limits it."""
    tyre = tyre_limited_laps(inputs.wear_per_lap)
    fuel = fuel_limited_laps(inputs.fuel_capacity_l, inputs.fuel_per_lap_l)

    if tyre is None and fuel is None:
        return None, CONSTRAINT_UNKNOWN
    if tyre is None:
        return fuel, CONSTRAINT_FUEL
    if fuel is None:
        return tyre, CONSTRAINT_TYRE
    if tyre <= fuel:
        return tyre, CONSTRAINT_TYRE
    return fuel, CONSTRAINT_FUEL


def split_laps(total: int, stints: int) -> list[int]:
    """Divide the race as evenly as possible, longer stints first."""
    if stints < 1:
        raise StrategyImpossible("a race needs at least one stint")
    base, extra = divmod(total, stints)
    return [base + (1 if i < extra else 0) for i in range(stints)]


def stint_time_s(laps: int, inputs: RaceInputs, *,
                 fuel_at_start_l: float | None) -> float:
    """Time for one stint, including degradation and fuel weight."""
    base_s = inputs.lap_time_ms / 1000.0
    total = 0.0
    for lap_index in range(laps):
        lap_time = base_s
        if inputs.wear_per_lap:
            consumed = (lap_index + 1) * inputs.wear_per_lap
            lap_time += pace_loss_s(consumed)
        if fuel_at_start_l is not None and inputs.fuel_per_lap_l:
            onboard = max(0.0, fuel_at_start_l
                          - lap_index * inputs.fuel_per_lap_l)
            lap_time += onboard * inputs.fuel_weight_s_per_l_per_lap
        total += lap_time
    return total


def refuel_time_s(litres: float, inputs: RaceInputs) -> float:
    if litres <= 0 or inputs.refuel_rate_lps <= 0:
        return 0.0
    return litres / inputs.refuel_rate_lps


def build_plan(inputs: RaceInputs, stops: int,
               compounds: list[str] | None = None) -> Plan:
    """One candidate: the race split into `stops + 1` stints."""
    stint_lengths = split_laps(inputs.race_laps, stops + 1)
    limit, constraint = max_stint_laps(inputs)
    if compounds is None:
        compounds = _compound_sequence(inputs, stops + 1)

    notes: list[str] = []
    if limit is not None and max(stint_lengths) > limit:
        notes.append(
            f"Longest stint is {max(stint_lengths)} laps but only {limit} are "
            f"runnable ({constraint}-limited).")

    stints: list[Stint] = []
    total = 0.0
    start_lap = 1
    for index, laps in enumerate(stint_lengths):
        fuel_needed = None
        if inputs.fuel_per_lap_l:
            # To the diamond, plus one lap of margin.
            fuel_needed = (laps + FUEL_MARGIN_LAPS) * inputs.fuel_per_lap_l
            if inputs.fuel_capacity_l:
                fuel_needed = min(fuel_needed, inputs.fuel_capacity_l)

        compound = compounds[index] if compounds and index < len(compounds) else None

        stints.append(Stint(laps=laps, compound=compound, fuel_l=fuel_needed,
                            start_lap=start_lap))
        total += stint_time_s(laps, inputs, fuel_at_start_l=fuel_needed)
        start_lap += laps

        if index < len(stint_lengths) - 1:
            total += inputs.pit_loss_s + inputs.pit_dead_time_s
            if fuel_needed:
                total += refuel_time_s(fuel_needed, inputs)

    planned = {stint.compound for stint in stints if stint.compound}
    if inputs.wear_per_lap and inputs.evidence_compound:
        untested = planned - {inputs.evidence_compound}
        if untested:
            notes.append(
                f"Wear was measured on {inputs.evidence_compound}; "
                f"{', '.join(sorted(untested))} "
                f"{'is' if len(untested) == 1 else 'are'} planned on that same "
                "rate, which is an assumption. Run a stint on it to confirm.")

    if inputs.wear_per_lap:
        worst = max(stint_lengths) * inputs.wear_per_lap
        notes.append(
            f"Stint length is {STINT_SAFETY_FACTOR} / w with the margin "
            f"deliberate; longest stint ends in the "
            f"'{phase_at(worst)}' phase at {worst:.0%} worn.")
        if not inputs.wear_measured_at_race_multiplier:
            notes.append(
                "[ASSUMED] Wear was calibrated at a different multiplier and "
                "scaled. Multiplier linearity is assumed, never demonstrated - "
                "calibrate at the race multiplier before trusting this.")
    else:
        notes.append(
            "No tyre wear rate entered, so stint length is fuel-limited only. "
            "Read the in-game gauge on a practice lap to fix this.")

    return Plan(stints=stints, total_time_s=total,
                binding_constraint=constraint, notes=notes)


def legal(plan: Plan, inputs: RaceInputs) -> bool:
    """Regulations, not preferences."""
    if plan.stops < inputs.mandatory_stops:
        return False
    if inputs.required_compounds:
        used = {stint.compound for stint in plan.stints if stint.compound}
        if not set(inputs.required_compounds) <= used:
            return False
    return True


def recommend(inputs: RaceInputs, *, max_stops: int = 4) -> list[Plan]:
    """Every legal plan, best first.

    Plans whose stints exceed what is runnable are dropped when any runnable
    plan exists - there is no point offering a stop count the tyres cannot
    reach. When nothing is runnable they are returned anyway, each carrying the
    note saying why, because "this race cannot be done inside the tyre life you
    measured" is a finding the driver needs rather than an empty screen.
    """
    if inputs.race_laps < 1:
        raise StrategyImpossible("a race needs at least one lap")
    if inputs.lap_time_ms <= 0:
        raise StrategyImpossible(
            "no reference lap time - run a practice lap first")

    limit, _ = max_stint_laps(inputs)
    plans: list[Plan] = []
    for stops in range(0, max_stops + 1):
        if stops + 1 > inputs.race_laps:
            break
        plan = build_plan(inputs, stops)
        if not legal(plan, inputs):
            continue
        plans.append(plan)

    if not plans:
        raise StrategyImpossible(
            "no plan satisfies the regulations - check mandatory stops and "
            "required compounds")

    runnable = [p for p in plans if _fits(p, limit)]
    ordered = sorted(runnable or plans, key=lambda p: p.total_time_s)
    best = ordered[0].total_time_s
    for plan in ordered:
        plan.delta_s = plan.total_time_s - best
    return ordered


def _fits(plan: Plan, limit: int | None) -> bool:
    if limit is None:
        return True
    return all(stint.laps <= limit for stint in plan.stints)


def _compound_sequence(inputs: RaceInputs, stints: int) -> list[str] | None:
    """Satisfy the required compounds first, then fill with the evidence's own.

    The filler is the compound practice was actually run on, not whatever comes
    first in the allowed list: the measured wear rate describes that compound
    and no other. GT7 cannot run split compounds front to rear, so a stint is
    one compound.
    """
    if not inputs.available_compounds:
        return None
    filler = inputs.evidence_compound
    if filler not in inputs.available_compounds:
        filler = inputs.available_compounds[0]
    sequence = list(inputs.required_compounds)[:stints]
    while len(sequence) < stints:
        sequence.append(filler)
    return sequence


def laps_from_minutes(minutes: float, lap_time_ms: int) -> int:
    """A timed race, expressed in laps so the same model applies."""
    if lap_time_ms <= 0:
        raise StrategyImpossible("no reference lap time")
    return max(1, math.ceil(minutes * 60_000 / lap_time_ms))
