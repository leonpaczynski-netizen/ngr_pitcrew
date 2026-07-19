"""Engineering Brain Phase 9 — Qt-free Engineering Context view-model tests."""
import pytest

from data.session_db import SessionDB
from strategy.development_history import MemoryContextKey, build_development_record
from ui import engineering_context_vm as vm


@pytest.fixture
def result():
    db = SessionDB(":memory:")
    ctx = MemoryContextKey(car="RSR", track="Fuji", layout_id="fc", discipline="Race")
    # a success and a failure in the same context
    for oid, eid, status, field, res in [
            (1, 10, "confirmed_improvement", "toe_front",
             [{"issue_key": "k", "family": "rotation", "issue_type": "understeer",
               "axle": "front", "phase": "apex", "segment_id": "T1", "corner_name": "T1",
               "residual_state": "resolved", "is_new": False, "is_regression": False,
               "still_present": False, "protected_good": False, "confidence": "high"}]),
            (2, 11, "regression", "lsd_accel",
             [{"issue_key": "k2", "family": "traction", "issue_type": "oversteer",
               "axle": "rear", "phase": "exit", "segment_id": "T4", "corner_name": "T4",
               "residual_state": "new", "is_new": True, "is_regression": False,
               "still_present": True, "protected_good": False, "confidence": "high"}])]:
        outcome = {"id": oid, "experiment_id": eid, "status": status,
                   "confidence_level": "high", "scope_fingerprint": "sf",
                   "test_session_id": str(300 + oid), "protected": [],
                   "failed_directions": ([{"field": "lsd_accel", "direction": "increase",
                                           "magnitude": "30", "severity": "high"}]
                                         if status == "regression" else [])}
        exp = {"id": eid, "scope_fingerprint": "sf",
               "changes": [{"field": field, "from_value": "1", "to_value": "2",
                            "delta_direction": "increase"}]}
        rec = build_development_record(outcome, exp, context=ctx, scope_fingerprint="sf",
                                      working_windows=[], residuals=res,
                                      recorded_at=f"2026-07-0{oid}T10:00",
                                      session_date=f"2026-07-0{oid}")
        db._persist_development_record(rec, created_at=rec.recorded_at)
    return db.build_engineering_context(
        car="RSR", track="Fuji", layout_id="fc", discipline="Race",
        proposed_change={"field": "lsd_accel", "direction": "increase", "value": "32"})


def test_not_empty(result):
    assert not vm.is_empty(result)
    assert "context" in vm.summary_line(result)


def test_matched_context_rows(result):
    rows = vm.matched_context_rows(result)
    assert rows and all(len(r) == len(vm.MATCH_COLUMNS) for r in rows)


def test_fix_rows(result):
    assert any("toe_front" in r[1] for r in vm.successful_fix_rows(result))
    assert any("lsd_accel" in r[1] for r in vm.failed_fix_rows(result))


def test_constraint_rows(result):
    rows = vm.constraint_rows(result)
    assert rows and all(len(r) == len(vm.CONSTRAINT_COLUMNS) for r in rows)


def test_risk_rows(result):
    rows = vm.regression_risk_rows(result)
    assert any("lsd_accel" == r[2] for r in rows)
    assert all(len(r) == len(vm.RISK_COLUMNS) for r in rows)


def test_is_empty_on_bad_result():
    assert vm.is_empty(None)
    assert vm.is_empty({"ok": False})
    assert vm.is_empty({"ok": True, "matched_contexts": [], "transfers": [],
                        "constraints": [], "regression_risks": []})
