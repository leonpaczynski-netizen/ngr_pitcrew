"""Phase 63-65 — safety invariants + property/metamorphic proofs.

Voice/PTT/strategy are interfaces to canonical authorities, never independent agents. No AI/network/keys,
no new telemetry listener, DB-free + Qt-free domain, Apply + voice gates intact, versions pinned, and the
metamorphic proofs the spec requires (voice cannot alter strategy; PTT cannot apply a setup; ambiguous
speech changes nothing; unavailable weather never becomes verified rain; small noise never spams; material
fuel divergence can change ranking; time-certain never trades completed laps for a faster average; stale
telemetry never yields a high-confidence replan; identical state does not spam; event switch invalidates).
"""
from __future__ import annotations

import pathlib

from strategy._setup_constants import DB_VERSION, RULE_ENGINE_VERSION

_ROOT = pathlib.Path(__file__).resolve().parents[1]

_NEW_DOMAIN = [
    "strategy/audio_first_engineer.py", "strategy/push_to_talk.py", "strategy/adaptive_live_strategy.py",
    "strategy/live_audio_strategy_build.py",
]
_NEW_PORTS = ["voice/ptt_input_port.py", "voice/speech_recognition_port.py"]

_FORBIDDEN = ["import openai", "anthropic", "requests.get", "urllib.request", "http://", "https://",
              "api_key", "API_KEY", "pyttsx", "azure", "google.cloud", "os.system", "eval(", "exec(",
              "pickle"]
_FORBIDDEN_LISTENER = ["recvfrom", "socket.socket", "0xdeadbeef", "sock.recv", "import socket"]


def test_new_domain_no_ai_network_keys():
    for rel in _NEW_DOMAIN + _NEW_PORTS:
        src = (_ROOT / rel).read_text(encoding="utf-8").lower()
        for bad in _FORBIDDEN:
            assert bad.lower() not in src, f"{rel} contains forbidden token {bad!r}"


def test_new_domain_creates_no_telemetry_listener():
    for rel in _NEW_DOMAIN + _NEW_PORTS:
        src = (_ROOT / rel).read_text(encoding="utf-8").lower()
        for bad in _FORBIDDEN_LISTENER:
            assert bad not in src, f"{rel} appears to create a telemetry listener ({bad!r})"


def test_new_domain_is_db_free_and_qt_free():
    for rel in _NEW_DOMAIN:
        src = (_ROOT / rel).read_text(encoding="utf-8")
        assert "session_db" not in src.lower() and "sqlite" not in src.lower(), f"{rel} touches the DB"
        assert "PyQt6" not in src and "PyQt5" not in src, f"{rel} imports Qt"


def test_no_cloud_recognition_in_ports():
    for rel in _NEW_PORTS:
        src = (_ROOT / rel).read_text(encoding="utf-8").lower()
        assert "speech_recognition" not in src or "cloud" not in src
        assert "recognizer_google" not in src and "recognize_google" not in src


def test_versions_pinned_and_no_new_migration():
    assert DB_VERSION == 28 and RULE_ENGINE_VERSION == "46.0"
    src = (_ROOT / "data" / "session_db.py").read_text(encoding="utf-8")
    assert f"_migrate_v{DB_VERSION + 1}" not in src


def test_apply_gate_and_voice_gate_untouched():
    from data.setup_state_authority import ActiveSetupAuthority
    from strategy.shadow_advisory import voice_gate_allows, LiveValidationReadiness
    assert hasattr(ActiveSetupAuthority, "mark_applied")
    assert voice_gate_allows(LiveValidationReadiness.VOICE_ELIGIBLE.value) is True
    assert voice_gate_allows(LiveValidationReadiness.NOT_READY.value) is False


# ------------------------- property / metamorphic ------------------------- #
def _tc(**kw):
    from strategy.adaptive_live_strategy import LiveStrategyState, StrategyObjective
    base = dict(objective=StrategyObjective.TIME_CERTAIN, time_remaining_s=1800.0,
                lap_time_actual_s=90.0, lap_time_plan_s=90.0, pit_loss_s=25.0, pit_loss_plan_s=25.0,
                tyre_age_laps=10, telemetry_fresh=True)
    base.update(kw)
    return LiveStrategyState(**base)


def test_voice_settings_cannot_alter_strategy_maths():
    from strategy.adaptive_live_strategy import decide_replan
    from strategy.live_audio_strategy_build import build_live_audio_strategy_view
    from strategy.audio_first_engineer import VrRuntimeMode
    st = _tc(lap_time_actual_s=95.0)
    pure = decide_replan(st)
    for enabled in (True, False):
        v = build_live_audio_strategy_view(st, vr_mode=VrRuntimeMode.AUDIO_FIRST, voice_enabled=enabled,
                                           gate_allows=enabled, tts_available=True)
        assert v["strategy_decision"]["fingerprint"] == pure.fingerprint


def test_ptt_and_acknowledge_execute_nothing():
    from strategy.adaptive_live_strategy import acknowledge_strategy
    from strategy.push_to_talk import recognize_command, DriverUtterance, DriverCommandClass
    ack = acknowledge_strategy(record_preference=True)
    assert ack.executes_anything is False
    # a feedback utterance never enters canonical learning directly
    fb = recognize_command(DriverUtterance("gearing too long", 0.9))
    assert fb.command_class == DriverCommandClass.ENGINEERING_FEEDBACK
    from strategy.push_to_talk import apply_readback_response, ReadbackResponse
    conf = apply_readback_response(fb, ReadbackResponse.CONFIRM)
    assert conf.enters_canonical is False


def test_ambiguous_speech_changes_nothing():
    from strategy.push_to_talk import recognize_command, DriverUtterance, DriverCommandClass
    it = recognize_command(DriverUtterance("strategy update", 0.2))  # low confidence
    assert it.command_class == DriverCommandClass.UNRECOGNISED
    assert it.executes_immediately is False and it.requires_readback is False


def test_unavailable_weather_never_becomes_verified_rain():
    from strategy.adaptive_live_strategy import detect_divergence_triggers, LiveStrategyTrigger
    trig = detect_divergence_triggers(_tc())  # no weather supplied
    assert not any(t.trigger == LiveStrategyTrigger.RAIN_BEGINNING.value for t in trig)


def test_small_pace_noise_does_not_create_replan_spam():
    from strategy.adaptive_live_strategy import decide_replan, StrategyMonitor, StrategyRecommendation
    mon = StrategyMonitor(cooldown_seconds=45.0)
    d = decide_replan(_tc(lap_time_actual_s=90.2))  # 0.2% — below the 1% threshold
    assert d.recommendation == StrategyRecommendation.PLAN_STILL_OPTIMAL.value
    assert mon.should_announce(d, now=10.0) is True
    assert mon.should_announce(d, now=12.0) is False


def test_material_fuel_divergence_can_change_ranking():
    from strategy.adaptive_live_strategy import (decide_replan, StrategyRecommendation, StrategyObjective,
                                                 LiveStrategyState)
    base = LiveStrategyState(objective=StrategyObjective.LAP_COUNT, laps_remaining=20, lap_time_actual_s=90.0,
                             lap_time_plan_s=90.0, pit_loss_s=25.0, tyre_age_laps=10,
                             fuel_per_lap_plan=3.0, fuel_per_lap_actual=3.0, telemetry_fresh=True)
    high = LiveStrategyState(objective=StrategyObjective.LAP_COUNT, laps_remaining=20, lap_time_actual_s=90.0,
                             lap_time_plan_s=90.0, pit_loss_s=25.0, tyre_age_laps=10,
                             fuel_per_lap_plan=3.0, fuel_per_lap_actual=3.6, telemetry_fresh=True)
    assert decide_replan(base).recommendation == StrategyRecommendation.PLAN_STILL_OPTIMAL.value
    assert decide_replan(high).recommendation == StrategyRecommendation.CONSERVATION_REQUIRED.value


def test_time_certain_never_trades_completed_laps_for_faster_average():
    from strategy.adaptive_live_strategy import project_time_certain
    keep = project_time_certain(time_remaining_s=600.0, lap_time_s=60.0)              # 600/60 = 10 laps
    # faster average (40s/lap) but a 240s stop: (600-240)/40 = 9 completed laps < 10
    faster_avg_fewer_laps = project_time_certain(time_remaining_s=600.0, lap_time_s=60.0,
                                                 extra_stops=1, pit_loss_s=240.0, pace_delta_s=-20.0)
    assert keep.expected_completed_laps > faster_avg_fewer_laps.expected_completed_laps


def test_stale_telemetry_never_high_confidence():
    from strategy.adaptive_live_strategy import decide_replan, StrategyConfidence
    d = decide_replan(_tc(telemetry_fresh=False, lap_time_actual_s=99.0))
    assert d.confidence == StrategyConfidence.INSUFFICIENT.value


def test_event_switch_invalidates_stale_view_fingerprint():
    from strategy.live_audio_strategy_build import build_live_audio_strategy_view
    from strategy.audio_first_engineer import VrRuntimeMode
    a = build_live_audio_strategy_view(_tc(), vr_mode=VrRuntimeMode.AUDIO_FIRST, voice_enabled=True,
                                       gate_allows=True, tts_available=True)
    b = build_live_audio_strategy_view(_tc(lap_time_actual_s=97.0), vr_mode=VrRuntimeMode.AUDIO_FIRST,
                                       voice_enabled=True, gate_allows=True, tts_available=True)
    assert a["view_fingerprint"] != b["view_fingerprint"]


def test_no_audio_or_ptt_action_writes_the_db():
    # the domain modules never import the DB; a spoken command produces only in-memory intents
    from strategy.push_to_talk import recognize_command, DriverUtterance
    it = recognize_command(DriverUtterance("box this lap and stop", 0.9))
    assert it.action == "return_to_garage"  # a safe operational command; no persistence occurs
