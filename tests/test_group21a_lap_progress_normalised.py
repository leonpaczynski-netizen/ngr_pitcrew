"""
Group 21A — Lap Progress Normalisation tests.

Verifies that after build_reference_path() completes:
  - points[0].lap_progress == 0.0
  - points[-1].lap_progress == 1.0
  - No lap_progress value exceeds 1.0
"""
import math
import pytest
from dataclasses import dataclass
from typing import Optional

from data.track_calibration import (
    CalibrationSession,
    CalibrationLap,
    TelemetrySample,
    build_reference_path,
)


def _make_sample(i: int, lap_number: int, total: int) -> TelemetrySample:
    """Return a TelemetrySample positioned on a simple circle."""
    angle = 2 * math.pi * i / total
    return TelemetrySample(
        timestamp_ms=i * 100,
        lap_number=lap_number,
        x=math.cos(angle) * 500.0,
        y=0.0,
        z=math.sin(angle) * 500.0,
        speed_kph=100.0,
        gear=3,
        rpm=6000.0,
        throttle=0.8,
        brake=0.0,
    )


def _make_usable_lap(lap_number: int, n_samples: int = 60) -> CalibrationLap:
    """Build a CalibrationLap that will pass quality checks."""
    samples = [_make_sample(i, lap_number, n_samples) for i in range(n_samples)]
    return CalibrationLap(
        lap_number=lap_number,
        lap_time_ms=90_000,
        samples=samples,
    )


def _build_session() -> CalibrationSession:
    """Return a session with 2 usable laps."""
    return CalibrationSession(
        session_id="test-session",
        track_location_id="test_track",
        layout_id="gp",
        laps=[_make_usable_lap(1), _make_usable_lap(2)],
    )


# ---------------------------------------------------------------------------
# Test 1 — first point lap_progress is 0.0
# ---------------------------------------------------------------------------

def test_first_point_lap_progress_zero():
    """points[0].lap_progress must be exactly 0.0 after build_reference_path."""
    session = _build_session()
    result = build_reference_path(session)
    assert result.success, f"Build failed: {result.errors}"
    assert result.reference_path is not None
    points = result.reference_path.points
    assert len(points) > 0
    assert points[0].lap_progress == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Test 2 — last point lap_progress is 1.0
# ---------------------------------------------------------------------------

def test_last_point_lap_progress_one():
    """points[-1].lap_progress must be exactly 1.0 after build_reference_path."""
    session = _build_session()
    result = build_reference_path(session)
    assert result.success, f"Build failed: {result.errors}"
    points = result.reference_path.points
    assert points[-1].lap_progress == pytest.approx(1.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Test 3 — no lap_progress value exceeds 1.0
# ---------------------------------------------------------------------------

def test_no_lap_progress_exceeds_one():
    """All lap_progress values must be in [0.0, 1.0] after build_reference_path."""
    session = _build_session()
    result = build_reference_path(session)
    assert result.success, f"Build failed: {result.errors}"
    points = result.reference_path.points
    for pt in points:
        assert pt.lap_progress <= 1.0 + 1e-9, (
            f"lap_progress {pt.lap_progress} exceeds 1.0 at "
            f"distance_along_lap_m={pt.distance_along_lap_m}"
        )
        assert pt.lap_progress >= 0.0 - 1e-9, (
            f"lap_progress {pt.lap_progress} is below 0.0"
        )
