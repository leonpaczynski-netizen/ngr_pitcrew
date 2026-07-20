"""Phase 39-41 — query-shape: chain once, portfolio once, constant count, no writes."""
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


class _NoWriteConn:
    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, *a, **k):
        low = str(sql).lstrip().lower()
        assert not low.startswith(("insert", "update", "delete", "create", "drop", "alter")), sql
        return self._conn.execute(sql, *a, **k)

    def __getattr__(self, name):
        return getattr(self._conn, name)


def _seeded(tmp_path, nc=3, nr=2, name="q"):
    db = SessionDB(str(tmp_path / f"{name}.db")); seed_contradiction(db, nc, nr); return db


def test_evidence_report_writes_nothing(tmp_path):
    db = _seeded(tmp_path); db._conn = _NoWriteConn(db._conn)
    assert db.build_context_scoped_evidence_report(applied_setup=applied(), now_date="2026-07-10",
                                                   **KW)["ok"]
    db.close()


def test_run_plan_writes_nothing(tmp_path):
    db = _seeded(tmp_path, name="r"); db._conn = _NoWriteConn(db._conn)
    assert db.build_engineering_run_plan_report(applied_setup=applied(), now_date="2026-07-10",
                                                **KW)["ok"]
    db.close()


def test_workflow_writes_nothing_when_viewing(tmp_path):
    db = _seeded(tmp_path, name="w"); db._conn = _NoWriteConn(db._conn)
    r = db.build_closed_loop_workflow_report(observation=None, applied_setup=applied(),
                                             now_date="2026-07-10", **KW)
    assert r["ok"]
    db.close()


def test_workflow_query_count_constant_small_vs_large(tmp_path):
    def n(nc, nr):
        db = _seeded(tmp_path, nc, nr, name=f"c{nc}_{nr}")
        db._conn = _CountingConn(db._conn)
        db.build_closed_loop_workflow_report(observation=None, applied_setup=applied(),
                                             now_date="2026-07-10", **KW)
        c = db._conn.selects; db.close(); return c
    assert n(3, 2) == n(9, 7)


def test_evidence_exact_fingerprint_present(tmp_path):
    db = _seeded(tmp_path, name="fp")
    r = db.build_context_scoped_evidence_report(applied_setup=applied(), now_date="2026-07-10", **KW)
    assert r["exact_content_fingerprint"] and r["content_fingerprint"]
    db.close()


def test_empty_history_is_truthful(tmp_path):
    db = SessionDB(str(tmp_path / "e.db"))
    r = db.build_closed_loop_workflow_report(observation=None, applied_setup=applied(),
                                             now_date="2026-07-10", **KW)
    assert r["ok"] and r["posture"] in ("collect", "protect")
    db.close()
