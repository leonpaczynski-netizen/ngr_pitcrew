"""Phase 24 — query-shape: bounded reads, no N+1, Phase-22/23 built at most once, no per-target reads."""
import pytest

from data.session_db import SessionDB
from strategy.development_history import MemoryContextKey, build_development_record
from data.applied_checkpoint import compute_setup_hash

PORSCHE = "Porsche 911 RSR (991) '17"
FIELDS = {"arb_front": 4, "lsd_accel": 20, "springs_front": 5.0}


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


def applied():
    d = {"car": PORSCHE, "track": "Fuji", "layout_id": "fc", "setup_id": "S1", "name": "B",
         "revision": 1, "state": "applied", "fields": dict(FIELDS), "purpose": "Race"}
    d["setup_hash"] = compute_setup_hash(FIELDS)
    return d


def _seed(db, n, car=PORSCHE, track="Fuji"):
    ctx = MemoryContextKey(driver="d", car=car, track=track, layout_id="fc", discipline="Race",
                           gt7_version="1", compound="RH")
    fams = ["rotation", "traction", "braking"]
    for i in range(n):
        rec = build_development_record(
            {"id": f"{car}{i}", "experiment_id": 100 + i, "status": "confirmed_improvement",
             "confidence_level": "high", "scope_fingerprint": "sf", "test_session_id": f"s{i}",
             "protected": [], "failed_directions": []},
            {"id": 100 + i, "scope_fingerprint": "sf", "changes": [{"field": "arb_front"}]},
            context=ctx, scope_fingerprint="sf", working_windows=[],
            residuals=[{"issue_key": f"k{car}{i}", "family": fams[i % 3],
                        "issue_type": "entry_understeer", "axle": "front", "phase": "entry",
                        "segment_id": f"T{i}", "corner_name": f"T{i}", "residual_state": "unchanged",
                        "is_new": False, "is_regression": False, "still_present": True,
                        "protected_good": False, "confidence": "high"}],
            recorded_at=f"2026-07-0{1 + (i % 8)}T10:00", session_date=f"2026-07-0{1 + (i % 8)}")
        db._persist_development_record(rec, created_at=rec.recorded_at)


def _kw():
    return dict(car=PORSCHE, track="Fuji", layout_id="fc", discipline="Race", driver="d",
                gt7_version="1", compound="RH")


def test_query_count_constant_in_campaign_count(tmp_path):
    db1 = SessionDB(str(tmp_path / "a.db")); _seed(db1, 1)
    db1._conn = _CountingConn(db1._conn)
    db1.build_programme_engineering_playbook(applied_setup=applied(), now_date="2026-07-10", **_kw())
    c1 = db1._conn.selects
    db6 = SessionDB(str(tmp_path / "b.db")); _seed(db6, 6)
    db6._conn = _CountingConn(db6._conn)
    db6.build_programme_engineering_playbook(applied_setup=applied(), now_date="2026-07-10", **_kw())
    c6 = db6._conn.selects
    assert c1 == c6, f"N+1 detected (query count grew with campaigns): {c1} -> {c6}"
    db1.close(); db6.close()


def test_phase22_built_at_most_once(monkeypatch, tmp_path):
    """The playbook must build the Phase-22 knowledge report exactly once, and NOT call the
    Phase-23 SessionDB entry point (which would rebuild Phase 22 a second time)."""
    db = SessionDB(str(tmp_path / "c.db")); _seed(db, 2)
    calls = {"pk": 0, "transfer_db": 0}
    real_pk = db.build_programme_knowledge_report
    real_tr = db.build_programme_transfer_report

    def _pk(*a, **k):
        calls["pk"] += 1
        return real_pk(*a, **k)

    def _tr(*a, **k):
        calls["transfer_db"] += 1
        return real_tr(*a, **k)

    monkeypatch.setattr(db, "build_programme_knowledge_report", _pk)
    monkeypatch.setattr(db, "build_programme_transfer_report", _tr)
    db.build_programme_engineering_playbook(applied_setup=applied(), now_date="2026-07-10", **_kw())
    assert calls["pk"] == 1, f"Phase-22 built {calls['pk']} times (must be exactly 1)"
    assert calls["transfer_db"] == 0, "must NOT call the Phase-23 DB entry (rebuilds Phase 22)"
    db.close()


def test_no_reads_in_target_render_loop(tmp_path):
    """Rendering the playbook (which loops over targets/themes) must touch no DB."""
    from strategy.engineering_playbook_render import render_playbook_text
    db = SessionDB(str(tmp_path / "r.db")); _seed(db, 3)
    result = db.build_programme_engineering_playbook(applied_setup=applied(),
                                                     now_date="2026-07-10", **_kw())
    db._conn = _CountingConn(db._conn)
    render_playbook_text(result["playbook"] or {})
    assert db._conn.selects == 0
    db.close()


def test_empty_and_single_cheap(tmp_path):
    db = SessionDB(str(tmp_path / "e.db"))
    db._conn = _CountingConn(db._conn)
    r = db.build_programme_engineering_playbook(car=PORSCHE, track="Fuji", discipline="Race")
    assert r["ok"] and r["theme_count"] == 0
    assert db._conn.selects <= 34
    db.close()
