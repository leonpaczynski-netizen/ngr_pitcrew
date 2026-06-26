"""Tests for detect_pit_lap_raw() — Group 21B pit lane detection."""
import pytest
from data.track_calibration import TelemetrySample, detect_pit_lap_raw

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sample(x: float, z: float, timestamp_ms: int) -> TelemetrySample:
    """Minimal TelemetrySample at the given XZ position and timestamp."""
    return TelemetrySample(
        timestamp_ms=timestamp_ms,
        lap_number=1,
        x=x,
        y=0.0,
        z=z,
        speed_kph=100.0,
        gear=3,
        rpm=5000.0,
        throttle=0.5,
        brake=0.0,
    )


def _make_clean_lap(n: int = 200) -> list:
    """Samples arranged in a small circle — all within 30 m of centroid."""
    import math
    samples = []
    for i in range(n):
        angle = 2.0 * math.pi * i / n
        x = 30.0 * math.cos(angle)   # radius 30 m — below 60 m threshold
        z = 30.0 * math.sin(angle)
        ts = i * (1000 // 60)         # ~60 Hz
        samples.append(_make_sample(x, z, ts))
    return samples


def _make_pit_lap(pit_duration_s: float = 12.0) -> list:
    """Samples where the car drives > 60 m from centroid for pit_duration_s.

    Uses a large on-track block (300 s) to anchor the centroid near (0, 0),
    so that the pit samples at (200, 200) are well beyond the 60 m threshold.
    """
    samples = []
    hz = 60

    # Long on-track phase — anchors centroid near origin
    on_track_samples = 300 * hz
    for i in range(on_track_samples):
        ts = i * (1000 // hz)
        samples.append(_make_sample(0.0, 0.0, ts))

    # Pit phase: 200 m from origin — dist from centroid ≈ 200 m > 60 m threshold
    pit_samples = int(pit_duration_s * hz)
    for i in range(pit_samples):
        ts = (on_track_samples + i) * (1000 // hz)
        samples.append(_make_sample(200.0, 200.0, ts))

    # Return to track
    return_samples = 300 * hz
    for i in range(return_samples):
        ts = (on_track_samples + pit_samples + i) * (1000 // hz)
        samples.append(_make_sample(0.0, 0.0, ts))

    return samples


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_clean_lap_returns_false():
    """A lap where all samples stay within 60 m of centroid should not be flagged."""
    samples = _make_clean_lap(n=300)
    assert detect_pit_lap_raw(samples) is False


def test_pit_lap_returns_true():
    """A lap with a > 10 s excursion beyond 60 m of centroid should be flagged."""
    samples = _make_pit_lap(pit_duration_s=12.0)
    assert detect_pit_lap_raw(samples) is True


def test_exactly_threshold_not_flagged():
    """A run just under threshold_seconds should NOT be flagged (boundary is exclusive).

    We use a large number of on-track samples so the centroid stays near the track,
    then add a short pit excursion well under 10 s.
    """
    hz = 60
    threshold_s = 10.0
    # 9 s of pit time — should NOT flag
    pit_duration_s = 9.0
    samples = []

    # 300 s of on-track laps at (0, 0) — centroid will be dominated by this block
    on_track_count = 300 * hz
    for i in range(on_track_count):
        ts = i * (1000 // hz)
        samples.append(_make_sample(0.0, 0.0, ts))

    # 9 s in the pit (far enough that distance from centroid (≈ 0,0) > 60 m)
    base_ts = on_track_count * (1000 // hz)
    pit_count = int(pit_duration_s * hz)
    for i in range(pit_count):
        ts = base_ts + i * (1000 // hz)
        samples.append(_make_sample(200.0, 200.0, ts))

    # Centroid is dominated by on-track block; pit samples (200,200) are > 60 m away.
    # But duration (9 s) < threshold (10 s) → should NOT flag.
    assert detect_pit_lap_raw(samples, threshold_seconds=threshold_s) is False


def test_empty_samples_returns_false():
    """Empty sample list should return False without raising."""
    assert detect_pit_lap_raw([]) is False
