"""Group 48 — Race Strategy Brain Phase 2: Porsche RSR / Fuji benchmark tests.

Proves the strategy brain optimises the RACE, not the hot lap, on the fixed
scenario in strategy/race_strategy_benchmark.py:

    Porsche 911 RSR '17 · Fuji Full Course · ~50 min · 8× tyre · 3× fuel · 1 L/s refuel

Expected behaviour:
  • produces a LEGAL race strategy
  • carries the fuel + tyre multipliers and the 1 L/s refuel rate
  • ranks by TOTAL race time (a one-stop beats a two-stop here)
  • protects rear traction (push plan flagged, never recommended)
  • explanation is clear and driver-readable

All tests are pure/offline.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.race_strategy_benchmark import (  # noqa: E402
    run_benchmark,
    build_benchmark_evidence,
    BENCHMARK_TYRE_MULT,
    BENCHMARK_FUEL_MULT,
    BENCHMARK_REFUEL_LPS,
)
from strategy.race_strategy_candidates import Legality  # noqa: E402
from strategy.race_strategy_evidence import StrategyConfidence  # noqa: E402


@pytest.fixture(scope="module")
def result():
    return run_benchmark()


class TestScenarioInputs:
    def test_evidence_carries_multipliers_and_refuel(self, result):
        ev = result.evidence
        assert ev.tyre_multiplier == BENCHMARK_TYRE_MULT == 8.0
        assert ev.fuel_multiplier == BENCHMARK_FUEL_MULT == 3.0
        assert ev.refuel_rate_lps == BENCHMARK_REFUEL_LPS == 1.0

    def test_timed_race_estimates_laps(self, result):
        # 50 min at ~100 s/lap → about 30 laps (estimated from the race pace).
        cand = result.recommendation.candidates[0]
        assert sum(cand.estimated_laps_per_stint) >= 25


class TestLegalRecommendation:
    def test_produces_a_legal_recommendation(self, result):
        rec = result.recommendation
        assert rec.has_recommendation
        # The recommended id must correspond to a LEGAL candidate.
        rec_cand = next(c for c in rec.candidates if c.candidate_id == rec.recommended.candidate_id)
        assert rec_cand.legality_status == Legality.LEGAL

    def test_confidence_is_reported(self, result):
        assert result.recommendation.confidence in set(StrategyConfidence)
        # Full evidence in this scenario → HIGH.
        assert result.recommendation.confidence == StrategyConfidence.HIGH


class TestTotalRaceTimeNotHotLap:
    def test_one_stop_beats_two_stop_on_total_time(self, result):
        by_id = {s.candidate_id: s for s in result.recommendation.ranked}
        assert "1stop" in by_id and "2stop" in by_id
        one = by_id["1stop"].estimated_total_time_seconds
        two = by_id["2stop"].estimated_total_time_seconds
        assert one < two, "expensive refuel should make the extra stop slower overall"

    def test_recommended_is_a_one_stop(self, result):
        assert result.recommendation.recommended.candidate_id.startswith("1stop")

    def test_pit_and_refuel_time_included(self, result):
        best = result.recommendation.recommended
        assert best.pit_time_total_seconds > 0
        assert best.refuel_time_total_seconds > 0

    def test_degradation_cost_present(self, result):
        # 8× wear with long-run data → a non-zero degradation cost.
        best = result.recommendation.recommended
        assert best.degradation_cost_seconds > 0


class TestRearTractionProtection:
    def test_rear_flag_derived_true(self, result):
        assert result.rear_traction_fragile is True

    def test_push_plan_is_flagged_and_not_recommended(self, result):
        ranked = {s.candidate_id: s for s in result.recommendation.ranked}
        assert "2stop_push" in ranked
        push = ranked["2stop_push"]
        joined = " ".join(push.risk_flags).lower()
        assert "rear" in joined
        assert result.recommendation.recommended.candidate_id != "2stop_push"


class TestDriverReadableExplanation:
    def test_explanation_has_all_sections(self, result):
        text = result.explanation.to_text()
        assert "Recommended Strategy" in text
        assert "Why" in text
        assert "Confidence" in text
        assert "Known evidence" in text
        assert "Calculated estimate" in text

    def test_explanation_mentions_fuel_tyre_pit_refuel(self, result):
        text = result.explanation.to_text().lower()
        assert "fuel" in text
        assert "tyre" in text
        assert "pit" in text
        assert "refuel" in text

    def test_explanation_is_not_overhyped(self, result):
        text = result.explanation.to_text().lower()
        for banned in ("perfect strategy", "guaranteed", "the winning strategy"):
            assert banned not in text


class TestDeterminism:
    def test_repeatable(self):
        a = run_benchmark()
        b = run_benchmark()
        ta = [s.estimated_total_time_seconds for s in a.recommendation.ranked]
        tb = [s.estimated_total_time_seconds for s in b.recommendation.ranked]
        assert ta == tb
        assert a.recommendation.recommended.candidate_id == b.recommendation.recommended.candidate_id


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
