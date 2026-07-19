"""Pure view-model for the Knowledge Assurance & Audit section (Qt-free, Phase 31).

Turns the read-only ``SessionDB.build_programme_assurance_report`` result into a structured card +
banner. Display strings only; never raises.
"""
from __future__ import annotations

from typing import List


def build(result=None) -> dict:
    return result if isinstance(result, dict) else {}


def _report(result) -> dict:
    r = build(result)
    v = r.get("assurance")
    return v if isinstance(v, dict) else {}


def is_empty(result) -> bool:
    rep = _report(result)
    return not build(result).get("ok") or not (rep.get("findings") or rep.get("grade_detail"))


def grade_label(result) -> str:
    rep = _report(result)
    return str(rep.get("assurance_grade") or "").replace("_", " ").upper() or "-"


def header_text(result) -> str:
    rep = _report(result)
    if not rep or not rep.get("grade_detail"):
        return ("No knowledge to assure yet. Read-only audit - a single blocking finding prevents "
                "ASSURED; the grade is rule-based over visible counts. Nothing is scheduled or "
                "applied; no setup values.")
    return str(rep.get("audit_summary") or "")


def banner_tone(result) -> str:
    rep = _report(result)
    grade = str(rep.get("assurance_grade") or "").lower()
    tot = rep.get("totals") or {}
    if grade == "not_assured" or int(tot.get("blocking", 0)) > 0:
        return "warn"
    if grade == "assured":
        return "success"
    return "info"


def assurance_cards(result) -> List[dict]:
    from strategy.programme_assurance_report_render import render_assurance_sections
    rep = _report(result)
    if not rep or not rep.get("grade_detail"):
        return []
    return [{
        "title": "Engineering Knowledge Assurance & Audit",
        "status": f"grade {grade_label(result)}",
        "sections": [(t, list(lines)) for t, lines in render_assurance_sections(rep)],
        "fingerprint": str(rep.get("content_fingerprint") or ""),
    }]
