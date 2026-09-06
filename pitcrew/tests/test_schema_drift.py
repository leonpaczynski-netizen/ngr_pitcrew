"""A column is added in two places or it is not added.

`CREATE TABLE IF NOT EXISTS` does nothing to a table that already exists, so a
column that reaches the DDL and not `ADDED_COLUMNS` reaches every fresh
database - the ones every other test builds - and no real one. `rival_stops.
compound_reads` was added to the DDL at 7ce870d with no entry, and every
`record_rival_stop` on the live file since then died on

    sqlite3.OperationalError: table rival_stops has no column named compound_reads

inside a try/except, while the suite asserted `compound_reads == 3` on a fresh
file. Seven stops recognised on Deep Forest race night, zero rows. This file
is the check that would have caught it on the first launch after the commit.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from pitcrew.store.db import Store
from pitcrew.store.schema import ADDED_COLUMNS, DDL, SCHEMA_VERSION
from tools.schema_audit import declared_columns, drift

LIVE = Path(__file__).resolve().parents[2] / "data" / "pitcrew.db"

# `rival_stops` exactly as d0efc6a created it at v12 - thirteen columns, no
# `compound_reads` - which is the shape the live file had for every race.
OLD_RIVAL_STOPS = """
CREATE TABLE rival_stops (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
    driver          TEXT    NOT NULL,
    lap             INTEGER,
    laps_total      INTEGER,
    fuel_in_l       REAL,
    fuel_out_l      REAL,
    compound        TEXT,
    assumed_start_l REAL,
    reads           INTEGER NOT NULL DEFAULT 0,
    watched_s       REAL,
    partial         INTEGER NOT NULL DEFAULT 0,
    recorded_at     TEXT    NOT NULL
);
"""


def _old_shape(path: Path) -> None:
    """A file that predates the column, at the current schema version - the
    state `IF NOT EXISTS` leaves behind and `user_version` cannot see."""
    conn = sqlite3.connect(path)
    try:
        conn.executescript(OLD_RIVAL_STOPS)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
    finally:
        conn.close()


def test_the_parser_reads_every_declared_table():
    tables = declared_columns()
    assert "rival_stops" in tables
    assert "compound_reads" in tables["rival_stops"]
    assert "laps" in tables and "fuel_used" in tables["laps"]
    # A constraint line is not a column.
    for columns in tables.values():
        assert not any(c.upper() in {"PRIMARY", "UNIQUE", "FOREIGN"}
                       for c in columns)


def test_added_columns_reach_a_fresh_database_too():
    """`ADDED_COLUMNS` is the only home of a column added after its table was
    created - the DDL is the table's original shape - and `_upgrade` applies
    it to a fresh file as well as an old one, so both shapes converge."""
    from pitcrew.store.schema import ADDED_COLUMNS
    import tempfile
    path = Path(tempfile.mkdtemp()) / "fresh.db"
    store = Store(path)
    try:
        for table, columns in ADDED_COLUMNS.items():
            have = {r[1] for r in
                    store._conn.execute(f"PRAGMA table_info({table})")}
            for name, _kind in columns:
                assert name in have, (table, name)
    finally:
        store.close()


def test_a_fresh_database_has_no_drift(tmp_path):
    store = Store(tmp_path / "fresh.db")
    try:
        assert drift(store._conn) == {}
    finally:
        store.close()


def test_a_file_that_predates_compound_reads_gains_it_on_open(tmp_path):
    """The exact production failure, on the live file's shape."""
    path = tmp_path / "old.db"
    _old_shape(path)
    before = sqlite3.connect(path)
    have = {r[1] for r in before.execute("PRAGMA table_info(rival_stops)")}
    before.close()
    assert "compound_reads" not in have, "the fixture must predate the column"

    store = Store(path)
    try:
        have = {r[1] for r in
                store._conn.execute("PRAGMA table_info(rival_stops)")}
        assert "compound_reads" in have
        assert drift(store._conn) == {}
        # And the write that died seven times on race night now lands.
        row_id = store.record_rival_stop(
            None, "Car #10", lap=13, fuel_in_l=8.0, fuel_out_l=59.0,
            compound="RS", reads=12, compound_reads=3, watched_s=40.0)
        row = store._conn.execute(
            "SELECT compound_reads, reads FROM rival_stops WHERE id = ?",
            (row_id,)).fetchone()
        assert (row[0], row[1]) == (3, 12)
    finally:
        store.close()


def test_added_columns_apply_before_migrations_and_are_idempotent(tmp_path):
    """Opening twice must not try to add the column twice."""
    path = tmp_path / "twice.db"
    _old_shape(path)
    for _ in range(2):
        store = Store(path)
        store.close()
    conn = sqlite3.connect(path)
    try:
        names = [r[1] for r in conn.execute("PRAGMA table_info(rival_stops)")]
    finally:
        conn.close()
    assert names.count("compound_reads") == 1


@pytest.mark.skipif(not LIVE.exists(), reason="no live database on this machine")
def test_the_live_database_has_every_declared_column():
    """Read-only, never a copy: the live file is the only one with data in it,
    and a fresh one has always been right. Skipped where there is none."""
    conn = sqlite3.connect(f"file:{LIVE.as_posix()}?mode=ro", uri=True)
    try:
        missing = drift(conn)
    finally:
        conn.close()
    # The live file may legitimately lack a table the DDL would create on
    # the next open; a column missing from a table that EXISTS is the defect.
    real = {t: c for t, c in missing.items()
            if len(c) < len(declared_columns()[t])}
    assert real == {}, (
        f"declared columns missing from {LIVE}: {real} - add them to "
        f"ADDED_COLUMNS and open the app once")
