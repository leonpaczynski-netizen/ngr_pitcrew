"""The debrief reaches the driver — on the radio and on the screen.

`RaceCoordinator` is built only in `start_race()`, so George owns the race and
nothing owned practice. This is the seam that closes that: `stop_practice`
starts the debrief off the Qt thread and `_on_debriefed` says it.
"""
from __future__ import annotations

import pytest

from pitcrew.store.db import Store
from pitcrew.ui.event_screen import EventScreen
from pitcrew.ui.practice_screen import PracticeScreen

pytest.importorskip("PyQt6.QtWidgets")

from pitcrew.controller import PitCrewController  # noqa: E402


@pytest.fixture(scope="session")
def qt_app():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture()
def wired(qt_app, store: Store):
    controller = PitCrewController(store, EventScreen(), PracticeScreen())
    yield controller
    controller.shutdown()


def _a_debrief():
    from pitcrew.analysis.debrief import Burn, Census, Debrief, Pace

    return Debrief(
        census=Census(recorded=16, out_laps=3, in_laps=0, excluded=0,
                      excursions=2, analysed=11),
        pace=Pace(n=13, median_ms=106_042, best_ms=104_306, sd_ms=2083.0),
        burn=Burn(n=13, median_l=7.55, sd_l=0.27),
        scatter=(), gears=(), correlations=(),
        silences=("Turn 3: r=-0.56 at p=0.07, which does not clear the bar",))


def test_the_debrief_is_spoken_when_the_session_closes(wired):
    spoken = []
    wired.voice.say = spoken.append
    wired._engineer_speaks = True

    wired._on_debriefed(_a_debrief())

    assert spoken, "the engineer said nothing at the end of practice"
    assert any("11 laps analysed" in line for line in spoken)
    assert any("106.0" in line for line in spoken)


def test_the_screen_carries_it_even_with_the_voice_muted(wired):
    """Muting the engineer is a preference about audio, not an instruction to
    withhold the finding — and speech alone cannot be re-read."""
    spoken, shown = [], []
    wired.voice.say = spoken.append
    wired.practice.set_status = lambda text, **kw: shown.append(text)
    wired._engineer_speaks = False

    wired._on_debriefed(_a_debrief())

    assert not spoken
    assert any("11 laps analysed" in text for text in shown)


def test_a_debrief_that_cannot_be_built_does_not_take_the_app_down(wired):
    """No corner model for the circuit is the ordinary case on a new track,
    not an error worth crashing at the moment the driver has just stopped."""
    class Exploding:
        def __getattr__(self, name):
            raise RuntimeError("no store")

    import threading

    real = wired.store
    wired.store = Exploding()
    try:
        wired._start_debrief({"id": 1})
        for thread in threading.enumerate():
            if thread.name == "debrief":
                thread.join(timeout=5.0)
        # Reaching here without an exception escaping is the assertion.
    finally:
        wired.store = real          # shutdown() needs it back


def test_the_debrief_thread_does_not_touch_qt(wired):
    """Building it decodes every lap's telemetry — 9.4 s on the largest event.
    The hop back is a queued signal, not `QTimer.singleShot`, which posted from
    a worker builds its dispatch object on the calling thread and never fires
    (see `_on_ptt_answer`)."""
    from pitcrew.controller import TelemetryBridge

    assert hasattr(TelemetryBridge, "debriefed")
    import inspect

    import ast
    import textwrap

    source = inspect.getsource(wired._start_debrief.__func__)
    assert "bridge.debriefed.emit" in source

    # The docstring explains WHY singleShot is wrong, so only the code counts.
    # `getdoc` normalises indentation and will not match the raw source, so the
    # docstring node is dropped properly rather than by string surgery.
    tree = ast.parse(textwrap.dedent(source)).body[0]
    statements = tree.body[1:] if (
        isinstance(tree.body[0], ast.Expr)
        and isinstance(tree.body[0].value, ast.Constant)) else tree.body
    body = " ".join(ast.unparse(node) for node in statements)
    assert "singleShot" not in body
    assert "threading.Thread" in body
