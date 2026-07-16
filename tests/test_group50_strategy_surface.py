"""Group 50 — Race Strategy Brain Phase 4: strategy surface / action tests.

Covers the driver-facing action layer:
  • the runner calls the session-backed pipeline when session data exists
  • it falls back safely (lower confidence) when session data is missing
  • it produces a driver-readable explanation and honest missing evidence
  • the Qt surface method requires no API key, exposes no Apply/approve control,
    writes no setup history, and creates no setup recommendation (source-verified)

The runner tests are pure (SQLite `:memory:`); the Qt method is verified by source
inspection so no QApplication is constructed (avoids the Win/Py3.14 PyQt segfault).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.session_db import SessionDB  # noqa: E402
from ui.race_strategy_vm import (  # noqa: E402
    RacePlanViewModel,
    run_race_plan_from_session,
    run_race_plan_from_event_context,
)


def _seed(db, *, n=12, fuel=4.0):
    sid = db.open_session(car_id=911, track="Fuji Speedway", session_type="Practice", car_name="RSR")
    remaining = 100.0
    for i in range(n):
        db.write_lap(session_id=sid, lap_num=i + 1, lap_time_ms=100000 + i * 80,
                     fuel_used=fuel, stats=None, compound="RM",
                     fuel_start=remaining, fuel_end=remaining - fuel)
        remaining -= fuel
    return sid


def _kwargs(**over):
    kw = dict(
        car_id=911, track="Fuji Speedway", layout_id="fuji__full",
        race_duration_minutes=50.0, fuel_multiplier=3.0, tyre_multiplier=8.0,
        refuel_rate_lps=1.0, pit_loss_seconds=22.0,
        available_compounds=("RM", "RH"), rear_traction_fragile=True,
    )
    kw.update(over)
    return kw


@pytest.fixture()
def db():
    yield SessionDB(":memory:")


class TestSessionBackedAction:
    def test_runner_uses_session_when_available(self, db):
        sid = _seed(db)
        vm = run_race_plan_from_session(db, session_id=sid, **_kwargs())
        assert isinstance(vm, RacePlanViewModel)
        assert vm.has_recommendation
        assert "SessionDB session" in vm.source_note
        assert any(r["category"] == "measured" for r in vm.evidence_source_rows)

    def test_runner_produces_readable_explanation(self, db):
        sid = _seed(db)
        vm = run_race_plan_from_session(db, session_id=sid, **_kwargs())
        assert vm.driver_explanation
        assert "one-stop" in vm.recommended_strategy_title.lower()

    def test_confidence_high_with_full_session(self, db):
        sid = _seed(db)
        vm = run_race_plan_from_session(db, session_id=sid, **_kwargs())
        assert vm.confidence_label == "High"


class TestFallback:
    def test_missing_session_is_safe_and_honest(self, db):
        vm = run_race_plan_from_session(db, session_id=999, **_kwargs())
        assert isinstance(vm, RacePlanViewModel)
        assert not vm.has_recommendation
        assert vm.confidence_label == "Insufficient evidence"
        assert vm.missing_evidence_rows  # visible
        assert "No session data selected" in vm.source_note

    def test_lower_confidence_when_tyre_missing(self, db):
        sid = _seed(db, n=2)  # too few laps → no long-run tyre proxy
        vm = run_race_plan_from_session(db, session_id=sid, **_kwargs())
        assert vm.confidence_label != "High"

    def test_event_context_runner(self, db):
        sid = _seed(db)

        class _EC:
            track = "Fuji Speedway"
            layout_id = "fuji__full"
            is_lap_race = False
            is_timed = True
            laps = 0
            race_duration_minutes = 50
            tyre_wear_multiplier = 8.0
            fuel_multiplier = 3.0
            refuel_rate_lps = 1.0
            mandatory_stops = 0
            available_tyres = ("RM", "RH")
            required_tyres = ()
            weather = "Fixed Dry"

        vm = run_race_plan_from_event_context(
            db, session_id=sid, event_context=_EC(),
            pit_loss_seconds=22.0, rear_traction_fragile=True,
        )
        assert vm.has_recommendation
        assert vm.estimated_total_time != "—"


class TestQtSurfaceSource:
    """Source-level guarantees on the Strategy Builder Race Plan method."""

    def _dashboard_src(self):
        return ((ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8") + (ROOT / "ui" / "race_plan_ui.py").read_text(encoding="utf-8"))

    def _race_plan_method(self, src: str) -> str:
        start = src.index("def _run_race_plan(self)")
        end = src.index("\n    def ", start + 1)
        return src[start:end]

    def test_race_plan_method_reads_no_api_key(self):
        body = self._race_plan_method(self._dashboard_src())
        assert "api_key" not in body
        assert "_ai_api_key" not in body

    def test_race_plan_method_has_no_apply_or_setup_history(self):
        body = self._race_plan_method(self._dashboard_src())
        for banned in ("setup_history", "_finalise_recommendation", "apply_ai_fields",
                       "save_entry", "insert_setup_recommendations"):
            assert banned not in body

    def test_race_plan_group_has_build_button_no_apply(self):
        src = self._dashboard_src()
        start = src.index("def _build_race_plan_group(self)")
        end = src.index("\n    def ", start + 1)
        body = src[start:end]
        assert "Build Race Strategy" in body
        assert "_btn_build_race_plan" in body
        # The Build button is wired to the deterministic runner. Group 51 also added
        # a read-only Refresh button; both handlers are strategy-only (no setup power).
        assert "self._run_race_plan" in body
        for handler in ("self._run_race_plan", "self._populate_race_plan_sessions"):
            assert handler in body
        # No setup-apply/approve CAPABILITY (the word may appear in disclaimers).
        for banned in ("apply_ai_fields", "_finalise_recommendation", "setup_fields",
                       "insert_setup_recommendations", "save_entry", "_btn_apply"):
            assert banned not in body

    def test_race_plan_group_wired_into_strategy_tab(self):
        src = self._dashboard_src()
        assert "self._build_race_plan_group()" in src


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
