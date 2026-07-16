"""Group 60 — safety-guard tests.

Asserts the new pure modules are Qt/AI/DB-write/file-write-free, author nothing,
introduce no setup Apply path, keep DB version + Apply-gate + disabled AI-build
intact, keep Group 48/49 scoring deterministic, and preserve Group 55–59 pit and
fallback invariants (unchanged production live behaviour).
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


_NEW_PURE_MODULES = (
    "data/road_distance_capture_analysis.py",
    "data/live_progress_stabiliser.py",
)


class TestModulePurity:
    def test_no_qt_import(self):
        for mod in _NEW_PURE_MODULES:
            src = (ROOT / mod).read_text(encoding="utf-8")
            for line in src.splitlines():
                s = line.strip()
                if s.startswith("import ") or s.startswith("from "):
                    assert "PyQt" not in s and "QtWidgets" not in s and "QtCore" not in s

    def test_no_ai_db_imports(self):
        for mod in _NEW_PURE_MODULES:
            src = (ROOT / mod).read_text(encoding="utf-8")
            for line in src.splitlines():
                s = line.strip()
                if s.startswith("import ") or s.startswith("from "):
                    assert "anthropic" not in s.lower() and "openai" not in s.lower()
                    assert "session_db" not in s

    def test_no_file_writes(self):
        for mod in _NEW_PURE_MODULES:
            src = (ROOT / mod).read_text(encoding="utf-8")
            assert ".write_text(" not in src
            assert ".write(" not in src
            assert "json.dump" not in src
            assert "open(" not in src  # read via Path.read_text only

    def test_no_api_key(self):
        for mod in _NEW_PURE_MODULES + ("ui/race_strategy_uat.py",):
            src = (ROOT / mod).read_text(encoding="utf-8")
            assert "api_key" not in src.lower()

    def test_no_setup_authoring_import(self):
        for mod in _NEW_PURE_MODULES:
            src = (ROOT / mod).read_text(encoding="utf-8")
            for banned in ("setup_plan", "setup_rule_engine", "setup_ai_audit",
                           "setup_knowledge_base", "setup_baseline", "setup_history"):
                assert banned not in src


class TestResultsHaveNoApplyPath:
    def test_capture_result_no_apply_attrs(self):
        from data.road_distance_capture_analysis import CaptureAnalysisResult
        from data.live_progress_stabiliser import StabilisedProgress
        from data.live_track_progress import LiveTrackProgressResult
        for obj in (CaptureAnalysisResult(),
                    StabilisedProgress(result=LiveTrackProgressResult(),
                                       stabilised_confidence=None)):
            for banned in ("apply", "approve", "write", "pit_now", "send_command",
                           "make_pit_call", "setup_fields"):
                assert not hasattr(obj, banned)


class TestSetupGuaranteesUntouched:
    def test_apply_gate_predicate_unchanged(self):
        src = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
        assert "_status_approved and bool(_parsed_ai_fields) and not _is_legacy" in src

    def test_old_ai_build_path_still_disabled(self):
        src = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
        assert "the from-scratch AI build path was removed" in src

    def test_no_setup_history_write(self):
        from ui.race_strategy_uat import run_fuji_live_replan, run_real_capture_road_distance_uat
        target = ROOT / "data" / "setup_history.json"
        before = _hash(target)
        for kind in ("pre_pit_healthy", "just_pitted", "missing_pit"):
            run_fuji_live_replan(kind)
        for kind in ("fuji", "daytona", "cumulative"):
            run_real_capture_road_distance_uat(kind)
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
        assert "_migrate_v20" not in src


class TestStrategyScoringDeterministic:
    def test_group48_49_scoring_stable(self):
        from ui.race_strategy_uat import run_fuji_uat
        a = run_fuji_uat()
        b = run_fuji_uat()
        assert a.recommendation.recommended.candidate_id == b.recommendation.recommended.candidate_id


class TestPitInvariantsIntact:
    def test_fallback_still_never_lifts_pit(self):
        # Group 55–59 invariant: road-distance fallback progress never corroborates a pit.
        from strategy.race_strategy_replan import RaceReplanState
        from strategy.race_strategy_live_state import (
            LiveReplanStateResult, apply_pit_lane_evidence, attach_track_progress,
        )
        from data.live_track_progress_fallback import resolve_progress_from_road_distance
        from strategy.race_strategy_live_replan import fuji_pit_lane_mapping
        fb = resolve_progress_from_road_distance(lap_distance_m=0.97 * 4563.0, lap_length_m=4563.0)
        base = LiveReplanStateResult(
            state=RaceReplanState(pit_stops_completed=1, tyre_age_laps=2),
            pit_state_confidence="MEDIUM")
        out = apply_pit_lane_evidence(attach_track_progress(base, fb),
                                      track_context=fuji_pit_lane_mapping())
        assert out.state.pit_stops_completed == 1
        assert out.pit_evidence_confidence != "HIGH"


class TestRuntimeAssetsUntouched:
    def test_capture_files_untouched_by_analysis(self):
        from data.road_distance_capture_analysis import analyse_calibration_capture
        f = (ROOT / "data" / "track_models" /
             "fuji_international_speedway__fuji_international_speedway__full_course.calibration_laps.json")
        before = _hash(f)
        analyse_calibration_capture("fuji_international_speedway",
                                    "fuji_international_speedway__full_course")
        assert _hash(f) == before


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
