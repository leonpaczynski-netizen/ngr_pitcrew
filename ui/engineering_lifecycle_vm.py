"""Pure view-model for the Engineering Lifecycle panel (Qt-free, Phase 16).

Turns the read-only ``SessionDB.build_engineering_lifecycle`` overview into structured cards
+ ordered loop-stage rows. Display strings only - it applies nothing, edits nothing, and
reads the deterministic lifecycle exactly as built. Never raises.
"""
from __future__ import annotations

from typing import List


def build(result=None) -> dict:
    return result if isinstance(result, dict) else {}


def is_empty(result) -> bool:
    r = build(result)
    return not r.get("ok") or not (r.get("stages") or [])


def header_text(result) -> str:
    r = build(result)
    n = int(r.get("count") or 0)
    ready = int(r.get("ready_count") or 0)
    recon = int(r.get("reconciliation_count") or 0)
    if not n:
        return ("No engineering lifecycle to show yet for this car / track / discipline. "
                "The closed loop appears once a diagnosis yields a bounded experiment.")
    return (f"{n} diagnosis chain(s) - {ready} with a bounded experiment ready for manual "
            f"apply; {recon} reconciliation record(s) folded into calibration. Read-only: "
            f"nothing is applied here.")


def _status_label(v: str) -> str:
    return str(v or "").replace("_", " ").title()


def stage_cards(result) -> List[dict]:
    from strategy.experiment_lifecycle_render import render_summary_sections
    r = build(result)
    cards: List[dict] = []
    for s in r.get("stages") or []:
        issue = s.get("diagnosis") or {}
        itype = str(issue.get("issue_type") or "issue").replace("_", " ")
        cards.append({
            "title": f"{itype.capitalize()}",
            "status": _status_label(s.get("lifecycle_state")),
            "status_key": str(s.get("lifecycle_state") or ""),
            "sections": [(t, list(lines)) for t, lines in render_summary_sections(s)],
            "fingerprint": str(s.get("content_fingerprint") or ""),
        })
    return cards


def banner_tone(result) -> str:
    r = build(result)
    if is_empty(r):
        return "info"
    states = {str(s.get("lifecycle_state")) for s in r.get("stages") or []}
    if "calibrated" in states or "reconciled" in states or "completed" in states:
        return "success"
    if states & {"ready_for_manual_apply", "outcome_recorded", "applied", "test_in_progress"}:
        return "info"
    if states & {"preflight_failed", "blocked", "rejected"}:
        return "warn"
    return "info"
