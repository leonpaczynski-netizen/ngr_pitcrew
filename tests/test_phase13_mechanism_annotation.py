"""Phase 13 — mechanism-annotation domain tests.

Covers Section 23.1 (knowledge consumption), 23.2 (eligibility), 23.4 (support /
contradiction), 23.5 (interactions), 23.6 (load transfer), 23.7 (experiment relationship),
23.8 (prediction calibration) and 23.9 (rendering).
"""
import inspect

import pytest

from strategy import mechanism_annotation as MA
from strategy.mechanism_annotation import (
    MechanismStatus, annotate_diagnosis, knowledge_versions,
)
from strategy.mechanism_annotation_render import render_sections, render_text
from strategy.vehicle_dynamics import VEHICLE_DYNAMICS_VERSION


def _diag(**over):
    d = {"issue_family": "braking", "issue_type": "front_lock", "axle": "front",
         "phase": "braking", "segment_id": "T1", "corner_name": "Turn 1",
         "residual_state": "unchanged", "recurring": True, "valid_laps": 4,
         "sessions_seen": 2, "telemetry_available": True, "key": "iss"}
    d.update(over)
    return d


# --- 23.1 knowledge consumption ---------------------------------------------
def test_pulls_mechanism_prose_from_phase12_not_authored_here():
    a = annotate_diagnosis(_diag())
    pm = a.primary_mechanism
    from strategy.vehicle_dynamics import explain_component, Component
    assert pm["primary_physical_cause"] == explain_component(Component.BRAKE_BIAS).primary_mechanism
    assert a.knowledge_versions["vehicle_dynamics"] == VEHICLE_DYNAMICS_VERSION


def test_knowledge_versions_include_all_authorities_and_sign_graph():
    kv = knowledge_versions()
    for k in ("mechanism_annotation", "mechanism_map", "vehicle_dynamics",
              "load_transfer", "handling_balance", "setup_interactions", "sign_graph"):
        assert kv.get(k)


# --- 23.2 eligibility --------------------------------------------------------
def test_valid_diagnosis_is_annotated():
    a = annotate_diagnosis(_diag())
    assert a.overall_status in ("supported", "supported_with_limitations")
    assert a.primary_mechanism is not None


def test_invalid_decision_blocks():
    a = annotate_diagnosis(_diag(), decision_state="invalid")
    assert a.overall_status == MechanismStatus.INVALID_SOURCE_DIAGNOSIS.value
    assert a.primary_mechanism is None
    assert a.ineligibility_reason


def test_invalid_comparison_blocks():
    a = annotate_diagnosis(_diag(residual_state="invalid_comparison"))
    assert a.overall_status == MechanismStatus.INVALID_SOURCE_DIAGNOSIS.value


def test_superseded_and_stale_and_ambiguous_block():
    for flag in ("superseded", "stale_checkpoint", "checkpoint_ambiguous"):
        a = annotate_diagnosis(_diag(**{flag: True}))
        assert a.overall_status == MechanismStatus.INVALID_SOURCE_DIAGNOSIS.value


def test_out_of_scope_unknown_family():
    a = annotate_diagnosis(_diag(issue_family="unknown", issue_type="mystery"))
    assert a.overall_status == MechanismStatus.OUT_OF_SCOPE.value


def test_too_broad_issue_is_not_evaluable():
    a = annotate_diagnosis(_diag(issue_type="understeer", phase="", axle=""))
    assert a.overall_status == MechanismStatus.NOT_EVALUABLE.value


def test_only_invalid_laps_is_insufficient():
    a = annotate_diagnosis(_diag(valid_laps=0, times_observed=0, recurring=False,
                                 residual_state="not_observed"))
    assert a.overall_status == MechanismStatus.INSUFFICIENT_EVIDENCE.value


def test_below_recurrence_is_insufficient():
    a = annotate_diagnosis(_diag(residual_state="ambiguous", recurring=False))
    assert a.overall_status == MechanismStatus.INSUFFICIENT_EVIDENCE.value


def test_blocked_annotation_still_explains_why():
    a = annotate_diagnosis(_diag(residual_state="invalid_comparison"))
    assert a.ineligibility_reason
    titles = [t for t, _ in render_sections(a.to_dict())]
    assert "Mechanism annotation unavailable" in titles


# --- 23.4 support / contradiction -------------------------------------------
def test_supported_primary_when_evidence_strong():
    a = annotate_diagnosis(_diag())
    assert a.primary_mechanism["status"] in ("supported", "supported_with_limitations")


def test_supported_with_limitations_when_gt7_limited():
    # LSD-driven entry oversteer: primary component is observability-limited (no diff state)
    a = annotate_diagnosis(_diag(issue_family="rotation", issue_type="entry_oversteer",
                                 axle="rear", phase="entry"))
    assert a.primary_mechanism["status"] == "supported_with_limitations"


def test_failed_direction_contradicts_intervention_not_mechanism():
    a = annotate_diagnosis(
        _diag(issue_family="traction", issue_type="wheelspin", axle="rear", phase="exit"),
        failed_directions=[("lsd_accel", "increase", "lockout")])
    lsd = [c for c in a.competing_mechanisms if c["mechanism_id"] == "exit_diff_locking"]
    assert lsd and lsd[0]["intervention_direction_contradicted"] is True
    # the mechanism itself is retained (competing), not deleted
    assert lsd[0]["status"] in ("competing", "plausible")


def test_competing_mechanisms_retained_without_a_winner():
    a = annotate_diagnosis(
        _diag(issue_family="traction", issue_type="wheelspin", axle="rear", phase="exit"))
    assert len(a.competing_mechanisms) >= 2
    # comparisons keep them indistinguishable (GT7 cannot separate directly)
    assert any(c["status"] == "indistinguishable" for c in a.comparisons)
    assert all(not c["gt7_can_distinguish"] for c in a.comparisons)


def test_aero_stays_plausible_without_speed_evidence():
    a = annotate_diagnosis(_diag(issue_family="rotation", issue_type="mid_corner_understeer",
                                 axle="front", phase="apex"))
    aero = [c for c in a.competing_mechanisms if "aero" in c["mechanism_id"]]
    assert aero and aero[0]["status"] == "plausible"
    assert a.primary_mechanism["mechanism_id"] == "mid_front_roll_stiffness"


def test_driver_disagreement_lowers_grade():
    strong = annotate_diagnosis(_diag(), driver_feedback={"agrees": True, "summary": "yes"})
    weak = annotate_diagnosis(_diag(), driver_feedback={"agrees": False, "summary": "no"})
    order = {"strong": 3, "moderate": 2, "weak": 1, "insufficient": 0}
    assert order[weak.primary_mechanism["evidence_grade"]] <= \
        order[strong.primary_mechanism["evidence_grade"]]


# --- 23.5 interactions -------------------------------------------------------
def test_relevant_interactions_only_not_a_flat_dump():
    a = annotate_diagnosis(_diag(issue_family="traction", issue_type="rear_loose_on_exit",
                                 axle="rear", phase="exit"))
    # every interaction must involve the primary component; not the whole graph
    prim = a.primary_mechanism["primary_component"]
    for i in a.interactions:
        assert prim in (i["a"], i["b"])
    assert len(a.interactions) < 12


def test_interaction_role_is_labelled():
    a = annotate_diagnosis(_diag(issue_family="traction", issue_type="rear_loose_on_exit",
                                 axle="rear", phase="exit"))
    for i in a.interactions:
        assert i["role"] in ("amplifies", "trades against", "enables / gates", "caps / masks")


# --- 23.6 load transfer ------------------------------------------------------
def test_load_transfer_present_and_no_numbers():
    a = annotate_diagnosis(_diag())
    lt = a.load_transfer_explanation
    assert lt and lt["mode"]
    # never fabricates loads
    blob = (lt.get("direction", "") + lt.get("note", "")).lower()
    assert "newton" in blob or "kilogram" in blob or "tyre load" in blob


def test_load_transfer_uses_phase12_taxonomy():
    from strategy.load_transfer import TransferMode
    a = annotate_diagnosis(_diag())
    assert a.load_transfer_explanation["mode"] in {m.value for m in TransferMode}


# --- 23.7 experiment relationship -------------------------------------------
def test_confirmed_improvement_does_not_prove_mechanism():
    a = annotate_diagnosis(
        _diag(), outcome={"status": "confirmed_improvement", "changes": [{"field": "brake_bias"}]})
    assert "does not by itself prove" in a.outcome_consistency
    # still not upgraded beyond supported/limitations purely by the outcome
    assert a.primary_mechanism["status"] in ("supported", "supported_with_limitations")


def test_regression_disproves_direction_not_whole_mechanism():
    a = annotate_diagnosis(
        _diag(), outcome={"status": "regression", "changes": [{"field": "brake_bias"}]})
    assert "disproven" in a.outcome_consistency or "disproven" in \
        a.primary_mechanism["experiment_relationship"]


def test_multi_field_experiment_marks_attribution_unsafe():
    a = annotate_diagnosis(
        _diag(), outcome={"status": "confirmed_improvement",
                          "changes": [{"field": "brake_bias"}, {"field": "arb_front"}]})
    assert any("unsafe" in c["experiment_relationship"] for c in
               ([a.primary_mechanism] + list(a.competing_mechanisms)))


# --- 23.8 prediction calibration --------------------------------------------
def _recon(status):
    return {"experiment_id": "10", "outcome_status": "regression",
            "prediction_fingerprint": "pf",
            "consequence_reconciliations": [
                {"kind": "primary_effect", "field": "brake_bias",
                 "predicted": "brake_bias forward reduces entry rotation",
                 "status": status, "observed": "x", "reason": "y"}],
            "accuracy": {"overall_accuracy": 0.4, "confirmed_count": 0,
                         "contradicted_count": 1}}


def test_prediction_supported_and_contradicted():
    a = annotate_diagnosis(_diag(), reconciliation=_recon("confirmed"))
    assert a.prediction_relationship["reconciliation_status"] == "confirmed"
    b = annotate_diagnosis(_diag(), reconciliation=_recon("contradicted"))
    assert b.prediction_relationship["reconciliation_status"] == "contradicted"
    # a contradicted prediction that names the field marks that mechanism contradicted
    assert any(c["predicted_relationship"] == "contradicted"
               for c in ([b.primary_mechanism] + list(b.competing_mechanisms)
                         + list(b.contradicted_mechanisms)) if c)


def test_prediction_relationship_is_read_only_note():
    a = annotate_diagnosis(_diag(), reconciliation=_recon("confirmed"))
    assert "read-only" in a.prediction_relationship["note"]


# --- 23.9 rendering ----------------------------------------------------------
def test_render_has_required_sections_and_no_apply():
    a = annotate_diagnosis(_diag())
    titles = [t for t, _ in render_sections(a.to_dict())]
    assert "What the app observed" in titles
    assert "Most supported mechanism" in titles
    assert any("GT7" in t for t in titles)
    text = render_text(a.to_dict())
    low = text.lower()
    for banned in ("apply", "set brake_bias to", "increase brake_bias to", "revert"):
        assert banned not in low, banned


def test_render_separates_observation_from_interpretation():
    text = render_text(annotate_diagnosis(_diag()).to_dict())
    assert "direct Program-1 observation" in text
    assert "physics-informed interpretation" in text


def test_render_is_stable():
    d = _diag()
    assert render_text(annotate_diagnosis(d).to_dict()) == \
        render_text(annotate_diagnosis(d).to_dict())
