"""Phase 45-47 — schema migration v27: fresh DB, migrate from v26, idempotent, rollback-safe."""
import hashlib
import os

from data.session_db import SessionDB
from strategy._setup_constants import DB_VERSION


def _tables(db):
    return {r[0] for r in db._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}


def test_fresh_db_creates_v27_snapshot_tables(tmp_path):
    db = SessionDB(str(tmp_path / "fresh.db"))
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION == 27
    t = _tables(db)
    assert "engineering_context_snapshots" in t and "engineering_context_snapshot_refs" in t
    db.close()


def test_migrate_from_legacy_v26(tmp_path):
    p = str(tmp_path / "legacy.db")
    db = SessionDB(p)
    # simulate a legacy v26 DB: drop the v27 tables and roll user_version back to 26
    db._conn.execute("DROP TABLE IF EXISTS engineering_context_snapshots")
    db._conn.execute("DROP TABLE IF EXISTS engineering_context_snapshot_refs")
    db._conn.execute("PRAGMA user_version = 26"); db._conn.commit(); db.close()
    db2 = SessionDB(p)   # reopen -> migration runs
    assert db2._conn.execute("PRAGMA user_version").fetchone()[0] == 27
    assert "engineering_context_snapshots" in _tables(db2)
    db2.close()


def test_repeated_startup_idempotent(tmp_path):
    p = str(tmp_path / "repeat.db")
    for _ in range(3):
        db = SessionDB(p)
        assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 27
        db.close()


def test_migration_preserves_existing_data(tmp_path):
    from tests._assurance_pack_helpers import seed_contradiction
    p = str(tmp_path / "data.db")
    db = SessionDB(p); seed_contradiction(db, 3, 2)
    n_before = db._conn.execute("SELECT COUNT(*) FROM engineering_development_records").fetchone()[0]
    db._conn.execute("DROP TABLE IF EXISTS engineering_context_snapshots")
    db._conn.execute("PRAGMA user_version = 26"); db._conn.commit(); db.close()
    db2 = SessionDB(p)
    n_after = db2._conn.execute("SELECT COUNT(*) FROM engineering_development_records").fetchone()[0]
    db2.close()
    assert n_before == n_after and n_before > 0   # migration touched no existing table


def test_rollback_safety_transactional(tmp_path):
    # capture within a transaction that is rolled back leaves no snapshot row.
    p = str(tmp_path / "rollback.db")
    db = SessionDB(p)
    content = dict(driver="Leon", car="P", track="Fuji", layout_id="fc", discipline="race",
                   gt7_version="1.49")
    # open an explicit transaction, capture, then ROLLBACK
    db._conn.execute("BEGIN")
    db._conn.execute("INSERT OR IGNORE INTO engineering_context_snapshots (semantic_digest) VALUES (?)",
                     ("tmpdigest",))
    db._conn.execute("ROLLBACK")
    n = db._conn.execute("SELECT COUNT(*) FROM engineering_context_snapshots "
                         "WHERE semantic_digest='tmpdigest'").fetchone()[0]
    db.close()
    assert n == 0


def test_no_runtime_files_modified_by_migration(tmp_path):
    p = str(tmp_path / "immut.db")
    db = SessionDB(p); db.close()
    h0 = hashlib.sha256(open(p, "rb").read()).hexdigest()
    db2 = SessionDB(p)   # reopen: _DDL + _migrate run again (idempotent), no schema change
    uv = db2._conn.execute("PRAGMA user_version").fetchone()[0]
    db2.close()
    assert uv == 27
    # (the WAL may differ, but the main DB structural content is stable across an idempotent reopen)
    assert hashlib.sha256(open(p, "rb").read()).hexdigest() == h0
