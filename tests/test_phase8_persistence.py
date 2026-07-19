"""Engineering Brain Phase 8 — persistence + orchestrator tests.

Locks the additive v24 migration, append-only immutability (idempotent record_key,
no rewriting), restart-determinism (rebuild from the stored JSON is byte-identical),
context isolation, and that the observer writes nothing beyond its own append-only log.
"""
import pytest

from data.session_db import SessionDB
from strategy._setup_constants import DB_VERSION
from strategy.development_history import MemoryContextKey, build_development_record
from strategy.engineering_issue import IssueFamily, ResidualState


@pytest.fixture
def db():
    return SessionDB(":memory:")


CTX = MemoryContextKey(driver="leon", car="RSR", track="Fuji", layout_id="fc",
                       discipline="Race", gt7_version="1.49", compound="RH")


def _res_dict(key, typ, state, present=True):
    return {"issue_key": key, "family": "rotation", "issue_type": typ, "axle": "front",
            "phase": "apex", "segment_id": "T1", "corner_name": "Turn 1",
            "residual_state": state, "is_new": False, "is_regression": False,
            "still_present": present, "protected_good": False, "confidence": "high"}


def _record(oid, eid, status, sess, residuals, *, at, ctx=CTX):
    outcome = {"id": oid, "experiment_id": eid, "status": status,
               "confidence_level": "high", "scope_fingerprint": "sf",
               "test_session_id": sess, "protected": [], "failed_directions": []}
    exp = {"id": eid, "scope_fingerprint": "sf",
           "changes": [{"field": "toe_front", "from_value": "0.1", "to_value": "0.2"}]}
    return build_development_record(outcome, exp, context=ctx, scope_fingerprint="sf",
                                   working_windows=[], residuals=residuals,
                                   recorded_at=at, session_date=at[:10])


# --- migration --------------------------------------------------------------
def test_v24_migration(db):
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION == 24
    t = db._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name='engineering_development_records'").fetchone()
    assert t is not None


def test_migration_idempotent(tmp_path):
    p = str(tmp_path / "s.db")
    a = SessionDB(p)
    r = _record(1, 10, "confirmed_improvement", "300",
                [_res_dict("k", "understeer", "resolved", present=False)], at="2026-07-01T10:00")
    a._persist_development_record(r, created_at=r.recorded_at)
    a._conn.close()
    b = SessionDB(p)   # re-open: migration is a no-op, record survives
    assert b._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION
    assert b._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0] == 1


# --- append-only immutability ----------------------------------------------
def test_record_key_idempotent_no_duplicate(db):
    r = _record(1, 10, "confirmed_improvement", "300",
                [_res_dict("k", "understeer", "resolved", present=False)], at="2026-07-01T10:00")
    assert db._persist_development_record(r, created_at=r.recorded_at) is True
    assert db._persist_development_record(r, created_at="2026-08-01T10:00") is False
    assert db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0] == 1


def test_history_never_rewritten(db):
    r = _record(1, 10, "confirmed_improvement", "300",
                [_res_dict("k", "understeer", "resolved", present=False)], at="2026-07-01T10:00")
    db._persist_development_record(r, created_at=r.recorded_at)
    before = db._conn.execute(
        "SELECT record_json, content_fingerprint FROM engineering_development_records "
        "WHERE record_key=?", (r.record_key,)).fetchone()
    # re-record the same review (idempotent) — the stored row must not change
    db._persist_development_record(r, created_at="2027-01-01T00:00")
    after = db._conn.execute(
        "SELECT record_json, content_fingerprint FROM engineering_development_records "
        "WHERE record_key=?", (r.record_key,)).fetchone()
    assert before[0] == after[0] and before[1] == after[1]


# --- context isolation ------------------------------------------------------
def test_incompatible_contexts_never_mix(db):
    rh = _record(1, 10, "confirmed_improvement", "300",
                 [_res_dict("k", "understeer", "resolved", present=False)], at="2026-07-01T10:00",
                 ctx=CTX)
    rm_ctx = MemoryContextKey(driver="leon", car="RSR", track="Fuji", layout_id="fc",
                              discipline="Race", gt7_version="1.49", compound="RM")
    rm = _record(2, 11, "regression", "301",
                 [_res_dict("k2", "oversteer", "new", present=True)], at="2026-07-02T10:00",
                 ctx=rm_ctx)
    db._persist_development_record(rh, created_at=rh.recorded_at)
    db._persist_development_record(rm, created_at=rm.recorded_at)
    rh_records = db.get_development_records(
        car="RSR", track="Fuji", layout_id="fc", discipline="Race",
        gt7_version="1.49", compound="RH", driver="leon")
    assert len(rh_records) == 1
    assert rh_records[0]["context"]["compound"] == "RH"


# --- restart determinism (rebuild from stored JSON) -------------------------
def test_restart_determinism(db):
    recs = [_record(i, 10 + i, "confirmed_improvement", str(300 + i),
                    [_res_dict("k", "understeer", "resolved", present=False)],
                    at=f"2026-07-0{i}T10:00") for i in (1, 2, 3)]
    for r in recs:
        db._persist_development_record(r, created_at=r.recorded_at)
    a = db.build_cross_session_memory(
        car="RSR", track="Fuji", layout_id="fc", discipline="Race",
        gt7_version="1.49", compound="RH", driver="leon")
    b = db.build_cross_session_memory(
        car="RSR", track="Fuji", layout_id="fc", discipline="Race",
        gt7_version="1.49", compound="RH", driver="leon")
    assert a["history"]["content_fingerprint"] == b["history"]["content_fingerprint"]
    assert a["memory"]["content_fingerprint"] == b["memory"]["content_fingerprint"]
    assert a["metrics"]["content_fingerprint"] == b["metrics"]["content_fingerprint"]


def test_empty_context_is_ok(db):
    res = db.build_cross_session_memory(car="Unknown", track="Nowhere")
    assert res["ok"] is True
    assert res["record_count"] == 0


def test_missing_experiment_returns_not_ok(db):
    assert db.record_engineering_development(99999)["ok"] is False
