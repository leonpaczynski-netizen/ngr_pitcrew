"""Tests for data/session_db.py using an in-memory SQLite database."""
import pytest
from data.session_db import SessionDB, ms_to_str


@pytest.fixture
def db():
    d = SessionDB(":memory:")
    yield d
    d.close()


# ---------------------------------------------------------------------------
# ms_to_str
# ---------------------------------------------------------------------------

def test_ms_to_str_zero():
    # ms_to_str returns an em-dash placeholder for invalid/zero values
    assert ms_to_str(0) == ms_to_str(-1)  # both invalid


def test_ms_to_str_negative():
    # Negative time is invalid — should not return a formatted time string
    result = ms_to_str(-1)
    assert ":" not in result  # no colon means it is the placeholder, not a formatted time


def test_ms_to_str_one_minute():
    assert ms_to_str(90_000) == "1:30.000"


def test_ms_to_str_sub_minute():
    assert ms_to_str(45_123) == "0:45.123"


def test_ms_to_str_large():
    # 2 minutes 3.456 seconds
    assert ms_to_str(123_456) == "2:03.456"


# ---------------------------------------------------------------------------
# open_session
# ---------------------------------------------------------------------------

def test_open_session_returns_positive_id(db):
    sid = db.open_session(
        car_id=1,
        track="Sardegna",
        session_type="Race",
        car_name="GR86",
        config_id="test-config",
    )
    assert sid > 0


def test_open_session_multiple_independent(db):
    sid1 = db.open_session(car_id=1, track="Nurburgring", session_type="Practice")
    sid2 = db.open_session(car_id=2, track="Brands Hatch", session_type="Race")
    assert sid1 != sid2


def test_get_all_sessions_includes_opened(db):
    sid = db.open_session(car_id=3, track="Tokyo", session_type="Race", car_name="M6")
    # get_all_sessions filters WHERE total_laps > 0 — insert a lap directly
    _insert_lap_direct(db, sid, 1, 92_000)
    with db._lock:
        db._conn.execute("UPDATE sessions SET total_laps=1 WHERE id=?", (sid,))
        db._conn.commit()
    sessions = db.get_all_sessions(limit=10)
    assert len(sessions) >= 1
    assert any(s["track"] == "Tokyo" for s in sessions)


# ---------------------------------------------------------------------------
# get_session_laps — insert row directly since write_lap requires LapStats
# ---------------------------------------------------------------------------

def _insert_lap_direct(db, session_id, lap_num, lap_time_ms):
    """Helper: bypass write_lap (which requires LapStats) by direct SQL insert."""
    with db._lock:
        db._conn.execute(
            """INSERT INTO lap_records
               (session_id, car_id, track, lap_num, lap_time_ms, fuel_used,
                lock_up_count, wheelspin_count, brake_consistency_m,
                max_speed_kmh, avg_throttle_pct, avg_brake_pct)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (session_id, 0, "", lap_num, lap_time_ms, 2.0, 0, 0, -1.0, 0.0, 0.0, 0.0),
        )
        db._conn.commit()


def test_get_session_laps(db):
    sid = db.open_session(car_id=1, track="Fuji", session_type="Race")
    _insert_lap_direct(db, sid, 1, 92_345)
    _insert_lap_direct(db, sid, 2, 91_800)

    laps = db.get_session_laps(sid)
    assert len(laps) == 2
    times = {r["lap_num"]: r["lap_time_ms"] for r in laps}
    assert times[1] == 92_345
    assert times[2] == 91_800


# ---------------------------------------------------------------------------
# write_feedback
# ---------------------------------------------------------------------------

def test_write_feedback(db):
    sid = db.open_session(car_id=1, track="Brands Hatch", session_type="Practice")
    fb = {
        "corner_entry": "Understeer",
        "mid_corner": "Neutral",
        "exit_stability": "Good",
        "rear_braking": "Locked",
        "tyre_condition": "Worn",
        "fuel_use": "Normal",
        "notes": "Push harder on exit",
    }
    row_id = db.write_feedback(session_id=sid, lap_num=3, feedback=fb, config_id="cfg-1")
    assert row_id > 0

    with db._lock:
        rows = db._conn.execute(
            "SELECT * FROM driver_feedback WHERE session_id=?", (sid,)
        ).fetchall()
    assert len(rows) == 1
    row = dict(rows[0])
    assert row["corner_entry"] == "Understeer"
    assert row["notes"] == "Push harder on exit"
    assert row["lap_num"] == 3


def test_write_feedback_empty_ok(db):
    row_id = db.write_feedback(session_id=0, lap_num=0, feedback={})
    assert row_id > 0


# ---------------------------------------------------------------------------
# v10: driver_feedback setup_id + rating, and lap-tag derived signals
# ---------------------------------------------------------------------------

def test_schema_version_is_v10(db):
    # Reconciled for Group 46: DB_VERSION bumped from 10 → 12 (_migrate_v12 added
    # learning_outcomes table). Reconciled again for Group 47: 12 → 13 (_migrate_v13
    # added the 5 additive outcome-verification columns to learning_outcomes).
    # Reconciled again for Group 62: 13 → 14 (_migrate_v14 added abs column to events).
    # Reconciled for Engineering-Brain Phase 1: 14 → 15 (_migrate_v15 added the
    # standalone additive setup_lineage table).
    # Reconciled for Engineering-Brain Phase 7: 15 → 16 (_migrate_v16 added additive
    # vs_previous/corner/phase columns to driver_feedback).
    # Reconciled for Engineering-Brain live telemetry: 16 → 17 (_migrate_v17 added the
    # standalone additive corner_slip_telemetry table).
    # Reconciled for cross-lap persistence (Sprint 5): 17 → 18 (_migrate_v18 added the
    # standalone additive corner_issue_occurrences table).
    # Reconciled for Sprint 10 UI: 18 → 19 (_migrate_v19 added the standalone additive
    # applied_setup_checkpoints table).
    # The test name is kept stable to not disrupt git blame.
    version = db._conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == 19


def test_driver_feedback_has_setup_id_and_rating_columns(db):
    cols = [c[1] for c in db._conn.execute("PRAGMA table_info(driver_feedback)").fetchall()]
    assert "setup_id" in cols
    assert "rating" in cols


def test_write_feedback_persists_setup_id_and_rating(db):
    sid = db.open_session(car_id=7, track="Fuji", session_type="Practice")
    row_id = db.write_feedback(session_id=sid, lap_num=5, feedback={"notes": "n"},
                               config_id="c", setup_id=42, rating="liked")
    assert row_id > 0
    row = dict(db._conn.execute(
        "SELECT * FROM driver_feedback WHERE id=?", (row_id,)).fetchone())
    assert row["setup_id"] == 42
    assert row["rating"] == "liked"


def test_write_feedback_defaults_setup_id_and_rating(db):
    # Existing call sites that don't pass the new args backfill to 0 / ''.
    row_id = db.write_feedback(session_id=0, lap_num=0, feedback={})
    row = dict(db._conn.execute(
        "SELECT * FROM driver_feedback WHERE id=?", (row_id,)).fetchone())
    assert row["setup_id"] == 0
    assert row["rating"] == ""


def test_get_recent_feedback_exposes_new_columns(db):
    sid = db.open_session(car_id=9, track="Suzuka", session_type="Practice")
    db.write_feedback(session_id=sid, lap_num=1, feedback={"notes": "x"},
                      setup_id=3, rating="hated")
    rows = db.get_recent_feedback(car_id=9, track="Suzuka", limit=5)
    assert rows and rows[0]["setup_id"] == 3
    assert rows[0]["rating"] == "hated"


def test_get_lap_count_for_setup(db):
    sid = db.open_session(car_id=1, track="Fuji", session_type="Practice")
    _insert_lap_direct(db, sid, 1, 92_000)
    _insert_lap_direct(db, sid, 2, 91_500)
    db.update_lap_setup_id(sid, 1, 55)
    db.update_lap_setup_id(sid, 2, 55)
    assert db.get_lap_count_for_setup(55) == 2
    assert db.get_lap_count_for_setup(999) == 0
    assert db.get_lap_count_for_setup(0) == 0


def test_get_dominant_setup_id(db):
    sid = db.open_session(car_id=1, track="Fuji", session_type="Practice")
    for n, t in enumerate((92_000, 91_800, 91_600), start=1):
        _insert_lap_direct(db, sid, n, t)
    # Two laps on setup 7, one on setup 8 → dominant is 7.
    db.update_lap_setup_id(sid, 1, 7)
    db.update_lap_setup_id(sid, 2, 7)
    db.update_lap_setup_id(sid, 3, 8)
    assert db.get_dominant_setup_id(sid) == 7


def test_get_dominant_setup_id_no_tags_returns_zero(db):
    sid = db.open_session(car_id=1, track="Fuji", session_type="Practice")
    _insert_lap_direct(db, sid, 1, 92_000)  # setup_id defaults to 0
    assert db.get_dominant_setup_id(sid) == 0
    assert db.get_dominant_setup_id(0) == 0


# ---------------------------------------------------------------------------
# write_grip_alert
# ---------------------------------------------------------------------------

def test_write_grip_alert(db):
    db.write_grip_alert(session_id=5, lap_num=7, score=72, alert_type="front")

    with db._lock:
        rows = db._conn.execute(
            "SELECT * FROM grip_alerts WHERE session_id=5"
        ).fetchall()
    assert len(rows) == 1
    row = dict(rows[0])
    assert row["score"] == 72
    assert row["alert_type"] == "front"
    assert row["lap_num"] == 7


def test_write_multiple_grip_alerts(db):
    for i in range(3):
        db.write_grip_alert(session_id=1, lap_num=i + 1, score=50 + i * 10, alert_type="rear")

    with db._lock:
        rows = db._conn.execute(
            "SELECT * FROM grip_alerts WHERE session_id=1"
        ).fetchall()
    assert len(rows) == 3


# ---------------------------------------------------------------------------
# write_strategy_snapshot + update_strategy_selection
# ---------------------------------------------------------------------------

def test_write_strategy_snapshot(db):
    snap_id = db.write_strategy_snapshot(
        config_id="cfg-abc",
        strategies_json='[{"rank": 1, "name": "Safe"}]',
    )
    assert snap_id > 0


def test_update_strategy_selection(db):
    snap_id = db.write_strategy_snapshot(config_id="cfg-x", strategies_json="[]")
    db.update_strategy_selection(snap_id, rank=2)

    with db._lock:
        row = db._conn.execute(
            "SELECT selected_rank FROM strategy_snapshots WHERE id=?", (snap_id,)
        ).fetchone()
    assert row["selected_rank"] == 2


# ---------------------------------------------------------------------------
# get_rev_limit_threshold_for_car (GROUP 22A / Finding I2)
# ---------------------------------------------------------------------------

def test_get_rev_limit_threshold_returns_default_when_car_missing(db):
    """Unknown car name returns the fallback 0.90."""
    result = db.get_rev_limit_threshold_for_car("NonExistentCar")
    assert result == 0.90


def test_get_rev_limit_threshold_returns_default_for_empty_name(db):
    """Empty car name returns the fallback 0.90 without querying."""
    result = db.get_rev_limit_threshold_for_car("")
    assert result == 0.90


def test_get_rev_limit_threshold_reads_db_value(db):
    """Returns the stored rev_limit_threshold_pct for a known car."""
    db.upsert_car({"name": "TestCar"})
    with db._lock:
        db._conn.execute(
            "UPDATE cars SET rev_limit_threshold_pct = 0.85 WHERE name = 'TestCar'"
        )
        db._conn.commit()
    result = db.get_rev_limit_threshold_for_car("TestCar")
    assert result == pytest.approx(0.85)


def test_get_rev_limit_threshold_returns_default_for_new_car(db):
    """A freshly inserted car gets the DB default (0.9) and the method returns it."""
    db.upsert_car({"name": "NewCar"})
    result = db.get_rev_limit_threshold_for_car("NewCar")
    assert result == pytest.approx(0.90)
