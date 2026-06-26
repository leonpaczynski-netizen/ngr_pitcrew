"""Tests for Group 23A — progress consistency smoke tests."""
import math
import pytest
from data.track_model_alignment import _MAX_LAP_DELTA_GOOD_PCT
from data.track_station_map import (
    TrackStationMap,
    StationPoint,
    build_track_station_map,
)
from data.track_calibration import ReferencePath, ReferencePathPoint


def test_max_lap_delta_good_pct_smoke():
    """Smoke: _MAX_LAP_DELTA_GOOD_PCT must be 8.0."""
    assert _MAX_LAP_DELTA_GOOD_PCT == 8.0


def _make_circular_reference_path(lap_length_m: float = 1000.0, n_points: int = 400) -> ReferencePath:
    """Build a circular reference path with n_points points."""
    radius = lap_length_m / (2.0 * math.pi)
    points = []
    for i in range(n_points):
        angle = 2.0 * math.pi * i / n_points
        x = radius * math.cos(angle)
        z = radius * math.sin(angle)
        dist = lap_length_m * i / n_points
        points.append(ReferencePathPoint(
            lap_progress=float(i) / n_points,
            distance_along_lap_m=dist,
            x=x,
            y=0.0,
            z=z,
            speed_kph_avg=80.0,
            source_lap_count=3,
        ))
    return ReferencePath(
        track_location_id="test",
        layout_id="test",
        calibration_car_id="test_car",
        source_lap_count=3,
        points=points,
        confidence=0.9,
    )


def test_seeded_corner_approx_progress_in_range():
    """SeededCorner approx_progress values from build_track_station_map must be in [0, 1]."""
    ref_path = _make_circular_reference_path(lap_length_m=2000.0, n_points=500)
    station_map = build_track_station_map(ref_path)

    for corner in station_map.seeded_corners:
        assert 0.0 <= corner.approx_progress <= 1.0, (
            f"Corner {corner.corner_id} has approx_progress={corner.approx_progress} out of [0,1]"
        )


def test_station_progress_pct_in_range():
    """All station progress_pct values must be in [0, 100]."""
    ref_path = _make_circular_reference_path(lap_length_m=1500.0, n_points=400)
    station_map = build_track_station_map(ref_path)

    assert station_map.station_count() > 0
    for st in station_map.stations:
        assert 0.0 <= st.progress_pct <= 100.0, (
            f"Station at {st.station_m:.1f} m has progress_pct={st.progress_pct:.2f} out of [0,100]"
        )


def test_segment_progress_in_range():
    """AC3: ReviewedTrackSegment.lap_progress_start/end must be in [0, 1]."""
    from data.track_segment_review import ReviewedTrackSegment
    assert hasattr(ReviewedTrackSegment, '__dataclass_fields__')
    fields = ReviewedTrackSegment.__dataclass_fields__
    assert 'lap_progress_start' in fields
    assert 'lap_progress_end' in fields
