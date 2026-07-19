"""Phase 13 — golden UAT scenarios A–L (Section 22).

Scenarios A–K exercise the pure annotator through the production-domain vocabulary;
L (restart determinism) and the DB end-to-end exercise the real SessionDB production path
that folds immutable records into canonical diagnoses and annotates them.
"""
import pytest

from data.session_db import SessionDB
from strategy._setup_constants import DB_VERSION
from strategy.development_history import MemoryContextKey, build_development_record
from strategy.mechanism_annotation import MechanismStatus, annotate_diagnosis


# --------------------------------------------------------------------------- #
# Scenario A — front lockup under braking (Porsche 911 RSR '17 @ Fuji)
# --------------------------------------------------------------------------- #
def test_scenario_A_front_lockup():
    a = annotate_diagnosis(
        {"issue_family": "braking", "issue_type": "front_lock", "axle": "front",
         "phase": "braking", "segment_id": "T1", "residual_state": "unchanged",
         "recurring": True, "valid_laps": 4, "key": "A"},
        context={"car": "Porsche 911 RSR '17", "track": "Fuji International Speedway"})
    assert a.overall_status in ("supported", "supported_with_limitations")
    assert a.load_transfer_explanation["mode"] == "longitudinal"
    # front longitudinal grip demand is the primary; no brake-balance VALUE recommended
    assert a.primary_mechanism["primary_component"] == "brake_bias"
    assert "individual tyre load" in " ".join(a.gt7_limitations).lower()
    txt = " ".join(l for _, ls in [] for l in ls)  # noqa: F841
    # secondary interactions constrained to Phase-12 knowledge (all involve the primary)
    for i in a.interactions:
        assert "brake_bias" in (i["a"], i["b"])


# --------------------------------------------------------------------------- #
# Scenario B — rear instability under trail braking, confirmed-good rotation
# --------------------------------------------------------------------------- #
def test_scenario_B_rear_trail_braking_instability():
    a = annotate_diagnosis(
        {"issue_family": "braking", "issue_type": "rear_loose_under_braking", "axle": "rear",
         "phase": "braking", "segment_id": "T3", "residual_state": "unchanged",
         "recurring": True, "valid_laps": 4, "key": "B"},
        protected_good=[{"behaviour": "entry rotation confirmed good"}])
    assert a.load_transfer_explanation["mode"] == "combined"
    assert "entry rotation confirmed good" in a.protected_good_behaviours
    # not reduced to one universal setting rule — multiple supported/competing mechanisms
    assert (a.primary_mechanism is not None) or a.competing_mechanisms


# --------------------------------------------------------------------------- #
# Scenario C — mid-corner understeer, aero not promoted without speed evidence
# --------------------------------------------------------------------------- #
def test_scenario_C_mid_corner_understeer():
    a = annotate_diagnosis(
        {"issue_family": "rotation", "issue_type": "mid_corner_understeer", "axle": "front",
         "phase": "apex", "residual_state": "unchanged", "recurring": True,
         "valid_laps": 4, "key": "C"})
    assert a.handling_phases == ("mid_corner",)
    assert a.primary_mechanism["mechanism_id"] == "mid_front_roll_stiffness"
    aero = [c for c in a.competing_mechanisms if "aero" in c["mechanism_id"]]
    assert aero and aero[0]["status"] == "plausible"     # not primary without speed evidence


# --------------------------------------------------------------------------- #
# Scenario D — exit wheelspin with a prior failed LSD direction + lockout
# --------------------------------------------------------------------------- #
def test_scenario_D_exit_wheelspin_failed_lsd():
    a = annotate_diagnosis(
        {"issue_family": "traction", "issue_type": "wheelspin", "axle": "rear",
         "phase": "exit", "segment_id": "T4", "residual_state": "worsened",
         "recurring": True, "valid_laps": 4, "key": "D"},
        failed_directions=[("lsd_accel", "increase", "lockout")],
        outcome={"status": "regression", "changes": [{"field": "lsd_accel"}]})
    # driven-wheel traction demand is the primary explanation, NOT an automatic LSD cure
    assert a.primary_mechanism["mechanism_id"] == "exit_traction_demand"
    lsd = [c for c in a.competing_mechanisms if c["mechanism_id"] == "exit_diff_locking"]
    assert lsd and lsd[0]["intervention_direction_contradicted"] is True
    # gear + rear-load remain competing
    ids = {c["mechanism_id"] for c in a.competing_mechanisms}
    assert "exit_gear_selection" in ids and "exit_rear_load" in ids
    # Phase 13 recommends no LSD increase — it authors nothing at all
    txt = a.to_dict()
    assert "increase lsd" not in str(txt).lower()


# --------------------------------------------------------------------------- #
# Scenario E — poor drive out caused by wrong gear
# --------------------------------------------------------------------------- #
def test_scenario_E_poor_drive_out_wrong_gear():
    a = annotate_diagnosis(
        {"issue_family": "drive_out", "issue_type": "poor_drive_out", "axle": "rear",
         "phase": "exit", "residual_state": "unchanged", "recurring": True,
         "valid_laps": 4, "key": "E"})
    assert a.primary_mechanism["mechanism_id"] == "drive_gear_torque"
    # LSD / suspension not promoted; engine-torque limit stated; no shift RPM fabricated
    assert any("engine torque" in g.lower() for g in a.gt7_limitations)
    assert "rpm" not in a.primary_mechanism["primary_physical_cause"].lower() or \
        "optimal shift rpm" in " ".join(a.gt7_limitations).lower()


# --------------------------------------------------------------------------- #
# Scenario F — high-speed understeer, uncertain aero attribution
# --------------------------------------------------------------------------- #
def test_scenario_F_high_speed_aero_uncertain():
    a = annotate_diagnosis(
        {"issue_family": "rotation", "issue_type": "understeer", "axle": "front",
         "phase": "", "residual_state": "unchanged", "recurring": True,
         "valid_laps": 4, "key": "F"},
        speed_context="high_speed")
    assert a.overall_status in ("competing", "plausible")
    # aero cannot be declared proven; mechanical/platform mechanisms remain visible
    assert not any(c["mechanism_id"].startswith("mid_aero") and c["status"] == "supported"
                   for c in a.competing_mechanisms)
    assert a.primary_mechanism is None
    assert a.required_discriminating_evidence


# --------------------------------------------------------------------------- #
# Scenario G — kerb instability
# --------------------------------------------------------------------------- #
def test_scenario_G_kerb_instability():
    a = annotate_diagnosis(
        {"issue_family": "platform", "issue_type": "kerb", "axle": "", "phase": "apex",
         "residual_state": "unchanged", "recurring": True, "valid_laps": 4, "key": "G"})
    assert a.load_transfer_explanation["mode"] == "platform"
    gt7 = " ".join(a.gt7_limitations).lower()
    assert "damper velocity" in gt7 and "suspension travel" in gt7
    # not asserted as proven over-stiff damping — the mechanism is transient/platform
    assert a.primary_mechanism is None or \
        a.primary_mechanism["mechanism_id"] == "kerb_transient_platform"


# --------------------------------------------------------------------------- #
# Scenario H — outcome improved but mechanism uncertain
# --------------------------------------------------------------------------- #
def test_scenario_H_improved_but_uncertain():
    a = annotate_diagnosis(
        {"issue_family": "traction", "issue_type": "wheelspin", "axle": "rear",
         "phase": "exit", "residual_state": "improved_but_present", "recurring": True,
         "valid_laps": 4, "key": "H"},
        outcome={"status": "confirmed_improvement",
                 "changes": [{"field": "lsd_accel"}, {"field": "springs_rear"}]})
    assert "does not by itself prove" in a.outcome_consistency
    # multiple mechanisms remain competing; missing discriminators listed
    assert len(a.competing_mechanisms) >= 1
    assert a.required_discriminating_evidence


# --------------------------------------------------------------------------- #
# Scenario I — prediction mechanism contradicted
# --------------------------------------------------------------------------- #
def test_scenario_I_prediction_contradicted():
    recon = {"experiment_id": "10", "prediction_fingerprint": "pf",
             "consequence_reconciliations": [
                 {"kind": "primary_effect", "field": "brake_bias",
                  "predicted": "brake_bias forward stabilises braking",
                  "status": "contradicted", "observed": "worse", "reason": "z"}],
             "accuracy": {"overall_accuracy": 0.3}}
    a = annotate_diagnosis(
        {"issue_family": "braking", "issue_type": "front_lock", "axle": "front",
         "phase": "braking", "residual_state": "worsened", "recurring": True,
         "valid_laps": 4, "key": "I"}, reconciliation=recon)
    assert a.prediction_relationship["reconciliation_status"] == "contradicted"
    assert a.prediction_relationship["predicted"]
    assert a.prediction_relationship["observed"]
    # existing calibration is authoritative — we only reference it
    assert "read-only" in a.prediction_relationship["note"]


# --------------------------------------------------------------------------- #
# Scenario J — invalid diagnosis
# --------------------------------------------------------------------------- #
def test_scenario_J_invalid_diagnosis():
    a = annotate_diagnosis(
        {"issue_family": "traction", "issue_type": "wheelspin", "axle": "rear",
         "phase": "exit", "residual_state": "invalid_comparison", "key": "J"},
        decision_state="invalid")
    assert a.overall_status == MechanismStatus.INVALID_SOURCE_DIAGNOSIS.value
    assert a.primary_mechanism is None
    assert a.ineligibility_reason


# --------------------------------------------------------------------------- #
# Scenario K — same symptom, different phase → different annotation
# --------------------------------------------------------------------------- #
def test_scenario_K_same_symptom_different_phase():
    base = {"issue_family": "rotation", "issue_type": "understeer", "axle": "front",
            "residual_state": "unchanged", "recurring": True, "valid_laps": 4}
    entry = annotate_diagnosis({**base, "phase": "entry", "key": "K-entry"})
    exit_ = annotate_diagnosis({**base, "phase": "exit", "key": "K-exit"})
    assert entry.handling_phases != exit_.handling_phases
    assert entry.content_fingerprint != exit_.content_fingerprint


# --------------------------------------------------------------------------- #
# Scenario L — restart determinism through the REAL SessionDB production path
# --------------------------------------------------------------------------- #
CTX = MemoryContextKey(driver="leon", car="Porsche 911 RSR '17", track="Fuji",
                       layout_id="fc", discipline="Race", gt7_version="1.49", compound="RH")


def _residual(issue_type, axle, phase, state="unchanged"):
    return {"issue_key": f"k-{issue_type}", "family": "traction" if "wheelspin" in issue_type
            else "braking", "issue_type": issue_type, "axle": axle, "phase": phase,
            "segment_id": "T4", "corner_name": "Turn 4", "residual_state": state,
            "is_new": False, "is_regression": state in ("worsened", "new"),
            "still_present": True, "protected_good": False, "confidence": "high"}


def _seed(db, at="2026-07-01T10:00"):
    outcome = {"id": "300", "experiment_id": 10, "status": "no_meaningful_change",
               "confidence_level": "high", "scope_fingerprint": "sf",
               "test_session_id": "s1", "protected": [], "failed_directions": []}
    exp = {"id": 10, "scope_fingerprint": "sf",
           "changes": [{"field": "lsd_accel", "from_value": "20", "to_value": "22"}]}
    rec = build_development_record(
        outcome, exp, context=CTX, scope_fingerprint="sf", working_windows=[],
        residuals=[_residual("wheelspin", "rear", "exit"),
                   _residual("front_lock", "front", "braking")],
        recorded_at=at, session_date=at[:10])
    db._persist_development_record(rec, created_at=rec.recorded_at)


def _ctx_kwargs():
    return dict(car="Porsche 911 RSR '17", track="Fuji", layout_id="fc",
                discipline="Race", driver="leon", gt7_version="1.49", compound="RH")


def test_scenario_L_db_production_path_and_restart_determinism(tmp_path):
    p = str(tmp_path / "s.db")
    db = SessionDB(p)
    _seed(db)
    r1 = db.build_mechanism_annotations(**_ctx_kwargs())
    assert r1["ok"] and r1["count"] >= 1
    ids = {a["canonical_issue"]["issue_type"] for a in r1["annotations"]}
    assert "wheelspin" in ids   # a real canonical diagnosis was annotated
    db._conn.close()

    # restart: reopen the same DB, rebuild — byte-identical annotation report
    db2 = SessionDB(p)
    r2 = db2.build_mechanism_annotations(**_ctx_kwargs())
    assert r2["content_fingerprint"] == r1["content_fingerprint"]
    assert [a["content_fingerprint"] for a in r2["annotations"]] == \
           [a["content_fingerprint"] for a in r1["annotations"]]
    assert db2._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION == 26
    db2._conn.close()
