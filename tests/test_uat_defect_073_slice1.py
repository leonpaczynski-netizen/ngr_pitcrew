"""UAT remediation Slice 1 — DEF-UAT-073-004/005/006 + Command Centre navigation.

Proves: the Command Centre primary action + cumulative-learning render REAL clickable buttons that navigate
(not inert status badges); "create / import event" targets the Event Planner tab; the legacy Home dashboard
(workflow stepper + duplicate cards + next-action banner) is removed so Home is the single Command Centre
surface (no stale prior-event state); and a persistent tab-bar button returns to the Command Centre from any
tab. Navigation changes the tab only — no domain/state mutation.
"""
from __future__ import annotations

import os
import queue
from unittest.mock import MagicMock

import pytest

import config_paths as cp
from ui import event_command_centre_vm as vm


# ---- pure VM (DEF-005/006) -------------------------------------------------
def test_primary_action_exposes_navigable_target():
    res = {"next_action": {"category": "create_event", "headline": "Create or import an NGR event",
                           "detail": "No active preparation cycle.", "target_surface": "no_event",
                           "tone": "info"}}
    na = vm.next_action_card(res)
    assert na["action_target"] == "no_event"
    assert na["action_label"] == "Create / Import Event"
    # the confusing raw "Go to: no_event" internal-surface line is gone
    assert not any("Go to:" in ln for ln in na["lines"])


def test_progress_card_exposes_navigable_target():
    p = vm.progress_card({"progress": {}})
    assert p["action_target"] == "development_history"
    assert p["action_label"] == "View Progress"


# ---- panel renders real buttons (offscreen) --------------------------------
@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt6 not available")
    return QApplication.instance() or QApplication([])


def test_primary_action_renders_button_and_navigates(qapp):
    from PyQt6.QtWidgets import QPushButton
    from ui.event_command_centre_panel import EventCommandCentrePanel
    fired = []
    p = EventCommandCentrePanel()
    p.set_handlers(navigate=lambda t: fired.append(t))
    p.update_result({"next_action": {"category": "create_event", "headline": "Create or import an NGR event",
                                     "detail": "-", "target_surface": "no_event", "tone": "info"}})
    btns = [b for b in p.findChildren(QPushButton) if "Create" in b.text()]
    assert btns, "primary action must render a real button"
    btns[0].click()
    assert fired == ["no_event"]


def test_action_card_suppresses_inert_pill_badge(qapp):
    from PyQt6.QtWidgets import QLabel
    from ui.event_command_centre_panel import EventCommandCentrePanel
    p = EventCommandCentrePanel()
    p.set_handlers(navigate=lambda t: None)
    p.update_result({"next_action": {"category": "create_event", "headline": "h", "detail": "d",
                                     "target_surface": "no_event", "tone": "info"}})
    # the old design showed a "CREATE EVENT" pill (QLabel) that looked clickable but wasn't; it must be gone
    labels = [l.text() for l in p.findChildren(QLabel)]
    assert "CREATE EVENT" not in labels


# ---- MainWindow: Home is command-centre only + nav button ------------------
@pytest.fixture
def window(qapp, tmp_path):
    cfg_path = str(tmp_path / "config.json")
    cp.write_default_config(cfg_path)
    config = cp.load_config(cfg_path)
    from ui.dashboard import MainWindow, SignalBridge
    win = MainWindow(config=config, logger=MagicMock(), announcer=MagicMock(),
                     bridge=SignalBridge(), ui_queue=queue.Queue(), config_path=cfg_path, db=None)
    win._query_listener = None
    yield win
    win.close()


def test_home_has_command_centre_and_no_legacy_dashboard(window):
    assert getattr(window, "_event_command_centre_panel", None) is not None
    # legacy Home dashboard removed (DEF-004)
    assert window._home_card_labels == {}
    assert window._home_stepper is None
    assert window._home_next_action_btn is None


def test_command_centre_corner_button_returns_home(window):
    from ui.tab_registry import TAB_HOME
    assert getattr(window, "_cc_home_btn", None) is not None
    # switch to another tab, then click the corner button → back to Home
    window.select_tab("telemetry")
    window._cc_home_btn.click()
    assert window.current_tab_key() == TAB_HOME


def test_create_event_navigates_to_event_planner(window):
    from ui.tab_registry import TAB_EVENT_PLANNER
    window._cc_navigate("no_event")
    assert window.current_tab_key() == TAB_EVENT_PLANNER


def test_home_refresh_survives_without_legacy_widgets(window):
    # the simplified _home_refresh must drive the Command Centre and never touch the removed widgets
    window._home_refresh()
    window._home_refresh_if_visible()
