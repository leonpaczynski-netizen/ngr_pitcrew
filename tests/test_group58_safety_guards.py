"""Group 58 — safety-guard tests.

Asserts the road-distance fallback weakens no Group 43–57 guarantee: pure
(Qt/AI-free), no filesystem/DB writes, authors nothing, never creates a pit,
never mutates pit count, never returns HIGH, and leaves the setup Apply gate +
disabled AI-build + DB version untouched.
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
    "data/live_track_progress_fallback.py",
    "data/reference_path_loader.py",
    "strategy/race_strategy_live_replan.py",
    "strategy/race_strategy_live_state.py",
    "telemetry/state.py",
)


class TestModulePurity:
    def test_fallback_no_qt_import(self):
        src = (ROOT / "data" / "live_track_progress_fallback.py").read_text(encoding="utf-8")
        for line in src.splitlines():
            s = line.strip()
            if s.startswith("import ") or s.startswith("from "):
                assert "PyQt" not in s and "QtWidgets" not in s and "QtCore" not in s

    def test_fallback_no_ai_db_write(self):
        src = (ROOT / "data" / "live_track_progress_fallback.py").read_text(encoding="utf-8")
        assert "api_key" not in src.lower()
        assert "anthropic" not in src.lower() and "openai" not in src.lower()
        assert "sqlite3" not in src and "session_db" not in src
        assert ".write(" not in src and "json.dump" not in src and "open(" not in src

    def test_no_api_key_in_touched_modules(self):
        for mod in _NEW_MODULES:
            src = (ROOT / mod).read_text(encoding="utf-8")
            assert "api_key" not in src.lower()

    def test_no_setup_authoring_import(self):
        for mod in ("data/live_track_progress_fallback.py", "data/reference_path_loader.py"):
            src = (ROOT / mod).read_text(encoding="utf-8")
            for banned in ("setup_plan", "setup_rule_engine", "setup_ai_audit",
                           "setup_knowledge_base", "setup_baseline", "setup_history"):
                assert banned not in src


class TestNeverHighNeverPit:
    def test_fallback_never_high(self):
        from data.live_track_progress_fallback import resolve_progress_from_road_distance
        from data.live_track_progress import TrackProgressConfidence
        for d in (0.0, 100.0, 4563.0, 4563.0 * 4 + 7):
            r = resolve_progress_from_road_distance(lap_distance_m=d, road_distance=d,
                                                    lap_length_m=4563.0)
            assert r.confidence != TrackProgressConfidence.HIGH

    def test_fallback_progress_never_creates_pit(self):
        from strategy.race_strategy_replan import RaceReplanState
        from strategy.race_strategy_live_state import (
            LiveReplanStateResult, apply_pit_lane_evidence, attach_track_progress,
        )
        from data.live_track_progress_fallback import resolve_progress_from_road_distance
        from strategy.race_strategy_live_replan import fuji_pit_lane_mapping
        fb = resolve_progress_from_road_distance(lap_distance_m=0.97 * 4563.0,
                                                 lap_length_m=4563.0)
        base = LiveReplanStateResult(
            state=RaceReplanState(pit_stops_completed=1, tyre_age_laps=2),
            pit_state_confidence="MEDIUM")
        out = apply_pit_lane_evidence(attach_track_progress(base, fb),
                                      track_context=fuji_pit_lane_mapping())
        # Pit count/tyre age unchanged; fallback did not corroborate → no HIGH.
        assert out.state.pit_stops_completed == 1
        assert out.state.tyre_age_laps == 2
        assert out.pit_evidence_confidence != "HIGH"


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
        # Engineering-Brain Phase 1/2 legitimately added _migrate_v20/_migrate_v21
        # (context spine + experiment ledger); guard now protects against v22.
        assert "_migrate_v20" in src
        assert "_migrate_v21" in src
        assert "_migrate_v22" not in src


class TestStrategyScoringDeterministic:
    def test_group48_49_scoring_stable(self):
        from ui.race_strategy_uat import run_fuji_uat
        a = run_fuji_uat()
        b = run_fuji_uat()
        assert a.recommendation.recommended.candidate_id == b.recommendation.recommended.candidate_id


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
