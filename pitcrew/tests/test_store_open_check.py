"""The foreign-key scan runs after an upgrade - and only then.

`PRAGMA foreign_key_check` scans every keyed table. It used to run on every
open: 10-13 ms of every launch on the driver's 600 MB file (measured 20 Sep
2026), guarding against the one thing that cannot happen to a file already
at this version - every write outside `_upgrade` runs with foreign keys ON.
It is kept exactly where keys are off: after a migration, on a new file, or
after a column is added.
"""
from __future__ import annotations

import sqlite3

import pytest

from pitcrew.store import db as db_module
from pitcrew.store.db import SCHEMA_VERSION, Store


def _statements(path, monkeypatch) -> list[str]:
    seen: list[str] = []
    real = sqlite3.connect

    def traced(*args, **kwargs):
        conn = real(*args, **kwargs)
        conn.set_trace_callback(seen.append)
        return conn

    monkeypatch.setattr(db_module.sqlite3, "connect", traced)
    Store(path).close()
    monkeypatch.setattr(db_module.sqlite3, "connect", real)
    return seen


def test_a_new_file_is_checked(tmp_path, monkeypatch):
    seen = _statements(tmp_path / "new.db", monkeypatch)
    assert any("foreign_key_check" in s for s in seen)


def test_a_file_at_this_version_is_not_scanned_or_rewritten(tmp_path,
                                                             monkeypatch):
    path = tmp_path / "current.db"
    Store(path).close()
    seen = _statements(path, monkeypatch)
    assert not any("foreign_key_check" in s for s in seen)
    assert not any(s.startswith("PRAGMA user_version =") for s in seen)
    # And keys are back on for everything after the open.
    store = Store(path)
    try:
        assert store._conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        store.close()


def test_an_older_file_is_checked_after_its_upgrade(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    Store(path).close()
    conn = sqlite3.connect(path)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION - 1}")
    conn.commit()
    conn.close()
    monkeypatch.setattr(db_module, "MIGRATIONS", {
        k: v for k, v in db_module.MIGRATIONS.items() if k != SCHEMA_VERSION})
    seen = _statements(path, monkeypatch)
    assert any("foreign_key_check" in s for s in seen)
    conn = sqlite3.connect(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    conn.close()


def test_a_dangling_reference_left_by_an_upgrade_is_still_refused(
        tmp_path, monkeypatch):
    path = tmp_path / "broken.db"
    Store(path).close()
    conn = sqlite3.connect(path)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION - 1}")
    conn.commit()
    conn.close()

    def breaks(conn):
        conn.execute("CREATE TABLE parent_x (id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE child_x (id INTEGER PRIMARY KEY, "
                     "p INTEGER REFERENCES parent_x(id))")
        conn.execute("INSERT INTO child_x (p) VALUES (99)")

    monkeypatch.setattr(db_module, "MIGRATIONS",
                        {SCHEMA_VERSION: ("breaks", breaks)})
    with pytest.raises(RuntimeError, match="dangling"):
        Store(path)
