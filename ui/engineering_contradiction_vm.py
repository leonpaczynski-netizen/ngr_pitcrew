"""Pure view-model for the Contradiction Resolution section (Qt-free, Phase 29).

Turns the read-only ``SessionDB.build_programme_contradiction_report`` result into structured cards +
banner. Display strings only; never raises.
"""
from __future__ import annotations

from typing import List


def build(result=None) -> dict:
    return result if isinstance(result, dict) else {}


def _report(result) -> dict:
    r = build(result)
    v = r.get("contradiction")
    return v if isinstance(v, dict) else {}


def is_empty(result) -> bool:
    return not build(result).get("ok") or not (_report(result).get("contradictions") or [])


def header_text(result) -> str:
    rep = _report(result)
    cs = rep.get("contradictions") or []
    if not cs:
        return ("No evidence contradictions found. Read-only - a contradiction is never resolved by "
                "majority or recency; a version/context mismatch is surfaced; a contradiction may "
                "stay open. Nothing is scheduled or applied; no setup values.")
    tot = rep.get("totals") or {}
    return (f"{len(cs)} contradiction(s): {tot.get('open')} open (evidence does not tell us which "
            f"is right), {tot.get('resolved')} resolved/explained "
            f"({tot.get('resolved_by_context')} by context). Advisory only - never resolved by "
            "majority or recency.")


def banner_tone(result) -> str:
    rep = _report(result)
    if not (rep.get("contradictions") or []):
        return "info"
    tot = rep.get("totals") or {}
    if int(tot.get("open", 0)) > 0:
        return "warn"
    return "success"


def contradiction_cards(result) -> List[dict]:
    from strategy.programme_contradiction_report_render import render_contradiction_sections
    rep = _report(result)
    if not (rep.get("contradictions") or []):
        return []
    return [{
        "title": "Knowledge Contradiction Resolution",
        "status": f"{len(rep.get('contradictions') or [])} contradiction(s)",
        "sections": [(t, list(lines)) for t, lines in render_contradiction_sections(rep)],
        "fingerprint": str(rep.get("content_fingerprint") or ""),
    }]
