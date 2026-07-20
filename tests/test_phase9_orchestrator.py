"""Engineering Brain Phase 9 — SessionDB orchestrator + golden UAT.

The orchestrator (`build_engineering_context`) is a READ-ONLY OBSERVER that regenerates
transfers/constraints/risks from the immutable Phase-8 records with NO migration. The
golden UAT drives the real review_and_learn loop to build history, then queries the
Phase-9 advisory for a proposed change.
"""
import dataclasses

import pytest

from data.session_db import SessionDB
from data.applied_checkpoint import make_checkpoint
from strategy._setup_constants import DB_VERSION
from strategy.development_history import MemoryContextKey, build_development_record
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


def _res(key, typ, state, new=False, present=True):
    return {"issue_key": key, "family": "rotation", "issue_type": typ, "axle": "front",
            "phase": "apex", "segment_id": "T1", "corner_name": "T1",
            "residual_state": state, "is_new": new, "is_regression": False,
            "still_present": present, "protected_good": False, "confidence": "high"}


def _persist(db, ctx, oid, eid, status, sess, field, residuals, failed=(),
             at="2026-07-01T10:00"):
    outcome = {"id": oid, "experiment_id": eid, "status": status,
               "confidence_level": "high", "scope_fingerprint": "sf",
               "test_session_id": sess, "protected": [], "failed_directions": list(failed)}
    exp = {"id": eid, "scope_fingerprint": "sf",
           "changes": [{"field": field, "from_value": "20", "to_value": "30",
                        "delta_direction": "increase"}]}
    rec = build_development_record(outcome, exp, context=ctx, scope_fingerprint="sf",
                                  working_windows=[], residuals=residuals,
                                  recorded_at=at, session_date=at[:10])
    db._persist_development_record(rec, created_at=rec.recorded_at)


DIRECT = MemoryContextKey(driver="", car=CAR, track=TRACK, layout_id=LAYOUT,
                          discipline="Race", gt7_version="", compound="")


# --- no migration -----------------------------------------------------------
def test_no_migration(db):
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION == 27


# --- end-to-end -------------------------------------------------------------
def test_end_to_end_transfers_constraints_risks(db):
    _persist(db, DIRECT, 1, 10, "regression", "300", "lsd_accel",
             [_res("k", "oversteer", "new", new=True)],
             failed=[{"field": "lsd_accel", "direction": "increase", "magnitude": "30",
                      "severity": "high"}], at="2026-07-01T10:00")
    _persist(db, DIRECT, 2, 11, "regression", "301", "lsd_accel",
             [_res("k", "oversteer", "new", new=True)],
             failed=[{"field": "lsd_accel", "direction": "increase", "magnitude": "30",
                      "severity": "high"}], at="2026-07-05T10:00")
    res = db.build_engineering_context(
        car=CAR, track=TRACK, layout_id=LAYOUT, discipline="Race",
        proposed_change={"field": "lsd_accel", "direction": "increase", "value": "32"})
    assert res["ok"]
    assert res["matched_contexts"]
    assert any(t["kind"] == "failed_experiment" for t in res["transfers"])
    kinds = {r["kind"] for r in res["regression_risks"]}
    assert "known_failed_direction" in kinds
    assert "repeated_regression" in kinds


# --- restart determinism ----------------------------------------------------
def test_restart_determinism(db):
    _persist(db, DIRECT, 1, 10, "confirmed_improvement", "300", "toe_front",
             [_res("k", "understeer", "resolved", present=False)])
    a = db.build_engineering_context(car=CAR, track=TRACK, layout_id=LAYOUT,
                                     discipline="Race")
    b = db.build_engineering_context(car=CAR, track=TRACK, layout_id=LAYOUT,
                                     discipline="Race")
    assert a["fingerprints"] == b["fingerprints"]


# --- writes nothing ---------------------------------------------------------
def test_writes_nothing(db):
    _persist(db, DIRECT, 1, 10, "confirmed_improvement", "300", "toe_front",
             [_res("k", "understeer", "resolved", present=False)])
    before = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0]
    db.build_engineering_context(car=CAR, track=TRACK, discipline="Race",
                                 proposed_change={"field": "toe_front",
                                                  "direction": "increase", "value": "1"})
    after = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0]
    assert before == after


# --- car-class RELATED tier via the cars table ------------------------------
def test_related_match_via_car_class(db):
    db._conn.execute("INSERT INTO cars (id, name, category) VALUES (?,?,?)",
                     (8, "AMG GT3", "Gr.3"))
    db._conn.commit()
    amg_ctx = MemoryContextKey(driver="", car="AMG GT3", track=TRACK, layout_id=LAYOUT,
                               discipline="Race")
    # note: RELATED requires same driver; with empty driver it falls to UNKNOWN/None.
    # Use a driver to exercise the RELATED tier.
    q_driver = MemoryContextKey(driver="leon", car=CAR, track=TRACK, layout_id=LAYOUT,
                                discipline="Race")
    amg_driver = dataclasses = MemoryContextKey(driver="leon", car="AMG GT3", track=TRACK,
                                                layout_id=LAYOUT, discipline="Race")
    _persist(db, amg_driver, 1, 10, "confirmed_improvement", "300", "toe_front",
             [_res("k", "understeer", "resolved", present=False)])
    res = db.build_engineering_context(car=CAR, track=TRACK, layout_id=LAYOUT,
                                       discipline="Race", driver="leon")
    strengths = {m["strength"] for m in res["matched_contexts"]}
    assert "related_match" in strengths


# --- golden UAT through the production loop ---------------------------------
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


def _laps(db, sid, n, compound="RH"):
    for i in range(1, n + 1):
        db._conn.execute(
            "INSERT INTO lap_records (session_id, car_id, track, lap_num, lap_time_ms, "
            "is_pit_lap, is_out_lap, compound) VALUES (?,?,?,?,?,0,0,?)",
            (sid, CAR_ID, TRACK, i, 95000, compound))
    db._conn.commit()


def _occ(sid, cp, laps, seg, issue, phase, axle=""):
    return [{"session_id": sid, "setup_checkpoint_id": cp, "lap_number": n,
             "segment_id": seg, "corner_phase": phase, "issue_type": issue,
             "axle": axle, "confidence": 0.85} for n in laps]


def test_golden_uat_production_loop_feeds_context(db):
    # a real review resolves understeer at T3 by raising aero_front → captured (Phase 8)
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
    # Phase 9 now surfaces the successful aero_front lesson for the same context
    res = db.build_engineering_context(car=CAR, track=TRACK, layout_id=LAYOUT,
                                       discipline="Race", compound="RH")
    assert res["ok"]
    assert res["candidate_record_count"] >= 1
    assert any(t["kind"] == "successful_experiment" and "aero_front" in t["field"]
               for t in res["transfers"])
