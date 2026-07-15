"""Group 51 — safety-regression tests.

Asserts the readiness/diagnostics hardening weakens no Group 43-50 guarantee:
  • Setup Apply-gate predicate unchanged; old AI Build path stays disabled
  • the SessionDB read path (readiness + selector) stays read-only
  • the strategy pipeline stays strategy-only; Group 48/49 scoring deterministic
  • Group 50 view model AND the Group 51 readiness module have no Qt import and
    import no setup-authoring module; neither writes setup history

Pure tests (SQLite `:memory:`); UI guarantees source-verified.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.session_db import SessionDB  # noqa: E402
from strategy.race_strategy_candidates import generate_candidates  # noqa: E402
from strategy.race_strategy_evidence import build_strategy_evidence  # noqa: E402
from strategy.race_strategy_scorer import score_candidates  # noqa: E402
from ui.race_strategy_readiness_vm import (  # noqa: E402
    build_race_plan_readiness, list_recent_matching_sessions,
)


def _seed(db, *, n=12, fuel=4.0):
    sid = db.open_session(car_id=911, track="Fuji Speedway", session_type="Practice", car_name="RSR")
    remaining = 100.0
    for i in range(n):
        db.write_lap(session_id=sid, lap_num=i + 1, lap_time_ms=100000 + i * 80,
                     fuel_used=fuel, stats=None, compound="RM",
                     fuel_start=remaining, fuel_end=remaining - fuel)
        remaining -= fuel
    return sid


def _hash(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


class TestSetupGuaranteesUntouched:
    def test_apply_gate_predicate_unchanged(self):
        src = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
        assert "_status_approved and bool(_parsed_ai_fields) and not _is_legacy" in src

    def test_old_ai_build_path_still_disabled(self):
        src = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
        assert "the from-scratch AI build path was removed" in src


class TestModulePurity:
    def test_readiness_module_no_qt_import(self):
        src = (ROOT / "ui" / "race_strategy_readiness_vm.py").read_text(encoding="utf-8")
        for line in src.splitlines():
            s = line.strip()
            if s.startswith("import ") or s.startswith("from "):
                assert "PyQt" not in s and "PySide" not in s and "QtWidgets" not in s

    def test_group50_view_model_still_no_qt_import(self):
        src = (ROOT / "ui" / "race_strategy_vm.py").read_text(encoding="utf-8")
        for line in src.splitlines():
            s = line.strip()
            if s.startswith("import ") or s.startswith("from "):
                assert "PyQt" not in s and "PySide" not in s and "QtWidgets" not in s

    def test_readiness_module_imports_no_setup_authoring(self):
        src = (ROOT / "ui" / "race_strategy_readiness_vm.py").read_text(encoding="utf-8")
        for banned in ("setup_plan", "setup_rule_engine", "setup_ai_audit",
                       "setup_knowledge_base", "setup_baseline"):
            assert banned not in src


class TestReadOnly:
    def test_readiness_and_selector_read_only(self):
        # DB exposing only the read methods the readiness layer needs.
        class RO:
            def __init__(self, inner):
                self._inner = inner
            def get_session_meta(self, sid):
                return self._inner.get_session_meta(sid)
            def get_session_laps(self, sid, exclude_pit=False, exclude_out=False):
                return self._inner.get_session_laps(sid, exclude_pit=exclude_pit, exclude_out=exclude_out)
            def get_practice_sessions(self, car_id, track):
                return self._inner.get_practice_sessions(car_id, track)

        inner = SessionDB(":memory:")
        _seed(inner)
        ro = RO(inner)
        assert list_recent_matching_sessions(ro, 911, "Fuji Speedway")
        assert not hasattr(ro, "write_lap")

    def test_readiness_does_not_write_setup_history(self):
        target = ROOT / "data" / "setup_history.json"
        before = _hash(target)
        db = SessionDB(":memory:")
        from strategy.race_strategy_session_adapter import extract_session_strategy_samples
        s = extract_session_strategy_samples(db, _seed(db), expected_car_id=911, expected_track="Fuji Speedway")
        build_race_plan_readiness(samples=s, event_settings={"race_laps": 20, "refuel_rate_lps": 1.0, "pit_loss_seconds": 22.0})
        list_recent_matching_sessions(db, 911, "Fuji Speedway")
        assert _hash(target) == before


class TestScoringDeterministic:
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


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
