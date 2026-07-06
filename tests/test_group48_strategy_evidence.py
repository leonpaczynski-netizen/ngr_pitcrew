"""Group 48 — Race Strategy Brain Phase 2: strategy evidence model tests.

Covers strategy/race_strategy_evidence.py:
  • building evidence from available event/session fields
  • honest recording of missing fuel / tyre / pit-loss / refuel evidence
  • confidence gating driven by evidence coverage
  • NO invented metrics (unknown fields stay at their sentinel, flagged missing)

All tests are pure/offline — no DB, no Qt, no network.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.race_strategy_evidence import (  # noqa: E402
    RaceStrategyEvidence,
    StrategyConfidence,
    build_strategy_evidence,
    compute_consistency,
    evidence_from_race_params,
    MISSING_FUEL_SAMPLES,
    MISSING_TYRE_WEAR_SAMPLES,
    MISSING_LONG_RUN_DATA,
    MISSING_PIT_LOSS,
    MISSING_REFUEL_RATE,
    MISSING_LAP_SAMPLES,
    MISSING_COMPOUND_DATA,
    POOR_DRIVER_CONSISTENCY,
    UNSTABLE_WEATHER,
    GT7_TANK_CAPACITY_L,
)


# Well-populated evidence used as a baseline in several tests.
def _full_evidence(**over):
    kw = dict(
        car_id=911,
        track="Fuji Speedway",
        layout_id="fuji__full",
        race_laps=20,
        fuel_multiplier=3.0,
        tyre_multiplier=8.0,
        refuel_rate_lps=1.0,
        pit_loss_seconds=22.0,
        available_compounds=("RM", "RH"),
        required_compounds=("RM",),
        mandatory_pit_stops=1,
        weather_context="dry_stable",
        lap_time_samples=[100.0, 100.2, 99.9, 100.1, 100.3, 100.0, 100.2, 100.1],
        fuel_use_samples=[4.0, 4.1, 3.9, 4.0],
        tyre_wear_samples=[0.08] * 10,
        compound_samples={"RM": [100.0, 100.2], "RH": [101.5, 101.6]},
    )
    kw.update(over)
    return build_strategy_evidence(**kw)


class TestBuild:
    def test_builds_from_available_fields(self):
        ev = _full_evidence()
        assert isinstance(ev, RaceStrategyEvidence)
        assert ev.car_id == 911
        assert ev.track == "Fuji Speedway"
        assert ev.race_laps == 20
        assert ev.refuel_rate_lps == 1.0
        assert ev.pit_loss_seconds == 22.0
        assert ev.fuel_capacity_basis == GT7_TANK_CAPACITY_L

    def test_never_raises_on_garbage(self):
        ev = build_strategy_evidence(
            car_id="nope", lap_time_samples=[None, "x", -3], fuel_use_samples=None
        )
        assert isinstance(ev, RaceStrategyEvidence)
        assert ev.evidence_confidence == StrategyConfidence.INSUFFICIENT_EVIDENCE

    def test_legality_fields_carried_through(self):
        ev = _full_evidence()
        assert ev.available_compounds == ("RM", "RH")
        assert ev.required_compounds == ("RM",)
        assert ev.mandatory_pit_stops == 1


class TestMissingEvidence:
    def test_missing_fuel_recorded(self):
        ev = _full_evidence(fuel_use_samples=[])
        assert MISSING_FUEL_SAMPLES in ev.missing_evidence

    def test_missing_tyre_recorded(self):
        ev = _full_evidence(tyre_wear_samples=[])
        assert MISSING_TYRE_WEAR_SAMPLES in ev.missing_evidence

    def test_short_tyre_run_flags_no_long_run(self):
        ev = _full_evidence(tyre_wear_samples=[0.08, 0.09, 0.1])  # < MIN_LONG_RUN_LAPS
        assert MISSING_LONG_RUN_DATA in ev.missing_evidence
        assert MISSING_TYRE_WEAR_SAMPLES not in ev.missing_evidence

    def test_missing_pit_loss_recorded_and_reduces_confidence(self):
        ev = _full_evidence(pit_loss_seconds=0.0)
        assert MISSING_PIT_LOSS in ev.missing_evidence
        # pit maths weakened → no better than LOW
        assert ev.evidence_confidence.rank <= StrategyConfidence.LOW.rank

    def test_missing_refuel_recorded_and_reduces_confidence(self):
        ev = _full_evidence(refuel_rate_lps=0.0)
        assert MISSING_REFUEL_RATE in ev.missing_evidence
        assert ev.evidence_confidence.rank <= StrategyConfidence.LOW.rank

    def test_missing_lap_samples_recorded(self):
        ev = _full_evidence(lap_time_samples=[100.0])  # < MIN_LAP_SAMPLES
        assert MISSING_LAP_SAMPLES in ev.missing_evidence

    def test_missing_compound_data_recorded(self):
        ev = _full_evidence(compound_samples={})
        assert MISSING_COMPOUND_DATA in ev.missing_evidence

    def test_unstable_weather_recorded(self):
        ev = _full_evidence(weather_context="random")
        assert UNSTABLE_WEATHER in ev.missing_evidence

    def test_poor_consistency_recorded(self):
        # Wide lap-time spread → poor coefficient of variation.
        ev = _full_evidence(lap_time_samples=[95.0, 105.0, 92.0, 108.0, 96.0, 104.0])
        assert POOR_DRIVER_CONSISTENCY in ev.missing_evidence

    def test_missing_evidence_text_is_human_readable(self):
        ev = _full_evidence(fuel_use_samples=[])
        texts = ev.missing_evidence_text()
        assert any("fuel" in t.lower() for t in texts)


class TestRefuelIncluded:
    def test_refuel_rate_included_when_available(self):
        ev = _full_evidence(refuel_rate_lps=1.5)
        assert ev.refuel_rate_lps == 1.5
        assert MISSING_REFUEL_RATE not in ev.missing_evidence


class TestNoInvention:
    def test_unknown_numeric_fields_stay_zero(self):
        ev = build_strategy_evidence(
            track="X",
            lap_time_samples=[100.0, 100.1, 100.2],
            fuel_use_samples=[4.0],
        )
        # Nothing supplied for these → must be the sentinel 0.0, not a guess.
        assert ev.refuel_rate_lps == 0.0
        assert ev.pit_loss_seconds == 0.0
        assert ev.tyre_multiplier == 0.0
        assert ev.fuel_multiplier == 0.0

    def test_compound_pace_absent_returns_zero_not_guess(self):
        ev = _full_evidence(compound_samples={})
        assert ev.compound_pace_s("RM") == 0.0

    def test_representative_lap_zero_without_data(self):
        ev = build_strategy_evidence(track="X")
        assert ev.representative_lap_s() == 0.0


class TestDerived:
    def test_representative_lap_is_median_not_min(self):
        ev = _full_evidence(lap_time_samples=[90.0, 100.0, 100.0, 100.0, 100.0])
        # Median ~100, not the 90 flyer.
        assert ev.representative_lap_s() == 100.0

    def test_consistency_lower_is_better(self):
        tight = compute_consistency([100.0, 100.1, 99.9, 100.05])
        loose = compute_consistency([90.0, 110.0, 95.0, 105.0])
        assert tight < loose

    def test_consistency_unknown_with_one_sample(self):
        assert compute_consistency([100.0]) == 0.0


class TestFromRaceParams:
    def test_adapts_race_params(self):
        from strategy.ai_planner import RaceParams

        params = RaceParams(
            track="Fuji Speedway",
            total_laps=15,
            tyre_wear_multiplier=8.0,
            fuel_burn_per_lap=4.0,
            refuel_speed_lps=1.0,
            pit_loss_secs=22.0,
            min_mandatory_stops=1,
            mandatory_compounds=["RM"],
            avail_tyres=["RM", "RH"],
        )
        ev = evidence_from_race_params(
            params,
            lap_time_samples=[100.0, 100.1, 100.2],
        )
        assert ev.track == "Fuji Speedway"
        assert ev.race_laps == 15
        assert ev.tyre_multiplier == 8.0
        assert ev.refuel_rate_lps == 1.0
        assert ev.required_compounds == ("RM",)
        # fuel_burn_per_lap seeds a single fuel sample when none supplied
        assert ev.mean_fuel_per_lap() == 4.0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
