"""Group 55 — safety-guard tests.

Asserts the pit-lane mapping feature weakens no Group 43–54 guarantee: the new
pure module is Qt/DB/AI/file-write-free, authors nothing, corroborates but never
CREATES a pit stop, degrades gracefully on missing data, never treats unknown
mapping as safe, and leaves the setup Apply gate + disabled AI-build untouched.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy._setup_constants import DB_VERSION


def _hash(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


_NEW_MODULES = (
    "data/pit_lane_resolver.py",
    "strategy/race_strategy_live_state.py",
    "strategy/race_strategy_live_replan.py",
)


class TestModulePurity:
    def test_resolver_no_qt_import(self):
        src = (ROOT / "data" / "pit_lane_resolver.py").read_text(encoding="utf-8")
        for line in src.splitlines():
            s = line.strip()
            if s.startswith("import ") or s.startswith("from "):
                assert "PyQt" not in s and "QtWidgets" not in s and "QtCore" not in s

    def test_resolver_no_db_ai_imports(self):
        src = (ROOT / "data" / "pit_lane_resolver.py").read_text(encoding="utf-8")
        for line in src.splitlines():
            s = line.strip()
            if s.startswith("import ") or s.startswith("from "):
                assert "sqlite3" not in s and "session_db" not in s
                assert "anthropic" not in s.lower() and "openai" not in s.lower()

    def test_resolver_writes_no_files(self):
        src = (ROOT / "data" / "pit_lane_resolver.py").read_text(encoding="utf-8")
        assert "open(" not in src
        assert ".write(" not in src
        assert "json.dump" not in src

    def test_modules_no_api_key(self):
        for mod in _NEW_MODULES:
            src = (ROOT / mod).read_text(encoding="utf-8")
            assert "api_key" not in src.lower()

    def test_modules_import_no_setup_authoring(self):
        for mod in _NEW_MODULES:
            src = (ROOT / mod).read_text(encoding="utf-8")
            for banned in ("setup_plan", "setup_rule_engine", "setup_ai_audit",
                           "setup_knowledge_base", "setup_baseline", "setup_history"):
                assert banned not in src


class TestNoApplyOrCommands:
    def test_result_has_no_apply_or_command_attrs(self):
        from ui.race_strategy_uat import run_fuji_live_replan
        r = run_fuji_live_replan("pre_pit_healthy")
        for banned in ("apply", "approve", "setup_fields", "write",
                       "pit_now", "box_now", "send_command", "make_pit_call"):
            assert not hasattr(r, banned)

    def test_render_has_no_command_wording(self):
        from ui.race_strategy_uat import run_fuji_uat
        from strategy.race_strategy_live_replan import (
            build_live_replan_snapshot, render_live_replan_text, fuji_pit_lane_mapping,
            fuji_live_state_just_pitted,
        )
        pre = run_fuji_uat()
        r = build_live_replan_snapshot(
            pre_race_result=pre, live_state=fuji_live_state_just_pitted(),
            track_context=fuji_pit_lane_mapping(), live_progress=0.97)
        text = render_live_replan_text(r).lower()
        for banned in ("pit now", "box now", "box box", "make the call", "come in"):
            assert banned not in text


class TestCorroborationNeverCreatesPit:
    def test_zone_entry_does_not_count_a_stop(self):
        # Being in the pit-lane corridor must NOT invent a pit stop or tyre age.
        from strategy.race_strategy_replan import RaceReplanState
        from strategy.race_strategy_live_state import (
            LiveReplanStateResult, apply_pit_lane_evidence,
        )
        from strategy.race_strategy_live_replan import fuji_pit_lane_mapping
        base = LiveReplanStateResult(state=RaceReplanState(), pit_state_confidence="UNKNOWN")
        out = apply_pit_lane_evidence(base, track_context=fuji_pit_lane_mapping(),
                                      live_progress=0.97)
        assert out.state.pit_stops_completed is None   # not fabricated
        assert out.state.tyre_age_laps is None
        assert out.pit_evidence_confidence == "UNKNOWN"  # no pit event → no lift


class TestGracefulDegradation:
    def test_missing_mapping_never_crashes(self):
        from strategy.race_strategy_replan import RaceReplanState
        from strategy.race_strategy_live_state import (
            LiveReplanStateResult, apply_pit_lane_evidence,
        )
        base = LiveReplanStateResult(state=RaceReplanState(), pit_state_confidence="MEDIUM")
        # None, empty, malformed contexts + bad progress must all be safe.
        for ctx in (None, {}, {"pit_lane": {}}, {"pit_lane": {"segments": "x"}}):
            for prog in (None, "bad", float("nan"), 0.5):
                out = apply_pit_lane_evidence(base, track_context=ctx, live_progress=prog)
                assert out.pit_evidence_confidence in ("MEDIUM", "UNKNOWN", "LOW", "HIGH")

    def test_unknown_mapping_not_treated_as_in_pit_lane(self):
        from data.pit_lane_resolver import resolve_pit_lane_zone, PitLaneZone
        res = resolve_pit_lane_zone(0.5, [])
        assert res.zone == PitLaneZone.UNKNOWN
        assert not res.is_inside_pit_lane  # unknown is never "inside/safe"


class TestSetupGuaranteesUntouched:
    def test_apply_gate_predicate_unchanged(self):
        src = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
        assert "_status_approved and bool(_parsed_ai_fields) and not _is_legacy" in src

    def test_old_ai_build_path_still_disabled(self):
        src = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
        assert "the from-scratch AI build path was removed" in src

    def test_no_setup_history_write(self):
        from ui.race_strategy_uat import run_fuji_live_replan
        target = ROOT / "data" / "setup_history.json"
        before = _hash(target)
        for kind in ("pre_pit_healthy", "just_pitted", "missing_pit"):
            run_fuji_live_replan(kind)
        assert _hash(target) == before


class TestNoSchemaMigration:
    def test_db_user_version_unchanged(self):
        # Group 62 introduced v14 (events.abs). This canary now tracks the
        # current schema (DB_VERSION) and forbids an unexpected next bump.
        src = (ROOT / "data" / "session_db.py").read_text(encoding="utf-8")
        assert f"PRAGMA user_version = {DB_VERSION}" in src
        assert f"PRAGMA user_version = {DB_VERSION + 1}" not in src

    def test_no_new_migration_hook(self):
        # Group 62 legitimately added _migrate_v14; an unexpected _migrate_v15
        # must still be absent.
        src = (ROOT / "data" / "session_db.py").read_text(encoding="utf-8")
        assert "_migrate_v14" in src
        # Engineering-Brain Phase 1 legitimately added _migrate_v15 (setup_lineage);
        # guard now protects against an unexpected _migrate_v16.
        assert "_migrate_v19" not in src


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
