"""The driver as a variable - three numbers per session, for the debrief only.

Plan row 2.11, **inside the refusal card**: incident rate, lap-one cost and
consistency, reported per session as trends **in the debrief and nowhere
else** - never priced into a plan, never a live warning, never per corner.
Incidents are memoryless (`references/refusals.md`): the next cannot be
predicted from the last, so a rate is a description of the sessions already
driven and never a forecast. Session scatter is a state, never banked as a
loss (`race-planner.md`, *The incident ledger*).

Each number carries its own n, and each is None - never 0 - where it cannot
be known (CLAUDE.md rule 3):

- **Incidents** are what the export calls incidents: `find_incidents`'
  verdicts, marked by `export.build.mark_incidents`, **and every lap already
  stored as one** (`exclusion_reason = 'incident'`, by the app or by the
  driver). Stored laps arrive struck, `find_incidents` skips struck laps,
  and the first version counted none of the 19 stored race incidents on
  file - the Sardegna grass spin and a crash the driver himself reported
  among them (critic 6). They are counted inside the runs `find_incidents`
  judges (three clean laps at least); one outside such a run is named, not
  rated. A session with no judged run has no incident count, not zero.
- **Lap-one cost** is a race's first lap against the median of its counted
  laps from lap five on - warm-up laps two to four cost a little and it is
  gone by lap five. Refused where lap one was a pit lap (its time is the
  stop's), labelled with the start type, and absent in practice, whose
  first lap is driven out of the pits.
- **Consistency** is the spread of the counted laps - the set pace and fuel
  read - **only where somebody screened them for incidents, and over three
  laps at least**; two laps nobody screened is not a spread.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median, pstdev

from pitcrew.analysis.incidents import REASON_INCIDENT, stored_or_read
from pitcrew.analysis.runs import (EXCLUSION_REASONS, auto_out_laps,
                                   classify_exclusions, split_runs)
from pitcrew.analysis.session import counted_laps

# Warm-up laps two to four cost a little and it is gone by lap five.
LAP_ONE_REFERENCE_FROM = 5
# The floor `find_incidents` judges a run on: the median of two laps is not a
# reference, and the same holds for lap one's, and for a spread.
MIN_REFERENCE_LAPS = 3
RACE = "race"


@dataclass(frozen=True)
class SessionTrend:
    session_id: int | None
    kind: str | None
    # Laps in runs `find_incidents` could judge, and the incidents in them.
    # `incidents` is None where no run could be judged.
    judged_laps: int
    incidents: int | None
    lap_one_cost_s: float | None
    lap_one_reference_n: int
    consistency_sd_s: float | None
    consistency_n: int
    silences: tuple[str, ...] = ()
    start_type: str | None = None

    @property
    def incident_rate(self) -> float | None:
        """Incidents per judged lap - a description, never a forecast."""
        if self.incidents is None or not self.judged_laps:
            return None
        return self.incidents / self.judged_laps


def _capacity(laps) -> float | None:
    # The debrief's own rule for the tank, so the counted set is its set.
    return next((lap.fuel_start for lap in laps
                 if lap.fuel_start and lap.fuel_start > 50), None)


def _stored_incident(lap) -> bool:
    return bool(lap.excluded) and lap.exclusion_reason == REASON_INCIDENT


def _judged_runs(laps) -> tuple[int, set[int], int]:
    """(laps judged, stored incidents inside judged runs, stored incidents
    outside them) - `find_incidents`' own filter and its own floor."""
    out_laps = auto_out_laps(laps)
    judged, inside, outside = 0, set(), 0
    for run in split_runs(laps):
        candidates = [lap for lap in run.laps
                      if not (lap.is_out_lap or lap.is_pit_lap or lap.excluded
                              or lap.lap_num in out_laps)]
        stored = [lap for lap in run.laps
                  if _stored_incident(lap) and not lap.is_pit_lap]
        times = [lap for lap in candidates if lap.lap_time_ms > 0]
        if len(times) >= MIN_REFERENCE_LAPS:
            judged += len(candidates) + len(stored)
            inside.update(lap.lap_num for lap in stored)
        else:
            outside += len(stored)
    return judged, inside, outside


def session_trend(laps, *, session_id=None, kind=None, start_type=None,
                  evidence_for=stored_or_read) -> SessionTrend:
    """The three numbers for ONE session's laps, in the order they were run.

    `laps` are `LapInput`s as `event_lap_inputs` gives them, not yet marked
    or classified. `evidence_for` is `find_incidents`' accessor.
    """
    from pitcrew.export.build import mark_incidents

    laps = list(laps)
    silences: list[str] = []
    judged, stored_inside, stored_outside = _judged_runs(laps)
    marked, found = mark_incidents(laps, evidence_for=evidence_for)
    incidents = len(set(found) | stored_inside) if judged else None
    if incidents is None:
        silences.append("no run had three clean laps, so no lap was judged "
                        "for an incident - not a count of zero")
    if stored_outside:
        silences.append(f"{stored_outside} lap(s) stored as incidents sit in "
                        "runs too short to judge - named here, not rated")
    # **A lap he struck in his own words is quoted, not counted and not
    # dropped** (critic 6). Deep Forest s135's lap 2 reads "crash ... the
    # driver reported damage": the export files a free-text strike as manual,
    # not as an incident, so counting it would make "incidents" mean two
    # things (rule 13) - and printing "0" beside it with nothing else would
    # hide his report (rule 1). The disagreement is shown, not averaged.
    for position, lap in enumerate(laps, 1):
        reason = (lap.exclusion_reason or "").strip()
        if lap.excluded and reason and reason not in EXCLUSION_REASONS:
            quoted = reason if len(reason) <= 90 else reason[:87] + "..."
            silences.append(f"lap {position} struck by hand, not as an "
                            f"incident: \"{quoted}\"")

    # `classify_exclusions` returns new objects, so everything below reads
    # THIS list and its own `counted` flag - never identity against `marked`.
    classified = classify_exclusions(marked, _capacity(marked))
    counted = counted_laps(classified)
    times = [lap.lap_time_ms / 1000.0 for lap in counted if lap.lap_time_ms > 0]
    sd = None
    if incidents is not None and len(times) >= MIN_REFERENCE_LAPS:
        sd = pstdev(times)

    cost, reference_n = None, 0
    if kind != RACE:
        silences.append("no lap-one cost: a practice lap one is driven out "
                        "of the pits, not from a start")
    elif not laps or not laps[0].lap_time_ms or laps[0].lap_time_ms <= 0:
        silences.append("no lap-one cost: lap one has no time on file")
    elif laps[0].is_pit_lap:
        silences.append("no lap-one cost: lap one was a pit lap, so its time "
                        "is the stop's")
    else:
        first = laps[0]
        # Position in the session, not `lap_num`, which `event_lap_inputs`
        # renumbers continuously across the event's runs.
        later = [lap.lap_time_ms / 1000.0
                 for index, lap in enumerate(classified, 1)
                 if index >= LAP_ONE_REFERENCE_FROM and lap.counted
                 and lap.lap_time_ms > 0]
        reference_n = len(later)
        if reference_n < MIN_REFERENCE_LAPS:
            silences.append(f"no lap-one cost: {reference_n} counted lap(s) "
                            f"from lap {LAP_ONE_REFERENCE_FROM} on, and a "
                            f"reference needs {MIN_REFERENCE_LAPS}")
        else:
            cost = first.lap_time_ms / 1000.0 - median(later)
            # `find_incidents` never judges lap one - `auto_out_laps` makes
            # every run's first lap an out-lap - so an off at the start is
            # inside this figure and in no incident count. Said, not guessed.
            silences.append("lap one is not judged for incidents, so its "
                            "cost may include one")
            if "rolling" in (start_type or "").lower():
                silences.append("a rolling start - lap one's cost is not a "
                                "standing start's")

    return SessionTrend(session_id=session_id, kind=kind, judged_laps=judged,
                        incidents=incidents, lap_one_cost_s=cost,
                        lap_one_reference_n=reference_n,
                        consistency_sd_s=sd, consistency_n=len(times),
                        silences=tuple(silences), start_type=start_type)
