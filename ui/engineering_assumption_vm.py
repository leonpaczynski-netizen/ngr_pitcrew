"""Pure view-model for the Assumption Register section (Qt-free, Phase 30).

Turns the read-only ``SessionDB.build_programme_assumption_register`` result into structured cards +
banner. Display strings only; never raises.
"""
from __future__ import annotations

from typing import List


def build(result=None) -> dict:
    return result if isinstance(result, dict) else {}


def _report(result) -> dict:
    r = build(result)
    v = r.get("assumptions")
    return v if isinstance(v, dict) else {}


def is_empty(result) -> bool:
    return not build(result).get("ok") or not (_report(result).get("assumptions") or [])


def header_text(result) -> str:
    rep = _report(result)
    items = rep.get("assumptions") or []
    if not items:
        return ("No engineering assumptions to register - the established knowledge is directly "
                "evidenced. Read-only - an assumption can only cap readiness, never create it; "
                "nothing is scheduled or applied; no setup values.")
    tot = rep.get("totals") or {}
    return (f"{len(items)} assumption(s) across {tot.get('domains_with_assumptions')} domain(s): "
            f"{tot.get('blocking')} blocking, {tot.get('capping')} capping, "
            f"{tot.get('narrowing_or_weakening')} narrowing/weakening; "
            f"{tot.get('at_risk_or_contradicted')} at-risk/contradicted; "
            f"{tot.get('conservative_bounds')} conservative bound(s). Advisory only - assumptions "
            "cap readiness, never create it.")


def banner_tone(result) -> str:
    rep = _report(result)
    if not (rep.get("assumptions") or []):
        return "info"
    tot = rep.get("totals") or {}
    if int(tot.get("blocking", 0)) + int(tot.get("at_risk_or_contradicted", 0)) > 0:
        return "warn"
    return "info"


def assumption_cards(result) -> List[dict]:
    from strategy.programme_assumption_register_render import render_assumption_sections
    rep = _report(result)
    if not (rep.get("assumptions") or []):
        return []
    return [{
        "title": "Engineering Assumption Register",
        "status": f"{len(rep.get('assumptions') or [])} assumption(s)",
        "sections": [(t, list(lines)) for t, lines in render_assumption_sections(rep)],
        "fingerprint": str(rep.get("content_fingerprint") or ""),
    }]
