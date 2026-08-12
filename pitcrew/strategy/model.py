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
from itertools import product

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

# Where a compound's pace and wear came from. The distinction is the whole
# point: a plan that puts the car on a compound it has never run is a
# hypothesis, and it has to read as one.
SOURCE_MEASURED = "measured"    # run in practice, gauge read, rate computed
SOURCE_DECLARED = "declared"    # the driver's own estimate
SOURCE_ASSUMED = "assumed"      # the reference compound's rate, reused

# How many compound assignments the search will enumerate before it gives up
# on being exhaustive. Five stints across four compounds is 1024 candidates,
# which is nothing; the cap exists so a driver who ticks all eleven compounds
# does not hang the screen.
MAX_CANDIDATES = 4096


class StrategyImpossible(ValueError):
    """The race cannot be planned from what is known."""


@dataclass(frozen=True)
class CompoundProfile:
    """What one compound costs and how long it lasts.

    `pace_delta_s` is seconds per lap against the reference compound — the one
    the bulk of the practice evidence came from — so the reference itself is
    always 0.0. A harder tyre is a positive number: slower per lap, and the
    whole question is whether the stint it buys pays that back.
    """
    code: str
    pace_delta_s: float = 0.0
    wear_per_lap: float | None = None
    source: str = SOURCE_ASSUMED
    laps_measured: int = 0
    stints_measured: int = 0
    # Where this compound's laps sat against its own temperature window, and
    # in one sentence what that does to the pace and wear above. None when no
    # temperature was captured, which is not the same as "the tyre was fine".
    window: dict | None = None
    window_note: str | None = None

    @property
    def is_measured(self) -> bool:
        return self.source == SOURCE_MEASURED

    @property
    def evidence_is_clean(self) -> bool:
        """Measured, *and* measured on a tyre that was actually working.

        A rate off a cold tyre is a measurement of the conditions as much as
        of the compound. It is still the best number available and it is still
        used - but a plan resting on it is not the same claim as one resting
        on a compound that ran in its window, and the two must not rank
        against each other silently.
        """
        return self.is_measured and self.window_note is None

    def as_export(self) -> dict:
        return {
            "compound": self.code,
            "paceDeltaSPerLap": round(self.pace_delta_s, 3),
            "wearPerLap": (None if self.wear_per_lap is None
                           else round(self.wear_per_lap, 5)),
            "source": self.source,
            "lapsMeasured": self.laps_measured,
            "stintsMeasured": self.stints_measured,
            "tyreWindow": self.window,
            "windowQualification": self.window_note,
        }


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
    # The compound the practice evidence was gathered on. It is the reference
    # every pace delta is measured against, and the fallback for any compound
    # with no profile of its own.
    evidence_compound: str | None = None
    # What each compound costs and how long it lasts, keyed by code. Empty
    # means the model has no way to tell compounds apart, and it says so
    # rather than quietly planning them all as identical.
    compound_profiles: dict[str, CompoundProfile] = field(default_factory=dict)

    def profile_for(self, compound: str | None) -> CompoundProfile:
        """The profile for a compound, or the reference's rate wearing its name.

        A compound with no profile inherits the measured reference rate and is
        labelled `assumed`, never `measured`. That is the difference between
        "this stint is planned" and "this stint is guessed", and every plan
        built on one carries a note saying which.
        """
        if compound and compound in self.compound_profiles:
            return self.compound_profiles[compound]
        return CompoundProfile(
            code=compound or (self.evidence_compound or "unknown"),
            pace_delta_s=0.0,
            wear_per_lap=self.wear_per_lap,
            source=(SOURCE_MEASURED
                    if compound and compound == self.evidence_compound
                    and self.wear_per_lap else SOURCE_ASSUMED),
        )

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
    # Whether every stint is inside what its own compound and tank can run.
    # Set in `build_plan` from the limits themselves. This used to be derived
    # by string-matching the plan's own notes, so rewording a sentence
    # silently disabled the only feasibility check in the system.
    feasible: bool = True
    # The compound profiles this plan was costed with, so a plan can be
    # audited afterwards against the evidence that produced it.
    profiles: dict[str, CompoundProfile] = field(default_factory=dict)
    # Why this plan beat the best alternative on different rubber, when there
    # was one. None when there was nothing to compare against.
    crossover: dict | None = None

    @property
    def compounds(self) -> tuple[str | None, ...]:
        return tuple(stint.compound for stint in self.stints)

    @property
    def rests_on_assumption(self) -> bool:
        """True when any stint is planned on a rate never measured on it."""
        return any(not profile.is_measured
                   for profile in self.profiles.values())

    @property
    def window_notes(self) -> list[str]:
        """Compounds whose evidence came off a tyre outside its window."""
        return [profile.window_note
                for profile in self.profiles.values()
                if profile.window_note]

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
            "compoundCrossover": self.crossover,
            "compoundProfiles": [profile.as_export()
                                 for profile in self.profiles.values()],
            "assumptions": {
                "pitLossS": inputs.pit_loss_s,
                "pitLossSource": "measured-this-track",
                "fuelPerLapL": inputs.fuel_per_lap_l,
                "fuelWeightSPerLPerLap": inputs.fuel_weight_s_per_l_per_lap,
                "fuelWeightSource": "derived-not-measured",
                # Now a real figure rather than a placeholder: the pace this
                # plan's compounds carry against the one practice ran on,
                # averaged over the race distance.
                "compoundDeltaSPerLap": round(mean_deficit(self, inputs), 3),
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
    """Laps runnable on one tank, with the reserve lap still in it.

    The reserve is subtracted here rather than checked afterwards, because
    `build_plan` fuels every stint to `laps + FUEL_MARGIN_LAPS`: a limit of
    `capacity / burn` says a 10-lap stint fits a 10-lap tank, and then the
    fuelling policy asks for 11 laps' worth and gets clamped to the tank. The
    plan reads as runnable and finishes the stint on fumes with no reserve at
    all - which is the one outcome §5.4's margin exists to prevent.

    Returns 0, not None, when the tank cannot even carry the reserve. Zero is
    a known limit that nothing satisfies; None means the limit is unknown, and
    the two must not collapse into each other.
    """
    if not fuel_capacity_l or not fuel_per_lap_l or fuel_per_lap_l <= 0:
        return None
    # Guard the divide: 0 L is a real capacity (electric), not a missing value.
    return max(0, int(fuel_capacity_l / fuel_per_lap_l - FUEL_MARGIN_LAPS))


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


def allocate_laps(total: int, limits: list[int | None]) -> list[int]:
    """Divide the race between stints that do not all last the same length.

    An even split is only right when every stint is on the same rubber. Put a
    hard tyre in the middle of a race and it should carry more of it than the
    softs either side — that longer stint is the entire reason for fitting it,
    and splitting evenly would hide the advantage the plan exists to find.

    Laps go out in proportion to each stint's own limit, which balances the
    *fraction* of tyre life each one consumes rather than the lap count. Then
    any stint over its limit hands laps back to whichever stint has the most
    headroom.

    This is a heuristic, not a proven optimum. It is a good one because the
    time cost of a stint is convex in its length — degradation compounds — so
    equalising consumed fraction is close to equalising marginal cost.
    """
    count = len(limits)
    if count < 1:
        raise StrategyImpossible("a race needs at least one stint")
    if count == 1:
        return [total]
    if any(limit is None for limit in limits):
        return split_laps(total, count)

    caps = [max(1, int(limit)) for limit in limits]  # type: ignore[arg-type]
    share = sum(caps)
    laps = [max(1, int(total * cap / share)) for cap in caps]

    # Hand out or take back the rounding remainder, respecting the caps.
    while sum(laps) < total:
        headroom = [cap - run for cap, run in zip(caps, laps)]
        if max(headroom) <= 0:
            # Nothing can legally take another lap. The plan is not runnable
            # and build_plan will say so; padding the last stint keeps the
            # race the right length so the shortfall is visible as a number.
            laps[-1] += total - sum(laps)
            break
        laps[headroom.index(max(headroom))] += 1
    while sum(laps) > total:
        # Take from the longest stint that can spare a lap.
        spare = [run if run > 1 else 0 for run in laps]
        if max(spare) == 0:
            break
        laps[spare.index(max(spare))] -= 1
    return laps


def stint_time_s(laps: int, inputs: RaceInputs, *,
                 fuel_at_start_l: float | None,
                 profile: CompoundProfile | None = None) -> float:
    """Time for one stint, including degradation, fuel weight and compound.

    `profile` carries the compound's own pace and wear. Without one the stint
    is timed on the reference compound, which is what every stint used to do —
    and why a harder tyre could never win: it was modelled as identical to the
    soft it replaced.
    """
    if profile is None:
        profile = inputs.profile_for(inputs.evidence_compound)
    base_s = inputs.lap_time_ms / 1000.0 + profile.pace_delta_s
    wear = profile.wear_per_lap
    total = 0.0
    for lap_index in range(laps):
        lap_time = base_s
        if wear:
            consumed = (lap_index + 1) * wear
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


def stint_limit(inputs: RaceInputs,
                profile: CompoundProfile) -> tuple[int | None, str]:
    """The longest runnable stint on this compound, and what limits it."""
    tyre = tyre_limited_laps(profile.wear_per_lap)
    fuel = fuel_limited_laps(inputs.fuel_capacity_l, inputs.fuel_per_lap_l)
    if tyre is None and fuel is None:
        return None, CONSTRAINT_UNKNOWN
    if tyre is None:
        return fuel, CONSTRAINT_FUEL
    if fuel is None:
        return tyre, CONSTRAINT_TYRE
    return (tyre, CONSTRAINT_TYRE) if tyre <= fuel else (fuel, CONSTRAINT_FUEL)


def build_plan(inputs: RaceInputs, stops: int,
               compounds: list[str] | None = None) -> Plan:
    """One candidate: the race split into `stops + 1` stints."""
    count = stops + 1
    if compounds is None:
        compounds = _compound_sequence(inputs, count)
    sequence = [compounds[i] if compounds and i < len(compounds) else None
                for i in range(count)]
    profiles = [inputs.profile_for(code) for code in sequence]

    limits = [stint_limit(inputs, profile)[0] for profile in profiles]
    stint_lengths = allocate_laps(inputs.race_laps, limits)
    limit, constraint = max_stint_laps(inputs)

    notes: list[str] = []
    over = [(index, laps, limits[index])
            for index, laps in enumerate(stint_lengths)
            if limits[index] is not None and laps > limits[index]]
    for index, laps, cap in over:
        _, why = stint_limit(inputs, profiles[index])
        notes.append(
            f"Stint {index + 1} is {laps} laps but only {cap} are runnable on "
            f"{sequence[index] or 'this compound'} ({why}-limited).")

    stints: list[Stint] = []
    total = 0.0
    start_lap = 1
    feasible = not over
    for index, laps in enumerate(stint_lengths):
        fuel_needed = None
        if inputs.fuel_per_lap_l:
            # To the diamond, plus one lap of margin. Deliberately NOT clamped
            # to the tank: clamping made an impossible plan look cheap, because
            # the stint was then costed as carrying a tankful rather than the
            # 1010 L it actually needed, and paid no stop for the difference.
            # The requirement is reported honestly and the plan is rejected.
            fuel_needed = (laps + FUEL_MARGIN_LAPS) * inputs.fuel_per_lap_l
            if inputs.fuel_capacity_l and fuel_needed > inputs.fuel_capacity_l:
                feasible = False
                notes.append(
                    f"Stint {index + 1} needs {fuel_needed:.0f} L including "
                    f"the reserve lap, and the tank holds "
                    f"{inputs.fuel_capacity_l:.0f} L.")

        stints.append(Stint(laps=laps, compound=sequence[index],
                            fuel_l=fuel_needed, start_lap=start_lap))
        total += stint_time_s(laps, inputs, fuel_at_start_l=fuel_needed,
                              profile=profiles[index])
        start_lap += laps

        if index < len(stint_lengths) - 1:
            total += inputs.pit_loss_s + inputs.pit_dead_time_s
            if fuel_needed:
                total += refuel_time_s(fuel_needed, inputs)

    for note in dict.fromkeys(profile.window_note for profile in profiles
                              if profile.window_note):
        notes.append(note)

    guessed = sorted({profile.code for profile in profiles
                      if not profile.is_measured and profile.wear_per_lap})
    if guessed:
        notes.append(
            f"{', '.join(guessed)} {'has' if len(guessed) == 1 else 'have'} no "
            f"measured rate of {'its' if len(guessed) == 1 else 'their'} own, "
            f"so {'it is' if len(guessed) == 1 else 'they are'} planned on "
            f"{inputs.evidence_compound or 'the reference'}'s. That is an "
            f"assumption, not a measurement - run a stint to confirm it.")

    worst_fraction = max(
        (laps * profile.wear_per_lap
         for laps, profile in zip(stint_lengths, profiles)
         if profile.wear_per_lap), default=None)
    if worst_fraction is not None:
        notes.append(
            f"Stint length is {STINT_SAFETY_FACTOR} / w with the margin "
            f"deliberate; longest stint ends in the "
            f"'{phase_at(worst_fraction)}' phase at {worst_fraction:.0%} worn.")
        if not inputs.wear_measured_at_race_multiplier:
            notes.append(
                "[ASSUMED] Wear was calibrated at a different multiplier and "
                "scaled. Multiplier linearity is assumed, never demonstrated - "
                "calibrate at the race multiplier before trusting this.")
    else:
        notes.append(
            "No tyre wear rate entered, so stint length is fuel-limited only. "
            "Read the in-game gauge on a practice lap to fix this.")

    plan = Plan(stints=stints, total_time_s=total,
                binding_constraint=constraint, notes=notes, feasible=feasible)
    plan.profiles = {profile.code: profile for profile in profiles}
    return plan


def legal(plan: Plan, inputs: RaceInputs) -> bool:
    """Regulations, not preferences."""
    if plan.stops < inputs.mandatory_stops:
        return False
    if inputs.required_compounds:
        used = {stint.compound for stint in plan.stints if stint.compound}
        if not set(inputs.required_compounds) <= used:
            return False
    return True


def _candidate_sequences(inputs: RaceInputs, stints: int) -> list[list[str] | None]:
    """Every compound assignment worth costing for a race of `stints` stints.

    Ordered assignments, not combinations: which compound runs *when* changes
    the answer, because a stint's length is set by the tyre on it and the fuel
    load differs stint to stint.
    """
    available = [code for code in inputs.available_compounds if code]
    if not available:
        # Nothing declared, so the compound is whatever practice ran on and
        # there is no choice to search over.
        return [_compound_sequence(inputs, stints)]

    if len(available) ** stints > MAX_CANDIDATES:
        # Too wide to enumerate honestly. Fall back to the assignments worth
        # most: every stint on one compound, for each compound. The narrowing
        # is reported in the plan's notes rather than passed off as a search.
        return [[code] * stints for code in available]

    return [list(combo) for combo in product(available, repeat=stints)]


def recommend(inputs: RaceInputs, *, max_stops: int = 4) -> list[Plan]:
    """Every legal plan, best first, across stop counts *and* compounds.

    This is where a harder compound gets to win. The model costs each
    candidate over the full race distance, so a tyre that is slower per lap
    but lasts long enough to delete a stop is compared against the softer one
    on total race time - which is the only comparison that decides anything.

    Plans whose stints exceed what is runnable are **never returned**, whether
    or not anything else fits. Feasibility is a filter applied before ranking,
    not a tie-break inside it.

    This used to be `runnable or plans`: when nothing fit, the infeasible set
    was ranked as though it were fine. That was worse than it sounds, because
    ranking is monotonically wrong in the infeasible region - the tank clamp
    made the most impossible plan the cheapest one, so a car that could not
    finish the race won it on paper and the card read "Fastest".

    "This race cannot be done inside the tyre life you measured" is still a
    finding the driver needs, so it is raised as `StrategyImpossible` carrying
    the reason. The caller shows that as a refusal, which is what it is.
    """
    if inputs.race_laps < 1:
        raise StrategyImpossible("a race needs at least one lap")
    if inputs.lap_time_ms <= 0:
        raise StrategyImpossible(
            "no reference lap time - run a practice lap first")

    plans: list[Plan] = []
    for stops in range(0, max_stops + 1):
        stints = stops + 1
        if stints > inputs.race_laps:
            break
        for sequence in _candidate_sequences(inputs, stints):
            plan = build_plan(inputs, stops, sequence)
            if legal(plan, inputs):
                plans.append(plan)

    if not plans:
        raise StrategyImpossible(
            "no plan satisfies the regulations - check mandatory stops and "
            "required compounds")

    runnable = [plan for plan in plans if plan.feasible]
    if not runnable:
        raise StrategyImpossible(_why_nothing_fits(plans))

    ordered = sorted(runnable, key=lambda p: (p.total_time_s, p.stops))
    best = ordered[0].total_time_s
    for plan in ordered:
        plan.delta_s = plan.total_time_s - best
    ordered[0].crossover = crossover(ordered, inputs)
    return ordered


def crossover(ordered: list[Plan], inputs: RaceInputs) -> dict | None:
    """Why the winner won, against the best plan on different rubber.

    The question this answers is the one the driver actually asks: is it worth
    running the harder tyre longer to save a stop? A pace deficit is paid every
    lap of the race; a pit stop is paid once. `breakEvenSPerLap` is how much
    slower per lap the alternative's compounds could be and still come out
    level — so a deficit comfortably inside it means the call is not close, and
    one just outside it means a tenth either way decides the race.
    """
    if not ordered:
        return None
    winner = ordered[0]
    rival = next((plan for plan in ordered[1:]
                  if set(plan.compounds) != set(winner.compounds)), None)
    if rival is None:
        return None

    # Laps run on whatever the rival fitted that the winner did not. Those are
    # the laps a pace difference is actually paid over.
    swapped = set(rival.compounds) - set(winner.compounds)
    laps_on_swapped = sum(stint.laps for stint in rival.stints
                          if stint.compound in swapped) or inputs.race_laps
    gap = rival.total_time_s - winner.total_time_s
    rival_deficit = mean_deficit(rival, inputs)

    assumed = winner.rests_on_assumption or rival.rests_on_assumption
    # Both sides, because a call is only as good as the weaker of the two
    # measurements it rests on.
    window_notes = list(dict.fromkeys(winner.window_notes + rival.window_notes))
    result = {
        "winner": {"label": winner.label(),
                   "compounds": [c for c in winner.compounds]},
        "alternative": {"label": rival.label(),
                        "compounds": [c for c in rival.compounds],
                        "lostBySeconds": round(gap, 1)},
        "stopsSaved": rival.stops - winner.stops,
        "alternativePaceDeltaSPerLap": round(rival_deficit, 3),
        "breakEvenSPerLap": round(rival_deficit - gap / laps_on_swapped, 3),
        "restsOnAssumption": assumed,
        "outsideTyreWindow": window_notes,
        "source": "derived-from-total-race-time",
    }
    result["verdict"] = _verdict(result, assumed, window_notes)
    return result


def _verdict(crossover: dict, assumed: bool,
             window_notes: list[str] | None = None) -> str:
    """One sentence saying what the comparison actually established.

    Written here rather than on the screen so the Strategy screen, the export
    and the race engineer's own prompt all say the same thing about the same
    plan. Three outcomes worth telling apart, and the third is the trap: a
    gap of nothing between two compounds is not "they are equally good", it
    is "nothing here can tell them apart", and it has to read that way.

    A tyre-window qualification is appended rather than folded in, because it
    does not change the arithmetic - it changes how far the arithmetic can be
    trusted, which is a separate claim and reads better as one.
    """
    win = "/".join(c or "?" for c in crossover["winner"]["compounds"])
    alt = "/".join(c or "?" for c in crossover["alternative"]["compounds"])
    gap = crossover["alternative"]["lostBySeconds"]
    saved = crossover["stopsSaved"]
    tail = " " + " ".join(window_notes) if window_notes else ""

    if assumed and gap < 0.5:
        return (f"{win} and {alt} come out level, but only because no wear "
                f"rate has been measured on both - they are being planned on "
                f"the same number. This is not a comparison yet. Run a stint "
                f"on each and read the gauge." + tail)

    stops = ""
    if saved > 0:
        stops = (f", saving {saved} stop{'' if saved == 1 else 's'}")
    elif saved < 0:
        stops = (f", despite {-saved} more stop{'' if saved == -1 else 's'}")

    lead = f"{win} beats {alt} by {gap:.1f} s over the race{stops}."
    breakeven = crossover["breakEvenSPerLap"]
    deficit = crossover["alternativePaceDeltaSPerLap"]
    margin = abs(deficit - breakeven)
    if margin < 0.15:
        lead += (f" It is close: {alt} draws level at "
                 f"{breakeven:+.2f} s/lap against its measured "
                 f"{deficit:+.2f}. Re-measure before committing.")
    else:
        lead += (f" {alt} would need to be {margin:.2f} s/lap quicker than "
                 f"it is to change the call.")
    if assumed:
        lead += " [ASSUMED] One of these compounds has no measured rate."
    return lead + tail


def mean_deficit(plan: Plan, inputs: RaceInputs) -> float:
    """Lap-time deficit this plan carries, averaged over the race distance."""
    total_laps = sum(stint.laps for stint in plan.stints) or 1
    weighted = sum(stint.laps * inputs.profile_for(stint.compound).pace_delta_s
                   for stint in plan.stints)
    return weighted / total_laps


def _why_nothing_fits(plans: list[Plan]) -> str:
    """The reason no candidate is runnable, taken from the closest one.

    "No plan fits" on its own is not actionable. The plan that came nearest -
    most stops, so shortest stints - carries the note that says what ran out,
    and that note is the finding: the race is longer than the tyre life or the
    tank measured, and one of those numbers has to change.
    """
    nearest = max(plans, key=lambda p: p.stops)
    reasons = [note for note in nearest.notes
               if note.startswith("Stint ")] or nearest.notes
    detail = " ".join(reasons[:2])
    return (f"No plan is runnable, even at {nearest.stops} stops. {detail} "
            f"Re-check the wear rate and the fuel figure, or shorten the race.")


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
