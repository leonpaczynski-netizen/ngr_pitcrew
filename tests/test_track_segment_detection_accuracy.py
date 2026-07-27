"""Ground-truth accuracy for curvature-based corner detection (Stage 2).

These build synthetic tracks with KNOWN geometry and assert the detector recovers it —
the cases the old speed-minima detector got wrong:

  * a flat-out kink driven at CONSTANT speed (no speed drop) is still a corner;
  * an L-then-R chicane with apexes a few metres apart is TWO corners, not one;
  * a brake-and-lift point on a straight (no curvature) is NOT a corner.

Corners come from X/Z geometry only, so speed is held constant on purpose.
"""

from __future__ import annotations

import math

import pytest

from data.track_calibration import (
    TelemetrySample, CalibrationLap, CalibrationSession, CalibrationLapQuality,
)
from data.track_segment_detection import (
    detect_track_segments, TrackSegmentType, TrackSegmentDirection,
)

DS = 2.0  # metres between samples


def _path_from_kappa(kappas, ds=DS):
    """Integrate a signed-curvature profile into an XZ path (heading atan2(dx,dz))."""
    theta = 0.0
    x = z = 0.0
    pts = [(x, z)]
    for k in kappas:
        theta += k * ds
        x += math.sin(theta) * ds
        z += math.cos(theta) * ds
        pts.append((x, z))
    return pts


def _bump(center, width, peak, n):
    return [peak * math.exp(-((i - center) / width) ** 2) for i in range(n)]


def _lap(pts, lap_number, *, speed_kph=150.0, brake_at=None):
    samples = []
    for i, (x, z) in enumerate(pts):
        brake = 0.0
        if brake_at is not None and brake_at[0] <= i <= brake_at[1]:
            brake = 0.9
        samples.append(TelemetrySample(
            timestamp_ms=i * 50, lap_number=lap_number,
            x=x, y=0.0, z=z, speed_kph=speed_kph, gear=4, rpm=7000.0,
            throttle=0.9, brake=brake))
    return CalibrationLap(
        lap_number=lap_number, lap_time_ms=len(pts) * 50,
        samples=samples, quality=CalibrationLapQuality.USABLE)


def _session(pts, *, laps=2, **kw):
    return CalibrationSession(
        session_id="acc", track_location_id="loc", layout_id="loc__lay",
        laps=[_lap(pts, n + 1, **kw) for n in range(laps)])


def _apexes(result):
    return [s for s in result.segments if s.segment_type == TrackSegmentType.APEX_ZONE]


# --------------------------------------------------------------------------- tests
def test_flat_out_kink_at_constant_speed_is_still_a_corner():
    # One curvature bump (radius ~33 m), driven at a dead-constant 150 kph. The old
    # speed-minima detector saw no speed drop and missed it entirely.
    kappa = [0.0] * 40 + _bump(20, 8.0, 0.03, 40) + [0.0] * 40
    result = detect_track_segments(_session(_path_from_kappa(kappa)))
    assert result.success
    apexes = _apexes(result)
    assert len(apexes) == 1


def test_left_right_chicane_is_two_corners_not_one():
    # +curvature bump then −curvature bump, apexes ~30 m apart — inside the old 80 m /
    # 2.5 %-lap merge that collapsed them into a single corner.
    kappa = ([0.0] * 30
             + _bump(10, 5.0, 0.035, 20)      # left
             + _bump(5, 5.0, -0.035, 20)      # right, close behind
             + [0.0] * 30)
    result = detect_track_segments(_session(_path_from_kappa(kappa)))
    apexes = _apexes(result)
    assert len(apexes) == 2
    dirs = {a.direction for a in apexes}
    assert TrackSegmentDirection.LEFT in dirs
    assert TrackSegmentDirection.RIGHT in dirs


def test_brake_and_lift_on_a_straight_is_not_a_corner():
    # A dead-straight path with a hard brake application in the middle (traffic). Zero
    # curvature everywhere → zero corners, even though speed/brake say "event here".
    kappa = [0.0] * 120
    result = detect_track_segments(
        _session(_path_from_kappa(kappa), brake_at=(50, 65)))
    assert len(_apexes(result)) == 0


def test_hairpin_and_gentle_kink_both_detected():
    # A tight hairpin (radius ~14 m) and a gentle-but-real kink (radius ~55 m).
    kappa = ([0.0] * 25
             + _bump(15, 6.0, 0.07, 30)       # hairpin
             + [0.0] * 25
             + _bump(15, 7.0, 0.018, 30)      # gentle kink, above threshold
             + [0.0] * 25)
    result = detect_track_segments(_session(_path_from_kappa(kappa)))
    assert len(_apexes(result)) == 2


def _signal_lap(pts, lap_number, brake_range, throttle_high_from):
    samples = []
    for i, (x, z) in enumerate(pts):
        brake = 0.9 if brake_range[0] <= i <= brake_range[1] else 0.0
        throttle = 0.9 if i >= throttle_high_from else 0.2
        samples.append(TelemetrySample(
            timestamp_ms=i * 50, lap_number=lap_number, x=x, y=0.0, z=z,
            speed_kph=120.0, gear=4, rpm=7000.0, throttle=throttle, brake=brake))
    return CalibrationLap(lap_number=lap_number, lap_time_ms=len(pts) * 50,
                          samples=samples, quality=CalibrationLapQuality.USABLE)


def _zones(pts, brake_range, throttle_from):
    sess = CalibrationSession(
        session_id="sig", track_location_id="loc", layout_id="loc__lay",
        laps=[_signal_lap(pts, n + 1, brake_range, throttle_from) for n in range(2)])
    result = detect_track_segments(sess)
    braking = [s for s in result.segments if s.segment_type == TrackSegmentType.BRAKING_ZONE]
    traction = [s for s in result.segments if s.segment_type == TrackSegmentType.TRACTION_ZONE]
    return braking[0], traction[0]


def test_braking_and_traction_zones_follow_the_signals_not_fixed_fractions():
    # One wide corner (apex ~sample 70, run ~51–89). If the phase boundaries were fixed
    # fractions of the window they'd be identical regardless of driver inputs; because
    # they come from the SIGNALS, releasing the brakes later moves the braking-zone end
    # later, and getting to throttle later moves the traction-zone start later.
    kappa = [0.0] * 30 + _bump(40, 16.0, 0.03, 80) + [0.0] * 30
    pts = _path_from_kappa(kappa)
    brake_early, traction_early = _zones(pts, brake_range=(30, 56), throttle_from=72)
    brake_late, traction_late = _zones(pts, brake_range=(30, 68), throttle_from=85)
    assert brake_early.lap_progress_end < brake_late.lap_progress_end
    assert traction_early.lap_progress_start < traction_late.lap_progress_start


def test_detected_direction_matches_curvature_sign():
    left = detect_track_segments(_session(_path_from_kappa(
        [0.0] * 30 + _bump(20, 8.0, 0.03, 40) + [0.0] * 30)))
    right = detect_track_segments(_session(_path_from_kappa(
        [0.0] * 30 + _bump(20, 8.0, -0.03, 40) + [0.0] * 30)))
    assert _apexes(left)[0].direction == TrackSegmentDirection.LEFT
    assert _apexes(right)[0].direction == TrackSegmentDirection.RIGHT
