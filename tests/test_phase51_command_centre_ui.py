"""Phase 51 — Command Centre view-model + offscreen panel construction (task items 30, 33)."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from strategy.active_cycle_resolution import CycleCandidate, resolve_active_cycle
from strategy.event_command_centre import build_event_command_centre, command_centre_to_dict
from ui import event_command_centre_vm as vm


def _view(**kw):
    r = resolve_active_cycle([CycleCandidate("a", explicit_state="active", event_name="Cup R3",
                                             series="NGR Porsche Cup", round_label="R3",
                                             official_race_date="2026-06-21")],
                             selected_cycle_id="a", now_date="2026-06-11")
    report = {"ok": True, "cycle": {"event_name": "Cup R3", "series": "NGR Porsche Cup", "round": "R3",
                                    "state": "active", "current_phase": "setup_development",
                                    "official_race_date": "2026-06-21"},
              "next_action": {"headline": "Build race_setup evidence", "rationale": "weakest"},
              "timeline": [{"name": "Race", "date": "2026-06-21", "state": "upcoming"}],
              "progress": {"valid_laps": 100, "practice_sessions": 6},
              "readiness": [["race_setup", "developing", "2 exact"]],
              "setup": {"race": "improving"}, "strategy": {"maturity": "developing"}}
    cc = build_event_command_centre(r, report, now_date="2026-06-11", **kw)
    return command_centre_to_dict(cc)


# --- view-model ------------------------------------------------------------

def test_vm_loading_state():
    assert vm.is_loading({"loading": True})
    assert "Loading" in vm.header_text({"loading": True})


def test_vm_empty_state():
    assert vm.is_empty(None)
    assert "No active NGR event" in vm.header_text(None)


def test_vm_populated_sections():
    d = _view()
    assert not vm.is_empty(d)
    assert "Cup R3" in vm.header_text(d)
    assert vm.next_action_card(d)["lines"][0] == "Build race_setup evidence"
    assert vm.progress_card(d)["title"] == "Cumulative Learning"
    assert len(vm.timeline_nodes(d)) == 1
    assert len(vm.quick_actions(d)) >= 5
    assert len(vm.readiness_rows(d)) == 1


def test_vm_candidate_rows_only_when_selection_required():
    # single selected -> no selector
    assert vm.candidate_rows(_view()) == []
    # multiple active -> selector rows
    r = resolve_active_cycle([CycleCandidate("a", explicit_state="active", event_name="A"),
                              CycleCandidate("b", explicit_state="active", event_name="B")])
    d = command_centre_to_dict(build_event_command_centre(r, None))
    rows = vm.candidate_rows(d)
    assert {row["cycle_id"] for row in rows} == {"a", "b"}


# --- offscreen panel construction ------------------------------------------

@pytest.fixture(scope="module")
def app():
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    a = QApplication.instance() or QApplication([])
    yield a


def test_panel_constructs_and_renders(app):
    from ui.event_command_centre_panel import EventCommandCentrePanel
    panel = EventCommandCentrePanel()
    panel.update_result(None)                       # empty
    panel.update_result({"loading": True})          # loading
    panel.update_result(_view())                    # populated
    panel.update_result(None)                       # back to empty; must not raise


def test_panel_navigation_and_selection_handlers(app):
    from ui.event_command_centre_panel import EventCommandCentrePanel
    calls = {"nav": [], "sel": []}
    panel = EventCommandCentrePanel()
    panel.set_handlers(navigate=lambda s: calls["nav"].append(s),
                       select=lambda c: calls["sel"].append(c))
    # multiple-active view renders a selector with Select buttons
    r = resolve_active_cycle([CycleCandidate("a", explicit_state="active", event_name="A"),
                              CycleCandidate("b", explicit_state="active", event_name="B")])
    panel.update_result(command_centre_to_dict(build_event_command_centre(r, None)))
    # find and click a Select button + a quick-action button
    from PyQt6.QtWidgets import QPushButton
    buttons = panel.findChildren(QPushButton)
    assert buttons, "expected buttons rendered"
    for b in buttons:
        b.click()
    assert calls["sel"] or calls["nav"]  # at least one handler fired
