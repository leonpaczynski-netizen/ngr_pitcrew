"""Pure view-model for the PSVR2 audio-first race engineer + live strategy (Qt-free, Program 2, Phase 63/65).

Turns the ``build_live_audio_strategy_view`` dict into a glanceable, low-cognitive-load driver surface:
an always-visible voice/listening STATUS line, ONE low-density strategy card (what changed → revised plan
→ confidence → next review) with an acknowledgement affordance, and recovery cards for voice failure /
telemetry loss. Meaning is carried by tag + text (never colour alone). Detailed candidate tables are NOT
here — they belong in the garage/strategy-review. Display strings only; never raises.

Design (from the /ui-ux-pro-max gate): audio is the primary live channel and this visual surface is the
fallback for non-VR users; one primary message at a time; high-contrast NGR tones; tabular numbers; the
detailed candidate comparison is deferred (progressive disclosure).
"""
from __future__ import annotations

from typing import List


def build(result=None) -> dict:
    return result if isinstance(result, dict) else {}


def is_empty(result) -> bool:
    r = build(result)
    return not r.get("ok")


_STATE_TONE = {
    "voice_ready": "success", "voice_active": "success", "ptt_active": "info",
    "voice_gated": "neutral", "voice_disabled": "neutral", "visual_only": "neutral",
    "muted": "neutral", "recognition_unavailable": "info", "critical_only": "warn",
    "telemetry_stale": "warn", "tts_unavailable": "warn", "adapter_failure": "warn",
}

_REC_TONE = {
    "PLAN_STILL_OPTIMAL": "success", "PLAN_VIABLE": "success", "MONITOR": "info",
    "PACE_INCREASE_AVAILABLE": "info", "CONSERVATION_REQUIRED": "warn",
    "REPLAN_RECOMMENDED": "warn", "REPLAN_URGENT": "warn",
    "INSUFFICIENT_EVIDENCE": "neutral", "CONTEXT_MISMATCH": "warn", "RULES_UNVERIFIED": "warn",
}


def status_line(result) -> str:
    r = build(result)
    if is_empty(result):
        return ("Audio-first race engineer: not active. Enable the voice and enter Live to receive spoken "
                "race-engineer support. Voice is off by default and issues no pit/tyre/fuel/setup command.")
    a = r.get("audio_state", {})
    line = str(a.get("status_line") or "")
    notes = a.get("notes") or []
    return line + (("  " + notes[0]) if notes else "")


def status_tone(result) -> str:
    r = build(result)
    if is_empty(result):
        return "neutral"
    return _STATE_TONE.get(str(r.get("audio_state", {}).get("state")), "neutral")


def strategy_card(result) -> dict:
    """The ONE low-density strategy card (headline, revised plan, confidence, next review, ack)."""
    r = build(result)
    if is_empty(result):
        return {}
    dec = r.get("strategy_decision", {})
    msg = r.get("strategy_message", {})
    rec = str(dec.get("recommendation") or "")
    return {
        "title": "Live Strategy",
        "status_tag": rec.replace("_", " ") or "-",
        "tone": _REC_TONE.get(rec, "info"),
        "headline": str(msg.get("headline") or "-"),
        "confidence": str(dec.get("confidence") or "-"),
        "next_review": str(dec.get("next_review_trigger") or "-"),
        # acknowledgement is an affordance; it never executes anything
        "acknowledgeable": rec not in ("PLAN_STILL_OPTIMAL", "INSUFFICIENT_EVIDENCE"),
        "detail_available": bool(msg.get("detail")),
    }


def recovery_card(result) -> dict:
    """A recovery card when voice failed or telemetry was lost; empty otherwise."""
    r = build(result)
    if is_empty(result):
        return {}
    state = str(r.get("audio_state", {}).get("state"))
    if state in ("adapter_failure", "tts_unavailable"):
        return {"title": "Voice Recovery", "tone": "warn",
                "lines": ["Voice unavailable — the visual pit wall and strategy card remain functional.",
                          "No retry loop; engineering conclusions are unchanged."]}
    if state == "telemetry_stale":
        return {"title": "Telemetry Recovery", "tone": "warn",
                "lines": ["Telemetry stale — routine radio paused; only critical messages will be spoken.",
                          "Strategy confidence is reduced until telemetry is restored."]}
    return {}


def cards(result) -> List[dict]:
    out: List[dict] = []
    sc = strategy_card(result)
    if sc:
        out.append(sc)
    rc = recovery_card(result)
    if rc:
        out.append(rc)
    return out
