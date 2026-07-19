"""Post-flight engineering reconciliation (Engineering Brain Phase 11).

After a completed experiment, this READ-ONLY module deterministically compares what the
Engineering Brain PREDICTED (the Phase-10 pre-flight review) against what ACTUALLY
occurred (the Phase-3 outcome + Phase-6 residual state). For every predicted
consequence it assigns a reconciliation status; it assembles an immutable calibration
record. It compares deterministic objects only — no prediction, no learning.

Phase 11 changes nothing: no experiment, no outcome, no memory, no working window, no
setup value. It only measures how accurate the expectation was.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; never raises; no random,
no wall-clock (timestamps are passed in as data).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import List, Mapping, Optional, Sequence, Tuple

from strategy.preflight_validation import (
    ChecklistValidation, validate_checklist,
)
from strategy.prediction_accuracy import PredictionAccuracy, compute_accuracy

POSTFLIGHT_RECONCILIATION_VERSION = "postflight_reconciliation_v1"


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


class ReconciliationStatus(str, Enum):
    CONFIRMED = "confirmed"
    PARTIALLY_CONFIRMED = "partially_confirmed"
    NOT_OBSERVED = "not_observed"
    CONTRADICTED = "contradicted"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    UNKNOWN = "unknown"


# Overall Phase-3 outcome status → the primary-consequence reconciliation status.
_PRIMARY_FROM_STATUS = {
    "confirmed_improvement": ReconciliationStatus.CONFIRMED,
    "partial_improvement": ReconciliationStatus.PARTIALLY_CONFIRMED,
    "no_meaningful_change": ReconciliationStatus.NOT_OBSERVED,
    "regression": ReconciliationStatus.CONTRADICTED,
    "insufficient_evidence": ReconciliationStatus.INSUFFICIENT_EVIDENCE,
    "confounded": ReconciliationStatus.UNKNOWN,
}
# Target-issue residual state → the primary-consequence reconciliation status.
_PRIMARY_FROM_RESIDUAL = {
    "resolved": ReconciliationStatus.CONFIRMED,
    "improved_but_present": ReconciliationStatus.PARTIALLY_CONFIRMED,
    "unchanged": ReconciliationStatus.NOT_OBSERVED,
    "not_observed": ReconciliationStatus.NOT_OBSERVED,
    "worsened": ReconciliationStatus.CONTRADICTED,
    "new": ReconciliationStatus.CONTRADICTED,
    "insufficient_evidence": ReconciliationStatus.INSUFFICIENT_EVIDENCE,
    "invalid_comparison": ReconciliationStatus.INSUFFICIENT_EVIDENCE,
    "ambiguous": ReconciliationStatus.UNKNOWN,
}

# handling-axis / side-effect keyword → observed issue family (for side-effect checks)
_KEYWORD_FAMILY = [
    ("traction", "traction"), ("wheelspin", "traction"),
    ("oversteer", "rotation"), ("rotation", "rotation"), ("understeer", "rotation"),
    ("front support", "rotation"), ("stability", "rotation"),
    ("brak", "braking"), ("lock", "braking"),
    ("kerb", "platform"), ("compliance", "platform"), ("bottom", "platform"),
    ("tyre", "tyre"), ("wear", "tyre"), ("fuel", "fuel"),
]


@dataclass(frozen=True)
class ConsequenceReconciliation:
    kind: str                           # ConsequenceKind value of the prediction
    field: str
    predicted: str                      # the predicted consequence text
    status: str                         # ReconciliationStatus value
    observed: str                       # what was actually observed
    reason: str
    eval_version: str = POSTFLIGHT_RECONCILIATION_VERSION

    def to_dict(self) -> dict:
        return {"kind": self.kind, "field": self.field, "predicted": self.predicted,
                "status": self.status, "observed": self.observed, "reason": self.reason,
                "eval_version": self.eval_version}


def _observed_families(residuals: Sequence[Mapping]) -> set:
    """Issue families that newly regressed / appeared in the observed residual state."""
    fams = set()
    for r in residuals or ():
        if r.get("is_new") or r.get("is_regression") or \
                _lc(r.get("residual_state")) in ("new", "worsened", "good_behaviour_damaged"):
            fams.add(_lc(r.get("family")))
    return fams


def _family_for_text(text: str) -> str:
    t = _lc(text)
    for kw, fam in _KEYWORD_FAMILY:
        if kw in t:
            return fam
    return ""


def _target_status(preflight: Mapping, outcome: Mapping,
                   residuals: Sequence[Mapping]) -> ReconciliationStatus:
    exp = (preflight or {}).get("experiment") or {}
    target = _lc(exp.get("target_issue"))
    if target:
        for r in residuals or ():
            if _lc(r.get("issue_type")) == target:
                return _PRIMARY_FROM_RESIDUAL.get(
                    _lc(r.get("residual_state")), ReconciliationStatus.UNKNOWN)
    return _PRIMARY_FROM_STATUS.get(_lc(outcome.get("status")),
                                    ReconciliationStatus.UNKNOWN)


def reconcile_consequences(
    preflight: Mapping, outcome: Mapping, residuals: Sequence[Mapping],
) -> Tuple[ConsequenceReconciliation, ...]:
    """Classify every predicted consequence against the observed outcome + residuals.
    Deterministic; consumes only the Phase-10 review + Phase-3 outcome + Phase-6
    residuals. Never mutates its inputs."""
    preflight = preflight or {}
    outcome = outcome or {}
    residuals = list(residuals or ())
    consequences = (preflight.get("review") or preflight).get("consequences") or []
    observed_fams = _observed_families(residuals)
    any_regression = bool(observed_fams) or _lc(outcome.get("status")) == "regression"
    status = _lc(outcome.get("status"))
    insufficient = status in ("insufficient_evidence", "confounded", "")
    out: List[ConsequenceReconciliation] = []

    for c in consequences:
        kind = _lc(c.get("kind"))
        field = _norm(c.get("field"))
        text = _norm(c.get("text"))

        if kind == "primary_effect":
            st = _target_status(preflight, outcome, residuals)
            observed = f"outcome status={status or 'unknown'}"
            reason = "target issue " + {
                "confirmed": "resolved as predicted",
                "partially_confirmed": "improved but still present",
                "not_observed": "unchanged",
                "contradicted": "worsened",
                "insufficient_evidence": "not measurable",
                "unknown": "ambiguous",
            }.get(st.value, "unknown")

        elif kind == "side_effect":
            if insufficient:
                st, observed, reason = (ReconciliationStatus.INSUFFICIENT_EVIDENCE,
                                        "not measurable", "no comparable evidence")
            else:
                fam = _family_for_text(text)
                hit = (fam and fam in observed_fams) or (not fam and any_regression)
                if hit:
                    st, observed = ReconciliationStatus.CONFIRMED, "the side effect appeared"
                    reason = "a matching regression was observed"
                else:
                    st, observed = ReconciliationStatus.NOT_OBSERVED, "the side effect did not appear"
                    reason = "no matching regression was observed"

        elif kind == "historical":
            if insufficient:
                st, observed, reason = (ReconciliationStatus.INSUFFICIENT_EVIDENCE,
                                        "not measurable", "no comparable evidence")
            elif status == "regression":
                st, observed, reason = (ReconciliationStatus.CONTRADICTED,
                                        "regressed this time", "history did not repeat")
            elif status in ("confirmed_improvement", "partial_improvement"):
                st, observed, reason = (ReconciliationStatus.CONFIRMED,
                                        "improved as history suggested", "history repeated")
            else:
                st, observed, reason = (ReconciliationStatus.NOT_OBSERVED,
                                        "no meaningful change", "history did not repeat")

        elif kind == "working_window":
            if insufficient:
                st, observed, reason = (ReconciliationStatus.INSUFFICIENT_EVIDENCE,
                                        "not measurable", "no comparable evidence")
            elif status == "regression" or _lc(field) in observed_fams:
                st, observed, reason = (ReconciliationStatus.CONTRADICTED,
                                        "a regression occurred", "the window did not hold")
            else:
                st, observed, reason = (ReconciliationStatus.CONFIRMED,
                                        "no window violation", "the window held")

        else:  # interaction
            fam = _family_for_text(text)
            if fam and fam in observed_fams:
                st, observed, reason = (ReconciliationStatus.CONFIRMED,
                                        "a coupled effect appeared", "coupled issue observed")
            elif insufficient:
                st, observed, reason = (ReconciliationStatus.INSUFFICIENT_EVIDENCE,
                                        "not measurable", "coupling not directly observable")
            else:
                st, observed, reason = (ReconciliationStatus.NOT_OBSERVED,
                                        "no coupled effect appeared", "no coupled issue observed")

        out.append(ConsequenceReconciliation(
            kind=kind, field=field, predicted=text, status=st.value,
            observed=observed, reason=reason))
    return tuple(out)


# --------------------------------------------------------------------------- #
# Immutable calibration record
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ReconciliationRecord:
    record_key: str
    memory_context_key: str
    experiment_id: str
    outcome_id: str
    predicted_risk: str
    outcome_status: str
    recorded_at: str
    prediction_fingerprint: str
    consequence_reconciliations: Tuple[ConsequenceReconciliation, ...]
    checklist_validations: Tuple[ChecklistValidation, ...]
    accuracy: PredictionAccuracy
    context: dict
    content_fingerprint: str
    eval_version: str = POSTFLIGHT_RECONCILIATION_VERSION

    def to_dict(self) -> dict:
        return {
            "record_key": self.record_key,
            "memory_context_key": self.memory_context_key,
            "experiment_id": self.experiment_id, "outcome_id": self.outcome_id,
            "predicted_risk": self.predicted_risk,
            "outcome_status": self.outcome_status, "recorded_at": self.recorded_at,
            "prediction_fingerprint": self.prediction_fingerprint,
            "consequence_reconciliations": [c.to_dict() for c in self.consequence_reconciliations],
            "checklist_validations": [c.to_dict() for c in self.checklist_validations],
            "accuracy": self.accuracy.to_dict(), "context": dict(self.context),
            "content_fingerprint": self.content_fingerprint,
            "eval_version": self.eval_version,
        }


def build_reconciliation_record(
    preflight: Mapping, outcome: Mapping, residuals: Sequence[Mapping], *,
    memory_context_key: str = "", context: Optional[Mapping] = None,
    recorded_at: str = "",
) -> Optional[ReconciliationRecord]:
    """Build ONE immutable calibration record reconciling the Phase-10 prediction with
    the Phase-3 outcome + Phase-6 residuals. Pure; deterministic; ``recorded_at`` is
    supplied (never read from the clock). Returns None if inputs are unusable."""
    if not isinstance(preflight, Mapping) or not isinstance(outcome, Mapping):
        return None
    review = preflight.get("review") or preflight
    experiment = review.get("experiment") or {}
    outcome_id = _norm(outcome.get("id") or outcome.get("outcome_id"))
    outcome_status = _norm(outcome.get("status"))
    experiment_id = _norm(experiment.get("candidate_id") or outcome.get("experiment_id"))
    pred_fp = _norm(review.get("content_fingerprint"))

    cons = reconcile_consequences(preflight, outcome, residuals)
    checks = validate_checklist(preflight, outcome, residuals)
    accuracy = compute_accuracy(cons, checks)

    payload = {
        "ctx": memory_context_key, "exp": experiment_id, "out": outcome_id,
        "pred": pred_fp, "status": outcome_status,
        "cons": [c.to_dict() for c in cons],
        "checks": [c.to_dict() for c in checks],
        "accuracy": accuracy.to_dict(),
    }
    content_fp = (f"{POSTFLIGHT_RECONCILIATION_VERSION}:"
                  + hashlib.sha256(_dumps(payload).encode()).hexdigest()[:24])
    record_key = (f"{POSTFLIGHT_RECONCILIATION_VERSION}:rec:"
                  + hashlib.sha256("|".join(
                      (memory_context_key, experiment_id, outcome_id, pred_fp)
                  ).encode()).hexdigest()[:24])
    return ReconciliationRecord(
        record_key=record_key, memory_context_key=_norm(memory_context_key),
        experiment_id=experiment_id, outcome_id=outcome_id,
        predicted_risk=_norm(review.get("risk_level")), outcome_status=outcome_status,
        recorded_at=_norm(recorded_at), prediction_fingerprint=pred_fp,
        consequence_reconciliations=cons, checklist_validations=checks,
        accuracy=accuracy, context=dict(context or {}), content_fingerprint=content_fp)


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
