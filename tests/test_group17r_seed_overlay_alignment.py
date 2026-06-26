"""GROUP 17R — Seed Map Overlay, True Map Alignment, and Recalibration Workflow.

Tests covering:
  DEF-17R-001  Corner labels are curvature peaks, not verified positions
  DEF-17R-002  seed_overlay_note set in TrackMapDrawData when positions unavailable
  DEF-17R-003  Seed truth source displayed in alignment panel
  DEF-17R-004  Old "corner count mismatch" warnings suppressed when station map is authoritative
  DEF-17R-005  Rebuild/Recalibrate clears station map state
  DEF-17R-006  Lap offset calibration status labels and explanations

Pure Python — no PyQt6 dependency.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional
from unittest.mock import MagicMock, patch

import pytest

from ui.track_map_vm import (
    MapPoint,
    CornerLabel,
    TrackMapDrawData,
    build_track_map_draw_data,
    project_to_screen,
)
from ui.track_model_alignment_vm import (
    format_alignment_summary,
    get_acceptance_button_states,
)
from data.track_model_alignment import (
    TrackModelAlignmentResult,
    TrackModelMatchStatus,
    SectorAlignmentResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_station_map(
    seed_corner_positions_available: bool = False,
    n_corners: int = 12,
    n_stations: int = 50,
) -> MagicMock:
    """Minimal TrackStationMap-like object for testing draw-data generation."""
    sm = MagicMock()
    sm.stations = [
        MagicMock(
            x=math.cos(i * 2 * math.pi / n_stations),
            z=math.sin(i * 2 * math.pi / n_stations),
            station_m=float(i),
            heading_rad=0.0,
            left_width_m=5.0,
            right_width_m=5.0,
        )
        for i in range(n_stations)
    ]
    sm.track_location_id = "test_track"
    sm.layout_id = "test__layout"
    sm.default_track_width_m = 10.0
    sm.seed_corner_positions_available = seed_corner_positions_available
    sm.seeded_corners = [
        MagicMock(
            corner_id=f"T{i + 1}",
            approx_station_m=float(i * 4),
            is_seeded_placeholder=False,
        )
        for i in range(n_corners)
    ]
    return sm


def _make_alignment_result(
    seed_positions_available: bool,
    match_status: TrackModelMatchStatus = TrackModelMatchStatus.GOOD_MATCH,
    n_expected: int = 12,
    n_matched: int = 0,
) -> TrackModelAlignmentResult:
    return TrackModelAlignmentResult(
        match_status=match_status,
        seed_corners_expected=n_expected,
        model_corners_found=n_expected,
        extra_peaks_suppressed=0,
        placeholder_count=0,
        lap_length_m_model=5800.0,
        lap_length_m_seed=5800.0,
        lap_length_delta_pct=0.0,
        station_count=5800,
        confidence=0.85,
        corner_alignments=[],
        sector_alignment=SectorAlignmentResult(seed_sector_count=0, status="not_available", note=""),
        blockers=[],
        warnings=[],
        accepted=False,
        accepted_at="",
        seed_corner_positions_available=seed_positions_available,
        corners_matched=n_matched,
        corner_position_match="NOT_AVAILABLE" if not seed_positions_available else "PASS",
        corner_candidate_matches=[],
    )


# ---------------------------------------------------------------------------
# DEF-17R-002: seed_overlay_note in TrackMapDrawData
# ---------------------------------------------------------------------------

class TestSeedOverlayNote:
    """build_track_map_draw_data() sets seed_overlay_note correctly."""

    def test_note_set_when_positions_unavailable(self):
        sm = _make_station_map(seed_corner_positions_available=False)
        dd = build_track_map_draw_data(sm)
        assert dd.seed_overlay_note != ""
        assert "curvature peaks" in dd.seed_overlay_note.lower()

    def test_note_empty_when_positions_available(self):
        sm = _make_station_map(seed_corner_positions_available=True)
        dd = build_track_map_draw_data(sm)
        assert dd.seed_overlay_note == ""

    def test_note_set_on_empty_map(self):
        dd = build_track_map_draw_data(None)
        # Empty map — note field should exist (defaults to "")
        assert hasattr(dd, "seed_overlay_note")

    def test_note_mentions_telemetry_model(self):
        sm = _make_station_map(seed_corner_positions_available=False)
        dd = build_track_map_draw_data(sm)
        assert "telemetry" in dd.seed_overlay_note.lower()

    def test_note_absent_when_map_is_none(self):
        dd = build_track_map_draw_data(None)
        # The empty draw data should have the field with empty string default
        assert dd.seed_overlay_note == ""


class TestProjectToScreenPreservesNote:
    """project_to_screen() passes seed_overlay_note through unchanged."""

    def test_note_preserved_when_positions_unavailable(self):
        sm = _make_station_map(seed_corner_positions_available=False, n_stations=20)
        dd = build_track_map_draw_data(sm)
        projected = project_to_screen(dd, canvas_w=800, canvas_h=600)
        assert projected.seed_overlay_note == dd.seed_overlay_note

    def test_note_empty_preserved_when_positions_available(self):
        sm = _make_station_map(seed_corner_positions_available=True, n_stations=20)
        dd = build_track_map_draw_data(sm)
        projected = project_to_screen(dd, canvas_w=800, canvas_h=600)
        assert projected.seed_overlay_note == ""

    def test_custom_note_preserved(self):
        sm = _make_station_map(seed_corner_positions_available=False, n_stations=10)
        dd = build_track_map_draw_data(sm)
        # Verify whatever note was set survives projection
        original_note = dd.seed_overlay_note
        projected = project_to_screen(dd, canvas_w=400, canvas_h=300)
        assert projected.seed_overlay_note == original_note


# ---------------------------------------------------------------------------
# DEF-17R-003: Seed truth source in format_alignment_summary
# ---------------------------------------------------------------------------

class TestSeedTruthSource:
    """format_alignment_summary() includes seed_truth_source key."""

    def test_key_present_in_summary(self):
        result = _make_alignment_result(seed_positions_available=False)
        summary = format_alignment_summary(result)
        assert "seed_truth_source" in summary

    def test_metadata_only_when_no_seed_positions(self):
        result = _make_alignment_result(seed_positions_available=False)
        summary = format_alignment_summary(result)
        assert "metadata only" in summary["seed_truth_source"].lower()

    def test_corner_windows_when_positions_available(self):
        result = _make_alignment_result(
            seed_positions_available=True,
            match_status=TrackModelMatchStatus.ACCEPTABLE_MATCH,
            n_matched=12,
        )
        summary = format_alignment_summary(result)
        assert "corner windows" in summary["seed_truth_source"].lower()
        assert "12" in summary["seed_truth_source"]

    def test_seed_truth_source_dash_when_result_none(self):
        summary = format_alignment_summary(None)
        assert summary["seed_truth_source"] == "—"

    def test_no_coordinate_data_message_when_unavailable(self):
        result = _make_alignment_result(seed_positions_available=False)
        summary = format_alignment_summary(result)
        # Should mention that coordinate/window data is missing
        note = summary["seed_truth_source"].lower()
        assert "no coordinate" in note or "no window" in note or "metadata only" in note


# ---------------------------------------------------------------------------
# DEF-17R-001: Seed position status is explicit about curvature peaks
# ---------------------------------------------------------------------------

class TestSeedPositionStatusExplicit:
    """seed_position_status text is informative when positions are unavailable."""

    def test_position_status_mentions_curvature_peaks_when_unavailable(self):
        result = _make_alignment_result(seed_positions_available=False)
        summary = format_alignment_summary(result)
        status = summary["seed_position_status"].lower()
        assert "curvature peaks" in status or "not verified" in status

    def test_position_status_shows_matched_count_when_available(self):
        result = _make_alignment_result(
            seed_positions_available=True,
            match_status=TrackModelMatchStatus.ACCEPTABLE_MATCH,
            n_matched=11,
        )
        summary = format_alignment_summary(result)
        assert "11" in summary["seed_position_status"]
        assert "12" in summary["seed_position_status"]

    def test_corners_matched_na_when_positions_unavailable(self):
        result = _make_alignment_result(seed_positions_available=False)
        summary = format_alignment_summary(result)
        assert "N/A" in summary["corners_matched"] or "no seed" in summary["corners_matched"].lower()

    def test_corners_matched_shows_fraction_when_available(self):
        result = _make_alignment_result(
            seed_positions_available=True,
            match_status=TrackModelMatchStatus.GOOD_MATCH,
            n_matched=10,
        )
        summary = format_alignment_summary(result)
        assert "10" in summary["corners_matched"]


# ---------------------------------------------------------------------------
# DEF-17R-004: Old count-mismatch warning suppression logic
# ---------------------------------------------------------------------------

class TestWarningSuppressionLogic:
    """Demonstrate the filtering used for old detect_track_segments() warnings.

    The actual suppression happens in dashboard._tm_detect_segments_safe(), which
    is a Qt method.  These tests verify the filter predicate independently.
    """

    _MISMATCH_WARNINGS = [
        "Corner count mismatch: detected 5, expected 12 (diff 7). Record more calibration laps.",
        "Detected 5 corners vs expected 12 (difference 7) — missing corners may need more calibration laps",
    ]
    _SAFE_WARNINGS = [
        "Low confidence — only 2 usable laps",
        "Speed drop threshold may be too aggressive",
    ]

    def _suppress(self, warnings: list[str], station_map_authoritative: bool) -> list[str]:
        if not station_map_authoritative:
            return warnings
        return [
            w for w in warnings
            if "Corner count mismatch" not in w
            and "corners vs expected" not in w
        ]

    def test_mismatch_warning_removed_when_station_map_present(self):
        all_warns = self._MISMATCH_WARNINGS + self._SAFE_WARNINGS
        result = self._suppress(all_warns, station_map_authoritative=True)
        for w in self._MISMATCH_WARNINGS:
            assert w not in result

    def test_safe_warnings_preserved_when_station_map_present(self):
        all_warns = self._MISMATCH_WARNINGS + self._SAFE_WARNINGS
        result = self._suppress(all_warns, station_map_authoritative=True)
        for w in self._SAFE_WARNINGS:
            assert w in result

    def test_all_warnings_preserved_without_station_map(self):
        all_warns = self._MISMATCH_WARNINGS + self._SAFE_WARNINGS
        result = self._suppress(all_warns, station_map_authoritative=False)
        assert result == all_warns

    def test_empty_list_survives_suppression(self):
        assert self._suppress([], station_map_authoritative=True) == []

    def test_only_mismatch_warnings_returns_empty(self):
        result = self._suppress(self._MISMATCH_WARNINGS, station_map_authoritative=True)
        assert result == []


# ---------------------------------------------------------------------------
# DEF-17R-005: Rebuild state — format_alignment_summary for None result
# ---------------------------------------------------------------------------

class TestRebuildState:
    """After clearing the station map, format_alignment_summary(None) shows Not built."""

    def test_workflow_state_is_not_built_after_clear(self):
        # Simulate the state after _tm_rebuild_model() clears the result
        summary = format_alignment_summary(None)
        assert summary["workflow_state"] == "Not built"

    def test_match_status_is_dash_after_clear(self):
        summary = format_alignment_summary(None)
        assert summary["match_status"] == "—"

    def test_accept_button_disabled_without_station_map(self):
        states = get_acceptance_button_states(None, has_station_map=False)
        assert states["accept"] is False
        assert states["rebuild"] is False

    def test_rebuild_button_disabled_without_station_map(self):
        states = get_acceptance_button_states(None, has_station_map=False)
        assert states["rebuild"] is False

    def test_workflow_shows_not_built_when_result_is_not_ready(self):
        result = TrackModelAlignmentResult(
            match_status=TrackModelMatchStatus.NOT_READY,
            seed_corners_expected=0,
            model_corners_found=0,
            extra_peaks_suppressed=0,
            placeholder_count=0,
            lap_length_m_model=0.0,
            lap_length_m_seed=0.0,
            lap_length_delta_pct=0.0,
            station_count=0,
            confidence=0.0,
            corner_alignments=[],
            sector_alignment=SectorAlignmentResult(seed_sector_count=0, status="not_available", note=""),
            blockers=[],
            warnings=[],
            accepted=False,
            accepted_at="",
            seed_corner_positions_available=False,
            corners_matched=0,
            corner_position_match="NOT_AVAILABLE",
            corner_candidate_matches=[],
        )
        summary = format_alignment_summary(result)
        assert summary["workflow_state"] == "Not built"


# ---------------------------------------------------------------------------
# DEF-17R-006: Lap offset status — format_lap_offset_status
# ---------------------------------------------------------------------------

class TestLapOffsetStatusLabels:
    """format_lap_offset_status() returns explicit status labels."""

    def test_not_loaded_status_when_no_calibration(self):
        from ui.track_modelling_vm import format_lap_offset_status
        info = format_lap_offset_status(None, track_length_m=5800.0)
        assert "No offset calibration" in info["status"] or "not loaded" in info["status"].lower()

    def test_provisional_note_present_without_calibration(self):
        from ui.track_modelling_vm import format_lap_offset_status
        info = format_lap_offset_status(None, track_length_m=5800.0)
        assert info["provisional_note"] != ""

    def test_track_length_shown_when_provided(self):
        from ui.track_modelling_vm import format_lap_offset_status
        info = format_lap_offset_status(None, track_length_m=5800.0)
        assert "5800" in info["track_length"]

    def test_track_length_unknown_when_not_provided(self):
        from ui.track_modelling_vm import format_lap_offset_status
        info = format_lap_offset_status(None, track_length_m=None)
        assert "Unknown" in info["track_length"] or "—" in info["track_length"]

    def test_zero_offset_status_is_provisional(self):
        from ui.track_modelling_vm import format_lap_offset_status
        cal = MagicMock()
        cal.offset_m = 0.0
        cal.confidence = MagicMock(value="low")
        cal.calibration_source = "zero_offset"
        cal.warnings = []
        cal.track_length_m = 5800.0
        info = format_lap_offset_status(cal, track_length_m=5800.0)
        assert "provisional" in info["status"].lower() or "zero" in info["status"].lower()

    def test_calibrated_status_when_confidence_high(self):
        from ui.track_modelling_vm import format_lap_offset_status
        cal = MagicMock()
        cal.offset_m = 42.5
        cal.confidence = MagicMock(value="high")
        cal.calibration_source = "measured_lap"
        cal.warnings = []
        cal.track_length_m = 5800.0
        info = format_lap_offset_status(cal, track_length_m=5800.0)
        assert "calibrated" in info["status"].lower()


# ---------------------------------------------------------------------------
# Backward compat / structural
# ---------------------------------------------------------------------------

class TestTrackMapDrawDataStructure:
    """TrackMapDrawData has the seed_overlay_note field."""

    def test_seed_overlay_note_field_exists(self):
        dd = TrackMapDrawData(
            centreline=[], width_left=[], width_right=[],
            start_finish=None, corner_labels=[], car_dot=None,
            telemetry_trace=[], bounds=(0.0, 0.0, 1.0, 1.0),
            status_text="test", confidence_color="#888",
        )
        assert hasattr(dd, "seed_overlay_note")

    def test_seed_overlay_note_defaults_to_empty(self):
        dd = TrackMapDrawData(
            centreline=[], width_left=[], width_right=[],
            start_finish=None, corner_labels=[], car_dot=None,
            telemetry_trace=[], bounds=(0.0, 0.0, 1.0, 1.0),
            status_text="test", confidence_color="#888",
        )
        assert dd.seed_overlay_note == ""

    def test_seed_overlay_note_can_be_set(self):
        dd = TrackMapDrawData(
            centreline=[], width_left=[], width_right=[],
            start_finish=None, corner_labels=[], car_dot=None,
            telemetry_trace=[], bounds=(0.0, 0.0, 1.0, 1.0),
            status_text="test", confidence_color="#888",
            seed_overlay_note="custom note",
        )
        assert dd.seed_overlay_note == "custom note"

    def test_build_draw_data_has_map_false_when_none(self):
        dd = build_track_map_draw_data(None)
        assert dd.has_map is False

    def test_build_draw_data_has_map_true_when_station_map_provided(self):
        sm = _make_station_map(n_stations=10)
        dd = build_track_map_draw_data(sm)
        assert dd.has_map is True
