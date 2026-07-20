"""Pure view-model for the Engineering Knowledge Quality section (Qt-free, Phase 20).

Turns the read-only ``SessionDB.build_engineering_knowledge_quality`` result into structured
cards + banner. Display strings only - it ranks/decides nothing itself, edits nothing, and
reads the deterministic advisory exactly as built. Never raises.
"""
from __future__ import annotations

from typing import List


def build(result=None) -> dict:
    return result if isinstance(result, dict) else {}


def _quality(result) -> dict:
    r = build(result)
    q = r.get("knowledge_quality")
    return q if isinstance(q, dict) else {}


def is_empty(result) -> bool:
    return not build(result).get("ok") or not (_quality(result).get("campaigns") or [])


def header_text(result) -> str:
    q = _quality(result)
    camps = q.get("campaigns") or []
    if not camps:
        return ("No campaigns to assess yet for this car / track / discipline. The knowledge-"
                "quality view appears once campaigns exist. Read-only - it measures confidence "
                "and remaining engineering return; it completes, ranks and applies nothing.")
    tot = q.get("totals") or {}
    lc = tot.get("confidence_level_counts") or {}
    conf = ", ".join(f"{str(k).replace('_', ' ')} {v}" for k, v in sorted(lc.items()))
    return (f"{len(camps)} campaign(s) - {tot.get('worthwhile_campaigns')} worth further work. "
            f"Confidence: {conf or '-'}. Advisory only - saturation/confidence never complete "
            "a campaign; the frozen Apply gate remains the only route to the car.")


def banner_tone(result) -> str:
    q = _quality(result)
    if not (q.get("campaigns") or []):
        return "info"
    lc = (q.get("totals") or {}).get("confidence_level_counts") or {}
    if int(lc.get("very_high", 0)) + int(lc.get("high", 0)) > 0:
        return "success"
    if int(lc.get("very_low", 0)) > 0:
        return "warn"
    return "info"


def quality_cards(result) -> List[dict]:
    from strategy.engineering_knowledge_quality_render import render_quality_sections
    q = _quality(result)
    if not (q.get("campaigns") or []):
        return []
    return [{
        "title": "Engineering Knowledge Quality",
        "status": f"{len(q.get('campaigns') or [])} campaign(s)",
        "sections": [(t, list(lines)) for t, lines in render_quality_sections(q)],
        "fingerprint": str(q.get("content_fingerprint") or ""),
    }]
