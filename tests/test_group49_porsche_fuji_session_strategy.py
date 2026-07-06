"""Group 49 — Race Strategy Brain Phase 3: Porsche RSR / Fuji SessionDB benchmark.

Proves the end-to-end SessionDB pathway offline via
strategy/race_strategy_session_benchmark.py:

    Porsche 911 RSR '17 · Fuji Full Course · ~50 min · 8× tyre · 3× fuel · 1 L/s refuel

Expected behaviour:
  • SessionDB samples are read and used to build evidence
  • one-stop and two-stop are compared by TOTAL race time (one-stop wins here)
  • pit loss + refuel time included; degradation from measured lap-drift proxy
  • confidence reflects evidence; missing data listed honestly
  • explanation says what came from SessionDB
  • the fragile push plan is flagged and never recommended
  • no AI, no external services, no runtime files

All tests are pure/offline (SQLite `:memory:`).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.race_strategy_session_benchmark import (  # noqa: E402
    run_session_benchmark,
    build_benchmark_db,
    seed_benchmark_session,
    BENCHMARK_TYRE_MULT,
    BENCHMARK_FUEL_MULT,
    BENCHMARK_REFUEL_LPS,
)
from strategy.race_strategy_candidates import Legality  # noqa: E402
from strategy.race_strategy_evidence import StrategyConfidence  # noqa: E402


@pytest.fixture(scope="module")
def bench():
    return run_session_benchmark()


class TestSessionBacked:
    def test_samples_read_from_sessiondb(self, bench):
        s = bench.result.samples
        assert s.clean_lap_count >= 10
        assert len(s.fuel_samples) >= 8
        assert s.tyre_wear_derived
        assert "RM" in s.compound_samples

    def test_evidence_carries_multipliers_and_refuel(self, bench):
        ev = bench.result.evidence
        assert ev.tyre_multiplier == BENCHMARK_TYRE_MULT == 8.0
        assert ev.fuel_multiplier == BENCHMARK_FUEL_MULT == 3.0
        assert ev.refuel_rate_lps == BENCHMARK_REFUEL_LPS == 1.0

    def test_confidence_reflects_evidence(self, bench):
        assert bench.result.confidence == StrategyConfidence.HIGH


class TestTotalRaceTime:
    def test_one_stop_beats_two_stop(self, bench):
        by_id = {s.candidate_id: s for s in bench.result.scored_candidates}
        assert "1stop" in by_id and "2stop" in by_id
        assert (by_id["1stop"].estimated_total_time_seconds
                < by_id["2stop"].estimated_total_time_seconds)

    def test_recommended_is_one_stop(self, bench):
        assert bench.result.recommendation.recommended.candidate_id.startswith("1stop")

    def test_pit_and_refuel_and_degradation_present(self, bench):
        best = bench.result.recommendation.recommended
        assert best.pit_time_total_seconds > 0
        assert best.refuel_time_total_seconds > 0
        assert best.degradation_cost_seconds > 0

    def test_recommendation_is_legal(self, bench):
        rec_id = bench.result.recommendation.recommended.candidate_id
        cand = next(c for c in bench.result.candidates if c.candidate_id == rec_id)
        assert cand.legality_status == Legality.LEGAL


class TestRearProtection:
    def test_rear_flag_true(self, bench):
        assert bench.rear_traction_fragile is True

    def test_push_flagged_and_not_recommended(self, bench):
        by_id = {s.candidate_id: s for s in bench.result.scored_candidates}
        assert "2stop_push" in by_id
        assert any("rear" in f.lower() for f in by_id["2stop_push"].risk_flags)
        assert bench.result.recommendation.recommended.candidate_id != "2stop_push"


class TestExplanation:
    def test_explanation_says_sessiondb(self, bench):
        text = bench.result.explanation.to_text()
        assert "Evidence source" in text
        assert "SessionDB measured" in text
        assert "SessionDB derived" in text  # tyre proxy

    def test_explanation_names_fuel_tyre_pit_refuel(self, bench):
        text = bench.result.explanation.to_text().lower()
        for term in ("fuel", "tyre", "pit", "refuel"):
            assert term in text

    def test_explanation_not_overhyped(self, bench):
        text = bench.result.explanation.to_text().lower()
        for banned in ("perfect strategy", "guaranteed", "the winning strategy"):
            assert banned not in text


class TestOfflineDeterminism:
    def test_no_ai_dependency_and_repeatable(self):
        a = run_session_benchmark()
        b = run_session_benchmark()
        ta = [s.estimated_total_time_seconds for s in a.result.scored_candidates]
        tb = [s.estimated_total_time_seconds for s in b.result.scored_candidates]
        assert ta == tb
        assert (a.result.recommendation.recommended.candidate_id
                == b.result.recommendation.recommended.candidate_id)

    def test_seed_helper_reusable_on_shared_db(self):
        db, sid = build_benchmark_db()
        sid2 = seed_benchmark_session(db)  # a second session in the same DB
        assert sid2 != sid
        # Reading the first session is unaffected by the second.
        from strategy.race_strategy_session_adapter import extract_session_strategy_samples
        s1 = extract_session_strategy_samples(db, sid, expected_car_id=911)
        assert s1.clean_lap_count >= 10


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
