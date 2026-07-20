"""Phase 36-38 — query-shape: chain once, no lower public builders, constant query count."""
from data.session_db import SessionDB
from tests._assurance_pack_helpers import seed_contradiction, applied, KW


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


def _lower_names():
    return ("build_programme_transfer_report", "build_programme_engineering_playbook",
            "build_programme_knowledge_timeline", "build_programme_revalidation_report",
            "build_programme_evidence_coverage_report", "build_programme_contradiction_report",
            "build_programme_knowledge_readiness_report", "build_programme_assumption_register",
            "build_programme_assurance_report", "build_assurance_engineering_priority_report",
            "build_assurance_chain_export_report")


def test_brief_builds_phase22_once_no_lower_entries(monkeypatch, tmp_path):
    db = SessionDB(str(tmp_path / "a.db")); seed_contradiction(db, 3, 2)
    calls = {"pk": 0, "lower": 0}
    real = db.build_programme_knowledge_report
    monkeypatch.setattr(db, "build_programme_knowledge_report",
                        lambda *a, **k: (calls.__setitem__("pk", calls["pk"] + 1), real(*a, **k))[1])
    for name in _lower_names():
        monkeypatch.setattr(db, name,
                            (lambda n: (lambda *a, **k: calls.__setitem__("lower", calls["lower"] + 1)))(name))
    r = db.build_race_engineer_team_brief(applied_setup=applied(), now_date="2026-07-10", **KW)
    assert r["ok"] and calls["pk"] == 1 and calls["lower"] == 0
    db.close()


def test_brief_query_count_constant_small_vs_large(tmp_path):
    def n(nc, nr):
        db = SessionDB(str(tmp_path / f"q{nc}_{nr}.db")); seed_contradiction(db, nc, nr)
        db._conn = _CountingConn(db._conn)
        db.build_race_engineer_team_brief(applied_setup=applied(), now_date="2026-07-10", **KW)
        c = db._conn.selects; db.close(); return c
    assert n(3, 2) == n(9, 7)


def test_brief_writes_nothing(tmp_path):
    db = SessionDB(str(tmp_path / "w.db")); seed_contradiction(db, 3, 2)

    class _NoWriteConn:
        def __init__(self, conn):
            self._conn = conn

        def execute(self, sql, *a, **k):
            low = str(sql).lstrip().lower()
            assert not low.startswith(("insert", "update", "delete", "create", "drop", "alter")), sql
            return self._conn.execute(sql, *a, **k)

        def __getattr__(self, name):
            return getattr(self._conn, name)

    db._conn = _NoWriteConn(db._conn)
    r = db.build_race_engineer_team_brief(applied_setup=applied(), now_date="2026-07-10", **KW)
    assert r["ok"]
    db.close()


def test_empty_programme_truthful(tmp_path):
    db = SessionDB(str(tmp_path / "e.db"))
    r = db.build_race_engineer_team_brief(applied_setup=applied(), now_date="2026-07-10", **KW)
    assert r["ok"] and r["brief"] is not None
    assert r["brief"]["empty_state"]  # honest collection plan, no fabricated setup
    db.close()
