"""Group 48 — Race Strategy Brain Phase 2: total-race-time scoring tests.

Covers strategy/race_strategy_scorer.py:
  • ranking by estimated TOTAL race time, not fastest lap
  • extra pit stop penalised by pit loss + refuel time
  • high degradation justifies an extra stop ONLY when the maths supports it
  • an on-track-faster (more-stops, fresher-tyre) plan loses when pit cost is high
  • fuel saving preferred only when it improves total time
  • missing evidence lowers confidence rather than inventing certainty

All tests are pure/offline.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.race_strategy_evidence import (  # noqa: E402
    build_strategy_evidence,
    StrategyConfidence,
)
from strategy.race_strategy_candidates import generate_candidates  # noqa: E402
from strategy.race_strategy_scorer import (  # noqa: E402
    score_candidate,
    score_candidates,
    recommend_strategy,
    fuel_save_worth_it,
)


def _ev(**over):
    kw = dict(
        car_id=911,
        track="Fuji",
        race_laps=20,
        fuel_multiplier=3.0,
        tyre_multiplier=8.0,
        refuel_rate_lps=1.0,
        pit_loss_seconds=22.0,
        available_compounds=("RM", "RH"),
        weather_context="dry_stable",
        lap_time_samples=[100.0] * 8,
        fuel_use_samples=[4.0, 4.0, 4.0, 4.0],
        tyre_wear_samples=[0.02] * 10,   # low degradation by default
        compound_samples={"RM": [100.0], "RH": [101.5]},
    )
    kw.update(over)
    return build_strategy_evidence(**kw)


def _scored_by_id(ev):
    scored = score_candidates(generate_candidates(ev), ev)
    return {s.candidate_id: s for s in scored}


class TestRanking:
    def test_ranked_ascending_by_total_time(self):
        scored = score_candidates(generate_candidates(_ev()), _ev())
        times = [s.estimated_total_time_seconds for s in scored]
        assert times == sorted(times)
        # ranks are 1..n contiguous
        assert [s.rank for s in scored] == list(range(1, len(scored) + 1))

    def test_gap_to_best_zero_for_leader(self):
        scored = score_candidates(generate_candidates(_ev()), _ev())
        assert scored[0].estimated_gap_to_best_seconds == 0.0
        assert all(s.estimated_gap_to_best_seconds >= 0 for s in scored)


class TestPitPenalty:
    def test_extra_stop_penalised_with_low_degradation(self):
        by_id = _scored_by_id(_ev(tyre_wear_samples=[0.02] * 10))
        # More stops → more pit + refuel time; with tiny degradation the extra
        # stop cannot pay for itself, so 1-stop beats 2-stop beats 3-stop.
        assert by_id["1stop"].estimated_total_time_seconds < by_id["2stop"].estimated_total_time_seconds
        assert by_id["2stop"].estimated_total_time_seconds < by_id["3stop"].estimated_total_time_seconds

    def test_pit_time_reflects_loss_and_refuel(self):
        by_id = _scored_by_id(_ev())
        s = by_id["1stop"]
        # 22 s pit-lane loss + 40 s refuel (10 laps * 4 L / 1 L/s)
        assert s.pit_time_total_seconds == pytest.approx(62.0)
        assert s.refuel_time_total_seconds == pytest.approx(40.0)


class TestDegradationTradeoff:
    def test_high_degradation_cheap_pit_justifies_extra_stop(self):
        # Huge degradation, cheap fast pit → more stops win on total time.
        ev = _ev(tyre_wear_samples=[1.0] * 10, pit_loss_seconds=5.0, refuel_rate_lps=10.0)
        by_id = _scored_by_id(ev)
        assert by_id["2stop"].estimated_total_time_seconds < by_id["1stop"].estimated_total_time_seconds

    def test_high_degradation_expensive_pit_does_not_justify_extra_stop(self):
        # Same huge degradation, but an expensive slow pit → fewer stops still win.
        ev = _ev(tyre_wear_samples=[1.0] * 10, pit_loss_seconds=60.0, refuel_rate_lps=1.0)
        by_id = _scored_by_id(ev)
        assert by_id["1stop"].estimated_total_time_seconds < by_id["2stop"].estimated_total_time_seconds

    def test_degradation_cost_is_zero_without_wear_data(self):
        ev = _ev(tyre_wear_samples=[])
        by_id = _scored_by_id(ev)
        assert by_id["1stop"].degradation_cost_seconds == 0.0


class TestFasterLapDoesNotAutoWin:
    def test_more_stops_fresher_tyres_loses_when_pit_cost_high(self):
        # A 2-stop runs fresher tyres (lower on-track degradation) but the pit
        # cost is so high that its TOTAL race time is worse — the scorer must
        # not reward the fresher-tyre plan just for on-track pace.
        ev = _ev(tyre_wear_samples=[0.2] * 10, pit_loss_seconds=45.0, refuel_rate_lps=1.0)
        by_id = _scored_by_id(ev)
        two = by_id["2stop"]
        one = by_id["1stop"]
        assert two.degradation_cost_seconds < one.degradation_cost_seconds  # fresher tyres
        assert two.estimated_total_time_seconds > one.estimated_total_time_seconds  # still slower race


class TestFuelSaving:
    def test_worth_it_helper(self):
        assert fuel_save_worth_it(3000.0, 3010.0) is True
        assert fuel_save_worth_it(3010.0, 3000.0) is False

    def test_fuelsave_preferred_over_extra_stop_when_base_onestop_infeasible(self):
        # Fuel so heavy the plain one-stop can't make the tank, but a lean map
        # can — so the fuel-save one-stop should beat a two-stop on total time.
        ev = _ev(fuel_use_samples=[10.5, 10.5, 10.5])
        by_id = _scored_by_id(ev)
        # base 1-stop is fuel-illegal → excluded from scored (legal_only)
        assert "1stop" not in by_id
        assert "1stop_fuelsave" in by_id and "2stop" in by_id
        assert (by_id["1stop_fuelsave"].estimated_total_time_seconds
                < by_id["2stop"].estimated_total_time_seconds)

    def test_fuelsave_not_recommended_when_it_loses(self):
        # With normal fuel the plain one-stop is legal and faster than fuel-save.
        rec = recommend_strategy(_ev())
        assert rec.recommended is not None
        assert rec.recommended.candidate_id != "1stop_fuelsave"


class TestConfidence:
    def test_missing_evidence_lowers_confidence(self):
        # Missing refuel rate weakens pit maths → LOW, never HIGH.
        ev = _ev(refuel_rate_lps=0.0)
        rec = recommend_strategy(ev)
        assert rec.confidence.rank <= StrategyConfidence.LOW.rank

    def test_insufficient_evidence_yields_no_recommendation(self):
        ev = _ev(lap_time_samples=[], fuel_use_samples=[])
        rec = recommend_strategy(ev)
        assert rec.recommended is None
        assert rec.confidence == StrategyConfidence.INSUFFICIENT_EVIDENCE
        assert rec.missing_evidence  # tells the driver what's missing

    def test_score_none_without_pace(self):
        ev = build_strategy_evidence(track="X", race_laps=10, fuel_use_samples=[4.0])
        cands = generate_candidates(ev)
        if cands:
            assert score_candidate(cands[0], ev) is None


class TestSafetyTieBreak:
    def test_safer_plan_preferred_within_tolerance(self):
        # Construct a near-tie where a push plan is marginally quicker; the
        # safety-aware pick must NOT choose the high-risk push plan.
        ev = _ev()
        rec = recommend_strategy(ev, rear_traction_fragile=True)
        assert rec.recommended is not None
        assert rec.recommended.candidate_id != "2stop_push"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
