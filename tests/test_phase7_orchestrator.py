"""Engineering Brain Phase 7 — SessionDB orchestrator + wiring tests.

The orchestrator (`build_live_engineering_state`) is a READ-ONLY OBSERVER that
regenerates the live state + development ledger from `corner_issue_occurrences` with
NO migration. These tests lock: no schema bump, restart-determinism, valid-lap
filtering, a golden UAT scenario, and that Phase 7 adds no competing telemetry table.
"""
import pytest

from data.session_db import SessionDB
from strategy._setup_constants import DB_VERSION


@pytest.fixture
def db():
    return SessionDB(":memory:")


def _laps(db, sid, n, *, t=95000, car_id=7, track="Fuji", pit=(), out=()):
    for i in range(1, n + 1):
        db._conn.execute(
            "INSERT INTO lap_records (session_id, car_id, track, lap_num, lap_time_ms, "
            "is_pit_lap, is_out_lap) VALUES (?,?,?,?,?,?,?)",
            (sid, car_id, track, i, t, 1 if i in pit else 0, 1 if i in out else 0))
    db._conn.commit()


def _occ(sid, lap, *, seg="T1", issue="understeer", phase="apex", axle="front"):
    return {"session_id": sid, "setup_checkpoint_id": "", "lap_number": lap,
            "segment_id": seg, "corner_phase": phase, "issue_type": issue,
            "axle": axle, "severity": 0.6, "confidence": 0.8}


# 1 — no migration: Phase 7 stores nothing new; DB stays at DB_VERSION.
def test_no_migration_db_version_unchanged(db):
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION


def test_no_new_telemetry_table(db):
    tables = {r[0] for r in db._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    telemetry = {t for t in tables if "corner" in t
                 and ("slip" in t or "occurrence" in t or "issue" in t)}
    assert telemetry == {"corner_issues", "corner_issue_occurrences",
                         "corner_slip_telemetry"}
    # no live-state / ledger persistence table was introduced
    assert not any("live_engineering" in t or "development_ledger" in t
                   for t in tables)


# 2 — end-to-end: persisted occurrences → live state + ledger
def test_end_to_end_live_state_and_ledger(db):
    sid = 300
    _laps(db, sid, 7)
    db.save_issue_occurrences(7, "Fuji", "", [_occ(sid, n) for n in (1, 2, 3, 4)])
    res = db.build_live_engineering_state(sid, car_id=7, track="Fuji",
                                          discipline="race", scope_fingerprint="A")
    assert res["ok"]
    assert res["valid_lap_count"] == 7
    assert len(res["live_state"]["issues"]) == 1
    assert res["live_state"]["issues"][0]["identity"]["issue_type"] == "understeer"
    assert res["ledger"]["events"]


# 3 — restart determinism: rebuild yields identical fingerprints
def test_restart_determinism(db):
    sid = 301
    _laps(db, sid, 6)
    db.save_issue_occurrences(7, "Fuji", "", [_occ(sid, n) for n in (2, 3, 4)])
    a = db.build_live_engineering_state(sid, car_id=7, track="Fuji", scope_fingerprint="A")
    b = db.build_live_engineering_state(sid, car_id=7, track="Fuji", scope_fingerprint="A")
    assert a["live_state"]["content_fingerprint"] == b["live_state"]["content_fingerprint"]
    assert a["ledger"]["content_fingerprint"] == b["ledger"]["content_fingerprint"]


# 4 — pit/out laps are excluded from the comparable window
def test_pit_and_out_laps_excluded(db):
    sid = 302
    _laps(db, sid, 7, pit=(4,), out=(1,))
    db.save_issue_occurrences(7, "Fuji", "", [_occ(sid, n) for n in (2, 3, 5)])
    res = db.build_live_engineering_state(sid, car_id=7, track="Fuji", scope_fingerprint="A")
    valid = res["live_state"]["valid_lap_numbers"]
    assert 1 not in valid and 4 not in valid


# 5 — golden UAT: an issue that recurs then clears resolves; timeline is monotonic
def test_golden_uat_resolution_timeline(db):
    sid = 303
    _laps(db, sid, 7)
    db.save_issue_occurrences(7, "Fuji", "", [_occ(sid, n) for n in (1, 2, 3, 4)])
    res = db.build_live_engineering_state(sid, car_id=7, track="Fuji", scope_fingerprint="A")
    issue = res["live_state"]["issues"][0]
    assert issue["status"] == "resolved"
    # ledger sequence numbers strictly increasing & lap numbers non-decreasing
    events = res["ledger"]["events"]
    seqs = [e["sequence_no"] for e in events]
    laps = [e["lap_number"] for e in events]
    assert seqs == sorted(seqs)
    assert laps == sorted(laps)


# 6 — no session scope → honest failure, never raises, never fabricates
def test_missing_scope_returns_not_ok(db):
    res = db.build_live_engineering_state(0)
    assert res["ok"] is False


# 7 — observer writes nothing: occurrence row count unchanged after a build
def test_observer_writes_nothing(db):
    sid = 304
    _laps(db, sid, 5)
    db.save_issue_occurrences(7, "Fuji", "", [_occ(sid, n) for n in (2, 3)])
    before = db._conn.execute(
        "SELECT COUNT(*) FROM corner_issue_occurrences").fetchone()[0]
    db.build_live_engineering_state(sid, car_id=7, track="Fuji", scope_fingerprint="A")
    after = db._conn.execute(
        "SELECT COUNT(*) FROM corner_issue_occurrences").fetchone()[0]
    assert before == after


# 8 — metamorphic: insertion order of occurrences does not change the state
def test_metamorphic_insertion_order_invariant(db):
    sid1, sid2 = 305, 306
    _laps(db, sid1, 6)
    _laps(db, sid2, 6)
    db.save_issue_occurrences(7, "Fuji", "", [_occ(sid1, n) for n in (2, 3, 4)])
    db.save_issue_occurrences(7, "Fuji", "", [_occ(sid2, n) for n in (4, 2, 3)])
    a = db.build_live_engineering_state(sid1, car_id=7, track="Fuji", scope_fingerprint="A")
    b = db.build_live_engineering_state(sid2, car_id=7, track="Fuji", scope_fingerprint="A")
    # different session ids, but issue-level classification is identical
    ia = a["live_state"]["issues"][0]
    ib = b["live_state"]["issues"][0]
    assert ia["status"] == ib["status"]
    assert ia["trend"] == ib["trend"]
    assert ia["consistency"]["affected_valid_laps"] == \
        ib["consistency"]["affected_valid_laps"]
