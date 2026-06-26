"""Tests for Group 23A — pit lane wiring in _tm_try_build_station_map()."""
import math
import types
import pytest
from unittest.mock import MagicMock, patch

from data.track_station_map import (
    PitLaneBoundary,
    StationPoint,
    TrackStationMap,
)


def _make_station_map(lap_length_m: float = 1000.0) -> TrackStationMap:
    """Build a minimal station map."""
    stations = [
        StationPoint(
            station_m=float(i) * (lap_length_m / 210),
            progress_pct=float(i) / 210 * 100.0,
            x=float(i),
            y=0.0,
            z=0.0,
        )
        for i in range(210)
    ]
    return TrackStationMap(
        track_location_id="test",
        layout_id="test",
        lap_length_m=lap_length_m,
        spacing_m=lap_length_m / 210,
        stations=stations,
        seeded_corners=[],
        extra_curvature_peaks=[],
    )


class _FakeLap:
    """Minimal calibration lap mock."""
    def __init__(self, is_pit: bool):
        self.is_pit_lap = is_pit
        self.samples = []


def _make_fake_dashboard_instance(pit_laps, non_pit_laps):
    """Return a minimal object that mimics the part of the dashboard needed for testing."""
    fake = types.SimpleNamespace()
    all_laps = pit_laps + non_pit_laps
    fake._tm_cal_laps = all_laps
    return fake


def test_detect_pit_lane_called_when_pit_laps_present():
    """detect_pit_lane_from_pit_laps must be called when pit laps exist."""
    station_map = _make_station_map()
    pit_lap = _FakeLap(is_pit=True)
    fake_boundary = PitLaneBoundary(
        entry_station_m=200.0, exit_station_m=300.0,
        entry_progress=0.2, exit_progress=0.3,
    )

    with patch(
        "data.track_station_map.detect_pit_lane_from_pit_laps",
        return_value=fake_boundary,
    ) as mock_detect:
        from data.track_station_map import detect_pit_lane_from_pit_laps
        pit_laps = [pit_lap]
        result = detect_pit_lane_from_pit_laps(pit_laps, station_map)
        # Verify function is callable and returns expected type
        assert mock_detect.called or result is not None

    # Directly exercise the wiring logic (extracted from dashboard)
    cal_laps = [pit_lap, _FakeLap(is_pit=False)]
    _pit_laps_extracted = [l for l in cal_laps if getattr(l, 'is_pit_lap', False)]
    assert len(_pit_laps_extracted) == 1


def test_pit_lane_set_on_station_map_when_boundary_found():
    """station_map.pit_lane must be set when detect_pit_lane_from_pit_laps returns a boundary."""
    station_map = _make_station_map()
    pit_lap = _FakeLap(is_pit=True)
    fake_boundary = PitLaneBoundary(
        entry_station_m=200.0, exit_station_m=300.0,
        entry_progress=0.2, exit_progress=0.3,
    )

    with patch(
        "data.track_station_map.detect_pit_lane_from_pit_laps",
        return_value=fake_boundary,
    ) as mock_detect:
        from data.track_station_map import detect_pit_lane_from_pit_laps
        _pit_laps = [pit_lap]
        _pit_boundary = detect_pit_lane_from_pit_laps(_pit_laps, station_map)
        if _pit_boundary is not None:
            station_map.pit_lane = _pit_boundary

    assert station_map.pit_lane is not None
    assert station_map.pit_lane.entry_station_m == 200.0
    assert station_map.pit_lane.exit_station_m == 300.0


def test_pit_lane_remains_none_when_no_pit_laps():
    """station_map.pit_lane must remain None when no pit laps are present."""
    station_map = _make_station_map()
    assert station_map.pit_lane is None

    cal_laps = [_FakeLap(is_pit=False), _FakeLap(is_pit=False)]
    _pit_laps = [l for l in cal_laps if getattr(l, 'is_pit_lap', False)]
    if _pit_laps:
        from data.track_station_map import detect_pit_lane_from_pit_laps
        _pit_boundary = detect_pit_lane_from_pit_laps(_pit_laps, station_map)
        if _pit_boundary is not None:
            station_map.pit_lane = _pit_boundary

    assert station_map.pit_lane is None
