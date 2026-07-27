"""Tests for Group 23A — lap delta threshold raised to 8.0%."""
import pytest
from data.track_model_alignment import (
    _MAX_LAP_DELTA_GOOD_PCT,
    TrackModelMatchStatus,
    align_track_model,
)
from data.track_station_map import TrackStationMap, StationPoint, SeededCorner

import types

# Two corners with matching seed windows, so corner POSITIONS verify (PASS) and the match
# status is then determined purely by the lap-length delta — which is what these tests
# exercise. Without seed corner positions the gate caps everything at PARTIAL, so verified
# corners are required to test the delta boundary at all (accuracy-overhaul gate).
_CORNER_APEXES = (25.0, 75.0)


def _make_station_map(lap_length_m: float = 1000.0) -> TrackStationMap:
    """Minimal station map with enough stations + two real corners at 25%/75%."""
    stations = [
        StationPoint(
            station_m=float(i),
            progress_pct=float(i) / lap_length_m * 100.0,
            x=float(i),
            y=0.0,
            z=0.0,
        )
        for i in range(210)  # > _MIN_STATIONS_FOR_ALIGNMENT (200)
    ]
    corners = [
        SeededCorner(
            corner_id=f"T{n}", display_name=f"T{n}",
            approx_station_m=apex / 100.0 * lap_length_m,
            approx_progress=apex / 100.0,
            is_seeded_placeholder=False, confidence=0.9)
        for n, apex in enumerate(_CORNER_APEXES, start=1)
    ]
    return TrackStationMap(
        track_location_id="test",
        layout_id="test",
        lap_length_m=lap_length_m,
        spacing_m=1.0,
        stations=stations,
        seeded_corners=corners,
        extra_curvature_peaks=[],
        corners_expected=len(corners),
        seed_corner_positions_available=True,
    )


def _make_seed(length_m: float) -> types.SimpleNamespace:
    defs = [
        types.SimpleNamespace(
            corner_id=f"T{n}", display_name=f"T{n}",
            start_progress_pct=apex - 5.0, apex_progress_pct=apex, end_progress_pct=apex + 5.0)
        for n, apex in enumerate(_CORNER_APEXES, start=1)
    ]
    return types.SimpleNamespace(
        corners_expected=len(defs),
        length_m=length_m,
        sectors=None,
        corner_definitions=defs,
    )


def test_max_lap_delta_good_pct_is_8():
    """Smoke test: threshold must be exactly 8.0."""
    assert _MAX_LAP_DELTA_GOOD_PCT == 8.0


def test_delta_7_99_pct_is_good_match():
    """7.99% delta should yield GOOD_MATCH (within new 8% threshold)."""
    seed_length = 1000.0
    # 7.99% below seed length
    model_length = seed_length * (1 - 0.0799)
    sm = _make_station_map(lap_length_m=model_length)
    seed = _make_seed(seed_length)
    result = align_track_model(sm, seed)
    assert result.match_status == TrackModelMatchStatus.GOOD_MATCH, (
        f"Expected GOOD_MATCH but got {result.match_status} "
        f"(delta={result.lap_length_delta_pct:.2f}%)"
    )


def test_delta_8_01_pct_is_not_good_match():
    """8.01% delta should NOT yield GOOD_MATCH — threshold exceeded."""
    seed_length = 1000.0
    model_length = seed_length * (1 - 0.0801)
    sm = _make_station_map(lap_length_m=model_length)
    seed = _make_seed(seed_length)
    result = align_track_model(sm, seed)
    assert result.match_status != TrackModelMatchStatus.GOOD_MATCH, (
        f"Expected not GOOD_MATCH but got {result.match_status} "
        f"(delta={result.lap_length_delta_pct:.2f}%)"
    )
    # Should be PARTIAL_MATCH because delta exceeds GOOD threshold but there's a blocker
    assert result.match_status == TrackModelMatchStatus.PARTIAL_MATCH
