"""Group 54 — safety-regression tests.

Asserts the pit/tyre-age tracking weakens no Group 43-53 guarantee.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.race_strategy_uat import run_fuji_live_replan  # noqa: E402


def _hash(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


_MODULES = (
    "telemetry/pit_state.py",
    "strategy/race_strategy_live_state.py",
    "strategy/race_strategy_live_replan.py",
)


class TestModulePurity:
    def test_pit_state_no_qt_import(self):
        src = (ROOT / "telemetry" / "pit_state.py").read_text(encoding="utf-8")
        for line in src.splitlines():
            s = line.strip()
            if s.startswith("import ") or s.startswith("from "):
                assert "PyQt" not in s and "QtWidgets" not in s

    def test_modules_import_no_setup_authoring(self):
        for mod in _MODULES:
            src = (ROOT / mod).read_text(encoding="utf-8")
            for banned in ("setup_plan", "setup_rule_engine", "setup_ai_audit",
                           "setup_knowledge_base", "setup_baseline", "setup_history"):
                assert banned not in src

    def test_modules_no_api_key(self):
        for mod in _MODULES:
            src = (ROOT / mod).read_text(encoding="utf-8")
            assert "api_key" not in src.lower()


class TestNoApplyCapability:
    def test_live_replan_result_no_apply_attrs(self):
        r = run_fuji_live_replan("pre_pit_healthy")
        for banned in ("apply", "approve", "setup_fields", "approved_fields", "write",
                       "pit_now", "send_command"):
            assert not hasattr(r, banned)
            assert not hasattr(r.snapshot, banned)


class TestNoRuntimeWrites:
    def test_no_setup_history_write(self):
        target = ROOT / "data" / "setup_history.json"
        before = _hash(target)
        for kind in ("pre_pit_healthy", "just_pitted", "missing_pit"):
            run_fuji_live_replan(kind)
        assert _hash(target) == before

    def test_pit_state_writes_no_files(self):
        # The tracker's pit-state integration is runtime-only.
        src = (ROOT / "telemetry" / "pit_state.py").read_text(encoding="utf-8")
        assert "open(" not in src
        assert ".write(" not in src


class TestSetupGuaranteesUntouched:
    def test_apply_gate_predicate_unchanged(self):
        src = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
        assert "_status_approved and bool(_parsed_ai_fields) and not _is_legacy" in src

    def test_old_ai_build_path_still_disabled(self):
        src = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
        assert "the from-scratch AI build path was removed" in src


class TestUnknownStateNotSafe:
    def test_missing_pit_state_not_treated_safe(self):
        from strategy.race_strategy_replan import ReplanConfidence
        r = run_fuji_live_replan("missing_pit")
        assert r.confidence in (ReplanConfidence.LOW, ReplanConfidence.INSUFFICIENT_EVIDENCE)

    def test_sessiondb_pipeline_still_read_only(self):
        # Group 49-53 read-only SessionDB path still works with a minimal read-only DB.
        from data.session_db import SessionDB
        from strategy.race_strategy_pipeline import recommend_strategy_from_session

        class RO:
            def __init__(self, inner):
                self._inner = inner
            def get_session_meta(self, sid):
                return self._inner.get_session_meta(sid)
            def get_session_laps(self, sid, exclude_pit=False, exclude_out=False):
                return self._inner.get_session_laps(sid, exclude_pit=exclude_pit, exclude_out=exclude_out)

        inner = SessionDB(":memory:")
        sid = inner.open_session(car_id=911, track="Fuji Speedway", session_type="Practice", car_name="RSR")
        rem = 100.0
        for i in range(12):
            inner.write_lap(session_id=sid, lap_num=i + 1, lap_time_ms=100000 + i * 80,
                            fuel_used=4.0, stats=None, compound="RM",
                            fuel_start=rem, fuel_end=rem - 4.0)
            rem -= 4.0
        result = recommend_strategy_from_session(
            RO(inner), session_id=sid, car_id=911, track="Fuji Speedway",
            race_duration_minutes=50.0, fuel_multiplier=3.0, tyre_multiplier=8.0,
            refuel_rate_lps=1.0, pit_loss_seconds=22.0, available_compounds=("RM", "RH"))
        assert result.recommendation.has_recommendation


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
