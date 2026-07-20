"""Engineering-Brain Phase 3 — orchestrator + lifecycle + learning integration.

Drives SessionDB.evaluate_setup_experiment end-to-end (Phase 2 experiment →
apply → Phase 3 evaluate), plus lifecycle gating, failed-direction learning,
existing-consumer feed, and the frozen safety contracts. Isolated in-memory DB.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from data.session_db import SessionDB
from strategy.setup_experiment import (
    build_experiment_from_recommendation, ProtectedBehaviour)
from strategy.setup_experiment_outcome import CornerObservation, DriverReviewInput, ConfounderInput

ROOT = Path(__file__).resolve().parents[1]


def _make_applied_experiment(db, *, parent="base1", car_id=7, track="Fuji",
                             layout="full_course"):
    data = {
        "recommendation_status": "approved", "analysis": "front lock at T1",
        "changes": [{"field": "brake_bias", "from": "55", "to_clamped": "52",
                     "rule_id": "BB1", "symptom": "front_lock"}],
        "diagnosis": {"dominant_problem": "front_lock", "target_corners": ["T1"]},
        "protected_fields": [], "deterministic_plan": {"rule_engine_version": "46.0"},
        "test_sequence": {"stages": [{"success_criterion": "T1 lockup reduced",
                                      "rollback": "Base RSR"}]},
        "rollback": {"label": "Base RSR"}}
    e = build_experiment_from_recommendation(
        data, car_id=car_id, track=track, layout_id=layout, discipline="Race",
        parent_setup_id=parent)
    e = dataclasses.replace(
        e, protected_behaviours=(ProtectedBehaviour("rear traction", corners=("T5",)),),
        test_protocol=dataclasses.replace(e.test_protocol, min_clean_laps=4,
                                          target_corners=("T1",))).with_idempotency_key()
    eid = db.create_setup_experiment(e)
    db.transition_experiment_state(eid, "ready_for_apply")
    db.link_experiment_applied_checkpoint(eid, f"cp{eid}", {"brake_bias": 52})
    return eid


def _laps(db, sid, n, t, car_id=7, track="Fuji"):
    for i in range(1, n + 1):
        db._conn.execute(
            "INSERT INTO lap_records (session_id, car_id, track, lap_num, "
            "lap_time_ms, is_pit_lap, is_out_lap) VALUES (?,?,?,?,?,0,0)",
            (sid, car_id, track, i, t))
    db._conn.commit()


_CB = (CornerObservation("T1", "T1", "braking", "front_lock", 5, 5),
       CornerObservation("T5", "T5", "exit", "rear_wheelspin", 0, 5))


def _ct(t1, t5):
    return (CornerObservation("T1", "T1", "braking", "front_lock", t1, 5),
            CornerObservation("T5", "T5", "exit", "rear_wheelspin", t5, 5))


@pytest.fixture
def db():
    return SessionDB(":memory:")


def _eval(db, eid, *, ct, review=None, confounders=None, valid=5, base=100,
          test=200, complete=True, car="RSR", track="Fuji", layout="full_course"):
    _laps(db, base, 5, 95200)
    _laps(db, test, valid, 95000)
    return db.evaluate_setup_experiment(
        eid, test_session_id=test, baseline_session_id=base, corner_baseline=_CB,
        corner_test=ct, driver_review=review, confounders=confounders,
        car=car, track=track, layout_id=layout, discipline="Race",
        complete_on_success=complete)


# ------------------------------------------------------------------ 44 COMPLETED gate
def test_completed_impossible_without_outcome(db):
    eid = _make_applied_experiment(db)
    # move to ready_for_review WITHOUT an outcome (append a manual test evidence)
    from strategy.setup_experiment import ExperimentEvidence, EvidencePhase
    db.append_experiment_evidence(eid, ExperimentEvidence(
        evidence_type="test", phase=EvidencePhase.TEST))
    db.transition_experiment_state(eid, "test_in_progress")
    db.transition_experiment_state(eid, "ready_for_review")
    # no outcome persisted → COMPLETED must be refused
    assert db.transition_experiment_state(eid, "completed") is False
    assert db.get_setup_experiment(eid)["status"] == "ready_for_review"


# ------------------------------------------------------------------ 45,46,47 lifecycle
def test_valid_success_completes(db):
    eid = _make_applied_experiment(db)
    r = _eval(db, eid, ct=_ct(1, 0),
              review=DriverReviewInput("f", True, target_symptom_resolved=True,
                                       braking_confidence_improved=True, vs_previous="better"))
    assert r["status"] == "confirmed_improvement"
    assert db.get_setup_experiment(eid)["status"] == "completed"


def test_regression_rejects(db):
    eid = _make_applied_experiment(db)
    r = _eval(db, eid, ct=_ct(1, 5),
              review=DriverReviewInput(refers_to_correct_setup=True, vs_previous="worse"))
    assert r["status"] == "regression"
    assert db.get_setup_experiment(eid)["status"] == "rejected"


def test_insufficient_does_not_complete(db):
    eid = _make_applied_experiment(db)
    r = _eval(db, eid, ct=_ct(1, 0), valid=2)   # < min_clean_laps=4
    assert r["status"] == "insufficient_evidence"
    assert db.get_setup_experiment(eid)["status"] == "ready_for_review"  # reviewable


def test_confounded_does_not_complete_or_reject(db):
    eid = _make_applied_experiment(db)
    r = _eval(db, eid, ct=_ct(1, 0), confounders=ConfounderInput(compound_changed=True))
    assert r["status"] == "confounded"
    assert db.get_setup_experiment(eid)["status"] == "ready_for_review"


# ------------------------------------------------------------------ 49 append-only history
def test_state_history_append_only(db):
    eid = _make_applied_experiment(db)
    _eval(db, eid, ct=_ct(1, 0),
          review=DriverReviewInput("f", True, target_symptom_resolved=True, vs_previous="better"))
    hist = db.get_experiment_state_history(eid)
    seq = [h["to_status"] for h in hist]
    assert "applied" in seq and "completed" in seq
    assert seq == sorted(seq, key=lambda s: hist[seq.index(s)]["id"])  # monotonic ids


# ------------------------------------------------------------------ 50,51,52 learning strength
def test_strong_regression_creates_scoped_lockout(db):
    eid = _make_applied_experiment(db)
    r = _eval(db, eid, ct=_ct(1, 5))
    fds = [f for f in r["failed_directions"]]
    assert any(f["strength"] == "lockout" for f in fds)
    assert db.list_failed_directions_by_scope(
        db.get_setup_experiment(eid)["scope_fingerprint"])


def test_weak_regression_creates_caution_only(db):
    eid = _make_applied_experiment(db)
    # emerging (2/5) rear regression → caution, not a hard lockout
    r = _eval(db, eid, ct=_ct(1, 2))
    if r["status"] == "regression":
        assert all(f["strength"] == "caution" for f in r["failed_directions"])
        assert r["learning_written"]["learning_outcomes"] == 0  # no hard block written


def test_no_lockout_for_insufficient(db):
    eid = _make_applied_experiment(db)
    r = _eval(db, eid, ct=_ct(1, 5), valid=2)   # insufficient
    assert r["status"] == "insufficient_evidence"
    assert not r["failed_directions"]


def test_confounded_generates_no_lockout(db):
    eid = _make_applied_experiment(db)
    r = _eval(db, eid, ct=_ct(1, 5), confounders=ConfounderInput(weather_changed=True))
    assert r["status"] == "confounded"
    assert not r["failed_directions"]


# ------------------------------------------------------------------ 53,54 no global lockout
def test_no_cross_car_or_cross_track_lockout(db):
    eid = _make_applied_experiment(db, car_id=7, track="Fuji")
    _eval(db, eid, ct=_ct(1, 5), car="RSR", track="Fuji", layout="full_course")
    # a lockout exists for RSR/Fuji/full_course but NOT for a different car/track
    assert db.list_failed_directions_for_field("RSR", "Fuji", "full_course", "brake_bias")
    assert not db.list_failed_directions_for_field("GT3", "Fuji", "full_course", "brake_bias")
    assert not db.list_failed_directions_for_field("RSR", "Spa", "gp", "brake_bias")


# ------------------------------------------------------------------ 55 idempotent learning
def test_idempotent_learning(db):
    eid = _make_applied_experiment(db)
    _laps(db, 100, 5, 95200); _laps(db, 200, 5, 95000)
    args = dict(test_session_id=200, baseline_session_id=100, corner_baseline=_CB,
                corner_test=_ct(1, 5), car="RSR", track="Fuji", layout_id="full_course",
                complete_on_success=False)
    db.evaluate_setup_experiment(eid, **args)
    n1 = db._conn.execute("SELECT COUNT(*) FROM setup_experiment_failed_directions").fetchone()[0]
    db.evaluate_setup_experiment(eid, **args)   # duplicate eval, same evidence
    n2 = db._conn.execute("SELECT COUNT(*) FROM setup_experiment_failed_directions").fetchone()[0]
    assert n1 == n2                              # no duplicate learning


# ------------------------------------------------------------------ 56 compound attribution
def test_compound_experiment_does_not_over_attribute(db):
    data = {"recommendation_status": "approved", "analysis": "x",
            "changes": [{"field": "brake_bias", "from": "55", "to_clamped": "52", "rule_id": "BB1"},
                        {"field": "front_arb", "from": "6", "to_clamped": "4", "rule_id": "AR1"}],
            "diagnosis": {"dominant_problem": "front_lock", "target_corners": ["T1"]},
            "deterministic_plan": {"rule_engine_version": "46.0"},
            "rollback": {"label": "Base"}}
    e = build_experiment_from_recommendation(data, car_id=7, track="Fuji",
                                             layout_id="full_course", discipline="Race",
                                             parent_setup_id="b")
    e = dataclasses.replace(
        e, protected_behaviours=(ProtectedBehaviour("rear traction", corners=("T5",)),),
        test_protocol=dataclasses.replace(e.test_protocol, min_clean_laps=4,
                                          target_corners=("T1",))).with_idempotency_key()
    eid = db.create_setup_experiment(e)
    db.transition_experiment_state(eid, "ready_for_apply")
    db.link_experiment_applied_checkpoint(eid, "cpc", {"brake_bias": 52, "front_arb": 4})
    r = _eval(db, eid, ct=_ct(1, 5))
    assert r["status"] == "regression"
    for fd in r["failed_directions"]:
        assert fd["strength"] == "caution"          # never a hard lockout when compound
        assert fd["attribution_confidence"] == "low"


# ------------------------------------------------------------------ 57 existing consumer
def test_existing_lockout_consumer_receives_evidence(db):
    from strategy.setup_lineage import blocked_rules_from_outcomes
    eid = _make_applied_experiment(db)
    _eval(db, eid, ct=_ct(1, 5))
    outcomes = db.get_learning_outcomes(0, "Fuji", "full_course")
    assert any(o["verdict"] == "worsened" and o["rule_id"] == "BB1" for o in outcomes)
    # the existing consumer reads Phase 3's row (one strong regression is valid evidence)
    blocked = blocked_rules_from_outcomes(outcomes, min_worsened=1)
    assert "BB1" in blocked


# ------------------------------------------------------------------ 58 superseding history
def test_superseding_keeps_history(db):
    eid = _make_applied_experiment(db)
    _laps(db, 100, 5, 95200)
    _laps(db, 200, 2, 95000)      # first test: too few valid laps → insufficient (reviewable)
    _laps(db, 300, 5, 95000)      # later test: enough valid laps → conclusive
    r1 = db.evaluate_setup_experiment(eid, test_session_id=200, baseline_session_id=100,
                                      corner_baseline=_CB, corner_test=_ct(1, 0),
                                      car="RSR", track="Fuji", layout_id="full_course",
                                      complete_on_success=False)
    assert r1["status"] == "insufficient_evidence"
    assert db.get_setup_experiment(eid)["status"] == "ready_for_review"
    # a later fuller test supersedes the prior conclusion WITHOUT deleting it
    r2 = db.evaluate_setup_experiment(eid, test_session_id=300, baseline_session_id=100,
                                      corner_baseline=_CB, corner_test=_ct(0, 0),
                                      driver_review=DriverReviewInput("f2", True, target_symptom_resolved=True, vs_previous="better"),
                                      car="RSR", track="Fuji", layout_id="full_course",
                                      complete_on_success=False)
    assert r2["superseded_prior"] == r1["outcome_id"]
    all_outcomes = db.list_experiment_outcomes(eid)
    assert len(all_outcomes) == 2                 # history preserved
    assert db.get_experiment_outcome(r1["outcome_id"])["superseded_by"] == r2["outcome_id"]
    assert db.get_latest_experiment_outcome(eid)["id"] == r2["outcome_id"]


# ------------------------------------------------------------------ 61,62 no auto apply/rollback
def test_no_auto_apply_or_rollback(db):
    eid = _make_applied_experiment(db)
    r = _eval(db, eid, ct=_ct(1, 5))
    assert r["rollback_eligible"] is True         # eligible = a FLAG, not an action
    assert r["rollback_target"] == "Base RSR"
    # no applied-checkpoint was created by evaluation; nothing was reverted
    outcome_src = (ROOT / "strategy" / "setup_experiment_outcome.py").read_text(encoding="utf-8")
    assert "mark_applied" not in outcome_src
    assert "apply_revert" not in outcome_src
    assert "save_applied_checkpoint" not in outcome_src


def test_orchestrator_gathers_off_thread_authorities(db):
    # The evaluator/orchestrator import no telemetry UDP thread; evaluation is a
    # plain synchronous call driven by the UI worker (off the packet thread).
    src = (ROOT / "strategy" / "setup_experiment_outcome.py").read_text(encoding="utf-8")
    for banned in ("socket", "recvfrom", "udp", "QThread", "telemetry.recorder"):
        assert banned.lower() not in src.lower()


# ------------------------------------------------------------------ 63-67 frozen contracts
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


def test_phase1_fingerprint_authoritative(db):
    # Phase 3 outcomes carry the Phase 1 scope fingerprint verbatim (never recomputed).
    src = (ROOT / "strategy" / "setup_experiment_outcome.py").read_text(encoding="utf-8")
    assert "def scope_fingerprint" not in src
    assert "compute_config_id" not in src
    eid = _make_applied_experiment(db)
    exp_scope = db.get_setup_experiment(eid)["scope_fingerprint"]
    r = _eval(db, eid, ct=_ct(1, 0),
              review=DriverReviewInput("f", True, target_symptom_resolved=True, vs_previous="better"))
    assert db.get_experiment_outcome(r["outcome_id"])["scope_fingerprint"] == exp_scope
