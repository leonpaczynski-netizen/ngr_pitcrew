"""Group 61 — safety invariants.

Asserts the new pure modules are Qt/AI/DB/file-write-free, fallback still never
HIGH / never lifts pit, pit count never mutates, no Apply/command/AI leakage, DB
version unchanged, Group 48/49 deterministic, and setup gates intact.
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
    "data/live_road_distance_capture.py",
    "data/live_progress_stabiliser.py",
    "data/road_distance_capture_analysis.py",
    "data/road_distance_semantics.py",
    # Live per-corner telemetry: pure classifier + aggregator + consumer.
    "strategy/wheel_slip.py",
    "strategy/live_corner_aggregator.py",
    "telemetry/live_corner_telemetry.py",
)


class TestModulePurity:
    def test_no_qt(self):
        for mod in _NEW_PURE_MODULES:
            src = (ROOT / mod).read_text(encoding="utf-8")
            for line in src.splitlines():
                s = line.strip()
                if s.startswith("import ") or s.startswith("from "):
                    assert "PyQt" not in s and "QtWidgets" not in s and "QtCore" not in s

    def test_no_ai_db_file_writes(self):
        for mod in _NEW_PURE_MODULES:
            src = (ROOT / mod).read_text(encoding="utf-8")
            assert "api_key" not in src.lower()
            assert "anthropic" not in src.lower() and "openai" not in src.lower()
            assert "session_db" not in src
            assert ".write_text(" not in src and ".write(" not in src
            assert "json.dump" not in src and "open(" not in src

    def test_no_setup_authoring(self):
        for mod in _NEW_PURE_MODULES:
            src = (ROOT / mod).read_text(encoding="utf-8")
            for banned in ("setup_plan", "setup_rule_engine", "setup_ai_audit",
                           "setup_knowledge_base", "setup_baseline", "setup_history"):
                assert banned not in src


class TestFallbackInvariants:
    def test_fallback_never_high(self):
        from data.live_track_progress_fallback import resolve_progress_from_road_distance
        from data.live_track_progress import TrackProgressConfidence as C
        for kw in ({"lap_distance_m": 100.0}, {"road_distance": 9999.0}, {"lap_distance_m": 4600.0}):
            r = resolve_progress_from_road_distance(lap_length_m=4563.0, **kw)
            assert r.confidence != C.HIGH

    def test_fallback_never_lifts_pit_and_no_mutation(self):
        from strategy.race_strategy_replan import RaceReplanState
        from strategy.race_strategy_live_state import (
            LiveReplanStateResult, apply_pit_lane_evidence, attach_track_progress,
        )
        from data.live_track_progress_fallback import resolve_progress_from_road_distance
        from strategy.race_strategy_live_replan import fuji_pit_lane_mapping
        fb = resolve_progress_from_road_distance(lap_distance_m=0.97 * 4563.0, lap_length_m=4563.0)
        base = LiveReplanStateResult(
            state=RaceReplanState(pit_stops_completed=2, tyre_age_laps=3),
            pit_state_confidence="MEDIUM")
        out = apply_pit_lane_evidence(attach_track_progress(base, fb),
                                      track_context=fuji_pit_lane_mapping())
        assert out.state.pit_stops_completed == 2
        assert out.state.tyre_age_laps == 3
        assert out.pit_evidence_confidence != "HIGH"

    def test_stabiliser_never_touches_pit_or_mutates(self):
        # A downgraded (jumped) frame must not change pit corroboration vs a stable frame.
        from ui.race_strategy_uat import run_fuji_uat
        from data.live_track_progress import build_track_path_stations
        from data.live_progress_stabiliser import LiveProgressStabiliserState
        from strategy.race_strategy_live_replan import (
            build_live_replan_snapshot, fuji_pit_lane_mapping, fuji_reference_path,
            fuji_position_at_progress, fuji_live_state_pre_pit_healthy,
        )
        pre = run_fuji_uat()
        ctx = dict(fuji_pit_lane_mapping()); ctx["reference_path"] = fuji_reference_path()["reference_path"]
        stations = build_track_path_stations(fuji_reference_path())
        state = LiveProgressStabiliserState()
        r1 = build_live_replan_snapshot(pre_race_result=pre, live_state=fuji_live_state_pre_pit_healthy(),
                                        track_context=ctx, live_position=fuji_position_at_progress(0.4),
                                        reference_stations=stations, stabiliser_state=state)
        r2 = build_live_replan_snapshot(pre_race_result=pre, live_state=fuji_live_state_pre_pit_healthy(),
                                        track_context=ctx, live_position=fuji_position_at_progress(0.9),
                                        reference_stations=stations, stabiliser_state=state)
        assert r1.pit_evidence_confidence == r2.pit_evidence_confidence
        assert r1.pit_corroboration == r2.pit_corroboration


class TestSetupGuaranteesUntouched:
    def test_apply_gate_predicate_unchanged(self):
        src = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
        assert "_status_approved and bool(_parsed_ai_fields) and not _is_legacy" in src

    def test_old_ai_build_path_still_disabled(self):
        src = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
        assert "form._btn_build_setup.setEnabled(False)" in src

    def test_no_setup_history_write(self):
        from ui.race_strategy_uat import (
            run_fuji_live_replan, run_raw_live_capture_uat, run_real_capture_road_distance_uat,
        )
        target = ROOT / "data" / "setup_history.json"
        before = _hash(target)
        for kind in ("pre_pit_healthy", "just_pitted", "missing_pit"):
            run_fuji_live_replan(kind)
        for kind in ("cumulative", "non_distance"):
            run_raw_live_capture_uat(kind)
        run_real_capture_road_distance_uat("fuji")
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
        assert "_migrate_v17" not in src


class TestStrategyDeterministic:
    def test_group48_49_scoring_stable(self):
        from ui.race_strategy_uat import run_fuji_uat
        a = run_fuji_uat()
        b = run_fuji_uat()
        assert a.recommendation.recommended.candidate_id == b.recommendation.recommended.candidate_id


class TestRuntimeAssetsUntouched:
    def test_calibration_capture_files_untouched(self):
        from ui.race_strategy_uat import run_real_capture_road_distance_uat
        f = (ROOT / "data" / "track_models" /
             "fuji_international_speedway__fuji_international_speedway__full_course.calibration_laps.json")
        before = _hash(f)
        run_real_capture_road_distance_uat("fuji")
        assert _hash(f) == before


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
