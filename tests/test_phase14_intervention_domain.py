"""Phase 14 — intervention-hypothesis domain tests.

Direction resolution (sign-graph-derived, final-drive invariant), eligibility gates,
mechanism-to-intervention mapping, expected response, trade-offs, coupled vs single-field,
controlled test design, rendering.
"""
import pytest

from strategy.mechanism_annotation import annotate_diagnosis
from strategy.intervention_hypothesis import (
    InterventionDirection, InterventionHypothesisStatus, InterventionTestKind,
    build_intervention_hypotheses, hypotheses_from_report,
)
from strategy.intervention_hypothesis_render import render_set_sections, render_set_text
from strategy import gearbox_evidence as gbx


def _ann(**o):
    d = {"issue_family": o.pop("fam", "rotation"), "issue_type": o["it"],
         "axle": o.get("axle", ""), "phase": o.get("phase", ""),
         "segment_id": o.get("seg", "T1"), "residual_state": o.get("rs", "unchanged"),
         "recurring": o.get("rec", True), "valid_laps": o.get("vl", 4),
         "sessions_seen": 2, "telemetry_available": True, "key": o.get("key", "k-" + o["it"])}
    return annotate_diagnosis(d, failed_directions=o.get("fd", ()),
                             speed_context=o.get("sc", ""),
                             outcome=o.get("outcome"), decision_state=o.get("ds", ""))


def _all(s):
    return (list(s.testable) + list(s.conditional) + list(s.competing)
            + list(s.blocked) + list(s.preserve_and_observe))


# --- direction resolution ---------------------------------------------------
def test_entry_understeer_softens_front_arb():
    s = build_intervention_hypotheses(_ann(it="entry_understeer", axle="front", phase="entry").to_dict())
    arb = [h for h in s.testable if h["target"]["component"] == "arb_front"]
    assert arb and arb[0]["direction"] == InterventionDirection.SOFTEN.value


def test_direction_derived_from_sign_authority_not_name():
    # mid-corner understeer: soften front ARB (more front grip) — derived from axis authority
    s = build_intervention_hypotheses(_ann(it="mid_corner_understeer", axle="front", phase="apex").to_dict())
    arb = [h for h in s.testable if h["target"]["component"] == "arb_front"]
    assert arb and arb[0]["direction"] == InterventionDirection.SOFTEN.value
    assert "axis authority" in arb[0]["direction_basis"]


def test_final_drive_invariant_semantics():
    # wheelspin + gearbox 'too_short' → LENGTHEN gearing (lower final-drive ratio)
    s = build_intervention_hypotheses(
        _ann(it="wheelspin", axle="rear", phase="exit", fam="traction").to_dict(),
        gearbox_state=gbx.GEARING_TOO_SHORT)
    gear = [h for h in _all(s) if h["target"]["component"] == "transmission"]
    assert gear and gear[0]["direction"] == InterventionDirection.LENGTHEN.value
    assert "longer gearing" in gear[0]["direction_basis"]
    # sanity: the canonical invariant itself
    assert gbx.final_drive_lengthens(4.25, 4.20) is True


def test_lockup_moves_brake_bias_rearward():
    s = build_intervention_hypotheses(
        _ann(it="front_lock", axle="front", phase="braking", fam="braking").to_dict())
    bb = [h for h in _all(s) if h["target"]["component"] == "brake_bias"]
    assert bb and bb[0]["direction"] == InterventionDirection.MOVE_REARWARD.value


# --- eligibility gates ------------------------------------------------------
def test_invalid_annotation_blocks_all():
    a = _ann(it="wheelspin", axle="rear", phase="exit", fam="traction",
             rs="invalid_comparison", ds="invalid")
    s = build_intervention_hypotheses(a.to_dict())
    assert s.overall_status == InterventionHypothesisStatus.BLOCKED_BY_SAFETY_OR_VALIDITY.value
    assert not s.testable


def test_insufficient_annotation_blocks():
    a = _ann(it="mid_corner_understeer", axle="front", phase="apex", rs="not_observed", rec=False)
    s = build_intervention_hypotheses(a.to_dict())
    assert s.overall_status == InterventionHypothesisStatus.INSUFFICIENT_EVIDENCE.value


def test_failed_direction_blocks_that_field():
    s = build_intervention_hypotheses(
        _ann(it="wheelspin", axle="rear", phase="exit", fam="traction",
             fd=[("lsd_accel", "increase", "lockout")]).to_dict())
    lsd = [h for h in s.blocked if h["target"]["component"] == "lsd_accel"]
    assert lsd and lsd[0]["status"] == InterventionHypothesisStatus.BLOCKED_BY_WORKING_WINDOW.value
    assert not [h for h in s.testable if h["target"]["component"] == "lsd_accel"]


def test_driver_technique_out_of_scope():
    s = build_intervention_hypotheses(
        _ann(it="poor_drive_out", axle="rear", phase="exit", fam="drive_out").to_dict())
    tech = [h for h in _all(s) if h["source_mechanism_id"] == "drive_throttle_technique"]
    assert tech and tech[0]["status"] == InterventionHypothesisStatus.OUT_OF_SCOPE.value


# --- competing / aero / gearing ---------------------------------------------
def test_wheelspin_competing_no_auto_lsd():
    s = build_intervention_hypotheses(
        _ann(it="wheelspin", axle="rear", phase="exit", fam="traction").to_dict())
    assert not [h for h in s.testable if h["target"]["component"] == "lsd_accel"]
    assert s.overall_status in ("competing_mechanisms", "insufficient_evidence", "conditional")


def test_aero_requires_speed_context():
    without = build_intervention_hypotheses(
        _ann(it="mid_corner_understeer", axle="front", phase="apex").to_dict())
    aero_w = [h for h in _all(without) if h["target"]["component"] == "aero_front"]
    assert aero_w and aero_w[0]["status"] in ("conditional", "insufficient_evidence")
    assert all(h["target"]["component"] != "aero_front" for h in without.testable)


def test_unknown_and_conflicting_gearbox_no_direction():
    for st in ("", gbx.GEARING_UNKNOWN, gbx.GEARING_CONFLICTING):
        s = build_intervention_hypotheses(
            _ann(it="wrong_gear", axle="rear", phase="exit", fam="gearing").to_dict(),
            gearbox_state=st)
        gear = [h for h in _all(s) if h["target"]["component"] == "transmission"]
        assert gear and gear[0]["direction"] == InterventionDirection.NO_DEFENSIBLE_DIRECTION.value
        assert gear[0]["status"] == InterventionHypothesisStatus.INSUFFICIENT_EVIDENCE.value


# --- coupled vs single-field ------------------------------------------------
def test_default_single_field():
    s = build_intervention_hypotheses(_ann(it="entry_understeer", axle="front", phase="entry").to_dict())
    for h in s.testable:
        assert h["test_design"]["test_kind"] == InterventionTestKind.SINGLE_FIELD.value
        assert h["test_design"]["attributable_to_single_field"] is True


def test_coupled_declares_why_and_caps_fields():
    # a prior coupled improvement enables a paired hypothesis crediting the SET
    a = _ann(it="rear_loose_on_exit", axle="rear", phase="exit", fam="traction")
    s = build_intervention_hypotheses(
        a.to_dict(),
        outcome_history=[{"fields": ["lsd_accel", "springs_rear"],
                          "outcome_status": "confirmed_improvement", "single_field": False}])
    coupled = [h for h in _all(s) if h["test_design"]["test_kind"] == InterventionTestKind.PAIRED_COUPLED.value]
    for h in coupled:
        assert len(h["test_design"]["fields_involved"]) <= 2
        assert h["test_design"]["attributable_to_single_field"] is False
        assert "field SET" in h["prior_outcome_relationship"]


# --- trade-offs / protected good --------------------------------------------
def test_trade_offs_present_and_protected_good_surfaced():
    a = annotate_diagnosis(
        {"issue_family": "rotation", "issue_type": "entry_understeer", "axle": "front",
         "phase": "entry", "segment_id": "T1", "residual_state": "unchanged",
         "recurring": True, "valid_laps": 4, "key": "k"},
        protected_good=[{"behaviour": "braking stability confirmed good"}])
    s = build_intervention_hypotheses(a.to_dict())
    h = s.testable[0]
    assert h["predicted_trade_offs"]
    assert "braking stability confirmed good" in h["protected_good_at_risk"]


# --- controlled test design --------------------------------------------------
def test_test_design_has_no_numeric_values():
    s = build_intervention_hypotheses(_ann(it="entry_understeer", axle="front", phase="entry").to_dict())
    import re
    blob = str(s.to_dict()).lower()
    assert not re.search(r"set \w+ to \d", blob)
    assert not re.search(r"final drive \d\.\d", blob)


# --- rendering ---------------------------------------------------------------
def test_render_sections_and_no_apply():
    s = build_intervention_hypotheses(_ann(it="entry_understeer", axle="front", phase="entry").to_dict())
    titles = [t for t, _ in render_set_sections(s.to_dict())]
    assert "Source observation" in titles
    assert "Safety" in titles
    text = render_set_text(s.to_dict()).lower()
    for banned in ("apply now", "set arb_front to", "the fix is", "guaranteed improvement",
                   "approve"):
        assert banned not in text


def test_report_batch_deterministic():
    a = _ann(it="entry_understeer", axle="front", phase="entry")
    rep = {"ok": True, "annotations": [a.to_dict()]}
    r1 = hypotheses_from_report(rep)
    r2 = hypotheses_from_report(rep)
    assert r1["content_fingerprint"] == r2["content_fingerprint"]
    assert r1["count"] == 1
