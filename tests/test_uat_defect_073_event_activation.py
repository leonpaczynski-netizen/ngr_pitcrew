"""UAT remediation — DEF-UAT-073-011: setting an event active makes it appear on the Command Centre.

The Event Planner's "Set as Active" set only ``active_event_id``; the Command Centre resolves the active
*preparation cycle* (``active_cycle_id``), which nothing ever set — so a freshly-activated event never
appeared on Home. The fix ensures a deterministic preparation cycle for the event and sets it as the active
cycle (an explicit selection the Phase-51 resolver honours), so the Command Centre resolves ONE_ACTIVE_EVENT.
"""
from __future__ import annotations

import os
import queue
from unittest.mock import MagicMock

import pytest

import config_paths as cp


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt6 not available")
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp, tmp_path):
    from data.session_db import SessionDB
    cfg_path = str(tmp_path / "config.json")
    cp.write_default_config(cfg_path)
    config = cp.load_config(cfg_path)
    db = SessionDB(":memory:")
    from ui.dashboard import MainWindow, SignalBridge
    win = MainWindow(config=config, logger=MagicMock(), announcer=MagicMock(),
                     bridge=SignalBridge(), ui_queue=queue.Queue(), config_path=cfg_path, db=db)
    win._query_listener = None
    yield win
    win.close()


def test_activation_creates_cycle_and_sets_active_cycle(window):
    db = window._db
    db.upsert_event({"name": "GR Enduro Rd2", "car": "Porsche Cayman GT4 Clubsport '16",
                     "track": "Watkins Glen International", "layout_id": "grand_prix",
                     "race_type": "timed", "race_duration_minutes": 60})
    cycle_id = window._ensure_active_preparation_cycle("GR Enduro Rd2")
    assert cycle_id == "cycle-gr-enduro-rd2"
    assert window._config["active_cycle_id"] == cycle_id
    # a real cycle row now exists, populated from the event
    cyc = db.get_preparation_cycle(cycle_id)
    assert cyc is not None
    assert cyc.get("event_name") == "GR Enduro Rd2"


def test_command_centre_resolves_the_activated_event(window):
    db = window._db
    db.upsert_event({"name": "GR Enduro Rd2", "car": "Porsche Cayman GT4 Clubsport '16",
                     "track": "Watkins Glen International", "layout_id": "grand_prix"})
    window._ensure_active_preparation_cycle("GR Enduro Rd2")
    view = db.build_event_command_centre_view(
        selected_cycle_id=window._config["active_cycle_id"], now_date="2026-07-21")
    # the Command Centre now resolves an active event (no longer "no active event / create event")
    assert view.get("ok", True) is not False
    import json
    blob = json.dumps(view).lower()
    assert "gr enduro rd2" in blob or view.get("resolved_cycle_id") or view.get("active_cycle_id")


def test_activation_is_idempotent(window):
    db = window._db
    db.upsert_event({"name": "GR Enduro Rd2", "car": "c", "track": "t", "layout_id": "l"})
    a = window._ensure_active_preparation_cycle("GR Enduro Rd2")
    b = window._ensure_active_preparation_cycle("GR Enduro Rd2")
    assert a == b == "cycle-gr-enduro-rd2"
    # no duplicate cycles created for the same event
    cycles = [c for c in db.list_preparation_cycles() if c.get("cycle_id") == a]
    assert len(cycles) == 1


def test_activation_defensive_without_db(qapp, tmp_path):
    cfg_path = str(tmp_path / "config.json")
    cp.write_default_config(cfg_path)
    config = cp.load_config(cfg_path)
    from ui.dashboard import MainWindow, SignalBridge
    win = MainWindow(config=config, logger=MagicMock(), announcer=MagicMock(),
                     bridge=SignalBridge(), ui_queue=queue.Queue(), config_path=cfg_path, db=None)
    win._query_listener = None
    try:
        assert win._ensure_active_preparation_cycle("X") == ""   # no DB → no-op, never raises
    finally:
        win.close()
