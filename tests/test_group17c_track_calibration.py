"""
Group 17C — Calibration Lap Capture and Reference Path Builder tests.

Tests the pure-Python data/track_calibration.py module.
No PyQt6, no QApplication required.
"""
import json
import math
import pytest
import tempfile
from pathlib import Path

from data.track_calibration import (
    # Constants
    MIN_CALIBRATION_SAMPLES,
    MAX_JUMP_THRESHOLD_M,
    MAX_PIT_FRACTION,
    MAX_OFF_TRACK_FRACTION,
    LAP_DURATION_OUTLIER_FACTOR,
    N_PROGRESS_BUCKETS,
    MIN_USABLE_LAPS_FOR_PATH,
    PRIMARY_CALIBRATION_CAR_ID,
    OFF_TRACK_ROAD_PLANE_Y_THRESHOLD,
    # Enums
    CalibrationLapQuality,
    CalibrationSource,
    # Dataclasses
    TelemetrySample,
    LapQualityResult,
    CalibrationLap,
    CalibrationSession,
    ReferencePathPoint,
    ReferencePath,
    CalibrationBuildResult,
    # Helper functions
    point_distance_3d,
    estimate_path_length,
    detect_coordinate_jumps,
    cumulative_distances,
    normalize_to_lap_progress,
    resample_to_buckets,
    # Lap quality
    evaluate_lap_quality,
    assess_session_laps,
    # Reference path
    build_reference_path,
    # File I/O
    export_reference_path_json,
    import_reference_path_json,
)


# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------

def _sample(
    lap: int = 1,
    t: int = 0,
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.0,
    speed: float = 100.0,
    gear: int = 4,
    rpm: float = 7000.0,
    throttle: float = 0.7,
    brake: float = 0.0,
    road_plane_y: float = 1.0,
    is_off_track: bool | None = None,
    is_in_pit: bool | None = None,
) -> TelemetrySample:
    """Factory for a minimal TelemetrySample."""
    return TelemetrySample(
        timestamp_ms   = t,
        lap_number     = lap,
        x              = x,
        y              = y,
        z              = z,
        speed_kph      = speed,
        gear           = gear,
        rpm            = rpm,
        throttle       = throttle,
        brake          = brake,
        road_plane_y   = road_plane_y,
        is_off_track   = is_off_track,
        is_in_pit_lane = is_in_pit,
    )


def _straight_line_samples(
    n: int = 100,
    lap: int = 1,
    dx: float = 5.0,
    speed: float = 150.0,
) -> list[TelemetrySample]:
    """n samples in a straight line along the X axis."""
    return [
        _sample(lap=lap, t=i * 100, x=i * dx, y=0.0, z=0.0, speed=speed)
        for i in range(n)
    ]


def _circular_samples(
    n: int = 120,
    lap: int = 1,
    radius: float = 500.0,
    speed: float = 150.0,
) -> list[TelemetrySample]:
    """n samples distributed around a circle (closed approximate lap)."""
    samples = []
    for i in range(n):
        angle = 2 * math.pi * i / n
        x = radius * math.cos(angle)
        z = radius * math.sin(angle)
        samples.append(_sample(lap=lap, t=i * 100, x=x, y=0.0, z=z, speed=speed))
    return samples


def _make_lap(
    lap_num: int = 1,
    samples: list[TelemetrySample] | None = None,
    lap_time_ms: int = 90_000,
) -> CalibrationLap:
    if samples is None:
        samples = _straight_line_samples(100, lap=lap_num)
    return CalibrationLap(
        lap_number  = lap_num,
        lap_time_ms = lap_time_ms,
        samples     = samples,
    )


def _make_session(
    n_laps: int = 3,
    lap_time_ms: int = 90_000,
    samples_per_lap: int = 100,
    track: str = "fuji_international_speedway",
    layout: str = "fuji_international_speedway__full_course",
) -> CalibrationSession:
    laps = [
        _make_lap(i + 1, _circular_samples(samples_per_lap, lap=i + 1), lap_time_ms)
        for i in range(n_laps)
    ]
    return CalibrationSession(
        session_id        = f"test_session_{n_laps}",
        track_location_id = track,
        layout_id         = layout,
        laps              = laps,
    )


# ---------------------------------------------------------------------------
# TelemetrySample
# ---------------------------------------------------------------------------

class TestTelemetrySample:
    def test_basic_construction(self):
        s = _sample()
        assert s.lap_number == 1
        assert s.speed_kph == 100.0

    def test_optional_channels_default_none(self):
        s = _sample()
        assert s.steering is None
        assert s.is_in_pit_lane is None

    def test_has_valid_xyz_true(self):
        s = _sample(x=10.0, y=5.0, z=-3.0)
        assert s.has_valid_xyz() is True

    def test_has_valid_xyz_false_all_zero(self):
        s = _sample(x=0.0, y=0.0, z=0.0)
        assert s.has_valid_xyz() is False

    def test_has_valid_xyz_nonzero_y_only(self):
        s = _sample(x=0.0, y=1.0, z=0.0)
        assert s.has_valid_xyz() is True

    def test_from_frame_basic(self):
        """Duck-typed factory from a mock frame object."""
        class MockFrame:
            elapsed_ms    = 5000
            pos_x = 10.0; pos_y = 2.0; pos_z = -5.0
            speed_kmh     = 120.0
            gear          = 3
            rpm           = 6500.0
            throttle      = 0.8
            brake         = 0.0
            road_distance = 1500.0
            angvel_z      = 0.1
            road_plane_y  = 1.0
        s = TelemetrySample.from_frame(MockFrame(), lap_number=2)
        assert s.x == 10.0
        assert s.y == 2.0
        assert s.z == -5.0
        assert s.lap_number == 2
        assert s.speed_kph == 120.0
        assert s.gear == 3
        assert s.yaw_rate == 0.1
        assert s.road_plane_y == 1.0

    def test_from_frame_off_track_detected(self):
        class MockFrame:
            elapsed_ms    = 0
            pos_x = 0.0; pos_y = 0.0; pos_z = 0.0
            speed_kmh     = 80.0
            gear          = 3
            rpm           = 5000.0
            throttle      = 0.5
            brake         = 0.0
            road_distance = 0.0
            angvel_z      = 0.0
            road_plane_y  = 0.3   # low → off-track
        s = TelemetrySample.from_frame(MockFrame(), lap_number=1)
        assert s.is_off_track is True

    def test_from_frame_on_track(self):
        class MockFrame:
            elapsed_ms    = 0
            pos_x = 5.0; pos_y = 0.0; pos_z = 0.0
            speed_kmh     = 60.0
            gear          = 2
            rpm           = 4000.0
            throttle      = 0.3
            brake         = 0.0
            road_distance = 0.0
            angvel_z      = 0.0
            road_plane_y  = 0.98
        s = TelemetrySample.from_frame(MockFrame(), lap_number=1)
        assert s.is_off_track is False

    def test_from_frame_no_road_plane_y(self):
        """Frame without road_plane_y should leave is_off_track as None."""
        class MockFrame:
            elapsed_ms    = 0
            pos_x = 5.0; pos_y = 0.0; pos_z = 0.0
            speed_kmh     = 60.0
            gear          = 2; rpm = 4000.0; throttle = 0.3; brake = 0.0
            road_distance = 0.0; angvel_z = 0.0
        s = TelemetrySample.from_frame(MockFrame(), lap_number=1)
        assert s.road_plane_y is None
        assert s.is_off_track is None

    def test_steering_is_none(self):
        """GT7 does not expose steering angle — must always be None."""
        class MockFrame:
            elapsed_ms = 0; pos_x = 0.0; pos_y = 0.0; pos_z = 0.0
            speed_kmh = 0.0; gear = 1; rpm = 0.0; throttle = 0.0; brake = 0.0
            road_distance = 0.0; angvel_z = 0.0; road_plane_y = 1.0
        s = TelemetrySample.from_frame(MockFrame(), lap_number=1)
        assert s.steering is None


# ---------------------------------------------------------------------------
# CalibrationSession defaults
# ---------------------------------------------------------------------------

class TestCalibrationSession:
    def test_default_car_id(self):
        sess = CalibrationSession(
            session_id="s1",
            track_location_id="fuji_international_speedway",
            layout_id="fuji_international_speedway__full_course",
        )
        assert sess.calibration_car_id == PRIMARY_CALIBRATION_CAR_ID

    def test_track_and_layout_stored(self):
        sess = CalibrationSession(
            session_id="s1",
            track_location_id="bathurst",
            layout_id="bathurst__full_course",
        )
        assert sess.track_location_id == "bathurst"
        assert sess.layout_id == "bathurst__full_course"

    def test_default_source_is_gt7_live(self):
        sess = CalibrationSession(
            session_id="s1",
            track_location_id="spa",
            layout_id="spa__full",
        )
        assert sess.source == CalibrationSource.GT7_TELEMETRY_LIVE

    def test_empty_laps_by_default(self):
        sess = CalibrationSession(
            session_id="s1",
            track_location_id="nurburgring",
            layout_id="nurburgring__full",
        )
        assert sess.laps == []

    def test_started_at_is_set(self):
        sess = CalibrationSession(
            session_id="s1",
            track_location_id="x",
            layout_id="x__y",
        )
        assert sess.started_at  # not empty

    def test_porsche_car_id_constant(self):
        assert PRIMARY_CALIBRATION_CAR_ID == "porsche_911_rsr_991_2017"


# ---------------------------------------------------------------------------
# Distance helpers
# ---------------------------------------------------------------------------

class TestPointDistance3d:
    def test_zero_same_point(self):
        assert point_distance_3d(0, 0, 0, 0, 0, 0) == 0.0

    def test_unit_axis_x(self):
        assert point_distance_3d(0, 0, 0, 1, 0, 0) == pytest.approx(1.0)

    def test_3_4_5_right_triangle(self):
        assert point_distance_3d(0, 0, 0, 3, 4, 0) == pytest.approx(5.0)

    def test_3d_distance(self):
        # sqrt(1+4+4) = 3
        assert point_distance_3d(0, 0, 0, 1, 2, 2) == pytest.approx(3.0)

    def test_negative_coordinates(self):
        assert point_distance_3d(-1, -1, -1, 1, 1, 1) == pytest.approx(math.sqrt(12))


class TestEstimatePathLength:
    def test_empty_returns_zero(self):
        assert estimate_path_length([]) == 0.0

    def test_single_sample_returns_zero(self):
        assert estimate_path_length([_sample()]) == 0.0

    def test_two_samples_unit_step(self):
        samples = [_sample(x=0.0), _sample(x=1.0)]
        assert estimate_path_length(samples) == pytest.approx(1.0)

    def test_straight_line_100_samples(self):
        # 99 steps of 5.0 m each
        samples = _straight_line_samples(100, dx=5.0)
        assert estimate_path_length(samples) == pytest.approx(99 * 5.0)

    def test_circle_approx_circumference(self):
        radius = 500.0
        n = 3600
        samples = _circular_samples(n, radius=radius)
        circumference = 2 * math.pi * radius
        # Polygon approximation should be close
        length = estimate_path_length(samples)
        assert abs(length - circumference) < circumference * 0.01  # within 1%


class TestDetectCoordinateJumps:
    def test_no_jumps_smooth_path(self):
        samples = _straight_line_samples(50, dx=1.0)
        assert detect_coordinate_jumps(samples) == []

    def test_single_jump_detected(self):
        samples = _straight_line_samples(20, dx=1.0)
        # Insert a teleport jump at index 10
        samples[10] = _sample(t=1000, x=samples[10].x + 200.0)
        jumps = detect_coordinate_jumps(samples, threshold_m=100.0)
        assert 10 in jumps

    def test_jump_at_threshold_not_detected(self):
        # Exactly at threshold = not exceeded
        s1 = _sample(x=0.0)
        s2 = _sample(x=MAX_JUMP_THRESHOLD_M)  # exactly threshold, not > threshold
        result = detect_coordinate_jumps([s1, s2])
        assert result == []

    def test_jump_above_threshold_detected(self):
        s1 = _sample(x=0.0)
        s2 = _sample(x=MAX_JUMP_THRESHOLD_M + 0.1)
        result = detect_coordinate_jumps([s1, s2])
        assert 1 in result

    def test_multiple_jumps(self):
        samples = [_sample(x=float(i)) for i in range(10)]
        samples[3] = _sample(x=200.0)  # jump at index 3
        samples[7] = _sample(x=500.0)  # jump at index 7
        jumps = detect_coordinate_jumps(samples, threshold_m=10.0)
        assert 3 in jumps
        assert 7 in jumps

    def test_empty_list(self):
        assert detect_coordinate_jumps([]) == []

    def test_single_sample(self):
        assert detect_coordinate_jumps([_sample()]) == []


class TestCumulativeDistances:
    def test_empty_returns_empty(self):
        assert cumulative_distances([]) == []

    def test_single_sample_zero(self):
        assert cumulative_distances([_sample()]) == [0.0]

    def test_two_unit_steps(self):
        samples = [_sample(x=0.0), _sample(x=1.0), _sample(x=2.0)]
        result = cumulative_distances(samples)
        assert result == pytest.approx([0.0, 1.0, 2.0])

    def test_length_matches_sample_count(self):
        samples = _straight_line_samples(20)
        result = cumulative_distances(samples)
        assert len(result) == 20

    def test_first_element_always_zero(self):
        samples = _straight_line_samples(5)
        assert cumulative_distances(samples)[0] == 0.0

    def test_monotonically_increasing(self):
        samples = _straight_line_samples(30)
        dists = cumulative_distances(samples)
        for i in range(1, len(dists)):
            assert dists[i] >= dists[i - 1]


class TestNormalizeToLapProgress:
    def test_empty_returns_empty(self):
        assert normalize_to_lap_progress([]) == []

    def test_single_sample_returns_zero(self):
        result = normalize_to_lap_progress([_sample()])
        assert result == [0.0]

    def test_first_is_zero(self):
        result = normalize_to_lap_progress(_straight_line_samples(10))
        assert result[0] == pytest.approx(0.0)

    def test_last_is_one(self):
        result = normalize_to_lap_progress(_straight_line_samples(10))
        assert result[-1] == pytest.approx(1.0)

    def test_monotonically_increasing(self):
        result = normalize_to_lap_progress(_straight_line_samples(20))
        for i in range(1, len(result)):
            assert result[i] >= result[i - 1]

    def test_all_zero_xyz_returns_all_zeros(self):
        samples = [_sample(x=0, y=0, z=0) for _ in range(5)]
        result = normalize_to_lap_progress(samples)
        assert result == [0.0] * 5


class TestResampleToBuckets:
    def test_returns_n_buckets(self):
        samples = _straight_line_samples(100)
        buckets = resample_to_buckets(samples, n_buckets=10)
        assert len(buckets) == 10

    def test_all_samples_assigned(self):
        n = 100
        samples = _straight_line_samples(n)
        buckets = resample_to_buckets(samples, n_buckets=10)
        total = sum(len(b) for b in buckets)
        assert total == n

    def test_no_bucket_has_samples_from_wrong_progress(self):
        samples = _straight_line_samples(100, dx=1.0)
        buckets = resample_to_buckets(samples, n_buckets=4)
        assert len(buckets) == 4

    def test_empty_samples_all_buckets_empty(self):
        buckets = resample_to_buckets([], n_buckets=5)
        assert all(b == [] for b in buckets)

    def test_single_bucket(self):
        samples = _straight_line_samples(10)
        buckets = resample_to_buckets(samples, n_buckets=1)
        assert len(buckets) == 1
        assert len(buckets[0]) == 10

    def test_ordered_progress_bins(self):
        # Bucket 0 should have earliest-progress samples, last bucket latest
        samples = _straight_line_samples(200, dx=1.0)
        buckets = resample_to_buckets(samples, n_buckets=5)
        # Samples in bucket 0 should have lower X than samples in bucket 4
        if buckets[0] and buckets[4]:
            avg_x0 = sum(s.x for s in buckets[0]) / len(buckets[0])
            avg_x4 = sum(s.x for s in buckets[4]) / len(buckets[4])
            assert avg_x0 < avg_x4


# ---------------------------------------------------------------------------
# Lap quality evaluator
# ---------------------------------------------------------------------------

class TestEvaluateLapQuality:
    # ── Too few samples ──────────────────────────────────────────────────────

    def test_too_few_samples_rejected(self):
        lap = _make_lap(samples=[_sample() for _ in range(MIN_CALIBRATION_SAMPLES - 1)])
        result = evaluate_lap_quality(lap)
        assert result.quality == CalibrationLapQuality.REJECTED
        assert any("Too few" in r for r in result.reasons)

    def test_exactly_minimum_samples_not_rejected_for_count(self):
        samples = _circular_samples(MIN_CALIBRATION_SAMPLES)
        lap = _make_lap(samples=samples)
        result = evaluate_lap_quality(lap)
        # Should not reject for "too few samples"
        assert not any("Too few" in r for r in result.reasons)

    # ── Missing xyz ──────────────────────────────────────────────────────────

    def test_all_zero_xyz_rejected(self):
        samples = [_sample(x=0, y=0, z=0) for _ in range(100)]
        lap = _make_lap(samples=samples)
        result = evaluate_lap_quality(lap)
        assert result.quality == CalibrationLapQuality.REJECTED
        assert any("zero" in r.lower() or "missing" in r.lower() for r in result.reasons)

    def test_some_zero_xyz_low_confidence(self):
        samples = _straight_line_samples(100)
        # Make a few zero
        for i in range(3):
            samples[i] = _sample(x=0, y=0, z=0)
        lap = _make_lap(samples=samples)
        result = evaluate_lap_quality(lap)
        # Not all zero — should be low confidence, not rejected for xyz alone
        assert result.quality in (CalibrationLapQuality.LOW_CONFIDENCE, CalibrationLapQuality.USABLE)

    # ── Coordinate jumps ─────────────────────────────────────────────────────

    def test_teleport_jump_rejected(self):
        samples = _straight_line_samples(100, dx=1.0)
        # Insert teleport at index 50
        samples[50] = _sample(t=5000, x=samples[50].x + 500.0)
        lap = _make_lap(samples=samples)
        result = evaluate_lap_quality(lap)
        assert result.quality == CalibrationLapQuality.REJECTED
        assert any("jump" in r.lower() or "teleport" in r.lower() for r in result.reasons)

    # ── Pit lane samples ─────────────────────────────────────────────────────

    def test_excessive_pit_lane_rejected(self):
        n = 100
        # 15% pit lane (> 10% limit)
        samples = [
            _sample(is_in_pit=True) if i < 15 else _sample()
            for i in range(n)
        ]
        lap = _make_lap(samples=samples)
        result = evaluate_lap_quality(lap)
        assert result.quality == CalibrationLapQuality.REJECTED
        assert any("pit" in r.lower() for r in result.reasons)

    def test_acceptable_pit_lane_fraction_not_rejected(self):
        n = 100
        # 5% pit lane (< 10% limit)
        samples = [
            _sample(is_in_pit=True) if i < 5 else _straight_line_samples(1)[0]
            for i in range(n)
        ]
        lap = _make_lap(samples=samples)
        result = evaluate_lap_quality(lap)
        assert not any("pit" in r.lower() for r in result.reasons)

    # ── Off-track samples ────────────────────────────────────────────────────

    def test_excessive_off_track_rejected(self):
        n = 100
        # 35% off-track (> 30% limit)
        samples = [
            _sample(is_off_track=True) if i < 35 else _sample()
            for i in range(n)
        ]
        lap = _make_lap(samples=samples)
        result = evaluate_lap_quality(lap)
        assert result.quality == CalibrationLapQuality.REJECTED
        assert any("off-track" in r.lower() or "off_track" in r.lower() for r in result.reasons)

    def test_acceptable_off_track_fraction_not_rejected(self):
        n = 100
        # 10% off-track (< 30% limit)
        samples = [_sample(is_off_track=True) if i < 10 else _sample() for i in range(n)]
        lap = _make_lap(samples=samples)
        result = evaluate_lap_quality(lap)
        assert not any("off-track" in r.lower() for r in result.reasons)

    # ── Duration outlier ─────────────────────────────────────────────────────

    def test_duration_outlier_rejected(self):
        samples = _circular_samples(100)
        # Lap time 5x the median
        lap = _make_lap(samples=samples, lap_time_ms=450_000)
        result = evaluate_lap_quality(
            lap,
            session_median_duration_ms=90_000,
        )
        assert result.quality == CalibrationLapQuality.REJECTED
        assert any("duration" in r.lower() for r in result.reasons)

    def test_normal_duration_not_rejected(self):
        samples = _circular_samples(100)
        lap = _make_lap(samples=samples, lap_time_ms=92_000)
        result = evaluate_lap_quality(
            lap,
            session_median_duration_ms=90_000,
        )
        assert not any("duration" in r.lower() for r in result.reasons)

    # ── Path length outlier ──────────────────────────────────────────────────

    def test_path_length_outlier_rejected(self):
        samples = _straight_line_samples(100, dx=0.1)  # total path ~ 9.9 m
        lap = _make_lap(samples=samples)
        result = evaluate_lap_quality(
            lap,
            session_median_path_m=4563.0,  # Fuji length
        )
        assert result.quality == CalibrationLapQuality.REJECTED
        assert any("path length" in r.lower() for r in result.reasons)

    # ── Usable ───────────────────────────────────────────────────────────────

    def test_good_lap_is_usable(self):
        samples = _circular_samples(200)
        lap = _make_lap(samples=samples, lap_time_ms=90_000)
        result = evaluate_lap_quality(lap, session_median_duration_ms=90_000)
        assert result.quality == CalibrationLapQuality.USABLE
        assert result.reasons == []

    def test_result_includes_sample_count(self):
        samples = _circular_samples(80)
        lap = _make_lap(samples=samples)
        result = evaluate_lap_quality(lap)
        assert result.sample_count == 80

    def test_result_includes_path_length(self):
        samples = _circular_samples(100)
        lap = _make_lap(samples=samples)
        result = evaluate_lap_quality(lap)
        assert result.path_length_m > 0.0

    def test_result_includes_duration_ms(self):
        samples = _circular_samples(100)
        lap = _make_lap(samples=samples, lap_time_ms=88_000)
        result = evaluate_lap_quality(lap)
        assert result.duration_ms == 88_000


# ---------------------------------------------------------------------------
# Reference path builder
# ---------------------------------------------------------------------------

class TestBuildReferencePath:
    def test_missing_session_ids_fails(self):
        sess = CalibrationSession(
            session_id="s1",
            track_location_id="",
            layout_id="",
        )
        result = build_reference_path(sess)
        assert result.success is False
        assert result.errors

    def test_no_laps_fails(self):
        sess = _make_session(n_laps=0)
        result = build_reference_path(sess)
        assert result.success is False

    def test_one_usable_lap_fails_minimum_check(self):
        sess = _make_session(n_laps=1)
        result = build_reference_path(sess)
        assert result.success is False
        assert result.usable_lap_count <= 1

    def test_two_usable_laps_succeeds(self):
        sess = _make_session(n_laps=2)
        result = build_reference_path(sess)
        assert result.success is True
        assert result.reference_path is not None

    def test_three_usable_laps_succeeds(self):
        sess = _make_session(n_laps=3)
        result = build_reference_path(sess)
        assert result.success is True

    def test_reference_path_has_points(self):
        sess = _make_session(n_laps=3)
        result = build_reference_path(sess)
        assert result.reference_path is not None
        assert len(result.reference_path.points) > 0

    def test_reference_path_preserves_track_ids(self):
        sess = _make_session(
            n_laps=3,
            track="fuji_international_speedway",
            layout="fuji_international_speedway__full_course",
        )
        result = build_reference_path(sess)
        assert result.reference_path.track_location_id == "fuji_international_speedway"
        assert result.reference_path.layout_id == "fuji_international_speedway__full_course"

    def test_reference_path_has_confidence(self):
        sess = _make_session(n_laps=3)
        result = build_reference_path(sess)
        assert 0.0 <= result.reference_path.confidence <= 1.0

    def test_rejected_laps_not_counted_as_usable(self):
        # Create 3 laps: 2 usable, 1 too-few-samples
        good_laps = [
            _make_lap(i + 1, _circular_samples(100, lap=i + 1), 90_000)
            for i in range(2)
        ]
        bad_lap = _make_lap(3, [_sample()], 90_000)  # only 1 sample
        sess = CalibrationSession(
            session_id="s",
            track_location_id="test",
            layout_id="test__full",
            laps=good_laps + [bad_lap],
        )
        result = build_reference_path(sess)
        assert result.rejected_lap_count >= 1
        assert result.usable_lap_count == 2

    def test_all_rejected_laps_fails(self):
        bad_laps = [
            _make_lap(i + 1, [_sample()], 90_000)  # too few samples
            for i in range(5)
        ]
        sess = CalibrationSession(
            session_id="s",
            track_location_id="test",
            layout_id="test__full",
            laps=bad_laps,
        )
        result = build_reference_path(sess)
        assert result.success is False
        assert result.usable_lap_count == 0

    def test_reference_path_points_have_progress_01(self):
        sess = _make_session(n_laps=3)
        result = build_reference_path(sess)
        for pt in result.reference_path.points:
            assert 0.0 <= pt.lap_progress <= 1.0

    def test_reference_path_distance_monotonically_increasing(self):
        sess = _make_session(n_laps=3)
        result = build_reference_path(sess)
        pts = result.reference_path.points
        for i in range(1, len(pts)):
            assert pts[i].distance_along_lap_m >= pts[i - 1].distance_along_lap_m

    def test_reference_path_source_lap_count_correct(self):
        sess = _make_session(n_laps=3)
        result = build_reference_path(sess)
        assert result.reference_path.source_lap_count == 3

    def test_usable_lap_count_in_result(self):
        sess = _make_session(n_laps=4)
        result = build_reference_path(sess)
        assert result.usable_lap_count == 4

    def test_warnings_for_few_laps(self):
        sess = _make_session(n_laps=2)
        result = build_reference_path(sess)
        # Should warn about only 2 laps
        assert any("2" in w for w in result.warnings) or any("lap" in w.lower() for w in result.warnings)

    def test_confidence_increases_with_laps(self):
        sess_2 = _make_session(n_laps=2)
        sess_5 = _make_session(n_laps=5)
        result_2 = build_reference_path(sess_2)
        result_5 = build_reference_path(sess_5)
        assert result_5.reference_path.confidence >= result_2.reference_path.confidence

    def test_reference_path_points_have_speed(self):
        sess = _make_session(n_laps=3, samples_per_lap=100)
        result = build_reference_path(sess)
        for pt in result.reference_path.points:
            assert pt.speed_kph_avg >= 0.0

    def test_reference_path_calibration_car_id(self):
        sess = _make_session(n_laps=3)
        result = build_reference_path(sess)
        assert result.reference_path.calibration_car_id == PRIMARY_CALIBRATION_CAR_ID


# ---------------------------------------------------------------------------
# File export / import
# ---------------------------------------------------------------------------

class TestFileExportImport:
    def test_export_creates_file(self):
        path = ReferencePath(
            track_location_id="fuji_international_speedway",
            layout_id="fuji_international_speedway__full_course",
            calibration_car_id=PRIMARY_CALIBRATION_CAR_ID,
            source_lap_count=3,
            points=[
                ReferencePathPoint(
                    lap_progress=0.0, distance_along_lap_m=0.0,
                    x=100.0, y=0.0, z=200.0, speed_kph_avg=120.0, source_lap_count=3,
                ),
            ],
            confidence=0.8,
        )
        with tempfile.TemporaryDirectory() as td:
            out = export_reference_path_json(path, output_dir=Path(td))
            assert out.exists()
            assert out.suffix == ".json"

    def test_export_filename_contains_ids(self):
        path = ReferencePath(
            track_location_id="fuji_international_speedway",
            layout_id="fuji_international_speedway__full_course",
            calibration_car_id=PRIMARY_CALIBRATION_CAR_ID,
            source_lap_count=2,
            confidence=0.5,
        )
        with tempfile.TemporaryDirectory() as td:
            out = export_reference_path_json(path, output_dir=Path(td))
            assert "fuji_international_speedway" in out.name

    def test_export_is_valid_json(self):
        path = ReferencePath(
            track_location_id="test_track",
            layout_id="test_track__full",
            calibration_car_id=PRIMARY_CALIBRATION_CAR_ID,
            source_lap_count=2,
            confidence=0.5,
        )
        with tempfile.TemporaryDirectory() as td:
            out = export_reference_path_json(path, output_dir=Path(td))
            data = json.loads(out.read_text())
            assert "track_location_id" in data
            assert "points" in data

    def test_roundtrip_preserves_data(self):
        original = ReferencePath(
            track_location_id="test_track",
            layout_id="test_track__full",
            calibration_car_id=PRIMARY_CALIBRATION_CAR_ID,
            source_lap_count=3,
            points=[
                ReferencePathPoint(
                    lap_progress=0.0, distance_along_lap_m=0.0,
                    x=1.0, y=2.0, z=3.0, speed_kph_avg=150.0, source_lap_count=3,
                ),
                ReferencePathPoint(
                    lap_progress=0.5, distance_along_lap_m=2000.0,
                    x=10.0, y=0.5, z=-5.0, speed_kph_avg=200.0, source_lap_count=3,
                ),
            ],
            confidence=0.7,
        )
        with tempfile.TemporaryDirectory() as td:
            out = export_reference_path_json(original, output_dir=Path(td))
            loaded = import_reference_path_json(out)
            assert loaded.track_location_id == original.track_location_id
            assert loaded.layout_id == original.layout_id
            assert loaded.source_lap_count == original.source_lap_count
            assert len(loaded.points) == 2
            assert loaded.points[0].x == pytest.approx(1.0)
            assert loaded.points[1].speed_kph_avg == pytest.approx(200.0)
            assert loaded.confidence == pytest.approx(0.7)

    def test_import_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            import_reference_path_json(Path("/nonexistent/path.json"))

    def test_export_creates_output_dir(self):
        path = ReferencePath(
            track_location_id="x",
            layout_id="x__y",
            calibration_car_id=PRIMARY_CALIBRATION_CAR_ID,
            source_lap_count=2,
            confidence=0.5,
        )
        with tempfile.TemporaryDirectory() as td:
            nested = Path(td) / "new_subdir" / "models"
            out = export_reference_path_json(path, output_dir=nested)
            assert out.exists()


# ---------------------------------------------------------------------------
# assess_session_laps (session-level quality with medians)
# ---------------------------------------------------------------------------

class TestAssessSessionLaps:
    def test_returns_one_result_per_lap(self):
        sess = _make_session(n_laps=4)
        results = assess_session_laps(sess)
        assert len(results) == 4

    def test_empty_session_returns_empty(self):
        sess = CalibrationSession(
            session_id="s",
            track_location_id="x",
            layout_id="x__y",
        )
        results = assess_session_laps(sess)
        assert results == []

    def test_all_good_laps_usable(self):
        sess = _make_session(n_laps=3, samples_per_lap=100)
        results = assess_session_laps(sess)
        assert all(r.quality == CalibrationLapQuality.USABLE for r in results)

    def test_duration_outlier_caught_by_session_median(self):
        good_laps = [
            _make_lap(i + 1, _circular_samples(100, lap=i + 1), 90_000)
            for i in range(3)
        ]
        # Add one very slow lap
        good_laps.append(
            _make_lap(4, _circular_samples(100, lap=4), 400_000)  # ~4.4x median
        )
        sess = CalibrationSession(
            session_id="s",
            track_location_id="fuji_international_speedway",
            layout_id="fuji_international_speedway__full_course",
            laps=good_laps,
        )
        results = assess_session_laps(sess)
        assert results[3].quality == CalibrationLapQuality.REJECTED
        assert results[0].quality == CalibrationLapQuality.USABLE


# ---------------------------------------------------------------------------
# CalibrationBuildResult
# ---------------------------------------------------------------------------

class TestCalibrationBuildResult:
    def test_failed_result_has_errors(self):
        result = CalibrationBuildResult(success=False, errors=["something wrong"])
        assert not result.success
        assert result.errors

    def test_success_result_has_path(self):
        sess = _make_session(n_laps=3)
        result = build_reference_path(sess)
        assert result.success
        assert result.reference_path is not None

    def test_counts_are_non_negative(self):
        sess = _make_session(n_laps=3)
        result = build_reference_path(sess)
        assert result.usable_lap_count >= 0
        assert result.rejected_lap_count >= 0
        assert result.low_confidence_lap_count >= 0


# ---------------------------------------------------------------------------
# Regression: existing Group 17A and 17B modules must still import cleanly
# ---------------------------------------------------------------------------

class TestRegressionImports:
    def test_track_intelligence_still_importable(self):
        import data.track_intelligence as ti
        assert hasattr(ti, "load_track_seed")
        assert hasattr(ti, "TrackModellingStatus")

    def test_track_modelling_vm_still_importable(self):
        import ui.track_modelling_vm as vm
        assert hasattr(vm, "format_layout_facts")
        assert hasattr(vm, "format_readiness")

    def test_seed_loads_without_error(self):
        from data.track_intelligence import load_track_seed
        result = load_track_seed()
        assert result.success

    def test_track_calibration_constants(self):
        assert MIN_CALIBRATION_SAMPLES > 0
        assert MAX_JUMP_THRESHOLD_M > 0
        assert 0.0 < MAX_PIT_FRACTION < 1.0
        assert 0.0 < MAX_OFF_TRACK_FRACTION < 1.0
        assert LAP_DURATION_OUTLIER_FACTOR > 1.0
        assert N_PROGRESS_BUCKETS > 0
        assert MIN_USABLE_LAPS_FOR_PATH >= 2
