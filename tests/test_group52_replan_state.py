"""Group 52 — replan current-race-state model + validation tests.

Covers strategy/race_strategy_replan.py: RaceReplanState, validate_replan_state,
assess_replan_readiness. Pure/offline; never crashes; never invents; unknown tyre
state is never treated as safe.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.race_strategy_replan import (  # noqa: E402
    RaceReplanState,
    validate_replan_state,
    assess_replan_readiness,
    ReplanReadinessLevel,
)


def _full_state(**over):
    kw = dict(current_lap=10, elapsed_time_seconds=1000.0, remaining_laps=20,
              remaining_time_seconds=2000.0, fuel_remaining_pct=60.0,
              current_compound="RM", tyre_age_laps=10, pit_stops_completed=0,
              required_compounds_used=(), weather_status="dry", damage_status="none",
              safety_car_status="green")
    kw.update(over)
    return RaceReplanState(**kw)


class TestReadiness:
    def test_full_state_ready(self):
        assert assess_replan_readiness(_full_state()).level == ReplanReadinessLevel.READY

    def test_partial_when_lap_or_stops_unknown(self):
        r = assess_replan_readiness(_full_state(current_lap=None))
        assert r.level == ReplanReadinessLevel.PARTIAL

    def test_low_confidence_when_tyre_unknown(self):
        r = assess_replan_readiness(_full_state(tyre_age_laps=None))
        assert r.level == ReplanReadinessLevel.LOW_CONFIDENCE
        assert any("tyre" in a.lower() for a in r.assumptions)

    def test_insufficient_when_no_fuel(self):
        r = assess_replan_readiness(_full_state(fuel_remaining_pct=None))
        assert r.level == ReplanReadinessLevel.INSUFFICIENT_EVIDENCE

    def test_insufficient_when_no_compound(self):
        assert assess_replan_readiness(_full_state(current_compound=None)).level \
            == ReplanReadinessLevel.INSUFFICIENT_EVIDENCE

    def test_insufficient_when_no_distance(self):
        r = assess_replan_readiness(_full_state(remaining_laps=None, remaining_time_seconds=None))
        assert r.level == ReplanReadinessLevel.INSUFFICIENT_EVIDENCE

    def test_distance_from_time_alone_is_enough(self):
        r = assess_replan_readiness(_full_state(remaining_laps=None))
        assert r.level in (ReplanReadinessLevel.READY, ReplanReadinessLevel.PARTIAL)


class TestValidation:
    def test_full_state_can_snapshot(self):
        v = validate_replan_state(_full_state())
        assert v.can_snapshot
        assert v.missing_state == [] or "tyre_age_laps" not in v.missing_state

    def test_missing_fuel_flagged(self):
        v = validate_replan_state(_full_state(fuel_remaining_pct=None))
        assert "fuel_remaining_pct" in v.missing_state
        assert not v.can_snapshot
        assert any("fuel remaining missing" in w.lower() for w in v.warnings)

    def test_missing_compound_flagged(self):
        v = validate_replan_state(_full_state(current_compound=None))
        assert "current_compound" in v.missing_state
        assert any("compound missing" in w.lower() for w in v.warnings)

    def test_missing_distance_flagged(self):
        v = validate_replan_state(_full_state(remaining_laps=None, remaining_time_seconds=None))
        assert "remaining_distance" in v.missing_state
        assert any("remaining race distance" in w.lower() for w in v.warnings)

    def test_unknown_tyre_is_not_treated_as_safe(self):
        v = validate_replan_state(_full_state(tyre_age_laps=None))
        assert "tyre_age_laps" in v.missing_state
        assert any("not assumed safe" in w.lower() for w in v.warnings)

    def test_required_compound_status_preserved(self):
        st = _full_state(required_compounds_used=("RM",))
        assert st.required_compounds_used == ("RM",)


class TestNoCrashNoInvent:
    def test_invalid_lap_does_not_crash(self):
        st = RaceReplanState(current_lap=-5, fuel_remaining_pct=50.0,
                             current_compound="RM", remaining_laps=10)
        v = validate_replan_state(st)
        assert v.field_status["current_lap"] == "MISSING"  # negative = unknown

    def test_empty_state_is_insufficient(self):
        assert assess_replan_readiness(RaceReplanState()).level \
            == ReplanReadinessLevel.INSUFFICIENT_EVIDENCE

    def test_no_fake_state_created(self):
        st = RaceReplanState()
        assert st.fuel_remaining_pct is None
        assert st.current_compound is None
        assert st.tyre_age_laps is None
        assert not st.has_fuel()
        assert not st.has_tyre_age()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
