"""Group 50 — Race Strategy Brain Phase 4: safety-regression tests.

Asserts the driver-facing Race Plan surface weakens no Group 43-49 guarantee:
  • Setup Apply-gate predicate unchanged; old AI Build path stays disabled
  • the Race Plan group/method exposes no Apply/approve control, reads no API key,
    creates no setup recommendation, and writes no setup history
  • the view-model surface leaks no setup-field tokens
  • running the surface writes nothing to data/setup_history.json (content-hash)
  • SessionDB access stays read-only; Group 48/49 scoring stays deterministic

Runner/VM tests are pure (SQLite `:memory:`); UI guarantees are source-verified so
no QApplication is constructed.
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
from strategy.race_strategy_scorer import recommend_strategy, score_candidates  # noqa: E402
from ui.race_strategy_vm import (  # noqa: E402
    RacePlanViewModel,
    run_race_plan_from_session,
    build_race_plan_view_model,
)


def _seed(db, *, fuel=4.0, n=12):
    sid = db.open_session(car_id=911, track="Fuji Speedway", session_type="Practice", car_name="RSR")
    remaining = 100.0
    for i in range(n):
        db.write_lap(session_id=sid, lap_num=i + 1, lap_time_ms=100000 + i * 80,
                     fuel_used=fuel, stats=None, compound="RM",
                     fuel_start=remaining, fuel_end=remaining - fuel)
        remaining -= fuel
    return sid


def _kwargs(**over):
    kw = dict(
        car_id=911, track="Fuji Speedway", race_duration_minutes=50.0,
        fuel_multiplier=3.0, tyre_multiplier=8.0, refuel_rate_lps=1.0,
        pit_loss_seconds=22.0, available_compounds=("RM", "RH"),
    )
    kw.update(over)
    return kw


_SETUP_FIELD_TOKENS = (
    "ride_height", "springs", "damper", "arb", "camber", "toe",
    "aero_front", "aero_rear", "lsd", "brake_bias", "ballast",
    "power_restrictor", "final_drive", "gear_ratio", "approved_fields",
    "setup_fields", "approved_changes",
)


def _hash(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def _dash():
    return (ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8")


def _race_plan_method():
    src = _dash()
    start = src.index("def _run_race_plan(self)")
    end = src.index("\n    def ", start + 1)
    return src[start:end]


def _race_plan_group():
    src = _dash()
    start = src.index("def _build_race_plan_group(self)")
    end = src.index("\n    def ", start + 1)
    return src[start:end]


class TestSetupGuaranteesUntouched:
    def test_apply_gate_predicate_unchanged(self):
        src = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
        assert "_status_approved and bool(_parsed_ai_fields) and not _is_legacy" in src

    def test_old_ai_build_path_still_disabled(self):
        src = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
        assert "the from-scratch AI build path was removed" in src


class TestRacePlanSurfaceHasNoSetupPower:
    def test_method_no_apply_no_setup_history(self):
        body = _race_plan_method()
        for banned in ("setup_history", "_finalise_recommendation", "apply_ai_fields",
                       "save_entry", "insert_setup_recommendations", "api_key"):
            assert banned not in body, f"{banned} present in _run_race_plan"

    def test_group_no_apply_or_approve_controls(self):
        # The disclaimer text may say "cannot apply a setup"; what must be absent
        # is any actual apply/approve CAPABILITY (button + setup-write plumbing).
        body = _race_plan_group()
        for banned in ("apply_ai_fields", "_finalise_recommendation", "setup_fields",
                       "insert_setup_recommendations", "save_entry", "_btn_apply",
                       "approved_fields"):
            assert banned not in body

    def test_vm_result_surface_has_no_setup_tokens(self):
        db = SessionDB(":memory:")
        vm = run_race_plan_from_session(db, session_id=_seed(db), **_kwargs())
        assert isinstance(vm, RacePlanViewModel)
        names = set(vars(vm).keys())
        for token in _SETUP_FIELD_TOKENS:
            assert not any(token in n for n in names)
        blob = (" ".join(vm.risk_flags) + " " + " ".join(vm.safety_notes)
                + " " + vm.driver_explanation).lower()
        for token in ("approved_fields", "setup_fields", "apply setup", "approve setup"):
            assert token not in blob

    def test_vm_has_no_apply_capability(self):
        db = SessionDB(":memory:")
        vm = run_race_plan_from_session(db, session_id=_seed(db), **_kwargs())
        for banned in ("apply", "approve", "approved_fields", "setup_fields", "write"):
            assert not hasattr(vm, banned)


class TestNoRuntimeWrites:
    def test_running_surface_does_not_write_setup_history(self):
        target = ROOT / "data" / "setup_history.json"
        before = _hash(target)
        db = SessionDB(":memory:")
        run_race_plan_from_session(db, session_id=_seed(db), **_kwargs())
        assert _hash(target) == before

    def test_vm_module_imports_no_setup_authoring(self):
        import ui.race_strategy_vm as m
        src = Path(m.__file__).read_text(encoding="utf-8")
        for banned in ("setup_plan", "setup_rule_engine", "setup_ai_audit",
                       "setup_knowledge_base", "setup_baseline"):
            assert banned not in src


class TestSessionDbReadOnly:
    def test_adapter_only_reads(self):
        # A DB exposing only the two read methods must still work end-to-end.
        class ReadOnlyDB:
            def __init__(self, inner):
                self._inner = inner
            def get_session_meta(self, sid):
                return self._inner.get_session_meta(sid)
            def get_session_laps(self, sid, exclude_pit=False, exclude_out=False):
                return self._inner.get_session_laps(sid, exclude_pit=exclude_pit, exclude_out=exclude_out)

        inner = SessionDB(":memory:")
        sid = _seed(inner)
        ro = ReadOnlyDB(inner)
        vm = run_race_plan_from_session(ro, session_id=sid, **_kwargs())
        assert vm.has_recommendation
        assert not hasattr(ro, "write_lap")


class TestDeterministicScoringStillPasses:
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

    def test_vm_deterministic(self):
        db = SessionDB(":memory:")
        sid = _seed(db)
        v1 = run_race_plan_from_session(db, session_id=sid, **_kwargs())
        v2 = run_race_plan_from_session(db, session_id=sid, **_kwargs())
        assert v1.recommended_strategy_title == v2.recommended_strategy_title
        assert v1.estimated_total_time == v2.estimated_total_time
        assert [r["total_time"] for r in v1.candidate_comparison_rows] == \
               [r["total_time"] for r in v2.candidate_comparison_rows]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
