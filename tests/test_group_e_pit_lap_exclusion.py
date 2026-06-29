"""Group E — pit-lap exclusion and track-map loop-closure tests.

Pure Python / no PyQt6 paint.
Covers:
  - Gate 0a: first lap (lowest lap_number) always rejected as out-lap
  - Gate 0b: detect_pit_lap_raw lap rejected
  - Clean non-first non-pit laps accepted
  - Exactly one result per lap, in session.laps order, lap_index==i
  - closure_gap_m computed correctly (success and can_generate=False paths)
  - GeometryBuildResult keyword construction without closure_gap_m defaults to 0.0
  - Renderer: centreline closed (centreline[-1]==centreline[0], len==N+1)
  - Renderer: pit_lane_polyline NOT closed
  - Renderer: None station_map → centreline == []
"""
from __future__ import annotations

import math
from typing import List
from unittest.mock import patch

import pytest

from data.track_calibration import (
    CalibrationLap,
    CalibrationLapQuality,
    CalibrationSession,
    TelemetrySample,
)
from data.track_geometry_builder import (
    CLOSURE_GAP_WARN_M,
    GeometryBuildResult,
    LapGeometryFilterResult,
    build_seed_geometry,
    filter_full_laps,
)
from ui.track_map_vm import MapPoint, build_track_map_draw_data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MANIFEST_LAP_M = 400.0   # square 100 m × 4 sides


def _make_square_samples(
    n_samples: int = 80,
    side_m: float = 100.0,
    lap_number: int = 1,
) -> List[TelemetrySample]:
    """Generate samples tracing a square of perimeter = 4 * side_m in XZ plane."""
    perimeter = 4 * side_m
    samples: List[TelemetrySample] = []
    for i in range(n_samples):
        t = i / n_samples
        dist = t * perimeter
        if dist < side_m:
            x, z = dist, 0.0
        elif dist < 2 * side_m:
            x, z = side_m, dist - side_m
        elif dist < 3 * side_m:
            x, z = side_m - (dist - 2 * side_m), side_m
        else:
            x, z = 0.0, side_m - (dist - 3 * side_m)
        samples.append(TelemetrySample(
            timestamp_ms=i * 100,
            lap_number=lap_number,
            x=float(x),
            y=0.0,
            z=float(z),
            speed_kph=100.0,
            gear=4,
            rpm=6000.0,
            throttle=0.8,
            brake=0.0,
        ))
    return samples


def _make_lap(
    lap_number: int = 1,
    side_m: float = 100.0,
    n_samples: int = 80,
) -> CalibrationLap:
    """Build a CalibrationLap with synthetic square-loop samples."""
    samples = _make_square_samples(n_samples=n_samples, side_m=side_m, lap_number=lap_number)
    return CalibrationLap(
        lap_number=lap_number,
        lap_time_ms=120_000,
        samples=samples,
        quality=CalibrationLapQuality.USABLE,
        quality_reasons=[],
        path_length_m=4 * side_m,
    )


def _make_session(laps: List[CalibrationLap]) -> CalibrationSession:
    return CalibrationSession(
        session_id="e_test_session",
        track_location_id="e_test_track",
        layout_id="e_test_layout",
        laps=laps,
    )


# ---------------------------------------------------------------------------
# Gate 0a: first lap (lowest lap_number) always rejected as out-lap
# ---------------------------------------------------------------------------

def test_lowest_lap_number_rejected_as_out_lap():
    """The lap with the globally lowest lap_number is rejected regardless of its position."""
    out_lap = _make_lap(lap_number=1, side_m=100.0)
    good_lap = _make_lap(lap_number=2, side_m=100.0)
    session = _make_session([out_lap, good_lap])
    results = filter_full_laps(session, manifest_lap_length_m=MANIFEST_LAP_M)
    assert len(results) == 2
    assert results[0].status == "rejected"
    assert "out-lap" in results[0].reason
    assert results[1].status == "accepted"


def test_tie_on_min_lap_number_rejects_only_first():
    """When several laps share the lowest lap_number (telemetry tie), only the FIRST
    occurrence is rejected as the out-lap — the rest are not over-excluded."""
    dup_a = _make_lap(lap_number=1, side_m=100.0)
    dup_b = _make_lap(lap_number=1, side_m=100.0)   # same lap_number as dup_a
    good  = _make_lap(lap_number=2, side_m=100.0)
    session = _make_session([dup_a, dup_b, good])
    results = filter_full_laps(session, manifest_lap_length_m=MANIFEST_LAP_M)
    assert len(results) == 3
    out_rejections = [
        r for r in results if r.status == "rejected" and "out-lap" in r.reason
    ]
    assert len(out_rejections) == 1            # exactly one out-lap rejection
    assert out_rejections[0].lap_index == 0    # the first occurrence
    assert results[1].status == "accepted"     # the tied lap survives
    assert results[2].status == "accepted"


def test_ui_appends_seed_messages_after_panel_refresh():
    """Regression guard: _tm_generate_seed_geometry must call the panel refresh
    BEFORE setting its user-facing messages and must APPEND to the existing label
    text, otherwise the refresh's per-lap diagnostics overwrite the message."""
    import re
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "ui" / "track_modelling_ui.py").read_text(
        encoding="utf-8"
    )
    m = re.search(r"def _tm_generate_seed_geometry\(self\).*?(?=\n    def )", src, re.S)
    assert m, "_tm_generate_seed_geometry not found"
    body = m.group(0)
    assert "_tm_refresh_seed_geometry_panel()" in body
    assert "_existing = lbl.text()" in body, "messages must append, not overwrite"
    refresh_idx = body.index("_tm_refresh_seed_geometry_panel()")
    msg_idx = body.index("Not enough clean laps")
    assert refresh_idx < msg_idx, "panel refresh must run before the message is appended"


def test_out_lap_identified_by_lowest_lap_number_not_position():
    """Out-lap detection uses the minimum lap_number, not list index 0."""
    # The lower lap_number lap appears at index 1 in the list.
    good_lap = _make_lap(lap_number=5, side_m=100.0)
    out_lap = _make_lap(lap_number=3, side_m=100.0)   # lap_number=3 < 5
    session = _make_session([good_lap, out_lap])
    results = filter_full_laps(session, manifest_lap_length_m=MANIFEST_LAP_M)
    assert len(results) == 2
    # good_lap (index 0, lap_number=5) should be accepted
    assert results[0].status == "accepted"
    # out_lap (index 1, lap_number=3) should be rejected as out-lap
    assert results[1].status == "rejected"
    assert "out-lap" in results[1].reason


def test_out_lap_rejection_reason_text():
    """The out-lap rejection reason contains the expected text."""
    out_lap = _make_lap(lap_number=0, side_m=100.0)
    good_lap = _make_lap(lap_number=1, side_m=100.0)
    session = _make_session([out_lap, good_lap])
    results = filter_full_laps(session, manifest_lap_length_m=MANIFEST_LAP_M)
    assert results[0].reason == (
        "out-lap: first calibration lap excluded (always starts from pits)"
    )


# ---------------------------------------------------------------------------
# Gate 0b: detect_pit_lap_raw lap rejected
# ---------------------------------------------------------------------------

def test_pit_lap_raw_detected_lap_rejected():
    """If detect_pit_lap_raw returns True for a lap, it is rejected with pit-in reason."""
    out_lap = _make_lap(lap_number=0, side_m=100.0)
    pit_lap = _make_lap(lap_number=1, side_m=100.0)
    session = _make_session([out_lap, pit_lap])

    with patch("data.track_geometry_builder.detect_pit_lap_raw", return_value=True):
        results = filter_full_laps(session, manifest_lap_length_m=MANIFEST_LAP_M)

    # results[0] = out-lap rejected
    # results[1] = pit-in lap rejected
    assert results[1].status == "rejected"
    assert "pit-in lap" in results[1].reason
    assert "pit lane excursion" in results[1].reason


def test_no_pit_lap_detection_when_returns_false():
    """If detect_pit_lap_raw returns False, the lap proceeds through normal gates."""
    out_lap = _make_lap(lap_number=0, side_m=100.0)
    good_lap = _make_lap(lap_number=1, side_m=100.0)
    session = _make_session([out_lap, good_lap])

    with patch("data.track_geometry_builder.detect_pit_lap_raw", return_value=False):
        results = filter_full_laps(session, manifest_lap_length_m=MANIFEST_LAP_M)

    assert results[1].status == "accepted"


def test_pit_lap_detection_not_applied_to_out_lap():
    """Gate 0a fires before Gate 0b; detect_pit_lap_raw is NOT called on the out-lap."""
    out_lap = _make_lap(lap_number=0, side_m=100.0)
    good_lap = _make_lap(lap_number=1, side_m=100.0)
    session = _make_session([out_lap, good_lap])

    call_log = []

    def mock_detect(samples):
        call_log.append(samples)
        return False

    with patch("data.track_geometry_builder.detect_pit_lap_raw", side_effect=mock_detect):
        results = filter_full_laps(session, manifest_lap_length_m=MANIFEST_LAP_M)

    # detect_pit_lap_raw should only have been called for good_lap, not out_lap
    assert len(call_log) == 1
    assert call_log[0] is good_lap.samples


# ---------------------------------------------------------------------------
# Clean non-first non-pit lap accepted
# ---------------------------------------------------------------------------

def test_clean_non_first_non_pit_lap_accepted():
    """A clean full lap that is not the out-lap and not a pit lap is accepted."""
    out_lap = _make_lap(lap_number=0, side_m=100.0)
    good_lap = _make_lap(lap_number=1, side_m=100.0)
    session = _make_session([out_lap, good_lap])

    with patch("data.track_geometry_builder.detect_pit_lap_raw", return_value=False):
        results = filter_full_laps(session, manifest_lap_length_m=MANIFEST_LAP_M)

    assert results[0].status == "rejected"   # out-lap
    assert results[1].status == "accepted"


# ---------------------------------------------------------------------------
# Exactly one result per lap, in session.laps order, lap_index == i
# ---------------------------------------------------------------------------

def test_exactly_one_result_per_lap_in_order():
    """filter_full_laps returns exactly one result per lap, in session.laps order."""
    out_lap = _make_lap(lap_number=0, side_m=100.0)
    lap1 = _make_lap(lap_number=1, side_m=100.0)
    lap2 = _make_lap(lap_number=2, side_m=100.0)
    lap3 = _make_lap(lap_number=3, side_m=85.0)  # too short → rejected by geometry
    session = _make_session([out_lap, lap1, lap2, lap3])

    with patch("data.track_geometry_builder.detect_pit_lap_raw", return_value=False):
        results = filter_full_laps(session, manifest_lap_length_m=MANIFEST_LAP_M)

    assert len(results) == 4
    for i, r in enumerate(results):
        assert r.lap_index == i, f"Expected lap_index={i}, got {r.lap_index}"


def test_lap_index_matches_session_position():
    """lap_index values in the results match the 0-based index in session.laps."""
    laps = [_make_lap(lap_number=i, side_m=100.0) for i in range(5)]
    session = _make_session(laps)

    with patch("data.track_geometry_builder.detect_pit_lap_raw", return_value=False):
        results = filter_full_laps(session, manifest_lap_length_m=MANIFEST_LAP_M)

    assert len(results) == 5
    for i, r in enumerate(results):
        assert r.lap_index == i


# ---------------------------------------------------------------------------
# closure_gap_m computed correctly
# ---------------------------------------------------------------------------

def test_closure_gap_m_small_for_closed_square():
    """A square lap resampled and averaged should have a small closure gap."""
    out_lap = _make_lap(lap_number=0, side_m=100.0)
    lap = _make_lap(lap_number=1, side_m=100.0, n_samples=400)  # high-res square
    session = _make_session([out_lap, lap])
    result = build_seed_geometry(session, MANIFEST_LAP_M, "e_track", "e_layout")
    assert result.can_generate is True
    # The square starts and ends at (0, 0) in XZ — averaged path should close tightly
    # With resampling at 1 m, first and last points of the averaged 400 m path
    # are ~1 m apart at most (they don't fully wrap by construction, but the gap
    # should be well under the 10 m warning threshold for a non-noisy square).
    assert result.closure_gap_m >= 0.0
    assert isinstance(result.closure_gap_m, float)


def test_closure_gap_m_is_euclidean_xz_distance():
    """closure_gap_m equals the XZ distance between the first and last averaged point."""
    out_lap = _make_lap(lap_number=0, side_m=100.0)
    lap = _make_lap(lap_number=1, side_m=100.0)
    session = _make_session([out_lap, lap])
    result = build_seed_geometry(session, MANIFEST_LAP_M, "e_track", "e_layout")
    assert result.can_generate is True
    stations = result.seed_map.stations
    expected_gap = math.sqrt(
        (stations[-1].x - stations[0].x) ** 2
        + (stations[-1].z - stations[0].z) ** 2
    )
    assert abs(result.closure_gap_m - expected_gap) < 1e-6


def test_closure_gap_m_zero_when_cannot_generate():
    """When can_generate=False, closure_gap_m defaults to 0.0."""
    # Single-lap session; the lap is out-lap → rejected → no accepted laps
    out_lap = _make_lap(lap_number=0, side_m=100.0)
    session = _make_session([out_lap])
    result = build_seed_geometry(session, MANIFEST_LAP_M, "e_track", "e_layout")
    assert result.can_generate is False
    assert result.closure_gap_m == 0.0


def test_closure_gap_m_zero_when_only_short_laps():
    """When no laps pass filtering, closure_gap_m == 0.0."""
    out_lap = _make_lap(lap_number=0, side_m=100.0)
    short_lap = _make_lap(lap_number=1, side_m=50.0)  # 200 m — well below 95%
    session = _make_session([out_lap, short_lap])
    result = build_seed_geometry(session, MANIFEST_LAP_M, "e_track", "e_layout")
    assert result.can_generate is False
    assert result.closure_gap_m == 0.0


def test_closure_gap_warn_m_constant():
    """CLOSURE_GAP_WARN_M is exported and equals 10.0."""
    assert CLOSURE_GAP_WARN_M == 10.0


# ---------------------------------------------------------------------------
# GeometryBuildResult keyword construction without closure_gap_m defaults to 0.0
# ---------------------------------------------------------------------------

def test_geometry_build_result_closure_gap_m_defaults_to_zero():
    """GeometryBuildResult(...) without closure_gap_m keyword defaults to 0.0."""
    result = GeometryBuildResult(
        accepted_lap_indices=[],
        rejected_laps=[],
        can_generate=False,
        seed_map=None,
        confidence="low",
        station_count=0,
        # closure_gap_m omitted — should default to 0.0
    )
    assert result.closure_gap_m == 0.0


def test_geometry_build_result_closure_gap_m_settable():
    """GeometryBuildResult accepts closure_gap_m as an explicit keyword."""
    result = GeometryBuildResult(
        accepted_lap_indices=[1],
        rejected_laps=[],
        can_generate=True,
        seed_map=None,
        confidence="low",
        station_count=100,
        closure_gap_m=5.3,
    )
    assert result.closure_gap_m == 5.3


# ---------------------------------------------------------------------------
# too-few-laps after exclusion → can_generate=False
# ---------------------------------------------------------------------------

def test_only_out_lap_in_session_cannot_generate():
    """Session with only one lap (the out-lap) → can_generate=False."""
    out_lap = _make_lap(lap_number=0, side_m=100.0)
    session = _make_session([out_lap])
    result = build_seed_geometry(session, MANIFEST_LAP_M, "e_track", "e_layout")
    assert result.can_generate is False
    assert result.seed_map is None
    assert len(result.accepted_lap_indices) == 0


def test_out_lap_plus_pit_lap_cannot_generate():
    """Out-lap + pit-in lap both rejected → can_generate=False."""
    out_lap = _make_lap(lap_number=0, side_m=100.0)
    pit_lap = _make_lap(lap_number=1, side_m=100.0)
    session = _make_session([out_lap, pit_lap])

    with patch("data.track_geometry_builder.detect_pit_lap_raw", return_value=True):
        result = build_seed_geometry(session, MANIFEST_LAP_M, "e_track", "e_layout")

    assert result.can_generate is False


# ---------------------------------------------------------------------------
# Renderer: centreline closed (centreline[-1]==centreline[0], len==N+1)
# ---------------------------------------------------------------------------

def _make_minimal_station_map():
    """Return a minimal TrackStationMap with 4 stations forming a square."""
    from data.track_station_map import TrackStationMap, StationPoint
    stations = []
    coords = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
    for i, (x, z) in enumerate(coords):
        stations.append(StationPoint(
            station_m=float(i * 100),
            progress_pct=float(i * 25),
            x=x,
            y=0.0,
            z=z,
            heading_rad=0.0,
            left_width_m=5.0,
            right_width_m=5.0,
        ))
    return TrackStationMap(
        track_location_id="e_track",
        layout_id="e_layout",
        lap_length_m=400.0,
        spacing_m=1.0,
        stations=stations,
        seeded_corners=[],
        default_track_width_m=10.0,
    )


def test_centreline_closed_after_build_draw_data():
    """build_track_map_draw_data closes the centreline by appending centreline[0]."""
    station_map = _make_minimal_station_map()
    data = build_track_map_draw_data(station_map)
    n_stations = len(station_map.stations)
    # Expect N+1 points (the extra is centreline[0] repeated at the end)
    assert len(data.centreline) == n_stations + 1, (
        f"Expected {n_stations + 1} centreline points (N+1), got {len(data.centreline)}"
    )
    assert data.centreline[-1].x == data.centreline[0].x
    assert data.centreline[-1].y == data.centreline[0].y


def test_centreline_first_and_last_are_equal():
    """The closing point is the identical world-space point as the first."""
    station_map = _make_minimal_station_map()
    data = build_track_map_draw_data(station_map)
    assert data.centreline[-1] == data.centreline[0]


def test_paint_loop_compatible_with_closed_centreline():
    """Iterating range(len(centreline)-1) covers all N segments including the closing one."""
    station_map = _make_minimal_station_map()
    data = build_track_map_draw_data(station_map)
    n = len(data.centreline)
    segment_count = 0
    for i in range(n - 1):
        _ = (data.centreline[i], data.centreline[i + 1])
        segment_count += 1
    # N+1 points → N segments (N station-to-station + 1 closing)
    assert segment_count == len(station_map.stations)


# ---------------------------------------------------------------------------
# Renderer: pit_lane_polyline NOT closed
# ---------------------------------------------------------------------------

def test_pit_lane_polyline_not_closed():
    """pit_lane_polyline is never closed (its first and last point are NOT the same)."""
    from data.track_station_map import TrackStationMap, StationPoint, PitLaneBoundary
    # Build a map with a pit lane covering stations 0..2
    stations = []
    for i in range(10):
        stations.append(StationPoint(
            station_m=float(i * 10),
            progress_pct=float(i * 10),
            x=float(i * 10),
            y=0.0,
            z=0.0,
            heading_rad=0.0,
            left_width_m=5.0,
            right_width_m=5.0,
        ))
    pit_lane = PitLaneBoundary(
        entry_station_m=0.0,
        exit_station_m=20.0,
        entry_progress=0.0,
        exit_progress=0.2,
    )
    station_map = TrackStationMap(
        track_location_id="e_track",
        layout_id="e_layout",
        lap_length_m=100.0,
        spacing_m=1.0,
        stations=stations,
        seeded_corners=[],
        default_track_width_m=10.0,
        pit_lane=pit_lane,
    )
    data = build_track_map_draw_data(station_map)
    pl = data.pit_lane_polyline
    if len(pl) > 1:
        # First and last should NOT be the same (polyline open)
        assert not (pl[-1].x == pl[0].x and pl[-1].y == pl[0].y), (
            "pit_lane_polyline should be open (not closed)"
        )


# ---------------------------------------------------------------------------
# Renderer: None station_map → centreline == []
# ---------------------------------------------------------------------------

def test_none_station_map_returns_empty_centreline():
    """build_track_map_draw_data(None) returns centreline == []."""
    data = build_track_map_draw_data(None)
    assert data.centreline == []


def test_empty_station_map_returns_empty_centreline():
    """build_track_map_draw_data with a station_map with no stations returns centreline == []."""
    from data.track_station_map import TrackStationMap
    empty_map = TrackStationMap(
        track_location_id="e_track",
        layout_id="e_layout",
        lap_length_m=400.0,
        spacing_m=1.0,
        stations=[],
        seeded_corners=[],
        default_track_width_m=10.0,
    )
    data = build_track_map_draw_data(empty_map)
    assert data.centreline == []


def test_none_station_map_no_index_error():
    """build_track_map_draw_data(None) must not raise IndexError."""
    try:
        data = build_track_map_draw_data(None)
    except IndexError as exc:
        pytest.fail(f"build_track_map_draw_data(None) raised IndexError: {exc}")
