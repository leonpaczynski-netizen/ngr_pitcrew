"""What the plan expects to execute, and what it is actually executing.

The driver asked for this in as many words: *"Race strat also needs to be
updated with a median laptime and fuel burn for the plan based on practice and
what it is calculating and expecting for that plan to execute. Then engineer
has something to reference lap to lap as to if and how we need to adjust the
plan."*

So a plan carries two numbers it was built on - a median lap time and a fuel
burn per lap - and every lap the race is compared against them. Three rules
keep the comparison honest, and they are not symmetric because the two
channels are not:

* **Fuel burn is the low-noise channel and it is actionable.** Measured on his
  own race: the running median of the race's own burn was within 2% of its
  final value after ONE lap and never left that band, while the practice
  figure the plan was built on was never closer than 9.6% - it was 10.7% high,
  and that error alone turned a zero-stop race into a two-stop plan. So the
  race's burn replaces practice outright rather than being averaged with it.

  **`planned()` will happily store a figure that is worth nothing**, and on
  the one race where it can be checked it did: 7.563 L/lap is not an average
  of anything, it is literally session 11 lap 4's `fuel_used`
  (7.563377380371094) - one lap, from a session tagged `car_category = GR3`
  among a car's GRN sessions. This module reports what the plan said it would
  execute; it cannot repair how the plan came by it. Fixing the evidence
  selection that produced it is separate and outstanding.
  It is not trusted on lap one all the same: the zero-versus-one-stop decision
  at that race sat inside **1.80%**, and a three-lap mean is only good to
  +/-2.18% at 95% where five laps is +/-1.69%. Five it is.
* **Lap time is the noisy channel and it only ever CONFIRMS.** His measured
  standard deviation at this car and circuit is **2.04 s** - not the 0.918 s
  on record, which was a Monza/Porsche figure taken over a population that
  still contained incident laps (recomputed clean, Monza is 0.68-0.76 s).
  **Sigma does not transfer between cars or circuits and is never inherited**:
  it is measured from the race's own laps, and until enough of them exist the
  honest output is "not yet measurable" rather than a number.
* **Wear has no live channel at all.** Confirmed on the measured race: zero
  gauge readings across all fifteen laps. The wear the plan was built on stays
  the plan's assumption for the whole race, labelled as one everywhere.

Every figure travels with its sample count and its source, because a burn from
three laps and one from fourteen are not the same claim.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import median, stdev

# **How many green race laps before the race's own burn replaces practice.**
# Measured: convergence is immediate - within 2% of the final median after one
# lap - so this is not a convergence figure, it is a PRECISION figure. The
# decision that mattered at the measured race (zero stops or one) turned on
# 1.80%; three laps resolve to +/-2.18% and five to +/-1.69%. Raised from the
# three that used to be here for exactly that reason.
RACE_BURN_LAPS = 5

# And the same question for pace, which is a different number because the
# channel is different: three clean laps is the minimum a median can be taken
# over at all, and it is what `RaceCoordinator.representative_pace_ms` already
# requires before it will report a pace.
RACE_PACE_LAPS = 3

# **The lap-time noise floor is measured, never inherited.** Below this many
# race laps there is no sigma and no comparison - the app says "not yet
# measurable" instead of showing a delta, because at the measured 2.04 s
# anything said about being on or off plan inside the first four laps is
# noise. Four is also exactly where a 2 s/lap deviation becomes detectable.
SIGMA_MIN_LAPS = 4

# The multiplier that turns that noise into a two-sided detection floor for a
# mean over n laps: sigma * K / sqrt(n). 1.96 is the 95% figure, which is the
# weakest claim worth making out loud.
DETECT_K = 1.96

# **A lap that is not evidence about the burn rate.** The burn on a green lap
# is extremely stable (CV 2.0%); the burn on any lap at all is not (CV 10.4%),
# and the whole spread comes from incident laps and from laps he was
# deliberately saving on. A trailing window that admits a saving lap reads
# **-12.17%** and would plan the rest of the race on a rate he was only
# achieving by lifting. So the burn population is filtered on the same signals
# the pace population is - a lap this far over the race's own best is an
# incident - plus the app's own knowledge of when it asked him to save.
BURN_OUTLIER_FRACTION = 0.04

PRACTICE = "practice"
RACE = "race"
# The pair where practice set the figure and the race has laps but not yet
# enough of them to take over. Named so the export can show which of the two
# the plan was running on at any point.
PRACTICE_PENDING_RACE = "practice, race not yet converged"
# What the pace comparison says before it can say anything. Not a number:
# a delta quoted inside the noise floor is an invitation to read noise as a
# trend, which is the whole reason lap time may not trigger anything.
NOT_YET_MEASURABLE = "not yet measurable"

# The band around the plan's expected burn inside which nothing is said. Wider
# than the burn channel's own noise and narrower than anything that changes a
# stop count - see `replan.BURN_BAND` for how the two edges are used.
BURN_ON_PLAN = 0.03

# The contradiction the wear label has to carry. Both halves are measured on
# his own data and they point opposite ways; CLAUDE.md §4.1 says a
# disagreement is the finding, and averaging two models is the same error as
# averaging the driver against the telemetry.
WEAR_CONTRADICTION = (
    "the three gauge readings on file all show the FRONTS wearing faster "
    "(0.18/0.13, 0.15/0.09, 0.08/0.05) while the tyre-temperature gap points "
    "at the rear - unreconciled, not averaged")


@dataclass(frozen=True)
class Expectation:
    """The pair of numbers a plan expects to execute, and where they came from."""
    lap_time_ms: int | None
    lap_time_samples: int
    lap_time_source: str
    fuel_per_lap_l: float | None
    fuel_samples: int
    fuel_source: str
    # The wear rate the plan was built on. **Always the plan's assumption**:
    # there is no live wear channel, so this never updates during a race and
    # its source is never anything but the plan.
    wear_per_lap: float | None = None
    wear_source: str = "plan assumption - GT7 broadcasts no wear channel"

    def as_plan(self) -> dict:
        """The shape stored in `strategies.plan_json` and shown on the wall."""
        return {
            "expected_lap_time_ms": self.lap_time_ms,
            "expected_lap_time_samples": self.lap_time_samples,
            "expected_lap_time_source": self.lap_time_source,
            "expected_fuel_per_lap_l": (round(self.fuel_per_lap_l, 3)
                                        if self.fuel_per_lap_l is not None
                                        else None),
            "expected_fuel_samples": self.fuel_samples,
            "expected_fuel_source": self.fuel_source,
            "expected_wear_per_lap": self.wear_per_lap,
            "expected_wear_source": self.wear_source,
        }


def detectable_delta_ms(laps: int, sigma_ms: float | None) -> float | None:
    """The smallest per-lap pace change this many laps could actually show.

    None where sigma is not yet measured, which is the honest answer for the
    first few laps of a race: the floor cannot be quoted from a sigma
    belonging to another car at another circuit. Measured at this car and
    circuit, 2.0 s/lap needs four laps and 1.0 s/lap needs sixteen - so a
    fifteen-lap race can never honestly show a one-second drift.
    """
    if laps < 2 or not sigma_ms:
        return None
    return sigma_ms * DETECT_K / math.sqrt(laps)


class ExpectationTracker:
    """The plan's expectations, refreshed each lap by what the race shows.

    Built at the green from the practice figures the plan was costed with, and
    fed one completed lap at a time. `planned()` never changes - it is what the
    plan was built on, which is what the post-race audit has to compare
    against. `current()` is what the plan is now expected to execute, and it
    moves as the race supplies better numbers.
    """

    def __init__(self, *, planned_lap_time_ms: int | None = None,
                 planned_fuel_per_lap_l: float | None = None,
                 planned_wear_per_lap: float | None = None,
                 practice_lap_samples: int = 0,
                 practice_fuel_samples: int = 0) -> None:
        self._planned_lap_ms = planned_lap_time_ms
        self._planned_fuel = planned_fuel_per_lap_l
        self._planned_wear = planned_wear_per_lap
        self._practice_lap_samples = practice_lap_samples
        self._practice_fuel_samples = practice_fuel_samples
        # Every completed lap's time, in order driven, incidents included.
        # This is what a timed race's distance is predicted from - see
        # `achieved_lap_time_ms`.
        self._all_lap_ms: list[int] = []
        # (lap_time_ms, fuel_used, was_saving) per lap eligible for the
        # green populations. Filtered at read time against the race's own
        # best, because a lap is only an outlier relative to laps that came
        # after it as well as before.
        self._green: list[tuple[int, float, bool]] = []

    # ------------------------------------------------------------------ feed

    def note_lap(self, lap) -> None:
        """One completed race lap.

        Lap one carries the standing start and the grid, and it fed a "lapping
        2% slower than planned" verdict two minutes into a measured race - on
        the one lap that is slower by construction. It stays out of the pace
        and burn populations and stays IN the achieved-distance population,
        which is a question about how long a lap of this race takes.

        A lap driven under the app's own short-shift instruction is not
        evidence about the car's burn rate either: it is evidence about the
        instruction. Measured, a trailing window admitting his two saving laps
        read 12% under the real rate.
        """
        if lap.lap_time_ms > 0:
            self._all_lap_ms.append(int(lap.lap_time_ms))
        pit = bool(getattr(lap, "is_pit_lap", False)
                   or getattr(lap, "is_out_lap", False))
        if pit or lap.lap_num <= 1 or lap.lap_time_ms <= 0:
            return
        saving = bool(getattr(lap, "short_shift_rpm", None))
        self._green.append((int(lap.lap_time_ms), float(lap.fuel_used or 0.0),
                            saving))

    def _clean(self) -> list[tuple[int, float, bool]]:
        """The laps that are evidence: no incident, no saving instruction.

        The incident test is the pace estimator's own - a lap more than
        `BURN_OUTLIER_FRACTION` over the race's own best. His lap-to-lap noise
        is about 1.7% of a two-minute lap while the measured incidents run
        5-10% over, so 4% splits the two populations with margin either side.
        """
        if not self._green:
            return []
        cutoff = min(ms for ms, _, _ in self._green) * (
            1.0 + BURN_OUTLIER_FRACTION)
        return [row for row in self._green if row[0] <= cutoff and not row[2]]

    # --------------------------------------------------------------- answers

    def planned(self) -> Expectation:
        """What the plan was built on, unchanged for the whole race."""
        return Expectation(
            lap_time_ms=self._planned_lap_ms,
            lap_time_samples=self._practice_lap_samples,
            lap_time_source=PRACTICE,
            fuel_per_lap_l=self._planned_fuel,
            fuel_samples=self._practice_fuel_samples,
            fuel_source=PRACTICE,
            wear_per_lap=self._planned_wear,
        )

    def current(self) -> Expectation:
        """What the plan is now expected to execute, race evidence included."""
        fuel, fuel_n, fuel_src = self._fuel_now()
        lap_ms, lap_n, lap_src = self._pace_now()
        return Expectation(
            lap_time_ms=lap_ms, lap_time_samples=lap_n, lap_time_source=lap_src,
            fuel_per_lap_l=fuel, fuel_samples=fuel_n, fuel_source=fuel_src,
            wear_per_lap=self._planned_wear)

    def _fuel_now(self) -> tuple[float | None, int, str]:
        clean = [used for _, used, _ in self._clean() if used > 0]
        if len(clean) >= RACE_BURN_LAPS:
            # The race replaces practice outright. Averaging the two would
            # dilute the only low-noise evidence about THIS race with a figure
            # that was measured 10.7% high on the one race where both exist.
            return round(median(clean), 3), len(clean), RACE
        source = PRACTICE_PENDING_RACE if clean else PRACTICE
        return self._planned_fuel, self._practice_fuel_samples, source

    def _pace_now(self) -> tuple[int | None, int, str]:
        clean = [ms for ms, _, _ in self._clean()]
        if len(clean) >= RACE_PACE_LAPS:
            # Practice pace was measured 1.6 s/lap optimistic against the race
            # it was meant to describe, and a pooled blend was still 0.5 s
            # optimistic at the flag. Race-only converges inside 0.5 s by five
            # laps; after three, practice is drag.
            return int(median(clean)), len(clean), RACE
        source = PRACTICE_PENDING_RACE if clean else PRACTICE
        return self._planned_lap_ms, self._practice_lap_samples, source

    def race_lap_time_ms(self) -> int | None:
        """The clean pace this race is running, or None before it has one."""
        clean = [ms for ms, _, _ in self._clean()]
        if len(clean) < RACE_PACE_LAPS:
            return None
        return int(median(clean))

    def achieved_lap_time_ms(self) -> int | None:
        """The median lap **as actually run**, incidents and all.

        **This, and not the clean pace, is what a timed race's distance is
        predicted from.** Measured on the 30-minute race: the achieved median
        of 121.51 s predicts fifteen laps, which is what happened; the clean
        pace median of 119.62 s predicts sixteen, and the practice median
        predicts sixteen too. An incident lap does not make the car slower but
        it does consume the clock, and the clock is the question here.
        """
        if not self._all_lap_ms:
            return None
        return int(median(self._all_lap_ms))

    def sigma_ms(self) -> float | None:
        """Lap-to-lap noise, **measured on this car at this circuit**.

        None until `SIGMA_MIN_LAPS` clean laps exist. Never a default and
        never inherited: the recorded 0.918 s belongs to a different car at a
        different circuit and, recomputed with an incident filter, is not even
        right there (0.68-0.76 s). This car at this circuit measures 2.04 s -
        2.7 times Monza - and a builder who used the recorded figure would
        over-claim detectability by a factor of about two.
        """
        clean = [ms for ms, _, _ in self._clean()]
        if len(clean) < SIGMA_MIN_LAPS:
            return None
        return float(stdev(clean))

    def green_laps(self) -> int:
        """How many laps of this race are evidence about anything.

        Not the same as laps completed, and **not the practice sample count**:
        reading the sample count off `current()` returned the practice figure
        while practice was still the source, so one race lap looked like eight
        laps of evidence and the engineer offered a new stop shape two minutes
        after the green on a single burn reading.
        """
        return len(self._clean())

    def race_fuel_per_lap_l(self) -> float | None:
        """The green burn this race is showing, whether or not it has taken over."""
        clean = [used for _, used, _ in self._clean() if used > 0]
        if not clean:
            return None
        return round(median(clean), 3)

    # ------------------------------------------------------ on the plan?

    def burn_vs_plan(self) -> float | None:
        """Fraction over (positive) or under (negative) the planned burn.

        None where either side is unknown, and None until `RACE_BURN_LAPS`
        green laps exist: the decision this feeds turned on 1.80% at the
        measured race, and fewer laps than this cannot resolve it.
        """
        clean = [used for _, used, _ in self._clean() if used > 0]
        observed = self.race_fuel_per_lap_l()
        if (observed is None or not self._planned_fuel
                or len(clean) < RACE_BURN_LAPS):
            return None
        return (observed - self._planned_fuel) / self._planned_fuel

    def pace_vs_plan_ms(self) -> int | None:
        """Milliseconds slower (positive) or quicker than the planned lap.

        **Confirmation only.** Read `pace_detectable_ms` beside it: below that
        floor this number is his own noise and describes nothing.
        """
        observed = self.race_lap_time_ms()
        if observed is None or not self._planned_lap_ms:
            return None
        return int(observed - self._planned_lap_ms)

    def pace_detectable_ms(self) -> float | None:
        """The pace change the laps run so far could actually show."""
        return detectable_delta_ms(len(self._clean()), self.sigma_ms())

    def pace_is_real(self) -> bool:
        """Whether the pace deviation clears his own measured noise floor.

        False is the common answer and the honest one. At this car's sigma a
        fifteen-lap race can never distinguish a one-second-a-lap drift, and
        nothing inside the first four laps means anything at all.
        """
        deviation = self.pace_vs_plan_ms()
        floor = self.pace_detectable_ms()
        if deviation is None or floor is None:
            return False
        return abs(deviation) >= floor

    # ----------------------------------------------------------- reporting

    def as_snapshot(self) -> dict:
        """Expectation and outcome side by side, for the wall and the PTT."""
        current, planned = self.current(), self.planned()
        burn = self.burn_vs_plan()
        pace = self.pace_vs_plan_ms()
        floor = self.pace_detectable_ms()
        sigma = self.sigma_ms()
        return {
            "expectedLapMs": current.lap_time_ms,
            "expectedLapSource": current.lap_time_source,
            "expectedLapSamples": current.lap_time_samples,
            "expectedFuelPerLapL": current.fuel_per_lap_l,
            "expectedFuelSource": current.fuel_source,
            "expectedFuelSamples": current.fuel_samples,
            "plannedLapMs": planned.lap_time_ms,
            "plannedFuelPerLapL": planned.fuel_per_lap_l,
            "actualLapMs": self.race_lap_time_ms(),
            "achievedLapMs": self.achieved_lap_time_ms(),
            "actualFuelPerLapL": self.race_fuel_per_lap_l(),
            "burnVsPlanPct": round(burn * 100.0, 1) if burn is not None else None,
            # **Withheld until it can mean something.** A delta shown inside
            # the noise floor is read as a trend, and at this car's sigma the
            # first four laps have no floor at all.
            "paceVsPlanMs": pace if floor is not None else None,
            "paceVsPlanNote": None if floor is not None else NOT_YET_MEASURABLE,
            "paceDetectableMs": round(floor) if floor is not None else None,
            "lapTimeSigmaMs": round(sigma) if sigma is not None else None,
            "paceIsReal": self.pace_is_real(),
        }

    def audit_line(self) -> str:
        """One sentence: what the plan expected, and what it ran on.

        Written for `strategy.outcome` in the export - the contract's own home
        for what actually happened. The expectation and the outcome travel
        together because that is the whole audit value: a plan built on a
        7.56 L/lap burn that ran at 6.75 is a plan that was wrong by 10.7% on
        the one number that decides the stop count, and it planned two stops
        for a race that needed none.
        """
        parts: list[str] = []
        planned = self.planned()
        clean = self._clean()
        if planned.fuel_per_lap_l:
            said = f"Planned on {planned.fuel_per_lap_l:.2f} L/lap"
            observed = self.race_fuel_per_lap_l()
            if observed is not None:
                drift = ((observed - planned.fuel_per_lap_l)
                         / planned.fuel_per_lap_l)
                said += (f", ran {observed:.2f} over {len(clean)} green laps")
                if abs(drift) >= BURN_ON_PLAN:
                    said += (f" ({abs(drift):.0%} "
                             f"{'over' if drift > 0 else 'under'})")
            parts.append(said + ".")
        if planned.lap_time_ms:
            said = f"Planned on a {planned.lap_time_ms / 1000.0:.1f} s lap"
            observed = self.race_lap_time_ms()
            if observed is not None:
                said += f", ran {observed / 1000.0:.1f} s"
                floor = self.pace_detectable_ms()
                if floor is None:
                    said += (" - too few clean laps to measure this car's own "
                             "lap-time noise, so the difference is not a "
                             "finding")
                elif not self.pace_is_real():
                    # Never a pace claim the sample cannot support: his
                    # lap-to-lap noise is wider than the degradation band, so
                    # the honest reading of most pace deltas is silence.
                    said += (f" - inside the {floor / 1000.0:.1f} s/lap "
                             f"{len(clean)} laps at this car's measured "
                             f"{(self.sigma_ms() or 0) / 1000.0:.1f} s spread "
                             f"can distinguish, so not a finding")
            parts.append(said + ".")
        if planned.wear_per_lap is not None:
            parts.append(
                f"Wear stayed the plan's assumption of "
                f"{planned.wear_per_lap:.1%} a lap - no gauge reading was "
                f"entered during the race and GT7 broadcasts no wear channel; "
                f"{WEAR_CONTRADICTION}.")
        return " ".join(parts)


class _LapRow:
    """A stored lap seen as a live one, for the offline rebuild below.

    `LapInput` carries the tank at each end of the lap rather than the litres
    burned, so the burn is differenced here. It carries **no record of whether
    the app was asking him to short-shift**, because that lives on the `laps`
    row and does not travel this far - so `short_shift_rpm` reads as None and
    such a lap counts as ordinary evidence about the burn.

    That is a known understatement and not a defaulting convenience: on the
    measured race his two saving laps would enter the offline burn median
    where the live path excludes them, which pulls the reported figure down.
    The audit line quotes the number of green laps behind it for exactly this
    reason. Carrying the flag through `LapInput` is the fix and it is not one
    this module can make on its own.
    """

    def __init__(self, lap) -> None:
        self.lap_num = lap.lap_num
        self.lap_time_ms = lap.lap_time_ms
        self.is_pit_lap = bool(getattr(lap, "is_pit_lap", False))
        self.is_out_lap = bool(getattr(lap, "is_out_lap", False))
        self.fuel_used = max(0.0, (lap.fuel_start or 0.0)
                             - (lap.fuel_end or 0.0))
        self.short_shift_rpm = getattr(lap, "short_shift_rpm", None)


def audit_line_from_laps(expects: dict | None, laps) -> str:
    """The plan's expectation against what the race actually ran.

    Rebuilt offline from the expectation stored with the plan and the race's
    own laps, for `strategy.outcome` in the export - **the contract's own home
    for what happened**, and a free-text field, so this adds no key the
    consuming tool would have to read conservatively.

    The audit value is in carrying both halves: a plan built on 7.56 L/lap
    that ran at 6.75 is a plan that was wrong by 10.7% on the one number that
    decides the stop count, and it planned two stops for a race that needed
    none. Returns an empty string where the plan carried no expectation -
    every plan approved before this existed - rather than a sentence of nulls.
    """
    if not expects or not laps:
        return ""
    tracker = ExpectationTracker(
        planned_lap_time_ms=expects.get("expected_lap_time_ms"),
        planned_fuel_per_lap_l=expects.get("expected_fuel_per_lap_l"),
        planned_wear_per_lap=expects.get("expected_wear_per_lap"),
        practice_lap_samples=expects.get("expected_lap_time_samples") or 0,
        practice_fuel_samples=expects.get("expected_fuel_samples") or 0)
    for lap in laps:
        tracker.note_lap(_LapRow(lap))
    return tracker.audit_line()

