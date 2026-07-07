"""Group 52 — read-only replan snapshot tests.

Covers `build_replan_snapshot`: advisory-only assessment of whether the pre-race
plan still holds against the reported live state. Never applies anything; missing
state stays visible; honest confidence; INSUFFICIENT_EVIDENCE when critical state
or the pre-race plan is missing.

All tests are pure/offline (SQLite `:memory:`).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.race_strategy_uat import run_fuji_uat  # noqa: E402
from strategy.race_strategy_replan import (  # noqa: E402
    RaceReplanState,
    build_replan_snapshot,
    render_replan_snapshot_text,
    RaceReplanReason,
    ReplanConfidence,
    REPLAN_SAFETY_NOTES,
)


@pytest.fixture(scope="module")
def pre_race():
    # One-stop plan over ~30 laps (pit ~lap 15).
    return run_fuji_uat()


def _state(**over):
    kw = dict(current_lap=10, fuel_remaining_pct=60.0, current_compound="RM",
              tyre_age_laps=10, pit_stops_completed=0, remaining_laps=20)
    kw.update(over)
    return RaceReplanState(**kw)


class TestViable:
    def test_plan_still_viable(self, pre_race):
        snap = build_replan_snapshot(pre_race_result=pre_race, state=_state())
        assert snap.current_plan_still_viable is True
        assert snap.reason == RaceReplanReason.VIABLE
        assert "still viable" in snap.driver_message.lower()

    def test_confidence_medium_with_tyre_known(self, pre_race):
        snap = build_replan_snapshot(pre_race_result=pre_race, state=_state())
        assert snap.confidence == ReplanConfidence.MEDIUM

    def test_options_are_pre_race_estimates(self, pre_race):
        snap = build_replan_snapshot(pre_race_result=pre_race, state=_state())
        assert snap.remaining_strategy_options
        joined = " ".join(o.estimated_delta for o in snap.remaining_strategy_options)
        assert "pre-race estimate" in joined or "reference" in joined


class TestNeedsReview:
    def test_fuel_below_expected_needs_review(self, pre_race):
        # 8% of a 100 L tank = 8 L; next stop is ~5 laps at ~4 L/lap = 20 L needed.
        snap = build_replan_snapshot(pre_race_result=pre_race, state=_state(fuel_remaining_pct=8.0))
        assert snap.current_plan_still_viable is False
        assert snap.reason == RaceReplanReason.FUEL_LOW
        assert "needs review" in snap.driver_message.lower()
        assert snap.remaining_strategy_options  # advisory alternatives shown


class TestInsufficient:
    def test_missing_critical_state(self, pre_race):
        snap = build_replan_snapshot(pre_race_result=pre_race,
                                     state=_state(fuel_remaining_pct=None))
        assert snap.current_plan_still_viable is None
        assert snap.reason == RaceReplanReason.INSUFFICIENT_STATE
        assert snap.confidence == ReplanConfidence.INSUFFICIENT_EVIDENCE
        assert snap.missing_state

    def test_low_confidence_when_tyre_unknown(self, pre_race):
        snap = build_replan_snapshot(pre_race_result=pre_race,
                                     state=_state(tyre_age_laps=None))
        # Still viable on fuel, but tyre unknown → LOW confidence.
        assert snap.confidence == ReplanConfidence.LOW

    def test_no_pre_race_plan(self):
        # A no-session result has no recommendation → PLAN_MISSING.
        from data.session_db import SessionDB
        from strategy.race_strategy_pipeline import recommend_strategy_from_session
        db = SessionDB(":memory:")
        result = recommend_strategy_from_session(db, session_id=999, car_id=911,
                                                 track="Fuji Speedway", race_duration_minutes=50.0,
                                                 fuel_multiplier=3.0, tyre_multiplier=8.0,
                                                 refuel_rate_lps=1.0, pit_loss_seconds=22.0,
                                                 available_compounds=("RM", "RH"))
        snap = build_replan_snapshot(pre_race_result=result, state=_state())
        assert snap.reason == RaceReplanReason.PLAN_MISSING
        assert snap.current_plan_still_viable is None


class TestAdvisoryOnly:
    def test_safety_notes_say_no_action(self, pre_race):
        snap = build_replan_snapshot(pre_race_result=pre_race, state=_state())
        assert snap.safety_notes == REPLAN_SAFETY_NOTES
        joined = " ".join(snap.safety_notes).lower()
        assert "no pit call" in joined
        assert "applies nothing" in joined or "changes nothing" in joined

    def test_missing_state_visible_in_text(self, pre_race):
        snap = build_replan_snapshot(pre_race_result=pre_race,
                                     state=_state(fuel_remaining_pct=None))
        text = render_replan_snapshot_text(snap)
        assert "Missing:" in text
        assert "Advisory only" in text

    def test_latest_fuel_samples_used_when_supplied(self, pre_race):
        # Supplying a higher live burn rate shrinks the viable margin honestly.
        snap = build_replan_snapshot(pre_race_result=pre_race, state=_state(fuel_remaining_pct=25.0),
                                     latest_fuel_samples=[4.0, 4.1, 3.9])
        assert snap.reason in (RaceReplanReason.VIABLE, RaceReplanReason.FUEL_LOW)


class TestNoSetupSurface:
    def test_snapshot_has_no_setup_tokens(self, pre_race):
        snap = build_replan_snapshot(pre_race_result=pre_race, state=_state())
        blob = (snap.driver_message + " " + snap.original_plan_status + " "
                + " ".join(o.label for o in snap.remaining_strategy_options)).lower()
        for tok in ("ride_height", "camber", "lsd_accel", "brake_bias",
                    "approved_fields", "setup_fields", "apply setup"):
            assert tok not in blob


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
