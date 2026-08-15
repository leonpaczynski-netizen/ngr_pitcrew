"""Tyre wear — modelled, never measured.

**GT7 exposes no tyre wear channel in any packet format.** This module exists to
make that explicit rather than to hide it, so every figure it produces carries
its source and its confidence.

Three corroborating sources, in descending reliability:

1. **The driver's gauge reading.** Coarse, but the only number anchored to the
   game's own model. If it is present, it wins.
2. **Lap-time degradation** against a fresh-tyre reference.
3. **Tyre temperature trend** and front/rear asymmetry.

Readings are **per corner**, because the four wear at different rates and a
stint ends when the worst single tyre is done. An axle pair cannot express a
car eating one specific corner, which is the pattern open tuning without BoP
tends to produce and the one brake balance and setup actually act on.

Degradation is **piecewise, not linear** (CLAUDE.md §5.1): near-flat to ~50%
worn, progressive from ~50 to ~90%, then a cliff where the car is undriveable
rather than merely slow. So a rate is never reported without saying which phase
it was fitted in, and stint length is `0.85 / w` — deliberately short of the
cliff, because overshooting costs far more than undershooting.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, median

from pitcrew.analysis.runs import run_of, split_runs
from pitcrew.analysis.session import LapInput, counted_laps, green_lap_reference_ms
from pitcrew.store.tyres import get_by_code

# Stop the stint at 85% of the modelled tyre life. The cliff's onset is sharp
# and the cost is asymmetric, so the margin is deliberate and is stated in
# `modelBasis` on every export.
STINT_SAFETY_FACTOR = 0.85

# Fewer counted laps than this inside one run is not a trend. A slope from
# three points decides stint length, so it is refused rather than reported.
MIN_DEGRADATION_LAPS = 5

PHASE_FLAT = "flat"        # 0 - 50% worn
PHASE_LINEAR = "linear"    # 50 - 90%
PHASE_CLIFF = "cliff"      # > 90%


def phase_for(fraction_consumed: float | None) -> str | None:
    if fraction_consumed is None:
        return None
    if fraction_consumed < 0.5:
        return PHASE_FLAT
    if fraction_consumed <= 0.9:
        return PHASE_LINEAR
    return PHASE_CLIFF


CORNERS = ("fl", "fr", "rl", "rr")

# A gauge reading needs a starting point before it becomes a rate. Where the
# driver has declared the set fresh, there is one. Where he has not, assuming
# the set went on at the run's first lap is the only workable choice — and it
# is stated in the export rather than made silently.
CONFIDENCE_MEASURED = "measured"
CONFIDENCE_ASSUMED = "assumed"
CONFIDENCE_CONVERTED = "converted"

METHOD_GAUGE_DELTA = "two gauge readings inside one run"
METHOD_FRESH_DECLARED = (
    "one gauge reading, over a set the driver declared fresh")
METHOD_FRESH_OBSERVED = (
    "one gauge reading, over a set whose opening temperatures are those of a "
    "set as fitted")
METHOD_FRESH_AT_RUN_START = (
    "one gauge reading, assumed fresh at the run's first lap")


@dataclass(frozen=True)
class RunWear:
    """What one run says about wear, and what it had to assume to say it.

    Bounded by the run, never by the compound tag: three runs on the same
    compound are three sets unless the driver says otherwise, and pooling them
    divides one set's reading by three sets' laps. That is what reported a
    Racing Soft set consuming 17% a lap as 6.9%.
    """
    run_id: int
    compound: str | None
    first_lap: int
    last_lap: int
    reading: float | None
    reading_lap: int | None
    reading_corner: str | None
    # Every corner of the closing reading, in `CORNERS` order. Kept beside
    # the worst-corner scalar because a rate has to be taken corner against
    # corner, and `worst` at one lap and `worst` at another need not name the
    # same tyre - see `rate`.
    reading_by_corner: tuple[float | None, ...]
    start_reading: float | None
    start_reading_lap: int | None
    start_reading_by_corner: tuple[float | None, ...]
    tyres_fresh: bool | None
    # How that was established. The rate rests on it, so it travels with the
    # rate rather than being left in `runs` for the reader to join up.
    tyres_fresh_declared: bool | None
    degradation_ms_per_lap: float | None
    degradation_samples: int

    @property
    def _spans_laps(self) -> bool:
        return (self.start_reading_lap is not None
                and self.reading_lap is not None
                and self.reading_lap > self.start_reading_lap)

    @property
    def _shared_corners(self) -> tuple[int, ...]:
        """Positions in `CORNERS` the driver read at **both** ends of the run.

        A partial read is a designed input, not an accident: the gauge lets
        him clear a corner and the contract says an unread corner stays null.
        So the two readings routinely name different tyres, and only the
        corners present in both can be subtracted.
        """
        return tuple(index for index in range(len(CORNERS))
                     if self.start_reading_by_corner[index] is not None
                     and self.reading_by_corner[index] is not None)

    @property
    def _has_delta(self) -> bool:
        """Two readings, laps apart, sharing at least one corner."""
        return self._spans_laps and bool(self._shared_corners)

    @property
    def _delta_rate(self) -> float | None:
        """The fastest-wearing corner's own rate, corner against corner.

        **Never `max(later) - max(earlier)`.** Both ends are the worst corner
        of whatever the driver happened to read on that lap, so the
        subtraction can span two different tyres: lap 8 read all four with the
        front-left worst at 0.30 and lap 18 read only the rears with the
        right-rear at 0.45 gave 0.015 a lap - and a 56-lap stint, on a set the
        front-left had finished by lap 22.
        Even with four corners read at both ends the identity
        `max(later) - max(earlier) <= max(per-corner delta)` holds, so the
        old arithmetic could only ever understate the rate when the limiting
        corner changed identity - always toward a longer stint, which
        `CLAUDE.md` §5.1 calls the expensive direction.

        `None` where every shared corner read no higher than it did before.
        That is a gauge going backwards, which is a tyre change inside what
        the fuel channel called one run or a mistyped reading; either way
        there is no rate through it, and `unavailable_reason` says which.
        """
        gap = self.reading_lap - self.start_reading_lap
        worst = max((self.reading_by_corner[index]
                     - self.start_reading_by_corner[index]) / gap
                    for index in self._shared_corners)
        return round(worst, 5) if worst > 0 else None

    @property
    def rate(self) -> float | None:
        """Fraction of the worst corner consumed per lap, inside this run."""
        if self._has_delta:
            return self._delta_rate
        # Two readings that share no corner are not a delta at all. Falling
        # through here uses the later one against the run's first lap rather
        # than discarding a reading that is perfectly usable on its own.
        if self.reading is None or self.reading_lap is None:
            return None
        laps = self.reading_lap - self.first_lap + 1
        if laps < 1 or self.reading <= 0:
            return None
        return round(self.reading / laps, 5)

    @property
    def method(self) -> str | None:
        if self.rate is None:
            return None
        if self._has_delta:
            return METHOD_GAUGE_DELTA
        if self.tyres_fresh_declared is True:
            return METHOD_FRESH_DECLARED
        if self.tyres_fresh is True:
            return METHOD_FRESH_OBSERVED
        return METHOD_FRESH_AT_RUN_START

    @property
    def confidence(self) -> str | None:
        """`measured` only where nothing had to be assumed to get the rate.

        Two readings assume nothing, and the driver's own declaration that the
        set went on fresh is primary evidence. **`tyres_fresh` is neither.**
        It falls back to `fresh_by_temperature`, an app-side reading of an
        opening temperature band the app itself chose - and four of six Monza
        runs carried `confidence: measured` on it, which promoted the whole
        payload to `modelConfidence: measured`. Contract §6.1 and §8 make
        `measured` conditional on two readings or his declaration, and on
        nothing else.
        """
        if self.rate is None:
            return None
        if self._has_delta or self.tyres_fresh_declared is True:
            return CONFIDENCE_MEASURED
        return CONFIDENCE_ASSUMED

    @property
    def unavailable_reason(self) -> str | None:
        if self.rate is not None:
            return None
        if self.reading is None:
            return "no gauge reading was taken on this run"
        # Separated from the sentence below, which used to be given for this
        # case too - "the readings do not span any laps" about two readings
        # ten laps apart.
        if self._has_delta:
            shared = ", ".join(CORNERS[index] for index in self._shared_corners)
            return (f"the gauge read no higher at lap {self.reading_lap} than "
                    f"at lap {self.start_reading_lap} on {shared}, so there is "
                    f"no wear across this run to take a rate from")
        if self.reading <= 0:
            return (f"the gauge read {self.reading:.0%} consumed, which gives "
                    f"no rate to plan a stint against")
        return "the readings do not span any laps"

    def as_export(self) -> dict:
        payload: dict = {
            "runId": self.run_id,
            "compound": self.compound,
            "firstLap": self.first_lap,
            "lastLap": self.last_lap,
            "readingLap": self.reading_lap,
            "reading": self.reading,
            "readingCorner": self.reading_corner,
            "wearPerLap": self.rate,
            "method": self.method,
            "confidence": self.confidence,
            "source": "driver-gauge",
        }
        # Only where it really was assumed. Where the driver declared the set
        # fresh there is nothing to assume, and a field saying otherwise would
        # understate evidence he actually gave. The temperature path assumes
        # exactly as much as the silent one does - it is the app's own reading
        # of an opening band, not his word - so it says so too.
        if self.method in (METHOD_FRESH_AT_RUN_START, METHOD_FRESH_OBSERVED):
            payload["assumesFreshAtLap"] = self.first_lap
        if self.unavailable_reason:
            payload["wearPerLapUnavailable"] = self.unavailable_reason
        # The lap-time trend inside this run and nowhere else. Two runs on one
        # compound can trend opposite ways, and a single headline figure hides
        # that - which is worth more than the headline.
        payload["degradationMsPerLap"] = self.degradation_ms_per_lap
        payload["degradationSamples"] = self.degradation_samples
        return payload


def _by_corner(lap: LapInput | None) -> tuple[float | None, ...]:
    """One lap's gauge reading in `CORNERS` order, unread corners left null."""
    if lap is None:
        return (None,) * len(CORNERS)
    read = lap.wear_by_corner
    return tuple(read[corner] for corner in CORNERS)


def run_wear(laps: list[LapInput]) -> list[RunWear]:
    """One wear record per run, in order."""
    out = []
    for run in split_runs(laps):
        read = run.gauge_readings
        last = read[-1] if read else None
        first = read[0] if len(read) > 1 else None
        out.append(RunWear(
            run_id=run.id,
            compound=run.compound,
            first_lap=run.first_lap,
            last_lap=run.last_lap,
            reading=last.worst_wear if last else None,
            reading_lap=last.lap_num if last else None,
            reading_corner=last.worst_corner if last else None,
            reading_by_corner=_by_corner(last),
            start_reading=first.worst_wear if first else None,
            start_reading_lap=first.lap_num if first else None,
            start_reading_by_corner=_by_corner(first),
            tyres_fresh=run.tyres_fresh,
            tyres_fresh_declared=run.tyres_fresh_declared,
            degradation_ms_per_lap=_run_slope(run),
            degradation_samples=len(run.counted_laps),
        ))
    return out


def _run_slope(run) -> float | None:
    counted = run.counted_laps
    if len(counted) < MIN_DEGRADATION_LAPS:
        return None
    slope = trend_slope([(lap.lap_num, lap.lap_time_ms) for lap in counted])
    return None if slope is None else round(slope, 1)


def wear_rate_by_compound(laps: list[LapInput]) -> dict[str, dict]:
    """Fraction consumed per lap, per compound, from the driver's readings.

    A rate measured on one compound describes that compound and no other, so
    they are never pooled across compounds. Within a compound they are averaged
    across the runs that produced one, and **`stints` is how many runs were
    actually run on that compound** — not how many produced a number. A
    compound run three times and readable once is a thinner claim than one run
    once and read once, and the pair of counts is what says so.
    """
    records = run_wear(laps)
    by_compound: dict[str, list[RunWear]] = {}
    for record in records:
        if record.compound:
            by_compound.setdefault(record.compound, []).append(record)

    out = {}
    for code, runs in by_compound.items():
        rated = [run for run in runs if run.rate is not None]
        measured = bool(rated) and all(
            run.confidence == CONFIDENCE_MEASURED for run in rated)
        entry = {
            # The full name beside the code, because `meta` speaks in full
            # names and a section keyed by code cannot otherwise be checked
            # against what the session recorded.
            "compound": _compound_name(code),
            "wearPerLap": (round(mean([run.rate for run in rated]), 5)
                           if rated else None),
            "stints": len(runs),
            "stintsMeasured": len(rated),
            "runIds": [run.run_id for run in runs],
            "source": "driver-gauge",
            "confidence": CONFIDENCE_MEASURED if measured else CONFIDENCE_ASSUMED,
        }
        if not rated:
            entry["wearPerLapUnavailable"] = (
                "no run on this compound carried a usable gauge reading")
        out[code] = entry
    return out


def _compound_name(code: str) -> str:
    compound = get_by_code(code)
    return compound.name if compound else code


def gauge_readings(laps: list[LapInput]) -> list[dict]:
    """The driver's own gauge readings, per corner, in lap order.

    A corner he did not read is null and stays null. `worst` and `worstCorner`
    are carried alongside so the consumer never has to re-derive which tyre is
    the limiting one, and never has to guess whether a missing corner was
    fresh or simply unread.

    **Every entry names its run.** Without that, a reading at lap 21 and the
    same reading at lap 36 cannot be told apart from one set read twice, and
    the reader cannot say whether the last fifteen laps were a fresh set or the
    tail of a twenty-six lap one. Those are different findings.
    """
    runs = split_runs(laps)
    out = []
    for lap in laps:
        by_corner = lap.wear_by_corner
        if all(value is None for value in by_corner.values()):
            continue
        out.append({
            "lap": lap.lap_num,
            "runId": run_of(runs, lap.lap_num),
            **by_corner,
            "worst": lap.worst_wear,
            "worstCorner": lap.worst_corner,
            "source": "driver-gauge",
        })
    return out


def pinned_gauge_note(laps: list[LapInput]) -> str | None:
    """Where the worst corner has not moved across laps **on one set**.

    Two readings of the same set, laps apart and identical, mean the gauge has
    saturated or the second entry is a copy of the first. Either way no rate
    can be taken through it.

    **Within one run only.** Two equal readings on two different sets are two
    sets that happened to come off equally worn, which is a coincidence and not
    a finding - and reporting it as one is what run identity was built to stop.
    Before `runs` existed the two cases were indistinguishable, which is
    exactly what the 11 Aug session's 84% at lap 21 and 84% at lap 36 was.
    """
    for run in split_runs(laps):
        readings = [(lap.lap_num, lap.worst_wear) for lap in run.laps
                    if lap.worst_wear is not None]
        for (first_lap, first), (second_lap, second) in zip(readings,
                                                            readings[1:]):
            if first != second or not first:
                continue
            return (f"The worst corner read {first:.0%} consumed at lap "
                    f"{first_lap} and the same at lap {second_lap}, both on "
                    f"run {run.id} and so on one set. A gauge that has not "
                    f"moved in {second_lap - first_lap} laps of running has "
                    f"saturated, so no rate is taken through it.")
    return None


def headline_wear(laps: list[LapInput], *,
                  compound: str | None = None) -> dict:
    """The one rate a stint is planned against, and which set it came from.

    Uses the **worst single corner**, not the worst axle and certainly not an
    average: the stint ends when one tyre is done, and three healthy corners do
    not extend the life of the fourth. On a car that eats its front-left — the
    common no-BoP open-tuning pattern — an axle figure understates the rate and
    a plan built on it overshoots the cliff, which §5.1 says costs far more
    than undershooting.

    Measured inside one run, never across a refuel, and never against the lap
    number: a reading of 60% at lap 20 is a very different rate depending on
    whether the tyres went on at lap 1 or at lap 12.

    **It names its compound or it refuses.** This was `rates[-1]` — whichever
    run happened to be last, unfiltered by compound and with no count of what
    it discarded. On the 91-lap Monza set that exported `modelledStintLaps: 26`
    off a Racing Hard rate while the Racing Soft rate says four laps: a driver
    planning 26 who fits softs runs six times past the cliff. A rate measured
    on one compound describes that compound and no other, so where two of them
    both produced one there is no headline to give — `byCompound` is the
    section that answers the question and this one says so.

    Where a compound is named the figure is the mean of that compound's rated
    runs, which is `wear_rate_by_compound`'s own arithmetic: one tyre must not
    have two figures inside one payload computed two different ways.

    Where the laps carry **no** compound tag at all there is nothing to name,
    and the runs are still separate sets. The latest run that produced a rate
    is the freshest evidence about the car as it is now — the same reasoning
    `analysis/recency` applies to pace — so that one is used and it is named.

    Always returns a record. `wearPerLap` is None with `unavailable` saying
    why: this figure drives every stint recommendation and must never be
    invented.
    """
    records = run_wear(laps)
    rated = [record for record in records if record.rate]
    blank = {"wearPerLap": None, "compound": None, "runIds": [],
             "runsMeasured": len(rated), "runs": len(records),
             "source": "driver-gauge", "unavailable": None}

    if not rated:
        return {**blank,
                "unavailable": "no run carried a usable gauge reading"}

    if compound is not None:
        on_compound = [record for record in rated
                       if record.compound == compound]
        if not on_compound:
            return {**blank, "unavailable": (
                f"no run on {compound} carried a usable gauge reading, and a "
                f"rate from another compound does not describe it")}
        return _headline(on_compound, compound, blank)

    tagged = {record.compound for record in rated}
    if len(tagged) > 1:
        named = sorted(code for code in tagged if code)
        parts = named + (["untagged runs"] if None in tagged else [])
        return {**blank,
                "runIds": [record.run_id for record in rated],
                "unavailable": (
                    f"{' and '.join(parts)} each produced a rate and they are "
                    f"not one set of tyres, so no single figure heads this "
                    f"section - see byCompound, and name the compound the "
                    f"plan is built on")}

    code = tagged.pop()
    if code is None:
        return _headline([rated[-1]], None, blank)
    return _headline(rated, code, blank)


def _headline(used: list[RunWear], compound: str | None, blank: dict) -> dict:
    return {**blank,
            "wearPerLap": round(mean([record.rate for record in used]), 5),
            "compound": compound,
            "runIds": [record.run_id for record in used]}


def wear_per_lap(laps: list[LapInput], *,
                 compound: str | None = None) -> float | None:
    """`headline_wear`'s rate alone, for callers that want the number."""
    return headline_wear(laps, compound=compound)["wearPerLap"]


def axle_bias(laps: list[LapInput]) -> dict | None:
    """Which end, and which corner, is going first.

    GT7 offers no strategy answer to axle-asymmetric wear - there are no
    partial tyre changes and no split compounds (§5.4) - so this exists to be
    reported rather than optimised against. It is what brake balance and setup
    act on, and it is the finding the driver's own account is checked against.
    """
    latest = None
    for lap in laps:
        if any(value is not None for value in lap.wear_by_corner.values()):
            latest = lap
    if latest is None:
        return None

    by_corner = latest.wear_by_corner
    fronts = [v for k, v in by_corner.items() if k.startswith("f") and v is not None]
    rears = [v for k, v in by_corner.items() if k.startswith("r") and v is not None]
    lefts = [v for k, v in by_corner.items() if k.endswith("l") and v is not None]
    rights = [v for k, v in by_corner.items() if k.endswith("r") and v is not None]

    return {
        "atLap": latest.lap_num,
        "worstCorner": latest.worst_corner,
        "worst": latest.worst_wear,
        # Null rather than 0 where an end was not read at all: a zero here
        # would read as a measured, perfectly balanced car.
        "frontMinusRear": (round(mean(fronts) - mean(rears), 3)
                           if fronts and rears else None),
        "leftMinusRight": (round(mean(lefts) - mean(rights), 3)
                           if lefts and rights else None),
        "source": "driver-gauge",
    }


def modelled_stint_laps(laps: list[LapInput], *,
                        compound: str | None = None) -> int | None:
    per_lap = wear_per_lap(laps, compound=compound)
    if not per_lap:
        return None
    return int(STINT_SAFETY_FACTOR / per_lap)


def degradation(laps: list[LapInput]) -> dict | None:
    """Lap-time drift, fitted inside one run and named.

    **Never fitted across a refuel.** A stint starts on a full tank and ends
    near empty; fitting straight through several of them turns the sawtooth
    into a rising trend and reports it as tyre degradation. On the 11 Aug Monza
    session that produced +72 ms a lap on a car that was in fact getting
    faster.

    The fit is the longest clean run in the session, least squares over its
    counted laps. Fuel load is **not** netted off: a full-to-empty tank is
    worth roughly +0.3 s a lap on its own, comfortably more than the tyre
    signal it would be netted against, and the coefficient that would do the
    netting is itself an open measurement. So the raw slope goes out with the
    fuel burned over the same window, and the reader nets it off with a figure
    they can state — rather than the app doing it silently with one it cannot.
    """
    best = _longest_clean_run(laps)
    if best is None:
        return None
    run, counted = best

    slope = trend_slope([(lap.lap_num, lap.lap_time_ms) for lap in counted])
    if slope is None:
        return None

    fuel_delta = round(counted[0].fuel_start - counted[-1].fuel_end, 2)
    payload = {
        "degradationMsPerLap": round(slope, 1),
        "fittedRunId": run.id,
        "fittedOverLaps": [counted[0].lap_num, counted[-1].lap_num],
        "samples": len(counted),
        "fuelDeltaL": fuel_delta,
        "fuelNetted": False,
        "fuelNettedNote": (
            "Raw slope. Fuel load is not netted off - a full tank is worth "
            "roughly 0.003 s/L/lap, which over this window is larger than the "
            "tyre signal, and that coefficient is derived rather than "
            "measured. Net it off with a figure you can state."),
    }
    disagreement = _runs_disagree(laps, run.id)
    if disagreement:
        payload["runsDisagree"] = disagreement
    return payload


def _runs_disagree(laps: list[LapInput], fitted_run_id: int) -> str | None:
    """Where other runs trend the other way from the one that was fitted.

    A headline slope taken from the longest run reads as the session's answer.
    Where a second run of the same length trends the opposite way, the honest
    finding is that the session does not have one - and the reader has to be
    told rather than handed whichever run happened to be a lap longer.
    """
    slopes = [(record.run_id, record.degradation_ms_per_lap)
              for record in run_wear(laps)
              if record.degradation_ms_per_lap is not None]
    if len(slopes) < 2:
        return None
    fitted = next((value for run_id, value in slopes
                   if run_id == fitted_run_id), None)
    if fitted is None:
        return None
    against = [f"run {run_id} at {value:+.0f}" for run_id, value in slopes
               if run_id != fitted_run_id
               and (value > 0) != (fitted > 0) and value != 0]
    if not against:
        return None
    return (f"The fitted run trends {fitted:+.0f} ms/lap but "
            f"{', '.join(against)} ms/lap trends the other way. The session "
            f"does not agree with itself on degradation; see byRun before "
            f"planning a stint on this figure.")


def degradation_ms_per_lap(laps: list[LapInput]) -> float | None:
    """The slope alone, for callers that want the number and nothing else."""
    fitted = degradation(laps)
    return fitted["degradationMsPerLap"] if fitted else None


def _longest_clean_run(laps: list[LapInput]):
    """The run with the most counted laps, and those laps.

    None when no run is long enough to fit: three points spanning a refuel are
    not a trend, and a number produced from them would be believed.
    """
    best = None
    for run in split_runs(laps):
        counted = run.counted_laps
        if len(counted) < MIN_DEGRADATION_LAPS:
            continue
        if best is None or len(counted) > len(best[1]):
            best = (run, counted)
    return best


def trend_slope(points: list[tuple[int, int]]) -> float | None:
    """Slope of lap time against lap number, ms per lap. Theil-Sen.

    The median of every pairwise slope, not least squares. A practice run
    contains incident laps the driver did not think to strike, and least
    squares gives each of them full weight: on the 11 Aug Monza session one
    un-struck lap five seconds off the pace moved the fitted slope by 90 ms a
    lap and took the sign with it. A stint length decided on that is decided on
    one moment of the session.

    The median of pairwise slopes survives roughly a quarter of the laps being
    junk, needs no threshold to be chosen and defended, and costs nothing at
    these sample sizes.
    """
    if len(points) < 2:
        return None
    slopes = [(y2 - y1) / (x2 - x1)
              for index, (x1, y1) in enumerate(points)
              for x2, y2 in points[index + 1:]
              if x2 != x1]
    return median(slopes) if slopes else None


def _front_rear_per_lap(laps: list[LapInput]) -> list[tuple[int, float, float]]:
    """Mean front and mean rear temperature per lap, for laps carrying frames."""
    out = []
    for lap in laps:
        if not lap.frames:
            continue
        fronts, rears = [], []
        for frame in lap.frames:
            for wheel, bucket in (("fl", fronts), ("fr", fronts),
                                  ("rl", rears), ("rr", rears)):
                value = frame.get(f"temp_{wheel}")
                if value is not None:
                    bucket.append(value)
        if fronts and rears:
            out.append((lap.lap_num, mean(fronts), mean(rears)))
    return out


def temperature_trend(laps: list[LapInput]) -> dict | None:
    """Front/rear asymmetry and front-temperature drift, **inside one run**.

    Contract §6.1's rule applies here exactly as it applies to lap time:
    nothing may be fitted across a refuel. This used to be fitted over the
    whole session - on the Monza set that was 74 laps spanning eight runs,
    three compounds and eight sets of tyres, reported as one number about the
    tyre. So both figures come from the longest clean run and `samples` is
    that run's lap count.

    The trend is Theil-Sen, the same estimator `degradation` uses. It replaced
    a half-mean difference that divided the gap between two half-centroids by
    the **full** span of the window - the centroids are only half a span
    apart, so every figure came out at about half the truth: ten laps rising
    exactly 1.0 C a lap were reported as 0.56.

    Where no run is long enough to fit, the asymmetry is still worth having -
    it is a standing property of the car rather than a trend - so it is taken
    over every counted lap carrying the channel and `trendCPerLap` is null.
    """
    best = _longest_clean_run(laps)
    inside = _front_rear_per_lap(best[1]) if best else []
    if len(inside) >= MIN_DEGRADATION_LAPS:
        slope = trend_slope([(lap_num, front) for lap_num, front, _ in inside])
        return {
            "frontRearAsymmetryC": round(
                mean([front - rear for _, front, rear in inside]), 1),
            "trendCPerLap": None if slope is None else round(slope, 2),
            "samples": len(inside),
            "source": "tyre-temp-trend",
            "confidence": "low",
        }

    per_lap = _front_rear_per_lap(counted_laps(laps))
    if not per_lap:
        return None
    return {
        "frontRearAsymmetryC": round(
            mean([front - rear for _, front, rear in per_lap]), 1),
        "trendCPerLap": None,
        "samples": len(per_lap),
        "source": "tyre-temp-trend",
        "confidence": "low",
    }


# Where a section-level confidence sits above per-field ones, it has to be the
# weakest of them or it overrides them. Ranked so the roll-up can be computed
# rather than declared.
_CONFIDENCE_RANK = {
    "low": 0,
    CONFIDENCE_ASSUMED: 0,
    CONFIDENCE_CONVERTED: 1,
    "medium": 1,
    CONFIDENCE_MEASURED: 2,
    "high": 2,
}
_RANK_TO_CONFIDENCE = {0: CONFIDENCE_ASSUMED,
                       1: CONFIDENCE_CONVERTED,
                       2: CONFIDENCE_MEASURED}


def roll_up_confidence(constituents: list[tuple[str, str | None]]) -> tuple[str, str]:
    """The weakest confidence beneath, and the sentence that shows the working.

    A section-level `measured` sitting over a fabricated `byCompound`, a
    wrong-signed `byLapTime` marked `low` and a pinned `byDriverGauge` is not a
    summary, it is an override — and it defeats the point of the per-field tags
    it sits above. So it is computed from them, and it names them.
    """
    known = [(name, value) for name, value in constituents
             if value in _CONFIDENCE_RANK]
    if not known:
        return CONFIDENCE_ASSUMED, "nothing beneath carries a confidence"
    weakest = min(_CONFIDENCE_RANK[value] for _, value in known)
    basis = ", ".join(f"{name} ({value})" for name, value in known)
    return _RANK_TO_CONFIDENCE[weakest], f"weakest of {basis}"


def wear_export(laps: list[LapInput], *,
                calibrated_at_race_multiplier: bool | None = None,
                race_multiplier: str | None = None,
                compound: str | None = None) -> dict:
    """The `wear` object.

    `calibrated_at_race_multiplier` is False when the numbers came from a run at
    a different tyre-wear multiplier, True where the caller can show they did
    not, and **None where nothing on record can say** - which is the default,
    because the multiplier is an event-level declaration and no session records
    the one it actually ran at. It used to default to True, so every export
    ever made asserted that its wear rate was taken at the race's setting.
    Multiplier linearity is assumed and has never been demonstrated, so a
    converted figure is labelled `converted` and must never be presented as
    measured.

    `compound` is the tyre the plan is being built on. Naming it picks the
    rate out of `byCompound` rather than leaving `headline_wear` to refuse a
    session that ran three of them.
    """
    readings = gauge_readings(laps)
    headline = headline_wear(laps, compound=compound)
    per_lap = headline["wearPerLap"]
    stint_laps = modelled_stint_laps(laps, compound=compound)
    by_run = [record.as_export() for record in run_wear(laps)]

    payload: dict = {
        "channelAvailable": False,
        "byDriverGauge": readings,
        "byRun": by_run,
        "modelledStintLaps": stint_laps,
        # Multiplier linearity has never been demonstrated, so the multiplier
        # the rate was measured at travels with the rate. Without it a figure
        # taken at 8x reads as one taken at the race setting.
        "wearMeasuredAtRaceMultiplier": calibrated_at_race_multiplier,
        "wearMultiplier": race_multiplier,
    }
    if stint_laps is not None:
        # Which rubber the stint length is for. Without it 26 laps off a
        # Racing Hard rate reads as 26 laps on whatever is fitted.
        payload["modelledStintCompound"] = headline["compound"]

    bias = axle_bias(laps)
    if bias is not None:
        payload["byCorner"] = bias

    per_compound = wear_rate_by_compound(laps)
    if per_compound:
        payload["byCompound"] = per_compound

    reference = green_lap_reference_ms(laps)
    fitted = degradation(laps)
    if fitted is not None:
        final_fraction = _fraction_at_fit_end(
            readings, fitted["fittedRunId"], fitted["fittedOverLaps"])
        payload["byLapTime"] = {
            "refLapMs": reference,
            **fitted,
            "phase": phase_for(final_fraction),
            "estimatedFractionAtEnd": final_fraction,
            # Named, because the fraction is the driver's gauge and everything
            # else in this block is the lap-time model. A `source` covering
            # both would put his reading under a model that did not produce it.
            "estimatedFractionSource": (
                "driver-gauge" if final_fraction is not None else None),
            "source": "lap-time-model",
            "confidence": "low",
        }
    else:
        payload["byLapTime"] = {
            "refLapMs": reference,
            "degradationMsPerLap": None,
            "degradationUnavailable": (
                f"no single run has {MIN_DEGRADATION_LAPS} counted laps, and a "
                f"slope fitted across a refuel measures the fuel load rather "
                f"than the tyre"),
            "source": "lap-time-model",
            "confidence": "low",
        }

    temps = temperature_trend(laps)
    if temps is not None:
        payload["byTemp"] = temps

    pinned = pinned_gauge_note(laps)
    if pinned:
        payload["gaugePinned"] = pinned

    payload["modelBasis"] = _model_basis(headline,
                                         calibrated_at_race_multiplier)
    payload["modelConfidence"], payload["modelConfidenceBasis"] = \
        _model_confidence(payload, per_lap, calibrated_at_race_multiplier)
    return payload


def _fraction_at_fit_end(readings: list[dict], run_id: int | None,
                         window: list[int]) -> float | None:
    """The gauge reading that belongs to the run the slope was fitted on.

    It used to be `readings[-1]` - the driver's last reading from anywhere in
    the session, published beside a slope fitted on a different run under
    `source: "lap-time-model"`. Two runs are two sets, and how worn one of
    them was says nothing about the phase the other was fitted in.
    """
    inside = [entry for entry in readings
              if entry.get("runId") == run_id
              and window[0] <= entry["lap"] <= window[1]]
    return inside[-1]["worst"] if inside else None


def _model_basis(headline: dict, calibrated: bool | None) -> str:
    """`0.85 / w`, and which set of tyres `w` actually came from.

    The compound is in the sentence because the number is worthless without
    it: `modelledStintLaps: 26` off a Racing Hard rate is six times the Racing
    Soft answer from the same session, and the payload used to name neither.
    """
    if headline["wearPerLap"] is None:
        return f"no stint length: {headline['unavailable']}"

    runs = ", ".join(str(run_id) for run_id in headline["runIds"])
    whose = (f"{headline['compound']} over run{'s' if len(headline['runIds']) > 1 else ''} {runs}"
             if headline["compound"]
             else f"run {runs}, which carries no compound tag")
    counted = (f"{len(headline['runIds'])} of {headline['runs']} runs, "
               f"{headline['runsMeasured']} of which produced a rate")
    multiplier = {
        True: "at this multiplier",
        False: ("scaled from a different multiplier [ASSUMED - multiplier "
                "linearity is not demonstrated]"),
        None: ("at a multiplier that is not on record for the session it was "
               "measured in"),
    }[calibrated]
    return (f"{STINT_SAFETY_FACTOR} / w, w from the driver's gauge on "
            f"{whose} ({counted}), {multiplier}")


def _model_confidence(payload: dict, per_lap: float | None,
                      calibrated: bool | None) -> tuple[str, str]:
    """Computed, never declared — the weakest of everything beneath it."""
    if per_lap is None:
        return CONFIDENCE_ASSUMED, "no gauge reading, so nothing is measured"

    constituents: list[tuple[str, str | None]] = []
    for code, entry in (payload.get("byCompound") or {}).items():
        constituents.append((f"byCompound.{code}", entry.get("confidence")))
    for record in payload.get("byRun") or []:
        if record.get("confidence"):
            constituents.append((f"byRun[{record['runId']}]",
                                 record["confidence"]))
    # `None` is not `False`. A rate scaled from another multiplier is
    # `converted`; a rate whose multiplier is simply not on record has not
    # been converted at all, and `wearMeasuredAtRaceMultiplier` is the field
    # that carries that gap rather than this one.
    if calibrated is False:
        constituents.append(("multiplier conversion", CONFIDENCE_CONVERTED))
    if payload.get("gaugePinned"):
        constituents.append(("byDriverGauge", "low"))

    confidence, basis = roll_up_confidence(constituents)
    # Named, so the roll-up cannot be read as covering the corroborating
    # sources it does not cover. They are low by nature - a lap-time slope and
    # a temperature trend never rise above corroboration - and rolling them in
    # would peg this field to `assumed` on every export ever made, which says
    # nothing about whether w itself was measured.
    corroborating = [name for name in ("byLapTime", "byTemp")
                     if isinstance(payload.get(name), dict)]
    if corroborating:
        basis += (f"; {' and '.join(corroborating)} corroborate rather than "
                  f"feed this and carry their own confidence")
    return confidence, basis
