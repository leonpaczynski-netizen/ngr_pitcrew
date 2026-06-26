"""Tests for is_pit_lap handling in SessionDB — Group 21B."""
import pytest
from data.session_db import SessionDB


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    d = SessionDB(":memory:")
    yield d
    d.close()


def _open_session(db: SessionDB) -> int:
    return db.open_session(car_id=1, track="Monza", session_type="Race")


def _write_lap(db: SessionDB, session_id: int, lap_num: int, lap_time_ms: int,
               is_pit_lap: bool = False, fuel_used: float = 2.5) -> int:
    return db.write_lap(
        session_id=session_id,
        lap_num=lap_num,
        lap_time_ms=lap_time_ms,
        fuel_used=fuel_used,
        stats=None,
        is_pit_lap=is_pit_lap,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_write_pit_lap_stored_as_1(db):
    """A lap written with is_pit_lap=True should be stored as 1 in the DB."""
    sid = _open_session(db)
    _write_lap(db, sid, lap_num=1, lap_time_ms=90_000, is_pit_lap=True)

    rows = db.get_session_laps(sid)
    assert len(rows) == 1
    assert rows[0]["is_pit_lap"] == 1


def test_get_best_lap_excludes_pit_laps(db):
    """get_best_lap_for_session() must exclude pit laps even when they are faster."""
    sid = _open_session(db)
    # A faster pit lap (should be excluded)
    _write_lap(db, sid, lap_num=1, lap_time_ms=80_000, is_pit_lap=True)
    # A normal lap
    _write_lap(db, sid, lap_num=2, lap_time_ms=95_000, is_pit_lap=False)

    best = db.get_best_lap_for_session(sid)
    assert best == 95_000


def test_fuel_calculation_excludes_pit_laps(db):
    """get_recent_fuel_sequence() already filters is_pit_lap = 0."""
    sid = _open_session(db)
    _write_lap(db, sid, 1, 90_000, is_pit_lap=False, fuel_used=2.0)
    _write_lap(db, sid, 2, 91_000, is_pit_lap=True,  fuel_used=10.0)  # pit stop refuel
    _write_lap(db, sid, 3, 89_500, is_pit_lap=False, fuel_used=2.1)

    fuel_seq = db.get_recent_fuel_sequence(car_id=1, track="Monza")
    # Only non-pit laps should appear
    assert all(f < 5.0 for f in fuel_seq), f"Pit lap fuel leaked into sequence: {fuel_seq}"


def test_all_pit_laps_best_lap_returns_none(db):
    """When every lap in a session is a pit lap, get_best_lap_for_session() returns None."""
    sid = _open_session(db)
    _write_lap(db, sid, 1, 80_000, is_pit_lap=True)
    _write_lap(db, sid, 2, 85_000, is_pit_lap=True)

    best = db.get_best_lap_for_session(sid)
    assert best is None
