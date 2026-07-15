"""
Group 20A — Gap-filling acceptance tests.

Covers ACs not fully tested by the primary test files:
  AC2  — oval/banking curvature peaks detectable from yaw-rate
  AC4  — corrected lap length closer to seed than raw accumulation
  AC5  — corrected length within 5% removes lap-delta blocker;
          corrected length outside 5% retains blocker
  AC7  — after successful AI verify, SeededCorner.verification_source is
          set to "ai_verified" (pure-Python mutation path only)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, List
from unittest.mock import patch
import json

import pytest

# ---------------------------------------------------------------------------
# Local stubs shared across test classes
# ---------------------------------------------------------------------------

from data.track_station_map import (
    StationPoint,
    WidthSource,
    _compute_heading,
    _compute_curvature,
    SeededCorner,
)

from data.track_calibration import compute_corrected_lap_length

from data.track_map_geometry_alignment import align_maps_geometry


@dataclass
class _RefPt:
    lap_progress: float
    speed_kph_avg: float
    yaw_rate_avg: Optional[float]


@dataclass
class _RawPt:
    x: float
    y: float
    z: float
    distance_along_lap_m: float
    lap_progress: float = 0.0
    speed_kph_avg: float = 0.0
    source_lap_count: int = 1
    yaw_rate_avg: Optional[float] = None


def _straight_stations(n: int = 30, spacing: float = 1.0) -> List[StationPoint]:
    """Build a dead-straight line of stations along the Z axis."""
    stations = []
    for i in range(n):
        stations.append(StationPoint(
            station_m=i * spacing,
            progress_pct=i / n * 100.0,
            x=0.0,
            y=0.0,
            z=float(i),
            left_width_m=6.0,
            right_width_m=6.0,
            width_source=WidthSource.SEED_DEFAULT,
        ))
    _compute_heading(stations)
    return stations


# ---------------------------------------------------------------------------
# AC2 — Oval / banking: yaw-rate produces curvature peaks on sections that
#        appear straight in XZ (constant heading but sustained yaw rate).
# ---------------------------------------------------------------------------

class TestOvalBankingCurvaturePeaks:
    """AC2: After map rebuild, oval/banking sections produce curvature peaks
    detectable from yaw-rate even when XZ heading is nearly constant."""

    def test_banking_yaw_produces_nonzero_curvature(self):
        """Stations with zero XZ heading change but non-zero yaw-rate → curvature > 0."""
        stations = _straight_stations(30)
        # All stations are on a dead straight (XZ heading = 0 → xz_curv ≈ 0).
        # Inject significant yaw_rate to simulate a banked oval turn.
        # speed = 144 kph = 40 m/s; yaw_rate = 0.2 rad/s → yaw_curv = 0.005 rad/m
        ref_points = [
            _RefPt(
                lap_progress=s.progress_pct / 100.0,
                speed_kph_avg=144.0,
                yaw_rate_avg=0.2,
            )
            for s in stations
        ]
        _compute_curvature(stations, ref_points=ref_points)

        # Every station should show the yaw-based curvature (above near-zero XZ)
        curvatures = [abs(s.curvature) for s in stations]
        assert max(curvatures) > 0.001, (
            f"Expected curvature > 0.001 from yaw-rate on a flat oval section, "
            f"got max={max(curvatures):.6f}"
        )

    def test_banking_peak_exceeds_straight_baseline(self):
        """Banked turn section curvature is measurably higher than a true straight."""
        # True straight — no yaw, no XZ change
        straight = _straight_stations(20)
        ref_straight = [
            _RefPt(s.progress_pct / 100.0, 144.0, 0.0) for s in straight
        ]
        _compute_curvature(straight, ref_points=ref_straight)
        straight_max = max(abs(s.curvature) for s in straight)

        # Banked turn — same XZ path, but sustained yaw_rate
        banked = _straight_stations(20)
        ref_banked = [
            _RefPt(s.progress_pct / 100.0, 144.0, 0.2) for s in banked
        ]
        _compute_curvature(banked, ref_points=ref_banked)
        banked_max = max(abs(s.curvature) for s in banked)

        assert banked_max > straight_max, (
            f"Banking curvature ({banked_max:.5f}) should exceed straight ({straight_max:.5f})"
        )


# ---------------------------------------------------------------------------
# AC4 — Corrected lap length closer to seed than raw accumulation.
# ---------------------------------------------------------------------------

class TestCorrectedLapLengthAccuracy:
    """AC4: compute_corrected_lap_length() snaps to a point near start and
    returns a distance closer to the true track length than the raw total."""

    def test_corrected_closer_to_seed_than_raw(self):
        """200-point near-loop: corrected length < raw last-point length and
        within 5% of a 'seed' value, while raw is over-accumulated."""
        seed_length = 5000.0  # metres — known seed
        n = 200

        # Build a near-loop where points slightly overshoot by 400 m due to drift.
        # Raw total = 5400 m; the closure point at index 175 is at 5000 m.
        raw_total = 5400.0
        start_x, start_z = 0.0, 0.0
        points = []
        for i in range(n):
            angle = 2 * math.pi * i / n
            # Circle of radius ~800 m → circumference ~5027 m
            x = math.cos(angle) * 800.0
            z = math.sin(angle) * 800.0
            dist = raw_total * i / n
            points.append(_RawPt(x=x, y=0.0, z=z, distance_along_lap_m=dist))

        # Start is at (800, 0)
        points[0].x = 800.0
        points[0].z = 0.0

        # Index 175 (87.5% through) is near the start again — at ~5000 m
        points[175].x = 800.0 + 2.0   # within 3 m of start
        points[175].z = 0.0 + 2.0
        points[175].distance_along_lap_m = seed_length  # closure snaps here

        raw_last = points[-1].distance_along_lap_m
        corrected = compute_corrected_lap_length(points)

        raw_err = abs(raw_last - seed_length)
        corrected_err = abs(corrected - seed_length)

        assert corrected_err < raw_err, (
            f"Corrected ({corrected:.1f} m, err={corrected_err:.1f}) should be closer "
            f"to seed ({seed_length:.0f}) than raw ({raw_last:.1f}, err={raw_err:.1f})"
        )

    def test_corrected_within_5pct_of_seed(self):
        """The corrected length must fall within 5% of the true seed length."""
        seed_length = 4000.0
        n = 200

        points = []
        for i in range(n):
            angle = 2 * math.pi * i / n
            x = math.cos(angle) * 637.0   # radius for ~4000 m circumference
            z = math.sin(angle) * 637.0
            dist = 4200.0 * i / n         # slightly over-accumulated
            points.append(_RawPt(x=x, y=0.0, z=z, distance_along_lap_m=dist))

        points[0].x = 637.0
        points[0].z = 0.0

        # Closure point at index 190 (95% through) is within 5 m of start
        points[190].x = 637.0 + 3.0
        points[190].z = 0.0 + 3.0
        points[190].distance_along_lap_m = seed_length

        corrected = compute_corrected_lap_length(points)
        delta_pct = abs(corrected - seed_length) / seed_length * 100.0

        assert delta_pct < 5.0, (
            f"Corrected length ({corrected:.1f} m) is {delta_pct:.1f}% from seed "
            f"({seed_length:.0f} m); expected < 5%"
        )


# ---------------------------------------------------------------------------
# AC5 — Lap-delta blocker removed when corrected length within 5%.
# ---------------------------------------------------------------------------

class _FakeStationMap:
    """Minimal duck-typed TrackStationMap for align_maps_geometry."""
    def __init__(self, lap_length_m: float):
        self.lap_length_m = lap_length_m
        self.stations = []
        self.default_spacing_m = 1.0


class _FakeSeedLayout:
    def __init__(self, length_m: float):
        self.length_m = length_m


class TestLapDeltaBlocker:
    """AC5: blocker absent when delta < 5%; blocker present when delta > 5%."""

    def test_within_5pct_no_blocker(self):
        """Model 4% shorter than seed → no lap-length blocker."""
        seed_len = 5000.0
        model_len = seed_len * (1.0 - 0.04)   # 4% short — inside threshold
        station_map = _FakeStationMap(model_len)
        layout = _FakeSeedLayout(seed_len)

        result = align_maps_geometry(station_map, seed_map=None, seed_layout=layout)

        lap_blockers = [b for b in result.blockers if "shorter" in b or "mismatch" in b.lower()]
        assert len(lap_blockers) == 0, (
            f"Expected no lap-length blocker for {model_len:.0f} m vs seed {seed_len:.0f} m "
            f"(4%), got: {result.blockers}"
        )

    def test_outside_5pct_blocker_raised(self):
        """Model 8% shorter than seed → lap-length blocker is added."""
        seed_len = 5000.0
        model_len = seed_len * (1.0 - 0.08)   # 8% short — outside threshold
        station_map = _FakeStationMap(model_len)
        layout = _FakeSeedLayout(seed_len)

        result = align_maps_geometry(station_map, seed_map=None, seed_layout=layout)

        lap_blockers = [b for b in result.blockers if "shorter" in b or "mismatch" in b.lower()]
        assert len(lap_blockers) > 0, (
            f"Expected a lap-length blocker for {model_len:.0f} m vs seed {seed_len:.0f} m "
            f"(8%), got none. blockers={result.blockers}"
        )

    def test_well_within_5pct_is_not_blocked(self):
        """2% delta is clearly within tolerance — no lap-length or missing-section blockers."""
        seed_len = 5000.0
        model_len = seed_len * 0.98   # 2% short — well inside 5% threshold
        station_map = _FakeStationMap(model_len)
        layout = _FakeSeedLayout(seed_len)

        result = align_maps_geometry(station_map, seed_map=None, seed_layout=layout)

        # No blockers of any kind expected at 2% delta
        assert len(result.blockers) == 0, (
            f"Expected no blockers at 2% delta, got: {result.blockers}"
        )

    def test_just_above_5pct_is_blocked(self):
        """5.1% delta → blocker is present."""
        seed_len = 5000.0
        model_len = seed_len * (1.0 - 0.051)
        station_map = _FakeStationMap(model_len)
        layout = _FakeSeedLayout(seed_len)

        result = align_maps_geometry(station_map, seed_map=None, seed_layout=layout)

        lap_blockers = [b for b in result.blockers if "shorter" in b or "mismatch" in b.lower()]
        assert len(lap_blockers) > 0, (
            f"5.1% delta should raise a blocker, got: {result.blockers}"
        )


# ---------------------------------------------------------------------------
# AC7 — verification_source mutation on SeededCorner after AI assign.
# ---------------------------------------------------------------------------

class TestSeededCornerVerificationSourceMutation:
    """AC7 (pure-Python path): after AI verify result is applied, corner
    objects whose IDs appear in the result dict have verification_source='ai_verified'.
    Corners not in the result retain their original source.

    This tests the mutation logic in isolation — not the Qt signal wiring.
    The mutation pattern comes from dashboard.py lines 3651-3656:
        for corner in station_map.seeded_corners:
            if corner.corner_id in result:
                corner.verification_source = "ai_verified"
    """

    @staticmethod
    def _apply_ai_result(corners: List[SeededCorner], result: dict) -> None:
        """Replicate the mutation loop from dashboard._tm_ai_corner_verify_done."""
        for corner in corners:
            if corner.corner_id in result:
                corner.verification_source = "ai_verified"

    def _make_corner(self, corner_id: str, progress: float = 0.1) -> SeededCorner:
        return SeededCorner(
            corner_id=corner_id,
            display_name=corner_id,
            approx_station_m=progress * 5000.0,
            approx_progress=progress,
            confidence=0.8,
            verification_source="greedy",
        )

    def test_matched_corners_get_ai_verified(self):
        """Corners in the AI result dict have verification_source='ai_verified'."""
        corners = [
            self._make_corner("T1", 0.1),
            self._make_corner("T2", 0.25),
            self._make_corner("T3", 0.5),
        ]
        ai_result = {
            "T1": {"progress_pct": 10.0, "confidence": 0.9},
            "T2": {"progress_pct": 25.0, "confidence": 0.85},
        }
        self._apply_ai_result(corners, ai_result)

        assert corners[0].verification_source == "ai_verified", "T1 should be ai_verified"
        assert corners[1].verification_source == "ai_verified", "T2 should be ai_verified"

    def test_unmatched_corner_retains_greedy(self):
        """Corners not in the AI result keep their original verification_source."""
        corners = [
            self._make_corner("T1", 0.1),
            self._make_corner("T3", 0.5),
        ]
        ai_result = {
            "T1": {"progress_pct": 10.0, "confidence": 0.9},
            # T3 absent from result
        }
        self._apply_ai_result(corners, ai_result)

        assert corners[1].verification_source == "greedy", (
            "T3 not in AI result — should remain 'greedy'"
        )

    def test_empty_result_leaves_all_greedy(self):
        """Empty AI result dict → all corners stay 'greedy'."""
        corners = [self._make_corner("T1"), self._make_corner("T2")]
        self._apply_ai_result(corners, {})
        for c in corners:
            assert c.verification_source == "greedy"
