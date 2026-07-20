"""Pure view-model for the Assisted Runtime pit-wall (Qt-free, Program 2, Phases 43-44).

Turns the read-only ``SessionDB.build_assisted_runtime_report`` result into a banner + a small set of
cards for ONE coordinated pit-wall: Run State, Live Advisory, Evidence Progress. Each card carries a
semantic tone AND an explicit text status tag (meaning is never carried by colour alone). Display
strings only; never raises; no setup values.
"""
from __future__ import annotations

from typing import List


def build(result=None) -> dict:
    return result if isinstance(result, dict) else {}


def is_empty(result) -> bool:
    r = build(result)
    return not r.get("ok") or not r.get("workflow")


def _state(result) -> str:
    return str((build(result).get("workflow") or {}).get("state") or "")


def status_summary(result):
    r = build(result)
    st = _state(result)
    if st == "invalid":
        return ("BLOCKED", "warn")
    if st == "ready_to_run":
        return ("READY TO RUN", "success")
    if st in ("outcome_review_required", "ready_to_record"):
        return ("OUTCOME REVIEW", "info")
    if st in ("setup_confirmation_required", "preflight_required"):
        return ("CONFIRM REQUIRED", "warn")
    if st == "recorded":
        return ("RECORDED", "success")
    return (st.replace("_", " ").upper() or "PLAN READY", "info")


def header_text(result) -> str:
    r = build(result)
    if is_empty(result):
        return ("No assisted runtime yet. Read-only, advisory-only - it guides a user-confirmed practice "
                "run and delivers safely-gated live text advisories. It applies no setup, creates no "
                "experiment, records no outcome, binds no session automatically, and speaks no voice. "
                "No setup values.")
    tag, _tone = status_summary(result)
    wf = r.get("workflow") or {}
    parts = [f"[{tag}]  Next: {wf.get('next_user_action') or '-'}"]
    ep = r.get("evidence_progress") or {}
    if ep.get("min_clean"):
        parts.append(f"Clean laps {ep.get('clean_laps', 0)}/{ep.get('min_clean')}.")
    return " ".join(parts)


def banner_tone(result) -> str:
    if is_empty(result):
        return "advisory"
    return status_summary(result)[1]


def runtime_cards(result) -> List[dict]:
    from strategy.live_advisory_render import render_advisory_sections
    r = build(result)
    if is_empty(result):
        return []
    cards: List[dict] = []

    wf = r.get("workflow") or {}
    tag, tone = status_summary(result)
    sc = wf.get("setup_check") or {}
    state_lines = [f"State: {str(wf.get('state') or '-').replace('_', ' ').upper()}.",
                   f"Next: {wf.get('next_user_action') or '-'}",
                   f"Setup check: {str(sc.get('verification') or '-').replace('_', ' ')} - "
                   f"{sc.get('reason') or ''}"]
    for b in (wf.get("blockers") or []):
        state_lines.append(f"Blocker: {b}")
    cards.append({"title": "1. Run State", "status_tag": tag, "tone": tone, "lines": state_lines})

    adv = r.get("advisory") or {}
    adv_lines: List[str] = []
    for _t, ls in render_advisory_sections(adv):
        adv_lines.append(f"[{_t}]")
        adv_lines.extend(ls)
    dv = adv.get("delivered")
    atag = ("STOP" if dv and dv.get("prompt_class") == "stop_critical" else
            "ADVISORY" if dv else "QUIET")
    atone = ("warn" if dv and dv.get("prompt_class") in ("stop_critical", "cautionary") else
             "info" if dv else "neutral")
    cards.append({"title": "2. Live Advisory", "status_tag": atag, "tone": atone, "lines": adv_lines})

    ep = r.get("evidence_progress") or {}
    mt = r.get("material_trust") or {}
    ev_lines = [f"Clean laps: {ep.get('clean_laps', 0)}/{ep.get('min_clean', '-')}.",
                f"Context trust: {str(mt.get('overall_trust') or '-').replace('_', ' ').upper()}.",
                f"Outcome review ready: {bool(r.get('outcome_ready'))}."]
    if mt.get("limitation_explanation"):
        ev_lines.append(f"Limitations: {mt.get('limitation_explanation')}")
    cards.append({"title": "3. Evidence Progress", "status_tag": "PROGRESS", "tone": "info",
                  "lines": ev_lines})
    return cards
