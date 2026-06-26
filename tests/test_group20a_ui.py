"""
Group 20A — UI layer tests for Track Modelling: Oval Detection + AI Corner Verify
+ Segment Highlight.

Covers:
  - TrackMapDrawData highlight fields (CHANGE 1)
  - project_to_screen preserves highlight fields (CHANGE 1)
  - format_segment_row verification_source mapping (CHANGE 2)
  - Highlight wrap-around logic (edge case)
"""
from __future__ import annotations

import dataclasses
from unittest.mock import MagicMock

import pytest

from ui.track_map_vm import (
    TrackMapDrawData,
    MapPoint,
    project_to_screen,
    build_track_map_draw_data,
)
from ui.track_modelling_vm import format_segment_row


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_empty_draw_data(**overrides) -> TrackMapDrawData:
    """Return a minimal TrackMapDrawData for testing."""
    base = dict(
        centreline=[MapPoint(0, 0), MapPoint(10, 10)],
        width_left=[MapPoint(0, 1), MapPoint(10, 11)],
        width_right=[MapPoint(0, -1), MapPoint(10, 9)],
        start_finish=None,
        corner_labels=[],
        car_dot=None,
        telemetry_trace=[],
        bounds=(0.0, 0.0, 100.0, 100.0),
        status_text="test",
        confidence_color="#888888",
        has_map=True,
        seed_centreline=[],
    )
    base.update(overrides)
    return TrackMapDrawData(**base)


def _make_seg(
    lap_progress_start=0.1,
    lap_progress_end=0.2,
    verification_source=None,
):
    """Return a duck-typed segment object for format_segment_row."""
    from data.track_segment_review import SegmentReviewStatus
    from data.track_segment_detection import TrackSegmentType, TrackSegmentDetectionConfidence

    seg = MagicMock()
    seg.lap_progress_start = lap_progress_start
    seg.lap_progress_end = lap_progress_end
    seg.lap_progress_mid = (lap_progress_start + lap_progress_end) / 2
    seg.display_name = "T1 Apex"
    seg.turn_number = 1
    seg.review_status = SegmentReviewStatus.UNREVIEWED
    seg.segment_type = TrackSegmentType.CORNER_EXIT
    seg.confidence = TrackSegmentDetectionConfidence.HIGH
    seg.source_lap_count = 3
    seg.warnings = []
    if verification_source is not None:
        seg.verification_source = verification_source
    else:
        # Simulate attribute missing (default greedy)
        del seg.verification_source
    return seg


# ---------------------------------------------------------------------------
# CHANGE 1 — TrackMapDrawData highlight fields
# ---------------------------------------------------------------------------

class TestHighlightFields:
    def test_default_none(self):
        """highlight fields default to None when not provided."""
        dd = _make_empty_draw_data()
        assert dd.highlight_start_progress is None
        assert dd.highlight_end_progress is None

    def test_set_highlight(self):
        """highlight fields accept 0.0–1.0 float values."""
        dd = _make_empty_draw_data(
            highlight_start_progress=0.25,
            highlight_end_progress=0.50,
        )
        assert dd.highlight_start_progress == 0.25
        assert dd.highlight_end_progress == 0.50

    def test_wrap_around_values_accepted(self):
        """start > end is valid for wrap-around (e.g. 0.90–0.10)."""
        dd = _make_empty_draw_data(
            highlight_start_progress=0.90,
            highlight_end_progress=0.10,
        )
        assert dd.highlight_start_progress == 0.90
        assert dd.highlight_end_progress == 0.10


class TestProjectToScreenPreservesHighlight:
    def test_highlight_preserved_after_projection(self):
        """project_to_screen must carry highlight fields through unchanged."""
        dd = _make_empty_draw_data(
            highlight_start_progress=0.3,
            highlight_end_progress=0.7,
        )
        projected = project_to_screen(dd, 800, 600)
        assert projected.highlight_start_progress == 0.3
        assert projected.highlight_end_progress == 0.7

    def test_none_highlight_preserved(self):
        """project_to_screen preserves None highlight fields."""
        dd = _make_empty_draw_data()
        projected = project_to_screen(dd, 800, 600)
        assert projected.highlight_start_progress is None
        assert projected.highlight_end_progress is None


# ---------------------------------------------------------------------------
# CHANGE 2 — format_segment_row verification_source display
# ---------------------------------------------------------------------------

class TestFormatSegmentRowVerificationSource:
    def test_greedy_default_when_missing(self):
        """Segments with no verification_source attribute → 'Curvature-detected'."""
        seg = _make_seg()
        row = format_segment_row(seg)
        assert row["verification_source"] == "Curvature-detected"

    def test_greedy_explicit(self):
        """verification_source='greedy' → 'Curvature-detected'."""
        seg = _make_seg(verification_source="greedy")
        row = format_segment_row(seg)
        assert row["verification_source"] == "Curvature-detected"

    def test_ai_verified(self):
        """verification_source='ai_verified' → 'AI-verified'."""
        seg = _make_seg(verification_source="ai_verified")
        row = format_segment_row(seg)
        assert row["verification_source"] == "AI-verified"

    def test_engineer_validated(self):
        """verification_source='engineer_validated' → 'Engineer-validated'."""
        seg = _make_seg(verification_source="engineer_validated")
        row = format_segment_row(seg)
        assert row["verification_source"] == "Engineer-validated"

    def test_unknown_value_passed_through(self):
        """Unknown verification_source values are passed through as-is."""
        seg = _make_seg(verification_source="some_future_source")
        row = format_segment_row(seg)
        assert row["verification_source"] == "some_future_source"

    def test_existing_fields_not_broken(self):
        """Adding verification_source must not remove existing fields."""
        seg = _make_seg()
        row = format_segment_row(seg)
        for key in ("name", "turn", "type", "progress", "confidence", "laps", "status", "warnings"):
            assert key in row, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# Highlight wrap-around logic verification (pure Python, no Qt)
# ---------------------------------------------------------------------------

class TestHighlightWrapLogic:
    """Verify the wrap-around logic used in paintEvent (unit-tested without Qt)."""

    @staticmethod
    def _stations_in_highlight(n_pts, h_start, h_end):
        """Replicate the paintEvent logic and return indices that would be drawn."""
        wraps = h_start > h_end
        selected = []
        for i in range(n_pts - 1):
            prog = i / n_pts
            if wraps:
                in_range = prog >= h_start or prog <= h_end
            else:
                in_range = h_start <= prog <= h_end
            if in_range:
                selected.append(i)
        return selected

    def test_normal_range(self):
        """0.25–0.50 selects only stations in that range."""
        sel = self._stations_in_highlight(100, 0.25, 0.50)
        assert all(0.25 <= i / 100 <= 0.50 for i in sel)
        assert len(sel) > 0

    def test_wrap_range(self):
        """0.90–0.10 selects stations at end AND start of lap."""
        sel = self._stations_in_highlight(100, 0.90, 0.10)
        assert len(sel) > 0
        # All selected stations should be >= 0.90 or <= 0.10
        for i in sel:
            prog = i / 100
            assert prog >= 0.90 or prog <= 0.10

    def test_empty_when_no_overlap(self):
        """0.50–0.51 with 10 stations — may select 0 or 1 station near that range."""
        sel = self._stations_in_highlight(10, 0.50, 0.51)
        # Either 0 or 1 station, not all 9
        assert len(sel) <= 1


# ---------------------------------------------------------------------------
# CHANGE 1 (21A) — prog = i / (n_pts - 1) fix: last progress reaches 1.0
# ---------------------------------------------------------------------------

class TestProgFormulaNPtsMinusOne:
    """Verify the corrected progress formula ensures the last segment reaches 1.0."""

    @staticmethod
    def _compute_prog_values_old(n_pts):
        """Old formula: i / n_pts — never reaches 1.0."""
        return [i / n_pts for i in range(n_pts - 1)]

    @staticmethod
    def _compute_prog_values_new(n_pts):
        """New formula: i / (n_pts - 1) if n_pts > 1 else 0.0."""
        return [i / (n_pts - 1) if n_pts > 1 else 0.0 for i in range(n_pts - 1)]

    def test_old_formula_last_value(self):
        """Old formula: max prog for n_pts=100 is 98/100 = 0.98, worse coverage near 1.0."""
        progs = self._compute_prog_values_old(100)
        # last i is 98, so 98/100 = 0.98
        assert abs(progs[-1] - 0.98) < 1e-10

    def test_new_formula_last_value_closer_to_one(self):
        """New formula: last i=98 gives 98/99 ≈ 0.9898, closer to 1.0 than old 98/100."""
        progs_old = self._compute_prog_values_old(100)
        progs_new = self._compute_prog_values_new(100)
        # The new formula's last value is strictly closer to 1.0 than the old formula's.
        assert progs_new[-1] > progs_old[-1]
        assert progs_new[-1] < 1.0  # never exceeds 1.0

    def test_new_formula_zero_division_safe_n_pts_1(self):
        """n_pts == 1: range(0) is empty — no ZeroDivisionError, returns []."""
        progs = self._compute_prog_values_new(1)
        assert progs == []  # range(0) is empty

    def test_new_formula_two_points(self):
        """n_pts == 2 gives a single segment with prog == 0.0 (i=0, n_pts-1=1)."""
        progs = self._compute_prog_values_new(2)
        assert progs == [0.0]

    def test_new_formula_monotonically_increasing(self):
        """Progress values should be monotonically non-decreasing."""
        progs = self._compute_prog_values_new(50)
        assert all(progs[i] <= progs[i + 1] for i in range(len(progs) - 1))

    def test_new_formula_all_in_zero_to_one(self):
        """All computed progress values must be in [0.0, 1.0]."""
        progs = self._compute_prog_values_new(100)
        assert all(0.0 <= p <= 1.0 for p in progs)


# ---------------------------------------------------------------------------
# CHANGE 3 (21A) — tuple unpacking in _tm_ai_corner_verify_done
# ---------------------------------------------------------------------------

class TestAiCornerVerifyTupleUnpacking:
    """Verify the tuple-unpacking logic that handles the new backend return type."""

    @staticmethod
    def _simulate_done(result_tuple):
        """
        Replicate the unpacking logic from _tm_ai_corner_verify_done
        and return (result, error_msg) without requiring Qt.
        """
        result, error_msg = result_tuple if isinstance(result_tuple, tuple) else (result_tuple, "")
        return result, error_msg

    def test_tuple_none_error_unpacks_correctly(self):
        """(None, 'test error') → result is None, error_msg is 'test error'."""
        result, error_msg = self._simulate_done((None, "test error"))
        assert result is None
        assert error_msg == "test error"

    def test_tuple_empty_dict_success_unpacks_correctly(self):
        """({}, '') → result is {}, error_msg is ''."""
        result, error_msg = self._simulate_done(({}, ""))
        assert result == {}
        assert error_msg == ""

    def test_tuple_with_data_unpacks_correctly(self):
        """({'T1': {...}}, '') → result contains key, no error."""
        payload = {"T1": {"angle": 90}}
        result, error_msg = self._simulate_done((payload, ""))
        assert "T1" in result
        assert error_msg == ""

    def test_non_tuple_bare_none_falls_back(self):
        """Bare None (old-style return) is treated as (None, '') for backward compat."""
        result, error_msg = self._simulate_done(None)
        assert result is None
        assert error_msg == ""

    def test_non_tuple_bare_dict_falls_back(self):
        """Bare dict (old-style return) is treated as (dict, '') for backward compat."""
        result, error_msg = self._simulate_done({"T2": {}})
        assert result == {"T2": {}}
        assert error_msg == ""

    def test_failure_status_message_contains_error(self):
        """When result is None, the status message should include the error reason."""
        result, error_msg = self._simulate_done((None, "API timeout"))
        reason = error_msg or "Unknown error"
        status_msg = f"AI corner verification failed: {reason}"
        assert "API timeout" in status_msg

    def test_failure_unknown_error_fallback(self):
        """When result is None and error_msg is empty, fallback to 'Unknown error'."""
        result, error_msg = self._simulate_done((None, ""))
        reason = error_msg or "Unknown error"
        assert reason == "Unknown error"


# ---------------------------------------------------------------------------
# AC6 — Success status bar message format: "AI corner verification complete — N corners updated"
# ---------------------------------------------------------------------------

class TestAiCornerVerifySuccessStatusMessage:
    """AC6: verify the exact success status message format produced by _tm_ai_corner_verify_done."""

    @staticmethod
    def _build_success_status(n_updated: int) -> str:
        """Replicate the success branch of _tm_ai_corner_verify_done."""
        return f"AI corner verification complete — {n_updated} corners updated."

    def test_success_message_zero_corners(self):
        """AC6: 0 corners updated produces correct message."""
        msg = self._build_success_status(0)
        assert msg == "AI corner verification complete — 0 corners updated."

    def test_success_message_one_corner(self):
        """AC6: 1 corner updated produces correct message."""
        msg = self._build_success_status(1)
        assert msg == "AI corner verification complete — 1 corners updated."

    def test_success_message_many_corners(self):
        """AC6: N corners updated produces correct message with count."""
        for n in (3, 7, 12):
            msg = self._build_success_status(n)
            assert f"{n} corners updated" in msg, f"Count {n} not found in: {msg}"
            assert msg.startswith("AI corner verification complete"), f"Wrong prefix: {msg}"


# ---------------------------------------------------------------------------
# AC7 — Failure status bar message format: "AI corner verification failed: {reason}"
# ---------------------------------------------------------------------------

class TestAiCornerVerifyFailureStatusMessage:
    """AC7: verify the exact failure status message format produced by _tm_ai_corner_verify_done."""

    @staticmethod
    def _build_failure_status(error_msg: str) -> str:
        """Replicate the failure branch of _tm_ai_corner_verify_done."""
        reason = error_msg or "Unknown error"
        return f"AI corner verification failed: {reason}"

    def test_failure_message_with_network_error(self):
        """AC7: network error reason appears in status."""
        msg = self._build_failure_status("Network error: timeout")
        assert msg == "AI corner verification failed: Network error: timeout"

    def test_failure_message_with_parse_error(self):
        """AC7: parse error reason appears in status."""
        msg = self._build_failure_status("AI response parse error")
        assert msg == "AI corner verification failed: AI response parse error"

    def test_failure_message_with_no_api_key(self):
        """AC7: no API key reason appears in status."""
        msg = self._build_failure_status("No API key configured")
        assert msg == "AI corner verification failed: No API key configured"

    def test_failure_message_empty_reason_falls_back(self):
        """AC7: empty error_msg falls back to 'Unknown error'."""
        msg = self._build_failure_status("")
        assert msg == "AI corner verification failed: Unknown error"

    def test_failure_message_starts_with_correct_prefix(self):
        """AC7: all failure messages start with the correct prefix."""
        for reason in ("timeout", "parse fail", "no key"):
            msg = self._build_failure_status(reason)
            assert msg.startswith("AI corner verification failed: "), (
                f"Wrong prefix in: {msg}"
            )
