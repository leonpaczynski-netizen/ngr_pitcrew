"""Engineering Brain Phase 8 — golden UAT through the PRODUCTION loop.

Porsche 911 RSR '17 @ Fuji Full Course. Each completed review runs the real
review_and_learn path (Phase 3 → 4 → 5 → 6) which now also captures an immutable
Phase-8 development record. The scenarios then fold cross-session memory over several
sessions and assert the permanent-memory conclusions.
"""
from __future__ import annotations

import dataclasses

import pytest

from data.session_db import SessionDB
from data.applied_checkpoint import make_checkpoint
from strategy.setup_experiment import build_experiment_from_recommendation, ProtectedBehaviour
from strategy.setup_experiment_outcome import DriverReviewInput

CAR_ID, CAR = 7, "Porsche 911 RSR (991) '17"
TRACK, LAYOUT = "Fuji International Speedway", "full_course"


@pytest.fixture
def db():
    d = SessionDB(":memory:")
    d._conn.execute("INSERT INTO cars (id, name) VALUES (?, ?)", (CAR_ID, CAR))
    d._conn.commit()
    return d


def _experiment(db, *, field, frm, to, symptom, target, extra_fields=None,
                parent="base_rsr"):
    data = {"recommendation_status": "approved", "analysis": symptom,
            "changes": [{"field": field, "from": frm, "to_clamped": to,
                         "rule_id": "R", "symptom": symptom}],
            "diagnosis": {"dominant_problem": symptom, "target_corners": [target]},
            "deterministic_plan": {"rule_engine_version": "46.0"},
            "test_sequence": {"stages": [{"success_criterion": "x", "rollback": "Base RSR"}]},
            "rollback": {"label": "Base RSR Race"}}
    e = build_experiment_from_recommendation(
        data, car_id=CAR_ID, track=TRACK, layout_id=LAYOUT, discipline="Race",
        parent_setup_id=parent)
    e = dataclasses.replace(
        e, protected_behaviours=(ProtectedBehaviour("rear traction", corners=("T5",)),),
        test_protocol=dataclasses.replace(e.test_protocol, min_clean_laps=4,
                                          target_corners=(target,),
                                          rollback_target="Base RSR Race")).with_idempotency_key()
    eid = db.create_setup_experiment(e)
    db.transition_experiment_state(eid, "ready_for_apply")
    fields = {field: float(to)}
    fields.update(extra_fields or {})
    cp = make_checkpoint(setup_id=f"exp{eid}", fields=fields, confirmed_at="t")
    db.save_applied_checkpoint(CAR_ID, TRACK, LAYOUT, "Race", cp)
    db.link_experiment_applied_checkpoint(eid, cp.checkpoint_id, {field: float(to)})
    return eid, cp.checkpoint_id, e.scope_fingerprint


def _laps(db, sid, n, t=95000, compound="RH"):
    for i in range(1, n + 1):
        db._conn.execute(
            "INSERT INTO lap_records (session_id, car_id, track, lap_num, lap_time_ms, "
            "is_pit_lap, is_out_lap, compound) VALUES (?,?,?,?,?,0,0,?)",
            (sid, CAR_ID, TRACK, i, t, compound))
    db._conn.commit()


def _occ(sid, cp, laps, seg, issue, phase, axle=""):
    return [{"session_id": sid, "setup_checkpoint_id": cp, "lap_number": n,
             "segment_id": seg, "corner_phase": phase, "issue_type": issue,
             "axle": axle, "confidence": 0.85} for n in laps]


_CUR = {"aero_front": 340, "aero_rear": 400, "arb_front": 5, "arb_rear": 4}


def _resolve_understeer_review(db, *, base_sid, test_sid, at):
    """Drive one full review where mid-corner understeer at T3 is resolved."""
    eid, cp, scope = _experiment(db, field="aero_front", frm="300", to="340",
                                 symptom="mid_corner_understeer", target="T3",
                                 extra_fields=_CUR)
    _laps(db, base_sid, 5); _laps(db, test_sid, 5)
    db.save_issue_occurrences(CAR_ID, TRACK, LAYOUT,
        _occ(base_sid, "", [2, 3, 4, 5], "T3", "understeer", "apex"))
    db.save_issue_occurrences(CAR_ID, TRACK, LAYOUT,
        _occ(test_sid, cp, [2], "T3", "understeer", "apex"))
    return db.review_and_learn(
        eid, test_session_id=test_sid, baseline_session_id=base_sid,
        driver_review=DriverReviewInput("f", True, target_symptom_resolved=True,
                                        vs_previous="better"))


# --- Scenario 1: a completed review is captured as an immutable record ------
def test_review_and_learn_captures_development_record(db):
    r = _resolve_understeer_review(db, base_sid=500, test_sid=600, at="2026-07-01")
    rec = r.get("development_record")
    assert rec and rec["ok"] and rec["recorded"] is True
    # the record is retrievable from the permanent store
    records = db.get_development_records(
        car=CAR, track=TRACK, layout_id=LAYOUT, discipline="Race", compound="RH")
    assert len(records) == 1
    assert records[0]["outcome_status"] in ("confirmed_improvement", "partial_improvement")


# --- Scenario 2: capture is idempotent (re-review same experiment) ----------
def test_capture_is_idempotent(db):
    _resolve_understeer_review(db, base_sid=500, test_sid=600, at="2026-07-01")
    # a second review of the SAME experiment produces the same record_key → no dup
    records = db.get_development_records(
        car=CAR, track=TRACK, layout_id=LAYOUT, discipline="Race", compound="RH")
    n_before = len(records)
    # re-run review_and_learn on the same experiment id
    eid = int(records[0]["experiment_id"])
    db.review_and_learn(eid, test_session_id=600, baseline_session_id=500,
                        driver_review=DriverReviewInput("f", True,
                                                        target_symptom_resolved=True,
                                                        vs_previous="better"))
    records2 = db.get_development_records(
        car=CAR, track=TRACK, layout_id=LAYOUT, discipline="Race", compound="RH")
    assert len(records2) == n_before   # no duplicate immutable record


# --- Scenario 3: cross-session memory over multiple reviews -----------------
def test_cross_session_memory_builds(db):
    _resolve_understeer_review(db, base_sid=500, test_sid=600, at="2026-07-01")
    # a second, different experiment on a later session
    eid2, cp2, _ = _experiment(db, field="arb_rear", frm="4", to="3",
                               symptom="corner_exit_oversteer", target="T4",
                               extra_fields=_CUR, parent="base_rsr")
    _laps(db, 700, 5); _laps(db, 800, 5)
    db.save_issue_occurrences(CAR_ID, TRACK, LAYOUT,
        _occ(700, "", [2, 3, 4, 5], "T4", "oversteer", "exit", "rear"))
    db.save_issue_occurrences(CAR_ID, TRACK, LAYOUT,
        _occ(800, cp2, [2], "T4", "oversteer", "exit", "rear"))
    db.review_and_learn(eid2, test_session_id=800, baseline_session_id=700,
                        driver_review=DriverReviewInput("f", True,
                                                        target_symptom_resolved=True,
                                                        vs_previous="better"))
    res = db.build_cross_session_memory(
        car=CAR, track=TRACK, layout_id=LAYOUT, discipline="Race", compound="RH")
    assert res["ok"]
    assert res["record_count"] == 2
    assert res["memory"]["review_count"] == 2
    assert res["timeline"]
    # scorecard + metrics computed deterministically
    assert res["scorecard"]["band"] in (
        "strong", "progressing", "stalled", "regressing", "insufficient")


# --- Scenario 4: restart determinism through the production path ------------
def test_restart_determinism_production(db):
    _resolve_understeer_review(db, base_sid=500, test_sid=600, at="2026-07-01")
    a = db.build_cross_session_memory(
        car=CAR, track=TRACK, layout_id=LAYOUT, discipline="Race", compound="RH")
    b = db.build_cross_session_memory(
        car=CAR, track=TRACK, layout_id=LAYOUT, discipline="Race", compound="RH")
    assert a["memory"]["content_fingerprint"] == b["memory"]["content_fingerprint"]
    assert a["history"]["content_fingerprint"] == b["history"]["content_fingerprint"]


# --- Scenario 5: the capture never writes prior evidence --------------------
def test_capture_writes_only_its_own_log(db):
    _resolve_understeer_review(db, base_sid=500, test_sid=600, at="2026-07-01")
    occ_before = db._conn.execute(
        "SELECT COUNT(*) FROM corner_issue_occurrences").fetchone()[0]
    out_before = db._conn.execute(
        "SELECT COUNT(*) FROM setup_experiment_outcomes").fetchone()[0]
    # build memory (a pure read) — must not change any prior store
    db.build_cross_session_memory(
        car=CAR, track=TRACK, layout_id=LAYOUT, discipline="Race", compound="RH")
    assert db._conn.execute(
        "SELECT COUNT(*) FROM corner_issue_occurrences").fetchone()[0] == occ_before
    assert db._conn.execute(
        "SELECT COUNT(*) FROM setup_experiment_outcomes").fetchone()[0] == out_before
