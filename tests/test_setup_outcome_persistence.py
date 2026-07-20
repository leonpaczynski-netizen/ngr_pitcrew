"""Engineering-Brain Phase 3 — outcome persistence tests (DB v22).

Covers the additive v22 ledger + repository APIs: migration, atomic/idempotent
creation, immutability, append-only children, superseding audit, rollback, and
Phase 1/2 read-back. Isolated in-memory SessionDB.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from data.session_db import SessionDB
from strategy._setup_constants import DB_VERSION
from strategy.setup_experiment_outcome import (
    ExperimentSnapshot, LapAggregate, CornerObservation, DriverReviewInput,
    ConfounderInput, AssociationResult, AssociationStatus, OutcomeInputs,
    evaluate_outcome, evaluate_lap_validity,
)

ROOT = Path(__file__).resolve().parents[1]


def _exp(**over):
    base = dict(experiment_id=1, scope_fingerprint="eck_v1:scope:abc",
                parent_setup_id="base1", applied_checkpoint_id="cp1",
                primary_diagnosis="front_lock", target_corners=("T1",),
                rollback_target="Base RSR", min_clean_laps=4,
                changes=({"field": "brake_bias", "from": "55", "to": "52",
                          "direction": "decrease", "rule_id": "BB1"},),
                protected_behaviours=({"behaviour": "rear traction", "field": "",
                                       "corners": ["T5"]},))
    base.update(over)
    return ExperimentSnapshot(**base)


def _outcome(*, exp=None, test_t1=1, t5=0, valid=5, evidence_fp=""):
    exp = exp or _exp()
    validity = evaluate_lap_validity(LapAggregate(clean_count=valid, median_lap_ms=95000),
                                     total_laps=valid, min_required=4)
    inp = OutcomeInputs(
        experiment=exp,
        association=AssociationResult(AssociationStatus.RESOLVED, candidate_experiment_ids=(1,)),
        validity=validity,
        baseline=LapAggregate(clean_count=5, median_lap_ms=95200, avg_lock_up=4.0),
        test=LapAggregate(clean_count=valid, median_lap_ms=95000, avg_lock_up=0.5),
        corner_baseline=(CornerObservation("T1", "T1", "braking", "front_lock", 5, 5),
                         CornerObservation("T5", "T5", "exit", "rear_wheelspin", 0, 5)),
        corner_test=(CornerObservation("T1", "T1", "braking", "front_lock", test_t1, 5),
                     CornerObservation("T5", "T5", "exit", "rear_wheelspin", t5, 5)),
        driver_review=DriverReviewInput("f", True, target_symptom_resolved=(test_t1 <= 1),
                                        vs_previous=("better" if t5 == 0 else "worse")),
        test_session_id="200", evidence_fingerprint=evidence_fp)
    return evaluate_outcome(inp)


@pytest.fixture
def db():
    return SessionDB(":memory:")


# ------------------------------------------------------------------ 34,35 migration
def test_user_version_is_22(db):
    # Phase 3 shipped the v22 outcome tables; later phases advance the schema.
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION
    assert DB_VERSION >= 22


def test_all_five_tables_exist(db):
    tables = {r[0] for r in db._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"setup_experiment_outcomes", "setup_experiment_outcome_criteria",
            "setup_experiment_outcome_protected", "setup_experiment_outcome_corners",
            "setup_experiment_failed_directions"} <= tables


def test_indexes_exist(db):
    idx = {r[0] for r in db._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
    for n in ("idx_exp_outcome_experiment", "idx_exp_outcome_scope",
              "idx_exp_outcome_checkpoint", "idx_exp_outcome_session",
              "idx_exp_outcome_status", "idx_exp_failed_dir_scope"):
        assert n in idx, n


def test_migration_idempotent(tmp_path):
    p = str(tmp_path / "s.db")
    a = SessionDB(p)
    a.create_experiment_outcome(_outcome(), car="RSR", track="Fuji", layout_id="fc")
    a._conn.close()
    b = SessionDB(p)
    assert b._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION
    assert b._conn.execute("SELECT COUNT(*) FROM setup_experiment_outcomes").fetchone()[0] == 1


# ------------------------------------------------------------------ 38 atomic + children
def test_atomic_creation_writes_children(db):
    oid = db.create_experiment_outcome(_outcome(t5=5), car="RSR", track="Fuji",
                                       layout_id="fc")
    assert oid is not None
    full = db.get_experiment_outcome(oid)
    assert full["status"] == "regression"
    assert len(full["criteria"]) >= 1
    assert len(full["protected"]) >= 1
    assert len(full["corners"]) == 2
    assert len(full["failed_directions"]) >= 1


# ------------------------------------------------------------------ 43 rollback
def test_failed_child_write_rolls_back(db):
    db._conn.execute("DROP TABLE setup_experiment_outcome_corners")
    oid = db.create_experiment_outcome(_outcome(), car="RSR", track="Fuji", layout_id="fc")
    assert oid is None
    assert db._conn.execute("SELECT COUNT(*) FROM setup_experiment_outcomes").fetchone()[0] == 0


# ------------------------------------------------------------------ 39,40 idempotency
def test_deterministic_idempotency(db):
    a = db.create_experiment_outcome(_outcome(), car="RSR", track="Fuji", layout_id="fc")
    b = db.create_experiment_outcome(_outcome(), car="RSR", track="Fuji", layout_id="fc")
    assert a == b
    assert db._conn.execute("SELECT COUNT(*) FROM setup_experiment_outcomes").fetchone()[0] == 1


def test_different_evidence_makes_new_outcome(db):
    a = db.create_experiment_outcome(_outcome(evidence_fp="run1"), car="RSR",
                                     track="Fuji", layout_id="fc")
    b = db.create_experiment_outcome(_outcome(evidence_fp="run2"), car="RSR",
                                     track="Fuji", layout_id="fc")
    assert a != b
    assert db._conn.execute("SELECT COUNT(*) FROM setup_experiment_outcomes").fetchone()[0] == 2


# ------------------------------------------------------------------ 36,41 immutable + supersede
def test_outcome_immutable_no_update_api(db):
    src = (ROOT / "data" / "session_db.py").read_text(encoding="utf-8")
    # The only writes to the immutable columns are the initial INSERT; audit
    # columns (superseded_by / invalidated_reason) are the sole UPDATE targets.
    import re
    updates = re.findall(r"UPDATE setup_experiment_outcomes SET (\w+)", src)
    assert set(updates) <= {"superseded_by", "invalidated_reason"}, updates


def test_superseding_is_audited(db):
    a = db.create_experiment_outcome(_outcome(evidence_fp="run1"), car="RSR",
                                     track="Fuji", layout_id="fc")
    b = db.create_experiment_outcome(_outcome(evidence_fp="run2"), car="RSR",
                                     track="Fuji", layout_id="fc")
    db.supersede_experiment_outcome(a, b)
    old = db.get_experiment_outcome(a)
    assert old["superseded_by"] == b            # prior points to replacement
    assert old["status"]                         # prior conclusion still present
    # latest resolves to the superseding one
    latest = db.get_latest_experiment_outcome(1)
    assert latest["id"] == b


def test_invalidation_is_audited(db):
    oid = db.create_experiment_outcome(_outcome(), car="RSR", track="Fuji", layout_id="fc")
    db.invalidate_experiment_outcome(oid, "wrong session attributed")
    row = db.get_experiment_outcome(oid)
    assert row["invalidated_reason"] == "wrong session attributed"
    assert row["status"]                         # row not deleted
    assert db.get_latest_experiment_outcome(1) is None  # excluded from 'latest'


# ------------------------------------------------------------------ 37 append-only children
def test_children_are_append_only(db):
    src = (ROOT / "data" / "session_db.py").read_text(encoding="utf-8")
    for tbl in ("setup_experiment_outcome_criteria",
                "setup_experiment_outcome_protected",
                "setup_experiment_outcome_corners"):
        assert f"UPDATE {tbl}" not in src
        assert f"DELETE FROM {tbl}" not in src


# ------------------------------------------------------------------ scope queries
def test_failed_directions_scoped(db):
    db.create_experiment_outcome(_outcome(t5=5), car="RSR", track="Fuji", layout_id="fc")
    rows = db.list_failed_directions_by_scope("eck_v1:scope:abc")
    assert rows and rows[0]["field"] == "brake_bias"
    assert db.list_failed_directions_for_field("RSR", "Fuji", "fc", "brake_bias")


# ------------------------------------------------------------------ 42 Phase 1/2 readable
def test_phase1_and_phase2_still_readable(db):
    sid = db.open_session(car_id=7, track="Fuji", session_type="Race", layout_id="fc")
    assert db.get_engineering_context_for_source("session", sid) is not None
    # a Phase 2 experiment table is still queryable
    assert db._conn.execute("SELECT COUNT(*) FROM setup_experiments").fetchone()[0] == 0
    # writing an outcome does not disturb Phase 1 context rows
    db.create_experiment_outcome(_outcome(), car="RSR", track="Fuji", layout_id="fc")
    assert db.get_engineering_context_for_source("session", sid) is not None
