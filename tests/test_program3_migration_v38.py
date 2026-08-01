"""Program 3 Phase B — schema v38: legacy classification + quarantine.

Verifies each legacy session is classified deterministically (never guessed into an
event), orphaned laps are quarantined, and the quarantine set is exposed read-only.
"""

import sqlite3

from data.session_db import SessionDB, _DDL


def _seed(path: str) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(_DDL)
        # RESOLVED: stable event_id
        conn.execute("INSERT INTO sessions(id, event_id, date_utc) VALUES(1, 5, '2026-01-01T00:00:00Z')")
        # RESOLVED_WITH_WARNING: event_id 0 but bound to an activity
        conn.execute("INSERT INTO sessions(id, event_id, date_utc) VALUES(2, 0, '2026-01-02T00:00:00Z')")
        conn.execute("INSERT INTO event_preparation_activities(activity_id, cycle_id) VALUES('a1','c1')")
        conn.execute("INSERT INTO event_preparation_activity_sessions(activity_id, session_id, cycle_id) "
                     "VALUES('a1','2','c1')")
        # AMBIGUOUS: event_id 0 and no binding — must NOT be guessed into an event
        conn.execute("INSERT INTO sessions(id, event_id, date_utc) VALUES(3, 0, '2026-01-03T00:00:00Z')")
        # a lap referencing a non-existent session (ORPHANED)
        conn.execute("INSERT INTO lap_records(session_id, lap_num, lap_time_ms) VALUES(999, 1, 90000)")
        conn.execute("PRAGMA user_version = 31")
        conn.commit()
    finally:
        conn.close()


def test_classification_is_deterministic(tmp_path):
    path = str(tmp_path / "old.db")
    _seed(path)
    db = SessionDB(path)
    cls = dict(db._conn.execute("SELECT id, legacy_class FROM sessions").fetchall())
    assert cls[1] == "RESOLVED"
    assert cls[2] == "RESOLVED_WITH_WARNING"
    assert cls[3] == "AMBIGUOUS"


def test_ambiguous_session_is_not_assigned_an_event(tmp_path):
    path = str(tmp_path / "old.db")
    _seed(path)
    db = SessionDB(path)
    # the ambiguous session keeps event_id 0 — it was quarantined, not guessed.
    assert db._conn.execute("SELECT event_id FROM sessions WHERE id=3").fetchone()[0] == 0
    assert db.is_session_quarantined(3) is True
    assert db.is_session_quarantined(1) is False


def test_report_and_quarantine_view(tmp_path):
    path = str(tmp_path / "old.db")
    _seed(path)
    db = SessionDB(path)
    rep = db.get_legacy_classification_report()
    assert rep["sessions"]["RESOLVED"] == 1
    assert rep["sessions"]["RESOLVED_WITH_WARNING"] == 1
    assert rep["sessions"]["AMBIGUOUS"] == 1
    assert rep["orphaned_laps"] == 1
    assert rep["quarantined"] == 2   # 1 ambiguous session + 1 orphaned lap

    q = db.get_quarantined_records()
    kinds = {(r["record_type"], r["reason"]) for r in q}
    assert ("session", "AMBIGUOUS") in kinds
    assert ("lap", "ORPHANED") in kinds


def test_idempotent(tmp_path):
    path = str(tmp_path / "old.db")
    _seed(path)
    r1 = SessionDB(path).get_legacy_classification_report()
    r2 = SessionDB(path).get_legacy_classification_report()
    assert r1 == r2
