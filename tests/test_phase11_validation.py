"""Engineering Brain Phase 11 — checklist-validation + accuracy tests."""
import inspect

import pytest

from strategy import preflight_validation as PV
from strategy import prediction_accuracy as PA
from strategy.preflight_validation import ItemOutcome, validate_checklist
from strategy.prediction_accuracy import compute_accuracy
from strategy.postflight_reconciliation import reconcile_consequences


def _pf(checklist):
    return {"review": {"experiment": {"field": "lsd_accel", "target_issue": "exit_wheelspin"},
                       "consequences": [], "checklist": checklist}}


def _resid(issue, family, state, new=False, present=True):
    return {"issue_type": issue, "family": family, "residual_state": state,
            "is_new": new, "is_regression": False, "still_present": present}


def test_protected_ok_did_not_materialise_when_preserved():
    pf = _pf([{"status": "ok", "label": "No protected-behaviour conflict", "why": "safe"}])
    outcome = {"status": "confirmed_improvement", "protected": [{"verdict": "preserved"}]}
    v = validate_checklist(pf, outcome, [])[0]
    assert v.outcome == ItemOutcome.DID_NOT_MATERIALISE.value
    assert v.useful


def test_protected_conflict_materialises_when_damaged():
    pf = _pf([{"status": "caution", "label": "Protected-behaviour conflict", "why": "x"}])
    outcome = {"status": "regression", "protected": [{"verdict": "material_regression"}]}
    v = validate_checklist(pf, outcome, [])[0]
    assert v.outcome == ItemOutcome.MATERIALISED.value
    assert v.useful


def test_window_caution_materialises_on_regression():
    pf = _pf([{"status": "caution", "label": "At working-window edge", "why": "x"}])
    outcome = {"status": "regression", "protected": []}
    resid = [_resid("oversteer", "rotation", "new", new=True)]
    v = validate_checklist(pf, outcome, resid)[0]
    assert v.outcome == ItemOutcome.MATERIALISED.value


def test_residual_still_unresolved_materialises():
    pf = _pf([{"status": "caution", "label": "rear_locking still unresolved", "why": "x"}])
    outcome = {"status": "confirmed_improvement", "protected": []}
    resid = [_resid("rear_locking", "braking", "unchanged", present=True)]
    v = validate_checklist(pf, outcome, resid)[0]
    assert v.outcome == ItemOutcome.MATERIALISED.value


def test_accuracy_full_when_all_confirmed():
    pf = {"review": {"experiment": {"field": "lsd_accel", "target_issue": "exit_wheelspin"},
                     "consequences": [{"kind": "primary_effect", "field": "lsd_accel",
                                       "text": "increases exit traction"}],
                     "checklist": [{"status": "ok", "label": "Inside learned window", "why": "w"}]}}
    outcome = {"status": "confirmed_improvement", "protected": []}
    resid = [_resid("exit_wheelspin", "traction", "resolved", present=False)]
    cons = reconcile_consequences(pf, outcome, resid)
    checks = validate_checklist(pf, outcome, resid)
    acc = compute_accuracy(cons, checks)
    assert acc.primary_consequence_accuracy == 1.0
    assert 0.0 <= acc.overall_accuracy <= 1.0


def test_accuracy_deterministic():
    pf = {"review": {"experiment": {"field": "lsd_accel", "target_issue": "exit_wheelspin"},
                     "consequences": [{"kind": "primary_effect", "field": "lsd_accel", "text": "x"}],
                     "checklist": []}}
    outcome = {"status": "confirmed_improvement", "protected": []}
    resid = [_resid("exit_wheelspin", "traction", "resolved", present=False)]
    a = compute_accuracy(reconcile_consequences(pf, outcome, resid), [])
    b = compute_accuracy(reconcile_consequences(pf, outcome, resid), [])
    assert a.content_fingerprint == b.content_fingerprint


def test_accuracy_empty_safe():
    acc = compute_accuracy([], [])
    assert acc.overall_accuracy == 0.0
    assert acc.to_dict()["evaluable_count"] == 0


def test_validation_module_pure():
    for mod in (PV, PA):
        src = inspect.getsource(mod)
        for banned in ("import random", "random.", "time.time", "datetime.now",
                       "import sqlite3", "PyQt", "requests", "urllib", "openai"):
            assert banned not in src, f"{mod.__name__}:{banned}"
