"""Pure view-model for the Post-Flight Review panel (Qt-free, Phase 11).

Turns a reconciliation record dict (from ``SessionDB.record_experiment_reconciliation``)
or the calibration summary (from ``SessionDB.build_prediction_calibration``) into the
rows the panel renders: prediction vs observed outcome, confirmed expectations,
unexpected behaviour, engineering accuracy, lessons observed.

READ-ONLY presentation: derives display strings only. No Apply controls. Deterministic;
never raises.
"""
from __future__ import annotations

from typing import List, Tuple

CONSEQUENCE_COLUMNS: Tuple[str, ...] = ("Predicted", "Status", "Observed", "Why")
CHECKLIST_COLUMNS: Tuple[str, ...] = ("Check", "Expected", "Outcome", "Useful", "Why")
ACCURACY_COLUMNS: Tuple[str, ...] = ("Metric", "Accuracy")
CALIBRATION_COLUMNS: Tuple[str, ...] = ("Metric", "Value")

_STATUS_LABEL = {
    "confirmed": "Confirmed ✓", "partially_confirmed": "Partial ~",
    "not_observed": "Not observed", "contradicted": "Contradicted ✗",
    "insufficient_evidence": "Insufficient", "unknown": "Unknown",
}
_OUTCOME_LABEL = {
    "materialised": "Happened", "did_not_materialise": "Did not happen",
    "insufficient_evidence": "Insufficient", "not_applicable": "N/A",
}


def _label(m, k) -> str:
    return m.get(str(k or ""), str(k or "").replace("_", " ").title())


def _record(result) -> dict:
    if not isinstance(result, dict):
        return {}
    return result.get("record") or result


def is_empty(result) -> bool:
    r = _record(result)
    return not r or not (r.get("consequence_reconciliations")
                         or r.get("checklist_validations"))


def _pct(v) -> str:
    try:
        return f"{float(v) * 100:.0f}%"
    except (TypeError, ValueError):
        return "—"


def summary_line(result) -> str:
    r = _record(result)
    if is_empty(result):
        return "No post-flight reconciliation available."
    acc = r.get("accuracy") or {}
    return (f"Predicted risk {r.get('predicted_risk', '—')} · outcome "
            f"{r.get('outcome_status', '—')} · overall accuracy "
            f"{_pct(acc.get('overall_accuracy'))}")


def prediction_vs_outcome_rows(result) -> List[Tuple[str, str]]:
    r = _record(result)
    acc = r.get("accuracy") or {}
    return [
        ("Predicted risk", str(r.get("predicted_risk") or "—")),
        ("Actual outcome", str(r.get("outcome_status") or "—")),
        ("Overall accuracy", _pct(acc.get("overall_accuracy"))),
        ("Confirmed", str(acc.get("confirmed_count") or 0)),
        ("Contradicted", str(acc.get("contradicted_count") or 0)),
    ]


def consequence_rows(result) -> List[Tuple[str, ...]]:
    out = []
    for c in _record(result).get("consequence_reconciliations") or []:
        out.append((str(c.get("predicted") or "—"),
                    _label(_STATUS_LABEL, c.get("status")),
                    str(c.get("observed") or "—"), str(c.get("reason") or "—")))
    return out


def confirmed_rows(result) -> List[Tuple[str, ...]]:
    return [r for r in consequence_rows(result) if "Confirmed" in r[1] or "Partial" in r[1]]


def unexpected_rows(result) -> List[Tuple[str, ...]]:
    return [r for r in consequence_rows(result) if "Contradicted" in r[1]]


def checklist_rows(result) -> List[Tuple[str, ...]]:
    out = []
    for c in _record(result).get("checklist_validations") or []:
        out.append((str(c.get("label") or "—"), str(c.get("expectation") or "—"),
                    _label(_OUTCOME_LABEL, c.get("outcome")),
                    ("yes" if c.get("useful") else "no"), str(c.get("reason") or "—")))
    return out


def accuracy_rows(result) -> List[Tuple[str, str]]:
    acc = _record(result).get("accuracy") or {}
    return [
        ("Primary consequence", _pct(acc.get("primary_consequence_accuracy"))),
        ("Side effects", _pct(acc.get("side_effect_accuracy"))),
        ("Risk", _pct(acc.get("risk_accuracy"))),
        ("Constraint", _pct(acc.get("constraint_accuracy"))),
        ("Historical transfer", _pct(acc.get("historical_transfer_usefulness"))),
        ("Checklist", _pct(acc.get("checklist_usefulness"))),
        ("Overall", _pct(acc.get("overall_accuracy"))),
    ]


def lessons_rows(result) -> List[str]:
    """Short lessons observed: contradicted predictions + materialised cautions."""
    out = []
    for c in _record(result).get("consequence_reconciliations") or []:
        if c.get("status") == "contradicted":
            out.append(f"Prediction did not hold: {c.get('predicted')} — {c.get('observed')}")
    for c in _record(result).get("checklist_validations") or []:
        if c.get("outcome") == "materialised" and c.get("status") == "caution":
            out.append(f"Warned risk materialised: {c.get('label')}")
    return out


# --- calibration summary (aggregate across reconciliations) -----------------
def calibration_is_empty(result) -> bool:
    if not isinstance(result, dict) or not result.get("ok"):
        return True
    return int((result.get("calibration") or {}).get("reconciliations") or 0) <= 0


def calibration_rows(result) -> List[Tuple[str, str]]:
    c = (result or {}).get("calibration") or {}
    if not c.get("reconciliations"):
        return []
    return [
        ("Reconciliations", str(c.get("reconciliations"))),
        ("Overall accuracy", _pct(c.get("overall_accuracy"))),
        ("Primary consequence", _pct(c.get("primary_consequence_accuracy"))),
        ("Side effects", _pct(c.get("side_effect_accuracy"))),
        ("Risk", _pct(c.get("risk_accuracy"))),
        ("Constraint", _pct(c.get("constraint_accuracy"))),
        ("Historical transfer", _pct(c.get("historical_transfer_usefulness"))),
        ("Checklist", _pct(c.get("checklist_usefulness"))),
        ("Confirmed total", str(c.get("confirmed_total") or 0)),
        ("Contradicted total", str(c.get("contradicted_total") or 0)),
        ("Elevated-risk regressions", str(c.get("elevated_risk_regressions") or 0)),
    ]
