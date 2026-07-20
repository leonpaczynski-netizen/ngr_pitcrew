"""Mechanism-Annotated Diagnosis (Engineering Brain Program 2, Phase 13).

The strict bridge between Program 1 ("what happened?") and Program 2 ("why could it have
happened?"). For an ALREADY-DECIDED canonical Program-1 diagnosis, this READ-ONLY module
produces an auditable, evidence-linked explanation of the vehicle-dynamics MECHANISMS
behind it — by querying the Phase-12 knowledge authority. It preserves the canonical
diagnosis unchanged.

It NEVER:
  * decides whether an observation occurred, a lap is valid, an issue recurs, an
    experiment improved the car, a change is safe, or which experiment is selected
    (Program 1 owns all of that);
  * authors a setup value, a delta, an Apply, a Revert, or a recommendation;
  * mutates an outcome, a working window, a lockout, or prediction calibration;
  * duplicates the Phase-12 component / interaction / LSD / aero knowledge or the
    Program-1 directional sign graph (it consumes both).

Three layers stay separate: OBSERVATION (Program 1) → MECHANISM (this module, from
Phase 12) → INTERVENTION (existing authoring/selection authorities, untouched here).

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no ML/statistics/black-box
scoring; deterministic; never raises; no random, no wall-clock (timestamps are data).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from strategy.mechanism_map import (
    MECHANISM_MAP_VERSION, MechanismTemplate, candidates_for, has_mapping,
    resolve_handling_phase,
)
from strategy.vehicle_dynamics import (
    VEHICLE_DYNAMICS_VERSION, Component, explain_component,
)
from strategy.load_transfer import LOAD_TRANSFER_VERSION, TransferMode, explain_transfer
from strategy.handling_balance import (
    HANDLING_BALANCE_VERSION, HandlingPhase, explain_phase,
)
from strategy.setup_interactions import (
    SETUP_INTERACTIONS_VERSION, InteractionType, explain_interaction, interactions_for,
)
from strategy.setup_synthesis import PARAMETER_INTERACTIONS

MECHANISM_ANNOTATION_VERSION = "mechanism_annotation_v1"
MECHANISM_ANNOTATION_SCHEMA = 1


# --------------------------------------------------------------------------- #
# Status / grade vocabularies (explicit; never collapsed to one % confidence)
# --------------------------------------------------------------------------- #
class MechanismStatus(str, Enum):
    SUPPORTED = "supported"
    SUPPORTED_WITH_LIMITATIONS = "supported_with_limitations"
    PLAUSIBLE = "plausible"
    COMPETING = "competing"
    CONTRADICTED = "contradicted"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NOT_EVALUABLE = "not_evaluable"
    OUT_OF_SCOPE = "out_of_scope"
    INVALID_SOURCE_DIAGNOSIS = "invalid_source_diagnosis"


# Statuses that mean "no supported physical mechanism is being asserted".
_NON_SUPPORTED = frozenset({
    MechanismStatus.INSUFFICIENT_EVIDENCE, MechanismStatus.NOT_EVALUABLE,
    MechanismStatus.OUT_OF_SCOPE, MechanismStatus.INVALID_SOURCE_DIAGNOSIS,
})
# Statuses that a hard eligibility failure forces on the whole annotation.
_ELIGIBILITY_STATUSES = _NON_SUPPORTED


class EvidenceGrade(str, Enum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    INSUFFICIENT = "insufficient"


class ConclusionKind(str, Enum):
    DIRECT_OBSERVATION = "direct_observation"       # measured / counted by Program 1
    PHYSICS_INFORMED = "physics_informed"           # interpreted from Phase-12 knowledge
    PROVISIONAL = "provisional"                     # not yet distinguishable


class EvidenceRelation(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    NEUTRAL = "neutral"


# --------------------------------------------------------------------------- #
# GT7 observability — the channels GT7 does NOT expose (never treated as observed)
# --------------------------------------------------------------------------- #
# Per issue family, the discriminating channels the app cannot measure. These are the
# same channels Program-1 marks fabricated (corner_evidence._FABRICATED_METRIC_KEYS).
_UNAVAILABLE_CHANNELS: Dict[str, Tuple[str, ...]] = {
    "braking": ("individual tyre load", "tyre temperature", "brake temperature",
                "ABS/lock threshold state"),
    "rotation": ("individual tyre load", "slip angle", "steering angle"),
    "traction": ("individual driven-wheel load", "differential lock state",
                 "tyre temperature", "true wheel slip"),
    "platform": ("damper velocity", "suspension travel / displacement",
                 "individual tyre load"),
    "aero": ("downforce / aero load", "centre of pressure", "individual tyre load"),
    "gearing": ("engine torque curve", "optimal shift RPM"),
    "drive_out": ("engine torque curve", "differential lock state",
                  "individual driven-wheel load"),
    "tyre": ("tyre temperature", "tyre wear percentage", "individual tyre load"),
    "fuel": ("aero load", "engine torque curve"),
}

# Components whose behaviour cannot be directly separated from others without an
# unavailable channel — these gate a mechanism to SUPPORTED_WITH_LIMITATIONS at best.
_OBSERVABILITY_LIMITED_COMPONENTS = frozenset({
    Component.LSD_INITIAL, Component.LSD_ACCEL, Component.LSD_DECEL,   # no diff lock state
    Component.AERO_FRONT, Component.AERO_REAR,                        # no aero load
    Component.DAMPER_BUMP_FRONT, Component.DAMPER_BUMP_REAR,          # no damper velocity
    Component.DAMPER_REBOUND_FRONT, Component.DAMPER_REBOUND_REAR,
    Component.TRANSMISSION,                                           # no engine torque
})


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _axle_of_component(c: Component) -> str:
    """front/rear/'' for a component, for axle-compatibility of a candidate."""
    v = c.value
    if v.endswith("_front") or v in ("brake_bias",):
        return "front" if v.endswith("_front") else ""
    if v.endswith("_rear") or v in ("lsd_initial", "lsd_accel", "lsd_decel", "springs_rear"):
        return "rear"
    return ""


# --------------------------------------------------------------------------- #
# Domain: evidence link
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MechanismEvidenceLink:
    """One traceable piece of evidence for/against a mechanism. Every field is optional
    and only populated from what the SOURCE actually exposes (no fabricated identifiers)."""

    source_type: str = ""                 # residual / corner_comparison / driver_feedback / outcome / reconciliation / lockout / protected
    relation: str = EvidenceRelation.SUPPORTS.value
    conclusion_kind: str = ConclusionKind.DIRECT_OBSERVATION.value
    summary: str = ""
    quality: str = ""                     # strong/moderate/weak/limited
    session_id: str = ""
    run_id: str = ""
    checkpoint_id: str = ""
    experiment_id: str = ""
    outcome_id: str = ""
    lap_number: str = ""
    segment_id: str = ""
    handling_phase: str = ""
    axle: str = ""
    issue_type: str = ""
    validity_state: str = ""
    recurrence_state: str = ""
    observation_id: str = ""
    feedback_id: str = ""
    prediction_id: str = ""
    exclusion_reason: str = ""
    context_fingerprint: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in {
            "source_type": self.source_type, "relation": self.relation,
            "conclusion_kind": self.conclusion_kind, "summary": self.summary,
            "quality": self.quality, "session_id": self.session_id, "run_id": self.run_id,
            "checkpoint_id": self.checkpoint_id, "experiment_id": self.experiment_id,
            "outcome_id": self.outcome_id, "lap_number": self.lap_number,
            "segment_id": self.segment_id, "handling_phase": self.handling_phase,
            "axle": self.axle, "issue_type": self.issue_type,
            "validity_state": self.validity_state, "recurrence_state": self.recurrence_state,
            "observation_id": self.observation_id, "feedback_id": self.feedback_id,
            "prediction_id": self.prediction_id, "exclusion_reason": self.exclusion_reason,
            "context_fingerprint": self.context_fingerprint,
        }.items() if v not in ("", None)}

    def sort_key(self) -> tuple:
        return (self.relation, self.source_type, self.segment_id, self.summary)


# --------------------------------------------------------------------------- #
# Domain: mechanism candidate
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CausalMechanismCandidate:
    mechanism_id: str
    name: str
    handling_phase: str                       # HandlingPhase value
    load_transfer_mode: str                   # TransferMode value
    primary_component: str                    # Component value
    secondary_components: Tuple[str, ...]
    interactions: Tuple[dict, ...]
    primary_physical_cause: str               # pulled from Phase-12 (never authored here)
    secondary_physical_effects: Tuple[str, ...]
    gt7_limitations: Tuple[str, ...]
    supporting_evidence: Tuple[MechanismEvidenceLink, ...]
    contradicting_evidence: Tuple[MechanismEvidenceLink, ...]
    missing_discriminators: Tuple[str, ...]
    status: str                               # MechanismStatus value
    evidence_grade: str                       # EvidenceGrade value
    conclusion_kind: str                      # ConclusionKind value
    scope_compatible: bool
    setup_state_compatible: bool
    experiment_relationship: str
    predicted_relationship: str
    outcome_consistency: str
    intervention_field: str
    intervention_direction_contradicted: bool
    reasoning: Tuple[str, ...]
    knowledge_ref: dict                       # the Phase-12 references consumed
    _rank: Tuple = field(default=(), repr=False, compare=False)

    def to_dict(self) -> dict:
        return {
            "mechanism_id": self.mechanism_id, "name": self.name,
            "handling_phase": self.handling_phase,
            "load_transfer_mode": self.load_transfer_mode,
            "primary_component": self.primary_component,
            "secondary_components": list(self.secondary_components),
            "interactions": [dict(i) for i in self.interactions],
            "primary_physical_cause": self.primary_physical_cause,
            "secondary_physical_effects": list(self.secondary_physical_effects),
            "gt7_limitations": list(self.gt7_limitations),
            "supporting_evidence": [e.to_dict() for e in self.supporting_evidence],
            "contradicting_evidence": [e.to_dict() for e in self.contradicting_evidence],
            "missing_discriminators": list(self.missing_discriminators),
            "status": self.status, "evidence_grade": self.evidence_grade,
            "conclusion_kind": self.conclusion_kind,
            "scope_compatible": self.scope_compatible,
            "setup_state_compatible": self.setup_state_compatible,
            "experiment_relationship": self.experiment_relationship,
            "predicted_relationship": self.predicted_relationship,
            "outcome_consistency": self.outcome_consistency,
            "intervention_field": self.intervention_field,
            "intervention_direction_contradicted": self.intervention_direction_contradicted,
            "reasoning": list(self.reasoning), "knowledge_ref": dict(self.knowledge_ref),
        }


# --------------------------------------------------------------------------- #
# Domain: mechanism comparison
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MechanismComparison:
    mechanism_a: str
    mechanism_b: str
    evidence_favouring_a: Tuple[str, ...]
    evidence_favouring_b: Tuple[str, ...]
    shared_evidence: Tuple[str, ...]
    contradictory_evidence: Tuple[str, ...]
    missing_discriminator: str
    gt7_can_distinguish: bool
    required_observation: str
    status: str                               # "indistinguishable" | "resolvable"

    def to_dict(self) -> dict:
        return {
            "mechanism_a": self.mechanism_a, "mechanism_b": self.mechanism_b,
            "evidence_favouring_a": list(self.evidence_favouring_a),
            "evidence_favouring_b": list(self.evidence_favouring_b),
            "shared_evidence": list(self.shared_evidence),
            "contradictory_evidence": list(self.contradictory_evidence),
            "missing_discriminator": self.missing_discriminator,
            "gt7_can_distinguish": self.gt7_can_distinguish,
            "required_observation": self.required_observation, "status": self.status,
        }


# --------------------------------------------------------------------------- #
# Domain: the annotated diagnosis
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MechanismAnnotatedDiagnosis:
    source_diagnosis_key: str
    source_diagnosis: dict                    # the canonical diagnosis, UNCHANGED
    context_fingerprint: str
    driver: str
    car: str
    track: str
    layout: str
    discipline: str
    applied_checkpoint: str
    experiment_id: str
    outcome_id: str
    canonical_issue: dict
    corners: Tuple[str, ...]
    handling_phases: Tuple[str, ...]
    axles: Tuple[str, ...]
    primary_mechanism: Optional[dict]
    secondary_mechanisms: Tuple[dict, ...]
    competing_mechanisms: Tuple[dict, ...]
    contradicted_mechanisms: Tuple[dict, ...]
    comparisons: Tuple[dict, ...]
    interactions: Tuple[dict, ...]
    load_transfer_explanation: Optional[dict]
    gt7_limitations: Tuple[str, ...]
    evidence_gaps: Tuple[str, ...]
    required_discriminating_evidence: Tuple[str, ...]
    protected_good_behaviours: Tuple[str, ...]
    outcome_consistency: str
    prediction_relationship: dict
    overall_status: str
    ineligibility_reason: str
    audit: Tuple[str, ...]
    content_fingerprint: str
    knowledge_versions: dict
    schema_version: int = MECHANISM_ANNOTATION_SCHEMA
    eval_version: str = MECHANISM_ANNOTATION_VERSION

    def to_dict(self) -> dict:
        return {
            "source_diagnosis_key": self.source_diagnosis_key,
            "source_diagnosis": dict(self.source_diagnosis),
            "context_fingerprint": self.context_fingerprint, "driver": self.driver,
            "car": self.car, "track": self.track, "layout": self.layout,
            "discipline": self.discipline, "applied_checkpoint": self.applied_checkpoint,
            "experiment_id": self.experiment_id, "outcome_id": self.outcome_id,
            "canonical_issue": dict(self.canonical_issue), "corners": list(self.corners),
            "handling_phases": list(self.handling_phases), "axles": list(self.axles),
            "primary_mechanism": (dict(self.primary_mechanism)
                                  if self.primary_mechanism else None),
            "secondary_mechanisms": [dict(m) for m in self.secondary_mechanisms],
            "competing_mechanisms": [dict(m) for m in self.competing_mechanisms],
            "contradicted_mechanisms": [dict(m) for m in self.contradicted_mechanisms],
            "comparisons": [dict(c) for c in self.comparisons],
            "interactions": [dict(i) for i in self.interactions],
            "load_transfer_explanation": (dict(self.load_transfer_explanation)
                                          if self.load_transfer_explanation else None),
            "gt7_limitations": list(self.gt7_limitations),
            "evidence_gaps": list(self.evidence_gaps),
            "required_discriminating_evidence": list(self.required_discriminating_evidence),
            "protected_good_behaviours": list(self.protected_good_behaviours),
            "outcome_consistency": self.outcome_consistency,
            "prediction_relationship": dict(self.prediction_relationship),
            "overall_status": self.overall_status,
            "ineligibility_reason": self.ineligibility_reason,
            "audit": list(self.audit), "content_fingerprint": self.content_fingerprint,
            "knowledge_versions": dict(self.knowledge_versions),
            "schema_version": self.schema_version, "eval_version": self.eval_version,
        }


# --------------------------------------------------------------------------- #
# Deterministic sign-graph fingerprint (Program-1 owns the graph; we detect drift)
# --------------------------------------------------------------------------- #
def _sign_graph_fingerprint() -> str:
    return hashlib.sha256(
        json.dumps(PARAMETER_INTERACTIONS, sort_keys=True,
                   separators=(",", ":")).encode()).hexdigest()[:12]


def knowledge_versions() -> dict:
    return {
        "mechanism_annotation": MECHANISM_ANNOTATION_VERSION,
        "mechanism_map": MECHANISM_MAP_VERSION,
        "vehicle_dynamics": VEHICLE_DYNAMICS_VERSION,
        "load_transfer": LOAD_TRANSFER_VERSION,
        "handling_balance": HANDLING_BALANCE_VERSION,
        "setup_interactions": SETUP_INTERACTIONS_VERSION,
        "sign_graph": _sign_graph_fingerprint(),
        "schema": MECHANISM_ANNOTATION_SCHEMA,
    }


# --------------------------------------------------------------------------- #
# Eligibility gate
# --------------------------------------------------------------------------- #
# Residual states that mean "no adequate comparable evidence to support a mechanism".
_INSUFFICIENT_RESIDUAL = frozenset({
    "insufficient_evidence", "not_observed", "ambiguous",
})
_INVALID_RESIDUAL = frozenset({"invalid_comparison"})
# Decision states that invalidate the source diagnosis.
_INVALID_DECISION = frozenset({"invalid"})


def _eligibility(diag: Mapping, decision_state: str,
                 phase: Optional[HandlingPhase]) -> Tuple[Optional[MechanismStatus], str]:
    """Hard gate. Returns (blocking_status, reason) or (None, '') when eligible.
    Runs BEFORE any confidence grading — no amount of weak evidence can override it."""
    issue_type = _lc(diag.get("issue_type"))
    residual = _lc(diag.get("residual_state") or diag.get("latest_state"))
    family = _lc(diag.get("issue_family") or diag.get("family"))

    if _lc(decision_state) in _INVALID_DECISION:
        return MechanismStatus.INVALID_SOURCE_DIAGNOSIS, "canonical decision state is INVALID"
    if residual in _INVALID_RESIDUAL:
        return (MechanismStatus.INVALID_SOURCE_DIAGNOSIS,
                "source comparison is invalid")
    if diag.get("superseded"):
        return MechanismStatus.INVALID_SOURCE_DIAGNOSIS, "the diagnosis was superseded"
    if diag.get("stale_checkpoint"):
        return (MechanismStatus.INVALID_SOURCE_DIAGNOSIS,
                "the diagnosis is stale relative to the active setup checkpoint")
    if diag.get("checkpoint_ambiguous"):
        return (MechanismStatus.INVALID_SOURCE_DIAGNOSIS,
                "the applied setup checkpoint is ambiguous")

    if family in ("unknown", "consistency", ""):
        return (MechanismStatus.OUT_OF_SCOPE,
                "the issue family is not a vehicle-dynamics mechanism")
    if not has_mapping(issue_type):
        return (MechanismStatus.NOT_EVALUABLE,
                "the issue type is too broad / has no structural mechanism map")
    if phase is None:
        return (MechanismStatus.NOT_EVALUABLE,
                "the handling phase is unresolved for this diagnosis")

    # evidence sufficiency
    if residual in _INSUFFICIENT_RESIDUAL:
        return (MechanismStatus.INSUFFICIENT_EVIDENCE,
                "no adequate comparable evidence in the canonical diagnosis")
    valid_laps = _int(diag.get("valid_laps", diag.get("sample_count")))
    only_invalid = bool(diag.get("valid_laps_only_invalid"))
    if only_invalid or (valid_laps == 0 and _int(diag.get("times_observed")) == 0):
        return (MechanismStatus.INSUFFICIENT_EVIDENCE,
                "evidence comes only from invalid / unmeasured laps")
    recurring = bool(diag.get("recurring"))
    is_regression = residual in ("worsened", "new", "good_behaviour_damaged")
    if not recurring and not is_regression and residual not in (
            "unchanged", "improved_but_present", "resolved", "confirmed_good"):
        return (MechanismStatus.INSUFFICIENT_EVIDENCE,
                "the observation is below the recurrence required to attribute a mechanism")
    return None, ""


def _int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


# --------------------------------------------------------------------------- #
# Interaction annotation (constrained; never a flat graph dump)
# --------------------------------------------------------------------------- #
_INTERACTION_ROLE = {
    InteractionType.REINFORCING: "amplifies",
    InteractionType.OPPOSING: "trades against",
    InteractionType.ENABLING: "enables / gates",
    InteractionType.LIMITING: "caps / masks",
}


def _annotate_interaction(a: Component, b: Component) -> Optional[dict]:
    ci = explain_interaction(a, b)
    if ci is None:
        return None
    return {
        "a": ci.a.value, "b": ci.b.value, "type": ci.interaction_type.value,
        "role": _INTERACTION_ROLE.get(ci.interaction_type, "interacts with"),
        "mechanism": ci.mechanism, "gt7_note": ci.gt7_note,
    }


def _relevant_interactions(primary: Component,
                           secondaries: Sequence[Component]) -> Tuple[dict, ...]:
    """Interactions of the primary component with the diagnosis-relevant secondaries
    only — constrained by the mechanism, not a dump of the whole interaction graph."""
    want = set(secondaries)
    out: List[dict] = []
    seen = set()
    for ci in interactions_for(primary):
        other = ci.b if ci.a == primary else ci.a
        if other in want:
            d = _annotate_interaction(ci.a, ci.b)
            if d and (d["a"], d["b"]) not in seen:
                seen.add((d["a"], d["b"]))
                out.append(d)
    return tuple(sorted(out, key=lambda d: (d["a"], d["b"])))


# --------------------------------------------------------------------------- #
# Load-transfer annotation (no numeric loads — honest about GT7 limits)
# --------------------------------------------------------------------------- #
_TRANSFER_DIRECTION = {
    TransferMode.LONGITUDINAL: "load moves between the front and rear axle "
                               "(forward under braking, rearward under power)",
    TransferMode.LATERAL: "load moves from the inside to the outside tyres in the corner",
    TransferMode.COMBINED: "longitudinal and lateral transfer add, concentrating load on "
                           "one corner (e.g. the outer-front under trail braking)",
    TransferMode.PITCH: "the body pitches — dive under braking, squat under power",
    TransferMode.ROLL: "the body rolls, splitting lateral transfer by front/rear roll "
                       "stiffness",
    TransferMode.YAW: "the car rotates about its vertical axis (rotation vs stability)",
    TransferMode.PLATFORM: "the ride-height / aero platform moves, changing effective grip",
}


def _load_transfer_explanation(mode: TransferMode, family: str) -> dict:
    rel = explain_transfer(mode)
    d = {
        "mode": mode.value,
        "direction": _TRANSFER_DIRECTION.get(mode, ""),
        "note": "The app does not compute tyre loads in Newtons or kilograms — GT7 does "
                "not expose individual tyre load, so this describes direction only.",
    }
    if rel is not None:
        d.update({"mechanism": rel.mechanism, "balance_effect": rel.balance_effect,
                  "gt7_note": rel.gt7_note})
    return d


# --------------------------------------------------------------------------- #
# Evidence grading (deterministic; hard gates already passed)
# --------------------------------------------------------------------------- #
def _grade(diag: Mapping, *, has_contradiction: bool, gt7_limited: bool,
           outcome_consistent: Optional[bool], has_reconciliation: bool,
           driver_agrees: Optional[bool]) -> EvidenceGrade:
    residual = _lc(diag.get("residual_state") or diag.get("latest_state"))
    score = 0
    if residual in ("worsened", "new", "unchanged", "good_behaviour_damaged"):
        score += 2
    elif residual in ("improved_but_present",):
        score += 1
    if bool(diag.get("recurring")):
        score += 1
    valid = _int(diag.get("valid_laps", diag.get("sample_count")))
    if valid >= 5:
        score += 2
    elif valid >= 3:
        score += 1
    if _int(diag.get("sessions_seen")) >= 2:
        score += 1
    if _norm(diag.get("segment_id") or diag.get("corner") or diag.get("corner_name")):
        score += 1
    if _norm(diag.get("phase")):
        score += 1
    if _norm(diag.get("axle")):
        score += 1
    if driver_agrees is True:
        score += 1
    elif driver_agrees is False:
        score -= 1
    if bool(diag.get("telemetry_available")):
        score += 1
    if outcome_consistent is True:
        score += 1
    if has_reconciliation:
        score += 1
    if gt7_limited:
        score -= 1
    if has_contradiction:
        score -= 2
    if score >= 7:
        return EvidenceGrade.STRONG
    if score >= 4:
        return EvidenceGrade.MODERATE
    if score >= 2:
        return EvidenceGrade.WEAK
    return EvidenceGrade.INSUFFICIENT


# --------------------------------------------------------------------------- #
# Public: annotate ONE canonical diagnosis
# --------------------------------------------------------------------------- #
def annotate_diagnosis(
    diagnosis: Mapping,
    *,
    context: Optional[Mapping] = None,
    decision_state: str = "",
    outcome: Optional[Mapping] = None,
    reconciliation: Optional[Mapping] = None,
    failed_directions: Sequence = (),
    protected_good: Sequence = (),
    speed_context: str = "",
    driver_feedback: Optional[Mapping] = None,
) -> MechanismAnnotatedDiagnosis:
    """Annotate a single canonical Program-1 diagnosis with its vehicle-dynamics
    mechanisms, drawn from the Phase-12 authority. Preserves the diagnosis unchanged.
    Deterministic; never raises; mutates nothing.

    ``diagnosis`` keys consumed (all optional; from IssueMemory / EngineeringIssueIdentity):
      issue_family|family, issue_type, axle, phase, segment_id|corner|corner_name,
      discipline, scope_fingerprint, residual_state|latest_state, recurring,
      valid_laps|sample_count, times_observed, sessions_seen, telemetry_available, key.
    ``failed_directions``: iterable of (field, direction) tuples or dicts with
      field/direction/strength (Program-1 Phase-3/Phase-5 lockouts — authoritative).
    """
    try:
        return _annotate(diagnosis or {}, context or {}, decision_state, outcome,
                         reconciliation, failed_directions, protected_good,
                         speed_context, driver_feedback)
    except Exception as exc:  # never raise into the caller
        src = dict(diagnosis or {})
        return _blocked(src, context or {}, MechanismStatus.NOT_EVALUABLE,
                        f"annotation error: {type(exc).__name__}")


def _ctx_get(context: Mapping, *names, default: str = "") -> str:
    for n in names:
        v = context.get(n)
        if v not in (None, ""):
            return str(v)
    return default


def _diag_key(diag: Mapping) -> str:
    k = _norm(diag.get("key") or diag.get("issue_key"))
    if k:
        return k
    raw = "|".join(_lc(diag.get(x)) for x in
                   ("issue_family", "family", "issue_type", "axle", "phase",
                    "segment_id", "discipline", "scope_fingerprint"))
    return f"{MECHANISM_ANNOTATION_VERSION}:diag:{hashlib.sha256(raw.encode()).hexdigest()[:20]}"


def _blocked(src: dict, context: Mapping, status: MechanismStatus,
             reason: str) -> MechanismAnnotatedDiagnosis:
    """Build an annotation that carries the canonical diagnosis + explains why no
    supported mechanism is asserted. Physics knowledge NEVER overrides invalid evidence."""
    kv = knowledge_versions()
    key = _diag_key(src)
    audit = (f"eligibility={status.value}", f"reason={reason}")
    payload = {"key": key, "status": status.value, "reason": reason, "kv": kv}
    fp = (f"{MECHANISM_ANNOTATION_VERSION}:"
          + hashlib.sha256(json.dumps(payload, sort_keys=True,
                                      separators=(",", ":")).encode()).hexdigest()[:24])
    return MechanismAnnotatedDiagnosis(
        source_diagnosis_key=key, source_diagnosis=dict(src),
        context_fingerprint=_ctx_get(context, "context_fingerprint", "scope_fingerprint"),
        driver=_ctx_get(context, "driver"), car=_ctx_get(context, "car"),
        track=_ctx_get(context, "track"), layout=_ctx_get(context, "layout", "layout_id"),
        discipline=_ctx_get(context, "discipline") or _norm(src.get("discipline")),
        applied_checkpoint=_ctx_get(context, "applied_checkpoint", "applied_checkpoint_id"),
        experiment_id=_ctx_get(context, "experiment_id"),
        outcome_id=_ctx_get(context, "outcome_id"),
        canonical_issue=dict(src), corners=_corners(src), handling_phases=(), axles=_axles(src),
        primary_mechanism=None, secondary_mechanisms=(), competing_mechanisms=(),
        contradicted_mechanisms=(), comparisons=(), interactions=(),
        load_transfer_explanation=None, gt7_limitations=(), evidence_gaps=(reason,),
        required_discriminating_evidence=(), protected_good_behaviours=(),
        outcome_consistency="", prediction_relationship={}, overall_status=status.value,
        ineligibility_reason=reason, audit=audit, content_fingerprint=fp,
        knowledge_versions=kv)


def _corners(diag: Mapping) -> Tuple[str, ...]:
    c = _norm(diag.get("segment_id")) or _norm(diag.get("corner")) or \
        _norm(diag.get("corner_name"))
    return (c,) if c else ()


def _axles(diag: Mapping) -> Tuple[str, ...]:
    a = _lc(diag.get("axle"))
    return (a,) if a in ("front", "rear") else ()


def _failed_set(failed_directions: Sequence) -> Dict[str, Dict[str, str]]:
    """Normalise failed/locked directions to {field: {direction: strength}}."""
    out: Dict[str, Dict[str, str]] = {}
    for fd in failed_directions or ():
        if isinstance(fd, Mapping):
            fld = _lc(fd.get("field"))
            direction = _lc(fd.get("direction"))
            strength = _lc(fd.get("strength") or "lockout")
        elif isinstance(fd, (tuple, list)) and len(fd) >= 2:
            fld, direction = _lc(fd[0]), _lc(fd[1])
            strength = _lc(fd[2]) if len(fd) >= 3 else "lockout"
        else:
            continue
        if fld:
            out.setdefault(fld, {})[direction] = strength
    return out


def _annotate(diag: Mapping, context: Mapping, decision_state: str,
              outcome: Optional[Mapping], reconciliation: Optional[Mapping],
              failed_directions: Sequence, protected_good: Sequence,
              speed_context: str, driver_feedback: Optional[Mapping]
              ) -> MechanismAnnotatedDiagnosis:
    src = dict(diag)
    issue_type = _lc(diag.get("issue_type"))
    family = _lc(diag.get("issue_family") or diag.get("family"))
    axle = _lc(diag.get("axle"))
    phase = resolve_handling_phase(issue_type, _norm(diag.get("phase")), speed_context)

    elig, reason = _eligibility(diag, decision_state, phase)
    if elig is not None:
        return _blocked(src, context, elig, reason)

    templates = candidates_for(issue_type, axle, phase)
    if not templates:
        return _blocked(src, context, MechanismStatus.NOT_EVALUABLE,
                        "no mechanism candidates map to this diagnosis")

    ctx_fp = _ctx_get(context, "context_fingerprint", "scope_fingerprint") \
        or _norm(diag.get("scope_fingerprint"))
    corners = _corners(diag)
    failed = _failed_set(failed_directions)
    has_high_speed = _lc(speed_context) in ("high_speed", "high-speed", "high")

    # --- shared direct-observation evidence (the issue occurred) ------------ #
    residual = _lc(diag.get("residual_state") or diag.get("latest_state"))
    valid_laps = _int(diag.get("valid_laps", diag.get("sample_count")))
    base_obs = MechanismEvidenceLink(
        source_type="residual", relation=EvidenceRelation.SUPPORTS.value,
        conclusion_kind=ConclusionKind.DIRECT_OBSERVATION.value,
        summary=(f"{issue_type or 'issue'} observed"
                 + (f" at {corners[0]}" if corners else "")
                 + (f" ({residual}" + (f", {valid_laps} valid laps" if valid_laps else "")
                    + ")" if residual else "")),
        quality="strong" if bool(diag.get("recurring")) else "moderate",
        segment_id=corners[0] if corners else "", handling_phase=phase.value, axle=axle,
        issue_type=issue_type, recurrence_state=residual,
        observation_id=_norm(diag.get("key") or diag.get("issue_key")),
        context_fingerprint=ctx_fp)

    driver_agrees = None
    driver_ev: List[MechanismEvidenceLink] = []
    if driver_feedback:
        agree = driver_feedback.get("agrees")
        driver_agrees = bool(agree) if agree is not None else None
        driver_ev.append(MechanismEvidenceLink(
            source_type="driver_feedback",
            relation=(EvidenceRelation.SUPPORTS.value if driver_agrees is not False
                      else EvidenceRelation.CONTRADICTS.value),
            conclusion_kind=ConclusionKind.DIRECT_OBSERVATION.value,
            summary=_norm(driver_feedback.get("summary") or "driver feedback on record"),
            feedback_id=_norm(driver_feedback.get("feedback_id")),
            issue_type=issue_type, context_fingerprint=ctx_fp))

    # --- outcome / prediction relationship ---------------------------------- #
    outcome_status = _lc((outcome or {}).get("status"))
    outcome_id = _ctx_get(context, "outcome_id") or _norm((outcome or {}).get("id"))
    experiment_id = _ctx_get(context, "experiment_id") \
        or _norm((outcome or {}).get("experiment_id"))
    outcome_consistent = None
    outcome_consistency = ""
    if outcome_status:
        if outcome_status in ("confirmed_improvement", "partial_improvement"):
            outcome_consistency = ("the tested change improved the car, but a confirmed "
                                   "improvement does not by itself prove one mechanism")
            outcome_consistent = True
        elif outcome_status == "regression":
            outcome_consistency = ("the tested change regressed; the intervention direction "
                                   "is disproven but the physical mechanism may still hold")
            outcome_consistent = True
        elif outcome_status in ("no_meaningful_change",):
            outcome_consistency = "the tested change produced no meaningful change"
        else:
            outcome_consistency = f"outcome status: {outcome_status}"

    prediction_rel = _prediction_relationship(reconciliation)

    protected_names = tuple(
        _norm(p.get("behaviour") if isinstance(p, Mapping) else p)
        for p in (protected_good or ()) if _norm(p.get("behaviour") if isinstance(p, Mapping) else p))

    # --- build candidates --------------------------------------------------- #
    built: List[Tuple[MechanismTemplate, CausalMechanismCandidate]] = []
    for tpl in templates:
        cand = _build_candidate(
            tpl, diag=diag, phase=phase, axle=axle, family=family, ctx_fp=ctx_fp,
            base_obs=base_obs, driver_ev=tuple(driver_ev), failed=failed,
            has_high_speed=has_high_speed, outcome=outcome, outcome_status=outcome_status,
            outcome_consistent=outcome_consistent, reconciliation=reconciliation,
            prediction_rel=prediction_rel, driver_agrees=driver_agrees,
            experiment_id=experiment_id, outcome_id=outcome_id)
        built.append((tpl, cand))

    ranked = _rank_and_classify(built, family=family)

    _SUPP = (MechanismStatus.SUPPORTED.value,
             MechanismStatus.SUPPORTED_WITH_LIMITATIONS.value)
    primary_cand = next((c for _, c in ranked
                         if c.status in _SUPP and _is_primary_slot(c)), None)
    primary = primary_cand.to_dict() if primary_cand else None
    secondary = tuple(c.to_dict() for _, c in ranked
                      if c is not primary_cand and c.status in _SUPP)
    competing = tuple(c.to_dict() for _, c in ranked
                      if c.status in (MechanismStatus.COMPETING.value,
                                      MechanismStatus.PLAUSIBLE.value))
    contradicted = tuple(c.to_dict() for _, c in ranked
                         if c.status == MechanismStatus.CONTRADICTED.value)

    # comparisons between the top plausible/competing mechanisms
    comparisons = _build_comparisons([c for _, c in ranked], family)

    # aggregate interactions/load-transfer/gt7/evidence-gaps from the driving mechanism
    driver_cand = primary_cand
    if driver_cand is None and competing:
        driver_cand = next((c for _, c in ranked
                            if c.mechanism_id == competing[0]["mechanism_id"]), None)
    interactions = driver_cand.interactions if driver_cand else ()
    lt = (_load_transfer_explanation(TransferMode(driver_cand.load_transfer_mode), family)
          if driver_cand else None)
    gt7 = _aggregate_gt7(ranked, family)
    gaps, required = _evidence_gaps(ranked, family, has_high_speed)

    overall = _overall_status(primary, competing, contradicted, ranked)
    audit = _audit(diag, phase, elig=None, primary=primary, competing=competing,
                   contradicted=contradicted, outcome_status=outcome_status,
                   prediction_rel=prediction_rel)

    kv = knowledge_versions()
    fp = _content_fingerprint(_diag_key(diag), overall, [c for _, c in ranked], kv)

    return MechanismAnnotatedDiagnosis(
        source_diagnosis_key=_diag_key(diag), source_diagnosis=src,
        context_fingerprint=ctx_fp,
        driver=_ctx_get(context, "driver"), car=_ctx_get(context, "car"),
        track=_ctx_get(context, "track"), layout=_ctx_get(context, "layout", "layout_id"),
        discipline=_ctx_get(context, "discipline") or _norm(diag.get("discipline")),
        applied_checkpoint=_ctx_get(context, "applied_checkpoint", "applied_checkpoint_id"),
        experiment_id=experiment_id, outcome_id=outcome_id,
        canonical_issue=dict(diag), corners=corners,
        handling_phases=(phase.value,), axles=_axles(diag),
        primary_mechanism=primary, secondary_mechanisms=secondary,
        competing_mechanisms=competing, contradicted_mechanisms=contradicted,
        comparisons=comparisons, interactions=interactions,
        load_transfer_explanation=lt, gt7_limitations=gt7,
        evidence_gaps=gaps, required_discriminating_evidence=required,
        protected_good_behaviours=protected_names, outcome_consistency=outcome_consistency,
        prediction_relationship=prediction_rel, overall_status=overall,
        ineligibility_reason="", audit=audit, content_fingerprint=fp,
        knowledge_versions=kv)


def _is_primary_slot(c: CausalMechanismCandidate) -> bool:
    return c._rank and c._rank[0] == 0  # role_hint == primary rank


def _prediction_relationship(reconciliation: Optional[Mapping]) -> dict:
    if not isinstance(reconciliation, Mapping):
        return {}
    cons = reconciliation.get("consequence_reconciliations") or []
    primary = next((c for c in cons if _lc(c.get("kind")) == "primary_effect"), None)
    acc = reconciliation.get("accuracy") or {}
    status = _lc(primary.get("status")) if primary else ""
    verdict = {
        "confirmed": "mechanism prediction supported by the outcome",
        "partially_confirmed": "mechanism prediction partially supported",
        "contradicted": "mechanism prediction contradicted by the outcome",
        "not_observed": "predicted consequence was not observed",
        "insufficient_evidence": "prediction not testable with available evidence",
        "unknown": "prediction outcome ambiguous",
    }.get(status, "no primary prediction on record")
    return {
        "has_prediction": bool(primary),
        "predicted": _norm(primary.get("predicted")) if primary else "",
        "observed": _norm(primary.get("observed")) if primary else "",
        "reconciliation_status": status,
        "verdict": verdict,
        "prediction_fingerprint": _norm(reconciliation.get("prediction_fingerprint")),
        "overall_accuracy": acc.get("overall_accuracy"),
        "note": "prediction calibration is owned by Phase 11 and is read-only here",
    }


def _build_candidate(tpl: MechanismTemplate, *, diag, phase, axle, family, ctx_fp,
                     base_obs, driver_ev, failed, has_high_speed, outcome, outcome_status,
                     outcome_consistent, reconciliation, prediction_rel, driver_agrees,
                     experiment_id, outcome_id) -> CausalMechanismCandidate:
    exp = explain_component(tpl.primary_component)
    primary_cause = exp.primary_mechanism if exp else tpl.name
    secondary_effects = tuple(exp.secondary_interactions) if exp else ()
    comp_gt7 = tuple(exp.gt7_limitations) if exp else ()

    interactions = _relevant_interactions(tpl.primary_component, tpl.secondary_components)
    # explicit interaction pairs from the template (constrained, deterministic)
    for a, b in tpl.interaction_pairs:
        d = _annotate_interaction(a, b)
        if d and d not in interactions:
            interactions = interactions + (d,)
    interactions = tuple(sorted(interactions, key=lambda d: (d["a"], d["b"])))

    supporting = [base_obs] + list(driver_ev)
    contradicting: List[MechanismEvidenceLink] = []
    reasoning: List[str] = []

    # scope / setup-state compatibility
    scope_ok = True
    setup_ok = True

    # GT7 observability limit for this mechanism's primary component
    gt7_limited = tpl.primary_component in _OBSERVABILITY_LIMITED_COMPONENTS

    # phase/axle compatibility
    phase_match = (tpl.handling_phase == phase) or (
        has_high_speed and tpl.handling_phase == HandlingPhase.HIGH_SPEED_STABILITY)
    comp_axle = _axle_of_component(tpl.primary_component)
    axle_match = (not axle) or (not comp_axle) or (comp_axle == axle)

    # failed-direction lockout on this mechanism's INTERVENTION (never on the mechanism)
    intervention_contra = False
    if tpl.intervention_field and tpl.intervention_field in failed:
        # A naive fix would move the field; any locked direction contradicts the fix.
        dirs = failed[tpl.intervention_field]
        intervention_contra = True
        for direction, strength in sorted(dirs.items()):
            contradicting.append(MechanismEvidenceLink(
                source_type="lockout", relation=EvidenceRelation.CONTRADICTS.value,
                conclusion_kind=ConclusionKind.DIRECT_OBSERVATION.value,
                summary=(f"a prior {tpl.intervention_field} {direction or 'change'} "
                         f"was a {strength} failed direction (regression evidence)"),
                issue_type=_lc(diag.get("issue_type")), context_fingerprint=ctx_fp))
        reasoning.append(
            f"the {tpl.intervention_field} intervention direction is blocked by a "
            f"Program-1 failed-direction lockout; the mechanism stays possible but no "
            f"change is proposed here")

    # outcome regression on this field contradicts the intervention direction
    if outcome_status == "regression" and tpl.intervention_field and \
            _field_in_outcome(outcome, tpl.intervention_field):
        intervention_contra = True
        contradicting.append(MechanismEvidenceLink(
            source_type="outcome", relation=EvidenceRelation.CONTRADICTS.value,
            conclusion_kind=ConclusionKind.DIRECT_OBSERVATION.value,
            summary=f"a prior change to {tpl.intervention_field} regressed the car",
            outcome_id=outcome_id, experiment_id=experiment_id,
            issue_type=_lc(diag.get("issue_type")), context_fingerprint=ctx_fp))

    # prediction contradiction: if the predicted primary consequence was contradicted and
    # names this field, the mechanism PREDICTION is contradicted (calibration untouched).
    predicted_rel = "not_predicted"
    if prediction_rel.get("has_prediction"):
        rs = prediction_rel.get("reconciliation_status")
        if rs == "contradicted" and tpl.intervention_field and \
                tpl.intervention_field in _lc(prediction_rel.get("predicted")):
            predicted_rel = "contradicted"
            contradicting.append(MechanismEvidenceLink(
                source_type="reconciliation", relation=EvidenceRelation.CONTRADICTS.value,
                conclusion_kind=ConclusionKind.DIRECT_OBSERVATION.value,
                summary="the pre-flight prediction for this mechanism was contradicted "
                        "post-flight",
                prediction_id=prediction_rel.get("prediction_fingerprint", ""),
                context_fingerprint=ctx_fp))
        elif rs in ("confirmed", "partially_confirmed"):
            predicted_rel = "supported" if rs == "confirmed" else "partially_supported"
        else:
            predicted_rel = rs or "not_predicted"

    # missing discriminators for this mechanism
    missing = list(_UNAVAILABLE_CHANNELS.get(family, ()))

    grade = _grade(diag, has_contradiction=bool(contradicting), gt7_limited=gt7_limited,
                   outcome_consistent=outcome_consistent,
                   has_reconciliation=bool(reconciliation), driver_agrees=driver_agrees)

    # experiment relationship
    exp_rel = _experiment_relationship(diag, outcome, outcome_status, tpl)

    # conclusion kind: the OBSERVATION is direct; the mechanism attribution is inferred
    conclusion = (ConclusionKind.PHYSICS_INFORMED.value if not tpl.is_driver_technique
                  else ConclusionKind.PHYSICS_INFORMED.value)

    # provisional status decision (final competition resolved in _rank_and_classify)
    status = _provisional_status(tpl, phase_match=phase_match, axle_match=axle_match,
                                 gt7_limited=gt7_limited, has_high_speed=has_high_speed,
                                 grade=grade, predicted_rel=predicted_rel,
                                 intervention_contra=intervention_contra)
    if not phase_match:
        reasoning.append(f"mechanism sits in the {tpl.handling_phase.value} phase, not the "
                         f"observed {phase.value} phase")
    if tpl.requires_speed_context and not has_high_speed:
        reasoning.append("aero attribution needs speed-dependent evidence that is not "
                         "available, so it stays plausible, never primary")
    if tpl.is_driver_technique:
        reasoning.append("this is a driver-technique factor, not a setup mechanism")

    rank = _rank_tuple(tpl, phase_match, axle_match, grade, status)

    return CausalMechanismCandidate(
        mechanism_id=tpl.mechanism_id, name=tpl.name,
        handling_phase=tpl.handling_phase.value, load_transfer_mode=tpl.transfer_mode.value,
        primary_component=tpl.primary_component.value,
        secondary_components=tuple(c.value for c in tpl.secondary_components),
        interactions=interactions, primary_physical_cause=primary_cause,
        secondary_physical_effects=secondary_effects, gt7_limitations=comp_gt7,
        supporting_evidence=tuple(supporting), contradicting_evidence=tuple(contradicting),
        missing_discriminators=tuple(missing), status=status.value,
        evidence_grade=grade.value, conclusion_kind=conclusion,
        scope_compatible=scope_ok, setup_state_compatible=setup_ok,
        experiment_relationship=exp_rel, predicted_relationship=predicted_rel,
        outcome_consistency=(outcome_status or ""), intervention_field=tpl.intervention_field,
        intervention_direction_contradicted=intervention_contra,
        reasoning=tuple(reasoning),
        knowledge_ref={
            "component": tpl.primary_component.value,
            "handling_phase": tpl.handling_phase.value,
            "transfer_mode": tpl.transfer_mode.value,
            "vehicle_dynamics": VEHICLE_DYNAMICS_VERSION,
            "handling_balance": HANDLING_BALANCE_VERSION,
            "load_transfer": LOAD_TRANSFER_VERSION,
            "setup_interactions": SETUP_INTERACTIONS_VERSION,
        },
        _rank=rank)


def _field_in_outcome(outcome: Optional[Mapping], fld: str) -> bool:
    if not isinstance(outcome, Mapping) or not fld:
        return False
    for ch in outcome.get("changes") or ():
        if isinstance(ch, Mapping) and _lc(ch.get("field")) == fld:
            return True
    return _lc(outcome.get("field")) == fld


def _experiment_relationship(diag, outcome, outcome_status, tpl) -> str:
    if not outcome_status:
        return "no linked experiment outcome"
    compound = bool((outcome or {}).get("is_compound")) or \
        len((outcome or {}).get("changes") or ()) > 1
    if compound:
        return ("multi-field experiment — mechanism attribution to a single field is "
                "unsafe")
    return {
        "confirmed_improvement": "outcome improved; mechanism plausible, not proven",
        "partial_improvement": "outcome partially improved; mechanism partially supported",
        "regression": "outcome regressed; intervention direction disproven",
        "no_meaningful_change": "no meaningful change; mechanism not tested cleanly",
        "confounded": "outcome confounded; setup effect cannot be isolated",
        "insufficient_evidence": "insufficient evidence to relate the mechanism",
    }.get(outcome_status, f"outcome: {outcome_status}")


# role rank: primary=0, secondary=1, competing=2; then compatibility & grade
_ROLE_RANK = {"primary": 0, "secondary": 1, "competing": 2}
_GRADE_RANK = {"strong": 0, "moderate": 1, "weak": 2, "insufficient": 3}


def _rank_tuple(tpl, phase_match, axle_match, grade, status) -> tuple:
    return (
        _ROLE_RANK.get(tpl.role_hint, 2),
        0 if phase_match else 1,
        0 if axle_match else 1,
        _GRADE_RANK.get(grade.value, 3),
        1 if tpl.requires_speed_context else 0,
        1 if tpl.is_driver_technique else 0,
        tpl.mechanism_id,
    )


def _provisional_status(tpl, *, phase_match, axle_match, gt7_limited, has_high_speed,
                        grade, predicted_rel, intervention_contra) -> MechanismStatus:
    if predicted_rel == "contradicted":
        return MechanismStatus.CONTRADICTED
    if tpl.is_driver_technique:
        return MechanismStatus.PLAUSIBLE
    if tpl.requires_speed_context and not has_high_speed:
        return MechanismStatus.PLAUSIBLE
    if not phase_match or not axle_match:
        return MechanismStatus.PLAUSIBLE
    if grade == EvidenceGrade.INSUFFICIENT:
        return MechanismStatus.INSUFFICIENT_EVIDENCE
    if tpl.role_hint == "primary":
        return (MechanismStatus.SUPPORTED_WITH_LIMITATIONS if gt7_limited
                else MechanismStatus.SUPPORTED)
    return MechanismStatus.COMPETING


def _rank_and_classify(built, *, family: str):
    """Sort candidates deterministically and resolve primary-vs-competing.

    A single SUPPORTED primary survives only when it strictly out-ranks every other
    primary-role candidate. When two or more primary-role candidates are compatible and
    indistinguishable, they are demoted to COMPETING (no auto-winner)."""
    ordered = sorted(built, key=lambda tc: tc[1]._rank)
    # collect compatible primary-role candidates (SUPPORTED*/would-be primary)
    primaries = [(t, c) for (t, c) in ordered
                 if c.status in (MechanismStatus.SUPPORTED.value,
                                 MechanismStatus.SUPPORTED_WITH_LIMITATIONS.value)]
    if len(primaries) >= 2:
        # indistinguishable if the top two share the same rank prefix (role/phase/axle/grade)
        r0 = primaries[0][1]._rank[:4]
        tie = [pc for pc in primaries if pc[1]._rank[:4] == r0]
        if len(tie) >= 2:
            demoted_ids = {c.mechanism_id for _, c in tie}
            new = []
            for t, c in ordered:
                if c.mechanism_id in demoted_ids:
                    c = _with_status(c, MechanismStatus.COMPETING)
                new.append((t, c))
            ordered = new
    return ordered


def _with_status(c: CausalMechanismCandidate, status: MechanismStatus
                 ) -> CausalMechanismCandidate:
    return CausalMechanismCandidate(
        **{**{k: getattr(c, k) for k in c.__dataclass_fields__ if k != "_rank"},
           "status": status.value}, _rank=c._rank)


def _build_comparisons(cands: Sequence[CausalMechanismCandidate],
                       family: str) -> Tuple[dict, ...]:
    """Pairwise comparisons among the plausible/competing mechanisms — retained without
    a winner when GT7 cannot distinguish them."""
    live = [c for c in cands if c.status in (
        MechanismStatus.COMPETING.value, MechanismStatus.PLAUSIBLE.value,
        MechanismStatus.SUPPORTED.value, MechanismStatus.SUPPORTED_WITH_LIMITATIONS.value)]
    out: List[dict] = []
    channels = _UNAVAILABLE_CHANNELS.get(family, ("controlled single-field evidence",))
    for i in range(len(live)):
        for j in range(i + 1, len(live)):
            a, b = live[i], live[j]
            shared = ["the same recurring observation supports both"]
            can_distinguish = False   # honest default: GT7 rarely separates these directly
            out.append(MechanismComparison(
                mechanism_a=a.mechanism_id, mechanism_b=b.mechanism_id,
                evidence_favouring_a=tuple(e.summary for e in a.contradicting_evidence),
                evidence_favouring_b=tuple(e.summary for e in b.contradicting_evidence),
                shared_evidence=tuple(shared),
                contradictory_evidence=(),
                missing_discriminator=("; ".join(channels)),
                gt7_can_distinguish=can_distinguish,
                required_observation=("a controlled single-field test on the same corner, "
                                      "gear and fuel state, comparing valid laps"),
                status="indistinguishable").to_dict())
    return tuple(out[:12])   # cap for display; deterministic prefix


def _aggregate_gt7(ranked, family: str) -> Tuple[str, ...]:
    out: List[str] = []
    seen = set()
    for _, c in ranked:
        for g in c.gt7_limitations:
            if g not in seen:
                seen.add(g)
                out.append(g)
    for ch in _UNAVAILABLE_CHANNELS.get(family, ()):
        line = f"GT7 does not expose {ch}; the app cannot measure it directly."
        if line not in seen:
            seen.add(line)
            out.append(line)
    return tuple(out)


def _evidence_gaps(ranked, family: str, has_high_speed: bool
                   ) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    gaps: List[str] = []
    required: List[str] = []
    competing = [c for _, c in ranked if c.status in (
        MechanismStatus.COMPETING.value, MechanismStatus.PLAUSIBLE.value)]
    if len(competing) >= 2:
        gaps.append("multiple physical mechanisms remain compatible with the evidence")
        required.append("a controlled single-field experiment on the same corner, gear and "
                        "fuel state to separate the competing mechanisms")
    for ch in _UNAVAILABLE_CHANNELS.get(family, ()):
        gaps.append(f"{ch} is not available from GT7 telemetry")
    if any(c.status == MechanismStatus.PLAUSIBLE.value and
           "aero" in c.mechanism_id for c in competing) and not has_high_speed:
        required.append("compare the same corner at different speeds to test aero vs "
                        "mechanical balance")
    required.append("repeat the corner over more valid laps with the same setup")
    # de-dupe, keep order
    return tuple(dict.fromkeys(gaps)), tuple(dict.fromkeys(required))


def _overall_status(primary, competing, contradicted, ranked) -> str:
    if primary is not None:
        return primary["status"]
    if competing:
        # if everything plausible is aero/driver-technique only → plausible, else competing
        statuses = {c["status"] for c in competing}
        if statuses == {MechanismStatus.PLAUSIBLE.value}:
            return MechanismStatus.PLAUSIBLE.value
        return MechanismStatus.COMPETING.value
    if contradicted:
        return MechanismStatus.CONTRADICTED.value
    # nothing survived
    grades = [c for _, c in ranked]
    return MechanismStatus.INSUFFICIENT_EVIDENCE.value


def _audit(diag, phase, *, elig, primary, competing, contradicted, outcome_status,
           prediction_rel) -> Tuple[str, ...]:
    a = [
        f"issue_type={_lc(diag.get('issue_type'))}",
        f"family={_lc(diag.get('issue_family') or diag.get('family'))}",
        f"axle={_lc(diag.get('axle')) or 'unspecified'}",
        f"resolved_phase={phase.value}",
        f"residual={_lc(diag.get('residual_state') or diag.get('latest_state'))}",
        f"primary={primary['mechanism_id'] if primary else 'none'}",
        f"competing={len(competing)}",
        f"contradicted={len(contradicted)}",
    ]
    if outcome_status:
        a.append(f"outcome_status={outcome_status}")
    if prediction_rel.get("has_prediction"):
        a.append(f"prediction={prediction_rel.get('reconciliation_status')}")
    a.append("layer=mechanism_only; observation & intervention authorities untouched")
    return tuple(a)


def _content_fingerprint(diag_key: str, overall: str,
                         cands: Sequence[CausalMechanismCandidate], kv: dict) -> str:
    payload = {
        "diag": diag_key, "overall": overall, "kv": kv,
        "cands": sorted(
            [{"id": c.mechanism_id, "status": c.status, "grade": c.evidence_grade,
              "comp": c.primary_component, "phase": c.handling_phase,
              "mode": c.load_transfer_mode,
              "contra": [e.summary for e in c.contradicting_evidence]}
             for c in cands], key=lambda d: d["id"]),
    }
    return (f"{MECHANISM_ANNOTATION_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True,
                                        separators=(",", ":")).encode()).hexdigest()[:24])


# --------------------------------------------------------------------------- #
# Public: annotate MANY diagnoses (deterministic order + report fingerprint)
# --------------------------------------------------------------------------- #
def annotations_from_memory(memory: Optional[Mapping], *,
                            calibration: Optional[Mapping] = None,
                            context: Optional[Mapping] = None) -> dict:
    """Turn a Phase-8 ``EngineeringMemory`` dict (+ optional Phase-11 calibration) into
    mechanism-annotated diagnoses. Read-only: it regenerates purely from the immutable
    records and mutates nothing. Deterministic. Never raises.

    The cross-session memory IS the canonical set of diagnoses here — each ``IssueMemory``
    is one canonical issue. Failed directions come from the memory's protected knowledge
    (Program-1 authority), protected-good behaviours from its protected behaviours, and the
    per-experiment prediction relationship from the calibration reconciliation records."""
    memory = memory if isinstance(memory, Mapping) else {}
    issues = memory.get("issues") or []
    # Program-1 protected knowledge → failed/locked directions (authoritative, read-only).
    failed = []
    for pk in memory.get("protected_knowledge") or ():
        if not isinstance(pk, Mapping):
            continue
        if _lc(pk.get("kind")) in ("never_move_direction", "known_unstable"):
            fld, direction = _lc(pk.get("field")), _lc(pk.get("direction"))
            if fld:
                failed.append((fld, direction, "lockout"))
    protected_good = tuple(memory.get("protected_behaviours") or ())

    # Reconciliation records indexed by experiment id (for the prediction relationship).
    recon_by_exp: Dict[str, Mapping] = {}
    for r in (calibration or {}).get("records") or ():
        if isinstance(r, Mapping):
            eid = _norm(r.get("experiment_id"))
            if eid:
                recon_by_exp[eid] = r

    diagnoses: List[MechanismAnnotatedDiagnosis] = []
    for iss in issues:
        if not isinstance(iss, Mapping):
            continue
        diag = {
            "issue_family": iss.get("family"), "issue_type": iss.get("issue_type"),
            "axle": iss.get("axle"), "phase": iss.get("phase"),
            "segment_id": iss.get("corner"), "corner": iss.get("corner"),
            "residual_state": iss.get("latest_state"), "recurring": iss.get("recurring"),
            "valid_laps": iss.get("times_observed"),
            "sample_count": iss.get("times_observed"),
            "times_observed": iss.get("times_observed"),
            "sessions_seen": iss.get("sessions_seen"),
            "key": iss.get("issue_key"),
        }
        # attach the reconciliation from the most recent fix experiment, if any
        recon = None
        exp_id = ""
        for eid in list(iss.get("failed_fix_experiments") or ()) + \
                list(iss.get("successful_fix_experiments") or ()):
            if _norm(eid) in recon_by_exp:
                recon = recon_by_exp[_norm(eid)]
                exp_id = _norm(eid)
                break
        ctx = dict(context or {})
        if exp_id:
            ctx.setdefault("experiment_id", exp_id)
        diagnoses.append(annotate_diagnosis(
            diag, context=ctx, reconciliation=recon,
            failed_directions=failed, protected_good=protected_good))

    diagnoses.sort(key=lambda a: a.source_diagnosis_key)
    dicts = [a.to_dict() for a in diagnoses]
    kv = knowledge_versions()
    fp = (f"{MECHANISM_ANNOTATION_VERSION}:memory:"
          + hashlib.sha256(json.dumps(
              {"n": len(dicts), "fps": [a.content_fingerprint for a in diagnoses], "kv": kv},
              sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:24])
    supported = sum(1 for a in diagnoses if a.overall_status in (
        MechanismStatus.SUPPORTED.value, MechanismStatus.SUPPORTED_WITH_LIMITATIONS.value))
    return {"ok": True, "version": MECHANISM_ANNOTATION_VERSION,
            "annotations": dicts, "count": len(dicts), "supported_count": supported,
            "knowledge_versions": kv, "content_fingerprint": fp}


def annotate_diagnoses(diagnoses: Sequence[Mapping], *, context: Optional[Mapping] = None,
                       **kw) -> dict:
    """Annotate a sequence of canonical diagnoses. Deterministic order (by diagnosis key);
    returns a serialisable report with a stable content fingerprint. Never raises."""
    out = []
    for d in diagnoses or ():
        try:
            out.append(annotate_diagnosis(d, context=context, **kw))
        except Exception:
            continue
    out.sort(key=lambda a: a.source_diagnosis_key)
    dicts = [a.to_dict() for a in out]
    kv = knowledge_versions()
    fp = (f"{MECHANISM_ANNOTATION_VERSION}:report:"
          + hashlib.sha256(json.dumps(
              {"n": len(dicts), "fps": [a.content_fingerprint for a in out], "kv": kv},
              sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:24])
    return {"ok": True, "version": MECHANISM_ANNOTATION_VERSION,
            "annotations": dicts, "count": len(dicts),
            "knowledge_versions": kv, "content_fingerprint": fp}
