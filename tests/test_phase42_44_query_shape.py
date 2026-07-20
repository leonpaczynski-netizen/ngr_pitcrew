"""Phase 42-44 — query shape at larger histories, immutability, explicit-write-only."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from data.session_db import SessionDB
from tests._assurance_pack_helpers import seed_contradiction, applied, KW, _mk


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


def _seed_n(db, n):
    for i in range(n):
        _mk(db, f"k{i}", "confirmed_improvement" if i % 2 else "regression", i)


def test_runtime_report_writes_nothing(tmp_path):
    db = SessionDB(str(tmp_path / "w.db")); seed_contradiction(db, 3, 2)
    db._conn = _NoWriteConn(db._conn)
    assert db.build_assisted_runtime_report(applied_setup=applied(), now_date="2026-07-10",
                                            now_monotonic=1.0, **KW)["ok"]
    assert db.build_material_context_trust_report(applied_setup=applied(), now_date="2026-07-10",
                                                  **KW)["ok"]
    db.close()


def test_material_report_writes_nothing_viewing(tmp_path):
    db = SessionDB(str(tmp_path / "m.db")); seed_contradiction(db, 3, 2)
    db._conn = _NoWriteConn(db._conn)
    assert db.build_material_context_trust_report(applied_setup=applied(), now_date="2026-07-10",
                                                  **KW)["ok"]
    db.close()


def test_query_count_constant_5_50_500(tmp_path):
    def n(records):
        db = SessionDB(str(tmp_path / f"q{records}.db"))
        _seed_n(db, records)
        db._conn = _CountingConn(db._conn)
        db.build_assisted_runtime_report(applied_setup=applied(), now_date="2026-07-10",
                                         now_monotonic=1.0, **KW)
        c = db._conn.selects; db.close(); return c
    c5, c50, c500 = n(5), n(50), n(500)
    assert c5 == c50 == c500, (c5, c50, c500)


def test_empty_history_truthful(tmp_path):
    db = SessionDB(str(tmp_path / "e.db"))
    r = db.build_assisted_runtime_report(applied_setup=applied(), now_date="2026-07-10",
                                         now_monotonic=1.0, **KW)
    assert r["ok"] and r["workflow"]
    db.close()
