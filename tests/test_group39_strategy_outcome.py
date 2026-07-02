"""
Group 39 — Deterministic Race Outcome Computation

Tests for strategy/outcome.py: compute_outcome and compare_outcomes,
and the wiring into StrategyOption via _parse_strategies in ai_planner.py.

All tests are offline — no API calls, no Qt, no file I/O beyond module imports.

Coverage
--------
* compute_outcome basic: known stints + params + deg => expected estimated_time_s,
  n_stops, pit_time_s correctness.
* Refuel time uses the rate (e.g. 50 L / 1 L/s => 50 s added), not a flat guess.
* Degradation raises stint time vs no-deg baseline; cliff step adds extra beyond cliff lap.
* Missing deg data => confidence "low"/"medium" + assumption note + no crash.
* compare_outcomes: fastest gets delta 0.0 / rank 1; slower gets positive delta;
  ordering of returned entries matches input order; empty and single-option cases.
* Wiring smoke: build StrategyOptions (via _parse_strategies) and assert
  deterministic_time_s / delta_vs_fastest_s / rank_by_time get populated;
  stints shape is unchanged.
* Guard test: StrategyOption.stints dict keys still contain compound, laps,
  ref_lap_ms, pace_threshold_ms after wiring.
"""
from __future__ import annotations

import dataclasses
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.outcome import (
    _per_lap_penalty_s,
    compare_outcomes,
    compute_outcome,
    format_outcome_comparison_for_prompt,
)
import strategy.ai_planner as ap
from strategy.ai_planner import RaceParams, StrategyOption


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_GT7_TANK_CAPACITY = 100.0  # L


def _make_params(**overrides) -> RaceParams:
    """Construct a minimal race-ready RaceParams."""
    kwargs = dict(
        track="Spa",
        total_laps=30,
        tyre_wear_multiplier=1.0,
        fuel_burn_per_lap=3.0,
        refuel_speed_lps=1.0,   # 1 L/s — makes refuel times easy to reason about
        pit_loss_secs=20.0,
    )
    kwargs.update(overrides)
    return RaceParams(**kwargs)


def _make_option(stints: list[dict], rank: int = 1, name: str = "Test") -> StrategyOption:
    """Construct a minimal StrategyOption."""
    return StrategyOption(
        rank=rank,
        name=name,
        stints=stints,
        estimated_time_s=0.0,
        pit_time_s=0.0,
        summary="",
        risks="",
    )


def _make_deg_entry(
    cliff_lap_practice: int = 10,
    pace_loss_at_cliff_s: float = 1.0,
    optimal_stint_race: int = 9,
    total_life_race: int = 12,
    confidence: str = "high",
) -> dict:
    return {
        "cliff_lap_practice": cliff_lap_practice,
        "pace_loss_at_cliff_s": pace_loss_at_cliff_s,
        "optimal_stint_race": optimal_stint_race,
        "total_life_race": total_life_race,
        "confidence": confidence,
    }


# ---------------------------------------------------------------------------
# _per_lap_penalty_s unit tests
# ---------------------------------------------------------------------------

class TestPerLapPenalty:
    """Unit tests for the per-lap degradation penalty helper."""

    def test_no_deg_data_zero_penalty(self):
        """When cliff_lap_practice is 0, penalty is always 0."""
        assert _per_lap_penalty_s(5, 0, 1.0, 1.0) == pytest.approx(0.0)

    def test_no_pace_loss_zero_penalty(self):
        """When pace_loss_at_cliff_s is 0, penalty is always 0."""
        assert _per_lap_penalty_s(5, 10, 0.0, 1.0) == pytest.approx(0.0)

    def test_linear_penalty_before_cliff(self):
        """Before the cliff, penalty = lap_index_0 * (pace_loss/cliff) * wear_mult."""
        # cliff_lap_practice=10, pace_loss=1.0, wear_mult=1.0 => rate=0.1 s/lap
        # lap_index_0=5 => 5 * 0.1 = 0.5 s
        result = _per_lap_penalty_s(5, 10, 1.0, 1.0)
        assert result == pytest.approx(0.5)

    def test_wear_multiplier_scales_linear(self):
        """tyre_wear_multiplier scales the linear component."""
        # wear_mult=2.0: rate=0.2 s/lap; lap_index_0=5 => 1.0 s (linear only, before cliff)
        result = _per_lap_penalty_s(5, 10, 1.0, 2.0)
        assert result == pytest.approx(1.0)

    def test_cliff_step_added_at_and_beyond_cliff(self):
        """At lap_index_0 == cliff_lap_practice, cliff step is applied once."""
        # cliff_lap_practice=5, pace_loss=2.0, wear_mult=1.0
        # rate=2.0/5=0.4 s/lap
        # lap_index_0=5 (0-indexed lap 6, the lap AFTER the cliff boundary):
        #   linear = 5 * 0.4 = 2.0
        #   cliff_step_count = max(0, 5 - 5 + 1) = 1  =>  1 * 2.0 = 2.0
        #   total = 4.0
        result = _per_lap_penalty_s(5, 5, 2.0, 1.0)
        assert result == pytest.approx(4.0)

    def test_cliff_step_accumulates(self):
        """Two laps beyond the cliff add two cliff steps."""
        # cliff_lap_practice=5, pace_loss=2.0
        # lap_index_0=6: linear=6*0.4=2.4; cliff_count=max(0,6-5+1)=2; cliff=4.0; total=6.4
        result = _per_lap_penalty_s(6, 5, 2.0, 1.0)
        assert result == pytest.approx(6.4)

    def test_lap_zero_penalty_is_zero(self):
        """First lap (lap_index_0=0) has zero penalty regardless of deg data."""
        result = _per_lap_penalty_s(0, 10, 1.0, 1.0)
        assert result == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# compute_outcome — basic correctness
# ---------------------------------------------------------------------------

class TestComputeOutcomeBasic:
    """compute_outcome with known inputs; verify estimated_time_s, n_stops, pit_time_s."""

    def test_single_stint_no_deg_no_stops(self):
        """0-stop race: green_time = base_lap_s * laps; pit_time = 0."""
        stints = [{"compound": "RH", "laps": 10, "ref_lap_ms": 90_000, "pace_threshold_ms": 3000}]
        params = _make_params(total_laps=10, fuel_burn_per_lap=3.0, refuel_speed_lps=1.0,
                              pit_loss_secs=20.0)
        option = _make_option(stints)
        # No deg data → no penalty
        result = compute_outcome(option, params, degradation={})
        assert result["n_stops"] == 0
        assert result["pit_time_s"] == pytest.approx(0.0)
        assert result["green_time_s"] == pytest.approx(90.0 * 10)
        assert result["estimated_time_s"] == pytest.approx(90.0 * 10)

    def test_two_stints_one_stop_pit_time_formula(self):
        """1-stop race: pit_time = pit_loss + ceil(fuel_for_second_stint / refuel_rate)."""
        # Stint 2 has 15 laps × 3 L/lap = 45 L; refuel_speed = 1 L/s => ceil(45/1) = 45 s
        # pit_time = 20 (loss) + 45 (refuel) = 65 s
        stints = [
            {"compound": "RM", "laps": 15, "ref_lap_ms": 92_000, "pace_threshold_ms": 2500},
            {"compound": "RH", "laps": 15, "ref_lap_ms": 94_000, "pace_threshold_ms": 3000},
        ]
        params = _make_params(total_laps=30, fuel_burn_per_lap=3.0, refuel_speed_lps=1.0,
                              pit_loss_secs=20.0)
        option = _make_option(stints)
        result = compute_outcome(option, params, degradation={})
        assert result["n_stops"] == 1
        expected_fuel = 3.0 * 15  # 45 L for stint 2
        expected_refuel_s = math.ceil(expected_fuel / 1.0)  # 45 s
        expected_pit = 20.0 + expected_refuel_s  # 65 s
        assert result["pit_time_s"] == pytest.approx(expected_pit)

    def test_refuel_uses_rate_not_flat(self):
        """Refuel time = ceil(fuel / rate); verifies rate-based calculation explicitly."""
        # 50 L / 1 L/s = 50 s
        stints = [
            {"compound": "RM", "laps": 10, "ref_lap_ms": 90_000, "pace_threshold_ms": 2500},
            {"compound": "RM", "laps": 10, "ref_lap_ms": 90_000, "pace_threshold_ms": 2500},
        ]
        params = _make_params(fuel_burn_per_lap=5.0, refuel_speed_lps=1.0, pit_loss_secs=0.0)
        option = _make_option(stints)
        result = compute_outcome(option, params, degradation={})
        # Next stint = 10 laps × 5 L/lap = 50 L; ceil(50/1) = 50 s
        assert result["pit_time_s"] == pytest.approx(50.0)

    def test_refuel_rate_2lps(self):
        """Different refuel rate: 50 L / 2 L/s = ceil(25) = 25 s."""
        stints = [
            {"compound": "RM", "laps": 10, "ref_lap_ms": 90_000, "pace_threshold_ms": 2500},
            {"compound": "RM", "laps": 10, "ref_lap_ms": 90_000, "pace_threshold_ms": 2500},
        ]
        params = _make_params(fuel_burn_per_lap=5.0, refuel_speed_lps=2.0, pit_loss_secs=0.0)
        option = _make_option(stints)
        result = compute_outcome(option, params, degradation={})
        assert result["pit_time_s"] == pytest.approx(25.0)

    def test_refuel_capped_at_tank_capacity(self):
        """Fuel per stop is capped at 100 L (GT7 tank capacity)."""
        # 20 laps × 8 L/lap = 160 L > 100 L cap => ceil(100 / 1) = 100 s
        stints = [
            {"compound": "RH", "laps": 5, "ref_lap_ms": 100_000, "pace_threshold_ms": 3000},
            {"compound": "RH", "laps": 20, "ref_lap_ms": 100_000, "pace_threshold_ms": 3000},
        ]
        params = _make_params(fuel_burn_per_lap=8.0, refuel_speed_lps=1.0, pit_loss_secs=0.0)
        option = _make_option(stints)
        result = compute_outcome(option, params, degradation={})
        assert result["pit_time_s"] == pytest.approx(100.0)

    def test_two_stops_pit_loss_multiplied(self):
        """2-stop: pit_loss_secs is multiplied by 2."""
        stints = [
            {"compound": "RS", "laps": 10, "ref_lap_ms": 88_000, "pace_threshold_ms": 2000},
            {"compound": "RM", "laps": 10, "ref_lap_ms": 92_000, "pace_threshold_ms": 2500},
            {"compound": "RH", "laps": 10, "ref_lap_ms": 94_000, "pace_threshold_ms": 3000},
        ]
        params = _make_params(total_laps=30, fuel_burn_per_lap=3.0, refuel_speed_lps=100.0,
                              pit_loss_secs=20.0)
        option = _make_option(stints)
        result = compute_outcome(option, params, degradation={})
        assert result["n_stops"] == 2
        # Refuel: stint2=10×3=30L => ceil(30/100)=1s; stint3=10×3=30L => ceil(30/100)=1s
        # pit = 2*20 + 1 + 1 = 42 s
        assert result["pit_time_s"] == pytest.approx(42.0)

    def test_per_stint_keys_present(self):
        """per_stint dicts contain the required keys."""
        stints = [{"compound": "RM", "laps": 5, "ref_lap_ms": 90_000, "pace_threshold_ms": 2500}]
        option = _make_option(stints)
        result = compute_outcome(option, _make_params(), degradation={})
        assert len(result["per_stint"]) == 1
        ps = result["per_stint"][0]
        assert "compound" in ps
        assert "laps" in ps
        assert "base_lap_s" in ps
        assert "deg_penalty_s" in ps
        assert "stint_time_s" in ps

    def test_estimated_time_green_plus_pit(self):
        """estimated_time_s == green_time_s + pit_time_s."""
        stints = [
            {"compound": "RM", "laps": 15, "ref_lap_ms": 90_000, "pace_threshold_ms": 2500},
            {"compound": "RH", "laps": 15, "ref_lap_ms": 94_000, "pace_threshold_ms": 3000},
        ]
        option = _make_option(stints)
        result = compute_outcome(option, _make_params(fuel_burn_per_lap=3.0, refuel_speed_lps=1.0,
                                                     pit_loss_secs=20.0), degradation={})
        assert result["estimated_time_s"] == pytest.approx(
            result["green_time_s"] + result["pit_time_s"]
        )


# ---------------------------------------------------------------------------
# compute_outcome — degradation model
# ---------------------------------------------------------------------------

class TestComputeOutcomeDegradation:
    """Verify degradation raises stint time vs no-deg baseline."""

    def _run(self, compound: str, laps: int, base_lap_s: float, deg: dict | None) -> dict:
        ref_ms = int(base_lap_s * 1000)
        stints = [{"compound": compound, "laps": laps, "ref_lap_ms": ref_ms, "pace_threshold_ms": 2000}]
        option = _make_option(stints)
        params = _make_params(total_laps=laps, tyre_wear_multiplier=1.0,
                              fuel_burn_per_lap=3.0, refuel_speed_lps=1.0, pit_loss_secs=0.0)
        return compute_outcome(option, params, degradation=deg)

    def test_deg_raises_stint_time_above_flat(self):
        """With degradation data, stint_time_s > flat pace * laps."""
        compound = "RS"
        laps = 12
        base_lap_s = 88.0
        flat_time = base_lap_s * laps  # 1056.0 s

        deg = {compound: _make_deg_entry(cliff_lap_practice=10, pace_loss_at_cliff_s=1.0)}
        result = self._run(compound, laps, base_lap_s, deg)

        assert result["green_time_s"] > flat_time, (
            f"Expected green_time_s > {flat_time}, got {result['green_time_s']}"
        )

    def test_no_deg_data_equals_flat_pace(self):
        """Without degradation data, green_time_s == base_lap_s * laps exactly."""
        compound = "RS"
        laps = 12
        base_lap_s = 88.0
        flat_time = base_lap_s * laps

        result = self._run(compound, laps, base_lap_s, deg={})
        assert result["green_time_s"] == pytest.approx(flat_time)

    def test_cliff_step_adds_penalty_beyond_cliff(self):
        """Laps beyond the cliff add the cliff step; verify the extra time is substantial."""
        compound = "RS"
        laps = 15
        base_lap_s = 88.0
        # cliff at lap 10, pace_loss=2.0 s
        deg = {compound: _make_deg_entry(cliff_lap_practice=10, pace_loss_at_cliff_s=2.0)}

        # No deg (flat) vs with deg (with cliff)
        result_flat = self._run(compound, laps, base_lap_s, deg={})
        result_deg = self._run(compound, laps, base_lap_s, deg=deg)

        assert result_deg["green_time_s"] > result_flat["green_time_s"]

    def test_cliff_step_exact_calculation(self):
        """Verify the exact penalty for a known 2-lap stint with cliff at lap 1.

        cliff_lap_practice=1, pace_loss=2.0, wear_mult=1.0
        lap 0 (1st lap):
          linear = 0 * (2.0/1) * 1.0 = 0.0
          cliff_count = max(0, 0-1+1) = 0
          penalty = 0.0
        lap 1 (2nd lap):
          linear = 1 * (2.0/1) * 1.0 = 2.0
          cliff_count = max(0, 1-1+1) = 1  => cliff = 2.0
          penalty = 4.0
        total green = base*2 + 0.0 + 4.0 = 180.0 + 4.0 = 184.0
        """
        compound = "RS"
        base_lap_s = 90.0
        laps = 2
        deg = {compound: {"cliff_lap_practice": 1, "pace_loss_at_cliff_s": 2.0,
                           "optimal_stint_race": 0, "total_life_race": 2, "confidence": "high"}}
        result = self._run(compound, laps, base_lap_s, deg)
        assert result["green_time_s"] == pytest.approx(90.0 * 2 + 0.0 + 4.0)

    def test_wear_multiplier_scales_linear_component(self):
        """tyre_wear_multiplier=2.0 doubles linear penalty; cliff step unaffected."""
        compound = "RS"
        laps = 5
        base_lap_s = 90.0
        # cliff at lap 20 (well beyond stint) so no cliff steps, only linear
        deg = {compound: _make_deg_entry(cliff_lap_practice=20, pace_loss_at_cliff_s=1.0)}

        stints = [{"compound": compound, "laps": laps, "ref_lap_ms": 90_000, "pace_threshold_ms": 2000}]
        option = _make_option(stints)

        p1 = _make_params(tyre_wear_multiplier=1.0, fuel_burn_per_lap=3.0,
                          refuel_speed_lps=1.0, pit_loss_secs=0.0)
        r1 = compute_outcome(option, p1, deg)

        p2 = _make_params(tyre_wear_multiplier=2.0, fuel_burn_per_lap=3.0,
                          refuel_speed_lps=1.0, pit_loss_secs=0.0)
        r2 = compute_outcome(option, p2, deg)

        penalty_1 = r1["green_time_s"] - base_lap_s * laps
        penalty_2 = r2["green_time_s"] - base_lap_s * laps
        # Linear penalty should double; both should be > 0
        assert penalty_1 > 0
        assert penalty_2 == pytest.approx(penalty_2 / penalty_1 * penalty_1, rel=1e-6)
        assert penalty_2 / penalty_1 == pytest.approx(2.0, abs=0.01)

    def test_deg_penalty_s_in_per_stint_positive(self):
        """per_stint[0].deg_penalty_s is positive when deg data is present."""
        compound = "RS"
        laps = 12
        deg = {compound: _make_deg_entry(cliff_lap_practice=10, pace_loss_at_cliff_s=1.0)}
        stints = [{"compound": compound, "laps": laps, "ref_lap_ms": 88_000, "pace_threshold_ms": 2000}]
        option = _make_option(stints)
        result = compute_outcome(option, _make_params(), deg)
        assert result["per_stint"][0]["deg_penalty_s"] > 0


# ---------------------------------------------------------------------------
# compute_outcome — missing / incomplete degradation data
# ---------------------------------------------------------------------------

class TestComputeOutcomeMissingDegData:
    """Missing or incomplete deg data => confidence drop + assumption note + no crash."""

    def test_no_degradation_dict_at_all(self):
        """degradation=None must not raise and confidence='low'."""
        stints = [{"compound": "RM", "laps": 10, "ref_lap_ms": 90_000, "pace_threshold_ms": 2500}]
        option = _make_option(stints)
        result = compute_outcome(option, _make_params(), degradation=None)
        assert result["confidence"] == "low"
        assert len(result["assumptions"]) > 0

    def test_empty_degradation_dict(self):
        """degradation={} for the compound => confidence='low'."""
        stints = [{"compound": "RM", "laps": 10, "ref_lap_ms": 90_000, "pace_threshold_ms": 2500}]
        option = _make_option(stints)
        result = compute_outcome(option, _make_params(), degradation={})
        assert result["confidence"] == "low"

    def test_incomplete_deg_entry_no_cliff(self):
        """Deg entry present but cliff_lap_practice=0 => confidence 'medium', no crash."""
        compound = "RM"
        stints = [{"compound": compound, "laps": 10, "ref_lap_ms": 90_000, "pace_threshold_ms": 2500}]
        option = _make_option(stints)
        deg = {compound: {"cliff_lap_practice": 0, "pace_loss_at_cliff_s": 0.0,
                           "optimal_stint_race": 9, "confidence": "high"}}
        result = compute_outcome(option, _make_params(), degradation=deg)
        # Entry exists but cliff data incomplete => medium
        assert result["confidence"] == "medium"
        # Should still not raise
        assert result["estimated_time_s"] > 0

    def test_assumption_note_present_for_missing_compound(self):
        """An assumption note must be included when compound has no deg data."""
        stints = [{"compound": "RS", "laps": 10, "ref_lap_ms": 88_000, "pace_threshold_ms": 2000}]
        option = _make_option(stints)
        result = compute_outcome(option, _make_params(), degradation={})
        # At least one assumption should mention the compound or no degradation
        assert any("RS" in a or "no degradation" in a.lower() for a in result["assumptions"])

    def test_high_confidence_when_full_deg_data(self):
        """All compounds have full deg data => confidence='high'."""
        compound = "RH"
        stints = [{"compound": compound, "laps": 10, "ref_lap_ms": 94_000, "pace_threshold_ms": 3000}]
        option = _make_option(stints)
        deg = {compound: _make_deg_entry(cliff_lap_practice=12, pace_loss_at_cliff_s=0.8)}
        result = compute_outcome(option, _make_params(), degradation=deg)
        assert result["confidence"] == "high"
        assert result["assumptions"] == []  # no fallback assumptions needed

    def test_mixed_compounds_confidence_low_when_any_missing(self):
        """Two stints: one has deg data, one does not => confidence='low'."""
        stints = [
            {"compound": "RM", "laps": 15, "ref_lap_ms": 92_000, "pace_threshold_ms": 2500},
            {"compound": "RH", "laps": 15, "ref_lap_ms": 94_000, "pace_threshold_ms": 3000},
        ]
        option = _make_option(stints)
        # Only RM has deg data; RH is missing
        deg = {"RM": _make_deg_entry()}
        result = compute_outcome(option, _make_params(total_laps=30), degradation=deg)
        assert result["confidence"] == "low"

    def test_no_crash_on_empty_stints(self):
        """Option with empty stints list does not raise."""
        option = _make_option([])
        result = compute_outcome(option, _make_params(), degradation={})
        assert result["n_stops"] == 0
        assert result["estimated_time_s"] == pytest.approx(0.0)

    def test_missing_ref_lap_ms_uses_fallback(self):
        """When ref_lap_ms is 0/missing, a fallback is applied and assumption noted."""
        stints = [{"compound": "RM", "laps": 5, "ref_lap_ms": 0, "pace_threshold_ms": 2500}]
        option = _make_option(stints)
        result = compute_outcome(option, _make_params(), degradation={})
        # Should not crash; green_time_s > 0 (placeholder or param-derived)
        assert result["estimated_time_s"] >= 0.0
        # With no ref_lap_ms and no fastest ref, the 90s placeholder is used
        # Assumptions must mention the fallback
        assert len(result["assumptions"]) > 0


# ---------------------------------------------------------------------------
# compare_outcomes
# ---------------------------------------------------------------------------

class TestCompareOutcomes:
    """compare_outcomes correctness and edge cases."""

    def _two_options(self, lap_s_fast: float = 90.0, lap_s_slow: float = 95.0,
                     laps: int = 10) -> tuple[list[StrategyOption], RaceParams]:
        fast = _make_option([{"compound": "RS", "laps": laps,
                               "ref_lap_ms": int(lap_s_fast * 1000), "pace_threshold_ms": 2000}],
                            rank=1, name="Fast")
        slow = _make_option([{"compound": "RH", "laps": laps,
                               "ref_lap_ms": int(lap_s_slow * 1000), "pace_threshold_ms": 3000}],
                            rank=2, name="Slow")
        params = _make_params(total_laps=laps, fuel_burn_per_lap=3.0,
                              refuel_speed_lps=1.0, pit_loss_secs=0.0)
        return [fast, slow], params

    def test_fastest_gets_delta_zero(self):
        """The fastest option has delta_vs_fastest_s == 0.0."""
        options, params = self._two_options()
        result = compare_outcomes(options, params, degradation=None)
        fast_entry = next(e for e in result if e["rank_by_time"] == 1)
        assert fast_entry["delta_vs_fastest_s"] == pytest.approx(0.0)

    def test_fastest_gets_rank_1(self):
        """The fastest option has rank_by_time == 1."""
        options, params = self._two_options(lap_s_fast=90.0, lap_s_slow=95.0)
        result = compare_outcomes(options, params, degradation=None)
        # Fast option is at index 0
        assert result[0]["rank_by_time"] == 1

    def test_slower_gets_positive_delta(self):
        """The slower option has delta_vs_fastest_s > 0."""
        options, params = self._two_options(lap_s_fast=90.0, lap_s_slow=95.0)
        result = compare_outcomes(options, params, degradation=None)
        slow_entry = next(e for e in result if e["rank_by_time"] == 2)
        assert slow_entry["delta_vs_fastest_s"] > 0.0

    def test_delta_matches_time_difference(self):
        """delta_vs_fastest_s == slow.estimated_time_s - fast.estimated_time_s."""
        options, params = self._two_options(lap_s_fast=90.0, lap_s_slow=95.0, laps=10)
        result = compare_outcomes(options, params, degradation=None)
        times = [e["estimated_time_s"] for e in result]
        min_t = min(times)
        for entry in result:
            assert entry["delta_vs_fastest_s"] == pytest.approx(
                entry["estimated_time_s"] - min_t
            )

    def test_output_order_matches_input_order(self):
        """Result entries appear in the same order as the input list (index 0, 1, 2)."""
        options, params = self._two_options()
        result = compare_outcomes(options, params, degradation=None)
        assert result[0]["index"] == 0
        assert result[1]["index"] == 1

    def test_empty_list_returns_empty(self):
        """Empty options list returns empty list."""
        result = compare_outcomes([], _make_params(), degradation=None)
        assert result == []

    def test_single_option_delta_zero_rank_one(self):
        """Single option: delta 0.0, rank 1."""
        option = _make_option([{"compound": "RM", "laps": 10,
                                 "ref_lap_ms": 90_000, "pace_threshold_ms": 2500}])
        result = compare_outcomes([option], _make_params(), degradation=None)
        assert len(result) == 1
        assert result[0]["delta_vs_fastest_s"] == pytest.approx(0.0)
        assert result[0]["rank_by_time"] == 1

    def test_three_options_ranks_ascending(self):
        """Three options are ranked 1 (fastest) to 3 (slowest) by time."""
        options = [
            _make_option([{"compound": "RM", "laps": 10,
                           "ref_lap_ms": 92_000, "pace_threshold_ms": 2500}], rank=2),
            _make_option([{"compound": "RS", "laps": 10,
                           "ref_lap_ms": 88_000, "pace_threshold_ms": 2000}], rank=1),
            _make_option([{"compound": "RH", "laps": 10,
                           "ref_lap_ms": 96_000, "pace_threshold_ms": 3000}], rank=3),
        ]
        params = _make_params(total_laps=10, pit_loss_secs=0.0, fuel_burn_per_lap=3.0,
                              refuel_speed_lps=1.0)
        result = compare_outcomes(options, params, degradation=None)
        # RS (index 1) is fastest
        assert result[1]["rank_by_time"] == 1
        # RM (index 0) is middle
        assert result[0]["rank_by_time"] == 2
        # RH (index 2) is slowest
        assert result[2]["rank_by_time"] == 3

    def test_compare_result_has_outcome_key(self):
        """Each entry has an 'outcome' key containing the compute_outcome dict."""
        option = _make_option([{"compound": "RM", "laps": 5,
                                 "ref_lap_ms": 90_000, "pace_threshold_ms": 2500}])
        result = compare_outcomes([option], _make_params(), degradation=None)
        assert "outcome" in result[0]
        assert "per_stint" in result[0]["outcome"]
        assert "green_time_s" in result[0]["outcome"]

    def test_confidence_propagated(self):
        """confidence field is present and is 'high'/'medium'/'low'."""
        compound = "RM"
        option = _make_option([{"compound": compound, "laps": 5,
                                 "ref_lap_ms": 90_000, "pace_threshold_ms": 2500}])
        deg = {compound: _make_deg_entry()}
        result = compare_outcomes([option], _make_params(), degradation=deg)
        assert result[0]["confidence"] in ("high", "medium", "low")


# ---------------------------------------------------------------------------
# format_outcome_comparison_for_prompt
# ---------------------------------------------------------------------------

class TestFormatOutcomeComparisonForPrompt:
    """Basic output tests for the optional prompt-helper."""

    def test_empty_returns_empty_string(self):
        assert format_outcome_comparison_for_prompt([]) == ""

    def test_single_entry_contains_rank(self):
        option = _make_option([{"compound": "RM", "laps": 10,
                                 "ref_lap_ms": 90_000, "pace_threshold_ms": 2500}])
        cr = compare_outcomes([option], _make_params(), degradation=None)
        text = format_outcome_comparison_for_prompt(cr)
        assert "rank by time: 1" in text

    def test_fastest_label_present(self):
        options, params = [
            _make_option([{"compound": "RS", "laps": 10,
                           "ref_lap_ms": 88_000, "pace_threshold_ms": 2000}]),
            _make_option([{"compound": "RH", "laps": 10,
                           "ref_lap_ms": 96_000, "pace_threshold_ms": 3000}]),
        ], _make_params(total_laps=10, pit_loss_secs=0.0, fuel_burn_per_lap=3.0)
        cr = compare_outcomes(options, params, degradation=None)
        text = format_outcome_comparison_for_prompt(cr)
        assert "fastest" in text


# ---------------------------------------------------------------------------
# Wiring smoke tests — StrategyOption gets deterministic fields
# ---------------------------------------------------------------------------

class TestWiringSmoke:
    """Build StrategyOptions via _parse_strategies and verify deterministic fields."""

    def _build_json(self, strategies: list[dict]) -> str:
        return json.dumps({"strategies": strategies})

    def _make_strategy_json(
        self, rank: int = 1, compound: str = "RM",
        laps: int = 10, ref_lap_ms: int = 90_000,
    ) -> dict:
        return {
            "rank": rank,
            "name": f"Strategy {rank}",
            "stints": [{"compound": compound, "laps": laps,
                         "ref_lap_ms": ref_lap_ms, "pace_threshold_ms": 2500}],
            "estimated_time_s": 900.0,
            "pit_time_s": 0.0,
            "summary": "test",
            "risks": "none",
            "positives": "",
            "negatives": "",
            "tyre_risk": "low",
            "fuel_risk": "low",
            "traffic_risk": "low",
            "undercut_risk": "low",
            "confidence_score": 0.8,
            "why_label": "test label",
            "estimated_speed_rank": rank,
        }

    def test_deterministic_fields_populated_when_params_given(self):
        """deterministic_time_s, delta_vs_fastest_s, rank_by_time, outcome_confidence
        are populated when params is passed to _parse_strategies."""
        raw = self._build_json([
            self._make_strategy_json(rank=1, compound="RS", laps=10, ref_lap_ms=88_000),
            self._make_strategy_json(rank=2, compound="RH", laps=10, ref_lap_ms=96_000),
        ])
        params = _make_params(total_laps=10, pit_loss_secs=0.0,
                              fuel_burn_per_lap=3.0, refuel_speed_lps=1.0)
        result = ap._parse_strategies(raw, params=params, degradation=None)
        # All options should have deterministic_time_s > 0
        for opt in result.strategies:
            assert opt.deterministic_time_s > 0.0, (
                f"{opt.name}.deterministic_time_s should be > 0"
            )
        # Fastest should have delta 0.0
        fastest = min(result.strategies, key=lambda o: o.deterministic_time_s)
        assert fastest.delta_vs_fastest_s == pytest.approx(0.0)
        # rank_by_time assigned
        ranks = [o.rank_by_time for o in result.strategies]
        assert 1 in ranks

    def test_deterministic_fields_default_when_no_params(self):
        """When params is None (old call style), deterministic fields stay at safe defaults."""
        raw = self._build_json([self._make_strategy_json(rank=1)])
        result = ap._parse_strategies(raw)
        opt = result.strategies[0]
        assert opt.deterministic_time_s == 0.0
        assert opt.delta_vs_fastest_s == 0.0
        assert opt.outcome_confidence == ""
        assert opt.rank_by_time == 0

    def test_stints_shape_unchanged(self):
        """stints dicts still contain exactly {compound, laps, ref_lap_ms, pace_threshold_ms}."""
        stints_json = [
            {"compound": "RS", "laps": 10, "ref_lap_ms": 88_000, "pace_threshold_ms": 2000},
            {"compound": "RH", "laps": 15, "ref_lap_ms": 94_000, "pace_threshold_ms": 3000},
        ]
        raw = json.dumps({
            "strategies": [{
                "rank": 1,
                "name": "1-Stop RS/RH",
                "stints": stints_json,
                "estimated_time_s": 2400.0,
                "pit_time_s": 45.0,
                "summary": "test",
                "risks": "none",
            }]
        })
        params = _make_params(total_laps=25, pit_loss_secs=20.0,
                              fuel_burn_per_lap=3.0, refuel_speed_lps=1.0)
        result = ap._parse_strategies(raw, params=params, degradation=None)
        opt = result.strategies[0]
        assert len(opt.stints) == 2
        for s in opt.stints:
            assert "compound" in s
            assert "laps" in s
            assert "ref_lap_ms" in s
            assert "pace_threshold_ms" in s

    def test_existing_fields_not_overwritten(self):
        """estimated_time_s (AI-supplied) and other fields are not changed."""
        raw = self._build_json([self._make_strategy_json(rank=1)])
        params = _make_params()
        result = ap._parse_strategies(raw, params=params, degradation=None)
        opt = result.strategies[0]
        # AI-supplied estimated_time_s must remain 900.0 (from fixture)
        assert opt.estimated_time_s == pytest.approx(900.0)
        # deterministic_time_s is DIFFERENT (computed separately)
        # (they may coincidentally be equal in some cases, but both should be > 0)
        assert opt.deterministic_time_s > 0.0

    def test_single_option_via_parse_strategies(self):
        """Single option: rank_by_time=1, delta=0."""
        raw = self._build_json([self._make_strategy_json(rank=1)])
        params = _make_params()
        result = ap._parse_strategies(raw, params=params, degradation=None)
        opt = result.strategies[0]
        assert opt.rank_by_time == 1
        assert opt.delta_vs_fastest_s == pytest.approx(0.0)

    def test_two_options_delta_correct(self):
        """Slower option has delta_vs_fastest_s > 0."""
        raw = self._build_json([
            self._make_strategy_json(rank=1, compound="RS", laps=10, ref_lap_ms=88_000),
            self._make_strategy_json(rank=2, compound="RH", laps=10, ref_lap_ms=96_000),
        ])
        params = _make_params(total_laps=10, pit_loss_secs=0.0,
                              fuel_burn_per_lap=3.0, refuel_speed_lps=1.0)
        result = ap._parse_strategies(raw, params=params, degradation=None)
        opts = result.strategies
        # The 88s/lap option is faster
        fast = next(o for o in opts if "RS" in [s["compound"] for s in o.stints])
        slow = next(o for o in opts if "RH" in [s["compound"] for s in o.stints])
        assert fast.delta_vs_fastest_s == pytest.approx(0.0)
        assert slow.delta_vs_fastest_s > 0.0

    def test_wiring_does_not_break_with_empty_degradation(self):
        """degradation={} does not raise; confidence fields are set to 'low'."""
        raw = self._build_json([self._make_strategy_json(rank=1)])
        params = _make_params()
        result = ap._parse_strategies(raw, params=params, degradation={})
        opt = result.strategies[0]
        assert opt.outcome_confidence == "low"


# ---------------------------------------------------------------------------
# Guard test: StrategyOption.stints dict key contract
# ---------------------------------------------------------------------------

class TestStintsShapeContract:
    """Regression guard: stints dicts must always carry the four required keys."""

    REQUIRED_KEYS = {"compound", "laps", "ref_lap_ms", "pace_threshold_ms"}

    def test_stints_keys_after_construction(self):
        """Direct StrategyOption construction preserves stints shape."""
        stints = [
            {"compound": "RS", "laps": 10, "ref_lap_ms": 88_000, "pace_threshold_ms": 2000},
        ]
        opt = _make_option(stints)
        for s in opt.stints:
            assert self.REQUIRED_KEYS <= s.keys(), (
                f"stints dict missing keys: {self.REQUIRED_KEYS - s.keys()}"
            )

    def test_stints_keys_after_parse_strategies(self):
        """stints dict keys are unchanged after _parse_strategies wiring call."""
        raw = json.dumps({
            "strategies": [{
                "rank": 1,
                "name": "Test",
                "stints": [
                    {"compound": "RM", "laps": 20, "ref_lap_ms": 91_000, "pace_threshold_ms": 2500},
                ],
                "estimated_time_s": 1820.0,
                "pit_time_s": 0.0,
                "summary": "",
                "risks": "",
            }]
        })
        params = _make_params(total_laps=20)
        result = ap._parse_strategies(raw, params=params, degradation=None)
        for opt in result.strategies:
            for s in opt.stints:
                assert self.REQUIRED_KEYS <= s.keys(), (
                    f"stints dict missing required keys: {self.REQUIRED_KEYS - s.keys()}"
                )

    def test_new_dataclass_fields_have_safe_defaults(self):
        """New deterministic fields have safe defaults when StrategyOption is constructed
        without them — old callers are not broken."""
        opt = StrategyOption(
            rank=1,
            name="Legacy",
            stints=[],
            estimated_time_s=100.0,
            pit_time_s=0.0,
            summary="",
            risks="",
        )
        assert opt.deterministic_time_s == 0.0
        assert opt.delta_vs_fastest_s == 0.0
        assert opt.outcome_confidence == ""
        assert opt.rank_by_time == 0

    def test_stints_field_not_rewritten_by_wiring(self):
        """Wiring must not replace or reshape the stints list; it must only add
        the four deterministic scalar fields to the StrategyOption."""
        original_stints = [
            {"compound": "RM", "laps": 15, "ref_lap_ms": 92_000, "pace_threshold_ms": 2500},
            {"compound": "RH", "laps": 15, "ref_lap_ms": 95_000, "pace_threshold_ms": 3000},
        ]
        raw = json.dumps({
            "strategies": [{
                "rank": 1,
                "name": "1-Stop",
                "stints": original_stints,
                "estimated_time_s": 2850.0,
                "pit_time_s": 65.0,
                "summary": "test",
                "risks": "none",
            }]
        })
        params = _make_params(total_laps=30, pit_loss_secs=20.0,
                              fuel_burn_per_lap=3.0, refuel_speed_lps=1.0)
        result = ap._parse_strategies(raw, params=params, degradation=None)
        opt = result.strategies[0]
        # Stints list identity is preserved
        assert len(opt.stints) == 2
        assert opt.stints[0]["compound"] == "RM"
        assert opt.stints[1]["compound"] == "RH"
        assert opt.stints[0]["ref_lap_ms"] == 92_000
        # Original AI-supplied fields are untouched
        assert opt.estimated_time_s == pytest.approx(2850.0)
        assert opt.pit_time_s == pytest.approx(65.0)
