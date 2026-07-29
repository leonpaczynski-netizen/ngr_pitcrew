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
