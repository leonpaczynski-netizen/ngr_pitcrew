"""Pure view-model for the Engineering Playbook section (Qt-free, Phase 24).

Turns the read-only ``SessionDB.build_programme_engineering_playbook`` result into structured
cards + banner. Display strings only - it assembles/decides nothing itself, edits nothing, and
reads the deterministic playbook exactly as built. Never raises.
"""
from __future__ import annotations

from typing import List


def build(result=None) -> dict:
    return result if isinstance(result, dict) else {}


def _playbook(result) -> dict:
    r = build(result)
    p = r.get("playbook")
    return p if isinstance(p, dict) else {}


def is_empty(result) -> bool:
    return not build(result).get("ok") or not (_playbook(result).get("stable_themes") or [])


def header_text(result) -> str:
    pb = _playbook(result)
    themes = pb.get("stable_themes") or []
    if not themes:
        return ("No cross-programme engineering playbook yet - it appears once this programme has "
                "established knowledge. Read-only - it assembles and explains existing knowledge "
                "as an investigation playbook; it generates, copies and applies NO setup values.")
    summ = pb.get("global_stable_summary") or {}
    return (f"{len(themes)} stable theme(s) - {summ.get('confirmed_good_themes')} confirmed-good, "
            f"{summ.get('themes_reusable_across_programmes')} reusable across programmes, "
            f"{summ.get('themes_with_negative_history')} with negative history; "
            f"{summ.get('target_programmes')} target programme(s). Advisory only - no setup "
            "values are copied, generated or applied; all knowledge requires validation.")


def banner_tone(result) -> str:
    pb = _playbook(result)
    if not (pb.get("stable_themes") or []):
        return "info"
    summ = pb.get("global_stable_summary") or {}
    if int(summ.get("confirmed_good_themes", 0)) > 0:
        return "success"
    if int(summ.get("themes_with_negative_history", 0)) > 0:
        return "warn"
    return "info"


def playbook_cards(result) -> List[dict]:
    from strategy.engineering_playbook_render import render_playbook_sections
    pb = _playbook(result)
    if not (pb.get("stable_themes") or []):
        return []
    return [{
        "title": "Cross-Programme Engineering Playbook",
        "status": f"{len(pb.get('stable_themes') or [])} theme(s)",
        "sections": [(t, list(lines)) for t, lines in render_playbook_sections(pb)],
        "fingerprint": str(pb.get("content_fingerprint") or ""),
    }]
