"""The button, the beep, and leaving a trace.

Both of the defects these cover were found the same way: the app went during a
practice session and there was nothing at all to read afterwards, and there was
no screen on which to set either of the two things the driver actually has to
set.
"""
from __future__ import annotations

import logging

import threading

import pytest

from pitcrew import diagnostics, settings
from pitcrew.controller import PitCrewController
from pitcrew.settings import RPM_FROM_GT7, RPM_MANUAL, Settings
from pitcrew.store.db import Store
from pitcrew.ui.event_screen import EventScreen
from pitcrew.ui.practice_screen import PracticeScreen
from pitcrew.ui.settings_screen import SettingsScreen

from .test_controller import raw

pytest.importorskip("PyQt6.QtWidgets")


@pytest.fixture(scope="session")
def qt_app():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture()
def wired(qt_app, store: Store):
    screen = SettingsScreen()
    controller = PitCrewController(store, EventScreen(), PracticeScreen(),
                                   settings_screen=screen)
    yield controller, screen, store
    controller.shutdown()


# ---------------------------------------------------------------- settings

def test_settings_round_trip_through_the_store(store):
    settings.save(store, Settings(ptt_key="f12", ptt_in_practice=True,
                                  beep_enabled=False,
                                  beep_rpm_source=RPM_MANUAL,
                                  beep_rpm=8640.0))
    loaded = settings.load(store)
    assert loaded.ptt_key == "f12"
    assert loaded.ptt_in_practice is True
    assert loaded.beep_enabled is False
    assert loaded.beep_rpm_source == RPM_MANUAL
    assert loaded.beep_rpm == 8640.0


def test_defaults_apply_when_nothing_has_been_set(store):
    loaded = settings.load(store)
    assert loaded.ptt_key == "f8"
    assert loaded.beep_rpm_source == RPM_FROM_GT7


def test_a_stored_value_that_no_longer_validates_is_discarded(store):
    """Better the default than a threshold that fires on every packet."""
    store.set_state(settings.PREFIX + "beep_rpm", "12")
    loaded = settings.load(store)
    assert loaded.beep_rpm == Settings().beep_rpm


def test_a_nonsense_threshold_is_refused_rather_than_clamped():
    with pytest.raises(ValueError, match="not a threshold"):
        Settings(beep_rpm=50.0).validate()
    with pytest.raises(ValueError, match="needs a button"):
        Settings(ptt_enabled=True, ptt_key="  ").validate()


# ------------------------------------------------------------- the beep

def test_a_manual_threshold_is_not_overwritten_by_the_game(wired):
    """A number the driver chose is usually a deliberate short-shift."""
    controller, screen, store = wired
    screen.load(Settings(beep_rpm_source=RPM_MANUAL, beep_rpm=8000.0))
    screen._on_save()

    controller.bridge.on_packet(raw(speed_ms=50.0, rpm_alert_min=9000))
    assert controller.bridge.shift_beep.rpm == 8000.0
    assert controller.bridge.shift_beep.enabled is True


def test_the_game_supplies_the_threshold_by_default(wired):
    controller, _screen, _store = wired
    controller.bridge.on_packet(raw(speed_ms=50.0, rpm_alert_min=8800))
    assert controller.bridge.shift_beep.rpm == 8800.0
    assert controller.bridge.shift_beep.enabled is True


def test_turning_the_beep_off_keeps_it_off_when_the_stream_arrives(wired):
    controller, screen, _store = wired
    screen.load(Settings(beep_enabled=False))
    screen._on_save()
    controller.bridge.on_packet(raw(speed_ms=50.0, rpm_alert_min=8800))
    assert controller.bridge.shift_beep.enabled is False


def test_the_beep_can_be_sounded_on_demand(wired):
    controller, screen, _store = wired
    played = []
    controller.bridge.shift_beep._tone = lambda: played.append(1)
    assert controller.test_beep() is True
    assert played == [1]
    assert "Beeped" in screen.beep_note.text()


def test_a_machine_with_no_tone_device_says_so_rather_than_claiming_a_beep(wired):
    controller, screen, _store = wired
    controller.bridge.shift_beep._tone = None
    assert controller.test_beep() is False
    assert "No beep" in screen.beep_note.text()


# -------------------------------------------------------------- the button

def test_changing_the_button_rebinds_the_hook(wired):
    controller, screen, _store = wired
    swapped = []
    controller.ptt.set_listener = lambda listener: swapped.append(listener)

    screen.load(Settings(ptt_key="f12"))
    screen._on_save()
    assert settings.load(controller.store).ptt_key == "f12"
    assert len(swapped) == 1


def test_saving_the_same_button_does_not_rebind(wired):
    controller, screen, _store = wired
    swapped = []
    controller.ptt.set_listener = lambda listener: swapped.append(listener)
    screen.load(controller.settings)
    screen._on_save()
    assert swapped == []


def test_the_screen_reports_what_actually_loaded_not_what_was_asked_for(wired):
    controller, screen, _store = wired
    screen.show_capabilities(speech="piper", hook=False)
    assert "NO keyboard hook" in screen.engine_note.text()
    screen.show_capabilities(speech="piper", hook=True)
    assert "piper" in screen.engine_note.text()


def test_a_manual_threshold_field_is_disabled_when_the_game_supplies_it(wired):
    _controller, screen, _store = wired
    screen.load(Settings(beep_rpm_source=RPM_FROM_GT7))
    assert screen.beep_rpm.isEnabled() is False
    screen.load(Settings(beep_rpm_source=RPM_MANUAL))
    assert screen.beep_rpm.isEnabled() is True


# --------------------------------------------------------- session hygiene

def test_a_session_left_open_is_closed_and_reported_on_the_next_run(qt_app,
                                                                    store):
    """A session with no end means the app went without stopping.

    Left alone it stays open forever; closed silently, nobody finds out the
    app died. It is closed at its last sign of life and said out loud.
    """
    event_id = store.create_event(name="E", track="Monza")
    session_id = store.start_session(event_id, "practice")

    open_now = store.open_sessions()
    assert [s["id"] for s in open_now] == [session_id]
    assert open_now[0]["last_seen"] == open_now[0]["started_at"]

    practice = PracticeScreen()
    controller = PitCrewController(store, EventScreen(), practice)
    try:
        assert store.open_sessions() == []
        assert store.get_session(session_id)["ended_at"] is not None
        assert "never closed" in practice.subtitle.text()
    finally:
        controller.shutdown()


def test_closing_the_window_while_recording_closes_the_session(qt_app, store):
    """A clean exit used to be indistinguishable from a crash."""
    event_id = store.create_event(name="E", track="Monza")
    store.set_state("active_event_id", event_id)
    controller = PitCrewController(store, EventScreen(), PracticeScreen())
    session_id = controller.open_practice_session()
    assert store.get_session(session_id)["ended_at"] is None

    controller.shutdown()
    assert store.get_session(session_id)["ended_at"] is not None
    assert store.open_sessions() == []


def test_an_orphan_is_closed_at_its_last_lap_not_at_the_next_launch(store):
    """Stamping it now would claim it ran until the next launch, which could
    be days."""
    event_id = store.create_event(name="E", track="Monza")
    session_id = store.start_session(event_id, "practice")
    from pitcrew.telemetry.session_state import Lap
    store.add_lap(session_id, Lap(
        lap_num=1, lap_time_ms=94000, best_lap_ms=94000, delta_ms=0,
        fuel_start=100.0, fuel_end=96.0, fuel_used=4.0, position=1,
        is_pit_lap=False, is_out_lap=False))

    orphan = store.open_sessions()[0]
    store.end_session(orphan["id"], at=orphan["last_seen"])
    ended = store.get_session(session_id)["ended_at"]
    assert ended == store.list_laps(session_id)[0]["recorded_at"]


# ---------------------------------------------------------------- the log

def test_installing_the_log_writes_a_file_and_is_idempotent(tmp_path,
                                                            monkeypatch):
    monkeypatch.setattr(diagnostics, "_installed", False)
    monkeypatch.setattr(diagnostics, "_fault_file", None)
    logger = logging.getLogger(diagnostics.LOGGER_NAME)
    original = list(logger.handlers)
    try:
        path = diagnostics.install(log_dir=tmp_path)
        assert path.exists()
        # Called twice - once from main(), once from a test harness - must not
        # stack a second handler and double every line.
        handlers = len(logger.handlers)
        diagnostics.install(log_dir=tmp_path)
        assert len(logger.handlers) == handlers

        diagnostics.log("probe").error("something went wrong")
        for handler in logger.handlers:
            handler.flush()
        assert "something went wrong" in path.read_text(encoding="utf-8")
    finally:
        for handler in list(logger.handlers):
            if handler not in original:
                handler.close()
                logger.removeHandler(handler)
        diagnostics._installed = False


def test_an_unhandled_exception_is_recorded_before_the_process_dies(tmp_path,
                                                                    monkeypatch):
    """PyQt aborts after sys.excepthook returns, so this is the last chance."""
    monkeypatch.setattr(diagnostics, "_installed", False)
    monkeypatch.setattr(diagnostics, "_fault_file", None)
    logger = logging.getLogger(diagnostics.LOGGER_NAME)
    original = list(logger.handlers)
    try:
        path = diagnostics.install(log_dir=tmp_path)
        try:
            raise ValueError("a slot blew up")
        except ValueError:
            import sys
            diagnostics._excepthook(*sys.exc_info())
        for handler in logger.handlers:
            handler.flush()
        written = path.read_text(encoding="utf-8")
        assert "unhandled exception" in written
        assert "a slot blew up" in written
        assert "Traceback" in written
    finally:
        for handler in list(logger.handlers):
            if handler not in original:
                handler.close()
                logger.removeHandler(handler)
        diagnostics._installed = False


def test_a_worker_thread_exception_is_recorded_too(tmp_path, monkeypatch):
    """The UDP listener and the voice thread both die out of sight."""
    monkeypatch.setattr(diagnostics, "_installed", False)
    monkeypatch.setattr(diagnostics, "_fault_file", None)
    logger = logging.getLogger(diagnostics.LOGGER_NAME)
    original = list(logger.handlers)
    try:
        path = diagnostics.install(log_dir=tmp_path)

        def blow_up():
            raise RuntimeError("no audio device")

        thread = threading.Thread(target=blow_up, name="PitCrewVoice")
        thread.start()
        thread.join()
        for handler in logger.handlers:
            handler.flush()
        written = path.read_text(encoding="utf-8")
        assert "no audio device" in written
        assert "PitCrewVoice" in written
    finally:
        for handler in list(logger.handlers):
            if handler not in original:
                handler.close()
                logger.removeHandler(handler)
        diagnostics._installed = False


# ------------------------------------------------------------- the voice

def test_the_voice_tuning_round_trips_and_reaches_the_engine(store):
    from pitcrew.engineer.voice import DEFAULT_TUNING, Voice

    settings.save(store, Settings(voice_length_scale=1.20,
                                  voice_noise_w_scale=0.40))
    loaded = settings.load(store)
    assert loaded.voice_tuning() == {"length_scale": 1.20,
                                     "noise_scale": 0.60,
                                     "noise_w_scale": 0.40}

    class Tunable:
        name = "tunable"

        def __init__(self):
            self.tuning = dict(DEFAULT_TUNING)

        def tune(self, **params):
            self.tuning.update(params)

        def speak(self, text):
            pass

    engine = Tunable()
    voice = Voice(engine=engine)
    voice.tune(**loaded.voice_tuning())
    assert engine.tuning["noise_w_scale"] == 0.40
    voice.stop()


def test_tuning_an_engine_that_cannot_be_tuned_is_not_an_error(store):
    """SAPI has no synthesis parameters, and no voice at all is still a
    running app."""
    from pitcrew.engineer.voice import NullEngine, Voice

    Voice(engine=NullEngine()).tune(length_scale=1.5)
    Voice(engine=None).tune(length_scale=1.5)


def test_the_engine_ignores_a_parameter_it_does_not_have():
    """A newer settings screen must not break an older engine."""
    from pitcrew.engineer.voice import PiperEngine

    engine = PiperEngine.__new__(PiperEngine)
    from pitcrew.engineer.voice import DEFAULT_TUNING
    engine.tuning = dict(DEFAULT_TUNING)
    engine.tune(noise_w_scale=0.3, invented_parameter=99.0)
    assert engine.tuning["noise_w_scale"] == 0.3
    assert "invented_parameter" not in engine.tuning


def test_a_nonsense_voice_tuning_is_refused():
    with pytest.raises(ValueError, match="noise_w_scale"):
        Settings(voice_noise_w_scale=9.0).validate()


def test_the_engine_chain_still_degrades_without_raising(monkeypatch):
    """Piper -> SAPI -> silent. Failure is silent, never fatal."""
    from pitcrew.engineer import voice as voice_module

    def unavailable(*_args, **_kwargs):
        raise RuntimeError("not on this machine")

    monkeypatch.setattr(voice_module, "PiperEngine", unavailable)
    monkeypatch.setattr(voice_module, "Sapi5Engine", unavailable)
    assert voice_module._best_engine() is None

    silent = voice_module.Voice(engine=None)
    assert silent.enabled is False
    silent.say("box this lap")          # must not raise
    assert silent.spoken == ["box this lap"]


def test_synthesis_streams_rather_than_collecting_the_whole_line():
    """Audio must start on the first chunk, not after the last one.

    Collecting every chunk before playing any of them puts the whole
    synthesis time in front of the first word, which on a long call is most
    of a second of silence while the engineer is supposedly talking.

    Proved by interleaving, not by counting: the log has to show the first
    chunk written before the last chunk was produced.
    """
    import sys
    import types

    from pitcrew.engineer.voice import PiperEngine

    log: list[str] = []

    class Stream:
        def start(self):
            log.append("start")

        def write(self, samples):
            log.append(f"write {samples[0]}")

        def stop(self):
            log.append("stop")

        def close(self):
            log.append("close")

    def synthesise(_text):
        for index in range(3):
            log.append(f"synth {index}")
            yield ([index], 22_050)

    engine = PiperEngine.__new__(PiperEngine)
    engine.synthesise = synthesise

    fake = types.ModuleType("sounddevice")
    fake.OutputStream = lambda **_kwargs: Stream()
    original = sys.modules.get("sounddevice")
    sys.modules["sounddevice"] = fake
    try:
        engine.speak("box this lap")
    finally:
        if original is None:
            sys.modules.pop("sounddevice", None)
        else:
            sys.modules["sounddevice"] = original

    assert log == ["synth 0", "start", "write 0",
                   "synth 1", "write 1",
                   "synth 2", "write 2",
                   "stop", "close"]
    # The load-bearing assertion, stated plainly: the first sample was on its
    # way to the device before the last one had been synthesised.
    assert log.index("write 0") < log.index("synth 2")


def test_a_line_that_synthesises_to_nothing_opens_no_stream():
    """No audio device is touched for an empty result, and nothing raises."""
    import sys
    import types

    from pitcrew.engineer.voice import PiperEngine

    opened = []
    engine = PiperEngine.__new__(PiperEngine)
    engine.synthesise = lambda _text: iter(())

    fake = types.ModuleType("sounddevice")

    def output_stream(**_kwargs):
        opened.append(1)
        raise AssertionError("no stream should be opened")

    fake.OutputStream = output_stream
    original = sys.modules.get("sounddevice")
    sys.modules["sounddevice"] = fake
    try:
        engine.speak("")
    finally:
        if original is None:
            sys.modules.pop("sounddevice", None)
        else:
            sys.modules["sounddevice"] = original
    assert opened == []
