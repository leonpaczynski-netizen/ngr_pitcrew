"""Group 52 — replan foundation safety tests.

Asserts the replan foundation is read-only / advisory-only and weakens no Group
43-51 guarantee:
  • the replan module imports no setup-authoring module and has no Qt import
  • it has no Apply/approve capability and writes no setup history (content-hash)
  • the placeholder message is honest ("not connected yet"); no auto pit call
  • Setup Apply-gate predicate unchanged; old AI Build path stays disabled

All tests are pure/offline.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.race_strategy_uat import run_fuji_uat  # noqa: E402
from strategy.race_strategy_replan import (  # noqa: E402
    RaceReplanState, RaceReplanSnapshot,
    build_replan_snapshot, replan_placeholder_message, REPLAN_SAFETY_NOTES,
)


def _hash(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


class TestModulePurity:
    def test_no_qt_import(self):
        src = (ROOT / "strategy" / "race_strategy_replan.py").read_text(encoding="utf-8")
        for line in src.splitlines():
            s = line.strip()
            if s.startswith("import ") or s.startswith("from "):
                assert "PyQt" not in s and "PySide" not in s and "QtWidgets" not in s

    def test_imports_no_setup_authoring(self):
        src = (ROOT / "strategy" / "race_strategy_replan.py").read_text(encoding="utf-8")
        for banned in ("setup_plan", "setup_rule_engine", "setup_ai_audit",
                       "setup_knowledge_base", "setup_baseline", "setup_history"):
            assert banned not in src

    def test_module_does_no_io(self):
        src = (ROOT / "strategy" / "race_strategy_replan.py").read_text(encoding="utf-8")
        for banned in ("open(", "write_lap", "save_entry", "insert_", "sqlite3",
                       "requests", "call_api", "os.remove"):
            assert banned not in src


class TestNoApplyCapability:
    def test_snapshot_has_no_apply_attrs(self):
        snap = build_replan_snapshot(
            pre_race_result=run_fuji_uat(),
            state=RaceReplanState(current_lap=10, fuel_remaining_pct=60.0,
                                  current_compound="RM", tyre_age_laps=10,
                                  remaining_laps=20, pit_stops_completed=0),
        )
        assert isinstance(snap, RaceReplanSnapshot)
        for banned in ("apply", "approve", "setup_fields", "approved_fields", "write",
                       "pit_now", "send_command"):
            assert not hasattr(snap, banned)

    def test_safety_notes_are_advisory_only(self):
        joined = " ".join(REPLAN_SAFETY_NOTES).lower()
        assert "no pit call" in joined
        assert "setup change" in joined
        assert "applies nothing" in joined or "changes nothing" in joined


class TestPlaceholderHonest:
    def test_placeholder_says_not_connected(self):
        msg = replan_placeholder_message().lower()
        assert "not connected yet" in msg
        assert "makes no pit calls" in msg
        # lists the required live fields
        for field in ("current lap", "fuel remaining", "compound", "tyre age", "remaining"):
            assert field in msg

    def test_placeholder_no_false_certainty(self):
        msg = replan_placeholder_message().lower()
        for banned in ("guaranteed", "automatic", "will pit", "applies"):
            # "applies nothing" is fine; a bare "applies <action>" is not present
            if banned == "applies":
                assert "applies nothing" in msg
            else:
                assert banned not in msg


class TestNoRuntimeWrites:
    def test_replan_does_not_write_setup_history(self):
        target = ROOT / "data" / "setup_history.json"
        before = _hash(target)
        build_replan_snapshot(
            pre_race_result=run_fuji_uat(),
            state=RaceReplanState(current_lap=10, fuel_remaining_pct=60.0,
                                  current_compound="RM", tyre_age_laps=10,
                                  remaining_laps=20, pit_stops_completed=0),
        )
        assert _hash(target) == before


class TestSetupGuaranteesUntouched:
    def test_apply_gate_predicate_unchanged(self):
        src = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
        assert "_status_approved and bool(_parsed_ai_fields) and not _is_legacy" in src

    def test_old_ai_build_path_still_disabled(self):
        src = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
        assert "form._btn_build_setup.setEnabled(False)" in src


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
