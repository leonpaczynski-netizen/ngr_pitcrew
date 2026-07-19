"""Pure view-model for the Engineering Season section (Qt-free, Phase 21).

Turns the read-only ``SessionDB.build_season_engineering_report`` result into structured cards +
banner. Display strings only - it aggregates/decides nothing itself, edits nothing, and reads
the deterministic report exactly as built. Never raises.
"""
from __future__ import annotations

from typing import List


def build(result=None) -> dict:
    return result if isinstance(result, dict) else {}


def _report(result) -> dict:
    r = build(result)
    s = r.get("season_report")
    return s if isinstance(s, dict) else {}


def is_empty(result) -> bool:
    return not build(result).get("ok") or not (_report(result).get("campaigns") or [])


def header_text(result) -> str:
    rep = _report(result)
    camps = rep.get("campaigns") or []
    if not camps:
        return ("No engineering campaigns this season yet for this car / track / discipline. "
                "The season view appears once campaigns exist. Read-only - it explains the "
                "current state of engineering; it schedules, completes and applies nothing.")
    dev = (rep.get("development") or {}).get("metrics") or {}

    def _v(name):
        m = dev.get(name)
        return m.get("value") if isinstance(m, dict) else None
    rel = rep.get("relationships") or {}
    return (f"{len(camps)} campaign(s) - {_v('completed_campaigns')} completed, "
            f"{_v('high_confidence_campaigns')} high-confidence, "
            f"{_v('low_confidence_campaigns')} low-confidence; knowledge completion "
            f"{_v('knowledge_completion')}. Relationships: {len(rel.get('edges') or [])}, "
            f"isolated {len(rel.get('isolated_campaign_ids') or [])}. Advisory only - it "
            "explains engineering; it schedules and completes nothing.")


def banner_tone(result) -> str:
    rep = _report(result)
    if not (rep.get("campaigns") or []):
        return "info"
    counts = (rep.get("relationships") or {}).get("relationship_counts") or {}
    if int(counts.get("contradicts", 0)) > 0 or int(counts.get("blocked_by", 0)) > 0:
        return "warn"
    dev = (rep.get("development") or {}).get("metrics") or {}
    kc = dev.get("knowledge_completion") or {}
    if isinstance(kc, dict) and isinstance(kc.get("value"), (int, float)) and kc["value"] >= 0.5:
        return "success"
    return "info"


def report_cards(result) -> List[dict]:
    from strategy.season_engineering_report_render import render_report_sections
    rep = _report(result)
    if not (rep.get("campaigns") or []):
        return []
    return [{
        "title": "Season Development Plan",
        "status": f"{len(rep.get('campaigns') or [])} campaign(s)",
        "sections": [(t, list(lines)) for t, lines in render_report_sections(rep)],
        "fingerprint": str(rep.get("content_fingerprint") or ""),
    }]
