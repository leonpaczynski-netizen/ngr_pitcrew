"""Engineering-Brain Phase 6 — golden UAT through the PRODUCTION loop.

Porsche 911 RSR '17 @ Fuji Full Course. Each scenario drives review_and_learn
(review → learn → residual snapshot → multi-symptom plan) with persisted evidence.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from data.session_db import SessionDB
from data.applied_checkpoint import make_checkpoint
from strategy.setup_experiment import build_experiment_from_recommendation, ProtectedBehaviour
from strategy.setup_experiment_outcome import DriverReviewInput, ConfounderInput

CAR_ID, CAR = 7, "Porsche 911 RSR (991) '17"
TRACK, LAYOUT = "Fuji International Speedway", "full_course"
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def db():
    d = SessionDB(":memory:")
    d._conn.execute("INSERT INTO cars (id, name) VALUES (?, ?)", (CAR_ID, CAR))
    d._conn.commit()
    return d


def _experiment(db, *, field, frm, to, symptom, target, protected_corner="T5",
                extra_fields=None, parent="base_rsr"):
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
        e, protected_behaviours=(ProtectedBehaviour("rear traction", corners=(protected_corner,)),),
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


def _laps(db, sid, n, t=95000):
    for i in range(1, n + 1):
        db._conn.execute("INSERT INTO lap_records (session_id, car_id, track, lap_num, "
                         "lap_time_ms, is_pit_lap, is_out_lap) VALUES (?,?,?,?,?,0,0)",
                         (sid, CAR_ID, TRACK, i, t))
    db._conn.commit()


def _occ(sid, cp, laps, seg, issue, phase, axle=""):
    return [{"session_id": sid, "setup_checkpoint_id": cp, "lap_number": n,
             "segment_id": seg, "corner_phase": phase, "issue_type": issue,
             "axle": axle, "confidence": 0.85} for n in laps]


_CUR = {"aero_front": 340, "aero_rear": 400, "arb_front": 5, "arb_rear": 4,
        "lsd_accel": 30, "toe_rear": 0.10, "brake_bias": 0}


# --- Scenario A: one issue resolved, another remains ------------------------
def test_scenario_A_one_resolved_one_remains(db):
    eid, cp, scope = _experiment(db, field="aero_front", frm="300", to="340",
                                 symptom="mid_corner_understeer", target="T3",
                                 extra_fields=_CUR)
    _laps(db, 500, 5); _laps(db, 600, 5)
    db.save_issue_occurrences(CAR_ID, TRACK, LAYOUT,
        _occ(500, "", [2, 3, 4, 5], "T3", "understeer", "apex")
        + _occ(500, "", [2, 3, 4, 5], "T4", "wheelspin", "exit", "rear"))
    db.save_issue_occurrences(CAR_ID, TRACK, LAYOUT,
        _occ(600, cp, [2], "T3", "understeer", "apex")
        + _occ(600, cp, [2, 3, 4, 5], "T4", "wheelspin", "exit", "rear"))
    r = db.review_and_learn(eid, test_session_id=600, baseline_session_id=500,
        driver_review=DriverReviewInput("f", True, target_symptom_resolved=True, vs_previous="better"))
    plan = r["engineering_plan"]
    snap = plan["snapshot"]; pl = plan["plan"]
    states = {ri["identity"]["issue_type"]: ri["residual_state"]
              for ri in snap["residual_issues"]}
    assert states["understeer"] == "resolved"        # only with adequate evidence
    assert states["wheelspin"] == "unchanged"        # persistent
    # resolved issue not re-selected; the remaining wheelspin drives the plan
    assert pl["immediate_experiment"] is not None
    assert pl["immediate_experiment"]["target_issue"] == "wheelspin"
    assert len(pl["queued"]) <= 3


# --- Scenario B: original improves, new regression appears ------------------
def test_scenario_B_new_regression_prioritised(db):
    eid, cp, scope = _experiment(db, field="brake_bias", frm="0", to="-2",
                                 symptom="front_lock", target="T1", extra_fields=_CUR)
    _laps(db, 700, 5); _laps(db, 800, 5)
    # baseline: T1 front_lock recurring; test: T1 improved but NEW rear braking instability
    db.save_issue_occurrences(CAR_ID, TRACK, LAYOUT,
        _occ(700, "", [2, 3, 4, 5], "T1", "front_lock", "braking", "front"))
    db.save_issue_occurrences(CAR_ID, TRACK, LAYOUT,
        _occ(800, cp, [2], "T1", "front_lock", "braking", "front")
        + _occ(800, cp, [2, 3, 4, 5], "T1", "rear_loose_under_braking", "braking", "rear"))
    r = db.review_and_learn(eid, test_session_id=800, baseline_session_id=700,
        driver_review=DriverReviewInput("f", True, new_symptoms=("rear steps out braking",), vs_previous="worse"))
    plan = r["engineering_plan"]
    snap = plan["snapshot"]; pl = plan["plan"]
    # the new rear-braking issue is a regression and outranks the residual
    assert snap["new_issues"] or snap["worsened"] or snap["damaged_good"]
    if pl["immediate_experiment"]:
        # immediate targets the regression family, not the improved front lock alone
        assert pl["immediate_experiment"]["target_issue"] != "front_lock"


# --- Scenario F: failed LSD direction remains blocked -----------------------
def test_scenario_F_failed_lsd_direction_blocked(db):
    # first: an LSD accel INCREASE that regresses (creates the lockout)
    eid, cp, scope = _experiment(db, field="lsd_accel", frm="22", to="26",
                                 symptom="rear_loose_on_exit", target="Final",
                                 extra_fields={"aero_rear": 400, "toe_rear": 0.10})
    _laps(db, 100, 5); _laps(db, 200, 5)
    db.save_issue_occurrences(CAR_ID, TRACK, LAYOUT,
        _occ(100, "", [2], "Final", "rear_wheelspin", "exit", "rear"))
    db.save_issue_occurrences(CAR_ID, TRACK, LAYOUT,
        _occ(200, cp, [2, 3, 4, 5], "Final", "rear_wheelspin", "exit", "rear"))
    db.review_and_learn(eid, test_session_id=200, baseline_session_id=100,
        driver_review=DriverReviewInput("f", True, vs_previous="worse"))
    w = db.get_working_window(scope, "lsd_accel", car=CAR, track=TRACK,
                              layout_id=LAYOUT, discipline="Race")
    assert "increase" in [d["direction"] for d in w["directional"] if d["locked_out"]]
    # a new plan proposing the same lsd_accel increase must NOT select it
    plan = db.build_engineering_plan(eid)
    pl = plan["plan"]
    if pl["immediate_experiment"]:
        assert pl["immediate_experiment"]["candidate_id"] != "lsd_accel:increase"


# --- Scenario G: one-off bad lap does not reorder --------------------------
def test_scenario_G_oneoff_bad_lap_excluded(db):
    eid, cp, scope = _experiment(db, field="aero_front", frm="300", to="340",
                                 symptom="mid_corner_understeer", target="T3",
                                 extra_fields=_CUR)
    _laps(db, 100, 5)
    # one INVALID lap (out lap) with severe events must be excluded
    db._conn.execute("INSERT INTO lap_records (session_id, car_id, track, lap_num, "
                     "lap_time_ms, is_pit_lap, is_out_lap) VALUES (?,?,?,?,?,0,1)",
                     (200, CAR_ID, TRACK, 1, 95000))
    for i in range(2, 6):
        db._conn.execute("INSERT INTO lap_records (session_id, car_id, track, lap_num, "
                         "lap_time_ms, is_pit_lap, is_out_lap) VALUES (?,?,?,?,?,0,0)",
                         (200, CAR_ID, TRACK, i, 95000))
    db._conn.commit()
    db.save_issue_occurrences(CAR_ID, TRACK, LAYOUT,
        _occ(100, "", [2, 3, 4, 5], "T3", "understeer", "apex"))
    # severe events only on the invalid out-lap (lap 1)
    db.save_issue_occurrences(CAR_ID, TRACK, LAYOUT,
        [{"session_id": 200, "setup_checkpoint_id": cp, "lap_number": 1,
          "segment_id": "T9", "corner_phase": "exit", "issue_type": "wheelspin",
          "axle": "rear", "confidence": 0.9} for _ in range(11)]
        + _occ(200, cp, [2], "T3", "understeer", "apex"))
    r = db.review_and_learn(eid, test_session_id=200, baseline_session_id=100,
        driver_review=DriverReviewInput("f", True, vs_previous="better"))
    snap = r["engineering_plan"]["snapshot"]
    states = {ri["identity"]["segment_id"]: ri["residual_state"]
              for ri in snap["residual_issues"]}
    # T9 wheelspin on the invalid lap must NOT appear as a recurring/new issue
    assert states.get("T9") not in ("new", "worsened", "unchanged")


# --- Scenario J: no setup change justified ---------------------------------
def test_scenario_J_no_change_justified(db):
    eid, cp, scope = _experiment(db, field="aero_front", frm="300", to="340",
                                 symptom="mid_corner_understeer", target="T3",
                                 extra_fields=_CUR)
    # confounded review → decision blocks → no immediate, retain
    _laps(db, 100, 5); _laps(db, 200, 5)
    db.save_issue_occurrences(CAR_ID, TRACK, LAYOUT,
        _occ(100, "", [2, 3, 4, 5], "T3", "understeer", "apex"))
    db.save_issue_occurrences(CAR_ID, TRACK, LAYOUT, _occ(200, cp, [2], "T3", "understeer", "apex"))
    r = db.review_and_learn(eid, test_session_id=200, baseline_session_id=100,
        confounders=ConfounderInput(compound_changed=True),
        driver_review=DriverReviewInput("f", True), complete_on_success=False)
    assert r["status"] == "confounded"
    pl = r["engineering_plan"]["plan"]
    assert pl["immediate_experiment"] is None      # no forced change


# --- Scenario L: restart determinism ---------------------------------------
def test_scenario_L_restart_determinism(tmp_path):
    p = str(tmp_path / "s.db")
    a = SessionDB(p)
    a._conn.execute("INSERT INTO cars (id, name) VALUES (?, ?)", (CAR_ID, CAR)); a._conn.commit()
    eid, cp, scope = _experiment(a, field="aero_front", frm="300", to="340",
                                 symptom="mid_corner_understeer", target="T3", extra_fields=_CUR)
    _laps(a, 100, 5); _laps(a, 200, 5)
    a.save_issue_occurrences(CAR_ID, TRACK, LAYOUT,
        _occ(100, "", [2, 3, 4, 5], "T3", "understeer", "apex")
        + _occ(100, "", [2, 3, 4, 5], "T4", "wheelspin", "exit", "rear"))
    a.save_issue_occurrences(CAR_ID, TRACK, LAYOUT,
        _occ(200, cp, [2], "T3", "understeer", "apex")
        + _occ(200, cp, [2, 3, 4, 5], "T4", "wheelspin", "exit", "rear"))
    a.review_and_learn(eid, test_session_id=200, baseline_session_id=100,
        driver_review=DriverReviewInput("f", True, vs_previous="better"))
    plan_a = a.build_engineering_plan(eid)
    a._conn.close()
    b = SessionDB(p)
    plan_b = b.build_engineering_plan(eid)
    assert plan_a["plan"]["content_fingerprint"] == plan_b["plan"]["content_fingerprint"]
    assert plan_a["snapshot"]["content_fingerprint"] == plan_b["snapshot"]["content_fingerprint"]


# --- Phase 6 added no migration (plan is regenerable) — the live schema tracks
# DB_VERSION, which later phases (Phase 8 → v24) legitimately advance ------------
def test_no_migration_needed(db):
    from strategy._setup_constants import DB_VERSION
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION
    assert DB_VERSION >= 23
    src = (ROOT / "data" / "session_db.py").read_text(encoding="utf-8")
    # Phase 6 itself introduced no _migrate_v24 (that arrived with Phase 8); guard
    # against an unexpected next bump.
    assert "_migrate_v25" not in src


def test_frozen_contracts():
    from tests.test_race_config_id_hash import GOLDEN_VECTORS, _bind
    for strategy, expected in GOLDEN_VECTORS:
        assert _bind(strategy)._compute_race_config_id() == expected
    from tests.test_legacy_fanout_phase_5 import _scan_inventory, FROZEN_ALLOWLIST
    assert _scan_inventory() == FROZEN_ALLOWLIST
    from strategy._setup_constants import RULE_ENGINE_VERSION
    assert RULE_ENGINE_VERSION == "46.0"


def test_apply_gate_and_arbiter_unchanged():
    src = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
    assert "_status_approved: bool = (not _is_legacy) and (_rec_status in _APPROVED_STATUSES)" in src
    from tests.test_engine_wiring_status import EXPERIMENTAL_SYMBOLS
    assert "arbitrate_setup_decision" in EXPERIMENTAL_SYMBOLS
    for pyf in (ROOT / "ui").glob("*.py"):
        assert "arbitrate_setup_decision" not in pyf.read_text(encoding="utf-8", errors="ignore")


def test_pure_planning_modules_no_apply():
    for mod in ("engineering_issue", "engineering_state", "experiment_planning"):
        s = (ROOT / "strategy" / f"{mod}.py").read_text(encoding="utf-8")
        assert "mark_applied" not in s and "save_applied_checkpoint" not in s
        assert "apply_revert" not in s
