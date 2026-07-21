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


@pytest.fixture(scope="module")
def window(qapp, tmp_path_factory):
    # module-scoped: ONE MainWindow reused across tests (many MainWindow constructions segfault PyQt on
    # Win/Py3.14). Operations under test are idempotent, so the tests stay order-independent.
    from data.session_db import SessionDB
    tmp = tmp_path_factory.mktemp("evt_activation")
    cfg_path = str(tmp / "config.json")
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
    from strategy.active_cycle_resolution import resolve_active_cycle, CycleCandidate
    db = window._db
    db.upsert_event({"name": "GR Enduro Rd2", "track": "Watkins Glen International",
                     "layout_id": "grand_prix"})
    window._ensure_active_preparation_cycle("GR Enduro Rd2")
    active = window._config["active_cycle_id"]
    # the Phase-51 resolver resolves the explicitly-activated cycle (no longer NO_ACTIVE_EVENT)
    cands = [CycleCandidate(cycle_id=r["cycle_id"], event_name=r["event_name"], series=r["series"],
                            round_label=r["round_label"], explicit_state=r["explicit_state"],
                            prep_open_date=r["prep_open_date"], official_race_date=r["official_race_date"],
                            context_digest=r["context_digest"])
             for r in db.list_preparation_cycle_candidates()]
    res = resolve_active_cycle(cands, selected_cycle_id=active, now_date="2026-07-21")
    assert res.resolved_cycle_id == active


def test_activation_is_idempotent(window):
    db = window._db
    db.upsert_event({"name": "GR Enduro Rd2", "car": "c", "track": "t", "layout_id": "l"})
    a = window._ensure_active_preparation_cycle("GR Enduro Rd2")
    b = window._ensure_active_preparation_cycle("GR Enduro Rd2")
    assert a == b == "cycle-gr-enduro-rd2"
    # no duplicate cycles created for the same event
    cycles = [c for c in db.list_preparation_cycles() if c.get("cycle_id") == a]
    assert len(cycles) == 1


def test_garage_car_persists_to_event_and_cycle(window):
    # DEF-UAT-073-013: selecting a car for the event in the Garage must persist it (event + cycle).
    db = window._db
    db.upsert_event({"name": "GR Enduro Rd2", "car": "old car", "track": "Watkins Glen International",
                     "layout_id": "grand_prix"})
    window._config["active_event_id"] = "GR Enduro Rd2"
    window._ensure_active_preparation_cycle("GR Enduro Rd2")
    # simulate the Garage selection + "Load to Event"
    window._garage_car_name_lbl.setText("Porsche Cayman GT4 Clubsport '16")
    window._on_garage_select_for_event()
    # the car is persisted in the strategy context AND pushed onto the active cycle (so it sticks)
    assert window._config["strategy"]["car"] == "Porsche Cayman GT4 Clubsport '16"
    cyc = db.get_preparation_cycle(window._config["active_cycle_id"])
    assert cyc.get("car") == "Porsche Cayman GT4 Clubsport '16"


def test_practice_setup_dropdown_filters_by_active_car(window):
    # DEF-UAT-073-010: the running-setup combos show only the ACTIVE car's setups, not every setup ever.
    window._config.setdefault("strategy", {})["car"] = "Porsche Cayman GT4 Clubsport '16"
    window._saved_setups = [
        {"setup_label": "GT4 Race", "setup_type": "Race", "car": "Porsche Cayman GT4 Clubsport '16"},
        {"setup_label": "MX5 Race", "setup_type": "Race", "car": "Mazda MX-5"},
    ]
    window._refresh_running_setup_combos()
    combo = window._prac_running_setup_combo
    items = [combo.itemText(i) for i in range(combo.count())]
    assert any("GT4 Race" in it for it in items)
    assert not any("MX5 Race" in it for it in items)   # other car's setup is filtered out


def test_practice_setup_dropdown_falls_back_when_no_match(window):
    # older setups with no car tag must not be hidden (graceful fallback to all)
    window._config.setdefault("strategy", {})["car"] = "Some Car"
    window._saved_setups = [{"setup_label": "Legacy", "setup_type": "Race"}]  # no car field
    window._refresh_running_setup_combos()
    combo = window._prac_running_setup_combo
    items = [combo.itemText(i) for i in range(combo.count())]
    assert any("Legacy" in it for it in items)


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
