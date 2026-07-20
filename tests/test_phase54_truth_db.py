"""Phase 54 — canonical Command Centre truth from real DB rows (task items 7-8, 32-33)."""
from __future__ import annotations

import hashlib

from data.session_db import SessionDB


def _cycle(db, cid="c1", track="Fuji", car="P"):
    db.upsert_preparation_cycle({"cycle_id": cid, "event_name": "Cup", "track": track, "car": car,
                                 "official_race_date": "2026-06-21", "format_profile_id": "multiweek",
                                 "explicit_state": "active"})


def _finalized_session(db, track="Fuji", car="P", laps=8):
    sid = db.open_session(car_id=1, track=track, session_type="Practice", car_name=car)
    db._conn.execute("UPDATE sessions SET total_laps=? WHERE CAST(id AS TEXT)=?", (laps, str(sid)))
    db._conn.commit()
    return sid


def test_pending_binding_true_from_real_rows(tmp_path):
    db = SessionDB(str(tmp_path / "t.db"))
    _cycle(db)
    db.upsert_preparation_activity({"activity_id": "exp", "cycle_id": "c1",
                                    "activity_type": "setup_experiment", "order_index": 0,
                                    "state": "in_progress"})
    _finalized_session(db)
    t = db.build_command_centre_truth("c1")
    assert t["pending_binding"] is True and t["pending_binding_activity_ids"] == ["exp"]
    assert t["pending_debrief"] is False
    db.close()


def test_binding_clears_pending_binding_and_makes_debrief_pending(tmp_path):
    db = SessionDB(str(tmp_path / "t.db"))
    _cycle(db)
    db.upsert_preparation_activity({"activity_id": "exp", "cycle_id": "c1",
                                    "activity_type": "setup_experiment", "order_index": 0,
                                    "state": "in_progress"})
    sid = _finalized_session(db)
    db.bind_session_to_activity("exp", sid, "c1")
    t = db.build_command_centre_truth("c1")
    assert t["pending_binding"] is False and t["pending_debrief"] is True


def test_completed_activity_has_no_pending(tmp_path):
    db = SessionDB(str(tmp_path / "t.db"))
    _cycle(db)
    db.upsert_preparation_activity({"activity_id": "exp", "cycle_id": "c1",
                                    "activity_type": "setup_experiment", "order_index": 0,
                                    "state": "completed"})
    sid = _finalized_session(db)
    db.bind_session_to_activity("exp", sid, "c1")
    t = db.build_command_centre_truth("c1")
    assert t["pending_binding"] is False and t["pending_debrief"] is False
    db.close()


def test_planned_activity_with_telemetry_is_not_pending(tmp_path):
    # telemetry existing alone does not make binding pending — the activity must have run
    db = SessionDB(str(tmp_path / "t.db"))
    _cycle(db)
    db.upsert_preparation_activity({"activity_id": "exp", "cycle_id": "c1",
                                    "activity_type": "setup_experiment", "order_index": 0,
                                    "state": "planned"})
    _finalized_session(db)
    t = db.build_command_centre_truth("c1")
    assert t["pending_binding"] is False
    db.close()


def test_truth_view_writes_nothing(tmp_path):
    p = str(tmp_path / "t.db")
    db = SessionDB(p)
    _cycle(db)
    db.upsert_preparation_activity({"activity_id": "exp", "cycle_id": "c1",
                                    "activity_type": "setup_experiment", "order_index": 0,
                                    "state": "in_progress"})
    _finalized_session(db)
    db.close()
    h0 = hashlib.sha256(open(p, "rb").read()).hexdigest()
    db2 = SessionDB(p)
    for _ in range(3):
        db2.build_command_centre_truth("c1")
    db2.close()
    assert hashlib.sha256(open(p, "rb").read()).hexdigest() == h0


def test_truth_query_shape_constant(tmp_path):
    db = SessionDB(str(tmp_path / "t.db"))
    _cycle(db)
    db.upsert_preparation_activity({"activity_id": "exp", "cycle_id": "c1",
                                    "activity_type": "long_race_run", "order_index": 0,
                                    "state": "in_progress"})

    def _count(n):
        for _ in range(n):
            sid = _finalized_session(db)
            db.bind_session_to_activity("exp", sid, "c1")
        calls = {"n": 0}
        db._conn.set_trace_callback(lambda s: calls.__setitem__("n", calls["n"] + 1)
                                    if s.strip().upper().startswith("SELECT") else None)
        try:
            db.build_command_centre_truth("c1")
        finally:
            db._conn.set_trace_callback(None)
        return calls["n"]

    assert _count(1) == _count(19)  # constant regardless of bound-session count
    db.close()


def test_truth_deterministic(tmp_path):
    db = SessionDB(str(tmp_path / "t.db"))
    _cycle(db)
    db.upsert_preparation_activity({"activity_id": "exp", "cycle_id": "c1",
                                    "activity_type": "setup_experiment", "order_index": 0,
                                    "state": "in_progress"})
    _finalized_session(db)
    assert db.build_command_centre_truth("c1")["fingerprint"] == db.build_command_centre_truth("c1")["fingerprint"]
    db.close()


def test_missing_cycle_is_safe(tmp_path):
    db = SessionDB(str(tmp_path / "t.db"))
    t = db.build_command_centre_truth("ghost")
    assert t["ok"] is False
    db.close()
