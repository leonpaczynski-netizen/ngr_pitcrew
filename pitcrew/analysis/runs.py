"""Run identity — which tank a lap was run on, and which set of tyres.

Nothing may be fitted across a refuel. A stint starts on a full tank and ends
near empty, so a lap-time series that spans a stop is a sawtooth: the car gets
heavier, then abruptly light again. Fitted straight through, that sawtooth
reads as a rising trend and gets reported as tyre degradation — which is how a
car that was *getting faster* came to be exported as losing 72 ms a lap.

**A tank and a set of tyres are different objects and this module keeps them
apart.** A refuel is visible in the feed: the tank goes up between one lap and
the next. A tyre change is not visible at all — GT7 broadcasts no wear channel
and no stop event, so whether the tyres came off at that stop is something only
the driver knows. So:

* a **run** is a fuel window, derived from the stream and therefore certain;
* whether the tyres were fresh at the start of one is `None` until the driver
  says. Never `False` — `False` is a positive claim that the set carried over,
  and the app has no evidence for it.

Every wear rate is computed inside one run. Where the driver has not declared
the tyres fresh, the rate still needs a starting point, and assuming the set
went on at the run's first lap is the only workable one — so the figure carries
`assumesFreshAtLap` and drops to `assumed` confidence rather than passing as
measured.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from statistics import median

from pitcrew.analysis import thresholds
from pitcrew.analysis.session import LapInput

# The tank rising by more than this between the end of one lap and the start of
# the next is a refuel. Well above float noise on a channel reported in litres,
# well below the smallest splash worth taking.
REFUEL_STEP_L = 0.5

# A lap burning less than this fraction of the session's typical burn did not
# go round the circuit — the lap boundary landed inside a pit or garage
# transition. Half is deliberately generous: the leanest fuel map still burns
# about half of what the richest does, so a real lap cannot fall under it.
FUEL_IMPLAUSIBLE_FRACTION = 0.5

REASON_FUEL_IMPLAUSIBLE = "fuel-implausible"
REASON_OUT_LAP = "out-lap"
REASON_IN_LAP = "in-lap"
REASON_MANUAL = "manual"

SOURCE_AUTO = "auto"
SOURCE_DRIVER = "driver"


@dataclass(frozen=True)
class Run:
    """One tank, from the lap after it was filled to the lap it ran dry."""
    id: int
    laps: tuple[LapInput, ...]
    refuelled_before: bool
    # What the stop *before* this run did to the tyres, read off the stream.
    # `None` where no stop was captured there, which is also the case for the
    # first run of a session. It lives on the Run rather than on its first lap
    # because the evidence is in the lap before it — the stop happens on the
    # in-lap, and the set it fitted is the set this run goes out on.
    tyres_changed_before: bool | None = None

    @property
    def first_lap(self) -> int:
        return self.laps[0].lap_num

    @property
    def last_lap(self) -> int:
        return self.laps[-1].lap_num

    @property
    def lap_count(self) -> int:
        return len(self.laps)

    @property
    def fuel_start_l(self) -> float:
        return self.laps[0].fuel_start

    @property
    def fuel_end_l(self) -> float:
        return self.laps[-1].fuel_end

    @property
    def fuel_delta_l(self) -> float:
        return round(self.fuel_start_l - self.fuel_end_l, 2)

    @property
    def compound(self) -> str | None:
        """The compound tagged on this run's laps, or None if untagged.

        None rather than a vote when the laps disagree: a run tagged two ways
        is a data-entry question, and picking the more common tag would answer
        it silently.
        """
        tagged = {lap.compound for lap in self.laps if lap.compound}
        return tagged.pop() if len(tagged) == 1 else None

    @property
    def tyres_fresh_declared(self) -> bool | None:
        """What the driver said on the rack. Primary evidence, and it wins."""
        return self.laps[0].tyres_fresh

    @property
    def tyres_fresh_observed(self) -> bool | None:
        """What the stream says. Corroboration, never more.

        Two sources, and the stronger one first. **The stop itself**: all four
        corners stepping to one temperature in a single frame is GT7 fitting a
        set, and it is conclusive. **The opening temperatures**, otherwise —
        which is all there is for a run that began in the garage, and which
        cannot read a run that left the box already rolling. The post-stop
        out-lap is exactly that case: it starts at pit exit at speed, so no
        frame of it is a reading of the set as fitted, and the temperatures
        alone will always say "cannot tell" about the one moment we most want
        to know about.
        """
        if self.tyres_changed_before is not None:
            return self.tyres_changed_before
        return fresh_by_temperature(self.laps[0])

    @property
    def tyres_fresh(self) -> bool | None:
        """Whether the set went on at this run's first lap.

        **Never inferred from the refuel.** GT7 lets you take fuel without
        taking tyres, and inferring `True` from a stop would turn every fuel
        stop into a fresh set and halve every wear rate spanning one.

        It is inferred from the *temperature*, which is a different thing: GT7
        fits every set at one fixed temperature on all four corners, so a run
        that opens there, stationary and even, is a run that went out on new
        rubber. The driver's own declaration outranks it either way - his
        report is primary evidence and this is corroboration.
        """
        declared = self.tyres_fresh_declared
        return self.tyres_fresh_observed if declared is None else declared

    @property
    def tyres_fresh_source(self) -> str:
        if self.tyres_fresh_declared is not None:
            return "driver-declared at the run's first lap"
        if self.tyres_changed_before is True:
            return ("derived: at the stop before this run all four corners "
                    "stepped to one temperature in a single frame, which is "
                    "GT7 fitting a set")
        if self.tyres_changed_before is False:
            return ("derived: a stop was captured before this run and the "
                    "temperatures did not step, so the set stayed on")
        if self.tyres_fresh_observed is True:
            return (f"derived: all four corners at GT7's fitting temperature "
                    f"({thresholds.FRESH_TYRE_TEMP_C:.0f} C) with the car "
                    f"stationary")
        if self.tyres_fresh_observed is False:
            return ("derived: the opening temperatures are not those of a set "
                    "as fitted")
        return ("not declared, and the opening temperatures cannot tell - the "
                "feed carries no tyre-change event")

    @property
    def tyres_fresh_disagreement(self) -> str | None:
        """Where the driver and the temperatures say different things.

        Surfaced, never averaged and never resolved. The driver's report is
        primary and stands; that the stream disagrees with it is the finding,
        and it is worth more than either statement on its own.
        """
        declared = self.tyres_fresh_declared
        observed = self.tyres_fresh_observed
        if declared is None or observed is None or declared == observed:
            return None
        if declared:
            return (f"Declared a fresh set, but lap {self.first_lap} opens at "
                    f"{_opening_temperature(self.laps[0]):.1f} C across the "
                    f"four corners, which is not a set as fitted. Either the "
                    f"declaration is on the wrong lap or the set was used.")
        return (f"Declared as carried over, but lap {self.first_lap} opens at "
                f"GT7's fitting temperature on all four corners, which is what "
                f"a new set reads. The declaration stands; the stream "
                f"disagrees with it.")

    @property
    def counted_laps(self) -> list[LapInput]:
        return [lap for lap in self.laps if lap.counted]

    @property
    def gauge_readings(self) -> list[LapInput]:
        return [lap for lap in self.laps if lap.worst_wear is not None]

    def as_export(self) -> dict:
        payload = {
            "id": self.id,
            "firstLap": self.first_lap,
            "lastLap": self.last_lap,
            "laps": self.lap_count,
            "lapsCounted": len(self.counted_laps),
            "fuelStartL": round(self.fuel_start_l, 2),
            "fuelEndL": round(self.fuel_end_l, 2),
            "fuelDeltaL": self.fuel_delta_l,
            "refuelledBefore": self.refuelled_before,
            "compound": self.compound,
            "tyresFresh": self.tyres_fresh,
            "tyresFreshSource": self.tyres_fresh_source,
            "tyresFreshDeclared": self.tyres_fresh_declared,
            "tyresFreshObserved": self.tyres_fresh_observed,
            "tyresChangedAtStop": self.tyres_changed_before,
        }
        disagreement = self.tyres_fresh_disagreement
        if disagreement:
            payload["tyresFreshDisagreement"] = disagreement
        return payload


def _opening_frame(lap: LapInput) -> dict | None:
    """The first frame of a lap with the car still stationary.

    A set as fitted has to be read before it turns a wheel: one corner of the
    circuit and the fronts are already ahead of the rears.
    """
    for frame in lap.frames or ():
        speed = frame.get("speed_kph")
        if speed is None or speed > thresholds.FRESH_TYRE_MAX_SPEED_KPH:
            return None
        if all(frame.get(f"temp_{corner}") is not None
               for corner in ("fl", "fr", "rl", "rr")):
            return frame
    return None


def _opening_temperature(lap: LapInput) -> float:
    frame = _opening_frame(lap)
    if frame is None:
        return float("nan")
    return max(frame[f"temp_{corner}"] for corner in ("fl", "fr", "rl", "rr"))


def fresh_by_temperature(lap: LapInput) -> bool | None:
    """Did this lap go out on a set as GT7 fits it?

    **GT7 fits a set with all four corners on one temperature** - somewhere
    between 60 and 70 C depending on the hour, not at one fixed figure; see
    `thresholds.FRESH_TYRE_TEMP_C` for the correction and the laps behind it.
    From there a stationary set only cools, so a fresh one reads inside that
    band or just under it with the four corners equal.

    This is the **fallback**. Where the stop itself was captured, the moment
    of fitting is a one-frame step in the stream and `Run.tyres_fresh` uses
    that instead - it is conclusive where this is inferential.

    The **even** reading is what does the work, not the absolute value. A set
    that has turned a wheel picks up corner-to-corner asymmetry inside one lap
    and keeps it, so a spread is enough on its own to say the set is not new.

    `None`, not `False`, in the two cases where the reading cannot tell:

    * no stationary frame carrying all four corners - he was already rolling
      when the recording picked him up, and a set already working reads like a
      used one whether it is or not;
    * an even reading that has cooled past the allowance, which a fresh set
      left waiting and a used set left longer both eventually do.
    """
    frame = _opening_frame(lap)
    if frame is None:
        return None

    corners = [frame[f"temp_{corner}"] for corner in ("fl", "fr", "rl", "rr")]
    if max(corners) - min(corners) > thresholds.FRESH_TYRE_SPREAD_C:
        return False
    hottest = max(corners)
    if hottest > thresholds.FRESH_TYRE_TEMP_C + thresholds.FRESH_TYRE_SPREAD_C:
        return False
    if hottest < (thresholds.FRESH_TYRE_TEMP_MIN_C
                  - thresholds.FRESH_TYRE_COOLING_C):
        return None
    return True


def refuelled_between(previous, lap) -> bool:
    """The tank went up between the end of one lap and the start of the next."""
    return lap.fuel_start > previous.fuel_end + REFUEL_STEP_L


def starts_run(previous, lap) -> bool:
    """Does this lap begin a new tank?

    Duck-typed on purpose. The lap rack asks this of its own row objects and
    the export asks it of `LapInput`, and they must agree exactly: the rack is
    where the driver declares a set fresh, and a declaration made on a lap the
    export does not treat as a run start would be silently ignored.

    A new run starts where the tank went up, where the driver came in, and
    wherever the recording session changed — stopping and restarting the app
    means he went back to the garage, and the laps either side are not one
    continuous stint.
    """
    session_changed = (lap.session_id is not None
                       and previous.session_id is not None
                       and lap.session_id != previous.session_id)
    return (refuelled_between(previous, lap) or session_changed
            or previous.is_pit_lap)


def split_runs(laps: list[LapInput]) -> list[Run]:
    """Group laps into the tanks they were run on."""
    if not laps:
        return []

    grouped: list[list[LapInput]] = [[laps[0]]]
    refuelled: list[bool] = [False]
    # What the stop that opened each run did to the tyres. The first run of a
    # session has no stop before it, so it stays unknown rather than False.
    swapped: list[bool | None] = [None]
    for previous, lap in zip(laps, laps[1:]):
        if starts_run(previous, lap):
            grouped.append([lap])
            refuelled.append(refuelled_between(previous, lap))
            swapped.append(previous.tyres_changed)
        else:
            grouped[-1].append(lap)

    return [Run(id=index, laps=tuple(group), refuelled_before=was_refuelled,
                tyres_changed_before=was_swapped)
            for index, (group, was_refuelled, was_swapped)
            in enumerate(zip(grouped, refuelled, swapped), start=1)]


def run_of(runs: list[Run], lap_num: int) -> int | None:
    """The id of the run a lap belongs to."""
    for run in runs:
        if run.first_lap <= lap_num <= run.last_lap:
            return run.id
    return None


def runs_export(runs: list[Run]) -> list[dict] | None:
    return [run.as_export() for run in runs] or None


def typical_fuel_burn_l(laps: list[LapInput]) -> float | None:
    """The session's representative burn per lap, in litres.

    Median, and only over laps that neither took fuel nor gave it back, so a
    stop cannot move the figure the implausibility test is measured against.
    """
    runs = split_runs(laps)
    burns = []
    for run in runs:
        for lap in run.laps:
            burn = lap.fuel_start - lap.fuel_end
            if burn > 0:
                burns.append(burn)
    return round(median(burns), 3) if burns else None


def fuel_implausible_laps(laps: list[LapInput],
                          fuel_capacity_l: float | None) -> set[int]:
    """Laps that cannot have gone round the circuit, by their fuel burn.

    A lap boundary landing inside a pit or garage transition produces a lap
    time that is not a lap of the track. Left alone it is counted, and being
    short it becomes the session best — which is what happened to the 11 Aug
    Monza session, where a lap that burned 0.16 L against a 6.57 L median was
    promoted to `bestLapMs` and read 1.9 s faster than the real best.

    Returns an empty set for electric cars: a capacity of 0 is a real value and
    every lap burns nothing, so the test has nothing to say and must not strike
    the whole session.
    """
    if fuel_capacity_l is not None and fuel_capacity_l <= 0:
        return set()
    typical = typical_fuel_burn_l(laps)
    if not typical:
        return set()
    floor = typical * FUEL_IMPLAUSIBLE_FRACTION
    return {lap.lap_num for lap in laps
            if 0.0 <= lap.fuel_start - lap.fuel_end < floor}


def auto_out_laps(laps: list[LapInput]) -> set[int]:
    """First laps of refuelled runs — an out-lap the driver should not have to
    strike by hand, and one the export should be able to name as an out-lap
    rather than as an unexplained hand strike."""
    return {run.first_lap for run in split_runs(laps)
            if run.refuelled_before and run.first_lap != laps[0].lap_num}


# The vocabulary the export uses for why a lap does not count. `manual` is the
# fallback for a hand strike the app cannot explain — and the point of the
# other five is that it should be the rare one. Eight identical "struck by
# hand" notes carry no information; four of the eight in the 11 Aug session
# were out-laps the refuel boundary names for free.
EXCLUSION_REASONS = (REASON_OUT_LAP, REASON_IN_LAP, "incident", "traffic",
                     REASON_FUEL_IMPLAUSIBLE, REASON_MANUAL)


def classify_exclusions(laps: list[LapInput],
                        fuel_capacity_l: float | None) -> list[LapInput]:
    """Give every excluded lap a reason from the vocabulary, and a source.

    Also *applies* the two mechanical exclusions — the out-lap after a refuel
    and the fuel-implausible lap — so that everything downstream, `lapsCounted`
    and `bestLapMs` included, sees one consistent set of counted laps rather
    than each aggregate deciding for itself.
    """
    implausible = fuel_implausible_laps(laps, fuel_capacity_l)
    out_laps = auto_out_laps(laps)

    out = []
    for lap in laps:
        reason, source = _reason_for(lap, implausible, out_laps)
        if reason is None:
            out.append(replace(lap, exclusion_reason=None,
                               exclusion_source=None, driver_note=None))
            continue
        # Structural laps carry their own flags; the rest are excluded here so
        # that a mechanical finding and a hand strike land in the same place.
        out.append(replace(
            lap,
            excluded=lap.excluded or reason in (REASON_FUEL_IMPLAUSIBLE,
                                                REASON_OUT_LAP),
            exclusion_reason=reason,
            exclusion_source=source,
            driver_note=_driver_note(lap, reason),
        ))
    return out


def _driver_note(lap: LapInput, reason: str) -> str | None:
    """What he typed, where the vocabulary does not already hold it.

    "spun at T4" is worth carrying through a `manual` classification. "struck
    by hand" is not: it repeats the classification and adds nothing, and eight
    copies of it in `notes` were the whole of P7.
    """
    stated = (lap.exclusion_reason or "").strip()
    if not stated or not lap.excluded:
        return None
    if stated.lower() in EXCLUSION_REASONS or stated.lower() in _EMPTY_NOTES:
        return None
    return stated


# Hand-strike wording that says only "the driver struck this", which is what
# `source: driver` already says.
_EMPTY_NOTES = ("struck by hand", "excluded", "struck")


def _reason_for(lap: LapInput, implausible: set[int],
                out_laps: set[int]) -> tuple[str | None, str | None]:
    if lap.is_out_lap:
        return REASON_OUT_LAP, SOURCE_AUTO
    if lap.is_pit_lap:
        return REASON_IN_LAP, SOURCE_AUTO
    if lap.lap_num in implausible:
        return REASON_FUEL_IMPLAUSIBLE, SOURCE_AUTO
    if lap.lap_num in out_laps:
        # Mechanically detectable, so it is named rather than left as a hand
        # strike — whether or not he also struck it.
        return REASON_OUT_LAP, SOURCE_AUTO
    if lap.excluded:
        stated = (lap.exclusion_reason or "").strip().lower()
        if stated in EXCLUSION_REASONS:
            return stated, SOURCE_DRIVER
        return REASON_MANUAL, SOURCE_DRIVER
    return None, None
