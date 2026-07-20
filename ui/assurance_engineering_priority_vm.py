"""Pure view-model for the Assurance-Driven Engineering Priority section (Qt-free, Phase 32).

Turns the read-only ``SessionDB.build_assurance_engineering_priority_report`` result into a structured
card + banner. Display strings only; never raises.
"""
from __future__ import annotations

from typing import List


def build(result=None) -> dict:
    return result if isinstance(result, dict) else {}


def _report(result) -> dict:
    r = build(result)
    v = r.get("priority")
    return v if isinstance(v, dict) else {}


def is_empty(result) -> bool:
    rep = _report(result)
    if not build(result).get("ok") or not rep:
        return True
    # show the card when there is a verdict to explain (candidates OR a truthful no-action state)
    return not (rep.get("prioritised_candidates") or rep.get("deferred_candidates")
                or rep.get("no_action_statement"))


def grade_label(result) -> str:
    rep = _report(result)
    return str(rep.get("assurance_grade") or "").replace("_", " ").upper() or "-"


def top_priority(result) -> str:
    rep = _report(result)
    cands = rep.get("prioritised_candidates") or []
    if not cands:
        return "no action" if rep.get("no_action_statement") else "-"
    c = cands[0]
    doms = ", ".join(str(d).replace("_", " ") for d in (c.get("domains") or [])) or "programme"
    return f"{str(c.get('investigation_type') or '').replace('_', ' ')} ({doms})"


def header_text(result) -> str:
    rep = _report(result)
    if not rep:
        return ("No assurance priority to report yet. Read-only, advisory-only - this ranks the "
                "evidence to collect next, never an experiment, setup or Apply; no setup values.")
    if rep.get("no_action_statement") and not (rep.get("prioritised_candidates")
                                               or rep.get("deferred_candidates")):
        return str(rep.get("no_action_statement"))
    return str(rep.get("assurance_summary") or "")


def banner_tone(result) -> str:
    rep = _report(result)
    if not rep:
        return "info"
    if int(rep.get("blocking_finding_count") or 0) > 0:
        return "warn"
    if rep.get("no_action_statement") and not rep.get("prioritised_candidates"):
        return "success"
    return "info"


def priority_cards(result) -> List[dict]:
    from strategy.assurance_engineering_priority_render import render_priority_sections
    rep = _report(result)
    if is_empty(result):
        return []
    return [{
        "title": "Assurance-Driven Engineering Priority",
        "status": f"grade {grade_label(result)} - top: {top_priority(result)}",
        "sections": [(t, list(lines)) for t, lines in render_priority_sections(rep)],
        "fingerprint": str(rep.get("content_fingerprint") or ""),
    }]
