"""Engineering-Brain Phase 2 — setup-experiment persistence tests.

Covers the additive DB v21 ledger + repository APIs in data/session_db.py:
idempotent migration, atomic creation, atomic rollback, append-only evidence +
state history, scope/setup/lineage/checkpoint/session queries, NULL unknowns,
indexes, and Phase 1 read-back. Uses an isolated in-memory SessionDB.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from data.session_db import SessionDB
from strategy._setup_constants import DB_VERSION
from strategy.setup_experiment import (
    build_experiment_from_recommendation, ExperimentEvidence, EvidencePhase,
    EvidenceStance,
)

ROOT = Path(__file__).resolve().parents[1]


def _rec_data(status="approved", changes=None):
    return {
        "recommendation_status": status,
        "analysis": "exit oversteer",
        "changes": changes if changes is not None else [
            {"field": "lsd_accel", "from": "8", "to_clamped": "12", "rule_id": "R1"},
            {"field": "rear_arb", "from": "6", "to_clamped": "5", "rule_id": "R2"},
        ],
        "diagnosis": {"dominant_problem": "exit_oversteer", "unresolved": ["gearing"]},
        "protected_fields": ["brake_bias"],
        "deterministic_plan": {"rule_engine_version": "46.0"},
        "rollback": {"label": "Base RSR"},
    }


def _exp(db=None, *, car_id=7, track="Fuji", layout_id="full_course",
         discipline="Race", parent="base1", status="approved", changes=None):
    return build_experiment_from_recommendation(
        _rec_data(status, changes), car_id=car_id, track=track, layout_id=layout_id,
        discipline=discipline, parent_setup_id=parent)


@pytest.fixture
def db():
    return SessionDB(":memory:")


# ------------------------------------------------------------------ 11 migration
def test_user_version_is_21(db):
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION
    assert DB_VERSION >= 21


def test_all_six_tables_exist(db):
    tables = {r[0] for r in db._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {
        "setup_experiments", "setup_experiment_changes",
        "setup_experiment_protected_behaviours", "setup_experiment_test_protocol",
        "setup_experiment_evidence", "setup_experiment_state_history",
    } <= tables


def test_migration_idempotent(tmp_path):
    p = str(tmp_path / "s.db")
    a = SessionDB(p)
    a.create_setup_experiment(_exp())
    a._conn.close()
    b = SessionDB(p)
    assert b._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION
    assert b._conn.execute("SELECT COUNT(*) FROM setup_experiments").fetchone()[0] == 1


# ------------------------------------------------------------------ 20 indexes
def test_required_indexes_exist(db):
    idx = {r[0] for r in db._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
    for name in ("idx_setup_exp_scope", "idx_setup_exp_context",
                 "idx_setup_exp_parent", "idx_setup_exp_lineage",
                 "idx_setup_exp_checkpoint", "idx_setup_exp_session",
                 "idx_setup_exp_status", "idx_setup_exp_created"):
        assert name in idx, name


# ------------------------------------------------------------------ 12 atomic creation
def test_atomic_creation_writes_all_children(db):
    eid = db.create_setup_experiment(_exp())
    assert eid is not None
    full = db.get_setup_experiment(eid)
    assert len(full["changes"]) == 2
    assert len(full["protected_behaviours"]) == 1
    assert full["test_protocol"] is not None
    assert full["test_protocol"]["rollback_target"] == "Base RSR"
    assert len(full["evidence"]) >= 1              # recommendation-time snapshot
    assert len(full["state_history"]) == 1         # creation transition
    assert full["state_history"][0]["to_status"] == "draft"


# ------------------------------------------------------------------ 13 rollback
def test_failed_child_write_rolls_back_whole_experiment(db):
    db._conn.execute("DROP TABLE setup_experiment_changes")   # force a child failure
    rid = db.create_setup_experiment(_exp())
    assert rid is None
    assert db._conn.execute("SELECT COUNT(*) FROM setup_experiments").fetchone()[0] == 0
    assert db._conn.execute(
        "SELECT COUNT(*) FROM setup_experiment_state_history").fetchone()[0] == 0


# ------------------------------------------------------------------ idempotent create
def test_duplicate_create_is_idempotent(db):
    e = _exp()
    a = db.create_setup_experiment(e)
    b = db.create_setup_experiment(e)
    assert a == b
    assert db._conn.execute("SELECT COUNT(*) FROM setup_experiments").fetchone()[0] == 1


# ------------------------------------------------------------------ 14 evidence append-only
def test_evidence_ledger_is_append_only(db):
    eid = db.create_setup_experiment(_exp())
    before = len(db.get_experiment_evidence(eid))
    ev = ExperimentEvidence(
        evidence_type="driver_feedback", phase=EvidencePhase.TEST,
        source_table="driver_feedback", source_id="42",
        summary="rear more planted on exit", stance=EvidenceStance.SUPPORTS,
        lap=7)
    rid = db.append_experiment_evidence(eid, ev)
    assert rid is not None
    after = db.get_experiment_evidence(eid)
    assert len(after) == before + 1
    # recommendation-time evidence still present (nothing overwritten)
    assert any(e["phase"] == "diagnosis" for e in after)
    assert any(e["phase"] == "test" and e["lap"] == 7 for e in after)


# ------------------------------------------------------------------ 15 state history append-only
def test_state_history_append_only(db):
    eid = db.create_setup_experiment(_exp())
    assert db.transition_experiment_state(eid, "ready_for_apply", source="analyse")
    hist = db.get_experiment_state_history(eid)
    assert len(hist) == 2
    assert hist[0]["to_status"] == "draft"
    assert hist[1]["from_status"] == "draft" and hist[1]["to_status"] == "ready_for_apply"


def test_invalid_transition_not_recorded(db):
    eid = db.create_setup_experiment(_exp())
    # DRAFT -> APPLIED is not permitted (needs ready + checkpoint)
    assert db.transition_experiment_state(eid, "applied") is False
    assert len(db.get_experiment_state_history(eid)) == 1  # unchanged


# ------------------------------------------------------------------ 16,17 queries
def test_query_by_scope(db):
    eid = db.create_setup_experiment(_exp())
    scope = db.get_setup_experiment(eid)["scope_fingerprint"]
    rows = db.list_setup_experiments_by_scope(scope)
    assert len(rows) == 1 and rows[0]["id"] == eid


def test_query_by_parent_lineage_checkpoint_session(db):
    e = build_experiment_from_recommendation(
        _rec_data(), car_id=7, track="Fuji", layout_id="full",
        discipline="Race", parent_setup_id="P1", lineage_id="55", session_id=9)
    eid = db.create_setup_experiment(e)
    assert db.list_setup_experiments_by_parent_setup("P1")[0]["id"] == eid
    assert db.list_setup_experiments_by_lineage("55")[0]["id"] == eid
    assert db.list_setup_experiments_by_session("9")[0]["id"] == eid
    # link a checkpoint then query by it
    db.transition_experiment_state(eid, "ready_for_apply")
    db.link_experiment_applied_checkpoint(eid, "cpZ", {"lsd_accel": 12})
    assert db.list_setup_experiments_by_checkpoint("cpZ")[0]["id"] == eid


# ------------------------------------------------------------------ 18 Phase 1 read-back
def test_phase1_contexts_still_readable(db):
    sid = db.open_session(car_id=7, track="Fuji", session_type="Race",
                          layout_id="full_course")
    ctx = db.get_engineering_context_for_source("session", sid)
    assert ctx is not None
    # And a Phase-2 experiment on the same scope shares the scope fingerprint.
    eid = db.create_setup_experiment(_exp())
    exp_scope = db.get_setup_experiment(eid)["scope_fingerprint"]
    # session had no driver/gt7 either → same scope key formula
    assert exp_scope == ctx["scope_fingerprint"]


# ------------------------------------------------------------------ 19 NULL unknowns
def test_unknown_values_are_null(db):
    e = build_experiment_from_recommendation(
        _rec_data(changes=[{"field": "lsd_accel", "to_clamped": "12"}]),
        car_id=7, track="Fuji", layout_id="full")
    eid = db.create_setup_experiment(e)
    row = db._conn.execute(
        "SELECT from_value, delta_magnitude FROM setup_experiment_changes "
        "WHERE experiment_id=?", (eid,)).fetchone()
    assert row[0] is None            # unknown from_value stored as NULL
    assert row[1] is None            # unknown magnitude stored as NULL
    # unknown session_id is NULL, not ''
    prow = db._conn.execute(
        "SELECT session_id FROM setup_experiments WHERE id=?", (eid,)).fetchone()
    assert prow[0] is None


# ------------------------------------------------------------------ admin lifecycle
def test_invalidate_and_cancel_are_append_only(db):
    eid = db.create_setup_experiment(_exp())
    assert db.invalidate_setup_experiment(eid, "duplicate of another test")
    assert db.get_setup_experiment(eid)["status"] == "invalid"
    hist = db.get_experiment_state_history(eid)
    assert hist[-1]["to_status"] == "invalid"
    assert "duplicate" in hist[-1]["reason"]
    # original creation record untouched
    assert hist[0]["to_status"] == "draft"

    e2 = _exp(car_id=8, track="Spa", layout_id="gp", parent="p2")
    id2 = db.create_setup_experiment(e2)
    assert db.cancel_setup_experiment(id2, "changed mind")
    assert db.get_setup_experiment(id2)["status"] == "cancelled"


def test_immutable_changes_after_creation(db):
    # There is no repository API that UPDATEs the change rows; verify the create
    # snapshot is preserved across an admin state change.
    eid = db.create_setup_experiment(_exp())
    before = db.get_setup_experiment(eid)["changes"]
    db.invalidate_setup_experiment(eid, "x")
    after = db.get_setup_experiment(eid)["changes"]
    assert [c["to_value"] for c in before] == [c["to_value"] for c in after]
