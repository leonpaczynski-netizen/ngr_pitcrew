"""Pure view-model for the Engineering Knowledge Timeline section (Qt-free, Phase 25).

Turns the read-only ``SessionDB.build_programme_knowledge_timeline`` result into structured cards +
banner. Display strings only - it assembles/decides nothing itself, edits nothing, and reads the
deterministic timeline exactly as built. Never raises.
"""
from __future__ import annotations

from typing import List


def build(result=None) -> dict:
    return result if isinstance(result, dict) else {}


def _timeline(result) -> dict:
    r = build(result)
    t = r.get("timeline")
    return t if isinstance(t, dict) else {}


def is_empty(result) -> bool:
    return not build(result).get("ok") or not (_timeline(result).get("timeline_points") or [])


def header_text(result) -> str:
    tl = _timeline(result)
    pts = tl.get("timeline_points") or []
    if not pts:
        return ("No engineering knowledge timeline yet - it appears once this programme has "
                "recorded evidence across events. Read-only - dates are evidence data, not "
                "authority; convergence requires independent evidence; no setup values are shown.")
    ind = tl.get("evidence_independence_summary") or {}
    conv = tl.get("convergence_summaries") or []
    strong = sum(1 for c in conv if c.get("convergence_status") == "strongly_converged")
    cg = len(tl.get("stable_confirmed_good") or [])
    conflicts = len(tl.get("unresolved_conflicts") or [])
    return (f"{len(pts)} timeline point(s), {ind.get('independent_groups')} independent evidence "
            f"line(s). {strong} strongly-converged, {cg} confirmed-good, {conflicts} unresolved "
            "conflict(s). Advisory only - a newer observation never automatically overrides an "
            "older stronger finding; no setup values.")


def banner_tone(result) -> str:
    tl = _timeline(result)
    if not (tl.get("timeline_points") or []):
        return "info"
    if int(len(tl.get("unresolved_conflicts") or [])) > 0 \
            or int(len(tl.get("regressions_and_retired") or [])) > 0:
        return "warn"
    if int(len(tl.get("stable_confirmed_good") or [])) > 0:
        return "success"
    return "info"


def timeline_cards(result) -> List[dict]:
    from strategy.programme_timeline_report_render import render_timeline_sections
    tl = _timeline(result)
    if not (tl.get("timeline_points") or []):
        return []
    return [{
        "title": "Engineering Knowledge Timeline",
        "status": f"{len(tl.get('timeline_points') or [])} point(s)",
        "sections": [(t, list(lines)) for t, lines in render_timeline_sections(tl)],
        "fingerprint": str(tl.get("content_fingerprint") or ""),
    }]
