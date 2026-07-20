"""Phases 33-35 — query-shape tests: chain once, no lower entries, zero extra reads, constant count."""
import hashlib

from data.session_db import SessionDB
from tests._assurance_pack_helpers import (
    seed_contradiction, seed_negative_only, applied, KW, real_export,
)


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


def _lower_names():
    return ("build_programme_transfer_report", "build_programme_engineering_playbook",
            "build_programme_knowledge_timeline", "build_programme_revalidation_report",
            "build_programme_evidence_coverage_report", "build_programme_contradiction_report",
            "build_programme_knowledge_readiness_report", "build_programme_assumption_register",
            "build_programme_assurance_report", "build_assurance_engineering_priority_report")


def test_export_phase22_once_no_lower_entries(monkeypatch, tmp_path):
    db = SessionDB(str(tmp_path / "a.db")); seed_contradiction(db, 3, 2)
    calls = {"pk": 0, "lower": 0}
    real = db.build_programme_knowledge_report
    monkeypatch.setattr(db, "build_programme_knowledge_report",
                        lambda *a, **k: (calls.__setitem__("pk", calls["pk"] + 1), real(*a, **k))[1])
    for name in _lower_names():
        monkeypatch.setattr(db, name,
                            (lambda n: (lambda *a, **k: calls.__setitem__("lower", calls["lower"] + 1)))(name))
    db.build_assurance_chain_export_report(applied_setup=applied(), now_date="2026-07-10", **KW)
    assert calls["pk"] == 1 and calls["lower"] == 0
    db.close()


def test_package_and_comparison_phase22_once_no_lower_entries(monkeypatch, tmp_path):
    db = SessionDB(str(tmp_path / "b.db")); seed_contradiction(db, 3, 2)
    export = real_export(db)  # a valid baseline
    calls = {"pk": 0, "lower": 0}
    real = db.build_programme_knowledge_report
    monkeypatch.setattr(db, "build_programme_knowledge_report",
                        lambda *a, **k: (calls.__setitem__("pk", calls["pk"] + 1), real(*a, **k))[1])
    for name in _lower_names():
        monkeypatch.setattr(db, name,
                            (lambda n: (lambda *a, **k: calls.__setitem__("lower", calls["lower"] + 1)))(name))
    import json
    db.build_assurance_review_package_report(baseline=json.dumps(export), applied_setup=applied(),
                                             now_date="2026-07-10", **KW)
    assert calls["pk"] == 1 and calls["lower"] == 0
    db.close()


def test_query_count_constant_small_vs_large(tmp_path):
    def n(nc, nr):
        db = SessionDB(str(tmp_path / f"q{nc}_{nr}.db")); seed_contradiction(db, nc, nr)
        db._conn = _CountingConn(db._conn)
        db.build_assurance_review_package_report(baseline=None, applied_setup=applied(),
                                                 now_date="2026-07-10", **KW)
        c = db._conn.selects; db.close(); return c
    assert n(3, 2) == n(9, 7)


def test_history_reads_are_bounded_full_scans(tmp_path):
    db = SessionDB(str(tmp_path / "h.db")); seed_contradiction(db, 3, 2)
    db._conn = _CountingConn(db._conn)
    db.build_assurance_chain_export_report(applied_setup=applied(), now_date="2026-07-10", **KW)
    reads = [s for s in db._conn.sql_log if "engineering_development_records" in s.lower()]
    assert reads and all("where id =" not in s.lower() and "limit 1" not in s.lower() for s in reads)
    db.close()


def test_baseline_validation_performs_no_db_read(tmp_path):
    db = SessionDB(str(tmp_path / "v.db")); seed_contradiction(db, 3, 2)
    db._conn = _CountingConn(db._conn)
    before = db._conn.selects
    # a malformed baseline must be rejected by the pure loader BEFORE any chain read
    r = db.build_assurance_snapshot_comparison_report("{bad json", applied_setup=applied(),
                                                      now_date="2026-07-10", **KW)
    assert not r["comparison"] and r["baseline_valid"] is False
    assert db._conn.selects == before   # zero DB reads for the invalid-baseline path
    db.close()


def test_no_db_writes_and_hash_unchanged(tmp_path):
    import os
    p = str(tmp_path / "w.db")
    db = SessionDB(p); seed_contradiction(db, 4, 2); db.close()
    h0 = hashlib.sha256(open(p, "rb").read()).hexdigest()
    db = SessionDB(p)
    uv0 = db._conn.execute("PRAGMA user_version").fetchone()[0]
    db.build_assurance_chain_export_report(applied_setup=applied(), now_date="2026-07-10", **KW)
    export = real_export(db)
    import json
    db.build_assurance_snapshot_comparison_report(json.dumps(export), applied_setup=applied(),
                                                  now_date="2026-07-10", **KW)
    db.build_assurance_review_package_report(baseline=None, applied_setup=applied(),
                                             now_date="2026-07-10", **KW)
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == uv0 == 28
    db.close()
    assert hashlib.sha256(open(p, "rb").read()).hexdigest() == h0


def test_empty_and_negative_only_programmes(tmp_path):
    # empty -> truthful None
    db = SessionDB(str(tmp_path / "e.db"))
    r = db.build_assurance_chain_export_report(car="X", track="Y", discipline="Race")
    assert r["ok"] and r["export"] is None
    db.close()
    # negative-only -> still exportable (Phase-29 gate not weakened)
    db2 = SessionDB(str(tmp_path / "n.db")); seed_negative_only(db2, 3)
    r2 = db2.build_assurance_chain_export_report(applied_setup=applied(), now_date="2026-07-10", **KW)
    assert r2["ok"] and r2["export"] is not None
    db2.close()
