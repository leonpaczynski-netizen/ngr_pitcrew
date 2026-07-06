"""Group 48 — Race Strategy Brain Phase 2: candidate generation tests.

Covers strategy/race_strategy_candidates.py:
  • no-stop generated only when fuel-legal / feasible
  • one-stop and two-stop generated for race-length events
  • mandatory pit-stop and mandatory-compound rules respected (illegal excluded)
  • candidate IDs stable and deterministic
  • pure fuel/pit maths, no invented telemetry

All tests are pure/offline.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.race_strategy_evidence import build_strategy_evidence  # noqa: E402
from strategy.race_strategy_candidates import (  # noqa: E402
    Legality,
    RiskLevel,
    StrategyCandidate,
    generate_candidates,
    legal_candidates,
    FUEL_MAP_SAVE,
    FUEL_MAP_PUSH,
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
        lap_time_samples=[100.0, 100.1, 100.2, 100.0, 100.1, 100.2, 100.0, 100.1],
        fuel_use_samples=[4.0, 4.0, 4.1, 3.9],
        tyre_wear_samples=[0.08] * 10,
        compound_samples={"RM": [100.0], "RH": [101.5]},
    )
    kw.update(over)
    return build_strategy_evidence(**kw)


def _ids(cands):
    return [c.candidate_id for c in cands]


class TestGeneration:
    def test_returns_candidates_for_race_length_event(self):
        cands = generate_candidates(_ev())
        assert cands
        assert all(isinstance(c, StrategyCandidate) for c in cands)

    def test_one_and_two_stop_generated(self):
        ids = _ids(generate_candidates(_ev()))
        assert "1stop" in ids
        assert "2stop" in ids

    def test_no_race_length_returns_empty(self):
        ev = build_strategy_evidence(track="X", race_laps=0, race_duration_minutes=0.0,
                                     lap_time_samples=[100, 100, 100], fuel_use_samples=[4.0])
        assert generate_candidates(ev) == []

    def test_ids_are_stable_and_deterministic(self):
        a = _ids(generate_candidates(_ev()))
        b = _ids(generate_candidates(_ev()))
        assert a == b
        # No duplicate IDs.
        assert len(a) == len(set(a))

    def test_laps_per_stint_sum_to_race_laps(self):
        for c in generate_candidates(_ev(race_laps=21)):
            assert sum(c.estimated_laps_per_stint) == 21


class TestNoStopFeasibility:
    def test_nostop_illegal_when_fuel_limited(self):
        # 20 laps * 5 L/lap = 100 L exactly? use 6 L/lap → 120 L > tank → illegal.
        ev = _ev(fuel_use_samples=[6.0, 6.0, 6.0])
        cands = generate_candidates(ev)
        nostop = next(c for c in cands if c.candidate_id == "nostop")
        assert nostop.legality_status == Legality.ILLEGAL
        assert nostop not in legal_candidates(cands)

    def test_nostop_legal_when_fuel_fits(self):
        # 20 laps * 2 L/lap = 40 L < tank → no-stop is fuel-legal.
        ev = _ev(fuel_use_samples=[2.0, 2.0, 2.0])
        cands = generate_candidates(ev)
        nostop = next(c for c in cands if c.candidate_id == "nostop")
        assert nostop.legality_status == Legality.LEGAL


class TestMandatoryStops:
    def test_below_mandatory_stops_is_illegal(self):
        ev = _ev(mandatory_pit_stops=1)
        cands = generate_candidates(ev)
        nostop = next(c for c in cands if c.candidate_id == "nostop")
        assert nostop.legality_status == Legality.ILLEGAL
        assert "nostop" not in _ids(legal_candidates(cands))

    def test_at_or_above_mandatory_is_legal(self):
        ev = _ev(mandatory_pit_stops=1)
        onestop = next(c for c in generate_candidates(ev) if c.candidate_id == "1stop")
        assert onestop.legality_status == Legality.LEGAL


class TestMandatoryCompounds:
    def test_required_compound_woven_into_plan(self):
        ev = _ev(required_compounds=("RH",))
        onestop = next(c for c in generate_candidates(ev) if c.candidate_id == "1stop")
        assert "RH" in onestop.compound_plan
        assert onestop.legality_status == Legality.LEGAL

    def test_two_required_compounds_need_enough_stints(self):
        # Two distinct required compounds cannot fit in a single-stint no-stop.
        ev = _ev(required_compounds=("RM", "RH"))
        cands = generate_candidates(ev)
        nostop = next(c for c in cands if c.candidate_id == "nostop")
        assert nostop.legality_status == Legality.ILLEGAL
        # A one-stop (2 stints) CAN fit both.
        onestop = next(c for c in cands if c.candidate_id == "1stop")
        assert set(("RM", "RH")).issubset(set(onestop.compound_plan))
        assert onestop.legality_status == Legality.LEGAL


class TestVariants:
    def test_fuelsave_and_push_and_switch_present(self):
        ids = _ids(generate_candidates(_ev()))
        assert "1stop_fuelsave" in ids
        assert "2stop_push" in ids
        assert "1stop_compound_switch" in ids

    def test_fuelsave_uses_save_map_and_less_fuel(self):
        cands = generate_candidates(_ev())
        base = next(c for c in cands if c.candidate_id == "1stop")
        save = next(c for c in cands if c.candidate_id == "1stop_fuelsave")
        assert FUEL_MAP_SAVE in save.fuel_map_plan
        assert save.estimated_fuel_needed < base.estimated_fuel_needed

    def test_push_uses_push_map_and_high_risk(self):
        push = next(c for c in generate_candidates(_ev()) if c.candidate_id == "2stop_push")
        assert FUEL_MAP_PUSH in push.fuel_map_plan
        assert push.risk_level == RiskLevel.HIGH

    def test_compound_switch_uses_two_compounds(self):
        switch = next(c for c in generate_candidates(_ev())
                      if c.candidate_id == "1stop_compound_switch")
        assert len(set(switch.compound_plan)) >= 2


class TestNoInvention:
    def test_fuel_fields_zero_when_fuel_unknown(self):
        ev = _ev(fuel_use_samples=[])
        onestop = next(c for c in generate_candidates(ev) if c.candidate_id == "1stop")
        assert onestop.estimated_fuel_needed == 0.0
        assert onestop.estimated_refuel_time == 0.0

    def test_refuel_time_zero_when_refuel_unknown(self):
        ev = _ev(refuel_rate_lps=0.0)
        onestop = next(c for c in generate_candidates(ev) if c.candidate_id == "1stop")
        assert onestop.estimated_refuel_time == 0.0
        # Pit-lane loss still counts when known.
        assert onestop.estimated_pit_time == 22.0

    def test_pit_time_includes_loss_and_refuel(self):
        ev = _ev()  # 20 laps, 1 stop → 2 stints of 10, second stint 10*4=40 L / 1 L/s = 40s
        onestop = next(c for c in generate_candidates(ev) if c.candidate_id == "1stop")
        assert onestop.estimated_pit_time == pytest.approx(22.0 + 40.0)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
