"""Group 57 — safety-guard tests.

Asserts the reference-path loader weakens no Group 43–56 guarantee: pure
(Qt/AI-free), read-only (no writes), authors nothing, never creates a pit, never
treats missing/mismatched paths as safe, and leaves the setup Apply gate +
disabled AI-build untouched. No schema migration.
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
    "data/reference_path_loader.py",
    "strategy/race_strategy_live_replan.py",
    "data/track_library.py",
)


class TestModulePurity:
    def test_loader_no_qt_import(self):
        src = (ROOT / "data" / "reference_path_loader.py").read_text(encoding="utf-8")
        for line in src.splitlines():
            s = line.strip()
            if s.startswith("import ") or s.startswith("from "):
                assert "PyQt" not in s and "QtWidgets" not in s and "QtCore" not in s

    def test_loader_no_ai_db_write_imports(self):
        src = (ROOT / "data" / "reference_path_loader.py").read_text(encoding="utf-8")
        for line in src.splitlines():
            s = line.strip()
            if s.startswith("import ") or s.startswith("from "):
                assert "anthropic" not in s.lower() and "openai" not in s.lower()
                assert "session_db" not in s

    def test_loader_writes_no_files(self):
        src = (ROOT / "data" / "reference_path_loader.py").read_text(encoding="utf-8")
        # Read-only: no open-for-write, no writes, no json.dump.
        assert ".write_text(" not in src
        assert ".write(" not in src
        assert "json.dump" not in src
        assert "open(" not in src

    def test_no_api_key(self):
        for mod in _NEW_MODULES:
            src = (ROOT / mod).read_text(encoding="utf-8")
            assert "api_key" not in src.lower()

    def test_no_setup_authoring_import(self):
        for mod in _NEW_MODULES:
            src = (ROOT / mod).read_text(encoding="utf-8")
            for banned in ("setup_plan", "setup_rule_engine", "setup_ai_audit",
                           "setup_knowledge_base", "setup_baseline", "setup_history"):
                assert banned not in src


class TestNoApplyOrCommands:
    def test_result_has_no_apply_attrs(self):
        from data.reference_path_loader import ReferencePathLoadResult, ReferencePathAsset
        for obj in (ReferencePathLoadResult(), ReferencePathAsset()):
            for banned in ("apply", "approve", "write", "pit_now", "send_command",
                           "make_pit_call", "setup_fields"):
                assert not hasattr(obj, banned)


class TestMissingNeverSafe:
    def test_missing_and_mismatch_not_usable(self, tmp_path):
        from data.reference_path_loader import (
            load_reference_path_for_layout, validate_reference_path_identity,
        )
        res = load_reference_path_for_layout("nope", "nope__x", search_roots=[tmp_path])
        assert not res.has_stations
        ok, _ = validate_reference_path_identity(res.asset, "nope", "nope__x")
        assert not ok  # asset is None → not verified

    def test_loader_never_crashes_on_garbage(self, tmp_path):
        from data.reference_path_loader import load_reference_path_file
        # A grid of malformed files must never raise.
        (tmp_path / "a.reference_path.json").write_text("{bad", encoding="utf-8")
        (tmp_path / "b.reference_path.json").write_text("[]", encoding="utf-8")
        (tmp_path / "c.reference_path.json").write_text("123", encoding="utf-8")
        for name in ("a", "b", "c", "missing"):
            res = load_reference_path_file(tmp_path / f"{name}.reference_path.json")
            assert res.has_stations is False


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
        # Engineering-Brain Phases 1-5 legitimately added _migrate_v20..v25
        # (context/experiment/outcome/working-window/dev-history/reconciliation); guard protects v26.
        assert "_migrate_v20" in src
        assert "_migrate_v25" in src
        # Repaired (Phase 51-53 Audit A): v26/v27/v28 are legitimate later migrations
        # (Phase 19/45/48). Guard the real invariant: no migration hook BEYOND the current
        # declared DB_VERSION (catches an accidental/unexpected new migration).
        from strategy._setup_constants import DB_VERSION as _DBV
        assert f"_migrate_v{_DBV + 1}" not in src
class TestRuntimeAssetsUntouched:
    def test_fuji_reference_path_file_untouched(self):
        # Loading the real asset must not modify it (read-only).
        from data.reference_path_loader import load_reference_path_for_layout
        f = (ROOT / "data" / "track_models" /
             "fuji_international_speedway__fuji_international_speedway__full_course.reference_path.json")
        before = _hash(f)
        load_reference_path_for_layout(
            "fuji_international_speedway", "fuji_international_speedway__full_course")
        assert _hash(f) == before


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
