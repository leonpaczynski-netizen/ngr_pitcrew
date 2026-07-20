"""Phase 58 — pit-wall VM + offscreen panel construction (task items 18, 39, 42)."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from strategy.gt7_live_adapter import TrackerRuntimeSnapshot, SelectedActivityContext, evaluate_live_runtime
from strategy.live_runtime_authority import evaluate_runtime_transition
from strategy.ngr_live_pit_wall import build_ngr_live_pit_wall, pit_wall_to_dict, VoiceStatus as VS
from ui import ngr_live_pit_wall_vm as vm


def _view(**tk):
    fields = dict(car="Porsche", track="Fuji", layout="Full", applied_setup_fingerprint="fp",
                  valid_laps=5, last_packet_monotonic=100.0, session_state="running")
    fields.update(tk)
    ctx = SelectedActivityContext(cycle_id="c1", activity_id="exp", activity_type="setup_experiment",
                                  discipline="race", car="Porsche", track="Fuji", layout="Full",
                                  expected_setup_fingerprint="fp", objective="rotation", target_laps=8)
    ev = evaluate_live_runtime(TrackerRuntimeSnapshot(**fields), ctx, now_monotonic=100.5)
    tr = evaluate_runtime_transition(ev, was_running=True)
    pw = build_ngr_live_pit_wall(ev, tr, event_line="NGR Porsche Cup R3", voice_status=VS.DISABLED,
                                 advisory_text="brake earlier into T1")
    return pit_wall_to_dict(pw)


# --- view-model ------------------------------------------------------------

def test_vm_empty_and_idle():
    assert vm.is_empty(None)
    assert vm.is_empty({"ok": True, "mode": "idle"})
    assert "No live activity" in vm.header_text(None)


def test_vm_populated_hierarchy():
    d = _view()
    assert not vm.is_empty(d)
    assert "PRACTICE" in vm.header_text(d)
    titles = [c["title"] for c in vm.hierarchy_cards(d)]
    assert "Context & Setup" in titles and "Telemetry" in titles and "Advisory" in titles
    assert "Evidence Progress" in titles and "Next Action" in titles and "Voice" in titles


def test_vm_suppressed_advisory_shows_suppression():
    d = _view(applied_setup_fingerprint="other")  # blocked -> suppressed
    adv = [c for c in vm.hierarchy_cards(d) if c["title"] == "Advisory"][0]
    assert adv["status_tag"] == "SUPPRESSED"


# --- offscreen construction ------------------------------------------------

@pytest.fixture(scope="module")
def app():
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    a = QApplication.instance() or QApplication([])
    yield a


def test_pit_wall_panel_constructs_and_renders(app):
    from ui.ngr_live_pit_wall_panel import NgrLivePitWallPanel
    panel = NgrLivePitWallPanel()
    panel.update_result(None)         # empty
    panel.update_result(_view())      # populated
    panel.update_result({"ok": True, "mode": "idle"})  # idle
    panel.update_result(None)


def test_development_history_hosts_pit_wall(app):
    from ui.development_history_page import DevelopmentHistoryPage
    page = DevelopmentHistoryPage()
    assert hasattr(page, "_live_pit_wall_panel")
    page.update_live_pit_wall(_view())
    page.update_live_pit_wall(None)
