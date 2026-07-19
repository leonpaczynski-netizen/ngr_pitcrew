"""Mechanism-Constrained Intervention Hypotheses (Engineering Brain Program 2, Phase 14).

The deterministic, READ-ONLY reasoning layer that converts a valid Phase-13
``MechanismAnnotatedDiagnosis`` into structured, mechanism-constrained *intervention
hypotheses*. A hypothesis is NOT a setup recommendation and NOT an authored setup change:
it is an engineering proposition — a scientifically-defensible controlled-test *direction*
for a supported physical mechanism, with expected response, required evidence, trade-offs,
rejection criteria and status.

It answers: "given what we currently believe is happening physically, what controlled
intervention directions are defensible to test next?" — never "set this value to X".

It NEVER authors a numeric setup value, applies/approves/persists a setup, mutates a
diagnosis / outcome / working window / calibration / setup history / active setup, and it
duplicates neither the Phase-12 knowledge, the Phase-13 mechanism model, nor the Program-1
directional sign graph (it consumes all three). Qualitative directions are derived from the
canonical sign authority — never inferred from a parameter name — and gearing preserves the
canonical final-drive invariant (lower ratio = LONGER gearing).

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no ML/statistics/black-box; no
random, no wall-clock (timestamps are data); deterministic; never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from strategy.mechanism_annotation import (
    MECHANISM_ANNOTATION_VERSION, MechanismStatus, knowledge_versions,
)
from strategy.mechanism_map import candidates_for
from strategy.vehicle_dynamics import Component, explain_component
from strategy.setup_interactions import InteractionType, explain_interaction
from strategy import gearbox_evidence as gbx

INTERVENTION_HYPOTHESIS_VERSION = "intervention_hypothesis_v1"
INTERVENTION_HYPOTHESIS_SCHEMA = 1

# Deterministic cap on fields in one coupled hypothesis (prefer two).
MAX_COUPLED_FIELDS = 2


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class InterventionHypothesisStatus(str, Enum):
    TESTABLE = "testable"
    CONDITIONAL = "conditional"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    COMPETING_MECHANISMS = "competing_mechanisms"
    CONTRADICTED_BY_OUTCOME = "contradicted_by_outcome"
    BLOCKED_BY_WORKING_WINDOW = "blocked_by_working_window"
    BLOCKED_BY_SAFETY_OR_VALIDITY = "blocked_by_safety_or_validity"
    NOT_EVALUABLE = "not_evaluable"
    OUT_OF_SCOPE = "out_of_scope"


_TESTABLE_STATUSES = frozenset({
    InterventionHypothesisStatus.TESTABLE, InterventionHypothesisStatus.CONDITIONAL})


class InterventionDirection(str, Enum):
    INCREASE = "increase"
    DECREASE = "decrease"
    STIFFEN = "stiffen"
    SOFTEN = "soften"
    RAISE = "raise"
    LOWER = "lower"
    MOVE_FORWARD = "move_forward"
    MOVE_REARWARD = "move_rearward"
    SHORTEN = "shorten"
    LENGTHEN = "lengthen"
    INCREASE_LOCKING = "increase_locking"
    DECREASE_LOCKING = "decrease_locking"
    ALTER_BALANCE = "alter_balance"
    ISOLATE_FOR_TESTING = "isolate_for_testing"
    PRESERVE_CURRENT = "preserve_current_state"
    NO_DEFENSIBLE_DIRECTION = "no_defensible_direction"


class InterventionTestKind(str, Enum):
    SINGLE_FIELD = "single_field_isolated"
    PAIRED_COUPLED = "paired_coupled"
    MULTI_FIELD = "multi_field_constrained"
    PRESERVE_AND_OBSERVE = "preserve_and_observe"
    EVIDENCE_COLLECTION = "evidence_collection_only"


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


# --------------------------------------------------------------------------- #
# Presentation: (component group) + raise/lower  ->  qualitative direction.
# This is a DISPLAY mapping only; the raise/lower SIGN comes from the canonical
# Phase-12 axis authority (never from the parameter name).
# --------------------------------------------------------------------------- #
def _label_direction(component: Component, raise_field: bool) -> InterventionDirection:
    v = component.value
    if component in (Component.ARB_FRONT, Component.ARB_REAR, Component.SPRINGS_FRONT,
                     Component.SPRINGS_REAR):
        return InterventionDirection.STIFFEN if raise_field else InterventionDirection.SOFTEN
    if component in (Component.RIDE_HEIGHT_FRONT, Component.RIDE_HEIGHT_REAR):
        return InterventionDirection.RAISE if raise_field else InterventionDirection.LOWER
    if component in (Component.LSD_INITIAL, Component.LSD_ACCEL, Component.LSD_DECEL):
        return (InterventionDirection.INCREASE_LOCKING if raise_field
                else InterventionDirection.DECREASE_LOCKING)
    if component == Component.BRAKE_BIAS:
        # canonical: raising brake_bias moves the split REARWARD
        return InterventionDirection.MOVE_REARWARD if raise_field else InterventionDirection.MOVE_FORWARD
    if component in (Component.WEIGHT_DISTRIBUTION, Component.BALLAST):
        return InterventionDirection.ALTER_BALANCE
    return InterventionDirection.INCREASE if raise_field else InterventionDirection.DECREASE


# Issue-type → the canonical handling axis the intervention should improve, and whether we
# want MORE of that axis. Direction is then resolved against the Phase-12 sign authority.
_ISSUE_GOAL_AXIS: Dict[str, Tuple[str, bool]] = {
    "entry_understeer": ("entry_rotation", True),
    "mid_corner_understeer": ("apex_front_support", True),
    "front_push": ("apex_front_support", True),
    "understeer": ("apex_front_support", True),
    "entry_oversteer": ("power_oversteer_resistance", True),
    "oversteer": ("power_oversteer_resistance", True),
    "snap_oversteer": ("power_oversteer_resistance", True),
    "rear_loose_on_exit": ("power_oversteer_resistance", True),
    "wheelspin": ("exit_traction", True),
    "rear_wheelspin": ("exit_traction", True),
    "poor_traction": ("exit_traction", True),
    "poor_drive_out": ("exit_traction", True),
    "rear_loose_under_braking": ("trail_braking_stability", True),
    "braking_instability": ("trail_braking_stability", True),
    "bottoming": ("high_speed_stability", True),
    "kerb": ("kerb_compliance", True),
    "tyre_deg": ("tyre_preservation", True),
    "tyre_wear": ("tyre_preservation", True),
    "fuel_use_high": ("fuel_efficiency", True),
}

# Brake-balance is genuinely two-sided; its defensible test direction is issue-specific.
_BRAKE_DIRECTION: Dict[str, InterventionDirection] = {
    "front_lock": InterventionDirection.MOVE_REARWARD,   # reduce front braking share
    "lockup": InterventionDirection.MOVE_REARWARD,
    "rear_loose_under_braking": InterventionDirection.MOVE_FORWARD,   # settle the rear
    "braking_instability": InterventionDirection.MOVE_FORWARD,
    "entry_understeer": InterventionDirection.MOVE_REARWARD,          # free the front to rotate
}

_GEARING_COMPONENTS = frozenset({Component.TRANSMISSION})


@dataclass(frozen=True)
class _DirectionResult:
    direction: InterventionDirection
    raise_field: Optional[bool]         # None for special/undefined
    basis: str                          # sign source / rule used
    axis: str = ""


def _resolve_direction(issue_type: str, component: Component, intervention_field: str,
                       gearbox_state: str) -> _DirectionResult:
    """Resolve the qualitative test direction from the canonical sign authority. Returns
    NO_DEFENSIBLE_DIRECTION when the graph/gearbox does not support a defensible direction."""
    it = _lc(issue_type)

    # gearing: canonical gearbox-evidence state + final-drive invariant
    if component in _GEARING_COMPONENTS or _lc(intervention_field) in (
            "final_drive", "gear", "transmission"):
        st = _lc(gearbox_state)
        if st == gbx.GEARING_CONFLICTING:
            return _DirectionResult(InterventionDirection.NO_DEFENSIBLE_DIRECTION, None,
                                    "gearbox evidence is conflicting")
        if st in ("", gbx.GEARING_UNKNOWN):
            return _DirectionResult(InterventionDirection.NO_DEFENSIBLE_DIRECTION, None,
                                    "gearbox evidence state is unknown")
        if st == gbx.GEARING_TOO_SHORT or it in ("wheelspin", "rear_wheelspin",
                                                 "poor_traction", "poor_drive_out"):
            # too-short / wheelspin → LENGTHEN gearing (lower final-drive ratio)
            return _DirectionResult(InterventionDirection.LENGTHEN, None,
                                    "gearbox state; lower final-drive ratio = longer gearing")
        if st == gbx.GEARING_TOO_LONG or it == "gearing_too_long":
            return _DirectionResult(InterventionDirection.SHORTEN, None,
                                    "gearbox state; higher final-drive ratio = shorter gearing")
        return _DirectionResult(InterventionDirection.NO_DEFENSIBLE_DIRECTION, None,
                                "gearing appropriate / no defensible direction")

    # brakes: issue-specific two-sided direction
    if component == Component.BRAKE_BIAS:
        d = _BRAKE_DIRECTION.get(it)
        if d is None:
            return _DirectionResult(InterventionDirection.NO_DEFENSIBLE_DIRECTION, None,
                                    "no defensible brake-bias direction for this issue")
        return _DirectionResult(d, d == InterventionDirection.MOVE_REARWARD,
                                "issue-specific brake-balance rule")

    # everything else: goal axis + Phase-12 axis authority
    goal = _ISSUE_GOAL_AXIS.get(it)
    if goal is None:
        return _DirectionResult(InterventionDirection.NO_DEFENSIBLE_DIRECTION, None,
                                "no canonical goal axis for this issue")
    axis, want_more = goal
    exp = explain_component(component)
    sign = exp.axis_effects.get(axis) if exp else None
    if sign is None or sign == 0:
        return _DirectionResult(InterventionDirection.NO_DEFENSIBLE_DIRECTION, None,
                                f"component has no signed effect on {axis} in the sign authority",
                                axis=axis)
    raise_field = (sign > 0) == want_more
    return _DirectionResult(_label_direction(component, raise_field), raise_field,
                            f"Phase-12 axis authority: raising {component.value} moves "
                            f"{axis} by {sign:+d}", axis=axis)


# --------------------------------------------------------------------------- #
# Domain dataclasses
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class InterventionTarget:
    component: str                      # canonical parameter (Component value)
    parameter_group: str
    axle: str
    handling_phase: str
    corner_context: Tuple[str, ...]
    adjustable_in_gt7: bool
    telemetry_measurable: bool
    gt7_limitations: Tuple[str, ...]

    def to_dict(self) -> dict:
        return {"component": self.component, "parameter_group": self.parameter_group,
                "axle": self.axle, "handling_phase": self.handling_phase,
                "corner_context": list(self.corner_context),
                "adjustable_in_gt7": self.adjustable_in_gt7,
                "telemetry_measurable": self.telemetry_measurable,
                "gt7_limitations": list(self.gt7_limitations)}


@dataclass(frozen=True)
class ExpectedResponse:
    primary_effect: str                 # from Phase-12 (never authored here)
    handling_response: str
    response_timing: str                # entry / transient / apex / exit / high_speed
    predicted_benefit: str
    adverse_secondary_effects: Tuple[str, ...]
    interactions: Tuple[dict, ...]
    direction_confidence: str
    evidence_source: str

    def to_dict(self) -> dict:
        return {"primary_effect": self.primary_effect,
                "handling_response": self.handling_response,
                "response_timing": self.response_timing,
                "predicted_benefit": self.predicted_benefit,
                "adverse_secondary_effects": list(self.adverse_secondary_effects),
                "interactions": [dict(i) for i in self.interactions],
                "direction_confidence": self.direction_confidence,
                "evidence_source": self.evidence_source}


@dataclass(frozen=True)
class ControlledTestDesign:
    test_kind: str                      # InterventionTestKind value
    variable_under_test: str
    fields_involved: Tuple[str, ...]
    hold_constant: Tuple[str, ...]
    baseline_reference: str
    tyre_compound: str
    fuel_state: str
    min_clean_laps: int
    recurrence_expectation: str
    corner_context: Tuple[str, ...]
    expected_positive_signal: str
    expected_negative_signal: str
    rejection_condition: str
    reversal_condition: str
    ab_structure: str                   # A/B, A/B/A, preserve_and_observe
    attributable_to_single_field: bool

    def to_dict(self) -> dict:
        return {"test_kind": self.test_kind, "variable_under_test": self.variable_under_test,
                "fields_involved": list(self.fields_involved),
                "hold_constant": list(self.hold_constant),
                "baseline_reference": self.baseline_reference,
                "tyre_compound": self.tyre_compound, "fuel_state": self.fuel_state,
                "min_clean_laps": self.min_clean_laps,
                "recurrence_expectation": self.recurrence_expectation,
                "corner_context": list(self.corner_context),
                "expected_positive_signal": self.expected_positive_signal,
                "expected_negative_signal": self.expected_negative_signal,
                "rejection_condition": self.rejection_condition,
                "reversal_condition": self.reversal_condition,
                "ab_structure": self.ab_structure,
                "attributable_to_single_field": self.attributable_to_single_field}


@dataclass(frozen=True)
class InterventionHypothesis:
    hypothesis_id: str
    source_diagnosis_key: str
    source_mechanism_id: str
    source_mechanism_status: str
    target: InterventionTarget
    direction: str                      # InterventionDirection value
    direction_basis: str
    expected_response: ExpectedResponse
    required_evidence: Tuple[str, ...]
    missing_discriminators: Tuple[str, ...]
    predicted_trade_offs: Tuple[str, ...]
    protected_good_at_risk: Tuple[str, ...]
    interaction_constraints: Tuple[str, ...]
    working_window_state: str
    prior_outcome_relationship: str
    test_design: ControlledTestDesign
    rejection_criteria: Tuple[str, ...]
    evidence_grade: str
    status: str                         # InterventionHypothesisStatus value
    explanation: str
    reasoning: Tuple[str, ...]
    content_fingerprint: str
    eval_version: str = INTERVENTION_HYPOTHESIS_VERSION

    def to_dict(self) -> dict:
        return {
            "hypothesis_id": self.hypothesis_id,
            "source_diagnosis_key": self.source_diagnosis_key,
            "source_mechanism_id": self.source_mechanism_id,
            "source_mechanism_status": self.source_mechanism_status,
            "target": self.target.to_dict(), "direction": self.direction,
            "direction_basis": self.direction_basis,
            "expected_response": self.expected_response.to_dict(),
            "required_evidence": list(self.required_evidence),
            "missing_discriminators": list(self.missing_discriminators),
            "predicted_trade_offs": list(self.predicted_trade_offs),
            "protected_good_at_risk": list(self.protected_good_at_risk),
            "interaction_constraints": list(self.interaction_constraints),
            "working_window_state": self.working_window_state,
            "prior_outcome_relationship": self.prior_outcome_relationship,
            "test_design": self.test_design.to_dict(),
            "rejection_criteria": list(self.rejection_criteria),
            "evidence_grade": self.evidence_grade, "status": self.status,
            "explanation": self.explanation, "reasoning": list(self.reasoning),
            "content_fingerprint": self.content_fingerprint,
            "eval_version": self.eval_version}


@dataclass(frozen=True)
class InterventionHypothesisSet:
    source_diagnosis_key: str
    source_annotation: dict             # the MechanismAnnotatedDiagnosis, UNCHANGED
    context_fingerprint: str
    canonical_issue: dict
    testable: Tuple[dict, ...]
    conditional: Tuple[dict, ...]
    competing: Tuple[dict, ...]
    blocked: Tuple[dict, ...]
    preserve_and_observe: Tuple[dict, ...]
    evidence_gaps: Tuple[str, ...]
    safety_statements: Tuple[str, ...]
    overall_status: str
    audit: Tuple[str, ...]
    content_fingerprint: str
    knowledge_versions: dict
    schema_version: int = INTERVENTION_HYPOTHESIS_SCHEMA
    eval_version: str = INTERVENTION_HYPOTHESIS_VERSION

    def to_dict(self) -> dict:
        return {
            "source_diagnosis_key": self.source_diagnosis_key,
            "source_annotation": dict(self.source_annotation),
            "context_fingerprint": self.context_fingerprint,
            "canonical_issue": dict(self.canonical_issue),
            "testable": [dict(h) for h in self.testable],
            "conditional": [dict(h) for h in self.conditional],
            "competing": [dict(h) for h in self.competing],
            "blocked": [dict(h) for h in self.blocked],
            "preserve_and_observe": [dict(h) for h in self.preserve_and_observe],
            "evidence_gaps": list(self.evidence_gaps),
            "safety_statements": list(self.safety_statements),
            "overall_status": self.overall_status, "audit": list(self.audit),
            "content_fingerprint": self.content_fingerprint,
            "knowledge_versions": dict(self.knowledge_versions),
            "schema_version": self.schema_version, "eval_version": self.eval_version}


# --------------------------------------------------------------------------- #
# Component helpers
# --------------------------------------------------------------------------- #
def _component(v) -> Optional[Component]:
    try:
        return v if isinstance(v, Component) else Component(str(v))
    except (ValueError, TypeError):
        return None


def _group_of(component: Optional[Component]) -> str:
    exp = explain_component(component) if component else None
    return exp.group.value if exp else ""


def _axle_of(component: Optional[Component]) -> str:
    if component is None:
        return ""
    v = component.value
    if v.endswith("_front"):
        return "front"
    if v.endswith("_rear") or v in ("lsd_initial", "lsd_accel", "lsd_decel", "springs_rear"):
        return "rear"
    return ""


_TIMING = {
    "corner_entry": "entry", "trail_braking": "entry/transient", "initial_rotation": "entry",
    "mid_corner": "apex", "exit_traction": "exit", "power_on_rotation": "exit",
    "straight_line_stability": "straight", "high_speed_stability": "high_speed",
}


def _template_for(issue_type: str, mechanism_id: str):
    for t in candidates_for(issue_type):
        if t.mechanism_id == mechanism_id:
            return t
    return None


# --------------------------------------------------------------------------- #
# Public: build the hypothesis set for ONE mechanism-annotated diagnosis
# --------------------------------------------------------------------------- #
def build_intervention_hypotheses(
    annotation: Mapping,
    *,
    gearbox_state: str = "",
    speed_context: str = "",
    driver_preference: Optional[Mapping] = None,
    outcome_history: Optional[Sequence[Mapping]] = None,
) -> InterventionHypothesisSet:
    """Convert a Phase-13 ``MechanismAnnotatedDiagnosis`` dict into mechanism-constrained
    intervention hypotheses. Read-only; deterministic; never raises; authors no setup
    value and mutates nothing.

    ``outcome_history``: iterable of {fields:[...], outcome_status, single_field:bool}
    describing prior controlled experiments in this canonical context (Program-1 owned;
    consumed read-only). ``driver_preference``: optional {priority: 'front_bite'|'rear_stability', ...}.
    """
    try:
        return _build(annotation or {}, gearbox_state, speed_context,
                      driver_preference or {}, list(outcome_history or ()))
    except Exception as exc:   # never raise into the caller
        return _empty_set(annotation or {},
                          InterventionHypothesisStatus.NOT_EVALUABLE,
                          f"intervention build error: {type(exc).__name__}")


_BLOCKING_ANNOTATION = {
    "invalid_source_diagnosis": (InterventionHypothesisStatus.BLOCKED_BY_SAFETY_OR_VALIDITY,
                                 "the source diagnosis is invalid"),
    "insufficient_evidence": (InterventionHypothesisStatus.INSUFFICIENT_EVIDENCE,
                              "the source diagnosis has insufficient evidence"),
    "not_evaluable": (InterventionHypothesisStatus.NOT_EVALUABLE,
                      "the source diagnosis is not evaluable"),
    "out_of_scope": (InterventionHypothesisStatus.OUT_OF_SCOPE,
                     "the source diagnosis is out of vehicle-dynamics scope"),
}

_SAFETY = (
    "Advisory only. These are controlled-test DIRECTIONS constrained by the supported "
    "physical mechanism — not setup values, not recommendations, and nothing is applied. "
    "Every direction stays subordinate to the canonical evidence, working-window lockouts, "
    "outcome history, the setup-synthesis authority and the manual Apply gate.",
)


def _empty_set(annotation: Mapping, status: InterventionHypothesisStatus,
               reason: str) -> InterventionHypothesisSet:
    ann = dict(annotation)
    key = _norm(ann.get("source_diagnosis_key"))
    kv = knowledge_versions()
    kv["intervention_hypothesis"] = INTERVENTION_HYPOTHESIS_VERSION
    payload = {"key": key, "status": status.value, "reason": reason, "kv": kv}
    fp = (f"{INTERVENTION_HYPOTHESIS_VERSION}:"
          + hashlib.sha256(json.dumps(payload, sort_keys=True,
                                      separators=(",", ":")).encode()).hexdigest()[:24])
    return InterventionHypothesisSet(
        source_diagnosis_key=key, source_annotation=ann,
        context_fingerprint=_norm(ann.get("context_fingerprint")),
        canonical_issue=dict(ann.get("canonical_issue") or {}),
        testable=(), conditional=(), competing=(), blocked=(), preserve_and_observe=(),
        evidence_gaps=(reason,), safety_statements=_SAFETY, overall_status=status.value,
        audit=(f"blocked={status.value}", f"reason={reason}"), content_fingerprint=fp,
        knowledge_versions=kv)


def _build(annotation: Mapping, gearbox_state: str, speed_context: str,
           driver_preference: Mapping, outcome_history: List[Mapping]
           ) -> InterventionHypothesisSet:
    ann = dict(annotation)
    overall = _lc(ann.get("overall_status"))
    if overall in _BLOCKING_ANNOTATION:
        status, reason = _BLOCKING_ANNOTATION[overall]
        return _empty_set(ann, status, reason)

    issue = dict(ann.get("canonical_issue") or {})
    issue_type = _lc(issue.get("issue_type"))
    diag_key = _norm(ann.get("source_diagnosis_key"))
    ctx_fp = _norm(ann.get("context_fingerprint"))
    corners = tuple(ann.get("corners") or ())
    protected_good = tuple(_norm(p) for p in (ann.get("protected_good_behaviours") or ()))
    has_high_speed = _lc(speed_context) in ("high_speed", "high-speed", "high")

    # outcome constraints (Program-1 owned; read-only)
    regressed_single = set()      # fields with a prior single-field regression
    improved_coupled = []         # prior coupled improvements (field-sets)
    for oh in outcome_history:
        if not isinstance(oh, Mapping):
            continue
        flds = tuple(sorted(_lc(f) for f in (oh.get("fields") or []) if _lc(f)))
        st = _lc(oh.get("outcome_status"))
        single = bool(oh.get("single_field")) or len(flds) == 1
        if st == "regression" and single and flds:
            regressed_single.add(flds[0])
        if st in ("confirmed_improvement", "partial_improvement") and not single and len(flds) >= 2:
            improved_coupled.append(flds)

    candidates = ([ann["primary_mechanism"]] if ann.get("primary_mechanism") else []) \
        + list(ann.get("secondary_mechanisms") or []) \
        + list(ann.get("competing_mechanisms") or []) \
        + list(ann.get("contradicted_mechanisms") or [])

    hyps: List[InterventionHypothesis] = []
    seen_ids = set()
    for cand in candidates:
        if not isinstance(cand, Mapping):
            continue
        h = _hypothesis_for(cand, issue_type=issue_type, diag_key=diag_key, ctx_fp=ctx_fp,
                            corners=corners, protected_good=protected_good,
                            gearbox_state=gearbox_state, has_high_speed=has_high_speed,
                            regressed_single=regressed_single,
                            improved_coupled=improved_coupled,
                            driver_preference=driver_preference)
        if h is None or h.hypothesis_id in seen_ids:
            continue
        seen_ids.add(h.hypothesis_id)
        hyps.append(h)

    # deterministic ordering: status priority, evidence grade, directness, then stable id
    hyps.sort(key=_hyp_sort_key)

    testable = tuple(h.to_dict() for h in hyps
                     if h.status == InterventionHypothesisStatus.TESTABLE.value)
    conditional = tuple(h.to_dict() for h in hyps
                        if h.status == InterventionHypothesisStatus.CONDITIONAL.value)
    competing = tuple(h.to_dict() for h in hyps
                      if h.status == InterventionHypothesisStatus.COMPETING_MECHANISMS.value)
    blocked = tuple(h.to_dict() for h in hyps if h.status in (
        InterventionHypothesisStatus.BLOCKED_BY_WORKING_WINDOW.value,
        InterventionHypothesisStatus.CONTRADICTED_BY_OUTCOME.value,
        InterventionHypothesisStatus.BLOCKED_BY_SAFETY_OR_VALIDITY.value,
        InterventionHypothesisStatus.NOT_EVALUABLE.value))
    preserve = tuple(h.to_dict() for h in hyps if h.status in (
        InterventionHypothesisStatus.OUT_OF_SCOPE.value,
        InterventionHypothesisStatus.INSUFFICIENT_EVIDENCE.value))

    gaps = list(ann.get("evidence_gaps") or [])
    if competing:
        gaps.append("competing mechanisms require a discriminating controlled test before "
                    "any single direction is defensible")
    gaps = tuple(dict.fromkeys(gaps))

    overall_status = _set_status(testable, conditional, competing, blocked, preserve)
    audit = (
        f"issue={issue_type}", f"annotation={overall}",
        f"testable={len(testable)}", f"conditional={len(conditional)}",
        f"competing={len(competing)}", f"blocked={len(blocked)}",
        f"preserve={len(preserve)}",
        "layer=hypothesis_only; authors no value, applies nothing",
    )
    kv = knowledge_versions()
    kv["intervention_hypothesis"] = INTERVENTION_HYPOTHESIS_VERSION
    fp = _set_fingerprint(diag_key, overall_status, hyps, kv)
    return InterventionHypothesisSet(
        source_diagnosis_key=diag_key, source_annotation=ann, context_fingerprint=ctx_fp,
        canonical_issue=issue, testable=testable, conditional=conditional,
        competing=competing, blocked=blocked, preserve_and_observe=preserve,
        evidence_gaps=gaps, safety_statements=_SAFETY, overall_status=overall_status,
        audit=audit, content_fingerprint=fp, knowledge_versions=kv)


def _hypothesis_for(cand: Mapping, *, issue_type, diag_key, ctx_fp, corners,
                    protected_good, gearbox_state, has_high_speed, regressed_single,
                    improved_coupled, driver_preference) -> Optional[InterventionHypothesis]:
    mech_id = _norm(cand.get("mechanism_id"))
    mech_status = _lc(cand.get("status"))
    component = _component(cand.get("primary_component"))
    if component is None:
        return None
    tpl = _template_for(issue_type, mech_id)
    is_driver_technique = bool(getattr(tpl, "is_driver_technique", False))
    requires_speed = bool(getattr(tpl, "requires_speed_context", False))
    intervention_field = _norm(getattr(tpl, "intervention_field", "")) or component.value
    phase = _norm(cand.get("handling_phase"))
    grade = _lc(cand.get("evidence_grade"))
    reasoning: List[str] = list(cand.get("reasoning") or [])

    direction = _resolve_direction(issue_type, component, intervention_field, gearbox_state)

    # working-window / outcome constraints on this field
    contra_sources = {(_lc(e.get("source_type"))) for e in (cand.get("contradicting_evidence") or [])
                      if isinstance(e, Mapping)}
    intervention_contra = bool(cand.get("intervention_direction_contradicted"))
    field_regressed = _lc(intervention_field) in regressed_single

    # -- status decision (hard gates first) ---------------------------------
    status = _decide_status(
        mech_status=mech_status, is_driver_technique=is_driver_technique,
        requires_speed=requires_speed, has_high_speed=has_high_speed,
        direction=direction.direction, intervention_contra=intervention_contra,
        contra_sources=contra_sources, field_regressed=field_regressed, grade=grade)

    ww_state = ("locked" if (intervention_contra and "lockout" in contra_sources)
                else "protected" if intervention_contra else "open")
    prior_rel = _prior_outcome_rel(field_regressed, intervention_contra, contra_sources,
                                   improved_coupled, intervention_field)

    # test kind
    coupled = _coupled_fields(component, intervention_field, improved_coupled, mech_status)
    test_kind = _test_kind(status, coupled)

    # expected response (from Phase-12; never authored)
    expected = _expected_response(component, phase, direction, cand, driver_preference)
    # trade-offs / protected-good at risk (from Phase-12 axis authority)
    trade_offs, at_risk = _trade_offs(component, direction, protected_good)
    interaction_constraints = _interaction_constraints(component, coupled)

    required_evidence = _required_evidence(status, cand, requires_speed, has_high_speed,
                                           gearbox_state, component, test_kind)
    rejection = _rejection_criteria(issue_type, direction, at_risk)
    test = _test_design(test_kind, component, intervention_field, coupled, corners, cand,
                        direction, status)

    explanation = _explain(issue_type, component, direction, status, mech_status,
                           at_risk, driver_preference)

    hyp_id = _hyp_id(diag_key, mech_id, component.value, direction.direction.value)
    fp = _hyp_fingerprint(hyp_id, status, grade, direction.direction.value, test_kind)

    return InterventionHypothesis(
        hypothesis_id=hyp_id, source_diagnosis_key=diag_key, source_mechanism_id=mech_id,
        source_mechanism_status=mech_status,
        target=InterventionTarget(
            component=component.value, parameter_group=_group_of(component),
            axle=_axle_of(component), handling_phase=phase, corner_context=corners,
            adjustable_in_gt7=True,
            telemetry_measurable=False,
            gt7_limitations=tuple(cand.get("gt7_limitations") or ())),
        direction=direction.direction.value, direction_basis=direction.basis,
        expected_response=expected, required_evidence=required_evidence,
        missing_discriminators=tuple(cand.get("missing_discriminators") or ()),
        predicted_trade_offs=trade_offs, protected_good_at_risk=at_risk,
        interaction_constraints=interaction_constraints, working_window_state=ww_state,
        prior_outcome_relationship=prior_rel, test_design=test,
        rejection_criteria=rejection, evidence_grade=grade, status=status.value,
        explanation=explanation, reasoning=tuple(reasoning), content_fingerprint=fp)


def _decide_status(*, mech_status, is_driver_technique, requires_speed, has_high_speed,
                   direction, intervention_contra, contra_sources, field_regressed, grade
                   ) -> InterventionHypothesisStatus:
    # hard gates first
    if is_driver_technique:
        return InterventionHypothesisStatus.OUT_OF_SCOPE
    if mech_status == MechanismStatus.CONTRADICTED.value:
        return InterventionHypothesisStatus.CONTRADICTED_BY_OUTCOME
    if field_regressed:
        return InterventionHypothesisStatus.CONTRADICTED_BY_OUTCOME
    if intervention_contra:
        return (InterventionHypothesisStatus.BLOCKED_BY_WORKING_WINDOW
                if "lockout" in contra_sources or "outcome" not in contra_sources
                else InterventionHypothesisStatus.CONTRADICTED_BY_OUTCOME)
    if direction == InterventionDirection.NO_DEFENSIBLE_DIRECTION:
        # unknown gearing / no signed effect → collect evidence, never testable
        return InterventionHypothesisStatus.INSUFFICIENT_EVIDENCE
    if requires_speed and not has_high_speed:
        return InterventionHypothesisStatus.CONDITIONAL
    if mech_status in (MechanismStatus.COMPETING.value,):
        return InterventionHypothesisStatus.COMPETING_MECHANISMS
    if mech_status == MechanismStatus.PLAUSIBLE.value:
        return InterventionHypothesisStatus.CONDITIONAL
    if mech_status == MechanismStatus.INSUFFICIENT_EVIDENCE.value:
        return InterventionHypothesisStatus.INSUFFICIENT_EVIDENCE
    if mech_status == MechanismStatus.SUPPORTED_WITH_LIMITATIONS.value:
        return InterventionHypothesisStatus.CONDITIONAL
    if mech_status == MechanismStatus.SUPPORTED.value:
        if grade == "insufficient":
            return InterventionHypothesisStatus.INSUFFICIENT_EVIDENCE
        return InterventionHypothesisStatus.TESTABLE
    return InterventionHypothesisStatus.NOT_EVALUABLE


def _coupled_fields(component, intervention_field, improved_coupled, mech_status
                    ) -> Tuple[str, ...]:
    """A coupled test is permitted ONLY where a prior coupled outcome improved this field-set,
    or a canonical ENABLING interaction makes single-field isolation physically misleading.
    Capped at MAX_COUPLED_FIELDS; prefer two."""
    fld = _lc(intervention_field)
    for grp in improved_coupled:
        if fld in grp:
            return tuple(grp[:MAX_COUPLED_FIELDS])
    return ()


def _test_kind(status: InterventionHypothesisStatus, coupled: Tuple[str, ...]) -> InterventionTestKind:
    if status in (InterventionHypothesisStatus.COMPETING_MECHANISMS,
                  InterventionHypothesisStatus.INSUFFICIENT_EVIDENCE):
        return InterventionTestKind.EVIDENCE_COLLECTION
    if status in (InterventionHypothesisStatus.OUT_OF_SCOPE,
                  InterventionHypothesisStatus.BLOCKED_BY_WORKING_WINDOW,
                  InterventionHypothesisStatus.CONTRADICTED_BY_OUTCOME,
                  InterventionHypothesisStatus.BLOCKED_BY_SAFETY_OR_VALIDITY,
                  InterventionHypothesisStatus.NOT_EVALUABLE):
        return InterventionTestKind.PRESERVE_AND_OBSERVE
    if len(coupled) >= 2:
        return InterventionTestKind.PAIRED_COUPLED
    return InterventionTestKind.SINGLE_FIELD


def _prior_outcome_rel(field_regressed, intervention_contra, contra_sources,
                       improved_coupled, intervention_field) -> str:
    if field_regressed:
        return ("a prior single-field test in this direction regressed — the direction is "
                "contradicted for this context (the physical mechanism may still hold)")
    if intervention_contra and "lockout" in contra_sources:
        return "a working-window lockout protects this field/direction"
    if any(_lc(intervention_field) in grp for grp in improved_coupled):
        return ("a prior coupled test improved the car — credit belongs to the field SET, "
                "not any single field")
    return "no contradicting prior outcome for this direction"


def _expected_response(component, phase, direction, cand, driver_preference) -> ExpectedResponse:
    exp = explain_component(component)
    primary = exp.primary_mechanism if exp else _norm(cand.get("primary_physical_cause"))
    raise_field = direction.raise_field
    effect = ""
    if exp is not None and raise_field is not None:
        effect = exp.raise_effect if raise_field else exp.lower_effect
    timing = _TIMING.get(phase, phase)
    benefit = _norm(cand.get("name"))
    adverse = tuple(exp.secondary_interactions) if exp else ()
    return ExpectedResponse(
        primary_effect=primary, handling_response=effect, response_timing=timing,
        predicted_benefit=benefit, adverse_secondary_effects=adverse,
        interactions=tuple(cand.get("interactions") or ()),
        direction_confidence=_lc(cand.get("evidence_grade")),
        evidence_source="Phase-12 vehicle-dynamics authority + Program-1 sign graph")


def _trade_offs(component, direction, protected_good) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """Trade-offs are the OTHER axes this field moves (from the Phase-12 sign authority);
    any that names a protected-good behaviour is surfaced as at-risk."""
    exp = explain_component(component)
    raise_field = direction.raise_field
    trade: List[str] = []
    at_risk: List[str] = []
    if exp is not None and raise_field is not None:
        for axis, sign in sorted(exp.axis_effects.items()):
            moved = sign if raise_field else -sign
            line = f"{axis.replace('_', ' ')} moves {'+' if moved > 0 else '-'}"
            trade.append(line)
    # protected-good behaviours are always surfaced so they cannot silently disappear
    for pg in protected_good:
        at_risk.append(pg)
    return tuple(trade), tuple(at_risk)


def _interaction_constraints(component, coupled) -> Tuple[str, ...]:
    out: List[str] = []
    if len(coupled) >= 2:
        others = [f for f in coupled if f != component.value]
        for o in others:
            oc = _component(o)
            ci = explain_interaction(component, oc) if oc else None
            if ci is not None:
                out.append(f"{component.value} + {o} are coupled ({ci.interaction_type.value}): "
                           f"{ci.mechanism}")
    return tuple(out)


def _required_evidence(status, cand, requires_speed, has_high_speed, gearbox_state,
                       component, test_kind) -> Tuple[str, ...]:
    out: List[str] = []
    if status == InterventionHypothesisStatus.COMPETING_MECHANISMS:
        out.append("a controlled single-field test that separates the competing mechanisms "
                   "on the same corner, gear and fuel state")
    if requires_speed and not has_high_speed:
        out.append("speed-context evidence (compare the same corner at different speeds) "
                   "before an aero direction can become testable")
    if component in (Component.TRANSMISSION,) and _lc(gearbox_state) in (
            "", gbx.GEARING_UNKNOWN):
        out.append("resolve the canonical gearbox-evidence state (currently unknown) before "
                   "any gearing direction")
    if component in (Component.TRANSMISSION,) and _lc(gearbox_state) == gbx.GEARING_CONFLICTING:
        out.append("resolve conflicting gearbox evidence before any gearing direction")
    for md in (cand.get("missing_discriminators") or []):
        out.append(f"{md} is not available from GT7 telemetry — a controlled test must "
                   f"discriminate it")
    if not out:
        out.append("repeat the corner over more valid laps with the same setup to confirm "
                   "recurrence before testing")
    return tuple(dict.fromkeys(out))


def _rejection_criteria(issue_type, direction, at_risk) -> Tuple[str, ...]:
    out = [
        "the target issue does not measurably improve over the controlled test window",
        "recurrence of the target issue does not fall on valid laps",
    ]
    if at_risk:
        out.append("any confirmed-good behaviour (" + "; ".join(at_risk) + ") regresses")
    out.append("a new repeatable issue appears that was absent at baseline")
    return tuple(out)


def _test_design(test_kind, component, intervention_field, coupled, corners, cand,
                 direction, status) -> ControlledTestDesign:
    single = test_kind == InterventionTestKind.SINGLE_FIELD
    fields = tuple(coupled) if coupled else (intervention_field,)
    ab = ("A/B/A" if test_kind in (InterventionTestKind.SINGLE_FIELD, InterventionTestKind.PAIRED_COUPLED,
                                   InterventionTestKind.MULTI_FIELD) else "preserve_and_observe")
    var = ("the current setting" if test_kind in (
        InterventionTestKind.PRESERVE_AND_OBSERVE, InterventionTestKind.EVIDENCE_COLLECTION)
        else f"one bounded {direction.direction.value.replace('_', ' ')} step of {intervention_field}")
    return ControlledTestDesign(
        test_kind=test_kind.value, variable_under_test=var, fields_involved=fields,
        hold_constant=("all other setup fields", "tyre compound", "fuel state", "line"),
        baseline_reference="the current applied setup checkpoint",
        tyre_compound="same as baseline", fuel_state="same fuel range as baseline",
        min_clean_laps=4, recurrence_expectation="the issue must recur on baseline before testing",
        corner_context=corners,
        expected_positive_signal=_norm(cand.get("name")) + " improves on valid laps",
        expected_negative_signal="a protected-good behaviour or lap time regresses",
        rejection_condition="no measurable improvement, or a protected regression",
        reversal_condition="revert to the baseline checkpoint if a regression is confirmed",
        ab_structure=ab, attributable_to_single_field=single)


def _explain(issue_type, component, direction, status, mech_status, at_risk,
             driver_preference) -> str:
    it = issue_type.replace("_", " ")
    d = direction.direction.value.replace("_", " ")
    if status == InterventionHypothesisStatus.TESTABLE:
        s = (f"Mechanism-constrained direction: a candidate controlled test would {d} "
             f"{component.value} to address {it}.")
    elif status == InterventionHypothesisStatus.CONDITIONAL:
        s = (f"Conditional: {d} {component.value} could address {it}, but the direction is "
             f"not yet fully supported — requires discrimination.")
    elif status == InterventionHypothesisStatus.COMPETING_MECHANISMS:
        s = (f"Competing mechanism: {component.value} is one of several plausible causes of "
             f"{it}; a discriminating test is required before any direction is defensible.")
    elif status == InterventionHypothesisStatus.CONTRADICTED_BY_OUTCOME:
        s = (f"Blocked by prior regression: testing {component.value} in this direction was "
             f"already contradicted for this context; the physical mechanism may still hold.")
    elif status == InterventionHypothesisStatus.BLOCKED_BY_WORKING_WINDOW:
        s = (f"Blocked by working-window lockout: a proven constraint protects "
             f"{component.value} in this direction.")
    elif status == InterventionHypothesisStatus.OUT_OF_SCOPE:
        s = (f"Driver technique, not a setup mechanism — preserve the current setting and "
             f"observe.")
    else:
        s = (f"No defensible setup direction yet for {it} via {component.value}; collect the "
             f"missing evidence first.")
    if at_risk:
        s += f" Protect: {', '.join(at_risk)}."
    pref = _lc(driver_preference.get("priority")) if driver_preference else ""
    if pref:
        s += (f" (Driver preference noted: {pref.replace('_', ' ')} — a preference informs the "
              f"trade-off but never overrides evidence or a lockout.)")
    return s


# --------------------------------------------------------------------------- #
# ordering / status / fingerprints
# --------------------------------------------------------------------------- #
_STATUS_ORDER = {
    InterventionHypothesisStatus.TESTABLE.value: 0,
    InterventionHypothesisStatus.CONDITIONAL.value: 1,
    InterventionHypothesisStatus.COMPETING_MECHANISMS.value: 2,
    InterventionHypothesisStatus.INSUFFICIENT_EVIDENCE.value: 3,
    InterventionHypothesisStatus.OUT_OF_SCOPE.value: 4,
    InterventionHypothesisStatus.BLOCKED_BY_WORKING_WINDOW.value: 5,
    InterventionHypothesisStatus.CONTRADICTED_BY_OUTCOME.value: 6,
    InterventionHypothesisStatus.BLOCKED_BY_SAFETY_OR_VALIDITY.value: 7,
    InterventionHypothesisStatus.NOT_EVALUABLE.value: 8,
}
_GRADE_ORDER = {"strong": 0, "moderate": 1, "weak": 2, "insufficient": 3, "": 4}


def _hyp_sort_key(h: InterventionHypothesis) -> tuple:
    return (_STATUS_ORDER.get(h.status, 9), _GRADE_ORDER.get(h.evidence_grade, 4),
            0 if h.test_design.test_kind == InterventionTestKind.SINGLE_FIELD.value else 1,
            h.hypothesis_id)   # explicit deterministic non-semantic tie-break


def _set_status(testable, conditional, competing, blocked, preserve) -> str:
    if testable:
        return InterventionHypothesisStatus.TESTABLE.value
    if conditional:
        return InterventionHypothesisStatus.CONDITIONAL.value
    if competing:
        return InterventionHypothesisStatus.COMPETING_MECHANISMS.value
    if preserve:
        return InterventionHypothesisStatus.INSUFFICIENT_EVIDENCE.value
    if blocked:
        return InterventionHypothesisStatus.BLOCKED_BY_WORKING_WINDOW.value
    return InterventionHypothesisStatus.NOT_EVALUABLE.value


def _hyp_id(diag_key, mech_id, component, direction) -> str:
    raw = "|".join((diag_key, mech_id, component, direction))
    return f"{INTERVENTION_HYPOTHESIS_VERSION}:hyp:{hashlib.sha256(raw.encode()).hexdigest()[:20]}"


def _hyp_fingerprint(hyp_id, status, grade, direction, test_kind) -> str:
    payload = {"id": hyp_id, "status": status.value if hasattr(status, "value") else status,
               "grade": grade, "direction": direction,
               "kind": test_kind.value if hasattr(test_kind, "value") else test_kind}
    return (f"{INTERVENTION_HYPOTHESIS_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True,
                                        separators=(",", ":")).encode()).hexdigest()[:24])


def _set_fingerprint(diag_key, overall, hyps, kv) -> str:
    payload = {"diag": diag_key, "overall": overall, "kv": kv,
               "hyps": sorted([{"id": h.hypothesis_id, "status": h.status,
                                "grade": h.evidence_grade, "dir": h.direction,
                                "kind": h.test_design.test_kind} for h in hyps],
                              key=lambda d: d["id"])}
    return (f"{INTERVENTION_HYPOTHESIS_VERSION}:set:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True,
                                        separators=(",", ":")).encode()).hexdigest()[:24])


# --------------------------------------------------------------------------- #
# Public: build hypotheses for a whole annotation report (batch)
# --------------------------------------------------------------------------- #
def hypotheses_from_report(report: Optional[Mapping], *, gearbox_state: str = "",
                           speed_context: str = "",
                           driver_preference: Optional[Mapping] = None,
                           outcome_history: Optional[Sequence[Mapping]] = None) -> dict:
    """Turn a ``build_mechanism_annotations`` report into intervention-hypothesis sets.
    Deterministic order (by source diagnosis key); read-only; never raises."""
    report = report if isinstance(report, Mapping) else {}
    sets: List[InterventionHypothesisSet] = []
    for ann in report.get("annotations") or []:
        try:
            sets.append(build_intervention_hypotheses(
                ann, gearbox_state=gearbox_state, speed_context=speed_context,
                driver_preference=driver_preference, outcome_history=outcome_history))
        except Exception:
            continue
    sets.sort(key=lambda s: s.source_diagnosis_key)
    dicts = [s.to_dict() for s in sets]
    kv = knowledge_versions()
    kv["intervention_hypothesis"] = INTERVENTION_HYPOTHESIS_VERSION
    testable_sets = sum(1 for s in sets if s.testable)
    fp = (f"{INTERVENTION_HYPOTHESIS_VERSION}:report:"
          + hashlib.sha256(json.dumps(
              {"n": len(dicts), "fps": [s.content_fingerprint for s in sets], "kv": kv},
              sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:24])
    return {"ok": True, "version": INTERVENTION_HYPOTHESIS_VERSION,
            "hypothesis_sets": dicts, "count": len(dicts),
            "sets_with_testable": testable_sets, "safety_statements": list(_SAFETY),
            "knowledge_versions": kv, "content_fingerprint": fp}
