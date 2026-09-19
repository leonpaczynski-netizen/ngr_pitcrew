"""The launch reads the league calendar beside the window build - and the
first fill only ever uses that read when it is still the right answer.

Round 4 (20 Sep 2026): the first fill, which runs in front of the window's
first frame, spent 30-80 ms of its 35-85 in one read of the hub's SQLite
file. `start_calendar_read` begins it on its own thread from `main`; the
first fill takes it through `_take_calendar_read`.

What each test pins:

* a finished read seeds the fill's memo, and the fill does not read again;
* a read taken against other stored events (or another driver name) is not
  used - the calendar is read afresh, as it always was;
* a read not finished within `CALENDAR_WAIT_S` is not waited for beyond it;
* a read that failed costs nothing but the read it would have saved;
* the seed lives only inside the first fill, like the memo it seeds;
* `main` starts the read before it builds the window, and hands it over.
"""
from __future__ import annotations

import inspect
import os
import threading
import time

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from pitcrew import controller as controller_module  # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


class Proposal:
    def __init__(self, round_id):
        self.round_id = round_id
        self.event_id = None


def _finished(outcome):
    thread = threading.Thread(target=lambda: None)
    thread.start()
    thread.join()
    return outcome, thread


def _controller(store, calendar):
    from pitcrew.controller import PitCrewController
    from pitcrew.ui.event_screen import EventScreen
    from pitcrew.ui.practice_screen import PracticeScreen

    return PitCrewController(store, EventScreen(), PracticeScreen(),
                             defer_strip=True, calendar=calendar)


@pytest.fixture()
def reads(monkeypatch):
    """Every calendar read the controller makes itself."""
    made: list = []

    def read(me, stored):
        made.append((me, stored))
        return []

    monkeypatch.setattr(controller_module, "read_calendar", read)
    return made


def _first_fill(control) -> None:
    """The first fill, as the launch runs it. The proposals here are empty
    lists - which read answered is told by `reads`, the controller's own
    reads, not by their contents."""
    control._first_paint_work()


def test_a_finished_read_seeds_the_first_fill(qt_app, store, reads):
    key = (store.driver_name(), store.list_events())
    control = _controller(store, _finished(
        {"key": key, "proposals": []}))
    try:
        _first_fill(control)
        assert reads == []
        # And the seed dies with the fill, as the memo always did: the next
        # question after it is read afresh.
        assert control._hub_memo is None
        control.hub_proposals()
        assert len(reads) == 1
    finally:
        control.shutdown()


def test_a_read_against_other_events_is_not_used(qt_app, store, event_id,
                                                 reads):
    stale_key = (store.driver_name(), [])       # before the event existed
    control = _controller(store, _finished(
        {"key": stale_key, "proposals": []}))
    try:
        _first_fill(control)
        assert len(reads) == 1
    finally:
        control.shutdown()


def test_an_unfinished_read_is_waited_for_no_longer_than_the_bound(
        qt_app, store, reads, monkeypatch):
    monkeypatch.setattr(controller_module, "CALENDAR_WAIT_S", 0.05)
    release = threading.Event()
    outcome: dict = {}

    def slow():
        release.wait(10)
        outcome["key"] = (store.driver_name(), store.list_events())
        outcome["proposals"] = []

    thread = threading.Thread(target=slow, daemon=True)
    thread.start()
    control = _controller(store, (outcome, thread))
    try:
        began = time.perf_counter()
        _first_fill(control)
        assert time.perf_counter() - began < 5.0
        assert len(reads) == 1
    finally:
        release.set()
        control.shutdown()


def test_a_failed_read_is_read_again(qt_app, store, reads):
    control = _controller(store, _finished({}))
    try:
        _first_fill(control)
        assert len(reads) == 1
    finally:
        control.shutdown()


def test_start_calendar_read_reads_against_the_store(store, event_id,
                                                     monkeypatch):
    monkeypatch.setattr(controller_module, "read_calendar",
                        lambda me, stored: [Proposal(len(stored))])
    outcome, thread = controller_module.start_calendar_read(store)
    thread.join(10)
    assert outcome["key"] == (store.driver_name(), store.list_events())
    assert [p.round_id for p in outcome["proposals"]] == [1]


def test_start_calendar_read_logs_a_failure_and_leaves_no_answer(
        store, monkeypatch, caplog):
    def broken(me, stored):
        raise RuntimeError("hub moved")

    monkeypatch.setattr(controller_module, "read_calendar", broken)
    with caplog.at_level("ERROR"):
        outcome, thread = controller_module.start_calendar_read(store)
        thread.join(10)
    assert outcome == {}
    assert any("calendar read failed" in r.getMessage()
               for r in caplog.records)


def test_main_starts_the_read_before_the_window_and_hands_it_over():
    import pitcrew.app as app_module

    main = inspect.getsource(app_module.main)
    assert main.index("start_calendar_read(store)") < main.index(
        "PitCrewWindow(")
    assert "calendar=calendar" in main
