"""Pure view-model for the structured Setup Builder recommendation (Qt-free).

UAT Finding 3. The Setup Builder crammed diagnosis, changes, evidence,
telemetry, rejected candidates, test instructions and technical details into one
``QTextEdit.setHtml()`` blob. This module turns the recommendation payload into a
structured model the tabbed view renders:

  * Header — car / track / layout / setup name+revision / active setup / status /
    confidence / primary issue.
  * Recommendation — a field table (field, current, recommended, delta, status,
    confidence). Changed rows are ``highlighted`` immediately at generate time
    (NOT on "Applied in Game").
  * Why — per changed field: symptom, evidence, rationale, alternatives, risk,
    confidence, driver-style alignment, rule source.
  * Test Plan — an ordered validation sequence.
  * Advanced Evidence — raw/rejected/technical detail.

``mark_applied`` flips proposed rows to applied WITHOUT changing which rows are
shown — clicking "Applied in Game" changes status, it is not what first
highlights a field.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import List, Optional, Tuple


PROPOSED = "proposed"
APPLIED = "applied"
REJECTED = "rejected"


@dataclass(frozen=True)
class FieldRow:
    field: str            # canonical param key, or "" if unresolved
    setting: str          # display name
    current_value: str
    recommended_value: str
    delta: str
    status: str           # proposed | applied | rejected
    confidence: str
    changed: bool = True
    highlighted: bool = True   # changed rows highlight immediately

    def applied(self) -> "FieldRow":
        return replace(self, status=APPLIED)


@dataclass(frozen=True)
class WhyCard:
    setting: str
    symptom: str
    evidence: Tuple[str, ...]
    rationale: str
    alternatives: Tuple[str, ...]
    risk: str
    confidence: str
    driver_style_alignment: str
    rule_source: str


@dataclass(frozen=True)
class HeaderInfo:
    car: str = ""
    track: str = ""
    layout: str = ""
    setup_name: str = ""
    revision: str = ""
    active_setup: str = ""
    status: str = ""
    confidence: str = ""
    primary_issue: str = ""


@dataclass(frozen=True)
class SetupRecommendationVM:
    header: HeaderInfo
    field_rows: Tuple[FieldRow, ...]
    why_cards: Tuple[WhyCard, ...]
    test_plan: Tuple[str, ...]
    advanced_evidence: Tuple[str, ...]
    has_recommendation: bool

    def proposed_rows(self) -> Tuple[FieldRow, ...]:
        return tuple(r for r in self.field_rows if r.changed and r.status == PROPOSED)

    def highlighted_rows(self) -> Tuple[FieldRow, ...]:
        return tuple(r for r in self.field_rows if r.highlighted)

    def mark_applied(self) -> "SetupRecommendationVM":
        """Flip every proposed changed row to applied; rows stay visible +
        highlighted so applying only changes STATUS, not visibility."""
        new_rows = tuple(
            r.applied() if (r.changed and r.status == PROPOSED) else r
            for r in self.field_rows)
        new_header = replace(self.header, status="Applied in game")
        return replace(self, field_rows=new_rows, header=new_header)


def _to_str(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def _delta(frm, to) -> str:
    try:
        d = float(to) - float(frm)
        if abs(d) < 1e-9:
            return "0"
        return f"{d:+g}"
    except (TypeError, ValueError):
        return f"{_to_str(frm)} → {_to_str(to)}"


def _recommended_value(ch: dict) -> str:
    to_raw = ch.get("to", "")
    if ch.get("field") is not None and "to_clamped" in ch:
        return _to_str(ch.get("to_clamped", to_raw))
    return _to_str(to_raw)


def build_recommendation_vm(
    data: dict,
    *,
    header: Optional[HeaderInfo] = None,
    status_approved: bool = True,
) -> SetupRecommendationVM:
    """Build the structured VM from the parsed recommendation payload.

    ``data`` is the same dict the legacy renderer parses: ``changes`` (approved),
    ``rejected_changes``, ``diagnosis``, ``recommendation_status`` etc.
    """
    data = data or {}
    approved = list(data.get("changes", []) or [])
    rejected = list(data.get("rejected_changes", []) or [])
    diagnosis = data.get("diagnosis") or {}

    rows: List[FieldRow] = []
    cards: List[WhyCard] = []
    for ch in approved:
        frm = ch.get("from", "")
        rec = _recommended_value(ch)
        rows.append(FieldRow(
            field=str(ch.get("field") or ""),
            setting=str(ch.get("setting", "?")),
            current_value=_to_str(frm),
            recommended_value=rec,
            delta=_delta(frm, ch.get("to_clamped", ch.get("to"))),
            status=PROPOSED if status_approved else PROPOSED,
            confidence=str(ch.get("confidence_level", "") or ""),
            changed=True,
            highlighted=True,
        ))
        cards.append(WhyCard(
            setting=str(ch.get("setting", "?")),
            symptom=str(ch.get("symptom", "") or ""),
            evidence=tuple(str(e) for e in (ch.get("evidence") or [])),
            rationale=str(ch.get("rationale", ch.get("why", "")) or ""),
            alternatives=tuple(str(a) for a in (ch.get("rejected_alternatives") or [])),
            risk=str(ch.get("risk_level", "") or ""),
            confidence=str(ch.get("confidence_level", "") or ""),
            driver_style_alignment=str(ch.get("driver_style_alignment", "") or ""),
            rule_source=str(ch.get("rule_id", "") or ""),
        ))

    # Rejected candidates as non-highlighted, rejected-status rows (Advanced).
    for ch in rejected:
        rows.append(FieldRow(
            field=str(ch.get("field") or ""),
            setting=str(ch.get("setting", "?")),
            current_value=_to_str(ch.get("from", "")),
            recommended_value=_recommended_value(ch),
            delta=_delta(ch.get("from"), ch.get("to")),
            status=REJECTED,
            confidence=str(ch.get("confidence_level", "") or ""),
            changed=False,
            highlighted=False,
        ))

    # Test plan: prefer the deterministic module, else derive from the changes.
    test_plan = _build_test_plan(data, approved)

    advanced: List[str] = []
    if data.get("validation_errors"):
        advanced.append("Validation errors: " + "; ".join(map(str, data["validation_errors"])))
    if data.get("engineering_validation_errors"):
        advanced.append("Engineering blocks: " + "; ".join(map(str, data["engineering_validation_errors"])))
    if rejected:
        advanced.append(f"{len(rejected)} rejected candidate(s) — see table rows marked rejected.")
    if data.get("ai_audit"):
        advanced.append("AI audit present (advisory only).")

    hdr = header or HeaderInfo()
    primary = str(diagnosis.get("primary_issue", "") or hdr.primary_issue or "")
    hdr = replace(hdr,
                  status=hdr.status or str(data.get("recommendation_status", "") or ""),
                  primary_issue=primary)

    return SetupRecommendationVM(
        header=hdr,
        field_rows=tuple(rows),
        why_cards=tuple(cards),
        test_plan=tuple(test_plan),
        advanced_evidence=tuple(advanced),
        has_recommendation=bool(approved),
    )


def _build_test_plan(data: dict, approved: list) -> List[str]:
    try:
        from strategy.setup_test_plan import build_test_plan  # type: ignore
        plan = build_test_plan(data)
        if plan:
            return [str(s) for s in plan]
    except Exception:
        pass
    # Deterministic fallback: one validation step per changed field, in order.
    steps = []
    for i, ch in enumerate(approved, 1):
        steps.append(
            f"{i}. Apply {ch.get('setting', 'the change')} and run 3 clean laps; "
            "confirm the target symptom improves without a new one appearing.")
    if not steps:
        steps.append("No changes to validate.")
    return steps
