"""Group 51 — Race Plan readiness / evidence-checklist tests.

Covers ui/race_strategy_readiness_vm.py `build_race_plan_readiness`:
  • READY / PARTIAL / LOW_CONFIDENCE / INSUFFICIENT_EVIDENCE grading
  • next_best_action is specific and actionable
  • found/missing are honest; no fake evidence is created

All tests are pure/offline (SQLite `:memory:` + the read-only adapter).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.session_db import SessionDB  # noqa: E402
from strategy.race_strategy_session_adapter import extract_session_strategy_samples  # noqa: E402
from ui.race_strategy_readiness_vm import (  # noqa: E402
    build_race_plan_readiness,
    ReadinessLevel,
    CheckStatus,
    MIN_CLEAN_LAPS,
)


def _seed(db, *, n=12, fuel=4.0, compound="RM"):
    sid = db.open_session(car_id=911, track="Fuji Speedway", session_type="Practice", car_name="RSR")
    remaining = 100.0
    for i in range(n):
        db.write_lap(session_id=sid, lap_num=i + 1, lap_time_ms=100000 + i * 80,
                     fuel_used=fuel, stats=None, compound=compound,
                     fuel_start=remaining, fuel_end=remaining - fuel)
        remaining -= fuel
    return sid


def _samples(db, sid):
    return extract_session_strategy_samples(db, sid, expected_car_id=911, expected_track="Fuji Speedway")


def _es(**over):
    es = dict(
        car_id=911, track="Fuji Speedway", layout_id="fuji__full",
        race_duration_minutes=50.0, race_laps=0,
        fuel_multiplier=3.0, tyre_multiplier=8.0,
        refuel_rate_lps=1.0, pit_loss_seconds=22.0, starting_fuel_pct=100.0,
        required_compounds=(), mandatory_pit_stops=0,
    )
    es.update(over)
    return es


@pytest.fixture()
def db():
    yield SessionDB(":memory:")


class TestLevels:
    def test_ready_with_full_evidence(self, db):
        r = build_race_plan_readiness(samples=_samples(db, _seed(db)), event_settings=_es())
        assert r.overall_readiness == ReadinessLevel.READY
        assert "Ready" in r.readiness_message
        assert not r.missing

    def test_partial_when_no_compound_tags(self, db):
        # Untagged laps → no per-compound pace, but tyre proxy still derives.
        r = build_race_plan_readiness(samples=_samples(db, _seed(db, compound="")), event_settings=_es())
        assert r.overall_readiness == ReadinessLevel.PARTIAL
        assert "compound-tagged laps" in r.missing

    def test_low_confidence_when_refuel_missing(self, db):
        r = build_race_plan_readiness(samples=_samples(db, _seed(db)),
                                      event_settings=_es(refuel_rate_lps=0.0))
        assert r.overall_readiness == ReadinessLevel.LOW_CONFIDENCE
        assert r.refuel_rate_status == CheckStatus.MISSING

    def test_low_confidence_when_pit_loss_missing(self, db):
        r = build_race_plan_readiness(samples=_samples(db, _seed(db)),
                                      event_settings=_es(pit_loss_seconds=0.0))
        assert r.overall_readiness == ReadinessLevel.LOW_CONFIDENCE
        assert r.pit_loss_status == CheckStatus.MISSING

    def test_insufficient_when_no_session(self, db):
        r = build_race_plan_readiness(samples=None, event_settings=_es())
        assert r.overall_readiness == ReadinessLevel.INSUFFICIENT_EVIDENCE
        assert r.session_status == CheckStatus.MISSING

    def test_insufficient_when_below_min_clean_laps(self, db):
        r = build_race_plan_readiness(samples=_samples(db, _seed(db, n=2)), event_settings=_es())
        assert r.overall_readiness == ReadinessLevel.INSUFFICIENT_EVIDENCE
        assert MIN_CLEAN_LAPS == 3

    def test_insufficient_when_no_race_length(self, db):
        r = build_race_plan_readiness(samples=_samples(db, _seed(db)),
                                      event_settings=_es(race_duration_minutes=0.0, race_laps=0))
        assert r.overall_readiness == ReadinessLevel.INSUFFICIENT_EVIDENCE

    def test_mismatch_marks_match_status(self, db):
        sid = _seed(db)
        s = extract_session_strategy_samples(db, sid, expected_car_id=222, expected_track="Suzuka")
        r = build_race_plan_readiness(samples=s, event_settings=_es())
        assert r.car_track_layout_match_status == CheckStatus.MISMATCH
        assert r.overall_readiness == ReadinessLevel.INSUFFICIENT_EVIDENCE


class TestGuidance:
    def test_next_best_action_specific_for_no_laps(self, db):
        r = build_race_plan_readiness(samples=None, event_settings=_es())
        assert "clean" in r.next_best_action.lower()
        assert str(MIN_CLEAN_LAPS) in r.next_best_action

    def test_next_best_action_for_missing_tyre(self, db):
        r = build_race_plan_readiness(samples=_samples(db, _seed(db, n=2)), event_settings=_es())
        # 2 clean laps → laps still below min, so the action targets laps first.
        assert r.next_best_action

    def test_next_best_action_ready(self, db):
        r = build_race_plan_readiness(samples=_samples(db, _seed(db)), event_settings=_es())
        assert "good" in r.next_best_action.lower()

    def test_next_best_action_for_mismatch(self, db):
        sid = _seed(db)
        s = extract_session_strategy_samples(db, sid, expected_car_id=222, expected_track="Suzuka")
        r = build_race_plan_readiness(samples=s, event_settings=_es())
        assert "different car or track" in r.next_best_action.lower()


class TestHonesty:
    def test_missing_not_hidden(self, db):
        r = build_race_plan_readiness(samples=_samples(db, _seed(db)),
                                      event_settings=_es(pit_loss_seconds=0.0))
        assert "measured pit loss" in r.missing

    def test_no_fake_evidence_when_empty(self, db):
        # With no session, session-derived evidence must NOT be fabricated. Event
        # settings (refuel/pit loss) legitimately remain "found" — they are known.
        r = build_race_plan_readiness(samples=None, event_settings=_es())
        assert r.lap_sample_status == CheckStatus.MISSING
        assert r.fuel_sample_status == CheckStatus.MISSING
        joined = " ".join(r.found).lower()
        assert "clean laps from sessiondb" not in joined
        assert "fuel use from" not in joined
        assert "derived lap-drift proxy" not in joined

    def test_never_raises_on_garbage(self):
        r = build_race_plan_readiness(samples=None, event_settings={"race_laps": "nonsense"})
        assert r.overall_readiness == ReadinessLevel.INSUFFICIENT_EVIDENCE


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
