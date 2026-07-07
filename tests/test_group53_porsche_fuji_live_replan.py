"""Group 53 — Porsche RSR / Fuji live-replan fixture tests.

Proves the offline live-replan path for the scenario:
    Porsche 911 RSR '17 · Fuji Full Course · 50 min · 8× tyre · 3× fuel · 1 L/s ·
    original plan = one-stop

All tests are pure/offline (SQLite `:memory:`).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.race_strategy_uat import run_fuji_uat, run_fuji_live_replan, FUJI_UAT_EVENT_SETTINGS  # noqa: E402
from strategy.race_strategy_replan import ReplanConfidence  # noqa: E402


class TestScenario:
    def test_scenario_values_represented(self):
        es = FUJI_UAT_EVENT_SETTINGS
        assert es["race_duration_minutes"] == 50.0
        assert es["tyre_multiplier"] == 8.0
        assert es["fuel_multiplier"] == 3.0
        assert es["refuel_rate_lps"] == 1.0

    def test_pre_race_plan_is_one_stop(self):
        assert run_fuji_uat().recommendation.recommended.candidate_id == "1stop"


class TestHealthyState:
    def test_one_stop_remains_viable(self):
        r = run_fuji_live_replan("healthy")
        assert r.snapshot.current_plan_still_viable is True
        assert r.status == "Current plan still viable"

    def test_runs_offline(self):
        r = run_fuji_live_replan("healthy", generated_at="10:00:00")
        assert r.generated_at == "10:00:00"


class TestFuelShortState:
    def test_plan_needs_review(self):
        r = run_fuji_live_replan("fuel_short")
        assert r.snapshot.current_plan_still_viable is False
        assert "needs review" in r.driver_message.lower()


class TestMissingState:
    def test_insufficient_evidence(self):
        r = run_fuji_live_replan("missing")
        assert r.confidence == ReplanConfidence.INSUFFICIENT_EVIDENCE
        assert r.missing_state


class TestSafety:
    def test_push_plan_not_promoted(self):
        # The live snapshot only surfaces pre-race options; the rear-fragile push is
        # never the recommended pre-race plan, so it is never promoted here either.
        r = run_fuji_live_replan("fuel_short")
        opt_labels = " ".join(o.label for o in r.snapshot.remaining_strategy_options).lower()
        # Options are advisory alternatives, not a "recommended" push.
        assert "push" not in r.status.lower()
        assert run_fuji_uat().recommendation.recommended.candidate_id != "2stop_push"

    def test_advisory_only(self):
        r = run_fuji_live_replan("healthy")
        joined = " ".join(r.safety_notes).lower()
        assert "no pit call" in joined

    def test_no_setup_apply_action_in_text(self):
        from strategy.race_strategy_live_replan import render_live_replan_text
        text = render_live_replan_text(run_fuji_live_replan("healthy")).lower()
        assert "apply setup" not in text
        assert "approve setup" not in text


class TestDeterminism:
    def test_repeatable(self):
        a = run_fuji_live_replan("healthy")
        b = run_fuji_live_replan("healthy")
        assert a.status == b.status
        assert a.confidence == b.confidence


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
