"""Engineering-Brain Phase 5 — working-window persistence (v23) tests."""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from data.session_db import SessionDB
from data.applied_checkpoint import make_checkpoint
from strategy._setup_constants import DB_VERSION
from strategy.setup_experiment import build_experiment_from_recommendation, ProtectedBehaviour
from strategy.setup_experiment_outcome import DriverReviewInput

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def db():
    d = SessionDB(":memory:")
    d._conn.execute("INSERT INTO cars (id, name) VALUES (7, ?)", ("Porsche 911 RSR",))
    d._conn.commit()
    return d


def _applied_experiment(db, *, field="rear_arb", frm="6", to="5",
                        symptom="mid_corner_understeer", target="T3", parent="base1"):
    data = {"recommendation_status": "approved", "analysis": symptom,
            "changes": [{"field": field, "from": frm, "to_clamped": to,
                         "rule_id": "R", "symptom": symptom}],
            "diagnosis": {"dominant_problem": symptom, "target_corners": [target]},
            "deterministic_plan": {"rule_engine_version": "46.0"},
            "test_sequence": {"stages": [{"success_criterion": "reduced", "rollback": "Base"}]},
            "rollback": {"label": "Base RSR"}}
    e = build_experiment_from_recommendation(
        data, car_id=7, track="Fuji", layout_id="full_course", discipline="Race",
        parent_setup_id=parent)
    e = dataclasses.replace(
        e, protected_behaviours=(ProtectedBehaviour("rear traction", corners=("T5",)),),
        test_protocol=dataclasses.replace(e.test_protocol, min_clean_laps=4,
                                          target_corners=(target,))).with_idempotency_key()
    eid = db.create_setup_experiment(e)
    db.transition_experiment_state(eid, "ready_for_apply")
    cp = make_checkpoint(setup_id=f"exp{eid}", fields={field: float(to)}, confirmed_at="t")
    db.save_applied_checkpoint(7, "Fuji", "full_course", "Race", cp)
    db.link_experiment_applied_checkpoint(eid, cp.checkpoint_id, {field: float(to)})
    return eid, cp.checkpoint_id, e.scope_fingerprint


def _laps(db, sid, n, t):
    for i in range(1, n + 1):
        db._conn.execute("INSERT INTO lap_records (session_id, car_id, track, lap_num, "
                         "lap_time_ms, is_pit_lap, is_out_lap) VALUES (?,?,?,?,?,0,0)",
                         (sid, 7, "Fuji", i, t))
    db._conn.commit()


def _improve(db, eid, cp, seg="T3", issue="understeer"):
    _laps(db, 100, 5, 95200); _laps(db, 200, 5, 95000)
    db.save_issue_occurrences(7, "Fuji", "full_course",
        [{"session_id": 100, "setup_checkpoint_id": "", "lap_number": n,
          "segment_id": seg, "corner_phase": "apex", "issue_type": issue,
          "confidence": 0.8} for n in (2, 3, 4, 5)])
    db.save_issue_occurrences(7, "Fuji", "full_course",
        [{"session_id": 200, "setup_checkpoint_id": cp, "lap_number": 2,
          "segment_id": seg, "corner_phase": "apex", "issue_type": issue, "confidence": 0.8}])
    return db.review_and_learn(eid, test_session_id=200, baseline_session_id=100,
                              driver_review=DriverReviewInput("f", True,
                                  target_symptom_resolved=True, vs_previous="better"))


# --- 12.7 persistence ------------------------------------------------------
def test_user_version_matches_db_version(db):
    # Phase 5 brought the schema to v23; later phases (Phase 8 → v24) advance it.
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION
    assert DB_VERSION >= 23


def test_tables_and_indexes_exist(db):
    tables = {r[0] for r in db._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"setup_working_windows", "setup_working_window_evidence"} <= tables
    idx = {r[0] for r in db._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
    assert "idx_ww_evidence_context" in idx and "idx_ww_scope" in idx


def test_migration_idempotent(tmp_path):
    p = str(tmp_path / "s.db")
    a = SessionDB(p)
    a._conn.execute("INSERT INTO cars (id, name) VALUES (7, ?)", ("Porsche 911 RSR",))
    a._conn.commit()
    eid, cp, _ = _applied_experiment(a)
    _improve(a, eid, cp)
    a._conn.close()
    b = SessionDB(p)   # re-open: migration is a no-op, learning survives
    assert b._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION
    assert b._conn.execute("SELECT COUNT(*) FROM setup_working_window_evidence").fetchone()[0] == 1


def test_learn_persists_window(db):
    eid, cp, scope = _applied_experiment(db)
    r = _improve(db, eid, cp)
    assert r["learning"]["ok"]
    w = db.get_working_window(scope, "rear_arb", car="Porsche 911 RSR", track="Fuji",
                              layout_id="full_course", discipline="Race")
    assert w and w["confidence"] == "provisional" and w["successful_values"] == [5.0]


def test_idempotent_learning_no_double_count(db):
    eid, cp, _ = _applied_experiment(db)
    _improve(db, eid, cp)
    db.learn_from_experiment_outcome(eid)   # replay
    db.learn_from_experiment_outcome(eid)   # replay again
    n = db._conn.execute("SELECT COUNT(*) FROM setup_working_window_evidence").fetchone()[0]
    assert n == 1


def test_unique_constraint_on_evidence_triple(db):
    eid, cp, _ = _applied_experiment(db)
    _improve(db, eid, cp)
    # a second learn of the same experiment/outcome must not insert a duplicate
    before = db._conn.execute("SELECT COUNT(*) FROM setup_working_window_evidence").fetchone()[0]
    db.learn_from_experiment_outcome(eid)
    after = db._conn.execute("SELECT COUNT(*) FROM setup_working_window_evidence").fetchone()[0]
    assert before == after


def test_provenance_round_trip(db):
    eid, cp, scope = _applied_experiment(db)
    _improve(db, eid, cp)
    w = db.get_working_window(scope, "rear_arb", car="Porsche 911 RSR", track="Fuji",
                              layout_id="full_course", discipline="Race")
    assert str(eid) in w["supporting_experiment_ids"]
    assert cp in w["supporting_checkpoint_ids"]


def test_stable_ordering_list_windows(db):
    eid, cp, scope = _applied_experiment(db)
    _improve(db, eid, cp)
    a = db.list_working_windows(scope)
    b = db.list_working_windows(scope)
    assert a == b and len(a) >= 1


def test_reload_reproduces_same_next_experiment(tmp_path):
    p = str(tmp_path / "s.db")
    a = SessionDB(p)
    a._conn.execute("INSERT INTO cars (id, name) VALUES (7, ?)", ("Porsche 911 RSR",))
    a._conn.commit()
    eid, cp, _ = _applied_experiment(a, field="lsd_accel", frm="22", to="26",
                                     symptom="rear_loose_on_exit", target="T5")
    # regression scenario
    _laps(a, 100, 5, 95200); _laps(a, 200, 5, 95000)
    a.save_issue_occurrences(7, "Fuji", "full_course",
        [{"session_id": 100, "lap_number": 2, "segment_id": "T5", "corner_phase": "exit",
          "issue_type": "wheelspin", "axle": "rear", "confidence": 0.8}])
    a.save_issue_occurrences(7, "Fuji", "full_course",
        [{"session_id": 200, "setup_checkpoint_id": cp, "lap_number": n,
          "segment_id": "T5", "corner_phase": "exit", "issue_type": "wheelspin",
          "axle": "rear", "confidence": 0.8} for n in (2, 3, 4, 5)])
    a.review_and_learn(eid, test_session_id=200, baseline_session_id=100,
                       driver_review=DriverReviewInput("f", True, vs_previous="worse"))
    sel_a = a.select_next_experiment(eid, dominant_issue="rear_loose_on_exit",
                                     target_corners=["T5"], recurrence_class="recurring",
                                     valid_lap_count=5,
                                     current_setup={"lsd_accel": 26, "aero_rear": 400})
    a._conn.close()
    b = SessionDB(p)   # restart
    sel_b = b.select_next_experiment(eid, dominant_issue="rear_loose_on_exit",
                                     target_corners=["T5"], recurrence_class="recurring",
                                     valid_lap_count=5,
                                     current_setup={"lsd_accel": 26, "aero_rear": 400})
    sa = (sel_a.get("selected") or {}).get("candidate_id")
    sb = (sel_b.get("selected") or {}).get("candidate_id")
    assert sa == sb                    # deterministic across restart
    assert sa != "lsd_accel:increase"  # failed direction never re-selected
