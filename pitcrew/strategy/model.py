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
import statistics
from dataclasses import dataclass, field, replace
from functools import lru_cache
from itertools import product

from pitcrew.store.tyres import get_by_code

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

# **The fuel margin is a COST, and at a slow refuel rate it is the whole
# argument.** CLAUDE.md §5.4 says "to the diamond plus one lap of margin", and
# a flat lap is the right answer when nothing about the burn has been
# measured. It stopped being the right answer at Watkins on 17 Aug 2026.
#
# That race: 8 laps to run on 6.068 L/lap measured, so 48.9 L needed. The call
# said fill to 55, he filled to 55.23, and he crossed the line with 6.31 L
# still aboard. **At the measured 1.001 L/s that margin was 6.3 seconds of
# standing still** - it turned a stop that would have released him six seconds
# clear into one that released him into a fight for the place. The margin cost
# more than everything the strategy model saved all race.
#
# So the margin is sized against what it actually protects, and in a LAP race
# that is not the distance - the distance is known exactly - it is the burn
# rate. Two ways the burn can beat its estimate, and the margin covers the
# worse of them:
#
# * **Scatter**, lap to lap. Independent, so it grows as sqrt(laps): three
#   sigma of the measured per-lap sd over the stint. On that race, sd 0.171 L
#   over 8 laps = 1.45 L.
# * **A systematic lift** - traffic, a defence, a wetter line - which is
#   common-mode and grows with laps. His hardest lap of that stint burned 5.6%
#   over the mean, so a flat 2% of the stint's own fuel is the floor under it.
#
# **A TIMED race keeps the full lap** and that is not a compromise: its
# distance is an output of the plan, not an input, so an extra lap can really
# appear and running dry on it is not a rounding error.
#
# Never larger than the old figure, so this can only ever take fuel out of the
# stop, and never below `FUEL_MARGIN_MIN_L` - crossing the line on fumes is
# not a plan, it is a coin toss.
FUEL_MARGIN_LAPS = 1.0
FUEL_MARGIN_SIGMAS = 3.0
FUEL_MARGIN_SYSTEMATIC = 0.02
FUEL_MARGIN_MIN_L = 0.5


def consecutive_sd(groups) -> float | None:
    """Lap-to-lap scatter, from consecutive differences within each group.

    **The plain sd of every burn on file is the wrong number and it is wrong
    by a factor of three.** Pooled across this event's ten sessions it reads
    0.557 L, because those sessions ran at genuinely different rates - 7.3
    L/lap in the early practices against 6.2 in the race-intent ones - and a
    dispersion that swallows that is measuring the difference between sessions
    rather than the scatter within one. A margin sized on it is a margin
    bought against a fault that does not exist.

    `sd(consecutive differences) / sqrt(2)` inside each group removes any
    drift the group carries and leaves the lap-to-lap term, pooled in
    quadrature across groups. Same estimator `analysis/tyre_model` uses for
    `cv_consec`, and on the same data it reads 0.174 L - which is also what
    the race's own eighteen green laps show on their own.

    Groups of fewer than three contribute nothing: two laps give one
    difference and one difference has no spread.
    """
    sigmas: list[float] = []
    for values in groups:
        series = [float(v) for v in values if v is not None]
        if len(series) < 3:
            continue
        deltas = [b - a for a, b in zip(series, series[1:])]
        try:
            sigmas.append(statistics.stdev(deltas) / math.sqrt(2.0))
        except statistics.StatisticsError:
            continue
    if not sigmas:
        return None
    return math.sqrt(sum(s * s for s in sigmas) / len(sigmas))


def fuel_margin_l(laps: int | float | None, fuel_per_lap_l: float | None, *,
                  sd_l: float | None = None,
                  timed: bool = False,
                  lap_count_firm: bool = False) -> tuple[float | None, str]:
    """Litres to carry beyond the stint, and the reason in one clause.

    The reason travels with the number because the margin is now variable and
    a variable margin nobody can read is worse than a fixed one. It is written
    to the plan's notes and to the export, so a stop that cost time can be
    audited against what the time was bought for.
    """
    if not fuel_per_lap_l or fuel_per_lap_l <= 0:
        return None, "no burn rate measured"
    full_lap = FUEL_MARGIN_LAPS * fuel_per_lap_l
    # **A timed race carries the extra lap only while it can really happen.**
    # Its distance is an output rather than an input, so the reflex was to
    # keep a whole lap always - but the app already works out how many laps
    # the clock allows, and it already knows when that answer is resolvable:
    # `laps_estimate_firm` is true when the slack before the count changes
    # exceeds this car's own lap-time sigma. While that holds, the lap count
    # is as known as a lap race's and a lap of fuel is the same wasted pit
    # time it was at Watkins. While it does not, an extra lap is genuinely in
    # play and running dry on it is not a rounding error.
    if timed and not lap_count_firm:
        return full_lap, ("one lap - the clock could still add one and the "
                          "count is inside this car's lap-time noise")
    if not laps or laps <= 0:
        return full_lap, "one lap - no stint length to size against"
    if not sd_l or sd_l <= 0:
        return full_lap, "one lap - lap-to-lap burn scatter not measured"
    scatter = FUEL_MARGIN_SIGMAS * sd_l * math.sqrt(laps)
    systematic = FUEL_MARGIN_SYSTEMATIC * fuel_per_lap_l * laps
    margin = max(FUEL_MARGIN_MIN_L, scatter, systematic)
    if margin >= full_lap:
        return full_lap, "one lap - the measured spread asks for more"
    driver = "scatter" if scatter >= systematic else "a systematic lift"
    return margin, (f"{margin:.1f} L over {laps:g} laps, sized on {driver} "
                    f"rather than a flat lap")

# Fuel map: index 1..6. Multipliers on consumption and power relative to map 1.
FUEL_MAP_CONSUMPTION = {1: 1.00, 2: 0.92, 3: 0.85, 4: 0.78, 5: 0.72, 6: 0.50}
FUEL_MAP_POWER = {1: 1.00, 2: 0.96, 3: 0.92, 4: 0.88, 5: 0.85, 6: 0.80}

CONSTRAINT_TYRE = "tyre"
CONSTRAINT_FUEL = "fuel"
# The stint is not limited by the car but by what has been run on the compound.
# `0.85 / w` extrapolates from a rate; this refuses to extrapolate past the
# longest stint the evidence actually contains, which is what stops an
# understated rate proposing a stint nobody has ever completed.
CONSTRAINT_EVIDENCE = "evidence"
CONSTRAINT_REGULATION = "regulation"
CONSTRAINT_UNKNOWN = "unknown"

# Where a compound's pace and wear came from. The distinction is the whole
# point: a plan that puts the car on a compound it has never run is a
# hypothesis, and it has to read as one.
SOURCE_MEASURED = "measured"    # run in practice, gauge read, rate computed
SOURCE_DECLARED = "declared"    # the driver's own estimate
SOURCE_ASSUMED = "assumed"      # the reference compound's rate, reused

# Where the pit-loss figure came from. **Nothing in the app measures it yet**:
# it is a spin box on the event page with a schema default of 20 s, and the
# Strategy screen's own evidence row has always called it declared. The export
# asserted "measured-this-track" for every event regardless - two paths
# claiming different provenance for one number, and the export claiming the
# stronger one.
PIT_LOSS_MEASURED = "measured-this-track"
PIT_LOSS_DECLARED = "declared-on-the-event-page"

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
    # Seconds per lap against the reference compound, **0.0 when unknown**.
    # `pace_known` below is what separates "the same as the reference" from
    # "we cannot tell": the same number, and very different claims.
    pace_delta_s: float = 0.0
    wear_per_lap: float | None = None
    source: str = SOURCE_ASSUMED
    laps_measured: int = 0
    stints_measured: int = 0
    # The longest single stint ever run on this compound. Not the same as
    # `laps_measured`, which is every lap on it across the session: a compound
    # run three times for five laps has fifteen laps of evidence and none at
    # all about a six-lap stint.
    longest_stint_laps: int = 0
    # Where this compound's laps sat against its own temperature window, and
    # in one sentence what that does to the pace and wear above. None when no
    # temperature was captured, which is not the same as "the tyre was fine".
    window: dict | None = None
    window_note: str | None = None
    # Appended deliberately: this dataclass is built positionally in a dozen
    # places, so a field inserted in the middle silently shifts `wear_per_lap`
    # into `source` and every plan downstream is costed on nonsense.
    pace_known: bool = False
    pace_basis: str | None = None

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
            "paceDeltaSPerLap": (round(self.pace_delta_s, 3)
                                 if self.pace_known else None),
            "paceBasis": self.pace_basis,
            "wearPerLap": (None if self.wear_per_lap is None
                           else round(self.wear_per_lap, 5)),
            "source": self.source,
            "lapsMeasured": self.laps_measured,
            "stintsMeasured": self.stints_measured,
            "longestStintLaps": self.longest_stint_laps,
            "tyreWindow": self.window,
            "windowQualification": self.window_note,
        }


@dataclass
class RaceInputs:
    """Everything the plan rests on, each with its provenance."""
    race_laps: int
    lap_time_ms: int
    # Set for a race run to the clock rather than to a distance. **A timed
    # race is a different problem**: the distance is not fixed, the time is,
    # so a pit stop does not make the race longer - it costs laps. Planning
    # one as a fixed lap count produced a 52-minute plan for a 50-minute race,
    # which is not a slow plan, it is an impossible one.
    race_minutes: float | None = None
    # Where in the game day the race runs. `daylight.race_span_h` turns these
    # into the hours it passes through, which is what practice is checked
    # against.
    start_hour: float | None = None
    time_multiplier: float | None = None
    # What GT7 allows for completing the lap in progress when the clock
    # expires. The race ends at the first line crossing after the limit, so
    # its longest possible duration is the limit plus one lap - or plus this,
    # whichever is shorter.
    extra_time_s: float | None = None
    fuel_per_lap_l: float | None = None
    # **Lap-to-lap scatter on that burn, and it is what sizes the margin.**
    # None where too few laps exist to take an sd from, and then the margin
    # falls back to CLAUDE.md's flat lap and says so. See `fuel_margin_l`.
    fuel_sd_l: float | None = None
    fuel_samples: int = 0
    # Lap-to-lap scatter on the reference lap, seconds. Only a timed race
    # needs it, and only to decide whether its own distance is resolvable -
    # see `lap_count_firm`. None where too few laps exist to take one from,
    # and then the count is treated as unresolved.
    lap_time_sd_s: float | None = None
    fuel_capacity_l: float | None = None
    refuel_rate_lps: float = 2.5
    pit_loss_s: float = 20.0
    # Declared until something times a stop at this circuit. Carried rather
    # than asserted at the export boundary so the payload and the screen
    # cannot disagree about it.
    pit_loss_source: str = PIT_LOSS_DECLARED
    pit_dead_time_s: float = PIT_DEAD_TIME_S
    wear_per_lap: float | None = None
    wear_measured_at_race_multiplier: bool = True
    mandatory_stops: int = 0
    available_compounds: tuple[str, ...] = ()
    required_compounds: tuple[str, ...] = ()
    fuel_weight_s_per_l_per_lap: float = FUEL_WEIGHT_S_PER_L_PER_LAP
    # How the pace and fuel figures above were weighted across sessions.
    # Carried so a plan can be audited: the same laps under a different
    # half-life give a different number, and a reader has to be able to tell
    # a changed driver from a changed detector.
    weighting: object | None = None
    starting_fuel_l: float | None = None
    # The compound the practice evidence was gathered on. It is the reference
    # every pace delta is measured against, and the fallback for any compound
    # with no profile of its own.
    evidence_compound: str | None = None
    # What each compound costs and how long it lasts, keyed by code. Empty
    # means the model has no way to tell compounds apart, and it says so
    # rather than quietly planning them all as identical.
    compound_profiles: dict[str, CompoundProfile] = field(default_factory=dict)

    @property
    def is_timed(self) -> bool:
        """A race run to the clock, where an extra lap can really appear."""
        return self.race_minutes is not None

    @property
    def lap_count_firm(self) -> bool:
        """Whether a timed race's distance is resolved enough to fuel to.

        Always true for a lap race - the distance is the entry. For a timed
        one it is the same test the live clock uses: how far the reference lap
        would have to move before the count changes, against the lap-to-lap
        noise it actually has. Inside the noise, an extra lap is real and the
        fuel has to cover it; outside, the count is as known as a distance
        race's and a lap of spare fuel is pit time spent on nothing.

        False where nothing has measured the noise, because an unmeasured
        margin is not a firm one.
        """
        if not self.is_timed:
            return True
        limit = self.race_limit_s
        lap_s = self.lap_time_ms / 1000.0 if self.lap_time_ms else 0.0
        if not limit or lap_s <= 0.0 or not self.lap_time_sd_s:
            return False
        laps = math.ceil(limit / lap_s)
        # How much slower the reference lap could be before `laps` no longer
        # fit, and how much quicker before one more does. The tighter of the
        # two is what the noise has to clear.
        slower = (limit / (laps - 1) - lap_s) if laps > 1 else float("inf")
        quicker = lap_s - limit / (laps + 1)
        return min(slower, quicker) >= self.lap_time_sd_s

    def margin_for(self, laps: int | float | None) -> tuple[float | None, str]:
        """This event's fuel margin for a stint of `laps`, and why."""
        return fuel_margin_l(laps, self.fuel_per_lap_l,
                             sd_l=self.fuel_sd_l, timed=self.is_timed,
                             lap_count_firm=self.lap_count_firm)

    def margin_cost_s(self, laps: int | float | None) -> float | None:
        """What that margin costs in the pit lane, at this event's rate.

        The number the driver actually feels. At Watkins' measured 1.001 L/s
        a litre is a second, and it was six of them.
        """
        margin, _ = self.margin_for(laps)
        if margin is None or not self.refuel_rate_lps:
            return None
        return margin / self.refuel_rate_lps

    def profile_for(self, compound: str | None) -> CompoundProfile:
        """The profile for a compound, or the reference's rate wearing its name.

        A compound with no profile inherits the measured reference rate and is
        labelled `assumed`, never `measured`. That is the difference between
        "this stint is planned" and "this stint is guessed", and every plan
        built on one carries a note saying which.

        **A profile with no wear rate inherits it too.** That case is not the
        same as having no profile: a compound run in practice and never
        gauge-read has a pace we know and a wear rate we do not, and it was
        being costed at *zero* degradation - so the tyre nobody had measured
        paid nothing while every measured one paid, and it won the plan. Two
        identical profiles, one with `wear_per_lap=None`, came out 4.9 s apart
        with the unmeasured one first.
        """
        if compound and compound in self.compound_profiles:
            profile = self.compound_profiles[compound]
            if profile.wear_per_lap is None and self.wear_per_lap:
                return replace(profile, wear_per_lap=self.wear_per_lap,
                               source=SOURCE_ASSUMED)
            return profile
        return CompoundProfile(
            code=compound or (self.evidence_compound or "unknown"),
            pace_delta_s=0.0,
            wear_per_lap=self.wear_per_lap,
            source=(SOURCE_MEASURED
                    if compound and compound == self.evidence_compound
                    and self.wear_per_lap else SOURCE_ASSUMED),
        )

    @property
    def is_timed(self) -> bool:
        return self.race_minutes is not None and self.race_minutes > 0

    @property
    def race_limit_s(self) -> float | None:
        return None if not self.is_timed else self.race_minutes * 60.0

    @property
    def final_lap_allowance_s(self) -> float:
        """How far past the clock the last lap may run.

        A lap that takes less than GT7's allowance is finished; one that takes
        longer is cut off by it. Both are ceilings on the same thing.
        """
        lap_s = self.lap_time_ms / 1000.0
        if self.extra_time_s is None:
            return lap_s
        return min(lap_s, self.extra_time_s)

    @property
    def max_duration_s(self) -> float | None:
        """The longest this race can possibly last, in seconds.

        Cross the line a moment before the clock expires and you still have to
        complete one more lap: that, and not a second more, is the ceiling. A
        plan whose total exceeds it is describing a race that cannot happen.
        """
        limit = self.race_limit_s
        return None if limit is None else limit + self.final_lap_allowance_s

    def planning_compounds(self) -> tuple[str, ...]:
        """The compounds a stint may actually be planned on.

        **Wet compounds are never planned on.** GT7's weather cannot be known
        before the race, and no wet running has ever been done, so a plan built
        around Intermediates is a plan built on nothing - and it competes with,
        and beats, plans built on measured rubber, because a compound with no
        profile inherits the reference's rate and looks free. They stay
        available to the driver as a live call; they are not a strategy.

        **Untested dry compounds are not planned on either, for the same
        reason.** Yas Marina, 16 Aug 2026: the night-race plan suggested RH
        and RM, neither of which had ever been run. A compound with no
        profile inherits the reference's pace delta of zero and the
        reference's wear rate, so the search saw three identical tyres and
        chose between them on nothing. Asked for directly: "it should only
        suggest tyres that have been tested." A declared-but-untested
        compound stays a live call for the driver, not a strategy.

        Two deliberate exceptions. A compound the REGULATIONS require is
        planned regardless - every plan without it is illegal, and the
        [ASSUMED] note already says what such a plan rests on. And when
        nothing at all has a profile the model cannot tell compounds apart
        anyway, so the filter stands down rather than filtering the whole
        declaration out.
        """
        dry = tuple(code for code in self.available_compounds
                    if code and not is_wet_compound(code))
        if not self.compound_profiles:
            return dry
        return tuple(code for code in dry
                     if code in self.compound_profiles
                     or code in self.required_compounds)

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
    def laps_completed(self) -> int:
        """Race distance. An input for a lap race, an output for a timed one."""
        return sum(stint.laps for stint in self.stints)

    @property
    def pit_laps(self) -> list[int]:
        return [stint.end_lap for stint in self.stints[:-1]]

    def label(self) -> str:
        if self.stops == 0:
            return "No stop"
        return f"{self.stops} stop" + ("" if self.stops == 1 else "s")

    def as_export(self, inputs: RaceInputs) -> dict:
        """The `strategy` section of the export contract."""
        payload = {
            "plan": {
                "stops": self.stops,
                "laps": self.laps_completed,
                "stintLaps": [stint.laps for stint in self.stints],
                "compounds": [stint.compound for stint in self.stints],
                # **Only the first stop travels.** A two-stop plan therefore
                # reads as a one-stop here, and the outcome line compared two
                # real stops against that single lap and called a correctly
                # executed plan a deviation. `race_outcome` now refuses that
                # comparison rather than making it wrongly; emitting the whole
                # list needs `pitLaps` adding to the contract's key
                # allow-list first, or `to_json` refuses the payload outright.
                "pitLap": self.pit_laps[0] if self.pit_laps else None,
            },
            "bindingConstraint": self.binding_constraint,
            "compoundCrossover": self.crossover,
            "compoundProfiles": [profile.as_export()
                                 for profile in self.profiles.values()],
            "assumptions": {
                "pitLossS": inputs.pit_loss_s,
                "pitLossSource": inputs.pit_loss_source,
                "fuelPerLapL": inputs.fuel_per_lap_l,
                "fuelWeightSPerLPerLap": inputs.fuel_weight_s_per_l_per_lap,
                "fuelWeightSource": "derived-not-measured",
                # The pace this plan's compounds carry against the one
                # practice ran on, averaged over the race distance - or null
                # where no compound in it has a pace that was ever comparable.
                "compoundDeltaSPerLap": measured_deficit(self, inputs),
            },
        }
        # A timed race is a different object from a lap race and the payload
        # has to say which. Without it a reader sees a lap count and takes the
        # distance for a regulation, when in this race it is an outcome of the
        # plan: the stops are paid for in laps, and the flag falls at the same
        # moment whatever the plan does.
        if inputs.is_timed:
            payload["raceLength"] = {
                "type": "time",
                "minutes": inputs.race_minutes,
                "startHour": inputs.start_hour,
                "timeMultiplier": inputs.time_multiplier,
                "extraTimeS": inputs.extra_time_s,
                "lapsAtThisPace": self.laps_completed,
                "maxDurationS": round(inputs.max_duration_s, 1),
                "finishAtS": round(self.total_time_s, 1),
                "note": (
                    "The flag falls at the first line crossing after the "
                    "clock. Distance is an output of the plan, not an input - "
                    "every stop is time stationary while the clock runs and is "
                    "paid for in laps. maxDurationS is the longest this race "
                    "can possibly last; a plan past it is impossible, not slow."),
            }
        else:
            # Type only. The contract documents nothing else under
            # `raceLength` for a lap race - the distance is `plan.laps` - and
            # an undocumented `laps` here made `to_json` refuse **every lap
            # race's payload**, which is the export failing closed on the
            # common case.
            payload["raceLength"] = {"type": "laps"}
        return payload

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

# The clock simulation moves one lap per pass and starts from the previous
# estimate, so it converges in a handful. The cap is a backstop against a
# pathological lap time, not a working limit.
MAX_CLOCK_ITERATIONS = 40


def is_wet_compound(code: str | None) -> bool:
    """Intermediate and Heavy Wet, from the one compound catalogue."""
    if not code:
        return False
    compound = get_by_code(code)
    return bool(compound and compound.wet)


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


@lru_cache(maxsize=200_000)
def _stint_seconds(laps: int, base_s: float, wear: float | None,
                   fuel_at_start_l: float | None, fuel_per_lap_l: float | None,
                   fuel_weight: float) -> float:
    """The integral itself, on primitives so it can be cached.

    The optimiser evaluates this thousands of times over a handful of distinct
    (compound, length) pairs, so caching turns the search from seconds into
    milliseconds. Nothing here reads mutable state.
    """
    total = 0.0
    for lap_index in range(laps):
        lap_time = base_s
        if wear:
            total += pace_loss_s((lap_index + 1) * wear)
        if fuel_at_start_l is not None and fuel_per_lap_l:
            onboard = max(0.0, fuel_at_start_l - lap_index * fuel_per_lap_l)
            lap_time += onboard * fuel_weight
        total += lap_time
    return total


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
    return _stint_seconds(
        laps, inputs.lap_time_ms / 1000.0 + profile.pace_delta_s,
        profile.wear_per_lap, fuel_at_start_l, inputs.fuel_per_lap_l,
        inputs.fuel_weight_s_per_l_per_lap)


def refuel_time_s(litres: float, inputs: RaceInputs) -> float:
    if litres <= 0 or inputs.refuel_rate_lps <= 0:
        return 0.0
    return litres / inputs.refuel_rate_lps


def stint_limit(inputs: RaceInputs,
                profile: CompoundProfile) -> tuple[int | None, str]:
    """The longest runnable stint on this compound, and what limits it.

    Three ceilings, and the lowest wins:

    * the **tyre**, from `0.85 / w`;
    * the **tank**, from capacity against burn;
    * the **evidence** - the longest stint actually run on this compound.

    The third exists because the first two are only as good as the rate behind
    them. A wear rate taken over four laps and divided wrongly proposed a
    twelve-lap stint on a set that had never gone past four, and nothing in the
    model objected: `0.85 / w` will happily extrapolate a stint nobody has
    completed. Refusing to plan past the evidence is the cheap guard against
    every future version of that, and it errs in the direction §5.1 of
    `CLAUDE.md` says is the survivable one.
    """
    candidates = [
        (tyre_limited_laps(profile.wear_per_lap), CONSTRAINT_TYRE),
        (fuel_limited_laps(inputs.fuel_capacity_l, inputs.fuel_per_lap_l),
         CONSTRAINT_FUEL),
        (profile.longest_stint_laps or None, CONSTRAINT_EVIDENCE),
    ]
    known = [(laps, why) for laps, why in candidates if laps is not None]
    if not known:
        return None, CONSTRAINT_UNKNOWN
    return min(known, key=lambda pair: pair[0])


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
    clock_total = None
    if inputs.is_timed:
        stint_lengths, clock_total = clock_bound_stints(inputs, profiles, limits)
    else:
        # The optimum, not an even share. `allocate_laps` is the fallback for
        # the case the optimiser refuses - the caps cannot cover the distance -
        # so the plan is still built and then reported as not runnable, rather
        # than vanishing without saying why.
        stint_lengths = (optimal_split(inputs, profiles, limits,
                                       inputs.race_laps)
                         or allocate_laps(inputs.race_laps, limits))
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
            # To the diamond, plus the margin `fuel_margin_l` sizes - a flat
            # lap only where the burn's own scatter has not been measured, or
            # where the clock rather than the distance decides the race. At a
            # slow refuel rate the difference is seconds in the pit lane and
            # they are the driver's, not the model's, to spend.
            #
            # Deliberately NOT clamped to the tank: clamping made an impossible
            # plan look cheap, because the stint was then costed as carrying a
            # tankful rather than the 1010 L it actually needed, and paid no
            # stop for the difference. The requirement is reported honestly and
            # the plan is rejected.
            margin_l, margin_why = inputs.margin_for(laps)
            fuel_needed = laps * inputs.fuel_per_lap_l + (margin_l or 0.0)
            if inputs.fuel_capacity_l and fuel_needed > inputs.fuel_capacity_l:
                feasible = False
                notes.append(
                    f"Stint {index + 1} needs {fuel_needed:.0f} L including "
                    f"{margin_l:.1f} L of margin ({margin_why}), and the tank "
                    f"holds {inputs.fuel_capacity_l:.0f} L.")

        stints.append(Stint(laps=laps, compound=sequence[index],
                            fuel_l=fuel_needed, start_lap=start_lap))
        total += stint_time_s(laps, inputs, fuel_at_start_l=fuel_needed,
                              profile=profiles[index])
        start_lap += laps

        if index < len(stint_lengths) - 1:
            # A stop the clock has already beaten is a stop nobody makes: the
            # flag falls at the next line crossing, and the driver takes it
            # rather than turning in. A plan that schedules one is describing
            # a race that does not happen, and its total runs past the longest
            # duration the race can have - which is how a 50-minute race came
            # back as a 52-minute plan.
            limit_s = inputs.race_limit_s
            if limit_s is not None and total >= limit_s:
                feasible = False
                notes.append(
                    f"The stop after stint {index + 1} falls at "
                    f"{total / 60:.1f} min, after the {inputs.race_minutes:g}-"
                    f"minute flag. Nobody pits on the last lap of a timed "
                    f"race; this plan cannot be run as written.")
            total += inputs.pit_loss_s + inputs.pit_dead_time_s
            if fuel_needed:
                total += refuel_time_s(fuel_needed, inputs)

    # **Say what the margin is and what it costs.** CLAUDE.md §5.1 asks for a
    # margin to be built in AND stated; the second half was missing, and a
    # margin nobody can see is a margin nobody can argue with. At Watkins it
    # was six seconds of standing still and the driver found out by finishing
    # the race with it still in the tank.
    if stints and inputs.fuel_per_lap_l:
        longest = max(stint.laps for stint in stints)
        margin_l, margin_why = inputs.margin_for(longest)
        cost_s = inputs.margin_cost_s(longest)
        if margin_l is not None:
            said = (f"Fuel margin on the longest stint is {margin_l:.1f} L "
                    f"({margin_why})")
            if cost_s is not None:
                said += (f" - {cost_s:.0f} s in the pit lane at "
                         f"{inputs.refuel_rate_lps:g} L/s")
            notes.append(said + ".")

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

    if inputs.is_timed:
        notes.append(
            f"Timed race: {inputs.race_minutes:g} minutes is "
            f"{sum(stint_lengths)} laps at this pace **with {stops} "
            f"{'stop' if stops == 1 else 'stops'}**. Stopping costs laps, not "
            f"time - the flag falls at the same moment either way, so these "
            f"plans are compared on distance covered and not on total time.")

    # A timed race finishes when the clock says so. `total` is the sum of the
    # parts and drifts from that by the fuel taken for the final lap, which the
    # reserve already covers; the clock is the authority on when the flag fell.
    if clock_total is not None:
        total = clock_total

    plan = Plan(stints=stints, total_time_s=total,
                binding_constraint=constraint, notes=notes, feasible=feasible)
    plan.profiles = {profile.code: profile for profile in profiles}
    return plan


def stint_cost_s(inputs: RaceInputs, profile: CompoundProfile, laps: int, *,
                 first: bool) -> float:
    """What one stint costs, **including the stop that put the car on it**.

    Every stint after the first pays for the stop that preceded it, and pays
    the refuel for **its own** fuel rather than the previous stint's. That is
    not a rearrangement: the old code charged the stop after stint *i* for
    stint *i*'s fuel, which is the wrong tank. It made no difference while
    every stint was the same length, and it makes a large one now that they
    are not - a 3-lap stint followed by a 14-lap one was being charged 3 laps
    of fuel for a stop that actually fills for 14.
    """
    fuel = stint_fuel_l(laps, inputs)
    total = stint_time_s(laps, inputs, fuel_at_start_l=fuel, profile=profile)
    if not first:
        total += inputs.pit_loss_s + inputs.pit_dead_time_s
        if fuel:
            total += refuel_time_s(fuel, inputs)
    return total


def optimal_split(inputs: RaceInputs, profiles: list[CompoundProfile],
                  limits: list[int | None], total_laps: int) -> list[int] | None:
    """The stint lengths that cover `total_laps` in the least time.

    **This is the answer to "when should I stop".** The old split shared the
    laps out evenly and clipped to the caps, so the only stint lengths ever
    costed were the even one and the cap - and the economics of stopping a lap
    earlier or later were never evaluated at all. A stint should end when
    carrying on costs more than stopping does, and that is not a threshold, it
    is an optimisation.

    Exact, not heuristic. A stint's cost depends on nothing but its own
    compound and length, so the problem decomposes and a dynamic program finds
    the true optimum in milliseconds. It also gets the end of the race right
    without a special case: a stop with too few laps left to amortise it never
    wins, which is the "unless it is close to the end" the driver asked for.

    Returns None when the caps cannot cover the distance at all - that is a
    finding, not a plan, and `build_plan` reports it as one.
    """
    count = len(profiles)
    caps = [min(cap, total_laps) if cap is not None else total_laps
            for cap in limits]
    if sum(caps) < total_laps:
        return None

    # f(index, remaining) -> (cost, first stint length)
    best: dict[tuple[int, int], tuple[float, int]] = {}

    def solve(index: int, remaining: int) -> tuple[float, int]:
        if index == count - 1:
            if 1 <= remaining <= caps[index]:
                return stint_cost_s(inputs, profiles[index], remaining,
                                    first=index == 0), remaining
            return math.inf, 0
        key = (index, remaining)
        if key in best:
            return best[key]
        # Leave at least one lap for every stint still to come.
        highest = min(caps[index], remaining - (count - index - 1))
        answer = (math.inf, 0)
        for laps in range(1, max(0, highest) + 1):
            here = stint_cost_s(inputs, profiles[index], laps,
                                first=index == 0)
            rest, _ = solve(index + 1, remaining - laps)
            if here + rest < answer[0]:
                answer = (here + rest, laps)
        best[key] = answer
        return answer

    cost, _ = solve(0, total_laps)
    if cost == math.inf:
        return None

    lengths, remaining = [], total_laps
    for index in range(count):
        _, laps = solve(index, remaining)
        lengths.append(laps)
        remaining -= laps
    return lengths


def stint_fuel_l(laps: int, inputs: RaceInputs) -> float | None:
    """What a stint of this length is fuelled for: the distance plus a lap."""
    if not inputs.fuel_per_lap_l:
        return None
    return (laps + FUEL_MARGIN_LAPS) * inputs.fuel_per_lap_l


def elapsed_for_s(inputs: RaceInputs, stint_lengths: list[int],
                  profiles: list[CompoundProfile]) -> float:
    """Wall-clock seconds to run these stints, stops included."""
    return sum(stint_cost_s(inputs, profiles[index], laps, first=index == 0)
               for index, laps in enumerate(stint_lengths))


def clock_bound_stints(inputs: RaceInputs, profiles: list[CompoundProfile],
                       limits: list[int | None]) -> tuple[list[int], float]:
    """The stints a timed race actually runs, and what the clock reads at the
    flag.

    **The distance is an output, not an input.** The race ends at the first
    line crossing after the clock expires, so every stop is time spent
    stationary while the clock runs and is paid for in laps rather than in
    seconds. A model handed a fixed lap count cannot see that trade at all and
    reports the stops as free - which is how a 50-minute race came back as a
    52-minute plan.

    Two things make this a fixed point rather than a division. A lap is not a
    constant: the tyre goes off and the tank empties, both already in
    `stint_time_s`. And the fuel load depends on the distance while the
    distance depends on the elapsed time, so the two have to be settled
    together - taking one more lap's fuel makes every stop longer, which can
    itself bring the flag forward a lap.

    So it settles on the longest schedule that is **still short of the flag**,
    and then adds the lap that carries the car past it. That final lap is
    covered by the reserve lap already in every stint's fuel, which is what
    the reserve is for, so it costs a lap of time and nothing at the pumps.
    """
    limit_s = inputs.race_limit_s
    if not limit_s:
        return allocate_laps(inputs.race_laps, limits), 0.0

    def elapsed_at(count: int) -> float:
        split = optimal_split(inputs, profiles, limits, count)
        return math.inf if split is None else elapsed_for_s(inputs, split,
                                                            profiles)

    laps = max(1, inputs.race_laps)
    for _ in range(MAX_CLOCK_ITERATIONS):
        if elapsed_at(laps) >= limit_s:
            if laps <= 1:
                break
            laps -= 1
            continue
        break
    for _ in range(MAX_CLOCK_ITERATIONS):
        if elapsed_at(laps + 1) < limit_s:
            laps += 1
            continue
        break

    lengths = optimal_split(inputs, profiles, limits, laps)
    if lengths is None:
        return allocate_laps(laps, limits), 0.0
    elapsed = elapsed_for_s(inputs, lengths, profiles)

    # The clock has not expired, so one more lap has to be run whatever the
    # plan says. It lands on the last stint, on the fuel that stint already
    # took, and it is what takes the race past the flag.
    fuel = stint_fuel_l(lengths[-1], inputs)
    final_lap_s = (stint_time_s(lengths[-1] + 1, inputs, fuel_at_start_l=fuel,
                                profile=profiles[-1])
                   - stint_time_s(lengths[-1], inputs, fuel_at_start_l=fuel,
                                  profile=profiles[-1]))
    lengths[-1] += 1
    return lengths, elapsed + final_lap_s


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
    available = list(inputs.planning_compounds())
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

    # **A timed race is won on distance, not on elapsed time.** Every plan
    # ends at the same moment - the flag falls when the clock does - so
    # ranking them on total time ranks them on how far past the limit their
    # last lap happened to fall, which is noise. The plan that covers more
    # laps in the same fifty minutes is the one in front, and among plans
    # covering the same distance the one that got there first.
    if inputs.is_timed:
        ordered = sorted(runnable,
                         key=lambda p: (-p.laps_completed, p.total_time_s,
                                        p.stops))
        best_laps = ordered[0].laps_completed
        best_time = ordered[0].total_time_s
        for plan in ordered:
            # Seconds behind at the flag: a lap down is a lap's worth of time,
            # which is what the driver actually sees in the results.
            lap_s = inputs.lap_time_ms / 1000.0
            plan.delta_s = ((best_laps - plan.laps_completed) * lap_s
                            + plan.total_time_s - best_time)
        ordered[0].crossover = crossover(ordered, inputs)
        return ordered

    ordered = sorted(runnable, key=lambda p: (p.total_time_s, p.stops))
    best = ordered[0].total_time_s
    for plan in ordered:
        plan.delta_s = plan.total_time_s - best
    ordered[0].crossover = crossover(ordered, inputs)
    return ordered


def crossover_lap(faster: CompoundProfile, harder: CompoundProfile,
                  *, max_laps: int = 60) -> int | None:
    """The lap on which a worn `faster` falls behind a **fresh** `harder`.

    The question as the driver asks it: when does the soft stop being the
    quicker tyre? It is not the same question as when to stop - that is an
    optimisation over the whole race and `optimal_split` answers it - but it is
    the one that makes the answer legible, and it is worth stating on its own.

    A compound at wear rate `w` loses nothing while it is inside the flat phase
    and then climbs; the crossover is where that climb has eaten the pace gap
    it started with. `None` when the gap is never eaten inside `max_laps`, or
    when either compound has no measured rate to climb.
    """
    if not faster.wear_per_lap or not harder.wear_per_lap:
        return None
    # Both gaps have to be measured. An unmeasured pace is stored as 0.0, and
    # 0.0 against a measured delta would read as a real gap and put a crossover
    # lap in front of the driver that nothing supports.
    if not (faster.pace_known and harder.pace_known):
        return None
    gap = harder.pace_delta_s - faster.pace_delta_s
    if gap <= 0:
        return None                     # the "harder" tyre is not the slower one
    for lap in range(1, max_laps + 1):
        lost = (pace_loss_s(lap * faster.wear_per_lap)
                - pace_loss_s(1 * harder.wear_per_lap))
        if lost >= gap:
            return lap
    return None


def crossover_table(inputs: RaceInputs) -> list[dict]:
    """Every ordered pair of planning compounds, and where they cross.

    Reported rather than acted on: the plan comes from the optimiser, and this
    says in one line why it looks the way it does.
    """
    codes = [code for code in inputs.planning_compounds()
             if code in inputs.compound_profiles]
    out = []
    for quick, hard in product(codes, repeat=2):
        if quick == hard:
            continue
        first, second = inputs.profile_for(quick), inputs.profile_for(hard)
        lap = crossover_lap(first, second)
        if lap is None:
            continue
        out.append({
            "faster": quick,
            "than": hard,
            "crossesOnLap": lap,
            "paceGapSPerLap": round(second.pace_delta_s - first.pace_delta_s, 3),
            "note": (f"A {quick} is quicker than a fresh {hard} for {lap - 1} "
                     f"laps; from lap {lap} the worn {quick} is the slower "
                     f"tyre."),
        })
    return out


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
        "compoundCrossoverLaps": crossover_table(inputs),
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


def measured_deficit(plan: Plan, inputs: RaceInputs) -> float | None:
    """`mean_deficit`, but **null where nothing in it was measured**.

    An unmeasured pace delta is stored as 0.0 and `pace_known` is what tells
    it apart from a real nothing. The same payload emits `paceDeltaSPerLap:
    null` per compound and then a confident 0.0 here, which reads as "these
    compounds are exactly level" - a finding, off a comparison
    `comparable_pace` refused to make.

    It does not refuse as far as `crossover_lap` does. A plan whose every
    stint runs the compound the evidence came from carries no gap at all: the
    reference against itself is 0.0 by construction, not by measurement, and
    that is a true 0.0 whether or not any comparison ever qualified.
    """
    pairs = [(stint.compound, inputs.profile_for(stint.compound))
             for stint in plan.stints]
    if any(profile.pace_known for _, profile in pairs):
        return round(mean_deficit(plan, inputs), 3)
    if all(code in (None, inputs.evidence_compound) for code, _ in pairs):
        return 0.0
    return None


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
    planning = inputs.planning_compounds() or inputs.available_compounds
    filler = inputs.evidence_compound
    if filler not in planning:
        filler = planning[0]
    sequence = list(inputs.required_compounds)[:stints]
    while len(sequence) < stints:
        sequence.append(filler)
    return sequence


def laps_from_minutes(minutes: float, lap_time_ms: int) -> int:
    """A timed race, expressed in laps so the same model applies."""
    if lap_time_ms <= 0:
        raise StrategyImpossible("no reference lap time")
    return max(1, math.ceil(minutes * 60_000 / lap_time_ms))
