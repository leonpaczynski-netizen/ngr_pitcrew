"""Phase 48-50 — UI construction + view-model tests (task items 41, 44).

Offscreen Qt construction of the Event Preparation and Race Weekend panels + pure view-model behaviour.
No SessionDB, no Qt event loop; proves the panels build, render empty/populated states, and never raise.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ui import event_preparation_vm as ep_vm
from ui import race_weekend_vm as rw_vm


# --- pure view-models (Qt-free) --------------------------------------------

def test_event_prep_vm_empty_state():
    assert ep_vm.is_empty(None)
    assert ep_vm.is_empty({"ok": False})
    assert "No active event preparation" in ep_vm.header_text(None)
    assert ep_vm.banner_tone(None) == "advisory"


def test_event_prep_vm_populated():
    report = {
        "ok": True,
        "cycle": {"event_name": "Porsche Cup R3", "series": "NGR Porsche Cup", "round": "R3",
                  "state": "active", "current_phase": "setup_development", "days_until_race": 12},
        "next_action": {"headline": "Build race_setup evidence", "tone": "info"},
        "timeline": [{"name": "Event opens", "date": "2026-06-01", "state": "done"},
                     {"name": "Baseline 1", "date": "2026-06-02", "state": "done"},
                     {"name": "Setup experiment", "date": "2026-06-08", "state": "current"},
                     {"name": "Setup Lock", "date": "2026-06-19", "state": "upcoming"}],
        "progress": {"valid_laps": 142, "practice_sessions": 6, "setup_experiments": 3,
                     "coaching_runs": 2, "tyre_samples": 4, "fuel_samples": 2, "race_simulations": 1},
        "readiness": [["race_setup", "developing", "2 exact samples"],
                      ["fuel_evidence", "missing", "no evidence collected"]],
        "setup": {"base": "improving", "qualifying": "provisional", "race": "stable_with_uncertainty"},
        "strategy": {"maturity": "developing", "missing": ["validated long run"]},
    }
    assert not ep_vm.is_empty(report)
    assert "Porsche Cup R3" in ep_vm.header_text(report)
    nodes = ep_vm.timeline_nodes(report)
    assert len(nodes) == 4
    assert nodes[0]["tone"] == "success" and nodes[2]["tone"] == "info"
    cards = ep_vm.progress_cards(report)
    titles = [c["title"] for c in cards]
    assert "Cumulative Programme" in titles and "Setup Convergence" in titles
    assert "Strategy Maturity" in titles and "Readiness" in titles


def test_race_weekend_vm_empty_and_populated():
    assert rw_vm.is_empty(None)
    report = {
        "ok": True, "phase": "final_arrival",
        "arrival": {"event_name": "E", "series": "NGR", "round": "R3", "track": "Fuji",
                    "sessions_completed": 6, "total_valid_laps": 142, "next_required_action": "brief"},
        "scrutineering": {"verdict": "cleared_with_warnings",
                          "checks": [{"name": "livery", "status": "warn"}]},
        "briefing": {"title": "NGR Briefing", "acknowledged": False,
                     "items": [{"topic": "track limits", "detail": "3-strike"}]},
        "race_briefing": {"starting_tyre": "MR", "primary_strategy": "2-stop",
                          "acknowledged": True, "grid_ready": True, "voice_state": "disabled"},
        "debrief": {"result": "P3", "lessons_for_next_event": ["earlier braking T1"]},
    }
    assert not rw_vm.is_empty(report)
    cards = rw_vm.weekend_cards(report)
    titles = [c["title"] for c in cards]
    assert "Final Arrival" in titles and "Virtual Scrutineering" in titles
    assert "Race Briefing" in titles and "Post-Race Debrief" in titles


# --- offscreen Qt construction ---------------------------------------------

@pytest.fixture(scope="module")
def app():
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    a = QApplication.instance() or QApplication([])
    yield a


def test_event_preparation_panel_constructs_and_renders(app):
    from ui.event_preparation_panel import EventPreparationPanel
    panel = EventPreparationPanel()
    panel.update_result(None)  # empty state
    panel.update_result({
        "ok": True,
        "cycle": {"event_name": "Cup R3", "state": "active", "days_until_race": 5},
        "next_action": {"headline": "confirm setup", "tone": "info"},
        "timeline": [{"name": "Race", "date": "2026-06-21", "state": "upcoming"}],
        "progress": {"valid_laps": 100}, "readiness": [["race_setup", "adequate", "ok"]],
        "setup": {"race": "lock_ready"}, "strategy": {"maturity": "provisional", "missing": []},
    })
    panel.update_result(None)  # back to empty; must not raise


def test_race_weekend_panel_constructs_and_renders(app):
    from ui.race_weekend_panel import RaceWeekendPanel
    panel = RaceWeekendPanel()
    panel.update_result(None)
    panel.update_result({"ok": True, "phase": "qualifying",
                         "scrutineering": {"verdict": "garage_hold",
                                           "checks": [{"name": "race number", "status": "fail"}]}})
    panel.update_result(None)


def test_development_history_page_hosts_new_panels(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    assert hasattr(page, "_event_preparation_panel")
    assert hasattr(page, "_race_weekend_panel")
    # page forwarders exist and do not raise on empty input
    page.update_event_preparation(None)
    page.update_race_weekend(None)
