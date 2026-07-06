"""Group 51 — session selection / diagnostics tests.

Covers `build_session_diagnostics` and `list_recent_matching_sessions`:
  • selected session id / "No session selected" shown honestly
  • car/track/layout match shown; mismatch detected + messaged
  • clean lap count / fuel / tyre proxy availability shown
  • recent matching sessions filtered by car+track; selector stays read-only

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
from ui.race_strategy_readiness_vm import (  # noqa: E402
    build_session_diagnostics,
    list_recent_matching_sessions,
    SessionSummary,
    CheckStatus,
)


def _seed(db, *, car_id=911, track="Fuji Speedway", n=12, fuel=4.0):
    sid = db.open_session(car_id=car_id, track=track, session_type="Practice", car_name="RSR")
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


class TestDiagnostics:
    def test_no_session_reported_honestly(self):
        d = build_session_diagnostics(None, event_car_id=911, event_track="Fuji Speedway")
        assert d.session_id == 0
        assert d.session_label == "No session selected"
        assert d.matches_event == CheckStatus.NA
        assert "event settings only" in d.message.lower()

    def test_selected_session_id_shown(self, db):
        sid = _seed(db)
        s = extract_session_strategy_samples(db, sid, expected_car_id=911, expected_track="Fuji Speedway")
        d = build_session_diagnostics(s, event_car_id=911, event_track="Fuji Speedway")
        assert d.session_id == sid
        assert f"{sid}" in d.session_label

    def test_match_ok(self, db):
        sid = _seed(db)
        s = extract_session_strategy_samples(db, sid, expected_car_id=911, expected_track="Fuji Speedway")
        d = build_session_diagnostics(s, event_car_id=911, event_track="Fuji Speedway")
        assert d.matches_event == CheckStatus.OK
        assert d.car_id == 911
        assert d.track == "Fuji Speedway"

    def test_mismatch_detected_and_messaged(self, db):
        sid = _seed(db, car_id=911, track="Fuji Speedway")
        s = extract_session_strategy_samples(db, sid, expected_car_id=222, expected_track="Suzuka")
        d = build_session_diagnostics(s, event_car_id=222, event_track="Suzuka")
        assert d.matches_event == CheckStatus.MISMATCH
        assert "different car or track" in d.message.lower()

    def test_clean_laps_and_evidence_flags(self, db):
        sid = _seed(db)
        s = extract_session_strategy_samples(db, sid, expected_car_id=911, expected_track="Fuji Speedway")
        d = build_session_diagnostics(s, event_car_id=911, event_track="Fuji Speedway")
        assert d.clean_lap_count == 12
        assert d.fuel_available is True
        assert d.tyre_proxy_available is True
        assert d.compound_available is True

    def test_session_not_found(self, db):
        s = extract_session_strategy_samples(db, 999)
        d = build_session_diagnostics(s, event_car_id=911, event_track="Fuji Speedway")
        assert "not found" in d.message.lower()

    def test_no_clean_laps_message(self, db):
        # A session whose only laps are pit laps → 0 clean laps.
        sid = db.open_session(car_id=911, track="Fuji Speedway", session_type="Practice", car_name="RSR")
        db.write_lap(session_id=sid, lap_num=1, lap_time_ms=100000, fuel_used=4.0,
                     stats=None, compound="RM", is_pit_lap=True)
        s = extract_session_strategy_samples(db, sid, expected_car_id=911, expected_track="Fuji Speedway")
        d = build_session_diagnostics(s, event_car_id=911, event_track="Fuji Speedway")
        assert d.clean_lap_count == 0
        assert "no clean laps" in d.message.lower()


class TestRecentSessions:
    def test_lists_recent_matching(self, db):
        _seed(db, n=10)
        _seed(db, n=8)
        out = list_recent_matching_sessions(db, 911, "Fuji Speedway")
        assert len(out) == 2
        assert all(isinstance(s, SessionSummary) for s in out)
        assert all("Session" in s.label for s in out)

    def test_filters_by_car_and_track(self, db):
        _seed(db, car_id=911, track="Fuji Speedway")
        _seed(db, car_id=222, track="Suzuka")
        out = list_recent_matching_sessions(db, 911, "Fuji Speedway")
        assert len(out) == 1
        assert out[0].total_laps == 12

    def test_empty_on_unknown_car_track(self, db):
        assert list_recent_matching_sessions(db, 0, "") == []
        assert list_recent_matching_sessions(None, 911, "Fuji Speedway") == []

    def test_read_only_no_write_methods_used(self, db):
        # A DB exposing only get_practice_sessions must still work → proves read-only.
        class RO:
            def __init__(self, inner):
                self._inner = inner
            def get_practice_sessions(self, car_id, track):
                return self._inner.get_practice_sessions(car_id, track)
        _seed(db)
        out = list_recent_matching_sessions(RO(db), 911, "Fuji Speedway")
        assert len(out) == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
