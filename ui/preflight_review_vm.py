"""Pure view-model for the Pre-Flight Engineering Review panel (Qt-free, Phase 10).

Turns ``SessionDB.build_experiment_preflight`` into the rows the panel renders: the
experiment, engineering rationale, expected consequences, historical outcomes, known
risks, protected behaviours, constraint summary, confidence, and the checklist.

READ-ONLY presentation: derives display strings only. No Apply buttons, no approval
controls. Deterministic; never raises.
"""
from __future__ import annotations

from typing import List, Tuple

CONSEQUENCE_COLUMNS: Tuple[str, ...] = ("Effect", "Detail", "Evidence", "Confidence")
CHECKLIST_COLUMNS: Tuple[str, ...] = ("", "Check", "Why", "Sessions", "Confidence")
SECTION_COLUMNS: Tuple[str, ...] = ("Detail", "Evidence", "Sessions", "Confidence")

_RISK_LABEL = {"low": "LOW", "moderate": "MODERATE", "high": "HIGH", "unknown": "UNKNOWN"}
_CONSEQUENCE_LABEL = {
    "primary_effect": "Primary", "side_effect": "Side effect", "historical": "History",
    "working_window": "Window", "interaction": "Interaction",
}


def _review(result) -> dict:
    if not isinstance(result, dict):
        return {}
    return result.get("review") or {}


def is_empty(result) -> bool:
    r = _review(result)
    return not r or not (r.get("sections") or r.get("checklist") or r.get("consequences"))


def risk_level(result) -> str:
    return _RISK_LABEL.get(str(_review(result).get("risk_level") or "unknown"), "UNKNOWN")


def summary_line(result) -> str:
    return str(_review(result).get("summary") or "No pre-flight review available.")


def experiment_rows(result) -> List[Tuple[str, str]]:
    e = _review(result).get("experiment") or {}
    out = [
        ("Field", str(e.get("field") or "—")),
        ("Direction", str(e.get("direction") or "—")),
        ("Change", f"{e.get('current_value')} → {e.get('proposed_value')}"),
        ("Target issue", str(e.get("target_issue") or "—")),
        ("Evidence grade", str(e.get("evidence_grade") or "—")),
        ("Window", str(e.get("window_relationship") or "—")),
    ]
    return out


def rationale_lines(result) -> List[str]:
    e = _review(result).get("experiment") or {}
    out = []
    for key in ("hypothesis", "expected_positive_effect", "selection_rationale"):
        v = str(e.get(key) or "").strip()
        if v:
            out.append(v)
    return out


def consequence_rows(result) -> List[Tuple[str, ...]]:
    out = []
    for c in _review(result).get("consequences") or []:
        out.append((
            _CONSEQUENCE_LABEL.get(str(c.get("kind")), str(c.get("kind") or "—")),
            str(c.get("text") or "—"), str(c.get("evidence_source") or "—"),
            str(c.get("confidence") or "—"),
        ))
    return out


def checklist_rows(result) -> List[Tuple[str, ...]]:
    out = []
    for c in _review(result).get("checklist") or []:
        out.append((
            str(c.get("glyph") or "•"), str(c.get("label") or "—"),
            str(c.get("why") or "—"),
            str(len(c.get("supporting_sessions") or [])),
            str(c.get("confidence") or "—"),
        ))
    return out


def _section(result, key) -> dict:
    for s in _review(result).get("sections") or []:
        if s.get("key") == key:
            return s
    return {}


def section_rows(result, key) -> List[Tuple[str, ...]]:
    out = []
    for l in _section(result, key).get("lines") or []:
        out.append((str(l.get("text") or "—"), str(l.get("evidence") or "—"),
                    str(len(l.get("supporting_sessions") or [])),
                    str(l.get("confidence") or "—")))
    return out


def section_titles(result) -> List[Tuple[str, str, str]]:
    """(key, title, severity) for each present section, in review order."""
    return [(str(s.get("key")), str(s.get("title")), str(s.get("severity")))
            for s in _review(result).get("sections") or []]


def compact_summary(result) -> List[str]:
    """A short text surfacing for embedding beside the proposed experiment."""
    if is_empty(result):
        return []
    r = _review(result)
    lines = [f"Pre-flight risk: {risk_level(result)}."]
    cautions = [c for c in (r.get("checklist") or []) if c.get("status") == "caution"]
    for c in cautions[:4]:
        lines.append(f"⚠ {c.get('label')}: {c.get('why')}")
    oks = [c for c in (r.get("checklist") or []) if c.get("status") == "ok"]
    if oks:
        lines.append("✓ " + "; ".join(str(c.get("label")) for c in oks[:3]))
    return lines
