"""Group 50 — Race Strategy Brain Phase 4: Porsche RSR / Fuji surface tests.

Proves the driver-facing Race Plan surface, built from the Group 49 SessionDB
benchmark, behaves correctly offline for:

    Porsche 911 RSR '17 · Fuji Full Course · ~50 min · 8× tyre · 3× fuel · 1 L/s refuel

Expected:
  • surface builds offline (no AI / API key)
  • one-stop vs two-stop total-time comparison visible
  • SessionDB evidence source appears when session samples exist
  • missing evidence appears when samples are incomplete
  • rear-fragile push plan is not recommended
  • no setup Apply action appears

All tests are pure/offline (SQLite `:memory:`).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.session_db import SessionDB  # noqa: E402
from strategy.race_strategy_session_benchmark import (  # noqa: E402
    run_session_benchmark,
    build_benchmark_db,
    BENCHMARK_TYRE_MULT,
    BENCHMARK_FUEL_MULT,
    BENCHMARK_REFUEL_LPS,
)
from ui.race_strategy_vm import (  # noqa: E402
    build_race_plan_view_model,
    run_race_plan_from_session,
    render_race_plan_html,
)


@pytest.fixture(scope="module")
def vm():
    return build_race_plan_view_model(run_session_benchmark().result)


class TestBuildsOffline:
    def test_surface_builds_offline(self, vm):
        assert vm.has_recommendation
        assert vm.recommended_strategy_title == "One-stop race plan"

    def test_multipliers_and_refuel_are_the_scenario(self):
        b = run_session_benchmark()
        ev = b.result.evidence
        assert ev.tyre_multiplier == BENCHMARK_TYRE_MULT == 8.0
        assert ev.fuel_multiplier == BENCHMARK_FUEL_MULT == 3.0
        assert ev.refuel_rate_lps == BENCHMARK_REFUEL_LPS == 1.0


class TestComparison:
    def test_one_vs_two_stop_visible(self, vm):
        by_id = {r["candidate_id"]: r for r in vm.candidate_comparison_rows}
        assert "1stop" in by_id and "2stop" in by_id
        assert by_id["1stop"]["gap_to_best"] == "best"
        assert by_id["2stop"]["gap_to_best"].startswith("+")

    def test_total_time_displayed(self, vm):
        assert vm.estimated_total_time == "51:52.0"


class TestEvidence:
    def test_sessiondb_source_appears(self, vm):
        html = render_race_plan_html(vm)
        assert "SessionDB measured" in html
        assert any(r["category"] == "measured" for r in vm.evidence_source_rows)

    def test_derived_tyre_labelled(self, vm):
        cats = {r["label"]: r["category"] for r in vm.evidence_source_rows}
        assert cats["Tyre degradation"] == "derived"

    def test_missing_evidence_when_incomplete(self):
        # Seed a short session (no fuel signal) → missing evidence must appear.
        db, _ = build_benchmark_db()
        sid = db.open_session(car_id=911, track="Fuji Speedway",
                              session_type="Practice", car_name="RSR")
        for i in range(4):
            db.write_lap(session_id=sid, lap_num=i + 1, lap_time_ms=100000 + i * 80,
                         fuel_used=0.0, stats=None, compound="RM")
        vm = run_race_plan_from_session(
            db, session_id=sid, car_id=911, track="Fuji Speedway",
            race_duration_minutes=50.0, fuel_multiplier=3.0, tyre_multiplier=8.0,
            refuel_rate_lps=1.0, pit_loss_seconds=22.0,
            available_compounds=("RM", "RH"),
        )
        assert vm.missing_evidence_rows
        assert vm.confidence_label != "High"


class TestRearProtectionAndSafety:
    def test_push_not_recommended(self, vm):
        assert vm.recommended_strategy_title != "Push two-stop race plan"
        joined = " ".join(vm.risk_flags).lower()
        assert "push strategy not recommended" in joined

    def test_no_setup_apply_action(self, vm):
        html = render_race_plan_html(vm).lower()
        assert "apply setup" not in html
        assert "approve setup" not in html
        # safety note states read-only
        assert any("read-only" in n.lower() for n in vm.safety_notes)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
