"""Engineering Brain Phase 8 — progress metrics, scorecard, comparison tests."""
import inspect

import pytest

from strategy import progress_metrics as PM
from strategy.development_history import MemoryContextKey, build_development_record, build_history
from strategy.engineering_memory import build_engineering_memory
from strategy.progress_metrics import (
    MetricTrend, ScorecardBand, build_progress_metrics, build_scorecard,
    compare_latest_sessions, numeric_trend,
)

CTX = MemoryContextKey(car="RSR", track="Fuji", layout_id="fc", discipline="Race",
                       compound="RH")


def _res(key, typ, state, *, new=False, reg=False, present=True, fam="rotation"):
    return {"issue_key": key, "family": fam, "issue_type": typ, "axle": "front",
            "phase": "apex", "segment_id": "T1", "corner_name": "Turn 1",
            "residual_state": state, "is_new": new, "is_regression": reg,
            "still_present": present, "protected_good": False, "confidence": "high"}


def _rec(oid, eid, status, sess, residuals, *, at):
    outcome = {"id": oid, "experiment_id": eid, "status": status,
               "confidence_level": "high", "scope_fingerprint": "sf",
               "test_session_id": sess, "protected": [], "failed_directions": []}
    exp = {"id": eid, "scope_fingerprint": "sf",
           "changes": [{"field": "toe_front", "from_value": "0.1", "to_value": "0.2"}]}
    return build_development_record(outcome, exp, context=CTX, scope_fingerprint="sf",
                                   working_windows=[], residuals=residuals,
                                   recorded_at=at, session_date=at[:10])


# --- numeric trend ----------------------------------------------------------
def test_trend_insufficient_below_min_points():
    assert numeric_trend([1.0, 2.0]) == MetricTrend.INSUFFICIENT


def test_trend_improving_and_worsening_respect_direction():
    # decreasing count with higher_is_better=False → improving
    assert numeric_trend([3.0, 2.0, 1.0, 0.0], higher_is_better=False) == MetricTrend.IMPROVING
    assert numeric_trend([0.0, 1.0, 2.0, 3.0], higher_is_better=False) == MetricTrend.WORSENING


def test_trend_single_point_never_flips():
    # a long flat series with one late spike stays STABLE (window means barely move)
    assert numeric_trend([1.0, 1.0, 1.0, 1.0, 1.0, 1.2]) == MetricTrend.STABLE


def test_trend_stable_when_flat():
    assert numeric_trend([1.0, 1.0, 1.0, 1.0]) == MetricTrend.STABLE


# --- metrics ----------------------------------------------------------------
def test_metrics_resolution_and_success_rate():
    recs = [
        _rec(1, 10, "no_meaningful_change", "300", [_res("k", "understeer", "unchanged")],
             at="2026-07-01T10:00"),
        _rec(2, 11, "partial_improvement", "301",
             [_res("k", "understeer", "improved_but_present")], at="2026-07-05T10:00"),
        _rec(3, 12, "confirmed_improvement", "302",
             [_res("k", "understeer", "resolved", present=False)], at="2026-07-09T10:00"),
    ]
    h = build_history(recs, context=CTX)
    mem = build_engineering_memory(h)
    m = build_progress_metrics(h, mem)
    assert m.issue_resolution_rate == 1.0
    assert 0.0 < m.experiment_success_rate <= 1.0
    assert m.entry_stability_trend == MetricTrend.IMPROVING.value  # understeer count 1→1→0


def test_metrics_deterministic():
    recs = [_rec(i, 10 + i, "confirmed_improvement", str(300 + i),
                 [_res("k", "understeer", "resolved", present=False)],
                 at=f"2026-07-0{i}T10:00") for i in (1, 2, 3)]
    h = build_history(recs, context=CTX)
    mem = build_engineering_memory(h)
    a = build_progress_metrics(h, mem)
    b = build_progress_metrics(h, mem)
    assert a.content_fingerprint == b.content_fingerprint


# --- scorecard --------------------------------------------------------------
def test_scorecard_insufficient_below_min():
    recs = [_rec(1, 10, "confirmed_improvement", "300",
                 [_res("k", "understeer", "resolved", present=False)], at="2026-07-01T10:00")]
    h = build_history(recs, context=CTX)
    mem = build_engineering_memory(h)
    sc = build_scorecard(h, mem, build_progress_metrics(h, mem))
    assert sc.band == ScorecardBand.INSUFFICIENT


def test_scorecard_strong_when_solving():
    recs = [_rec(i, 10 + i, "confirmed_improvement", str(300 + i),
                 [_res(f"k{i}", "understeer", "resolved", present=False)],
                 at=f"2026-07-0{i}T10:00") for i in (1, 2, 3)]
    h = build_history(recs, context=CTX)
    mem = build_engineering_memory(h)
    sc = build_scorecard(h, mem, build_progress_metrics(h, mem))
    assert sc.band in (ScorecardBand.STRONG, ScorecardBand.PROGRESSING)
    assert sc.issues_solved == 3


# --- comparison -------------------------------------------------------------
def test_compare_latest_sessions_detects_improvement():
    recs = [
        _rec(1, 10, "no_meaningful_change", "300", [_res("k", "understeer", "unchanged")],
             at="2026-07-01T10:00"),
        _rec(2, 11, "confirmed_improvement", "301",
             [_res("k", "understeer", "resolved", present=False)], at="2026-07-05T10:00"),
    ]
    cmp = compare_latest_sessions(build_history(recs, context=CTX))
    assert cmp is not None
    assert cmp.verdict == "improved"
    assert cmp.issues_resolved_delta == 1


def test_compare_none_with_single_session():
    recs = [_rec(1, 10, "confirmed_improvement", "300",
                 [_res("k", "understeer", "resolved", present=False)], at="2026-07-01T10:00")]
    assert compare_latest_sessions(build_history(recs, context=CTX)) is None


def test_module_is_pure():
    src = inspect.getsource(PM)
    for banned in ("import random", "random.", "time.time", "datetime.now",
                   "import sqlite3", "PyQt", "requests", "urllib", "openai"):
        assert banned not in src, banned
