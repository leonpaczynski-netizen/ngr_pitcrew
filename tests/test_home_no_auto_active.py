"""No-auto-active-event-on-open — unit tests for the active_cycle_id gate in
``build_initial_app_state`` (ui/new_shell_launch.py).

Qt-free: the function imports app_state (Qt-free) and calls window methods via the
defensive _safe_ctx wrapper; the live_shell_bridge import (PyQt6) is guarded inside
a try/except, so these tests run without a QApplication.

The gate: when config["active_cycle_id"] is absent or empty the event context is
suppressed → EventContext.event_id is None → AppState.has_active_event is False.
Once a cycle is explicitly selected, save_and_activate writes "active_cycle_id" into
the config dict, the gate does not fire, and the normal context path runs.
"""
from __future__ import annotations

from data.event_context import build_event_context
from data.session_context import build_session_context
from data.strategy_context import build_strategy_context
from ui.new_shell_launch import build_initial_app_state


def _fake_window_with_event():
    """A duck-typed window whose _build_event_context returns a non-None event_id.

    Simulates the state where config["strategy"] still carries an event_id from the
    previous session (the regression: on open the header would show that event even
    though active_cycle_id was cleared).
    """
    class _FakeWindow:
        def _build_event_context(self):
            # strategy dict still has an event_id — as happens after a previous session
            return build_event_context(strategy={"event_id": 42, "car": "Porsche 911 GT3 R"})

        def _build_session_context(self):
            return build_session_context()

        def _build_strategy_context(self):
            return build_strategy_context()

    return _FakeWindow()


def test_build_initial_app_state_no_active_cycle_gives_no_active_event():
    """Config with no active_cycle_id → has_active_event is False even if the window's
    event context would otherwise resolve a non-None event_id."""
    window = _fake_window_with_event()
    config = {}  # active_cycle_id absent
    state = build_initial_app_state(window, config)
    assert state.has_active_event is False


def test_build_initial_app_state_with_active_cycle_gives_active_event():
    """Config with a populated active_cycle_id → gate does not fire → event context
    flows through → has_active_event is True."""
    window = _fake_window_with_event()
    config = {"active_cycle_id": "cid-1"}
    state = build_initial_app_state(window, config)
    assert state.has_active_event is True


def test_build_initial_app_state_active_cycle_empty_string_gives_no_active_event():
    """An explicit empty string for active_cycle_id is treated as absent (no selection
    → no auto-active event)."""
    window = _fake_window_with_event()
    config = {"active_cycle_id": ""}
    state = build_initial_app_state(window, config)
    assert state.has_active_event is False


# ---------------------------------------------------------------------------
# Qt tests: HomePage rendering when resolution_state="event_requires_selection"
# ---------------------------------------------------------------------------
import pytest
from PyQt6.QtWidgets import QApplication
from ui.components.home_page import HomePage
from ui.app_state import AppState

_REQUIRES_SELECTION_PROMPT = (
    "Which event are you preparing for? Pick one below to start attaching laps."
)

_ONE_CANDIDATE_VIEW = {
    "resolution_state": "event_requires_selection",
    "candidates": [{"cycle_id": "c1", "event_name": "NGR Porsche Cup Rd7"}],
}


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class TestRequiresSelectionHomePage:
    """HomePage rendering for the event_requires_selection resolution state.

    These tests cover the UAT scenario where a single incomplete event arrives
    in the requires-selection state (because no active_cycle_id is set on open).
    """

    def test_requires_selection_shows_count_neutral_prompt(self, qapp):
        """The event_state label must show the count-neutral action prompt and
        must not contain the old "Several" wording."""
        page = HomePage()
        page.render(AppState.empty(), _ONE_CANDIDATE_VIEW)
        text = page._event_state.text()
        assert _REQUIRES_SELECTION_PROMPT in text
        assert "Several" not in text

    def test_requires_selection_shows_event_picker(self, qapp):
        """The candidate combo and Switch button must be visible (not hidden) and
        enabled, and the combo must carry the single candidate item.

        Visibility note: QWidget.isVisible() requires the widget to be in a
        shown window, so we assert isHidden() is False (setVisible(True) was
        called) and isEnabled() is True as the reliable Qt-unit-test proxy.
        """
        page = HomePage()
        page.render(AppState.empty(), _ONE_CANDIDATE_VIEW)
        assert not page._event_combo.isHidden(), (
            "_event_combo was hidden; expected setVisible(True) from have_candidates=True"
        )
        assert page._btn_switch.isEnabled(), (
            "_btn_switch was disabled; expected enabled with one candidate"
        )
        assert not page._btn_switch.isHidden(), (
            "_btn_switch was hidden; expected setVisible(True) from have_candidates=True"
        )
        assert page._event_combo.count() == 1
        assert "NGR Porsche Cup Rd7" in page._event_combo.itemText(0)

    def test_no_active_event_header_when_requires_selection(self, qapp):
        """The event title must show 'No active event' — not an event name —
        when AppState.empty() (has_active_event=False) is paired with the
        requires-selection view."""
        page = HomePage()
        page.render(AppState.empty(), _ONE_CANDIDATE_VIEW)
        assert page._event_title.text() == "No active event"
