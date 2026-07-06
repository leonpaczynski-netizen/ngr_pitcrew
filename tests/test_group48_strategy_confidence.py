"""Group 48 — Race Strategy Brain Phase 2: evidence-gated confidence tests.

Covers the StrategyConfidence gating in strategy/race_strategy_evidence.py:
  HIGH / MEDIUM / LOW / INSUFFICIENT_EVIDENCE transitions as evidence degrades.

The app must be honest: better data → higher confidence; missing critical data
→ INSUFFICIENT_EVIDENCE; soft gaps (no long-run, unstable weather, poor
consistency) step confidence down rather than inventing certainty.

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


def _ev(**over):
    """Fully-evidenced HIGH-confidence baseline; override to degrade it."""
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
        lap_time_samples=[100.0, 100.1, 99.9, 100.05, 100.0, 100.1, 99.95, 100.05],
        fuel_use_samples=[4.0, 4.0, 4.1, 3.9],
        tyre_wear_samples=[0.08] * 10,       # long-run present
        compound_samples={"RM": [100.0], "RH": [101.5]},
    )
    kw.update(over)
    return build_strategy_evidence(**kw)


class TestConfidenceOrdering:
    def test_rank_ordering(self):
        assert StrategyConfidence.INSUFFICIENT_EVIDENCE.rank < StrategyConfidence.LOW.rank
        assert StrategyConfidence.LOW.rank < StrategyConfidence.MEDIUM.rank
        assert StrategyConfidence.MEDIUM.rank < StrategyConfidence.HIGH.rank

    def test_worst_picks_lowest(self):
        assert StrategyConfidence.worst(
            StrategyConfidence.HIGH, StrategyConfidence.LOW
        ) == StrategyConfidence.LOW
        assert StrategyConfidence.worst() == StrategyConfidence.INSUFFICIENT_EVIDENCE


class TestGrading:
    def test_full_evidence_is_high(self):
        assert _ev().evidence_confidence == StrategyConfidence.HIGH

    def test_no_lap_data_is_insufficient(self):
        assert _ev(lap_time_samples=[]).evidence_confidence == StrategyConfidence.INSUFFICIENT_EVIDENCE

    def test_no_fuel_data_is_insufficient(self):
        assert _ev(fuel_use_samples=[]).evidence_confidence == StrategyConfidence.INSUFFICIENT_EVIDENCE

    def test_missing_refuel_is_low(self):
        assert _ev(refuel_rate_lps=0.0).evidence_confidence == StrategyConfidence.LOW

    def test_missing_pit_loss_is_low(self):
        assert _ev(pit_loss_seconds=0.0).evidence_confidence == StrategyConfidence.LOW

    def test_no_long_run_steps_down_to_medium(self):
        ev = _ev(tyre_wear_samples=[0.08, 0.09, 0.1])  # short sample
        assert ev.evidence_confidence == StrategyConfidence.MEDIUM

    def test_unstable_weather_steps_down_to_medium(self):
        assert _ev(weather_context="random").evidence_confidence == StrategyConfidence.MEDIUM

    def test_two_soft_gaps_step_down_to_low(self):
        # no long-run AND unstable weather → two soft gaps → LOW
        ev = _ev(tyre_wear_samples=[0.08, 0.09], weather_context="random")
        assert ev.evidence_confidence == StrategyConfidence.LOW

    def test_poor_consistency_steps_down(self):
        ev = _ev(lap_time_samples=[95.0, 105.0, 92.0, 108.0, 96.0, 104.0])
        assert ev.evidence_confidence.rank <= StrategyConfidence.MEDIUM.rank


class TestHonesty:
    def test_confidence_never_high_when_core_data_missing(self):
        for over in (
            {"refuel_rate_lps": 0.0},
            {"pit_loss_seconds": 0.0},
            {"lap_time_samples": []},
            {"fuel_use_samples": []},
        ):
            assert _ev(**over).evidence_confidence != StrategyConfidence.HIGH


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
