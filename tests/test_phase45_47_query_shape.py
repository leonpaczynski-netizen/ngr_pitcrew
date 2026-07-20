"""Phase 45-47 — query shape, snapshot dedup, explicit-write-only, no-write shadow/runtime."""
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


def test_runtime_report_and_snapshot_view_writes_nothing(tmp_path):
    db = SessionDB(str(tmp_path / "w.db")); seed_contradiction(db, 3, 2)
    db._conn = _NoWriteConn(db._conn)
    assert db.build_assisted_runtime_report(applied_setup=applied(), now_date="2026-07-10",
                                            now_monotonic=1.0, **KW)["ok"]
    db.close()


def test_shadow_validation_writes_nothing(tmp_path):
    db = SessionDB(str(tmp_path / "s.db")); seed_contradiction(db, 3, 2)
    db._conn = _NoWriteConn(db._conn)
    frames = [{"dt": 0.2, "lap": 1, "run_active": True, "segment_type": "straight", "workload": "low",
               "telemetry_fresh": True, "clean_laps": 1}]
    assert db.build_live_shadow_validation_report(frames, applied_setup=applied(),
                                                  now_date="2026-07-10", **KW)["ok"]
    db.close()


def test_viewing_persists_no_snapshot(tmp_path):
    db = SessionDB(str(tmp_path / "v.db")); seed_contradiction(db, 3, 2)
    db.build_assisted_runtime_report(applied_setup=applied(), now_date="2026-07-10", now_monotonic=1.0,
                                     **KW)
    n = db._conn.execute("SELECT COUNT(*) FROM engineering_context_snapshots").fetchone()[0]
    assert n == 0   # explicit-write-only: viewing never captures
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


def test_snapshot_ref_lookup_single_query(tmp_path):
    db = SessionDB(str(tmp_path / "r.db"))
    content = dict(driver="Leon", car="P", track="Fuji", layout_id="fc", discipline="race",
                   gt7_version="1.49")
    db.capture_context_snapshot(content, ref_kind="setup_experiment", ref_key="e1",
                                captured_at="2026-07-20T10:00:00Z")
    db._conn = _CountingConn(db._conn)
    db.get_snapshot_for_ref("setup_experiment", "e1")
    assert db._conn.selects <= 2   # ref lookup + content lookup, no N+1
    db.close()
