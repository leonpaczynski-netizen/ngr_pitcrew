"""Group 49 — Race Strategy Brain Phase 3: session-aware pipeline tests.

Covers strategy/race_strategy_pipeline.py against a REAL in-memory SessionDB:
  • loads samples → evidence → legal candidates → scoring → recommendation → explanation
  • ranks by total race time; excludes illegal strategies
  • applies the Group 48 safety-aware tie-break
  • surfaces missing evidence, warnings, and standing safety notes
  • imports no setup-authoring module

All tests are pure/offline (SQLite `:memory:`).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.session_db import SessionDB  # noqa: E402
from strategy.race_strategy_candidates import Legality  # noqa: E402
from strategy.race_strategy_evidence import StrategyConfidence  # noqa: E402
from strategy.race_strategy_pipeline import (  # noqa: E402
    SessionStrategyResult,
    recommend_strategy_from_session,
)


def _seed(db, *, car_id=911, track="Fuji Speedway", n=12, fuel=4.0, drift_ms=80):
    sid = db.open_session(car_id=car_id, track=track, session_type="Practice", car_name="RSR")
    remaining = 100.0
    for i in range(n):
        db.write_lap(session_id=sid, lap_num=i + 1, lap_time_ms=100000 + i * drift_ms,
                     fuel_used=fuel, stats=None, compound="RM",
                     fuel_start=remaining, fuel_end=remaining - fuel)
        remaining -= fuel
    return sid


@pytest.fixture()
def db():
    yield SessionDB(":memory:")


def _run(db, sid, **over):
    kw = dict(
        car_id=911, track="Fuji Speedway", layout_id="fuji__full",
        race_duration_minutes=50.0, fuel_multiplier=3.0, tyre_multiplier=8.0,
        refuel_rate_lps=1.0, pit_loss_seconds=22.0,
        available_compounds=("RM", "RH"), rear_traction_fragile=True,
    )
    kw.update(over)
    return recommend_strategy_from_session(db, session_id=sid, **kw)


class TestPipeline:
    def test_full_result_shape(self, db):
        r = _run(db, _seed(db))
        assert isinstance(r, SessionStrategyResult)
        assert r.samples.clean_lap_count == 12
        assert r.candidates
        assert r.scored_candidates
        assert r.recommendation.has_recommendation
        assert r.explanation.has_recommendation
        assert r.confidence in set(StrategyConfidence)

    def test_ranked_by_total_time(self, db):
        r = _run(db, _seed(db))
        times = [s.estimated_total_time_seconds for s in r.scored_candidates]
        assert times == sorted(times)

    def test_recommendation_is_legal(self, db):
        r = _run(db, _seed(db))
        rec_id = r.recommendation.recommended.candidate_id
        cand = next(c for c in r.candidates if c.candidate_id == rec_id)
        assert cand.legality_status == Legality.LEGAL

    def test_illegal_excluded_from_scored(self, db):
        # Heavy fuel makes a no-stop illegal → it must not be scored.
        r = _run(db, _seed(db, fuel=6.0))
        scored_ids = {s.candidate_id for s in r.scored_candidates}
        assert "nostop" not in scored_ids
        nostop = next(c for c in r.candidates if c.candidate_id == "nostop")
        assert nostop.legality_status == Legality.ILLEGAL

    def test_safety_tie_break_avoids_push(self, db):
        r = _run(db, _seed(db), rear_traction_fragile=True)
        assert r.recommendation.recommended.candidate_id != "2stop_push"

    def test_warnings_and_safety_notes_present(self, db):
        r = _run(db, _seed(db))
        assert r.safety_notes
        assert any("read-only" in n.lower() for n in r.safety_notes)
        # Tyre-wear derivation warning surfaces.
        assert any("proxy" in w.lower() for w in r.warnings)

    def test_missing_evidence_surfaced(self, db):
        # Two laps → no long-run → medium-ish; still produces a recommendation.
        r = _run(db, _seed(db, n=2))
        assert r.confidence != StrategyConfidence.HIGH

    def test_no_session_is_honest(self, db):
        r = _run(db, 999)
        assert not r.has_recommendation
        assert r.confidence == StrategyConfidence.INSUFFICIENT_EVIDENCE
        assert r.explanation.missing_evidence

    def test_explanation_names_sessiondb(self, db):
        r = _run(db, _seed(db))
        text = r.explanation.to_text()
        assert "SessionDB measured" in text
        assert "Evidence source" in text


class TestNoSetupImports:
    def test_pipeline_module_imports_no_setup_authoring(self):
        import strategy.race_strategy_pipeline as m
        import strategy.race_strategy_from_session as m2
        import strategy.race_strategy_session_adapter as m3
        for mod in (m, m2, m3):
            src = Path(mod.__file__).read_text(encoding="utf-8")
            for banned in ("setup_plan", "setup_rule_engine", "setup_ai_audit",
                           "setup_knowledge_base", "setup_baseline"):
                assert banned not in src, f"{mod.__file__} imports {banned}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
