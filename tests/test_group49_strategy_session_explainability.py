"""Group 49 — Race Strategy Brain Phase 3: session-aware explainability tests.

Covers strategy/race_strategy_session_explain.py + the additive Group 48
`StrategyExplanation.evidence_sources` field:
  • explanation shows what came from SessionDB, event settings, defaults, missing
  • confidence displayed; missing evidence displayed; no false certainty
  • no setup-field tokens surface as actionable changes
  • the Group 48 caller-sample explanation path is unchanged (evidence_sources empty)

All tests are pure/offline (SQLite `:memory:`).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.session_db import SessionDB  # noqa: E402
from strategy.race_strategy_evidence import build_strategy_evidence  # noqa: E402
from strategy.race_strategy_scorer import recommend_strategy  # noqa: E402
from strategy.race_strategy_explain import build_explanation  # noqa: E402
from strategy.race_strategy_session_explain import (  # noqa: E402
    build_session_explanation,
    evidence_source_lines,
)
from strategy.race_strategy_pipeline import recommend_strategy_from_session  # noqa: E402


def _seed(db, *, n=12, fuel=4.0):
    sid = db.open_session(car_id=911, track="Fuji Speedway", session_type="Practice", car_name="RSR")
    remaining = 100.0
    for i in range(n):
        db.write_lap(session_id=sid, lap_num=i + 1, lap_time_ms=100000 + i * 80,
                     fuel_used=fuel, stats=None, compound="RM",
                     fuel_start=remaining, fuel_end=remaining - fuel)
        remaining -= fuel
    return sid


@pytest.fixture()
def db():
    yield SessionDB(":memory:")


def _run(db, sid, **over):
    kw = dict(
        car_id=911, track="Fuji Speedway", race_duration_minutes=50.0,
        fuel_multiplier=3.0, tyre_multiplier=8.0, refuel_rate_lps=1.0,
        pit_loss_seconds=22.0, available_compounds=("RM", "RH"),
        rear_traction_fragile=True,
    )
    kw.update(over)
    return recommend_strategy_from_session(db, session_id=sid, **kw)


class TestSourceLines:
    def test_source_lines_from_summary(self):
        summary = {"fields": {
            "race_pace": "SessionDB measured (7 clean laps)",
            "fuel_use": "SessionDB measured (5 laps)",
            "tyre_degradation": "missing",
            "pit_loss": "event setting",
            "refuel_rate": "event setting",
            "weather": "assumed",
        }}
        lines = evidence_source_lines(summary)
        joined = "\n".join(lines)
        assert "Race pace: SessionDB measured (7 clean laps)" in joined
        assert "Tyre degradation: missing, confidence reduced" in joined
        assert "Refuel rate: event setting" in joined

    def test_source_lines_safe_on_garbage(self):
        assert evidence_source_lines({}) == []
        assert evidence_source_lines({"fields": None}) == []


class TestSessionExplanation:
    def test_shows_sessiondb_and_event_and_defaults(self, db):
        r = _run(db, _seed(db))
        text = r.explanation.to_text()
        assert "Evidence source" in text
        assert "SessionDB measured" in text          # measured
        assert "event setting" in text               # event
        assert "MEDIAN clean lap" in text            # assumption/default

    def test_confidence_and_missing_shown(self, db):
        # 2 laps → medium; still shows confidence + a plan.
        r = _run(db, _seed(db, n=2))
        text = r.explanation.to_text()
        assert "Confidence:" in text

    def test_missing_tyre_shown_when_absent(self, db):
        r = _run(db, _seed(db, n=2))  # too few laps → tyre proxy missing
        joined = "\n".join(r.explanation.evidence_sources)
        assert "Tyre degradation: missing" in joined

    def test_no_false_certainty(self, db):
        r = _run(db, _seed(db))
        text = r.explanation.to_text().lower()
        for banned in ("perfect strategy", "guaranteed", "the winning strategy",
                       "definitely the best", "flawless"):
            assert banned not in text

    def test_no_setup_field_tokens(self, db):
        r = _run(db, _seed(db))
        text = r.explanation.to_text().lower()
        for token in ("ride_height", "springs", "camber", "brake_bias",
                      "lsd_accel", "approved_fields", "setup_fields"):
            assert token not in text


class TestGroup48Unchanged:
    def test_caller_sample_explanation_has_empty_sources(self):
        # A Group 48 explanation built without session provenance must keep the
        # additive field empty and NOT render an "Evidence source" section.
        ev = build_strategy_evidence(
            track="Fuji", race_laps=20, fuel_multiplier=3.0, tyre_multiplier=8.0,
            refuel_rate_lps=1.0, pit_loss_seconds=22.0,
            available_compounds=("RM",),
            lap_time_samples=[100.0] * 8, fuel_use_samples=[4.0] * 4,
            tyre_wear_samples=[0.08] * 10,
        )
        exp = build_explanation(recommend_strategy(ev), ev)
        assert exp.evidence_sources == []
        assert "Evidence source" not in exp.to_text()

    def test_session_explanation_reuses_group48_builder(self, db):
        # build_session_explanation should equal build_explanation plus sources.
        r = _run(db, _seed(db))
        assert r.explanation.recommended_plan
        assert r.explanation.evidence_sources  # populated on the session path


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
