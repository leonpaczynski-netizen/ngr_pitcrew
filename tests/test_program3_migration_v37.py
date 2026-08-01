"""Program 3 Phase B — schema v37: driver-profile versioning with history."""

import json
import sqlite3
import uuid

from data.session_db import SessionDB, _DDL


def test_table_exists(tmp_path):
    db = SessionDB(str(tmp_path / "fresh.db"))
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 37
    tables = {r[0] for r in db._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "driver_profile_versions" in tables


def test_seeds_v1_from_existing_user_profile(tmp_path):
    """An existing DB with a user_profile row gets a v1.0 seed on migration."""
    path = str(tmp_path / "old.db")
    conn = sqlite3.connect(path)
    conn.executescript(_DDL)
    conn.execute(
        "INSERT INTO user_profile(name, throttle_style, updated_at) "
        "VALUES('Leon', 'smooth progressive', '2026-01-01T00:00:00Z')")
    conn.execute("PRAGMA user_version = 31")
    conn.commit()
    conn.close()

    db = SessionDB(path)
    cur = db.get_current_driver_profile_version()
    assert cur is not None
    assert cur["version_label"] == "v1.0-baseline"
    assert json.loads(cur["profile_json"])["throttle_style"] == "smooth progressive"


def test_no_seed_without_user_profile(tmp_path):
    db = SessionDB(str(tmp_path / "fresh.db"))  # fresh DB has no user_profile row
    assert db.get_driver_profile_versions() == []


def test_version_history_is_immutable_and_chained(tmp_path):
    db = SessionDB(str(tmp_path / "fresh.db"))
    v1 = db.append_driver_profile_version(
        version_label="v1.0", profile_json='{"trail_braking": "moderate"}',
        effective_from="2026-01-01", reason="initial")
    v2 = db.append_driver_profile_version(
        version_label="v1.1", profile_json='{"trail_braking": "strong"}',
        changes_json='[{"field": "trail_braking", "from": "moderate", "to": "strong"}]',
        effective_from="2026-02-01", reason="repeated evidence across events")

    hist = db.get_driver_profile_versions()
    assert [h["version_label"] for h in hist] == ["v1.0", "v1.1"]
    assert hist[1]["prior_version_id"] == v1
    # the earlier version is NOT rewritten with the later profile
    assert json.loads(hist[0]["profile_json"])["trail_braking"] == "moderate"
    # exactly one current version, and it is the latest
    assert db.get_current_driver_profile_version()["version_id"] == v2
    assert sum(h["is_current"] for h in hist) == 1
