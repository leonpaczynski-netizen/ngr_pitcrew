"""OFR-2 — SessionDB additions.

Covers:
- get_session_laps rows now carry snap_throttle_count and brake_consistency_m
- get_session_type round-trip (existing session)
- get_session_type missing-id defaults to ''
- get_session_type with session_id=0 returns ''
- OFR-1 non-collision: data/recommendation_scoring.py byte-unchanged
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db():
    from data.session_db import SessionDB
    return SessionDB(":memory:")


def _insert_lap_direct(db, session_id, lap_num, lap_time_ms,
                       snap_throttle=3, brake_con=2.5):
    """Direct SQL insert bypassing LapStats for isolation."""
    with db._lock:
        db._conn.execute(
            """INSERT INTO lap_records
               (session_id, car_id, track, lap_num, lap_time_ms, fuel_used,
                lock_up_count, wheelspin_count, brake_consistency_m,
                snap_throttle_count,
                max_speed_kmh, avg_throttle_pct, avg_brake_pct)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (session_id, 0, "", lap_num, lap_time_ms, 2.0,
             1, 0, brake_con, snap_throttle, 0.0, 0.0, 0.0),
        )
        db._conn.commit()


# ---------------------------------------------------------------------------
# get_session_laps new columns
# ---------------------------------------------------------------------------

class TestGetSessionLapsNewColumns:
    def test_snap_throttle_count_key_present(self):
        db = _make_db()
        sid = db.open_session(car_id=0, track="Suzuka", session_type="Qualifying")
        _insert_lap_direct(db, sid, 1, 90_000, snap_throttle=5)
        rows = db.get_session_laps(sid)
        assert len(rows) == 1
        assert "snap_throttle_count" in rows[0], (
            "snap_throttle_count must be present in get_session_laps rows"
        )

    def test_brake_consistency_m_key_present(self):
        db = _make_db()
        sid = db.open_session(car_id=0, track="Spa", session_type="Race")
        _insert_lap_direct(db, sid, 1, 120_000, brake_con=3.5)
        rows = db.get_session_laps(sid)
        assert "brake_consistency_m" in rows[0], (
            "brake_consistency_m must be present in get_session_laps rows"
        )

    def test_snap_throttle_count_value_correct(self):
        db = _make_db()
        sid = db.open_session(car_id=0, track="Monza", session_type="Practice")
        _insert_lap_direct(db, sid, 1, 88_000, snap_throttle=7)
        rows = db.get_session_laps(sid)
        assert rows[0]["snap_throttle_count"] == 7

    def test_brake_consistency_m_value_correct(self):
        db = _make_db()
        sid = db.open_session(car_id=0, track="Monza", session_type="Practice")
        _insert_lap_direct(db, sid, 1, 88_000, brake_con=4.75)
        rows = db.get_session_laps(sid)
        assert abs(rows[0]["brake_consistency_m"] - 4.75) < 0.001

    def test_brake_consistency_m_minus_one_default(self):
        """When brake_consistency_m was inserted as -1 (unavailable) it is preserved."""
        db = _make_db()
        sid = db.open_session(car_id=0, track="Fuji", session_type="Qualifying")
        _insert_lap_direct(db, sid, 1, 92_000, brake_con=-1.0)
        rows = db.get_session_laps(sid)
        assert rows[0]["brake_consistency_m"] == -1.0

    def test_existing_columns_still_present(self):
        """Legacy columns must not have been removed."""
        db = _make_db()
        sid = db.open_session(car_id=0, track="Spa", session_type="Race")
        _insert_lap_direct(db, sid, 1, 120_000)
        rows = db.get_session_laps(sid)
        row = rows[0]
        for col in (
            "lap_num", "lap_time_ms", "fuel_used", "is_pit_lap", "is_out_lap",
            "lock_up_count", "wheelspin_count", "oversteer_count",
            "max_lat_g", "tyre_temp_fl_avg", "tyre_temp_fr_avg",
            "tyre_temp_rl_avg", "tyre_temp_rr_avg",
        ):
            assert col in row, f"{col} missing from get_session_laps row"


# ---------------------------------------------------------------------------
# get_session_type
# ---------------------------------------------------------------------------

class TestGetSessionType:
    def test_returns_session_type_for_existing_session(self):
        db = _make_db()
        sid = db.open_session(car_id=1, track="Fuji", session_type="Qualifying")
        result = db.get_session_type(sid)
        assert result == "Qualifying"

    def test_returns_race_session_type(self):
        db = _make_db()
        sid = db.open_session(car_id=2, track="Spa", session_type="Race")
        result = db.get_session_type(sid)
        assert result == "Race"

    def test_returns_practice_session_type(self):
        db = _make_db()
        sid = db.open_session(car_id=0, track="Monza", session_type="Practice")
        result = db.get_session_type(sid)
        assert result == "Practice"

    def test_returns_empty_string_for_missing_id(self):
        db = _make_db()
        result = db.get_session_type(99999)
        assert result == ""

    def test_returns_empty_string_for_zero_id(self):
        db = _make_db()
        result = db.get_session_type(0)
        assert result == ""

    def test_returns_empty_string_for_negative_id(self):
        db = _make_db()
        result = db.get_session_type(-1)
        assert result == ""

    def test_never_raises(self):
        db = _make_db()
        # Should not raise even on pathological input
        try:
            result = db.get_session_type(None)  # type: ignore
        except Exception as e:
            pytest.fail(f"get_session_type raised: {e}")

    def test_return_type_is_str(self):
        db = _make_db()
        result = db.get_session_type(0)
        assert isinstance(result, str)

    def test_unknown_session_type_stored_and_returned(self):
        db = _make_db()
        sid = db.open_session(car_id=0, track="Test", session_type="")
        result = db.get_session_type(sid)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# OFR-1 non-collision: recommendation_scoring.py byte-unchanged
# ---------------------------------------------------------------------------

class TestOFR1NonCollision:
    EXPECTED_HASH = "0fbd7d07c0dfc23c"

    def test_recommendation_scoring_byte_unchanged(self):
        path = ROOT / "data" / "recommendation_scoring.py"
        data = path.read_bytes()
        actual = hashlib.sha256(data).hexdigest()[:16]
        assert actual == self.EXPECTED_HASH, (
            f"data/recommendation_scoring.py was modified (OFR-1 non-collision breach). "
            f"Expected sha256[:16]={self.EXPECTED_HASH}, got {actual}"
        )
