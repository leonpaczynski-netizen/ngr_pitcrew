"""Live Activation 1 — the SessionDB port + coordinator against a REAL in-memory SessionDB.

Proves the authoritative Practice recording persists against the real schema: one canonical
session run bound to its planned session, laps stamped with that run + stint, correct event,
status driven through the lifecycle. No Qt.
"""
from __future__ import annotations

from data.session_db import SessionDB
from strategy.live_practice_runtime import LivePracticeCoordinator
from ui.live_practice_db_port import SessionDbLivePracticePort


def _identity(event_id=42):
    return {
        "planned_session_type": "Practice",
        "event_programme_id": "cyc-1", "event_id": str(event_id), "session_plan_id": "plan-1",
        "car_id": "333", "car_name": "Test GT3", "track": "Fuji", "config_id": "cfg-1",
        "car_spec_revision_id": "spec-1", "driver_profile_version_id": "drv-1",
        "context_revision_id": "ctx-1", "setup_snapshot_id": "setup-1",
        "track_model_version_id": "trk-1",
    }


def _db(tmp_path):
    return SessionDB(str(tmp_path / "s.db"))


def test_authoritative_run_is_created_bound_and_persists_laps(tmp_path):
    db = _db(tmp_path)
    ctx = _identity()
    port = SessionDbLivePracticePort(db, lambda: ctx)
    co = LivePracticeCoordinator(port)

    act = co.activate()
    assert act.ok and co.run_id
    # one canonical run for this session, bound to the planned session
    run = db.get_run_for_session(port.session_id)
    assert run is not None and run["run_id"] == co.run_id
    assert run["session_plan_id"] == "plan-1"
    assert int(run["event_id"]) == 42 and run["session_type"] == "Practice"

    assert co.telemetry_connected()
    for ln, t in [(1, 91000), (2, 89000), (3, 88000)]:
        out = co.on_lap(session_run_id=co.run_id, event_id="42", lap_number=ln, lap_time_ms=t)
        assert out.recorded and out.valid

    # every lap for this session is stamped with the canonical run + stint
    laps = db._conn.execute(
        "SELECT session_run_id, stint_id, lap_time_ms FROM lap_records WHERE session_id=? "
        "ORDER BY lap_num", (port.session_id,)).fetchall()
    assert len(laps) == 3
    assert all(r[0] == co.run_id and r[1] and r[2] > 0 for r in laps)
    assert db.count_valid_laps(port.session_id) == 3

    assert co.complete()
    assert db.get_session_run(co.run_id)["status"] == "completed"


def test_blocked_activation_opens_no_session(tmp_path):
    db = _db(tmp_path)
    ctx = _identity()
    ctx["driver_profile_version_id"] = ""     # unresolved required context
    co = LivePracticeCoordinator(SessionDbLivePracticePort(db, lambda: ctx))
    act = co.activate()
    assert not act.ok and "driver_profile_version_id" in act.missing
    # nothing was recorded
    assert db._conn.execute("SELECT COUNT(*) FROM session_runs").fetchone()[0] == 0
    assert db._conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0


def test_distinct_runs_never_cross_write_laps(tmp_path):
    db = _db(tmp_path)
    # run A on event 42
    portA = SessionDbLivePracticePort(db, lambda: _identity(42))
    coA = LivePracticeCoordinator(portA)
    coA.activate(); coA.telemetry_connected()
    coA.on_lap(session_run_id=coA.run_id, event_id="42", lap_number=1, lap_time_ms=90000)
    coA.complete()
    # a lap tagged with a different event never records to run A
    assert not coA.on_lap(session_run_id=coA.run_id, event_id="99",
                          lap_number=2, lap_time_ms=90000).recorded

    # run B on event 99 — fully separate session + run
    portB = SessionDbLivePracticePort(db, lambda: _identity(99))
    coB = LivePracticeCoordinator(portB)
    coB.activate(); coB.telemetry_connected()
    coB.on_lap(session_run_id=coB.run_id, event_id="99", lap_number=1, lap_time_ms=90000)

    assert coA.run_id != coB.run_id and portA.session_id != portB.session_id
    a_laps = [r[0] for r in db._conn.execute(
        "SELECT DISTINCT session_run_id FROM lap_records WHERE session_id=?",
        (portA.session_id,)).fetchall()]
    b_laps = [r[0] for r in db._conn.execute(
        "SELECT DISTINCT session_run_id FROM lap_records WHERE session_id=?",
        (portB.session_id,)).fetchall()]
    assert a_laps == [coA.run_id] and b_laps == [coB.run_id]
