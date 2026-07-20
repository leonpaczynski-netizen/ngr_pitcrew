"""Engineering Brain Phase 9 — engineering-constraints derivation tests."""
import inspect

import pytest

from strategy import engineering_constraints as EC
from strategy.development_history import MemoryContextKey, build_development_record
from strategy.engineering_constraints import derive_constraints, constraints_fingerprint

Q = MemoryContextKey(driver="leon", car="RSR", track="Fuji", layout_id="fc",
                     discipline="Race", gt7_version="1.49", compound="RH")
CLS = {"RSR": "Gr.3"}


def _res(key, typ, state, new=False, present=True):
    return {"issue_key": key, "family": "rotation", "issue_type": typ, "axle": "front",
            "phase": "apex", "segment_id": "T1", "corner_name": "T1",
            "residual_state": state, "is_new": new, "is_regression": False,
            "still_present": present, "protected_good": False, "confidence": "high"}


def _rec(oid, eid, status, sess, residuals, field="lsd_accel", windows=None, failed=(),
         at="2026-07-01T10:00", ctx=Q):
    outcome = {"id": oid, "experiment_id": eid, "status": status,
               "confidence_level": "high", "scope_fingerprint": "sf",
               "test_session_id": sess, "protected": [], "failed_directions": list(failed)}
    exp = {"id": eid, "scope_fingerprint": "sf",
           "changes": [{"field": field, "from_value": "20", "to_value": "30",
                        "delta_direction": "increase"}]}
    return build_development_record(outcome, exp, context=ctx, scope_fingerprint="sf",
                                   working_windows=windows or [], residuals=residuals,
                                   recorded_at=at, session_date=at[:10])


def test_learned_window_constraints():
    recs = [_rec(1, 10, "partial_improvement", "300",
                 [_res("k", "understeer", "improved_but_present")],
                 windows=[{"field": "brake_bias", "min": 50.0, "max": 56.0,
                           "confidence": "high"}])]
    cons = derive_constraints(Q, recs, car_class_of=CLS)
    kinds = {(c.kind, c.field) for c in cons}
    assert ("never_below", "brake_bias") in kinds
    assert ("never_above", "brake_bias") in kinds


def test_failed_direction_constraint_with_provenance():
    recs = [
        _rec(1, 10, "regression", "300", [_res("k", "oversteer", "new", new=True)],
             failed=[{"field": "lsd_accel", "direction": "increase", "magnitude": "30",
                      "severity": "high"}], at="2026-07-01T10:00"),
        _rec(2, 11, "regression", "301", [_res("k", "oversteer", "new", new=True)],
             failed=[{"field": "lsd_accel", "direction": "increase", "magnitude": "30",
                      "severity": "high"}], at="2026-07-05T10:00"),
    ]
    cons = derive_constraints(Q, recs, car_class_of=CLS)
    fd = next(c for c in cons if c.kind == "never_move_direction" and c.field == "lsd_accel")
    assert set(fd.supporting_sessions) == {"300", "301"}
    assert fd.times_reinforced == 2
    assert fd.confirmed          # high confidence, 2 sessions, DIRECT match


def test_provisional_when_weak_evidence():
    # single session, one context → provisional (not confirmed)
    recs = [_rec(1, 10, "regression", "300", [_res("k", "oversteer", "new", new=True)],
                 failed=[{"field": "lsd_accel", "direction": "increase",
                          "magnitude": "30", "severity": "high"}])]
    cons = derive_constraints(Q, recs, car_class_of=CLS)
    fd = next(c for c in cons if c.kind == "never_move_direction")
    assert not fd.confirmed


def test_constraints_deterministic():
    recs = [_rec(i, 10 + i, "regression", str(300 + i),
                 [_res("k", "oversteer", "new", new=True)],
                 failed=[{"field": "lsd_accel", "direction": "increase",
                          "magnitude": "30", "severity": "high"}],
                 at=f"2026-07-0{i}T10:00") for i in (1, 2, 3)]
    a = derive_constraints(Q, recs, car_class_of=CLS)
    b = derive_constraints(Q, list(reversed(recs)), car_class_of=CLS)
    assert constraints_fingerprint(a) == constraints_fingerprint(b)


def test_confirmed_first_order():
    cons = derive_constraints(Q, [
        _rec(1, 10, "regression", "300", [_res("k", "oversteer", "new", new=True)],
             failed=[{"field": "lsd_accel", "direction": "increase", "magnitude": "30",
                      "severity": "high"}], at="2026-07-01T10:00"),
        _rec(2, 11, "regression", "301", [_res("k", "oversteer", "new", new=True)],
             failed=[{"field": "lsd_accel", "direction": "increase", "magnitude": "30",
                      "severity": "high"}], at="2026-07-05T10:00"),
        _rec(3, 12, "partial_improvement", "302",
             [_res("k2", "understeer", "improved_but_present")], field="toe_front",
             windows=[{"field": "arb_front", "min": 3.0, "max": 7.0,
                       "confidence": "low"}], at="2026-07-09T10:00"),
    ], car_class_of=CLS)
    confirmed = [c.confirmed for c in cons]
    assert confirmed == sorted(confirmed, key=lambda x: 0 if x else 1)


def test_module_is_pure():
    src = inspect.getsource(EC)
    for banned in ("import random", "random.", "time.time", "datetime.now",
                   "import sqlite3", "PyQt", "requests", "urllib", "openai"):
        assert banned not in src, banned
