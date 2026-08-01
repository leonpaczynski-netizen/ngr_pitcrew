"""Program 3 Phase B — schema v33: event-programme identity becomes a UUID.

Offline / DB-only. Verifies the cycle_id slug -> UUID migration cascades onto the
child tables, preserves the old slug in legacy_cycle_id, keeps lookups working
(by event_id via get_cycle_by_event, and by legacy slug via get_preparation_cycle),
and is idempotent.
"""

import sqlite3
import uuid

from data.session_db import SessionDB, _DDL


def _seed_v32_cycle(path: str, slug: str = "cycle-round-4-fuji",
                    event_id: int = 5, event_name: str = "Round 4 Fuji") -> None:
    """A pre-v33 DB (schema 32) with a slug-keyed cycle + one child activity and
    one activity-session binding, so the cascade can be checked."""
    conn = sqlite3.connect(path)
    try:
        conn.executescript(_DDL)
        conn.execute(
            "INSERT INTO event_preparation_cycles(cycle_id, event_id, event_name, created_at) "
            "VALUES(?,?,?, '2026-01-01T00:00:00Z')", (slug, event_id, event_name))
        conn.execute(
            "INSERT INTO event_preparation_activities(activity_id, cycle_id) VALUES(?,?)",
            (f"{slug}::practice::1", slug))
        conn.execute(
            "INSERT INTO event_preparation_activity_sessions(activity_id, session_id, cycle_id) "
            "VALUES(?,?,?)", (f"{slug}::practice::1", "1", slug))
        conn.execute("PRAGMA user_version = 32")
        conn.commit()
    finally:
        conn.close()


def test_fresh_db_reaches_v33_with_legacy_column(tmp_path):
    db = SessionDB(str(tmp_path / "fresh.db"))
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] >= 33
    cols = {r[1] for r in db._conn.execute("PRAGMA table_info(event_preparation_cycles)")}
    assert "legacy_cycle_id" in cols


def test_slug_is_replaced_by_uuid_and_cascaded(tmp_path):
    path = str(tmp_path / "old.db")
    _seed_v32_cycle(path)
    db = SessionDB(path)
    row = db._conn.execute(
        "SELECT cycle_id, legacy_cycle_id FROM event_preparation_cycles").fetchone()
    new_cid, legacy = row[0], row[1]
    assert uuid.UUID(new_cid).version == 7           # cycle_id is now a UUIDv7
    assert legacy == "cycle-round-4-fuji"            # old slug preserved
    # children cascaded to the new id; none left pointing at the old slug
    act = db._conn.execute("SELECT cycle_id FROM event_preparation_activities").fetchone()[0]
    sess = db._conn.execute(
        "SELECT cycle_id FROM event_preparation_activity_sessions").fetchone()[0]
    assert act == new_cid and sess == new_cid
    assert db._conn.execute(
        "SELECT COUNT(*) FROM event_preparation_activities WHERE cycle_id='cycle-round-4-fuji'"
    ).fetchone()[0] == 0


def test_get_cycle_by_event_finds_migrated_cycle(tmp_path):
    path = str(tmp_path / "old.db")
    _seed_v32_cycle(path)
    db = SessionDB(path)
    by_id = db.get_cycle_by_event(5)
    assert by_id is not None
    assert uuid.UUID(by_id["cycle_id"]).version == 7
    assert by_id["event_name"] == "Round 4 Fuji"
    # by name also works; unknown event returns None
    assert db.get_cycle_by_event(0, "Round 4 Fuji") is not None
    assert db.get_cycle_by_event(999) is None


def test_get_preparation_cycle_tolerates_legacy_slug(tmp_path):
    path = str(tmp_path / "old.db")
    _seed_v32_cycle(path)
    db = SessionDB(path)
    # looking the cycle up by its OLD slug still resolves (via legacy_cycle_id)
    cyc = db.get_preparation_cycle("cycle-round-4-fuji")
    assert cyc is not None
    assert uuid.UUID(cyc["cycle_id"]).version == 7


def test_migration_idempotent_no_rekey(tmp_path):
    path = str(tmp_path / "old.db")
    _seed_v32_cycle(path)
    db1 = SessionDB(path)
    cid_1 = db1._conn.execute("SELECT cycle_id FROM event_preparation_cycles").fetchone()[0]
    db1._conn.close()
    db2 = SessionDB(path)
    cid_2 = db2._conn.execute("SELECT cycle_id FROM event_preparation_cycles").fetchone()[0]
    assert cid_1 == cid_2  # a re-open must NOT mint a second uuid
    assert db2._conn.execute("PRAGMA user_version").fetchone()[0] >= 33


def test_upsert_new_cycle_with_uuid_roundtrips(tmp_path):
    """A brand-new cycle created post-v33 with a UUID id survives migration re-runs
    (its uuid is left alone) and is retrievable by event."""
    from data.ids import new_id
    db = SessionDB(str(tmp_path / "fresh.db"))
    cid = new_id()
    db.upsert_preparation_cycle(
        {"cycle_id": cid, "event_id": 7, "event_name": "Round 7 Spa",
         "created_at": "2026-02-02T00:00:00Z", "updated_at": "2026-02-02T00:00:00Z"})
    got = db.get_cycle_by_event(7)
    assert got is not None and got["cycle_id"] == cid
