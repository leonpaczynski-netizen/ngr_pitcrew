"""Pure view-model for the Engineering Campaigns panel (Qt-free, Phase 18).

Turns the read-only ``SessionDB.build_engineering_campaign_programme`` result into structured
cards + sections. Display strings only - it groups/ranks nothing itself, edits nothing, and
reads the deterministic programme exactly as built. Never raises.
"""
from __future__ import annotations

from typing import List


def build(result=None) -> dict:
    return result if isinstance(result, dict) else {}


def _programme(result) -> dict:
    r = build(result)
    p = r.get("programme")
    return p if isinstance(p, dict) else {}


def is_empty(result) -> bool:
    return not build(result).get("ok") or not (_programme(result).get("campaigns") or [])


def header_text(result) -> str:
    p = _programme(result)
    camps = p.get("campaigns") or []
    if not camps:
        return ("No engineering campaigns yet for this car / track / discipline. Campaigns "
                "appear once the portfolio yields experiments toward a bounded objective.")
    focus = p.get("recommended_focus") or {}
    return (f"{len(camps)} campaign(s) - active {p.get('active_count')}, blocked "
            f"{p.get('blocked_count')}, ready-to-freeze {p.get('ready_to_freeze_count')}, "
            f"completed {p.get('completed_count')}, stale {p.get('stale_count')}. "
            + (f"Focus: {focus.get('title')}. " if focus else "")
            + "Read-only - nothing is applied here.")


def banner_tone(result) -> str:
    p = _programme(result)
    if not (p.get("campaigns") or []):
        return "info"
    if int(p.get("stale_count") or 0) > 0 or int(p.get("blocked_count") or 0) > 0:
        return "warn"
    if int(p.get("ready_to_freeze_count") or 0) > 0 or int(p.get("completed_count") or 0) > 0:
        return "success"
    return "info"


def programme_cards(result) -> List[dict]:
    from strategy.engineering_campaign_render import render_programme_sections
    p = _programme(result)
    if not (p.get("campaigns") or []):
        return []
    return [{
        "title": "Engineering Campaigns",
        "status": (p.get("recommended_focus") or {}).get("title") or "no focus",
        "sections": [(t, list(lines)) for t, lines in render_programme_sections(p)],
        "fingerprint": str(p.get("content_fingerprint") or ""),
    }]
