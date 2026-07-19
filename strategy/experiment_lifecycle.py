"""Guarded Experiment Lifecycle orchestration (Engineering Brain Program 2, Phase 16).

The deterministic orchestration layer that CLOSES the Engineering-Brain loop by connecting
existing authorities — it creates NO new experiment system, Apply path, outcome recorder or
reconciler. It converts a READY Phase-15 bounded experiment into a canonical
``SetupExperiment`` request (via the existing ``build_experiment_from_recommendation``),
routes it through the existing Phase-10 preflight, and — for an already-executed experiment —
assembles a read-only lifecycle summary from the existing Phase-3 outcome, Phase-11
reconciliation and prediction-calibration records.

It NEVER: applies a setup, bypasses the frozen Apply gate, persists/duplicates an experiment,
creates an outcome or reconciliation, invents driver feedback, simulates results, or mutates
any diagnosis / mechanism / hypothesis / setup-history / active-setup / calibration. The only
mutation route to the car remains the existing Apply gate; the only experiment persistence
route remains the existing explicit ``create_setup_experiment`` workflow.

Every object preserves the full provenance chain: diagnosis -> mechanism -> hypothesis ->
synthesis -> experiment -> outcome -> reconciliation -> prediction calibration.

Purity: Qt-free, DB-free (no sqlite / SessionDB), UI-free, network-free, AI-free; no random,
no wall-clock (timestamps are data); deterministic; never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Mapping, Optional, Tuple

from strategy.experiment_synthesis import EXPERIMENT_SYNTHESIS_VERSION, ExperimentSynthesisStatus
from strategy.setup_experiment import build_experiment_from_recommendation

EXPERIMENT_LIFECYCLE_VERSION = "experiment_lifecycle_v1"
EXPERIMENT_LIFECYCLE_SCHEMA = 1

# The recommendation status Phase-15 candidates carry into the canonical experiment builder.
# "approved" is the honest framing: a bounded change that passed every synthesis gate and is
# safe to surface/apply AS A TEST (the frozen Apply gate remains the sole mutation route).
_APPROVED_STATUS = "approved"


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


class ExperimentLifecycleState(str, Enum):
    NOT_ACTIONABLE = "not_actionable"           # candidate not READY / not a valid experiment
    EXPERIMENT_BUILT = "experiment_built"        # canonical SetupExperiment constructed
    PREFLIGHT_FAILED = "preflight_failed"        # the preflight build itself failed
    READY_FOR_MANUAL_APPLY = "ready_for_manual_apply"   # preflight passed; awaiting Apply gate
    AWAITING_APPLY = "awaiting_apply"            # persisted, not yet applied in GT7
    APPLIED = "applied"
    TEST_IN_PROGRESS = "test_in_progress"
    READY_FOR_REVIEW = "ready_for_review"
    OUTCOME_RECORDED = "outcome_recorded"        # Phase-3 outcome exists
    RECONCILED = "reconciled"                    # Phase-11 reconciliation exists
    CALIBRATED = "calibrated"                    # calibration reflects it
    COMPLETED = "completed"
    REJECTED = "rejected"
    REVERTED = "reverted"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


# existing ExperimentStatus value -> lifecycle state (for a persisted experiment)
_EXP_STATUS_STATE = {
    "draft": ExperimentLifecycleState.EXPERIMENT_BUILT,
    "ready_for_apply": ExperimentLifecycleState.READY_FOR_MANUAL_APPLY,
    "applied": ExperimentLifecycleState.APPLIED,
    "test_in_progress": ExperimentLifecycleState.TEST_IN_PROGRESS,
    "ready_for_review": ExperimentLifecycleState.READY_FOR_REVIEW,
    "completed": ExperimentLifecycleState.COMPLETED,
    "rejected": ExperimentLifecycleState.REJECTED,
    "reverted": ExperimentLifecycleState.REVERTED,
    "cancelled": ExperimentLifecycleState.BLOCKED,
    "invalid": ExperimentLifecycleState.BLOCKED,
}


# --------------------------------------------------------------------------- #
# Traceability
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class LifecycleTrace:
    """The unbroken provenance chain. Every field is a stable id / fingerprint that links a
    stage to the previous authority — nothing is lost between stages."""

    diagnosis_key: str = ""
    mechanism_ids: Tuple[str, ...] = ()
    hypothesis_ids: Tuple[str, ...] = ()
    hypothesis_set_fingerprint: str = ""
    synthesis_candidate_id: str = ""
    synthesis_fingerprint: str = ""
    baseline_setup_hash: str = ""
    experiment_id: str = ""
    experiment_idempotency_key: str = ""
    outcome_id: str = ""
    prediction_fingerprint: str = ""
    reconciliation_record_key: str = ""

    def to_dict(self) -> dict:
        return {
            "diagnosis_key": self.diagnosis_key, "mechanism_ids": list(self.mechanism_ids),
            "hypothesis_ids": list(self.hypothesis_ids),
            "hypothesis_set_fingerprint": self.hypothesis_set_fingerprint,
            "synthesis_candidate_id": self.synthesis_candidate_id,
            "synthesis_fingerprint": self.synthesis_fingerprint,
            "baseline_setup_hash": self.baseline_setup_hash,
            "experiment_id": self.experiment_id,
            "experiment_idempotency_key": self.experiment_idempotency_key,
            "outcome_id": self.outcome_id,
            "prediction_fingerprint": self.prediction_fingerprint,
            "reconciliation_record_key": self.reconciliation_record_key,
        }

    def is_unbroken_to(self, stage: str) -> bool:
        """True when every link UP TO ``stage`` is present (deterministic completeness check)."""
        order = ["diagnosis", "mechanism", "hypothesis", "synthesis", "experiment",
                 "outcome", "reconciliation"]
        present = {
            "diagnosis": bool(self.diagnosis_key),
            "mechanism": bool(self.mechanism_ids),
            "hypothesis": bool(self.hypothesis_ids),
            "synthesis": bool(self.synthesis_candidate_id),
            "experiment": bool(self.experiment_id or self.experiment_idempotency_key),
            "outcome": bool(self.outcome_id),
            "reconciliation": bool(self.reconciliation_record_key),
        }
        if stage not in order:
            return False
        return all(present[s] for s in order[:order.index(stage) + 1])


# --------------------------------------------------------------------------- #
# Execution request / result (forward path: synthesis -> experiment -> preflight)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ExperimentExecutionRequest:
    """An immutable description of the canonical experiment to create through the EXISTING
    workflow. It carries the canonical ``SetupExperiment`` (unpersisted) + the Phase-10
    preflight ``selection`` + full provenance. It is a request, not a mutation."""

    actionable: bool
    reason: str
    recommendation_data: dict           # the input to build_experiment_from_recommendation
    selection: dict                     # the Phase-10 preflight selection dict
    setup_experiment: Optional[dict]    # canonical SetupExperiment.to_dict() or None
    trace: LifecycleTrace
    baseline: dict
    scope: dict

    def to_dict(self) -> dict:
        return {
            "actionable": self.actionable, "reason": self.reason,
            "recommendation_data": dict(self.recommendation_data),
            "selection": dict(self.selection),
            "setup_experiment": (dict(self.setup_experiment) if self.setup_experiment else None),
            "trace": self.trace.to_dict(), "baseline": dict(self.baseline),
            "scope": dict(self.scope),
        }


@dataclass(frozen=True)
class ExperimentExecutionResult:
    request: dict
    preflight_review: Optional[dict]
    lifecycle_state: str
    trace: LifecycleTrace
    next_action: str
    safety_statement: str
    audit: Tuple[str, ...]
    content_fingerprint: str
    schema_version: int = EXPERIMENT_LIFECYCLE_SCHEMA
    eval_version: str = EXPERIMENT_LIFECYCLE_VERSION

    def to_dict(self) -> dict:
        return {
            "request": dict(self.request),
            "preflight_review": (dict(self.preflight_review) if self.preflight_review else None),
            "lifecycle_state": self.lifecycle_state, "trace": self.trace.to_dict(),
            "next_action": self.next_action, "safety_statement": self.safety_statement,
            "audit": list(self.audit), "content_fingerprint": self.content_fingerprint,
            "schema_version": self.schema_version, "eval_version": self.eval_version,
        }


# --------------------------------------------------------------------------- #
# Lifecycle summary (closed loop: experiment -> outcome -> reconciliation -> calibration)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ExperimentLifecycleSummary:
    lifecycle_state: str
    trace: LifecycleTrace
    diagnosis: dict
    mechanism: dict
    hypothesis: dict
    synthesis: dict
    experiment: dict
    preflight_state: str
    apply_state: str
    outcome: dict
    reconciliation: dict
    calibration: dict
    stage_states: dict                  # {stage: present/absent/state}
    safety_statement: str
    content_fingerprint: str
    schema_version: int = EXPERIMENT_LIFECYCLE_SCHEMA
    eval_version: str = EXPERIMENT_LIFECYCLE_VERSION

    def to_dict(self) -> dict:
        return {
            "lifecycle_state": self.lifecycle_state, "trace": self.trace.to_dict(),
            "diagnosis": dict(self.diagnosis), "mechanism": dict(self.mechanism),
            "hypothesis": dict(self.hypothesis), "synthesis": dict(self.synthesis),
            "experiment": dict(self.experiment), "preflight_state": self.preflight_state,
            "apply_state": self.apply_state, "outcome": dict(self.outcome),
            "reconciliation": dict(self.reconciliation), "calibration": dict(self.calibration),
            "stage_states": dict(self.stage_states),
            "safety_statement": self.safety_statement,
            "content_fingerprint": self.content_fingerprint,
            "schema_version": self.schema_version, "eval_version": self.eval_version,
        }


_SAFETY = ("Read-only orchestration. It connects existing authorities only: the canonical "
           "experiment builder, the Phase-10 preflight, the frozen Apply gate, the Phase-3 "
           "outcome, the Phase-11 reconciliation and the prediction calibration. It applies "
           "nothing, persists no experiment, records no outcome, and mutates nothing - the "
           "Apply gate remains the sole route to the car.")


# --------------------------------------------------------------------------- #
# Forward path
# --------------------------------------------------------------------------- #
def _candidate_trace(candidate: Mapping) -> LifecycleTrace:
    hset_fp = _norm(candidate.get("source_hypothesis_set_fingerprint"))
    hyp_ids = tuple(_norm(x) for x in (candidate.get("selected_hypothesis_ids") or ()) if _norm(x))
    mech_ids = tuple(dict.fromkeys(
        _norm(d.get("source_mechanism_id")) for d in (candidate.get("deltas") or [])
        if _norm(d.get("source_mechanism_id"))))
    base = candidate.get("baseline") or {}
    return LifecycleTrace(
        hypothesis_ids=hyp_ids, mechanism_ids=mech_ids,
        hypothesis_set_fingerprint=hset_fp,
        synthesis_candidate_id=_norm(candidate.get("candidate_id")),
        synthesis_fingerprint=_norm(candidate.get("content_fingerprint")),
        baseline_setup_hash=_norm(base.get("setup_hash")))


def build_execution_request(candidate: Optional[Mapping], *,
                            diagnosis_key: str = "", scope: Optional[Mapping] = None
                            ) -> ExperimentExecutionRequest:
    """Map a READY Phase-15 ``BoundedSetupExperiment`` dict into a canonical experiment
    request via the EXISTING ``build_experiment_from_recommendation``. Pure; deterministic;
    persists nothing; applies nothing. Non-READY / invalid candidates are NOT actionable."""
    candidate = candidate if isinstance(candidate, Mapping) else {}
    scope = dict(scope or {})
    trace = _candidate_trace(candidate)
    if diagnosis_key:
        trace = _with(trace, diagnosis_key=diagnosis_key)

    status = _lc(candidate.get("status"))
    deltas = list(candidate.get("deltas") or [])
    if status != ExperimentSynthesisStatus.READY_FOR_PREFLIGHT.value or not deltas:
        return ExperimentExecutionRequest(
            actionable=False,
            reason=(f"candidate is not READY_FOR_PREFLIGHT (status={status or 'none'})"
                    if deltas else "candidate has no bounded delta"),
            recommendation_data={}, selection={}, setup_experiment=None, trace=trace,
            baseline=dict(candidate.get("baseline") or {}), scope=scope)

    # Build the recommendation data for the EXISTING canonical experiment builder.
    changes = []
    for d in deltas:
        changes.append({
            "field": _norm(d.get("field")),
            "from": d.get("baseline_value"),
            "to": d.get("candidate_value"),
            "rationale": _norm(d.get("expected_benefit")),
            "symptom": _norm((candidate.get("canonical_issue") or {}).get("issue_type"))
            or _norm(scope.get("issue_type")),
            "risk_level": "low" if d.get("is_exactly_one_step") else "moderate",
            "confidence_level": _norm(candidate.get("evidence_grade")),
            "rule_id": f"{EXPERIMENT_LIFECYCLE_VERSION}:{_norm(d.get('source_hypothesis_id'))}",
        })
    baseline = dict(candidate.get("baseline") or {})
    rec_data = {
        "recommendation_status": _APPROVED_STATUS,
        "recommendation_source": "engineering_brain_phase15_synthesis",
        "changes": changes,
        "diagnosis": {"issue_type": _norm((candidate.get("canonical_issue") or {}).get("issue_type"))},
        "hypothesis": {
            "statement": _norm(candidate.get("explanation")),
            "primary_diagnosis": diagnosis_key,
        },
        "protected_behaviours": [{"description": b} for b in
                                 (candidate.get("protected_good_behaviours") or [])],
    }
    exp = None
    try:
        se = build_experiment_from_recommendation(
            rec_data, recommendation_source="engineering_brain_phase15_synthesis",
            track=_norm(scope.get("track")), layout_id=_norm(scope.get("layout_id")),
            discipline=_norm(scope.get("discipline")),
            parent_setup_id=_norm(baseline.get("setup_id")),
            label=f"P15 test: {changes[0]['field']} {deltas[0].get('direction')}")
        exp = se.to_dict() if se is not None else None
    except Exception:
        exp = None

    if exp is not None:
        trace = _with(trace,
                      experiment_idempotency_key=_norm(exp.get("idempotency_key")))

    primary = deltas[0]
    selection = {
        "candidate_id": trace.synthesis_candidate_id,
        "field": _norm(primary.get("field")),
        "direction": _direction_word(_norm(primary.get("direction"))),
        "current_value": primary.get("baseline_value"),
        "proposed_value": primary.get("candidate_value"),
        "delta": primary.get("delta"),
        "target_issue": _norm((candidate.get("canonical_issue") or {}).get("issue_type")),
        "target_phase": _norm(candidate.get("test_protocol", {}).get("target_handling_phase")),
        "hypothesis": _norm(candidate.get("explanation")),
        "window_relationship": "", "evidence_grade": _norm(candidate.get("evidence_grade")),
    }
    return ExperimentExecutionRequest(
        actionable=(exp is not None), reason=("" if exp is not None else
                    "the canonical experiment builder returned no actionable experiment"),
        recommendation_data=rec_data, selection=selection, setup_experiment=exp,
        trace=trace, baseline=baseline, scope=scope)


_DIRECTION_WORD = {
    "stiffen": "increase", "soften": "decrease", "raise": "increase", "lower": "decrease",
    "increase": "increase", "decrease": "decrease", "increase_locking": "increase",
    "decrease_locking": "decrease", "move_rearward": "increase", "move_forward": "decrease",
    "shorten": "increase", "lengthen": "decrease",
}


def _direction_word(direction: str) -> str:
    return _DIRECTION_WORD.get(_lc(direction), "change")


def assemble_execution_result(request: ExperimentExecutionRequest,
                              preflight_review: Optional[Mapping], *,
                              recorded_at: str = "") -> ExperimentExecutionResult:
    """Route the request through the (already-run) Phase-10 preflight review into a lifecycle
    state. Preflight is advisory and NEVER blocks (Phase 10) — a failed preflight *build*
    (``ok`` false / None) yields PREFLIGHT_FAILED; otherwise READY_FOR_MANUAL_APPLY."""
    trace = request.trace
    if not request.actionable:
        state = ExperimentLifecycleState.NOT_ACTIONABLE
        review = None
        nxt = "no canonical experiment to route (candidate not READY / not actionable)"
    elif not isinstance(preflight_review, Mapping) or not preflight_review.get("ok"):
        state = ExperimentLifecycleState.PREFLIGHT_FAILED
        review = dict(preflight_review) if isinstance(preflight_review, Mapping) else None
        nxt = "preflight review could not be built; do not proceed"
    else:
        state = ExperimentLifecycleState.READY_FOR_MANUAL_APPLY
        review = dict(preflight_review)
        nxt = ("review the preflight, then create + apply the experiment through the EXISTING "
               "experiment workflow and frozen Apply gate (manual)")
    audit = (
        f"actionable={request.actionable}",
        f"state={state.value}",
        f"trace_to_synthesis={trace.is_unbroken_to('synthesis')}",
        "layer=orchestration_only; applies nothing, persists nothing",
    )
    fp = _fp("exec", {
        "req": request.to_dict().get("setup_experiment") and
        request.recommendation_data, "state": state.value,
        "cand": trace.synthesis_candidate_id, "syn": trace.synthesis_fingerprint,
        "pf": _norm((review or {}).get("review", {}).get("content_fingerprint")) if review else "",
    })
    return ExperimentExecutionResult(
        request=request.to_dict(), preflight_review=review, lifecycle_state=state.value,
        trace=trace, next_action=nxt, safety_statement=_SAFETY, audit=audit,
        content_fingerprint=fp)


# --------------------------------------------------------------------------- #
# Closed loop
# --------------------------------------------------------------------------- #
def assemble_lifecycle_summary(
    *, candidate: Optional[Mapping] = None, annotation: Optional[Mapping] = None,
    hypothesis_set: Optional[Mapping] = None, experiment: Optional[Mapping] = None,
    outcome: Optional[Mapping] = None, reconciliation: Optional[Mapping] = None,
    calibration: Optional[Mapping] = None, preflight_state: str = "",
    diagnosis_key: str = "",
) -> ExperimentLifecycleSummary:
    """Assemble the full read-only closed-loop summary from EXISTING records. It reads the
    Phase-3 outcome, Phase-11 reconciliation and prediction calibration — it creates none of
    them. Deterministic; never raises; mutates nothing."""
    candidate = dict(candidate or {})
    hypothesis_set = dict(hypothesis_set or {})
    annotation = dict(annotation or (hypothesis_set.get("source_annotation") or {}))
    experiment = dict(experiment or {})
    outcome = dict(outcome or {})
    reconciliation = dict(reconciliation or {})
    calibration = dict(calibration or {})

    issue = dict(hypothesis_set.get("canonical_issue")
                 or annotation.get("canonical_issue") or candidate.get("canonical_issue") or {})
    diag_key = diagnosis_key or _norm(hypothesis_set.get("source_diagnosis_key")) \
        or _norm(annotation.get("source_diagnosis_key"))

    trace = _candidate_trace(candidate) if candidate else LifecycleTrace()
    trace = _with(
        trace, diagnosis_key=diag_key,
        experiment_id=_norm(experiment.get("id") or experiment.get("experiment_id")),
        experiment_idempotency_key=_norm(experiment.get("idempotency_key")
                                         or trace.experiment_idempotency_key),
        outcome_id=_norm(outcome.get("id") or outcome.get("outcome_id")),
        prediction_fingerprint=_norm(reconciliation.get("prediction_fingerprint")),
        reconciliation_record_key=_norm(reconciliation.get("record_key")))
    if not trace.mechanism_ids:
        pm = annotation.get("primary_mechanism") or {}
        if pm.get("mechanism_id"):
            trace = _with(trace, mechanism_ids=(_norm(pm.get("mechanism_id")),))

    exp_status = _lc(experiment.get("status"))
    outcome_status = _lc(outcome.get("status"))
    has_recon = bool(reconciliation.get("record_key") or reconciliation.get("content_fingerprint"))
    calibrated = int((calibration or {}).get("reconciliations")
                     or (calibration or {}).get("record_count") or 0) > 0

    # derive the furthest-reached lifecycle state
    if has_recon:
        state = ExperimentLifecycleState.CALIBRATED if calibrated \
            else ExperimentLifecycleState.RECONCILED
    elif outcome_status:
        state = ExperimentLifecycleState.OUTCOME_RECORDED
    elif exp_status:
        state = _EXP_STATUS_STATE.get(exp_status, ExperimentLifecycleState.UNKNOWN)
    elif candidate:
        state = ExperimentLifecycleState.READY_FOR_MANUAL_APPLY \
            if _lc(candidate.get("status")) == ExperimentSynthesisStatus.READY_FOR_PREFLIGHT.value \
            else ExperimentLifecycleState.NOT_ACTIONABLE
    else:
        state = ExperimentLifecycleState.UNKNOWN

    apply_state = ("applied" if exp_status in ("applied", "test_in_progress", "ready_for_review",
                                               "completed") else
                   "awaiting_manual_apply" if candidate or exp_status in ("draft", "ready_for_apply")
                   else "n/a")
    pm = annotation.get("primary_mechanism") or {}
    stage_states = {
        "diagnosis": "present" if issue else "absent",
        "mechanism": "present" if (trace.mechanism_ids or pm) else "absent",
        "hypothesis": "present" if trace.hypothesis_ids else "absent",
        "synthesis": _lc(candidate.get("status")) or ("present" if candidate else "absent"),
        "experiment": exp_status or ("built" if trace.experiment_idempotency_key else "absent"),
        "preflight": _norm(preflight_state) or ("ready" if candidate else "absent"),
        "apply": apply_state,
        "outcome": outcome_status or "absent",
        "reconciliation": "present" if has_recon else "absent",
        "calibration": "present" if calibrated else "absent",
    }
    summary = {
        "issue": issue, "primary_mechanism": pm.get("name", ""),
        "candidate_id": trace.synthesis_candidate_id,
        "experiment_id": trace.experiment_id, "outcome_status": outcome_status,
        "reconciliation": has_recon,
    }
    fp = _fp("summary", {
        "diag": diag_key, "cand": trace.synthesis_candidate_id, "exp": trace.experiment_id,
        "out": trace.outcome_id, "recon": trace.reconciliation_record_key,
        "state": state.value, "stages": stage_states,
    })
    return ExperimentLifecycleSummary(
        lifecycle_state=state.value, trace=trace, diagnosis=issue,
        mechanism={"name": pm.get("name", ""), "status": pm.get("status", ""),
                   "id": _norm(pm.get("mechanism_id"))},
        hypothesis={"ids": list(trace.hypothesis_ids),
                    "overall_status": _norm(hypothesis_set.get("overall_status"))},
        synthesis={"candidate_id": trace.synthesis_candidate_id,
                   "status": _norm(candidate.get("status")),
                   "fingerprint": trace.synthesis_fingerprint},
        experiment={"id": trace.experiment_id, "status": exp_status,
                    "idempotency_key": trace.experiment_idempotency_key},
        preflight_state=_norm(preflight_state), apply_state=apply_state,
        outcome={"id": trace.outcome_id, "status": outcome_status,
                 "confidence_level": _norm(outcome.get("confidence_level"))},
        reconciliation={"record_key": trace.reconciliation_record_key,
                        "outcome_status": _norm(reconciliation.get("outcome_status")),
                        "prediction_fingerprint": trace.prediction_fingerprint},
        calibration={"reconciliations": int((calibration or {}).get("reconciliations") or 0),
                     "overall_accuracy": (calibration or {}).get("overall_accuracy")},
        stage_states=stage_states, safety_statement=_SAFETY, content_fingerprint=fp)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _with(trace: LifecycleTrace, **kw) -> LifecycleTrace:
    data = {k: getattr(trace, k) for k in trace.__dataclass_fields__}
    data.update({k: v for k, v in kw.items() if v not in ("", (), None) or k in data})
    # only override with truthy values (never blank an existing link)
    for k, v in kw.items():
        if v in ("", (), None):
            data[k] = getattr(trace, k)
        else:
            data[k] = v
    return LifecycleTrace(**data)


def knowledge_versions() -> dict:
    return {"experiment_lifecycle": EXPERIMENT_LIFECYCLE_VERSION,
            "experiment_synthesis": EXPERIMENT_SYNTHESIS_VERSION,
            "schema": EXPERIMENT_LIFECYCLE_SCHEMA}


def _fp(kind: str, payload: dict) -> str:
    body = {"kind": kind, "kv": knowledge_versions(), "p": payload}
    return (f"{EXPERIMENT_LIFECYCLE_VERSION}:{kind}:"
            + hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"),
                                        default=str).encode()).hexdigest()[:24])
