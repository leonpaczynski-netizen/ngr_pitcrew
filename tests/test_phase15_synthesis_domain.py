"""Phase 15 — bounded experiment synthesis domain tests.

Baseline authority, minimum-effective legal step, single-field isolation, coupled,
legality/quantisation, direction sign (incl. final-drive invariant), rendering.
"""
import pytest

from strategy.mechanism_annotation import annotate_diagnosis
from strategy.intervention_hypothesis import build_intervention_hypotheses as BIH
from strategy.experiment_synthesis import (
    ExperimentSynthesisStatus as ST, InterventionTestKind,
    build_baseline_reference, synthesize_bounded_experiments as SYN,
    synthesize_from_report,
)
from strategy.experiment_synthesis_render import render_result_sections, render_result_text
from strategy.setup_ranges import resolve_ranges
from strategy import gearbox_evidence as gbx
from data.applied_checkpoint import compute_setup_hash

RANGES = dict(resolve_ranges("Porsche 911 RSR"))
RANGES["final_drive"] = (3.0, 5.0)
IDENT = {"car": "Porsche 911 RSR", "track": "Fuji", "layout_id": "fc"}
FIELDS = {"arb_front": 4, "arb_rear": 4, "brake_bias": 0, "springs_front": 5.0,
          "springs_rear": 5.0, "lsd_accel": 20, "lsd_decel": 20, "lsd_initial": 10,
          "aero_front": 300, "aero_rear": 400, "camber_front": -3.0, "camber_rear": -2.0,
          "toe_front": 0.10, "toe_rear": 0.20, "ride_height_front": 70,
          "ride_height_rear": 75, "final_drive": 4.100}


def applied(fields=None, car="Porsche 911 RSR", track="Fuji", layout="fc", state="applied"):
    f = dict(fields if fields is not None else FIELDS)
    d = {"car": car, "track": track, "layout_id": layout, "setup_id": "S1", "name": "Base",
         "revision": 1, "state": state, "fields": f, "purpose": "Race"}
    d["setup_hash"] = compute_setup_hash(f)
    return d


def ann(it, fam="rotation", axle="", phase="", **kw):
    d = {"issue_family": fam, "issue_type": it, "axle": axle, "phase": phase,
         "segment_id": "T1", "residual_state": "unchanged", "recurring": True,
         "valid_laps": 4, "sessions_seen": 2, "telemetry_available": True, "key": "k-" + it}
    return annotate_diagnosis(d, failed_directions=kw.get("fd", ()),
                             protected_good=kw.get("pg", ()), speed_context=kw.get("sc", ""))


def syn(it, fam="rotation", axle="", phase="", applied_setup=None, gearbox_state="", **kw):
    hs = BIH(ann(it, fam, axle, phase, **kw).to_dict(), gearbox_state=gearbox_state,
             speed_context=kw.get("sc", ""))
    return SYN(hs.to_dict(), applied_setup=applied_setup if applied_setup is not None else applied(),
               session_identity=IDENT, ranges=RANGES, gearbox_state=gearbox_state,
               larger_step_justifications=kw.get("just"))


def _all(r):
    return ([r.selected_candidate] if r.selected_candidate else []) + list(r.alternative_candidates)


# --- baseline authority -----------------------------------------------------
def test_baseline_defaults_to_applied_setup():
    b = build_baseline_reference(applied(), session_identity=IDENT)
    assert b.is_valid_baseline and b.is_active_on_car and b.identity_matches
    assert b.setup_hash == compute_setup_hash(FIELDS)


def test_baseline_missing_blocks():
    b = build_baseline_reference(None, session_identity=IDENT)
    assert not b.is_valid_baseline and b.block_reason == "no_active_setup"


def test_baseline_mismatch_blocks():
    b = build_baseline_reference(applied(car="Mazda"), session_identity=IDENT)
    assert not b.is_valid_baseline and b.block_reason == "identity_mismatch"


def test_baseline_not_applied_blocks():
    b = build_baseline_reference(applied(state="proposed"), session_identity=IDENT)
    assert not b.is_valid_baseline and b.block_reason == "not_applied"


def test_baseline_drift_blocks():
    a = applied()
    a["setup_hash"] = "tampered"          # snapshot hash no longer matches fields
    b = build_baseline_reference(a, session_identity=IDENT)
    assert not b.is_valid_baseline and b.block_reason == "baseline_drift"


# --- minimum-effective step -------------------------------------------------
def test_single_field_one_legal_step():
    r = syn("entry_understeer", axle="front", phase="entry")
    sc = r.selected_candidate
    assert sc and len(sc["deltas"]) == 1
    d = sc["deltas"][0]
    assert d["field"] == "arb_front" and d["direction"] == "soften"
    assert d["candidate_value"] == 3 and d["is_exactly_one_step"] and not d["larger_step_used"]
    assert sc["unchanged_field_count"] == len(FIELDS) - 1


def test_all_unrelated_fields_preserved():
    r = syn("entry_understeer", axle="front", phase="entry")
    changed = {d["field"] for d in r.selected_candidate["deltas"]}
    assert changed == {"arb_front"}


def test_larger_step_requires_justification_and_reverts():
    base = syn("entry_understeer", axle="front", phase="entry")
    just = {"arb_front": {"reason": "current_value_in_dead_band", "steps": 2}}
    bigger = syn("entry_understeer", axle="front", phase="entry", just=just)
    d0 = base.selected_candidate["deltas"][0]
    d1 = bigger.selected_candidate["deltas"][0]
    assert d0["is_exactly_one_step"] and abs(d0["delta"]) == 1
    assert d1["larger_step_used"] and abs(d1["delta"]) == 2 and d1["larger_step_reason"]
    # removing the justification restores the one-step result
    assert syn("entry_understeer", axle="front", phase="entry").content_fingerprint == \
        base.content_fingerprint


def test_illegal_step_produces_no_candidate_no_clamp():
    f = dict(FIELDS); f["brake_bias"] = 5   # at legal max (-5,5)
    r = syn("front_lock", fam="braking", axle="front", phase="braking", applied_setup=applied(f))
    assert not [c for c in _all(r) if c and c["deltas"][0]["field"] == "brake_bias"]
    assert r.overall_status == ST.BLOCKED_BY_LEGALITY.value


# --- direction sign / final-drive invariant ---------------------------------
def test_final_drive_invariant_shorten_is_higher_ratio():
    r = syn("gearing_too_long", fam="gearing", axle="rear", gearbox_state=gbx.GEARING_TOO_LONG)
    fd = [c for c in _all(r) if c and c["deltas"][0]["field"] == "final_drive"][0]
    d = fd["deltas"][0]
    assert d["direction"] == "shorten" and d["candidate_value"] > d["baseline_value"]


def test_unknown_gearbox_no_gearing_candidate():
    r = syn("wrong_gear", fam="gearing", axle="rear", phase="exit", gearbox_state="unknown")
    assert not [c for c in _all(r) if c and c["deltas"][0]["field"] == "final_drive"]


# --- eligibility ------------------------------------------------------------
def test_blocked_hypothesis_no_numeric():
    r = syn("wheelspin", fam="traction", axle="rear", phase="exit",
            fd=[("lsd_accel", "increase", "lockout")])
    assert not [c for c in _all(r) if c and c["deltas"][0]["field"] == "lsd_accel"]


def test_out_of_scope_component_rejected():
    # 'tyres' component maps to no tunable field
    hset = {"canonical_issue": {"issue_type": "tyre_deg"}, "content_fingerprint": "fp",
            "testable": [{"hypothesis_id": "h", "source_mechanism_id": "m", "status": "testable",
                          "direction": "increase", "evidence_grade": "moderate",
                          "target": {"component": "tyres", "handling_phase": "mid_corner"},
                          "expected_response": {}, "predicted_trade_offs": [],
                          "protected_good_at_risk": [], "rejection_criteria": [], "test_design": {}}],
            "conditional": [], "competing": [], "blocked": [], "preserve_and_observe": []}
    r = SYN(hset, applied_setup=applied(), session_identity=IDENT, ranges=RANGES)
    assert any(x["status"] == ST.OUT_OF_SCOPE.value for x in r.rejected)


# --- coupled ----------------------------------------------------------------
def test_coupled_hypothesis_requires_coupled_status():
    hset = {"canonical_issue": {"issue_type": "rear_loose_on_exit"}, "content_fingerprint": "fp",
            "testable": [{"hypothesis_id": "h", "source_mechanism_id": "m", "status": "testable",
                          "direction": "increase_locking", "evidence_grade": "moderate",
                          "target": {"component": "lsd_accel", "handling_phase": "exit_traction"},
                          "expected_response": {"predicted_benefit": "x"}, "predicted_trade_offs": [],
                          "protected_good_at_risk": [], "rejection_criteria": [],
                          "test_design": {"test_kind": InterventionTestKind.PAIRED_COUPLED.value}}],
            "conditional": [], "competing": [], "blocked": [], "preserve_and_observe": []}
    r = SYN(hset, applied_setup=applied(), session_identity=IDENT, ranges=RANGES)
    cands = _all(r)
    assert cands and cands[0]["status"] == ST.REQUIRES_COUPLED_EXPERIMENT.value
    assert cands[0]["attribution_scope"] == "coupled_pair"


# --- rendering --------------------------------------------------------------
def test_render_distinguishes_baseline_and_candidate_no_apply():
    r = syn("entry_understeer", axle="front", phase="entry")
    text = render_result_text(r.to_dict())
    assert "BASELINE" in text and "CANDIDATE" in text
    low = text.lower()
    for banned in ("apply now", "is optimal", "optimal setup", "optimal value",
                   "the fix is", "guaranteed"):
        assert banned not in low
    assert "canonical apply gate" in low


def test_render_has_baseline_and_safety_sections():
    r = syn("entry_understeer", axle="front", phase="entry")
    titles = [t for t, _ in render_result_sections(r.to_dict())]
    assert "Canonical applied baseline" in titles and "Safety" in titles


# --- batch determinism ------------------------------------------------------
def test_batch_report_deterministic():
    hs = BIH(ann("entry_understeer", axle="front", phase="entry").to_dict())
    rep = {"ok": True, "hypothesis_sets": [hs.to_dict()]}
    r1 = synthesize_from_report(rep, applied_setup=applied(), session_identity=IDENT, ranges=RANGES)
    r2 = synthesize_from_report(rep, applied_setup=applied(), session_identity=IDENT, ranges=RANGES)
    assert r1["content_fingerprint"] == r2["content_fingerprint"] and r1["count"] == 1
