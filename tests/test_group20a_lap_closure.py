"""
Group 20A — Lap Closure / compute_corrected_lap_length tests.
"""
import math
import pytest
from dataclasses import dataclass
from typing import Optional

from data.track_calibration import compute_corrected_lap_length


@dataclass
class _Pt:
    """Minimal ReferencePathPoint stub for closure tests."""
    x: float
    y: float
    z: float
    distance_along_lap_m: float
    lap_progress: float = 0.0
    speed_kph_avg: float = 0.0
    source_lap_count: int = 1
    yaw_rate_avg: Optional[float] = None


# ---------------------------------------------------------------------------
# Test 1 — standard closure: point at index 175 is closest to start
# ---------------------------------------------------------------------------

def test_closure_standard():
    """200 near-loop points; index 175 is placed closest to start → returns its distance."""
    n = 200
    # Start at (1000, 0, 0); all other points far away except index 175
    start_x, start_z = 1000.0, 0.0
    points = []
    for i in range(n):
        # Spread points on a large circle so most are far from start
        angle = 2 * math.pi * i / n
        x = math.cos(angle) * 5000.0
        z = math.sin(angle) * 5000.0
        points.append(_Pt(x=x, y=0.0, z=z, distance_along_lap_m=float(i * 30)))

    # Overwrite start to a known coordinate
    points[0].x = start_x
    points[0].z = start_z

    # Place index 175 (in last 20%) very close to start
    points[175].x = start_x + 1.0   # 1 m from start
    points[175].z = start_z + 1.0
    points[175].distance_along_lap_m = 5250.0

    # Make sure no other point in the search region [160:] is closer
    for i in range(160, n):
        if i != 175:
            # Distance from start should be > 500 m (they're on a 5000 m radius circle)
            pass  # the circle geometry already ensures this

    result = compute_corrected_lap_length(points)
    assert result == points[175].distance_along_lap_m


# ---------------------------------------------------------------------------
# Test 2 — open lap: no point in last 20% is near start → returns closest in region
# ---------------------------------------------------------------------------

def test_closure_open_lap():
    """Straight-line path: no point close to start; min() still returns some point."""
    points = []
    n = 200
    for i in range(n):
        points.append(_Pt(x=float(i * 10), y=0.0, z=0.0, distance_along_lap_m=float(i * 10)))

    result = compute_corrected_lap_length(points)
    # The search region is points[160:]. The closest to (0,0,0) is points[160]
    # (x=1600 — still far, but it's the minimum in the region).
    search_region = points[int(n * 0.80):]
    expected = min(search_region, key=lambda p: (p.x**2 + p.y**2 + p.z**2)**0.5)
    assert result == expected.distance_along_lap_m


# ---------------------------------------------------------------------------
# Test 3 — fewer than 10 points → returns last point's distance
# ---------------------------------------------------------------------------

def test_closure_too_few_points():
    """5 points → falls back to last point's distance_along_lap_m."""
    points = [_Pt(x=float(i), y=0.0, z=0.0, distance_along_lap_m=float(i * 10)) for i in range(5)]
    result = compute_corrected_lap_length(points)
    assert result == points[-1].distance_along_lap_m
