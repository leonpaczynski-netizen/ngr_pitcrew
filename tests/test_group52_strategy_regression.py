"""Group 52 — cross-group strategy regression pins.

Confirms Groups 48/49/50/51 guarantees still hold after the Group 52 additions:
  • Group 48 scoring stays deterministic
  • SessionDB strategy access stays read-only
  • the Race Plan surface + replan foundation need no API key
  • the readiness / view-model modules stay Qt-free and setup-authoring-free

All tests are pure/offline (SQLite `:memory:`).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.session_db import SessionDB  # noqa: E402
from strategy.race_strategy_candidates import generate_candidates  # noqa: E402
from strategy.race_strategy_evidence import build_strategy_evidence  # noqa: E402
from strategy.race_strategy_scorer import score_candidates  # noqa: E402
from strategy.race_strategy_pipeline import recommend_strategy_from_session  # noqa: E402
from ui.race_strategy_vm import build_race_plan_view_model  # noqa: E402


def _seed(db, *, n=12, fuel=4.0):
    sid = db.open_session(car_id=911, track="Fuji Speedway", session_type="Practice", car_name="RSR")
    rem = 100.0
    for i in range(n):
        db.write_lap(session_id=sid, lap_num=i + 1, lap_time_ms=100000 + i * 80,
                     fuel_used=fuel, stats=None, compound="RM",
                     fuel_start=rem, fuel_end=rem - fuel)
        rem -= fuel
    return sid


def _kwargs(**over):
    kw = dict(car_id=911, track="Fuji Speedway", race_duration_minutes=50.0,
              fuel_multiplier=3.0, tyre_multiplier=8.0, refuel_rate_lps=1.0,
              pit_loss_seconds=22.0, available_compounds=("RM", "RH"))
    kw.update(over)
    return kw


class TestDeterministicScoring:
    def test_group48_scoring_deterministic(self):
        ev = build_strategy_evidence(
            track="Fuji", race_laps=20, fuel_multiplier=3.0, tyre_multiplier=8.0,
            refuel_rate_lps=1.0, pit_loss_seconds=22.0, available_compounds=("RM", "RH"),
            lap_time_samples=[100.0] * 8, fuel_use_samples=[4.0] * 4,
            tyre_wear_samples=[0.08] * 10, compound_samples={"RM": [100.0], "RH": [101.5]},
        )
        a = [(s.candidate_id, s.estimated_total_time_seconds)
             for s in score_candidates(generate_candidates(ev), ev)]
        b = [(s.candidate_id, s.estimated_total_time_seconds)
             for s in score_candidates(generate_candidates(ev), ev)]
        assert a == b

    def test_pipeline_deterministic(self):
        db = SessionDB(":memory:")
        sid = _seed(db)
        v1 = build_race_plan_view_model(recommend_strategy_from_session(db, session_id=sid, **_kwargs()))
        v2 = build_race_plan_view_model(recommend_strategy_from_session(db, session_id=sid, **_kwargs()))
        assert v1.recommended_strategy_title == v2.recommended_strategy_title
        assert v1.estimated_total_time == v2.estimated_total_time


class TestSessionDbReadOnly:
    def test_pipeline_works_with_read_only_db(self):
        class RO:
            def __init__(self, inner):
                self._inner = inner
            def get_session_meta(self, sid):
                return self._inner.get_session_meta(sid)
            def get_session_laps(self, sid, exclude_pit=False, exclude_out=False):
                return self._inner.get_session_laps(sid, exclude_pit=exclude_pit, exclude_out=exclude_out)

        inner = SessionDB(":memory:")
        sid = _seed(inner)
        vm = build_race_plan_view_model(recommend_strategy_from_session(RO(inner), session_id=sid, **_kwargs()))
        assert vm.has_recommendation


class TestNoApiKey:
    def test_race_plan_and_replan_modules_reference_no_api_key(self):
        for mod in ("ui/race_strategy_vm.py", "ui/race_strategy_readiness_vm.py",
                    "ui/race_strategy_uat.py", "strategy/race_strategy_replan.py"):
            src = (ROOT / mod).read_text(encoding="utf-8")
            assert "api_key" not in src.lower()

    def test_run_race_plan_method_reads_no_api_key(self):
        src = ((ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8") + (ROOT / "ui" / "race_plan_ui.py").read_text(encoding="utf-8"))
        start = src.index("def _run_race_plan(self)")
        end = src.index("\n    def ", start + 1)
        assert "api_key" not in src[start:end]


class TestModulePurity:
    def test_strategy_and_ui_vm_modules_qt_free_where_required(self):
        for mod in ("ui/race_strategy_vm.py", "ui/race_strategy_readiness_vm.py",
                    "strategy/race_strategy_replan.py"):
            src = (ROOT / mod).read_text(encoding="utf-8")
            for line in src.splitlines():
                s = line.strip()
                if s.startswith("import ") or s.startswith("from "):
                    assert "PyQt" not in s and "QtWidgets" not in s

    def test_modules_import_no_setup_authoring(self):
        for mod in ("ui/race_strategy_vm.py", "ui/race_strategy_readiness_vm.py",
                    "ui/race_strategy_uat.py", "strategy/race_strategy_replan.py"):
            src = (ROOT / mod).read_text(encoding="utf-8")
            for banned in ("setup_plan", "setup_rule_engine", "setup_ai_audit",
                           "setup_knowledge_base", "setup_baseline"):
                assert banned not in src


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
