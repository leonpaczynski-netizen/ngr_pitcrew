"""Engineering Brain Phase 10 — engineering-checklist + risk-level tests."""
import inspect

import pytest

from strategy import engineering_checklist as EC
from strategy.engineering_checklist import (
    ChecklistStatus, RiskLevel, build_checklist, checklist_fingerprint,
)

CAND = {
    "field": "lsd_accel", "direction": "increase", "proposed_value": 25.0,
    "window_relationship": "inside_window", "protected_behaviours_at_risk": [],
}


def _ctx(transfers=(), risks=(), constraints=()):
    return {"transfers": list(transfers), "regression_risks": list(risks),
            "constraints": list(constraints),
            "matched_contexts": [{"strength": "direct_match"}]}


def _succ(sessions=("300", "301"), confirmed=True):
    return {"kind": "successful_experiment", "field": "lsd_accel", "direction": "increase",
            "detail": "resolved", "supporting_sessions": list(sessions),
            "confirmed": confirmed, "strength": "strong_match"}


def test_inside_window_and_no_protected_conflict_ok():
    items, _ = build_checklist(CAND, context=_ctx(transfers=[_succ()]))
    labels = {i.label: i.status for i in items}
    assert labels.get("Inside learned window") == ChecklistStatus.OK.value
    assert labels.get("No protected-behaviour conflict") == ChecklistStatus.OK.value
    assert labels.get("Similar experiment succeeded") == ChecklistStatus.OK.value


def test_only_one_supporting_session_caution():
    items, _ = build_checklist(CAND, context=_ctx(transfers=[_succ(sessions=("300",))]))
    assert any(i.label == "Only one supporting session"
               and i.status == ChecklistStatus.CAUTION.value for i in items)


def test_outstanding_residual_caution():
    memory = {"memory": {"issues": [{"issue_type": "rear_locking", "corner": "T1",
                                     "currently_resolved": False}]}}
    items, _ = build_checklist(CAND, context=_ctx(transfers=[_succ()]), memory=memory)
    assert any("rear_locking still unresolved" in i.label for i in items)


def test_coupled_interaction_caution():
    items, _ = build_checklist(CAND, context=_ctx(transfers=[_succ()]))
    assert any(i.label == "Coupled interaction exists" for i in items)


def test_risk_high_on_confirmed_failed_direction():
    risks = [{"field": "lsd_accel", "kind": "known_failed_direction", "severity": "high",
              "direction": "increase", "reason": "failed", "confirmed": True}]
    _, risk = build_checklist(CAND, context=_ctx(risks=risks))
    assert risk == RiskLevel.HIGH


def test_risk_unknown_without_history():
    _, risk = build_checklist({"field": "ride_height_front", "direction": "increase",
                               "proposed_value": 60, "window_relationship": ""},
                              context={"transfers": [], "regression_risks": [],
                                       "matched_contexts": []})
    assert risk == RiskLevel.UNKNOWN


def test_risk_low_when_clean():
    items, risk = build_checklist(
        {"field": "aero_front_ratio", "direction": "increase", "proposed_value": 50,
         "window_relationship": "inside_window", "protected_behaviours_at_risk": []},
        context=_ctx(transfers=[_succ()]))
    # aero_front_ratio has no coupled fields → fewer cautions
    assert risk in (RiskLevel.LOW, RiskLevel.MODERATE)


def test_checklist_never_changes_inputs():
    cand = dict(CAND)
    ctx = _ctx(transfers=[_succ()])
    before = dict(cand)
    build_checklist(cand, context=ctx)
    assert cand == before        # inputs untouched (no mutation)


def test_deterministic():
    items_a, risk_a = build_checklist(CAND, context=_ctx(transfers=[_succ()]))
    items_b, risk_b = build_checklist(CAND, context=_ctx(transfers=[_succ()]))
    assert checklist_fingerprint(items_a, risk_a) == checklist_fingerprint(items_b, risk_b)


def test_module_is_pure():
    src = inspect.getsource(EC)
    for banned in ("import random", "random.", "time.time", "datetime.now",
                   "import sqlite3", "PyQt", "requests", "urllib", "openai"):
        assert banned not in src, banned
