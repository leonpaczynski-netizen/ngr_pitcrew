"""Engineering Brain Phase 11 — persistence + calibration-fold tests."""
import pytest

from data.session_db import SessionDB
from strategy._setup_constants import DB_VERSION
from strategy.postflight_reconciliation import build_reconciliation_record

PREFLIGHT = {"review": {
    "risk_level": "moderate", "content_fingerprint": "pf:abc",
    "experiment": {"candidate_id": "7", "field": "lsd_accel", "direction": "increase",
                   "proposed_value": 25.0, "target_issue": "exit_wheelspin"},
    "consequences": [{"kind": "primary_effect", "field": "lsd_accel", "text": "increases exit traction"}],
    "checklist": [{"status": "ok", "label": "Inside learned window", "why": "w"}],
}}


@pytest.fixture
def db():
    return SessionDB(":memory:")


def _record(outcome_id=55, status="confirmed_improvement"):
    outcome = {"id": outcome_id, "status": status, "protected": []}
    resid = [{"issue_type": "exit_wheelspin", "family": "traction",
              "residual_state": "resolved", "is_new": False, "is_regression": False,
              "still_present": False}]
    return build_reconciliation_record(PREFLIGHT, outcome, resid, memory_context_key="ctxA",
                                       recorded_at="2026-07-19T10:00")


def test_v25_migration(db):
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION == 25
    t = db._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name='engineering_reconciliation_records'").fetchone()
    assert t is not None


def test_migration_idempotent(tmp_path):
    p = str(tmp_path / "s.db")
    a = SessionDB(p)
    a._persist_reconciliation_record(_record(), created_at="2026-07-19T10:00")
    a._conn.close()
    b = SessionDB(p)
    assert b._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION
    assert b._conn.execute(
        "SELECT COUNT(*) FROM engineering_reconciliation_records").fetchone()[0] == 1


def test_append_only_idempotent(db):
    rec = _record()
    assert db._persist_reconciliation_record(rec, created_at="2026-07-19T10:00") is True
    assert db._persist_reconciliation_record(rec, created_at="2027-01-01T00:00") is False
    assert db._conn.execute(
        "SELECT COUNT(*) FROM engineering_reconciliation_records").fetchone()[0] == 1


def test_never_rewritten(db):
    rec = _record()
    db._persist_reconciliation_record(rec, created_at="2026-07-19T10:00")
    before = db._conn.execute(
        "SELECT record_json, content_fingerprint FROM engineering_reconciliation_records "
        "WHERE record_key=?", (rec.record_key,)).fetchone()
    db._persist_reconciliation_record(rec, created_at="2028-01-01T00:00")
    after = db._conn.execute(
        "SELECT record_json, content_fingerprint FROM engineering_reconciliation_records "
        "WHERE record_key=?", (rec.record_key,)).fetchone()
    assert before[0] == after[0] and before[1] == after[1]


def test_calibration_fold_and_restart_determinism(db):
    db._persist_reconciliation_record(_record(55, "confirmed_improvement"),
                                      created_at="2026-07-19T10:00")
    db._persist_reconciliation_record(_record(56, "regression"),
                                      created_at="2026-07-20T10:00")
    a = db.build_prediction_calibration("ctxA")
    b = db.build_prediction_calibration("ctxA")
    assert a["calibration"]["reconciliations"] == 2
    assert a["calibration"] == b["calibration"]
    assert 0.0 <= a["calibration"]["overall_accuracy"] <= 1.0


def test_empty_calibration_ok(db):
    res = db.build_prediction_calibration("nonexistent")
    assert res["ok"] and res["record_count"] == 0


def test_context_isolation(db):
    db._persist_reconciliation_record(_record(), created_at="2026-07-19T10:00")
    other = build_reconciliation_record(
        PREFLIGHT, {"id": 99, "status": "confirmed_improvement", "protected": []},
        [{"issue_type": "x", "family": "y", "residual_state": "resolved",
          "still_present": False}], memory_context_key="ctxOTHER",
        recorded_at="2026-07-19T10:00")
    db._persist_reconciliation_record(other, created_at="2026-07-19T10:00")
    assert len(db.get_reconciliation_records("ctxA")) == 1
    assert len(db.get_reconciliation_records("ctxOTHER")) == 1
