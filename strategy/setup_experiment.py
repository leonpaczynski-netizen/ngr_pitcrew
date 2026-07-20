"""Setup Experiment domain — the pure model of a controlled, reversible setup test.

Engineering Brain Phase 2 (builds on Phase 1's canonical engineering context).

Doctrine
--------
A setup recommendation is not merely text: it is a controlled, reversible
engineering experiment —

    Observe → Diagnose → Form hypothesis → Define protected behaviours
    → Propose minimum effective changes → Persist experiment → Apply setup
    → Gather test evidence → Evaluate outcome (Phase 3)

Every experiment belongs to the Phase 1 canonical engineering context through its
``scope_fingerprint``. Unknown evidence stays unknown — this module never invents
corner attribution, confidence, expected gains, applied values, driver outcomes,
telemetry evidence or rollback success.

Purity
------
Qt-free, DB-free, UI-free, network-free, AI-free. It imports ONLY the pure Phase 1
identity module (``data.engineering_context_key``) to obtain — never to recompute —
the canonical context fingerprints via the Phase 1 API. It must not import PyQt, UI
modules, SessionDB, setup-Apply modules, or any network/AI library.

Immutability
------------
After creation, an experiment's hypothesis, proposed changes, evidence snapshot,
test protocol, expected effects, protected behaviours, confidence and rollback
target are frozen. Corrections are represented by append-only amendments, state
history, a superseding experiment, or administrative invalidation with a reason —
never by mutating history to make a later outcome look cleaner.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Mapping, Optional, Sequence, Tuple

from data.engineering_context_key import (
    EngineeringContextResolution, ResolutionStatus, FINGERPRINT_VERSION,
    build_engineering_context,
)


# --------------------------------------------------------------------------- #
# Schema version
# --------------------------------------------------------------------------- #
EXPERIMENT_SCHEMA_VERSION = "setup_experiment_v1"


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class ExperimentStatus(str, Enum):
    """Lifecycle of a setup experiment. Transitions are deterministic + validated;
    there is NO automatic progression based on assumptions."""

    DRAFT = "draft"                       # created, not yet released for apply
    READY_FOR_APPLY = "ready_for_apply"   # actionable changes validated, awaiting driver
    APPLIED = "applied"                   # confirmed applied in GT7 (needs a checkpoint link)
    TEST_IN_PROGRESS = "test_in_progress"  # gathering on-track evidence
    READY_FOR_REVIEW = "ready_for_review"  # has test evidence / driver review
    COMPLETED = "completed"               # Phase 3 outcome recorded (unavailable until Phase 3)
    REJECTED = "rejected"                 # reviewed and judged a regression / bad direction
    REVERTED = "reverted"                 # rolled back to the parent / proven setup
    CANCELLED = "cancelled"               # administratively withdrawn before completion
    INVALID = "invalid"                   # administratively invalidated (with a reason)


# Terminal states — no outgoing transition except to themselves (idempotent).
_TERMINAL: frozenset = frozenset({
    ExperimentStatus.COMPLETED, ExperimentStatus.REJECTED,
    ExperimentStatus.REVERTED, ExperimentStatus.CANCELLED,
    ExperimentStatus.INVALID,
})


class ChangeRole(str, Enum):
    """The role a proposed change plays in the minimum-effective intervention."""

    PRIMARY = "primary"          # directly treats the dominant diagnosis
    SUPPORTING = "supporting"    # coupled change required for the primary to work
    PROTECTED = "protected"      # a no-change field the engine deliberately preserved
    DEFERRED = "deferred"        # an unresolved diagnosis intentionally NOT actioned yet


class ChangeKind(str, Enum):
    DIAGNOSTIC = "diagnostic"        # a controlled test to disambiguate evidence
    PERFORMANCE = "performance"      # a change expected to improve lap performance


class EvidencePhase(str, Enum):
    """When a piece of evidence entered the ledger."""

    BASELINE = "baseline"
    DIAGNOSIS = "diagnosis"
    RECOMMENDATION = "recommendation"     # captured at experiment creation
    APPLY_VERIFICATION = "apply_verification"
    TEST = "test"
    DRIVER_REVIEW = "driver_review"
    OUTCOME = "outcome"                    # Phase 3


class EvidenceStance(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    NEUTRAL = "neutral"


class HandlingPhase(str, Enum):
    """Targeted handling phases a hypothesis can address."""

    ENTRY = "entry"
    MID_CORNER = "mid_corner"
    EXIT = "exit"
    BRAKING = "braking"
    TRACTION = "traction"
    PLATFORM = "platform"
    GEARING = "gearing"
    TYRE_FUEL = "tyre_fuel"


class AppliedMatchState(str, Enum):
    """Result of comparing proposed setup values to what was applied in GT7."""

    MATCH = "match"                 # every proposed field present and equal (within tolerance)
    PARTIAL_MATCH = "partial_match"  # some proposed fields matched, others missing (none differ)
    MISMATCH = "mismatch"           # at least one proposed field present with a different value
    UNVERIFIABLE = "unverifiable"   # no proposed values, or no applied values to compare


# --------------------------------------------------------------------------- #
# Value objects
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ExperimentChange:
    """One structured proposed setup delta (source-of-truth, not rendered text)."""

    field: str                          # canonical field id
    subsystem: str = ""                 # e.g. 'lsd', 'aero', 'gearbox', 'ride_height'
    from_value: Optional[str] = None    # previous value (None = unknown)
    to_value: Optional[str] = None      # proposed value (None = unknown/no-change)
    delta_direction: str = ""           # 'increase' | 'decrease' | 'change' | '' (unknown)
    delta_magnitude: Optional[float] = None
    unit: str = ""
    rationale: str = ""
    expected_effect: str = ""
    side_effects: str = ""
    contraindications_checked: str = ""
    role: ChangeRole = ChangeRole.PRIMARY
    kind: Optional[ChangeKind] = None
    order: int = 0
    rule_id: str = ""                   # source rule / solver / proven-history ref
    source_label: str = ""
    symptom: str = ""
    risk_level: str = ""
    confidence_level: str = ""

    def to_dict(self) -> dict:
        return {
            "field": self.field, "subsystem": self.subsystem,
            "from_value": self.from_value, "to_value": self.to_value,
            "delta_direction": self.delta_direction,
            "delta_magnitude": self.delta_magnitude, "unit": self.unit,
            "rationale": self.rationale, "expected_effect": self.expected_effect,
            "side_effects": self.side_effects,
            "contraindications_checked": self.contraindications_checked,
            "role": self.role.value,
            "kind": self.kind.value if self.kind else None,
            "order": self.order, "rule_id": self.rule_id,
            "source_label": self.source_label, "symptom": self.symptom,
            "risk_level": self.risk_level, "confidence_level": self.confidence_level,
        }


@dataclass(frozen=True)
class ProtectedBehaviour:
    """A confirmed-good behaviour the change set must not degrade."""

    description: str
    field: str = ""                     # the protected field id, when there is one
    source_evidence: str = ""
    corners: Tuple[str, ...] = ()
    baseline_confidence: str = ""
    regression_threshold: str = ""      # where known; '' = unknown

    def to_dict(self) -> dict:
        return {
            "description": self.description, "field": self.field,
            "source_evidence": self.source_evidence, "corners": list(self.corners),
            "baseline_confidence": self.baseline_confidence,
            "regression_threshold": self.regression_threshold,
        }


@dataclass(frozen=True)
class TestProtocol:
    """The deterministic on-track test plan for the experiment."""

    min_clean_laps: Optional[int] = None
    preferred_clean_laps: Optional[int] = None
    warmup_exclusion_laps: Optional[int] = None
    tyre_compound: str = ""
    fuel_state: str = ""
    weather_assumption: str = ""
    target_corners: Tuple[str, ...] = ()
    metrics_to_observe: Tuple[str, ...] = ()
    driver_questions: Tuple[str, ...] = ()
    success_criteria: Tuple[str, ...] = ()
    failure_criteria: Tuple[str, ...] = ()
    confounders: Tuple[str, ...] = ()
    rollback_target: str = ""           # the setup to restore on failure
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "min_clean_laps": self.min_clean_laps,
            "preferred_clean_laps": self.preferred_clean_laps,
            "warmup_exclusion_laps": self.warmup_exclusion_laps,
            "tyre_compound": self.tyre_compound, "fuel_state": self.fuel_state,
            "weather_assumption": self.weather_assumption,
            "target_corners": list(self.target_corners),
            "metrics_to_observe": list(self.metrics_to_observe),
            "driver_questions": list(self.driver_questions),
            "success_criteria": list(self.success_criteria),
            "failure_criteria": list(self.failure_criteria),
            "confounders": list(self.confounders),
            "rollback_target": self.rollback_target, "notes": self.notes,
        }


@dataclass(frozen=True)
class ExperimentEvidence:
    """One immutable evidence reference + structured summary (never a telemetry blob)."""

    evidence_type: str                  # e.g. 'driver_feedback', 'corner_slip', 'lineage_outcome'
    phase: EvidencePhase
    source_table: str = ""
    source_id: str = ""                 # source record id where available
    summary: str = ""
    confidence: str = ""
    provenance: str = ""
    corner: str = ""
    lap: Optional[int] = None
    session_id: Optional[str] = None
    run_id: Optional[str] = None
    stance: EvidenceStance = EvidenceStance.NEUTRAL

    def to_dict(self) -> dict:
        return {
            "evidence_type": self.evidence_type, "phase": self.phase.value,
            "source_table": self.source_table, "source_id": self.source_id,
            "summary": self.summary, "confidence": self.confidence,
            "provenance": self.provenance, "corner": self.corner, "lap": self.lap,
            "session_id": self.session_id, "run_id": self.run_id,
            "stance": self.stance.value,
        }


@dataclass(frozen=True)
class ExperimentHypothesis:
    """The engineering hypothesis behind the experiment."""

    statement: str = ""
    primary_diagnosis: str = ""
    secondary_diagnoses: Tuple[str, ...] = ()
    handling_phases: Tuple[str, ...] = ()      # HandlingPhase values
    target_corners: Tuple[str, ...] = ()
    supporting_evidence: Tuple[str, ...] = ()
    contradicting_evidence: Tuple[str, ...] = ()
    assumptions: Tuple[str, ...] = ()
    unresolved_evidence: Tuple[str, ...] = ()
    confidence: str = ""                       # '' = unknown

    def to_dict(self) -> dict:
        return {
            "statement": self.statement,
            "primary_diagnosis": self.primary_diagnosis,
            "secondary_diagnoses": list(self.secondary_diagnoses),
            "handling_phases": list(self.handling_phases),
            "target_corners": list(self.target_corners),
            "supporting_evidence": list(self.supporting_evidence),
            "contradicting_evidence": list(self.contradicting_evidence),
            "assumptions": list(self.assumptions),
            "unresolved_evidence": list(self.unresolved_evidence),
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class StateTransition:
    """One append-only lifecycle transition record."""

    from_status: str
    to_status: str
    reason: str = ""
    source: str = ""                    # 'analyse' | 'apply' | 'admin' | ...
    at: str = ""                        # timestamp (stamped by the persistence layer)

    def to_dict(self) -> dict:
        return {
            "from_status": self.from_status, "to_status": self.to_status,
            "reason": self.reason, "source": self.source, "at": self.at,
        }


# --------------------------------------------------------------------------- #
# The experiment aggregate
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SetupExperiment:
    """An immutable setup experiment aggregate (creation-time snapshot).

    The `experiment_id` / `created_at` are assigned by the persistence layer; in
    the pure model they may be empty until persisted. Identity for de-duplication
    is the deterministic `idempotency_key` (never a timestamp).
    """

    # -- identity + canonical context ------------------------------------- #
    schema_version: str = EXPERIMENT_SCHEMA_VERSION
    scope_fingerprint: str = ""
    context_fingerprint: str = ""
    context_schema_version: str = FINGERPRINT_VERSION
    context_status: str = ""
    context_unresolved: Tuple[str, ...] = ()
    context_warnings: Tuple[str, ...] = ()
    label: str = ""                      # concise human-facing label

    # -- recommendation provenance ---------------------------------------- #
    recommendation_source: str = ""      # e.g. 'analyse' | 'baseline'
    recommendation_status: str = ""      # the APPROVED_STATUSES value
    rule_engine_version: str = ""
    driver_profile_version: str = ""

    # -- setup identity linkage ------------------------------------------- #
    parent_setup_id: str = ""
    proposed_setup_id: str = ""
    applied_checkpoint_id: str = ""      # filled when applied (state history records it)
    lineage_id: str = ""
    session_id: str = ""
    run_id: str = ""

    # -- engineering content ---------------------------------------------- #
    status: ExperimentStatus = ExperimentStatus.DRAFT
    hypothesis: ExperimentHypothesis = field(default_factory=ExperimentHypothesis)
    changes: Tuple[ExperimentChange, ...] = ()
    protected_behaviours: Tuple[ProtectedBehaviour, ...] = ()
    test_protocol: TestProtocol = field(default_factory=TestProtocol)
    evidence: Tuple[ExperimentEvidence, ...] = ()
    deferred_diagnoses: Tuple[str, ...] = ()
    rollback_target: str = ""
    idempotency_key: str = ""

    # -- convenience ------------------------------------------------------ #
    @property
    def actionable_changes(self) -> Tuple[ExperimentChange, ...]:
        return tuple(c for c in self.changes
                     if c.role in (ChangeRole.PRIMARY, ChangeRole.SUPPORTING))

    @property
    def proposed_values(self) -> dict:
        """{field: to_value} for actionable changes (the values a driver applies)."""
        out = {}
        for c in self.actionable_changes:
            if c.to_value is not None:
                out[c.field] = c.to_value
        return out

    @property
    def is_actionable(self) -> bool:
        return bool(self.actionable_changes)

    def with_context(self, resolution: EngineeringContextResolution,
                     ) -> "SetupExperiment":
        """Return a copy stamped with the Phase 1 canonical context (via Phase 1 API)."""
        return replace(
            self,
            scope_fingerprint=resolution.scope_fingerprint,
            context_fingerprint=resolution.fingerprint,
            context_schema_version=resolution.fingerprint_version,
            context_status=resolution.status.value,
            context_unresolved=tuple(resolution.unresolved),
            context_warnings=tuple(resolution.warnings),
        )

    def with_idempotency_key(self) -> "SetupExperiment":
        return replace(self, idempotency_key=compute_idempotency_key(self))

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "scope_fingerprint": self.scope_fingerprint,
            "context_fingerprint": self.context_fingerprint,
            "context_schema_version": self.context_schema_version,
            "context_status": self.context_status,
            "context_unresolved": list(self.context_unresolved),
            "context_warnings": list(self.context_warnings),
            "label": self.label,
            "recommendation_source": self.recommendation_source,
            "recommendation_status": self.recommendation_status,
            "rule_engine_version": self.rule_engine_version,
            "driver_profile_version": self.driver_profile_version,
            "parent_setup_id": self.parent_setup_id,
            "proposed_setup_id": self.proposed_setup_id,
            "applied_checkpoint_id": self.applied_checkpoint_id,
            "lineage_id": self.lineage_id, "session_id": self.session_id,
            "run_id": self.run_id, "status": self.status.value,
            "hypothesis": self.hypothesis.to_dict(),
            "changes": [c.to_dict() for c in self.changes],
            "protected_behaviours": [p.to_dict() for p in self.protected_behaviours],
            "test_protocol": self.test_protocol.to_dict(),
            "evidence": [e.to_dict() for e in self.evidence],
            "deferred_diagnoses": list(self.deferred_diagnoses),
            "rollback_target": self.rollback_target,
            "idempotency_key": self.idempotency_key,
        }


# --------------------------------------------------------------------------- #
# Idempotency
# --------------------------------------------------------------------------- #
def compute_idempotency_key(exp: SetupExperiment) -> str:
    """Deterministic de-duplication key. NEVER uses a timestamp.

    Repeated rendering / tab-switching / re-reading the SAME recommendation
    reproduces the SAME key, so no duplicate experiment is created. Keyed by:
    schema, canonical scope, parent setup, recommendation source + engine
    version, and the ORDERED (field, to_value) tuples of the actionable changes.
    """
    ordered_changes = sorted(
        (c.field, "" if c.to_value is None else str(c.to_value))
        for c in exp.actionable_changes
    )
    payload = {
        "schema": exp.schema_version,
        "scope": exp.scope_fingerprint,
        "parent": exp.parent_setup_id,
        "source": exp.recommendation_source,
        "rule_engine_version": exp.rule_engine_version,
        "rec_status": exp.recommendation_status,
        "changes": ordered_changes,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return f"{EXPERIMENT_SCHEMA_VERSION}:{hashlib.sha256(raw).hexdigest()[:20]}"


# --------------------------------------------------------------------------- #
# State-transition validation
# --------------------------------------------------------------------------- #
# Allowed transitions (structural). Guard predicates enforce the honesty rules
# (e.g. APPLIED needs a checkpoint) on top of this graph.
VALID_TRANSITIONS: dict = {
    ExperimentStatus.DRAFT: frozenset({
        ExperimentStatus.READY_FOR_APPLY, ExperimentStatus.CANCELLED,
        ExperimentStatus.INVALID,
    }),
    ExperimentStatus.READY_FOR_APPLY: frozenset({
        ExperimentStatus.APPLIED, ExperimentStatus.CANCELLED,
        ExperimentStatus.INVALID,
    }),
    ExperimentStatus.APPLIED: frozenset({
        ExperimentStatus.TEST_IN_PROGRESS, ExperimentStatus.READY_FOR_REVIEW,
        ExperimentStatus.REVERTED, ExperimentStatus.INVALID,
        ExperimentStatus.CANCELLED,
    }),
    ExperimentStatus.TEST_IN_PROGRESS: frozenset({
        ExperimentStatus.READY_FOR_REVIEW, ExperimentStatus.REVERTED,
        ExperimentStatus.INVALID, ExperimentStatus.CANCELLED,
    }),
    ExperimentStatus.READY_FOR_REVIEW: frozenset({
        ExperimentStatus.COMPLETED, ExperimentStatus.REJECTED,
        ExperimentStatus.REVERTED, ExperimentStatus.INVALID,
    }),
    # Terminal states: no outgoing transitions.
    ExperimentStatus.COMPLETED: frozenset(),
    ExperimentStatus.REJECTED: frozenset(),
    ExperimentStatus.REVERTED: frozenset(),
    ExperimentStatus.CANCELLED: frozenset(),
    ExperimentStatus.INVALID: frozenset(),
}


@dataclass(frozen=True)
class TransitionCheck:
    ok: bool
    reason: str = ""


def can_transition(from_status: ExperimentStatus,
                   to_status: ExperimentStatus) -> bool:
    """Pure structural check against the transition graph."""
    return to_status in VALID_TRANSITIONS.get(from_status, frozenset())


def validate_transition(
    from_status: ExperimentStatus,
    to_status: ExperimentStatus,
    *,
    has_actionable_changes: bool = True,
    has_applied_checkpoint: bool = False,
    has_test_evidence: bool = False,
    has_outcome_record: bool = False,
) -> TransitionCheck:
    """Deterministic, honest transition validation.

    Honesty gates layered on the structural graph:
      * DRAFT → READY_FOR_APPLY needs actionable changes;
      * → APPLIED needs an applied-setup checkpoint link;
      * → READY_FOR_REVIEW needs test evidence (or an explicit driver review);
      * → COMPLETED needs a Phase-3 outcome record (unavailable until Phase 3).
    """
    if from_status == to_status:
        return TransitionCheck(False, "no-op transition")
    if not can_transition(from_status, to_status):
        return TransitionCheck(
            False, f"{from_status.value} → {to_status.value} is not permitted")
    if to_status == ExperimentStatus.READY_FOR_APPLY and not has_actionable_changes:
        return TransitionCheck(
            False, "cannot become READY_FOR_APPLY without actionable changes")
    if to_status == ExperimentStatus.APPLIED and not has_applied_checkpoint:
        return TransitionCheck(
            False, "cannot become APPLIED without an applied setup checkpoint link")
    if to_status == ExperimentStatus.READY_FOR_REVIEW and not has_test_evidence:
        return TransitionCheck(
            False, "cannot become READY_FOR_REVIEW without test evidence / driver review")
    if to_status == ExperimentStatus.COMPLETED and not has_outcome_record:
        return TransitionCheck(
            False, "cannot become COMPLETED without a Phase 3 outcome record")
    return TransitionCheck(True)


def is_terminal(status: ExperimentStatus) -> bool:
    return status in _TERMINAL


# --------------------------------------------------------------------------- #
# Applied-value verification
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class FieldComparison:
    field: str
    proposed: Optional[str]
    applied: Optional[str]
    matched: bool
    present: bool

    def to_dict(self) -> dict:
        return {"field": self.field, "proposed": self.proposed,
                "applied": self.applied, "matched": self.matched,
                "present": self.present}


@dataclass(frozen=True)
class AppliedComparison:
    state: AppliedMatchState
    fields: Tuple[FieldComparison, ...] = ()
    missing_fields: Tuple[str, ...] = ()
    mismatched_fields: Tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "state": self.state.value,
            "fields": [f.to_dict() for f in self.fields],
            "missing_fields": list(self.missing_fields),
            "mismatched_fields": list(self.mismatched_fields),
        }


def _values_equal(a, b, *, tol: float) -> bool:
    """Compare two setup values honestly.

    Numeric-vs-numeric compares within ``tol`` (float epsilon / rounding). Any
    non-numeric value compares by normalised string equality. Never coerces one
    unit to another — same field id only (the caller guarantees that).
    """
    if a is None or b is None:
        return False
    fa = _as_float(a)
    fb = _as_float(b)
    if fa is not None and fb is not None:
        return abs(fa - fb) <= tol
    return str(a).strip() == str(b).strip()


def _as_float(v) -> Optional[float]:
    try:
        if isinstance(v, bool):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def compare_proposed_vs_applied(
    proposed: Mapping,
    applied: Mapping,
    *,
    tolerance: float = 1e-6,
) -> AppliedComparison:
    """Deterministically compare proposed setup values to what was applied in GT7.

    * MATCH        — every proposed field is present in ``applied`` and equal.
    * PARTIAL_MATCH — some proposed fields matched, others are missing; none differ.
    * MISMATCH     — at least one proposed field is present with a different value.
    * UNVERIFIABLE — there are no proposed values, or no applied values to compare.

    The original recommendation is never altered; missing fields are reported, not
    silently coerced.
    """
    proposed = dict(proposed or {})
    applied = dict(applied or {})
    if not proposed or not applied:
        return AppliedComparison(AppliedMatchState.UNVERIFIABLE)

    comparisons = []
    missing = []
    mismatched = []
    any_matched = False
    for fld in sorted(proposed.keys()):
        pv = proposed[fld]
        if fld not in applied:
            comparisons.append(FieldComparison(fld, _s(pv), None, False, False))
            missing.append(fld)
            continue
        av = applied[fld]
        eq = _values_equal(pv, av, tol=tolerance)
        comparisons.append(FieldComparison(fld, _s(pv), _s(av), eq, True))
        if eq:
            any_matched = True
        else:
            mismatched.append(fld)

    if mismatched:
        state = AppliedMatchState.MISMATCH
    elif missing:
        state = (AppliedMatchState.PARTIAL_MATCH if any_matched
                 else AppliedMatchState.UNVERIFIABLE)
    else:
        state = AppliedMatchState.MATCH
    return AppliedComparison(state, tuple(comparisons), tuple(missing),
                             tuple(mismatched))


def _s(v) -> Optional[str]:
    return None if v is None else str(v)


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ExperimentValidation:
    ok: bool
    errors: Tuple[str, ...] = ()


def validate_experiment(exp: SetupExperiment) -> ExperimentValidation:
    """Validate a to-be-persisted experiment. Honest about missing context."""
    errors = []
    if exp.schema_version != EXPERIMENT_SCHEMA_VERSION:
        errors.append(f"unexpected schema_version {exp.schema_version!r}")
    if not exp.scope_fingerprint:
        errors.append("missing canonical scope_fingerprint (Phase 1 context required)")
    if not exp.idempotency_key:
        errors.append("missing idempotency_key")
    if not exp.is_actionable:
        errors.append("no actionable changes — not a valid actionable experiment")
    # duplicate field ids among actionable changes would break apply comparison
    seen = set()
    for c in exp.actionable_changes:
        if c.field in seen:
            errors.append(f"duplicate actionable change for field {c.field!r}")
        seen.add(c.field)
    return ExperimentValidation(not errors, tuple(errors))


# --------------------------------------------------------------------------- #
# Builder — parsed recommendation _data dict → SetupExperiment
# --------------------------------------------------------------------------- #
def _subsystem_for(field_id: str) -> str:
    f = (field_id or "").lower()
    for key, sub in (
        ("lsd", "lsd"), ("diff", "lsd"), ("aero", "aero"), ("downforce", "aero"),
        ("wing", "aero"), ("spring", "suspension"), ("damper", "suspension"),
        ("arb", "suspension"), ("anti_roll", "suspension"), ("ride_height", "ride_height"),
        ("camber", "alignment"), ("toe", "alignment"), ("brake", "brakes"),
        ("gear", "gearbox"), ("final_drive", "gearbox"), ("ballast", "mass"),
        ("tyre", "tyres"), ("pressure", "tyres"),
    ):
        if key in f:
            return sub
    return ""


def _delta_direction(from_v, to_v) -> Tuple[str, Optional[float]]:
    a = _as_float(from_v)
    b = _as_float(to_v)
    if a is None or b is None:
        return ("change" if (from_v is not None and to_v is not None
                             and str(from_v) != str(to_v)) else "", None)
    if b > a:
        return "increase", round(b - a, 6)
    if b < a:
        return "decrease", round(a - b, 6)
    return "none", 0.0


def _change_from_raw(raw: Mapping, order: int, role: ChangeRole) -> ExperimentChange:
    fld = str(raw.get("field") or "")
    from_v = raw.get("from")
    to_v = raw.get("to_clamped", raw.get("to"))
    direction, magnitude = _delta_direction(from_v, to_v)
    evid = raw.get("evidence")
    if isinstance(evid, (list, tuple)):
        expected_effect = "; ".join(str(x) for x in evid)
    else:
        expected_effect = str(evid or "")
    return ExperimentChange(
        field=fld,
        subsystem=_subsystem_for(fld),
        from_value=None if from_v in (None, "") else str(from_v),
        to_value=None if to_v is None else str(to_v),
        delta_direction=direction,
        delta_magnitude=magnitude,
        rationale=str(raw.get("rationale") or raw.get("why") or ""),
        expected_effect=expected_effect,
        contraindications_checked="; ".join(
            str(x) for x in (raw.get("rejected_alternatives") or [])),
        role=role,
        order=order,
        rule_id=str(raw.get("rule_id") or ""),
        source_label=str(raw.get("source_label") or ""),
        symptom=str(raw.get("symptom") or ""),
        risk_level=str(raw.get("risk_level") or ""),
        confidence_level=str(raw.get("confidence_level") or ""),
    )


def _protected_from_data(data: Mapping) -> Tuple[ProtectedBehaviour, ...]:
    out = []
    for fld in (data.get("protected_fields") or []):
        out.append(ProtectedBehaviour(
            description=f"preserve {str(fld).replace('_', ' ')}",
            field=str(fld),
            source_evidence="rule-engine protected field",
            baseline_confidence="confirmed",
        ))
    return tuple(out)


def _test_protocol_from_data(data: Mapping) -> TestProtocol:
    seq = data.get("test_sequence") or {}
    stages = seq.get("stages") if isinstance(seq, Mapping) else None
    success = []
    rollback = ""
    if isinstance(stages, (list, tuple)):
        for st in stages:
            if isinstance(st, Mapping):
                sc = st.get("success_criterion")
                if sc:
                    success.append(str(sc))
                if not rollback and st.get("rollback"):
                    rollback = str(st.get("rollback"))
    rb = data.get("rollback")
    rollback_target = ""
    if isinstance(rb, Mapping):
        rollback_target = str(rb.get("label") or rb.get("target") or "")
    corners = _target_corners_from_data(data)
    return TestProtocol(
        target_corners=corners,
        success_criteria=tuple(success),
        rollback_target=rollback_target or rollback,
        notes=str(seq.get("note") or "") if isinstance(seq, Mapping) else "",
    )


def _target_corners_from_data(data: Mapping) -> Tuple[str, ...]:
    corners = []
    diag = data.get("diagnosis") or {}
    cd = data.get("corner_diagnosis") or {}
    for src in (diag, cd):
        if isinstance(src, Mapping):
            for key in ("target_corners", "corners"):
                v = src.get(key)
                if isinstance(v, (list, tuple)):
                    corners.extend(str(x) for x in v)
    # dedupe, preserve order
    seen = set()
    out = []
    for c in corners:
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return tuple(out)


def _hypothesis_from_data(data: Mapping) -> ExperimentHypothesis:
    diag = data.get("diagnosis") or {}
    primary = str(diag.get("dominant_problem") or data.get("primary_issue") or "")
    secondary = tuple(str(x) for x in (diag.get("secondary_problems") or []))
    phases = _handling_phases_from_diagnosis(diag)
    return ExperimentHypothesis(
        statement=str(data.get("analysis") or "")[:2000],
        primary_diagnosis=primary,
        secondary_diagnoses=secondary,
        handling_phases=phases,
        target_corners=_target_corners_from_data(data),
        confidence=str((data.get("confidence") or {}).get("overall") or "")
        if isinstance(data.get("confidence"), Mapping) else "",
    )


_PHASE_KEYWORDS = {
    HandlingPhase.ENTRY.value: ("entry", "turn-in", "turn_in"),
    HandlingPhase.MID_CORNER.value: ("mid", "apex"),
    HandlingPhase.EXIT.value: ("exit",),
    HandlingPhase.BRAKING.value: ("brak", "lock"),
    HandlingPhase.TRACTION.value: ("traction", "wheelspin", "spin", "power down"),
    HandlingPhase.PLATFORM.value: ("bottom", "platform", "ride height", "kerb"),
    HandlingPhase.GEARING.value: ("gear", "final drive"),
    HandlingPhase.TYRE_FUEL.value: ("tyre", "tire", "fuel"),
}


def _handling_phases_from_diagnosis(diag: Mapping) -> Tuple[str, ...]:
    text_parts = [str(diag.get("dominant_problem") or "")]
    text_parts.extend(str(x) for x in (diag.get("secondary_problems") or []))
    blob = " ".join(text_parts).lower()
    phases = []
    for phase, kws in _PHASE_KEYWORDS.items():
        if any(kw in blob for kw in kws):
            phases.append(phase)
    return tuple(phases)


def build_experiment_from_recommendation(
    data: Mapping,
    *,
    recommendation_source: str = "analyse",
    car_id=None,
    track: str = "",
    layout_id: str = "",
    discipline: str = "",
    driver_id=None,
    gt7_version=None,
    event_id=None,
    config_id: str = "",
    parent_setup_id: str = "",
    proposed_setup_id: str = "",
    lineage_id="",
    session_id=None,
    run_id=None,
    label: str = "",
    context_resolution: Optional[EngineeringContextResolution] = None,
) -> Optional[SetupExperiment]:
    """Map a parsed recommendation ``_data`` dict → an immutable SetupExperiment.

    Returns ``None`` when the recommendation is NOT a valid actionable experiment:
    a status outside APPROVED_STATUSES, or no approved changes. Blocked / empty /
    evidence-required / rendering-only responses therefore create no experiment.

    ``context_resolution`` (Phase 1) may be supplied; otherwise it is resolved via
    the Phase 1 ``build_engineering_context`` API from the given scope inputs. The
    context is NEVER computed independently here.
    """
    from strategy._setup_constants import APPROVED_STATUSES

    if not isinstance(data, Mapping):
        return None
    status = str(data.get("recommendation_status") or "")
    if status not in APPROVED_STATUSES:
        return None
    raw_changes = data.get("changes") or []
    if not isinstance(raw_changes, (list, tuple)) or not raw_changes:
        return None

    # Build actionable changes; first change = PRIMARY, the rest SUPPORTING.
    changes = []
    for i, raw in enumerate(raw_changes):
        if not isinstance(raw, Mapping) or not raw.get("field"):
            continue
        role = ChangeRole.PRIMARY if i == 0 else ChangeRole.SUPPORTING
        changes.append(_change_from_raw(raw, i, role))
    if not changes:
        return None

    # Deferred / unresolved diagnoses (persisted, not actioned).
    deferred = []
    diag = data.get("diagnosis") or {}
    if isinstance(diag, Mapping):
        for x in (diag.get("unresolved") or diag.get("deferred") or []):
            deferred.append(str(x))
    for rej in (data.get("rejected_changes") or []):
        if isinstance(rej, Mapping) and rej.get("symptom"):
            deferred.append(f"deferred:{rej.get('field')}:{rej.get('symptom')}")

    det = data.get("deterministic_plan") or {}
    rule_engine_version = str(
        det.get("rule_engine_version") or data.get("rule_engine_version") or "")
    driver_profile_version = str(det.get("driver_profile_version") or "")

    test_protocol = _test_protocol_from_data(data)

    exp = SetupExperiment(
        recommendation_source=recommendation_source,
        recommendation_status=status,
        rule_engine_version=rule_engine_version,
        driver_profile_version=driver_profile_version,
        parent_setup_id=str(parent_setup_id or ""),
        proposed_setup_id=str(proposed_setup_id or ""),
        lineage_id=str(lineage_id or ""),
        session_id=None if session_id in (None, "") else str(session_id),
        run_id=None if run_id in (None, "") else str(run_id),
        label=label,
        status=ExperimentStatus.DRAFT,
        hypothesis=_hypothesis_from_data(data),
        changes=tuple(changes),
        protected_behaviours=_protected_from_data(data),
        test_protocol=test_protocol,
        evidence=recommendation_evidence_from_data(data),
        deferred_diagnoses=tuple(deferred),
        rollback_target=test_protocol.rollback_target,
    )

    # Stamp the Phase 1 canonical context via the Phase 1 API (never recomputed).
    if context_resolution is None:
        context_resolution = build_engineering_context(
            car_id=car_id, free_text_track=track, layout_id=layout_id,
            discipline=discipline, driver_id=driver_id, gt7_version=gt7_version,
            event_id=event_id, config_id=config_id, session_id=session_id,
            run_id=run_id,
        )
    exp = exp.with_context(context_resolution)
    exp = exp.with_idempotency_key()
    return exp


def recommendation_evidence_from_data(data: Mapping) -> Tuple[ExperimentEvidence, ...]:
    """Extract RECOMMENDATION-phase evidence snapshot from the parsed _data dict.

    Structured references only (no telemetry blobs). Captures the diagnosis, the
    setup-lineage timeline, and any corner-telemetry diagnoses present at
    recommendation time. Provenance is preserved from the source keys.
    """
    out = []
    diag = data.get("diagnosis") or {}
    if isinstance(diag, Mapping) and diag:
        out.append(ExperimentEvidence(
            evidence_type="diagnosis", phase=EvidencePhase.DIAGNOSIS,
            source_table="setup_diagnosis",
            summary=str(diag.get("dominant_problem") or ""),
            provenance="rule-engine diagnosis",
            stance=EvidenceStance.SUPPORTS,
        ))
    lineage = data.get("setup_lineage")
    if isinstance(lineage, (list, tuple)):
        for node in lineage:
            if isinstance(node, Mapping):
                out.append(ExperimentEvidence(
                    evidence_type="lineage_node", phase=EvidencePhase.BASELINE,
                    source_table="setup_lineage",
                    source_id=str(node.get("id") or ""),
                    summary=str(node.get("label") or node.get("outcome_verdict") or ""),
                    provenance="setup_lineage",
                    stance=EvidenceStance.NEUTRAL,
                ))
    ctd = data.get("corner_telemetry_diagnoses")
    if isinstance(ctd, (list, tuple)):
        for c in ctd:
            if isinstance(c, Mapping):
                out.append(ExperimentEvidence(
                    evidence_type="corner_telemetry", phase=EvidencePhase.RECOMMENDATION,
                    source_table="corner_slip_telemetry",
                    corner=str(c.get("corner") or c.get("segment_id") or ""),
                    summary=str(c.get("issue") or c.get("summary") or ""),
                    provenance="live_corner_aggregator",
                    stance=EvidenceStance.SUPPORTS,
                ))
    return tuple(out)
