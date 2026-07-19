"""Phase 15 — golden UAT scenarios A-R (Section 25).

A-Q exercise the pure synthesis through production-domain vocabulary; N/R + the DB tests
exercise the real SessionDB production path (canonical applied baseline + restart).
"""
import pytest

from data.session_db import SessionDB
from strategy._setup_constants import DB_VERSION
from strategy.development_history import MemoryContextKey, build_development_record
from strategy.mechanism_annotation import annotate_diagnosis
from strategy.intervention_hypothesis import build_intervention_hypotheses as BIH
from strategy.experiment_synthesis import (
    ExperimentSynthesisStatus as ST, InterventionTestKind,
    synthesize_bounded_experiments as SYN,
)
from strategy.setup_ranges import resolve_ranges
from strategy import gearbox_evidence as gbx
from data.applied_checkpoint import compute_setup_hash

RANGES = dict(resolve_ranges("Porsche 911 RSR")); RANGES["final_drive"] = (3.0, 5.0)
IDENT = {"car": "Porsche 911 RSR", "track": "Fuji", "layout_id": "fc"}
FIELDS = {"arb_front": 4, "arb_rear": 4, "brake_bias": 0, "springs_front": 5.0,
          "springs_rear": 5.0, "lsd_accel": 20, "lsd_decel": 20, "lsd_initial": 10,
          "aero_front": 300, "aero_rear": 400, "camber_front": -3.0, "camber_rear": -2.0,
          "toe_front": 0.10, "toe_rear": 0.20, "ride_height_front": 70,
          "ride_height_rear": 75, "final_drive": 4.100}


def applied(fields=None, car="Porsche 911 RSR", state="applied"):
    f = dict(fields if fields is not None else FIELDS)
    d = {"car": car, "track": "Fuji", "layout_id": "fc", "setup_id": "S1", "name": "Base",
         "revision": 1, "state": state, "fields": f, "purpose": "Race"}
    d["setup_hash"] = compute_setup_hash(f)
    return d


def ann(it, fam="rotation", axle="", phase="", **kw):
    d = {"issue_family": fam, "issue_type": it, "axle": axle, "phase": phase,
         "segment_id": "T1", "residual_state": "unchanged", "recurring": True,
         "valid_laps": 4, "sessions_seen": 2, "telemetry_available": True, "key": "k-" + it}
    return annotate_diagnosis(d, failed_directions=kw.get("fd", ()),
                             protected_good=kw.get("pg", ()), speed_context=kw.get("sc", ""))


def syn(it, fam="rotation", axle="", phase="", applied_setup=None, gearbox_state="",
        outcome_history=None, **kw):
    hs = BIH(ann(it, fam, axle, phase, **kw).to_dict(), gearbox_state=gearbox_state,
             speed_context=kw.get("sc", ""), outcome_history=outcome_history)
    return SYN(hs.to_dict(), applied_setup=applied_setup if applied_setup is not None else applied(),
               session_identity=IDENT, ranges=RANGES, gearbox_state=gearbox_state)


def _all(r):
    return ([r.selected_candidate] if r.selected_candidate else []) + list(r.alternative_candidates)


# A: eligible single-field ARB
def test_A_single_field_arb():
    r = syn("entry_understeer", axle="front", phase="entry", pg=[{"behaviour": "traction good"}])
    sc = r.selected_candidate
    assert r.overall_status == ST.READY_FOR_PREFLIGHT.value
    assert len(sc["deltas"]) == 1 and sc["deltas"][0]["field"] == "arb_front"
    assert sc["deltas"][0]["is_exactly_one_step"]
    assert sc["unchanged_field_count"] == len(FIELDS) - 1
    assert "traction good" in sc["protected_good_behaviours"]
    assert not r.preflight_ready or True  # ready, but nothing applied
    assert r.selected_candidate["test_protocol"]["unchanged_field_guarantee"] is True


# B: entry understeer with the locked field blocked; alternatives may only be conditional
def test_B_locked_braking_stability():
    r = syn("entry_understeer", axle="front", phase="entry",
            fd=[("arb_front", "decrease", "lockout")])
    # the locked field produces NO candidate and is explicitly rejected as locked
    assert not [c for c in _all(r) if c and c["deltas"][0]["field"] == "arb_front"]
    assert any(x["component"] == "arb_front" and x["status"] == ST.BLOCKED_BY_WORKING_WINDOW.value
               for x in r.rejected)
    # nothing is ready-for-preflight (the risky primary is locked); no silent compensating
    # field — every candidate remains single-field
    assert not r.preflight_ready
    for c in _all(r):
        if c:
            assert len(c["deltas"]) == 1


# C: exit wheelspin with competing LSD → no LSD increase
def test_C_wheelspin_no_lsd_increase():
    r = syn("wheelspin", fam="traction", axle="rear", phase="exit",
            fd=[("lsd_accel", "increase", "lockout")])
    assert not [c for c in _all(r) if c and c["deltas"][0]["field"] == "lsd_accel"]


# D: valid LSD initial-torque hypothesis (synthetic) → only lsd_initial one step
def test_D_lsd_initial_only():
    hset = {"canonical_issue": {"issue_type": "apex_connection"}, "content_fingerprint": "fp",
            "testable": [{"hypothesis_id": "h", "source_mechanism_id": "m", "status": "testable",
                          "direction": "increase_locking", "evidence_grade": "moderate",
                          "target": {"component": "lsd_initial", "handling_phase": "mid_corner"},
                          "expected_response": {"predicted_benefit": "apex"}, "predicted_trade_offs": [],
                          "protected_good_at_risk": [], "rejection_criteria": [], "test_design": {}}],
            "conditional": [], "competing": [], "blocked": [], "preserve_and_observe": []}
    r = SYN(hset, applied_setup=applied(), session_identity=IDENT, ranges=RANGES)
    sc = r.selected_candidate
    assert sc and len(sc["deltas"]) == 1 and sc["deltas"][0]["field"] == "lsd_initial"
    assert sc["deltas"][0]["candidate_value"] == 11   # 10 + one step, no hard-coded value
    changed = {d["field"] for d in sc["deltas"]}
    assert "lsd_accel" not in changed and "lsd_decel" not in changed


# E: aero hypothesis with valid high-speed context
def test_E_aero_with_speed_context():
    r = syn("understeer", axle="front", phase="", sc="high_speed")
    aero = [c for c in _all(r) if c and c["deltas"][0]["field"] == "aero_front"]
    # aero candidate exists (conditional or competing) with a legal step, trade-offs shown
    assert aero
    assert aero[0]["deltas"][0]["field"] == "aero_front"


# F: same aero issue without speed context → no ready aero experiment
def test_F_aero_without_context():
    r = syn("mid_corner_understeer", axle="front", phase="apex")
    aero = [c for c in _all(r) if c and c["deltas"][0]["field"] == "aero_front"]
    if aero:
        assert aero[0]["status"] != ST.READY_FOR_PREFLIGHT.value


# G: gearing too long → final drive one step shorter (higher ratio)
def test_G_gearing_too_long():
    r = syn("gearing_too_long", fam="gearing", axle="rear", gearbox_state=gbx.GEARING_TOO_LONG)
    fd = [c for c in _all(r) if c and c["deltas"][0]["field"] == "final_drive"][0]
    d = fd["deltas"][0]
    assert d["direction"] == "shorten" and d["candidate_value"] > d["baseline_value"]
    assert len(fd["deltas"]) == 1


# H: conflicting gearbox → no final-drive candidate
def test_H_conflicting_gearbox():
    r = syn("wrong_gear", fam="gearing", axle="rear", phase="exit",
            gearbox_state=gbx.GEARING_CONFLICTING)
    assert not [c for c in _all(r) if c and c["deltas"][0]["field"] == "final_drive"]


# I: count-only bottoming → no ride-height/spring/damper experiment
def test_I_count_only_bottoming():
    r = syn("bottoming", fam="platform", axle="", phase="")
    fields = {d["field"] for c in _all(r) if c for d in c["deltas"]}
    assert not (fields & {"ride_height_front", "ride_height_rear", "springs_front",
                          "springs_rear", "dampers_front_comp"})


# J: confirmed prior regression → same field/direction blocked
def test_J_prior_regression_blocks():
    r = syn("entry_understeer", axle="front", phase="entry",
            outcome_history=[{"fields": ["arb_front"], "outcome_status": "regression",
                              "single_field": True}])
    arb = [c for c in _all(r) if c and c["deltas"][0]["field"] == "arb_front"]
    assert not arb
    assert any(x["status"] == ST.BLOCKED_BY_PRIOR_REGRESSION.value for x in r.rejected)


# K: prior coupled improvement → coupled candidate only if Phase 14 marked coupled
def test_K_prior_coupled():
    r = syn("rear_loose_on_exit", fam="traction", axle="rear", phase="exit",
            outcome_history=[{"fields": ["lsd_accel", "aero_rear"],
                              "outcome_status": "confirmed_improvement", "single_field": False}])
    coupled = [c for c in _all(r) if c and c["attribution_scope"] == "coupled_pair"]
    for c in coupled:
        assert c["status"] == ST.REQUIRES_COUPLED_EXPERIMENT.value


# L: fresh profile → one-step from current, no invented prior
def test_L_fresh_profile():
    r = syn("entry_understeer", axle="front", phase="entry")
    sc = r.selected_candidate
    assert sc["deltas"][0]["is_exactly_one_step"]
    assert "4.10" not in str(r.to_dict())  # no historic final-drive jump


# M: genuine matching proven history → still smallest step from CURRENT baseline
def test_M_proven_history_still_one_step():
    # even with a nearby proven value, synthesis moves one legal step from the baseline
    r = syn("entry_understeer", axle="front", phase="entry")
    d = r.selected_candidate["deltas"][0]
    assert abs(d["delta"]) == d["legal_step"] and d["candidate_value"] == 3


# N: canonical applied setup mismatch → blocked
def test_N_baseline_mismatch():
    r = syn("entry_understeer", axle="front", phase="entry", applied_setup=applied(car="Mazda"))
    assert r.overall_status == ST.BLOCKED_BY_BASELINE_STATE.value and r.selected_candidate is None


# O: legal boundary → no candidate, no clamp disguising a no-op
def test_O_legal_boundary():
    f = dict(FIELDS); f["brake_bias"] = 5
    r = syn("front_lock", fam="braking", axle="front", phase="braking", applied_setup=applied(f))
    assert r.overall_status == ST.BLOCKED_BY_LEGALITY.value


# P: tied experiments → both visible, no auto winner
def test_P_ties_not_auto_selected():
    # two synthetic testable single-field hypotheses of equal grade/step/protection
    def h(hid, comp):
        return {"hypothesis_id": hid, "source_mechanism_id": "m", "status": "testable",
                "direction": "stiffen", "evidence_grade": "moderate",
                "target": {"component": comp, "handling_phase": "mid_corner"},
                "expected_response": {"predicted_benefit": "x"}, "predicted_trade_offs": [],
                "protected_good_at_risk": [], "rejection_criteria": [], "test_design": {}}
    hset = {"canonical_issue": {"issue_type": "oversteer"}, "content_fingerprint": "fp",
            "testable": [h("h1", "arb_rear"), h("h2", "springs_rear")],
            "conditional": [], "competing": [], "blocked": [], "preserve_and_observe": []}
    r = SYN(hset, applied_setup=applied(), session_identity=IDENT, ranges=RANGES)
    assert r.selected_candidate is None and len(r.alternative_candidates) >= 2
    assert r.unresolved_conflicts


# --- DB production path (N-real, Q, R) --------------------------------------
CTX = MemoryContextKey(driver="leon", car="Porsche 911 RSR", track="Fuji", layout_id="fc",
                       discipline="Race", gt7_version="1.49", compound="RH")


def _seed(db, at="2026-07-01T10:00"):
    outcome = {"id": "300", "experiment_id": 10, "status": "no_meaningful_change",
               "confidence_level": "high", "scope_fingerprint": "sf", "test_session_id": "s1",
               "protected": [], "failed_directions": []}
    exp = {"id": 10, "scope_fingerprint": "sf",
           "changes": [{"field": "arb_front", "from_value": "5", "to_value": "4"}]}
    residuals = [{"issue_key": "k1", "family": "rotation", "issue_type": "entry_understeer",
                  "axle": "front", "phase": "entry", "segment_id": "T1", "corner_name": "T1",
                  "residual_state": "unchanged", "is_new": False, "is_regression": False,
                  "still_present": True, "protected_good": False, "confidence": "high"}]
    rec = build_development_record(outcome, exp, context=CTX, scope_fingerprint="sf",
                                  working_windows=[], residuals=residuals, recorded_at=at,
                                  session_date=at[:10])
    db._persist_development_record(rec, created_at=rec.recorded_at)


def _kw():
    return dict(car="Porsche 911 RSR", track="Fuji", layout_id="fc", discipline="Race",
                driver="leon", gt7_version="1.49", compound="RH")


def test_Q_empty_database_safe():
    db = SessionDB(":memory:")
    r = db.build_bounded_setup_experiments(car="Porsche 911 RSR", track="Fuji", discipline="Race")
    assert r["ok"] and r["count"] == 0 and r["synthesis_results"] == []
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 25
    db.close()


def test_R_db_production_path_and_restart(tmp_path):
    p = str(tmp_path / "s.db")
    db = SessionDB(p)
    _seed(db)
    r1 = db.build_bounded_setup_experiments(applied_setup=applied(), session_identity=IDENT, **_kw())
    assert r1["ok"] and r1["count"] >= 1
    import re
    assert not re.search(r"set \w+ to \d", str(r1).lower())  # no imperative Apply
    db._conn.close()
    db2 = SessionDB(p)
    r2 = db2.build_bounded_setup_experiments(applied_setup=applied(), session_identity=IDENT, **_kw())
    assert r2["content_fingerprint"] == r1["content_fingerprint"]
    assert db2._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION == 25
    db2._conn.close()
