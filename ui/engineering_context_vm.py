"""Pure view-model for the Engineering Context panel (Qt-free, Phase 9).

Turns ``SessionDB.build_engineering_context`` (matched contexts + transfers +
constraints + regression risks) into the rows the panel renders: relevant past
sessions, known successful fixes, known failures, stable working windows, protected
behaviours, engineering constraints and regression risks.

READ-ONLY presentation: derives display strings only. No Apply controls, no decision
controls. Deterministic; never raises.
"""
from __future__ import annotations

from typing import List, Tuple

MATCH_COLUMNS: Tuple[str, ...] = ("Context", "Match", "Why", "Reviews")
FIX_COLUMNS: Tuple[str, ...] = ("Match", "Field", "Direction", "Result", "Sessions", "Confirmed")
WINDOW_COLUMNS: Tuple[str, ...] = ("Match", "Field", "Stable range", "Confidence", "Confirmed")
PROTECTED_COLUMNS: Tuple[str, ...] = ("Match", "Behaviour / field", "Sessions", "Confirmed")
CONSTRAINT_COLUMNS: Tuple[str, ...] = (
    "Constraint", "Field", "Detail", "Source", "Sessions", "Confidence", "Confirmed")
RISK_COLUMNS: Tuple[str, ...] = ("Severity", "Risk", "Field", "Why", "Confirmed")

_STRENGTH_LABEL = {
    "direct_match": "Direct", "strong_match": "Strong", "related_match": "Related",
    "weak_match": "Weak", "unknown": "General",
}
_RISK_LABEL = {
    "known_failed_direction": "Known failed direction",
    "previously_unstable_range": "Previously unstable",
    "protected_field_conflict": "Protected-field conflict",
    "working_window_edge": "Working-window edge",
    "repeated_regression": "Repeated regression",
    "confidence_weakness": "Weak confidence",
}
_CONSTRAINT_LABEL = {
    "never_move_direction": "Avoid direction", "never_below": "Never below",
    "never_above": "Never above", "preferred_range": "Preferred range",
    "known_unstable": "Known unstable", "protected_behaviour": "Protected behaviour",
}
_SEVERITY_LABEL = {"high": "HIGH", "medium": "MED", "low": "LOW", "info": "INFO"}


def _label(mapping, key) -> str:
    return mapping.get(str(key or ""), str(key or "").replace("_", " ").title())


def _yn(v) -> str:
    return "confirmed" if v else "provisional"


def is_empty(result) -> bool:
    if not isinstance(result, dict) or not result.get("ok"):
        return True
    return not (result.get("matched_contexts") or result.get("transfers")
                or result.get("constraints") or result.get("regression_risks"))


def summary_line(result) -> str:
    if is_empty(result):
        return "No comparable engineering history yet for this context."
    r = result or {}
    return (f"{len(r.get('matched_contexts') or [])} matching context(s) · "
            f"{len(r.get('transfers') or [])} lesson(s) · "
            f"{len(r.get('constraints') or [])} constraint(s) · "
            f"{len(r.get('regression_risks') or [])} risk(s)")


def matched_context_rows(result) -> List[Tuple[str, ...]]:
    out = []
    for m in (result or {}).get("matched_contexts") or []:
        ctx = m.get("context") or {}
        out.append((str(ctx.get("label") or "—"),
                    _label(_STRENGTH_LABEL, m.get("strength")),
                    str(m.get("reason") or "—"), str(m.get("record_count") or 0)))
    return out


def _transfers(result, kind):
    return [t for t in (result or {}).get("transfers") or [] if t.get("kind") == kind]


def _fix_row(t) -> Tuple[str, ...]:
    return (_label(_STRENGTH_LABEL, t.get("strength")), str(t.get("field") or "—"),
            str(t.get("direction") or "—"), str(t.get("detail") or "—"),
            str(len(t.get("supporting_sessions") or [])), _yn(t.get("confirmed")))


def successful_fix_rows(result) -> List[Tuple[str, ...]]:
    return [_fix_row(t) for t in _transfers(result, "successful_experiment")]


def failed_fix_rows(result) -> List[Tuple[str, ...]]:
    return [_fix_row(t) for t in _transfers(result, "failed_experiment")]


def stable_window_rows(result) -> List[Tuple[str, ...]]:
    out = []
    for t in _transfers(result, "stable_window"):
        out.append((_label(_STRENGTH_LABEL, t.get("strength")), str(t.get("field") or "—"),
                    str(t.get("value") or "—"), str(t.get("confidence") or "—"),
                    _yn(t.get("confirmed"))))
    return out


def protected_behaviour_rows(result) -> List[Tuple[str, ...]]:
    out = []
    for t in _transfers(result, "protected_behaviour"):
        out.append((_label(_STRENGTH_LABEL, t.get("strength")),
                    str(t.get("detail") or t.get("field") or "—"),
                    str(len(t.get("supporting_sessions") or [])), _yn(t.get("confirmed"))))
    return out


def constraint_rows(result) -> List[Tuple[str, ...]]:
    out = []
    for c in (result or {}).get("constraints") or []:
        out.append((_label(_CONSTRAINT_LABEL, c.get("kind")), str(c.get("field") or "—"),
                    str(c.get("detail") or "—"), str(c.get("evidence_source") or "—"),
                    str(len(c.get("supporting_sessions") or [])),
                    str(c.get("confidence") or "—"), _yn(c.get("confirmed"))))
    return out


def regression_risk_rows(result) -> List[Tuple[str, ...]]:
    out = []
    for r in (result or {}).get("regression_risks") or []:
        out.append((_label(_SEVERITY_LABEL, r.get("severity")),
                    _label(_RISK_LABEL, r.get("kind")), str(r.get("field") or "—"),
                    str(r.get("reason") or "—"), _yn(r.get("confirmed"))))
    return out
