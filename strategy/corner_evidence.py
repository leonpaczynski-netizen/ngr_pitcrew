"""Canonical per-corner engineering evidence authority (Engineering Brain Phase 4).

ONE pure representation of a per-corner engineering observation, unifying the
evidence already produced by mature systems (live corner telemetry / persisted
`corner_slip_telemetry`, persisted `corner_issue_occurrences`, practice-pattern
analysis, track-model segment resolution). It does NOT re-process raw telemetry —
it adapts existing producers into a canonical shape and classifies recurrence
using the SINGLE existing authority (`practice_pattern_analysis.RecurrenceThresholds`).

Doctrine: valid laps only; a repeatable same-corner/same-phase pattern outweighs a
noisy count on one bad lap; excluded (kerb/airborne/shift-transient/noise) events
never count; an unresolved corner stays unresolved; no invented GT7 channels
(steering angle, true slip, tyre wear %, brake temp, tyre load).

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; never raises.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Optional, Sequence, Tuple

from strategy.practice_pattern_analysis import RecurrenceClass, RecurrenceThresholds

# Phase 3's consumer shape (this authority feeds it verbatim).
from strategy.setup_experiment_outcome import CornerObservation


CORNER_EVIDENCE_VERSION = "corner_evidence_v1"


class CornerPhase(str, Enum):
    BRAKING = "braking"
    ENTRY = "entry"
    APEX = "apex"                # mid-corner
    EXIT = "exit"
    STRAIGHT = "straight"
    UNRESOLVED = "unresolved"


_PHASE_ALIASES = {
    "braking": CornerPhase.BRAKING, "brake": CornerPhase.BRAKING,
    "entry": CornerPhase.ENTRY, "turn_in": CornerPhase.ENTRY,
    "apex": CornerPhase.APEX, "mid": CornerPhase.APEX, "mid_corner": CornerPhase.APEX,
    "exit": CornerPhase.EXIT, "straight": CornerPhase.STRAIGHT,
    "": CornerPhase.UNRESOLVED, "unresolved": CornerPhase.UNRESOLVED,
}


def normalise_phase(phase) -> CornerPhase:
    return _PHASE_ALIASES.get(str(phase or "").strip().lower(), CornerPhase.UNRESOLVED)


@dataclass(frozen=True)
class CornerObservationRecord:
    """Canonical per-corner observation on ONE lap (or one aggregate)."""

    scope_fingerprint: str = ""
    session_id: Optional[str] = None
    run_id: Optional[str] = None
    lap_id: Optional[str] = None
    lap_number: Optional[int] = None
    setup_id: str = ""
    applied_checkpoint_id: str = ""
    experiment_id: Optional[str] = None
    track: str = ""
    layout_id: str = ""
    segment_id: str = ""
    corner_name: str = ""               # driver-facing name/number, '' if unresolved
    corner_resolution_confidence: str = ""   # high/medium/low/unknown
    phase: CornerPhase = CornerPhase.UNRESOLVED
    issue_type: str = ""
    axle: str = ""                      # front/rear/'' where irrelevant
    event_count: int = 0
    episode_count: int = 0
    affected_sample_count: int = 0
    occurred_on_lap: bool = False
    confidence: str = ""
    severity: str = ""
    source: str = ""                    # corner_issue_occurrences / corner_slip / practice
    telemetry_available: str = "unknown"
    exclusion_reason: str = ""          # '' = admissible
    metrics: Mapping[str, float] = field(default_factory=dict)  # only real channels
    eval_version: str = CORNER_EVIDENCE_VERSION

    @property
    def excluded(self) -> bool:
        return bool(self.exclusion_reason)

    @property
    def resolved(self) -> bool:
        return bool(self.segment_id) and self.phase != CornerPhase.UNRESOLVED

    def group_key(self) -> Tuple[str, str, str, str]:
        """Aggregation key: segment + phase + issue + axle (never across corners)."""
        return (self.segment_id or self.corner_name, self.phase.value,
                self.issue_type, self.axle)

    def to_dict(self) -> dict:
        return {
            "scope_fingerprint": self.scope_fingerprint, "session_id": self.session_id,
            "run_id": self.run_id, "lap_id": self.lap_id, "lap_number": self.lap_number,
            "setup_id": self.setup_id, "applied_checkpoint_id": self.applied_checkpoint_id,
            "experiment_id": self.experiment_id, "track": self.track,
            "layout_id": self.layout_id, "segment_id": self.segment_id,
            "corner_name": self.corner_name,
            "corner_resolution_confidence": self.corner_resolution_confidence,
            "phase": self.phase.value, "issue_type": self.issue_type, "axle": self.axle,
            "event_count": self.event_count, "episode_count": self.episode_count,
            "affected_sample_count": self.affected_sample_count,
            "occurred_on_lap": self.occurred_on_lap, "confidence": self.confidence,
            "severity": self.severity, "source": self.source,
            "telemetry_available": self.telemetry_available,
            "exclusion_reason": self.exclusion_reason, "metrics": dict(self.metrics),
            "eval_version": self.eval_version,
        }


# --------------------------------------------------------------------------- #
# Adapters from existing producers (no raw telemetry re-processing)
# --------------------------------------------------------------------------- #
_REAL_METRIC_KEYS = (
    "entry_speed_kmh", "min_speed_kmh", "exit_speed_kmh", "braking_point_m",
    "max_brake", "max_throttle", "throttle_on_m", "exit_gear", "apex_gear",
    "entry_gear", "duration_s", "speed_kmh", "gear", "throttle", "brake",
)
# NEVER accept these — GT7 does not provide them.
_FABRICATED_METRIC_KEYS = frozenset({
    "steering_angle", "slip_angle", "true_slip", "tyre_wear_pct", "tyre_wear",
    "brake_temp", "brake_temperature", "tyre_load",
})


def _clean_metrics(raw: Mapping) -> dict:
    out = {}
    for k in _REAL_METRIC_KEYS:
        v = raw.get(k)
        if v is None or k in _FABRICATED_METRIC_KEYS:
            continue
        try:
            out[k] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def from_issue_occurrence_row(
    row: Mapping, *, scope_fingerprint: str = "", experiment_id: Optional[str] = None,
) -> CornerObservationRecord:
    """Adapt a persisted ``corner_issue_occurrences`` row (the session-keyed,
    checkpoint-tagged, per-lap store) into a canonical observation."""
    seg = str(row.get("segment_id") or "")
    conf = row.get("confidence")
    try:
        conf_f = float(conf) if conf is not None else 0.0
    except (TypeError, ValueError):
        conf_f = 0.0
    conf_label = ("high" if conf_f >= 0.66 else
                  "medium" if conf_f >= 0.4 else
                  "low" if conf_f > 0 else "unknown")
    return CornerObservationRecord(
        scope_fingerprint=scope_fingerprint,
        session_id=(str(row.get("session_id")) if row.get("session_id") is not None else None),
        lap_number=(int(row["lap_number"]) if row.get("lap_number") is not None else None),
        applied_checkpoint_id=str(row.get("setup_checkpoint_id") or ""),
        experiment_id=(str(experiment_id) if experiment_id is not None else None),
        track=str(row.get("track") or ""), layout_id=str(row.get("layout_id") or ""),
        segment_id=seg,
        corner_resolution_confidence=("low" if not seg else conf_label),
        phase=normalise_phase(row.get("corner_phase")),
        issue_type=str(row.get("issue_type") or ""),
        axle=str(row.get("axle") or ""),
        event_count=1, episode_count=1, occurred_on_lap=True,
        confidence=conf_label, severity=_severity_label(row.get("severity")),
        source="corner_issue_occurrences", telemetry_available="full",
        exclusion_reason=str(row.get("exclusion_reason") or ""),
        metrics=_clean_metrics(row))


def _severity_label(v) -> str:
    try:
        f = float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return ""
    return "high" if f >= 0.66 else "medium" if f >= 0.33 else "low" if f > 0 else ""


# --------------------------------------------------------------------------- #
# Recurrence authority (reuses the practice-pattern thresholds — not reinvented)
# --------------------------------------------------------------------------- #
R_ISOLATED_ONE_LAP = "isolated_single_lap"
R_BELOW_MIN_LAPS = "below_min_valid_laps"
R_ALL_EXCLUDED = "all_evidence_excluded"
R_REPEATABLE = "repeatable_same_corner_phase"


@dataclass(frozen=True)
class RecurrenceResult:
    segment_id: str
    corner_name: str
    phase: str
    issue_type: str
    axle: str
    classification: RecurrenceClass
    affected_valid_laps: int
    total_valid_laps: int
    recurrence_ratio: float
    min_threshold: int
    confidence: str
    event_count: int
    episode_count: int
    excluded_count: int
    rationale_code: str
    source_lap_numbers: Tuple[int, ...]
    eval_version: str = CORNER_EVIDENCE_VERSION

    @property
    def is_authorable(self) -> bool:
        return self.classification in (RecurrenceClass.RECURRING,
                                       RecurrenceClass.STRONGLY_RECURRING)

    def to_dict(self) -> dict:
        return {
            "segment_id": self.segment_id, "corner_name": self.corner_name,
            "phase": self.phase, "issue_type": self.issue_type, "axle": self.axle,
            "classification": self.classification.value,
            "affected_valid_laps": self.affected_valid_laps,
            "total_valid_laps": self.total_valid_laps,
            "recurrence_ratio": self.recurrence_ratio,
            "min_threshold": self.min_threshold, "confidence": self.confidence,
            "event_count": self.event_count, "episode_count": self.episode_count,
            "excluded_count": self.excluded_count,
            "rationale_code": self.rationale_code,
            "source_lap_numbers": list(self.source_lap_numbers),
            "eval_version": self.eval_version,
        }


def classify_recurrence(
    records: Sequence[CornerObservationRecord],
    *,
    total_valid_laps: int,
    thresholds: Optional[RecurrenceThresholds] = None,
) -> RecurrenceResult:
    """Classify one corner+phase+issue+axle group over VALID laps only, reusing the
    canonical `RecurrenceThresholds`. Recurrence is NEVER based on raw event count:
    it counts DISTINCT affected valid laps against the total valid laps."""
    th = thresholds or RecurrenceThresholds()
    admissible = [r for r in records if not r.excluded]
    excluded_count = len(records) - len(admissible)
    first = records[0] if records else CornerObservationRecord()
    affected_laps = {r.lap_number for r in admissible
                     if r.lap_number is not None and r.occurred_on_lap}
    affected = len(affected_laps)
    events = sum(max(1, r.event_count) for r in admissible)
    episodes = sum(max(1, r.episode_count) for r in admissible)
    denom = max(total_valid_laps, affected)
    ratio = round(affected / denom, 4) if denom else 0.0

    if total_valid_laps < th.min_clean_laps_for_persistence:
        cls = RecurrenceClass.ISOLATED if affected else RecurrenceClass.STRENGTH
        rationale = R_BELOW_MIN_LAPS
        confidence = "low"
    elif not admissible:
        cls = RecurrenceClass.STRENGTH
        rationale = R_ALL_EXCLUDED
        confidence = "low"
    else:
        cls = th.classify(affected, total_valid_laps)
        if cls in (RecurrenceClass.RECURRING, RecurrenceClass.STRONGLY_RECURRING):
            rationale = R_REPEATABLE
        elif affected <= 1:
            rationale = R_ISOLATED_ONE_LAP
        else:
            rationale = "emerging_pattern"
        confidence = ("high" if total_valid_laps >= 5 and affected >= 3 else
                      "medium" if total_valid_laps >= th.min_clean_laps_for_persistence
                      else "low")

    return RecurrenceResult(
        segment_id=first.segment_id, corner_name=first.corner_name,
        phase=first.phase.value, issue_type=first.issue_type, axle=first.axle,
        classification=cls, affected_valid_laps=affected,
        total_valid_laps=total_valid_laps, recurrence_ratio=ratio,
        min_threshold=th.recurring_min, confidence=confidence, event_count=events,
        episode_count=episodes, excluded_count=excluded_count,
        rationale_code=rationale, source_lap_numbers=tuple(sorted(affected_laps)))


def aggregate_corner_evidence(
    records: Sequence[CornerObservationRecord],
    *,
    total_valid_laps: int,
    valid_lap_numbers: Optional[Sequence[int]] = None,
    thresholds: Optional[RecurrenceThresholds] = None,
) -> Tuple[RecurrenceResult, ...]:
    """Group canonical observations by (segment, phase, issue, axle) and classify
    recurrence per group. Only observations on VALID laps are counted; different
    corners / phases / axles never aggregate together."""
    valid_set = set(valid_lap_numbers) if valid_lap_numbers is not None else None
    groups: dict = {}
    for r in records:
        if valid_set is not None and r.lap_number is not None \
                and r.lap_number not in valid_set:
            continue                       # evidence from a rejected lap never counts
        groups.setdefault(r.group_key(), []).append(r)
    out = [classify_recurrence(recs, total_valid_laps=total_valid_laps,
                               thresholds=thresholds)
           for _, recs in sorted(groups.items())]
    return tuple(out)


def to_phase3_observations(
    records: Sequence[CornerObservationRecord],
    *,
    total_valid_laps: int,
    valid_lap_numbers: Optional[Sequence[int]] = None,
    thresholds: Optional[RecurrenceThresholds] = None,
) -> Tuple[CornerObservation, ...]:
    """Convert canonical observations → Phase 3 ``CornerObservation`` tuples (the
    exact shape `evaluate_setup_experiment` consumes). One per corner+phase+issue+
    axle group; ``affected_laps`` = distinct affected valid laps, ``clean_laps`` =
    total valid laps, ``event_count`` = admissible events."""
    aggs = aggregate_corner_evidence(
        records, total_valid_laps=total_valid_laps,
        valid_lap_numbers=valid_lap_numbers, thresholds=thresholds)
    # corner_name lookup (first record per group that has one)
    name_by_seg = {}
    for r in records:
        if r.segment_id and r.corner_name and r.segment_id not in name_by_seg:
            name_by_seg[r.segment_id] = r.corner_name
    out = []
    for a in aggs:
        out.append(CornerObservation(
            segment_id=a.segment_id,
            corner_name=name_by_seg.get(a.segment_id, a.corner_name or a.segment_id),
            phase=a.phase, issue_type=a.issue_type,
            affected_laps=a.affected_valid_laps, clean_laps=a.total_valid_laps,
            event_count=a.event_count, samples=a.total_valid_laps))
    return tuple(out)
