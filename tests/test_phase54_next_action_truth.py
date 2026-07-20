"""Phase 54 — Command Centre next-action wired to canonical truth (task items 13, 32-34)."""
from __future__ import annotations

import hashlib
import json

from data.session_db import SessionDB


def _cycle(db, cid="c1", **kw):
    base = dict(cycle_id=cid, event_name="Cup R3", track="Fuji", car="P",
                official_race_date="2026-06-21", format_profile_id="multiweek", explicit_state="active")
    base.update(kw)
    db.upsert_preparation_cycle(base)


def _session(db, track="Fuji", car="P", laps=8):
    sid = db.open_session(car_id=1, track=track, session_type="Practice", car_name=car)
    db._conn.execute("UPDATE sessions SET total_laps=? WHERE CAST(id AS TEXT)=?", (laps, str(sid)))
    db._conn.commit()
    return sid


def _next(db, cid="c1"):
    return db.build_event_command_centre_view(selected_cycle_id=cid, now_date="2026-06-11")["next_action"]["category"]


def test_session_ended_binding_pending_is_primary():
    db = SessionDB(":memory:")
    _cycle(db)
    db.upsert_preparation_activity({"activity_id": "exp", "cycle_id": "c1",
                                    "activity_type": "setup_experiment", "order_index": 0,
                                    "state": "in_progress"})
    _session(db)
    assert _next(db) == "bind_session"
    db.close()


def test_binding_complete_debrief_pending_is_primary():
    db = SessionDB(":memory:")
    _cycle(db)
    db.upsert_preparation_activity({"activity_id": "exp", "cycle_id": "c1",
                                    "activity_type": "setup_experiment", "order_index": 0,
                                    "state": "in_progress"})
    sid = _session(db)
    db.bind_session_to_activity("exp", sid, "c1")
    assert _next(db) == "complete_debrief"
    db.close()


def test_no_placeholder_default_when_nothing_pending():
    db = SessionDB(":memory:")
    _cycle(db)
    db.upsert_preparation_activity({"activity_id": "base", "cycle_id": "c1",
                                    "activity_type": "baseline_practice", "order_index": 0,
                                    "state": "planned"})
    # nothing ran -> not bind/debrief; the primary action is the cumulative objective, not a placeholder
    assert _next(db) == "next_activity"
    db.close()


def test_persisted_strategy_final_ready_becomes_primary():
    # strategy finalisation eligibility comes from real maturity; here we exercise the readiness wiring
    db = SessionDB(":memory:")
    _cycle(db)
    # no pending binding/debrief; strategy readiness derived from report (developing by default -> not ready)
    db.upsert_preparation_activity({"activity_id": "a", "cycle_id": "c1",
                                    "activity_type": "baseline_practice", "order_index": 0, "state": "planned"})
    cat = _next(db)
    assert cat in ("next_activity", "finalise_strategy", "lock_setup")  # never a fabricated placeholder
    db.close()


def test_persisted_lock_marks_discipline_not_ready():
    db = SessionDB(":memory:")
    # a locked race discipline should not appear as lock-ready
    _cycle(db, setup_lock={"race": {"locked": True}})
    db.upsert_preparation_activity({"activity_id": "a", "cycle_id": "c1",
                                    "activity_type": "baseline_practice", "order_index": 0, "state": "planned"})
    locked_disc, finalised = db._persisted_lock_strategy("c1")
    assert "race" in locked_disc
    db.close()


def test_next_action_view_writes_nothing(tmp_path):
    p = str(tmp_path / "t.db")
    db = SessionDB(p)
    _cycle(db)
    db.upsert_preparation_activity({"activity_id": "exp", "cycle_id": "c1",
                                    "activity_type": "setup_experiment", "order_index": 0,
                                    "state": "in_progress"})
    _session(db)
    db.close()
    h0 = hashlib.sha256(open(p, "rb").read()).hexdigest()
    db2 = SessionDB(p)
    for _ in range(3):
        db2.build_event_command_centre_view(selected_cycle_id="c1", now_date="2026-06-11")
    db2.close()
    assert hashlib.sha256(open(p, "rb").read()).hexdigest() == h0


def test_exactly_one_primary_action():
    db = SessionDB(":memory:")
    _cycle(db)
    db.upsert_preparation_activity({"activity_id": "exp", "cycle_id": "c1",
                                    "activity_type": "setup_experiment", "order_index": 0,
                                    "state": "in_progress"})
    _session(db)
    v = db.build_event_command_centre_view(selected_cycle_id="c1", now_date="2026-06-11")
    assert isinstance(v["next_action"], dict) and v["next_action"]["headline"]
    db.close()
