"""Engineering Brain Phase 11 — reconciliation logic tests."""
import inspect

import pytest

from strategy import postflight_reconciliation as PR
from strategy.postflight_reconciliation import (
    ReconciliationStatus, build_reconciliation_record, reconcile_consequences,
)

PREFLIGHT = {"review": {
    "risk_level": "moderate", "content_fingerprint": "pf:abc",
    "experiment": {"candidate_id": "7", "field": "lsd_accel", "direction": "increase",
                   "proposed_value": 25.0, "target_issue": "exit_wheelspin"},
    "consequences": [
        {"kind": "primary_effect", "field": "lsd_accel", "text": "increases exit traction"},
        {"kind": "side_effect", "field": "lsd_accel", "text": "may reduce power-oversteer resistance"},
        {"kind": "historical", "field": "lsd_accel", "text": "previously improved exit wheelspin"},
        {"kind": "working_window", "field": "lsd_accel", "text": "stays inside working window"},
        {"kind": "interaction", "field": "lsd_accel", "text": "known interaction with arb_rear"},
    ],
    "checklist": [{"status": "ok", "label": "Inside learned window", "why": "w"}],
}}


def _resid(issue, family, state, new=False, reg=False, present=True):
    return {"issue_type": issue, "family": family, "residual_state": state,
            "is_new": new, "is_regression": reg, "still_present": present}


def test_all_statuses_on_confirmed_improvement():
    outcome = {"id": 55, "status": "confirmed_improvement", "protected": []}
    resid = [_resid("exit_wheelspin", "traction", "resolved", present=False)]
    by = {c.kind: c.status for c in reconcile_consequences(PREFLIGHT, outcome, resid)}
    assert by["primary_effect"] == ReconciliationStatus.CONFIRMED.value
    assert by["side_effect"] == ReconciliationStatus.NOT_OBSERVED.value
    assert by["historical"] == ReconciliationStatus.CONFIRMED.value
    assert by["working_window"] == ReconciliationStatus.CONFIRMED.value


def test_regression_contradicts_and_side_effect_confirms():
    outcome = {"id": 56, "status": "regression", "protected": []}
    resid = [_resid("exit_wheelspin", "traction", "unchanged", present=True),
             _resid("snap_oversteer", "rotation", "new", new=True)]
    by = {c.kind: c.status for c in reconcile_consequences(PREFLIGHT, outcome, resid)}
    assert by["side_effect"] == ReconciliationStatus.CONFIRMED.value
    assert by["historical"] == ReconciliationStatus.CONTRADICTED.value
    assert by["working_window"] == ReconciliationStatus.CONTRADICTED.value


def test_partial_improvement_partially_confirms():
    outcome = {"id": 57, "status": "partial_improvement", "protected": []}
    resid = [_resid("exit_wheelspin", "traction", "improved_but_present", present=True)]
    by = {c.kind: c.status for c in reconcile_consequences(PREFLIGHT, outcome, resid)}
    assert by["primary_effect"] == ReconciliationStatus.PARTIALLY_CONFIRMED.value


def test_insufficient_evidence_flows_through():
    outcome = {"id": 58, "status": "insufficient_evidence", "protected": []}
    by = {c.kind: c.status for c in reconcile_consequences(PREFLIGHT, outcome, [])}
    assert by["primary_effect"] == ReconciliationStatus.INSUFFICIENT_EVIDENCE.value
    assert by["side_effect"] == ReconciliationStatus.INSUFFICIENT_EVIDENCE.value


def test_record_time_independent_and_idempotent():
    outcome = {"id": 55, "status": "confirmed_improvement", "protected": []}
    resid = [_resid("exit_wheelspin", "traction", "resolved", present=False)]
    a = build_reconciliation_record(PREFLIGHT, outcome, resid, memory_context_key="ctx",
                                    recorded_at="2026-07-19T10:00")
    b = build_reconciliation_record(PREFLIGHT, outcome, resid, memory_context_key="ctx",
                                    recorded_at="2026-09-01T23:59")
    assert a.record_key == b.record_key
    assert a.content_fingerprint == b.content_fingerprint


def test_record_deterministic_and_json_safe():
    import json
    outcome = {"id": 55, "status": "confirmed_improvement", "protected": []}
    resid = [_resid("exit_wheelspin", "traction", "resolved", present=False)]
    rec = build_reconciliation_record(PREFLIGHT, outcome, resid, memory_context_key="ctx",
                                      recorded_at="2026-07-19T10:00")
    json.dumps(rec.to_dict())
    assert rec.accuracy.overall_accuracy >= 0.0


def test_inputs_not_mutated():
    pf = dict(PREFLIGHT)
    before = str(pf)
    reconcile_consequences(pf, {"status": "confirmed_improvement"}, [])
    assert str(pf) == before


def test_module_is_pure():
    src = inspect.getsource(PR)
    for banned in ("import random", "random.", "time.time", "datetime.now",
                   "import sqlite3", "PyQt", "requests", "urllib", "openai"):
        assert banned not in src, banned
