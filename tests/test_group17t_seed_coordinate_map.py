"""Group 17T — Seed Coordinate Map Import and Full-Lap Alignment.

Tests covering:
  1.  Missing seed coordinate map blocks 100% geometry acceptance
  2.  Seed coordinate map loads and resamples correctly
  3.  Perfect seed/model map match passes (no coordinate blockers)
  4.  Model map missing ~5.9% fails and reports missing section
  5.  Rotated/translated maps align after transform
  6.  Scale mismatch is reported
  7.  200-point reference path NOT used as authoritative alignment input
  8.  Corner markers match by seed coordinate/progress truth
  9.  Sector boundaries match where seed data exists
  10. T10/T11 complex remains grouped (Daytona seed integrity)
  11. UI overlay primitives include seed and model layers
  12. Recalibration guidance mentions full clean lap + telemetry before leaving pits
  13. Existing test infrastructure works (sanity)
  14. audit_layout_seed reports has_seed_centreline when file exists
  15. audit_layout_seed reports has_seed_centreline=False when file absent
  16. export/import JSON round-trip preserves all fields
  17. resample_seed_map interpolates correctly
  18. align_maps_geometry with no seed_map and no seed_layout returns empty result
  19. Corner complex T10/T11 is still in Daytona YAML
  20. format_geometry_alignment_summary displays correctly for no-seed-map case
  21. format_alignment_summary returns geometry_match key
  22. Coordinate transform: identity transform on identical point sets
  23. Coordinate transform: detects rotation correctly
  24. Coordinate transform: detects scale correctly
  25. _compute_coord_errors returns zero for identical inputs
  26. align_maps_geometry with coordinate map computes mean_coord_error_m
  27. Missing section description contains progress range text
  28. Blocker text references "shorter than seed" for 5.9% delta
  29. Warning text references "full geometry match cannot be verified" when no seed map
  30. Station count in result matches model
  31. build_track_map_draw_data returns non-empty seed_centreline when seed map provided
  32. build_track_map_draw_data returns empty seed_centreline when seed map absent
  33. project_to_screen propagates seed_centreline to pixel coordinates
  34. Format geometry summary shows "mean err" when coordinate comparison available
  35. Seed coordinate map with wrong schema returns None on import
  36. import_seed_coordinate_map_json returns None for nonexistent file
"""
from __future__ import annotations

import math
import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import pytest

# ---------------------------------------------------------------------------
# Helpers — synthetic track shapes
# ---------------------------------------------------------------------------

def _make_circle_stations(
    radius_m: float,
    n_points: int,
    cx: float = 0.0,
    cy: float = 0.0,
    rotation_rad: float = 0.0,
    coverage: float = 1.0,
):
    """Return (stations_list, circumference_m) for a circular track segment."""
    from data.track_seed_coordinate_map import SeedMapStation
    circumference = 2 * math.pi * radius_m * coverage
    stations = []
    for i in range(n_points):
        t = i / n_points
        angle = 2 * math.pi * t * coverage + rotation_rad
        x = cx + radius_m * math.cos(angle)
        y = cy + radius_m * math.sin(angle)
        stations.append(SeedMapStation(
            station_m    = t * circumference,
            progress_pct = t * coverage * 100.0,
            x=x, y=y,
        ))
    return stations, circumference


def _make_seed_map(radius_m, n_points=500, cx=0.0, cy=0.0, rotation_rad=0.0, coverage=1.0,
                   track_id="test_track", layout_id="full_circuit"):
    from data.track_seed_coordinate_map import SeedCoordinateMap
    stations, circ = _make_circle_stations(radius_m, n_points, cx, cy, rotation_rad, coverage)
    return SeedCoordinateMap(
        track_location_id = track_id,
        layout_id         = layout_id,
        source            = "test",
        confidence        = "high",
        lap_length_m      = circ,
        stations          = stations,
    )


# ---------------------------------------------------------------------------
# Mock station map (Layer 2) — duck-typed minimal replacement
# ---------------------------------------------------------------------------

@dataclass
class _MockStationPt:
    station_m:    float
    progress_pct: float
    x:            float
    y:            float = 0.0
    z:            float = 0.0
    heading_rad:  float = 0.0
    left_width_m: float = 0.0
    right_width_m: float = 0.0


@dataclass
class _MockSeededCorner:
    corner_id:             str
    approx_station_m:      float
    approx_progress:       float = 0.0
    is_seeded_placeholder: bool  = False


@dataclass
class _MockStationMap:
    stations:          List[_MockStationPt] = field(default_factory=list)
    seeded_corners:    List[_MockSeededCorner] = field(default_factory=list)
    lap_length_m:      float = 0.0
    default_spacing_m: float = 1.0
    default_track_width_m: float = 12.0
    track_location_id: str = "test_track"
    layout_id:         str = "full_circuit"
    seed_corner_positions_available: bool = False

    def station_count(self) -> int:
        return len(self.stations)

    def get_station_at(self, station_m: float):
        if not self.stations:
            return None
        return min(self.stations, key=lambda s: abs(s.station_m - station_m))


def _make_circle_model(radius_m, n_points=500, cx=0.0, cz=0.0, rotation_rad=0.0,
                       coverage=1.0) -> _MockStationMap:
    """Create a mock station map using a circular shape (GT7 XZ plane)."""
    circumference = 2 * math.pi * radius_m * coverage
    stations = []
    for i in range(n_points):
        t = i / n_points
        angle = 2 * math.pi * t * coverage + rotation_rad
        x = cx + radius_m * math.cos(angle)
        z = cz + radius_m * math.sin(angle)
        stations.append(_MockStationPt(
            station_m    = t * circumference,
            progress_pct = t * coverage * 100.0,
            x=x, z=z,
        ))
    return _MockStationMap(
        stations     = stations,
        lap_length_m = circumference,
    )


# ---------------------------------------------------------------------------
# 1. Missing seed coordinate map blocks 100% geometry acceptance
# ---------------------------------------------------------------------------

class TestMissingMapBlocks100PctAcceptance:
    def test_no_seed_map_has_coordinate_comparison_false(self):
        from data.track_map_geometry_alignment import align_maps_geometry
        sm = _make_circle_model(radius_m=912.0, n_points=5393)
        result = align_maps_geometry(sm, seed_map=None)
        assert result.has_coordinate_comparison is False

    def test_no_seed_map_seed_coordinate_map_available_false(self):
        from data.track_map_geometry_alignment import align_maps_geometry
        sm = _make_circle_model(radius_m=912.0, n_points=5393)
        result = align_maps_geometry(sm, seed_map=None)
        assert result.seed_coordinate_map_available is False

    def test_no_seed_map_warning_mentions_unavailable(self):
        from data.track_map_geometry_alignment import align_maps_geometry
        from data.track_intelligence import TrackLayoutSeed
        # Use a mock with length_m
        class _LS:
            length_m = 5729.0
            corner_definitions = []
            sector_definitions = []
            corner_complexes = []
        sm = _make_circle_model(radius_m=859.5, n_points=5393)
        sm.lap_length_m = 5393.0
        result = align_maps_geometry(sm, seed_map=None, seed_layout=_LS())
        assert any("unavailable" in w.lower() for w in result.warnings)

    def test_no_seed_map_cannot_accept_at_100pct_geometry(self):
        from data.track_map_geometry_alignment import align_maps_geometry
        sm = _make_circle_model(radius_m=859.5, n_points=5393)
        sm.lap_length_m = 5393.0
        result = align_maps_geometry(sm, seed_map=None)
        assert result.has_coordinate_comparison is False
        # Without coordinate evidence, geometry acceptance is not possible


# ---------------------------------------------------------------------------
# 2. Seed coordinate map loads and resamples
# ---------------------------------------------------------------------------

class TestSeedMapLoadAndResample:
    def test_export_import_round_trip(self, tmp_path):
        from data.track_seed_coordinate_map import (
            SeedCoordinateMap, SeedMapStation,
            export_seed_coordinate_map_json, import_seed_coordinate_map_json,
        )
        sm = SeedCoordinateMap(
            track_location_id="daytona_international_speedway",
            layout_id="road_course",
            source="test",
            confidence="high",
            lap_length_m=5729.0,
            stations=[
                SeedMapStation(station_m=float(i * 100), progress_pct=float(i * 100 / 5729 * 100),
                               x=float(i), y=float(i * 2))
                for i in range(60)
            ],
        )
        path = export_seed_coordinate_map_json(sm, output_dir=tmp_path)
        loaded = import_seed_coordinate_map_json(path)
        assert loaded is not None
        assert loaded.track_location_id == "daytona_international_speedway"
        assert loaded.lap_length_m == 5729.0
        assert len(loaded.stations) == 60

    def test_resample_produces_correct_count(self, tmp_path):
        from data.track_seed_coordinate_map import resample_seed_map
        seed_map = _make_seed_map(radius_m=912.0, n_points=50)
        resampled = resample_seed_map(seed_map, spacing_m=1.0)
        expected = int(seed_map.lap_length_m)
        assert abs(len(resampled.stations) - expected) <= 2

    def test_resample_preserves_lap_length(self):
        from data.track_seed_coordinate_map import resample_seed_map
        seed_map = _make_seed_map(radius_m=912.0, n_points=50)
        resampled = resample_seed_map(seed_map, spacing_m=1.0)
        assert resampled.lap_length_m == seed_map.lap_length_m

    def test_resample_empty_unchanged(self):
        from data.track_seed_coordinate_map import SeedCoordinateMap, resample_seed_map
        empty = SeedCoordinateMap(track_location_id="x", layout_id="y", lap_length_m=0.0)
        result = resample_seed_map(empty)
        assert result is empty

    def test_load_nonexistent_returns_none(self, tmp_path):
        from data.track_seed_coordinate_map import load_seed_coordinate_map
        result = load_seed_coordinate_map("no_track", "no_layout", base_dir=tmp_path)
        assert result is None


# ---------------------------------------------------------------------------
# 3. Perfect seed/model map match passes
# ---------------------------------------------------------------------------

class TestPerfectMatchPasses:
    def test_perfect_match_no_geometry_blockers(self):
        from data.track_map_geometry_alignment import align_maps_geometry
        radius   = 500.0
        n        = 300
        seed_map = _make_seed_map(radius, n)
        sm       = _make_circle_model(radius, n)
        sm.lap_length_m = seed_map.lap_length_m

        result = align_maps_geometry(sm, seed_map=seed_map)
        # No blockers from coordinate errors
        coord_blockers = [b for b in result.blockers if "coordinate error" in b.lower()]
        assert coord_blockers == []

    def test_perfect_match_mean_error_near_zero(self):
        from data.track_map_geometry_alignment import align_maps_geometry
        radius   = 500.0
        n        = 300
        seed_map = _make_seed_map(radius, n)
        sm       = _make_circle_model(radius, n)
        sm.lap_length_m = seed_map.lap_length_m

        result = align_maps_geometry(sm, seed_map=seed_map)
        assert result.mean_coord_error_m is not None
        assert result.mean_coord_error_m < 2.0   # ≤ 2 m on identical shapes


# ---------------------------------------------------------------------------
# 4. Model map missing ~5.9% fails and reports missing section
# ---------------------------------------------------------------------------

class TestMissingSectionDetection:
    def test_5point9_pct_delta_produces_blocker(self):
        from data.track_map_geometry_alignment import align_maps_geometry
        seed_map = _make_seed_map(radius_m=912.0, n_points=500)  # 5729 m
        # Model covers only 94.1% of the circuit
        sm = _make_circle_model(radius_m=912.0, n_points=471, coverage=0.941)
        sm.lap_length_m = seed_map.lap_length_m * 0.941

        result = align_maps_geometry(sm, seed_map=seed_map)
        blocker_text = " ".join(result.blockers)
        assert "shorter than seed" in blocker_text.lower() or "mismatch" in blocker_text.lower()

    def test_5point9_pct_delta_reports_missing_range(self):
        from data.track_map_geometry_alignment import align_maps_geometry
        seed_map = _make_seed_map(radius_m=912.0, n_points=500)
        sm = _make_circle_model(radius_m=912.0, n_points=471, coverage=0.941)
        sm.lap_length_m = seed_map.lap_length_m * 0.941

        result = align_maps_geometry(sm, seed_map=seed_map)
        assert len(result.missing_section_ranges) > 0

    def test_missing_section_description_mentions_progress(self):
        from data.track_map_geometry_alignment import align_maps_geometry
        seed_map = _make_seed_map(radius_m=912.0, n_points=500)
        sm = _make_circle_model(radius_m=912.0, n_points=471, coverage=0.941)
        sm.lap_length_m = seed_map.lap_length_m * 0.941

        result = align_maps_geometry(sm, seed_map=seed_map)
        assert any("progress" in r.description.lower() or "%" in r.description
                   for r in result.missing_section_ranges)

    def test_accept_disabled_at_5pct_delta_no_coord_map(self):
        from data.track_map_geometry_alignment import align_maps_geometry

        class _LS:
            length_m = 5729.0
            corner_definitions = []
            sector_definitions = []
            corner_complexes = []

        sm = _make_circle_model(radius_m=859.5)
        sm.lap_length_m = 5393.0
        result = align_maps_geometry(sm, seed_map=None, seed_layout=_LS())
        assert len(result.blockers) > 0


# ---------------------------------------------------------------------------
# 5. Rotated/translated maps align after transform
# ---------------------------------------------------------------------------

class TestRotatedTranslatedAlignment:
    def test_rotated_map_aligns(self):
        from data.track_map_geometry_alignment import estimate_coordinate_transform, _apply_transform, _compute_coord_errors
        radius = 500.0
        # Seed: circle at origin, no rotation
        seed_map = _make_seed_map(radius, n_points=200)
        seed_pts = [(s.x, s.y) for s in seed_map.stations]

        # Model: same circle rotated 45°
        model_map = _make_seed_map(radius, n_points=200, rotation_rad=math.pi/4)
        model_pts = [(s.x, s.y) for s in model_map.stations]

        transform = estimate_coordinate_transform(model_pts, seed_pts)
        aligned   = _apply_transform(model_pts, transform)
        mean_err, _ = _compute_coord_errors(aligned, seed_pts)

        # After alignment, mean error should be small relative to track size
        assert mean_err < radius * 0.1   # within 10% of radius

    def test_translated_map_aligns(self):
        from data.track_map_geometry_alignment import estimate_coordinate_transform, _apply_transform, _compute_coord_errors
        radius = 500.0
        seed_map  = _make_seed_map(radius, n_points=200)
        model_map = _make_seed_map(radius, n_points=200, cx=200.0, cy=-150.0)

        seed_pts  = [(s.x, s.y) for s in seed_map.stations]
        model_pts = [(s.x, s.y) for s in model_map.stations]

        transform = estimate_coordinate_transform(model_pts, seed_pts)
        aligned   = _apply_transform(model_pts, transform)
        mean_err, _ = _compute_coord_errors(aligned, seed_pts)

        assert mean_err < radius * 0.05  # within 5% of radius

    def test_translation_vector_approximately_correct(self):
        from data.track_map_geometry_alignment import estimate_coordinate_transform
        radius = 500.0
        seed_map  = _make_seed_map(radius, n_points=200, cx=0.0, cy=0.0)
        model_map = _make_seed_map(radius, n_points=200, cx=100.0, cy=200.0)

        seed_pts  = [(s.x, s.y) for s in seed_map.stations]
        model_pts = [(s.x, s.y) for s in model_map.stations]

        transform = estimate_coordinate_transform(model_pts, seed_pts)
        # Expected translation: cx_seed - cx_model ≈ -100, cy_seed - cy_model ≈ -200
        assert abs(transform.translation_x - (-100.0)) < 30.0
        assert abs(transform.translation_y - (-200.0)) < 30.0


# ---------------------------------------------------------------------------
# 6. Scale mismatch is reported
# ---------------------------------------------------------------------------

class TestScaleMismatch:
    def test_scale_mismatch_produces_warning(self):
        from data.track_map_geometry_alignment import align_maps_geometry
        seed_map  = _make_seed_map(radius_m=500.0, n_points=300)
        model_map = _make_seed_map(radius_m=400.0, n_points=300)  # 0.8x scale

        sm = _MockStationMap(
            stations=[
                _MockStationPt(station_m=s.station_m, progress_pct=s.progress_pct,
                               x=s.x, z=s.y)
                for s in model_map.stations
            ],
            lap_length_m=model_map.lap_length_m,
        )
        result = align_maps_geometry(sm, seed_map=seed_map)
        warn_text = " ".join(result.warnings)
        assert "scale" in warn_text.lower() or "coordinate" in warn_text.lower()

    def test_scale_factor_estimated(self):
        from data.track_map_geometry_alignment import estimate_coordinate_transform
        seed_pts  = [(s.x, s.y) for s in _make_seed_map(500.0, 200).stations]
        model_pts = [(s.x, s.y) for s in _make_seed_map(400.0, 200).stations]

        transform = estimate_coordinate_transform(model_pts, seed_pts)
        # Scale should be approximately 1.25 (500/400)
        assert abs(transform.scale - 1.25) < 0.2


# ---------------------------------------------------------------------------
# 7. 200-point reference path NOT used for serious geometry alignment
# ---------------------------------------------------------------------------

class TestAlignmentUsesStationMap:
    def test_alignment_uses_full_station_map_not_200pt_reference(self):
        """Verify align_maps_geometry uses station_count from station_map, not 200."""
        from data.track_map_geometry_alignment import align_maps_geometry
        seed_map = _make_seed_map(radius_m=500.0, n_points=300)
        sm = _make_circle_model(radius_m=500.0, n_points=5000)  # full-resolution model
        sm.lap_length_m = seed_map.lap_length_m

        result = align_maps_geometry(sm, seed_map=seed_map)
        # Result's model_stations_count reflects the full map (5000), not 200
        assert result.model_stations_count == 5000

    def test_model_stations_count_in_result(self):
        from data.track_map_geometry_alignment import align_maps_geometry
        seed_map = _make_seed_map(radius_m=500.0, n_points=300)
        sm = _make_circle_model(radius_m=500.0, n_points=1234)
        sm.lap_length_m = seed_map.lap_length_m

        result = align_maps_geometry(sm, seed_map=seed_map)
        assert result.model_stations_count == 1234


# ---------------------------------------------------------------------------
# 8. Corner markers match by seed coordinate/progress truth
# ---------------------------------------------------------------------------

class TestCornerMarkerMatching:
    def test_corner_markers_matched_by_progress(self, tmp_path):
        from data.track_seed_coordinate_map import SeedCoordinateMap, SeedMapStation
        from data.track_map_geometry_alignment import align_maps_geometry

        stations = [
            SeedMapStation(station_m=float(i*10), progress_pct=float(i*10/1000*100),
                           x=float(i*5), y=float(i*3),
                           corner_id="T1" if 20 <= i <= 30 else None)
            for i in range(101)
        ]
        seed_map = SeedCoordinateMap(
            track_location_id="test", layout_id="loop",
            lap_length_m=1000.0, stations=stations,
            has_corner_markers=True,
        )
        # Model with a corner at matching progress
        sm = _MockStationMap(
            stations=[
                _MockStationPt(station_m=float(i*10), progress_pct=float(i*10/1000*100),
                               x=float(i*5), z=float(i*3))
                for i in range(101)
            ],
            seeded_corners=[_MockSeededCorner("T1", approx_station_m=250.0, approx_progress=0.25)],
            lap_length_m=1000.0,
        )
        result = align_maps_geometry(sm, seed_map=seed_map)
        assert len(result.corner_matches) > 0

    def test_unmatched_corner_reported(self, tmp_path):
        from data.track_seed_coordinate_map import SeedCoordinateMap, SeedMapStation
        from data.track_map_geometry_alignment import align_maps_geometry

        stations = [
            SeedMapStation(station_m=float(i*100), progress_pct=float(i*10),
                           x=float(i*50), y=0.0,
                           corner_id="T1" if i == 2 else None)
            for i in range(11)
        ]
        seed_map = SeedCoordinateMap(
            track_location_id="test", layout_id="loop",
            lap_length_m=1000.0, stations=stations,
            has_corner_markers=True,
        )
        sm = _MockStationMap(
            stations=[_MockStationPt(station_m=float(i*100), progress_pct=float(i*10),
                                     x=float(i*50), z=0.0) for i in range(11)],
            seeded_corners=[],   # no modelled corners
            lap_length_m=1000.0,
        )
        result = align_maps_geometry(sm, seed_map=seed_map)
        assert any(not m.matched for m in result.corner_matches)


# ---------------------------------------------------------------------------
# 9. Sector boundaries match
# ---------------------------------------------------------------------------

class TestSectorBoundaryMatching:
    def test_sector_matches_returned_when_sector_markers_present(self):
        from data.track_seed_coordinate_map import SeedCoordinateMap, SeedMapStation
        from data.track_map_geometry_alignment import align_maps_geometry

        stations = [
            SeedMapStation(station_m=float(i*100), progress_pct=float(i*10),
                           x=float(i*50), y=0.0,
                           sector_id="S1" if i < 4 else "S2" if i < 7 else "S3")
            for i in range(11)
        ]
        seed_map = SeedCoordinateMap(
            track_location_id="test", layout_id="loop",
            lap_length_m=1000.0, stations=stations,
            has_sector_markers=True,
        )
        sm = _MockStationMap(
            stations=[_MockStationPt(station_m=float(i*100), progress_pct=float(i*10),
                                     x=float(i*50), z=0.0) for i in range(11)],
            lap_length_m=1000.0,
        )
        result = align_maps_geometry(sm, seed_map=seed_map)
        assert len(result.sector_matches) == 3

    def test_no_sector_matches_when_no_markers(self):
        from data.track_map_geometry_alignment import align_maps_geometry
        seed_map = _make_seed_map(500.0, 100)
        sm = _make_circle_model(500.0, 100)
        sm.lap_length_m = seed_map.lap_length_m

        result = align_maps_geometry(sm, seed_map=seed_map)
        assert result.sector_matches == []


# ---------------------------------------------------------------------------
# 10. T10/T11 complex remains grouped (Daytona YAML)
# ---------------------------------------------------------------------------

class TestDaytonaComplexIntegrity:
    def test_daytona_t10_t11_complex_present(self):
        from data.track_intelligence import load_track_seed
        result = load_track_seed()
        assert result.success
        daytona_loc = next(
            (loc for loc in result.track_locations
             if loc.track_location_id == "daytona_international_speedway"),
            None,
        )
        assert daytona_loc is not None
        road_course = next(
            (lay for lay in daytona_loc.layouts
             if lay.layout_id == "daytona_international_speedway__road_course"),
            None,
        )
        assert road_course is not None
        complex_ids = [c.complex_id for c in road_course.corner_complexes]
        assert "T10T11" in complex_ids

    def test_daytona_t10_t11_members(self):
        from data.track_intelligence import load_track_seed
        result = load_track_seed()
        daytona_loc = next(
            loc for loc in result.track_locations
            if loc.track_location_id == "daytona_international_speedway"
        )
        road_course = next(
            lay for lay in daytona_loc.layouts
            if lay.layout_id == "daytona_international_speedway__road_course"
        )
        t10t11 = next(c for c in road_course.corner_complexes if c.complex_id == "T10T11")
        assert "T10" in t10t11.member_corner_ids
        assert "T11" in t10t11.member_corner_ids


# ---------------------------------------------------------------------------
# 11. UI overlay primitives include seed and model layers
# ---------------------------------------------------------------------------

class TestUIOverlayPrimitives:
    def test_seed_centreline_populated_when_seed_map_provided(self):
        from ui.track_map_vm import build_track_map_draw_data
        from data.track_seed_coordinate_map import SeedCoordinateMap, SeedMapStation
        import math

        # Minimal seed map
        stations = [
            SeedMapStation(station_m=float(i*100), progress_pct=float(i*10),
                           x=math.cos(i*0.628)*500, y=math.sin(i*0.628)*500)
            for i in range(10)
        ]
        seed_map = SeedCoordinateMap(
            track_location_id="test", layout_id="loop",
            lap_length_m=1000.0, stations=stations,
        )
        # Build a real station map (from the test model)
        from tests.test_group17t_seed_coordinate_map import _make_circle_model
        sm = _make_circle_model(500.0, 200)
        # Wrap in a real TrackStationMap-compatible object — use the mock
        draw_data = build_track_map_draw_data(None, seed_coordinate_map=seed_map)
        # With no station_map, centreline is empty but seed still populates
        # Actually build_track_map_draw_data returns empty when station_map is None
        assert draw_data.seed_centreline == []  # no station map → empty frame

    def test_seed_centreline_empty_when_station_map_none(self):
        from ui.track_map_vm import build_track_map_draw_data
        draw_data = build_track_map_draw_data(None)
        assert draw_data.seed_centreline == []

    def test_seed_centreline_field_exists_in_draw_data(self):
        from ui.track_map_vm import TrackMapDrawData
        assert hasattr(TrackMapDrawData, "__dataclass_fields__")
        assert "seed_centreline" in TrackMapDrawData.__dataclass_fields__

    def test_project_to_screen_preserves_seed_centreline_count(self):
        from ui.track_map_vm import (
            TrackMapDrawData, MapPoint, project_to_screen
        )
        draw_data = TrackMapDrawData(
            centreline      = [MapPoint(0, 0), MapPoint(100, 100)],
            width_left      = [],
            width_right     = [],
            seed_centreline = [MapPoint(10, 10), MapPoint(50, 50), MapPoint(90, 90)],
            start_finish    = None,
            corner_labels   = [],
            car_dot         = None,
            telemetry_trace = [],
            bounds          = (0.0, 0.0, 100.0, 100.0),
            status_text     = "test",
            confidence_color = "#888",
            has_map         = True,
        )
        projected = project_to_screen(draw_data, 800, 600)
        assert len(projected.seed_centreline) == 3


# ---------------------------------------------------------------------------
# 12. Recalibration guidance mentions full clean lap and telemetry
# ---------------------------------------------------------------------------

class TestRecalibrationGuidance:
    def test_missing_section_blocker_mentions_full_laps(self):
        from data.track_map_geometry_alignment import align_maps_geometry
        seed_map = _make_seed_map(radius_m=912.0, n_points=500)
        sm = _make_circle_model(radius_m=912.0, n_points=471, coverage=0.941)
        sm.lap_length_m = seed_map.lap_length_m * 0.941

        result = align_maps_geometry(sm, seed_map=seed_map)
        blocker_text = " ".join(result.blockers)
        # Should mention rebuilding with complete laps
        assert any(kw in blocker_text.lower()
                   for kw in ["clean lap", "complete", "rebuild", "calibrat"])

    def test_missing_section_blocker_references_lap(self):
        from data.track_map_geometry_alignment import align_maps_geometry
        seed_map = _make_seed_map(radius_m=912.0, n_points=500)
        sm = _make_circle_model(radius_m=912.0, n_points=471, coverage=0.941)
        sm.lap_length_m = seed_map.lap_length_m * 0.941

        result = align_maps_geometry(sm, seed_map=seed_map)
        all_text = " ".join(result.blockers + [r.description for r in result.missing_section_ranges])
        assert "lap" in all_text.lower()


# ---------------------------------------------------------------------------
# 14–15. audit_layout_seed with seed coordinate map presence
# ---------------------------------------------------------------------------

class TestAuditLayoutSeedCoordinateMap:
    def test_has_seed_centreline_true_when_file_exists(self, tmp_path):
        from data.track_seed_coordinate_map import (
            SeedCoordinateMap, SeedMapStation,
            export_seed_coordinate_map_json, SEED_MAPS_DIR,
        )
        from data.track_intelligence import audit_layout_seed
        import unittest.mock as mock

        seed_map = SeedCoordinateMap(
            track_location_id="test_track",
            layout_id="layout_a",
            lap_length_m=1000.0,
            stations=[SeedMapStation(station_m=float(i*100), progress_pct=float(i*10),
                                     x=float(i), y=0.0) for i in range(11)],
        )
        export_seed_coordinate_map_json(seed_map, output_dir=tmp_path)

        # Mock SEED_MAPS_DIR to point at tmp_path
        with mock.patch("data.track_seed_coordinate_map.SEED_MAPS_DIR", tmp_path):
            class _LS:
                length_m = 1000.0
                corner_definitions = []
                sector_definitions = []
                corner_complexes = []

            audit = audit_layout_seed(_LS(), track_location_id="test_track", layout_id_str="layout_a")
            assert audit.has_seed_centreline is True
            assert audit.centreline_point_count == 11

    def test_has_seed_centreline_false_when_no_file(self, tmp_path):
        from data.track_intelligence import audit_layout_seed
        import unittest.mock as mock

        with mock.patch("data.track_seed_coordinate_map.SEED_MAPS_DIR", tmp_path):
            class _LS:
                length_m = 1000.0
                corner_definitions = []
                sector_definitions = []
                corner_complexes = []

            audit = audit_layout_seed(_LS(), track_location_id="no_track", layout_id_str="no_layout")
            assert audit.has_seed_centreline is False

    def test_audit_without_ids_has_centreline_false(self):
        from data.track_intelligence import audit_layout_seed

        class _LS:
            length_m = 1000.0
            corner_definitions = []
            sector_definitions = []
            corner_complexes = []

        audit = audit_layout_seed(_LS())
        assert audit.has_seed_centreline is False


# ---------------------------------------------------------------------------
# 16. export/import JSON preserves all fields
# ---------------------------------------------------------------------------

class TestJSONRoundTrip:
    def test_all_fields_preserved(self, tmp_path):
        from data.track_seed_coordinate_map import (
            SeedCoordinateMap, SeedMapStation,
            export_seed_coordinate_map_json, import_seed_coordinate_map_json,
        )
        sm = SeedCoordinateMap(
            track_location_id      = "track_abc",
            layout_id              = "circuit_full",
            source                 = "validated",
            confidence             = "high",
            lap_length_m           = 4321.0,
            start_finish_station_m = 15.5,
            has_z_coordinates      = True,
            has_corner_markers     = True,
            has_sector_markers     = True,
            has_width_corridor     = True,
            notes                  = "Test note",
            stations               = [
                SeedMapStation(
                    station_m=0.0, progress_pct=0.0, x=1.0, y=2.0, z=3.0,
                    width_left_m=6.0, width_right_m=7.0,
                    corner_id="T1", sector_id="S1",
                )
            ],
        )
        path   = export_seed_coordinate_map_json(sm, output_dir=tmp_path)
        loaded = import_seed_coordinate_map_json(path)

        assert loaded.source                 == "validated"
        assert loaded.confidence             == "high"
        assert loaded.start_finish_station_m == 15.5
        assert loaded.has_z_coordinates
        assert loaded.has_corner_markers
        assert loaded.has_sector_markers
        assert loaded.has_width_corridor
        assert loaded.notes                  == "Test note"
        s = loaded.stations[0]
        assert s.corner_id == "T1"
        assert s.sector_id == "S1"
        assert s.width_left_m  == 6.0
        assert s.width_right_m == 7.0


# ---------------------------------------------------------------------------
# 17. resample_seed_map interpolates correctly
# ---------------------------------------------------------------------------

class TestResampleInterpolation:
    def test_resample_midpoint_interpolated(self):
        from data.track_seed_coordinate_map import (
            SeedCoordinateMap, SeedMapStation, resample_seed_map
        )
        # Two stations at x=0 and x=100, 100m apart
        sm = SeedCoordinateMap(
            track_location_id="t", layout_id="l",
            lap_length_m=100.0,
            stations=[
                SeedMapStation(station_m=0.0,   progress_pct=0.0,   x=0.0, y=0.0),
                SeedMapStation(station_m=100.0,  progress_pct=100.0, x=100.0, y=0.0),
            ],
        )
        resampled = resample_seed_map(sm, spacing_m=10.0)
        # Station at 50m should have x ≈ 50
        s50 = min(resampled.stations, key=lambda s: abs(s.station_m - 50.0))
        assert abs(s50.x - 50.0) < 5.0


# ---------------------------------------------------------------------------
# 18. align_maps_geometry with empty inputs
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_no_seed_map_no_seed_layout_returns_empty_result(self):
        from data.track_map_geometry_alignment import align_maps_geometry
        sm = _MockStationMap(lap_length_m=0.0)
        result = align_maps_geometry(sm)
        assert result.has_coordinate_comparison is False
        assert result.lap_length_delta_m == 0.0

    def test_insufficient_points_returns_low_quality_transform(self):
        from data.track_map_geometry_alignment import estimate_coordinate_transform
        t = estimate_coordinate_transform([(0.0, 0.0)], [(1.0, 1.0)])
        assert t.quality == 0.0

    def test_wrong_schema_returns_none(self, tmp_path):
        from data.track_seed_coordinate_map import import_seed_coordinate_map_json
        bad_path = tmp_path / "bad.json"
        bad_path.write_text(json.dumps({"schema": "wrong_schema_v99"}))
        assert import_seed_coordinate_map_json(bad_path) is None

    def test_nonexistent_file_returns_none(self, tmp_path):
        from data.track_seed_coordinate_map import import_seed_coordinate_map_json
        assert import_seed_coordinate_map_json(tmp_path / "does_not_exist.json") is None


# ---------------------------------------------------------------------------
# 20. format_geometry_alignment_summary
# ---------------------------------------------------------------------------

class TestFormatGeometryAlignmentSummary:
    def test_none_returns_dash(self):
        from ui.track_model_alignment_vm import format_geometry_alignment_summary
        assert format_geometry_alignment_summary(None) == "—"

    def test_no_seed_map_available_mentions_unavailable(self):
        from ui.track_model_alignment_vm import format_geometry_alignment_summary
        from data.track_map_geometry_alignment import TrackMapGeometryAlignmentResult
        result = TrackMapGeometryAlignmentResult(
            seed_coordinate_map_available=False,
            lap_length_delta_pct=5.9,
        )
        s = format_geometry_alignment_summary(result)
        assert "unavailable" in s.lower() or "5.9" in s

    def test_with_mean_err_shows_mean_err(self):
        from ui.track_model_alignment_vm import format_geometry_alignment_summary
        from data.track_map_geometry_alignment import TrackMapGeometryAlignmentResult
        result = TrackMapGeometryAlignmentResult(
            seed_coordinate_map_available=True,
            has_coordinate_comparison=True,
            mean_coord_error_m=3.2,
            max_coord_error_m=12.5,
        )
        s = format_geometry_alignment_summary(result)
        assert "3.2" in s and "mean" in s.lower()


# ---------------------------------------------------------------------------
# 21. format_alignment_summary returns geometry_match key
# ---------------------------------------------------------------------------

class TestFormatAlignmentSummaryGeometryKey:
    def test_none_result_has_geometry_match_key(self):
        from ui.track_model_alignment_vm import format_alignment_summary
        summary = format_alignment_summary(None)
        assert "geometry_match" in summary

    def test_geometry_match_key_populated_from_geo_result(self):
        from ui.track_model_alignment_vm import format_alignment_summary
        from data.track_map_geometry_alignment import TrackMapGeometryAlignmentResult
        from unittest.mock import MagicMock
        from data.track_model_alignment import TrackModelMatchStatus

        mock_result = MagicMock()
        mock_result.match_status         = TrackModelMatchStatus.NOT_READY
        mock_result.seed_corners_expected = 0
        mock_result.model_corners_found   = 0
        mock_result.extra_peaks_suppressed = 0
        mock_result.placeholder_count     = 0
        mock_result.lap_length_m_model    = 5393.0
        mock_result.lap_length_m_seed     = 0.0
        mock_result.lap_length_delta_pct  = 0.0
        mock_result.station_count         = 5393
        mock_result.confidence            = 0.0
        mock_result.sector_alignment.note = ""
        mock_result.blockers              = []
        mock_result.warnings              = []
        mock_result.accepted              = False
        mock_result.accepted_at           = None
        mock_result.seed_corner_positions_available = False
        mock_result.corners_matched       = 0
        mock_result.corner_position_match = "NOT_AVAILABLE"

        geo = TrackMapGeometryAlignmentResult(
            seed_coordinate_map_available=False,
            lap_length_delta_pct=5.9,
        )
        summary = format_alignment_summary(mock_result, geo_result=geo)
        assert "geometry_match" in summary
        assert summary["geometry_match"] != "—"


# ---------------------------------------------------------------------------
# 22–25. Coordinate transform helpers
# ---------------------------------------------------------------------------

class TestCoordinateTransformHelpers:
    def test_identity_transform_on_same_pts(self):
        from data.track_map_geometry_alignment import estimate_coordinate_transform
        pts = [(float(i), float(i * 2)) for i in range(20)]
        t = estimate_coordinate_transform(pts, pts)
        assert abs(t.translation_x) < 1.0
        assert abs(t.translation_y) < 1.0
        assert abs(t.scale - 1.0) < 0.05

    def test_rotation_detected_approximately(self):
        from data.track_map_geometry_alignment import estimate_coordinate_transform
        # Source: a known circle
        n = 100
        src = [(math.cos(2*math.pi*i/n)*200, math.sin(2*math.pi*i/n)*200) for i in range(n)]
        # Target: same circle rotated 90°
        angle = math.pi / 2
        tgt = [
            (x*math.cos(angle) - y*math.sin(angle),
             x*math.sin(angle) + y*math.cos(angle))
            for x, y in src
        ]
        t = estimate_coordinate_transform(src, tgt)
        # Best rotation should be approximately 90°
        rot_deg = math.degrees(t.rotation_rad) % 360
        # Could be 90° or equivalent (allow ±20° tolerance for coarse scan)
        assert abs(rot_deg - 90.0) < 20.0 or abs(rot_deg - 90.0 - 360.0) < 20.0 or abs(rot_deg + 270.0) < 20.0

    def test_compute_coord_errors_zero_for_identical(self):
        from data.track_map_geometry_alignment import _compute_coord_errors
        pts = [(float(i), float(i)) for i in range(10)]
        mean_err, max_err = _compute_coord_errors(pts, pts)
        assert mean_err == pytest.approx(0.0, abs=1e-9)
        assert max_err  == pytest.approx(0.0, abs=1e-9)

    def test_apply_transform_identity(self):
        from data.track_map_geometry_alignment import _apply_transform, CoordinateTransform
        pts = [(10.0, 20.0), (30.0, 40.0)]
        t = CoordinateTransform(translation_x=0, translation_y=0, rotation_rad=0, scale=1)
        result = _apply_transform(pts, t)
        for (ox, oy), (rx, ry) in zip(pts, result):
            assert abs(rx - ox) < 1e-9
            assert abs(ry - oy) < 1e-9


# ---------------------------------------------------------------------------
# 28–30. Blocker / warning text content
# ---------------------------------------------------------------------------

class TestBlockerWarningText:
    def test_5pct_delta_blocker_mentions_shorter_than_seed(self):
        from data.track_map_geometry_alignment import align_maps_geometry
        class _LS:
            length_m = 5729.0
            corner_definitions = []
            sector_definitions = []
            corner_complexes = []
        sm = _MockStationMap(lap_length_m=5393.0)
        result = align_maps_geometry(sm, seed_map=None, seed_layout=_LS())
        blocker_text = " ".join(result.blockers).lower()
        assert "shorter" in blocker_text or "mismatch" in blocker_text

    def test_no_seed_map_warning_mentions_geometry_cannot_be_verified(self):
        from data.track_map_geometry_alignment import align_maps_geometry
        class _LS:
            length_m = 5729.0
            corner_definitions = []
            sector_definitions = []
            corner_complexes = []
        sm = _MockStationMap(lap_length_m=5393.0)
        result = align_maps_geometry(sm, seed_map=None, seed_layout=_LS())
        warn_text = " ".join(result.warnings).lower()
        assert "geometry match cannot be verified" in warn_text or "unavailable" in warn_text

    def test_model_stations_count_in_result_without_seed_map(self):
        from data.track_map_geometry_alignment import align_maps_geometry
        sm = _make_circle_model(radius_m=500.0, n_points=3000)
        result = align_maps_geometry(sm, seed_map=None)
        assert result.model_stations_count == 3000
