"""Engineering Brain Phase 10 — pre-flight review assembly tests."""
import inspect

import pytest

from strategy import preflight_review as PR
from strategy.preflight_review import build_preflight_review

CAND = {
    "candidate_id": "c1", "target_issue": "exit_wheelspin", "target_phase": "exit",
    "field": "lsd_accel", "subsystem": "diff", "current_value": 20.0,
    "proposed_value": 25.0, "delta": 5.0, "direction": "increase",
    "hypothesis": "reduce exit wheelspin", "expected_positive_effect": "increases exit traction",
    "expected_negative_effects": ["may reduce power-oversteer resistance"],
    "protected_behaviours_at_risk": [], "supporting_evidence": ["recurring wheelspin T4"],
    "window_relationship": "inside_window", "evidence_grade": "medium",
    "selection_rationale": "minimum-effective single-field change",
}
CONTEXT = {
    "ok": True,
    "matched_contexts": [{"context": {"label": "RSR"}, "strength": "direct_match",
                          "reason": "same", "record_count": 2}],
    "transfers": [{"kind": "successful_experiment", "strength": "strong_match",
                   "field": "lsd_accel", "direction": "increase", "detail": "resolved",
                   "supporting_sessions": ["300", "301"], "supporting_experiments": ["10", "11"],
                   "confirmed": True}],
    "constraints": [{"kind": "preferred_range", "field": "lsd_accel",
                     "detail": "keep within 18..28", "evidence_source": "ww",
                     "supporting_sessions": ["300", "301"], "confidence": "high",
                     "confirmed": True}],
    "regression_risks": [],
}
MEMORY = {
    "ok": True, "scorecard": {"band": "progressing"},
    "metrics": {"issues_remaining": 1, "issues_solved": 2},
    "memory": {"issues": [{"issue_type": "rear_locking", "corner": "T1",
                           "currently_resolved": False, "latest_state": "unchanged"}]},
}


def test_experiment_echoed_unmodified():
    r = build_preflight_review(CAND, context=CONTEXT, memory=MEMORY)
    assert r.experiment["field"] == "lsd_accel"
    assert r.experiment["proposed_value"] == 25.0
    assert r.experiment["target_issue"] == "exit_wheelspin"


def test_core_sections_present():
    r = build_preflight_review(CAND, context=CONTEXT, memory=MEMORY)
    keys = {s.key for s in r.sections}
    for need in ("evidence_quality", "working_window", "protected_impact",
                 "historical_success", "known_constraints", "interaction_risks",
                 "coupled_fields", "driver_familiarity", "outstanding_residuals",
                 "current_state"):
        assert need in keys, need


def test_regression_section_only_when_risks_present():
    clean = build_preflight_review(CAND, context=CONTEXT, memory=MEMORY)
    assert "regression_risk" not in {s.key for s in clean.sections}
    ctx = dict(CONTEXT)
    ctx["regression_risks"] = [{"field": "lsd_accel", "kind": "known_failed_direction",
                                "severity": "high", "reason": "failed", "confirmed": True,
                                "direction": "increase"}]
    risky = build_preflight_review(CAND, context=ctx, memory=MEMORY)
    assert "regression_risk" in {s.key for s in risky.sections}
    assert risky.risk_level == "high"


def test_consequences_and_checklist_attached():
    r = build_preflight_review(CAND, context=CONTEXT, memory=MEMORY)
    assert r.consequences
    assert r.checklist
    assert r.risk_level in ("low", "moderate", "high", "unknown")


def test_deterministic_fingerprint():
    a = build_preflight_review(CAND, context=CONTEXT, memory=MEMORY)
    b = build_preflight_review(CAND, context=CONTEXT, memory=MEMORY)
    assert a.content_fingerprint == b.content_fingerprint


def test_metamorphic_inputs_not_mutated():
    cand, ctx, mem = dict(CAND), dict(CONTEXT), dict(MEMORY)
    before = (dict(cand), str(ctx), str(mem))
    build_preflight_review(cand, context=ctx, memory=mem)
    assert dict(cand) == before[0]


def test_empty_inputs_safe():
    r = build_preflight_review({"field": "x", "direction": "increase", "proposed_value": 1},
                               context={}, memory={})
    assert r.risk_level == "unknown"
    assert isinstance(r.to_dict(), dict)


def test_to_dict_json_safe():
    import json
    r = build_preflight_review(CAND, context=CONTEXT, memory=MEMORY)
    json.dumps(r.to_dict())


def test_module_is_pure():
    src = inspect.getsource(PR)
    for banned in ("import random", "random.", "time.time", "datetime.now",
                   "import sqlite3", "PyQt", "requests", "urllib", "openai"):
        assert banned not in src, banned
