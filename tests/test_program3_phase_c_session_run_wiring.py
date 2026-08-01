"""Program 3 Phase C — session_run identity wired into the live recording path.

open_session now opens a canonical session_run (+ opening stint); write_lap stamps
each lap with its run/stint; bind_session_to_activity links the run to its plan.
All best-effort and additive — recording never depends on the run spine.
"""

from data.session_db import SessionDB


def test_open_session_opens_a_recording_run_with_stint(tmp_path):
    db = SessionDB(str(tmp_path / "s.db"))
    sid = db.open_session(333, "Fuji", "Practice", event_id=5)
    run = db.get_run_for_session(sid)
    assert run is not None
    assert run["status"] == "recording"
    assert run["session_id"] == sid
    assert run["session_uuid"]                      # stamped from sessions.uuid (v32)
    stints = db._conn.execute(
        "SELECT stint_id FROM stints WHERE session_run_id=?", (run["run_id"],)).fetchall()
    assert len(stints) == 1                         # one opening stint


def test_write_lap_stamps_run_and_stint(tmp_path):
    db = SessionDB(str(tmp_path / "s.db"))
    sid = db.open_session(333, "Fuji", "Practice")
    db.write_lap(sid, 1, 90000, 1.5, None)
    db.write_lap(sid, 2, 89000, 1.5, None)
    run = db.get_run_for_session(sid)
    stint = db._conn.execute(
        "SELECT stint_id FROM stints WHERE session_run_id=?", (run["run_id"],)).fetchone()[0]
    rows = db._conn.execute(
        "SELECT session_run_id, stint_id, uuid FROM lap_records WHERE session_id=?", (sid,)).fetchall()
    assert len(rows) == 2
    assert all(r[0] == run["run_id"] and r[1] == stint for r in rows)
    import uuid as _uuid
    assert all(_uuid.UUID(r[2]).version == 7 for r in rows)   # new laps get a canonical id


def test_bind_links_run_to_plan(tmp_path):
    db = SessionDB(str(tmp_path / "s.db"))
    sid = db.open_session(333, "Fuji", "Practice")
    assert db.bind_session_to_activity("plan-1", sid, cycle_id="cyc-1") is True
    run = db.get_run_for_session(sid)
    assert run["session_plan_id"] == "plan-1"
    assert run["cycle_id"] == "cyc-1"


def test_distinct_sessions_get_distinct_runs(tmp_path):
    db = SessionDB(str(tmp_path / "s.db"))
    s1 = db.open_session(333, "Fuji", "Practice")
    s2 = db.open_session(333, "Fuji", "Practice")
    r1, r2 = db.get_run_for_session(s1), db.get_run_for_session(s2)
    assert r1["run_id"] != r2["run_id"]             # each recording is its own run


def test_run_creation_is_idempotent_per_session(tmp_path):
    db = SessionDB(str(tmp_path / "s.db"))
    sid = db.open_session(333, "Fuji", "Practice")
    # a defensive second attach must not create a second run for the same session
    db._attach_session_run(sid, session_type="Practice")
    n = db._conn.execute(
        "SELECT COUNT(*) FROM session_runs WHERE session_id=?", (sid,)).fetchone()[0]
    assert n == 1
