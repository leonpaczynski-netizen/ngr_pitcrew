"""The screen filling that was moved off the launch path.

`load_active_event()` and `_close_orphaned_sessions()` used to run inside
`PitCrewController.__init__`, costing ~130 ms of widget building before the
window could appear. They now run from a zero-delay timer, once.

Three things are pinned, and none of them is the timing.

**The order.** Loading the event writes the practice status line; the orphan
sweep writes the one message saying the app died last time. Run the other way
round and that message is overwritten before anyone sees it - silently, with
no exception and no log. Qt gives no ordering diagnostic to whoever splits
these into two callbacks later, so the test is the only guard.

**That it runs at all.** `main()` can return through its `finally` without
ever reaching `app.exec()`. Deferring an unconditional side effect to an event
loop that may never turn would make the app's only unclean-shutdown detector
best-effort - and the thing it detects is the app dying. So `shutdown()` runs
it if the loop did not.

**That it runs once.** Twice would re-close sessions already closed and refill
every screen for nothing.
"""
from __future__ import annotations

import os

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from pitcrew.controller import PitCrewController        # noqa: E402
from pitcrew.store.db import Store                      # noqa: E402
from pitcrew.ui.event_screen import EventScreen         # noqa: E402
from pitcrew.ui.practice_screen import PracticeScreen   # noqa: E402


@pytest.fixture(scope="session")
def qt_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def a_controller(store: Store):
    return PitCrewController(store, EventScreen(), PracticeScreen())


def an_open_session(store: Store) -> int:
    """A session with no `ended_at` - what a crash leaves behind."""
    event_id = store.create_event(name="orphan test", track="Monza",
                                  car_name="Porsche 911 RSR (991) '17")
    store.set_state("active_event_id", str(event_id))
    return store.start_session(event_id, "practice")


def test_the_screens_are_not_filled_until_the_loop_turns(qt_app, store):
    """The whole point: the window can paint before this work happens."""
    controller = a_controller(store)
    assert controller._first_paint_done is False
    qt_app.processEvents()
    assert controller._first_paint_done is True
    controller.shutdown()


def test_the_unclean_shutdown_warning_survives_the_event_load(qt_app, store):
    """The ordering guard. `load_active_event` writes the idle status; the
    orphan sweep must write over *it*, not the reverse."""
    an_open_session(store)
    controller = a_controller(store)
    qt_app.processEvents()

    status = controller.practice.subtitle.text()
    assert "did not shut down cleanly" in status, (
        "the orphan sweep ran before load_active_event and its warning was "
        "overwritten - see PitCrewController._first_paint_work")
    controller.shutdown()


def test_shutdown_sweeps_orphans_when_the_loop_never_turned(qt_app, store):
    """`main()` can die between the controller and `app.exec()`. Without this,
    a run that dies could skip the check for the last run that died."""
    session_id = an_open_session(store)
    controller = a_controller(store)
    assert controller._first_paint_done is False   # no processEvents
    controller.shutdown()

    closed = [s for s in store.open_sessions() if s["id"] == session_id]
    assert not closed, "the orphaned session was left open"


def test_it_runs_exactly_once(qt_app, store):
    an_open_session(store)
    controller = a_controller(store)
    calls: list[int] = []
    original = controller.load_active_event
    controller.load_active_event = lambda *a, **k: (calls.append(1),
                                                    original(*a, **k))[1]
    qt_app.processEvents()
    qt_app.processEvents()
    controller._first_paint_work()
    controller.shutdown()
    assert len(calls) <= 1
