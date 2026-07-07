"""Group 52 — Porsche RSR / Fuji UAT verification harness tests.

Covers `run_fuji_race_plan_uat_check` in ui/race_strategy_uat.py: a structured,
deterministic, offline check of the whole Race Plan surface.

All tests are pure/offline (SQLite `:memory:`).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.race_strategy_uat import (  # noqa: E402
    run_fuji_race_plan_uat_check,
    FujiUatCheckResult,
)


@pytest.fixture(scope="module")
def check():
    return run_fuji_race_plan_uat_check()


class TestFullScenario:
    def test_runs_offline_and_passes(self, check):
        assert isinstance(check, FujiUatCheckResult)
        assert check.passed
        assert check.failure_reasons == []

    def test_event_and_session_validated(self, check):
        assert check.event_context_ok
        assert check.session_match_ok

    def test_readiness_and_evidence(self, check):
        assert check.readiness_level == "READY"
        assert check.clean_lap_count == 12
        assert check.fuel_evidence_found
        assert check.tyre_proxy_found

    def test_one_vs_two_stop_comparison(self, check):
        assert check.one_stop_total_time == "51:52.0"
        assert check.two_stop_total_time == "52:28.0"
        assert check.candidate_count >= 2

    def test_recommended_is_one_stop(self, check):
        assert "one-stop" in check.recommended_strategy.lower()

    def test_push_not_recommended(self, check):
        assert check.push_plan_rejected_or_not_recommended

    def test_safety_checks_pass(self, check):
        assert all(check.safety_checks.values())

    def test_no_false_certainty_in_safety(self, check):
        assert check.safety_checks["no_apply_setup_wording"]
        assert check.safety_checks["read_only_safety_note"]
        assert check.safety_checks["no_setup_field_tokens"]


class TestIncompleteScenario:
    def test_incomplete_session_still_passes_harness_but_flags_missing(self):
        # 4 laps, no fuel → INSUFFICIENT_EVIDENCE result, but the surface behaves
        # correctly (harness passes: no crash, missing evidence visible).
        c = run_fuji_race_plan_uat_check(n_laps=4, fuel=0.0)
        assert c.passed  # the surface handled it honestly
        assert c.readiness_level == "INSUFFICIENT_EVIDENCE"
        assert c.missing_evidence  # remains visible

    def test_missing_evidence_visible(self):
        c = run_fuji_race_plan_uat_check(n_laps=4, fuel=0.0)
        joined = " ".join(c.missing_evidence).lower()
        assert "fuel" in joined


class TestDeterminism:
    def test_repeatable(self):
        a = run_fuji_race_plan_uat_check()
        b = run_fuji_race_plan_uat_check()
        assert a.passed == b.passed
        assert a.one_stop_total_time == b.one_stop_total_time
        assert a.recommended_strategy == b.recommended_strategy


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
