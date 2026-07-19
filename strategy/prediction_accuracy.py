"""Deterministic prediction-accuracy metrics (Engineering Brain Phase 11).

From the reconciled consequences + validated checklist, computes deterministic accuracy
metrics: how well the primary consequence, the side effects, the risks, the constraints,
the historical transfers and the checklist matched reality. No statistics, no learning —
plain deterministic ratios over classified objects.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; never raises; no random,
no wall-clock.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import List, Mapping, Sequence, Tuple

PREDICTION_ACCURACY_VERSION = "prediction_accuracy_v1"

# Consequence statuses that count as "accurate" per consequence kind, and the ones that
# are simply not evaluable (excluded from the denominator).
_NOT_EVALUABLE = {"insufficient_evidence", "unknown"}


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _ratio(hit: float, total: int) -> float:
    return round(hit / total, 4) if total else 0.0


@dataclass(frozen=True)
class PredictionAccuracy:
    primary_consequence_accuracy: float
    side_effect_accuracy: float
    risk_accuracy: float
    constraint_accuracy: float
    historical_transfer_usefulness: float
    checklist_usefulness: float
    overall_accuracy: float
    evaluable_count: int
    confirmed_count: int
    contradicted_count: int
    content_fingerprint: str
    eval_version: str = PREDICTION_ACCURACY_VERSION

    def to_dict(self) -> dict:
        return {
            "primary_consequence_accuracy": self.primary_consequence_accuracy,
            "side_effect_accuracy": self.side_effect_accuracy,
            "risk_accuracy": self.risk_accuracy,
            "constraint_accuracy": self.constraint_accuracy,
            "historical_transfer_usefulness": self.historical_transfer_usefulness,
            "checklist_usefulness": self.checklist_usefulness,
            "overall_accuracy": self.overall_accuracy,
            "evaluable_count": self.evaluable_count,
            "confirmed_count": self.confirmed_count,
            "contradicted_count": self.contradicted_count,
            "content_fingerprint": self.content_fingerprint,
            "eval_version": self.eval_version,
        }


def _by_kind(cons: Sequence[Mapping], kind: str) -> list:
    return [c for c in cons if _lc(getattr(c, "kind", None) or c.get("kind")) == kind]


def _status(c) -> str:
    return _lc(getattr(c, "status", None) or (c.get("status") if isinstance(c, Mapping) else ""))


def _primary_accuracy(cons) -> Tuple[float, int]:
    items = [c for c in cons if _lc(_kind(c)) == "primary_effect"]
    ev = [c for c in items if _status(c) not in _NOT_EVALUABLE]
    if not ev:
        return 0.0, 0
    score = sum(1.0 if _status(c) == "confirmed" else 0.5 if _status(c) == "partially_confirmed"
                else 0.0 for c in ev)
    return _ratio(score, len(ev)), len(ev)


def _kind(c) -> str:
    return getattr(c, "kind", None) or (c.get("kind") if isinstance(c, Mapping) else "")


def _side_effect_accuracy(cons) -> Tuple[float, int]:
    items = [c for c in cons if _lc(_kind(c)) == "side_effect"]
    ev = [c for c in items if _status(c) not in _NOT_EVALUABLE]
    if not ev:
        return 0.0, 0
    # a side-effect prediction is accurate when it materialised (confirmed) or was a
    # correctly-cautious note that did not fire (not_observed); wrong only if contradicted.
    good = sum(1 for c in ev if _status(c) in ("confirmed", "not_observed"))
    return _ratio(good, len(ev)), len(ev)


def _historical_usefulness(cons) -> Tuple[float, int]:
    items = [c for c in cons if _lc(_kind(c)) == "historical"]
    ev = [c for c in items if _status(c) not in _NOT_EVALUABLE]
    if not ev:
        return 0.0, 0
    good = sum(1 for c in ev if _status(c) == "confirmed")
    return _ratio(good, len(ev)), len(ev)


def _window_accuracy(cons) -> Tuple[float, int]:
    items = [c for c in cons if _lc(_kind(c)) == "working_window"]
    ev = [c for c in items if _status(c) not in _NOT_EVALUABLE]
    if not ev:
        return 0.0, 0
    good = sum(1 for c in ev if _status(c) == "confirmed")
    return _ratio(good, len(ev)), len(ev)


def _checklist_metrics(checks) -> Tuple[float, float, int]:
    """(risk_accuracy, checklist_usefulness, evaluable). Risk items are the caution
    items that flag a regression/risk; usefulness = fraction of all evaluable items
    whose `useful` flag is True."""
    def _out(c):
        return _lc(getattr(c, "outcome", None) or (c.get("outcome") if isinstance(c, Mapping) else ""))

    def _useful(c):
        v = getattr(c, "useful", None)
        return bool(c.get("useful")) if v is None and isinstance(c, Mapping) else bool(v)

    def _status_c(c):
        return _lc(getattr(c, "status", None) or (c.get("status") if isinstance(c, Mapping) else ""))

    def _label(c):
        return _lc(getattr(c, "label", None) or (c.get("label") if isinstance(c, Mapping) else ""))

    evaluable = [c for c in checks if _out(c) not in ("insufficient_evidence", "not_applicable")]
    useful = _ratio(sum(1 for c in evaluable if _useful(c)), len(evaluable)) if evaluable else 0.0

    risk_items = [c for c in evaluable if _status_c(c) == "caution"
                  and ("regression" in _label(c) or "failed direction" in _label(c)
                       or "unstable" in _label(c) or "edge" in _label(c)
                       or "protected" in _label(c))]
    risk_acc = _ratio(sum(1 for c in risk_items if _useful(c)), len(risk_items)) \
        if risk_items else 0.0
    return risk_acc, useful, len(evaluable)


def compute_accuracy(consequences: Sequence, checklist: Sequence) -> PredictionAccuracy:
    """Deterministic accuracy metrics over the reconciled consequences + validated
    checklist. Both may be dataclasses or dicts."""
    cons = list(consequences or [])
    checks = list(checklist or [])

    primary, p_n = _primary_accuracy(cons)
    side, s_n = _side_effect_accuracy(cons)
    hist, h_n = _historical_usefulness(cons)
    window, w_n = _window_accuracy(cons)
    risk_acc, checklist_useful, chk_n = _checklist_metrics(checks)
    # constraint accuracy = the working-window/constraint consequences that held
    constraint_acc = window

    evaluable = p_n + s_n + h_n + w_n + chk_n
    confirmed = sum(1 for c in cons if _status(c) == "confirmed")
    contradicted = sum(1 for c in cons if _status(c) == "contradicted")

    # overall = mean of the populated category scores (empty categories excluded)
    populated = [(primary, p_n), (side, s_n), (hist, h_n), (constraint_acc, w_n),
                 (checklist_useful, chk_n)]
    live = [v for v, n in populated if n]
    overall = round(sum(live) / len(live), 4) if live else 0.0

    payload = {"primary": primary, "side": side, "risk": risk_acc,
               "constraint": constraint_acc, "hist": hist,
               "checklist": checklist_useful, "overall": overall,
               "ev": evaluable, "conf": confirmed, "contra": contradicted}
    fp = (f"{PREDICTION_ACCURACY_VERSION}:"
          + hashlib.sha256(json.dumps(payload, sort_keys=True,
                                      separators=(",", ":")).encode()).hexdigest()[:20])
    return PredictionAccuracy(
        primary_consequence_accuracy=primary, side_effect_accuracy=side,
        risk_accuracy=risk_acc, constraint_accuracy=constraint_acc,
        historical_transfer_usefulness=hist, checklist_usefulness=checklist_useful,
        overall_accuracy=overall, evaluable_count=evaluable,
        confirmed_count=confirmed, contradicted_count=contradicted,
        content_fingerprint=fp)
