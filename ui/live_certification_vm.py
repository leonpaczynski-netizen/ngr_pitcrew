"""Pure view-model for the live/VR certification display + PSVR2 readiness (Qt-free, Program 2, Phase 68).

Turns a certification payload into a glanceable per-area + overall display (per-area and overall shown
SEPARATELY, per the /ui-ux-pro-max gate), and computes the PSVR2 audio-first readiness checklist. Meaning
by tag + text (never colour alone); NONE areas render neutral with their required-next-evidence. Display
strings only; never raises.
"""
from __future__ import annotations

from typing import List


_LEVEL_TONE = {
    "not_tested": "neutral", "automated_only": "info", "offscreen_validated": "info",
    "replay_validated": "info", "visual_uat_partial": "warn", "visual_uat_validated": "success",
    "live_gt7_partial": "warn", "live_gt7_validated": "success",
    "operationally_ready_with_limitations": "success", "operationally_ready": "success",
}

_EVIDENCE_TONE = {"none": "neutral", "automated": "info", "offscreen": "info", "replay": "info",
                  "visual_partial": "warn", "visual": "success", "live_partial": "warn", "live": "success"}


def overall_card(cert_payload) -> dict:
    p = cert_payload if isinstance(cert_payload, dict) else {}
    level = str(p.get("overall_level") or "not_tested")
    return {"title": "Overall Certification", "status_tag": level.replace("_", " ").upper(),
            "tone": _LEVEL_TONE.get(level, "neutral"),
            "lines": [f"Overall: {level.replace('_', ' ')}.",
                      "Per-area detail is shown separately below — overall is bounded by the weakest area."]}


def area_rows(cert_payload) -> List[dict]:
    p = cert_payload if isinstance(cert_payload, dict) else {}
    rows: List[dict] = []
    for a in p.get("areas", []):
        ev = str(a.get("evidence_type") or "none")
        lvl = str(a.get("effective_level") or "not_tested")
        findings = a.get("findings") or []
        note = findings[0].get("message") if findings else ""
        rows.append({"name": str(a.get("name") or "").replace("_", " "),
                     "evidence_tag": ev.replace("_", " ").upper(),
                     "level_tag": lvl.replace("_", " ").upper(),
                     "tone": _EVIDENCE_TONE.get(ev, "neutral"), "note": note})
    return rows


def psvr2_readiness(*, tts_available: bool, ptt_bound: bool, voice_enabled: bool,
                    recognition_available: bool = False) -> dict:
    """A pass/fail PSVR2 audio-first readiness checklist. Recognition is optional (voice-out still works
    without a mic). Never raises."""
    checks = [
        {"label": "TTS output device ready", "pass": bool(tts_available), "required": True},
        {"label": "Push-to-talk bound", "pass": bool(ptt_bound), "required": True},
        {"label": "Race-engineer voice enabled", "pass": bool(voice_enabled), "required": True},
        {"label": "Microphone / recognition (optional)", "pass": bool(recognition_available),
         "required": False},
    ]
    required_ok = all(c["pass"] for c in checks if c["required"])
    return {"checks": checks, "ready": bool(required_ok),
            "summary": ("Audio-first ready — you can drive in PSVR2 without the screen."
                        if required_ok else
                        "Not ready — complete the required checks to drive in PSVR2 without the screen.")}
