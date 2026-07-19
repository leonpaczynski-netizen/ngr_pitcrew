"""Pure view-model for the Engineering Efficiency section (Qt-free, Phase 19).

Turns the read-only ``SessionDB.build_engineering_efficiency`` result into structured cards +
banner. Display strings only - it ranks/decides nothing itself, edits nothing, and reads the
deterministic advisory exactly as built. Never raises.
"""
from __future__ import annotations

from typing import List


def build(result=None) -> dict:
    return result if isinstance(result, dict) else {}


def _efficiency(result) -> dict:
    r = build(result)
    e = r.get("efficiency")
    return e if isinstance(e, dict) else {}


def is_empty(result) -> bool:
    return not build(result).get("ok") or not (_efficiency(result).get("campaigns") or [])


def header_text(result) -> str:
    e = _efficiency(result)
    camps = e.get("campaigns") or []
    if not camps:
        return ("No engineering campaigns to measure yet for this car / track / discipline. "
                "The efficiency view appears once campaigns exist. Read-only - nothing is "
                "applied, completed or frozen here.")
    tot = e.get("totals") or {}
    return (f"{len(camps)} campaign(s) - {tot.get('saturated_campaigns')} saturated / "
            f"over-tested, {tot.get('archived_campaigns')} archived. Estimated remaining "
            f"testing: {tot.get('estimated_remaining_laps')} laps, "
            f"{tot.get('estimated_remaining_tyre_sets')} tyre set(s). "
            "Advisory only - saturation never completes a campaign; the frozen Apply gate "
            "remains the only route to the car.")


def banner_tone(result) -> str:
    e = _efficiency(result)
    if not (e.get("campaigns") or []):
        return "info"
    tot = e.get("totals") or {}
    if int(tot.get("saturated_campaigns") or 0) > 0:
        return "success"
    return "info"


def efficiency_cards(result) -> List[dict]:
    from strategy.engineering_efficiency_render import render_efficiency_sections
    e = _efficiency(result)
    if not (e.get("campaigns") or []):
        return []
    return [{
        "title": "Engineering Efficiency",
        "status": f"{len(e.get('campaigns') or [])} campaign(s)",
        "sections": [(t, list(lines)) for t, lines in render_efficiency_sections(e)],
        "fingerprint": str(e.get("content_fingerprint") or ""),
    }]
