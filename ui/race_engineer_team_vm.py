"""Pure view-model for the Race-Engineer Team Brief section (Qt-free, Program 2, Phase 38).

Turns the read-only ``SessionDB.build_race_engineer_team_brief`` result into a structured card +
banner. Display strings only; never raises; no setup values.
"""
from __future__ import annotations

from typing import List


def build(result=None) -> dict:
    return result if isinstance(result, dict) else {}


def _brief(result) -> dict:
    r = build(result)
    v = r.get("brief")
    return v if isinstance(v, dict) else {}


def is_empty(result) -> bool:
    r = build(result)
    b = _brief(result)
    if not r.get("ok") or not b:
        return True
    # a brief with no plan and an empty-state message is an honest "nothing yet".
    return not (b.get("ordered_development_plan") or b.get("chief_engineer"))


def completeness_label(result) -> str:
    return str(_brief(result).get("completeness") or "").replace("_", " ").upper() or "-"


def header_text(result) -> str:
    b = _brief(result)
    if not b:
        return ("No race-engineer brief yet. Read-only, advisory-only - the Engineering Brain "
                "coordinates the current best-PROVEN setup, working windows, driver progression and "
                "the next controlled step. It is not a certification, not an experiment, not a setup "
                "and not permission to Apply. No setup values.")
    ce = b.get("chief_engineer") or {}
    parts = [f"Context readiness {completeness_label(result)}.",
             f"{len(b.get('ordered_development_plan') or [])} planned step(s).",
             f"Brief fingerprint {b.get('content_fingerprint')}."]
    if b.get("empty_state"):
        parts.append(b.get("empty_state"))
    else:
        parts.append("Highest priority: " + str(ce.get("highest_priority_problem") or "-"))
    return " ".join(parts)


def banner_tone(result) -> str:
    b = _brief(result)
    if is_empty(result):
        return "info"
    comp = str(b.get("completeness") or "")
    if comp in ("insufficient", "partial"):
        return "warn"
    if (b.get("setup_engineer") or {}).get("rollback_plan", {}).get("needed"):
        return "warn"
    return "info"


def brief_cards(result) -> List[dict]:
    from strategy.race_engineer_team_brief_render import render_brief_sections
    b = _brief(result)
    if not b:
        return []
    sections = [(t, list(lines)) for t, lines in render_brief_sections(b)]
    status = completeness_label(result)
    if (b.get("setup_engineer") or {}).get("rollback_plan", {}).get("needed"):
        status += " + rollback"
    return [{
        "title": "Race-Engineer Team Brief",
        "status": status,
        "sections": sections,
        "fingerprint": str(b.get("content_fingerprint") or ""),
    }]
