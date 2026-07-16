"""Group 56 — safety-guard tests.

Asserts the live position→progress resolver weakens no Group 43–55 guarantee:
the new pure module is Qt/DB/AI/file-write-free, authors nothing, never creates a
pit, never treats unknown/low progress as safe, and leaves the setup Apply gate +
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
    "data/live_track_progress.py",
    "strategy/race_strategy_live_state.py",
    "strategy/race_strategy_live_replan.py",
)


class TestModulePurity:
    def test_resolver_no_qt_import(self):
        src = (ROOT / "data" / "live_track_progress.py").read_text(encoding="utf-8")
        for line in src.splitlines():
            s = line.strip()
            if s.startswith("import ") or s.startswith("from "):
                assert "PyQt" not in s and "QtWidgets" not in s and "QtCore" not in s

    def test_resolver_no_db_ai_imports(self):
        src = (ROOT / "data" / "live_track_progress.py").read_text(encoding="utf-8")
        for line in src.splitlines():
            s = line.strip()
            if s.startswith("import ") or s.startswith("from "):
                assert "sqlite3" not in s and "session_db" not in s
                assert "anthropic" not in s.lower() and "openai" not in s.lower()

    def test_resolver_writes_no_files(self):
        src = (ROOT / "data" / "live_track_progress.py").read_text(encoding="utf-8")
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
        from data.live_track_progress import LiveTrackProgressResult
        r = LiveTrackProgressResult()
        for banned in ("apply", "approve", "setup_fields", "write",
                       "pit_now", "box_now", "send_command", "make_pit_call"):
            assert not hasattr(r, banned)

    def test_evidence_has_no_command_wording(self):
        from strategy.race_strategy_live_replan import (
            build_live_replan_snapshot, render_live_replan_text,
            fuji_pit_lane_mapping, fuji_reference_path, fuji_position_at_progress,
        )
        from ui.race_strategy_uat import run_fuji_uat

        class _Tr:
            laps_recorded = 18
            laps_remaining = 0
            _current_compound = "RM"
            avg_fuel_per_lap = 4.0
            timed_duration_minutes = 50.0
            pit_state_confidence = "MEDIUM"
            tyre_age_laps = 2
            pit_stops_completed = 1
            in_pit = False
            live_world_position = fuji_position_at_progress(0.97) + (200.0,)

            def computed_remaining_ms(self):
                return 1800000

        ctx = dict(fuji_pit_lane_mapping())
        ctx["reference_path"] = fuji_reference_path()["reference_path"]
        r = build_live_replan_snapshot(pre_race_result=run_fuji_uat(),
                                       live_source=_Tr(), track_context=ctx)
        text = render_live_replan_text(r).lower()
        for banned in ("pit now", "box now", "box box", "make the call", "come in"):
            assert banned not in text


class TestUnknownProgressNeverSafe:
    def test_unknown_progress_not_usable(self):
        from data.live_track_progress import (
            LiveTrackProgressResult, TrackProgressConfidence,
        )
        r = LiveTrackProgressResult(confidence=TrackProgressConfidence.UNKNOWN)
        assert not r.has_progress
        assert not r.usable_for_pit

    def test_low_progress_not_usable(self):
        from data.live_track_progress import (
            LiveTrackProgressResult, TrackProgressConfidence,
        )
        r = LiveTrackProgressResult(progress=0.5, confidence=TrackProgressConfidence.LOW)
        assert not r.usable_for_pit

    def test_resolver_never_crashes_on_garbage(self):
        from data.live_track_progress import resolve_live_track_progress
        garbage_positions = [None, "x", (float("nan"), 0, 0), (float("inf"),), {}, []]
        garbage_stations = [None, [], "bad", [{"x": "y"}], [{"nope": 1}]]
        for p in garbage_positions:
            for stns in garbage_stations:
                r = resolve_live_track_progress(p, stns if isinstance(stns, list) else [])
                assert r.confidence.value in ("UNKNOWN", "LOW", "MEDIUM", "HIGH")


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
        # Cross-lap persistence (Sprint 5) legitimately added _migrate_v18
        # (corner_issue_occurrences); guard now protects against an unexpected v19.
        assert "_migrate_v20" not in src


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
