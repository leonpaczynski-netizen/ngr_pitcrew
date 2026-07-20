"""Live audio-first + adaptive-strategy composition (Program 2, Phases 63/65 production integration).

Ties the Phase-63 audio-first engineer state, the Phase-65 adaptive live strategy decision, and the
resulting concise verbal message into ONE immutable, DB-FREE view for the production Live tab and the
Phase-47 voice controller. It is the analogue of ``live_pit_wall_build`` for the audio-first channel.

Runtime loop it serves:
  live GT7 evidence → canonical race-state → strategy assessment → workload-aware approved message →
  offline verbal delivery → driver acknowledgement / PTT → continued monitoring.

Purity: no DB, no Qt, no network, no AI, no wall clock (timing injected). Never raises. It DECIDES and
COMPOSES; the voice controller/queue perform delivery, and no engineering state is mutated.
"""
from __future__ import annotations

from typing import Mapping, Optional

from strategy.audio_first_engineer import (
    VrRuntimeMode, EngineerMessageIntent, DriverWorkloadState,
    assess_driver_workload, resolve_audio_engineer_state, decide_engineer_speech,
)
from strategy.adaptive_live_strategy import (
    LiveStrategyState, StrategyObjective, decide_replan, build_strategy_driver_message,
)


def _b(x, default=False) -> bool:
    return bool(x) if x is not None else default


def build_live_audio_strategy_view(
    strategy_state: LiveStrategyState,
    *,
    vr_mode=VrRuntimeMode.DESKTOP,
    workload_context: Optional[Mapping] = None,
    voice_enabled: bool = False,
    gate_allows: bool = False,
    speaking: bool = False,
    ptt_active: bool = False,
    muted: bool = False,
    tts_available: bool = True,
    recognition_available: bool = False,
    ptt_available: bool = False,
    adapter_failed: bool = False,
    critical_only: bool = False,
    context_ok: bool = True,
    rules_verified: bool = True,
) -> dict:
    """Compose the audio-first + strategy view. DB-FREE. Returns a stable dict with the audio state, the
    strategy decision, the concise verbal message, and the speech decision (whether it may be spoken now
    given driver workload + audio state). Never raises."""
    try:
        telemetry_fresh = _b(getattr(strategy_state, "telemetry_fresh", True), True)

        audio = resolve_audio_engineer_state(
            vr_mode=vr_mode, voice_enabled=voice_enabled, gate_allows=gate_allows, speaking=speaking,
            ptt_active=ptt_active, muted=muted, tts_available=tts_available,
            recognition_available=recognition_available, ptt_available=ptt_available,
            telemetry_fresh=telemetry_fresh, adapter_failed=adapter_failed, critical_only=critical_only)

        workload = assess_driver_workload(workload_context)

        decision = decide_replan(strategy_state, context_ok=context_ok, rules_verified=rules_verified)
        message = build_strategy_driver_message(decision)

        # a strategy change is a STRATEGY_CHANGE intent; decide whether it may be spoken now.
        speech = decide_engineer_speech(EngineerMessageIntent.STRATEGY_CHANGE,
                                        workload=workload.state, audio=audio)

        return {
            "ok": True,
            "audio_state": audio.to_dict(),
            "workload": workload.to_dict(),
            "strategy_decision": decision.to_dict(),
            "strategy_message": message.to_dict(),
            "speech_decision": speech.to_dict(),
            "may_speak_now": bool(speech.speak),
            # stable identity for the stale-result guard (excludes volatile display state)
            "view_fingerprint": _view_fp(audio.fingerprint, decision.fingerprint, message.fingerprint),
        }
    except Exception:  # pragma: no cover - defensive
        return {"ok": False, "audio_state": {}, "workload": {}, "strategy_decision": {},
                "strategy_message": {}, "speech_decision": {}, "may_speak_now": False,
                "view_fingerprint": ""}


def _view_fp(*parts) -> str:
    import hashlib
    return "live_audio_strategy_v1:" + hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:24]
