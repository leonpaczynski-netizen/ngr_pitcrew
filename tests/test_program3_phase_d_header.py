"""Program 3 Phase D — the persistent context header gains Strategy + recording state.

The header must always show the active context so the wrong one is impossible to
miss, and clearly distinguish recording vs idle (colour + text + glyph, never colour
alone).
"""

import os

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from data.session_context import build_session_context
from data.strategy_context import build_strategy_context
from ui.app_state import build_app_state
from ui.components.event_header import EventHeaderBar

_app = QApplication.instance() or QApplication([])


def test_empty_state_shows_placeholders():
    h = EventHeaderBar()
    h.bind(build_app_state())
    assert h._strategy.text() == "Strategy: —"
    assert h._rec.accessibleName() == "IDLE"
    assert h._rec.tone == "neutral"


def test_recording_state_is_unmistakable():
    h = EventHeaderBar()
    sess = build_session_context(connected=True, laps_recorded=6, active_session_id=1)
    h.bind(build_app_state(session=sess, connected=True))
    # colour (danger) + text (REC) + glyph (●) — never colour alone
    assert h._rec.tone == "danger"
    assert h._rec.accessibleName() == "REC · Lap 6"
    assert "●" in h._rec.text()
    # connection is a distinct signal from recording
    assert h._conn.tone == "success"


def test_idle_when_connected_but_not_recording():
    h = EventHeaderBar()
    sess = build_session_context(connected=True, laps_recorded=0, active_session_id=None)
    h.bind(build_app_state(session=sess, connected=True))
    assert h._rec.tone == "neutral"
    assert h._rec.accessibleName() == "IDLE"
    assert h._conn.tone == "success"        # signal is live, but nothing recording


def test_strategy_plan_label():
    h = EventHeaderBar()
    strat = build_strategy_context(
        strategy={"stops": [{"compound": "RH", "laps": 10}, {"compound": "RM", "laps": 15}]})
    h.bind(build_app_state(strategy=strat))
    assert h._strategy.text().startswith("Strategy:")
    assert h._strategy.text() != "Strategy: —"


def test_no_active_event_is_shown():
    h = EventHeaderBar()
    h.bind(build_app_state())
    assert h._event_line.text() == "No active event"
