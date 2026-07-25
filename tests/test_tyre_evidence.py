"""Tests for strategy/tyre_evidence.py — cliff detection, optimal stint, crossover.

Covers:
  • Theil-Sen slope on flat data returns ~0 (not the fabricated positive from the
    old increment-summation approach)
  • Theil-Sen slope on a linearly degrading stint returns the correct slope
  • Profiles are capped at tested lap count (no extrapolation)
  • Cliff detected when degradation accelerates significantly
  • Optimal stint length ≤ cliff onset (or ≤ tested laps when no cliff)
  • Compound crossover requires measured runs on both compounds
  • Compound crossover beyond tested range returns crossover_lap=0 (unknown)
  • All public functions are pure, never raise, deterministic

Pure/offline: no DB, no Qt, no AI.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.tyre_evidence import (  # noqa: E402
    CompoundTyreProfile,
    CompoundCrossover,
    build_compound_profile,
    compute_compound_crossover,
    _theil_sen_slope,
    _detect_cliff,
    _optimal_stint_laps,
    FLAT_SLOPE_THRESHOLD,
    MIN_LAPS_FOR_PROFILE,
    MIN_LAPS_FOR_CLIFF,
)


# ---------------------------------------------------------------------------
# Theil-Sen helpers
# ---------------------------------------------------------------------------

class TestTheilSenSlope:
    def test_flat_data_returns_zero(self):
        """Flat lap times → slope ≈ 0, NOT the fabricated positive from incrementing."""
        pairs = [(i + 1, 100.0) for i in range(10)]
        assert _theil_sen_slope(pairs) == pytest.approx(0.0, abs=1e-9)

    def test_linear_degradation(self):
        """Perfectly linear +0.08 s/lap → slope = 0.08."""
        pairs = [(i + 1, 100.0 + i * 0.08) for i in range(12)]
        assert _theil_sen_slope(pairs) == pytest.approx(0.08, abs=1e-6)

    def test_negative_slope_clamped_externally(self):
        """Improving lap times yield a negative slope (external callers clamp ≥ 0)."""
        pairs = [(i + 1, 100.0 - i * 0.05) for i in range(8)]
        slope = _theil_sen_slope(pairs)
        assert slope < 0  # negative is correct; clamping is the caller's job

    def test_single_point_returns_zero(self):
        assert _theil_sen_slope([(1, 100.0)]) == 0.0

    def test_empty_returns_zero(self):
        assert _theil_sen_slope([]) == 0.0

    def test_outlier_robustness(self):
        """A single extreme outlier lap should not dominate the slope."""
        pairs = [(i + 1, 100.0 + i * 0.08) for i in range(11)]
        pairs.append((12, 110.0))  # outlier spike
        slope = _theil_sen_slope(pairs)
        # Should still be much closer to 0.08 than to (110-100)/11 ≈ 0.9
        assert slope < 0.3


# ---------------------------------------------------------------------------
# Cliff detection
# ---------------------------------------------------------------------------

class TestDetectCliff:
    def test_flat_no_cliff(self):
        laps = [100.0] * 12
        cliff_lap, convex = _detect_cliff(laps)
        assert cliff_lap == 0 and not convex

    def test_linear_no_cliff(self):
        """Uniform degradation is NOT a cliff — ratio first/last ≈ 1.0."""
        laps = [100.0 + i * 0.08 for i in range(12)]
        cliff_lap, convex = _detect_cliff(laps)
        assert not convex  # uniform slope, not accelerating

    def test_cliff_detected_late_acceleration(self):
        """Mild degradation early, steep acceleration late → cliff detected."""
        laps = [100.0 + i * 0.05 for i in range(6)]    # first 6: mild
        laps += [laps[-1] + (i + 1) * 0.6 for i in range(6)]  # next 6: steep
        cliff_lap, convex = _detect_cliff(laps)
        assert convex, "accelerating degradation should be detected as a cliff"
        assert cliff_lap > 0

    def test_too_few_laps_no_cliff(self):
        """Fewer than MIN_LAPS_FOR_CLIFF laps → cannot detect a cliff."""
        laps = [100.0 + i * 0.5 for i in range(MIN_LAPS_FOR_CLIFF - 1)]
        cliff_lap, convex = _detect_cliff(laps)
        assert cliff_lap == 0 and not convex


# ---------------------------------------------------------------------------
# Optimal stint laps
# ---------------------------------------------------------------------------

class TestOptimalStintLaps:
    def test_formula_basic(self):
        """S* = floor(sqrt(2 × pit / slope)), basic sanity check."""
        # pit=25s, slope=0.1 s/lap → S* = floor(sqrt(500)) = floor(22.36) = 22
        result = _optimal_stint_laps(0.1, 25.0, known_good_laps=30, fuel_limit_laps=0)
        assert result == 22

    def test_capped_at_known_good(self):
        """Never recommend more than the tested (known-good) stint length."""
        result = _optimal_stint_laps(0.01, 25.0, known_good_laps=10, fuel_limit_laps=0)
        assert result <= 10

    def test_capped_at_fuel_limit(self):
        """Never exceed the fuel-limited max stint."""
        result = _optimal_stint_laps(0.001, 25.0, known_good_laps=50, fuel_limit_laps=20)
        assert result <= 20

    def test_flat_tyre_uses_evidence_cap(self):
        """Flat tyre: optimal → ∞, so fuel/evidence cap dominates."""
        result = _optimal_stint_laps(0.0, 25.0, known_good_laps=15, fuel_limit_laps=0)
        assert result == 15

    def test_flat_tyre_no_caps_returns_zero(self):
        """Flat tyre with no fuel or evidence cap → 0 (unknown)."""
        result = _optimal_stint_laps(0.0, 25.0, known_good_laps=0, fuel_limit_laps=0)
        assert result == 0

    def test_no_pit_loss_returns_zero(self):
        """Without a pit-loss reference, the formula is undefined."""
        result = _optimal_stint_laps(0.1, 0.0, known_good_laps=20, fuel_limit_laps=0)
        assert result == 0


# ---------------------------------------------------------------------------
# build_compound_profile
# ---------------------------------------------------------------------------

class TestBuildCompoundProfile:
    def test_flat_profile_slope_near_zero(self):
        """Flat lap times → slope ≈ 0 (not fabricated wear)."""
        laps = [100.0] * 8
        p = build_compound_profile("RM", laps, pit_loss_s=22.0)
        assert p.slope_s_per_lap == pytest.approx(0.0, abs=1e-6)
        assert p.is_flat

    def test_degrading_profile_positive_slope(self):
        """Linearly degrading laps → slope = wear rate."""
        laps = [100.0 + i * 0.08 for i in range(12)]
        p = build_compound_profile("RM", laps, pit_loss_s=22.0)
        assert p.slope_s_per_lap == pytest.approx(0.08, abs=1e-4)
        assert not p.is_flat

    def test_profile_capped_at_tested_laps(self):
        """Tested laps = len(input): evidence never extrapolated beyond measured data."""
        laps = [100.0 + i * 0.1 for i in range(8)]
        p = build_compound_profile("RS", laps, pit_loss_s=22.0)
        assert p.tested_laps == 8
        assert p.known_good_laps <= 8  # known-good is at most what was tested

    def test_cliff_onset_below_tested_laps(self):
        """If a cliff is detected, known_good_laps < tested_laps."""
        mild = [100.0 + i * 0.04 for i in range(6)]
        steep = [mild[-1] + (i + 1) * 0.8 for i in range(6)]
        laps = mild + steep
        p = build_compound_profile("RS", laps, pit_loss_s=22.0)
        if p.cliff_onset_lap > 0:
            assert p.known_good_laps < p.tested_laps
            assert p.cliff_onset_lap <= p.tested_laps

    def test_insufficient_laps_returns_safe_profile(self):
        """Too few laps → confident="insufficient", slope=0, never raises."""
        p = build_compound_profile("RM", [100.0, 100.1], pit_loss_s=22.0)
        assert p.confidence == "insufficient"
        assert p.slope_s_per_lap == 0.0

    def test_empty_input_returns_safe_profile(self):
        p = build_compound_profile("RM", [])
        assert isinstance(p, CompoundTyreProfile)
        assert p.confidence == "insufficient"

    def test_optimal_stint_never_exceeds_known_good(self):
        """Optimal stint (if non-zero) is always ≤ known_good_laps."""
        laps = [100.0 + i * 0.1 for i in range(12)]
        p = build_compound_profile("RM", laps, pit_loss_s=22.0)
        if p.optimal_stint_laps > 0:
            assert p.optimal_stint_laps <= p.known_good_laps

    def test_high_confidence_for_8_or_more_laps(self):
        laps = [100.0 + i * 0.08 for i in range(8)]
        p = build_compound_profile("RM", laps)
        assert p.confidence == "high"

    def test_fuel_limit_laps_stored(self):
        laps = [100.0] * 8
        p = build_compound_profile("RM", laps, fuel_limit_laps=20)
        assert p.fuel_limit_laps == 20

    def test_never_raises_on_junk_input(self):
        """Never raises regardless of input quality."""
        p = build_compound_profile("RM", [None, "x", -1, 0], pit_loss_s=22.0)
        assert isinstance(p, CompoundTyreProfile)


# ---------------------------------------------------------------------------
# compute_compound_crossover
# ---------------------------------------------------------------------------

class TestComputeCompoundCrossover:
    def _make_profile(self, compound, n_laps, slope):
        laps = [100.0 + i * slope for i in range(n_laps)]
        return build_compound_profile(compound, laps, pit_loss_s=22.0)

    def test_crossover_beyond_tested_returns_zero(self):
        """Crossover lap beyond the tested range → crossover_lap=0 (unknown)."""
        # RM faster fresh but degrades slowly; RS slower fresh but stable → crossover far away
        profile_rm = self._make_profile("RM", 8, 0.1)    # degrades 0.1/lap
        profile_rs = self._make_profile("RS", 8, 0.08)   # degrades 0.08/lap (more durable)
        # RM is 1.0 s faster fresh; RM degrades faster (0.1 > 0.08 s/lap)
        # Crossover = 2×1.0/(0.1-0.08) + 1 = 2/0.02 + 1 = 101 → beyond 8 laps
        co = compute_compound_crossover("RM", "RS", profile_rm, profile_rs, 1.0, 22.0)
        assert co.crossover_lap == 0
        assert co.confidence == "insufficient"

    def test_crossover_within_tested_returns_lap(self):
        """Crossover within tested range returns the correct lap number."""
        # A = fast fresh but degrades 0.5/lap; B = 0.5s slower fresh, flat
        laps_a = [100.0 + i * 0.5 for i in range(15)]
        laps_b = [100.5] * 15  # flat, no degradation
        profile_a = build_compound_profile("A", laps_a, pit_loss_s=22.0)
        profile_b = build_compound_profile("B", laps_b, pit_loss_s=22.0)
        # N* = 2×0.5/(0.5-0) + 1 = 2 + 1 = 3
        co = compute_compound_crossover("A", "B", profile_a, profile_b, 0.5, 22.0)
        # Crossover should be at or near lap 3
        assert 1 <= co.crossover_lap <= 5
        assert co.confidence in ("high", "medium")

    def test_insufficient_when_compound_not_tested(self):
        """crossover requires ≥ MIN_LAPS_FOR_PROFILE on BOTH compounds."""
        profile_ok = self._make_profile("RM", 8, 0.1)
        profile_short = build_compound_profile("RS", [100.0, 100.1])  # too short
        co = compute_compound_crossover("RM", "RS", profile_ok, profile_short, 0.5, 22.0)
        assert co.crossover_lap == 0
        assert co.confidence == "insufficient"

    def test_no_crossover_when_b_already_faster_fresh(self):
        """When fresh_pace_delta ≤ 0 (B already faster), crossover_lap=0."""
        profile_a = self._make_profile("RM", 8, 0.1)
        profile_b = self._make_profile("RS", 8, 0.05)
        co = compute_compound_crossover("RM", "RS", profile_a, profile_b,
                                        fresh_pace_delta_s=-0.5, pit_loss_s=22.0)
        assert co.crossover_lap == 0

    def test_no_crossover_when_a_degrades_no_faster(self):
        """When slope_a ≤ slope_b, A stays faster → crossover_lap=0."""
        profile_a = self._make_profile("RM", 8, 0.05)
        profile_b = self._make_profile("RS", 8, 0.1)
        co = compute_compound_crossover("RM", "RS", profile_a, profile_b, 0.5, 22.0)
        assert co.crossover_lap == 0

    def test_never_raises_on_junk(self):
        """compute_compound_crossover never raises."""
        p = build_compound_profile("RM", [100.0] * 8)
        co = compute_compound_crossover(None, None, p, p, "bad", "bad")
        assert isinstance(co, CompoundCrossover)


# ---------------------------------------------------------------------------
# End-to-end: adapter integration check
# ---------------------------------------------------------------------------

class TestAdapterIntegration:
    """Prove build_compound_profile is wired from extract_session_strategy_samples."""

    def _make_db(self, laps_ms):
        class MockDB:
            def get_session_meta(self, sid):
                return {"id": sid, "car_id": 911, "track": "Fuji", "config_id": ""}

            def get_session_laps(self, sid, exclude_pit=False, exclude_out=False):
                return [
                    {"lap_num": i + 1, "lap_time_ms": t, "fuel_used": 4.0,
                     "compound": "RM", "is_pit_lap": 0, "is_out_lap": 0,
                     "fuel_start": 0, "fuel_end": 0}
                    for i, t in enumerate(laps_ms)
                ]
        return MockDB()

    def test_profiles_populated_in_samples(self):
        from strategy.race_strategy_session_adapter import extract_session_strategy_samples
        db = self._make_db([100000 + i * 80 for i in range(12)])  # 0.08 s/lap drift
        s = extract_session_strategy_samples(db, 1)
        assert "RM" in s.compound_tyre_profiles
        p = s.compound_tyre_profiles["RM"]
        assert isinstance(p, CompoundTyreProfile)
        assert p.tested_laps == 12
        assert p.slope_s_per_lap == pytest.approx(0.08, abs=1e-4)

    def test_flat_profile_in_adapter(self):
        """Flat laps → slope ≈ 0 in the compound profile built by the adapter."""
        from strategy.race_strategy_session_adapter import extract_session_strategy_samples
        db = self._make_db([100000] * 12)  # flat
        s = extract_session_strategy_samples(db, 1)
        p = s.compound_tyre_profiles.get("RM")
        assert p is not None
        assert p.slope_s_per_lap == pytest.approx(0.0, abs=1e-6)
        assert p.is_flat


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
