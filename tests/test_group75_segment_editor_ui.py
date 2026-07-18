"""UAT Finding 4 completion — interactive segment editor through the real UI."""
from __future__ import annotations

import os
import queue
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6", reason="PyQt6 not available for headless UI test")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402
import config_paths as cp  # noqa: E402

from data.track_segment_review import (
    TrackModelReviewResult, ReviewedTrackSegment, SegmentReviewStatus,
)
from data.track_segment_detection import (
    TrackSegmentType, TrackSegmentDetectionConfidence,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp, tmp_path):
    cfg = str(tmp_path / "config.json")
    cp.write_default_config(cfg)
    from ui.dashboard import MainWindow, SignalBridge
    win = MainWindow(config=cp.load_config(cfg), logger=MagicMock(),
                     announcer=MagicMock(), bridge=SignalBridge(),
                     ui_queue=queue.Queue(), config_path=cfg, db=None)
    win._query_listener = None
    yield win
    win.close()


def _seg(seg_id, lo, hi, name, turn=None):
    return ReviewedTrackSegment(
        segment_id=seg_id, segment_type=TrackSegmentType.APEX_ZONE,
        original_display_name=name, lap_progress_start=lo, lap_progress_end=hi,
        lap_progress_mid=(lo + hi) / 2,
        confidence=TrackSegmentDetectionConfidence.MEDIUM, turn_number=turn)


def _seed_review(win):
    win._tm_review_result = TrackModelReviewResult(
        track_location_id="fuji", layout_id="full_course", calibration_car_id=None,
        source_lap_count=5, detected_corner_count=3, expected_corner_count=3,
        detection_confidence=TrackSegmentDetectionConfidence.MEDIUM,
        segments=[_seg("t1", 0.10, 0.18, "Turn 1", 1),
                  _seg("t1b", 0.18, 0.24, "Turn 1b", 1),
                  _seg("t2", 0.40, 0.50, "Turn 2", 2)])
    win._tm_refresh_seg_table()


def test_editor_widgets_exist(window):
    assert hasattr(window, "_tm_seg_name_edit")
    assert hasattr(window, "_tm_btn_seg_merge")
    assert hasattr(window, "_tm_btn_seg_split")


def test_rename_through_ui(window):
    _seed_review(window)
    window._tm_selected_segment_id = "t1"
    window._tm_seg_name_edit.setText("Hairpin")
    window._tm_seg_rename()
    seg = next(s for s in window._tm_review_result.segments if s.segment_id == "t1")
    assert seg.display_name == "Hairpin"


def test_renumber_through_ui(window):
    _seed_review(window)
    window._tm_selected_segment_id = "t2"
    window._tm_seg_turn_spin.setValue(3)
    window._tm_seg_renumber()
    seg = next(s for s in window._tm_review_result.segments if s.segment_id == "t2")
    assert seg.turn_number == 3


def test_merge_through_ui(window):
    _seed_review(window)
    window._tm_selected_segment_id = "t1"
    n_before = len(window._tm_review_result.segments)
    window._tm_seg_merge()  # merge t1 with next (t1b)
    assert len(window._tm_review_result.segments) == n_before - 1
    assert not any(s.segment_id == "t1b" for s in window._tm_review_result.segments)


def test_split_through_ui(window):
    _seed_review(window)
    window._tm_selected_segment_id = "t2"
    window._tm_seg_split()
    ids = [s.segment_id for s in window._tm_review_result.segments]
    assert "t2__a" in ids and "t2__b" in ids
    assert "t2" not in ids


def test_reject_and_approve_through_ui(window):
    _seed_review(window)
    window._tm_selected_segment_id = "t1b"
    window._tm_seg_reject()
    assert next(s for s in window._tm_review_result.segments
                if s.segment_id == "t1b").review_status is SegmentReviewStatus.REJECTED
    window._tm_selected_segment_id = "t1"
    window._tm_seg_approve()
    assert next(s for s in window._tm_review_result.segments
                if s.segment_id == "t1").review_status is SegmentReviewStatus.CONFIRMED


def test_edit_without_selection_is_safe(window):
    _seed_review(window)
    window._tm_selected_segment_id = None
    window._tm_seg_rename()  # must not raise
    assert "Select a segment" in window._tm_seg_edit_status.text()
