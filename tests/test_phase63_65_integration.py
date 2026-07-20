"""Phase 63/65 — production composition (build_live_audio_strategy_view) + the Qt-free VM."""
from __future__ import annotations

from strategy.audio_first_engineer import VrRuntimeMode
from strategy.adaptive_live_strategy import LiveStrategyState, StrategyObjective
from strategy.live_audio_strategy_build import build_live_audio_strategy_view
import ui.vr_audio_engineer_vm as vm


def _state(**kw):
    base = dict(objective=StrategyObjective.LAP_COUNT, laps_remaining=20, lap_time_actual_s=90.0,
                lap_time_plan_s=90.0, pit_loss_s=25.0, pit_loss_plan_s=25.0, tyre_age_laps=10,
                fuel_per_lap_plan=3.0, fuel_per_lap_actual=3.0, telemetry_fresh=True)
    base.update(kw)
    return LiveStrategyState(**base)


def test_build_is_db_free_and_stable():
    v = build_live_audio_strategy_view(_state(), vr_mode=VrRuntimeMode.AUDIO_FIRST, voice_enabled=True,
                                       gate_allows=True, tts_available=True, recognition_available=True,
                                       workload_context={"segment": "back_straight"})
    assert v["ok"] is True
    assert v["audio_state"]["state"] == "voice_ready"
    assert v["strategy_decision"]["recommendation"] == "PLAN_STILL_OPTIMAL"
    # deterministic
    v2 = build_live_audio_strategy_view(_state(), vr_mode=VrRuntimeMode.AUDIO_FIRST, voice_enabled=True,
                                        gate_allows=True, tts_available=True, recognition_available=True,
                                        workload_context={"segment": "back_straight"})
    assert v["view_fingerprint"] == v2["view_fingerprint"]


def test_strategy_message_may_speak_only_in_low_workload_or_urgent():
    # routine 'plan optimal' strategy update in HIGH workload → deferred (strategy is urgent-priority so
    # it overrides — verify the override path explicitly with a real strategy change).
    high = build_live_audio_strategy_view(
        _state(fuel_per_lap_actual=3.5), vr_mode=VrRuntimeMode.AUDIO_FIRST, voice_enabled=True,
        gate_allows=True, tts_available=True, workload_context={"braking": True})
    # STRATEGY_CHANGE is an urgent-window-override intent → may speak even while braking
    assert high["may_speak_now"] is True


def test_telemetry_stale_suppresses_routine_speech():
    v = build_live_audio_strategy_view(_state(telemetry_fresh=False), vr_mode=VrRuntimeMode.AUDIO_FIRST,
                                       voice_enabled=True, gate_allows=True, tts_available=True,
                                       workload_context={"segment": "straight"})
    assert v["audio_state"]["state"] == "telemetry_stale"
    # strategy change is stop-critical? no — telemetry_stale allows only critical; strategy is not critical
    assert v["may_speak_now"] is False


def test_voice_disabled_blocks_speech():
    v = build_live_audio_strategy_view(_state(fuel_per_lap_actual=3.5), vr_mode=VrRuntimeMode.AUDIO_FIRST,
                                       voice_enabled=False, workload_context={"segment": "straight"})
    assert v["may_speak_now"] is False


# --- VM --- #
def test_vm_status_line_and_card():
    v = build_live_audio_strategy_view(_state(fuel_per_lap_actual=3.5), vr_mode=VrRuntimeMode.AUDIO_FIRST,
                                       voice_enabled=True, gate_allows=True, tts_available=True,
                                       recognition_available=True, workload_context={"segment": "straight"})
    assert "ready" in vm.status_line(v).lower() or vm.status_tone(v) == "success"
    card = vm.strategy_card(v)
    assert card["status_tag"] and card["headline"]
    assert card["acknowledgeable"] is True  # a conservation replan is acknowledgeable


def test_vm_empty_state_is_safe():
    assert vm.is_empty({}) is True
    assert "not active" in vm.status_line({}).lower()
    assert vm.cards({}) == []


def test_vm_recovery_card_on_adapter_failure():
    v = build_live_audio_strategy_view(_state(), vr_mode=VrRuntimeMode.AUDIO_FIRST, voice_enabled=True,
                                       adapter_failed=True)
    rc = vm.recovery_card(v)
    assert rc and "visual" in " ".join(rc["lines"]).lower()


def test_vm_detailed_tables_not_in_driving_card():
    # the driving strategy card exposes a headline + confidence + next review, but NOT a candidate table
    v = build_live_audio_strategy_view(_state(fuel_per_lap_actual=3.5), vr_mode=VrRuntimeMode.AUDIO_FIRST,
                                       voice_enabled=True, gate_allows=True, tts_available=True,
                                       workload_context={"segment": "straight"})
    card = vm.strategy_card(v)
    assert "candidates" not in card and "detail_available" in card
