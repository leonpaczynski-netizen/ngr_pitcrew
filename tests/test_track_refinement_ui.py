"""Headless smoke test for the Track Modelling 'Continuous Refinement' panel (UAT #6, Phase 1b).

Builds the real MainWindow offscreen against an isolated temp config, points the
refinement model dir at a temp dir, and drives the panel handlers.
Skipped when PyQt6 isn't importable.
"""
from __future__ import annotations

import os
import queue
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6", reason="PyQt6 not available for headless smoke test")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

import config_paths as cp  # noqa: E402
import data.track_model_alignment as tma  # noqa: E402
import data.track_refinement as tr  # noqa: E402
from data.track_model_alignment import (  # noqa: E402
    SectorAlignmentResult, TrackModelAlignmentResult, TrackModelMatchStatus,
    export_accepted_model_json,
)

LOC, LAY = "fuji", "fuji__full_course"


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def _main_window(qapp, tmp_path_factory):
    # Construct MainWindow ONCE per module — repeated construction segfaults PyQt
    # on Windows/Py3.14.
    cfg_path = str(tmp_path_factory.mktemp("refine_ui") / "config.json")
    cp.write_default_config(cfg_path)
    from ui.dashboard import MainWindow, SignalBridge
    win = MainWindow(
        config=cp.load_config(cfg_path), logger=MagicMock(), announcer=MagicMock(),
        bridge=SignalBridge(), ui_queue=queue.Queue(), config_path=cfg_path, db=None,
    )
    win._tm_refine_ids = lambda: (LOC, LAY)
    yield win


@pytest.fixture()
def window(_main_window, tmp_path, monkeypatch):
    # Fresh temp model dir per test; point BOTH dir bindings at it so the panel
    # never touches real data. Reset per-test refinement state on the shared window.
    monkeypatch.setattr(tma, "STATION_MODELS_DIR", tmp_path, raising=False)
    monkeypatch.setattr(tr, "STATION_MODELS_DIR", tmp_path, raising=False)
    _main_window._tmp_models = tmp_path
    _main_window._track_path_capture = None
    _main_window._tm_refine_status_lbl.setText("—")
    _main_window._tm_refine_result_lbl.setText("")
    yield _main_window


def _mk_align(**over):
    base = dict(
        match_status=TrackModelMatchStatus.GOOD_MATCH, seed_corners_expected=16,
        model_corners_found=16, extra_peaks_suppressed=0, placeholder_count=0,
        lap_length_m_model=4440.0, lap_length_m_seed=4563.0, lap_length_delta_pct=2.68,
        station_count=4441, confidence=1.0, corner_alignments=[],
        sector_alignment=SectorAlignmentResult(0, "not_available", ""), blockers=[],
        warnings=[], accepted=True, accepted_at="2026-07-12T09:00:00+00:00",
    )
    base.update(over)
    return TrackModelAlignmentResult(**base)


def test_panel_widgets_exist(window):
    for attr in ("_tm_btn_refine_capture", "_tm_btn_refine_now", "_tm_btn_refine_accept",
                 "_tm_btn_refine_discard", "_tm_refine_status_lbl", "_tm_refine_result_lbl"):
        assert hasattr(window, attr), attr
    assert window._track_path_capture is None


def test_capture_requires_accepted_model(window):
    # No accepted model in the temp dir → toggling capture is refused gracefully.
    window._tm_toggle_refine_capture()
    assert window._track_path_capture is None
    assert "No accepted model" in window._tm_refine_status_lbl.text()


def test_capture_starts_when_accepted_model_present(window):
    export_accepted_model_json(_mk_align(), LOC, LAY, output_dir=window._tmp_models)
    window._tm_toggle_refine_capture()
    assert window._track_path_capture is not None
    assert window._track_path_capture.matches(LOC, LAY)
    assert "Capturing" in window._tm_refine_status_lbl.text()
    # Stop → refine. Empty capture → graceful "no usable laps" and capture cleared.
    window._tm_toggle_refine_capture()
    assert window._track_path_capture is None
    assert "No refinement" in window._tm_refine_status_lbl.text()


def test_poll_ui_queue_feeds_active_capture(window):
    # Verify the global per-packet hook feeds the capture (mirrors _raw_rd_capture).
    calls = {"n": 0}

    class _StubCapture:
        def add_packet(self, packet, lap_number):
            calls["n"] += 1
            return True

    window._track_path_capture = _StubCapture()
    # Stub the per-frame work that would choke on a bare sentinel packet — we are
    # only exercising the capture hook here.
    window._update_live = lambda p: None
    window._refresh_strategy_fuel_column = lambda: None
    window._refresh_gear_ratios = lambda: None
    window._update_telemetry_labels = lambda: None
    window._ui_queue.put(object())
    window._poll_ui_queue()
    assert calls["n"] == 1
    window._track_path_capture = None


def test_refresh_panel_offers_improving_candidate(window):
    export_accepted_model_json(_mk_align(model_corners_found=15), LOC, LAY,
                               output_dir=window._tmp_models)
    cand = _mk_align(model_corners_found=16, accepted=False)
    tr.export_candidate_model_json(
        cand, LOC, LAY,
        {"base_accepted_at": "2026-07-12T09:00:00+00:00", "contributing_laps": 3,
         "improves": True, "improvement_reasons": ["more corners found (16 > 15)"]},
        output_dir=window._tmp_models,
    )
    window._tm_refresh_refinement_panel()
    assert "Refined model available" in window._tm_refine_status_lbl.text()
    assert window._tm_btn_refine_accept.isEnabled()
    assert window._tm_btn_refine_discard.isEnabled()


def test_accept_promotes_candidate(window):
    from data.track_model_alignment import import_accepted_model_json, find_accepted_model_path
    export_accepted_model_json(_mk_align(model_corners_found=15), LOC, LAY,
                               output_dir=window._tmp_models)
    cand = _mk_align(model_corners_found=16, accepted=False)
    tr.export_candidate_model_json(
        cand, LOC, LAY, {"base_accepted_at": "2026-07-12T09:00:00+00:00", "improves": True},
        output_dir=window._tmp_models,
    )
    window._tm_accept_refinement()
    assert "accepted" in window._tm_refine_status_lbl.text().lower()
    promoted = import_accepted_model_json(find_accepted_model_path(LOC, LAY, base_dir=window._tmp_models))
    assert promoted.model_corners_found == 16
    assert tr.find_candidate_model_path(LOC, LAY, base_dir=window._tmp_models) is None


def test_discard_removes_candidate(window):
    export_accepted_model_json(_mk_align(), LOC, LAY, output_dir=window._tmp_models)
    tr.export_candidate_model_json(_mk_align(accepted=False), LOC, LAY, {}, output_dir=window._tmp_models)
    window._tm_discard_refinement()
    assert tr.find_candidate_model_path(LOC, LAY, base_dir=window._tmp_models) is None
    assert "discarded" in window._tm_refine_status_lbl.text().lower()
