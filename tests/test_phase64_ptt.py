"""Phase 64 — push-to-talk: binding, grammar, command classes, reports, feedback, read-back, ports."""
from __future__ import annotations

from strategy.push_to_talk import (
    PttInputKind, PttActivationMode, PushToTalkBinding, PttOperationalReadiness, assess_ptt_readiness,
    DriverCommandClass, DriverReportLabel, DriverUtterance, recognize_command,
    ReadbackResponse, decide_readback, apply_readback_response, build_feedback_draft,
    label_driver_report_against_telemetry,
)
from voice.ptt_input_port import DisabledPttInputPort, FakePttInputPort
from voice.speech_recognition_port import (
    DisabledSpeechRecognitionPort, FakeSpeechRecognitionPort, RecognitionKind,
)


# --- binding + readiness --- #
def test_binding_default_is_unbound_and_not_listening():
    b = PushToTalkBinding()
    assert b.is_bound is False
    assert assess_ptt_readiness(b, recogniser_available=True) == PttOperationalReadiness.UNBOUND


def test_binding_roundtrips_config_and_is_hardware_neutral():
    b = PushToTalkBinding(kind=PttInputKind.WHEEL_BUTTON, input_code="js0_btn7",
                          activation=PttActivationMode.PRESS_AND_HOLD, label="Wheel left paddle")
    assert b.is_bound
    assert PushToTalkBinding.from_config(b.to_config()) == b
    # readiness needs both a binding and a recogniser
    assert assess_ptt_readiness(b, recogniser_available=False) == PttOperationalReadiness.NO_RECOGNISER
    assert assess_ptt_readiness(b, recogniser_available=True) == PttOperationalReadiness.READY


# --- command grammar: the four classes --- #
def test_safe_operational_executes_immediately():
    for phrase in ("acknowledge", "repeat", "mute", "status", "fuel status", "next pit window"):
        it = recognize_command(DriverUtterance(text=phrase, confidence=0.9, ptt_held=True))
        assert it.command_class == DriverCommandClass.SAFE_OPERATIONAL
        assert it.executes_immediately is True and it.requires_readback is False


def test_strategy_requests_are_requests_not_forced_changes():
    it = recognize_command(DriverUtterance(text="is the plan still viable", confidence=0.9))
    assert it.command_class == DriverCommandClass.STRATEGY_REQUEST
    assert it.executes_immediately is False and it.requires_readback is False


def test_driver_report_is_labelled_and_requires_readback():
    it = recognize_command(DriverUtterance(text="rain starting", confidence=0.9))
    assert it.command_class == DriverCommandClass.DRIVER_REPORT
    assert it.requires_readback is True
    assert it.driver_report_label in (DriverReportLabel.DRIVER_REPORTED.value,
                                      DriverReportLabel.UNVERIFIED.value)


def test_engineering_feedback_requires_readback_and_is_not_immediate():
    it = recognize_command(DriverUtterance(text="more understeer mid corner", confidence=0.9))
    assert it.command_class == DriverCommandClass.ENGINEERING_FEEDBACK
    assert it.requires_readback is True and it.executes_immediately is False


# --- ambiguity --- #
def test_low_confidence_is_ambiguous_and_triggers_nothing():
    it = recognize_command(DriverUtterance(text="rain starting", confidence=0.3))
    assert it.ambiguous is True
    assert it.command_class == DriverCommandClass.UNRECOGNISED
    assert it.executes_immediately is False and it.requires_readback is False


def test_ptt_not_held_is_ambiguous():
    it = recognize_command(DriverUtterance(text="acknowledge", confidence=0.99, ptt_held=False))
    assert it.ambiguous is True and it.command_class == DriverCommandClass.UNRECOGNISED


def test_unrecognised_phrase():
    it = recognize_command(DriverUtterance(text="tell me a joke", confidence=0.95))
    assert it.command_class == DriverCommandClass.UNRECOGNISED


# --- read-back + confirmation --- #
def test_readback_required_for_reports_and_feedback_only():
    rep = recognize_command(DriverUtterance(text="front damage", confidence=0.9))
    assert decide_readback(rep).required is True
    op = recognize_command(DriverUtterance(text="fuel status", confidence=0.9))
    assert decide_readback(op).required is False


def test_confirm_report_labels_confirmed_but_not_telemetry():
    rep = recognize_command(DriverUtterance(text="rain starting", confidence=0.9))
    conf = apply_readback_response(rep, ReadbackResponse.CONFIRM)
    assert conf.confirmed is True
    assert conf.driver_report_label == DriverReportLabel.CONFIRMED_BY_READBACK.value
    assert conf.enters_canonical is False


def test_confirm_feedback_creates_draft_not_canonical():
    fb = recognize_command(DriverUtterance(text="gearing too long", confidence=0.9))
    conf = apply_readback_response(fb, ReadbackResponse.CONFIRM)
    assert conf.creates_draft is True and conf.enters_canonical is False
    draft = build_feedback_draft(fb)
    assert draft is not None and draft.confirmed is False


def test_cancel_response_records_nothing():
    fb = recognize_command(DriverUtterance(text="rear is loose", confidence=0.9))
    conf = apply_readback_response(fb, ReadbackResponse.CANCEL)
    assert conf.confirmed is False and conf.creates_draft is False


# --- driver report vs telemetry labelling --- #
def test_report_corroboration_requires_available_and_agreeing_telemetry():
    rep = recognize_command(DriverUtterance(text="car damaged", confidence=0.9))
    assert label_driver_report_against_telemetry(rep, telemetry_available=False,
                                                 telemetry_agrees=None) == \
        DriverReportLabel.UNAVAILABLE_FOR_VERIFICATION.value
    assert label_driver_report_against_telemetry(rep, telemetry_available=True,
                                                 telemetry_agrees=True) == \
        DriverReportLabel.CORROBORATED_BY_TELEMETRY.value
    assert label_driver_report_against_telemetry(rep, telemetry_available=True,
                                                 telemetry_agrees=False) == \
        DriverReportLabel.CONFLICTING_WITH_TELEMETRY.value


# --- ports --- #
def test_disabled_ports_are_the_default_and_inert():
    assert DisabledPttInputPort().is_available() is False
    assert DisabledPttInputPort().is_pressed() is False
    assert DisabledSpeechRecognitionPort().is_available() is False
    assert DisabledSpeechRecognitionPort().recognize() is None
    assert DisabledSpeechRecognitionPort().recognition_kind == RecognitionKind.NONE


def test_fake_ptt_input_press_release():
    p = FakePttInputPort()
    assert p.is_pressed() is False
    p.press()
    assert p.is_pressed() is True and p.press_events == 1
    p.release()
    assert p.is_pressed() is False and p.release_events == 1


def test_fake_recogniser_scripted_and_failure():
    r = FakeSpeechRecognitionPort([("acknowledge", 0.9), (None, 0.0)])
    first = r.recognize()
    assert first is not None and first.text == "acknowledge"
    assert r.recognize() is None  # scripted failure
    assert r.recognition_kind == RecognitionKind.COMMAND_GRAMMAR


# --- determinism --- #
def test_command_intent_fingerprint_excludes_raw_transcript():
    a = recognize_command(DriverUtterance(text="rain starting", confidence=0.9))
    b = recognize_command(DriverUtterance(text="it's starting to rain", confidence=0.9))
    # different transcripts, same recognised action -> same intent fingerprint
    assert a.action == b.action == "rain_starting"
    assert a.fingerprint == b.fingerprint
