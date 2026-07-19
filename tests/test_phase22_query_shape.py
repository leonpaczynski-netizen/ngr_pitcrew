"""Phase 22 — query-shape: one build per event, constant vs campaign count; renderer DB-free."""
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


FIELDS = {"arb_front": 4, "arb_rear": 4, "brake_bias": 0, "springs_front": 5.0}


def applied():
    d = {"car": "Porsche 911 RSR", "track": "Fuji", "layout_id": "fc", "setup_id": "S1",
         "name": "Base", "revision": 1, "state": "applied", "fields": dict(FIELDS),
         "purpose": "Race"}
    d["setup_hash"] = compute_setup_hash(FIELDS)
    return d


def _seed(db, n, track="Fuji"):
    ctx = MemoryContextKey(driver="d", car="Porsche 911 RSR", track=track, layout_id="fc",
                           discipline="Race", gt7_version="1", compound="RH")
    families = ["rotation", "traction", "braking"]
    for i in range(n):
        rec = build_development_record(
            {"id": f"{track}{i}", "experiment_id": 100 + i, "status": "confirmed_improvement",
             "confidence_level": "high", "scope_fingerprint": "sf",
             "test_session_id": f"{track}s{i}", "protected": [], "failed_directions": []},
            {"id": 100 + i, "scope_fingerprint": "sf", "changes": [{"field": "arb_front"}]},
            context=ctx, scope_fingerprint="sf", working_windows=[],
            residuals=[{"issue_key": f"{track}k{i}", "family": families[i % 3],
                        "issue_type": "entry_understeer", "axle": "front", "phase": "entry",
                        "segment_id": f"T{i}", "corner_name": f"T{i}",
                        "residual_state": "unchanged", "is_new": False, "is_regression": False,
                        "still_present": True, "protected_good": False, "confidence": "high"}],
            recorded_at=f"2026-07-0{1 + (i % 8)}T10:00", session_date=f"2026-07-0{1 + (i % 8)}")
        db._persist_development_record(rec, created_at=rec.recorded_at)


def _kw():
    return dict(car="Porsche 911 RSR", track="Fuji", layout_id="fc", discipline="Race",
                driver="d", gt7_version="1", compound="RH")


def test_query_count_constant_in_campaign_count(tmp_path):
    """Within a single event context, the query count must NOT grow with campaign count."""
    db1 = SessionDB(str(tmp_path / "a.db")); _seed(db1, 1)
    db1._conn = _CountingConn(db1._conn)
    db1.build_programme_knowledge_report(applied_setup=applied(), now_date="2026-07-10", **_kw())
    c1 = db1._conn.selects
    db6 = SessionDB(str(tmp_path / "b.db")); _seed(db6, 6)
    db6._conn = _CountingConn(db6._conn)
    db6.build_programme_knowledge_report(applied_setup=applied(), now_date="2026-07-10", **_kw())
    c6 = db6._conn.selects
    assert c1 == c6, f"N+1 detected (query count grew with campaigns): {c1} -> {c6}"
    db1.close(); db6.close()


def test_empty_cheap(tmp_path):
    db = SessionDB(str(tmp_path / "e.db"))
    db._conn = _CountingConn(db._conn)
    r = db.build_programme_knowledge_report(car="Porsche 911 RSR", track="Fuji",
                                            discipline="Race")
    assert r["ok"] and r["known_domain_count"] == 0
    assert db._conn.selects <= 30
    db.close()


def test_renderer_touches_no_db(tmp_path):
    from strategy.programme_knowledge_report_render import render_report_text
    db = SessionDB(str(tmp_path / "r.db")); _seed(db, 3)
    result = db.build_programme_knowledge_report(applied_setup=applied(),
                                                 now_date="2026-07-10", **_kw())
    db._conn = _CountingConn(db._conn)
    render_report_text(result["programme_knowledge"])
    assert db._conn.selects == 0
    db.close()
