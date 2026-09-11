"""The driver as a variable - three numbers per session, for the debrief only.

Plan row 2.11, **inside the refusal card**: incident rate, lap-one cost and
consistency, reported per session as trends **in the debrief and nowhere
else** - never in a brief, never priced into a plan, never a live warning,
never per corner. Incidents are memoryless (`references/refusals.md`): the
next cannot be predicted from the last, so a rate is a description of the
sessions already driven and never a forecast. Session scatter is a state,
never banked as a loss (`race-planner.md`, *The incident ledger*).

Each number carries its own n, and each is None - never 0 - where it cannot
be known (CLAUDE.md rule 3):

- **Incidents** are `find_incidents`' own verdicts, marked by
  `export.build.mark_incidents` - the one marking the export uses. A run with
  fewer than three clean laps gets no verdict from it, so its laps are not
  counted as judged: a session with no judged run has no incident count,
  which is not a count of zero.
- **Lap-one cost** is a race's first lap against the median of its counted
  laps from lap five on - warm-up laps two to four cost a little and it is
  gone by lap five, so they are left out of the reference. Practice has no
  lap-one cost: its first lap is driven out of the pits.
- **Consistency** is the spread of the counted laps - the set pace and fuel
  read (`classify_exclusions`, then `counted_laps`), which is exactly the
  set the debrief's own pace line uses.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median, pstdev

from pitcrew.analysis.incidents import stored_or_read
from pitcrew.analysis.runs import auto_out_laps, classify_exclusions, split_runs
from pitcrew.analysis.session import counted_laps

# Warm-up laps two to four cost a little and it is gone by lap five.
LAP_ONE_REFERENCE_FROM = 5
# The floor `find_incidents` judges a run on: the median of two laps is not a
# reference, and the same holds for lap one's.
MIN_REFERENCE_LAPS = 3
RACE = "race"


@dataclass(frozen=True)
class SessionTrend:
    session_id: int | None
    kind: str | None
    # Laps in runs `find_incidents` could judge, and the incidents it found in
    # them. `incidents` is None where no run could be judged.
    judged_laps: int
    incidents: int | None
    lap_one_cost_s: float | None
    lap_one_reference_n: int
    consistency_sd_s: float | None
    consistency_n: int
    silences: tuple[str, ...] = ()

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


def _judged(laps) -> int:
    """Laps in runs `find_incidents` gives a verdict on - its own filter."""
    out_laps = auto_out_laps(laps)
    judged = 0
    for run in split_runs(laps):
        candidates = [lap for lap in run.laps
                      if not (lap.is_out_lap or lap.is_pit_lap or lap.excluded
                              or lap.lap_num in out_laps)]
        if sum(1 for lap in candidates if lap.lap_time_ms > 0) >= MIN_REFERENCE_LAPS:
            judged += len(candidates)
    return judged


def session_trend(laps, *, session_id=None, kind=None,
                  evidence_for=stored_or_read) -> SessionTrend:
    """The three numbers for ONE session's laps, in the order they were run.

    `laps` are `LapInput`s as `event_lap_inputs` gives them, not yet marked
    or classified. `evidence_for` is `find_incidents`' accessor.
    """
    from pitcrew.export.build import mark_incidents

    laps = list(laps)
    silences: list[str] = []
    judged = _judged(laps)
    marked, found = mark_incidents(laps, evidence_for=evidence_for)
    incidents = len(found) if judged else None
    if incidents is None:
        silences.append("no run had three clean laps, so no lap was judged "
                        "for an incident - not a count of zero")

    # `classify_exclusions` returns new objects, so everything below reads
    # THIS list and its own `counted` flag - never identity against `marked`.
    classified = classify_exclusions(marked, _capacity(marked))
    counted = counted_laps(classified)
    times = [lap.lap_time_ms / 1000.0 for lap in counted if lap.lap_time_ms > 0]
    sd = pstdev(times) if len(times) >= 2 else None

    cost, reference_n = None, 0
    if kind != RACE:
        silences.append("no lap-one cost: a practice lap one is driven out "
                        "of the pits, not from a start")
    elif not laps or not laps[0].lap_time_ms or laps[0].lap_time_ms <= 0:
        silences.append("no lap-one cost: lap one has no time on file")
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

    return SessionTrend(session_id=session_id, kind=kind, judged_laps=judged,
                        incidents=incidents, lap_one_cost_s=cost,
                        lap_one_reference_n=reference_n,
                        consistency_sd_s=sd, consistency_n=len(times),
                        silences=tuple(silences))
