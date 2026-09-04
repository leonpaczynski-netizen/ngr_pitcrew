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
from pitcrew.analysis.incidents import REASON_INCIDENT
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
    # `lobby`, `time-trial`, or None where the driver has not said. Only the
    # first run of a session uses it.
    practice_mode: str | None = None

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
                tyres_changed_before=was_swapped,
                practice_mode=group[0].practice_mode)
            for index, (group, was_refuelled, was_swapped)
            in enumerate(zip(grouped, refuelled, swapped), start=1)]


def carry_compound(rows, lap_id) -> list:
    """A compound tagged once carries to the end of its stint.

    *"When I enter a tyre compound at the start of the stint replicate that
    compound until either the end of the stint or until you detect a tyre
    change."* One set of tyres is one set of tyres; tagging every lap of it
    by hand is the app making him restate a fact it already knows.

    The stint boundary is the run boundary, which is exactly where a set can
    change: a refuel, a stop, or going back to the garage. So the fill stops
    where the evidence says the tyres could have come off, and never runs past
    it into a set it has no claim about.

    Returns the rows whose compound this changed, the edited one included, so
    the caller writes only what moved.

    Backwards is deliberately not filled. Tagging lap 8 says what lap 8 ran
    on; whether lap 3 of the same stint ran on it is the same question and the
    same answer, but filling backwards would silently overwrite a tag he had
    already made on an earlier lap and disagreed with.
    """
    rows = list(rows)
    edited = next((row for row in rows if row.lap_id == lap_id), None)
    if edited is None or not edited.compound:
        return [edited] if edited is not None else []

    run = next((run for run in split_runs(rows)
                if run.first_lap <= edited.lap_num <= run.last_lap), None)
    if run is None:
        return [edited]

    changed = []
    for row in rows:
        if not (edited.lap_num <= row.lap_num <= run.last_lap):
            continue
        if row.compound != edited.compound:
            row.compound = edited.compound
            changed.append(row)
    return changed if edited in changed else [edited, *changed]


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


# Where the car is when a practice session begins, which is what decides
# whether its opening lap is an out-lap.
LOBBY = "lobby"                # in the pit box; the first lap is an out-lap
TIME_TRIAL = "time-trial"      # on the track ahead of the line; it is not

# What a session was for. Orthogonal to where the car started: a
# qualifying simulation is usually a time trial and race running is usually
# a lobby, but neither implies the other.
FOR_QUALIFYING = "qualifying"
FOR_RACE = "race"
PRACTICE_INTENTS = (FOR_RACE, FOR_QUALIFYING)


@dataclass(frozen=True)
class OpeningLap:
    """Whether a session's opening lap is an out-lap, and the evidence.

    `is_out_lap` is tri-state. `None` is "cannot say" and every caller must
    leave the stored flag exactly as it was on `None` - a lap the app cannot
    place is not a lap that started on the track, and it is not a lap that
    started in the box either.
    """
    is_out_lap: bool | None
    reason: str


def opening_lap_verdict(*, session_kind: str | None,
                        practice_mode: str | None,
                        standing_start_ms: int | None) -> OpeningLap:
    """Is the first lap of a session an out-lap? One rule for every path.

    **Why this exists.** The live flag came from `session_state`, which sets
    it on a PIT EXIT - and a pit exit needs a pit ENTRY first. A session's
    opening lap begins already in the box, so no entry is ever seen and the
    flag could not fire: twelve Daytona sessions in a row stored their
    opening lap as `is_out_lap = 0`, five of them 91-95 s against a 104 s
    lap, and `min(lap_time_ms)` over the event returned a lap nobody drove.
    The rack named those laps correctly on the screen, from `auto_out_laps`,
    and wrote nothing back - so the screen and the database disagreed about
    the number every session is judged by (CLAUDE.md rule 13).

    **The driver's declaration is primary (rule 1) and the frames corroborate
    it.** Where the car started the session is the whole question, and it is
    the one thing about a session GT7 cannot say; he answers it on the rack.
    What the feed carries is `standing_start_ms` - how long the car sat
    before it set off on this lap. Measured across every session on file:
    every lobby opener begins at `speed 0.0` (0.4 s to 64 s at rest, in the
    box); every time-trial opener begins rolling at 135-272 km/h, on the
    track ahead of the line; every race opener begins at rest on the grid.
    So, in order:

    * **A race opens from the grid, not the pit box.** Its first lap is a
      full lap from a standing start and counts. `False`.
    * **Declared time trial**: `False`. The frames showing the car at rest
      would be a disagreement, and it is named in the reason rather than
      resolved here - he can correct the declaration on the rack.
    * **Declared lobby**: `True`. Whether the frames caught the car at rest
      or picked it up already rolling out of the box is noted, not decided.
    * **Undeclared**, the frames decide: at rest → `True` (a practice
      session that begins stationary began in the box - a time trial never
      does); rolling → `None` (the recording caught the car late and cannot
      say where it started); no frames → `None`.

    **Frame distance is deliberately not a signal.** A lobby opener at
    Daytona integrates 3-4% short of the circuit because the pit exit skips
    the start straight - but so does a full lap whose recording began late
    (session 20 lap 1: rolling at 199 km/h at the first frame, 3.4% short,
    and a full lap time). Coverage of the *frames* cannot tell a partial lap
    from a partial recording, so it cannot flag one without also flagging
    the other. And lap TIME is not used at all: a short lap is what this rule
    exists to catch, so it cannot be the evidence for it.
    """
    at_rest = standing_start_ms is not None and standing_start_ms > 0
    if standing_start_ms is None:
        seen = "no frames to corroborate"
    elif at_rest:
        seen = f"frames begin at rest for {standing_start_ms / 1000:.1f} s"
    else:
        seen = "frames begin rolling"

    if session_kind == "race":
        return OpeningLap(False, f"a race opens from the grid, not the pit box "
                                 f"({seen})")
    if practice_mode == TIME_TRIAL:
        if at_rest:
            return OpeningLap(False, (
                f"declared time trial, but {seen} - the declaration stands; "
                f"a time trial starts rolling on track, so check it"))
        return OpeningLap(False, f"declared time trial: started on track "
                                 f"ahead of the line ({seen})")
    if practice_mode == LOBBY:
        if standing_start_ms is None:
            return OpeningLap(True, f"declared lobby: out of the pit box "
                                    f"({seen})")
        if at_rest:
            return OpeningLap(True, f"declared lobby, and {seen} in the box")
        return OpeningLap(True, (
            "declared lobby; the recording picked the car up already rolling "
            "out of the box, so the frames neither confirm nor deny it"))
    # Undeclared: only the feed can say, and only one way.
    if at_rest:
        return OpeningLap(True, (
            f"undeclared, but {seen}: a practice session that begins "
            f"stationary began in the pit box - a time trial starts rolling"))
    if standing_start_ms is None:
        return OpeningLap(None, "undeclared and no frames: cannot say where "
                                "the car started")
    return OpeningLap(None, (
        "undeclared and the recording picked the car up already rolling: "
        "cannot say whether it started in the box or on the track"))


def flag_opening_lap(lap, *, session_kind: str | None,
                     practice_mode: str | None,
                     standing_start_ms: int | None):
    """The live path's half of the rule: the lap as it should be stored.

    Called with the lap the session state built, before it is written. Only
    a session's first lap is judged, only a flag the detector left clear is
    touched, and only ever SET - `None` leaves it as it was (rule 3), and
    `False` has nothing to clear because the detector cannot have set it on
    a lap with no pit entry before it. Returns `(lap, verdict)`; `verdict` is
    `None` where the rule did not apply, so the caller can log what was
    accepted as well as what was refused (rule 10).
    """
    if getattr(lap, "lap_num", None) != 1 or getattr(lap, "is_out_lap", False):
        return lap, None
    verdict = opening_lap_verdict(session_kind=session_kind,
                                  practice_mode=practice_mode,
                                  standing_start_ms=standing_start_ms)
    if verdict.is_out_lap:
        lap = replace(lap, is_out_lap=True)
    return lap, verdict


def auto_out_laps(laps: list[LapInput]) -> set[int]:
    """**The first lap of every run** — with one exception, and it matters.

    It used to be the first lap of a *refuelled* run only, and explicitly not
    the session's own first lap. The refuel condition was a proxy for "a stop
    happened", written when a stop could not be detected; it can be now, and a
    stop for tyres alone opens a run just as much as one for fuel does. So
    every run's first lap qualifies.

    **Except the opening lap of a time trial.** The two modes put the car in
    different places when the session starts:

    * **In a lobby** it starts in the pit box. The first lap is driven out of
      the pits on cold tyres and is an out-lap in every sense.
    * **In a time trial** it starts on the track, ahead of the start/finish
      line. The lap is timed from the line like any other, and on the capture
      set it is the *fastest lap of the session* in six of the eight time
      trials recorded. Striking it would throw away the best lap of the day
      and call it housekeeping.

    The mode is the driver's to declare. Where he has not, the opening lap is
    treated as an out-lap: that is the lobby case, it is the safer of the two
    errors — a struck lap is visible on the rack and can be restored, a
    counted out-lap is invisible and moves every aggregate — and it is what
    the app did before the exception existed.

    **The exception belongs to the first lap of a session, not to `runs[0]`.**
    `practice_mode` is per session and an event export concatenates every
    practice session it has, each opening a new run — so applying it to
    `runs[0]` alone struck the opening lap of the second and third time trial
    of the day, usually the fastest lap each of them had. It is not applied to
    every run either: a mid-session refuel opens a genuine out-lap whatever
    mode the session is in. Where the car started the session is the whole of
    what the exception is about.

    **The opener's verdict comes from `opening_lap_verdict`, the same rule
    the live path writes with**, so the rack, the export and the stored flag
    reach one answer (rule 13). One difference remains and is deliberate: on
    `None` - undeclared and the frames cannot say - the live path leaves the
    stored flag clear (rule 3, never guess into the database), while the rack
    keeps the opener struck, as it always has. A struck lap is visible and
    can be put back; a counted out-lap is invisible and moves every
    aggregate. The live path can never reach `None`: the rack's mode picker
    always holds a mode, so every session recorded since it existed is
    declared, and the nineteen undeclared sessions on file all predate it.
    """
    runs = split_runs(laps)
    out = {run.first_lap for run in runs}
    session_openers = _session_opening_laps(laps)
    for run in runs:
        if run.first_lap not in session_openers:
            continue
        first = run.laps[0]
        verdict = opening_lap_verdict(
            session_kind=getattr(first, "session_kind", None),
            practice_mode=run.practice_mode,
            standing_start_ms=getattr(first, "standing_start_ms", None))
        if verdict.is_out_lap is False:
            out.discard(run.first_lap)
    return out


def _session_opening_laps(laps: list[LapInput]) -> set[int]:
    """The lap number each recording session opened with.

    Keyed on `session_id`, and `None` is a key like any other: a lap list
    built by hand carries no session and its first lap is still the first lap
    of what there is.
    """
    opening: dict[int | None, int] = {}
    for lap in laps:
        if lap.session_id not in opening:
            opening[lap.session_id] = lap.lap_num
    return set(opening.values())


# The vocabulary the export uses for why a lap does not count. `manual` is the
# fallback for a hand strike the app cannot explain — and the point of the
# other five is that it should be the rare one. Eight identical "struck by
# hand" notes carry no information; four of the eight in the 11 Aug session
# were out-laps the refuel boundary names for free.
EXCLUSION_REASONS = (REASON_OUT_LAP, REASON_IN_LAP, REASON_INCIDENT, "traffic",
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
    # Ahead of the driver's own strike, so a lap he struck *and* the frames
    # explain reads as the explanation rather than as an unexplained mark.
    # His note survives either way - `_driver_note` carries it separately.
    if lap.incident:
        return REASON_INCIDENT, SOURCE_AUTO
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
