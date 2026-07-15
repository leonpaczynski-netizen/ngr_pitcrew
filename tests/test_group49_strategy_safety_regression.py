"""Group 49 — Race Strategy Brain Phase 3: safety-regression tests.

Asserts the SessionDB integration does not weaken any Group 43-48 guarantee:
  • the Setup Apply-gate predicate is unchanged; old AI Build path stays disabled
  • the strategy pipeline authors no setup fields, has no apply/approve capability,
    and imports no setup-authoring module
  • running the pipeline writes nothing to data/setup_history.json (or any runtime file)
  • driver memory cannot flip strategy legality or change the scoring maths
  • Group 48 scoring remains deterministic

All tests are pure/offline (SQLite `:memory:`).
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.session_db import SessionDB  # noqa: E402
from strategy.race_strategy_candidates import Legality, generate_candidates, legal_candidates  # noqa: E402
from strategy.race_strategy_evidence import build_strategy_evidence  # noqa: E402
from strategy.race_strategy_scorer import recommend_strategy, score_candidates  # noqa: E402
from strategy.race_strategy_pipeline import (  # noqa: E402
    recommend_strategy_from_session,
    SessionStrategyResult,
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


def _run(db, sid, **over):
    kw = dict(
        car_id=911, track="Fuji Speedway", race_duration_minutes=50.0,
        fuel_multiplier=3.0, tyre_multiplier=8.0, refuel_rate_lps=1.0,
        pit_loss_seconds=22.0, available_compounds=("RM", "RH"),
    )
    kw.update(over)
    return recommend_strategy_from_session(db, session_id=sid, **kw)


_SETUP_FIELD_TOKENS = (
    "ride_height", "springs", "damper", "arb", "camber", "toe",
    "aero_front", "aero_rear", "lsd", "brake_bias", "ballast",
    "power_restrictor", "final_drive", "gear_ratio", "approved_fields",
    "setup_fields", "approved_changes",
)


class TestSetupGuaranteesUntouched:
    def test_apply_gate_predicate_unchanged(self):
        src = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
        assert "_status_approved and bool(_parsed_ai_fields) and not _is_legacy" in src

    def test_old_ai_build_path_still_disabled(self):
        src = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
        assert "the from-scratch AI build path was removed" in src


class TestPipelineHasNoSetupPower:
    def test_result_has_no_apply_or_approve(self):
        db = SessionDB(":memory:")
        r = _run(db, _seed(db))
        assert isinstance(r, SessionStrategyResult)
        for banned in ("apply", "approve", "approved_fields", "setup_fields", "write"):
            assert not hasattr(r, banned)
            if r.recommendation.recommended is not None:
                assert not hasattr(r.recommendation.recommended, banned)

    def test_result_surface_has_no_setup_field_tokens(self):
        db = SessionDB(":memory:")
        r = _run(db, _seed(db))
        names = set()
        objs = [r, r.recommendation, r.recommendation.recommended, r.explanation,
                r.samples, *r.candidates, *r.scored_candidates]
        for obj in objs:
            if obj is None:
                continue
            names |= set(vars(obj).keys())
        for token in _SETUP_FIELD_TOKENS:
            assert not any(token in n for n in names), f"setup token {token} leaked"

    def test_group49_modules_import_no_setup_authoring(self):
        import strategy.race_strategy_pipeline as p
        import strategy.race_strategy_from_session as fs
        import strategy.race_strategy_session_adapter as ad
        import strategy.race_strategy_session_explain as ex
        import strategy.race_strategy_session_benchmark as bm
        for mod in (p, fs, ad, ex, bm):
            src = Path(mod.__file__).read_text(encoding="utf-8")
            for banned in ("setup_plan", "setup_rule_engine", "setup_ai_audit",
                           "setup_knowledge_base", "setup_baseline"):
                assert banned not in src, f"{mod.__file__} imports {banned}"


class TestNoRuntimeWrites:
    def test_pipeline_does_not_write_setup_history(self):
        target = ROOT / "data" / "setup_history.json"
        before = _hash(target)
        db = SessionDB(":memory:")
        _run(db, _seed(db))
        after = _hash(target)
        assert before == after, "data/setup_history.json changed during a strategy run"

    def test_modules_do_not_import_or_write_setup_history(self):
        # Docstrings may *mention* setup_history to state they never touch it; what
        # must be absent is an actual import of, or write call to, that module.
        import strategy.race_strategy_pipeline as p
        import strategy.race_strategy_from_session as fs
        import strategy.race_strategy_session_adapter as ad
        for mod in (p, fs, ad):
            src = Path(mod.__file__).read_text(encoding="utf-8")
            for line in src.splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                assert "import setup_history" not in stripped
                assert "from data.setup_history" not in stripped
                assert "setup_history.save" not in stripped
                assert "save_entry(" not in stripped


class TestLearningCannotOverrideMaths:
    def test_driver_memory_cannot_flip_legality(self):
        db = SessionDB(":memory:")
        sid = _seed(db, fuel=6.0)  # no-stop fuel-illegal
        rec_safe = _run(db, sid, rear_traction_fragile=True)
        rec_plain = _run(db, sid, rear_traction_fragile=False)
        assert rec_safe.recommendation.recommended.candidate_id != "nostop"
        assert rec_plain.recommendation.recommended.candidate_id != "nostop"
        legal_safe = {c.candidate_id for c in legal_candidates(list(rec_safe.candidates))}
        legal_plain = {c.candidate_id for c in legal_candidates(list(rec_plain.candidates))}
        assert legal_safe == legal_plain

    def test_driver_memory_cannot_change_total_time(self):
        db = SessionDB(":memory:")
        sid = _seed(db)
        a = {s.candidate_id: s.estimated_total_time_seconds
             for s in _run(db, sid, rear_traction_fragile=True).scored_candidates}
        b = {s.candidate_id: s.estimated_total_time_seconds
             for s in _run(db, sid, rear_traction_fragile=False).scored_candidates}
        assert a == b

    def test_pipeline_has_no_learning_parameter(self):
        import inspect
        sig = inspect.signature(recommend_strategy_from_session)
        params = set(sig.parameters)
        for banned in ("learning", "outcome_store", "rule_outcome_store", "learn"):
            assert banned not in params


class TestGroup48ScoringDeterministic:
    def test_scoring_deterministic(self):
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
        assert recommend_strategy(ev).recommended.candidate_id == recommend_strategy(ev).recommended.candidate_id


def _hash(path: Path):
    """Content hash of a file, or None when it does not exist."""
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
