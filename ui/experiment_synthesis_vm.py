"""Pure view-model for the Bounded Experiment Synthesis panel (Qt-free, Phase 15).

Turns the read-only ``SessionDB.build_bounded_setup_experiments`` report into structured
cards + sections. Display strings only - it authors no value, selects no tie, and reads the
deterministic synthesis exactly as built. Never raises.
"""
from __future__ import annotations

from typing import List


def build(result=None) -> dict:
    return result if isinstance(result, dict) else {}


def is_empty(result) -> bool:
    r = build(result)
    return not r.get("ok") or not (r.get("synthesis_results") or [])


def header_text(result) -> str:
    r = build(result)
    n = int(r.get("count") or 0)
    ready = int(r.get("ready_for_preflight") or 0)
    if not n:
        return ("No bounded setup experiments yet for this car / track / discipline. "
                "A candidate appears once a diagnosis yields an eligible testable hypothesis "
                "and the canonical applied setup is a valid baseline.")
    return (f"{n} diagnosis(es) with bounded-experiment synthesis - {ready} ready for "
            f"preflight. Advisory only: the smallest legal reversible TEST, not a final "
            f"tune; nothing is applied.")


def safety_text(result) -> str:
    r = build(result)
    return str(r.get("safety_statement") or "")


def _status_label(v: str) -> str:
    return str(v or "").replace("_", " ").title()


def result_cards(result) -> List[dict]:
    from strategy.experiment_synthesis_render import render_result_sections
    r = build(result)
    cards: List[dict] = []
    for s in r.get("synthesis_results") or []:
        hset = s.get("source_hypothesis_set") or {}
        issue = hset.get("canonical_issue") or {}
        itype = str(issue.get("issue_type") or "issue").replace("_", " ")
        base = s.get("baseline") or {}
        cards.append({
            "title": f"{itype.capitalize()}  ·  baseline {str(base.get('setup_hash'))[:8] or '-'}",
            "status": _status_label(s.get("overall_status")),
            "status_key": str(s.get("overall_status") or ""),
            "sections": [(t, list(lines)) for t, lines in render_result_sections(s)],
            "fingerprint": str(s.get("content_fingerprint") or ""),
        })
    return cards


def banner_tone(result) -> str:
    r = build(result)
    if is_empty(r):
        return "info"
    statuses = {str(s.get("overall_status")) for s in r.get("synthesis_results") or []}
    if "ready_for_preflight" in statuses:
        return "success"
    if statuses & {"conditional", "requires_coupled_experiment"}:
        return "info"
    if statuses & {"blocked_by_prior_regression", "blocked_by_working_window",
                   "blocked_by_baseline_state", "blocked_by_legality",
                   "blocked_by_interaction_risk"}:
        return "warn"
    return "info"
