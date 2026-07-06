"""Group 51 — empty / missing-evidence state message tests.

Covers `empty_state_messages` (and `strategy_result_message`): short, clear,
actionable driver-readable lines for every detected input problem, and the
result-level "no recommendation" reason. No vague "strategy failed" wording.

All tests are pure/offline (SQLite `:memory:`).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.session_db import SessionDB  # noqa: E402
from strategy.race_strategy_session_adapter import extract_session_strategy_samples  # noqa: E402
from strategy.race_strategy_pipeline import recommend_strategy_from_session  # noqa: E402
from ui.race_strategy_readiness_vm import (  # noqa: E402
    empty_state_messages,
    strategy_result_message,
)


def _seed(db, *, car_id=911, track="Fuji Speedway", n=12, fuel=4.0, compound="RM"):
    sid = db.open_session(car_id=car_id, track=track, session_type="Practice", car_name="RSR")
    remaining = 100.0
    for i in range(n):
        db.write_lap(session_id=sid, lap_num=i + 1, lap_time_ms=100000 + i * 80,
                     fuel_used=fuel, stats=None, compound=compound,
                     fuel_start=remaining, fuel_end=remaining - fuel)
        remaining -= fuel
    return sid


def _es(**over):
    es = dict(
        car_id=911, track="Fuji Speedway", race_duration_minutes=50.0, race_laps=0,
        fuel_multiplier=3.0, tyre_multiplier=8.0, refuel_rate_lps=1.0,
        pit_loss_seconds=22.0, available_compounds=("RM", "RH"),
    )
    es.update(over)
    return es


def _samples(db, sid, car=911, track="Fuji Speedway"):
    return extract_session_strategy_samples(db, sid, expected_car_id=car, expected_track=track)


@pytest.fixture()
def db():
    yield SessionDB(":memory:")


def _joined(msgs):
    return " || ".join(msgs).lower()


class TestSessionStates:
    def test_no_session_selected(self, db):
        msgs = empty_state_messages(None, _es())
        assert any("no session selected" in m.lower() for m in msgs)

    def test_session_not_found(self, db):
        msgs = empty_state_messages(_samples(db, 999), _es())
        assert any("session not found" in m.lower() for m in msgs)

    def test_car_mismatch(self, db):
        sid = _seed(db)
        s = extract_session_strategy_samples(db, sid, expected_car_id=222, expected_track="Suzuka")
        msgs = empty_state_messages(s, _es())
        assert any("different car or track" in m.lower() for m in msgs)

    def test_no_clean_laps(self, db):
        sid = db.open_session(car_id=911, track="Fuji Speedway", session_type="Practice", car_name="RSR")
        db.write_lap(session_id=sid, lap_num=1, lap_time_ms=100000, fuel_used=4.0,
                     stats=None, compound="RM", is_pit_lap=True)
        msgs = empty_state_messages(_samples(db, sid), _es())
        assert any("no clean laps" in m.lower() for m in msgs)

    def test_below_min_clean_laps(self, db):
        msgs = empty_state_messages(_samples(db, _seed(db, n=2)), _es())
        assert any("clean lap" in m.lower() for m in msgs)

    def test_fuel_missing(self, db):
        msgs = empty_state_messages(_samples(db, _seed(db, fuel=0.0)), _es())
        assert any("fuel" in m.lower() for m in msgs)

    def test_tyre_proxy_missing(self, db):
        msgs = empty_state_messages(_samples(db, _seed(db, n=2)), _es())
        assert any("tyre" in m.lower() for m in msgs)

    def test_compound_missing(self, db):
        msgs = empty_state_messages(_samples(db, _seed(db, compound="")), _es())
        assert any("tag" in m.lower() and "compound" in m.lower() for m in msgs)


class TestEventStates:
    def test_race_length_missing(self, db):
        msgs = empty_state_messages(_samples(db, _seed(db)),
                                    _es(race_duration_minutes=0.0, race_laps=0))
        assert any("race duration" in m.lower() for m in msgs)

    def test_refuel_missing(self, db):
        msgs = empty_state_messages(_samples(db, _seed(db)), _es(refuel_rate_lps=0.0))
        assert any("refuel rate" in m.lower() for m in msgs)

    def test_pit_loss_missing(self, db):
        msgs = empty_state_messages(_samples(db, _seed(db)), _es(pit_loss_seconds=0.0))
        assert any("pit loss" in m.lower() for m in msgs)


class TestQuality:
    def test_no_messages_when_all_good(self, db):
        assert empty_state_messages(_samples(db, _seed(db)), _es()) == []

    def test_messages_are_actionable_not_vague(self, db):
        msgs = empty_state_messages(None, _es(refuel_rate_lps=0.0, pit_loss_seconds=0.0))
        assert msgs
        text = _joined(msgs)
        assert "strategy failed" not in text
        # each message suggests a concrete action verb
        assert any(v in text for v in ("record", "set ", "enter", "measure", "select", "load", "tag"))

    def test_deduplicated(self, db):
        msgs = empty_state_messages(_samples(db, _seed(db, fuel=0.0)), _es())
        assert len(msgs) == len(set(msgs))


class TestResultMessage:
    def test_no_legal_candidates_surfaces_reason(self, db):
        # No session at all → INSUFFICIENT_EVIDENCE result with an honest reason.
        result = recommend_strategy_from_session(db, session_id=999, **_es())
        msg = strategy_result_message(result)
        assert msg
        assert "strategy failed" not in msg.lower()

    def test_empty_when_recommendation_exists(self, db):
        result = recommend_strategy_from_session(db, session_id=_seed(db), **_es())
        assert strategy_result_message(result) == ""


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
