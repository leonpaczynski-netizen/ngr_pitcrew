"""Pure view-model for the Engineering Plan panel (Qt-free, Phase 17).

Turns the read-only ``SessionDB.build_experiment_portfolio`` result into structured cards +
sections. Display strings only - it ranks nothing itself, edits nothing, and reads the
deterministic portfolio exactly as built. Never raises.
"""
from __future__ import annotations

from typing import List


def build(result=None) -> dict:
    return result if isinstance(result, dict) else {}


def _portfolio(result) -> dict:
    r = build(result)
    p = r.get("portfolio")
    return p if isinstance(p, dict) else {}


def is_empty(result) -> bool:
    r = build(result)
    return not r.get("ok") or not (_portfolio(r).get("valuations") or [])


def header_text(result) -> str:
    r = build(result)
    p = _portfolio(r)
    n = len(p.get("valuations") or [])
    if not n:
        return ("No engineering plan yet for this car / track / discipline. A prioritised "
                "experiment plan appears once legal bounded experiments exist.")
    hv = p.get("highest_value")
    lead = (f"Next: {str(hv.get('direction') or '').replace('_', ' ')} {hv.get('field')}"
            if hv else "no single highest-value experiment (tie/none)")
    return (f"{n} legal experiment(s) ranked by engineering value (information gain first). "
            f"{lead}. Session suitability: {str(p.get('session_suitability') or '').replace('_', ' ')}. "
            f"Advisory only - nothing is applied.")


def banner_tone(result) -> str:
    p = _portfolio(result)
    if not (p.get("valuations") or []):
        return "info"
    if p.get("highest_value"):
        return "success"
    return "info"


def plan_cards(result) -> List[dict]:
    from strategy.experiment_portfolio_render import render_portfolio_sections
    p = _portfolio(result)
    if not (p.get("valuations") or []):
        return []
    return [{
        "title": "Engineering Plan",
        "status": (str((p.get("highest_value") or {}).get("field") or "tie / manual choice")),
        "sections": [(t, list(lines)) for t, lines in render_portfolio_sections(p)],
        "fingerprint": str(p.get("content_fingerprint") or ""),
    }]
