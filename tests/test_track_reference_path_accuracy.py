"""Reference-path accuracy (Stage 3): metre-aligned averaging with a shared datum.

The old builder averaged laps in 200 self-normalized progress buckets with no start/finish
alignment, so bucket k of two laps sat at different physical points and every apex smeared.
These verify the replacement: laps are resampled in metres, aligned to a common datum,
shape outliers are dropped, and the averaged line stays dense and un-shrunk.
"""

from __future__ import annotations

import math

import pytest

from data.track_calibration import (
    TelemetrySample, CalibrationLap, CalibrationSession,
    build_reference_path, _align_lap_offset, _roll, REF_PATH_SPACING_M,
)


def _loop_points(n=160, scale=60.0):
    """An asymmetric closed loop (so the datum offset is uniquely recoverable)."""
    pts = []
    for i in range(n):
        th = 2 * math.pi * i / n
        r = scale * (1.0 + 0.30 * math.sin(th) + 0.18 * math.sin(2 * th))
        pts.append((r * math.cos(th), 0.0, r * math.sin(th), 150.0, None))
    return pts


def _loop_samples(radius=500.0, n=200, lap=1, scale_z=1.0):
    samples = []
    for i in range(n):
        th = 2 * math.pi * i / n
        samples.append(TelemetrySample(
            timestamp_ms=i * 100, lap_number=lap,
            x=radius * math.cos(th), y=0.0, z=radius * scale_z * math.sin(th),
            speed_kph=150.0, gear=4, rpm=7000.0, throttle=0.7, brake=0.0,
            road_plane_y=1.0))
    return samples


def _lap(samples, n):
    return CalibrationLap(lap_number=n, lap_time_ms=90_000, samples=samples)


# --------------------------------------------------------------------------- align
def test_align_offset_recovers_a_known_datum_shift():
    ref = _loop_points()
    shifted = _roll(ref, 12)                 # a lap whose start is 12 stations late
    k = _align_lap_offset(ref, shifted, max_shift=25)
    # Rolling the shifted lap by the recovered offset must reproduce the reference line.
    realigned = _roll(shifted, k)
    err = max(math.hypot(a[0] - b[0], a[2] - b[2])
              for a, b in zip(ref, realigned))
    assert err < 1e-6


def test_align_offset_returns_zero_when_already_aligned():
    ref = _loop_points()
    assert _align_lap_offset(ref, list(ref), max_shift=25) == 0


# --------------------------------------------------------------------------- density
def test_reference_path_is_dense_metre_spacing_not_capped_at_200():
    # A ~3.1 km circular lap now yields ~one point per metre, not the old 200-bucket cap.
    sess = CalibrationSession(
        session_id="s", track_location_id="t", layout_id="t__l",
        laps=[_lap(_loop_samples(lap=n + 1), n + 1) for n in range(3)])
    result = build_reference_path(sess)
    assert result.success
    pts = result.reference_path.points
    circumference = 2 * math.pi * 500.0
    assert len(pts) > 1000                                   # far more than 200 buckets
    assert result.reference_path.points[-1].distance_along_lap_m == pytest.approx(
        circumference, rel=0.05)


# --------------------------------------------------------------------------- outlier
def test_shape_outlier_lap_is_dropped_from_the_average():
    # Three clean circular laps + one lap on a badly wrong line (squashed ellipse).
    clean = [_lap(_loop_samples(lap=n + 1), n + 1) for n in range(3)]
    outlier = _lap(_loop_samples(lap=4, scale_z=0.4), 4)     # way off the median line
    sess = CalibrationSession(
        session_id="s", track_location_id="t", layout_id="t__l",
        laps=clean + [outlier])
    result = build_reference_path(sess)
    assert result.success
    # The outlier is excluded from the averaged line (3 of 4 kept).
    assert result.reference_path.source_lap_count == 3
    assert any("outlier" in w.lower() for w in result.reference_path.warnings)


def test_clean_laps_are_all_kept():
    sess = CalibrationSession(
        session_id="s", track_location_id="t", layout_id="t__l",
        laps=[_lap(_loop_samples(lap=n + 1), n + 1) for n in range(4)])
    result = build_reference_path(sess)
    assert result.reference_path.source_lap_count == 4      # nothing dropped
