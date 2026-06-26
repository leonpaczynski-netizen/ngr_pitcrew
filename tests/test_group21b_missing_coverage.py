"""Group 21B — Pit Lane Mapping: additional tests for missing AC coverage.

Covers:
  AC1 — build_reference_path() excludes pit-in laps from reference path building
  AC3 — detect_track_segments() injects exactly one PIT_LANE segment per station map
  AC5 — build_track_map_draw_data() populates pit_lane_polyline from station_map.pit_lane
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# AC1 — build_reference_path excludes pit laps
# ---------------------------------------------------------------------------

from unittest.mock import patch

from data.track_calibration import (
    CalibrationLap,
    CalibrationLapQuality,
    CalibrationSession,
    TelemetrySample,
    build_reference_path,
)


def _make_normal_lap(lap_num: int) -> CalibrationLap:
    """A lap where every sample stays well within 30 m of the lap centroid.

    Samples trace a small circle of radius 20 m centred at (100, 0, 100).
    Using a non-zero centre avoids (x=0, y=0, z=0) which would trip the
    has_valid_xyz() check.  Radius 20 m < 60 m pit threshold.

    - 5 400 samples at 60 Hz = 90 s → lap_time_ms = 86 400 ms
    - Smooth circle: arc step ≈ 0.023 m — no coordinate jumps.
    """
    hz = 60
    n = hz * 90        # 5 400
    interval_ms = 1000 // hz
    radius = 20.0
    cx, cz = 100.0, 100.0

    samples: list[TelemetrySample] = []
    for i in range(n):
        angle = 2.0 * math.pi * i / n
        samples.append(TelemetrySample(
            timestamp_ms=i * interval_ms,
            lap_number=lap_num,
            x=cx + radius * math.cos(angle),
            y=0.0,
            z=cz + radius * math.sin(angle),
            speed_kph=150.0, gear=4, rpm=7000.0,
            throttle=0.7, brake=0.0,
        ))
    return CalibrationLap(
        lap_number=lap_num,
        lap_time_ms=n * interval_ms,
        samples=samples,
    )


def _make_session_three_laps() -> CalibrationSession:
    """Session with 3 identical normal laps — all will be USABLE after quality assessment."""
    laps = [_make_normal_lap(i + 1) for i in range(3)]
    return CalibrationSession(
        session_id="test_pit_session",
        track_location_id="monza",
        layout_id="monza__full_course",
        laps=laps,
    )


class TestBuildReferencePathExcludesPitLap:
    """AC1: pit-in laps must be excluded from reference path building.

    detect_pit_lap_raw() geometry is already covered by test_group21b_detect_pit_lap_raw.py.
    These tests verify that build_reference_path() correctly wires detect_pit_lap_raw()
    into its filtering pipeline: when the function returns True for a USABLE lap, the
    lap is flagged with is_pit_lap=True and excluded, and a warning is emitted.

    We patch detect_pit_lap_raw to return True only for lap_number=3 so we can isolate
    the pipeline logic without needing to construct a lap that both passes quality
    assessment AND has a genuine centroid excursion.
    """

    def test_pit_lap_flagged_as_is_pit_lap(self):
        """build_reference_path() must set lap.is_pit_lap=True on the mocked pit lap."""
        session = _make_session_three_laps()
        # Patch detect_pit_lap_raw: only the third lap (lap_number=3) returns True.
        call_count = [0]
        def fake_detect(samples, threshold_seconds=10.0):
            call_count[0] += 1
            # Third call corresponds to lap_number 3
            return call_count[0] == 3

        with patch("data.track_calibration.detect_pit_lap_raw", side_effect=fake_detect):
            build_reference_path(session)

        pit_lap = session.laps[2]  # lap index 2 = lap_number 3
        assert pit_lap.is_pit_lap is True, (
            "Pit lap was not flagged with is_pit_lap=True after build_reference_path()"
        )

    def test_pit_lap_excluded_produces_warning(self):
        """build_reference_path() must emit a warning when a pit lap is excluded."""
        session = _make_session_three_laps()
        call_count = [0]
        def fake_detect(samples, threshold_seconds=10.0):
            call_count[0] += 1
            return call_count[0] == 3

        with patch("data.track_calibration.detect_pit_lap_raw", side_effect=fake_detect):
            result = build_reference_path(session)

        pit_warnings = [w for w in result.warnings if "pit" in w.lower()]
        assert pit_warnings, (
            "Expected at least one pit-lap warning in result.warnings, got none. "
            f"All warnings: {result.warnings}"
        )

    def test_normal_laps_not_flagged_as_pit(self):
        """Non-pit laps must not be marked as is_pit_lap."""
        session = _make_session_three_laps()
        call_count = [0]
        def fake_detect(samples, threshold_seconds=10.0):
            call_count[0] += 1
            return call_count[0] == 3

        with patch("data.track_calibration.detect_pit_lap_raw", side_effect=fake_detect):
            build_reference_path(session)

        assert session.laps[0].is_pit_lap is False
        assert session.laps[1].is_pit_lap is False


# ---------------------------------------------------------------------------
# AC3 — exactly one PIT_LANE segment from detect_track_segments()
# ---------------------------------------------------------------------------

from data.track_station_map import (
    PitLaneBoundary,
    StationPoint,
    TrackStationMap,
)
from data.track_segment_detection import (
    TrackSegmentType,
    detect_track_segments,
)


def _make_station_map_with_pit(
    lap_length_m: float = 1000.0,
    spacing_m: float = 10.0,
) -> TrackStationMap:
    """Build a circular station map with a PitLaneBoundary attached."""
    n = int(lap_length_m / spacing_m)
    stations = []
    for i in range(n):
        angle = 2.0 * math.pi * i / n
        r = lap_length_m / (2.0 * math.pi)
        stations.append(StationPoint(
            station_m=i * spacing_m,
            progress_pct=i / n * 100.0,
            x=r * math.cos(angle),
            y=0.0,
            z=r * math.sin(angle),
        ))
    pit = PitLaneBoundary(
        entry_station_m=250.0,
        exit_station_m=350.0,
        entry_progress=0.25,
        exit_progress=0.35,
    )
    return TrackStationMap(
        track_location_id="test_track",
        layout_id="test_track__full",
        lap_length_m=lap_length_m,
        spacing_m=spacing_m,
        stations=stations,
        seeded_corners=[],
        extra_curvature_peaks=[],
        pit_lane=pit,
    )


def _minimal_calibration_session() -> CalibrationSession:
    """Two simple circular laps pre-marked as USABLE for detect_track_segments()."""
    laps = [_make_normal_lap(i + 1) for i in range(2)]
    for lap in laps:
        lap.quality = CalibrationLapQuality.USABLE
    return CalibrationSession(
        session_id="test_seg_session",
        track_location_id="test_track",
        layout_id="test_track__full",
        laps=laps,
    )


class TestPitLaneSegmentInjected:
    """AC3: detect_track_segments() injects exactly one PIT_LANE segment."""

    def test_exactly_one_pit_lane_segment(self):
        """When station_map has a PitLaneBoundary, exactly one PIT_LANE segment appears."""
        session = _minimal_calibration_session()
        smap = _make_station_map_with_pit()
        result = detect_track_segments(session, station_map=smap)

        pit_segs = [s for s in result.segments if s.segment_type == TrackSegmentType.PIT_LANE]
        assert len(pit_segs) == 1, (
            f"Expected exactly 1 PIT_LANE segment; got {len(pit_segs)}"
        )

    def test_pit_lane_segment_progress_matches_boundary(self):
        """Injected PIT_LANE segment's progress values match the PitLaneBoundary."""
        session = _minimal_calibration_session()
        smap = _make_station_map_with_pit()
        result = detect_track_segments(session, station_map=smap)

        pit_segs = [s for s in result.segments if s.segment_type == TrackSegmentType.PIT_LANE]
        assert pit_segs, "No PIT_LANE segment found"
        seg = pit_segs[0]
        assert seg.lap_progress_start == pytest.approx(0.25, abs=1e-6)
        assert seg.lap_progress_end   == pytest.approx(0.35, abs=1e-6)

    def test_pit_lane_segment_display_name(self):
        """Injected PIT_LANE segment must have display_name 'Pit Lane'."""
        session = _minimal_calibration_session()
        smap = _make_station_map_with_pit()
        result = detect_track_segments(session, station_map=smap)

        pit_segs = [s for s in result.segments if s.segment_type == TrackSegmentType.PIT_LANE]
        assert pit_segs, "No PIT_LANE segment found"
        assert pit_segs[0].display_name == "Pit Lane"

    def test_no_pit_lane_segment_without_boundary(self):
        """When station_map has no PitLaneBoundary, no PIT_LANE segment is injected."""
        session = _minimal_calibration_session()
        smap = _make_station_map_with_pit()
        smap.pit_lane = None  # remove the boundary
        result = detect_track_segments(session, station_map=smap)

        pit_segs = [s for s in result.segments if s.segment_type == TrackSegmentType.PIT_LANE]
        assert len(pit_segs) == 0


# ---------------------------------------------------------------------------
# AC5 — pit_lane_polyline populated in TrackMapDrawData
# ---------------------------------------------------------------------------

from ui.track_map_vm import build_track_map_draw_data


class TestPitLanePolylineInDrawData:
    """AC5: build_track_map_draw_data() populates pit_lane_polyline when pit_lane is set."""

    def test_pit_lane_polyline_populated(self):
        """pit_lane_polyline must be non-empty when station_map has a PitLaneBoundary."""
        smap = _make_station_map_with_pit()
        draw_data = build_track_map_draw_data(smap)
        assert len(draw_data.pit_lane_polyline) > 0, (
            "Expected non-empty pit_lane_polyline when station_map.pit_lane is set"
        )

    def test_pit_lane_polyline_empty_without_boundary(self):
        """pit_lane_polyline must be empty when station_map.pit_lane is None."""
        smap = _make_station_map_with_pit()
        smap.pit_lane = None
        draw_data = build_track_map_draw_data(smap)
        assert draw_data.pit_lane_polyline == [], (
            "Expected empty pit_lane_polyline when station_map.pit_lane is None"
        )

    def test_pit_lane_polyline_points_in_entry_exit_range(self):
        """All points in pit_lane_polyline must come from stations in [entry_m, exit_m]."""
        smap = _make_station_map_with_pit()
        pl = smap.pit_lane
        draw_data = build_track_map_draw_data(smap)

        # Collect expected station positions in pit range
        pit_xs = {
            round(s.x, 3)
            for s in smap.stations
            if pl.entry_station_m <= s.station_m <= pl.exit_station_m
        }
        polyline_xs = {round(p.x, 3) for p in draw_data.pit_lane_polyline}
        assert polyline_xs == pit_xs, (
            "pit_lane_polyline X-coords do not match expected stations in pit range"
        )

    def test_no_station_map_gives_empty_polyline(self):
        """When station_map is None, pit_lane_polyline is empty (via empty draw data)."""
        draw_data = build_track_map_draw_data(None)
        assert draw_data.pit_lane_polyline == []
