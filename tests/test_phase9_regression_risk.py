"""Engineering Brain Phase 9 — regression-risk flagging tests (never blocks)."""
import inspect

import pytest

from strategy import regression_risk as RR
from strategy.development_history import MemoryContextKey, build_development_record
from strategy.context_transfer import build_context_transfers, group_matched_records
from strategy.engineering_constraints import derive_constraints
from strategy.regression_risk import RiskKind, assess_regression_risk, risk_fingerprint

Q = MemoryContextKey(driver="leon", car="RSR", track="Fuji", layout_id="fc",
                     discipline="Race", gt7_version="1.49", compound="RH")
CLS = {"RSR": "Gr.3"}


def _res(key, typ, state, new=False, present=True):
    return {"issue_key": key, "family": "rotation", "issue_type": typ, "axle": "front",
            "phase": "apex", "segment_id": "T1", "corner_name": "T1",
            "residual_state": state, "is_new": new, "is_regression": False,
            "still_present": present, "protected_good": False, "confidence": "high"}


def _rec(oid, eid, status, sess, residuals, field="lsd_accel", windows=None,
         protected=(), failed=(), at="2026-07-01T10:00"):
    outcome = {"id": oid, "experiment_id": eid, "status": status,
               "confidence_level": "high", "scope_fingerprint": "sf",
               "test_session_id": sess, "protected": list(protected),
               "failed_directions": list(failed)}
    exp = {"id": eid, "scope_fingerprint": "sf",
           "changes": [{"field": field, "from_value": "20", "to_value": "30",
                        "delta_direction": "increase"}]}
    return build_development_record(outcome, exp, context=Q, scope_fingerprint="sf",
                                   working_windows=windows or [], residuals=residuals,
                                   recorded_at=at, session_date=at[:10])


def _bundle(recs):
    matched = group_matched_records(Q, recs, car_class_of=CLS)
    transfers = build_context_transfers(Q, recs, car_class_of=CLS, matched=matched)
    constraints = derive_constraints(Q, recs, car_class_of=CLS, matched=matched)
    return transfers, constraints


def test_flags_known_failed_direction_and_repeated_regression():
    recs = [
        _rec(1, 10, "regression", "300", [_res("k", "oversteer", "new", new=True)],
             failed=[{"field": "lsd_accel", "direction": "increase", "magnitude": "30",
                      "severity": "high"}], at="2026-07-01T10:00"),
        _rec(2, 11, "regression", "301", [_res("k", "oversteer", "new", new=True)],
             failed=[{"field": "lsd_accel", "direction": "increase", "magnitude": "30",
                      "severity": "high"}], at="2026-07-05T10:00"),
    ]
    transfers, constraints = _bundle(recs)
    risks = assess_regression_risk(constraints, transfers,
                                   proposed_change={"field": "lsd_accel",
                                                    "direction": "increase", "value": "32"})
    kinds = {r.kind for r in risks}
    assert RiskKind.KNOWN_FAILED_DIRECTION.value in kinds
    assert RiskKind.REPEATED_REGRESSION.value in kinds


def test_flags_working_window_edge():
    recs = [_rec(1, 10, "partial_improvement", "300",
                 [_res("k", "understeer", "improved_but_present")], field="toe_front",
                 windows=[{"field": "brake_bias", "min": 50.0, "max": 56.0,
                           "confidence": "high"}])]
    transfers, constraints = _bundle(recs)
    risks = assess_regression_risk(constraints, transfers,
                                   proposed_change={"field": "brake_bias",
                                                    "direction": "decrease", "value": "48"})
    assert any(r.kind == RiskKind.WORKING_WINDOW_EDGE.value for r in risks)


def test_flags_protected_field_conflict():
    recs = [_rec(1, 10, "confirmed_improvement", "300",
                 [_res("k", "understeer", "resolved", present=False)], field="toe_front",
                 protected=[{"behaviour": "rear traction", "field": "lsd_decel",
                             "verdict": "preserved", "confidence": "high"}])]
    transfers, constraints = _bundle(recs)
    risks = assess_regression_risk(constraints, transfers,
                                   proposed_change={"field": "lsd_decel",
                                                    "direction": "increase", "value": "5"})
    assert any(r.kind == RiskKind.PROTECTED_FIELD_CONFLICT.value for r in risks)


def test_never_blocks_and_is_empty_safe():
    # no history, no proposed change → empty tuple, never raises
    assert assess_regression_risk((), ()) == ()
    assert isinstance(assess_regression_risk((), (), proposed_change={"field": "x"}), tuple)


def test_unrelated_field_not_flagged():
    recs = [_rec(1, 10, "regression", "300", [_res("k", "oversteer", "new", new=True)],
                 failed=[{"field": "lsd_accel", "direction": "increase", "magnitude": "30",
                          "severity": "high"}])]
    transfers, constraints = _bundle(recs)
    risks = assess_regression_risk(constraints, transfers,
                                   proposed_change={"field": "ride_height",
                                                    "direction": "increase", "value": "60"})
    assert all(r.field != "lsd_accel" for r in risks)


def test_risk_deterministic():
    recs = [_rec(i, 10 + i, "regression", str(300 + i),
                 [_res("k", "oversteer", "new", new=True)],
                 failed=[{"field": "lsd_accel", "direction": "increase",
                          "magnitude": "30", "severity": "high"}],
                 at=f"2026-07-0{i}T10:00") for i in (1, 2, 3)]
    transfers, constraints = _bundle(recs)
    a = assess_regression_risk(constraints, transfers,
                               proposed_change={"field": "lsd_accel",
                                                "direction": "increase", "value": "32"})
    b = assess_regression_risk(constraints, transfers,
                               proposed_change={"field": "lsd_accel",
                                                "direction": "increase", "value": "32"})
    assert risk_fingerprint(a) == risk_fingerprint(b)


def test_module_is_pure():
    src = inspect.getsource(RR)
    for banned in ("import random", "random.", "time.time", "datetime.now",
                   "import sqlite3", "PyQt", "requests", "urllib", "openai"):
        assert banned not in src, banned
