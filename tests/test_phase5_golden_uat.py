"""Engineering-Brain Phase 5 — golden UAT through the PRODUCTION loop.

Porsche 911 RSR '17 @ Fuji Full Course. Each scenario drives the real
review_and_learn (assemble → Phase-3 evaluate → learn → select) with persisted
evidence — no test-only manual learning objects.
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


def _experiment(db, *, field, frm, to, symptom, target, protected_corner="Final",
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
        e, protected_behaviours=(ProtectedBehaviour("mid-corner balance", corners=("T3",)),
                                 ProtectedBehaviour("rear traction", corners=(protected_corner,))),
        test_protocol=dataclasses.replace(e.test_protocol, min_clean_laps=4,
                                          target_corners=(target,),
                                          rollback_target="Base RSR Race")).with_idempotency_key()
    eid = db.create_setup_experiment(e)
    db.transition_experiment_state(eid, "ready_for_apply")
    cp = make_checkpoint(setup_id=f"exp{eid}", fields={field: float(to)}, confirmed_at="t")
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


# --- Scenario A: confirmed improvement reinforces a working direction -------
def test_scenario_A_confirmed_reinforces(db):
    eid, cp, scope = _experiment(db, field="aero_front", frm="300", to="340",
                                 symptom="mid_corner_understeer", target="T3")
    _laps(db, 500, 5); _laps(db, 600, 5)
    db.save_issue_occurrences(CAR_ID, TRACK, LAYOUT,
        _occ(500, "", [2, 3, 4, 5], "T3", "understeer", "apex"))
    db.save_issue_occurrences(CAR_ID, TRACK, LAYOUT,
        _occ(600, cp, [2], "T3", "understeer", "apex"))
    r = db.review_and_learn(eid, test_session_id=600, baseline_session_id=500,
        driver_review=DriverReviewInput("f", True, target_symptom_resolved=True,
                                        braking_confidence_improved=True, vs_previous="better"))
    assert r["status"] == "confirmed_improvement"
    w = db.get_working_window(scope, "aero_front", car=CAR, track=TRACK,
                              layout_id=LAYOUT, discipline="Race")
    assert w["confidence"] == "provisional"          # one success ≠ broad high confidence
    assert 340.0 in w["successful_values"]
    inc = [d for d in w["directional"] if d["direction"] == "increase"][0]
    assert inc["improved_count"] == 1
    # next experiment is a refinement or "retain / gather more evidence" (target resolved)
    nxt = r["next_experiment"]
    assert nxt["selected"] is None or nxt["selected"]["field"] != "aero_front" \
        or nxt.get("no_selection_reason")


# --- Scenario B: confirmed regression creates a failed-direction lockout ----
def test_scenario_B_regression_lockout_lsd(db):
    # the historical failure pattern: increasing LSD accel-lock worsened rear control
    eid, cp, scope = _experiment(db, field="lsd_accel", frm="22", to="26",
                                 symptom="rear_loose_on_exit", target="Final")
    _laps(db, 700, 5); _laps(db, 800, 5)
    db.save_issue_occurrences(CAR_ID, TRACK, LAYOUT,
        _occ(700, "", [2], "Final", "wheelspin", "exit", "rear"))
    db.save_issue_occurrences(CAR_ID, TRACK, LAYOUT,
        _occ(800, cp, [2, 3, 4, 5], "Final", "wheelspin", "exit", "rear"))
    r = db.review_and_learn(eid, test_session_id=800, baseline_session_id=700,
        driver_review=DriverReviewInput("f", True, new_symptoms=("rear snap",), vs_previous="worse"))
    assert r["status"] == "regression"
    assert db.get_setup_experiment(eid)["status"] == "rejected"
    # parent remains rollback target; no auto-rollback
    assert r["rollback_target"] == "Base RSR Race"
    assert db.get_setup_experiment(eid)["applied_checkpoint_id"] == cp
    w = db.get_working_window(scope, "lsd_accel", car=CAR, track=TRACK,
                              layout_id=LAYOUT, discipline="Race")
    assert "increase" in [d["direction"] for d in w["directional"] if d["locked_out"]]
    # a candidate proposing the SAME increase must be blocked
    nxt = db.select_next_experiment(eid, dominant_issue="rear_loose_on_exit",
        target_corners=["Final"], recurrence_class="recurring", valid_lap_count=5,
        current_setup={"lsd_accel": 26, "aero_rear": 400, "toe_rear": 0.10})
    assert (nxt.get("selected") or {}).get("candidate_id") != "lsd_accel:increase"
    lsd = [c for c in nxt["considered"] if c["candidate_id"] == "lsd_accel:increase"]
    if lsd:
        assert "repeated_failed_direction" in lsd[0]["hard_blockers"] \
            or "hypothesis_already_disproved" in lsd[0]["hard_blockers"]


# --- Scenario C: no meaningful effect retires a dead-end test ---------------
def test_scenario_C_no_effect_retires_deadend(db):
    eid, cp, scope = _experiment(db, field="aero_front", frm="300", to="340",
                                 symptom="mid_corner_understeer", target="T3")
    _laps(db, 100, 5); _laps(db, 200, 5)
    # baseline + test both show the same understeer recurrence → no meaningful change
    db.save_issue_occurrences(CAR_ID, TRACK, LAYOUT,
        _occ(100, "", [2, 3, 4], "T3", "understeer", "apex"))
    db.save_issue_occurrences(CAR_ID, TRACK, LAYOUT,
        _occ(200, cp, [2, 3, 4], "T3", "understeer", "apex"))
    r = db.review_and_learn(eid, test_session_id=200, baseline_session_id=100,
        driver_review=DriverReviewInput("f", True, target_symptom_resolved=False))
    assert r["status"] in ("no_meaningful_change", "insufficient_evidence")
    if r["status"] == "no_meaningful_change":
        w = db.get_working_window(scope, "aero_front", car=CAR, track=TRACK,
                                  layout_id=LAYOUT, discipline="Race")
        assert w["improvement_count"] == 0 and w["unchanged_count"] == 1
        assert 340.0 in w["ineffective_values"]


# --- Scenario D: ambiguous / invalid evidence does not teach ----------------
def test_scenario_D_confounded_does_not_teach(db):
    eid, cp, scope = _experiment(db, field="aero_front", frm="300", to="340",
                                 symptom="mid_corner_understeer", target="T3")
    _laps(db, 100, 5); _laps(db, 200, 5)
    db.save_issue_occurrences(CAR_ID, TRACK, LAYOUT,
        _occ(100, "", [2, 3, 4, 5], "T3", "understeer", "apex"))
    db.save_issue_occurrences(CAR_ID, TRACK, LAYOUT,
        _occ(200, cp, [2], "T3", "understeer", "apex"))
    r = db.review_and_learn(eid, test_session_id=200, baseline_session_id=100,
        confounders=ConfounderInput(compound_changed=True),
        driver_review=DriverReviewInput("f", True, target_symptom_resolved=True),
        complete_on_success=False)
    assert r["status"] == "confounded"
    w = db.get_working_window(scope, "aero_front", car=CAR, track=TRACK,
                              layout_id=LAYOUT, discipline="Race")
    # no value learning from a confounded outcome
    assert w is None or (not w["successful_values"] and not w["unsuccessful_values"])
    # no forced setup change
    assert r["next_experiment"]["selected"] is None


# --- Scenario J: no safe experiment is the correct answer -------------------
def test_scenario_J_no_safe_experiment(db):
    eid, cp, scope = _experiment(db, field="aero_front", frm="300", to="340",
                                 symptom="mid_corner_understeer", target="T3")
    # weakly recurrent target → selection defers (insufficient recurrence)
    nxt = db.select_next_experiment(eid, dominant_issue="mid_corner_understeer",
        target_corners=["T3"], recurrence_class="isolated", valid_lap_count=2,
        current_setup={"aero_front": 300, "arb_front": 5})
    assert nxt["selected"] is None and nxt["no_selection_reason"]


# --- frozen safety contracts (12.9) -----------------------------------------
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


def test_arbiter_remains_dormant():
    from tests.test_engine_wiring_status import EXPERIMENTAL_SYMBOLS
    assert "arbitrate_setup_decision" in EXPERIMENTAL_SYMBOLS
    for p in (ROOT / "ui").glob("*.py"):
        assert "arbitrate_setup_decision" not in p.read_text(encoding="utf-8", errors="ignore")


def test_no_auto_apply_or_rollback_in_pure_modules():
    for mod in ("working_window", "experiment_selection"):
        src = (ROOT / "strategy" / f"{mod}.py").read_text(encoding="utf-8")
        assert "mark_applied" not in src and "apply_revert" not in src
        assert "save_applied_checkpoint" not in src
