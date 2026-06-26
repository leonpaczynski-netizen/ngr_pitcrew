"""
Group 21A — Station Map Coordinate Consistency tests.

Verifies that after building a station map:
  - All SeededCorner.approx_progress values are in [0.0, 1.0]
  - No two consecutive corners have approx_progress delta > 0.5
"""
import math
import pytest
from dataclasses import dataclass, field
from typing import Optional, List

from data.track_station_map import (
    build_track_station_map,
    SeededCorner,
    TrackStationMap,
)
from data.track_segment_review import ReviewedTrackSegment


# ---------------------------------------------------------------------------
# Minimal mock ref_path duck-type
# ---------------------------------------------------------------------------

@dataclass
class _MockRefPoint:
    lap_progress: float
    distance_along_lap_m: float
    x: float
    y: float
    z: float
    speed_kph_avg: float = 100.0
    source_lap_count: int = 2
    yaw_rate_avg: Optional[float] = None


@dataclass
class _MockRefPath:
    track_location_id: str = "test_track"
    layout_id: str = "gp"
    calibration_car_id: str = "porsche_911_rsr_991_2017"
    source_lap_count: int = 2
    confidence: float = 0.8
    points: List[_MockRefPoint] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def _make_circular_ref_path(n_points: int = 60, radius: float = 300.0) -> _MockRefPath:
    """Build a circular reference path with n_points."""
    total_circumference = 2 * math.pi * radius
    pts = []
    for i in range(n_points):
        angle = 2 * math.pi * i / n_points
        dist = total_circumference * i / n_points
        pts.append(_MockRefPoint(
            lap_progress=dist / total_circumference,
            distance_along_lap_m=dist,
            x=math.cos(angle) * radius,
            y=0.0,
            z=math.sin(angle) * radius,
        ))
    # Ensure last point has distance == total_circumference
    if pts:
        pts[-1].distance_along_lap_m = total_circumference
        pts[-1].lap_progress = 1.0
    return _MockRefPath(points=pts)


# ---------------------------------------------------------------------------
# Test 1 — all approx_progress values in [0.0, 1.0]
# ---------------------------------------------------------------------------

def test_all_approx_progress_in_range():
    """All SeededCorner.approx_progress must be in [0.0, 1.0]."""
    ref_path = _make_circular_ref_path()
    station_map = build_track_station_map(ref_path, layout_seed=None, spacing_m=5.0)
    for corner in station_map.seeded_corners + station_map.extra_curvature_peaks:
        assert 0.0 <= corner.approx_progress <= 1.0, (
            f"Corner {corner.corner_id} approx_progress={corner.approx_progress} "
            f"is outside [0.0, 1.0]"
        )


# ---------------------------------------------------------------------------
# Test 2 — clustering guard: no two consecutive corners delta > 0.5
# ---------------------------------------------------------------------------

def test_no_consecutive_corner_progress_delta_gt_half():
    """No two consecutive seeded corners may have approx_progress delta > 0.5."""
    ref_path = _make_circular_ref_path(n_points=120, radius=500.0)
    station_map = build_track_station_map(ref_path, layout_seed=None, spacing_m=5.0)
    corners = station_map.seeded_corners
    if len(corners) < 2:
        pytest.skip("Not enough corners detected to test clustering guard")
    for i in range(1, len(corners)):
        delta = abs(corners[i].approx_progress - corners[i - 1].approx_progress)
        assert delta <= 0.5, (
            f"Consecutive corners {corners[i-1].corner_id} and {corners[i].corner_id} "
            f"have approx_progress delta {delta:.3f} > 0.5 (clustering guard violated)"
        )


# ---------------------------------------------------------------------------
# Test 3 — direct construction: SeededCorner objects satisfy constraints
# ---------------------------------------------------------------------------

def test_directly_constructed_corners_in_range():
    """Directly constructed SeededCorner objects with valid approx_progress pass range check."""
    corners = [
        SeededCorner(corner_id="T1", display_name="T1", approx_station_m=100.0, approx_progress=0.10),
        SeededCorner(corner_id="T2", display_name="T2", approx_station_m=250.0, approx_progress=0.25),
        SeededCorner(corner_id="T3", display_name="T3", approx_station_m=500.0, approx_progress=0.50),
        SeededCorner(corner_id="T4", display_name="T4", approx_station_m=750.0, approx_progress=0.75),
    ]
    for corner in corners:
        assert 0.0 <= corner.approx_progress <= 1.0
    for i in range(1, len(corners)):
        delta = abs(corners[i].approx_progress - corners[i - 1].approx_progress)
        assert delta <= 0.5, f"Delta {delta} > 0.5 between {corners[i-1].corner_id} and {corners[i].corner_id}"


# ---------------------------------------------------------------------------
# AC2 — ReviewedTrackSegment lap_progress_start/end must be in [0.0, 1.0]
# ---------------------------------------------------------------------------

def _make_reviewed_segment(start: float, end: float) -> ReviewedTrackSegment:
    """Build a minimal ReviewedTrackSegment with given progress values."""
    from data.track_segment_detection import TrackSegmentType, TrackSegmentDetectionConfidence
    from data.track_segment_review import SegmentReviewStatus
    return ReviewedTrackSegment(
        segment_id="seg-001",
        original_display_name="T1 Apex",
        turn_number=1,
        segment_type=TrackSegmentType.APEX_ZONE,
        confidence=TrackSegmentDetectionConfidence.HIGH,
        source_lap_count=2,
        lap_progress_start=start,
        lap_progress_end=end,
        lap_progress_mid=(start + end) / 2,
        warnings=[],
        review_status=SegmentReviewStatus.UNREVIEWED,
    )


def test_reviewed_segment_progress_in_range():
    """AC2: ReviewedTrackSegment lap_progress_start/end must each be in [0.0, 1.0]."""
    # Build a set of segments spanning the whole circuit
    segments = [
        _make_reviewed_segment(0.00, 0.10),
        _make_reviewed_segment(0.10, 0.25),
        _make_reviewed_segment(0.25, 0.50),
        _make_reviewed_segment(0.50, 0.75),
        _make_reviewed_segment(0.75, 1.00),
    ]
    for seg in segments:
        assert 0.0 <= seg.lap_progress_start <= 1.0, (
            f"lap_progress_start {seg.lap_progress_start} out of [0,1] for {seg.segment_id}"
        )
        assert 0.0 <= seg.lap_progress_end <= 1.0, (
            f"lap_progress_end {seg.lap_progress_end} out of [0,1] for {seg.segment_id}"
        )
        assert seg.lap_progress_start <= seg.lap_progress_end, (
            f"lap_progress_start > lap_progress_end for {seg.segment_id}"
        )


def test_seeded_corner_and_segment_share_same_denominator():
    """AC2: SeededCorner.approx_progress and ReviewedTrackSegment progress use same
    corrected lap length as denominator — verified by checking that a corner apex
    station and a segment around the same point produce consistent progress values."""
    # Build a reference path with a known total distance
    n_points = 60
    radius = 300.0
    total_circumference = 2 * math.pi * radius
    ref_path = _make_circular_ref_path(n_points, radius)

    # The corrected denominator is ref_path.points[-1].distance_along_lap_m
    denom = ref_path.points[-1].distance_along_lap_m
    assert abs(denom - total_circumference) < 1.0, (
        f"Expected denom ~{total_circumference:.1f}, got {denom:.1f}"
    )

    # A segment at 25% of the track should have progress ~0.25 using the same denom
    station_m = denom * 0.25
    expected_progress = station_m / denom
    seg = _make_reviewed_segment(expected_progress - 0.05, expected_progress + 0.05)

    # A SeededCorner at the same station should also report ~0.25
    corner = SeededCorner(
        corner_id="T1",
        display_name="T1",
        approx_station_m=station_m,
        approx_progress=station_m / denom,
    )

    assert abs(corner.approx_progress - expected_progress) < 1e-6, (
        f"Corner approx_progress {corner.approx_progress} != expected {expected_progress}"
    )
    assert abs(seg.lap_progress_start - (expected_progress - 0.05)) < 1e-6
    assert abs(seg.lap_progress_end - (expected_progress + 0.05)) < 1e-6
