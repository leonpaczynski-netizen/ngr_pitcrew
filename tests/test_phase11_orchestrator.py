"""Engineering Brain Phase 11 — SessionDB reconciliation orchestrator + golden UAT.

The golden UAT drives the real review_and_learn loop to produce a completed outcome,
builds the Phase-10 pre-flight for the same experiment, then reconciles prediction vs
actual and persists an immutable calibration record.
"""
import dataclasses

import pytest

from data.session_db import SessionDB
from data.applied_checkpoint import make_checkpoint
from strategy._setup_constants import DB_VERSION
from strategy.setup_experiment import build_experiment_from_recommendation, ProtectedBehaviour
from strategy.setup_experiment_outcome import DriverReviewInput

CAR_ID, CAR = 7, "Porsche 911 RSR (991) '17"
TRACK, LAYOUT = "Fuji International Speedway", "full_course"


@pytest.fixture
def db():
    d = SessionDB(":memory:")
    d._conn.execute("INSERT INTO cars (id, name, category) VALUES (?,?,?)",
                    (CAR_ID, CAR, "Gr.3"))
    d._conn.commit()
    return d


def _experiment(db, *, field, frm, to, symptom, target):
    data = {"recommendation_status": "approved", "analysis": symptom,
            "changes": [{"field": field, "from": frm, "to_clamped": to,
                         "rule_id": "R", "symptom": symptom}],
            "diagnosis": {"dominant_problem": symptom, "target_corners": [target]},
            "deterministic_plan": {"rule_engine_version": "46.0"},
            "test_sequence": {"stages": [{"success_criterion": "x", "rollback": "Base"}]},
            "rollback": {"label": "Base RSR Race"}}
    e = build_experiment_from_recommendation(
        data, car_id=CAR_ID, track=TRACK, layout_id=LAYOUT, discipline="Race",
        parent_setup_id="base_rsr")
    e = dataclasses.replace(
        e, protected_behaviours=(ProtectedBehaviour("rear traction", corners=("T5",)),),
        test_protocol=dataclasses.replace(e.test_protocol, min_clean_laps=4,
                                          target_corners=(target,),
                                          rollback_target="Base RSR Race")).with_idempotency_key()
    eid = db.create_setup_experiment(e)
    db.transition_experiment_state(eid, "ready_for_apply")
    cp = make_checkpoint(setup_id=f"exp{eid}", fields={field: float(to)}, confirmed_at="t")
    db.save_applied_checkpoint(CAR_ID, TRACK, LAYOUT, "Race", cp)
    db.link_experiment_applied_checkpoint(eid, cp.checkpoint_id, {field: float(to)})
    return eid, cp.checkpoint_id


def _laps(db, sid, n):
    for i in range(1, n + 1):
        db._conn.execute(
            "INSERT INTO lap_records (session_id, car_id, track, lap_num, lap_time_ms, "
            "is_pit_lap, is_out_lap, compound) VALUES (?,?,?,?,?,0,0,'RH')",
            (sid, CAR_ID, TRACK, i, 95000))
    db._conn.commit()


def _occ(sid, cp, laps, seg, issue, phase, axle=""):
    return [{"session_id": sid, "setup_checkpoint_id": cp, "lap_number": n,
             "segment_id": seg, "corner_phase": phase, "issue_type": issue,
             "axle": axle, "confidence": 0.85} for n in laps]


SELECTION = {
    "candidate_id": "auto", "target_issue": "understeer", "field": "aero_front",
    "direction": "increase", "current_value": 300.0, "proposed_value": 340.0,
    "expected_positive_effect": "increases apex front support",
    "expected_negative_effects": ["reduces fuel efficiency"],
    "protected_behaviours_at_risk": [], "supporting_evidence": ["recurring understeer"],
    "window_relationship": "inside_window", "evidence_grade": "medium",
}


def _run_resolve(db):
    eid, cp = _experiment(db, field="aero_front", frm="300", to="340",
                          symptom="mid_corner_understeer", target="T3")
    _laps(db, 500, 5); _laps(db, 600, 5)
    db.save_issue_occurrences(CAR_ID, TRACK, LAYOUT,
        _occ(500, "", [2, 3, 4, 5], "T3", "understeer", "apex"))
    db.save_issue_occurrences(CAR_ID, TRACK, LAYOUT,
        _occ(600, cp, [2], "T3", "understeer", "apex"))
    db.review_and_learn(eid, test_session_id=600, baseline_session_id=500,
                        driver_review=DriverReviewInput("f", True,
                                                        target_symptom_resolved=True,
                                                        vs_previous="better"))
    return eid


def test_no_migration_needed_beyond_v25(db):
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION == 28


def test_no_preflight_returns_not_ok(db):
    eid = _run_resolve(db)
    assert db.record_experiment_reconciliation(eid, {})["ok"] is False


def test_golden_uat_reconcile_after_real_review(db):
    eid = _run_resolve(db)
    # build the Phase-10 pre-flight for the SAME experiment, then reconcile
    pf = db.build_experiment_preflight(SELECTION, car=CAR, track=TRACK, layout_id=LAYOUT,
                                       discipline="Race", compound="RH")
    r = db.record_experiment_reconciliation(eid, pf)
    assert r["ok"]
    assert r["recorded"] is True
    rec = r["record"]
    # the understeer target was resolved → the primary consequence is confirmed
    prim = [c for c in rec["consequence_reconciliations"] if c["kind"] == "primary_effect"]
    assert prim and prim[0]["status"] in ("confirmed", "partially_confirmed")
    assert rec["accuracy"]["overall_accuracy"] >= 0.0


def test_reconciliation_idempotent_and_writes_only_its_log(db):
    eid = _run_resolve(db)
    pf = db.build_experiment_preflight(SELECTION, car=CAR, track=TRACK, layout_id=LAYOUT,
                                       discipline="Race", compound="RH")
    dev_before = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0]
    a = db.record_experiment_reconciliation(eid, pf)
    b = db.record_experiment_reconciliation(eid, pf)   # same prediction → no duplicate
    assert a["recorded"] is True and b["recorded"] is False
    n = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_reconciliation_records").fetchone()[0]
    assert n == 1
    # did not touch the development records
    dev_after = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0]
    assert dev_after == dev_before


def test_calibration_summary_after_reconcile(db):
    eid = _run_resolve(db)
    pf = db.build_experiment_preflight(SELECTION, car=CAR, track=TRACK, layout_id=LAYOUT,
                                       discipline="Race", compound="RH")
    db.record_experiment_reconciliation(eid, pf, compound="RH")
    cal = db.build_prediction_calibration(car=CAR, track=TRACK, layout_id=LAYOUT,
                                          discipline="Race", compound="RH")
    assert cal["ok"]
    assert cal["calibration"]["reconciliations"] >= 1
