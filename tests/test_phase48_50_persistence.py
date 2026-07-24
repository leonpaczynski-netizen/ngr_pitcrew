"""Phase 48-50 — v28 migration, SessionDB persistence, event-scoped query shape, orchestration.

Covers task test items: preparation-cycle persistence, session-to-cycle binding (16), query shape (39),
runtime DB immutability (40), fresh DB + migration + repeated startup, and the end-to-end cumulative
invariants through the DB.
"""
from __future__ import annotations

import hashlib

from data.session_db import SessionDB
from strategy._setup_constants import DB_VERSION


def _tables(db):
    return {r[0] for r in db._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}


# --- migration -------------------------------------------------------------

def test_db_version_is_28():
    assert DB_VERSION == 28


def test_fresh_db_creates_v28_tables(tmp_path):
    db = SessionDB(str(tmp_path / "fresh.db"))
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION == 28
    t = _tables(db)
    assert {"event_preparation_cycles", "event_preparation_activities",
            "event_preparation_activity_sessions"} <= t
    db.close()


def test_migrate_from_legacy_v27(tmp_path):
    p = str(tmp_path / "legacy.db")
    db = SessionDB(p)
    db._conn.execute("DROP TABLE IF EXISTS event_preparation_cycles")
    db._conn.execute("DROP TABLE IF EXISTS event_preparation_activities")
    db._conn.execute("DROP TABLE IF EXISTS event_preparation_activity_sessions")
    db._conn.execute("PRAGMA user_version = 27"); db._conn.commit(); db.close()
    db2 = SessionDB(p)
    assert db2._conn.execute("PRAGMA user_version").fetchone()[0] == 28
    assert "event_preparation_cycles" in _tables(db2)
    db2.close()


def test_repeated_startup_idempotent(tmp_path):
    p = str(tmp_path / "repeat.db")
    for _ in range(3):
        db = SessionDB(p)
        assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 28
        db.close()


def test_viewing_creates_no_rows(tmp_path):
    """Building the report for a non-existent cycle writes nothing (viewing never persists)."""
    db = SessionDB(str(tmp_path / "v.db"))
    rep = db.build_event_preparation_report("nope")
    assert rep["ok"] is False
    n = db._conn.execute("SELECT COUNT(*) FROM event_preparation_cycles").fetchone()[0]
    assert n == 0
    db.close()


# --- persistence -----------------------------------------------------------

def _seed_cycle(db, cycle_id="cyc-1", track="Fuji", car="Porsche 911 RSR"):
    db.upsert_preparation_cycle({
        "cycle_id": cycle_id, "event_name": "Porsche Cup R3", "series": "NGR Porsche Cup",
        "round_label": "R3", "driver_id": "leon", "car": car, "track": track, "layout": "Full",
        "prep_open_date": "2026-06-01", "official_quali_date": "2026-06-21",
        "official_race_date": "2026-06-21", "format_profile_id": "multiweek",
        "disciplines": ["race", "qualifying"]})


def test_lock_setup_writes_and_reads_per_discipline(tmp_path):
    """UAT-7: "how do I 'lock the base setup'?" The lock domain existed but nothing
    wrote setup_lock_json — the CTA had no effect. lock_setup is the focused writer."""
    db = SessionDB(str(tmp_path / "lock.db"))
    _seed_cycle(db)
    assert db.setup_locks("cyc-1") == ()
    assert db.lock_setup("cyc-1", "race", locked=True, locked_at="2026-06-20 10:00") is True
    assert db.setup_locks("cyc-1") == ("race",)


def test_locking_one_discipline_never_clears_another(tmp_path):
    db = SessionDB(str(tmp_path / "lock2.db"))
    _seed_cycle(db)
    db.lock_setup("cyc-1", "race", locked=True)
    db.lock_setup("cyc-1", "qualifying", locked=True)
    assert set(db.setup_locks("cyc-1")) == {"race", "qualifying"}
    db.lock_setup("cyc-1", "race", locked=False)          # reopen only race
    assert db.setup_locks("cyc-1") == ("qualifying",)


def test_lock_setup_leaves_the_rest_of_the_cycle_untouched(tmp_path):
    db = SessionDB(str(tmp_path / "lock3.db"))
    _seed_cycle(db)
    db.lock_setup("cyc-1", "race", locked=True)
    cyc = db.get_preparation_cycle("cyc-1")
    assert cyc["event_name"] == "Porsche Cup R3"           # a focused UPDATE, not a rebuild
    assert cyc["disciplines"] == ("race", "qualifying")


def test_lock_setup_on_a_missing_cycle_or_blank_discipline_is_false(tmp_path):
    db = SessionDB(str(tmp_path / "lock4.db"))
    _seed_cycle(db)
    assert db.lock_setup("nope", "race") is False
    assert db.lock_setup("cyc-1", "") is False


def test_upsert_and_read_cycle_is_idempotent(tmp_path):
    db = SessionDB(str(tmp_path / "c.db"))
    _seed_cycle(db)
    _seed_cycle(db)  # upsert again
    assert db._conn.execute("SELECT COUNT(*) FROM event_preparation_cycles").fetchone()[0] == 1
    cyc = db.get_preparation_cycle("cyc-1")
    assert cyc["event_name"] == "Porsche Cup R3"
    assert cyc["disciplines"] == ("race", "qualifying")
    db.close()


def test_activities_and_binding_round_trip(tmp_path):
    db = SessionDB(str(tmp_path / "a.db"))
    _seed_cycle(db)
    db.upsert_preparation_activity({"activity_id": "a1", "cycle_id": "cyc-1",
                                    "activity_type": "setup_experiment", "order_index": 0})
    db.upsert_preparation_activity({"activity_id": "a2", "cycle_id": "cyc-1",
                                    "activity_type": "long_race_run", "order_index": 1})
    acts = db.list_preparation_activities("cyc-1")
    assert [a["activity_id"] for a in acts] == ["a1", "a2"]
    # binding is explicit + idempotent
    assert db.bind_session_to_activity("a1", "101", "cyc-1") is True
    assert db.bind_session_to_activity("a1", "101", "cyc-1") is True  # idempotent
    n = db._conn.execute("SELECT COUNT(*) FROM event_preparation_activity_sessions").fetchone()[0]
    assert n == 1
    db.close()


def test_event_scoped_practice_query(tmp_path):
    """The event-scoped Practice query the flat sessions.event_id column never provided."""
    db = SessionDB(str(tmp_path / "q.db"))
    _seed_cycle(db)
    db.upsert_preparation_activity({"activity_id": "a1", "cycle_id": "cyc-1",
                                    "activity_type": "long_race_run", "order_index": 0})
    sid = db.open_session(car_id=1, track="Fuji", session_type="Practice", car_name="Porsche 911 RSR")
    db.bind_session_to_activity("a1", sid, "cyc-1")
    rows = db.get_practice_sessions_for_cycle("cyc-1")
    assert len(rows) == 1 and rows[0]["activity_type"] == "long_race_run"
    db.close()


# --- query shape (constant regardless of session count) --------------------

def test_report_query_count_is_constant(tmp_path):
    db = SessionDB(str(tmp_path / "shape.db"))
    _seed_cycle(db)
    db.upsert_preparation_activity({"activity_id": "a1", "cycle_id": "cyc-1",
                                    "activity_type": "long_race_run", "order_index": 0})

    def _count_queries_for(n_sessions):
        for i in range(n_sessions):
            sid = db.open_session(car_id=1, track="Fuji", session_type="Practice",
                                  car_name="Porsche 911 RSR")
            db._conn.execute("UPDATE sessions SET total_laps=8 WHERE CAST(id AS TEXT)=?", (str(sid),))
            db._conn.commit()
            db.bind_session_to_activity("a1", sid, "cyc-1")
        calls = {"n": 0}
        def _trace(sql):
            if sql.strip().upper().startswith("SELECT"):
                calls["n"] += 1
        db._conn.set_trace_callback(_trace)
        try:
            db.build_event_preparation_report("cyc-1")
        finally:
            db._conn.set_trace_callback(None)
        return calls["n"]

    q1 = _count_queries_for(1)
    q20 = _count_queries_for(19)  # now 20 total
    assert q1 == q20, f"query count grew with sessions: {q1} vs {q20} (N+1)"
    db.close()


# --- end-to-end orchestration ----------------------------------------------

def test_report_accumulates_evidence_and_stays_context_safe(tmp_path):
    db = SessionDB(str(tmp_path / "e2e.db"))
    _seed_cycle(db)
    db.upsert_preparation_activity({"activity_id": "exp", "cycle_id": "cyc-1",
                                    "activity_type": "setup_experiment", "order_index": 0})
    db.upsert_preparation_activity({"activity_id": "coach", "cycle_id": "cyc-1",
                                    "activity_type": "coaching_run", "order_index": 1})
    # two valid on-context experiment sessions
    for _ in range(2):
        sid = db.open_session(car_id=1, track="Fuji", session_type="Practice", car_name="Porsche 911 RSR")
        db._conn.execute("UPDATE sessions SET total_laps=8 WHERE CAST(id AS TEXT)=?", (str(sid),))
        db._conn.commit()
        db.bind_session_to_activity("exp", sid, "cyc-1")
    # an OFF-context session (wrong track) bound to the same activity -> must not strengthen exact setup
    off = db.open_session(car_id=1, track="Spa", session_type="Practice", car_name="Porsche 911 RSR")
    db._conn.execute("UPDATE sessions SET total_laps=8 WHERE CAST(id AS TEXT)=?", (str(off),))
    db._conn.commit()
    db.bind_session_to_activity("exp", off, "cyc-1")

    rep = db.build_event_preparation_report("cyc-1", now_date="2026-06-10")
    assert rep["ok"] is True
    assert rep["cycle"]["event_name"] == "Porsche Cup R3"
    assert rep["cycle"]["days_until_race"] == 11
    # 3 bound sessions but only 2 on-context contribute to exact setup evidence membership
    assert len(rep["evidence_membership"]) == 2
    # coaching activity present but no coaching session bound -> coaching did not fabricate setup
    assert isinstance(rep["setup"], dict) and "race" in rep["setup"]
    db.close()


def test_report_runtime_db_immutability(tmp_path):
    db = SessionDB(str(tmp_path / "immut.db"))
    _seed_cycle(db)
    db.upsert_preparation_activity({"activity_id": "a1", "cycle_id": "cyc-1",
                                    "activity_type": "baseline_practice", "order_index": 0})
    sid = db.open_session(car_id=1, track="Fuji", session_type="Practice", car_name="Porsche 911 RSR")
    db.bind_session_to_activity("a1", sid, "cyc-1")
    db.close()
    p = str(tmp_path / "immut.db")
    h0 = hashlib.sha256(open(p, "rb").read()).hexdigest()
    db2 = SessionDB(p)
    db2.build_event_preparation_report("cyc-1")  # a read must not mutate
    db2.build_event_preparation_report("cyc-1")
    db2.close()
    assert hashlib.sha256(open(p, "rb").read()).hexdigest() == h0
