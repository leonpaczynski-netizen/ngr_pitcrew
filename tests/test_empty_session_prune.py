"""Ghost 0-lap sessions are pruned, but real and bound-but-empty sessions are spared.

An eager session-open (a live-mode toggle before driving) left a 0-lap "ghost" row.
These carry no data and cluttered the history (UAT: the event "hasn't registered any
sessions" while the DB filled with hundreds of empty rows).
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.session_db import SessionDB


def _bind(db, cycle_id, event_id, sid):
    from strategy.practice_run_recording import run_type_for_domain
    db.upsert_preparation_cycle({"cycle_id": cycle_id, "event_id": event_id,
                                 "event_name": "Rd1", "car": "Car", "track": "T"})
    rt = run_type_for_domain("setup_base")
    aid = f"{cycle_id}::{rt.value}::1"
    db.upsert_preparation_activity({"activity_id": aid, "cycle_id": cycle_id,
                                    "activity_type": rt.value, "title": "b",
                                    "objective": "x", "state": "completed", "order_index": 1})
    db.bind_session_to_activity(aid, sid, cycle_id=cycle_id)


def test_prune_removes_ghosts_but_spares_real_and_bound():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = SessionDB(os.path.join(tmp, "s.db"))
        try:
            cid = db.upsert_car({"name": "Car"})
            eid = db.upsert_event({"name": "Rd1", "track": "T"})
            ghost = db.open_session(cid, "T", "practice", car_name="Car", event_id=eid)
            real = db.open_session(cid, "T", "practice", car_name="Car", event_id=eid)
            db.write_lap(real, 1, 95_000, 3.0, None, event_id=eid)
            bound = db.open_session(cid, "T", "practice", car_name="Car", event_id=eid)
            _bind(db, "cyc", eid, bound)

            assert db.session_is_empty(ghost) is True
            assert db.session_is_empty(real) is False

            pruned = db.prune_empty_sessions()
            assert pruned == 1                      # only the unbound ghost
            ids = [r[0] for r in db._conn.execute(
                "SELECT id FROM sessions ORDER BY id").fetchall()]
            assert ghost not in ids
            assert real in ids and bound in ids     # real + bound-but-empty spared
        finally:
            db.close()


def test_keep_session_id_spares_the_open_session():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = SessionDB(os.path.join(tmp, "s.db"))
        try:
            cid = db.upsert_car({"name": "Car"})
            open_now = db.open_session(cid, "T", "practice", car_name="Car")
            other = db.open_session(cid, "T", "practice", car_name="Car")
            pruned = db.prune_empty_sessions(keep_session_id=open_now)
            assert pruned == 1                      # only `other`
            ids = [r[0] for r in db._conn.execute("SELECT id FROM sessions").fetchall()]
            assert open_now in ids and other not in ids
        finally:
            db.close()
