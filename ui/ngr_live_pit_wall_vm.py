"""Pure view-model for the NGR Live Pit Wall (Qt-free, Program 2, Phase 58).

Turns the pit-wall view dict (from ``pit_wall_to_dict``) into a glanceable, low-cognitive-load driver
HUD: a mode banner + a strict hierarchy (event/objective, match, telemetry, single advisory, evidence
progress, next action, voice status). ONE coordinated message. Meaning by tag + tone (never colour
alone). Display strings only; never raises.

Design (from the /ui-ux-pro-max gate): glanceable, one primary message, high-contrast NGR tones,
mode-distinct; the driving hierarchy is replaced by a transition/recovery card at session end / telemetry
loss; advisories are suppressed when stale or blocked.
"""
from __future__ import annotations

from typing import List


def build(result=None) -> dict:
    return result if isinstance(result, dict) else {}


def is_empty(result) -> bool:
    r = build(result)
    return not r.get("ok") or r.get("mode") == "idle"


_MODE_TONE = {"practice": "info", "qualifying": "info", "race": "warn", "transition": "warn",
              "recovery": "warn", "idle": "neutral"}


def header_text(result) -> str:
    r = build(result)
    if is_empty(result):
        return ("No live activity. Select a preparation activity and enter Live to receive safe NGR "
                "pit-wall support. Read-only; issues no pit/tyre/fuel/setup command; voice off by default.")
    mode = str(r.get("mode") or "practice").upper()
    parts = [f"[{mode}]  {r.get('event_line') or 'NGR live'}"]
    if r.get("objective"):
        parts.append(f"Objective: {r.get('objective')}.")
    return "  ".join(parts)


def banner_tone(result) -> str:
    if is_empty(result):
        return "advisory"
    if build(result).get("blocked"):
        return "warn"
    return _MODE_TONE.get(str(build(result).get("mode")), "info")


def hierarchy_cards(result) -> List[dict]:
    r = build(result)
    if is_empty(result):
        return []
    cards: List[dict] = []
    blocked = bool(r.get("blocked"))
    mode = str(r.get("mode") or "practice")

    # (3) context + setup match
    cards.append({"title": "Context & Setup", "status_tag": "BLOCKED" if blocked else "MATCH",
                  "tone": "warn" if blocked else "success",
                  "lines": [r.get("match_summary") or "-"]
                           + ([r.get("purpose_note")] if r.get("purpose_note") else [])})

    # (4) telemetry state
    telem = str(r.get("telemetry_state") or "-")
    cards.append({"title": "Telemetry", "status_tag": telem.upper(),
                  "tone": "success" if telem == "fresh" else "warn", "lines": [f"Telemetry {telem}."]})

    # (5) single advisory (or suppression note)
    if r.get("advisory_suppressed"):
        cards.append({"title": "Advisory", "status_tag": "SUPPRESSED", "tone": "neutral",
                      "lines": ["Routine advisories suppressed (stale telemetry or blocked activity)."]})
    elif r.get("advisory"):
        cards.append({"title": "Advisory", "status_tag": "ADVISORY", "tone": "info",
                      "lines": [r.get("advisory")]})

    # (6) evidence progress
    vl, tl = int(r.get("valid_laps", 0)), int(r.get("target_laps", 0))
    pct = int(round(float(r.get("evidence_progress", 0.0)) * 100))
    cards.append({"title": "Evidence Progress", "status_tag": f"{pct}%", "tone": "info",
                  "lines": [f"Valid laps: {vl}" + (f" / {tl}" if tl else "") + f"  ({pct}%)."]})

    # (7) next action
    cards.append({"title": "Next Action", "status_tag": mode.upper(), "tone": _MODE_TONE.get(mode, "info"),
                  "lines": [r.get("next_action") or "-"]})

    # (8) voice status
    vs = str(r.get("voice_status") or "disabled")
    cards.append({"title": "Voice", "status_tag": vs.replace("_", " ").upper(),
                  "tone": "warn" if vs == "adapter_failure" else ("success" if vs in ("eligible", "active") else "neutral"),
                  "lines": [f"Voice: {vs.replace('_', ' ')}."]})
    return cards
