"""Group 51 — Race Plan surface hardening tests.

Covers the hardened Strategy Builder Race Plan surface:
  • Build/refresh methods read no API key, write no setup history, create no setup
    recommendation, and expose no Apply/approve controls (source-verified)
  • the readiness banner + plan still render when session/explanation evidence is
    missing, and never emit false-certainty wording

Qt guarantees are verified by source inspection (no QApplication constructed).
Pure render checks use the readiness/VM modules directly.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.session_db import SessionDB  # noqa: E402
from strategy.race_strategy_pipeline import recommend_strategy_from_session  # noqa: E402
from ui.race_strategy_vm import build_race_plan_view_model, render_race_plan_html  # noqa: E402
from ui.race_strategy_readiness_vm import (  # noqa: E402
    build_race_plan_readiness,
    build_session_diagnostics,
    render_readiness_html,
    ReadinessLevel,
)


def _dash():
    return ((ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8") + (ROOT / "ui" / "race_plan_ui.py").read_text(encoding="utf-8"))


def _method(name: str) -> str:
    src = _dash()
    start = src.index(f"def {name}(self")
    end = src.index("\n    def ", start + 1)
    return src[start:end]


def _es(**over):
    es = dict(
        car_id=911, track="Fuji Speedway", race_duration_minutes=50.0, race_laps=0,
        fuel_multiplier=3.0, tyre_multiplier=8.0, refuel_rate_lps=1.0,
        pit_loss_seconds=22.0, available_compounds=("RM", "RH"),
    )
    es.update(over)
    return es


class TestNoApiKeyOrSetupPower:
    def test_run_race_plan_reads_no_api_key(self):
        body = _method("_run_race_plan")
        assert "api_key" not in body
        assert "_ai_api_key" not in body

    def test_run_race_plan_no_setup_history_or_apply(self):
        body = _method("_run_race_plan")
        for banned in ("setup_history", "_finalise_recommendation", "apply_ai_fields",
                       "save_entry", "insert_setup_recommendations"):
            assert banned not in body

    def test_diagnostics_method_read_only(self):
        # Docstrings may say "never writes"; what must be absent is a write CALL.
        body = _method("_refresh_race_plan_diagnostics")
        for banned in ("write_lap", "open_session", "save_entry", "insert_",
                       "setup_history", "_finalise_recommendation", "delete_session"):
            assert banned not in body

    def test_populate_sessions_read_only(self):
        body = _method("_populate_race_plan_sessions")
        assert "list_recent_matching_sessions" in body
        for banned in ("write_lap", "open_session", "save_entry", "insert_",
                       "delete_session"):
            assert banned not in body

    def test_group_no_apply_or_approve_capability(self):
        src = _dash()
        start = src.index("def _build_race_plan_group(self)")
        end = src.index("\n    def ", start + 1)
        body = src[start:end]
        for banned in ("apply_ai_fields", "_finalise_recommendation", "setup_fields",
                       "insert_setup_recommendations", "save_entry", "_btn_apply",
                       "approved_fields"):
            assert banned not in body


class TestRendersWhenEvidenceMissing:
    def test_readiness_renders_when_insufficient(self):
        r = build_race_plan_readiness(samples=None, event_settings=_es())
        html = render_readiness_html(r)
        assert html
        assert r.overall_readiness == ReadinessLevel.INSUFFICIENT_EVIDENCE
        assert "Next best action" in html

    def test_readiness_renders_with_diagnostics(self):
        d = build_session_diagnostics(None, event_car_id=911, event_track="Fuji Speedway")
        r = build_race_plan_readiness(samples=None, event_settings=_es())
        html = render_readiness_html(r, d)
        assert "No session selected" in html

    def test_plan_renders_when_no_recommendation(self):
        db = SessionDB(":memory:")
        result = recommend_strategy_from_session(db, session_id=999, **_es())
        vm = build_race_plan_view_model(result)
        html = render_race_plan_html(vm)
        assert html  # still renders
        assert not vm.has_recommendation

    def test_plan_renders_with_empty_sections(self):
        db = SessionDB(":memory:")
        result = recommend_strategy_from_session(db, session_id=999, **_es())
        vm = build_race_plan_view_model(result)
        # stint rows / candidate rows are empty in the no-recommendation case
        assert vm.stint_plan_rows == []
        assert render_race_plan_html(vm)


class TestNoFalseCertainty:
    def test_readiness_no_certainty_words(self):
        db = SessionDB(":memory:")
        sid = db.open_session(car_id=911, track="Fuji Speedway", session_type="Practice", car_name="RSR")
        rem = 100.0
        for i in range(12):
            db.write_lap(session_id=sid, lap_num=i + 1, lap_time_ms=100000 + i * 80,
                         fuel_used=4.0, stats=None, compound="RM",
                         fuel_start=rem, fuel_end=rem - 4.0)
            rem -= 4.0
        from strategy.race_strategy_session_adapter import extract_session_strategy_samples
        s = extract_session_strategy_samples(db, sid, expected_car_id=911, expected_track="Fuji Speedway")
        html = render_readiness_html(build_race_plan_readiness(samples=s, event_settings=_es())).lower()
        for banned in ("guaranteed", "perfect strategy", "the winning strategy", "certain to win"):
            assert banned not in html


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
