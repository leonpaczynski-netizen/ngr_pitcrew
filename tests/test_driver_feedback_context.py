"""Phase 2 — DrivingAdvisor._get_driver_feedback_context.

Covers the feedback restructure:
- the free_text→notes bug fix (notes were silently dropped from the prompt);
- the moved subjective rating surfacing as DRIVER LIKED / DRIVER HATED;
- applied-ness derived from lap setup tags (not a manual checkbox).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.session_db import SessionDB  # noqa: E402
import strategy.driving_advisor as da  # noqa: E402


@pytest.fixture
def db():
    d = SessionDB(":memory:")
    yield d
    d.close()


def _make_advisor(db, car_id: int, track: str):
    adv = da.DrivingAdvisor.__new__(da.DrivingAdvisor)
    adv._db = db
    adv._car_id_ref = [car_id]
    adv._config = {"strategy": {"track": track}}
    return adv


def _insert_lap(db, session_id, lap_num, setup_id):
    with db._lock:
        db._conn.execute(
            """INSERT INTO lap_records
               (session_id, car_id, track, lap_num, lap_time_ms, fuel_used,
                lock_up_count, wheelspin_count, brake_consistency_m,
                max_speed_kmh, avg_throttle_pct, avg_brake_pct, setup_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (session_id, 0, "", lap_num, 92_000, 2.0, 0, 0, -1.0, 0.0, 0.0, 0.0, setup_id),
        )
        db._conn.commit()


def test_no_feedback_returns_empty(db):
    adv = _make_advisor(db, 1, "Fuji")
    assert adv._get_driver_feedback_context() == ""


def test_notes_are_included(db):
    # Regression: the old code read row["free_text"] (a non-existent column) so
    # notes never reached the prompt.
    sid = db.open_session(car_id=1, track="Fuji", session_type="Practice")
    db.write_feedback(session_id=sid, lap_num=1,
                      feedback={"notes": "rear steps out mid-corner"})
    adv = _make_advisor(db, 1, "Fuji")
    out = adv._get_driver_feedback_context()
    assert "rear steps out mid-corner" in out


def test_liked_rating_with_applied_annotation(db):
    sid = db.open_session(car_id=2, track="Suzuka", session_type="Practice")
    _insert_lap(db, sid, 1, 42)
    _insert_lap(db, sid, 2, 42)
    db.write_feedback(session_id=sid, lap_num=2, feedback={"notes": ""},
                      setup_id=42, rating="liked")
    adv = _make_advisor(db, 2, "Suzuka")
    out = adv._get_driver_feedback_context()
    assert "DRIVER LIKED" in out
    assert "applied" in out and "2 laps" in out


def test_hated_rating_without_tagged_laps_has_no_applied_note(db):
    sid = db.open_session(car_id=3, track="Monza", session_type="Practice")
    db.write_feedback(session_id=sid, lap_num=1, feedback={"notes": ""},
                      setup_id=99, rating="hated")
    adv = _make_advisor(db, 3, "Monza")
    out = adv._get_driver_feedback_context()
    assert "DRIVER HATED" in out
    assert "applied" not in out  # no laps tagged with setup 99


def test_neutral_rating_emits_no_directive(db):
    sid = db.open_session(car_id=4, track="Spa", session_type="Practice")
    db.write_feedback(session_id=sid, lap_num=1, feedback={"corner_entry": "Good balance"},
                      setup_id=5, rating="neutral")
    adv = _make_advisor(db, 4, "Spa")
    out = adv._get_driver_feedback_context()
    assert "DRIVER LIKED" not in out
    assert "DRIVER HATED" not in out
    assert "corner entry: Good balance" in out
