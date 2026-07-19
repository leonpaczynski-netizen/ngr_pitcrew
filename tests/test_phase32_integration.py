"""Phase 32 — integration / query-shape tests.

Phase 22 built at most once via the shared knowledge chain; Phase 23/24/25/26/27/28/29/30/31 SessionDB
entries never called; in-memory reuse; constant query count vs event count (no N+1); one bounded bulk
read; renderer zero DB access; no writes; DB hash / table counts / user_version unchanged; negative-
only programmes still build; empty programmes return the truthful empty result.
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
        self.sql_log = []

    def execute(self, sql, *a, **k):
        if str(sql).lstrip().lower().startswith("select"):
            self.selects += 1
            self.sql_log.append(str(sql))
        return self._conn.execute(sql, *a, **k)

    def __getattr__(self, name):
        return getattr(self._conn, name)


def applied():
    d = {"car": PORSCHE, "track": "Fuji", "layout_id": "fc", "setup_id": "S1", "name": "B",
         "revision": 1, "state": "applied", "fields": dict(FIELDS), "purpose": "Race"}
    d["setup_hash"] = compute_setup_hash(FIELDS)
    return d


def _mk(db, key, outcome, i, fam="rotation", field="arb_front"):
    ctx = MemoryContextKey(driver="d", car=PORSCHE, track="Fuji", layout_id="fc", discipline="Race",
                           gt7_version="1", compound="RH")
    rec = build_development_record(
        {"id": key, "experiment_id": 100 + i, "status": outcome, "confidence_level": "high",
         "scope_fingerprint": f"sf{key}", "test_session_id": f"s{key}", "protected": [],
         "failed_directions": []},
        {"id": 100 + i, "scope_fingerprint": f"sf{key}", "changes": [{"field": field}]},
        context=ctx, scope_fingerprint=f"sf{key}", working_windows=[],
        residuals=[{"issue_key": f"k{key}", "family": fam, "issue_type": "entry_understeer",
                    "axle": "front", "phase": "entry", "segment_id": f"T{i}", "corner_name": f"T{i}",
                    "residual_state": "unchanged", "is_new": False,
                    "is_regression": outcome == "regression", "still_present": True,
                    "protected_good": False, "confidence": "high"}],
        recorded_at=f"2026-07-0{1 + (i % 8)}T10:00", session_date=f"2026-07-0{1 + (i % 8)}")
    db._persist_development_record(rec, created_at=rec.recorded_at)


def _seed(db, n_confirm=3, n_regress=2):
    fams = ["rotation", "traction", "braking"]
    for i in range(n_confirm):
        _mk(db, f"c{i}", "confirmed_improvement", i, fam=fams[i % 3])
    for i in range(n_regress):
        _mk(db, f"r{i}", "regression", i + 3, fam="rotation")


def _seed_negative_only(db, n=3):
    for i in range(n):
        _mk(db, f"neg{i}", "regression", i)


def _kw():
    return dict(car=PORSCHE, track="Fuji", layout_id="fc", discipline="Race", driver="d",
                gt7_version="1", compound="RH")


def test_query_count_constant_in_event_count(tmp_path):
    db1 = SessionDB(str(tmp_path / "a.db")); _seed(db1, 3, 1)
    db1._conn = _CountingConn(db1._conn)
    db1.build_assurance_engineering_priority_report(applied_setup=applied(), now_date="2026-07-10",
                                                    **_kw())
    c1 = db1._conn.selects
    db6 = SessionDB(str(tmp_path / "b.db")); _seed(db6, 8, 6)
    db6._conn = _CountingConn(db6._conn)
    db6.build_assurance_engineering_priority_report(applied_setup=applied(), now_date="2026-07-10",
                                                    **_kw())
    c6 = db6._conn.selects
    assert c1 == c6, f"N+1 detected: {c1} -> {c6}"
    db1.close(); db6.close()


def test_bounded_bulk_history_reads_are_constant_and_full_scans(tmp_path):
    """The chain's reads over the immutable development records are BOUNDED full-table scans (not
    per-record lookups) and their count is CONSTANT as history grows - Phase 32 itself adds none."""
    def _dev_reads(n_conf, n_reg):
        db = SessionDB(str(tmp_path / f"h{n_conf}_{n_reg}.db")); _seed(db, n_conf, n_reg)
        db._conn = _CountingConn(db._conn)
        db.build_assurance_engineering_priority_report(applied_setup=applied(),
                                                       now_date="2026-07-10", **_kw())
        reads = [s for s in db._conn.sql_log if "engineering_development_records" in s.lower()]
        db.close()
        return reads

    small = _dev_reads(3, 2)
    large = _dev_reads(9, 7)
    # same (small, constant) number of reads regardless of history size -> no N+1
    assert len(small) == len(large)
    assert len(small) <= 4, f"too many history reads: {len(small)}"
    # every history read is a bounded full-table scan, never a per-id / per-candidate lookup
    for s in small:
        low = s.lower()
        assert "where id =" not in low and "where id=" not in low
        assert "limit 1" not in low


def test_phase22_once_lower_db_entries_never_called(monkeypatch, tmp_path):
    db = SessionDB(str(tmp_path / "c.db")); _seed(db, 3, 2)
    calls = {"pk": 0}
    real_pk = db.build_programme_knowledge_report
    monkeypatch.setattr(db, "build_programme_knowledge_report",
                        lambda *a, **k: (calls.__setitem__("pk", calls["pk"] + 1), real_pk(*a, **k))[1])
    lower = ("build_programme_transfer_report", "build_programme_engineering_playbook",
             "build_programme_knowledge_timeline", "build_programme_revalidation_report",
             "build_programme_evidence_coverage_report", "build_programme_contradiction_report",
             "build_programme_knowledge_readiness_report", "build_programme_assumption_register",
             "build_programme_assurance_report")
    for name in lower:
        calls[name] = 0
        monkeypatch.setattr(db, name,
                            (lambda n: (lambda *a, **kw: calls.__setitem__(n, calls[n] + 1)))(name))
    db.build_assurance_engineering_priority_report(applied_setup=applied(), now_date="2026-07-10",
                                                   **_kw())
    assert calls["pk"] == 1, f"Phase-22 built {calls['pk']} times (must be 1)"
    for name in lower:
        assert calls[name] == 0, f"{name} must not be called"
    db.close()


def test_renderer_touches_no_db(tmp_path):
    from strategy.assurance_engineering_priority_render import render_priority_text
    db = SessionDB(str(tmp_path / "r.db")); _seed(db, 3, 2)
    result = db.build_assurance_engineering_priority_report(applied_setup=applied(),
                                                            now_date="2026-07-10", **_kw())
    db._conn = _CountingConn(db._conn)
    render_priority_text(result.get("priority") or {})
    assert db._conn.selects == 0
    db.close()


def test_no_writes_db_hash_and_counts_unchanged(tmp_path):
    p = str(tmp_path / "w.db")
    db = SessionDB(p); _seed(db, 4, 2)
    db.close()
    h_before = hashlib.sha256(open(p, "rb").read()).hexdigest()
    db = SessionDB(p)
    counts_before = {t: db._conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                     for t in ("engineering_development_records", "engineering_campaign_registry",
                               "setup_experiments", "setup_snapshots", "learning_outcomes")}
    uv_before = db._conn.execute("PRAGMA user_version").fetchone()[0]
    db.build_assurance_engineering_priority_report(applied_setup=applied(), now_date="2026-07-10",
                                                   **_kw())
    counts_after = {t: db._conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                    for t in counts_before}
    assert counts_after == counts_before
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == uv_before == 26
    db.close()
    assert hashlib.sha256(open(p, "rb").read()).hexdigest() == h_before


def test_empty_cheap_and_truthful(tmp_path):
    db = SessionDB(str(tmp_path / "e.db"))
    db._conn = _CountingConn(db._conn)
    r = db.build_assurance_engineering_priority_report(car=PORSCHE, track="Fuji", discipline="Race")
    assert r["ok"] and r["candidate_count"] == 0 and r["grade"] == "insufficient_evidence"
    assert r["priority"] is None
    assert db._conn.selects <= 40
    db.close()


def test_negative_only_programme_still_builds(tmp_path):
    db = SessionDB(str(tmp_path / "n.db")); _seed_negative_only(db, 3)
    r = db.build_assurance_engineering_priority_report(applied_setup=applied(),
                                                       now_date="2026-07-10", **_kw())
    # negative-only evidence must remain analysable (chain not gated out)
    assert r["ok"] and r["priority"] is not None
    db.close()


def test_result_shape(tmp_path):
    db = SessionDB(str(tmp_path / "s.db")); _seed(db, 3, 2)
    r = db.build_assurance_engineering_priority_report(applied_setup=applied(),
                                                       now_date="2026-07-10", **_kw())
    assert set(r) >= {"ok", "priority", "grade", "candidate_count", "content_fingerprint"}
    assert r["ok"]
    assert r["content_fingerprint"] == r["priority"]["content_fingerprint"]
    assert r["grade"] == r["priority"]["assurance_grade"]
    db.close()
