"""Group 53 — live replan snapshot runner tests.

Covers strategy/race_strategy_live_replan.py: combines the pre-race Race Plan +
a live current-state source into a read-only, advisory-only LiveReplanResult.

All tests are pure/offline (SQLite `:memory:` for the pre-race plan).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.race_strategy_uat import run_fuji_uat  # noqa: E402
from strategy.race_strategy_replan import RaceReplanState, ReplanConfidence, RaceReplanReason  # noqa: E402
from strategy.race_strategy_live_replan import (  # noqa: E402
    LiveReplanResult,
    build_live_replan_snapshot,
    render_live_replan_text,
    fuji_live_state_healthy,
    fuji_live_state_fuel_short,
    fuji_live_state_missing,
)


@pytest.fixture(scope="module")
def pre_race():
    return run_fuji_uat()


class TestHealthy:
    def test_plan_still_viable(self, pre_race):
        r = build_live_replan_snapshot(pre_race_result=pre_race, live_state=fuji_live_state_healthy())
        assert isinstance(r, LiveReplanResult)
        assert r.snapshot.current_plan_still_viable is True
        assert r.status == "Current plan still viable"

    def test_confidence_medium_with_tyre_known(self, pre_race):
        r = build_live_replan_snapshot(pre_race_result=pre_race, live_state=fuji_live_state_healthy())
        assert r.confidence == ReplanConfidence.MEDIUM


class TestFuelShort:
    def test_plan_needs_review(self, pre_race):
        r = build_live_replan_snapshot(pre_race_result=pre_race, live_state=fuji_live_state_fuel_short())
        assert r.snapshot.current_plan_still_viable is False
        assert r.snapshot.reason == RaceReplanReason.FUEL_LOW
        assert "needs review" in r.driver_message.lower()

    def test_advisory_options_present(self, pre_race):
        r = build_live_replan_snapshot(pre_race_result=pre_race, live_state=fuji_live_state_fuel_short())
        assert r.snapshot.remaining_strategy_options
        joined = " ".join(o.estimated_delta for o in r.snapshot.remaining_strategy_options)
        assert "pre-race estimate" in joined or "reference" in joined


class TestInsufficient:
    def test_missing_fuel_and_distance_insufficient(self, pre_race):
        r = build_live_replan_snapshot(pre_race_result=pre_race, live_state=fuji_live_state_missing())
        assert r.snapshot.current_plan_still_viable is None
        assert r.confidence == ReplanConfidence.INSUFFICIENT_EVIDENCE
        assert r.missing_state

    def test_missing_fuel_alone_insufficient(self, pre_race):
        st = RaceReplanState(current_lap=12, current_compound="RM", remaining_laps=18)
        r = build_live_replan_snapshot(pre_race_result=pre_race, live_state=st)
        assert r.confidence == ReplanConfidence.INSUFFICIENT_EVIDENCE

    def test_missing_distance_insufficient(self, pre_race):
        st = RaceReplanState(current_lap=12, fuel_remaining_pct=60.0, current_compound="RM")
        r = build_live_replan_snapshot(pre_race_result=pre_race, live_state=st)
        assert r.confidence == ReplanConfidence.INSUFFICIENT_EVIDENCE


class TestTyreConfidenceCap:
    def test_unknown_tyre_age_caps_confidence_low(self, pre_race):
        st = RaceReplanState(current_lap=12, fuel_remaining_pct=60.0, current_compound="RM",
                             remaining_laps=18, pit_stops_completed=0)  # tyre_age None
        r = build_live_replan_snapshot(pre_race_result=pre_race, live_state=st)
        assert r.confidence == ReplanConfidence.LOW


class TestVisibilityAndSafety:
    def test_missing_state_visible(self, pre_race):
        r = build_live_replan_snapshot(pre_race_result=pre_race, live_state=fuji_live_state_missing())
        text = render_live_replan_text(r)
        assert "Missing:" in text

    def test_safety_note_says_no_action(self, pre_race):
        r = build_live_replan_snapshot(pre_race_result=pre_race, live_state=fuji_live_state_healthy())
        joined = " ".join(r.safety_notes).lower()
        assert "no pit call" in joined
        assert "applies nothing" in joined or "changes nothing" in joined

    def test_no_setup_recommendation_created(self, pre_race):
        r = build_live_replan_snapshot(pre_race_result=pre_race, live_state=fuji_live_state_healthy())
        blob = (r.driver_message + " " + render_live_replan_text(r)).lower()
        for tok in ("ride_height", "camber", "lsd_accel", "apply setup", "approve setup",
                    "approved_fields", "setup_fields"):
            assert tok not in blob

    def test_generated_at_passthrough(self, pre_race):
        r = build_live_replan_snapshot(pre_race_result=pre_race, live_state=fuji_live_state_healthy(),
                                       generated_at="12:34:56")
        assert r.generated_at == "12:34:56"


class TestLiveSourcePath:
    def test_from_tracker_with_packet(self, pre_race):
        class T:
            laps_recorded = 12
            laps_remaining = 0
            _current_compound = "RM"
            avg_fuel_per_lap = 4.0
            timed_duration_minutes = 50.0
            def computed_remaining_ms(self):
                return 1800000

        class D:
            _tracker = T()
            class _P:
                fuel_level = 60.0
                fuel_capacity = 100.0
            _last_packet = _P()

        r = build_live_replan_snapshot(pre_race_result=pre_race, live_source=D())
        # tyre unknown → LOW; fuel viable → still-viable.
        assert r.snapshot.current_plan_still_viable is True
        assert r.confidence == ReplanConfidence.LOW


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
