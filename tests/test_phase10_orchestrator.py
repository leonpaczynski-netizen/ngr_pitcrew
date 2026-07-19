"""Engineering Brain Phase 10 — SessionDB pre-flight orchestrator + golden UAT."""
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

SELECTION = {
    "candidate_id": "c1", "target_issue": "exit_wheelspin", "field": "lsd_accel",
    "direction": "increase", "current_value": 22.0, "proposed_value": 25.0, "delta": 3.0,
    "expected_positive_effect": "increases exit traction",
    "expected_negative_effects": ["may reduce power-oversteer resistance"],
    "protected_behaviours_at_risk": [], "supporting_evidence": ["recurring exit wheelspin"],
    "window_relationship": "inside_window", "evidence_grade": "medium",
}


@pytest.fixture
def db():
    d = SessionDB(":memory:")
    d._conn.execute("INSERT INTO cars (id, name, category) VALUES (?,?,?)",
                    (CAR_ID, CAR, "Gr.3"))
    d._conn.commit()
    return d


def _res(k, t, s, present=False):
    return {"issue_key": k, "family": "traction", "issue_type": t, "axle": "rear",
            "phase": "exit", "segment_id": "T4", "corner_name": "T4",
            "residual_state": s, "is_new": False, "is_regression": False,
            "still_present": present, "protected_good": False, "confidence": "high"}


def _persist(db, oid, eid, status, sess, field, residuals, at):
    ctx = MemoryContextKey(car=CAR, track=TRACK, layout_id=LAYOUT, discipline="Race")
    outcome = {"id": oid, "experiment_id": eid, "status": status,
               "confidence_level": "high", "scope_fingerprint": "sf",
               "test_session_id": sess, "protected": [], "failed_directions": []}
    exp = {"id": eid, "scope_fingerprint": "sf",
           "changes": [{"field": field, "from_value": "20", "to_value": "25",
                        "delta_direction": "increase"}]}
    rec = build_development_record(outcome, exp, context=ctx, scope_fingerprint="sf",
                                  working_windows=[], residuals=residuals,
                                  recorded_at=at, session_date=at[:10])
    db._persist_development_record(rec, created_at=rec.recorded_at)


def test_no_migration(db):
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION == 24


def test_end_to_end_review(db):
    _persist(db, 1, 10, "confirmed_improvement", "300", "lsd_accel",
             [_res("k", "exit_wheelspin", "resolved")], "2026-07-01T10:00")
    _persist(db, 2, 11, "confirmed_improvement", "301", "lsd_accel",
             [_res("k", "exit_wheelspin", "resolved")], "2026-07-05T10:00")
    r = db.build_experiment_preflight(SELECTION, car=CAR, track=TRACK, layout_id=LAYOUT,
                                      discipline="Race")
    assert r["ok"]
    rv = r["review"]
    assert rv["experiment"]["field"] == "lsd_accel"
    assert rv["experiment"]["proposed_value"] == 25.0
    assert rv["risk_level"] in ("low", "moderate", "high", "unknown")
    assert rv["checklist"] and rv["consequences"]


def test_no_selection_returns_not_ok(db):
    assert db.build_experiment_preflight({})["ok"] is False
    assert db.build_experiment_preflight({"direction": "increase"})["ok"] is False


def test_restart_determinism(db):
    _persist(db, 1, 10, "confirmed_improvement", "300", "lsd_accel",
             [_res("k", "exit_wheelspin", "resolved")], "2026-07-01T10:00")
    a = db.build_experiment_preflight(SELECTION, car=CAR, track=TRACK, layout_id=LAYOUT,
                                      discipline="Race")
    b = db.build_experiment_preflight(SELECTION, car=CAR, track=TRACK, layout_id=LAYOUT,
                                      discipline="Race")
    assert a["review"]["content_fingerprint"] == b["review"]["content_fingerprint"]


def test_writes_nothing(db):
    _persist(db, 1, 10, "confirmed_improvement", "300", "lsd_accel",
             [_res("k", "exit_wheelspin", "resolved")], "2026-07-01T10:00")
    before = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0]
    db.build_experiment_preflight(SELECTION, car=CAR, track=TRACK, discipline="Race")
    after = db._conn.execute(
        "SELECT COUNT(*) FROM engineering_development_records").fetchone()[0]
    assert before == after


# --- golden UAT: a real prior review, then pre-flight a follow-up experiment ---
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


def test_golden_uat_preflight_after_real_review(db):
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
    # pre-flight a proposed follow-up aero_front change → surfaces the successful history
    sel = dict(SELECTION); sel["field"] = "aero_front"; sel["direction"] = "increase"
    r = db.build_experiment_preflight(sel, car=CAR, track=TRACK, layout_id=LAYOUT,
                                      discipline="Race", compound="RH")
    assert r["ok"]
    rv = r["review"]
    keys = {s["key"] for s in rv["sections"]}
    assert "historical_success" in keys
    assert any(c["kind"] == "primary_effect" for c in rv["consequences"])
