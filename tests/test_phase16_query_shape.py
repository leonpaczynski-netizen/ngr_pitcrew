"""Phase 16 — query-shape tests: aggregate reuse, no per-diagnosis / N+1 query."""
import pytest

from data.session_db import SessionDB
from strategy.development_history import MemoryContextKey, build_development_record
from data.applied_checkpoint import compute_setup_hash


class _CountingConn:
    def __init__(self, conn):
        self._conn = conn
        self.selects = 0

    def execute(self, sql, *a, **k):
        if str(sql).lstrip().lower().startswith("select"):
            self.selects += 1
        return self._conn.execute(sql, *a, **k)

    def __getattr__(self, name):
        return getattr(self._conn, name)


CTX = MemoryContextKey(driver="d", car="Porsche 911 RSR", track="Fuji", layout_id="fc",
                       discipline="Race", gt7_version="1", compound="RH")
FIELDS = {"arb_front": 4, "arb_rear": 4, "brake_bias": 0, "springs_front": 5.0}


def applied():
    d = {"car": "Porsche 911 RSR", "track": "Fuji", "layout_id": "fc", "setup_id": "S1",
         "name": "Base", "revision": 1, "state": "applied", "fields": dict(FIELDS),
         "purpose": "Race"}
    d["setup_hash"] = compute_setup_hash(FIELDS)
    return d


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
    return dict(car="Porsche 911 RSR", track="Fuji", layout_id="fc", discipline="Race",
                driver="d", gt7_version="1", compound="RH")


def test_lifecycle_query_count_constant(tmp_path):
    db1 = SessionDB(str(tmp_path / "a.db")); _seed(db1, 1)
    db1._conn = _CountingConn(db1._conn)
    db1.build_engineering_lifecycle(applied_setup=applied(), **_kw())
    c1 = db1._conn.selects
    db5 = SessionDB(str(tmp_path / "b.db")); _seed(db5, 5)
    db5._conn = _CountingConn(db5._conn)
    db5.build_engineering_lifecycle(applied_setup=applied(), **_kw())
    c5 = db5._conn.selects
    assert c1 == c5, f"N+1 detected: {c1} -> {c5}"
    db1.close(); db5.close()


def test_empty_lifecycle_cheap(tmp_path):
    db = SessionDB(str(tmp_path / "e.db"))
    db._conn = _CountingConn(db._conn)
    r = db.build_engineering_lifecycle(car="Porsche 911 RSR", track="Fuji", discipline="Race")
    assert r["ok"] and r["count"] == 0
    assert db._conn.selects <= 12
    db.close()


def test_renderer_touches_no_db(tmp_path):
    from strategy.experiment_lifecycle_render import render_summary_text
    db = SessionDB(str(tmp_path / "r.db")); _seed(db, 2)
    result = db.build_engineering_lifecycle(applied_setup=applied(), **_kw())
    db._conn = _CountingConn(db._conn)
    for s in result["stages"]:
        render_summary_text(s)
    assert db._conn.selects == 0
    db.close()
