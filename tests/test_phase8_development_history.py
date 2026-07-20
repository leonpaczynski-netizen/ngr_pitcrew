"""Engineering Brain Phase 8 — development-history foundation tests.

Locks the immutable memory context key, the time-independent + idempotent development
record, chronological history assembly (dedup, order), the timeline, and purity.
"""
import inspect

import pytest

from strategy import development_history as DH
from strategy.development_history import (
    ConstraintKind, DevelopmentRecord, MemoryContextKey, build_development_record,
    build_history, build_timeline,
)


def _residual(key, typ, state, *, new=False, reg=False, present=True, fam="rotation",
              corner="Turn 1", seg="T1"):
    return {"issue_key": key, "family": fam, "issue_type": typ, "axle": "front",
            "phase": "apex", "segment_id": seg, "corner_name": corner,
            "residual_state": state, "is_new": new, "is_regression": reg,
            "still_present": present, "protected_good": False, "confidence": "high"}


def _outcome(oid, exp, status, sess, *, protected=(), failed=()):
    return {"id": oid, "experiment_id": exp, "status": status,
            "confidence_level": "high", "scope_fingerprint": "sf",
            "test_session_id": sess, "protected": list(protected),
            "failed_directions": list(failed)}


def _exp(eid, field="toe_front"):
    return {"id": eid, "scope_fingerprint": "sf",
            "changes": [{"field": field, "from_value": "0.1", "to_value": "0.2",
                         "delta_direction": "increase", "rationale": "understeer"}]}


CTX = MemoryContextKey(driver="leon", car="RSR", track="Fuji", layout_id="fc",
                       discipline="Race", gt7_version="1.49", compound="RH")


def _record(oid, eid, status, sess, residuals, *, windows=None, recorded_at="2026-07-01T10:00",
            session_date="2026-07-01", protected=(), failed=()):
    return build_development_record(
        _outcome(oid, eid, status, sess, protected=protected, failed=failed),
        _exp(eid), context=CTX, scope_fingerprint="sf",
        working_windows=windows or [], residuals=residuals, recorded_at=recorded_at,
        session_date=session_date)


# --- context key ------------------------------------------------------------
def test_context_key_stable_and_isolating():
    a = MemoryContextKey(car="RSR", track="Fuji", compound="RH")
    b = MemoryContextKey(car="RSR", track="Fuji", compound="RH")
    c = MemoryContextKey(car="RSR", track="Fuji", compound="RM")
    assert a.key() == b.key()
    assert a.key() != c.key()          # incompatible compound never merges


def test_context_unknown_differs_from_known():
    known = MemoryContextKey(car="RSR", gt7_version="1.49")
    unknown = MemoryContextKey(car="RSR", gt7_version="")
    assert known.key() != unknown.key()


# --- development record -----------------------------------------------------
def test_record_is_time_independent_and_idempotent():
    r1 = _record(1, 10, "confirmed_improvement", "300",
                 [_residual("k", "understeer", "resolved", present=False)],
                 recorded_at="2026-07-01T10:00")
    r2 = _record(1, 10, "confirmed_improvement", "300",
                 [_residual("k", "understeer", "resolved", present=False)],
                 recorded_at="2026-07-09T23:59")   # different clock time
    assert r1.record_key == r2.record_key
    assert r1.content_fingerprint == r2.content_fingerprint


def test_record_captures_improvements_and_regressions():
    r = _record(2, 11, "regression", "301",
                [_residual("k1", "understeer", "resolved", present=False),
                 _residual("k2", "rear_loose", "new", new=True)])
    assert any(i["issue_type"] == "understeer" for i in r.confirmed_improvements)
    assert any(i["issue_type"] == "rear_loose" for i in r.new_regressions)
    assert r.regressed


def test_record_derives_protected_knowledge():
    windows = [{"field": "toe_front", "min": 0.0, "max": 0.3, "confidence": "high"}]
    failed = [{"field": "lsd_accel", "direction": "increase", "magnitude": "5",
               "severity": "high"}]
    r = _record(3, 12, "confirmed_improvement", "302",
                [_residual("k", "understeer", "resolved", present=False)],
                windows=windows, failed=failed)
    kinds = {k["kind"] for k in r.protected_knowledge}
    assert ConstraintKind.NEVER_BELOW.value in kinds
    assert ConstraintKind.NEVER_ABOVE.value in kinds
    assert ConstraintKind.NEVER_MOVE_DIRECTION.value in kinds


def test_record_roundtrip():
    r = _record(4, 13, "partial_improvement", "303",
                [_residual("k", "understeer", "improved_but_present")])
    r2 = DevelopmentRecord.from_dict(r.to_dict())
    assert r2.content_fingerprint == r.content_fingerprint
    assert r2.record_key == r.record_key


# --- history ----------------------------------------------------------------
def test_history_is_chronological_and_dedups():
    a = _record(1, 10, "no_meaningful_change", "300",
                [_residual("k", "understeer", "unchanged")],
                recorded_at="2026-07-01T10:00")
    b = _record(2, 11, "confirmed_improvement", "301",
                [_residual("k", "understeer", "resolved", present=False)],
                recorded_at="2026-07-05T10:00")
    h = build_history([b, a, a])       # unordered + duplicate
    assert h.review_count == 2         # duplicate 'a' collapsed
    assert h.records[0].recorded_at <= h.records[1].recorded_at


def test_history_fingerprint_order_stable():
    recs = [_record(i, 10 + i, "no_meaningful_change", str(300 + i),
                    [_residual("k", "understeer", "unchanged")],
                    recorded_at=f"2026-07-0{i}T10:00") for i in (1, 2, 3)]
    h1 = build_history(recs)
    h2 = build_history(list(reversed(recs)))
    assert h1.content_fingerprint == h2.content_fingerprint


# --- timeline ---------------------------------------------------------------
def test_timeline_has_session_experiment_and_resolution():
    r = _record(1, 10, "confirmed_improvement", "300",
                [_residual("k", "understeer", "resolved", present=False)])
    tl = build_timeline(build_history([r]))
    kinds = [e.kind.value for e in tl]
    assert "session" in kinds and "experiment" in kinds and "resolution" in kinds
    assert [e.sequence_no for e in tl] == list(range(len(tl)))


# --- purity -----------------------------------------------------------------
def test_module_is_pure():
    src = inspect.getsource(DH)
    for banned in ("import random", "random.", "time.time", "datetime.now",
                   "import sqlite3", "PyQt", "requests", "urllib", "openai"):
        assert banned not in src, banned
