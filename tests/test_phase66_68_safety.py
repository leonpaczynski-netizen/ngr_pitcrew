"""Phase 66-68 — safety invariants + property/metamorphic proofs for live activation + physical VR."""
from __future__ import annotations

import pathlib

from strategy._setup_constants import DB_VERSION, RULE_ENGINE_VERSION

_ROOT = pathlib.Path(__file__).resolve().parents[1]

_NEW_DOMAIN = [
    "strategy/canonical_live_race_state.py", "strategy/ptt_tts_coordination.py",
]
_NEW_ADAPTERS = [
    "voice/keyboard_ptt.py", "voice/joystick_ptt.py", "voice/windows_sapi_recognition.py",
]

_FORBIDDEN = ["import openai", "anthropic", "requests.get", "urllib.request", "http://", "https://",
              "api_key", "API_KEY", "azure", "google.cloud", "os.system", "eval(", "exec(", "pickle"]
_FORBIDDEN_LISTENER = ["recvfrom", "socket.socket", "0xdeadbeef", "sock.recv", "import socket"]


def test_new_domain_no_ai_network_keys():
    for rel in _NEW_DOMAIN + _NEW_ADAPTERS:
        src = (_ROOT / rel).read_text(encoding="utf-8").lower()
        for bad in _FORBIDDEN:
            assert bad.lower() not in src, f"{rel} contains forbidden token {bad!r}"


def test_new_domain_creates_no_telemetry_listener():
    for rel in _NEW_DOMAIN + _NEW_ADAPTERS:
        src = (_ROOT / rel).read_text(encoding="utf-8").lower()
        for bad in _FORBIDDEN_LISTENER:
            assert bad not in src, f"{rel} appears to create a telemetry listener ({bad!r})"


def test_domain_is_db_free_and_qt_free():
    for rel in _NEW_DOMAIN:
        src = (_ROOT / rel).read_text(encoding="utf-8")
        assert "session_db" not in src.lower() and "sqlite" not in src.lower(), f"{rel} touches the DB"
        assert "PyQt6" not in src and "PyQt5" not in src, f"{rel} imports Qt"


def test_recognition_adapter_is_offline_no_cloud():
    src = (_ROOT / "voice/windows_sapi_recognition.py").read_text(encoding="utf-8").lower()
    # no cloud-recognition API calls (the word "cloud" may appear in prose disclaiming it)
    for tok in ("recognize_google", "recognizer_google", "azure", "google.cloud", "aws", "watson",
                "boto3", "cognitiveservices"):
        assert tok not in src, f"cloud-recognition token {tok!r} present"
    # offline SAPI only
    assert "spinprocrecognizer" in src


def test_versions_pinned_and_no_new_migration():
    assert DB_VERSION == 28 and RULE_ENGINE_VERSION == "46.0"
    src = (_ROOT / "data" / "session_db.py").read_text(encoding="utf-8")
    assert f"_migrate_v{DB_VERSION + 1}" not in src


def test_apply_and_voice_gates_untouched():
    from data.setup_state_authority import ActiveSetupAuthority
    from strategy.shadow_advisory import voice_gate_allows, LiveValidationReadiness
    assert hasattr(ActiveSetupAuthority, "mark_applied")
    assert voice_gate_allows(LiveValidationReadiness.VOICE_ELIGIBLE.value) is True
    assert voice_gate_allows(LiveValidationReadiness.NOT_READY.value) is False


# ------------------------- property / metamorphic ------------------------- #
class _Tracker:
    def __init__(self, **kw):
        self._d = {"race_type": "timed", "laps_recorded": 5, "laps_in_race": 0,
                   "timed_duration_minutes": 30.0, "last_fuel": 60.0, "avg_fuel_per_lap": 3.0,
                   "best_lap_ms": 90000, "pit_stops_completed": 0, "laps_since_pit": 5,
                   "tyre_age_laps": 5, "in_pit": False, "pit_state_confidence": "high",
                   "last_position": 4, "tyre_compound": "RM", "car_name": "RSR", "track": "Fuji",
                   "layout_id": "full"}
        self._d.update(kw)

    def __getattr__(self, name):
        d = object.__getattribute__(self, "_d")
        if name in d:
            return d[name]
        raise AttributeError(name)


def _canon(**kw):
    from strategy.canonical_live_race_state import build_canonical_live_race_state
    base = dict(elapsed_s=600.0, recent_clean_lap_times_s=[90.0, 90.0, 90.0, 90.0])
    base.update(kw)
    return build_canonical_live_race_state(_Tracker(**base.pop("tracker_kw", {})), **base)


def test_identical_telemetry_gives_identical_strategy_decision():
    from strategy.adaptive_live_strategy import decide_replan
    a = decide_replan(_canon().to_live_strategy_state())
    b = decide_replan(_canon().to_live_strategy_state())
    assert a.fingerprint == b.fingerprint


def test_live_packet_processing_cannot_write_db():
    # the canonical adapter never imports the DB — a build touches no DB
    from strategy.canonical_live_race_state import build_canonical_live_race_state
    s = build_canonical_live_race_state(_Tracker())
    assert s.fingerprint  # built purely in memory


def test_audio_device_change_cannot_alter_strategy():
    from strategy.adaptive_live_strategy import decide_replan
    from strategy.live_audio_strategy_build import build_live_audio_strategy_view
    from strategy.audio_first_engineer import VrRuntimeMode
    st = _canon().to_live_strategy_state()
    pure = decide_replan(st)
    for enabled in (True, False):
        v = build_live_audio_strategy_view(st, vr_mode=VrRuntimeMode.AUDIO_FIRST, voice_enabled=enabled,
                                           gate_allows=enabled, tts_available=True)
        assert v["strategy_decision"]["fingerprint"] == pure.fingerprint


def test_ptt_cannot_apply_setup_and_ack_cannot_execute_pit():
    from strategy.adaptive_live_strategy import acknowledge_strategy
    from strategy.push_to_talk import recognize_command, DriverUtterance, apply_readback_response, ReadbackResponse
    assert acknowledge_strategy(record_preference=True).executes_anything is False
    fb = recognize_command(DriverUtterance("gearing too long", 0.9))
    assert apply_readback_response(fb, ReadbackResponse.CONFIRM).enters_canonical is False


def test_uncertain_recognition_cannot_update_race_state():
    from strategy.push_to_talk import recognize_command, DriverUtterance, DriverCommandClass
    it = recognize_command(DriverUtterance("rain starting", 0.2))  # low confidence
    assert it.command_class == DriverCommandClass.UNRECOGNISED
    # unrecognised report never becomes a driver_reports entry
    assert it.driver_report_label is None


def test_telemetry_loss_cannot_produce_high_confidence():
    from strategy.adaptive_live_strategy import decide_replan, StrategyConfidence
    s = _canon(telemetry_fresh=False)
    d = decide_replan(s.to_live_strategy_state())
    assert d.confidence == StrategyConfidence.INSUFFICIENT.value


def test_time_certain_never_prefers_fewer_completed_laps():
    from strategy.adaptive_live_strategy import project_time_certain
    keep = project_time_certain(time_remaining_s=600.0, lap_time_s=60.0)          # 10 laps
    fewer = project_time_certain(time_remaining_s=600.0, lap_time_s=60.0, extra_stops=1,
                                 pit_loss_s=240.0, pace_delta_s=-20.0)             # 9 laps
    assert keep.expected_completed_laps > fewer.expected_completed_laps


def test_confirmed_pit_not_counted_twice():
    from strategy.canonical_live_race_state import EvaluationCadence, StrategyEvaluationTrigger
    cad = EvaluationCadence()
    s_pre = _canon(tracker_kw={"pit_stops_completed": 0})
    cad.triggers(s_pre, now=1.0)  # prime last_pit_stops = 0
    s_pit = _canon(tracker_kw={"pit_stops_completed": 1, "in_pit": True})
    first = cad.triggers(s_pit, now=2.0)
    assert StrategyEvaluationTrigger.CONFIRMED_PIT_EVENT in first
    # same stop count again -> not re-counted
    second = cad.triggers(_canon(tracker_kw={"pit_stops_completed": 1, "in_pit": True}), now=3.0)
    assert StrategyEvaluationTrigger.CONFIRMED_PIT_EVENT not in second


def test_repeated_identical_conditions_do_not_spam():
    from strategy.adaptive_live_strategy import decide_replan, StrategyMonitor
    mon = StrategyMonitor(cooldown_seconds=45.0)
    d = decide_replan(_canon().to_live_strategy_state())
    assert mon.should_announce(d, now=10.0) is True
    assert mon.should_announce(d, now=12.0) is False


def test_event_switch_invalidates_stale_recognition():
    from strategy.ptt_tts_coordination import is_stale_recognition
    assert is_stale_recognition(("A", "1"), ("B", "1")) is True
    assert is_stale_recognition(("A", "1"), ("A", "1")) is False


def test_driver_reported_rain_never_verified_telemetry():
    s = _canon(driver_reports={"weather": "rain"})
    assert s.weather_source == "driver_reported"
    assert s.to_live_strategy_state().weather_source == "driver_reported"
