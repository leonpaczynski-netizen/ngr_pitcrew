"""One model load at a time, in a stated order, and nothing left armed.

Two accepted launch branches were merged on 20 Sep 2026 and the result would
not run its own suite: `python -m pytest pitcrew/tests` died at 41 % with no
failing test and `0xC0000409` - a hard process abort, twice, at the same
point. The arrangement that produced it:

* the app-open work starts the **speech** load on the window's first frame
  (`after_launch_paint` -> `release_speech`);
* the practice-start work armed
  `QTimer.singleShot(PREWARM_DELAY_MS, controller.prewarm_for_sessions)` at
  the end of `warm_screens`, which starts the **voice** load 500 ms later.

Two faults, and both are pinned here.

**The loads overlapped.** `PiperVoice.load` holds the GIL for its whole
~1.5 s, so started beside the speech thread it stops it, and the Qt thread
with it - on a window whose whole purpose was to be answering by then. Two
model loads racing at launch is also what killed push to talk in four
launches of five (`ptt.start_warm_up`).

**The timer was nobody's.** It fired 500 ms later whatever had happened in
between - including a window that had been shut down and a store that had
been closed. `prewarm_for_sessions` reached the closed database, the
`ProgrammingError` escaped the Qt slot, and PyQt ended the process with no
window, no message and no failing test. That is the abort: a stale timer, not
the machine.
"""
from __future__ import annotations

import threading
import time

import pytest

from pitcrew.engineer import ptt


@pytest.fixture(scope="module")
def qt_app():
    pytest.importorskip("PyQt6.QtWidgets")
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def held_warm_up():
    """A speech warm-up whose thread runs until `release` is set - the shape
    `ptt.start_warm_up` returns, and the only way to hold a load open for
    long enough to ask what started beside it."""
    release = threading.Event()
    outcome: dict = {}

    def load() -> None:
        try:
            release.wait(30)
            outcome["recogniser"] = None
            outcome["matcher"] = None
        finally:
            outcome["landed"] = True

    thread = threading.Thread(target=load, daemon=True, name="warm-speech")
    return (outcome, thread), release


def _pump_for(qt_app, seconds: float) -> None:
    deadline = time.perf_counter() + seconds
    while time.perf_counter() < deadline:
        qt_app.processEvents()
        time.sleep(0.005)


def _pump_until(qt_app, until, seconds: float = 5.0) -> None:
    deadline = time.perf_counter() + seconds
    while not until() and time.perf_counter() < deadline:
        qt_app.processEvents()
        time.sleep(0.005)


def _watch_prewarm(monkeypatch, ctrl, warm=None):
    """Record, for every pre-warm, whether the speech load had landed when it
    ran. The order is the thing under test, so the observation is of the
    order and not of a side effect."""
    seen: list[bool] = []
    real = ctrl.prewarm_for_sessions

    def watched():
        seen.append(warm is None or ptt.speech_landed(warm))
        real()

    monkeypatch.setattr(ctrl, "prewarm_for_sessions", watched)
    return seen


# ------------------------------------------------------------ the order

def test_the_pre_warm_waits_for_the_speech_models_and_then_runs(
        qt_app, store, monkeypatch):
    """The voice load starts **after** the speech models have landed.

    Against the merge as it stood, the pre-warm ran 500 ms after the screens
    with the speech thread still in its loader, and this records `False`.
    """
    from pitcrew.app import PitCrewWindow

    warm, release = held_warm_up()
    window = PitCrewWindow(store, warm=warm)
    ctrl = window.controller
    seen = _watch_prewarm(monkeypatch, ctrl, warm)
    monkeypatch.setattr(ctrl.voice, "warm", lambda: None)
    try:
        window.release_speech()          # what the first frame does
        assert warm[1].ident is not None, "the speech load never started"
        window.warm_screens()
        # The gate first - the screens take as long as they take - and then
        # well past `PREWARM_DELAY_MS` with the speech thread still loading.
        _pump_until(qt_app, lambda: window._prewarm_gate is not None, 20)
        assert window._prewarm_gate is not None, "the gate was never armed"
        _pump_for(qt_app, 1.2)
        assert seen == [], ("the session pre-warm ran while the speech "
                            "models were still loading")
        release.set()
        _pump_until(qt_app, lambda: seen)
        assert seen == [True]
    finally:
        release.set()
        ctrl.shutdown()


def test_a_speech_load_that_never_lands_is_reported_and_not_waited_on(
        qt_app, store, monkeypatch, caplog):
    """A load that never lands must be reported, not waited on for ever -
    and the first Practice press must still not pay the model load."""
    import pitcrew.app as app_module
    from pitcrew.app import PitCrewWindow

    monkeypatch.setattr(app_module, "PREWARM_DELAY_MS", 0)
    monkeypatch.setattr(app_module, "PREWARM_SPEECH_LIMIT_S", 0.2)
    warm, release = held_warm_up()
    window = PitCrewWindow(store, warm=warm)
    ctrl = window.controller
    seen = _watch_prewarm(monkeypatch, ctrl, warm)
    monkeypatch.setattr(ctrl.voice, "warm", lambda: None)
    try:
        with caplog.at_level("ERROR"):
            window.release_speech()
            window.warm_screens()
            _pump_until(qt_app, lambda: seen)
        assert seen == [False], "the pre-warm was skipped, not reported"
        assert any("has not landed" in record.getMessage()
                   for record in caplog.records), (
            "the wait ended with nothing in the log")
    finally:
        release.set()
        ctrl.shutdown()


def test_the_gate_is_armed_once_however_many_times_the_chain_ends(
        qt_app, store, monkeypatch):
    """`warm_screens` reaches its end twice on a launch where a screen is
    visited early. One gate, one pre-warm."""
    from pitcrew.app import PitCrewWindow

    window = PitCrewWindow(store)
    ctrl = window.controller
    seen = _watch_prewarm(monkeypatch, ctrl)
    monkeypatch.setattr(ctrl.voice, "warm", lambda: None)
    try:
        window.warm_screens()
        _pump_until(qt_app, lambda: seen)
        gate = window._prewarm_gate
        window.warm_screens()
        window.warm_screens()
        _pump_for(qt_app, 0.8)
        assert seen == [True]
        assert gate is None or not gate.isActive()
    finally:
        ctrl.shutdown()


# -------------------------------------------------- nothing fires too late

def test_a_gate_that_fires_after_shutdown_pre_warms_nothing(
        qt_app, store, monkeypatch, caplog):
    """**The abort, as a test.** The gate outlives the window here on
    purpose - the suite shuts controllers down without closing their windows,
    which is how the stale timer was found. It must reach a shut-down
    controller and do nothing: no voice load, no widgets, no read of a store
    that has been closed under it, and nothing raised into the event loop.
    """
    from pitcrew.app import PitCrewWindow

    window = PitCrewWindow(store)
    ctrl = window.controller
    warmed: list[int] = []
    monkeypatch.setattr(ctrl.voice, "warm", lambda: warmed.append(1))
    ctrl.settings.driver_board_enabled = True
    window.warm_screens()
    # Until it is armed, not for a fixed slice of wall clock: how long the
    # screens take is the machine's business, and a test that guesses at it
    # fails under suite load for a reason that has nothing to do with the
    # thing it is testing.
    _pump_until(qt_app, lambda: window._prewarm_gate is not None, 20)
    assert window._prewarm_gate is not None, "the gate was never armed"
    with caplog.at_level("ERROR"):
        ctrl.shutdown()
        store.close()                    # what the fixture does next
        _pump_for(qt_app, 1.0)           # the gate fires in here
    assert warmed == [], "the pre-warm ran against a shut-down controller"
    assert ctrl.driver_board is None
    assert ctrl._prewarmed is False, (
        "a refused pre-warm must not read as one that has been done")
    assert [r.getMessage() for r in caplog.records
            if r.levelname == "ERROR"] == []


def test_closing_the_window_disarms_the_gate(qt_app, store, monkeypatch):
    from pitcrew.app import PitCrewWindow

    window = PitCrewWindow(store)
    ctrl = window.controller
    seen = _watch_prewarm(monkeypatch, ctrl)
    window.warm_screens()
    _pump_until(qt_app, lambda: window._prewarm_gate is not None, 20)
    assert window._prewarm_gate is not None
    window.close()
    assert window._prewarm_gate is None
    _pump_for(qt_app, 1.0)
    assert seen == []


# ------------------------------------------ never raises, never on a race

def test_the_pre_warm_never_raises_out_of_its_slot(store, monkeypatch,
                                                   caplog, qt_app):
    """Every caller is a Qt timer, and an exception out of a slot ends the
    process rather than failing a test. So it does not raise - it logs."""
    from pitcrew.app import PitCrewWindow

    window = PitCrewWindow(store)
    ctrl = window.controller
    monkeypatch.setattr(ctrl.voice, "warm", lambda: None)

    def boom():
        raise RuntimeError("Cannot operate on a closed database.")

    monkeypatch.setattr(ctrl, "_prefetch_event_frames", boom)
    try:
        with caplog.at_level("WARNING"):
            ctrl.prewarm_for_sessions()          # must not raise
        assert any("frame prefetch" in record.getMessage()
                   for record in caplog.records)
    finally:
        ctrl.shutdown()


def test_the_voice_warm_up_says_when_it_landed(caplog):
    """**The accept, not only the refusal** (rule 10). The second model load
    said nothing at all when it worked, so a log could not answer "did the
    voice load, and when" - which is the first question to ask of a launch
    that has two model loads in a stated order."""
    from pitcrew.engineer.voice import Voice

    class _Engine:
        name = "fake"

        def __init__(self) -> None:
            self.warmed = 0

        def warm(self) -> None:
            self.warmed += 1

        def speak(self, text: str) -> None:
            pass

    engine = _Engine()
    spoken = Voice(engine, enabled=False)
    try:
        with caplog.at_level("INFO"):
            spoken.warm()
            deadline = time.perf_counter() + 10
            while (engine.warmed == 0
                   or not any("voice warm-up finished" in r.getMessage()
                              for r in caplog.records)):
                assert time.perf_counter() < deadline, (
                    "the voice warm-up never reported that it finished")
                time.sleep(0.005)
        assert engine.warmed == 1
    finally:
        spoken.stop()


@pytest.mark.parametrize("busy", ["session", "race", "free-run"])
def test_the_pre_warm_stands_down_for_anything_already_running(
        store, monkeypatch, qt_app, busy):
    """Rule 11, at the one door: the voice load freezes every thread for
    ~1.5 s and the board is widgets on the Qt thread. Neither may land on a
    driver who is already out there."""
    from pitcrew.app import PitCrewWindow

    window = PitCrewWindow(store)
    ctrl = window.controller
    warmed: list[int] = []
    monkeypatch.setattr(ctrl.voice, "warm", lambda: warmed.append(1))
    ctrl.settings.driver_board_enabled = True
    if busy == "session":
        ctrl.session_id = 77
    elif busy == "race":
        ctrl.race = type("_Race", (), {"armed": True, "running": False})()
    else:
        ctrl._rig_only_mode = True
    try:
        ctrl.prewarm_for_sessions()
        assert warmed == []
        assert ctrl.driver_board is None
        assert ctrl._prewarmed, "the frame prefetch would never run again"
    finally:
        ctrl.session_id = None
        ctrl.race = None
        ctrl._rig_only_mode = False
        ctrl.shutdown()
