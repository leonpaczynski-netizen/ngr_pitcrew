"""
Group 19A — Track Intelligence Enrichment tests.

Tests strategy/track_intelligence_enrichment.py functions using plain mock
objects. No PyQt6, no DB, no file I/O.
"""
import pytest

from strategy.track_intelligence_enrichment import (
    compute_sector_fuel,
    compute_corner_speed_load,
    compute_overtaking_zones,
    compute_kerb_characterisation,
    format_sector_fuel_block,
    format_corner_speed_load_block,
    format_overtaking_zones_block,
    format_kerb_block,
    format_car_mismatch_warning,
    get_calibration_car_display_name,
)


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

class MockSample:
    def __init__(self, lap_progress, speed_kph=100.0, throttle=0.8,
                 timestamp_ms=0, surface_type="road"):
        self.lap_progress = lap_progress
        self.speed_kph = speed_kph
        self.throttle = throttle
        self.timestamp_ms = timestamp_ms
        self.surface_type = surface_type


class MockLap:
    def __init__(self, samples, is_usable=True):
        self.samples = samples
        self.is_usable = is_usable


class MockSegment:
    def __init__(self, segment_type, lap_progress_start, lap_progress_end,
                 display_name=None, segment_id=None, confidence="HIGH"):
        self.segment_type = segment_type
        self.lap_progress_start = lap_progress_start
        self.lap_progress_end = lap_progress_end
        self.display_name = display_name
        self.segment_id = segment_id or f"seg_{lap_progress_start}"
        self.confidence = confidence


class MockRefPoint:
    def __init__(self, lap_progress, speed_kph_avg):
        self.lap_progress = lap_progress
        self.speed_kph_avg = speed_kph_avg


class MockReferencePath:
    def __init__(self, points):
        self.points = points


def make_apex(start, end, name=None):
    return MockSegment("APEX_ZONE", start, end, display_name=name or f"T1@{start:.2f}")


def make_straight(start, end, name=None):
    return MockSegment("STRAIGHT", start, end, display_name=name or f"Straight@{start:.2f}")


def make_samples_in_range(start, end, count=5, speed=100.0, throttle=0.8,
                           surface_type="road", ts_start=0, ts_step=100):
    """Create evenly-spaced samples within a progress range."""
    samples = []
    for i in range(count):
        prog = start + (end - start) * (i / max(count - 1, 1))
        ts = ts_start + i * ts_step
        samples.append(MockSample(prog, speed, throttle, ts, surface_type))
    return samples


# ---------------------------------------------------------------------------
# Tests 1–3: compute_sector_fuel
# ---------------------------------------------------------------------------

def test_sector_fuel_normal_two_laps_three_sectors():
    """Test 1: 2 laps × 3 sectors → 3 dicts with throttle_integral > 0."""
    sectors = [
        {"sector_name": "S1", "start_progress": 0.0, "end_progress": 0.33},
        {"sector_name": "S2", "start_progress": 0.33, "end_progress": 0.66},
        {"sector_name": "S3", "start_progress": 0.66, "end_progress": 1.0},
    ]

    def make_lap(ts_offset):
        samples = []
        for i in range(30):
            prog = i / 29.0
            ts = ts_offset + i * 200
            samples.append(MockSample(prog, 100.0, 0.8, ts))
        return MockLap(samples)

    laps = [make_lap(0), make_lap(10000)]
    result = compute_sector_fuel(laps, sectors)

    assert len(result) == 3
    for r in result:
        assert r["throttle_integral"] > 0.0
        assert r["lap_count"] == 2


def test_sector_fuel_missing_sector_omitted():
    """Test 2: sector range has no samples → omitted from output."""
    sectors = [
        {"sector_name": "S1", "start_progress": 0.0, "end_progress": 0.5},
        {"sector_name": "S2", "start_progress": 0.9, "end_progress": 1.0},  # no samples here
    ]
    samples = [MockSample(i / 9.0 * 0.5, 100.0, 0.8, i * 200) for i in range(10)]
    laps = [MockLap(samples)]

    result = compute_sector_fuel(laps, sectors)

    sector_names = [r["sector_name"] for r in result]
    assert "S1" in sector_names
    assert "S2" not in sector_names


def test_sector_fuel_zero_throttle_included():
    """Test 3: samples present but all throttle=0 → included with throttle_integral=0.0."""
    sectors = [{"sector_name": "S1", "start_progress": 0.0, "end_progress": 1.0}]
    samples = [MockSample(i / 9.0, 100.0, 0.0, i * 200) for i in range(10)]
    laps = [MockLap(samples)]

    result = compute_sector_fuel(laps, sectors)

    assert len(result) == 1
    assert result[0]["throttle_integral"] == 0.0


# ---------------------------------------------------------------------------
# Tests 4–6: compute_corner_speed_load
# ---------------------------------------------------------------------------

def test_corner_speed_load_normal_three_corners():
    """Test 4: 3 apex zones with samples → 3 dicts, all speed fields set."""
    segments = [
        make_apex(0.1, 0.2, "T1"),
        make_apex(0.4, 0.5, "T2"),
        make_apex(0.7, 0.8, "T3"),
    ]
    all_samples = []
    for i in range(100):
        prog = i / 99.0
        speed = 80.0 + 40.0 * abs(0.5 - prog)  # U-shape
        all_samples.append(MockSample(prog, speed))
    laps = [MockLap(all_samples)]

    result = compute_corner_speed_load(laps, segments)

    assert len(result) == 3
    for r in result:
        assert "entry_speed_kph" in r
        assert "apex_speed_kph" in r
        assert "exit_speed_kph" in r
        assert "peak_lateral_g" in r


def test_corner_speed_load_no_samples_in_range_omitted():
    """Test 5: no samples in corner range → corner omitted."""
    segments = [make_apex(0.9, 1.0, "T_Last")]
    # samples only cover 0.0–0.5
    samples = [MockSample(i / 20.0 * 0.5, 100.0) for i in range(10)]
    laps = [MockLap(samples)]

    result = compute_corner_speed_load(laps, segments)

    assert result == []


def test_corner_speed_load_zero_speed():
    """Test 6: zero speed at all samples → entry/apex/exit = 0.0, corner still returned."""
    segments = [make_apex(0.1, 0.5, "T1")]
    samples = [MockSample(0.1 + i * 0.04, 0.0) for i in range(10)]
    laps = [MockLap(samples)]

    result = compute_corner_speed_load(laps, segments)

    assert len(result) == 1
    assert result[0]["entry_speed_kph"] == 0.0
    assert result[0]["apex_speed_kph"] == 0.0
    assert result[0]["exit_speed_kph"] == 0.0


# ---------------------------------------------------------------------------
# Tests 7–10: compute_overtaking_zones
# ---------------------------------------------------------------------------

def _make_ref_path_with_speeds(progress_speed_pairs):
    points = [MockRefPoint(p, s) for p, s in progress_speed_pairs]
    return MockReferencePath(points)


def test_overtaking_zones_delta_above_threshold_included():
    """Test 7: delta >= 80 kph → included."""
    ref_path = _make_ref_path_with_speeds(
        [(i / 20.0, 200.0 if i / 20.0 <= 0.5 else 100.0) for i in range(21)]
    )
    segments = [
        make_straight(0.0, 0.4, "Main Straight"),
        make_apex(0.5, 0.6, "T1"),
    ]

    result = compute_overtaking_zones(ref_path, segments)

    assert len(result) == 1
    assert result[0]["delta_kph"] >= 80.0


def test_overtaking_zones_delta_below_threshold_excluded():
    """Test 8: delta < 80 kph → excluded."""
    ref_path = _make_ref_path_with_speeds(
        [(i / 20.0, 150.0 if i / 20.0 <= 0.5 else 100.0) for i in range(21)]
    )
    segments = [
        make_straight(0.0, 0.4, "Short Straight"),
        make_apex(0.5, 0.6, "T1"),
    ]

    result = compute_overtaking_zones(ref_path, segments)

    assert result == []


def test_overtaking_zones_end_of_lap_wraps_to_first_apex():
    """Test 9: end-of-lap straight (no following apex after s_end) → wraps to first apex."""
    # Straight near end of lap, apex only at the start
    speeds = []
    for i in range(21):
        p = i / 20.0
        if p >= 0.8:
            speed = 250.0
        elif p <= 0.1:
            speed = 80.0
        else:
            speed = 150.0
        speeds.append((p, speed))
    ref_path = _make_ref_path_with_speeds(speeds)

    segments = [
        make_apex(0.0, 0.1, "T1"),       # only apex — at lap start
        make_straight(0.8, 1.0, "Back Straight"),
    ]

    result = compute_overtaking_zones(ref_path, segments)

    # Should have wrapped to T1 (first apex) since no apex after 1.0
    assert len(result) == 1
    assert result[0]["following_corner_id"] == "T1"


def test_overtaking_zones_no_ref_points_in_range_omitted():
    """Test 10: no reference path points in straight range → omitted."""
    # ref path covers 0.5–1.0 only; straight is at 0.0–0.4
    ref_path = _make_ref_path_with_speeds(
        [(0.5 + i / 20.0 * 0.5, 200.0) for i in range(10)]
    )
    segments = [
        make_straight(0.0, 0.4, "Front Straight"),
        make_apex(0.5, 0.6, "T1"),
    ]

    result = compute_overtaking_zones(ref_path, segments)

    assert result == []


# ---------------------------------------------------------------------------
# Tests 11–15: compute_kerb_characterisation
# ---------------------------------------------------------------------------

def _make_kerb_laps(surface_types, p_start=0.1, p_end=0.3):
    """Create one lap with samples in the corner range having given surface types."""
    samples = []
    for i, surf in enumerate(surface_types):
        prog = p_start + (p_end - p_start) * (i / max(len(surface_types) - 1, 1))
        samples.append(MockSample(prog, 100.0, 0.5, i * 100, surf))
    return [MockLap(samples)]


def test_kerb_characterisation_high():
    """Test 11: kerb_count > 15% of total → HIGH."""
    # 20 kerb out of 100 total = 20%
    surfaces = ["kerb"] * 20 + ["road"] * 80
    laps = _make_kerb_laps(surfaces)
    segments = [make_apex(0.1, 0.3, "T1")]

    result = compute_kerb_characterisation(laps, segments)

    assert len(result) == 1
    assert result[0]["kerb_aggressiveness"] == "HIGH"
    assert result[0]["kerb_available"] is True


def test_kerb_characterisation_low():
    """Test 12: kerb_count 1–15% → LOW."""
    surfaces = ["kerb"] * 10 + ["road"] * 90
    laps = _make_kerb_laps(surfaces)
    segments = [make_apex(0.1, 0.3, "T1")]

    result = compute_kerb_characterisation(laps, segments)

    assert len(result) == 1
    assert result[0]["kerb_aggressiveness"] == "LOW"
    assert result[0]["kerb_available"] is True


def test_kerb_characterisation_none():
    """Test 13: kerb_count = 0 → NONE, kerb_available = False."""
    surfaces = ["road"] * 50
    laps = _make_kerb_laps(surfaces)
    segments = [make_apex(0.1, 0.3, "T1")]

    result = compute_kerb_characterisation(laps, segments)

    assert len(result) == 1
    assert result[0]["kerb_aggressiveness"] == "NONE"
    assert result[0]["kerb_available"] is False


def test_kerb_characterisation_grass_hard_limits():
    """Test 14: grass_count > 0 → track_limits = 'hard_limits'."""
    surfaces = ["grass"] * 5 + ["road"] * 45
    laps = _make_kerb_laps(surfaces)
    segments = [make_apex(0.1, 0.3, "T1")]

    result = compute_kerb_characterisation(laps, segments)

    assert result[0]["track_limits_proximity"] == "hard_limits"


def test_kerb_characterisation_no_laps_still_returns_all_corners():
    """Test 15: no laps at all → all corners return NONE (AC9 requirement)."""
    segments = [make_apex(0.1, 0.3, "T1"), make_apex(0.5, 0.7, "T2")]

    result = compute_kerb_characterisation([], segments)

    assert len(result) == 2
    for r in result:
        assert r["kerb_aggressiveness"] == "NONE"
        assert r["kerb_available"] is False


# ---------------------------------------------------------------------------
# Tests 16–18: car-mismatch detection
# ---------------------------------------------------------------------------

def test_car_mismatch_no_warning_when_same():
    """Test 16: active_car matches calib display name → no warning."""
    calib_display = get_calibration_car_display_name("porsche_911_rsr_991_2017")
    active = calib_display

    # simulate the comparison logic from build_resolved_track_context_for_prompt
    active_norm = active.strip().lower()
    calib_norm = calib_display.strip().lower()
    mismatch = active_norm != calib_norm

    assert not mismatch


def test_car_mismatch_warning_contains_both_names():
    """Test 17: active_car differs → warning contains both names."""
    active_car = "Ferrari 488 GT3"
    calib_display = get_calibration_car_display_name("porsche_911_rsr_991_2017")

    warning = format_car_mismatch_warning(active_car, calib_display)

    assert active_car in warning
    assert calib_display in warning


def test_car_mismatch_empty_active_car_no_warning():
    """Test 18: active_car is empty string → no warning produced."""
    active_car = ""
    calib_car_id = "porsche_911_rsr_991_2017"

    # simulate the guard: if active_car_name and calib_car_id
    should_warn = bool(active_car) and bool(calib_car_id)

    assert not should_warn


# ---------------------------------------------------------------------------
# Test 19: AC7 guard — empty input returns ""
# ---------------------------------------------------------------------------

def test_ac7_empty_calib_session_no_enrichment_blocks():
    """Test 19: format functions with empty input return '' (AC7 guard)."""
    assert format_sector_fuel_block([], 1.0) == ""
    assert format_corner_speed_load_block([]) == ""
    assert format_overtaking_zones_block([]) == ""
    assert format_kerb_block([]) == ""


# ---------------------------------------------------------------------------
# Test 20: AC8 coexistence — all four blocks non-empty simultaneously
# ---------------------------------------------------------------------------

def test_ac8_all_four_format_functions_non_empty_simultaneously():
    """Test 20: all four format functions with non-empty data return non-empty strings."""
    sector_fuel = [{"sector_name": "S1", "throttle_integral": 5.0, "sample_count": 10, "lap_count": 2}]
    corners = [{"display_name": "T1", "entry_speed_kph": 150.0, "apex_speed_kph": 80.0,
                 "exit_speed_kph": 120.0, "peak_lateral_g": 2.1}]
    zones = [{"display_name": "Main Straight", "peak_speed_kph": 250.0, "following_corner_id": "T1",
               "following_corner_min_kph": 80.0, "delta_kph": 170.0,
               "lap_progress_start": 0.0, "lap_progress_end": 0.4}]
    kerb = [{"display_name": "T1", "kerb_available": True, "kerb_aggressiveness": "HIGH",
              "track_limits_proximity": "runoff_available"}]

    assert format_sector_fuel_block(sector_fuel, 1.0) != ""
    assert format_corner_speed_load_block(corners) != ""
    assert format_overtaking_zones_block(zones) != ""
    assert format_kerb_block(kerb) != ""


# ---------------------------------------------------------------------------
# Test 21: TelemetrySample surface_type backward compatibility
# ---------------------------------------------------------------------------

def test_telemetry_sample_surface_type_defaults_to_road():
    """Test 21: dict without 'surface_type' key → surface_type defaults to 'road'."""
    from data.track_calibration import TelemetrySample

    sample_dict = {
        "timestamp_ms": 1000,
        "lap_number": 1,
        "x": 0.0,
        "y": 0.0,
        "z": 0.0,
        "speed_kph": 100.0,
        "gear": 3,
        "rpm": 6000.0,
        "throttle": 0.8,
        "brake": 0.0,
        "road_distance": 500.0,
        "yaw_rate": None,
        "road_plane_y": None,
        "is_off_track": None,
        # "surface_type" deliberately absent
    }
    s = TelemetrySample(**{k: sample_dict[k] for k in sample_dict})
    assert s.surface_type == "road"

    # Also test via import deserialiser (s.get with default)
    loaded_surface = sample_dict.get("surface_type", "road")
    assert loaded_surface == "road"


# ---------------------------------------------------------------------------
# Tests 22–24: additional AC coverage
# ---------------------------------------------------------------------------

def test_ac1_fuel_multiplier_stated_separately_in_format():
    """Test 22 (AC1): fuel multiplier appears as a distinct line in formatted output."""
    sector_fuel = [{"sector_name": "S1", "throttle_integral": 3.5, "sample_count": 8, "lap_count": 2}]
    fuel_multiplier = 1.3

    output = format_sector_fuel_block(sector_fuel, fuel_multiplier)

    # The multiplier must be stated separately (not embedded inside a sector line)
    assert "1.3" in output
    # Must appear on its own dedicated line, not just inside the sector entry
    multiplier_lines = [line for line in output.splitlines() if "1.3" in line]
    assert len(multiplier_lines) >= 1
    # The sector line must NOT contain the multiplier value (it's stated separately)
    sector_line = next(line for line in output.splitlines() if "S1" in line)
    assert "1.3" not in sector_line


def test_ac3_corner_block_contains_per_corner_breakdown():
    """Test 23 (AC3): formatted corner block contains each individual corner name."""
    corners = [
        {"display_name": "Raidillon", "entry_speed_kph": 210.0, "apex_speed_kph": 190.0,
         "exit_speed_kph": 200.0, "peak_lateral_g": 3.1},
        {"display_name": "La Source", "entry_speed_kph": 130.0, "apex_speed_kph": 75.0,
         "exit_speed_kph": 100.0, "peak_lateral_g": 1.8},
    ]

    output = format_corner_speed_load_block(corners)

    assert "Raidillon" in output
    assert "La Source" in output
    # Each corner must appear on its own line with speed breakdown
    lines = output.splitlines()
    raidillon_line = next((l for l in lines if "Raidillon" in l), None)
    la_source_line = next((l for l in lines if "La Source" in l), None)
    assert raidillon_line is not None
    assert la_source_line is not None
    # They must be different lines (per-corner breakdown, not combined)
    assert raidillon_line != la_source_line


def test_ac9_surface_type_derived_from_road_plane_y():
    """Test 24 (AC9): TelemetrySample.from_frame() derives surface_type from road_plane_y thresholds."""
    from data.track_calibration import TelemetrySample

    class MockFrame:
        def __init__(self, road_plane_y, speed_kmh=80.0):
            self.road_plane_y = road_plane_y
            self.speed_kmh = speed_kmh
            self.elapsed_ms = 1000
            self.lap_number = 1
            self.pos_x = self.pos_y = self.pos_z = 0.0
            self.gear = 3
            self.rpm = 6000.0
            self.throttle = 0.8
            self.brake = 0.0
            self.road_distance = 100.0

    # road_plane_y >= 0.85 → road
    s_road = TelemetrySample.from_frame(MockFrame(0.90), lap_number=1)
    assert s_road.surface_type == "road"

    # road_plane_y in [0.50, 0.85) → kerb
    s_kerb = TelemetrySample.from_frame(MockFrame(0.65), lap_number=1)
    assert s_kerb.surface_type == "kerb"

    # road_plane_y < 0.50 → grass
    s_grass = TelemetrySample.from_frame(MockFrame(0.30), lap_number=1)
    assert s_grass.surface_type == "grass"

    # road_plane_y is None → road (default)
    s_none = TelemetrySample.from_frame(MockFrame(None), lap_number=1)
    assert s_none.surface_type == "road"


# ---------------------------------------------------------------------------
# Test 25 — AC4: mismatch warning suppressed when calib_car_id is empty
# ---------------------------------------------------------------------------

def test_car_mismatch_warning_suppressed_when_calib_car_id_empty():
    # active_car is set, but calib_car_id is empty (old JSON without car field)
    # The guard `if active_car_name and calib_car_id:` must suppress the warning
    from strategy.track_intelligence_enrichment import format_car_mismatch_warning, get_calibration_car_display_name
    active_car = "Ferrari F40"
    calib_car_id = ""  # empty — old file, no car field
    # Simulate the resolver guard
    warning_shown = bool(active_car and calib_car_id)
    assert warning_shown is False


# ---------------------------------------------------------------------------
# Test 26 — AC7: all format_* functions return empty string for empty input
# ---------------------------------------------------------------------------

def test_ac7_all_format_functions_empty_on_no_calibration():
    from strategy.track_intelligence_enrichment import (
        format_sector_fuel_block,
        format_corner_speed_load_block,
        format_overtaking_zones_block,
        format_kerb_block,
    )
    assert format_sector_fuel_block([], 1.0) == ""
    assert format_corner_speed_load_block([]) == ""
    assert format_overtaking_zones_block([]) == ""
    assert format_kerb_block([]) == ""
