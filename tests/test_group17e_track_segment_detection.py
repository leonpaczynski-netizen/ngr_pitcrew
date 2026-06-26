"""Group 17E — Track Segment Detection Tests.

Tests for data/track_segment_detection.py:
  - Enums and dataclasses construct safely
  - Straight detection
  - Braking zone from speed-drop + brake signal
  - Apex zone from local speed minimum
  - Corner exit from throttle rise + speed increase
  - Traction zone candidate
  - Gear zone evidence
  - Limiter zone when RPM near observed max
  - Fuel-saving candidate on long high-throttle straight
  - Kerb/bump from consistent Z disturbances across laps
  - Corner numbering order by lap_progress
  - Expected corner count mismatch produces warning
  - No invented corners to match expected count
  - Missing position/heading data lowers confidence / adds warning
  - Rejected laps are ignored
  - Empty/malformed sessions fail safely
  - JSON export/import roundtrip
  - Regression: previous group imports still work
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from data.track_calibration import (
    PRIMARY_CALIBRATION_CAR_ID,
    CalibrationLap,
    CalibrationLapQuality,
    CalibrationSession,
    TelemetrySample,
)
from data.track_segment_detection import (
    DetectedTrackSegment,
    SegmentDetectionConfig,
    SegmentDetectionResult,
    TrackSegmentDetectionConfidence,
    TrackSegmentDirection,
    TrackSegmentType,
    assign_corner_numbers,
    detect_segments_from_lap,
    detect_track_segments,
    export_segment_detection_json,
    import_segment_detection_json,
    _smooth,
    _compute_headings_xz,
    _compute_curvature,
    _find_local_minima,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sample(
    ts: int = 0,
    x: float = 0.0, y: float = 0.0, z: float = 0.0,
    speed: float = 100.0,
    gear: int = 4,
    rpm: float = 6000.0,
    throttle: float = 0.5,
    brake: float = 0.0,
    lap: int = 1,
) -> TelemetrySample:
    return TelemetrySample(
        timestamp_ms=ts,
        lap_number=lap,
        x=x, y=y, z=z,
        speed_kph=speed,
        gear=gear,
        rpm=rpm,
        throttle=throttle,
        brake=brake,
    )


def _make_straight_lap(n: int = 80) -> CalibrationLap:
    """Straight: all samples at high speed, full throttle, no braking, moving in +X."""
    samples = [
        _sample(
            ts=i * 100,
            x=float(i * 10),   # moving 10m per sample in X
            speed=200.0,
            gear=6, rpm=8000.0,
            throttle=0.95, brake=0.0,
        )
        for i in range(n)
    ]
    return CalibrationLap(
        lap_number=1,
        lap_time_ms=n * 100,
        samples=samples,
        quality=CalibrationLapQuality.USABLE,
    )


def _make_corner_lap(n_straight: int = 25, n_brake: int = 15, n_corner: int = 15, n_exit: int = 25) -> CalibrationLap:
    """One corner: straight → braking → apex → corner exit."""
    samples: list[TelemetrySample] = []
    ts = 0

    # Straight approach at 200 kph, full throttle
    for i in range(n_straight):
        samples.append(_sample(
            ts=ts, x=float(i * 10), z=0.0,
            speed=200.0, gear=6, rpm=8500.0,
            throttle=0.95, brake=0.0,
        ))
        ts += 100

    # Braking: heavy brake, speed drops from 200 to 80
    for i in range(n_brake):
        frac = i / (n_brake - 1)
        spd = 200.0 - 120.0 * frac
        samples.append(_sample(
            ts=ts, x=float(n_straight * 10 + i * 5), z=float(i * 1.0),
            speed=spd, gear=max(3, 6 - i // 4), rpm=7000.0 - i * 200,
            throttle=0.0, brake=0.9,
        ))
        ts += 100

    # Apex: low speed (around 80 kph), slight curve in Z
    for i in range(n_corner):
        frac = i / (n_corner - 1)
        spd = 80.0 + 10.0 * frac  # very gently rising
        samples.append(_sample(
            ts=ts,
            x=float(n_straight * 10 + n_brake * 5 + i * 3),
            z=float(n_brake + i * 3.0),  # curving left
            speed=spd, gear=3, rpm=5500.0 + i * 200,
            throttle=frac * 0.4, brake=0.0,
        ))
        ts += 100

    # Exit: throttle rises, speed climbs back
    for i in range(n_exit):
        frac = i / (n_exit - 1)
        spd = 90.0 + 80.0 * frac
        samples.append(_sample(
            ts=ts,
            x=float(n_straight * 10 + n_brake * 5 + n_corner * 3 + i * 8),
            z=float(n_brake + n_corner * 3.0),
            speed=spd, gear=max(3, 3 + i // 8), rpm=5000.0 + i * 300,
            throttle=0.6 + 0.4 * frac, brake=0.0,
        ))
        ts += 100

    return CalibrationLap(
        lap_number=1,
        lap_time_ms=ts,
        samples=samples,
        quality=CalibrationLapQuality.USABLE,
    )


def _make_two_usable_laps() -> CalibrationSession:
    """Session with 2 USABLE laps — sufficient for multi-lap detection."""
    session = CalibrationSession(
        session_id="test_17e",
        track_location_id="test_track",
        layout_id="test_layout",
    )
    for lap_num in (1, 2):
        lap = _make_corner_lap()
        lap.lap_number = lap_num
        session.laps.append(lap)
    return session


def _make_fuel_save_lap(n: int = 100) -> CalibrationLap:
    """Long straight: > 8% lap at high throttle → fuel save candidate."""
    samples = [
        _sample(ts=i * 100, x=float(i * 12), speed=230.0,
                gear=6, rpm=8200.0, throttle=0.92, brake=0.0)
        for i in range(n)
    ]
    return CalibrationLap(
        lap_number=1,
        lap_time_ms=n * 100,
        samples=samples,
        quality=CalibrationLapQuality.USABLE,
    )


def _make_limiter_lap(n: int = 80) -> CalibrationLap:
    """Lap with some samples at 92%+ of max RPM → limiter zone."""
    samples = []
    for i in range(n):
        rpm = 9000.0 if i >= 60 else 7000.0
        samples.append(_sample(
            ts=i * 100, x=float(i * 10),
            speed=200.0, gear=6, rpm=rpm,
            throttle=0.95, brake=0.0,
        ))
    return CalibrationLap(
        lap_number=1,
        lap_time_ms=n * 100,
        samples=samples,
        quality=CalibrationLapQuality.USABLE,
    )


def _make_kerb_lap(z_spikes: list[int], n: int = 80) -> CalibrationLap:
    """Lap with Z spikes at specified sample indices."""
    samples = []
    for i in range(n):
        z_val = 5.0 if i in z_spikes else 0.0
        samples.append(_sample(
            ts=i * 100, x=float(i * 10), z=z_val,
            speed=150.0, gear=5, throttle=0.8, brake=0.0,
        ))
    return CalibrationLap(
        lap_number=1,
        lap_time_ms=n * 100,
        samples=samples,
        quality=CalibrationLapQuality.USABLE,
    )


# ---------------------------------------------------------------------------
# 1. Enums
# ---------------------------------------------------------------------------

class TestEnums:
    def test_segment_types_exist(self):
        assert TrackSegmentType.STRAIGHT.value == "straight"
        assert TrackSegmentType.BRAKING_ZONE.value == "braking_zone"
        assert TrackSegmentType.APEX_ZONE.value == "apex_zone"
        assert TrackSegmentType.CORNER_EXIT.value == "corner_exit"
        assert TrackSegmentType.TRACTION_ZONE.value == "traction_zone"
        assert TrackSegmentType.FUEL_SAVING_CANDIDATE.value == "fuel_saving_candidate"
        assert TrackSegmentType.LIMITER_ZONE.value == "limiter_zone"
        assert TrackSegmentType.GEAR_ZONE.value == "gear_zone"
        assert TrackSegmentType.KERB_OR_BUMP_CANDIDATE.value == "kerb_or_bump_candidate"
        assert TrackSegmentType.START_FINISH.value == "start_finish"
        assert TrackSegmentType.CORNER_ENTRY.value == "corner_entry"
        assert TrackSegmentType.UNKNOWN.value == "unknown"

    def test_direction_enum(self):
        assert TrackSegmentDirection.LEFT.value == "left"
        assert TrackSegmentDirection.RIGHT.value == "right"
        assert TrackSegmentDirection.UNKNOWN.value == "unknown"

    def test_confidence_enum(self):
        assert TrackSegmentDetectionConfidence.HIGH.value == "high"
        assert TrackSegmentDetectionConfidence.MEDIUM.value == "medium"
        assert TrackSegmentDetectionConfidence.LOW.value == "low"
        assert TrackSegmentDetectionConfidence.INSUFFICIENT.value == "insufficient"

    def test_segment_type_is_str_comparable(self):
        assert TrackSegmentType.STRAIGHT == "straight"

    def test_confidence_is_str_comparable(self):
        assert TrackSegmentDetectionConfidence.LOW == "low"


# ---------------------------------------------------------------------------
# 2. Dataclasses
# ---------------------------------------------------------------------------

class TestDataclasses:
    def test_config_constructs_with_defaults(self):
        cfg = SegmentDetectionConfig()
        assert cfg.min_corner_speed_drop_kph == pytest.approx(15.0)
        assert cfg.brake_threshold == pytest.approx(0.15)

    def test_config_custom_values(self):
        cfg = SegmentDetectionConfig(min_corner_speed_drop_kph=30.0, brake_threshold=0.25)
        assert cfg.min_corner_speed_drop_kph == pytest.approx(30.0)

    def test_detected_segment_constructs(self):
        seg = DetectedTrackSegment(
            segment_id="test_seg",
            segment_type=TrackSegmentType.APEX_ZONE,
            display_name="Apex",
            lap_progress_start=0.3,
            lap_progress_end=0.36,
            lap_progress_mid=0.33,
            confidence=TrackSegmentDetectionConfidence.MEDIUM,
        )
        assert seg.turn_number is None
        assert seg.calibration_car_id is None
        assert seg.evidence == []
        assert seg.warnings == []

    def test_detection_result_constructs(self):
        result = SegmentDetectionResult(
            success=True,
            track_location_id="nurburgring",
            layout_id="gp",
        )
        assert result.detected_corner_count == 0
        assert result.segments == []
        assert result.errors == []


# ---------------------------------------------------------------------------
# 3. Private helpers
# ---------------------------------------------------------------------------

class TestSmooth:
    def test_empty(self):
        assert _smooth([]) == []

    def test_single(self):
        result = _smooth([5.0])
        assert len(result) == 1
        assert result[0] == pytest.approx(5.0)

    def test_constant_is_unchanged(self):
        vals = [10.0] * 20
        result = _smooth(vals, window=5)
        assert all(v == pytest.approx(10.0) for v in result)

    def test_length_preserved(self):
        vals = list(range(30))
        assert len(_smooth(vals)) == 30

    def test_reduces_spike(self):
        # A spike in the middle should be reduced but not eliminated
        vals = [0.0] * 10 + [100.0] + [0.0] * 10
        result = _smooth(vals, window=5)
        spike_idx = 10
        assert result[spike_idx] < 100.0   # reduced
        assert result[spike_idx] > 0.0     # not gone


class TestHeadings:
    def test_straight_x_gives_zero_heading(self):
        samples = [_sample(x=float(i * 10)) for i in range(5)]
        headings = _compute_headings_xz(samples)
        assert len(headings) == 5
        # Moving in +x with z=0 → heading = atan2(0, 10) = 0
        for h in headings:
            assert h == pytest.approx(0.0, abs=0.01)

    def test_constant_position_gives_zeros(self):
        samples = [_sample(x=0.0, z=0.0) for _ in range(5)]
        headings = _compute_headings_xz(samples)
        assert all(h == pytest.approx(0.0) for h in headings)

    def test_single_sample(self):
        assert _compute_headings_xz([_sample()]) == [0.0]

    def test_empty(self):
        assert _compute_headings_xz([]) == []


class TestCurvature:
    def test_straight_gives_zero_curvature(self):
        import math
        samples = [_sample(x=float(i * 10)) for i in range(10)]
        headings = _compute_headings_xz(samples)
        from data.track_calibration import cumulative_distances
        dists = cumulative_distances(samples)
        curvs = _compute_curvature(headings, dists)
        assert len(curvs) == 10
        # All except first should be ~0
        for c in curvs[1:]:
            assert abs(c) < 0.01

    def test_empty(self):
        assert _compute_curvature([], []) == []


class TestLocalMinima:
    def test_finds_minimum(self):
        vals = [100.0, 90.0, 80.0, 50.0, 80.0, 90.0, 100.0]
        idxs = _find_local_minima(vals, min_drop=30.0)
        assert 3 in idxs

    def test_too_small_drop_not_found(self):
        vals = [100.0, 98.0, 97.0, 98.0, 100.0]
        idxs = _find_local_minima(vals, min_drop=20.0)
        assert len(idxs) == 0

    def test_empty(self):
        assert _find_local_minima([]) == []

    def test_two_long(self):
        assert _find_local_minima([1.0, 2.0]) == []

    def test_multiple_minima(self):
        vals = [100.0, 50.0, 100.0, 40.0, 100.0]
        idxs = _find_local_minima(vals, min_drop=30.0)
        assert 1 in idxs
        assert 3 in idxs


# ---------------------------------------------------------------------------
# 4. Straight detection
# ---------------------------------------------------------------------------

class TestStraightDetection:
    def test_straight_lap_produces_straight_segment(self):
        lap = _make_straight_lap(n=80)
        segs = detect_segments_from_lap(lap)
        types = [s.segment_type for s in segs]
        assert TrackSegmentType.STRAIGHT in types or TrackSegmentType.FUEL_SAVING_CANDIDATE in types

    def test_straight_has_no_apex_segments(self):
        lap = _make_straight_lap(n=80)
        segs = detect_segments_from_lap(lap)
        types = [s.segment_type for s in segs]
        assert TrackSegmentType.APEX_ZONE not in types

    def test_straight_has_no_braking_segments(self):
        lap = _make_straight_lap(n=80)
        segs = detect_segments_from_lap(lap)
        types = [s.segment_type for s in segs]
        assert TrackSegmentType.BRAKING_ZONE not in types

    def test_straight_segment_spans_most_of_lap(self):
        lap = _make_straight_lap(n=80)
        segs = detect_segments_from_lap(lap)
        straight = next(
            (s for s in segs
             if s.segment_type in (TrackSegmentType.STRAIGHT, TrackSegmentType.FUEL_SAVING_CANDIDATE)),
            None
        )
        assert straight is not None
        span = straight.lap_progress_end - straight.lap_progress_start
        assert span > 0.50   # should dominate the lap


# ---------------------------------------------------------------------------
# 5. Braking zone detection
# ---------------------------------------------------------------------------

class TestBrakingZoneDetection:
    def test_braking_zone_detected(self):
        lap = _make_corner_lap()
        segs = detect_segments_from_lap(lap)
        types = [s.segment_type for s in segs]
        assert TrackSegmentType.BRAKING_ZONE in types

    def test_braking_zone_has_car_id(self):
        lap = _make_corner_lap()
        segs = detect_segments_from_lap(lap)
        braking = [s for s in segs if s.segment_type == TrackSegmentType.BRAKING_ZONE]
        assert len(braking) > 0
        assert all(s.calibration_car_id == PRIMARY_CALIBRATION_CAR_ID for s in braking)

    def test_braking_zone_has_car_warning(self):
        lap = _make_corner_lap()
        segs = detect_segments_from_lap(lap)
        braking = next(s for s in segs if s.segment_type == TrackSegmentType.BRAKING_ZONE)
        warning_text = " ".join(braking.warnings)
        assert "Porsche" in warning_text or "car" in warning_text.lower()

    def test_braking_zone_comes_before_apex(self):
        lap = _make_corner_lap()
        segs = sorted(detect_segments_from_lap(lap), key=lambda s: s.lap_progress_start)
        braking_idx = next((i for i, s in enumerate(segs) if s.segment_type == TrackSegmentType.BRAKING_ZONE), None)
        apex_idx = next((i for i, s in enumerate(segs) if s.segment_type == TrackSegmentType.APEX_ZONE), None)
        if braking_idx is not None and apex_idx is not None:
            assert braking_idx < apex_idx


# ---------------------------------------------------------------------------
# 6. Apex zone detection
# ---------------------------------------------------------------------------

class TestApexZoneDetection:
    def test_apex_zone_detected(self):
        lap = _make_corner_lap()
        segs = detect_segments_from_lap(lap)
        types = [s.segment_type for s in segs]
        assert TrackSegmentType.APEX_ZONE in types

    def test_apex_zone_contains_speed_evidence(self):
        lap = _make_corner_lap()
        segs = detect_segments_from_lap(lap)
        apex = next(s for s in segs if s.segment_type == TrackSegmentType.APEX_ZONE)
        evidence_text = " ".join(apex.evidence).lower()
        assert "speed" in evidence_text or "kph" in evidence_text or "minimum" in evidence_text

    def test_apex_progress_is_in_middle_range(self):
        lap = _make_corner_lap(n_straight=25, n_brake=15, n_corner=15, n_exit=25)
        segs = detect_segments_from_lap(lap)
        apex = next(s for s in segs if s.segment_type == TrackSegmentType.APEX_ZONE)
        # Apex should be in the middle section of the lap (not at 0 or 1)
        assert 0.05 < apex.lap_progress_mid < 0.95

    def test_apex_progress_mid_equals_midpoint(self):
        lap = _make_corner_lap()
        segs = detect_segments_from_lap(lap)
        for apex in (s for s in segs if s.segment_type == TrackSegmentType.APEX_ZONE):
            expected_mid = (apex.lap_progress_start + apex.lap_progress_end) / 2.0
            assert apex.lap_progress_mid == pytest.approx(expected_mid, abs=0.02)


# ---------------------------------------------------------------------------
# 7. Corner exit detection
# ---------------------------------------------------------------------------

class TestCornerExitDetection:
    def test_corner_exit_detected(self):
        lap = _make_corner_lap()
        segs = detect_segments_from_lap(lap)
        types = [s.segment_type for s in segs]
        assert TrackSegmentType.CORNER_EXIT in types

    def test_corner_exit_after_apex(self):
        lap = _make_corner_lap()
        segs = sorted(detect_segments_from_lap(lap), key=lambda s: s.lap_progress_start)
        apex = next((s for s in segs if s.segment_type == TrackSegmentType.APEX_ZONE), None)
        exit_seg = next((s for s in segs if s.segment_type == TrackSegmentType.CORNER_EXIT), None)
        if apex and exit_seg:
            assert exit_seg.lap_progress_start >= apex.lap_progress_mid - 0.01

    def test_corner_exit_has_evidence(self):
        lap = _make_corner_lap()
        segs = detect_segments_from_lap(lap)
        exit_seg = next(s for s in segs if s.segment_type == TrackSegmentType.CORNER_EXIT)
        assert len(exit_seg.evidence) > 0


# ---------------------------------------------------------------------------
# 8. Traction zone detection
# ---------------------------------------------------------------------------

class TestTractionZoneDetection:
    def test_traction_zone_detected(self):
        lap = _make_corner_lap()
        segs = detect_segments_from_lap(lap)
        types = [s.segment_type for s in segs]
        assert TrackSegmentType.TRACTION_ZONE in types

    def test_traction_zone_has_car_id(self):
        lap = _make_corner_lap()
        segs = detect_segments_from_lap(lap)
        traction = [s for s in segs if s.segment_type == TrackSegmentType.TRACTION_ZONE]
        # Traction zones are car-specific
        for seg in traction:
            assert seg.calibration_car_id is not None

    def test_traction_zone_after_apex(self):
        lap = _make_corner_lap()
        segs = sorted(detect_segments_from_lap(lap), key=lambda s: s.lap_progress_start)
        apex = next((s for s in segs if s.segment_type == TrackSegmentType.APEX_ZONE), None)
        traction = next((s for s in segs if s.segment_type == TrackSegmentType.TRACTION_ZONE), None)
        if apex and traction:
            assert traction.lap_progress_start >= apex.lap_progress_mid - 0.01


# ---------------------------------------------------------------------------
# 9. Gear zone detection
# ---------------------------------------------------------------------------

class TestGearZoneDetection:
    def test_gear_zone_detected_in_corner(self):
        lap = _make_corner_lap()
        session = CalibrationSession(
            session_id="test", track_location_id="t", layout_id="l"
        )
        session.laps = [lap, _make_corner_lap()]
        session.laps[1].lap_number = 2
        result = detect_track_segments(session)
        gear_segs = [s for s in result.segments if s.segment_type == TrackSegmentType.GEAR_ZONE]
        assert len(gear_segs) > 0

    def test_gear_zone_has_car_id(self):
        lap = _make_corner_lap()
        session = CalibrationSession(session_id="test", track_location_id="t", layout_id="l")
        session.laps = [lap, _make_corner_lap()]
        session.laps[1].lap_number = 2
        result = detect_track_segments(session)
        gear_segs = [s for s in result.segments if s.segment_type == TrackSegmentType.GEAR_ZONE]
        for seg in gear_segs:
            assert seg.calibration_car_id is not None


# ---------------------------------------------------------------------------
# 10. Limiter zone detection
# ---------------------------------------------------------------------------

class TestLimiterZoneDetection:
    def test_limiter_zone_detected_when_rpm_near_max(self):
        lap = _make_limiter_lap(n=80)
        session = CalibrationSession(session_id="test", track_location_id="t", layout_id="l")
        session.laps = [lap, _make_limiter_lap(n=80)]
        session.laps[1].lap_number = 2
        result = detect_track_segments(session)
        limiter_segs = [s for s in result.segments if s.segment_type == TrackSegmentType.LIMITER_ZONE]
        assert len(limiter_segs) > 0

    def test_limiter_zone_has_car_id(self):
        lap = _make_limiter_lap(n=80)
        session = CalibrationSession(session_id="test", track_location_id="t", layout_id="l")
        session.laps = [lap, _make_limiter_lap(n=80)]
        session.laps[1].lap_number = 2
        result = detect_track_segments(session)
        limiter_segs = [s for s in result.segments if s.segment_type == TrackSegmentType.LIMITER_ZONE]
        for seg in limiter_segs:
            assert seg.calibration_car_id is not None

    def test_limiter_zone_evidence_mentions_rpm(self):
        lap = _make_limiter_lap(n=80)
        session = CalibrationSession(session_id="test", track_location_id="t", layout_id="l")
        session.laps = [lap, _make_limiter_lap(n=80)]
        session.laps[1].lap_number = 2
        result = detect_track_segments(session)
        limiter_segs = [s for s in result.segments if s.segment_type == TrackSegmentType.LIMITER_ZONE]
        for seg in limiter_segs:
            assert any("rpm" in e.lower() or "RPM" in e for e in seg.evidence)

    def test_limiter_covers_only_high_rpm_samples(self):
        # 10 high-RPM samples (9000) then 70 at mid-range (5000) — only first section triggers
        # threshold = 9000 * 0.92 = 8280; samples at 5000 < 8280 should NOT trigger
        high_samples = [_sample(ts=i * 100, x=float(i * 10), rpm=9000.0) for i in range(10)]
        low_samples = [_sample(ts=(10 + i) * 100, x=float((10 + i) * 10), rpm=5000.0) for i in range(70)]
        all_samples = high_samples + low_samples
        lap = CalibrationLap(
            lap_number=1, lap_time_ms=8000, samples=all_samples,
            quality=CalibrationLapQuality.USABLE,
        )
        lap2 = CalibrationLap(
            lap_number=2, lap_time_ms=8000, samples=list(all_samples),
            quality=CalibrationLapQuality.USABLE,
        )
        session = CalibrationSession(session_id="test", track_location_id="t", layout_id="l")
        session.laps = [lap, lap2]
        result = detect_track_segments(session)
        limiter_segs = [s for s in result.segments if s.segment_type == TrackSegmentType.LIMITER_ZONE]
        # If any limiter zones exist, they should span a small fraction (just the high-rpm region)
        if limiter_segs:
            for seg in limiter_segs:
                assert seg.lap_progress_end < 0.50  # should be in early part of lap


# ---------------------------------------------------------------------------
# 11. Fuel-saving candidate detection
# ---------------------------------------------------------------------------

class TestFuelSavingCandidateDetection:
    def test_long_straight_is_fuel_save_candidate(self):
        lap = _make_fuel_save_lap(n=100)
        segs = detect_segments_from_lap(lap)
        types = [s.segment_type for s in segs]
        assert TrackSegmentType.FUEL_SAVING_CANDIDATE in types

    def test_low_throttle_straight_is_not_fuel_save(self):
        # Low throttle straight → should not qualify as fuel-save candidate (avg_throttle ≤ 0.70)
        samples = [_sample(ts=i * 100, x=float(i * 10), speed=120.0, throttle=0.3, brake=0.0)
                   for i in range(80)]
        lap = CalibrationLap(
            lap_number=1, lap_time_ms=8000, samples=samples,
            quality=CalibrationLapQuality.USABLE,
        )
        segs = detect_segments_from_lap(lap)
        types = [s.segment_type for s in segs]
        assert TrackSegmentType.FUEL_SAVING_CANDIDATE not in types

    def test_fuel_save_has_car_id(self):
        lap = _make_fuel_save_lap(n=100)
        segs = detect_segments_from_lap(lap)
        fuel_segs = [s for s in segs if s.segment_type == TrackSegmentType.FUEL_SAVING_CANDIDATE]
        assert all(s.calibration_car_id is not None for s in fuel_segs)

    def test_fuel_save_has_car_warning(self):
        lap = _make_fuel_save_lap(n=100)
        segs = detect_segments_from_lap(lap)
        fuel_segs = [s for s in segs if s.segment_type == TrackSegmentType.FUEL_SAVING_CANDIDATE]
        for seg in fuel_segs:
            warning_text = " ".join(seg.warnings).lower()
            assert "car" in warning_text or "porsche" in warning_text


# ---------------------------------------------------------------------------
# 12. Kerb/bump candidate detection
# ---------------------------------------------------------------------------

class TestKerbCandidateDetection:
    def test_kerb_detected_across_two_laps(self):
        # Z spike at index ~40 in both laps
        session = CalibrationSession(
            session_id="test", track_location_id="t", layout_id="l"
        )
        lap1 = _make_kerb_lap(z_spikes=[40, 41], n=80)
        lap2 = _make_kerb_lap(z_spikes=[40, 41], n=80)
        lap2.lap_number = 2
        session.laps = [lap1, lap2]
        result = detect_track_segments(session)
        kerb_segs = [s for s in result.segments if s.segment_type == TrackSegmentType.KERB_OR_BUMP_CANDIDATE]
        assert len(kerb_segs) > 0

    def test_single_lap_kerb_not_reported(self):
        # Only one lap → kerb candidates require ≥ 2 laps for consistency
        session = CalibrationSession(
            session_id="test", track_location_id="t", layout_id="l"
        )
        lap1 = _make_kerb_lap(z_spikes=[40, 41], n=80)
        session.laps = [lap1]
        result = detect_track_segments(session)
        kerb_segs = [s for s in result.segments if s.segment_type == TrackSegmentType.KERB_OR_BUMP_CANDIDATE]
        assert len(kerb_segs) == 0

    def test_kerb_evidence_mentions_z_spike(self):
        session = CalibrationSession(
            session_id="test", track_location_id="t", layout_id="l"
        )
        lap1 = _make_kerb_lap(z_spikes=[40, 41], n=80)
        lap2 = _make_kerb_lap(z_spikes=[40, 41], n=80)
        lap2.lap_number = 2
        session.laps = [lap1, lap2]
        result = detect_track_segments(session)
        kerb_segs = [s for s in result.segments if s.segment_type == TrackSegmentType.KERB_OR_BUMP_CANDIDATE]
        for seg in kerb_segs:
            evidence_text = " ".join(seg.evidence).lower()
            assert "z" in evidence_text or "spike" in evidence_text or "kerb" in evidence_text


# ---------------------------------------------------------------------------
# 13. Corner numbering
# ---------------------------------------------------------------------------

class TestCornerNumbering:
    def _make_multi_corner_segments(self) -> list[DetectedTrackSegment]:
        """Create 3 fake apex segments at different lap progress values."""
        return [
            DetectedTrackSegment(
                segment_id=f"apex_{p:.3f}",
                segment_type=TrackSegmentType.APEX_ZONE,
                display_name=f"Apex ({p:.1%})",
                lap_progress_start=p - 0.02,
                lap_progress_end=p + 0.02,
                lap_progress_mid=p,
                confidence=TrackSegmentDetectionConfidence.MEDIUM,
            )
            for p in [0.20, 0.45, 0.70]
        ]

    def test_turn_numbers_assigned(self):
        segs = self._make_multi_corner_segments()
        numbered = assign_corner_numbers(segs)
        apex_segs = [s for s in numbered if s.segment_type == TrackSegmentType.APEX_ZONE]
        numbers = sorted(s.turn_number for s in apex_segs if s.turn_number is not None)
        assert numbers == [1, 2, 3]

    def test_turn_numbers_in_progress_order(self):
        segs = self._make_multi_corner_segments()
        numbered = assign_corner_numbers(segs)
        apex_segs = sorted(
            (s for s in numbered if s.segment_type == TrackSegmentType.APEX_ZONE),
            key=lambda s: s.turn_number
        )
        progresses = [s.lap_progress_mid for s in apex_segs]
        assert progresses == sorted(progresses)

    def test_display_name_includes_turn_number(self):
        segs = self._make_multi_corner_segments()
        numbered = assign_corner_numbers(segs)
        for seg in numbered:
            if seg.segment_type == TrackSegmentType.APEX_ZONE:
                assert f"T{seg.turn_number}" in seg.display_name

    def test_non_apex_segments_unchanged(self):
        base_segs = [
            DetectedTrackSegment(
                segment_id="straight_0",
                segment_type=TrackSegmentType.STRAIGHT,
                display_name="Straight",
                lap_progress_start=0.0,
                lap_progress_end=0.10,
                lap_progress_mid=0.05,
                confidence=TrackSegmentDetectionConfidence.LOW,
            ),
            DetectedTrackSegment(
                segment_id="apex_0.300",
                segment_type=TrackSegmentType.APEX_ZONE,
                display_name="Apex",
                lap_progress_start=0.28,
                lap_progress_end=0.32,
                lap_progress_mid=0.30,
                confidence=TrackSegmentDetectionConfidence.MEDIUM,
            ),
        ]
        numbered = assign_corner_numbers(base_segs)
        straight = next(s for s in numbered if s.segment_type == TrackSegmentType.STRAIGHT)
        assert straight.turn_number is None
        assert straight.display_name == "Straight"


# ---------------------------------------------------------------------------
# 14. Corner count mismatch
# ---------------------------------------------------------------------------

class TestCornerCountMismatch:
    def test_mismatch_produces_warning(self):
        session = _make_two_usable_laps()
        # The corner lap has 1 corner, but we expect 16
        from data.track_intelligence import TrackLayoutSeed
        seed = TrackLayoutSeed(
            layout_id="test_layout",
            display_name="Test Layout",
            track_location_id="test_track",
            corners_expected=16,
        )
        result = detect_track_segments(session, layout_seed=seed)
        all_warnings = " ".join(result.warnings)
        assert "corner" in all_warnings.lower() or "expected" in all_warnings.lower()

    def test_mismatch_warning_on_apex_segments(self):
        session = _make_two_usable_laps()
        from data.track_intelligence import TrackLayoutSeed
        seed = TrackLayoutSeed(
            layout_id="test_layout",
            display_name="Test Layout",
            track_location_id="test_track",
            corners_expected=20,
        )
        result = detect_track_segments(session, layout_seed=seed)
        apex_segs = [s for s in result.segments if s.segment_type == TrackSegmentType.APEX_ZONE]
        # All apex segments should carry the mismatch warning
        for seg in apex_segs:
            all_seg_warnings = " ".join(seg.warnings).lower()
            assert "corner" in all_seg_warnings or "expected" in all_seg_warnings

    def test_small_mismatch_no_warning(self):
        session = _make_two_usable_laps()
        from data.track_intelligence import TrackLayoutSeed
        result = detect_track_segments(session)
        detected = result.detected_corner_count
        seed = TrackLayoutSeed(
            layout_id="test_layout",
            display_name="Test Layout",
            track_location_id="test_track",
            corners_expected=detected + 2,  # within tolerance
        )
        result2 = detect_track_segments(session, layout_seed=seed)
        # Should be considered matching (diff ≤ 2)
        assert result2.corner_count_matches_expected is True


# ---------------------------------------------------------------------------
# 15. No invented corners
# ---------------------------------------------------------------------------

class TestNoInventedCorners:
    def test_detected_count_not_inflated_to_match_expected(self):
        session = _make_two_usable_laps()
        from data.track_intelligence import TrackLayoutSeed
        seed = TrackLayoutSeed(
            layout_id="test_layout",
            display_name="Test Layout",
            track_location_id="test_track",
            corners_expected=50,  # wildly high — detection must NOT invent 49 more corners
        )
        result = detect_track_segments(session, layout_seed=seed)
        # Detected corners should be based on data, not expected count
        assert result.detected_corner_count <= 5  # reasonable max from one synthetic corner

    def test_apex_segments_do_not_exceed_detected_count(self):
        session = _make_two_usable_laps()
        from data.track_intelligence import TrackLayoutSeed
        seed = TrackLayoutSeed(
            layout_id="test_layout",
            display_name="Test Layout",
            track_location_id="test_track",
            corners_expected=25,
        )
        result = detect_track_segments(session, layout_seed=seed)
        apex_count = sum(1 for s in result.segments if s.segment_type == TrackSegmentType.APEX_ZONE)
        assert apex_count == result.detected_corner_count


# ---------------------------------------------------------------------------
# 16. Missing position/heading data
# ---------------------------------------------------------------------------

class TestMissingPositionData:
    def _make_zero_position_session(self) -> CalibrationSession:
        """Session where all x/z = 0 — no heading computable."""
        samples = [
            TelemetrySample(
                timestamp_ms=i * 100, lap_number=1,
                x=0.0, y=0.0, z=0.0,  # no movement
                speed_kph=200.0 if i < 40 else (80.0 if i < 60 else 200.0),
                gear=6, rpm=8000.0,
                throttle=0.9 if i < 40 else (0.1 if i < 60 else 0.9),
                brake=0.0 if i < 40 else (0.8 if i < 50 else 0.0),
            )
            for i in range(80)
        ]
        lap1 = CalibrationLap(
            lap_number=1, lap_time_ms=8000, samples=samples,
            quality=CalibrationLapQuality.USABLE,
        )
        lap2 = CalibrationLap(
            lap_number=2, lap_time_ms=8000, samples=list(samples),
            quality=CalibrationLapQuality.USABLE,
        )
        lap2.lap_number = 2
        session = CalibrationSession(
            session_id="zero_pos", track_location_id="t", layout_id="l"
        )
        session.laps = [lap1, lap2]
        return session

    def test_zero_position_adds_warning(self):
        session = self._make_zero_position_session()
        result = detect_track_segments(session)
        all_warnings = " ".join(result.warnings).lower()
        assert "heading" in all_warnings or "curvature" in all_warnings or "position" in all_warnings or "direction" in all_warnings

    def test_zero_position_does_not_crash(self):
        session = self._make_zero_position_session()
        result = detect_track_segments(session)  # must not raise
        assert isinstance(result, SegmentDetectionResult)

    def test_no_heading_segments_have_direction_warning(self):
        session = self._make_zero_position_session()
        result = detect_track_segments(session)
        # All apex/corner segments should warn about unknown direction
        for seg in result.segments:
            if seg.segment_type in (TrackSegmentType.APEX_ZONE, TrackSegmentType.BRAKING_ZONE):
                seg_warn = " ".join(seg.warnings).lower()
                assert "direction" in seg_warn or "heading" in seg_warn or "curvature" in seg_warn


# ---------------------------------------------------------------------------
# 17. Rejected laps ignored
# ---------------------------------------------------------------------------

class TestRejectedLapsIgnored:
    def test_session_with_all_rejected_laps_fails(self):
        lap = _make_corner_lap()
        lap.quality = CalibrationLapQuality.REJECTED
        session = CalibrationSession(
            session_id="test", track_location_id="t", layout_id="l"
        )
        session.laps = [lap]
        result = detect_track_segments(session)
        assert result.success is False
        assert len(result.errors) > 0

    def test_rejected_lap_not_in_source_count(self):
        good_lap = _make_corner_lap()
        bad_lap = _make_corner_lap()
        bad_lap.quality = CalibrationLapQuality.REJECTED
        bad_lap.lap_number = 2

        good_lap2 = _make_corner_lap()
        good_lap2.lap_number = 3
        good_lap2.quality = CalibrationLapQuality.USABLE

        session = CalibrationSession(
            session_id="test", track_location_id="t", layout_id="l"
        )
        session.laps = [good_lap, bad_lap, good_lap2]
        result = detect_track_segments(session)
        assert result.source_lap_count == 2  # only 2 USABLE laps

    def test_mixed_session_still_detects(self):
        good = _make_corner_lap()
        bad = _make_corner_lap()
        bad.lap_number = 2
        bad.quality = CalibrationLapQuality.REJECTED
        good2 = _make_corner_lap()
        good2.lap_number = 3
        session = CalibrationSession(
            session_id="test", track_location_id="t", layout_id="l"
        )
        session.laps = [good, bad, good2]
        result = detect_track_segments(session)
        assert result.success is True


# ---------------------------------------------------------------------------
# 18. Empty/malformed sessions
# ---------------------------------------------------------------------------

class TestEmptyMalformedSessions:
    def test_empty_session_fails_safely(self):
        session = CalibrationSession(
            session_id="empty", track_location_id="t", layout_id="l"
        )
        session.laps = []
        result = detect_track_segments(session)
        assert result.success is False
        assert len(result.errors) > 0

    def test_session_with_no_samples_fails_safely(self):
        lap = CalibrationLap(
            lap_number=1, lap_time_ms=1000, samples=[],
            quality=CalibrationLapQuality.USABLE,
        )
        session = CalibrationSession(
            session_id="test", track_location_id="t", layout_id="l"
        )
        session.laps = [lap]
        result = detect_track_segments(session)
        # Either fails gracefully or produces no corner segments
        assert isinstance(result, SegmentDetectionResult)
        if result.success:
            assert result.detected_corner_count == 0

    def test_single_sample_lap_fails_safely(self):
        lap = CalibrationLap(
            lap_number=1, lap_time_ms=100,
            samples=[_sample(ts=0, x=0.0)],
            quality=CalibrationLapQuality.USABLE,
        )
        session = CalibrationSession(
            session_id="test", track_location_id="t", layout_id="l"
        )
        session.laps = [lap]
        result = detect_track_segments(session)
        assert isinstance(result, SegmentDetectionResult)
        # Either fails gracefully or returns empty segments
        if result.success:
            assert result.detected_corner_count == 0

    def test_detect_from_lap_too_few_samples_returns_empty(self):
        lap = CalibrationLap(
            lap_number=1, lap_time_ms=100,
            samples=[_sample()],
            quality=CalibrationLapQuality.USABLE,
        )
        result = detect_segments_from_lap(lap)
        assert result == []


# ---------------------------------------------------------------------------
# 19. JSON export / import roundtrip
# ---------------------------------------------------------------------------

class TestJsonRoundtrip:
    def _make_result(self) -> SegmentDetectionResult:
        session = _make_two_usable_laps()
        return detect_track_segments(session)

    def test_export_creates_file(self):
        result = self._make_result()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = export_segment_detection_json(result, output_dir=Path(tmpdir), session_id="test123")
            assert path.exists()

    def test_export_filename_contains_ids(self):
        result = self._make_result()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = export_segment_detection_json(result, output_dir=Path(tmpdir), session_id="sess1")
            assert result.track_location_id in path.name
            assert result.layout_id in path.name

    def test_roundtrip_preserves_success(self):
        result = self._make_result()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = export_segment_detection_json(result, output_dir=Path(tmpdir), session_id="sess1")
            loaded = import_segment_detection_json(path)
        assert loaded.success == result.success

    def test_roundtrip_preserves_segments(self):
        result = self._make_result()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = export_segment_detection_json(result, output_dir=Path(tmpdir), session_id="sess1")
            loaded = import_segment_detection_json(path)
        assert len(loaded.segments) == len(result.segments)

    def test_roundtrip_preserves_corner_count(self):
        result = self._make_result()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = export_segment_detection_json(result, output_dir=Path(tmpdir), session_id="sess1")
            loaded = import_segment_detection_json(path)
        assert loaded.detected_corner_count == result.detected_corner_count

    def test_roundtrip_preserves_segment_types(self):
        result = self._make_result()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = export_segment_detection_json(result, output_dir=Path(tmpdir), session_id="sess1")
            loaded = import_segment_detection_json(path)
        original_types = sorted(s.segment_type.value for s in result.segments)
        loaded_types   = sorted(s.segment_type.value for s in loaded.segments)
        assert original_types == loaded_types

    def test_roundtrip_preserves_turn_numbers(self):
        result = self._make_result()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = export_segment_detection_json(result, output_dir=Path(tmpdir), session_id="sess1")
            loaded = import_segment_detection_json(path)
        orig_turns = sorted(s.turn_number for s in result.segments if s.turn_number is not None)
        load_turns = sorted(s.turn_number for s in loaded.segments if s.turn_number is not None)
        assert orig_turns == load_turns

    def test_import_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            import_segment_detection_json(Path("/nonexistent/path/file.json"))

    def test_import_wrong_schema_raises(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"schema": "wrong_schema"}, f)
            bad_path = Path(f.name)
        try:
            with pytest.raises(ValueError):
                import_segment_detection_json(bad_path)
        finally:
            bad_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 20. Multi-lap detection confidence
# ---------------------------------------------------------------------------

class TestMultiLapConfidence:
    def test_two_lap_session_has_at_least_medium_confidence(self):
        session = _make_two_usable_laps()
        result = detect_track_segments(session)
        assert result.confidence in (
            TrackSegmentDetectionConfidence.MEDIUM,
            TrackSegmentDetectionConfidence.HIGH,
        )

    def test_confirmed_corners_have_higher_source_count(self):
        session = _make_two_usable_laps()
        result = detect_track_segments(session)
        apex_segs = [s for s in result.segments if s.segment_type == TrackSegmentType.APEX_ZONE]
        for seg in apex_segs:
            assert seg.source_lap_count >= 2

    def test_result_success_true_with_usable_laps(self):
        session = _make_two_usable_laps()
        result = detect_track_segments(session)
        assert result.success is True

    def test_result_has_segments_with_usable_laps(self):
        session = _make_two_usable_laps()
        result = detect_track_segments(session)
        assert len(result.segments) > 0

    def test_track_location_propagated(self):
        session = _make_two_usable_laps()
        result = detect_track_segments(session)
        assert result.track_location_id == "test_track"
        assert result.layout_id == "test_layout"


# ---------------------------------------------------------------------------
# 21. Detect from lap (single-lap API)
# ---------------------------------------------------------------------------

class TestDetectFromLap:
    def test_returns_list(self):
        lap = _make_corner_lap()
        result = detect_segments_from_lap(lap)
        assert isinstance(result, list)

    def test_segments_have_valid_progress_range(self):
        lap = _make_corner_lap()
        segs = detect_segments_from_lap(lap)
        for seg in segs:
            assert 0.0 <= seg.lap_progress_start <= 1.0
            assert 0.0 <= seg.lap_progress_end <= 1.0
            assert seg.lap_progress_start <= seg.lap_progress_mid <= seg.lap_progress_end + 0.001

    def test_segments_sorted_by_progress(self):
        lap = _make_corner_lap()
        segs = detect_segments_from_lap(lap)
        progresses = [s.lap_progress_start for s in segs]
        assert progresses == sorted(progresses)

    def test_confidence_is_low_for_single_lap(self):
        lap = _make_corner_lap()
        segs = detect_segments_from_lap(lap)
        for seg in segs:
            # Single-lap detection → at most MEDIUM (with curvature), never HIGH
            assert seg.confidence in (
                TrackSegmentDetectionConfidence.LOW,
                TrackSegmentDetectionConfidence.MEDIUM,
            )


# ---------------------------------------------------------------------------
# 22. Regression — previous group imports still work
# ---------------------------------------------------------------------------

class TestRegressionImports:
    def test_17a_track_intelligence_importable(self):
        from data.track_intelligence import (
            TrackLocationSeed,
            TrackLayoutSeed,
            TrackSeedLoadResult,
            load_track_seed,
            get_track_locations,
            search_track_layouts,
        )
        assert TrackLayoutSeed is not None

    def test_17b_track_calibration_importable(self):
        from data.track_calibration import (
            TelemetrySample,
            CalibrationLap,
            CalibrationSession,
            CalibrationLapQuality,
            ReferencePath,
            ReferencePathPoint,
            assess_session_laps,
            build_reference_path,
        )
        assert TelemetrySample is not None

    def test_17c_track_modelling_vm_importable(self):
        from ui.track_modelling_vm import (
            CALIBRATION_CAR_BOUNDARY_NOTE,
            SEED_WARNING_TEXT,
            format_layout_facts,
            get_seed_warning_text,
            is_seed_only,
        )
        assert CALIBRATION_CAR_BOUNDARY_NOTE is not None
        assert is_seed_only is not None

    def test_17d_calibration_runtime_importable(self):
        from data.track_calibration_runtime import (
            TrackCalibrationCaptureController,
            CalibrationCaptureState,
            packet_to_calibration_sample,
            can_capture_calibration_sample,
        )
        assert TrackCalibrationCaptureController is not None

    def test_17e_segment_detection_importable(self):
        from data.track_segment_detection import (
            TrackSegmentType,
            TrackSegmentDirection,
            TrackSegmentDetectionConfidence,
            DetectedTrackSegment,
            SegmentDetectionConfig,
            SegmentDetectionResult,
            detect_track_segments,
            detect_segments_from_lap,
            assign_corner_numbers,
            export_segment_detection_json,
            import_segment_detection_json,
        )
        assert detect_track_segments is not None

    def test_all_segment_types_have_string_values(self):
        for member in TrackSegmentType:
            assert isinstance(member.value, str)
            assert len(member.value) > 0
