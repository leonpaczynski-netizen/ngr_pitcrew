"""Pure view-model for the Evidence Coverage & Blind-Spot section (Qt-free, Phase 27).

Turns the read-only ``SessionDB.build_programme_evidence_coverage_report`` result into structured
cards + banner. Display strings only; never raises.
"""
from __future__ import annotations

from typing import List


def build(result=None) -> dict:
    return result if isinstance(result, dict) else {}


def _report(result) -> dict:
    r = build(result)
    v = r.get("coverage")
    return v if isinstance(v, dict) else {}


def is_empty(result) -> bool:
    return not build(result).get("ok") or not (_report(result).get("domain_coverage") or [])


def header_text(result) -> str:
    rep = _report(result)
    coverages = rep.get("domain_coverage") or []
    if not coverages:
        return ("No evidence coverage to map yet. Read-only - a blind spot is where more evidence "
                "would help, never a fault; missing coverage means untested, not wrong. Nothing is "
                "scheduled or applied; no setup values.")
    tot = rep.get("totals") or {}
    return (f"{len(coverages)} domain(s) assessed: {tot.get('well_covered')} well-covered, "
            f"{tot.get('blind_spots_raised')} blind spot(s) raised (critical {tot.get('critical')}, "
            f"material {tot.get('material')}, moderate {tot.get('moderate')}), "
            f"{tot.get('early_stage_gaps')} early-stage gap(s). Advisory only - a blind spot is a "
            "place for more evidence, not a defect.")


def banner_tone(result) -> str:
    rep = _report(result)
    if not (rep.get("domain_coverage") or []):
        return "info"
    tot = rep.get("totals") or {}
    if int(tot.get("critical", 0)) + int(tot.get("material", 0)) > 0:
        return "warn"
    if int(tot.get("well_covered", 0)) > 0:
        return "success"
    return "info"


def coverage_cards(result) -> List[dict]:
    from strategy.programme_coverage_report_render import render_coverage_sections
    rep = _report(result)
    if not (rep.get("domain_coverage") or []):
        return []
    return [{
        "title": "Evidence Coverage & Blind Spots",
        "status": f"{len(rep.get('domain_coverage') or [])} domain(s)",
        "sections": [(t, list(lines)) for t, lines in render_coverage_sections(rep)],
        "fingerprint": str(rep.get("content_fingerprint") or ""),
    }]
