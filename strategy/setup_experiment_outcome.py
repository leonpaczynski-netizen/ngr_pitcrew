"""Setup Experiment Outcome — pure deterministic closed-loop evaluation.

Engineering Brain Phase 3. Judges a Phase 2 setup experiment against measured
test evidence and produces an immutable engineering outcome, WITHOUT new physics,
new setup rules, auto-apply or auto-rollback.

Doctrine
--------
A setup change is NOT successful merely because the driver completed laps, lap
time improved once, one positive feeling was reported, one symptom disappeared,
or the apply produced no error. An experiment is judged against: its persisted
hypothesis, targeted symptoms, persisted success/failure criteria, protected-good
behaviours, valid repeatable telemetry, driver feedback, the parent baseline, and
uncertainty/confounders. **The system prefers an honest inconclusive outcome over
a fabricated conclusion.**

Purity
------
Qt-free, DB-free, UI-free, network-free, AI-free; never raises for ordinary
missing-evidence conditions. It COMPOSES existing deterministic authorities
rather than reinventing them:
  * clean-lap window semantics: ``data/recommendation_scoring.py`` (LapWindow;
    the orchestrator builds windows via ``aggregate_lap_window``);
  * repeatability classes: ``strategy/practice_pattern_analysis.RecurrenceThresholds``
    (isolated / emerging / recurring / strongly_recurring);
  * verdict vocabulary: improved / worsened / neutral / insufficient_data;
  * driver-feedback flags: parsed deterministically upstream (no generative text).

This module owns ONLY the outcome decision logic + typed models. The Phase 1
``scope_fingerprint`` remains the authoritative identity; this module never
recomputes it.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from enum import Enum
from statistics import median as _median, pstdev as _pstdev
from typing import Mapping, Optional, Sequence, Tuple

from strategy.practice_pattern_analysis import RecurrenceClass, RecurrenceThresholds


OUTCOME_EVAL_VERSION = "setup_outcome_v1"

# Default decision thresholds (deterministic; documented). Whole-lap median deltas
# are in milliseconds; positive = slower (worse).
CONFIRM_CONFIDENCE_THRESHOLD = 0.5
LAPTIME_IMPROVE_MS = -200        # median lap materially faster
LAPTIME_REGRESS_MS = 300         # median lap materially slower
CONSISTENCY_REGRESS_MS = 250     # lap-time stdev materially worse
MIN_VALID_LAPS_DEFAULT = 3       # falls back to protocol.min_clean_laps when set


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class OutcomeStatus(str, Enum):
    CONFIRMED_IMPROVEMENT = "confirmed_improvement"
    PARTIAL_IMPROVEMENT = "partial_improvement"
    NO_MEANINGFUL_CHANGE = "no_meaningful_change"
    REGRESSION = "regression"
    CONFOUNDED = "confounded"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class CriterionVerdict(str, Enum):
    MET = "met"
    PARTIALLY_MET = "partially_met"
    NOT_MET = "not_met"
    REGRESSED = "regressed"
    UNMEASURABLE = "unmeasurable"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class ProtectedVerdict(str, Enum):
    PRESERVED = "preserved"
    MINOR_REGRESSION = "minor_regression"
    MATERIAL_REGRESSION = "material_regression"
    UNMEASURABLE = "unmeasurable"


class CornerVerdict(str, Enum):
    IMPROVED = "improved"
    UNCHANGED = "unchanged"
    REGRESSED = "regressed"
    UNMEASURABLE = "unmeasurable"


class AssociationStatus(str, Enum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    MISMATCH = "mismatch"
    UNRESOLVED = "unresolved"


class DriverTelemetryAgreement(str, Enum):
    AGREE = "agree"
    PARTIAL = "partial"
    DISAGREE = "disagree"
    NO_REVIEW = "no_review"
    INVALID_REVIEW = "invalid_review"


class NextAction(str, Enum):
    RETAIN = "retain"
    RETAIN_SUCCESSFUL_DIRECTION = "retain_successful_direction"
    REVERT_TO_PARENT = "revert_to_parent"
    REPEAT_MORE_LAPS = "repeat_more_laps"
    ISOLATE_FIELD = "isolate_field"
    REDUCE_MAGNITUDE = "reduce_magnitude"
    TEST_OPPOSITE = "test_opposite_direction"
    PROTECT_WINDOW = "protect_working_window"


class LearningStrength(str, Enum):
    LOCKOUT = "lockout"
    CAUTION = "caution"
    NONE = "none"


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


def confidence_level_for(score: float) -> ConfidenceLevel:
    if score >= 0.7:
        return ConfidenceLevel.HIGH
    if score >= 0.4:
        return ConfidenceLevel.MEDIUM
    return ConfidenceLevel.LOW


# --------------------------------------------------------------------------- #
# Input value objects (built by the orchestrator from DB evidence)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ExperimentSnapshot:
    """The Phase-2 experiment fields Phase-3 needs, decoupled from the DB row."""

    experiment_id: int
    scope_fingerprint: str = ""
    parent_setup_id: str = ""
    applied_checkpoint_id: str = ""
    status: str = ""
    car: str = ""
    track: str = ""
    layout_id: str = ""
    discipline: str = ""
    driver: str = ""
    rule_engine_version: str = ""
    primary_diagnosis: str = ""
    target_corners: Tuple[str, ...] = ()
    rollback_target: str = ""
    min_clean_laps: Optional[int] = None
    # actionable changes: each {field, from, to, direction, magnitude, subsystem,
    # rule_id, symptom}
    changes: Tuple[dict, ...] = ()
    # protected behaviours: each {behaviour, field, corners, baseline_confidence}
    protected_behaviours: Tuple[dict, ...] = ()
    # persisted criteria
    success_criteria: Tuple[str, ...] = ()
    failure_criteria: Tuple[str, ...] = ()

    @property
    def is_compound(self) -> bool:
        return len(self.changes) > 1

    @classmethod
    def from_experiment(cls, exp: Mapping) -> "ExperimentSnapshot":
        """Build from a get_setup_experiment(...) dict (Phase 2 shape)."""
        if not isinstance(exp, Mapping):
            return cls(experiment_id=0)
        tp = exp.get("test_protocol") or {}
        changes = tuple(
            {"field": c.get("field", ""), "from": c.get("from_value"),
             "to": c.get("to_value"), "direction": c.get("delta_direction", ""),
             "magnitude": c.get("delta_magnitude"), "subsystem": c.get("subsystem", ""),
             "rule_id": c.get("rule_id", ""), "symptom": c.get("symptom", "")}
            for c in (exp.get("changes") or [])
            if str(c.get("role", "")) in ("primary", "supporting"))
        protected = tuple(
            {"behaviour": p.get("description", ""), "field": p.get("field", ""),
             "corners": _json_list(p.get("corners_json")),
             "baseline_confidence": p.get("baseline_confidence", "")}
            for p in (exp.get("protected_behaviours") or []))
        hyp = _parse_json(exp.get("hypothesis_json"))
        return cls(
            experiment_id=int(exp.get("id") or 0),
            scope_fingerprint=str(exp.get("scope_fingerprint") or ""),
            parent_setup_id=str(exp.get("parent_setup_id") or ""),
            applied_checkpoint_id=str(exp.get("applied_checkpoint_id") or ""),
            status=str(exp.get("status") or ""),
            rule_engine_version=str(exp.get("rule_engine_version") or ""),
            primary_diagnosis=str(hyp.get("primary_diagnosis") or ""),
            target_corners=tuple(hyp.get("target_corners") or []),
            rollback_target=str(exp.get("rollback_target") or ""),
            min_clean_laps=_opt_int(tp.get("min_clean_laps")),
            changes=changes,
            protected_behaviours=protected,
            success_criteria=tuple(_json_list(tp.get("success_criteria_json"))),
            failure_criteria=tuple(_json_list(tp.get("failure_criteria_json"))),
        )


@dataclass(frozen=True)
class LapAggregate:
    """A minimal clean-lap window summary (mirrors recommendation_scoring.LapWindow)."""

    clean_count: int = 0
    compound: str = ""
    median_lap_ms: int = 0
    lap_time_stdev_ms: float = 0.0
    best_clean_ms: int = 0
    avg_lock_up: float = 0.0
    avg_wheelspin: float = 0.0
    avg_oversteer: float = 0.0
    avg_bottoming: float = 0.0
    avg_brake_consistency: float = 0.0
    incident_count: int = 0
    fuel_per_lap: float = 0.0

    @classmethod
    def from_lap_window(cls, w, lap_rows: Sequence[Mapping] = ()) -> "LapAggregate":
        """Adapt a recommendation_scoring.LapWindow (+ raw rows) into a LapAggregate."""
        times = []
        incidents = 0
        for r in (lap_rows or getattr(w, "laps", []) or []):
            try:
                if int(r.get("is_pit_lap") or 0) or int(r.get("is_out_lap") or 0):
                    continue
                t = int(r.get("lap_time_ms") or 0)
                if t > 0:
                    times.append(t)
                incidents += int(r.get("off_track_count") or 0)
            except Exception:
                continue
        med = int(_median(times)) if times else 0
        sd = float(_pstdev(times)) if len(times) >= 2 else 0.0
        return cls(
            clean_count=int(getattr(w, "clean_count", 0) or 0),
            compound=str(getattr(w, "compound", "") or ""),
            median_lap_ms=med,
            lap_time_stdev_ms=round(sd, 1),
            best_clean_ms=int(getattr(w, "best_clean_ms", 0) or 0),
            avg_lock_up=float(getattr(w, "avg_lock_up", 0.0) or 0.0),
            avg_wheelspin=float(getattr(w, "avg_wheelspin", 0.0) or 0.0),
            avg_oversteer=float(getattr(w, "avg_oversteer", 0.0) or 0.0),
            avg_bottoming=float(getattr(w, "avg_bottoming", 0.0) or 0.0),
            avg_brake_consistency=float(getattr(w, "avg_brake_consistency", 0.0) or 0.0),
            incident_count=incidents,
        )


@dataclass(frozen=True)
class CornerObservation:
    """One corner's issue evidence for one setup side (baseline OR test)."""

    segment_id: str
    corner_name: str = ""
    phase: str = ""
    issue_type: str = ""            # e.g. 'front_lock', 'rear_wheelspin'
    affected_laps: int = 0         # clean laps on which the issue occurred
    clean_laps: int = 0            # total clean laps observed at this corner
    event_count: int = 0
    samples: int = 0

    def key(self) -> Tuple[str, str]:
        return (self.segment_id or self.corner_name, self.issue_type)


@dataclass(frozen=True)
class DriverReviewInput:
    """Deterministically-parsed driver review (no generative text)."""

    feedback_id: str = ""
    refers_to_correct_setup: bool = True   # False ⇒ excluded as invalid evidence
    target_symptom_resolved: Optional[bool] = None   # None = not stated
    new_symptoms: Tuple[str, ...] = ()
    protected_status: Mapping[str, str] = field(default_factory=dict)  # field -> ok/regressed
    braking_confidence_improved: Optional[bool] = None
    driver_confidence: str = ""            # '' unknown
    notes: str = ""
    vs_previous: str = ""                  # better/worse/unchanged/''


@dataclass(frozen=True)
class ConfounderInput:
    """Fair-comparison blockers detected upstream."""

    weather_changed: bool = False
    compound_changed: bool = False
    fuel_regime_changed: bool = False
    damage_present: bool = False
    track_condition_changed: bool = False
    setup_identity_uncertain: bool = False
    notes: Tuple[str, ...] = ()

    @property
    def any(self) -> bool:
        return (self.weather_changed or self.compound_changed or
                self.fuel_regime_changed or self.damage_present or
                self.track_condition_changed or self.setup_identity_uncertain)

    def reasons(self) -> Tuple[str, ...]:
        r = []
        if self.weather_changed: r.append("weather changed between baseline and test")
        if self.compound_changed: r.append("tyre compound changed")
        if self.fuel_regime_changed: r.append("fuel regime changed")
        if self.damage_present: r.append("car damage present")
        if self.track_condition_changed: r.append("track condition changed")
        if self.setup_identity_uncertain: r.append("applied setup identity uncertain")
        return tuple(r) + tuple(self.notes)


# --------------------------------------------------------------------------- #
# Result value objects
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AssociationResult:
    status: AssociationStatus
    reasons: Tuple[str, ...] = ()
    candidate_experiment_ids: Tuple[int, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status == AssociationStatus.RESOLVED

    def to_dict(self) -> dict:
        return {"status": self.status.value, "reasons": list(self.reasons),
                "candidate_experiment_ids": list(self.candidate_experiment_ids)}


@dataclass(frozen=True)
class LapValidity:
    total_laps: int
    valid_laps: int
    rejected_laps: int
    rejection_reasons: Tuple[str, ...] = ()
    min_required: int = MIN_VALID_LAPS_DEFAULT
    repeatability_assessable: bool = False
    telemetry_completeness: str = ""       # full/partial/missing
    setup_identity_confidence: str = ""    # high/medium/low
    track_position_confidence: str = ""

    @property
    def sufficient(self) -> bool:
        return self.valid_laps >= self.min_required and self.repeatability_assessable

    def to_dict(self) -> dict:
        return {
            "total_laps": self.total_laps, "valid_laps": self.valid_laps,
            "rejected_laps": self.rejected_laps,
            "rejection_reasons": list(self.rejection_reasons),
            "min_required": self.min_required,
            "repeatability_assessable": self.repeatability_assessable,
            "telemetry_completeness": self.telemetry_completeness,
            "setup_identity_confidence": self.setup_identity_confidence,
            "track_position_confidence": self.track_position_confidence,
            "sufficient": self.sufficient,
        }


@dataclass(frozen=True)
class CriterionResult:
    criterion_id: str
    description: str
    metric: str
    expected: str
    observed: str
    sample_count: int
    confidence: str
    verdict: CriterionVerdict
    missing_evidence: str = ""
    rationale: str = ""
    is_target: bool = True

    def to_dict(self) -> dict:
        return {
            "criterion_id": self.criterion_id, "description": self.description,
            "metric": self.metric, "expected": self.expected,
            "observed": self.observed, "sample_count": self.sample_count,
            "confidence": self.confidence, "verdict": self.verdict.value,
            "missing_evidence": self.missing_evidence, "rationale": self.rationale,
            "is_target": self.is_target,
        }


@dataclass(frozen=True)
class ProtectedBehaviourResult:
    behaviour: str
    field: str
    baseline_state: str
    test_state: str
    comparison: str
    confidence: str
    verdict: ProtectedVerdict
    supporting_evidence: str = ""
    corners: Tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "behaviour": self.behaviour, "field": self.field,
            "baseline_state": self.baseline_state, "test_state": self.test_state,
            "comparison": self.comparison, "confidence": self.confidence,
            "verdict": self.verdict.value,
            "supporting_evidence": self.supporting_evidence,
            "corners": list(self.corners),
        }


@dataclass(frozen=True)
class CornerComparison:
    segment_id: str
    corner_name: str
    issue_type: str
    phase: str
    baseline_class: str
    test_class: str
    baseline_affected: int
    test_affected: int
    sample_count: int
    confidence: str
    verdict: CornerVerdict
    is_target: bool = False
    is_protected: bool = False

    def to_dict(self) -> dict:
        return {
            "segment_id": self.segment_id, "corner_name": self.corner_name,
            "issue_type": self.issue_type, "phase": self.phase,
            "baseline_class": self.baseline_class, "test_class": self.test_class,
            "baseline_affected": self.baseline_affected,
            "test_affected": self.test_affected, "sample_count": self.sample_count,
            "confidence": self.confidence, "verdict": self.verdict.value,
            "is_target": self.is_target, "is_protected": self.is_protected,
        }


@dataclass(frozen=True)
class WholeLapComparison:
    baseline_median_ms: int
    test_median_ms: int
    median_delta_ms: int
    baseline_stdev_ms: float
    test_stdev_ms: float
    consistency_delta_ms: float
    baseline_incidents: int
    test_incidents: int
    materially_faster: bool
    materially_slower: bool
    consistency_regressed: bool
    measurable: bool

    def to_dict(self) -> dict:
        return {
            "baseline_median_ms": self.baseline_median_ms,
            "test_median_ms": self.test_median_ms,
            "median_delta_ms": self.median_delta_ms,
            "baseline_stdev_ms": self.baseline_stdev_ms,
            "test_stdev_ms": self.test_stdev_ms,
            "consistency_delta_ms": self.consistency_delta_ms,
            "baseline_incidents": self.baseline_incidents,
            "test_incidents": self.test_incidents,
            "materially_faster": self.materially_faster,
            "materially_slower": self.materially_slower,
            "consistency_regressed": self.consistency_regressed,
            "measurable": self.measurable,
        }


@dataclass(frozen=True)
class FailedDirectionLearning:
    field: str
    from_value: Optional[str]
    to_value: Optional[str]
    direction: str
    magnitude: Optional[float]
    symptom: str
    strength: LearningStrength
    regression_observed: str
    affected_protected: str
    corners: Tuple[str, ...]
    confidence: str
    attribution_confidence: str
    evidence_count: int
    rule_id: str = ""

    def to_dict(self) -> dict:
        return {
            "field": self.field, "from_value": self.from_value,
            "to_value": self.to_value, "direction": self.direction,
            "magnitude": self.magnitude, "symptom": self.symptom,
            "strength": self.strength.value,
            "regression_observed": self.regression_observed,
            "affected_protected": self.affected_protected,
            "corners": list(self.corners), "confidence": self.confidence,
            "attribution_confidence": self.attribution_confidence,
            "evidence_count": self.evidence_count, "rule_id": self.rule_id,
        }


@dataclass(frozen=True)
class OutcomeInputs:
    """Everything the pure evaluator needs (gathered by the orchestrator)."""

    experiment: ExperimentSnapshot
    association: AssociationResult
    validity: LapValidity
    baseline: LapAggregate
    test: LapAggregate
    corner_baseline: Tuple[CornerObservation, ...] = ()
    corner_test: Tuple[CornerObservation, ...] = ()
    driver_review: Optional[DriverReviewInput] = None
    confounders: ConfounderInput = field(default_factory=ConfounderInput)
    test_session_id: Optional[str] = None
    test_run_id: Optional[str] = None
    thresholds: RecurrenceThresholds = field(default_factory=RecurrenceThresholds)
    confirm_confidence_threshold: float = CONFIRM_CONFIDENCE_THRESHOLD
    evidence_fingerprint: str = ""


@dataclass(frozen=True)
class SetupExperimentOutcome:
    """Immutable evaluated outcome aggregate."""

    experiment_id: int
    scope_fingerprint: str
    parent_setup_id: str
    applied_checkpoint_id: str
    test_session_id: Optional[str]
    test_run_id: Optional[str]
    eval_version: str
    status: OutcomeStatus
    confidence: float
    confidence_level: ConfidenceLevel
    evidence_completeness: str
    validity: LapValidity
    criteria: Tuple[CriterionResult, ...]
    protected: Tuple[ProtectedBehaviourResult, ...]
    corner_comparisons: Tuple[CornerComparison, ...]
    whole_lap: WholeLapComparison
    regressions: Tuple[str, ...]
    improvements: Tuple[str, ...]
    neutral_findings: Tuple[str, ...]
    confounders: Tuple[str, ...]
    missing_evidence: Tuple[str, ...]
    driver_agreement: DriverTelemetryAgreement
    driver_review_summary: str
    decision_rationale: str
    next_action: NextAction
    next_action_detail: str
    rollback_eligible: bool
    rollback_target: str
    learning_eligible: bool
    failed_directions: Tuple[FailedDirectionLearning, ...]
    idempotency_key: str

    def to_dict(self) -> dict:
        return {
            "experiment_id": self.experiment_id,
            "scope_fingerprint": self.scope_fingerprint,
            "parent_setup_id": self.parent_setup_id,
            "applied_checkpoint_id": self.applied_checkpoint_id,
            "test_session_id": self.test_session_id,
            "test_run_id": self.test_run_id, "eval_version": self.eval_version,
            "status": self.status.value, "confidence": self.confidence,
            "confidence_level": self.confidence_level.value,
            "evidence_completeness": self.evidence_completeness,
            "validity": self.validity.to_dict(),
            "criteria": [c.to_dict() for c in self.criteria],
            "protected": [p.to_dict() for p in self.protected],
            "corner_comparisons": [c.to_dict() for c in self.corner_comparisons],
            "whole_lap": self.whole_lap.to_dict(),
            "regressions": list(self.regressions),
            "improvements": list(self.improvements),
            "neutral_findings": list(self.neutral_findings),
            "confounders": list(self.confounders),
            "missing_evidence": list(self.missing_evidence),
            "driver_agreement": self.driver_agreement.value,
            "driver_review_summary": self.driver_review_summary,
            "decision_rationale": self.decision_rationale,
            "next_action": self.next_action.value,
            "next_action_detail": self.next_action_detail,
            "rollback_eligible": self.rollback_eligible,
            "rollback_target": self.rollback_target,
            "learning_eligible": self.learning_eligible,
            "failed_directions": [f.to_dict() for f in self.failed_directions],
            "idempotency_key": self.idempotency_key,
        }


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _parse_json(v) -> dict:
    if isinstance(v, Mapping):
        return dict(v)
    try:
        d = json.loads(v) if v else {}
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _json_list(v) -> list:
    if isinstance(v, (list, tuple)):
        return list(v)
    try:
        d = json.loads(v) if v else []
        return list(d) if isinstance(d, (list, tuple)) else []
    except Exception:
        return []


def _opt_int(v) -> Optional[int]:
    try:
        return None if v is None else int(v)
    except (TypeError, ValueError):
        return None


def _s(v) -> Optional[str]:
    return None if v is None else str(v)


# --------------------------------------------------------------------------- #
# Association resolver
# --------------------------------------------------------------------------- #
def resolve_experiment_evidence_association(
    experiment: ExperimentSnapshot,
    *,
    test_scope_fingerprint: str,
    test_checkpoint_id: str = "",
    test_session_started_after_apply: Optional[bool] = None,
    driver_feedback_setup_id: str = "",
    candidate_experiment_ids: Sequence[int] = (),
    has_parent_baseline: bool = True,
) -> AssociationResult:
    """Associate test evidence with an experiment through AUTHORITATIVE identity,
    never free-text coincidence. Returns an explicit ambiguous/mismatch/unresolved
    result rather than silently picking the newest experiment."""
    reasons = []
    cands = tuple(int(c) for c in candidate_experiment_ids
                  if int(c) != experiment.experiment_id)
    if cands:
        return AssociationResult(
            AssociationStatus.AMBIGUOUS,
            ("multiple plausible active experiments in this scope",),
            candidate_experiment_ids=tuple(sorted(
                (experiment.experiment_id, *cands))))

    if not experiment.scope_fingerprint or not test_scope_fingerprint:
        return AssociationResult(
            AssociationStatus.UNRESOLVED,
            ("missing canonical scope fingerprint on experiment or test evidence",))
    if experiment.scope_fingerprint != test_scope_fingerprint:
        return AssociationResult(
            AssociationStatus.MISMATCH,
            ("test evidence scope_fingerprint does not match the experiment "
             "(car/track/layout/driver mismatch)",))

    if (test_checkpoint_id and experiment.applied_checkpoint_id
            and test_checkpoint_id != experiment.applied_checkpoint_id):
        return AssociationResult(
            AssociationStatus.MISMATCH,
            ("applied setup checkpoint mismatch",))

    if test_session_started_after_apply is False:
        return AssociationResult(
            AssociationStatus.MISMATCH,
            ("test session was recorded BEFORE the setup was applied",))

    if not has_parent_baseline:
        return AssociationResult(
            AssociationStatus.UNRESOLVED,
            ("absent parent baseline for before/after comparison",))

    if (driver_feedback_setup_id and experiment.applied_checkpoint_id
            and driver_feedback_setup_id not in ("", experiment.applied_checkpoint_id,
                                                 experiment.parent_setup_id)):
        # feedback refers to a different setup — do not silently accept it
        reasons.append("driver feedback references a different setup (excluded)")

    return AssociationResult(AssociationStatus.RESOLVED, tuple(reasons),
                             candidate_experiment_ids=(experiment.experiment_id,))


# --------------------------------------------------------------------------- #
# Lap validity gate
# --------------------------------------------------------------------------- #
def evaluate_lap_validity(
    test: LapAggregate,
    *,
    total_laps: int,
    rejected_laps: int = 0,
    rejection_reasons: Sequence[str] = (),
    min_required: int = MIN_VALID_LAPS_DEFAULT,
    telemetry_completeness: str = "full",
    setup_identity_confidence: str = "high",
    track_position_confidence: str = "high",
) -> LapValidity:
    """Build a Phase-3 validity result. 'Valid laps' = clean laps (pit/out already
    excluded by the clean-lap window authority). Repeatability is assessable only
    when at least min_required valid laps exist."""
    valid = int(test.clean_count)
    reasons = tuple(rejection_reasons)
    if valid < min_required and "insufficient valid laps" not in reasons:
        reasons = reasons + (f"only {valid} valid laps (< {min_required} required)",)
    return LapValidity(
        total_laps=int(total_laps),
        valid_laps=valid,
        rejected_laps=int(rejected_laps if rejected_laps else max(0, total_laps - valid)),
        rejection_reasons=reasons,
        min_required=int(min_required),
        repeatability_assessable=valid >= min_required,
        telemetry_completeness=telemetry_completeness,
        setup_identity_confidence=setup_identity_confidence,
        track_position_confidence=track_position_confidence,
    )


# --------------------------------------------------------------------------- #
# Whole-lap + per-corner comparison
# --------------------------------------------------------------------------- #
def compare_whole_lap(baseline: LapAggregate, test: LapAggregate) -> WholeLapComparison:
    """Median-based whole-lap comparison (NEVER fastest-lap alone)."""
    measurable = baseline.median_lap_ms > 0 and test.median_lap_ms > 0
    delta = (test.median_lap_ms - baseline.median_lap_ms) if measurable else 0
    cons_delta = round(test.lap_time_stdev_ms - baseline.lap_time_stdev_ms, 1)
    return WholeLapComparison(
        baseline_median_ms=baseline.median_lap_ms,
        test_median_ms=test.median_lap_ms,
        median_delta_ms=delta,
        baseline_stdev_ms=baseline.lap_time_stdev_ms,
        test_stdev_ms=test.lap_time_stdev_ms,
        consistency_delta_ms=cons_delta,
        baseline_incidents=baseline.incident_count,
        test_incidents=test.incident_count,
        materially_faster=measurable and delta <= LAPTIME_IMPROVE_MS,
        materially_slower=measurable and delta >= LAPTIME_REGRESS_MS,
        consistency_regressed=measurable and cons_delta >= CONSISTENCY_REGRESS_MS,
        measurable=measurable,
    )


def _classify(obs: CornerObservation, thresholds: RecurrenceThresholds) -> RecurrenceClass:
    return thresholds.classify(obs.affected_laps, obs.clean_laps or obs.affected_laps)


def compare_corners(
    baseline: Sequence[CornerObservation],
    test: Sequence[CornerObservation],
    *,
    thresholds: RecurrenceThresholds,
    target_corners: Sequence[str] = (),
    protected_corners: Sequence[str] = (),
    min_clean_laps: int = 3,
) -> Tuple[CornerComparison, ...]:
    """Per-corner before/after comparison keyed on (segment/corner, issue_type).

    Only compares corners present with compatible issue evidence on BOTH sides, or
    a NEW issue appearing only in test (potential regression). Uses recurrence
    classes so a repeatable same-corner pattern outweighs one isolated bad lap.
    """
    b_by = {o.key(): o for o in baseline}
    t_by = {o.key(): o for o in test}
    targets = {str(c).lower() for c in target_corners}
    protecteds = {str(c).lower() for c in protected_corners}
    out = []
    for key in sorted(set(b_by) | set(t_by)):
        b = b_by.get(key)
        t = t_by.get(key)
        seg = (b or t).segment_id
        name = (b or t).corner_name
        issue = (b or t).issue_type
        phase = (b or t).phase
        b_cls = _classify(b, thresholds) if b else RecurrenceClass.STRENGTH
        t_cls = _classify(t, thresholds) if t else RecurrenceClass.STRENGTH
        b_aff = b.affected_laps if b else 0
        t_aff = t.affected_laps if t else 0
        samples = (t.clean_laps if t else 0) or (b.clean_laps if b else 0)
        assessable = samples >= min_clean_laps
        confidence = "high" if samples >= 5 else ("medium" if samples >= 3 else "low")
        if not assessable:
            verdict = CornerVerdict.UNMEASURABLE
        else:
            b_auth = thresholds.is_authorable(b_cls)
            t_auth = thresholds.is_authorable(t_cls)
            if b_auth and not t_auth:
                verdict = CornerVerdict.IMPROVED
            elif t_auth and not b_auth:
                verdict = CornerVerdict.REGRESSED
            elif t_aff < b_aff and b_auth:
                verdict = CornerVerdict.IMPROVED
            elif t_aff > b_aff and t_auth:
                verdict = CornerVerdict.REGRESSED
            else:
                verdict = CornerVerdict.UNCHANGED
        is_target = (str(seg).lower() in targets or str(name).lower() in targets)
        is_protected = (str(seg).lower() in protecteds or str(name).lower() in protecteds)
        out.append(CornerComparison(
            segment_id=seg, corner_name=name, issue_type=issue, phase=phase,
            baseline_class=b_cls.value, test_class=t_cls.value,
            baseline_affected=b_aff, test_affected=t_aff, sample_count=samples,
            confidence=confidence, verdict=verdict, is_target=is_target,
            is_protected=is_protected))
    return tuple(out)


# --------------------------------------------------------------------------- #
# Criteria + protected-behaviour evaluation
# --------------------------------------------------------------------------- #
def evaluate_criteria(
    experiment: ExperimentSnapshot,
    corner_comparisons: Sequence[CornerComparison],
    whole_lap: WholeLapComparison,
    validity: LapValidity,
) -> Tuple[CriterionResult, ...]:
    """Evaluate the persisted success criteria + the primary-diagnosis target.

    The primary target criterion is judged by the per-corner recurrence of the
    diagnosed symptom at the target corners (NOT by general lap time)."""
    results = []
    target_cmps = [c for c in corner_comparisons if c.is_target] or \
        [c for c in corner_comparisons if c.verdict != CornerVerdict.UNMEASURABLE]

    # Primary target criterion — did the diagnosed symptom improve repeatably?
    if experiment.primary_diagnosis:
        if not validity.repeatability_assessable:
            verdict = CriterionVerdict.INSUFFICIENT_EVIDENCE
            observed = "not enough valid laps"
            samples = validity.valid_laps
        elif not target_cmps:
            verdict = CriterionVerdict.UNMEASURABLE
            observed = "no per-corner evidence at the target"
            samples = 0
        else:
            improved = [c for c in target_cmps if c.verdict == CornerVerdict.IMPROVED]
            regressed = [c for c in target_cmps if c.verdict == CornerVerdict.REGRESSED]
            samples = max((c.sample_count for c in target_cmps), default=0)
            if regressed:
                verdict = CriterionVerdict.REGRESSED
                observed = f"symptom worse at {regressed[0].corner_name or regressed[0].segment_id}"
            elif improved and not [c for c in target_cmps
                                   if c.verdict == CornerVerdict.UNCHANGED]:
                verdict = CriterionVerdict.MET
                observed = "diagnosed symptom improved repeatably at every target corner"
            elif improved:
                verdict = CriterionVerdict.PARTIALLY_MET
                observed = "diagnosed symptom improved at some target corners"
            else:
                verdict = CriterionVerdict.NOT_MET
                observed = "diagnosed symptom unchanged"
        results.append(CriterionResult(
            criterion_id="primary_target",
            description=f"resolve {experiment.primary_diagnosis}",
            metric="per-corner recurrence class",
            expected="target symptom reduced repeatably",
            observed=observed, sample_count=samples,
            confidence=("high" if validity.valid_laps >= 5 else
                        ("medium" if validity.repeatability_assessable else "low")),
            verdict=verdict, is_target=True,
            rationale="fastest lap alone cannot prove a symptom fix; recurrence governs"))

    # Persisted success criteria (free-text) — measured where a metric is derivable.
    for i, crit in enumerate(experiment.success_criteria):
        results.append(_evaluate_text_criterion(
            f"success_{i}", str(crit), corner_comparisons, whole_lap, validity))
    return tuple(results)


def _evaluate_text_criterion(cid, text, corner_comparisons, whole_lap, validity):
    """Evaluate one persisted free-text SUCCESS criterion. These are SUPPORTING
    criteria (is_target=False) — the diagnosed symptom is the single primary
    target — so a partially-met support criterion does not by itself block a
    confirmed target fix, but a REGRESSED one still triggers regression."""
    low = text.lower()
    metric, expected = "n/a", text
    if not validity.repeatability_assessable:
        v, obs, samples, conf = (CriterionVerdict.INSUFFICIENT_EVIDENCE,
                                 "insufficient valid laps", validity.valid_laps, "low")
    elif any(k in low for k in ("lap time", "laptime", "pace", "faster")):
        metric = "median lap"
        if not whole_lap.measurable:
            v, obs, samples, conf = (CriterionVerdict.UNMEASURABLE,
                                     "no lap-time evidence", 0, "low")
        else:
            obs = f"median {whole_lap.median_delta_ms:+d}ms"
            samples, conf = validity.valid_laps, "medium"
            if whole_lap.materially_slower:
                v = CriterionVerdict.REGRESSED
            elif whole_lap.materially_faster:
                v = CriterionVerdict.MET
            else:
                v = CriterionVerdict.NOT_MET
    else:
        metric = "per-corner recurrence"
        relevant = [c for c in corner_comparisons
                    if c.verdict != CornerVerdict.UNMEASURABLE]
        if not relevant:
            v, obs, samples, conf = (CriterionVerdict.UNMEASURABLE,
                                     "no corner evidence", 0, "low")
        else:
            samples = max((c.sample_count for c in relevant), default=0)
            conf = "medium"
            changed = [c for c in relevant if c.verdict != CornerVerdict.UNCHANGED]
            if any(c.verdict == CornerVerdict.REGRESSED for c in relevant):
                v = CriterionVerdict.REGRESSED
            elif changed and all(c.verdict == CornerVerdict.IMPROVED for c in changed):
                v = CriterionVerdict.MET
            elif any(c.verdict == CornerVerdict.IMPROVED for c in relevant):
                v = CriterionVerdict.PARTIALLY_MET
            else:
                v = CriterionVerdict.NOT_MET
            obs = v.value
    return CriterionResult(cid, text, metric, expected, obs, samples, conf, v,
                           is_target=False)


def evaluate_protected_behaviours(
    experiment: ExperimentSnapshot,
    corner_comparisons: Sequence[CornerComparison],
    baseline: LapAggregate,
    test: LapAggregate,
    validity: LapValidity,
    driver_review: Optional[DriverReviewInput] = None,
) -> Tuple[ProtectedBehaviourResult, ...]:
    """For each persisted protected behaviour, compare baseline vs test evidence
    and classify preservation. A NEW recurring issue at a protected corner (or a
    protected field's characteristic worsening) is a MATERIAL regression."""
    results = []
    for pb in experiment.protected_behaviours:
        behaviour = str(pb.get("behaviour") or "")
        field_id = str(pb.get("field") or "")
        corners = tuple(str(c) for c in (pb.get("corners") or []))
        # Match ONLY this behaviour's own corners (never every protected corner),
        # so an unrelated corner's regression cannot be blamed on this behaviour.
        if corners:
            relevant = [c for c in corner_comparisons
                        if c.corner_name in corners or c.segment_id in corners]
        else:
            relevant = []
        if not relevant:
            # fall back to the global handling proxy for this behaviour
            verdict, base_state, test_state, comp, conf = _protected_from_global(
                behaviour, field_id, baseline, test, validity)
            results.append(ProtectedBehaviourResult(
                behaviour=behaviour, field=field_id, baseline_state=base_state,
                test_state=test_state, comparison=comp, confidence=conf,
                verdict=verdict, supporting_evidence="global handling proxy"))
            continue
        regressed = [c for c in relevant if c.verdict == CornerVerdict.REGRESSED]
        if regressed:
            strong = any(c.test_class == RecurrenceClass.STRONGLY_RECURRING.value
                         or c.test_class == RecurrenceClass.RECURRING.value
                         for c in regressed)
            verdict = (ProtectedVerdict.MATERIAL_REGRESSION if strong
                       else ProtectedVerdict.MINOR_REGRESSION)
            base_state = "confirmed good"
            test_state = f"regressed at {regressed[0].corner_name or regressed[0].segment_id}"
            comp = "worse"
        else:
            verdict = ProtectedVerdict.PRESERVED
            base_state = "confirmed good"
            test_state = "preserved"
            comp = "unchanged"
        results.append(ProtectedBehaviourResult(
            behaviour=behaviour, field=field_id, baseline_state=base_state,
            test_state=test_state, comparison=comp,
            confidence="high" if validity.valid_laps >= 5 else "medium",
            verdict=verdict, supporting_evidence="per-corner comparison",
            corners=tuple(c.corner_name or c.segment_id for c in relevant)))
    return tuple(results)


_PROTECTED_METRIC = {
    "traction": "avg_wheelspin", "wheelspin": "avg_wheelspin",
    "rear traction": "avg_wheelspin", "braking": "avg_lock_up",
    "braking stability": "avg_lock_up", "rotation": "avg_oversteer",
    "mid-corner": "avg_oversteer", "platform": "avg_bottoming",
    "kerb": "avg_bottoming",
}


def _protected_from_global(behaviour, field_id, baseline, test, validity):
    metric = None
    low = (behaviour or "").lower()
    for kw, m in _PROTECTED_METRIC.items():
        if kw in low:
            metric = m
            break
    if metric is None or not validity.repeatability_assessable:
        return (ProtectedVerdict.UNMEASURABLE, "unknown", "unknown", "unmeasurable", "low")
    b = getattr(baseline, metric, 0.0)
    t = getattr(test, metric, 0.0)
    # lower is better for all these event-rate proxies
    if t <= b + 1e-9:
        return (ProtectedVerdict.PRESERVED, f"{b:.2f}/lap", f"{t:.2f}/lap", "unchanged/better", "medium")
    worse_ratio = (t - b) / (b if b > 0 else 1.0)
    if worse_ratio >= 1.0 and t >= 1.0:
        return (ProtectedVerdict.MATERIAL_REGRESSION, f"{b:.2f}/lap", f"{t:.2f}/lap", "worse", "medium")
    return (ProtectedVerdict.MINOR_REGRESSION, f"{b:.2f}/lap", f"{t:.2f}/lap", "slightly worse", "medium")


# --------------------------------------------------------------------------- #
# Driver / telemetry arbitration
# --------------------------------------------------------------------------- #
def arbitrate_driver_vs_telemetry(
    review: Optional[DriverReviewInput],
    target_met: bool,
    target_regressed: bool,
) -> Tuple[DriverTelemetryAgreement, str]:
    """Preserve disagreement — driver feedback never silently overrules telemetry."""
    if review is None:
        return DriverTelemetryAgreement.NO_REVIEW, "no driver review provided"
    if not review.refers_to_correct_setup:
        return (DriverTelemetryAgreement.INVALID_REVIEW,
                "driver feedback refers to the wrong setup/session — excluded")
    driver_positive = (review.target_symptom_resolved is True
                       or review.braking_confidence_improved is True
                       or review.vs_previous == "better")
    driver_negative = (review.target_symptom_resolved is False
                       or bool(review.new_symptoms)
                       or review.vs_previous == "worse")
    if target_met and driver_positive:
        return DriverTelemetryAgreement.AGREE, "telemetry and driver both positive"
    if target_regressed and driver_negative:
        return DriverTelemetryAgreement.AGREE, "telemetry and driver both negative"
    if driver_positive and target_regressed:
        return DriverTelemetryAgreement.DISAGREE, "driver positive but telemetry regressed"
    if driver_negative and target_met:
        return DriverTelemetryAgreement.DISAGREE, "telemetry positive but driver negative"
    if driver_positive or driver_negative:
        return DriverTelemetryAgreement.PARTIAL, "driver and telemetry partly aligned"
    return DriverTelemetryAgreement.NO_REVIEW, "driver review present but non-committal"


# --------------------------------------------------------------------------- #
# Confidence
# --------------------------------------------------------------------------- #
def _confidence_score(validity: LapValidity,
                      agreement: DriverTelemetryAgreement,
                      target_samples: int) -> float:
    conf = 1.0
    for laps in (validity.valid_laps,):
        conf -= 0.1 * max(0, 6 - laps)
    if target_samples and target_samples < 3:
        conf -= 0.2
    if agreement == DriverTelemetryAgreement.DISAGREE:
        conf -= 0.25
    elif agreement == DriverTelemetryAgreement.AGREE:
        conf += 0.1
    elif agreement in (DriverTelemetryAgreement.NO_REVIEW,
                       DriverTelemetryAgreement.INVALID_REVIEW):
        conf -= 0.05
    if validity.telemetry_completeness == "partial":
        conf -= 0.1
    return max(0.0, min(1.0, round(conf, 4)))


# --------------------------------------------------------------------------- #
# Failed-direction learning + next action
# --------------------------------------------------------------------------- #
def build_failed_direction_learning(
    experiment: ExperimentSnapshot,
    status: OutcomeStatus,
    corner_comparisons: Sequence[CornerComparison],
    protected: Sequence[ProtectedBehaviourResult],
    validity: LapValidity,
    confidence: float,
) -> Tuple[FailedDirectionLearning, ...]:
    """Only a CONFIRMED REGRESSION on VALID evidence yields learning. Strong,
    single-field, repeatable evidence → LOCKOUT; weaker or compound-attributed →
    CAUTION. Never from an invalid/confounded/insufficient test; never global."""
    if status != OutcomeStatus.REGRESSION or not validity.sufficient:
        return ()
    regressing_corners = [c for c in corner_comparisons
                          if c.verdict == CornerVerdict.REGRESSED]
    material_protected = [p for p in protected
                          if p.verdict == ProtectedVerdict.MATERIAL_REGRESSION]
    strong_evidence = confidence >= 0.6 and (
        any(c.test_class in (RecurrenceClass.STRONGLY_RECURRING.value,
                             RecurrenceClass.RECURRING.value)
            for c in regressing_corners) or bool(material_protected))
    compound = experiment.is_compound
    attribution = "low" if compound else "high"
    strength = LearningStrength.LOCKOUT if (strong_evidence and not compound) \
        else LearningStrength.CAUTION
    symptom = experiment.primary_diagnosis
    affected = "; ".join(p.behaviour for p in material_protected)
    corners = tuple(c.corner_name or c.segment_id for c in regressing_corners)
    evidence_count = max((c.test_affected for c in regressing_corners), default=0) \
        or validity.valid_laps
    out = []
    for ch in experiment.changes:
        out.append(FailedDirectionLearning(
            field=str(ch.get("field") or ""),
            from_value=_s(ch.get("from")), to_value=_s(ch.get("to")),
            direction=str(ch.get("direction") or ""),
            magnitude=ch.get("magnitude"),
            symptom=symptom, strength=strength,
            regression_observed=(f"regression at {', '.join(corners)}"
                                 if corners else (affected or "regression")),
            affected_protected=affected, corners=corners,
            confidence=("high" if confidence >= 0.6 else "medium"),
            attribution_confidence=attribution, evidence_count=evidence_count,
            rule_id=str(ch.get("rule_id") or "")))
    return tuple(out)


def build_next_action(
    experiment: ExperimentSnapshot, status: OutcomeStatus,
) -> Tuple[NextAction, str]:
    compound = experiment.is_compound
    if status == OutcomeStatus.CONFIRMED_IMPROVEMENT:
        return NextAction.RETAIN, "retain the setup and protect the new working window"
    if status == OutcomeStatus.PARTIAL_IMPROVEMENT:
        if compound:
            return (NextAction.ISOLATE_FIELD,
                    "isolate one field to attribute the partial gain")
        return (NextAction.REPEAT_MORE_LAPS,
                "useful direction — repeat with more valid laps to confirm")
    if status == OutcomeStatus.NO_MEANINGFUL_CHANGE:
        return (NextAction.REVERT_TO_PARENT,
                "no meaningful change — revert to parent or test a larger/opposite change")
    if status == OutcomeStatus.REGRESSION:
        return (NextAction.REVERT_TO_PARENT,
                "revert to the parent setup; consider testing the opposite direction")
    if status == OutcomeStatus.CONFOUNDED:
        return (NextAction.REPEAT_MORE_LAPS,
                "control the confounder (weather/tyre/fuel) and retest")
    return (NextAction.REPEAT_MORE_LAPS,
            "gather more valid laps / required evidence before concluding")


# --------------------------------------------------------------------------- #
# The deterministic decision + top-level evaluator
# --------------------------------------------------------------------------- #
def decide_outcome(
    association: AssociationResult,
    validity: LapValidity,
    criteria: Sequence[CriterionResult],
    protected: Sequence[ProtectedBehaviourResult],
    corner_comparisons: Sequence[CornerComparison],
    whole_lap: WholeLapComparison,
    confounders: ConfounderInput,
    agreement: DriverTelemetryAgreement,
    confidence: float,
    confirm_threshold: float,
) -> Tuple[OutcomeStatus, str]:
    """Explicit deterministic outcome decision table."""
    if not association.ok:
        return (OutcomeStatus.INSUFFICIENT_EVIDENCE,
                f"evidence association {association.status.value}: "
                + "; ".join(association.reasons))
    if confounders.any:
        return (OutcomeStatus.CONFOUNDED,
                "; ".join(confounders.reasons()))
    if not validity.sufficient:
        return (OutcomeStatus.INSUFFICIENT_EVIDENCE,
                "; ".join(validity.rejection_reasons)
                or "insufficient valid laps to assess repeatability")

    target = [c for c in criteria if c.is_target]
    target_met = bool(target) and all(c.verdict == CriterionVerdict.MET for c in target)
    target_partial = any(c.verdict in (CriterionVerdict.MET,
                                        CriterionVerdict.PARTIALLY_MET) for c in criteria)
    target_regressed = any(c.verdict == CriterionVerdict.REGRESSED for c in target)
    any_criterion_regressed = any(c.verdict == CriterionVerdict.REGRESSED for c in criteria)
    protected_material = any(p.verdict == ProtectedVerdict.MATERIAL_REGRESSION
                             for p in protected)
    protected_minor = any(p.verdict == ProtectedVerdict.MINOR_REGRESSION
                          for p in protected)
    new_recurring = any(c.verdict == CornerVerdict.REGRESSED and not c.is_target
                        for c in corner_comparisons)

    # --- Regression precedence (safety-first) --------------------------------
    if target_regressed or protected_material or any_criterion_regressed \
            or new_recurring or whole_lap.materially_slower:
        reasons = []
        if target_regressed or any_criterion_regressed:
            reasons.append("a criterion regressed")
        if protected_material:
            reasons.append("a protected behaviour materially regressed")
        if new_recurring:
            reasons.append("a new repeatable issue appeared")
        if whole_lap.materially_slower:
            reasons.append(f"median lap {whole_lap.median_delta_ms:+d}ms slower")
        return OutcomeStatus.REGRESSION, "; ".join(reasons)

    # --- Confirmed improvement ----------------------------------------------
    if (target_met and not protected_minor and confidence >= confirm_threshold
            and agreement != DriverTelemetryAgreement.DISAGREE):
        return (OutcomeStatus.CONFIRMED_IMPROVEMENT,
                "target symptom improved repeatably with no protected regression")

    # --- Partial improvement -------------------------------------------------
    if target_met or target_partial or protected_minor:
        why = []
        if target_met and confidence < confirm_threshold:
            why.append("target met but confidence below threshold")
        if target_partial and not target_met:
            why.append("some but not all targets improved")
        if protected_minor:
            why.append("a minor protected behaviour worsened")
        if agreement == DriverTelemetryAgreement.DISAGREE:
            why.append("driver and telemetry disagree")
        return OutcomeStatus.PARTIAL_IMPROVEMENT, "; ".join(why) or "partial improvement"

    # --- No meaningful change ------------------------------------------------
    measurable_change = (whole_lap.materially_faster or whole_lap.materially_slower
                         or any(c.verdict in (CornerVerdict.IMPROVED,
                                              CornerVerdict.REGRESSED)
                                for c in corner_comparisons))
    if not measurable_change:
        return (OutcomeStatus.NO_MEANINGFUL_CHANGE,
                "valid test; no target or protected behaviour changed materially")
    return (OutcomeStatus.INSUFFICIENT_EVIDENCE,
            "changes present but not sufficient to conclude an engineering verdict")


def _evidence_completeness(validity: LapValidity,
                           corner_comparisons: Sequence[CornerComparison],
                           review: Optional[DriverReviewInput]) -> str:
    have_corner = any(c.verdict != CornerVerdict.UNMEASURABLE for c in corner_comparisons)
    have_review = review is not None and review.refers_to_correct_setup
    if validity.sufficient and have_corner and have_review:
        return "complete"
    if validity.valid_laps == 0:
        return "missing"
    return "partial"


def evaluate_outcome(inputs: OutcomeInputs) -> SetupExperimentOutcome:
    """Top-level PURE evaluator: deterministic, order-independent, never raises for
    ordinary missing-evidence conditions. Same inputs → identical outcome."""
    exp = inputs.experiment
    min_req = exp.min_clean_laps or inputs.validity.min_required or MIN_VALID_LAPS_DEFAULT
    validity = replace(inputs.validity, min_required=min_req,
                       repeatability_assessable=inputs.validity.valid_laps >= min_req)

    whole_lap = compare_whole_lap(inputs.baseline, inputs.test)
    protected_corners = tuple(
        cc for pb in exp.protected_behaviours for cc in (pb.get("corners") or []))
    corner_cmps = compare_corners(
        inputs.corner_baseline, inputs.corner_test,
        thresholds=inputs.thresholds, target_corners=exp.target_corners,
        protected_corners=protected_corners, min_clean_laps=min_req)
    criteria = evaluate_criteria(exp, corner_cmps, whole_lap, validity)
    protected = evaluate_protected_behaviours(
        exp, corner_cmps, inputs.baseline, inputs.test, validity, inputs.driver_review)

    target_crit = [c for c in criteria if c.is_target]
    target_met = bool(target_crit) and all(
        c.verdict == CriterionVerdict.MET for c in target_crit)
    target_regressed = any(c.verdict == CriterionVerdict.REGRESSED for c in target_crit)
    agreement, agree_note = arbitrate_driver_vs_telemetry(
        inputs.driver_review, target_met, target_regressed)
    target_samples = max((c.sample_count for c in target_crit), default=0)
    confidence = _confidence_score(validity, agreement, target_samples)

    status, rationale = decide_outcome(
        inputs.association, validity, criteria, protected, corner_cmps, whole_lap,
        inputs.confounders, agreement, confidence, inputs.confirm_confidence_threshold)

    failed_dirs = build_failed_direction_learning(
        exp, status, corner_cmps, protected, validity, confidence)
    next_action, next_detail = build_next_action(exp, status)

    improvements = tuple(
        f"{c.corner_name or c.segment_id}: {c.issue_type} improved"
        for c in corner_cmps if c.verdict == CornerVerdict.IMPROVED)
    regressions = tuple(
        f"{c.corner_name or c.segment_id}: {c.issue_type} regressed"
        for c in corner_cmps if c.verdict == CornerVerdict.REGRESSED) + tuple(
        f"protected '{p.behaviour}' materially regressed"
        for p in protected if p.verdict == ProtectedVerdict.MATERIAL_REGRESSION)
    neutral = tuple(
        f"{c.corner_name or c.segment_id}: {c.issue_type} unchanged"
        for c in corner_cmps if c.verdict == CornerVerdict.UNCHANGED)
    missing = tuple(validity.rejection_reasons) + (
        () if any(c.verdict != CornerVerdict.UNMEASURABLE for c in corner_cmps)
        else ("no usable per-corner evidence",)) + (
        () if inputs.driver_review is not None else ("no driver review",))

    rollback_eligible = status in (OutcomeStatus.REGRESSION,
                                   OutcomeStatus.NO_MEANINGFUL_CHANGE)
    learning_eligible = bool(failed_dirs)

    return SetupExperimentOutcome(
        experiment_id=exp.experiment_id,
        scope_fingerprint=exp.scope_fingerprint,
        parent_setup_id=exp.parent_setup_id,
        applied_checkpoint_id=exp.applied_checkpoint_id,
        test_session_id=inputs.test_session_id, test_run_id=inputs.test_run_id,
        eval_version=OUTCOME_EVAL_VERSION, status=status, confidence=confidence,
        confidence_level=confidence_level_for(confidence),
        evidence_completeness=_evidence_completeness(validity, corner_cmps,
                                                     inputs.driver_review),
        validity=validity, criteria=criteria, protected=protected,
        corner_comparisons=corner_cmps, whole_lap=whole_lap,
        regressions=regressions, improvements=improvements, neutral_findings=neutral,
        confounders=inputs.confounders.reasons(), missing_evidence=missing,
        driver_agreement=agreement, driver_review_summary=agree_note,
        decision_rationale=rationale, next_action=next_action,
        next_action_detail=next_detail, rollback_eligible=rollback_eligible,
        rollback_target=exp.rollback_target, learning_eligible=learning_eligible,
        failed_directions=failed_dirs,
        idempotency_key=compute_outcome_idempotency_key(inputs))


def compute_outcome_idempotency_key(inputs: OutcomeInputs) -> str:
    """Deterministic key. Same experiment + checkpoint + test session + evidence
    fingerprint → same key (idempotent). Genuinely new evidence → new key (a
    superseding evaluation). Never a timestamp."""
    payload = {
        "v": OUTCOME_EVAL_VERSION,
        "experiment_id": inputs.experiment.experiment_id,
        "checkpoint": inputs.experiment.applied_checkpoint_id,
        "test_session": inputs.test_session_id or "",
        "test_run": inputs.test_run_id or "",
        "evidence": inputs.evidence_fingerprint
        or _default_evidence_fingerprint(inputs),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return f"{OUTCOME_EVAL_VERSION}:{hashlib.sha256(raw).hexdigest()[:20]}"


def _default_evidence_fingerprint(inputs: OutcomeInputs) -> str:
    parts = [
        inputs.validity.valid_laps, inputs.baseline.median_lap_ms,
        inputs.test.median_lap_ms,
        round(inputs.baseline.avg_lock_up, 3), round(inputs.test.avg_lock_up, 3),
        round(inputs.baseline.avg_wheelspin, 3), round(inputs.test.avg_wheelspin, 3),
    ]
    for o in sorted(inputs.corner_test, key=lambda c: c.key()):
        parts.append((o.segment_id, o.issue_type, o.affected_laps, o.clean_laps))
    raw = json.dumps(parts, sort_keys=True, ensure_ascii=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()[:16]
