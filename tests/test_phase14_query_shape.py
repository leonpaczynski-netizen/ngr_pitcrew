"""Phase 14 — query-shape / performance tests (Section 28).

Prove the intervention build reuses the Phase-13 annotation aggregate exactly once and adds
NO per-hypothesis / per-experiment database query, that the empty path is cheap, and that
the renderer touches no database.
"""
import pytest

from data.session_db import SessionDB
from strategy.development_history import MemoryContextKey, build_development_record


class _CountingConn:
    """Wraps a sqlite connection and counts execute() calls that read data."""
    def __init__(self, conn):
        self._conn = conn
        self.selects = 0

    def execute(self, sql, *a, **k):
        if str(sql).lstrip().lower().startswith("select"):
            self.selects += 1
        return self._conn.execute(sql, *a, **k)

    def __getattr__(self, name):
        return getattr(self._conn, name)


CTX = MemoryContextKey(driver="d", car="c", track="t", layout_id="l", discipline="Race",
                       gt7_version="1", compound="RH")


def _seed(db, n):
    for i in range(n):
        rec = build_development_record(
            {"id": str(i), "experiment_id": 100 + i, "status": "no_meaningful_change",
             "confidence_level": "high", "scope_fingerprint": "sf", "test_session_id": f"s{i}",
             "protected": [], "failed_directions": []},
            {"id": 100 + i, "scope_fingerprint": "sf", "changes": [{"field": "arb_front"}]},
            context=CTX, scope_fingerprint="sf", working_windows=[],
            residuals=[{"issue_key": f"k{i}", "family": "rotation",
                        "issue_type": "entry_understeer", "axle": "front", "phase": "entry",
                        "segment_id": f"T{i}", "corner_name": f"T{i}",
                        "residual_state": "unchanged", "is_new": False, "is_regression": False,
                        "still_present": True, "protected_good": False, "confidence": "high"}],
            recorded_at=f"2026-07-0{1 + i}T10:00", session_date=f"2026-07-0{1 + i}")
        db._persist_development_record(rec, created_at=rec.recorded_at)


def _kw():
    return dict(car="c", track="t", layout_id="l", discipline="Race", driver="d",
                gt7_version="1", compound="RH")


def test_intervention_adds_no_query_over_annotation(tmp_path):
    db = SessionDB(str(tmp_path / "s.db"))
    _seed(db, 3)
    real = db._conn
    db._conn = _CountingConn(real)
    db.build_mechanism_annotations(**_kw())
    ann_selects = db._conn.selects
    db._conn.selects = 0
    db.build_intervention_hypotheses(**_kw())
    hyp_selects = db._conn.selects
    db._conn = real
    # Phase 14 reuses the annotation aggregate; it issues the SAME read queries (no extra)
    assert hyp_selects == ann_selects
    db.close()


def test_query_count_constant_regardless_of_diagnosis_count(tmp_path):
    # more diagnoses must NOT create per-hypothesis / per-experiment queries
    db1 = SessionDB(str(tmp_path / "a.db"))
    _seed(db1, 1)
    db1._conn = _CountingConn(db1._conn)
    db1.build_intervention_hypotheses(**_kw())
    c1 = db1._conn.selects

    db5 = SessionDB(str(tmp_path / "b.db"))
    _seed(db5, 5)
    db5._conn = _CountingConn(db5._conn)
    db5.build_intervention_hypotheses(**_kw())
    c5 = db5._conn.selects

    assert c1 == c5, f"query count grew with diagnoses: {c1} -> {c5} (N+1 detected)"
    db1.close(); db5.close()


def test_empty_db_is_cheap(tmp_path):
    db = SessionDB(str(tmp_path / "e.db"))
    db._conn = _CountingConn(db._conn)
    r = db.build_intervention_hypotheses(car="c", track="t", discipline="Race")
    assert r["ok"] and r["count"] == 0
    # a handful of scoped reads, never a per-experiment scan loop
    assert db._conn.selects <= 6
    db.close()


def test_renderer_touches_no_database(tmp_path):
    from strategy.intervention_hypothesis_render import render_set_text
    db = SessionDB(str(tmp_path / "r.db"))
    _seed(db, 2)
    result = db.build_intervention_hypotheses(**_kw())
    db._conn = _CountingConn(db._conn)   # count from here on
    for s in result["hypothesis_sets"]:
        render_set_text(s)
    assert db._conn.selects == 0
    db.close()
