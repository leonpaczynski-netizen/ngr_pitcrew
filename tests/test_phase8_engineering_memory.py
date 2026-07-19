"""Engineering Brain Phase 8 — permanent engineering memory fold tests."""
import inspect

import pytest

from strategy import engineering_memory as EM
from strategy.development_history import MemoryContextKey, build_development_record, build_history
from strategy.engineering_memory import build_engineering_memory

CTX = MemoryContextKey(car="RSR", track="Fuji", layout_id="fc", discipline="Race",
                       compound="RH")


def _res(key, typ, state, *, new=False, reg=False, present=True):
    return {"issue_key": key, "family": "rotation", "issue_type": typ, "axle": "front",
            "phase": "apex", "segment_id": "T1", "corner_name": "Turn 1",
            "residual_state": state, "is_new": new, "is_regression": reg,
            "still_present": present, "protected_good": False, "confidence": "high"}


def _rec(oid, eid, status, sess, residuals, *, windows=None, protected=(), failed=(),
         date="2026-07-01", at="2026-07-01T10:00"):
    outcome = {"id": oid, "experiment_id": eid, "status": status,
               "confidence_level": "high", "scope_fingerprint": "sf",
               "test_session_id": sess, "protected": list(protected),
               "failed_directions": list(failed)}
    exp = {"id": eid, "scope_fingerprint": "sf",
           "changes": [{"field": "toe_front", "from_value": "0.1", "to_value": "0.2",
                        "delta_direction": "increase"}]}
    return build_development_record(outcome, exp, context=CTX, scope_fingerprint="sf",
                                   working_windows=windows or [], residuals=residuals,
                                   recorded_at=at, session_date=date)


def _history(recs):
    return build_history(recs, context=CTX)


def test_issue_resolution_tracked_across_sessions():
    recs = [
        _rec(1, 10, "no_meaningful_change", "300", [_res("k", "understeer", "unchanged")],
             date="2026-07-01", at="2026-07-01T10:00"),
        _rec(2, 11, "partial_improvement", "301",
             [_res("k", "understeer", "improved_but_present")],
             date="2026-07-05", at="2026-07-05T10:00"),
        _rec(3, 12, "confirmed_improvement", "302",
             [_res("k", "understeer", "resolved", present=False)],
             date="2026-07-09", at="2026-07-09T10:00"),
    ]
    mem = build_engineering_memory(_history(recs))
    im = mem.issue_for("k")
    assert im is not None
    assert im.times_observed == 3
    assert im.sessions_seen == 3
    assert im.currently_resolved
    assert im.times_resolved == 1
    assert "12" in im.successful_fix_experiments


def test_recurring_issue_flagged():
    recs = [
        _rec(1, 10, "no_meaningful_change", "300", [_res("k", "understeer", "unchanged")],
             at="2026-07-01T10:00"),
        _rec(2, 11, "no_meaningful_change", "301", [_res("k", "understeer", "unchanged")],
             at="2026-07-05T10:00"),
    ]
    mem = build_engineering_memory(_history(recs))
    im = mem.issue_for("k")
    assert im.recurring          # present in >= 2 records
    assert not im.currently_resolved


def test_failed_fix_recorded():
    recs = [_rec(1, 10, "regression", "300",
                 [_res("k", "oversteer", "new", new=True)], at="2026-07-01T10:00")]
    mem = build_engineering_memory(_history(recs))
    im = mem.issue_for("k")
    assert im.times_regressed == 1
    assert "10" in im.failed_fix_experiments
    assert mem.failed_fix_count == 1


def test_working_window_evolution():
    recs = [
        _rec(1, 10, "partial_improvement", "300", [_res("k", "understeer", "improved_but_present")],
             windows=[{"field": "toe_front", "min": 0.0, "max": 0.4, "confidence": "low"}],
             at="2026-07-01T10:00"),
        _rec(2, 11, "confirmed_improvement", "301", [_res("k", "understeer", "resolved", present=False)],
             windows=[{"field": "toe_front", "min": 0.1, "max": 0.3, "confidence": "high"}],
             at="2026-07-05T10:00"),
    ]
    mem = build_engineering_memory(_history(recs))
    w = next(w for w in mem.window_evolution if w.field == "toe_front")
    assert len(w.snapshots) == 2
    assert w.latest_confidence == "high"
    assert w.latest_min == 0.1 and w.latest_max == 0.3


def test_protected_knowledge_reinforced():
    windows = [{"field": "rear_rebound", "min": 4.0, "max": 8.0, "confidence": "high"}]
    recs = [
        _rec(1, 10, "partial_improvement", "300", [_res("k", "understeer", "improved_but_present")],
             windows=windows, at="2026-07-01T10:00"),
        _rec(2, 11, "confirmed_improvement", "301", [_res("k", "understeer", "resolved", present=False)],
             windows=windows, at="2026-07-05T10:00"),
    ]
    mem = build_engineering_memory(_history(recs))
    nb = [k for k in mem.protected_knowledge
          if k.kind == "never_below" and k.field == "rear_rebound"]
    assert nb and nb[0].times_reinforced == 2


def test_protected_behaviour_retained():
    recs = [_rec(1, 10, "confirmed_improvement", "300",
                 [_res("k", "understeer", "resolved", present=False)],
                 protected=[{"behaviour": "rear traction", "field": "lsd_decel",
                             "verdict": "preserved", "confidence": "high"}],
                 at="2026-07-01T10:00")]
    mem = build_engineering_memory(_history(recs))
    assert any(p.get("verdict") == "preserved" for p in mem.protected_behaviours)
    assert any(k.kind == "protected_behaviour" for k in mem.protected_knowledge)


def test_memory_deterministic():
    recs = [_rec(i, 10 + i, "confirmed_improvement", str(300 + i),
                 [_res("k", "understeer", "resolved", present=False)],
                 at=f"2026-07-0{i}T10:00") for i in (1, 2, 3)]
    a = build_engineering_memory(_history(recs))
    b = build_engineering_memory(_history(list(reversed(recs))))
    assert a.content_fingerprint == b.content_fingerprint


def test_module_is_pure():
    src = inspect.getsource(EM)
    for banned in ("import random", "random.", "time.time", "datetime.now",
                   "import sqlite3", "PyQt", "requests", "urllib", "openai"):
        assert banned not in src, banned
