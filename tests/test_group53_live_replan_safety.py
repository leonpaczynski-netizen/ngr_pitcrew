"""Group 53 — live replan safety tests.

Asserts the live current-state adapter + live replan runner weaken no Group 43-52
guarantee: read-only, advisory-only, no setup power, no API key, no writes.

All tests are pure/offline.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.race_strategy_uat import run_fuji_uat, run_fuji_live_replan  # noqa: E402
from strategy.race_strategy_live_replan import LiveReplanResult, build_live_replan_snapshot  # noqa: E402
from strategy.race_strategy_live_replan import fuji_live_state_healthy  # noqa: E402


def _hash(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


_LIVE_MODULES = (
    "strategy/race_strategy_live_state.py",
    "strategy/race_strategy_live_replan.py",
)


class TestModulePurity:
    def test_no_qt_import(self):
        for mod in _LIVE_MODULES:
            src = (ROOT / mod).read_text(encoding="utf-8")
            for line in src.splitlines():
                s = line.strip()
                if s.startswith("import ") or s.startswith("from "):
                    assert "PyQt" not in s and "PySide" not in s and "QtWidgets" not in s

    def test_imports_no_setup_authoring(self):
        for mod in _LIVE_MODULES:
            src = (ROOT / mod).read_text(encoding="utf-8")
            for banned in ("setup_plan", "setup_rule_engine", "setup_ai_audit",
                           "setup_knowledge_base", "setup_baseline", "setup_history"):
                assert banned not in src

    def test_no_io_or_ai(self):
        for mod in _LIVE_MODULES:
            src = (ROOT / mod).read_text(encoding="utf-8")
            for banned in ("open(", "write_lap", "save_entry", "insert_", "sqlite3",
                           "requests", "call_api", "api_key"):
                assert banned not in src


class TestNoApplyCapability:
    def test_result_has_no_apply_attrs(self):
        r = build_live_replan_snapshot(pre_race_result=run_fuji_uat(),
                                       live_state=fuji_live_state_healthy())
        assert isinstance(r, LiveReplanResult)
        for banned in ("apply", "approve", "setup_fields", "approved_fields", "write",
                       "pit_now", "send_command"):
            assert not hasattr(r, banned)
            assert not hasattr(r.snapshot, banned)

    def test_advisory_only_notes(self):
        r = run_fuji_live_replan("healthy")
        joined = " ".join(r.safety_notes).lower()
        assert "no pit call" in joined
        assert "setup change" in joined


class TestNoRuntimeWrites:
    def test_live_replan_does_not_write_setup_history(self):
        target = ROOT / "data" / "setup_history.json"
        before = _hash(target)
        run_fuji_live_replan("healthy")
        run_fuji_live_replan("fuel_short")
        run_fuji_live_replan("missing")
        assert _hash(target) == before


class TestSetupGuaranteesUntouched:
    def test_apply_gate_predicate_unchanged(self):
        src = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
        assert "_status_approved and bool(_parsed_ai_fields) and not _is_legacy" in src

    def test_old_ai_build_path_still_disabled(self):
        src = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
        assert "the from-scratch AI build path was removed" in src


class TestUnknownStateNotSafe:
    def test_unknown_tyre_never_high_confidence(self):
        from strategy.race_strategy_replan import ReplanConfidence
        # Healthy fuel but tyre unknown must not read as high confidence.
        r = run_fuji_live_replan("healthy")
        assert r.confidence in (ReplanConfidence.MEDIUM, ReplanConfidence.LOW,
                                ReplanConfidence.INSUFFICIENT_EVIDENCE)

    def test_missing_fuel_returns_insufficient(self):
        from strategy.race_strategy_replan import ReplanConfidence
        r = run_fuji_live_replan("missing")
        assert r.confidence == ReplanConfidence.INSUFFICIENT_EVIDENCE


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
