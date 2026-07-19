"""Pure view-model for the Re-validation Status section (Qt-free, Phase 26).

Turns the read-only ``SessionDB.build_programme_revalidation_report`` result into structured cards +
banner. Display strings only; never raises.
"""
from __future__ import annotations

from typing import List


def build(result=None) -> dict:
    return result if isinstance(result, dict) else {}


def _report(result) -> dict:
    r = build(result)
    v = r.get("revalidation")
    return v if isinstance(v, dict) else {}


def is_empty(result) -> bool:
    return not build(result).get("ok") or not (_report(result).get("items") or [])


def header_text(result) -> str:
    rep = _report(result)
    items = rep.get("items") or []
    if not items:
        return ("No knowledge to assess for re-validation yet. Read-only - dates are evidence "
                "data, not an automatic expiry; nothing is scheduled or applied; no setup values.")
    tot = rep.get("totals") or {}
    return (f"{len(items)} domain(s): {tot.get('current_protected')} current/protected, "
            f"{tot.get('advised')} advised, {tot.get('required') + tot.get('version_invalidated')} "
            f"require re-validation, {tot.get('conflict_weakened') + tot.get('regression_weakened')} "
            f"weakened, {tot.get('superseded_retired')} superseded/retired. Advisory only - no "
            "action is scheduled or applied.")


def banner_tone(result) -> str:
    rep = _report(result)
    if not (rep.get("items") or []):
        return "info"
    tot = rep.get("totals") or {}
    if int(tot.get("version_invalidated", 0)) + int(tot.get("conflict_weakened", 0)) \
            + int(tot.get("regression_weakened", 0)) > 0:
        return "warn"
    if int(tot.get("current_protected", 0)) > 0:
        return "success"
    return "info"


def revalidation_cards(result) -> List[dict]:
    from strategy.programme_revalidation_report_render import render_revalidation_sections
    rep = _report(result)
    if not (rep.get("items") or []):
        return []
    return [{
        "title": "Knowledge Re-validation Status",
        "status": f"{len(rep.get('items') or [])} domain(s)",
        "sections": [(t, list(lines)) for t, lines in render_revalidation_sections(rep)],
        "fingerprint": str(rep.get("content_fingerprint") or ""),
    }]
