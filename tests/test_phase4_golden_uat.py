"""Engineering-Brain Phase 4 — golden runtime UAT through the PRODUCTION assembly
path (Porsche 911 RSR '17 @ Fuji Full Course). No test-only manual CornerObservation
objects — evidence is persisted and assembled by the canonical authorities.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from data.session_db import SessionDB
from data.applied_checkpoint import make_checkpoint
from strategy.setup_experiment import build_experiment_from_recommendation, ProtectedBehaviour
from strategy.setup_experiment_outcome import DriverReviewInput
from strategy.setup_decision_status import resolve_setup_decision, SetupDecisionState

CAR_ID = 7
CAR = "Porsche 911 RSR (991) '17"
TRACK = "Fuji International Speedway"
LAYOUT = "full_course"
ROOT = Path(__file__).resolve().parents[1]


def _register_car(db):
    db._conn.execute(
        "INSERT INTO cars (id, name) VALUES (?, ?)", (CAR_ID, CAR))
    db._conn.commit()


def _experiment(db):
    data = {"recommendation_status": "approved",
            "analysis": "Repeatable front lockup into T1; reduce front brake bias.",
            "changes": [{"field": "brake_bias", "from": "56", "to_clamped": "53",
                         "rule_id": "BRK_FRONT_LOCK", "symptom": "front_lock"}],
            "diagnosis": {"dominant_problem": "front_lock", "target_corners": ["T1"]},
            "deterministic_plan": {"rule_engine_version": "46.0"},
            "test_sequence": {"stages": [{"success_criterion": "T1 lockup reduced",
                                          "rollback": "Base RSR Race"}]},
            "rollback": {"label": "Base RSR Race"}}
    e = build_experiment_from_recommendation(
        data, car_id=CAR_ID, track=TRACK, layout_id=LAYOUT, discipline="Race",
        parent_setup_id="base_rsr")
    e = dataclasses.replace(
        e, protected_behaviours=(ProtectedBehaviour("mid-corner balance", corners=("T3",)),
                                 ProtectedBehaviour("rear traction", corners=("Final",))),
        test_protocol=dataclasses.replace(e.test_protocol, min_clean_laps=4,
                                          target_corners=("T1",),
                                          rollback_target="Base RSR Race")).with_idempotency_key()
    eid = db.create_setup_experiment(e)
    db.transition_experiment_state(eid, "ready_for_apply")
    cp = make_checkpoint(setup_id="exp_rsr", fields={"brake_bias": 53},
                         confirmed_at="2026-07-19 10:00")
    db.save_applied_checkpoint(CAR_ID, TRACK, LAYOUT, "Race", cp)
    db.link_experiment_applied_checkpoint(eid, cp.checkpoint_id, {"brake_bias": 53})
    return eid, cp.checkpoint_id


def _laps(db, sid, n, t):
    for i in range(1, n + 1):
        db._conn.execute(
            "INSERT INTO lap_records (session_id, car_id, track, lap_num, lap_time_ms, "
            "is_pit_lap, is_out_lap) VALUES (?,?,?,?,?,0,0)", (sid, CAR_ID, TRACK, i, t))
    db._conn.commit()


def _occ(sid, cp, lap, seg, issue, phase, axle=""):
    return {"session_id": sid, "setup_checkpoint_id": cp, "lap_number": lap,
            "segment_id": seg, "corner_phase": phase, "issue_type": issue,
            "axle": axle, "severity": 0.7, "confidence": 0.85}


# Baseline: recurring T1 front_lock (laps 2-5); protected corners clean.
def _baseline_occ():
    return [_occ(500, "", n, "T1", "front_lock", "braking", "front") for n in (2, 3, 4, 5)]


@pytest.fixture
def db():
    d = SessionDB(":memory:")
    _register_car(d)
    return d


def test_golden_improvement_case(db):
    eid, cp = _experiment(db)
    _laps(db, 500, 5, 95300)
    _laps(db, 600, 5, 95250)
    db.save_issue_occurrences(CAR_ID, TRACK, LAYOUT, _baseline_occ())
    # Test: T1 lockup now isolated (1/5); protected corners clean.
    db.save_issue_occurrences(CAR_ID, TRACK, LAYOUT,
                              [_occ(600, cp, 2, "T1", "front_lock", "braking", "front")])
    res = db.review_experiment_outcome(
        eid, test_session_id=600, baseline_session_id=500,
        driver_review=DriverReviewInput("f", True, target_symptom_resolved=True,
                                        braking_confidence_improved=True, vs_previous="better"))
    assert res["status"] == "confirmed_improvement", res
    assert db.get_setup_experiment(eid)["status"] == "completed"
    assert not res["failed_directions"]
    # canonical setup-decision status
    dec = resolve_setup_decision(experiment_status="completed",
                                 outcome_status="confirmed_improvement")
    assert dec.state == SetupDecisionState.CONFIRMED
    # assembled from the production path
    assert res["assembly"]["corner_baseline_count"] >= 1


def test_golden_regression_case(db):
    eid, cp = _experiment(db)
    _laps(db, 700, 5, 95300)
    _laps(db, 800, 5, 95250)
    db.save_issue_occurrences(CAR_ID, TRACK, LAYOUT, _baseline_occ())
    # Test: T1 improves (2/5) but rear-exit wheelspin recurring at Final (laps 2-5).
    test_occ = [_occ(800, cp, 2, "T1", "front_lock", "braking", "front"),
                _occ(800, cp, 3, "T1", "front_lock", "braking", "front")]
    test_occ += [_occ(800, cp, n, "Final", "rear_wheelspin", "exit", "rear")
                 for n in (2, 3, 4, 5)]
    db.save_issue_occurrences(CAR_ID, TRACK, LAYOUT, test_occ)
    res = db.review_experiment_outcome(
        eid, test_session_id=800, baseline_session_id=700,
        driver_review=DriverReviewInput("f", True, new_symptoms=("rear steps out",),
                                        vs_previous="worse"))
    assert res["status"] == "regression", res
    assert db.get_setup_experiment(eid)["status"] == "rejected"
    fds = db.list_failed_directions_for_field(CAR, TRACK, LAYOUT, "brake_bias")
    assert fds and fds[0]["strength"] == "lockout"
    assert res["rollback_target"] == "Base RSR Race"
    # no automatic rollback: the applied checkpoint is unchanged
    assert db.get_setup_experiment(eid)["applied_checkpoint_id"] == cp
    dec = resolve_setup_decision(experiment_status="rejected", outcome_status="regression")
    assert dec.state == SetupDecisionState.REJECTED


def test_golden_insufficient_case(db):
    eid, cp = _experiment(db)
    _laps(db, 900, 2, 95250)     # only 2 valid laps < min 4
    db.save_issue_occurrences(CAR_ID, TRACK, LAYOUT, _baseline_occ())
    # High raw event count concentrated on ONE lap — the authority excludes it.
    db.save_issue_occurrences(CAR_ID, TRACK, LAYOUT,
                              [_occ(900, cp, 1, "T1", "front_lock", "braking", "front")
                               for _ in range(12)])
    res = db.review_experiment_outcome(eid, test_session_id=900, complete_on_success=False)
    assert res["status"] == "insufficient_evidence", res
    assert not res["failed_directions"]
    # experiment stays reviewable (not falsely completed/rejected)
    assert db.get_setup_experiment(eid)["status"] == "ready_for_review"
    assert res["assembly"]["missing_evidence"]        # UI can explain what's missing


# --- frozen safety contracts (84-96) ---
def test_golden_config_id_unchanged():
    from tests.test_race_config_id_hash import GOLDEN_VECTORS, _bind
    for strategy, expected in GOLDEN_VECTORS:
        assert _bind(strategy)._compute_race_config_id() == expected


def test_frozen_fanout_allowlist_unchanged():
    from tests.test_legacy_fanout_phase_5 import _scan_inventory, FROZEN_ALLOWLIST
    assert _scan_inventory() == FROZEN_ALLOWLIST


def test_apply_gate_predicate_unchanged():
    src = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
    assert "_status_approved: bool = (not _is_legacy) and (_rec_status in _APPROVED_STATUSES)" in src


def test_rule_engine_version_unchanged():
    from strategy._setup_constants import RULE_ENGINE_VERSION
    assert RULE_ENGINE_VERSION == "46.0"


def test_no_auto_apply_or_rollback_in_phase4():
    for mod in ("engineering_lap_validity", "corner_evidence", "setup_evidence_assembly",
                "setup_decision_status"):
        src = (ROOT / "strategy" / f"{mod}.py").read_text(encoding="utf-8")
        assert "mark_applied" not in src
        assert "apply_revert" not in src
        assert "save_applied_checkpoint" not in src
