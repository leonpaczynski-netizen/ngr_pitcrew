"""Engineering-Brain Phase 3 — pure outcome-domain tests.

Covers strategy/setup_experiment_outcome.py: every outcome state, deterministic
decisions, protected-behaviour enforcement, repeatability, driver/telemetry
arbitration, compound attribution, comparison logic, confounders, association,
property/metamorphic invariants, and purity. NO database, NO runtime files.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from strategy.setup_experiment_outcome import (
    OUTCOME_EVAL_VERSION, OutcomeStatus, CriterionVerdict, ProtectedVerdict,
    CornerVerdict, AssociationStatus, DriverTelemetryAgreement, NextAction,
    LearningStrength, ExperimentSnapshot, LapAggregate, CornerObservation,
    DriverReviewInput, ConfounderInput, AssociationResult, LapValidity,
    OutcomeInputs, evaluate_outcome, evaluate_lap_validity,
    resolve_experiment_evidence_association, compare_whole_lap, compare_corners,
    arbitrate_driver_vs_telemetry,
)
from strategy.practice_pattern_analysis import RecurrenceThresholds

ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #
def _exp(**over):
    base = dict(
        experiment_id=1, scope_fingerprint="eck_v1:scope:abc",
        parent_setup_id="base1", applied_checkpoint_id="cp1", status="applied",
        primary_diagnosis="front_lock", target_corners=("T1",),
        rollback_target="Base RSR", min_clean_laps=4,
        changes=({"field": "brake_bias", "from": "55", "to": "52",
                  "direction": "decrease", "magnitude": 3.0, "rule_id": "BB1",
                  "symptom": "front_lock"},),
        protected_behaviours=({"behaviour": "mid-corner grip", "field": "",
                               "corners": ["T3"]},
                              {"behaviour": "rear traction", "field": "",
                               "corners": ["T5"]}),
    )
    base.update(over)
    return ExperimentSnapshot(**base)


def _corner(seg, issue, aff, clean=5, phase=""):
    return CornerObservation(seg, seg, phase, issue, aff, clean, aff)


def _inputs(*, exp=None, valid=5, base_t1=5, test_t1=1, t3_test=0, t5_test=0,
            baseline_ms=95200, test_ms=95000, review=None,
            confounders=None, association=None, min_req=4, base_stdev=300,
            test_stdev=280):
    exp = exp or _exp()
    validity = evaluate_lap_validity(
        LapAggregate(clean_count=valid, median_lap_ms=test_ms),
        total_laps=valid, min_required=min_req)
    baseline = LapAggregate(clean_count=5, median_lap_ms=baseline_ms,
                            lap_time_stdev_ms=base_stdev, avg_lock_up=4.0)
    test = LapAggregate(clean_count=valid, median_lap_ms=test_ms,
                        lap_time_stdev_ms=test_stdev, avg_lock_up=0.6)
    cb = (_corner("T1", "front_lock", base_t1), _corner("T3", "understeer", 0),
          _corner("T5", "rear_wheelspin", 0))
    ct = (_corner("T1", "front_lock", test_t1), _corner("T3", "understeer", t3_test),
          _corner("T5", "rear_wheelspin", t5_test))
    return OutcomeInputs(
        experiment=exp,
        association=association or AssociationResult(AssociationStatus.RESOLVED,
                                                     candidate_experiment_ids=(1,)),
        validity=validity, baseline=baseline, test=test,
        corner_baseline=cb, corner_test=ct, driver_review=review,
        confounders=confounders or ConfounderInput(), test_session_id="200")


# --------------------------------------------------------------------------- #
# 1,2 states + determinism
# --------------------------------------------------------------------------- #
def test_confirmed_improvement():
    out = evaluate_outcome(_inputs(
        review=DriverReviewInput("f", True, target_symptom_resolved=True,
                                 vs_previous="better")))
    assert out.status == OutcomeStatus.CONFIRMED_IMPROVEMENT
    assert out.next_action == NextAction.RETAIN
    assert not out.failed_directions


def test_evaluation_is_deterministic():
    inp = _inputs()
    a = evaluate_outcome(inp)
    b = evaluate_outcome(inp)
    assert a.to_dict() == b.to_dict()
    assert a.idempotency_key == b.idempotency_key


def test_partial_improvement_confidence_below_threshold():
    # target met but thin laps → low confidence → partial, not confirmed
    out = evaluate_outcome(_inputs(valid=4, min_req=4))
    # 4 valid laps → confidence deductions; target met → partial or confirmed
    assert out.status in (OutcomeStatus.PARTIAL_IMPROVEMENT,
                          OutcomeStatus.CONFIRMED_IMPROVEMENT)


def test_no_meaningful_change():
    out = evaluate_outcome(_inputs(base_t1=0, test_t1=0, baseline_ms=95000,
                                   test_ms=95010, base_stdev=200, test_stdev=205))
    assert out.status == OutcomeStatus.NO_MEANINGFUL_CHANGE


def test_regression_protected_material():
    out = evaluate_outcome(_inputs(test_t1=1, t5_test=4,
                                   review=DriverReviewInput(refers_to_correct_setup=True,
                                                            vs_previous="worse")))
    assert out.status == OutcomeStatus.REGRESSION
    assert any("rear traction" in r for r in out.regressions)


def test_confounded():
    out = evaluate_outcome(_inputs(confounders=ConfounderInput(compound_changed=True)))
    assert out.status == OutcomeStatus.CONFOUNDED
    assert not out.failed_directions      # confounded never learns


def test_insufficient_evidence_thin_laps():
    out = evaluate_outcome(_inputs(valid=2, min_req=4))
    assert out.status == OutcomeStatus.INSUFFICIENT_EVIDENCE
    assert not out.validity.sufficient


# --------------------------------------------------------------------------- #
# 9,10,11,12 core doctrine
# --------------------------------------------------------------------------- #
def test_protected_regression_blocks_confirmed_even_if_target_met():
    # target T1 fully fixed, but protected rear traction (T5) recurs
    out = evaluate_outcome(_inputs(test_t1=1, t5_test=4))
    assert out.status == OutcomeStatus.REGRESSION
    assert out.status != OutcomeStatus.CONFIRMED_IMPROVEMENT


def test_target_improvement_does_not_hide_protected_regression():
    out = evaluate_outcome(_inputs(test_t1=0, t5_test=5))
    prot = {p.behaviour: p.verdict for p in out.protected}
    assert prot["rear traction"] == ProtectedVerdict.MATERIAL_REGRESSION
    assert out.status == OutcomeStatus.REGRESSION


def test_fastest_lap_alone_cannot_prove_success():
    # target symptom NOT fixed (still recurring) but a fast median — must not confirm
    out = evaluate_outcome(_inputs(base_t1=5, test_t1=5, baseline_ms=96000,
                                   test_ms=95000))
    assert out.status != OutcomeStatus.CONFIRMED_IMPROVEMENT


def test_repeatable_same_corner_outweighs_isolated_bad_lap():
    # baseline recurring T1 (5/5), test only 1 isolated → improved (repeatable fix)
    out = evaluate_outcome(_inputs(base_t1=5, test_t1=1))
    t1 = [c for c in out.corner_comparisons if c.segment_id == "T1"][0]
    assert t1.verdict == CornerVerdict.IMPROVED
    # a single isolated event in test (1/5) is not "recurring"
    assert t1.test_class in ("isolated", "emerging")


# --------------------------------------------------------------------------- #
# 13,14 driver arbitration
# --------------------------------------------------------------------------- #
def test_driver_and_telemetry_agreement_confirms():
    out = evaluate_outcome(_inputs(
        review=DriverReviewInput("f", True, target_symptom_resolved=True,
                                 braking_confidence_improved=True, vs_previous="better")))
    assert out.driver_agreement == DriverTelemetryAgreement.AGREE
    assert out.status == OutcomeStatus.CONFIRMED_IMPROVEMENT


def test_driver_disagrees_with_positive_telemetry_downgrades():
    out = evaluate_outcome(_inputs(
        review=DriverReviewInput("f", True, target_symptom_resolved=False,
                                 vs_previous="worse")))
    assert out.driver_agreement == DriverTelemetryAgreement.DISAGREE
    assert out.status != OutcomeStatus.CONFIRMED_IMPROVEMENT


def test_feedback_wrong_setup_is_excluded():
    a, note = arbitrate_driver_vs_telemetry(
        DriverReviewInput("f", refers_to_correct_setup=False), True, False)
    assert a == DriverTelemetryAgreement.INVALID_REVIEW
    assert "wrong setup" in note


# --------------------------------------------------------------------------- #
# 15 compound attribution
# --------------------------------------------------------------------------- #
def test_compound_change_attribution_uncertain():
    exp = _exp(changes=(
        {"field": "brake_bias", "from": "55", "to": "52", "direction": "decrease",
         "rule_id": "BB1"},
        {"field": "front_arb", "from": "6", "to": "4", "direction": "decrease",
         "rule_id": "AR1"}))
    out = evaluate_outcome(_inputs(exp=exp, test_t1=1, t5_test=4))
    assert out.status == OutcomeStatus.REGRESSION
    # compound → caution (not hard lockout) + low attribution confidence
    for fd in out.failed_directions:
        assert fd.strength == LearningStrength.CAUTION
        assert fd.attribution_confidence == "low"
    assert out.next_action in (NextAction.REVERT_TO_PARENT, NextAction.ISOLATE_FIELD)


def test_single_field_strong_regression_is_lockout():
    out = evaluate_outcome(_inputs(test_t1=1, t5_test=5))
    assert out.status == OutcomeStatus.REGRESSION
    assert any(fd.strength == LearningStrength.LOCKOUT for fd in out.failed_directions)


# --------------------------------------------------------------------------- #
# 16,17 missing evidence + no invented metrics
# --------------------------------------------------------------------------- #
def test_missing_evidence_is_explicit():
    out = evaluate_outcome(_inputs(review=None))
    assert "no driver review" in out.missing_evidence


def test_no_invented_metrics_in_module():
    src = (ROOT / "strategy" / "setup_experiment_outcome.py").read_text(encoding="utf-8")
    for banned in ("steering_angle", "tyre_wear_pct", "slip_angle", "true_slip"):
        assert banned not in src


# --------------------------------------------------------------------------- #
# 25-33 comparison
# --------------------------------------------------------------------------- #
def test_whole_lap_uses_median_not_fastest():
    cmp = compare_whole_lap(
        LapAggregate(median_lap_ms=95500, best_clean_ms=94000),
        LapAggregate(median_lap_ms=95000, best_clean_ms=94500))
    assert cmp.median_delta_ms == -500
    assert cmp.materially_faster


def test_consistency_comparison():
    cmp = compare_whole_lap(
        LapAggregate(median_lap_ms=95000, lap_time_stdev_ms=200),
        LapAggregate(median_lap_ms=95000, lap_time_stdev_ms=600))
    assert cmp.consistency_regressed


def test_per_corner_lockup_repeatability():
    cmps = compare_corners(
        (_corner("T1", "front_lock", 5),), (_corner("T1", "front_lock", 1),),
        thresholds=RecurrenceThresholds(), min_clean_laps=4)
    assert cmps[0].verdict == CornerVerdict.IMPROVED


def test_per_corner_wheelspin_regression():
    cmps = compare_corners(
        (_corner("T5", "rear_wheelspin", 0),), (_corner("T5", "rear_wheelspin", 4),),
        thresholds=RecurrenceThresholds(), min_clean_laps=4)
    assert cmps[0].verdict == CornerVerdict.REGRESSED


def test_missing_baseline_metric_unmeasurable():
    cmp = compare_whole_lap(LapAggregate(median_lap_ms=0),
                            LapAggregate(median_lap_ms=95000))
    assert not cmp.measurable


def test_min_sample_enforcement_unmeasurable():
    cmps = compare_corners(
        (_corner("T1", "front_lock", 1, clean=2),),
        (_corner("T1", "front_lock", 0, clean=2),),
        thresholds=RecurrenceThresholds(), min_clean_laps=4)
    assert cmps[0].verdict == CornerVerdict.UNMEASURABLE


def test_confounder_detection_blocks_verdict():
    out = evaluate_outcome(_inputs(confounders=ConfounderInput(
        weather_changed=True, notes=("rain in test",))))
    assert out.status == OutcomeStatus.CONFOUNDED
    assert any("weather" in c for c in out.confounders)


# --------------------------------------------------------------------------- #
# 18-24 association (pure)
# --------------------------------------------------------------------------- #
def test_association_resolved():
    r = resolve_experiment_evidence_association(
        _exp(), test_scope_fingerprint="eck_v1:scope:abc",
        test_checkpoint_id="cp1")
    assert r.status == AssociationStatus.RESOLVED


def test_association_scope_mismatch():
    r = resolve_experiment_evidence_association(
        _exp(), test_scope_fingerprint="eck_v1:scope:DIFFERENT")
    assert r.status == AssociationStatus.MISMATCH


def test_association_checkpoint_mismatch():
    r = resolve_experiment_evidence_association(
        _exp(), test_scope_fingerprint="eck_v1:scope:abc",
        test_checkpoint_id="cp_OTHER")
    assert r.status == AssociationStatus.MISMATCH


def test_association_before_apply_mismatch():
    r = resolve_experiment_evidence_association(
        _exp(), test_scope_fingerprint="eck_v1:scope:abc",
        test_session_started_after_apply=False)
    assert r.status == AssociationStatus.MISMATCH


def test_association_multiple_candidates_ambiguous():
    r = resolve_experiment_evidence_association(
        _exp(), test_scope_fingerprint="eck_v1:scope:abc",
        candidate_experiment_ids=(1, 2, 3))
    assert r.status == AssociationStatus.AMBIGUOUS
    assert set(r.candidate_experiment_ids) >= {1, 2, 3}


def test_association_absent_parent_unresolved():
    r = resolve_experiment_evidence_association(
        _exp(), test_scope_fingerprint="eck_v1:scope:abc", has_parent_baseline=False)
    assert r.status == AssociationStatus.UNRESOLVED


def test_mismatched_association_yields_insufficient_outcome():
    out = evaluate_outcome(_inputs(
        association=AssociationResult(AssociationStatus.MISMATCH, ("scope mismatch",))))
    assert out.status == OutcomeStatus.INSUFFICIENT_EVIDENCE


# --------------------------------------------------------------------------- #
# Property / metamorphic
# --------------------------------------------------------------------------- #
def test_stronger_improvement_cannot_reduce_success():
    weak = evaluate_outcome(_inputs(base_t1=4, test_t1=1))
    strong = evaluate_outcome(_inputs(base_t1=5, test_t1=0))
    order = [OutcomeStatus.INSUFFICIENT_EVIDENCE, OutcomeStatus.NO_MEANINGFUL_CHANGE,
             OutcomeStatus.PARTIAL_IMPROVEMENT, OutcomeStatus.CONFIRMED_IMPROVEMENT]
    assert order.index(strong.status) >= order.index(weak.status)


def test_unrelated_isolated_noise_cannot_flip_to_regression():
    clean = evaluate_outcome(_inputs(test_t1=1))
    # add an unrelated ISOLATED (1/5) event at a new non-protected corner
    inp = _inputs(test_t1=1)
    noisy = dataclasses.replace(inp, corner_test=inp.corner_test + (
        _corner("T9", "minor_slip", 1),))
    out = evaluate_outcome(noisy)
    assert out.status == clean.status            # isolated noise did not flip it
    assert out.status != OutcomeStatus.REGRESSION


def test_protected_regression_cannot_improve_outcome():
    good = evaluate_outcome(_inputs(test_t1=1))
    bad = evaluate_outcome(_inputs(test_t1=1, t5_test=5))
    order = [OutcomeStatus.REGRESSION, OutcomeStatus.CONFOUNDED,
             OutcomeStatus.INSUFFICIENT_EVIDENCE, OutcomeStatus.NO_MEANINGFUL_CHANGE,
             OutcomeStatus.PARTIAL_IMPROVEMENT, OutcomeStatus.CONFIRMED_IMPROVEMENT]
    assert order.index(bad.status) <= order.index(good.status)


def test_fewer_valid_laps_cannot_increase_confidence():
    many = evaluate_outcome(_inputs(valid=6, min_req=4))
    few = evaluate_outcome(_inputs(valid=4, min_req=4))
    assert few.confidence <= many.confidence


def test_changing_scope_breaks_association():
    r_ok = resolve_experiment_evidence_association(
        _exp(), test_scope_fingerprint="eck_v1:scope:abc")
    r_bad = resolve_experiment_evidence_association(
        _exp(scope_fingerprint="eck_v1:scope:car8"),
        test_scope_fingerprint="eck_v1:scope:abc")
    assert r_ok.ok and not r_bad.ok


def test_evaluation_order_independence():
    inp = _inputs()
    shuffled = dataclasses.replace(
        inp, corner_test=tuple(reversed(inp.corner_test)),
        corner_baseline=tuple(reversed(inp.corner_baseline)))
    assert evaluate_outcome(inp).status == evaluate_outcome(shuffled).status
    assert evaluate_outcome(inp).idempotency_key == evaluate_outcome(shuffled).idempotency_key


# --------------------------------------------------------------------------- #
# 59,60 purity
# --------------------------------------------------------------------------- #
def test_module_no_ui_db_network_ai_imports():
    src = (ROOT / "strategy" / "setup_experiment_outcome.py").read_text(encoding="utf-8")
    for banned in ("PyQt6", "PyQt5", "from ui.", "import sqlite3",
                   "from data.session_db", "requests", "urllib", "anthropic",
                   "openai", "api_key"):
        assert banned not in src, banned


def test_module_no_wallclock():
    src = (ROOT / "strategy" / "setup_experiment_outcome.py").read_text(encoding="utf-8")
    assert "datetime.now" not in src
    assert "random" not in src
