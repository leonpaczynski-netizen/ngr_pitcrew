"""Phase 16 — guarded experiment lifecycle domain tests.

Lifecycle creation, traceability, preflight/apply/outcome/reconciliation/prediction routing,
fingerprint preservation, determinism, rendering.
"""
import copy

import pytest

from strategy.mechanism_annotation import annotate_diagnosis
from strategy.intervention_hypothesis import build_intervention_hypotheses as BIH
from strategy.experiment_synthesis import synthesize_bounded_experiments as SYN
from strategy.experiment_lifecycle import (
    ExperimentLifecycleState as LS, LifecycleTrace,
    assemble_execution_result, assemble_lifecycle_summary, build_execution_request,
)
from strategy.experiment_lifecycle_render import render_summary_sections, render_summary_text
from strategy.setup_ranges import resolve_ranges
from data.applied_checkpoint import compute_setup_hash

RANGES = resolve_ranges("Porsche 911 RSR")
IDENT = {"car": "Porsche 911 RSR", "track": "Fuji", "layout_id": "fc"}
FIELDS = {"arb_front": 4, "arb_rear": 4, "brake_bias": 0, "springs_front": 5.0, "lsd_accel": 20}


def applied():
    d = {"car": "Porsche 911 RSR", "track": "Fuji", "layout_id": "fc", "setup_id": "S1",
         "name": "Base", "revision": 1, "state": "applied", "fields": dict(FIELDS),
         "purpose": "Race"}
    d["setup_hash"] = compute_setup_hash(FIELDS)
    return d


def _candidate(it="entry_understeer", axle="front", phase="entry", key="diag-1"):
    a = annotate_diagnosis({"issue_family": "rotation", "issue_type": it, "axle": axle,
                            "phase": phase, "segment_id": "T1", "residual_state": "unchanged",
                            "recurring": True, "valid_laps": 4, "sessions_seen": 2,
                            "telemetry_available": True, "key": key})
    hs = BIH(a.to_dict())
    res = SYN(hs.to_dict(), applied_setup=applied(), session_identity=IDENT, ranges=RANGES)
    return res.selected_candidate, a.to_dict(), hs.to_dict()


SCOPE = {"track": "Fuji", "layout_id": "fc", "discipline": "Race", "issue_type": "entry_understeer"}


# --- lifecycle creation -----------------------------------------------------
def test_ready_candidate_builds_canonical_experiment():
    cand, _, _ = _candidate()
    req = build_execution_request(cand, diagnosis_key="diag-1", scope=SCOPE)
    assert req.actionable and req.setup_experiment is not None
    # the canonical experiment is a real SetupExperiment (draft), not a duplicate model
    assert req.setup_experiment["schema_version"] == "setup_experiment_v1"
    assert req.setup_experiment["status"] == "draft"
    # exactly the synthesised change is carried
    changes = req.setup_experiment["changes"]
    assert len(changes) == 1 and changes[0]["field"] == "arb_front"


def test_non_ready_candidate_not_actionable():
    for c in ({"status": "conditional", "deltas": [{"field": "x"}]},
              {"status": "ready_for_preflight", "deltas": []}, {}):
        req = build_execution_request(c, scope=SCOPE)
        assert not req.actionable and req.setup_experiment is None


# --- traceability -----------------------------------------------------------
def test_full_traceability_chain():
    cand, ann, hs = _candidate()
    req = build_execution_request(cand, diagnosis_key="diag-1", scope=SCOPE)
    t = req.trace
    assert t.diagnosis_key == "diag-1"
    assert t.mechanism_ids and t.hypothesis_ids and t.synthesis_candidate_id
    assert t.baseline_setup_hash == compute_setup_hash(FIELDS)
    assert t.is_unbroken_to("synthesis") is True
    # summary continues the chain through experiment/outcome/reconciliation
    summ = assemble_lifecycle_summary(
        candidate=cand, annotation=ann, hypothesis_set=hs,
        experiment={"id": "42", "status": "completed", "idempotency_key": "idk"},
        outcome={"id": "7", "status": "confirmed_improvement"},
        reconciliation={"record_key": "rk", "prediction_fingerprint": "pf"},
        calibration={"reconciliations": 1, "overall_accuracy": 0.8}, diagnosis_key="diag-1")
    assert summ.trace.is_unbroken_to("reconciliation") is True


def test_trace_never_blanks_existing_link():
    t = LifecycleTrace(diagnosis_key="d", hypothesis_ids=("h",))
    from strategy.experiment_lifecycle import _with
    t2 = _with(t, diagnosis_key="", experiment_id="42")   # empty must not erase 'd'
    assert t2.diagnosis_key == "d" and t2.experiment_id == "42" and t2.hypothesis_ids == ("h",)


# --- preflight / failure routing --------------------------------------------
def test_preflight_ok_routes_to_manual_apply():
    cand, _, _ = _candidate()
    req = build_execution_request(cand, diagnosis_key="diag-1", scope=SCOPE)
    res = assemble_execution_result(req, {"ok": True, "review": {"content_fingerprint": "pf"}})
    assert res.lifecycle_state == LS.READY_FOR_MANUAL_APPLY.value
    assert "manual" in res.next_action.lower() and "apply gate" in res.next_action.lower()


def test_preflight_failure_routes_to_failed():
    cand, _, _ = _candidate()
    req = build_execution_request(cand, diagnosis_key="diag-1", scope=SCOPE)
    assert assemble_execution_result(req, {"ok": False}).lifecycle_state == \
        LS.PREFLIGHT_FAILED.value
    assert assemble_execution_result(req, None).lifecycle_state == LS.PREFLIGHT_FAILED.value


def test_not_actionable_routes_out():
    req = build_execution_request({"status": "conditional", "deltas": []}, scope=SCOPE)
    assert assemble_execution_result(req, None).lifecycle_state == LS.NOT_ACTIONABLE.value


# --- outcome / reconciliation / prediction routing --------------------------
def _summ(**over):
    cand, ann, hs = _candidate()
    base = dict(candidate=cand, annotation=ann, hypothesis_set=hs, diagnosis_key="diag-1")
    base.update(over)
    return assemble_lifecycle_summary(**base)


def test_apply_state_from_experiment_status():
    assert _summ(experiment={"id": "1", "status": "applied"}).apply_state == "applied"
    assert _summ(experiment={"id": "1", "status": "draft"}).apply_state == "awaiting_manual_apply"


def test_outcome_routing():
    s = _summ(experiment={"id": "1", "status": "completed"},
              outcome={"id": "9", "status": "confirmed_improvement"})
    assert s.lifecycle_state == LS.OUTCOME_RECORDED.value
    assert s.stage_states["outcome"] == "confirmed_improvement"


def test_reconciliation_and_calibration_routing():
    s = _summ(experiment={"id": "1", "status": "completed"},
              outcome={"id": "9", "status": "regression"},
              reconciliation={"record_key": "rk", "prediction_fingerprint": "pf",
                              "outcome_status": "regression"})
    assert s.lifecycle_state == LS.RECONCILED.value
    s2 = _summ(experiment={"id": "1", "status": "completed"},
               outcome={"id": "9", "status": "regression"},
               reconciliation={"record_key": "rk", "prediction_fingerprint": "pf"},
               calibration={"reconciliations": 3, "overall_accuracy": 0.5})
    assert s2.lifecycle_state == LS.CALIBRATED.value
    assert s2.stage_states["calibration"] == "present"


def test_synthesis_only_state_when_no_experiment():
    assert _summ().lifecycle_state == LS.READY_FOR_MANUAL_APPLY.value


# --- fingerprint preservation / determinism ---------------------------------
def test_execution_result_deterministic():
    cand, _, _ = _candidate()
    req = build_execution_request(cand, diagnosis_key="diag-1", scope=SCOPE)
    a = assemble_execution_result(req, {"ok": True, "review": {"content_fingerprint": "pf"}})
    b = assemble_execution_result(req, {"ok": True, "review": {"content_fingerprint": "pf"}})
    assert a.content_fingerprint == b.content_fingerprint
    assert a.to_dict() == b.to_dict()


def test_summary_deterministic_and_synthesis_fp_preserved():
    cand, ann, hs = _candidate()
    s1 = assemble_lifecycle_summary(candidate=cand, hypothesis_set=hs, diagnosis_key="d")
    s2 = assemble_lifecycle_summary(candidate=copy.deepcopy(cand), hypothesis_set=copy.deepcopy(hs),
                                    diagnosis_key="d")
    assert s1.content_fingerprint == s2.content_fingerprint
    # the synthesis fingerprint survives into the lifecycle trace unchanged
    assert s1.trace.synthesis_fingerprint == cand["content_fingerprint"]


# --- no source mutation -----------------------------------------------------
def test_no_source_mutation():
    cand, ann, hs = _candidate()
    csrc, asrc, hsrc = copy.deepcopy(cand), copy.deepcopy(ann), copy.deepcopy(hs)
    req = build_execution_request(cand, diagnosis_key="d", scope=SCOPE)
    assemble_execution_result(req, {"ok": True, "review": {}})
    assemble_lifecycle_summary(candidate=cand, annotation=ann, hypothesis_set=hs)
    assert cand == csrc and ann == asrc and hs == hsrc


# --- rendering --------------------------------------------------------------
def test_render_shows_chain_and_no_apply_control():
    s = _summ(experiment={"id": "1", "status": "completed"},
              outcome={"id": "9", "status": "confirmed_improvement"},
              reconciliation={"record_key": "rk"}, calibration={"reconciliations": 1})
    titles = [t for t, _ in render_summary_sections(s.to_dict())]
    assert "Loop stages" in titles and "Traceability" in titles and "Safety" in titles
    text = render_summary_text(s.to_dict()).lower()
    for banned in ("apply now", "click apply", "approve now", "set arb_front to"):
        assert banned not in text
    assert "sole route to the car" in text
    for stage in ("diagnosis", "mechanism", "hypothesis", "outcome", "reconciliation",
                  "prediction calibration"):
        assert stage in text
