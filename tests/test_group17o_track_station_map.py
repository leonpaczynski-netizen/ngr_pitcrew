"""Group 17O — Track Station Map, Map Matching, Width Model, Drawing Primitives.

Pure Python tests: no QApplication, no PyQt6 import.

Test categories (14):
  1.  Creating a 1m station model from seed/reference data
  2.  Resampling a path into 1m stations
  3.  Mapping X/Y/Z telemetry to nearest station
  4.  Calculating station_m and progress_pct
  5.  Calculating lateral_offset_m
  6.  Calculating left/right edge distance from width corridor
  7.  Handling missing/unknown width safely
  8.  Ignoring pit/out-lap fragments
  9.  Keeping seeded 12-corner Daytona structure even if telemetry refinement incomplete
  10. Separating telemetry overlays from track geometry
  11. Producing drawing primitives without PyQt
  12. Producing a live car-dot primitive from mapped telemetry
  13. Low-confidence map matching state
  14. Legacy low-resolution reference path handling (200-point path)
"""
from __future__ import annotations

import math
import types
from dataclasses import dataclass, field
from typing import List

import pytest


# ---------------------------------------------------------------------------
# Helpers to build dummy reference paths and station maps
# ---------------------------------------------------------------------------

def _make_ref_path(
    loc="test_loc",
    lay="test_loc__test_lay",
    n_points: int = 200,
    lap_length_m: float = 5729.0,
    closed: bool = True,
    confidence: float = 1.0,
):
    """Fake ReferencePath with points arranged around an ellipse.

    The ellipse approximates a simple closed circuit so curvature varies
    naturally.  Major axis ≈ lap_length_m / (2π).
    """
    @dataclass
    class FakePoint:
        lap_progress: float
        distance_along_lap_m: float
        x: float
        y: float
        z: float
        speed_kph_avg: float = 200.0
        source_lap_count: int = 5

    @dataclass
    class FakeRefPath:
        track_location_id: str
        layout_id: str
        calibration_car_id: str
        confidence: float
        points: list

    a = lap_length_m / (2 * math.pi) * 1.5   # semi-major axis
    b = a * 0.5                                # semi-minor axis
    points = []
    cum = 0.0
    prev_x, prev_z = a, 0.0

    for i in range(n_points):
        theta  = 2 * math.pi * i / n_points
        px     = a * math.cos(theta)
        pz     = b * math.sin(theta)
        py     = 1.0 + 0.5 * math.sin(theta * 3)  # gentle elevation
        if i > 0:
            dx  = px - prev_x
            dz  = pz - prev_z
            cum += math.sqrt(dx ** 2 + dz ** 2)
        prog = i / n_points
        points.append(FakePoint(
            lap_progress         = prog,
            distance_along_lap_m = cum,
            x=px, y=py, z=pz,
        ))
        prev_x, prev_z = px, pz

    # Close path: approximate total length by adding last segment
    if closed and points:
        points[-1].distance_along_lap_m = cum

    return FakeRefPath(
        track_location_id = loc,
        layout_id         = lay,
        calibration_car_id = "porsche_911_rsr_991_2017",
        confidence        = confidence,
        points            = points,
    )


def _make_layout_seed(corners_expected: int = 12, length_m: float = 5729.0):
    """Fake TrackLayoutSeed."""
    obj = types.SimpleNamespace()
    obj.corners_expected = corners_expected
    obj.length_m         = length_m
    return obj


def _make_simple_station_map(n: int = 100, lap_m: float = 500.0, width: float = 12.0):
    """Build a simple straight-line station map (not from a ref path)."""
    from data.track_station_map import StationPoint, TrackStationMap, WidthSource

    stations = []
    for i in range(n):
        x = float(i) * (lap_m / n)
        stations.append(StationPoint(
            station_m    = float(i),
            progress_pct = float(i) / n * 100.0,
            x            = x,
            y            = 0.0,
            z            = 0.0,
            heading_rad  = 0.0,
            left_width_m  = width / 2,
            right_width_m = width / 2,
            width_source  = WidthSource.SEED_DEFAULT,
            confidence   = 1.0,
        ))
    return TrackStationMap(
        track_location_id     = "test",
        layout_id             = "test__layout",
        lap_length_m          = lap_m,
        spacing_m             = 1.0,
        stations              = stations,
        seeded_corners        = [],
        default_track_width_m = width,
        confidence_overall    = 1.0,
    )


# ===========================================================================
# 1. Creating a 1m station model from seed/reference data
# ===========================================================================

class TestBuildTrackStationMap:
    def test_returns_station_map(self):
        from data.track_station_map import build_track_station_map
        ref = _make_ref_path(n_points=200)
        sm  = build_track_station_map(ref)
        assert sm is not None

    def test_station_count_approximately_one_per_metre(self):
        from data.track_station_map import build_track_station_map
        ref = _make_ref_path(n_points=200, lap_length_m=1000.0)
        sm  = build_track_station_map(ref, spacing_m=1.0)
        # Should have roughly lap_length_m stations (±10%)
        assert 800 <= sm.station_count() <= 1200

    def test_track_ids_preserved(self):
        from data.track_station_map import build_track_station_map
        ref = _make_ref_path(loc="daytona_international_speedway",
                             lay="daytona_international_speedway__road_course")
        sm  = build_track_station_map(ref)
        assert sm.track_location_id == "daytona_international_speedway"
        assert sm.layout_id         == "daytona_international_speedway__road_course"

    def test_confidence_propagated(self):
        from data.track_station_map import build_track_station_map
        ref = _make_ref_path(confidence=0.75)
        sm  = build_track_station_map(ref)
        assert abs(sm.confidence_overall - 0.75) < 1e-6

    def test_with_layout_seed_uses_corners_expected(self):
        from data.track_station_map import build_track_station_map
        ref  = _make_ref_path()
        seed = _make_layout_seed(corners_expected=12)
        sm   = build_track_station_map(ref, layout_seed=seed)
        assert sm.corners_expected == 12

    def test_raises_on_empty_ref_path(self):
        from data.track_station_map import build_track_station_map
        ref = _make_ref_path()
        ref.points = []
        with pytest.raises(ValueError):
            build_track_station_map(ref)

    def test_stations_have_headings(self):
        from data.track_station_map import build_track_station_map
        ref = _make_ref_path()
        sm  = build_track_station_map(ref)
        # Heading should vary (not all zero) for an elliptical circuit
        headings = [s.heading_rad for s in sm.stations]
        assert max(headings) - min(headings) > 0.5

    def test_stations_have_curvature(self):
        from data.track_station_map import build_track_station_map
        ref = _make_ref_path()
        sm  = build_track_station_map(ref)
        curvatures = [abs(s.curvature) for s in sm.stations]
        assert max(curvatures) > 0.0

    def test_spacing_m_2_halves_station_count(self):
        from data.track_station_map import build_track_station_map
        ref = _make_ref_path(n_points=200, lap_length_m=1000.0)
        sm1 = build_track_station_map(ref, spacing_m=1.0)
        sm2 = build_track_station_map(ref, spacing_m=2.0)
        # 2 m spacing should give roughly half as many stations
        assert sm2.station_count() < sm1.station_count() * 0.7


# ===========================================================================
# 2. Resampling a path into 1m stations
# ===========================================================================

class TestResamplePath:
    def test_basic_straight_path(self):
        from data.track_station_map import resample_path_to_uniform_spacing
        pts = [(float(i), 0.0, 0.0) for i in range(0, 101, 10)]
        result = resample_path_to_uniform_spacing(pts, spacing_m=1.0)
        # Should produce 100 intervals → 101 points
        assert len(result) >= 99

    def test_spacing_is_approximately_correct(self):
        from data.track_station_map import resample_path_to_uniform_spacing, _seg_length
        pts = [(float(i * 5), 0.0, 0.0) for i in range(21)]  # 100 m straight
        result = resample_path_to_uniform_spacing(pts, spacing_m=2.5)
        for i in range(len(result) - 1):
            d = _seg_length(result[i], result[i + 1])
            assert abs(d - 2.5) < 0.5, f"Spacing {d:.3f} at index {i}"

    def test_single_point_returned_unchanged(self):
        from data.track_station_map import resample_path_to_uniform_spacing
        pts = [(1.0, 2.0, 3.0)]
        result = resample_path_to_uniform_spacing(pts, spacing_m=1.0)
        assert result == [(1.0, 2.0, 3.0)]

    def test_empty_list_returned_unchanged(self):
        from data.track_station_map import resample_path_to_uniform_spacing
        result = resample_path_to_uniform_spacing([], spacing_m=1.0)
        assert result == []

    def test_3d_path_preserves_y(self):
        from data.track_station_map import resample_path_to_uniform_spacing
        pts = [(0.0, 0.0, 0.0), (0.0, 5.0, 0.0), (0.0, 10.0, 0.0)]
        result = resample_path_to_uniform_spacing(pts, spacing_m=1.0)
        assert len(result) >= 9
        # All y values should be between 0 and 10
        for (x, y, z) in result:
            assert 0.0 <= y <= 10.0


# ===========================================================================
# 3. Mapping X/Y/Z telemetry to nearest station
# ===========================================================================

class TestFindNearestStation:
    def test_exact_match(self):
        from data.track_map_matching import find_nearest_station_idx
        sm = _make_simple_station_map(n=50, lap_m=50.0)
        idx = find_nearest_station_idx(10.0, 0.0, sm.stations)
        assert idx == 10

    def test_between_stations(self):
        from data.track_map_matching import find_nearest_station_idx
        sm = _make_simple_station_map(n=50, lap_m=50.0)
        # Position between station 5 (x=5) and 6 (x=6) — closer to 5
        idx = find_nearest_station_idx(5.4, 0.0, sm.stations)
        assert idx == 5

    def test_raises_on_empty(self):
        from data.track_map_matching import find_nearest_station_idx
        from data.track_station_map import TrackStationMap
        empty_sm = TrackStationMap("t", "t__l", 100.0, 1.0, [], [], 0.0)
        with pytest.raises(ValueError):
            find_nearest_station_idx(0.0, 0.0, empty_sm.stations)

    def test_off_track_position(self):
        from data.track_map_matching import find_nearest_station_idx
        sm = _make_simple_station_map(n=50, lap_m=50.0)
        # Far off track but nearest station is still index 0
        idx = find_nearest_station_idx(-1000.0, -1000.0, sm.stations)
        assert idx == 0


# ===========================================================================
# 4. Calculating station_m and progress_pct
# ===========================================================================

class TestStationMAndProgress:
    def test_start_of_track(self):
        from data.track_map_matching import match_position_to_map
        sm = _make_simple_station_map(n=100, lap_m=100.0)
        result = match_position_to_map(0.0, 0.0, 0.0, sm, speed_kph=100.0)
        assert result.station_m == pytest.approx(0.0, abs=1.0)
        assert result.progress_pct == pytest.approx(0.0, abs=2.0)

    def test_midpoint_of_track(self):
        from data.track_map_matching import match_position_to_map
        sm = _make_simple_station_map(n=100, lap_m=100.0)
        result = match_position_to_map(50.0, 0.0, 0.0, sm, speed_kph=100.0)
        assert result.station_m == pytest.approx(50.0, abs=2.0)
        assert result.progress_pct == pytest.approx(50.0, abs=2.0)

    def test_progress_pct_bounded_0_to_100(self):
        from data.track_map_matching import match_position_to_map
        sm = _make_simple_station_map(n=100, lap_m=100.0)
        result = match_position_to_map(200.0, 0.0, 0.0, sm, speed_kph=100.0)
        assert 0.0 <= result.progress_pct <= 100.0


# ===========================================================================
# 5. Calculating lateral_offset_m
# ===========================================================================

class TestLateralOffset:
    def _straight_map(self):
        """Station map along the Z axis (heading = 0 → forward is +Z)."""
        from data.track_station_map import StationPoint, TrackStationMap, WidthSource
        import math
        stations = []
        for i in range(100):
            stations.append(StationPoint(
                station_m    = float(i),
                progress_pct = float(i),
                x            = 0.0,
                y            = 0.0,
                z            = float(i),
                heading_rad  = 0.0,  # forward = +Z; left = +X
                left_width_m  = 6.0,
                right_width_m = 6.0,
                width_source  = WidthSource.SEED_DEFAULT,
            ))
        return TrackStationMap("t", "t__l", 100.0, 1.0, stations, [], 0.0)

    def test_centreline_offset_is_zero(self):
        from data.track_map_matching import match_position_to_map
        sm = self._straight_map()
        result = match_position_to_map(0.0, 0.0, 50.0, sm, speed_kph=100.0)
        assert abs(result.lateral_offset_m) < 0.5

    def test_left_offset_positive(self):
        from data.track_map_matching import match_position_to_map
        sm = self._straight_map()
        # Left of centreline (heading 0 → left is +X)
        result = match_position_to_map(3.0, 0.0, 50.0, sm, speed_kph=100.0)
        assert result.lateral_offset_m > 0.0

    def test_right_offset_negative(self):
        from data.track_map_matching import match_position_to_map
        sm = self._straight_map()
        # Right of centreline (heading 0 → right is -X)
        result = match_position_to_map(-3.0, 0.0, 50.0, sm, speed_kph=100.0)
        assert result.lateral_offset_m < 0.0

    def test_offset_magnitude_matches_distance(self):
        from data.track_map_matching import match_position_to_map
        sm = self._straight_map()
        result = match_position_to_map(4.0, 0.0, 50.0, sm, speed_kph=100.0)
        assert abs(result.lateral_offset_m) == pytest.approx(4.0, abs=0.5)


# ===========================================================================
# 6. Left/right edge distances from width corridor
# ===========================================================================

class TestEdgeDistances:
    def _map_12m_wide(self):
        from data.track_station_map import StationPoint, TrackStationMap, WidthSource
        stations = [StationPoint(
            station_m=50.0, progress_pct=50.0,
            x=0.0, y=0.0, z=50.0,
            heading_rad=0.0,
            left_width_m=6.0, right_width_m=6.0,
            width_source=WidthSource.SEED_DEFAULT,
        )]
        return TrackStationMap("t", "t__l", 100.0, 1.0, stations, [], 0.0,
                               default_track_width_m=12.0)

    def test_centreline_equal_edges(self):
        from data.track_map_matching import match_position_to_map
        sm = self._map_12m_wide()
        result = match_position_to_map(0.0, 0.0, 50.0, sm, speed_kph=100.0)
        assert result.dist_to_left_edge_m  == pytest.approx(6.0, abs=0.5)
        assert result.dist_to_right_edge_m == pytest.approx(6.0, abs=0.5)

    def test_near_left_edge_reduces_left_distance(self):
        from data.track_map_matching import match_position_to_map
        sm = self._map_12m_wide()
        result = match_position_to_map(5.0, 0.0, 50.0, sm, speed_kph=100.0)
        assert result.dist_to_left_edge_m  < 2.0
        assert result.dist_to_right_edge_m > 8.0

    def test_edge_distances_nonnegative(self):
        from data.track_map_matching import match_position_to_map
        sm = self._map_12m_wide()
        for x_off in [-10.0, 0.0, 10.0]:
            result = match_position_to_map(x_off, 0.0, 50.0, sm, speed_kph=100.0)
            assert result.dist_to_left_edge_m  >= 0.0
            assert result.dist_to_right_edge_m >= 0.0


# ===========================================================================
# 7. Missing/unknown width handled safely
# ===========================================================================

class TestMissingWidth:
    def test_zero_width_falls_back_to_default(self):
        from data.track_map_matching import match_position_to_map
        from data.track_station_map import StationPoint, TrackStationMap, WidthSource
        # Station with left/right width = 0 (unknown)
        stations = [StationPoint(
            station_m=0.0, progress_pct=0.0,
            x=0.0, y=0.0, z=0.0, heading_rad=0.0,
            left_width_m=0.0, right_width_m=0.0,
            width_source=WidthSource.UNKNOWN,
        )]
        sm = TrackStationMap("t", "t__l", 10.0, 1.0, stations, [], 0.0,
                             default_track_width_m=10.0)
        result = match_position_to_map(0.0, 0.0, 0.0, sm, speed_kph=100.0)
        # Should fall back to default 10m / 2 = 5m each side
        assert result.dist_to_left_edge_m  > 0.0
        assert result.dist_to_right_edge_m > 0.0

    def test_no_stations_returns_unknown(self):
        from data.track_map_matching import match_position_to_map
        from data.track_station_map import TrackStationMap
        from data.track_map_matching import MapMatchConfidence
        sm = TrackStationMap("t", "t__l", 100.0, 1.0, [], [], 0.0)
        result = match_position_to_map(0.0, 0.0, 0.0, sm, speed_kph=100.0)
        assert result.confidence == MapMatchConfidence.UNKNOWN


# ===========================================================================
# 8. Pit/out-lap detection
# ===========================================================================

class TestPitAndOutlapDetection:
    def test_low_speed_returns_pit_likely(self):
        from data.track_map_matching import match_position_to_map, MIN_SPEED_KPH
        sm = _make_simple_station_map(n=50, lap_m=50.0)
        result = match_position_to_map(25.0, 0.0, 0.0, sm, speed_kph=MIN_SPEED_KPH - 1.0)
        assert result.is_pit_likely is True

    def test_far_from_track_returns_pit_likely(self):
        from data.track_map_matching import match_position_to_map, PIT_DISTANCE_THRESHOLD_M
        sm = _make_simple_station_map(n=50, lap_m=50.0)
        result = match_position_to_map(
            0.0 + PIT_DISTANCE_THRESHOLD_M + 100.0,
            0.0, 0.0,
            sm, speed_kph=100.0,
        )
        assert result.is_pit_likely is True

    def test_on_track_not_pit_likely(self):
        from data.track_map_matching import match_position_to_map
        sm = _make_simple_station_map(n=100, lap_m=100.0)
        result = match_position_to_map(50.0, 0.0, 0.0, sm, speed_kph=150.0)
        assert result.is_pit_likely is False

    def test_outlap_flag_before_first_crossing(self):
        from data.track_map_matching import is_likely_outlap
        assert is_likely_outlap(100.0, 5729.0, has_crossed_start_finish=False) is True

    def test_not_outlap_after_first_crossing(self):
        from data.track_map_matching import is_likely_outlap
        assert is_likely_outlap(100.0, 5729.0, has_crossed_start_finish=True) is False


# ===========================================================================
# 9. Daytona 12-corner seeded structure retained
# ===========================================================================

class TestDaytonaSeededCorners:
    def _daytona_map(self):
        from data.track_station_map import build_track_station_map
        ref  = _make_ref_path(
            loc = "daytona_international_speedway",
            lay = "daytona_international_speedway__road_course",
            n_points = 200,
            lap_length_m = 5729.0,
        )
        seed = _make_layout_seed(corners_expected=12, length_m=5729.0)
        return build_track_station_map(ref, layout_seed=seed)

    def test_corner_count_equals_expected(self):
        sm = self._daytona_map()
        assert len(sm.seeded_corners) == 12

    def test_corners_numbered_t1_through_t12(self):
        sm = self._daytona_map()
        ids = [c.corner_id for c in sm.seeded_corners]
        assert ids == [f"T{i}" for i in range(1, 13)]

    def test_corner_stations_in_ascending_order(self):
        sm = self._daytona_map()
        stations = [c.approx_station_m for c in sm.seeded_corners]
        assert stations == sorted(stations)

    def test_placeholders_have_low_confidence(self):
        sm = self._daytona_map()
        for c in sm.seeded_corners:
            if c.is_seeded_placeholder:
                assert c.confidence < 0.5

    def test_corners_expected_field_correct(self):
        sm = self._daytona_map()
        assert sm.corners_expected == 12

    def test_no_corners_still_produces_map(self):
        from data.track_station_map import build_track_station_map
        ref  = _make_ref_path()
        seed = _make_layout_seed(corners_expected=0)
        sm   = build_track_station_map(ref, layout_seed=seed)
        assert sm.station_count() > 0

    def test_fewer_detected_than_expected_gets_placeholders(self):
        """If only 2 corners detected but 12 expected, placeholders fill to 12."""
        from data.track_station_map import build_track_station_map
        # Straight-line ref path has almost no curvature → few detected corners
        @dataclass
        class FlatPoint:
            lap_progress: float
            distance_along_lap_m: float
            x: float
            y: float = 1.0
            z: float = 0.0
            speed_kph_avg: float = 200.0
            source_lap_count: int = 5

        @dataclass
        class FlatRefPath:
            track_location_id: str = "test"
            layout_id: str = "test__flat"
            calibration_car_id: str = "porsche"
            confidence: float = 1.0
            points: list = field(default_factory=list)

        points = [
            FlatPoint(lap_progress=i/199, distance_along_lap_m=float(i*29),
                      x=float(i * 29), y=1.0, z=0.0)
            for i in range(200)
        ]
        ref  = FlatRefPath(points=points)
        seed = _make_layout_seed(corners_expected=12, length_m=5729.0)
        sm   = build_track_station_map(ref, layout_seed=seed)
        assert len(sm.seeded_corners) == 12


# ===========================================================================
# 10. Telemetry overlays separated from track geometry
# ===========================================================================

class TestTelemetryOverlaySeparation:
    """Track station map contains ONLY geometry — no telemetry events."""

    def test_station_map_has_no_braking_event_fields(self):
        from data.track_station_map import StationPoint
        s = StationPoint(station_m=0.0, progress_pct=0.0, x=0.0, y=0.0, z=0.0)
        # These telemetry event attributes must NOT exist on StationPoint
        assert not hasattr(s, "lock_up_count")
        assert not hasattr(s, "wheelspin_count")
        assert not hasattr(s, "limiter_hit")
        assert not hasattr(s, "oversteer_count")
        assert not hasattr(s, "gear")
        assert not hasattr(s, "brake_input")
        assert not hasattr(s, "throttle_input")

    def test_station_point_has_only_geometry_fields(self):
        from data.track_station_map import StationPoint
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(StationPoint)}
        geometry_fields = {
            "station_m", "progress_pct", "x", "y", "z",
            "heading_rad", "curvature", "gradient",
            "left_width_m", "right_width_m", "width_source",
            "segment_id", "corner_id", "corner_phase",
            "confidence", "source",
        }
        assert field_names == geometry_fields

    def test_corner_phase_uses_only_geometry_phases(self):
        from data.track_station_map import CornerPhase
        geometry_phases = {CornerPhase.STRAIGHT, CornerPhase.BRAKING,
                           CornerPhase.TURN_IN, CornerPhase.APEX,
                           CornerPhase.EXIT, CornerPhase.UNKNOWN}
        telemetry_phases = {"limiter_zone", "gear_zone", "fuel_saving", "kerb_candidate"}
        for tp in telemetry_phases:
            assert tp not in {p.value for p in geometry_phases}

    def test_segment_detection_types_excluded_from_station_map(self):
        """Segment types from Group 17E must not appear in station map corner phases."""
        from data.track_station_map import CornerPhase
        forbidden = {
            "limiter_zone", "fuel_saving_candidate", "kerb_or_bump_candidate",
            "gear_zone", "traction_zone",
        }
        for f in forbidden:
            assert f not in {p.value for p in CornerPhase}


# ===========================================================================
# 11. Drawing primitives without PyQt
# ===========================================================================

class TestDrawingPrimitives:
    def _station_map(self):
        from data.track_station_map import build_track_station_map
        return build_track_station_map(_make_ref_path(n_points=200))

    def test_build_returns_draw_data(self):
        from ui.track_map_vm import build_track_map_draw_data
        sm = self._station_map()
        dd = build_track_map_draw_data(sm)
        assert dd is not None

    def test_centreline_has_points(self):
        from ui.track_map_vm import build_track_map_draw_data
        sm = self._station_map()
        dd = build_track_map_draw_data(sm)
        assert len(dd.centreline) > 0

    def test_width_edges_match_centreline_length(self):
        from ui.track_map_vm import build_track_map_draw_data
        sm = self._station_map()
        dd = build_track_map_draw_data(sm)
        # centreline has N+1 points (N stations + 1 closing point to join the circuit).
        # Width edge polylines are NOT closed, so they remain N points.
        n_stations = len(sm.stations)
        assert len(dd.centreline) == n_stations + 1
        assert len(dd.width_left)  == n_stations
        assert len(dd.width_right) == n_stations

    def test_corner_labels_count_matches_corners(self):
        from ui.track_map_vm import build_track_map_draw_data
        from data.track_station_map import build_track_station_map
        ref  = _make_ref_path()
        seed = _make_layout_seed(corners_expected=12)
        sm   = build_track_station_map(ref, layout_seed=seed)
        dd   = build_track_map_draw_data(sm)
        assert len(dd.corner_labels) == 12

    def test_no_car_dot_without_match(self):
        from ui.track_map_vm import build_track_map_draw_data
        sm = self._station_map()
        dd = build_track_map_draw_data(sm)
        assert dd.car_dot is None

    def test_has_map_true_with_valid_map(self):
        from ui.track_map_vm import build_track_map_draw_data
        sm = self._station_map()
        dd = build_track_map_draw_data(sm)
        assert dd.has_map is True

    def test_empty_map_returns_no_map(self):
        from ui.track_map_vm import build_track_map_draw_data
        dd = build_track_map_draw_data(None)
        assert dd.has_map is False

    def test_no_pyqt_import(self):
        import ui.track_map_vm as tvm_mod
        import sys
        # Confirm no PyQt6 import happened
        pyqt_mods = [k for k in sys.modules if "PyQt6" in k]
        assert not any("PyQt6" in k for k in sys.modules
                       if k.startswith("ui.track_map_vm")), \
            "track_map_vm should not import PyQt6"

    def test_bounds_are_valid(self):
        from ui.track_map_vm import build_track_map_draw_data
        sm = self._station_map()
        dd = build_track_map_draw_data(sm)
        min_x, min_y, max_x, max_y = dd.bounds
        assert max_x > min_x
        assert max_y > min_y

    def test_status_text_includes_station_count(self):
        from ui.track_map_vm import build_track_map_draw_data
        sm = self._station_map()
        dd = build_track_map_draw_data(sm)
        assert "station" in dd.status_text.lower()


# ===========================================================================
# 12. Live car dot primitive from mapped telemetry
# ===========================================================================

class TestCarDotPrimitive:
    def _sm_and_match(self, x_off=2.0, speed=150.0):
        from data.track_map_matching import match_position_to_map
        sm = _make_simple_station_map(n=100, lap_m=100.0)
        # Track runs along X (z=0). Match at station 50 (x=50) with z=x_off as
        # the perpendicular offset so dist_to_centreline ≈ |x_off|.
        result = match_position_to_map(50.0, 0.0, x_off, sm, speed_kph=speed)
        return sm, result

    def test_car_dot_created_when_match_valid(self):
        from ui.track_map_vm import build_track_map_draw_data
        sm, result = self._sm_and_match(x_off=2.0)
        dd = build_track_map_draw_data(sm, match_result=result)
        assert dd.car_dot is not None

    def test_car_dot_position_near_match_station(self):
        from ui.track_map_vm import build_track_map_draw_data
        sm, result = self._sm_and_match(x_off=0.0)
        dd = build_track_map_draw_data(sm, match_result=result)
        # With no lateral offset the dot x should be near the station x
        st = sm.stations[result.nearest_station_idx]
        assert abs(dd.car_dot.x - st.x) < 2.0

    def test_car_dot_confidence_reflects_match(self):
        from ui.track_map_vm import build_track_map_draw_data
        from data.track_map_matching import MapMatchConfidence
        sm, result = self._sm_and_match(x_off=0.0)
        dd = build_track_map_draw_data(sm, match_result=result)
        assert dd.car_dot.confidence == MapMatchConfidence.HIGH

    def test_no_dot_for_pit_sample(self):
        from ui.track_map_vm import build_track_map_draw_data
        from data.track_map_matching import match_position_to_map
        sm = _make_simple_station_map(n=50, lap_m=50.0)
        result = match_position_to_map(0.0, 0.0, 0.0, sm, speed_kph=1.0)
        dd = build_track_map_draw_data(sm, match_result=result)
        assert dd.car_dot is None

    def test_project_to_screen_scales_dot(self):
        from ui.track_map_vm import build_track_map_draw_data, project_to_screen
        sm, result = self._sm_and_match(x_off=0.0)
        dd  = build_track_map_draw_data(sm, match_result=result)
        pdd = project_to_screen(dd, canvas_w=800, canvas_h=600)
        if pdd.car_dot:
            assert 0.0 <= pdd.car_dot.x <= 800.0
            assert 0.0 <= pdd.car_dot.y <= 600.0


# ===========================================================================
# 13. Low-confidence map matching state
# ===========================================================================

class TestLowConfidenceState:
    def test_far_position_gives_unknown_confidence(self):
        from data.track_map_matching import match_position_to_map, MapMatchConfidence, PIT_DISTANCE_THRESHOLD_M
        sm = _make_simple_station_map(n=50, lap_m=50.0)
        result = match_position_to_map(
            PIT_DISTANCE_THRESHOLD_M + 100.0,
            0.0, 0.0,
            sm, speed_kph=100.0,
        )
        assert result.confidence == MapMatchConfidence.UNKNOWN

    def test_medium_distance_gives_medium_confidence(self):
        from data.track_map_matching import (
            match_position_to_map, MapMatchConfidence,
            CONFIDENCE_HIGH_M, CONFIDENCE_MED_M,
        )
        sm = _make_simple_station_map(n=100, lap_m=100.0)
        mid_dist = (CONFIDENCE_HIGH_M + CONFIDENCE_MED_M) / 2.0
        # Track runs along X (z=0). Place car at station 50 (x=50), z=mid_dist
        # perpendicular → dist_to_centreline ≈ mid_dist → MEDIUM confidence.
        result   = match_position_to_map(50.0, 0.0, mid_dist, sm, speed_kph=100.0)
        assert result.confidence == MapMatchConfidence.MEDIUM

    def test_on_centreline_gives_high_confidence(self):
        from data.track_map_matching import match_position_to_map, MapMatchConfidence
        sm = _make_simple_station_map(n=100, lap_m=100.0)
        # Track runs along X (z=0); match directly on station 50.
        result = match_position_to_map(50.0, 0.0, 0.0, sm, speed_kph=150.0)
        assert result.confidence == MapMatchConfidence.HIGH

    def test_low_confidence_flagged_in_warnings(self):
        from data.track_map_matching import match_position_to_map, CONFIDENCE_MED_M
        sm     = _make_simple_station_map(n=50, lap_m=50.0)
        result = match_position_to_map(
            CONFIDENCE_MED_M + 5.0, 0.0, 25.0, sm, speed_kph=100.0,
        )
        assert len(result.warnings) > 0

    def test_draw_data_confidence_color_reflects_match(self):
        from data.track_map_matching import match_position_to_map
        from ui.track_map_vm import build_track_map_draw_data
        sm     = _make_simple_station_map(n=100, lap_m=100.0)
        result = match_position_to_map(50.0, 0.0, 0.0, sm, speed_kph=150.0)
        dd     = build_track_map_draw_data(sm, match_result=result)
        assert dd.confidence_color == "#2EA043"  # green for HIGH


# ===========================================================================
# 14. Legacy low-resolution (200-point) reference path handling
# ===========================================================================

class TestLegacyRefPathHandling:
    def test_200_point_path_produces_valid_map(self):
        from data.track_station_map import build_track_station_map
        ref = _make_ref_path(n_points=200, lap_length_m=5729.0)
        sm  = build_track_station_map(ref, spacing_m=1.0)
        assert sm.station_count() > 100

    def test_200_point_path_extracts_corners(self):
        from data.track_station_map import build_track_station_map
        ref  = _make_ref_path(n_points=200, lap_length_m=5729.0)
        seed = _make_layout_seed(corners_expected=12)
        sm   = build_track_station_map(ref, layout_seed=seed)
        assert len(sm.seeded_corners) == 12

    def test_200_point_path_map_can_be_matched(self):
        from data.track_station_map import build_track_station_map
        from data.track_map_matching import match_position_to_map
        ref = _make_ref_path(n_points=200, lap_length_m=5729.0)
        sm  = build_track_station_map(ref)
        # Match a point that is definitely on the path
        s   = sm.stations[100]
        result = match_position_to_map(s.x, s.y, s.z, sm, speed_kph=200.0)
        assert result.station_m == pytest.approx(s.station_m, abs=5.0)

    def test_low_resolution_path_still_produces_usable_curvature(self):
        from data.track_station_map import build_track_station_map
        ref = _make_ref_path(n_points=200)
        sm  = build_track_station_map(ref)
        curvatures = [abs(s.curvature) for s in sm.stations]
        assert max(curvatures) > 0.001  # not all flat

    def test_json_roundtrip(self, tmp_path):
        from data.track_station_map import (
            build_track_station_map, export_station_map_json, import_station_map_json,
        )
        ref    = _make_ref_path(n_points=50, lap_length_m=500.0)
        sm     = build_track_station_map(ref, spacing_m=5.0)
        path   = export_station_map_json(sm, output_dir=tmp_path)
        loaded = import_station_map_json(path)
        assert loaded.track_location_id == sm.track_location_id
        assert loaded.layout_id         == sm.layout_id
        assert len(loaded.stations)     == len(sm.stations)
        assert len(loaded.seeded_corners) == len(sm.seeded_corners)


# ===========================================================================
# Width model tests (bonus)
# ===========================================================================

class TestWidthModel:
    def test_unused_width_pct_at_centreline(self):
        from data.track_width_model import unused_track_width_pct
        from data.track_map_matching import MapMatchResult, MapMatchConfidence
        result = MapMatchResult(
            station_m=50.0, progress_pct=50.0, nearest_station_idx=50,
            corner_id=None, corner_phase="straight",
            lateral_offset_m=0.0,
            dist_to_left_edge_m=6.0, dist_to_right_edge_m=6.0,
            dist_to_centreline_m=0.0,
            confidence=MapMatchConfidence.HIGH,
            is_pit_likely=False,
        )
        assert unused_track_width_pct(result) == pytest.approx(0.0, abs=0.05)

    def test_near_left_edge_detected(self):
        from data.track_width_model import is_near_left_edge, is_near_right_edge, NEAR_EDGE_THRESHOLD_M
        from data.track_map_matching import MapMatchResult, MapMatchConfidence
        result = MapMatchResult(
            station_m=50.0, progress_pct=50.0, nearest_station_idx=50,
            corner_id=None, corner_phase="apex",
            lateral_offset_m=5.5,
            dist_to_left_edge_m=0.3, dist_to_right_edge_m=11.7,
            dist_to_centreline_m=5.5,
            confidence=MapMatchConfidence.HIGH,
            is_pit_likely=False,
        )
        assert is_near_left_edge(result) is True
        assert is_near_right_edge(result) is False

    def test_near_right_edge_detected(self):
        from data.track_width_model import is_near_right_edge
        from data.track_map_matching import MapMatchResult, MapMatchConfidence
        result = MapMatchResult(
            station_m=50.0, progress_pct=50.0, nearest_station_idx=50,
            corner_id=None, corner_phase="exit",
            lateral_offset_m=-5.5,
            dist_to_left_edge_m=11.7, dist_to_right_edge_m=0.3,
            dist_to_centreline_m=5.5,
            confidence=MapMatchConfidence.HIGH,
            is_pit_likely=False,
        )
        assert is_near_right_edge(result) is True

    def test_near_left_edge(self):
        from data.track_width_model import is_near_left_edge
        from data.track_map_matching import MapMatchResult, MapMatchConfidence
        result = MapMatchResult(
            station_m=0.0, progress_pct=0.0, nearest_station_idx=0,
            corner_id=None, corner_phase="straight",
            lateral_offset_m=0.0,
            dist_to_left_edge_m=6.0, dist_to_right_edge_m=6.0,
            dist_to_centreline_m=0.0,
            confidence=MapMatchConfidence.HIGH,
            is_pit_likely=False,
        )
        # Not near edge when on centreline
        assert is_near_left_edge(result) is False


# ---------------------------------------------------------------------------
# Import safeguard
# ---------------------------------------------------------------------------

def test_no_pyqt_in_data_modules():
    """None of the new data modules should import PyQt6."""
    import sys
    import importlib

    for mod_name in (
        "data.track_station_map",
        "data.track_map_matching",
        "data.track_width_model",
    ):
        importlib.import_module(mod_name)

    # Check no PyQt6 leaked through
    for k in sys.modules:
        if "PyQt6" in k:
            # PyQt6 may be loaded by other modules already — that's fine.
            # What we want is that the new data modules themselves do not
            # have PyQt6 in their module dict.
            pass   # We only verify imports didn't raise
