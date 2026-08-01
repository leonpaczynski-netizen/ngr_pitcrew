"""Program 3 Phase B — schema v34: planned session vs actual run + stint.

Verifies the backfill (one completed run + single stint per existing session, laps
repointed), that a plan can carry MULTIPLE distinct runs that are never merged, and
idempotency.
"""

import sqlite3
import uuid

from data.session_db import SessionDB, _DDL


def _seed_v33(path: str) -> None:
    """A pre-v34 DB (schema 33) with one session, two laps, and an activity binding."""
    conn = sqlite3.connect(path)
    try:
        conn.executescript(_DDL)
        conn.execute(
            "INSERT INTO sessions(id, event_id, session_type, date_utc) "
            "VALUES(1, 5, 'Practice', '2026-01-01T10:00:00Z')")
        for lap in (1, 2):
            conn.execute(
                "INSERT INTO lap_records(session_id, lap_num, lap_time_ms) VALUES(1, ?, ?)",
                (lap, 90000 + lap))
        # a planned activity + binding of the session to it
        conn.execute(
            "INSERT INTO event_preparation_activities(activity_id, cycle_id) "
            "VALUES('plan-baseline', 'cyc-x')")
        conn.execute(
            "INSERT INTO event_preparation_activity_sessions(activity_id, session_id, cycle_id) "
            "VALUES('plan-baseline', '1', 'cyc-x')")
        # Seed at the last pre-Program-3 version so v32 (uuid) + v33 + v34 all run,
        # mirroring a real upgrade (v34's backfill reads sessions.uuid from v32).
        conn.execute("PRAGMA user_version = 31")
        conn.commit()
    finally:
        conn.close()


def test_fresh_db_has_run_and_stint_tables(tmp_path):
    db = SessionDB(str(tmp_path / "fresh.db"))
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 34
    tables = {r[0] for r in db._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"session_runs", "stints"} <= tables
    lap_cols = {r[1] for r in db._conn.execute("PRAGMA table_info(lap_records)")}
    assert {"session_run_id", "stint_id"} <= lap_cols


def test_backfill_one_run_per_session_bound_to_plan(tmp_path):
    path = str(tmp_path / "old.db")
    _seed_v33(path)
    db = SessionDB(path)
    runs = db._conn.execute(
        "SELECT run_id, session_id, session_plan_id, event_id, status FROM session_runs").fetchall()
    assert len(runs) == 1
    run_id, session_id, plan_id, event_id, status = runs[0]
    assert uuid.UUID(run_id).version == 7
    assert session_id == 1
    assert plan_id == "plan-baseline"      # bound to its planned activity
    assert event_id == 5
    assert status == "complete"            # historical runs are complete
    # exactly one stint, and both laps repointed to run + stint
    stints = db._conn.execute("SELECT stint_id FROM stints WHERE session_run_id=?", (run_id,)).fetchall()
    assert len(stints) == 1
    laps = db._conn.execute(
        "SELECT session_run_id, stint_id FROM lap_records WHERE session_id=1").fetchall()
    assert all(l[0] == run_id and l[1] == stints[0][0] for l in laps)


def test_a_plan_can_have_multiple_distinct_runs(tmp_path):
    """The core Program 3 property: a failed run and a successful run of the same
    planned session are DISTINCT rows, never merged."""
    db = SessionDB(str(tmp_path / "fresh.db"))
    r_fail = db.create_session_run(session_plan_id="plan-1", session_type="practice",
                                   status="failed", created_at="2026-01-01T10:00:00Z")
    r_ok = db.create_session_run(session_plan_id="plan-1", session_type="practice",
                                 status="complete", created_at="2026-01-01T11:00:00Z")
    assert r_fail != r_ok
    runs = db.get_runs_for_plan("plan-1")
    assert len(runs) == 2
    assert {r["status"] for r in runs} == {"failed", "complete"}


def test_get_run_for_session_and_status_update(tmp_path):
    db = SessionDB(str(tmp_path / "fresh.db"))
    rid = db.create_session_run(session_id=42, session_type="race", status="recording")
    got = db.get_run_for_session(42)
    assert got is not None and got["run_id"] == rid and got["status"] == "recording"
    db.set_session_run_status(rid, "complete", ended_at="2026-01-01T12:00:00Z")
    assert db.get_session_run(rid)["status"] == "complete"


def test_migration_idempotent(tmp_path):
    path = str(tmp_path / "old.db")
    _seed_v33(path)
    db1 = SessionDB(path)
    n1 = db1._conn.execute("SELECT COUNT(*) FROM session_runs").fetchone()[0]
    db1._conn.close()
    db2 = SessionDB(path)
    n2 = db2._conn.execute("SELECT COUNT(*) FROM session_runs").fetchone()[0]
    assert n1 == n2 == 1  # re-open does not create a second run for the same session
