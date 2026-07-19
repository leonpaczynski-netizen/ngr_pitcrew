"""Pure view-model for the Knowledge Readiness executive-summary section (Qt-free, Phase 28).

Turns the read-only ``SessionDB.build_programme_knowledge_readiness_report`` result into a structured
card + banner. Display strings only; never raises.
"""
from __future__ import annotations

from typing import List


def build(result=None) -> dict:
    return result if isinstance(result, dict) else {}


def _report(result) -> dict:
    r = build(result)
    v = r.get("readiness")
    return v if isinstance(v, dict) else {}


def is_empty(result) -> bool:
    return not build(result).get("ok") or not (_report(result).get("items") or [])


def header_text(result) -> str:
    rep = _report(result)
    items = rep.get("items") or []
    if not items:
        return ("No engineering knowledge readiness to report yet. Read-only - 'ready' means the "
                "evidence supports relying on the knowledge, never 'apply this setup'. Nothing is "
                "scheduled or applied; no setup values.")
    return str(rep.get("executive_summary") or "")


def banner_tone(result) -> str:
    rep = _report(result)
    if not (rep.get("items") or []):
        return "info"
    grade = str(rep.get("programme_grade") or "").lower()
    tot = rep.get("totals") or {}
    if int(tot.get("blocked", 0)) > 0 or grade == "low":
        return "warn"
    if grade == "high":
        return "success"
    return "info"


def grade_label(result) -> str:
    rep = _report(result)
    return str(rep.get("programme_grade") or "").replace("_", " ").upper() or "-"


def readiness_cards(result) -> List[dict]:
    from strategy.programme_readiness_report_render import render_readiness_sections
    rep = _report(result)
    if not (rep.get("items") or []):
        return []
    return [{
        "title": "Engineering Knowledge Readiness",
        "status": f"grade {grade_label(result)}",
        "sections": [(t, list(lines)) for t, lines in render_readiness_sections(rep)],
        "fingerprint": str(rep.get("content_fingerprint") or ""),
    }]
