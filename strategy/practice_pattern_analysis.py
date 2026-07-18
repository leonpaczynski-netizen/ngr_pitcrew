"""Deterministic cross-lap Practice Analysis engine (pure, Qt-free).

UAT Finding 2. The app reacted to isolated packets / one bad lap; it never
proved it analysed *patterns across laps and corners*. This engine consumes
consolidated slip/handling episodes (already produced per lap by
``telemetry/slip_events.py``, which merges consecutive packets into one episode
and excludes kerb strikes, airborne wheels, wheel hop, downshifts and
brake/coast-side slip) and answers, per track segment and driving phase:

  * is this a repeated / emerging / isolated issue?
  * where is the driver consistently strong (setup should be preserved)?
  * is it improving or worsening?
  * does it agree or contradict the driver's own feedback?
  * is it eligible to author a setup change, or only a note?

Central, configurable, tested recurrence thresholds live in
``RecurrenceThresholds``. Persistence conclusions use **clean laps only**.
Excluded episodes (kerb/airborne/downshift/…) are classified separately and are
never presented as recurring or used for setup authoring.

Pure: no Qt, no I/O, no telemetry parsing — the caller assembles
``EpisodeObservation`` rows from the existing episode extractor + segment
resolver and passes them in.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, List, Optional, Sequence, Tuple


class RecurrenceClass(str, Enum):
    ISOLATED = "isolated"                 # one affected clean lap
    EMERGING = "emerging"                 # two affected clean laps
    RECURRING = "recurring"               # three+ affected clean laps
    STRONGLY_RECURRING = "strongly_recurring"  # four+ affected clean laps
    EXCLUDED = "excluded"                 # kerb/airborne/downshift/… — not authored
    STRENGTH = "strength"                 # consistently clean — preserve setup


class Trend(str, Enum):
    STABLE = "stable"
    IMPROVING = "improving"
    WORSENING = "worsening"
    UNKNOWN = "unknown"


class FeedbackAgreement(str, Enum):
    NONE = "none"               # driver said nothing about this
    AGREES = "agrees"           # telemetry confirms the driver's feedback
    CONTRADICTS = "contradicts"  # driver reported the opposite


@dataclass(frozen=True)
class RecurrenceThresholds:
    """Central deterministic recurrence model. Configurable + tested.

    The class is a function of affected clean laps AND total clean laps observed
    (a 3/3 pattern is stronger evidence than 3/12).
    """
    isolated_max: int = 1
    emerging_min: int = 2
    recurring_min: int = 3
    strongly_recurring_min: int = 4
    # Need at least this many clean laps before persistence conclusions are drawn.
    min_clean_laps_for_persistence: int = 3
    # A pattern in this fraction of clean laps is "strongly recurring" even if the
    # absolute count is below strongly_recurring_min (e.g. 3/3 laps).
    strong_fraction: float = 0.75

    def classify(self, affected_laps: int, clean_total: int) -> RecurrenceClass:
        if affected_laps <= 0:
            return RecurrenceClass.STRENGTH
        frac = (affected_laps / clean_total) if clean_total else 0.0
        if affected_laps >= self.strongly_recurring_min or (
            frac >= self.strong_fraction and affected_laps >= self.recurring_min):
            return RecurrenceClass.STRONGLY_RECURRING
        if affected_laps >= self.recurring_min:
            return RecurrenceClass.RECURRING
        if affected_laps >= self.emerging_min:
            return RecurrenceClass.EMERGING
        return RecurrenceClass.ISOLATED

    def is_authorable(self, cls: RecurrenceClass) -> bool:
        return cls in (RecurrenceClass.RECURRING, RecurrenceClass.STRONGLY_RECURRING)


@dataclass(frozen=True)
class EpisodeObservation:
    """One consolidated episode observed on one lap at one segment+phase.

    Assembled by the caller from ``telemetry/slip_events.py`` episodes + the
    live segment resolver. ``excluded`` carries the extractor's suppression
    verdict (kerb/airborne/downshift/coast/…).
    """
    lap_number: int
    is_clean: bool
    segment_id: str
    corner_name: str          # display name, or "" if unresolved
    phase: str                # braking / entry / apex / exit
    issue_type: str           # e.g. "front_lock", "rear_wheelspin"
    duration_s: float = 0.0
    magnitude: float = 0.0    # e.g. slip ratio / severity
    throttle: float = 0.0     # 0..1
    brake: float = 0.0        # 0..1
    steering: float = 0.0     # signed, normalised
    excluded: bool = False
    exclusion_reason: str = ""


@dataclass(frozen=True)
class CornerPatternFinding:
    corner_name: str
    segment_id: str
    location_resolved: bool
    phase: str
    finding: str                 # human-readable issue label
    issue_type: str
    clean_laps_observed: int
    laps_affected: int
    recurrence_pct: float
    consolidated_episode_count: int
    median_duration_s: float
    max_duration_s: float
    median_magnitude: float
    max_magnitude: float
    throttle_range: Tuple[float, float]
    brake_range: Tuple[float, float]
    steering_context: str
    lap_time_consequence: str
    trend: Trend
    confidence: str              # high | medium | low
    recurrence_class: RecurrenceClass
    driver_feedback_agreement: FeedbackAgreement
    setup_authoring_eligible: bool

    def headline(self) -> str:
        loc = self.corner_name if self.location_resolved else "an unresolved location"
        return (f"{self.finding} in the {self.phase} phase of {loc} on "
                f"{self.laps_affected} of {self.clean_laps_observed} clean laps.")


@dataclass(frozen=True)
class StrongCorner:
    corner_name: str
    segment_id: str
    clean_laps_observed: int
    note: str


@dataclass(frozen=True)
class PracticeAnalysisReport:
    total_laps: int
    clean_laps: int
    corners_analysed: int
    findings: Tuple[CornerPatternFinding, ...]
    repeatable_issues: Tuple[CornerPatternFinding, ...]
    isolated_events: Tuple[CornerPatternFinding, ...]
    strong_corners: Tuple[StrongCorner, ...]
    targeted_tests: Tuple[str, ...]
    notes: Tuple[str, ...] = ()

    @property
    def has_enough_clean_laps(self) -> bool:
        return self.clean_laps >= 1


_ISSUE_LABELS = {
    "front_lock": "front brake lock-up",
    "rear_lock": "rear brake lock-up",
    "rear_wheelspin": "rear wheelspin",
    "front_wheelspin": "front wheelspin",
    "wheelspin": "wheelspin",
    "oversteer": "oversteer",
    "understeer": "understeer",
}


def _label(issue_type: str) -> str:
    return _ISSUE_LABELS.get(issue_type, issue_type.replace("_", " "))


def _confidence(affected: int, clean_total: int, thresholds: RecurrenceThresholds) -> str:
    if clean_total < thresholds.min_clean_laps_for_persistence:
        return "low"
    if affected >= thresholds.strongly_recurring_min:
        return "high"
    if affected >= thresholds.recurring_min:
        return "medium"
    return "low"


def _trend(affected_laps: Sequence[int], clean_laps_sorted: Sequence[int]) -> Trend:
    """Improving if the issue clusters in the earlier half of clean laps,
    worsening if it clusters later, else stable/unknown."""
    if len(clean_laps_sorted) < 4 or len(affected_laps) < 2:
        return Trend.UNKNOWN
    mid = clean_laps_sorted[len(clean_laps_sorted) // 2]
    early = sum(1 for l in affected_laps if l < mid)
    late = sum(1 for l in affected_laps if l >= mid)
    if late > early:
        return Trend.WORSENING
    if early > late:
        return Trend.IMPROVING
    return Trend.STABLE


def _steering_context(steers: Sequence[float]) -> str:
    if not steers:
        return "n/a"
    avg = statistics.fmean(steers)
    if abs(avg) < 0.05:
        return "near-straight"
    return "left-hand" if avg < 0 else "right-hand"


def _feedback_agreement(issue_type: str, corner_name: str, phase: str,
                        driver_feedback: Optional[dict]) -> FeedbackAgreement:
    """Very deterministic string-match agreement between telemetry and the
    driver's own words. AGREES if the feedback mentions this issue family."""
    if not driver_feedback:
        return FeedbackAgreement.NONE
    text = " ".join(str(v) for v in driver_feedback.values()).lower()
    if not text.strip():
        return FeedbackAgreement.NONE
    family = issue_type.split("_")[-1]  # lock / wheelspin / oversteer / understeer
    synonyms = {
        "lock": ("lock", "locking", "locked"),
        "wheelspin": ("wheelspin", "spin", "spinning", "traction"),
        "oversteer": ("oversteer", "loose", "snap"),
        "understeer": ("understeer", "push", "washing"),
    }
    words = synonyms.get(family, (family,))
    mentions_issue = any(w in text for w in words)
    # Contradiction: driver reported the opposite handling family.
    opposite = {"oversteer": ("understeer", "push"),
                "understeer": ("oversteer", "loose", "snap")}.get(family, ())
    mentions_opposite = any(w in text for w in opposite)
    if mentions_issue:
        return FeedbackAgreement.AGREES
    if mentions_opposite:
        return FeedbackAgreement.CONTRADICTS
    return FeedbackAgreement.NONE


def analyze_practice(
    observations: Iterable[EpisodeObservation],
    *,
    clean_lap_numbers: Sequence[int],
    total_lap_numbers: Sequence[int],
    track_corners: Optional[Sequence[Tuple[str, str]]] = None,  # (segment_id, name)
    driver_feedback: Optional[dict] = None,
    thresholds: Optional[RecurrenceThresholds] = None,
) -> PracticeAnalysisReport:
    """Produce the cross-lap practice pattern report.

    Persistence conclusions use clean laps only; excluded episodes are reported
    as isolated/EXCLUDED and never drive setup authoring.
    """
    th = thresholds or RecurrenceThresholds()
    clean_set = set(int(l) for l in clean_lap_numbers)
    clean_total = len(clean_set)
    clean_sorted = sorted(clean_set)

    obs = list(observations)
    notes: List[str] = []

    # Group non-excluded, clean-lap episodes by (segment, phase, issue_type).
    groups: dict[Tuple[str, str, str], List[EpisodeObservation]] = {}
    excluded_groups: dict[Tuple[str, str, str], List[EpisodeObservation]] = {}
    for e in obs:
        if int(e.lap_number) not in clean_set:
            continue  # clean laps only for persistence conclusions
        key = (e.segment_id, e.phase, e.issue_type)
        if e.excluded:
            excluded_groups.setdefault(key, []).append(e)
        else:
            groups.setdefault(key, []).append(e)

    findings: List[CornerPatternFinding] = []
    corners_with_issues: set[str] = set()

    def _build_finding(key, eps, forced_excluded=False) -> CornerPatternFinding:
        seg_id, phase, issue = key
        corner_name = next((e.corner_name for e in eps if e.corner_name), "")
        location_resolved = bool(corner_name)
        affected_laps = sorted({int(e.lap_number) for e in eps})
        n_affected = len(affected_laps)
        durations = [e.duration_s for e in eps]
        mags = [e.magnitude for e in eps]
        throttles = [e.throttle for e in eps]
        brakes = [e.brake for e in eps]
        steers = [e.steering for e in eps]
        if forced_excluded:
            cls = RecurrenceClass.EXCLUDED
        else:
            cls = th.classify(n_affected, clean_total)
        # An issue in too few clean laps to conclude persistence is isolated.
        eligible = (
            not forced_excluded
            and th.is_authorable(cls)
            and location_resolved
            and clean_total >= th.min_clean_laps_for_persistence
        )
        consequence = "significant" if cls in (
            RecurrenceClass.RECURRING, RecurrenceClass.STRONGLY_RECURRING) else "minor"
        return CornerPatternFinding(
            corner_name=corner_name,
            segment_id=seg_id,
            location_resolved=location_resolved,
            phase=phase,
            finding=(_label(issue) if not forced_excluded
                     else f"{_label(issue)} after {eps[0].exclusion_reason or 'an external event'}"),
            issue_type=issue,
            clean_laps_observed=clean_total,
            laps_affected=n_affected,
            recurrence_pct=round(100.0 * n_affected / clean_total, 1) if clean_total else 0.0,
            consolidated_episode_count=len(eps),
            median_duration_s=round(statistics.median(durations), 3) if durations else 0.0,
            max_duration_s=round(max(durations), 3) if durations else 0.0,
            median_magnitude=round(statistics.median(mags), 3) if mags else 0.0,
            max_magnitude=round(max(mags), 3) if mags else 0.0,
            throttle_range=(round(min(throttles), 2), round(max(throttles), 2)) if throttles else (0.0, 0.0),
            brake_range=(round(min(brakes), 2), round(max(brakes), 2)) if brakes else (0.0, 0.0),
            steering_context=_steering_context(steers),
            lap_time_consequence=consequence,
            trend=_trend(affected_laps, clean_sorted) if not forced_excluded else Trend.UNKNOWN,
            confidence=("low" if forced_excluded else _confidence(n_affected, clean_total, th)),
            recurrence_class=cls,
            driver_feedback_agreement=_feedback_agreement(issue, corner_name, phase, driver_feedback),
            setup_authoring_eligible=eligible,
        )

    for key, eps in groups.items():
        f = _build_finding(key, eps)
        findings.append(f)
        corners_with_issues.add(key[0])
    for key, eps in excluded_groups.items():
        findings.append(_build_finding(key, eps, forced_excluded=True))
        # excluded episodes still mark the corner as "touched", but not as an issue

    # Sort findings most-severe first (by class rank then laps affected).
    _rank = {RecurrenceClass.STRONGLY_RECURRING: 0, RecurrenceClass.RECURRING: 1,
             RecurrenceClass.EMERGING: 2, RecurrenceClass.ISOLATED: 3,
             RecurrenceClass.EXCLUDED: 4, RecurrenceClass.STRENGTH: 5}
    findings.sort(key=lambda f: (_rank[f.recurrence_class], -f.laps_affected))

    repeatable = tuple(f for f in findings if th.is_authorable(f.recurrence_class))
    isolated = tuple(
        f for f in findings
        if f.recurrence_class in (RecurrenceClass.ISOLATED, RecurrenceClass.EMERGING,
                                  RecurrenceClass.EXCLUDED))

    # Strong corners: track corners that had NO issue episodes across clean laps.
    strong: List[StrongCorner] = []
    if track_corners and clean_total >= th.min_clean_laps_for_persistence:
        for seg_id, name in track_corners:
            if seg_id in corners_with_issues:
                continue
            strong.append(StrongCorner(
                corner_name=name, segment_id=seg_id,
                clean_laps_observed=clean_total,
                note=f"{name} was consistent across all {clean_total} clean laps."))

    # Targeted next tests from the top repeatable issues.
    tests: List[str] = []
    for f in repeatable[:3]:
        tests.append(
            f"Validate a change targeting {_label(f.issue_type)} in {f.corner_name} "
            f"({f.phase}); re-check over {max(3, clean_total)} clean laps.")

    if clean_total < th.min_clean_laps_for_persistence:
        notes.append(
            f"Only {clean_total} clean lap(s) — need "
            f"{th.min_clean_laps_for_persistence} to draw persistence conclusions.")

    return PracticeAnalysisReport(
        total_laps=len(set(int(l) for l in total_lap_numbers)),
        clean_laps=clean_total,
        corners_analysed=len({f.segment_id for f in findings}) + len(strong),
        findings=tuple(findings),
        repeatable_issues=repeatable,
        isolated_events=isolated,
        strong_corners=tuple(strong),
        targeted_tests=tuple(tests),
        notes=tuple(notes),
    )
