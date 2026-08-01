"""Program 3 Phase B — schema v32 canonical UUIDv7 identity migration.

Offline / DB-only (no PyQt). Verifies:
  * fresh DB reaches user_version 32 with a uuid column on every core table;
  * existing rows are backfilled with unique, non-null v7 uuids;
  * ORDER BY uuid reproduces the rows' original (timestamp, id) chronology
    (the proof obligation that lets later phases repoint ORDER BY id reads);
  * the migration is idempotent (reopen ⇒ no change, no error);
  * an existing pre-v32 DB is snapshotted to <db>.pre_v32.bak, a fresh DB is not;
  * config_id-bearing data is untouched;
  * the id helpers mint valid, ordered v7 ids.
"""

import os
import sqlite3
import uuid

import pytest

from data.ids import new_id, backfill_id
from data.session_db import SessionDB, _DDL

CORE_TABLES = (
    "events", "sessions", "setups", "setup_snapshots",
    "lap_records", "setup_lineage", "cars", "ai_interactions",
)


def _seed_v31_db(path: str) -> None:
    """Create a pre-v32 (schema 31) DB with a few rows whose id order differs
    from their timestamp order, so the ordering-preservation test is meaningful."""
    conn = sqlite3.connect(path)
    try:
        conn.executescript(_DDL)
        # sessions: id order (1,2,3) deliberately != date order (Jan 3, 1, 2)
        conn.execute("INSERT INTO sessions(date_utc) VALUES('2026-01-03T10:00:00Z')")
        conn.execute("INSERT INTO sessions(date_utc) VALUES('2026-01-01T10:00:00Z')")
        conn.execute("INSERT INTO sessions(date_utc) VALUES('2026-01-02T10:00:00Z')")
        conn.execute(
            "INSERT INTO events(name, created_at, updated_at) "
            "VALUES('Round 4 Fuji', '2026-01-02T09:00:00Z', '2026-01-02T09:00:00Z')")
        conn.execute(
            "INSERT INTO events(name, created_at, updated_at) "
            "VALUES('Round 3 Monza', '2026-01-01T09:00:00Z', '2026-01-01T09:00:00Z')")
        conn.execute("INSERT INTO cars(name) VALUES('Porsche 911 RSR 17')")
        for lap in (1, 2, 3):
            conn.execute(
                "INSERT INTO lap_records(session_id, lap_num, lap_time_ms) "
                "VALUES(1, ?, ?)", (lap, 90000 + lap))
        conn.execute("INSERT INTO ai_interactions(timestamp) VALUES('2026-01-01T00:00:00Z')")
        conn.execute("PRAGMA user_version = 31")
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# id helpers
# --------------------------------------------------------------------------- #

def test_new_id_is_uuid7():
    u = uuid.UUID(new_id())
    assert u.version == 7


def test_backfill_id_is_uuid7_and_order_preserving():
    ids = [backfill_id(ms) for ms in (1000, 2000, 3000, 4000)]
    assert all(uuid.UUID(i).version == 7 for i in ids)
    assert ids == sorted(ids)          # strictly increasing ms ⇒ sortable strings
    assert len(set(ids)) == len(ids)   # unique


# --------------------------------------------------------------------------- #
# fresh DB
# --------------------------------------------------------------------------- #

def test_fresh_db_reaches_v32_with_uuid_columns(tmp_path):
    db = SessionDB(str(tmp_path / "fresh.db"))
    ver = db._conn.execute("PRAGMA user_version").fetchone()[0]
    assert ver >= 32
    for table in CORE_TABLES:
        cols = {r[1] for r in db._conn.execute(f"PRAGMA table_info({table})")}
        assert "uuid" in cols, f"{table} missing uuid column"


def test_fresh_db_writes_no_backup(tmp_path):
    path = str(tmp_path / "fresh.db")
    SessionDB(path)
    assert not os.path.exists(path + ".pre_v32.bak")


# --------------------------------------------------------------------------- #
# migration of an existing pre-v32 DB
# --------------------------------------------------------------------------- #

def test_existing_db_backfills_all_rows(tmp_path):
    path = str(tmp_path / "old.db")
    _seed_v31_db(path)
    db = SessionDB(path)
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] >= 32
    for table in CORE_TABLES:
        n_total = db._conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        n_uuid = db._conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE uuid IS NOT NULL AND uuid != ''"
        ).fetchone()[0]
        assert n_uuid == n_total, f"{table}: {n_uuid}/{n_total} rows have a uuid"
        # every uuid is a valid v7 and unique
        uuids = [r[0] for r in db._conn.execute(f"SELECT uuid FROM {table}")]
        assert all(uuid.UUID(u).version == 7 for u in uuids)
        assert len(set(uuids)) == len(uuids)


def test_order_by_uuid_matches_timestamp_chronology(tmp_path):
    path = str(tmp_path / "old.db")
    _seed_v31_db(path)
    db = SessionDB(path)
    # sessions were inserted id=1→Jan3, id=2→Jan1, id=3→Jan2.
    by_uuid = [r[0] for r in db._conn.execute(
        "SELECT date_utc FROM sessions ORDER BY uuid")]
    by_time = [r[0] for r in db._conn.execute(
        "SELECT date_utc FROM sessions ORDER BY date_utc, id")]
    assert by_uuid == by_time
    assert by_uuid[0].startswith("2026-01-01")  # earliest first, not insertion order


def test_order_by_uuid_matches_id_for_untimestamped(tmp_path):
    path = str(tmp_path / "old.db")
    _seed_v31_db(path)
    db = SessionDB(path)
    by_uuid = [r[0] for r in db._conn.execute(
        "SELECT lap_num FROM lap_records ORDER BY uuid")]
    by_id = [r[0] for r in db._conn.execute(
        "SELECT lap_num FROM lap_records ORDER BY id")]
    assert by_uuid == by_id == [1, 2, 3]


def test_existing_db_writes_one_backup(tmp_path):
    path = str(tmp_path / "old.db")
    _seed_v31_db(path)
    SessionDB(path)
    assert os.path.exists(path + ".pre_v32.bak")


def test_migration_is_idempotent(tmp_path):
    path = str(tmp_path / "old.db")
    _seed_v31_db(path)
    db1 = SessionDB(path)
    before = {t: [r[0] for r in db1._conn.execute(f"SELECT uuid FROM {t} ORDER BY id")]
              for t in CORE_TABLES}
    db1._conn.close()
    # reopen — _migrate runs again but v32 is already applied
    db2 = SessionDB(path)
    assert db2._conn.execute("PRAGMA user_version").fetchone()[0] >= 32
    after = {t: [r[0] for r in db2._conn.execute(f"SELECT uuid FROM {t} ORDER BY id")]
             for t in CORE_TABLES}
    assert before == after  # uuids unchanged on re-open


def test_config_id_data_untouched(tmp_path):
    """The migration must not perturb config_id-bearing columns."""
    path = str(tmp_path / "cfg.db")
    conn = sqlite3.connect(path)
    conn.executescript(_DDL)
    conn.execute(
        "INSERT INTO sessions(date_utc, config_id) VALUES('2026-01-01T00:00:00Z', 'b99682463a')")
    conn.execute("PRAGMA user_version = 31")
    conn.commit()
    conn.close()
    db = SessionDB(path)
    cfg = db._conn.execute("SELECT config_id FROM sessions").fetchone()[0]
    assert cfg == "b99682463a"


def test_uuid_unique_index_present(tmp_path):
    db = SessionDB(str(tmp_path / "fresh.db"))
    idx = {r[0] for r in db._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'")}
    for table in CORE_TABLES:
        assert f"idx_{table}_uuid" in idx
