"""Phase 28 — integration / query-shape tests.

Phase 22 built at most once via the shared knowledge chain; Phase 23/24/25/26/27 SessionDB entries
never called; in-memory reuse; constant query count vs event count (no N+1); renderer zero DB
access; no writes; DB hash / table counts / user_version unchanged.
"""
import hashlib

from data.session_db import SessionDB
from strategy.development_history import MemoryContextKey, build_development_record
from data.applied_checkpoint import compute_setup_hash

PORSCHE = "Porsche 911 RSR (991) '17"
FIELDS = {"arb_front": 4, "lsd_accel": 20}


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


def _seed(db, n, track="Fuji"):
    ctx = MemoryContextKey(driver="d", car=PORSCHE, track=track, layout_id="fc", discipline="Race",
                           gt7_version="1", compound="RH")
    for i in range(n):
        rec = build_development_record(
            {"id": f"{track}{i}", "experiment_id": 100 + i, "status": "confirmed_improvement",
             "confidence_level": "high", "scope_fingerprint": f"sf{i}",
             "test_session_id": f"{track}s{i}", "protected": [], "failed_directions": []},
            {"id": 100 + i, "scope_fingerprint": f"sf{i}", "changes": [{"field": "arb_front"}]},
            context=ctx, scope_fingerprint=f"sf{i}", working_windows=[],
            residuals=[{"issue_key": f"k{track}{i}", "family": "rotation",
                        "issue_type": "entry_understeer", "axle": "front", "phase": "entry",
                        "segment_id": f"T{i}", "corner_name": f"T{i}", "residual_state": "unchanged",
                        "is_new": False, "is_regression": False, "still_present": True,
                        "protected_good": False, "confidence": "high"}],
            recorded_at=f"2026-07-0{1 + (i % 8)}T10:00", session_date=f"2026-07-0{1 + (i % 8)}")
        db._persist_development_record(rec, created_at=rec.recorded_at)


def _kw():
    return dict(car=PORSCHE, track="Fuji", layout_id="fc", discipline="Race", driver="d",
                gt7_version="1", compound="RH")


def test_query_count_constant_in_event_count(tmp_path):
    db1 = SessionDB(str(tmp_path / "a.db")); _seed(db1, 1)
    db1._conn = _CountingConn(db1._conn)
    db1.build_programme_knowledge_readiness_report(applied_setup=applied(), now_date="2026-07-10",
                                                   **_kw())
    c1 = db1._conn.selects
    db6 = SessionDB(str(tmp_path / "b.db")); _seed(db6, 6)
    db6._conn = _CountingConn(db6._conn)
    db6.build_programme_knowledge_readiness_report(applied_setup=applied(), now_date="2026-07-10",
                                                   **_kw())
    c6 = db6._conn.selects
    assert c1 == c6, f"N+1 detected (query count grew with events): {c1} -> {c6}"
    db1.close(); db6.close()


def test_phase22_once_lower_db_entries_never_called(monkeypatch, tmp_path):
    db = SessionDB(str(tmp_path / "c.db")); _seed(db, 3)
    calls = {"pk": 0, "transfer_db": 0, "playbook_db": 0, "timeline_db": 0, "reval_db": 0,
             "cov_db": 0}
    real_pk = db.build_programme_knowledge_report
    monkeypatch.setattr(db, "build_programme_knowledge_report",
                        lambda *a, **k: (calls.__setitem__("pk", calls["pk"] + 1), real_pk(*a, **k))[1])
    monkeypatch.setattr(db, "build_programme_transfer_report",
                        lambda *a, **k: calls.__setitem__("transfer_db", calls["transfer_db"] + 1))
    monkeypatch.setattr(db, "build_programme_engineering_playbook",
                        lambda *a, **k: calls.__setitem__("playbook_db", calls["playbook_db"] + 1))
    monkeypatch.setattr(db, "build_programme_knowledge_timeline",
                        lambda *a, **k: calls.__setitem__("timeline_db", calls["timeline_db"] + 1))
    monkeypatch.setattr(db, "build_programme_revalidation_report",
                        lambda *a, **k: calls.__setitem__("reval_db", calls["reval_db"] + 1))
    monkeypatch.setattr(db, "build_programme_evidence_coverage_report",
                        lambda *a, **k: calls.__setitem__("cov_db", calls["cov_db"] + 1))
    db.build_programme_knowledge_readiness_report(applied_setup=applied(), now_date="2026-07-10",
                                                  **_kw())
    assert calls["pk"] == 1, f"Phase-22 built {calls['pk']} times (must be 1)"
    for k in ("transfer_db", "playbook_db", "timeline_db", "reval_db", "cov_db"):
        assert calls[k] == 0, f"{k} must not be called"
    db.close()


def test_renderer_touches_no_db(tmp_path):
    from strategy.programme_readiness_report_render import render_readiness_text
    db = SessionDB(str(tmp_path / "r.db")); _seed(db, 3)
    result = db.build_programme_knowledge_readiness_report(applied_setup=applied(),
                                                          now_date="2026-07-10", **_kw())
    db._conn = _CountingConn(db._conn)
    render_readiness_text(result["readiness"] or {})
    assert db._conn.selects == 0
    db.close()


def test_no_writes_db_hash_and_counts_unchanged(tmp_path):
    p = str(tmp_path / "w.db")
    db = SessionDB(p); _seed(db, 4)
    db.close()
    h_before = hashlib.sha256(open(p, "rb").read()).hexdigest()
    db = SessionDB(p)
    counts_before = {t: db._conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                     for t in ("engineering_development_records", "engineering_campaign_registry",
                               "setup_experiments", "setup_snapshots", "learning_outcomes")}
    uv_before = db._conn.execute("PRAGMA user_version").fetchone()[0]
    db.build_programme_knowledge_readiness_report(applied_setup=applied(), now_date="2026-07-10",
                                                  **_kw())
    counts_after = {t: db._conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                    for t in counts_before}
    assert counts_after == counts_before
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == uv_before == 28
    db.close()
    assert hashlib.sha256(open(p, "rb").read()).hexdigest() == h_before


def test_empty_cheap(tmp_path):
    db = SessionDB(str(tmp_path / "e.db"))
    db._conn = _CountingConn(db._conn)
    r = db.build_programme_knowledge_readiness_report(car=PORSCHE, track="Fuji", discipline="Race")
    assert r["ok"] and r["domain_count"] == 0 and r["grade"] == "insufficient_evidence"
    assert db._conn.selects <= 40
    db.close()


def test_result_shape(tmp_path):
    db = SessionDB(str(tmp_path / "s.db")); _seed(db, 3)
    r = db.build_programme_knowledge_readiness_report(applied_setup=applied(), now_date="2026-07-10",
                                                     **_kw())
    assert set(r) >= {"ok", "readiness", "grade", "domain_count", "content_fingerprint"}
    assert r["ok"] and r["domain_count"] >= 1
    assert r["content_fingerprint"] == r["readiness"]["content_fingerprint"]
    assert r["grade"] == r["readiness"]["programme_grade"]
    db.close()
