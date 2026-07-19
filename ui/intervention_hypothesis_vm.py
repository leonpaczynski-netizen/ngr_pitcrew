"""Pure view-model for the Intervention Hypothesis panel (Qt-free, Phase 14).

Turns the read-only ``SessionDB.build_intervention_hypotheses`` report into the structured
cards + sections the panel renders. Display strings only — it authors nothing, proposes no
value, and reads the deterministic hypothesis sets exactly as built. Never raises.
"""
from __future__ import annotations

from typing import List


def build(result=None) -> dict:
    return result if isinstance(result, dict) else {}


def is_empty(result) -> bool:
    r = build(result)
    return not r.get("ok") or not (r.get("hypothesis_sets") or [])


def header_text(result) -> str:
    r = build(result)
    n = int(r.get("count") or 0)
    tset = int(r.get("sets_with_testable") or 0)
    if not n:
        return ("No mechanism-constrained intervention hypotheses yet for this car / track / "
                "discipline. Hypotheses appear once a diagnosis has a supported mechanism.")
    return (f"{n} diagnosis(es) with mechanism-constrained intervention hypotheses - "
            f"{tset} with at least one testable controlled-test direction. Advisory only: "
            f"no setup value is authored and nothing is applied.")


def safety_text(result) -> str:
    r = build(result)
    return " ".join(r.get("safety_statements") or [])


def _status_label(v: str) -> str:
    return str(v or "").replace("_", " ").title()


def set_cards(result) -> List[dict]:
    """One card per hypothesis set, each with a status chip and ordered
    (section_title, lines) pairs from the deterministic renderer."""
    from strategy.intervention_hypothesis_render import render_set_sections
    r = build(result)
    cards: List[dict] = []
    for s in r.get("hypothesis_sets") or []:
        issue = s.get("canonical_issue") or {}
        itype = str(issue.get("issue_type") or "issue").replace("_", " ")
        corners = ", ".join(s.get("source_annotation", {}).get("corners") or []) or "-"
        cards.append({
            "title": f"{itype.capitalize()} @ {corners}",
            "status": _status_label(s.get("overall_status")),
            "status_key": str(s.get("overall_status") or ""),
            "sections": [(t, list(lines)) for t, lines in render_set_sections(s)],
            "fingerprint": str(s.get("content_fingerprint") or ""),
        })
    return cards


def banner_tone(result) -> str:
    r = build(result)
    if is_empty(r):
        return "info"
    statuses = {str(s.get("overall_status")) for s in r.get("hypothesis_sets") or []}
    if "testable" in statuses:
        return "success"
    if statuses & {"conditional", "competing_mechanisms", "insufficient_evidence"}:
        return "info"
    if statuses & {"contradicted_by_outcome", "blocked_by_working_window",
                   "blocked_by_safety_or_validity"}:
        return "warn"
    return "info"
