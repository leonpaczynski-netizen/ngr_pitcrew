"""Phase 63 — PSVR2 audio-first race engineer: priority, workload, window, duration, state, decision."""
from __future__ import annotations

from strategy.audio_first_engineer import (
    VrRuntimeMode, EngineerMessageIntent, EngineerMessagePriority, DriverWorkloadState,
    AudioFirstEngineerState, AudioOperationalReadiness, SpeechWindowVerdict,
    classify_message_priority, assess_driver_workload, decide_speech_window, message_duration_budget,
    resolve_audio_engineer_state, decide_engineer_speech,
)


# --- message priority (single authority) --- #
def test_priority_order_is_deterministic_and_ranked():
    assert classify_message_priority(EngineerMessageIntent.SAFETY_CRITICAL) == EngineerMessagePriority.SAFETY
    assert classify_message_priority(EngineerMessageIntent.STRATEGY_CHANGE) == EngineerMessagePriority.STRATEGY
    assert classify_message_priority(EngineerMessageIntent.DRIVER_COACHING) == EngineerMessagePriority.COACHING
    # safety strictly outranks (lower int) coaching
    assert int(EngineerMessagePriority.SAFETY) < int(EngineerMessagePriority.COACHING)


def test_unknown_intent_is_lowest_never_urgent():
    assert classify_message_priority("nonsense") == EngineerMessagePriority.INFO
    assert classify_message_priority(None) == EngineerMessagePriority.INFO


# --- workload --- #
def test_workload_low_on_straight_and_pit():
    assert assess_driver_workload({"segment": "back_straight"}).state == DriverWorkloadState.LOW
    assert assess_driver_workload({"in_pit_lane": True}).state == DriverWorkloadState.LOW
    assert assess_driver_workload({"speed_kmh": 0.0}).state == DriverWorkloadState.LOW


def test_workload_high_when_braking_or_cornering():
    assert assess_driver_workload({"braking": True}).state == DriverWorkloadState.HIGH
    assert assess_driver_workload({"segment": "turn_1_apex"}).state == DriverWorkloadState.HIGH
    assert assess_driver_workload({"steering": 0.6}).state == DriverWorkloadState.HIGH


def test_workload_unknown_is_conservative():
    assert assess_driver_workload({}).state == DriverWorkloadState.UNKNOWN
    assert assess_driver_workload(None).state == DriverWorkloadState.UNKNOWN
    assert assess_driver_workload({"telemetry_fresh": False}).state == DriverWorkloadState.UNKNOWN
    # unknown workload is not 'inputs_available'
    assert assess_driver_workload({}).inputs_available is False


# --- speech window --- #
def test_routine_only_speaks_in_low_workload():
    coaching = EngineerMessagePriority.COACHING
    assert decide_speech_window(coaching, DriverWorkloadState.LOW).verdict == SpeechWindowVerdict.SPEAK_NOW
    assert decide_speech_window(coaching, DriverWorkloadState.HIGH).verdict == SpeechWindowVerdict.DEFER
    # unknown workload defers routine (conservative)
    assert decide_speech_window(coaching, DriverWorkloadState.UNKNOWN).verdict == SpeechWindowVerdict.DEFER
    assert decide_speech_window(coaching, DriverWorkloadState.MODERATE).verdict == SpeechWindowVerdict.DEFER


def test_urgent_overrides_workload_window():
    for pr in (EngineerMessagePriority.SAFETY, EngineerMessagePriority.STRATEGY,
               EngineerMessagePriority.PIT_FUEL):
        d = decide_speech_window(pr, DriverWorkloadState.HIGH)
        assert d.verdict == SpeechWindowVerdict.OVERRIDE and d.may_speak is True


# --- duration budget --- #
def test_duration_budget_concise_and_routine_capped():
    assert message_duration_budget(EngineerMessagePriority.SAFETY) <= 1.5
    assert message_duration_budget(EngineerMessagePriority.COACHING) <= 2.5
    assert message_duration_budget(EngineerMessagePriority.LAP_STINT) <= 2.5


# --- composite state / readiness --- #
def test_desktop_mode_is_visual_only_by_default():
    s = resolve_audio_engineer_state(vr_mode=VrRuntimeMode.DESKTOP)
    assert s.state == AudioFirstEngineerState.VISUAL_ONLY
    assert s.readiness == AudioOperationalReadiness.NOT_AUDIO_FIRST


def test_audio_first_ready_requires_tts_and_gate():
    s = resolve_audio_engineer_state(vr_mode=VrRuntimeMode.AUDIO_FIRST, voice_enabled=True,
                                     gate_allows=True, tts_available=True, recognition_available=True)
    assert s.state == AudioFirstEngineerState.VOICE_READY
    assert s.readiness == AudioOperationalReadiness.READY


def test_audio_first_gated_when_gate_denies():
    s = resolve_audio_engineer_state(vr_mode=VrRuntimeMode.AUDIO_FIRST, voice_enabled=True,
                                     gate_allows=False, tts_available=True, recognition_available=True)
    assert s.state == AudioFirstEngineerState.VOICE_GATED


def test_adapter_failure_and_tts_unavailable_are_unavailable_and_preserve_visual():
    fail = resolve_audio_engineer_state(vr_mode=VrRuntimeMode.AUDIO_FIRST, voice_enabled=True,
                                        adapter_failed=True)
    assert fail.state == AudioFirstEngineerState.ADAPTER_FAILURE
    assert fail.readiness == AudioOperationalReadiness.UNAVAILABLE
    assert any("visual pit wall preserved" in n.lower() for n in fail.notes)
    no_tts = resolve_audio_engineer_state(vr_mode=VrRuntimeMode.AUDIO_FIRST, voice_enabled=True,
                                          tts_available=False)
    assert no_tts.state == AudioFirstEngineerState.TTS_UNAVAILABLE


def test_no_mic_is_voice_out_ready_but_degraded():
    s = resolve_audio_engineer_state(vr_mode=VrRuntimeMode.AUDIO_FIRST, voice_enabled=True,
                                     gate_allows=True, tts_available=True, recognition_available=False)
    assert s.state == AudioFirstEngineerState.RECOGNITION_UNAVAILABLE
    assert s.readiness == AudioOperationalReadiness.DEGRADED


def test_telemetry_stale_and_critical_only_states():
    stale = resolve_audio_engineer_state(vr_mode=VrRuntimeMode.AUDIO_FIRST, voice_enabled=True,
                                         gate_allows=True, tts_available=True, telemetry_fresh=False)
    assert stale.state == AudioFirstEngineerState.TELEMETRY_STALE
    crit = resolve_audio_engineer_state(vr_mode=VrRuntimeMode.AUDIO_FIRST, voice_enabled=True,
                                        gate_allows=True, tts_available=True, critical_only=True)
    assert crit.state == AudioFirstEngineerState.CRITICAL_ONLY


# --- speech decision composition --- #
def test_speech_decision_defers_routine_in_high_workload():
    d = decide_engineer_speech(EngineerMessageIntent.DRIVER_COACHING, workload=DriverWorkloadState.HIGH)
    assert d.speak is False and d.stop_critical is False


def test_speech_decision_safety_overrides_and_is_stop_critical():
    d = decide_engineer_speech(EngineerMessageIntent.SAFETY_CRITICAL, workload=DriverWorkloadState.HIGH)
    assert d.speak is True and d.stop_critical is True


def test_critical_only_state_suppresses_routine_but_allows_safety():
    crit = resolve_audio_engineer_state(vr_mode=VrRuntimeMode.AUDIO_FIRST, voice_enabled=True,
                                        gate_allows=True, tts_available=True, critical_only=True)
    routine = decide_engineer_speech(EngineerMessageIntent.LAP_STINT_STATUS,
                                     workload=DriverWorkloadState.LOW, audio=crit)
    assert routine.speak is False
    safety = decide_engineer_speech(EngineerMessageIntent.SAFETY_CRITICAL,
                                    workload=DriverWorkloadState.LOW, audio=crit)
    assert safety.speak is True


def test_voice_disabled_state_blocks_delivery_decision():
    off = resolve_audio_engineer_state(vr_mode=VrRuntimeMode.AUDIO_FIRST, voice_enabled=False)
    d = decide_engineer_speech(EngineerMessageIntent.SAFETY_CRITICAL, workload=DriverWorkloadState.LOW,
                               audio=off)
    assert d.speak is False


# --- determinism --- #
def test_decisions_are_deterministic():
    a = decide_engineer_speech(EngineerMessageIntent.STRATEGY_CHANGE, workload=DriverWorkloadState.HIGH)
    b = decide_engineer_speech(EngineerMessageIntent.STRATEGY_CHANGE, workload=DriverWorkloadState.HIGH)
    assert a.fingerprint == b.fingerprint
    w1 = assess_driver_workload({"segment": "turn_1_apex"})
    w2 = assess_driver_workload({"segment": "turn_1_apex"})
    assert w1.fingerprint == w2.fingerprint


def test_state_fingerprint_excludes_volatile_but_reflects_semantics():
    s1 = resolve_audio_engineer_state(vr_mode=VrRuntimeMode.AUDIO_FIRST, voice_enabled=True,
                                      gate_allows=True, tts_available=True, recognition_available=True)
    s2 = resolve_audio_engineer_state(vr_mode=VrRuntimeMode.AUDIO_FIRST, voice_enabled=True,
                                      gate_allows=True, tts_available=True, recognition_available=True)
    assert s1.fingerprint == s2.fingerprint
    disabled = resolve_audio_engineer_state(vr_mode=VrRuntimeMode.AUDIO_FIRST, voice_enabled=False)
    assert disabled.fingerprint != s1.fingerprint
