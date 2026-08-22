"""How to attack a qualifying session — how much fuel, and how many runs.

The app could coach a flying lap (`race/qualifying.py`) and could plan a race
(`strategy/model.py`), and had nothing at all between them. The driver asked
the question this exists to answer: *"is it one and done, or a timed qualifying
with fuel burn to lighten the car?"*

### The fuel answer is the one worth having, and it is arithmetic

**A full tank is about 73 kg of dead weight.** A qualifying run needs the laps
it is actually going to drive and not one litre more, and the difference is
large: at Monza's measured burn a two-run session wants something like a fifth
of a tank. Everything here is built from the burn this car has actually shown -
there is no model, and where the burn has not been measured the plan refuses
rather than assuming one.

**The lap-time value of shedding that weight is DERIVED and says so.**
`strategy/model.FUEL_WEIGHT_S_PER_L_PER_LAP` is a working figure of
0.003 s/L/lap on a ~90 s circuit; CLAUDE.md §5.3 says to flag it and let the
driver overwrite it, and [the lap-time work] found the coefficient
unmeasurable on his data without something like 1,875 laps. So the litres are a
measurement and the seconds beside them are an estimate, and they are never
printed as the same kind of number.

### What it will not decide

**Whether to run once or twice is only arithmetic when the session length is
known**, so the session length is an input and there is no default. Given one,
the plan says how many flying laps fit and what each costs in fuel. Given none,
it plans a single run and says that is what it did.

**It does not model track evolution.** A second run is usually quicker because
the circuit rubbers in, and nothing in the feed measures that - so the plan
reports what fits and leaves the choice where CLAUDE.md §4.1 puts it.

**It does not decide tyres.** GT7 qualifying is one lap on the softest thing
available, and a plan that solemnly derived that would be pretending.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from pitcrew.strategy.model import FUEL_WEIGHT_S_PER_L_PER_LAP

# Litres carried beyond what the runs need. **Deliberately small and stated.**
# A race margin is sized on the cost of running dry with a flag to reach; a
# qualifying margin is sized on the cost of stopping on the circuit during a
# lap that was going to be deleted anyway, which is much lower. One lap of
# burn, no more.
MARGIN_LAPS = 1.0

# A tank this size is what GT7 gives almost every car; karts get 5 L and
# electric cars 0. **A capacity of 0 is a real value, not an error** - the
# guard is the divide, not the reading.
DEFAULT_CAPACITY_L = 100.0
# Kilograms of fuel per litre, for saying the weight out loud. A full 100 L
# tank is ~73 kg, which is the figure CLAUDE.md §5.3 carries.
KG_PER_L = 0.73

# Laps of warm-up assumed when nobody has measured any. **There is no such
# number**, which is why this does not exist: with no measured
# `laps_to_window` the plan says so and prices a single out lap, because a car
# has to leave the pits whatever the tyres are doing.
MIN_OUT_LAPS = 1


@dataclass(frozen=True)
class QualifyingInputs:
    """What the plan is allowed to read. Everything optional is honestly so."""

    # The fastest counted practice lap, in ms. The plan's unit of time.
    lap_time_ms: int | None = None
    # Measured burn. **Without it there is no plan** - see `build`.
    fuel_per_lap_l: float | None = None
    fuel_capacity_l: float | None = None
    # Measured laps from a cold set to both axles inside the working range,
    # from `race/temps.py`. None where no practice session started cold
    # enough to show it, and then the plan prices one out lap and says why.
    laps_to_window: int | None = None
    # Session length. None is a real state - a lobby that does not say - and
    # the plan then sizes a single run.
    session_minutes: float | None = None
    # An out lap is not driven at racing speed. Used only to fit runs into the
    # session clock, never to claim a time.
    out_lap_factor: float = 1.25
    # Overridable, because §5.3 says it must be.
    fuel_weight_s_per_l_per_lap: float = FUEL_WEIGHT_S_PER_L_PER_LAP


@dataclass(frozen=True)
class Run:
    """One trip out of the pits: warm up, set a time, come back."""

    out_laps: int
    flying_laps: int

    @property
    def laps(self) -> int:
        # The in-lap is the flyer's own return to the pits and is charged as a
        # lap of fuel, because it is one.
        return self.out_laps + self.flying_laps + 1


@dataclass(frozen=True)
class QualifyingPlan:
    runs: list[Run] = field(default_factory=list)
    fuel_l: float | None = None
    # What that fuel weighs against a full tank, in kg. Measurement.
    weight_saved_kg: float | None = None
    # ...and what the weight is worth per lap, in seconds. ESTIMATE.
    estimated_gain_s: float | None = None
    assumptions: list[str] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        return self.fuel_l is not None

    @property
    def total_laps(self) -> int:
        return sum(run.laps for run in self.runs)

    def as_text(self) -> list[str]:
        """The plan as an engineer would write it on the board."""
        if not self.usable:
            return ["No qualifying plan: " + "; ".join(self.refusals)]
        flying = sum(run.flying_laps for run in self.runs)
        lines = [
            f"{len(self.runs)} run(s), {flying} flying lap(s), "
            f"{self.total_laps} laps of fuel.",
            f"Fuel to {self.fuel_l:.0f} litres.",
        ]
        if self.weight_saved_kg:
            gain = ""
            if self.estimated_gain_s:
                gain = (f", worth an ESTIMATED {self.estimated_gain_s:.2f} s "
                        f"a lap")
            lines.append(f"That is {self.weight_saved_kg:.0f} kg less than a "
                         f"full tank{gain}.")
        return lines


def build(inputs: QualifyingInputs) -> QualifyingPlan:
    """The plan, or an honest account of why there isn't one."""
    refusals = []
    if not inputs.fuel_per_lap_l or inputs.fuel_per_lap_l <= 0:
        refusals.append("no fuel burn has been measured for this car, so the "
                        "litres would be invented")
    # **`or DEFAULT` is wrong here and CLAUDE.md §3.4 says why**: fuel capacity
    # is 100 L for almost every car, 5 L for karts and **0 L for electric
    # ones**, and 0 is a real reading. Written as `inputs.fuel_capacity_l or
    # DEFAULT_CAPACITY_L` this quietly turned an electric car into a 100 L tank
    # and told the driver he had saved 57 kg of fuel he was never carrying.
    capacity = (DEFAULT_CAPACITY_L if inputs.fuel_capacity_l is None
                else inputs.fuel_capacity_l)
    if capacity <= 0:
        refusals.append("this car carries no fuel, so there is no fuel plan - "
                        "the run shape below is all there is to decide")
    if refusals:
        return QualifyingPlan(refusals=refusals)

    assumptions = []
    out_laps = inputs.laps_to_window
    if out_laps is None or out_laps < MIN_OUT_LAPS:
        out_laps = MIN_OUT_LAPS
        assumptions.append(
            "no measured warm-up: nothing in practice started cold enough to "
            f"show how long the set takes, so this prices {MIN_OUT_LAPS} out "
            "lap because the car has to leave the pits whatever the tyres "
            "are doing")
    else:
        assumptions.append(
            f"{out_laps} out lap(s), measured - that is how long this set "
            f"took to reach its working range in practice")

    runs = _fit_runs(inputs, out_laps, assumptions)
    laps = sum(run.laps for run in runs)
    # **Never ask for more than the tank holds.** The strategy audit found this
    # app proposing "Fuel to 510 litres" into a 100 L tank.
    wanted = (laps + MARGIN_LAPS) * inputs.fuel_per_lap_l
    fuel = min(wanted, capacity)
    if wanted > capacity:
        # **And say so.** Capping quietly turns "this plan needs 7 litres" into
        # "fuel to 5 litres", which is a plan that runs out on the flyer while
        # reading as though it fits.
        assumptions.append(
            f"the runs below want {wanted:.1f} L and the tank holds "
            f"{capacity:.0f} - this is filled to the brim and is SHORT. Drop "
            f"a run or an out lap")
    assumptions.append(
        f"{MARGIN_LAPS:.0f} lap of fuel in hand beyond the runs - a "
        f"qualifying margin is sized on stopping during a lap that was going "
        f"to be deleted anyway, not on reaching a flag")

    saved = None
    gain = None
    if fuel < capacity:
        saved = (capacity - fuel) * KG_PER_L
        if inputs.fuel_weight_s_per_l_per_lap:
            gain = (capacity - fuel) * inputs.fuel_weight_s_per_l_per_lap
            assumptions.append(
                f"the seconds are DERIVED from "
                f"{inputs.fuel_weight_s_per_l_per_lap:.4f} s/L/lap, which is "
                f"a working figure and not a measurement on this car - the "
                f"litres and the kilograms are measured, the seconds are not")

    return QualifyingPlan(runs=runs, fuel_l=fuel, weight_saved_kg=saved,
                          estimated_gain_s=gain, assumptions=assumptions)


def _fit_runs(inputs: QualifyingInputs, out_laps: int,
              assumptions: list[str]) -> list[Run]:
    """How many trips out of the pits the session clock allows.

    One run when the session length is unknown - which is a real state, not a
    failure. A lobby that does not say how long qualifying is gets a plan for
    one flying lap, and the plan says that is what it did.
    """
    one = Run(out_laps=out_laps, flying_laps=1)
    if not inputs.session_minutes or not inputs.lap_time_ms:
        assumptions.append(
            "session length unknown, so this plans ONE run - tell it the "
            "minutes and it will say how many fit")
        return [one]

    lap_s = inputs.lap_time_ms / 1000.0
    # An out lap is slower than a flyer and an in lap is slower still; both are
    # charged at the same factor because neither is being timed and the only
    # thing they buy here is a place in the clock.
    run_s = lap_s * (out_laps * inputs.out_lap_factor + 1
                     + inputs.out_lap_factor)
    budget_s = inputs.session_minutes * 60.0
    fits = int(budget_s // run_s) if run_s > 0 else 0
    if fits <= 1:
        assumptions.append(
            f"one run fits in {inputs.session_minutes:.0f} minutes at this "
            f"pace - it is one and done, so the out lap is the whole "
            f"preparation")
        return [one]
    assumptions.append(
        f"{fits} runs fit in {inputs.session_minutes:.0f} minutes. Whether to "
        f"take the second is yours: the circuit rubbers in, which nothing in "
        f"the feed measures, and the set is a lap older")
    return [one for _ in range(fits)]
