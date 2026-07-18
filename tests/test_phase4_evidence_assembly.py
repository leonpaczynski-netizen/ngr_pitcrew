"""Engineering-Brain Phase 4 — evidence assembly (pure selection) + runtime path."""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from data.session_db import SessionDB
from data.applied_checkpoint import make_checkpoint
from strategy._setup_constants import DB_VERSION
from strategy.setup_experiment import build_experiment_from_recommendation, ProtectedBehaviour
from strategy.setup_experiment_outcome import DriverReviewInput
from strategy.setup_evidence_assembly import (
    SessionCandidate, SelectionStatus, select_test_session, select_baseline_session,
    summarise_valid_laps,
)
from strategy.engineering_lap_validity import evaluate_session_laps, LapPurpose

ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------- pure selection
def _cand(sid, cps=(), laps=5, scope="s"):
    return SessionCandidate(session_id=str(sid), checkpoint_ids=tuple(cps),
                            valid_lap_count=laps, scope_fingerprint=scope)


# 34
def test_authoritative_parent_baseline_selected():
    cands = [_cand("100", cps=("parent_cp",)), _cand("200", cps=("exp_cp",))]
    r = select_baseline_session(cands, applied_checkpoint_id="exp_cp",
                                parent_checkpoint_id="parent_cp")
    assert r.status == SelectionStatus.RESOLVED and r.session_id == "100"


# 35
def test_newest_unrelated_not_selected():
    # two non-parent sessions → ambiguous, never silently the newest
    cands = [_cand("100"), _cand("300")]
    r = select_baseline_session(cands, applied_checkpoint_id="exp_cp")
    assert r.status == SelectionStatus.AMBIGUOUS


# 36
def test_correct_checkpoint_test_selected():
    cands = [_cand("200", cps=("exp_cp",)), _cand("100", cps=("other",))]
    r = select_test_session(cands, applied_checkpoint_id="exp_cp")
    assert r.status == SelectionStatus.RESOLVED and r.session_id == "200"


# 37 / 38 timing exclusion is enforced by checkpoint tagging (before-apply sessions
# carry a different / no checkpoint)
def test_before_apply_session_excluded_from_test():
    cands = [_cand("100", cps=())]      # no experiment checkpoint tag
    r = select_test_session(cands, applied_checkpoint_id="exp_cp")
    assert r.status == SelectionStatus.MISSING


def test_after_apply_session_excluded_from_baseline():
    r = select_baseline_session([_cand("200", cps=("exp_cp",))],
                                applied_checkpoint_id="exp_cp",
                                explicit_session_id="200")
    assert r.status == SelectionStatus.INCOMPATIBLE


# 39
def test_multiple_baselines_ambiguous():
    cands = [_cand("100", cps=("parent_cp",)), _cand("110", cps=("parent_cp",))]
    r = select_baseline_session(cands, applied_checkpoint_id="exp_cp",
                                parent_checkpoint_id="parent_cp")
    assert r.status == SelectionStatus.AMBIGUOUS
    assert set(r.candidate_session_ids) == {"100", "110"}


# 40
def test_multiple_tests_ambiguous():
    cands = [_cand("200", cps=("exp_cp",)), _cand("210", cps=("exp_cp",))]
    r = select_test_session(cands, applied_checkpoint_id="exp_cp")
    assert r.status == SelectionStatus.AMBIGUOUS


# 41
def test_wrong_scope_excluded():
    cands = [_cand("200", cps=("exp_cp",), scope="OTHER")]
    r = select_test_session(cands, applied_checkpoint_id="exp_cp",
                            scope_fingerprint="MINE")
    assert r.status == SelectionStatus.MISSING


# 43
def test_wrong_setup_excluded():
    r = select_test_session([_cand("200", cps=("other_cp",))],
                            applied_checkpoint_id="exp_cp",
                            explicit_session_id="200")
    assert r.status == SelectionStatus.INCOMPATIBLE


# 44 / 45
def test_missing_baseline_and_test_explicit():
    assert select_baseline_session([], applied_checkpoint_id="cp").status == SelectionStatus.MISSING
    assert select_test_session([], applied_checkpoint_id="cp").status == SelectionStatus.MISSING


# 46
def test_partial_when_few_laps():
    r = select_test_session([_cand("200", cps=("exp_cp",), laps=2)],
                            applied_checkpoint_id="exp_cp")
    assert r.status == SelectionStatus.PARTIAL


# 47 / 48 / 49 / 50 whole-lap summary
def test_whole_lap_median_valid_only_not_fastest():
    rows = [{"lap_num": n, "lap_time_ms": t, "is_pit_lap": 0, "is_out_lap": 0,
             "off_track_count": 0} for n, t in
            [(1, 99000), (2, 95000), (3, 95200), (4, 95100), (5, 94000)]]
    # lap 1 is a warmup outlier rejected; lap 5 fastest but median governs
    _, summ = evaluate_session_laps(rows, purpose=LapPurpose.OUTCOME_COMPARISON)
    wl = summarise_valid_laps(rows, summ)
    assert wl.valid_lap_count == summ.usable_laps
    assert wl.median_lap_ms > 0
    assert wl.median_lap_ms != 94000           # not the fastest
    assert "rejected_lap_count" in wl.to_dict()


# ---------------------------------------------------- runtime DB integration
@pytest.fixture
def db():
    return SessionDB(":memory:")


def _applied_experiment(db, *, car_id=7, track="Fuji", layout="full_course",
                        parent="base1"):
    data = {"recommendation_status": "approved", "analysis": "front lock T1",
            "changes": [{"field": "brake_bias", "from": "55", "to_clamped": "52",
                         "rule_id": "BB1", "symptom": "front_lock"}],
            "diagnosis": {"dominant_problem": "front_lock", "target_corners": ["T1"]},
            "deterministic_plan": {"rule_engine_version": "46.0"},
            "test_sequence": {"stages": [{"success_criterion": "T1 lockup reduced",
                                          "rollback": "Base"}]},
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
    cp = make_checkpoint(setup_id=f"exp{eid}", fields={"brake_bias": 52},
                         confirmed_at="2026-07-19 10:00")
    db.save_applied_checkpoint(car_id, track, layout, "Race", cp)
    db.link_experiment_applied_checkpoint(eid, cp.checkpoint_id, {"brake_bias": 52})
    return eid, cp.checkpoint_id


def _laps(db, sid, n, t, car_id=7, track="Fuji"):
    for i in range(1, n + 1):
        db._conn.execute(
            "INSERT INTO lap_records (session_id, car_id, track, lap_num, lap_time_ms, "
            "is_pit_lap, is_out_lap) VALUES (?,?,?,?,?,0,0)", (sid, car_id, track, i, t))
    db._conn.commit()


def _occ(sid, cp, lap, seg="T1", issue="front_lock", phase="braking", axle="front"):
    return {"session_id": sid, "setup_checkpoint_id": cp, "lap_number": lap,
            "segment_id": seg, "corner_phase": phase, "issue_type": issue,
            "axle": axle, "severity": 0.7, "confidence": 0.8}


# 77 — no migration required; DB stays v22
def test_no_new_migration_needed(db):
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 22
    assert DB_VERSION == 22


# 80 — no duplicate telemetry storage: assembler reads existing corner_issue_occurrences
def test_no_duplicate_telemetry_tables(db):
    src = (ROOT / "data" / "session_db.py").read_text(encoding="utf-8")
    # Phase 4 added no new corner/telemetry table (only reads existing stores).
    assert "_DDL_V23" not in src
    assert "_migrate_v23" not in src


# 53/54/61 — practice-persisted corner occurrence reaches assembler → meaningful outcome
def test_persisted_occurrence_reaches_assembler_and_outcome(db):
    eid, cp = _applied_experiment(db)
    _laps(db, 100, 5, 95200)   # baseline
    _laps(db, 200, 5, 95000)   # test
    db.save_issue_occurrences(7, "Fuji", "full_course",
                              [_occ(100, "", n) for n in (2, 3, 4, 5)])       # baseline recurring
    db.save_issue_occurrences(7, "Fuji", "full_course", [_occ(200, cp, 2)])   # test isolated
    asm = db.assemble_setup_experiment_evidence(eid, test_session_id=200,
                                                baseline_session_id=100)
    assert asm["ok"]
    assert asm["test_selection"]["status"] == "resolved"
    assert asm["baseline_selection"]["status"] == "resolved"
    assert asm["corner_test"] and asm["corner_baseline"]
    # baseline T1 recurring 4/5, test isolated 1/5
    assert asm["corner_baseline"][0].affected_laps == 4
    assert asm["corner_test"][0].affected_laps == 1


# 52/60 — production review path produces a meaningful outcome without manual objects
def test_production_review_path_meaningful_outcome(db):
    eid, cp = _applied_experiment(db)
    _laps(db, 100, 5, 95200)
    _laps(db, 200, 5, 95000)
    db.save_issue_occurrences(7, "Fuji", "full_course", [_occ(100, "", n) for n in (2, 3, 4, 5)])
    db.save_issue_occurrences(7, "Fuji", "full_course", [_occ(200, cp, 2)])
    res = db.review_experiment_outcome(
        eid, test_session_id=200, baseline_session_id=100,
        driver_review=DriverReviewInput("f", True, target_symptom_resolved=True,
                                        braking_confidence_improved=True, vs_previous="better"))
    assert res["status"] == "confirmed_improvement"
    assert res["assembly"]["corner_test_count"] >= 1
    assert db.get_setup_experiment(eid)["status"] == "completed"


# 56 — applied experiment linkage retained (test evidence tied to the checkpoint)
def test_applied_experiment_linkage_retained(db):
    eid, cp = _applied_experiment(db)
    _laps(db, 200, 5, 95000)
    # occurrence tagged with a DIFFERENT checkpoint must not be treated as this test
    db.save_issue_occurrences(7, "Fuji", "full_course",
                              [{"session_id": 200, "setup_checkpoint_id": "OTHER_CP",
                                "lap_number": 2, "segment_id": "T1",
                                "corner_phase": "braking", "issue_type": "front_lock",
                                "confidence": 0.8}])
    asm = db.assemble_setup_experiment_evidence(eid, test_session_id=200)
    # session 200 does not carry THIS experiment's checkpoint → test incompatible/missing
    assert asm["test_selection"]["status"] in ("incompatible", "missing")


# 79 — Phase 1-3 records remain readable after assembly
def test_phase1_3_records_readable(db):
    eid, cp = _applied_experiment(db)
    _laps(db, 200, 5, 95000)
    db.save_issue_occurrences(7, "Fuji", "full_course", [_occ(200, cp, 2)])
    db.review_experiment_outcome(eid, test_session_id=200)
    assert db.get_setup_experiment(eid) is not None
    assert db.get_engineering_context_for_source is not None
    # applied checkpoint still resolvable
    assert db.get_latest_applied_checkpoint(7, "Fuji", "full_course", "Race") is not None


# 58 — review runs off-thread (structural: the worker calls review_experiment_outcome)
def test_review_uses_off_thread_worker():
    src = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
    assert "review_experiment_outcome" in src
    assert "threading.Thread(target=_worker, daemon=True)" in src


# insufficient case: high raw count but only one valid lap → INSUFFICIENT
def test_insufficient_when_evidence_thin(db):
    eid, cp = _applied_experiment(db)
    _laps(db, 200, 2, 95000)     # only 2 valid laps (< min 4)
    db.save_issue_occurrences(7, "Fuji", "full_course",
                              [_occ(200, cp, 1) for _ in range(11)])   # 11 events, 1 lap
    res = db.review_experiment_outcome(eid, test_session_id=200, complete_on_success=False)
    assert res["status"] == "insufficient_evidence"
    assert not res["failed_directions"]
