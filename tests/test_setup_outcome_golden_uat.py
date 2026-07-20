"""Engineering-Brain Phase 3 — golden UAT (Porsche 911 RSR '17 @ Fuji Full Course).

Two deterministic, offline end-to-end scenarios through the full closed loop
(Phase 2 experiment → apply → Phase 3 evaluate → outcome → lifecycle → learning).
Isolated in-memory SessionDB; no runtime files.
"""
from __future__ import annotations

import dataclasses

import pytest

from data.session_db import SessionDB
from strategy.setup_experiment import (
    build_experiment_from_recommendation, ProtectedBehaviour)
from strategy.setup_experiment_outcome import CornerObservation, DriverReviewInput

CAR = "Porsche 911 RSR (991) '17"
TRACK = "Fuji International Speedway"
LAYOUT = "full_course"


def _build_experiment(db):
    data = {
        "recommendation_status": "approved",
        "analysis": "Repeatable front lockup into T1 under braking; reduce front "
                    "brake bias to settle the front axle without hurting rotation.",
        "changes": [{"field": "brake_bias", "from": "56", "to_clamped": "53",
                     "rule_id": "BRK_FRONT_LOCK", "symptom": "front_lock"}],
        "diagnosis": {"dominant_problem": "front_lock", "target_corners": ["T1"]},
        "protected_fields": [],
        "deterministic_plan": {"rule_engine_version": "46.0", "driver_profile_version": "v1"},
        "test_sequence": {"stages": [{"success_criterion": "T1 lockup reduced repeatably",
                                      "rollback": "Base RSR Race"}]},
        "rollback": {"label": "Base RSR Race"}}
    e = build_experiment_from_recommendation(
        data, car_id=7, track=TRACK, layout_id=LAYOUT, discipline="Race",
        parent_setup_id="base_rsr_race")
    e = dataclasses.replace(
        e,
        protected_behaviours=(ProtectedBehaviour("mid-corner balance", corners=("T3",),
                                                 baseline_confidence="confirmed"),
                              ProtectedBehaviour("rear traction", corners=("Final",),
                                                 baseline_confidence="confirmed")),
        test_protocol=dataclasses.replace(e.test_protocol, min_clean_laps=4,
                                          target_corners=("T1",),
                                          rollback_target="Base RSR Race"),
    ).with_idempotency_key()
    eid = db.create_setup_experiment(e)
    db.transition_experiment_state(eid, "ready_for_apply")
    db.link_experiment_applied_checkpoint(eid, "cp_rsr_1", {"brake_bias": 53})
    return eid


def _laps(db, sid, n, t):
    for i in range(1, n + 1):
        db._conn.execute(
            "INSERT INTO lap_records (session_id, car_id, track, lap_num, "
            "lap_time_ms, is_pit_lap, is_out_lap) VALUES (?,?,?,?,?,0,0)",
            (sid, 7, TRACK, i, t))
    db._conn.commit()


# Baseline: T1 front_lock recurring 5/5; T3 + Final clean.
_BASELINE = (CornerObservation("T1", "T1", "braking", "front_lock", 5, 5, 5),
             CornerObservation("T3", "T3", "apex", "mid_corner_understeer", 0, 5),
             CornerObservation("Final", "Final", "exit", "rear_wheelspin", 0, 5))


@pytest.fixture
def db():
    return SessionDB(":memory:")


def test_golden_scenario_1_confirmed_improvement(db):
    eid = _build_experiment(db)

    # (3) applied checkpoint matches the recommended values (MATCH)
    exp = db.get_setup_experiment(eid)
    assert exp["applied_checkpoint_id"] == "cp_rsr_1"
    assert exp["applied_match_state"] == "match"
    # (1) parent baseline has a repeatable T1 front lockup
    assert _BASELINE[0].affected_laps == 5

    # (4) enough valid laps on both sides
    _laps(db, 500, 5, 95300)      # baseline session
    _laps(db, 600, 5, 95250)      # test session (no material lap-time regression)

    # (5) T1 lockup drops materially + repeatably; (6)(7) protected corners stay clean
    test_corners = (CornerObservation("T1", "T1", "braking", "front_lock", 1, 5, 1),
                    CornerObservation("T3", "T3", "apex", "mid_corner_understeer", 0, 5),
                    CornerObservation("Final", "Final", "exit", "rear_wheelspin", 0, 5))
    # (9) driver confirms improved braking confidence
    review = DriverReviewInput("fb1", refers_to_correct_setup=True,
                               target_symptom_resolved=True,
                               braking_confidence_improved=True, vs_previous="better")

    res = db.evaluate_setup_experiment(
        eid, test_session_id=600, baseline_session_id=500,
        corner_baseline=_BASELINE, corner_test=test_corners, driver_review=review,
        test_checkpoint_id="cp_rsr_1", car=CAR, track=TRACK, layout_id=LAYOUT,
        discipline="Race", driver="Leon")

    # (10) CONFIRMED_IMPROVEMENT
    assert res["status"] == "confirmed_improvement", res
    # (8) whole-lap not materially slower
    outcome = db.get_experiment_outcome(res["outcome_id"])
    import json
    wl = json.loads(outcome["whole_lap_json"])
    assert not wl["materially_slower"]
    # (6)(7) protected behaviours preserved
    prot = {p["behaviour"]: p["verdict"] for p in outcome["protected"]}
    assert prot["mid-corner balance"] == "preserved"
    assert prot["rear traction"] == "preserved"
    # (11) experiment COMPLETED
    assert db.get_setup_experiment(eid)["status"] == "completed"
    # (12) no failed-direction lockout
    assert not res["failed_directions"]
    assert not db.list_failed_directions_by_scope(exp["scope_fingerprint"])
    assert res["learning_written"]["learning_outcomes"] == 0


def test_golden_scenario_2_protected_regression_rejects(db):
    eid = _build_experiment(db)
    exp = db.get_setup_experiment(eid)

    _laps(db, 700, 5, 95300)
    _laps(db, 800, 5, 95250)

    # (1) target improves slightly (5→2), (2) rear-exit wheelspin becomes recurring (4/5)
    test_corners = (CornerObservation("T1", "T1", "braking", "front_lock", 2, 5, 2),
                    CornerObservation("T3", "T3", "apex", "mid_corner_understeer", 0, 5),
                    CornerObservation("Final", "Final", "exit", "rear_wheelspin", 4, 5, 4))
    review = DriverReviewInput("fb2", refers_to_correct_setup=True,
                               new_symptoms=("rear steps out on exit",), vs_previous="worse")

    res = db.evaluate_setup_experiment(
        eid, test_session_id=800, baseline_session_id=700,
        corner_baseline=_BASELINE, corner_test=test_corners, driver_review=review,
        test_checkpoint_id="cp_rsr_1", car=CAR, track=TRACK, layout_id=LAYOUT,
        discipline="Race", driver="Leon")

    # (4) REGRESSION
    assert res["status"] == "regression", res
    # (3) rear traction protected → material regression
    outcome = db.get_experiment_outcome(res["outcome_id"])
    prot = {p["behaviour"]: p["verdict"] for p in outcome["protected"]}
    assert prot["rear traction"] == "material_regression"
    # (5) experiment REJECTED
    assert db.get_setup_experiment(eid)["status"] == "rejected"
    # (6) a scoped failed-direction learning record created (this car/track/layout only)
    fds = db.list_failed_directions_for_field(CAR, TRACK, LAYOUT, "brake_bias")
    assert fds and fds[0]["strength"] == "lockout"
    assert not db.list_failed_directions_for_field("Some Other Car", TRACK, LAYOUT, "brake_bias")
    # (7) parent remains the rollback target
    assert res["rollback_target"] == "Base RSR Race"
    assert outcome["rollback_target"] == "Base RSR Race"
    # (8) no automatic rollback — the applied checkpoint is unchanged, no revert occurred
    assert res["rollback_eligible"] is True    # a flag, not an action
    assert db.get_setup_experiment(eid)["applied_checkpoint_id"] == "cp_rsr_1"


def test_golden_scenarios_are_deterministic(db):
    # Re-running scenario 1's evaluation reproduces the same outcome id (idempotent).
    eid = _build_experiment(db)
    _laps(db, 500, 5, 95300)
    _laps(db, 600, 5, 95250)
    tc = (CornerObservation("T1", "T1", "braking", "front_lock", 1, 5, 1),
          CornerObservation("T3", "T3", "apex", "mid_corner_understeer", 0, 5),
          CornerObservation("Final", "Final", "exit", "rear_wheelspin", 0, 5))
    kw = dict(test_session_id=600, baseline_session_id=500, corner_baseline=_BASELINE,
              corner_test=tc, test_checkpoint_id="cp_rsr_1", car=CAR, track=TRACK,
              layout_id=LAYOUT, discipline="Race", complete_on_success=False,
              driver_review=DriverReviewInput("fb1", True, target_symptom_resolved=True,
                                              braking_confidence_improved=True, vs_previous="better"))
    a = db.evaluate_setup_experiment(eid, **kw)
    b = db.evaluate_setup_experiment(eid, **kw)
    assert a["outcome_id"] == b["outcome_id"]
    assert a["status"] == b["status"] == "confirmed_improvement"
