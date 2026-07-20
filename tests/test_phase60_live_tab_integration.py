"""Phase 60 — production Live-tab placement + track-map (map-match) integration (task items 4, 14, 33)."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from strategy.gt7_live_adapter import TrackerRuntimeSnapshot, SelectedActivityContext
from strategy.live_pit_wall_controller import LivePitWallNavigationContext as NAV
from strategy.live_pit_wall_build import build_live_pit_wall_view
from strategy.runtime_context_resolution import resolve_runtime_context


def _ctx():
    return SelectedActivityContext(cycle_id="c1", activity_id="exp", activity_type="setup_experiment",
                                   discipline="race", car="Porsche", track="Fuji", layout="Full",
                                   expected_setup_fingerprint="fp", event_context_digest="ctx",
                                   run_plan_fingerprint="rp", target_laps=8)


# --- track-map (map-match confidence) integration --------------------------

def test_high_map_confidence_confirms_layout_enables_exact():
    r = resolve_runtime_context(tracker_car="Porsche", tracker_track="Fuji", tracker_layout="Full",
                                map_match_confidence=0.95, expected_car="Porsche", expected_track="Fuji",
                                expected_layout="Full", expected_context_digest="ctx",
                                applied_setup_fingerprint="fp", expected_setup_fingerprint="fp")
    tracker = TrackerRuntimeSnapshot(car="Porsche", track="Fuji", layout="Full",
                                     applied_setup_fingerprint="fp", live_context_digest=r.live_context_digest,
                                     tyre_compound="MR", valid_laps=3, last_packet_monotonic=100.0,
                                     map_match_confidence=0.95)
    nav = NAV(active_event_id="c1", selected_activity_id="exp", started=True)
    v = build_live_pit_wall_view(tracker, _ctx(), nav, was_running=True, now_monotonic=100.5)
    assert v["production_state"] == "exact_match"


def test_low_map_confidence_keeps_layout_limited():
    r = resolve_runtime_context(tracker_car="Porsche", tracker_track="Fuji", tracker_layout="Full",
                                map_match_confidence=0.2, expected_car="Porsche", expected_track="Fuji",
                                expected_layout="Full", expected_context_digest="ctx",
                                applied_setup_fingerprint="fp", expected_setup_fingerprint="fp")
    tracker = TrackerRuntimeSnapshot(car="Porsche", track="Fuji", layout="Full",
                                     applied_setup_fingerprint="fp", live_context_digest=r.live_context_digest,
                                     tyre_compound="MR", valid_laps=3, last_packet_monotonic=100.0,
                                     map_match_confidence=0.2)
    nav = NAV(active_event_id="c1", selected_activity_id="exp", started=True)
    v = build_live_pit_wall_view(tracker, _ctx(), nav, was_running=True, now_monotonic=100.5)
    assert v["production_state"] == "limited_match"  # layout unconfirmed -> not exact


# --- Live-tab placement ----------------------------------------------------

@pytest.fixture(scope="module")
def app():
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    a = QApplication.instance() or QApplication([])
    yield a


def test_pit_wall_snapshot_from_tracker_is_immutable_read(app):
    # a stub with a minimal tracker -> _build_tracker_runtime_snapshot reads it without creating anything
    import ui.dashboard as dash

    class _Tracker:
        car_name = "Porsche"; track = "Fuji"; layout_id = "Full"; laps_recorded = 4; in_pit = False

    class _Stub:
        pass
    stub = _Stub.__new__(_Stub)
    stub._tracker = _Tracker()
    snap = dash.MainWindow._build_tracker_runtime_snapshot(stub)
    assert snap.car == "Porsche" and snap.track == "Fuji" and snap.lap == 4


def test_refresh_no_panel_is_safe():
    import ui.dashboard as dash

    class _Stub:
        pass
    stub = _Stub.__new__(_Stub)
    stub._live_pit_wall_panel = None
    # refresh with no panel must not raise
    dash.MainWindow._refresh_live_pit_wall(stub)
