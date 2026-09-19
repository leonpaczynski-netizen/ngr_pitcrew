"""The speech engine may land after the window - and nothing is lost for it.

Critic, round 3 (19 Sep 2026): `engine_from` joined the launch's engine
build on the Qt thread, with no limit, while the controller was building the
window. Usually free; 1.4 s once under load, and the one join left on the
path to the first frame. `Voice(arriving=build)` now takes a finished build
exactly as before and lets an unfinished one land on the voice thread.

What each test pins is a way that move could have cost George a line, or
told the driver something untrue about his speech:

* nothing said before the engine lands is dropped - it is said, in order;
* `tune` and `warm` asked for before it lands are applied when it does;
* no engine at all answers every waiting line "not heard", as before;
* a build that raised is chosen again - on the voice thread, not Qt's;
* the controller is built without waiting, and Settings is corrected when
  the engine lands.
"""
from __future__ import annotations

import os
import threading
import time

import pytest

from pitcrew.engineer import voice
from pitcrew.engineer.voice import Voice


class Engine:
    name = "fake"

    def __init__(self):
        self.said: list[str] = []
        self.tuned: list[dict] = []
        self.warmed = 0
        self.speaking_thread: list[str] = []

    def speak(self, text):
        self.said.append(text)
        self.speaking_thread.append(threading.current_thread().name)

    def tune(self, **params):
        self.tuned.append(params)

    def warm(self):
        self.warmed += 1


def held_build(engine=None, *, raises=False):
    """`start_engine_build`'s shape, held until `release` is set."""
    release = threading.Event()
    outcome: dict = {}

    def build():
        release.wait(30)
        if not raises:
            outcome["engine"] = engine

    thread = threading.Thread(target=build, name="voice-engine", daemon=True)
    thread.start()
    return (outcome, thread), release


def until(done, timeout=10.0):
    deadline = time.monotonic() + timeout
    while not done():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.005)


def test_a_finished_build_is_taken_at_once_exactly_as_before():
    engine = Engine()
    build, release = held_build(engine)
    release.set()
    build[1].join(5)
    spoken = Voice(arriving=build)
    try:
        assert spoken.landed is True
        assert spoken._engine is engine and spoken.enabled is True
        assert spoken.engine_name == "fake"
    finally:
        spoken.stop()


def test_construction_does_not_wait_for_an_unfinished_build():
    engine = Engine()
    build, release = held_build(engine)
    started = time.perf_counter()
    spoken = Voice(arriving=build)
    try:
        assert time.perf_counter() - started < 1.0
        assert spoken.landed is False
        assert spoken.engine_name == "loading"
        assert spoken.enabled is True            # lines are accepted
    finally:
        release.set()
        spoken.stop()


def test_lines_said_before_it_lands_are_said_in_order_once_it_does():
    engine = Engine()
    build, release = held_build(engine)
    spoken = Voice(arriving=build)
    heard: list[tuple[str, bool]] = []
    try:
        spoken.say("Radio check.", on_done=lambda ok: heard.append(("a", ok)))
        spoken.say("Box this lap.", on_done=lambda ok: heard.append(("b", ok)))
        time.sleep(0.05)
        assert engine.said == []                 # nothing to say it through
        release.set()
        until(lambda: len(heard) == 2)
        assert engine.said == ["Radio check.", "Box this lap."]
        assert heard == [("a", True), ("b", True)]
        assert set(engine.speaking_thread) == {"PitCrewVoice"}
        assert spoken.engine_name == "fake"
    finally:
        spoken.stop()


def test_tune_and_warm_asked_for_early_are_applied_when_it_lands():
    engine = Engine()
    build, release = held_build(engine)
    spoken = Voice(arriving=build)
    try:
        spoken.tune(length_scale=1.1)
        spoken.tune(noise_scale=0.5)
        spoken.warm()
        assert engine.tuned == [] and engine.warmed == 0
        release.set()
        assert spoken.wait_landed(10)
        until(lambda: engine.warmed == 1)
        assert engine.tuned == [{"length_scale": 1.1, "noise_scale": 0.5}]
        # After it has landed, straight through as always.
        spoken.tune(length_scale=0.9)
        assert engine.tuned[-1] == {"length_scale": 0.9}
    finally:
        spoken.stop()


def test_no_engine_answers_every_waiting_line_not_heard():
    build, release = held_build(None)
    spoken = Voice(arriving=build)
    heard: list[bool] = []
    try:
        spoken.say("Fuel is fine.", on_done=heard.append)
        release.set()
        assert spoken.wait_landed(10)
        until(lambda: heard == [False])
        assert spoken.enabled is False
        assert spoken.engine_name == "none"
        # And after it, the voice-off path, answered at once.
        spoken.say("Still here?", on_done=heard.append)
        assert heard == [False, False]
        assert spoken.say_now("Radio check.")[0] is False
    finally:
        spoken.stop()


def test_a_build_that_raised_is_chosen_again_on_the_voice_thread(
        monkeypatch):
    engine = Engine()
    chosen_on: list[str] = []

    def best():
        chosen_on.append(threading.current_thread().name)
        return engine

    monkeypatch.setattr(voice, "_best_engine", best)
    build, release = held_build(raises=True)
    spoken = Voice(arriving=build)
    try:
        release.set()
        assert spoken.wait_landed(10)
        assert chosen_on == ["PitCrewVoice"]
        assert spoken._engine is engine and spoken.enabled is True
    finally:
        spoken.stop()


def test_on_landed_is_called_once_after_the_engine_is_in(monkeypatch):
    engine = Engine()
    build, release = held_build(engine)
    seen: list[str] = []
    spoken = Voice(arriving=build,
                   on_landed=lambda: seen.append(spoken.engine_name))
    try:
        release.set()
        until(lambda: seen)
        time.sleep(0.05)
        assert seen == ["fake"]
    finally:
        spoken.stop()


def test_say_now_waits_for_an_engine_still_landing():
    """The Settings self-test: bounded, and it says so if it runs out."""
    engine = Engine()
    build, release = held_build(engine)
    spoken = Voice(arriving=build)
    try:
        threading.Timer(0.1, release.set).start()
        assert spoken.say_now("Radio check.") == (True, "")
        assert engine.said == ["Radio check."]
    finally:
        spoken.stop()


def test_say_now_is_bounded(monkeypatch):
    monkeypatch.setattr(voice, "ENGINE_WAIT_S", 0.05)
    build, release = held_build(Engine())
    spoken = Voice(arriving=build)
    try:
        ok, why = spoken.say_now("Radio check.")
        assert ok is False and "still loading" in why
    finally:
        release.set()
        spoken.stop()


def test_a_disabled_voice_still_lands_its_engine():
    engine = Engine()
    build, release = held_build(engine)
    spoken = Voice(arriving=build, enabled=False)
    release.set()
    assert spoken.wait_landed(10)
    assert spoken.enabled is False and spoken.engine_name == "fake"


# ----------------------------------------------------- the controller's side

@pytest.fixture(scope="module")
def qt_app():
    pytest.importorskip("PyQt6.QtWidgets")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_the_controller_does_not_join_the_engine_build(qt_app, store,
                                                       monkeypatch):
    """The join removed from the path to the window. The build here would
    block for thirty seconds; the controller must be built long before."""
    from pitcrew.controller import PitCrewController
    from pitcrew.ui.event_screen import EventScreen
    from pitcrew.ui.practice_screen import PracticeScreen

    engine = Engine()
    build, release = held_build(engine)
    started = time.perf_counter()
    controller = None
    try:
        controller = PitCrewController(store, EventScreen(), PracticeScreen(),
                                       voice_engine=build)
        took = time.perf_counter() - started
        assert took < 10, f"the controller waited {took:.1f}s"
        assert controller.voice.landed is False

        shown: list[str] = []

        class Settings:
            def show_capabilities(self, *, speech, hook):
                shown.append(speech)

        controller.settings_screen = Settings()
        release.set()
        assert controller.voice.wait_landed(10)
        # Emitted on the voice thread, delivered on this one.
        deadline = time.monotonic() + 5
        while not shown and time.monotonic() < deadline:
            qt_app.processEvents()
            time.sleep(0.005)
        assert shown == ["fake"]
        # The tuning the controller applied at construction reached it.
        assert engine.tuned, "the settings' voice tuning was lost"
    finally:
        release.set()
        if controller is not None:
            controller.settings_screen = None
            controller.shutdown()
