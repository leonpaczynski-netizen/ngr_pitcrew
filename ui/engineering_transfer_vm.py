"""Pure view-model for the Engineering Transfer section (Qt-free, Phase 23).

Turns the read-only ``SessionDB.build_programme_transfer_report`` result into structured cards +
banner. Display strings only - it evaluates/decides nothing itself, edits nothing, and reads the
deterministic report exactly as built. Never raises.
"""
from __future__ import annotations

from typing import List


def build(result=None) -> dict:
    return result if isinstance(result, dict) else {}


def _report(result) -> dict:
    r = build(result)
    t = r.get("transfer_report")
    return t if isinstance(t, dict) else {}


def is_empty(result) -> bool:
    return not build(result).get("ok") or not (_report(result).get("candidates") or [])


def header_text(result) -> str:
    rep = _report(result)
    cands = rep.get("candidates") or []
    if not cands:
        return ("No knowledge-transfer candidates yet - transfer is evaluated once this "
                "programme has established knowledge and other engineering contexts exist. "
                "Read-only - it reasons about knowledge reuse; it transfers no setup, imports "
                "nothing and applies nothing.")
    tot = rep.get("totals") or {}
    return (f"{len(cands)} candidate(s) across {tot.get('target_contexts')} target context(s): "
            f"{tot.get('reusable')} reusable, {tot.get('needs_more_evidence')} need more "
            f"evidence, {tot.get('not_reusable')} not reusable, {tot.get('isolated_targets')} "
            "isolated. Advisory only - it reasons about knowledge, not setups; it imports and "
            "applies nothing.")


def banner_tone(result) -> str:
    rep = _report(result)
    if not (rep.get("candidates") or []):
        return "info"
    tot = rep.get("totals") or {}
    if int(tot.get("reusable", 0)) > 0:
        return "success"
    if int(tot.get("isolated_targets", 0)) > 0 and int(tot.get("reusable", 0)) == 0:
        return "warn"
    return "info"


def transfer_cards(result) -> List[dict]:
    from strategy.programme_transfer_report_render import render_report_sections
    rep = _report(result)
    if not (rep.get("candidates") or []):
        return []
    return [{
        "title": "Engineering Knowledge Transfer",
        "status": f"{len(rep.get('candidates') or [])} candidate(s)",
        "sections": [(t, list(lines)) for t, lines in render_report_sections(rep)],
        "fingerprint": str(rep.get("content_fingerprint") or ""),
    }]
