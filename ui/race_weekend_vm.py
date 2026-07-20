"""Pure view-model for the Immersive Race Weekend surface (Qt-free, Program 2, Phase 50).

Turns the read-only race-weekend report dict into a banner + ceremonial cards (final arrival,
scrutineering verdict, chief-engineer plan, qualifying, race briefing, debrief). Built FROM the
accumulated preparation — it never rebuilds setup or strategy. Display strings only; never raises; no
setup values. Voice is shown as disabled-by-default and gated by VOICE_ELIGIBLE.
"""
from __future__ import annotations

from typing import List


def build(result=None) -> dict:
    return result if isinstance(result, dict) else {}


def is_empty(result) -> bool:
    r = build(result)
    return not r.get("ok")


_VERDICT_TONE = {
    "cleared": "success", "cleared_with_warnings": "warn", "garage_hold": "warn",
    "unverifiable": "info", "not_applicable": "neutral",
}


def header_text(result) -> str:
    r = build(result)
    if is_empty(result):
        return ("No race weekend active. The official weekend is the climax of the preparation cycle - "
                "it is built from the accumulated Practice evidence, never rebuilt from scratch. "
                "Read-only; issues no pit/tyre/fuel command; voice disabled by default. No setup values.")
    phase = str(r.get("phase") or "final_arrival").replace("_", " ").upper()
    arr = r.get("arrival") or {}
    parts = [f"[{phase}]  {arr.get('event_name') or 'Event'}"]
    if arr.get("next_required_action"):
        parts.append(f"Next: {arr.get('next_required_action')}.")
    return "  ".join(parts)


def banner_tone(result) -> str:
    if is_empty(result):
        return "advisory"
    sc = build(result).get("scrutineering") or {}
    v = str(sc.get("verdict") or "")
    if v == "garage_hold":
        return "warn"
    return "info"


def weekend_cards(result) -> List[dict]:
    r = build(result)
    if is_empty(result):
        return []
    cards: List[dict] = []

    arr = r.get("arrival") or {}
    if arr:
        cards.append({"title": "Final Arrival", "status_tag": "SUMMARY", "tone": "info", "lines": [
            f"Series/round: {arr.get('series') or '-'} {arr.get('round') or ''}".strip(),
            f"Track/layout: {arr.get('track') or '-'} {arr.get('layout') or ''}".strip(),
            f"Sessions completed: {arr.get('sessions_completed', 0)}   "
            f"Valid laps: {arr.get('total_valid_laps', 0)}.",
            f"Tyre model: {arr.get('tyre_model_confidence') or '-'}   "
            f"Fuel model: {arr.get('fuel_model_confidence') or '-'}   "
            f"Strategy: {arr.get('strategy_confidence') or '-'}.",
            f"Qualifying setup: {arr.get('qualifying_setup_fingerprint') or '-'}.",
            f"Race setup: {arr.get('race_setup_fingerprint') or '-'}.",
        ] + [f"Risk: {x}" for x in (arr.get("unresolved_risks") or [])]
          + [f"Blocker: {x}" for x in (arr.get("readiness_blockers") or [])]})

    br = r.get("briefing") or {}
    if br:
        acked = bool(br.get("acknowledged"))
        lines = [f"{it.get('topic')}: {it.get('detail') or ''}".strip(" :")
                 for it in (br.get("items") or [])]
        cards.append({"title": "NGR Driver Briefing",
                      "status_tag": "ACKNOWLEDGED" if acked else "ACK REQUIRED",
                      "tone": "success" if acked else "warn", "lines": lines or ["(no items)"]})

    sc = r.get("scrutineering") or {}
    if sc:
        v = str(sc.get("verdict") or "not_applicable")
        lines = [f"{c.get('name')}: {str(c.get('status') or '').upper()} {c.get('detail') or ''}".strip()
                 for c in (sc.get("checks") or [])]
        cards.append({"title": "Virtual Scrutineering", "status_tag": v.replace("_", " ").upper(),
                      "tone": _VERDICT_TONE.get(v, "neutral"), "lines": lines or ["(no checks)"]})

    cm = r.get("chief_meeting") or {}
    if cm:
        cards.append({"title": "Chief Engineer Final Meeting", "status_tag": "PLAN", "tone": "info",
                      "lines": [
                          f"Event objective: {cm.get('event_objective') or '-'}.",
                          f"Qualifying: {cm.get('qualifying_objective') or '-'}.",
                          f"Race: {cm.get('race_objective') or '-'}.",
                          f"Tyre plan: {cm.get('tyre_plan') or '-'}   Fuel plan: {cm.get('fuel_plan') or '-'}.",
                          f"Strategy: {cm.get('strategy_summary') or '-'}.",
                          f"Contingency: {cm.get('contingency_plan') or '-'}.",
                          f"Voice: {cm.get('voice_state') or 'disabled'}.",
                      ] + [f"Protected strength: {s}" for s in (cm.get("protected_strengths") or [])]})

    q = r.get("qualifying") or {}
    if q:
        cards.append({"title": "Qualifying", "status_tag": "LOW DENSITY", "tone": "info", "lines": [
            f"Setup: {q.get('setup_confirmation') or '-'}   Tyre: {q.get('tyre') or '-'}.",
            f"Attempts: {q.get('available_attempts', 0)}   Target: {q.get('target_lap') or '-'}.",
            "Critical corners: " + ", ".join(q.get("critical_corners") or []) + ".",
        ]})

    rb = r.get("race_briefing") or {}
    if rb:
        acked = bool(rb.get("acknowledged"))
        cards.append({"title": "Race Briefing",
                      "status_tag": "GRID READY" if rb.get("grid_ready") else
                                    ("ACKNOWLEDGED" if acked else "ACK REQUIRED"),
                      "tone": "success" if rb.get("grid_ready") else ("info" if acked else "warn"),
                      "lines": [
                          f"Start tyre: {rb.get('starting_tyre') or '-'}   Fuel: {rb.get('starting_fuel') or '-'}.",
                          f"Primary: {rb.get('primary_strategy') or '-'}.",
                          f"Fallback: {rb.get('fallback_strategy') or '-'}.",
                          "Pit windows: " + ", ".join(rb.get("pit_windows") or []) + ".",
                          f"Voice: {rb.get('voice_state') or 'disabled'}.",
                      ] + [f"Blocker: {b}" for b in (rb.get("final_blockers") or [])]})

    db = r.get("debrief") or {}
    if db:
        cards.append({"title": "Post-Race Debrief", "status_tag": "LEARNING", "tone": "info", "lines": [
            f"Result: {db.get('result') or '-'}   Race pace: {db.get('race_pace') or '-'}.",
            f"Setup: {db.get('setup_performance') or '-'}   Driver: {db.get('driver_performance') or '-'}.",
            f"Promotion/rollback: {db.get('setup_promotion_or_rollback') or '-'}.",
        ] + [f"Lesson: {x}" for x in (db.get("lessons_for_next_event") or [])]})

    return cards
