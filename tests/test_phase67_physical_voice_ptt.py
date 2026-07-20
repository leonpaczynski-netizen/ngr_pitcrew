"""Phase 67 — concrete adapters + PTT/TTS coordination + binding workflow (offline; no physical hardware)."""
from __future__ import annotations

from voice.keyboard_ptt import KeyboardPttInputPort
from voice.joystick_ptt import JoystickPttInputPort
from voice.windows_sapi_recognition import WindowsSapiRecognitionPort
from voice.advisory_voice_port import WindowsOfflineVoicePort, make_voice_port
from voice.ptt_input_port import PushToTalkInputPort
from voice.speech_recognition_port import SpeechRecognitionPort, RecognitionKind
from strategy.push_to_talk import PushToTalkBinding, PttInputKind
from strategy.ptt_tts_coordination import (
    decide_ptt_tts_action, PttTtsAction, is_stale_recognition, validate_binding, BindingConflict,
    default_binding, apply_binding, clear_binding,
)


# --- concrete adapters implement the ports + are safe/inert without hardware --- #
def test_keyboard_ptt_implements_port_and_is_inert_without_key():
    p = KeyboardPttInputPort()
    assert isinstance(p, PushToTalkInputPort)
    assert p.is_available() is False   # no vk bound
    assert p.is_pressed() is False
    p.shutdown()


def test_keyboard_ptt_with_vk_does_not_raise():
    p = KeyboardPttInputPort(vk_code=0x7C)   # F13
    # availability depends on the platform; the call must never raise and pressed is deterministic-safe
    _ = p.is_available()
    assert p.is_pressed() in (True, False)


def test_joystick_ptt_implements_port_and_is_safe():
    p = JoystickPttInputPort(joy_id=0, button_index=7)
    assert isinstance(p, PushToTalkInputPort)
    assert p.is_pressed() in (True, False)   # never raises even with no joystick
    p.shutdown()


def test_sapi_recognition_implements_port_disabled_by_default():
    r = WindowsSapiRecognitionPort()
    assert isinstance(r, SpeechRecognitionPort)
    assert r.recognition_kind == RecognitionKind.COMMAND_GRAMMAR
    assert r.is_available() is False        # disabled until enable() succeeds
    assert r.recognize() is None
    # push-recognition sink is inert while disabled (no crash)
    r.push_recognition("acknowledge", 0.9)
    assert r.recognize() is None
    r.shutdown()


def test_sapi_recognition_grammar_phrases_from_command_grammar():
    r = WindowsSapiRecognitionPort()
    from voice.windows_sapi_recognition import _default_phrases
    phrases = _default_phrases()
    assert "acknowledge" in phrases and "strategy update" in phrases and "rain starting" in phrases


def test_sapi_tts_port_disabled_by_default():
    v = WindowsOfflineVoicePort()
    assert v.is_available() is False
    assert v.speak("test") is False   # disabled until enable()
    assert make_voice_port("windows").name == "windows_sapi5_offline"


# --- PTT/TTS coordination --- #
def test_ptt_pauses_routine_but_preserves_urgent():
    routine = decide_ptt_tts_action(ptt_active=True, active_message_priority=8)  # coaching
    assert routine.action == PttTtsAction.PAUSE_ROUTINE.value
    urgent = decide_ptt_tts_action(ptt_active=True, active_message_priority=1)   # safety
    assert urgent.action == PttTtsAction.PRESERVE_URGENT.value


def test_ptt_release_resumes():
    d = decide_ptt_tts_action(ptt_active=False, just_released=True)
    assert d.action == PttTtsAction.RESUME.value


def test_stale_recognition_rejected_on_event_switch():
    assert is_stale_recognition(("cyc-A", "act-1"), ("cyc-B", "act-1")) is True
    assert is_stale_recognition(("cyc-A", "act-1"), ("cyc-A", "act-1")) is False


# --- binding workflow --- #
def test_reserved_key_rejected():
    b = PushToTalkBinding(kind=PttInputKind.KEYBOARD, input_code="0x1B")  # Esc
    v = validate_binding(b)
    assert v.ok is False and v.conflict == BindingConflict.RESERVED_KEY.value


def test_duplicate_binding_detected():
    existing = PushToTalkBinding(kind=PttInputKind.KEYBOARD, input_code="0x7C")
    dup = PushToTalkBinding(kind=PttInputKind.KEYBOARD, input_code="0x7C")
    v = validate_binding(dup, other_bindings=[existing])
    assert v.ok is False and v.conflict == BindingConflict.ALREADY_BOUND.value


def test_valid_binding_written_only_when_ok():
    cfg = {}
    good = PushToTalkBinding(kind=PttInputKind.KEYBOARD, input_code="0x7C", label="F13")
    v = apply_binding(cfg, good)
    assert v.ok is True and cfg.get("ptt_binding", {}).get("input_code") == "0x7C"
    # a reserved key is NOT written
    cfg2 = {}
    apply_binding(cfg2, PushToTalkBinding(kind=PttInputKind.KEYBOARD, input_code="0x0D"))  # Enter
    assert "ptt_binding" not in cfg2


def test_default_binding_and_clear():
    d = default_binding()
    assert d.is_bound and d.kind == PttInputKind.KEYBOARD
    cfg = {"ptt_binding": d.to_config()}
    clear_binding(cfg)
    assert "ptt_binding" not in cfg
