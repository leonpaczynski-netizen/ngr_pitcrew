"""Phase 14 — golden UAT scenarios A-N (Section 26).

A-L exercise the pure reasoning through the production-domain vocabulary; M and N exercise
the real SessionDB production path (proven-history fold + empty database).
"""
import pytest

from data.session_db import SessionDB
from strategy._setup_constants import DB_VERSION
from strategy.development_history import MemoryContextKey, build_development_record
from strategy.mechanism_annotation import annotate_diagnosis
from strategy.intervention_hypothesis import (
    InterventionHypothesisStatus as S, build_intervention_hypotheses,
)
from strategy import gearbox_evidence as gbx


def _ann(it, fam, axle="", phase="", **kw):
    d = {"issue_family": fam, "issue_type": it, "axle": axle, "phase": phase,
         "segment_id": kw.get("seg", "T1"), "residual_state": kw.get("rs", "unchanged"),
         "recurring": kw.get("rec", True), "valid_laps": kw.get("vl", 4),
         "sessions_seen": 2, "telemetry_available": True, "key": "k-" + it}
    return annotate_diagnosis(d, failed_directions=kw.get("fd", ()),
                             protected_good=kw.get("pg", ()), speed_context=kw.get("sc", ""),
                             outcome=kw.get("outcome"))


def _all(s):
    return (list(s.testable) + list(s.conditional) + list(s.competing)
            + list(s.blocked) + list(s.preserve_and_observe))


# A: entry understeer with valid repeated evidence
def test_A_entry_understeer():
    s = build_intervention_hypotheses(
        _ann("entry_understeer", "rotation", "front", "entry",
             pg=[{"behaviour": "braking stability good"}]).to_dict())
    assert s.testable
    top = s.testable[0]
    assert top["direction"] == "soften"          # bounded front-end response direction
    assert top["predicted_trade_offs"]
    assert "braking stability good" in top["protected_good_at_risk"]
    assert top["test_design"]["variable_under_test"]
    assert "set " not in str(s.to_dict()).lower().replace("setup", "")


# B: mid-corner understeer with good entry balance -> don't churn entry
def test_B_mid_corner_understeer_protects_entry():
    s = build_intervention_hypotheses(
        _ann("mid_corner_understeer", "rotation", "front", "apex",
             pg=[{"behaviour": "turn-in confirmed good"}]).to_dict())
    assert s.testable
    # steady-state mechanisms (ARB/camber) considered; aero only conditional
    comps = {h["target"]["component"] for h in _all(s)}
    assert "arb_front" in comps
    for h in _all(s):
        if h["target"]["component"] == "aero_front":
            assert h["status"] in ("conditional", "insufficient_evidence")


# C: exit wheelspin with rear loose on throttle
def test_C_exit_wheelspin_no_auto_lsd():
    s = build_intervention_hypotheses(
        _ann("wheelspin", "traction", "rear", "exit",
             fd=[("lsd_accel", "increase", "lockout")]).to_dict())
    assert not [h for h in s.testable if h["target"]["component"] == "lsd_accel"]
    lsd = [h for h in s.blocked if h["target"]["component"] == "lsd_accel"]
    assert lsd and lsd[0]["status"] in (S.BLOCKED_BY_WORKING_WINDOW.value,
                                        S.CONTRADICTED_BY_OUTCOME.value)
    # competing traction-demand / gear / platform retained
    ids = {h["source_mechanism_id"] for h in _all(s)}
    assert {"exit_traction_demand", "exit_gear_selection", "exit_rear_load"} <= ids


# D: rear loose under braking -> competing causes; controlled braking-phase test
def test_D_rear_loose_under_braking():
    s = build_intervention_hypotheses(
        _ann("rear_loose_under_braking", "braking", "rear", "braking").to_dict())
    comps = {h["target"]["component"] for h in _all(s)}
    assert "lsd_decel" in comps and "brake_bias" in comps
    # brake-phase controlled test present
    assert any(h["target"]["handling_phase"] == "trail_braking" for h in _all(s))


# E: count-only bottoming -> no forced platform intervention
def test_E_count_only_bottoming_insufficient():
    s = build_intervention_hypotheses(_ann("bottoming", "platform", "", "").to_dict())
    assert s.overall_status in (S.INSUFFICIENT_EVIDENCE.value, S.NOT_EVALUABLE.value)
    assert not s.testable


# F: high-speed instability with valid speed context -> aero testable/conditional
def test_F_high_speed_aero_with_context():
    s = build_intervention_hypotheses(
        _ann("understeer", "rotation", "front", "", sc="high_speed").to_dict(),
        speed_context="high_speed")
    aero = [h for h in _all(s) if h["target"]["component"] == "aero_front"]
    # with valid speed context aero becomes a live candidate (testable / conditional /
    # competing) rather than being blocked pending speed evidence (contrast Scenario G)
    assert aero and aero[0]["status"] in ("testable", "conditional", "competing_mechanisms")
    assert aero[0]["status"] != "insufficient_evidence"
    # straight-line / balance trade-offs explicit; no fabricated downforce/load numbers
    assert aero[0]["predicted_trade_offs"]
    import re
    assert not re.search(r"\d+\s*(kg|n\b|newton|kpa|%\s*downforce|lb)", str(aero[0]).lower())


# G: same instability without speed context -> aero remains conditional/insufficient
def test_G_high_speed_without_context():
    s = build_intervention_hypotheses(
        _ann("mid_corner_understeer", "rotation", "front", "apex").to_dict())
    aero = [h for h in _all(s) if h["target"]["component"] == "aero_front"]
    assert aero and aero[0]["status"] in ("conditional", "insufficient_evidence")
    assert aero[0]["required_evidence"]


# H: unused sixth gear + telemetry suggesting too-short gearing -> conflicting
def test_H_conflicting_gearbox_no_direction():
    s = build_intervention_hypotheses(
        _ann("wrong_gear", "gearing", "rear", "exit").to_dict(),
        gearbox_state=gbx.GEARING_CONFLICTING)
    gear = [h for h in _all(s) if h["target"]["component"] == "transmission"]
    assert gear and gear[0]["direction"] == "no_defensible_direction"
    # correct final-drive semantics still hold
    assert gbx.final_drive_lengthens(4.30, 4.10) and gbx.final_drive_shortens(4.10, 4.30)


# I: confirmed prior regression from a single-field test -> direction blocked
def test_I_prior_regression_blocks_direction():
    s = build_intervention_hypotheses(
        _ann("entry_understeer", "rotation", "front", "entry").to_dict(),
        outcome_history=[{"fields": ["arb_front"], "outcome_status": "regression",
                          "single_field": True}])
    arb = [h for h in _all(s) if h["target"]["component"] == "arb_front"]
    assert arb and arb[0]["status"] == S.CONTRADICTED_BY_OUTCOME.value
    # the physical mechanism is not deleted (still referenced in the annotation)
    assert s.source_annotation.get("primary_mechanism")


# J: confirmed prior improvement from a coupled test -> coupled may be supported
def test_J_prior_coupled_improvement():
    s = build_intervention_hypotheses(
        _ann("rear_loose_on_exit", "traction", "rear", "exit").to_dict(),
        outcome_history=[{"fields": ["lsd_accel", "aero_rear"],
                          "outcome_status": "confirmed_improvement", "single_field": False}])
    coupled = [h for h in _all(s) if h["test_design"]["test_kind"] == "paired_coupled"]
    for h in coupled:
        assert h["test_design"]["attributable_to_single_field"] is False
        assert "field SET" in h["prior_outcome_relationship"]


# K: driver prefers front bite, but working window protects braking stability
def test_K_driver_preference_cannot_bypass_lockout():
    s = build_intervention_hypotheses(
        _ann("entry_understeer", "rotation", "front", "entry",
             fd=[("arb_front", "decrease", "lockout")]).to_dict(),
        driver_preference={"priority": "front_bite"})
    arb = [h for h in _all(s) if h["target"]["component"] == "arb_front"]
    # lockout remains authoritative regardless of preference
    assert arb and arb[0]["status"] == S.BLOCKED_BY_WORKING_WINDOW.value


# L: fresh profile with no proven history -> evidence-honest, no invented prior
def test_L_fresh_profile_no_invented_prior():
    s = build_intervention_hypotheses(_ann("entry_understeer", "rotation", "front", "entry").to_dict())
    blob = str(s.to_dict())
    assert "4.10" not in blob and "final drive 4" not in blob.lower()
    for h in _all(s):
        assert "no contradicting prior outcome" in h["prior_outcome_relationship"] or \
            "field SET" in h["prior_outcome_relationship"] or "regressed" in h["prior_outcome_relationship"] \
            or "lockout" in h["prior_outcome_relationship"]


# --- real production path (M, N) --------------------------------------------
CTX = MemoryContextKey(driver="leon", car="Porsche 911 RSR '17", track="Fuji",
                       layout_id="fc", discipline="Race", gt7_version="1.49", compound="RH")


def _seed(db, at="2026-07-01T10:00"):
    outcome = {"id": "300", "experiment_id": 10, "status": "no_meaningful_change",
               "confidence_level": "high", "scope_fingerprint": "sf",
               "test_session_id": "s1", "protected": [], "failed_directions": []}
    exp = {"id": 10, "scope_fingerprint": "sf",
           "changes": [{"field": "arb_front", "from_value": "5", "to_value": "4"}]}
    residuals = [{"issue_key": "k1", "family": "rotation", "issue_type": "mid_corner_understeer",
                  "axle": "front", "phase": "apex", "segment_id": "T3", "corner_name": "T3",
                  "residual_state": "unchanged", "is_new": False, "is_regression": False,
                  "still_present": True, "protected_good": False, "confidence": "high"}]
    rec = build_development_record(outcome, exp, context=CTX, scope_fingerprint="sf",
                                  working_windows=[], residuals=residuals,
                                  recorded_at=at, session_date=at[:10])
    db._persist_development_record(rec, created_at=rec.recorded_at)


def _kw():
    return dict(car="Porsche 911 RSR '17", track="Fuji", layout_id="fc",
                discipline="Race", driver="leon", gt7_version="1.49", compound="RH")


def test_M_populated_history_production_path(tmp_path):
    p = str(tmp_path / "s.db")
    db = SessionDB(p)
    _seed(db)
    r1 = db.build_intervention_hypotheses(**_kw())
    assert r1["ok"] and r1["count"] >= 1
    # a real diagnosis produced a hypothesis set; no numeric setup values authored
    blob = str(r1).lower()
    import re
    assert not re.search(r"set \w+ to \d", blob)
    db._conn.close()
    # restart determinism
    db2 = SessionDB(p)
    r2 = db2.build_intervention_hypotheses(**_kw())
    assert r2["content_fingerprint"] == r1["content_fingerprint"]
    assert db2._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION == 28
    db2._conn.close()


def test_N_empty_database_safe_and_fast():
    db = SessionDB(":memory:")
    r = db.build_intervention_hypotheses(car="RSR", track="Fuji", discipline="race")
    assert r["ok"] and r["count"] == 0 and r["hypothesis_sets"] == []
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 28
    db.close()
