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
# Clean laps a stint needs before its own burn sizes the fill. Three is the
# floor the fill's scatter term already asks for, and the stint after a
# stop has usually driven three before the next stop is in question.
STINT_BURN_LAPS = 3

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

#: "the beep column being driven now" where a column may be named.
CURRENT_COLUMN = object()

# What `current_fuel_basis` sized the laps ahead on. A burn is only as good as
# the laps behind it, and after a stop those are not this stint's until there
# are `STINT_BURN_LAPS` of them.
FUEL_BASIS_STINT = "this stint"
FUEL_BASIS_RACE = "the race"
# **The two outcomes of "the higher of the race and this stint so far", named
# apart.** One string used to cover both, and it hid the thing that actually
# moves. At Bathurst Rd 8 the installed burn walked 9 -> 2 -> 3 laps across
# laps 13-15 with no stop between 12 and 22, and 19 -> 3 across laps 25-26,
# while the figure itself moved 1.14% and 0.97% - about 0.4 sigma of one lap's
# measured scatter (sd 0.214 L/lap over 22 green laps). The burn did not
# change; the population behind it did, and the record could not say which
# one had won or how many laps it had.
#
# The SELECTION is kept as it was, deliberately. Its reason is measured: at
# Bathurst a previous stint's burn was 0.25 L/lap light, and a light burn is
# the direction that says "fuel good" about a tank that is short. Taking the
# higher can over-fill by a litre; taking the lower runs him dry, and on race
# eve that is not a trade to reverse. What changes is that the answer now
# names its own population, so the count travelling beside it belongs to the
# figure (rules 4 and 12).
FUEL_BASIS_HIGHER_RACE = "the race, higher than this stint so far"
FUEL_BASIS_HIGHER_STINT = "this stint so far, higher than the race"
# **The beep's two columns are two burns, not one population.** Sardegna,
# session 183: 5.37 L/lap on the saving points and 7.04 at full revs on
# consecutive laps - a 31% step, where the whole reason the burn is trusted
# over practice is that a green lap's burn has a CV of 2.0%. Where the column
# now being driven has too few laps of its own, this race's measurement on the
# OTHER column converted by the plan's own `fuel_burns` ratio is still a
# measurement of this race; it is derived, and it is named so every call that
# quotes it says so.
FUEL_BASIS_COLUMN = "this race's other beep column, at the plan's ratio"
# And where this column HAS shown something, however little, the higher of the
# two - the same reason the pair above exists. A conversion that comes out
# under what he is actually burning is the direction that says "fuel good"
# about a tank that is short.
FUEL_BASIS_COLUMN_HIGHER = ("the higher of this beep column's own laps and the "
                            "other column at the plan's ratio")
# **Every basis that is a hedge rather than a reading**, for the callers that
# have to speak or score at a lower confidence because of it. A tuple rather
# than a list of names at each consumer: a basis added later hedges everywhere
# by construction, instead of at whichever sites someone remembered.
FUEL_BASES_HEDGED = (FUEL_BASIS_HIGHER_RACE, FUEL_BASIS_HIGHER_STINT,
                     FUEL_BASIS_COLUMN, FUEL_BASIS_COLUMN_HIGHER)
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


@dataclass(frozen=True)
class SavingResponse:
    """What the burn did after a saving instruction, and whether that is real."""

    before_l: float
    after_l: float
    #: Signed fraction. Negative is a saving.
    change: float
    #: What the change had to clear to be measurable at all, same units.
    floor: float
    laps_after: int

    @property
    def measurable(self) -> bool:
        return abs(self.change) > self.floor

    @property
    def saved(self) -> bool:
        return self.measurable and self.change < 0

    def call(self) -> str:
        """One sentence: instruction or fact first, the numbers second."""
        if not self.measurable:
            return "I can't resolve a change that small yet."
        if self.saved:
            return f"That's working. {abs(self.change) * 100:.0f} percent down."
        return (f"Not enough - the burn hasn't moved. "
                f"{self.after_l:.2f} against {self.before_l:.2f}.")


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
                 practice_fuel_samples: int = 0,
                 planned_burns: tuple[float, float] | None = None) -> None:
        self._planned_lap_ms = planned_lap_time_ms
        self._planned_fuel = planned_fuel_per_lap_l
        self._planned_wear = planned_wear_per_lap
        # `(saving, full-revs)` L/lap as the plan measured them, for converting
        # a burn from the column that has laps to the one being driven. None
        # where the plan does not run the beep, and then no conversion is
        # offered - see `other_column_burn`.
        self._planned_burns = planned_burns
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
        self._green: list[tuple[int, float, bool, int]] = []
        # **The mean fuel aboard on each of those laps, same order.** Kept
        # beside the burns rather than inside the tuple so that every existing
        # reader of `_green` and `_clean` keeps its shape - both are unpacked
        # positionally in several places. Empty where the lap did not report a
        # tank level, and then the load correction stands down.
        self._green_loads: list[float | None] = []
        # **Which beep column each green lap belongs to**, parallel to
        # `_green` - True saving, False full revs, None where nobody declared
        # one. Kept beside the rows for the same reason `_green_loads` is:
        # the tuple is unpacked positionally in a dozen places.
        #
        # `_column` is the column being driven NOW, and it is what every
        # population below is read on. None until a caller feeds one, and then
        # nothing is filtered - which is exactly the behaviour every race
        # before the plan ran the beep had, and what the offline rebuild in
        # `audit_line_from_laps` still has.
        self._green_column: list[bool | None] = []
        self._column: bool | None = None
        # **Which stint each green lap belongs to**, parallel to `_green`.
        # A pit or out lap closes a stint. The burn that sizes a fill and
        # judges the plan is the CURRENT stint's once it has enough laps:
        # at Deep Forest the whole-race median (7.35, from a stint driven
        # lift-and-coasting) said "burning 6% under plan" with the hose in
        # while the stint about to be driven ran 7.9-8.1.
        self._green_stint: list[int] = []
        # Laps that served a track-limit penalty, by number. Out of the
        # clean population whichever order the row and the read arrive in.
        self._penalised: set[int] = set()
        # **Whether the race started rolling.** Lap one of a standing start
        # carries the launch and the grid and is slower by construction; a
        # rolling start's lap one is a flying lap in the same traffic as lap
        # two, and there is no reason to throw it away. Set from the event's
        # `start_type` by the coordinator at arming; False (standing) where
        # nobody said, which is the exclusion every race had.
        self.rolling_start: bool = False
        self._stint = 0

    # ------------------------------------------------------------------ feed

    def note_lap(self, lap, *, column: bool | None = None,
                 off_reference: bool | None = None) -> None:
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

        **But a stint the PLAN declares fuel-save is not an instruction**, and
        that distinction is the caller's to make, not this module's. Since the
        `fuel_save` plan field of 15 Sep 2026 a whole stint can hand the beep
        over, and then `lap.short_shift_rpm` is set on every lap of the race -
        all 29 of Sardegna session 183. Read as "an instruction was given" it
        emptied every population here, `green_laps()` never reached the
        coordinator's `BURN_LAPS_NEEDED`, and every fuel sentence of that race
        rested on the practice figure the plan was costed with. 17 laps were
        fuelled at 5.586 L/lap where the race was burning 5.365: 97 L asked
        for against 91.2 wanted, about six seconds standing at the pump.

        * `column` - which of the beep's two columns is being driven at the
          END of this lap, or None where nothing declares one. It is what the
          populations below are read on from here.
        * `off_reference` - whether THIS lap is evidence about an instruction
          rather than about the race: it changed column mid-lap, or it was
          driven off the column the plan declared. None falls back to
          `lap.short_shift_rpm`, which is what every caller that feeds no
          column has always had.
        """
        if lap.lap_time_ms > 0:
            self._all_lap_ms.append(int(lap.lap_time_ms))
        pit = bool(getattr(lap, "is_pit_lap", False)
                   or getattr(lap, "is_out_lap", False))
        if pit:
            # The next green lap opens a new stint.
            self._stint += 1
        first = lap.lap_num <= 1 and not self.rolling_start
        if pit or first or lap.lap_time_ms <= 0:
            return
        saving = (bool(getattr(lap, "short_shift_rpm", None))
                  if off_reference is None else bool(off_reference))
        # **The lap number rides along.** Without it there is no way to split
        # the burn at the lap an instruction was given, which is the only way
        # to answer "did the saving work" - see `saving_response`.
        # **0.0 is this population's "no burn read" sentinel, not a burn.**
        # Every figure taken off `_green` filters on `used > 0` - the race
        # median, the stint median, the scatter, the lap counts - so a lap
        # whose burn could not be read is excluded everywhere rather than
        # entering a median as a zero. `_LapRow` now hands over `None` for
        # exactly those laps instead of a clamped zero (rule 9); this is
        # where the two meet.
        self._green.append((int(lap.lap_time_ms), float(lap.fuel_used or 0.0),
                            saving, int(lap.lap_num)))
        self._green_column.append(column)
        # Moved only by a caller that has a column to give: a None here is
        # "nobody said", not "full revs", and it must not retire a column that
        # was declared (rule 3).
        if column is not None:
            self._column = column
        self._green_stint.append(self._stint)
        start = getattr(lap, "fuel_start", None)
        end = getattr(lap, "fuel_end", None)
        self._green_loads.append((start + end) / 2.0
                                 if start is not None and end is not None
                                 else None)

    def set_column(self, column: bool | None) -> None:
        """The beep column being driven from here, before a lap proves it.

        **The burn has to move with the instruction, not a lap behind it.**
        The populations here are keyed on the column, and a column is
        otherwise only learned when a lap driven on it completes - so the lap
        immediately after George moves the beep would be fuelled at the burn
        of the column just left, which is about 30% away. Called by the
        coordinator wherever `RaceState.fuel_save_engaged` moves.

        A measured lap still overrules this: `note_lap` sets the column from
        what the frames say he actually drove, which is the whole point of
        `_measured_column`. None is ignored - a race with no column declared
        has one population and nothing to point at.
        """
        if column is None:
            return
        self._column = bool(column)

    def adopt_unfiled_column(self, column: bool) -> None:
        """File every lap that has no column under `column`.

        **A race with no declared column still drove its laps on one.** When
        the driver takes the beep himself mid-race (the tablet's button, 17
        Sep 2026) the population splits from that moment - and every lap
        already driven was filed with no column at all, so a plain split
        orphans them: `_on_column` matches on `is`, `None is False` is False,
        and the race loses its measured burn, its pace and its sigma back to
        the practice figures. Those laps are evidence about the column he was
        on until he pressed, and this says so.
        """
        self._green_column = [column if on is None else on
                              for on in self._green_column]

    def revise_lap_column(self, lap_num: int, column: bool) -> None:
        """File a lap under the column the frames say it was driven on.

        The measured column arrives on its own path - the controller reads the
        upshift rpm off the lap frames and hands it to the race - and it can
        land either side of the crossing. So the lap is filed with whatever
        was known at the time and corrected here when the better answer comes.

        **A measured column also clears the lap of being an instruction.** The
        exclusion exists for a lap that is a clean sample of neither column;
        one the frames place on a column is a clean sample of that column.
        Silent where the lap is not in the green population - lap one, a pit
        or out lap, and every lap of a race with no column declared.
        """
        for index, row in enumerate(self._green):
            if row[3] != int(lap_num):
                continue
            if self._green_column[index] is None:
                # No column was declared for this race at all. Filing one now
                # would split a population nothing else knows is split.
                return
            self._green_column[index] = bool(column)
            self._green[index] = (row[0], row[1], False, row[3])
            if index == len(self._green) - 1:
                self._column = bool(column)
            return

    def _on_column(self, column) -> list[tuple[int, float, bool, int]]:
        """The green rows driven on `column`, in order.

        `CURRENT_COLUMN` means the one being driven now; an explicit True or
        False asks for the other one, which is how `other_column_burn` prices
        a column this race has laps for but is not on. **Where no column was
        ever declared the whole population comes back** - no plan runs the
        beep, there is one column, and nothing here changes.
        """
        want = self._column if column is CURRENT_COLUMN else column
        if want is None:
            return list(self._green)
        return [row for row, on in zip(self._green, self._green_column)
                if on is want]

    def _clean(self, column=CURRENT_COLUMN) -> list[tuple[int, float, bool, int]]:
        """The laps that are evidence: no incident, no instruction, this column.

        The incident test is the pace estimator's own - a lap more than
        `BURN_OUTLIER_FRACTION` over the race's own best. His lap-to-lap noise
        is about 1.7% of a two-minute lap while the measured incidents run
        5-10% over, so 4% splits the two populations with margin either side.

        **The race's own best is taken within the column**, because the two
        columns are two populations in lap time as well as in burn - a
        full-revs best would tighten the window a saving lap is judged in by
        the whole cost of short-shifting.
        """
        rows = self._on_column(column)
        if not rows:
            return []
        cutoff = min(row[0] for row in rows) * (1.0 + BURN_OUTLIER_FRACTION)
        return [row for row in rows if row[0] <= cutoff and not row[2]
                and row[3] not in self._penalised]

    def note_penalty(self, lap_num: int) -> None:
        """A lap that served a track-limit penalty is not evidence of pace
        or of burn - the crawl is in both."""
        self._penalised.add(int(lap_num))

    def forget_penalty(self, lap_num: int) -> None:
        """Put a lap back: what was read as a penalty was the road.

        **CLAUDE.md rule 10 - a rule that refuses a reading must be able to
        refuse its own baseline.** The penalty detector's one systematic
        false positive is a corner the auto-segment model does not contain:
        the brake for it is at speed, going straight and outside every
        window, so it reads as a penalty on EVERY lap. The controller
        recognises that shape - a place braked on `BRAKED_SHARE` of the
        session's laps is the road - and calls this to hand a lap back where
        NOTHING is left standing on it, because that lap was struck on a
        reading that has
        since been withdrawn - a place braked on nearly every lap of the
        session is a corner, and `RoadNotPenalty` carries the measurement.
        Silent where the lap was never struck.
        """
        self._penalised.discard(int(lap_num))

    # ------------------------------------------------- did the saving work

    def saving_response(self, instructed_at_lap: int, *,
                        minimum_after: int = 2) -> "SavingResponse | None":
        """Whether the burn actually moved after a saving instruction.

        **The engineer opens this loop every time he asks for a short-shift or
        a lift, and has never closed it.** A real one comes back two or three
        laps later and says whether it worked - and if it did not, the shortfall
        the instruction was meant to cover is still there and the driver needs
        to know while he can still box.

        A split of the green burns at the instruction lap, not a second
        population: the laps are already here and the instruction lap is
        already recorded.

        **Three answers, never two.** Saved, did not save, or *cannot yet
        tell* - and the third is the honest one for the first couple of laps,
        because a difference smaller than the detection floor is not a small
        effect, it is no measurement. Run retrospectively on the race of 19
        Aug, where the engineer asked for a short-shift on lap 14: the burn
        moved 5.478 to 5.422 L, **-1.0% against a floor of 0.9%** - at the
        floor, indistinguishable from nothing, against a measured short-shift
        effect of -21.6%. He did not save, and the engineer could have said so
        on lap 17.
        """
        from statistics import median, pstdev

        before = [row[1] for row in self._clean_any()
                  if row[3] <= instructed_at_lap and row[1] > 0]
        after = [row[1] for row in self._clean_any()
                 if row[3] > instructed_at_lap and row[1] > 0]
        if len(before) < 2 or len(after) < minimum_after:
            return None

        was, now = median(before), median(after)
        if was <= 0:
            return None
        change = (now - was) / was

        # The floor is what a difference has to clear to be a difference at
        # all: the 95% interval on the median of the laps since. Stated, not
        # applied silently - "I can't resolve a change this small" is a
        # different claim from "you did not save".
        spread = pstdev(after) if len(after) > 1 else 0.0
        floor = (1.96 * spread / (len(after) ** 0.5) / was) if was else 0.0
        return SavingResponse(before_l=round(was, 3), after_l=round(now, 3),
                              change=change, floor=floor,
                              laps_after=len(after))

    def _clean_any(self) -> list[tuple[int, float, bool, int]]:
        """`_clean`, but keeping the saving laps.

        `_clean` drops them on purpose - they are evidence about the
        instruction and not about the car, so they must never reach the burn
        the plan is costed on. Here they are exactly what is being measured.
        """
        if not self._green:
            return []
        cutoff = min(row[0] for row in self._green) * (
            1.0 + BURN_OUTLIER_FRACTION)
        return [row for row in self._green if row[0] <= cutoff]

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
        clean = [used for _, used, _, _ in self._clean() if used > 0]
        if len(clean) >= RACE_BURN_LAPS:
            # The race replaces practice outright. Averaging the two would
            # dilute the only low-noise evidence about THIS race with a figure
            # that was measured 10.7% high on the one race where both exist.
            return round(median(clean), 3), len(clean), RACE
        source = PRACTICE_PENDING_RACE if clean else PRACTICE
        return self._planned_fuel, self._practice_fuel_samples, source

    def _pace_now(self) -> tuple[int | None, int, str]:
        clean = [row[0] for row in self._clean()]
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
        clean = [row[0] for row in self._clean()]
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
        clean = [row[0] for row in self._clean()]
        if len(clean) < SIGMA_MIN_LAPS:
            return None
        return float(stdev(clean))

    def laps_by_number(self) -> dict[int, tuple[int, float]]:
        """lap -> (lap_time_ms, fuel_used_l) for the laps that are evidence.

        For pairing a lap's burn and time with what the wall read of the gap
        on that lap - the tow trade (`race/tow.py`) is made on exactly that
        pairing, and nothing else keys the clean population by lap.
        """
        return {row[3]: (row[0], row[1]) for row in self._clean()}

    def green_laps(self) -> int:
        """How many laps of this race are evidence about anything.

        Not the same as laps completed, and **not the practice sample count**:
        reading the sample count off `current()` returned the practice figure
        while practice was still the source, so one race lap looked like eight
        laps of evidence and the engineer offered a new stop shape two minutes
        after the green on a single burn reading.
        """
        return len(self._clean())

    def race_fuel_per_lap_l(self, column=CURRENT_COLUMN) -> float | None:
        """The green burn this race is showing, whether or not it has taken over.

        On the beep column being driven now, or on the one named."""
        clean = [used for _, used, _, _ in self._clean(column) if used > 0]
        if not clean:
            return None
        return round(median(clean), 3)

    def race_burn_laps(self, column=CURRENT_COLUMN) -> int:
        """Green laps behind `race_fuel_per_lap_l` on that column."""
        return len([row for row in self._clean(column) if row[1] > 0])

    def other_column_burn(self) -> tuple[float, int, bool] | None:
        """This race's burn on the column it is NOT on, converted to this one.

        `(L/lap, laps behind it, the column it was measured on)`, or None.

        **The alternative is a stale number that looks fresh.** When George
        moves the beep the burn steps by about 30% (5.37 -> 7.04 at Sardegna),
        and the column just engaged has no laps of its own for five more.
        Holding the figure measured on the column he has just left is a
        confident wrong answer of exactly the kind rule 9 is about, and
        falling back to practice throws away the only measurement of this race
        there is. So the other column's own laps are converted by the ratio
        between the plan's two measured burns - which is what
        `RaceCoordinator.mode_burns_l` already does to price a switch.

        None where the plan gave no pair to convert with, where no column has
        been declared, or where the other column has fewer than
        `RACE_BURN_LAPS` laps of its own. Derived, never measured: the caller
        labels it `FUEL_BASIS_COLUMN` and the call says so out loud.
        """
        if self._planned_burns is None or self._column is None:
            return None
        save, full = self._planned_burns
        if not save or not full:
            return None
        other = not self._column
        burn = self.race_fuel_per_lap_l(other)
        laps = self.race_burn_laps(other)
        if burn is None or laps < RACE_BURN_LAPS:
            return None
        # save -> full multiplies by full/save; full -> save divides by it.
        ratio = (full / save) if self._column is False else (save / full)
        return round(burn * ratio, 3), laps, other

    def _burn_this_stint(self) -> list[tuple[int, float, bool, int]]:
        """The rows of the stint being driven now that are evidence about BURN.

        **No lap-time filter - a lap-time filter is a pace filter.** This was
        the pace population with `BURN_OUTLIER_FRACTION` applied, and a lap
        slowed by an off, a spin or a fight is not a lap that burned less:
        Bathurst, 14 Sep 2026, stint 2 ran 8.37, 8.52, 8.63 and 8.42 L with
        two of the four more than 4% off the stint's best, so the stint "had"
        two laps, never reached `STINT_BURN_LAPS`, and the race median of
        8.248 - mostly stint 1 - stood in for a stint burning 8.5. "Fuel good
        to the flag." was said three laps out, and lap 19 closed on 7.70 L
        with a lap to run at 8.4.

        What stays out is what is not a burn at all or is the app's own
        instruction: pit and out laps (a fill is not a burn; `note_lap` never
        admits them), lap one of a standing start, laps driven under the
        short-shift instruction (evidence about the instruction), and a lap
        that served a penalty - the crawl is in the burn as well as the time,
        and `_clean` has always dropped it; this did not.

        **And the beep column being driven now**, on the same grounds as
        everything else: a stint that changes column part way through is two
        burns 30% apart, and a median over both belongs to neither.
        """
        if not self._green:
            return []
        current = self._stint
        want = self._column
        return [row for row, stint, on in zip(self._green, self._green_stint,
                                              self._green_column)
                if stint == current and not row[2] and row[1] > 0
                and row[3] not in self._penalised
                and (want is None or on is want)]

    def stint_green_laps(self) -> int:
        """Laps behind this stint's burn - see `_burn_this_stint`."""
        return len(self._burn_this_stint())

    def stint_fuel_per_lap_l(self) -> float | None:
        """This stint's own green burn, or None until it has enough laps.

        The whole-race median is kept for anything that spans stints; the
        stint's figure is what the next laps will actually burn - the car is
        lighter, and the driver may have stopped saving.
        """
        burns = [used for _, used, _, _ in self._burn_this_stint()]
        if len(burns) < STINT_BURN_LAPS:
            return None
        return round(median(burns), 3)

    def stint_fuel_reference_load_l(self) -> float | None:
        """The mean fuel aboard across the laps `stint_fuel_per_lap_l` used."""
        rows = self._burn_this_stint()
        if len(rows) < STINT_BURN_LAPS:
            return None
        loads = []
        for row, load in zip(self._green, self._green_loads):
            if load is not None and row in rows:
                loads.append(load)
        if not loads:
            return None
        return round(sum(loads) / len(loads), 2)

    def stint_fuel_sd_l(self) -> float | None:
        """Lap-to-lap scatter on this stint's green burn, or None before
        `STINT_BURN_LAPS`. Never across a stint boundary - the step between
        stints is a change, not scatter."""
        burns = [used for _, used, _, _ in self._burn_this_stint()]
        if len(burns) < STINT_BURN_LAPS:
            return None
        return stdev(burns)

    def current_fuel_per_lap_l(self) -> float | None:
        """The burn to size the next laps on - `current_fuel_basis`'s figure."""
        return self.current_fuel_basis()[0]

    def current_fuel_basis(self) -> tuple[float | None, int, str]:
        """`(burn, laps behind it, what it is)` for the laps AHEAD.

        * **The stint's own** once it has `STINT_BURN_LAPS` laps
          (`FUEL_BASIS_STINT`).
        * **Before that, after a stop, the HIGHER of the race's and the
          stint's so far.** The previous stint's burn may not stand in
          silently for this one: at Bathurst it was 0.25 L a lap light, and a
          light burn is the direction that says "fuel good" about a tank that
          is short. The higher of the two can over-fill by a litre or so; the
          lower runs him dry. **Which of the two won is in the name** -
          `FUEL_BASIS_HIGHER_RACE` or `FUEL_BASIS_HIGHER_STINT` - because the
          laps returned beside the figure are that population's and the two
          are an order of magnitude apart. One name for both outcomes made a
          count of 9 and a count of 2 read as the same claim.
        * **The race's** in the first stint, or where the stint has nothing
          yet (`FUEL_BASIS_RACE`).

        And **before any of those**, where the beep column being driven has
        not yet shown `RACE_BURN_LAPS` laps of its own but the other one has:
        the other column converted by the plan's ratio (`FUEL_BASIS_COLUMN`),
        or the higher of that and what this column has shown so far
        (`FUEL_BASIS_COLUMN_HIGHER`). It goes first because it is the case
        where every figure below belongs to a burn 30% away from the one being
        driven - the moment George moves the beep, and the moment a stale
        number does the most damage.
        """
        stint = self.stint_fuel_per_lap_l()
        stint_laps = self.stint_green_laps()
        race = self.race_fuel_per_lap_l()
        race_laps = self.race_burn_laps()
        converted = (self.other_column_burn()
                     if race_laps < RACE_BURN_LAPS else None)
        if converted is not None:
            burn, laps, _on = converted
            # This column's own laps, however few, may not be silently
            # under-stated by a conversion - and whichever wins names itself
            # (rule 12).
            mine = stint if stint is not None else race
            if mine is not None and mine > burn:
                return (mine, stint_laps if stint is not None else race_laps,
                        FUEL_BASIS_COLUMN_HIGHER)
            return burn, laps, FUEL_BASIS_COLUMN
        if stint is not None:
            return stint, stint_laps, FUEL_BASIS_STINT
        if self._stint > 0 and stint_laps:
            so_far = round(median(used for _, used, _, _
                                  in self._burn_this_stint()), 3)
            if race is None or so_far > race:
                return so_far, stint_laps, FUEL_BASIS_HIGHER_STINT
            return race, race_laps, FUEL_BASIS_HIGHER_RACE
        return race, race_laps, FUEL_BASIS_RACE

    def current_fuel_reference_load_l(self) -> float | None:
        _burn, _laps, basis = self.current_fuel_basis()
        if basis in (FUEL_BASIS_COLUMN, FUEL_BASIS_COLUMN_HIGHER):
            # Measured on laps this column did not drive, or on too few of
            # its own to anchor: no load here, and rule 3 says so as None.
            return None
        if basis == FUEL_BASIS_STINT:
            return self.stint_fuel_reference_load_l()
        if basis == FUEL_BASIS_HIGHER_STINT:
            # A burn from one or two laps has no load worth anchoring to.
            # **Read off the basis, not off a value comparison.** This used
            # to ask whether `burn != race_fuel_per_lap_l()`, which is the
            # same question answered a second time and from a second place -
            # the basis already knows which population won (rule 12).
            return None
        return self.race_fuel_reference_load_l()

    def race_fuel_reference_load_l(self) -> float | None:
        """The mean fuel aboard across the laps `race_fuel_per_lap_l` came from.

        **Burn rises with what is in the tank**, so the median burn is only
        usable once the load it was taken at is known - see
        `strategy/fuel_model.py`. Early in a stint that median is measured on a
        heavy car and over-states the rest of the stint; sizing the fill off it
        puts litres in that come straight back out at the flag, and at the
        measured 1.0009 L/s each one is a second.

        None where no lap reported a tank level, and every fuel sum then falls
        back to `laps x burn` exactly as it did before.
        """
        clean = self._clean()
        if not clean or len(self._green_loads) != len(self._green):
            return None
        keep = set(id(row) for row in clean)
        loads = [load for row, load in zip(self._green, self._green_loads)
                 if id(row) in keep and load is not None]
        if not loads:
            return None
        return round(sum(loads) / len(loads), 3)

    def race_fuel_sd_l(self) -> float | None:
        """Lap-to-lap scatter on the green burn, **measured on this race**.

        What sizes the fill at the stop. None below `RACE_BURN_LAPS`, and
        never inherited from another race or another circuit for the same
        reason `sigma_ms` is not: a margin is only cheap if the number it is
        built on belongs to the car actually running.
        """
        clean = [used for _, used, _, _ in self._clean() if used > 0]
        if len(clean) < RACE_BURN_LAPS:
            return None
        return stdev(clean)

    # ------------------------------------------------------ on the plan?

    def burn_vs_plan(self) -> float | None:
        """Fraction over (positive) or under (negative) the planned burn.

        None where either side is unknown, and None until `RACE_BURN_LAPS`
        green laps exist: the decision this feeds turned on 1.80% at the
        measured race, and fewer laps than this cannot resolve it.
        """
        clean = [used for _, used, _, _ in self._clean() if used > 0]
        # Against the plan as the car is burning NOW: this stint's figure
        # once it has three clean laps, the race's before that.
        observed = self.current_fuel_per_lap_l()
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
                # **The count off the same expression as the median** (rule
                # 12). `len(clean)` is every green lap; `race_burn_laps()` is
                # the green laps that actually reported a burn, which is what
                # `race_fuel_per_lap_l` takes its median over. The two differ
                # by exactly the laps whose burn could not be read - three of
                # them on Bathurst Rd 8 - so the audit was quoting a sample
                # size larger than the sample.
                counted = self.race_burn_laps()
                said += f", ran {observed:.2f} over {counted} green laps"
                unread = len(clean) - counted
                if unread > 0:
                    said += (f" ({unread} more took fuel or reported no tank "
                             f"level and could not be differenced)")
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

    ### The burn, and why it is `None` rather than `0.0`

    **`max(0.0, start - end)` was rule 9 in its plainest form** and it was
    here until 20 Sep 2026. `LapInput` carries no `fuel_added_l`, so every lap
    with a fill in it differences to a large negative number and clamped to
    zero: at Bathurst Rd 8 that is laps 12 and 23 (the out laps carrying the
    fill), plus lap 1 whose stored `fuel_used` is itself a clamped zero from
    the grid fill. A lap that plainly burned eight litres came out of the
    rebuild as a lap that burned none, indistinguishable from a measurement.

    `None` says what is true: this lap's burn cannot be differenced from the
    two tank readings alone. `note_lap` files it as the population's existing
    "not evidence" sentinel and every burn figure already filters on
    `used > 0`, so no median moves - what changes is that the audit can now
    count the laps it actually used and say how many it could not read.
    """

    def __init__(self, lap) -> None:
        self.lap_num = lap.lap_num
        self.lap_time_ms = lap.lap_time_ms
        self.is_pit_lap = bool(getattr(lap, "is_pit_lap", False))
        self.is_out_lap = bool(getattr(lap, "is_out_lap", False))
        start, end = getattr(lap, "fuel_start", None), getattr(lap, "fuel_end",
                                                               None)
        used = None if start is None or end is None else start - end
        # Not clamped, and not "0 litres burned": a negative difference is a
        # lap that took fuel, and the litres it took are not on this row.
        self.fuel_used = used if used is not None and used > 0.0 else None
        self.fuel_used_why = (
            None if self.fuel_used is not None
            else "no tank reading at one end of the lap"
            if start is None or end is None
            else "fuel was added during the lap and LapInput carries no "
                 "fuel_added_l to difference against")
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

