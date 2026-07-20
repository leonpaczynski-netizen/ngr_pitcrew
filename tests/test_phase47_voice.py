"""Phase 47 — opt-in offline voice: disabled default, exact message, queue, ack, failure fallback."""
from strategy.voice_delivery import (
    VoiceQueue, DisabledVoicePort, FakeVoicePort, VoiceDeliveryRequest,
)
from voice.voice_controller import VoiceController
from voice.advisory_voice_port import WindowsOfflineVoicePort, make_voice_port


def _prompt(key="coach:T2", prio=5, cls="informational", msg="T2 progressive throttle",
            ptype="coaching_objective", cooldown=30.0):
    return {"message": msg, "priority": prio, "prompt_class": cls, "suppression_key": key,
            "prompt_type": ptype, "cooldown_seconds": cooldown}


# ---- 26. voice disabled by default ---------------------------------------------------------- #
def test_disabled_by_default_speaks_nothing():
    vc = VoiceController(port=FakeVoicePort())
    assert vc.enabled is False
    vc.submit(_prompt())
    assert vc.tick(1.0, readiness="voice_eligible")["spoke"] is None


def test_disabled_port_never_speaks():
    d = DisabledVoicePort()
    assert d.is_available() is False and d.speak("x") is False


# ---- 27. local adapter abstraction ---------------------------------------------------------- #
def test_windows_port_import_safe_and_disabled():
    w = WindowsOfflineVoicePort()
    assert w.is_available() is False   # disabled until enable() (which needs Windows/SAPI5)
    assert make_voice_port("disabled").is_available() is False


# ---- 28. exact-message delivery ------------------------------------------------------------- #
def test_exact_message_delivered():
    port = FakeVoicePort()
    vc = VoiceController(port=port); vc.enable()
    vc.submit(_prompt(msg="Exact approved message"))
    vc.tick(1.0, readiness="voice_eligible")
    assert port.spoken == ["Exact approved message"]


def test_below_gate_no_speech():
    port = FakeVoicePort()
    vc = VoiceController(port=port); vc.enable()
    vc.submit(_prompt())
    vc.tick(1.0, readiness="shadow_ready")   # below voice-eligible gate
    assert port.spoken == []


# ---- 29/30. queue + stop-critical interruption ---------------------------------------------- #
def test_stop_critical_interrupts_routine():
    q = VoiceQueue()
    q.submit(_prompt())
    d1 = q.poll(0.0, voice_enabled=True)
    assert d1.action == "speak"
    q.submit(_prompt(key="run_invalidated", prio=1, cls="stop_critical", msg="Run invalid stop",
                     ptype="run_invalidated"))
    d2 = q.poll(1.0, voice_enabled=True)
    assert d2.action == "interrupt" and d2.request["suppression_key"] == "run_invalidated"


def test_routine_does_not_interrupt_routine():
    q = VoiceQueue()
    q.submit(_prompt(key="a")); q.poll(0.0, voice_enabled=True)
    q.submit(_prompt(key="b", prio=6))
    assert q.poll(1.0, voice_enabled=True).action == "hold"


# ---- 31/32/33. acknowledgement, repeat, mute ------------------------------------------------ #
def test_acknowledge_suppresses_repeat():
    q = VoiceQueue()
    q.submit(_prompt(key="k")); q.acknowledge("k")
    assert q.poll(0.0, voice_enabled=True).action == "hold"


def test_repeat_once_same_message_no_new_recommendation():
    port = FakeVoicePort()
    vc = VoiceController(port=port); vc.enable()
    vc.submit(_prompt(msg="Approved message"))
    vc.tick(1.0, readiness="voice_eligible"); vc.notify_finished_speaking()
    vc.repeat_once(_prompt(msg="Approved message", cooldown=0.0))
    vc.tick(2.0, readiness="voice_eligible")
    assert port.spoken == ["Approved message", "Approved message"]


def test_mute_type_and_coaching_lap():
    q = VoiceQueue()
    q.submit(_prompt(key="coach:T2")); q.mute_type("coach:T2")
    assert q.poll(0.0, voice_enabled=True).action == "hold"
    q2 = VoiceQueue(); q2.submit(_prompt(key="coach:T3")); q2.mute_coaching_for_lap(4)
    assert q2.poll(0.0, voice_enabled=True, current_lap=4).action == "hold"


# ---- 34. voice failure fallback ------------------------------------------------------------- #
def test_adapter_failure_disables_and_no_crash():
    vc = VoiceController(port=FakeVoicePort(fail=True)); vc.enable()
    vc.submit(_prompt())
    r = vc.tick(1.0, readiness="voice_eligible")
    assert r["health"] == "failed" and r["enabled"] is False and r["spoke"] is None


# ---- 35. session-end cleanup ---------------------------------------------------------------- #
def test_session_end_flushes_queue():
    vc = VoiceController(port=FakeVoicePort()); vc.enable()
    vc.submit(_prompt())
    vc.on_session_end()
    assert vc.tick(1.0, readiness="voice_eligible")["spoke"] is None


def test_context_change_flushes():
    q = VoiceQueue(); q.submit(_prompt())
    d = q.cancel_all("context changed")
    assert d.action == "cancelled" and q.poll(0.0, voice_enabled=True).action == "hold"


# ---- 36. no strategy commands --------------------------------------------------------------- #
def test_no_strategy_command_messages():
    # nothing in the voice path emits a strategy command; the message is whatever the gated advisory
    # already approved (never synthesised here). Verify the request carries the exact text unchanged.
    req = VoiceDeliveryRequest.from_prompt(_prompt(msg="T2 progressive throttle"))
    assert req.message == "T2 progressive throttle"
    banned = ("pit now", "change tyres", "fuel map", "save fuel", "push", "overtake",
              "change brake balance", "change setup")
    assert not any(b in req.message.lower() for b in banned)


# ---- test voice guarded during active run --------------------------------------------------- #
def test_test_voice_blocked_during_run():
    vc = VoiceController(port=FakeVoicePort()); vc.enable(); vc.set_run_active(True)
    assert vc.test_voice()["ok"] is False


# ---- property: voice settings do not change engineering fingerprints ------------------------ #
def test_voice_settings_not_in_engineering_fingerprint():
    from strategy.live_advisory import build_candidate_prompts
    from strategy.live_advisory_engine import evaluate_live_advisories
    snap = {"context_fingerprint": "cfp", "run_plan_fingerprint": "pfp", "run_active": True, "lap": 3,
            "clean_laps": 1, "telemetry_fresh": True, "plan_current": True, "session_active": True,
            "segment_type": "straight", "workload": "low", "approaching_corner": "T2"}
    plan = {"content_fingerprint": "pfp", "run_structure": {"minimum_clean_laps": 3, "warm_up_laps": 2}}
    coach = {"priorities": [{"corner": "T2", "technique_focus": "x", "confidence": "high"}]}
    a = evaluate_live_advisories(build_candidate_prompts(snap, plan, {"state": "run_active"}, coach),
                                 snap, now_monotonic=1.0, state={}).content_fingerprint
    # changing the voice controller config/rate/volume must not touch the engine decision fingerprint
    vc = VoiceController(port=FakeVoicePort()); vc.enable(); vc.set_config(rate=5, volume=20)
    b = evaluate_live_advisories(build_candidate_prompts(snap, plan, {"state": "run_active"}, coach),
                                 snap, now_monotonic=1.0, state={}).content_fingerprint
    assert a == b
