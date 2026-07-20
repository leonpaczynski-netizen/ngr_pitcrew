"""Phase 67/68 — PTT runtime lifecycle (fakes), UI construction, certification VM, dashboard activation."""
from __future__ import annotations

import os

import pytest

from voice.ptt_input_port import FakePttInputPort
from voice.speech_recognition_port import FakeSpeechRecognitionPort
from voice.ptt_runtime_controller import PttRuntimeController
from strategy.voice_delivery import VoiceQueue
from strategy.push_to_talk import PushToTalkState


# --- PTT runtime lifecycle (deterministic via fakes) --- #
def _controller(scripted):
    inp = FakePttInputPort()
    recog = FakeSpeechRecognitionPort(scripted)
    return PttRuntimeController(inp, recog), inp, recog


def test_ptt_press_hold_release_recognises_command():
    ctrl, inp, recog = _controller([("status", 0.9)])
    inp.press()
    r1 = ctrl.poll(nav_key=("A", "1"), current_nav_key=("A", "1"))
    assert r1.state == PushToTalkState.LISTENING.value and r1.coordination == "pause_routine"
    inp.release()
    r2 = ctrl.poll(nav_key=("A", "1"), current_nav_key=("A", "1"))
    assert r2.state == PushToTalkState.RECOGNISED.value
    assert r2.intent["action"] == "status" and r2.intent["executes_immediately"] is True


def test_ptt_report_requires_readback():
    ctrl, inp, recog = _controller([("rain starting", 0.9)])
    inp.press(); ctrl.poll(nav_key=("A", "1"), current_nav_key=("A", "1"))
    inp.release()
    r = ctrl.poll(nav_key=("A", "1"), current_nav_key=("A", "1"))
    assert r.state == PushToTalkState.AWAITING_CONFIRMATION.value
    assert r.readback is not None and r.readback["required"] is True


def test_ptt_ambiguous_recognition_triggers_nothing():
    ctrl, inp, recog = _controller([("rain starting", 0.2)])  # low confidence
    inp.press(); ctrl.poll(nav_key=("A", "1"), current_nav_key=("A", "1"))
    inp.release()
    r = ctrl.poll(nav_key=("A", "1"), current_nav_key=("A", "1"))
    assert r.state == PushToTalkState.AMBIGUOUS.value


def test_ptt_stale_recognition_rejected_on_event_switch():
    ctrl, inp, recog = _controller([("status", 0.9)])
    inp.press(); ctrl.poll(nav_key=("A", "1"), current_nav_key=("A", "1"))
    inp.release()
    r = ctrl.poll(nav_key=("A", "1"), current_nav_key=("B", "1"))  # event switched
    assert r.stale_rejected is True and r.state == PushToTalkState.CANCELLED.value


def test_ptt_no_recognition_times_out():
    ctrl, inp, recog = _controller([])  # nothing scripted
    inp.press(); ctrl.poll(nav_key=("A", "1"), current_nav_key=("A", "1"))
    inp.release()
    r = ctrl.poll(nav_key=("A", "1"), current_nav_key=("A", "1"))
    assert r.state == PushToTalkState.TIMED_OUT.value


def test_ptt_urgent_message_preserved_on_press():
    ctrl, inp, recog = _controller([("status", 0.9)])
    inp.press()
    r = ctrl.poll(nav_key=("A", "1"), current_nav_key=("A", "1"), active_message_priority=1)  # safety
    assert r.coordination == "preserve_urgent"


def test_ptt_unavailable_when_no_device():
    ctrl = PttRuntimeController(FakePttInputPort(available=False), FakeSpeechRecognitionPort([]))
    r = ctrl.poll(nav_key=("A", "1"), current_nav_key=("A", "1"))
    assert r.state == PushToTalkState.UNAVAILABLE.value


def test_repeated_ptt_presses_are_safe():
    ctrl, inp, recog = _controller([("status", 0.9), ("repeat", 0.9)])
    for _ in range(3):
        inp.press(); ctrl.poll(nav_key=("A", "1"), current_nav_key=("A", "1"))
        inp.release(); ctrl.poll(nav_key=("A", "1"), current_nav_key=("A", "1"))
    # never raised; controller still responsive
    assert ctrl.available is True


# --- certification VM + PSVR2 readiness --- #
def test_certification_vm_overall_and_areas_separate():
    from strategy.event_programme_certification import live_vr_certification
    from ui import live_certification_vm as vm
    payload = live_vr_certification().as_payload()
    oc = vm.overall_card(payload)
    rows = vm.area_rows(payload)
    assert oc["status_tag"] and len(rows) == 31
    # NONE areas render neutral with a note
    none_rows = [r for r in rows if r["evidence_tag"] == "NONE"]
    assert none_rows and all(r["note"] for r in none_rows)


def test_psvr2_readiness_requires_tts_ptt_voice():
    from ui.live_certification_vm import psvr2_readiness
    not_ready = psvr2_readiness(tts_available=True, ptt_bound=False, voice_enabled=True)
    assert not_ready["ready"] is False
    ready = psvr2_readiness(tts_available=True, ptt_bound=True, voice_enabled=True)
    assert ready["ready"] is True
    # mic is optional
    assert ready["checks"][-1]["required"] is False


# --- offscreen Qt construction --- #
@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt6 not available")
    app = QApplication.instance() or QApplication([])
    yield app


def test_ptt_binding_panel_constructs(qapp):
    from ui.ptt_binding_panel import PttBindingPanel
    from strategy.event_programme_certification import live_vr_certification
    from ui.live_certification_vm import psvr2_readiness
    p = PttBindingPanel()
    p.update_state(None)
    p.update_state({"binding_label": "Keyboard F13", "binding_conflict": "",
                    "psvr2": psvr2_readiness(tts_available=True, ptt_bound=True, voice_enabled=True),
                    "certification": live_vr_certification().as_payload()})
    assert p._cards  # readiness + certification cards rendered


def test_dashboard_runtime_activation_wired():
    import ui.dashboard as dash
    src = open(dash.__file__, encoding="utf-8").read()
    assert "build_canonical_live_race_state" in src
    assert "_refresh_audio_engineer" in src
    # activation reads the real tracker
    assert "getattr(self, \"_tracker\", None)" in src
