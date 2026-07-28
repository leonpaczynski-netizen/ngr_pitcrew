"""Evidence matches by the stable event_id, not fragile track/car text — and the
migration backfills event_id on existing (text-linked) prep data.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.session_db import SessionDB


def _cycle(db, cycle_id, event_id, car, track, event_name=""):
    db.upsert_preparation_cycle({
        "cycle_id": cycle_id, "event_id": event_id,
        "event_name": event_name or cycle_id, "car": car, "track": track})


def _run(db, car_id, car, track, event_id, laps=5):
    sid = db.open_session(car_id, track, "Practice", car_name=car, event_id=event_id)
    for lap in range(1, laps + 1):
        db.write_lap(sid, lap, 95_000, 3.0, None, event_id=event_id)
    return sid


def _bind(db, cycle_id, sid, n=1):
    from strategy.practice_run_recording import run_type_for_domain
    rt = run_type_for_domain("setup_base")
    aid = f"{cycle_id}::{rt.value}::{n}"
    db.upsert_preparation_activity({"activity_id": aid, "cycle_id": cycle_id,
                                    "activity_type": rt.value, "title": "b",
                                    "objective": "Build setup_base", "state": "completed",
                                    "order_index": n})
    db.bind_session_to_activity(aid, sid, cycle_id=cycle_id)


def test_event_id_match_counts_despite_track_text_drift():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = SessionDB(os.path.join(tmp, "s.db"))
        try:
            eid = db.upsert_event({"name": "Rd1", "track": "Sainte-Croix"})
            _cycle(db, "cyc", eid, "Shelby", "Sainte-Croix")
            car_id = db.upsert_car({"name": "Shelby"})
            # Session with the SAME event_id but a DIFFERENTLY-SPELLED track (encoding
            # drift). Under the old text match this vanished; by event_id it counts.
            sid = _run(db, car_id, "Shelby", "Sainte-Croix � Circuit B", eid)
            _bind(db, "cyc", sid)
            rep = db.build_event_preparation_report("cyc", now_date="2026-08-01")
            mem = {str(x) for x in (rep.get("evidence_membership") or [])}
            assert str(sid) in mem, rep.get("evidence_membership")
        finally:
            db.close()


def test_wrong_event_id_is_excluded():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = SessionDB(os.path.join(tmp, "s.db"))
        try:
            eid = db.upsert_event({"name": "Rd1", "track": "T"})
            other = db.upsert_event({"name": "Rd2", "track": "T"})
            _cycle(db, "cyc", eid, "Car", "T")
            car_id = db.upsert_car({"name": "Car"})
            sid = _run(db, car_id, "Car", "T", other)  # right car/track, WRONG event
            _bind(db, "cyc", sid)
            rep = db.build_event_preparation_report("cyc", now_date="2026-08-01")
            mem = {str(x) for x in (rep.get("evidence_membership") or [])}
            assert str(sid) not in mem, rep.get("evidence_membership")
        finally:
            db.close()


def test_legacy_zero_event_id_falls_back_to_text_match():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = SessionDB(os.path.join(tmp, "s.db"))
        try:
            _cycle(db, "cyc", 0, "Car", "Track")   # legacy cycle, no event_id
            car_id = db.upsert_car({"name": "Car"})
            sid = _run(db, car_id, "Car", "Track", 0)  # legacy session, no event_id
            _bind(db, "cyc", sid)
            rep = db.build_event_preparation_report("cyc", now_date="2026-08-01")
            mem = {str(x) for x in (rep.get("evidence_membership") or [])}
            assert str(sid) in mem
        finally:
            db.close()


def test_migration_backfills_event_id():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        path = os.path.join(tmp, "s.db")
        db = SessionDB(path)
        try:
            eid = db.upsert_event({"name": "Rd1", "track": "T"})
            _cycle(db, "cyc", 0, "Car", "T", event_name="Rd1")   # cycle left at event_id 0
            car_id = db.upsert_car({"name": "Car"})
            sid = _run(db, car_id, "Car", "T", 0)       # session left at event_id 0
            _bind(db, "cyc", sid)
            # Force the backfill migration to re-run.
            db._conn.execute("PRAGMA user_version = 28")
            db._conn.commit()
            db._migrate()
            cyc = db.get_preparation_cycle("cyc")
            assert int(cyc["event_id"]) == eid, cyc
            row = db._conn.execute("SELECT event_id FROM sessions WHERE id=?", (sid,)).fetchone()
            assert int(row[0]) == eid
        finally:
            db.close()
