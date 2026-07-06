"""Group 51 — Porsche RSR / Fuji manual-UAT support path tests.

Proves the offline UAT helper (`build_fuji_uat_context`) supports:

    Porsche 911 RSR '17 · Fuji Full Course · 50 min · 8× tyre · 3× fuel · 1 L/s refuel

Confirms readiness builds offline, the scenario values are represented, one-stop vs
two-stop comparison appears, SessionDB measured evidence appears with mock samples,
missing evidence appears when samples are incomplete, the rear-fragile push plan is
not recommended, and no setup Apply action exists.

All tests are pure/offline (SQLite `:memory:`).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.race_strategy_uat import (  # noqa: E402
    build_fuji_uat_context,
    FUJI_UAT_EVENT_SETTINGS,
    run_fuji_uat,
)
from ui.race_strategy_readiness_vm import ReadinessLevel, CheckStatus
from ui.race_strategy_vm import build_race_plan_view_model, render_race_plan_html


class TestOfflineReadiness:
    def test_context_builds_offline(self):
        ctx = build_fuji_uat_context()
        assert ctx.readiness.overall_readiness == ReadinessLevel.READY
        assert ctx.diagnostics.matches_event == CheckStatus.OK

    def test_scenario_values_represented(self):
        es = FUJI_UAT_EVENT_SETTINGS
        assert es["tyre_multiplier"] == 8.0
        assert es["fuel_multiplier"] == 3.0
        assert es["refuel_rate_lps"] == 1.0
        assert es["race_duration_minutes"] == 50.0

    def test_readiness_found_lists_sessiondb_evidence(self):
        ctx = build_fuji_uat_context()
        joined = " ".join(ctx.readiness.found).lower()
        assert "clean laps from sessiondb" in joined
        assert "derived lap-drift proxy" in joined


class TestComparisonAndEvidence:
    def test_one_vs_two_stop_comparison_appears(self):
        vm = build_race_plan_view_model(run_fuji_uat())
        by_id = {r["candidate_id"]: r for r in vm.candidate_comparison_rows}
        assert "1stop" in by_id and "2stop" in by_id
        assert by_id["1stop"]["gap_to_best"] == "best"
        assert by_id["2stop"]["gap_to_best"].startswith("+")

    def test_sessiondb_measured_evidence_appears(self):
        vm = build_race_plan_view_model(run_fuji_uat())
        html = render_race_plan_html(vm)
        assert "SessionDB measured" in html

    def test_missing_evidence_appears_when_incomplete(self):
        # Incomplete: only 4 laps, no fuel → readiness must flag missing evidence.
        ctx = build_fuji_uat_context(n_laps=4, fuel=0.0)
        assert ctx.readiness.overall_readiness != ReadinessLevel.READY
        assert ctx.readiness.missing
        assert ctx.empty_state_messages


class TestRearProtectionAndSafety:
    def test_push_not_recommended(self):
        vm = build_race_plan_view_model(run_fuji_uat())
        assert vm.recommended_strategy_title != "Push two-stop race plan"
        assert any("push strategy not recommended" in r.lower() for r in vm.risk_flags)

    def test_no_setup_apply_action(self):
        vm = build_race_plan_view_model(run_fuji_uat())
        html = render_race_plan_html(vm).lower()
        assert "apply setup" not in html
        assert "approve setup" not in html
        assert any("read-only" in n.lower() for n in vm.safety_notes)


class TestDeterminism:
    def test_repeatable(self):
        a = build_fuji_uat_context()
        b = build_fuji_uat_context()
        assert a.readiness.overall_readiness == b.readiness.overall_readiness
        assert a.diagnostics.clean_lap_count == b.diagnostics.clean_lap_count


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
