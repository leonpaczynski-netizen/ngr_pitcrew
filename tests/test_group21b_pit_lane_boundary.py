"""Tests for detect_pit_lane_from_pit_laps() — Group 21B."""
import math
import pytest
from data.track_station_map import (
    PitLaneBoundary,
    StationPoint,
    TrackStationMap,
    detect_pit_lane_from_pit_laps,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_station_map(lap_length_m: float = 1000.0) -> TrackStationMap:
    """Build a simple circular track station map with stations every 10 m."""
    stations = []
    spacing = 10.0
    n = int(lap_length_m / spacing)
    for i in range(n):
        angle = 2.0 * math.pi * i / n
        station_m = i * spacing
        x = (lap_length_m / (2.0 * math.pi)) * math.cos(angle)
        z = (lap_length_m / (2.0 * math.pi)) * math.sin(angle)
        stations.append(StationPoint(
            station_m=station_m,
            progress_pct=station_m / lap_length_m * 100.0,
            x=x,
            y=0.0,
            z=z,
        ))
    return TrackStationMap(
        track_location_id="test",
        layout_id="test",
        lap_length_m=lap_length_m,
        spacing_m=spacing,
        stations=stations,
        seeded_corners=[],
        extra_curvature_peaks=[],
    )


class _FakeSample:
    """Lightweight sample mock."""
    def __init__(self, x: float, z: float):
        self.x = x
        self.z = z
        self.timestamp_ms = 0


class _FakeLap:
    def __init__(self, samples: list):
        self.samples = samples


def _make_pit_lap_samples(
    station_map: TrackStationMap,
    entry_fraction: float = 0.25,
    pit_offset: float = 80.0,
    exit_fraction: float = 0.35,
) -> list:
    """Build a lap that stays on track, then veers >60 m off centreline, then returns."""
    lap_m = station_map.lap_length_m
    samples = []

    for st in station_map.stations:
        frac = st.station_m / lap_m
        if entry_fraction <= frac <= exit_fraction:
            # Off centreline by pit_offset metres
            samples.append(_FakeSample(st.x + pit_offset, st.z + pit_offset))
        else:
            samples.append(_FakeSample(st.x, st.z))

    return samples


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_detect_pit_lane_returns_boundary():
    """Mock pit lap that crosses 60 m should produce a PitLaneBoundary."""
    smap = _make_station_map()
    lap_samples = _make_pit_lap_samples(smap, entry_fraction=0.25, pit_offset=90.0, exit_fraction=0.35)
    pit_lap = _FakeLap(lap_samples)

    result = detect_pit_lane_from_pit_laps([pit_lap], smap)

    assert result is not None
    assert isinstance(result, PitLaneBoundary)
    # Entry should be somewhere around 25% of lap
    assert 0.0 < result.entry_station_m < smap.lap_length_m
    assert 0.0 < result.exit_station_m < smap.lap_length_m
    # Progress values should be normalised
    assert 0.0 <= result.entry_progress <= 1.0
    assert 0.0 <= result.exit_progress <= 1.0


def test_wrap_around_no_error():
    """detect_pit_lane_from_pit_laps() must not raise on any pit lap geometry.

    When the pit crosses the lap seam (entry near end, exit near start),
    the function either returns a PitLaneBoundary or None — it must never
    raise an exception.  The rendering layer is responsible for handling
    wrap-around cases where entry_station_m > exit_station_m.
    """
    smap = _make_station_map(lap_length_m=1000.0)
    # Create a lap that goes off-track (by a large offset) for the last 10% and
    # first 10% of the lap, simulating a pit lane that crosses the seam.
    samples = []
    for st in smap.stations:
        frac = st.station_m / smap.lap_length_m
        if frac >= 0.90 or frac <= 0.10:
            # Displace 90 m off centreline
            samples.append(_FakeSample(st.x + 90.0, st.z + 90.0))
        else:
            samples.append(_FakeSample(st.x, st.z))

    pit_lap = _FakeLap(samples)
    # Must not raise — result may be None or a valid PitLaneBoundary
    result = detect_pit_lane_from_pit_laps([pit_lap], smap)
    assert result is None or isinstance(result, PitLaneBoundary)


def test_no_pit_laps_returns_none():
    """Empty pit lap list should return None."""
    smap = _make_station_map()
    assert detect_pit_lane_from_pit_laps([], smap) is None


def test_no_station_map_stations_returns_none():
    """Empty station map should return None gracefully."""
    smap = _make_station_map()
    smap.stations = []
    pit_lap = _FakeLap([_FakeSample(80.0, 80.0)] * 10)
    assert detect_pit_lane_from_pit_laps([pit_lap], smap) is None
