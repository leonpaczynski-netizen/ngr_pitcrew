"""A slow launch leaves a trace in the log - where, and how long.

Critic, round 3 (19 Sep 2026): one in-process launch under full-suite load
spent 17.7 s building the Event screen, and the log said nothing between
"voice pack loaded" and "window built". It could not be reproduced in 13
more launches. Whatever it was, a repeat on race day must not be silent:

* every step of the window build is timed and WARNs past a second;
* a launch that has not drawn its first frame by 3 s logs the Qt thread's
  stack, so a stall inside Qt shows the line that called into it;
* the font warm-up - the candidate, because it holds Qt's font lock while
  it loads - logs when it finished and how long it took.
"""
from __future__ import annotations

import inspect
import logging
import os
import threading
import time

import pytest

from pitcrew import diagnostics


def _warnings(caplog, text):
    return [r.getMessage() for r in caplog.records
            if r.levelno >= logging.WARNING and text in r.getMessage()]


# --------------------------------------------------------------- timed_step

def test_a_fast_step_says_nothing(caplog):
    with caplog.at_level("INFO"):
        with diagnostics.timed_step("quick", warn_after_s=10.0) as step:
            pass
    assert step.took_s < 1.0
    assert not _warnings(caplog, "slow launch step")


def test_a_slow_step_warns_with_its_name_and_time(caplog):
    with caplog.at_level("INFO"):
        with diagnostics.timed_step("EventScreen", warn_after_s=0.01):
            time.sleep(0.03)
    [line] = _warnings(caplog, "slow launch step")
    assert "EventScreen" in line and " ms" in line


def test_a_step_that_raises_is_still_timed_and_still_raises(caplog):
    with caplog.at_level("INFO"):
        with pytest.raises(RuntimeError):
            with diagnostics.timed_step("boom", warn_after_s=0.0):
                raise RuntimeError("x")
    assert _warnings(caplog, "boom")


# ----------------------------------------------------------------- watchdog

def test_the_watchdog_logs_where_a_stuck_thread_is(caplog):
    """Armed on a thread that is stuck in a named function; the dump names
    it. This is what the 17.7 s launch would have left behind."""
    got: dict = {}

    def stuck_building_the_event_screen(release):
        got["dog"] = diagnostics.LaunchWatchdog(every_s=0.05, dumps=2)
        release.wait(5)

    release = threading.Event()
    with caplog.at_level("INFO"):
        worker = threading.Thread(target=stuck_building_the_event_screen,
                                  args=(release,))
        worker.start()
        deadline = time.monotonic() + 5
        while (not _warnings(caplog, "has not drawn its first frame")
               and time.monotonic() < deadline):
            time.sleep(0.01)
        release.set()
        worker.join(5)
        got["dog"].disarm()
    dumps = _warnings(caplog, "has not drawn its first frame")
    assert dumps, "the watchdog said nothing"
    assert "stuck_building_the_event_screen" in dumps[0]


def test_a_disarmed_watchdog_says_nothing(caplog):
    with caplog.at_level("INFO"):
        dog = diagnostics.LaunchWatchdog(every_s=0.05, dumps=3)
        dog.disarm()
        time.sleep(0.2)
    assert dog.fired == 0
    assert not _warnings(caplog, "has not drawn its first frame")


def test_the_watchdog_is_bounded(caplog):
    """A launch that never draws must not log for ever."""
    with caplog.at_level("INFO"):
        dog = diagnostics.LaunchWatchdog(every_s=0.02, dumps=2)
        time.sleep(0.3)
    assert dog.fired == 2
    dog.disarm()


def test_the_launch_arms_it_and_the_first_frame_stands_it_down():
    """`main` and `boot.early` arm it; the first frame and every exit path
    disarm it. Pinned by text: the suite never runs `main`."""
    import pitcrew.app as app_module
    from pitcrew import boot

    assert "diagnostics.watch_launch()" in inspect.getsource(boot.early)
    main = inspect.getsource(app_module.main)
    assert "diagnostics.watch_launch()" in main
    # The refused second copy, and the `finally`.
    assert main.count("diagnostics.launch_drawn()") >= 2
    first_frame = inspect.getsource(
        app_module.PitCrewWindow.after_launch_paint)
    assert "diagnostics.launch_drawn()" in first_frame


def test_launch_drawn_is_safe_unarmed(monkeypatch):
    monkeypatch.setattr(diagnostics, "_WATCHDOG", None)
    diagnostics.launch_drawn()
    diagnostics.launch_drawn()


# ------------------------------------------------------------- the window

@pytest.fixture(scope="module")
def qt_app():
    pytest.importorskip("PyQt6.QtWidgets")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_every_step_of_the_window_build_is_timed(qt_app, store, monkeypatch,
                                                 caplog):
    """With the threshold at zero every step reports, so this lists them."""
    from pitcrew.app import PitCrewWindow

    monkeypatch.setattr(diagnostics, "SLOW_STEP_S", 0.0)
    with caplog.at_level("INFO"):
        window = PitCrewWindow(store)
        try:
            window._ensure_screen(1)
            window._ensure_screen(6)
        finally:
            window.controller.shutdown()
    said = " | ".join(_warnings(caplog, "slow launch step"))
    for step in ("EventScreen", "PracticeScreen", "StrategyScreen",
                 "RaceScreen", "NavRail", "PitCrewController",
                 "car_screen", "settings_screen"):
        assert f"slow launch step: {step} took" in said, step


def test_main_times_the_window_build_and_show():
    import pitcrew.app as app_module

    main = inspect.getsource(app_module.main)
    assert 'diagnostics.timed_step("the window build")' in main
    assert "diagnostics.timed_step(\"the window's show()\")" in main


# ---------------------------------------------------------- the font warm-up

def test_the_font_warm_up_logs_when_it_finished_and_how_long(qt_app, caplog):
    from pitcrew.ui import font_warm, theme

    with caplog.at_level("INFO"):
        warm = font_warm.start("Pit Crew −･", theme.text_font(15),
                               "test-logged")
        deadline = time.monotonic() + 10
        while not warm.done() and time.monotonic() < deadline:
            qt_app.processEvents()
            time.sleep(0.005)
        # The thread's `finished` is emitted as it ends; give the log a beat.
        deadline = time.monotonic() + 5
        while warm.took_s is None and time.monotonic() < deadline:
            time.sleep(0.005)
    assert warm.done()
    assert warm.took_s is not None and warm.took_s >= 0.0
    lines = [r.getMessage() for r in caplog.records
             if "font warm-up test-logged finished in" in r.getMessage()]
    assert lines, "the warm-up's end was not logged"


def test_a_slow_font_warm_up_is_a_warning(qt_app, caplog, monkeypatch):
    from pitcrew.ui import font_warm, theme

    monkeypatch.setattr(diagnostics, "SLOW_STEP_S", 0.0)
    with caplog.at_level("INFO"):
        warm = font_warm.start("x", theme.text_font(15), "test-slow")
        deadline = time.monotonic() + 10
        while warm.took_s is None and time.monotonic() < deadline:
            qt_app.processEvents()
            time.sleep(0.005)
    assert _warnings(caplog, "font warm-up test-slow finished in")


def test_the_font_warm_up_runs_above_the_qt_threads_priority(qt_app):
    """It holds Qt's font lock while it loads; a starved worker makes the
    Qt thread wait on it (measured under load: up to 3.1 s)."""
    from PyQt6.QtCore import QThread

    from pitcrew.ui import font_warm, theme

    assert font_warm.PRIORITY == QThread.Priority.HighestPriority
    assert "self._thread.start(PRIORITY)" in inspect.getsource(
        font_warm.FontWarmUp.__init__)
    warm = font_warm.start("x", theme.text_font(15), "test-priority")
    try:
        # Read while it may still be running; once finished Qt reports
        # InheritPriority, so only a live read is meaningful.
        priority = warm._thread.priority()
        if not warm.done():
            assert priority == QThread.Priority.HighestPriority
    finally:
        font_warm.stop_all()
