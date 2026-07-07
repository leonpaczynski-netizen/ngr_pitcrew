"""Group 54 — Porsche RSR / Fuji pit-state fixture tests.

Extends the offline live-replan fixtures with pit/tyre-age cases:
    pre-pit healthy · just pitted · missing pit state · suspicious pit signal.
Advisory only; no pit command; no setup Apply.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.race_strategy_uat import run_fuji_uat, run_fuji_live_replan, FUJI_UAT_EVENT_SETTINGS  # noqa: E402
from strategy.race_strategy_replan import ReplanConfidence  # noqa: E402
from strategy.race_strategy_live_replan import render_live_replan_text  # noqa: E402
from telemetry.pit_state import (  # noqa: E402
    PitStintState, PitEvent, PitDetectionConfidence,
    start_stint_tracking, apply_pit_event,
)


class TestScenario:
    def test_values_represented(self):
        es = FUJI_UAT_EVENT_SETTINGS
        assert es["race_duration_minutes"] == 50.0
        assert es["tyre_multiplier"] == 8.0
        assert es["fuel_multiplier"] == 3.0
        assert es["refuel_rate_lps"] == 1.0

    def test_pre_race_plan_is_one_stop(self):
        assert run_fuji_uat().recommendation.recommended.candidate_id == "1stop"


class TestPrePitHealthy:
    def test_runs_offline_viable_above_low(self):
        r = run_fuji_live_replan("pre_pit_healthy")
        assert r.snapshot.current_plan_still_viable is True
        assert r.confidence == ReplanConfidence.MEDIUM   # tyre age + pit count known
        text = render_live_replan_text(r)
        assert "laps since pit: 12" in text
        assert "pit stops completed: 0" in text


class TestJustPitted:
    def test_runs_offline_pit_count_and_fresh_tyres(self):
        r = run_fuji_live_replan("just_pitted")
        assert r.state.pit_stops_completed == 1
        assert r.state.tyre_age_laps == 1
        assert r.snapshot.current_plan_still_viable is True   # advisory, still viable


class TestMissingPitState:
    def test_missing_pit_state_low_confidence(self):
        r = run_fuji_live_replan("missing_pit")
        assert r.confidence == ReplanConfidence.LOW
        assert "tyre_age_laps" in r.missing_state or any(
            "tyre" in m.lower() for m in r.missing_state)


class TestSuspiciousPitSignal:
    def test_suspicious_signal_not_counted(self):
        # A suspicious/no-event signal must not increment the pit count.
        s = start_stint_tracking(PitStintState())
        r = apply_pit_event(s, pit_lap=5, confidence=PitDetectionConfidence.LOW,
                            source="single low-speed moment", event=PitEvent.NONE)
        assert r.counted is False
        assert r.state.pit_stops_completed == 0


class TestSafety:
    def test_advisory_only_no_pit_command(self):
        r = run_fuji_live_replan("pre_pit_healthy")
        joined = " ".join(r.safety_notes).lower()
        assert "no pit call" in joined
        text = render_live_replan_text(r).lower()
        assert "box box" not in text
        assert "pit now" not in text

    def test_no_setup_apply_action(self):
        text = render_live_replan_text(run_fuji_live_replan("just_pitted")).lower()
        assert "apply setup" not in text
        assert "approve setup" not in text

    def test_one_stop_plan_remains_advisory(self):
        r = run_fuji_live_replan("pre_pit_healthy")
        assert "advisory only" in " ".join(r.safety_notes).lower()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
