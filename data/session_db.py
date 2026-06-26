"""Persistent SQLite storage for GT7 VR Dashboard sessions and lap telemetry.

Stores per-session lap stats, fuel data, car setups, events, and compressed
per-frame telemetry across sessions, cars and tracks.  The AI coaching/setup
prompts use historical context from this database.

Schema versioning: PRAGMA user_version tracks applied migrations.
  Version 0: original 7 tables (pre-architecture-stabilisation)
  Version 1: adds events, cars, user_profile, setups, lap_telemetry tables;
             extends sessions, lap_records, ai_interactions with new columns.

Thread-safety: all public methods acquire _lock before touching the
sqlite3.Connection (check_same_thread=False is still required because
EventDispatcher and the Qt thread both call write_lap).
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import zlib
from dataclasses import asdict as _dc_asdict
from datetime import datetime, timezone
from statistics import mean as _mean
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from telemetry.recorder import LapStats, TelemetryFrame


# ---------------------------------------------------------------------------
# DDL — original 7 tables (created on every open via IF NOT EXISTS)
# ---------------------------------------------------------------------------
_DDL_BASE = """
CREATE TABLE IF NOT EXISTS sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    car_id       INTEGER NOT NULL DEFAULT 0,
    car_name     TEXT    NOT NULL DEFAULT '',
    config_id    TEXT    NOT NULL DEFAULT '',
    track        TEXT    NOT NULL DEFAULT '',
    session_type TEXT    NOT NULL DEFAULT 'Race',
    date_utc     TEXT    NOT NULL,
    total_laps   INTEGER NOT NULL DEFAULT 0,
    event_id     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS lap_records (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id              INTEGER NOT NULL,
    car_id                  INTEGER NOT NULL DEFAULT 0,
    track                   TEXT    NOT NULL DEFAULT '',
    lap_num                 INTEGER NOT NULL,
    lap_time_ms             INTEGER NOT NULL,
    fuel_used               REAL    NOT NULL DEFAULT 0.0,
    lock_up_count           INTEGER NOT NULL DEFAULT 0,
    wheelspin_count         INTEGER NOT NULL DEFAULT 0,
    brake_consistency_m     REAL    NOT NULL DEFAULT -1.0,
    max_speed_kmh           REAL    NOT NULL DEFAULT 0.0,
    avg_throttle_pct        REAL    NOT NULL DEFAULT 0.0,
    avg_brake_pct           REAL    NOT NULL DEFAULT 0.0,
    compound                TEXT    NOT NULL DEFAULT '',
    setup_id                INTEGER NOT NULL DEFAULT 0,
    oversteer_count         INTEGER NOT NULL DEFAULT 0,
    oversteer_throttle_on   INTEGER NOT NULL DEFAULT 0,
    kerb_count              INTEGER NOT NULL DEFAULT 0,
    bottoming_count         INTEGER NOT NULL DEFAULT 0,
    snap_throttle_count     INTEGER NOT NULL DEFAULT 0,
    over_braking_count      INTEGER NOT NULL DEFAULT 0,
    abrupt_release_count    INTEGER NOT NULL DEFAULT 0,
    rev_limiter_count       INTEGER NOT NULL DEFAULT 0,
    max_lat_g               REAL    NOT NULL DEFAULT 0.0,
    off_track_count         INTEGER NOT NULL DEFAULT 0,
    tyre_temp_avg           REAL    NOT NULL DEFAULT 0.0,
    is_out_lap              INTEGER NOT NULL DEFAULT 0,
    is_pit_lap              INTEGER NOT NULL DEFAULT 0,
    delta_ms                INTEGER NOT NULL DEFAULT 0,
    position                INTEGER NOT NULL DEFAULT 0,
    session_type            TEXT    NOT NULL DEFAULT '',
    event_positions_json    TEXT    NOT NULL DEFAULT '{}',
    fuel_start              REAL    NOT NULL DEFAULT 0.0,
    fuel_end                REAL    NOT NULL DEFAULT 0.0,
    tyre_temp_fl_avg        REAL    NOT NULL DEFAULT 0.0,
    tyre_temp_fr_avg        REAL    NOT NULL DEFAULT 0.0,
    tyre_temp_rl_avg        REAL    NOT NULL DEFAULT 0.0,
    tyre_temp_rr_avg        REAL    NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS setup_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL DEFAULT 0,
    car_id      INTEGER NOT NULL DEFAULT 0,
    track       TEXT    NOT NULL DEFAULT '',
    name        TEXT    NOT NULL DEFAULT '',
    setup_json  TEXT    NOT NULL,
    captured_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS driver_feedback (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL DEFAULT 0,
    lap_num         INTEGER NOT NULL DEFAULT 0,
    submitted_at    TEXT    NOT NULL,
    corner_entry    TEXT    NOT NULL DEFAULT '',
    mid_corner      TEXT    NOT NULL DEFAULT '',
    exit_stability  TEXT    NOT NULL DEFAULT '',
    rear_braking    TEXT    NOT NULL DEFAULT '',
    tyre_condition  TEXT    NOT NULL DEFAULT '',
    fuel_use        TEXT    NOT NULL DEFAULT '',
    notes           TEXT    NOT NULL DEFAULT '',
    config_id       TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS grip_alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL DEFAULT 0,
    lap_num     INTEGER NOT NULL DEFAULT 0,
    score       INTEGER NOT NULL DEFAULT 0,
    alert_type  TEXT    NOT NULL DEFAULT '',
    fired_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS strategy_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    config_id       TEXT    NOT NULL DEFAULT '',
    created_at      TEXT    NOT NULL,
    strategies_json TEXT    NOT NULL,
    selected_rank   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS ai_interactions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp           TEXT    NOT NULL,
    feature             TEXT    NOT NULL DEFAULT '',
    model               TEXT    NOT NULL DEFAULT '',
    prompt              TEXT    NOT NULL DEFAULT '',
    structured_payload  TEXT    NOT NULL DEFAULT '{}',
    response            TEXT    NOT NULL DEFAULT '',
    success             INTEGER NOT NULL DEFAULT 1,
    duration_ms         INTEGER NOT NULL DEFAULT 0,
    prompt_tokens       INTEGER NOT NULL DEFAULT 0,
    response_tokens     INTEGER NOT NULL DEFAULT 0,
    estimated_cost      REAL    NOT NULL DEFAULT 0.0,
    error_msg           TEXT    NOT NULL DEFAULT '',
    validation_warnings TEXT    NOT NULL DEFAULT '[]',
    car_id              INTEGER NOT NULL DEFAULT 0,
    track               TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_lap_car_track
    ON lap_records (car_id, track);
"""

# ---------------------------------------------------------------------------
# DDL — new tables added in schema version 1
# ---------------------------------------------------------------------------
_DDL_V1 = """
CREATE TABLE IF NOT EXISTS events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL UNIQUE,
    track           TEXT    NOT NULL DEFAULT '',
    race_type       TEXT    NOT NULL DEFAULT 'lap',
    laps            INTEGER NOT NULL DEFAULT 25,
    duration_mins   INTEGER NOT NULL DEFAULT 60,
    tyre_wear       REAL    NOT NULL DEFAULT 1.0,
    fuel_mult       REAL    NOT NULL DEFAULT 1.0,
    refuel_rate_lps REAL    NOT NULL DEFAULT 10.0,
    mandatory_stops INTEGER NOT NULL DEFAULT 0,
    bop             INTEGER NOT NULL DEFAULT 0,
    tuning          INTEGER NOT NULL DEFAULT 1,
    weather         TEXT    NOT NULL DEFAULT 'Fixed Dry',
    damage          TEXT    NOT NULL DEFAULT 'None',
    avail_tyres     TEXT    NOT NULL DEFAULT '[]',
    req_tyres       TEXT    NOT NULL DEFAULT '[]',
    allowed_tuning  TEXT    NOT NULL DEFAULT '[]',
    notes           TEXT    NOT NULL DEFAULT '',
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS cars (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL UNIQUE,
    manufacturer TEXT    NOT NULL DEFAULT '',
    category     TEXT    NOT NULL DEFAULT '',
    drivetrain   TEXT    NOT NULL DEFAULT '',
    power_hp     REAL    NOT NULL DEFAULT 0.0,
    weight_kg    REAL    NOT NULL DEFAULT 0.0,
    pp           REAL    NOT NULL DEFAULT 0.0,
    notes        TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS user_profile (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    name                     TEXT    NOT NULL DEFAULT 'Leon',
    driving_style_summary    TEXT    NOT NULL DEFAULT '',
    setup_preferences        TEXT    NOT NULL DEFAULT '',
    brake_bias_preference    TEXT    NOT NULL DEFAULT '',
    throttle_style           TEXT    NOT NULL DEFAULT '',
    trail_braking_preference TEXT    NOT NULL DEFAULT '',
    stability_preference     TEXT    NOT NULL DEFAULT '',
    rotation_preference      TEXT    NOT NULL DEFAULT '',
    updated_at               TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS setups (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    car_id      INTEGER NOT NULL DEFAULT 0,
    event_id    INTEGER NOT NULL DEFAULT 0,
    name        TEXT    NOT NULL DEFAULT '',
    setup_json  TEXT    NOT NULL DEFAULT '{}',
    ai_notes    TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS lap_telemetry (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    lap_record_id INTEGER NOT NULL DEFAULT 0,
    session_id    INTEGER NOT NULL DEFAULT 0,
    lap_num       INTEGER NOT NULL,
    sample_hz     REAL    NOT NULL DEFAULT 10.0,
    frame_count   INTEGER NOT NULL DEFAULT 0,
    frames_blob   BLOB    NOT NULL,
    captured_at   TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_lap_telemetry_lap
    ON lap_telemetry (lap_record_id);
"""

# Columns added to existing tables in migration v1.
# Each tuple: (table, column_def_sql).
_V1_ALTER_COLUMNS: list[tuple[str, str]] = [
    # sessions
    ("sessions", "car_name TEXT NOT NULL DEFAULT ''"),
    ("sessions", "config_id TEXT NOT NULL DEFAULT ''"),
    ("sessions", "event_id INTEGER NOT NULL DEFAULT 0"),
    # lap_records
    ("lap_records", "setup_id INTEGER NOT NULL DEFAULT 0"),
    ("lap_records", "oversteer_count INTEGER NOT NULL DEFAULT 0"),
    ("lap_records", "oversteer_throttle_on INTEGER NOT NULL DEFAULT 0"),
    ("lap_records", "kerb_count INTEGER NOT NULL DEFAULT 0"),
    ("lap_records", "bottoming_count INTEGER NOT NULL DEFAULT 0"),
    ("lap_records", "snap_throttle_count INTEGER NOT NULL DEFAULT 0"),
    ("lap_records", "over_braking_count INTEGER NOT NULL DEFAULT 0"),
    ("lap_records", "abrupt_release_count INTEGER NOT NULL DEFAULT 0"),
    ("lap_records", "rev_limiter_count INTEGER NOT NULL DEFAULT 0"),
    ("lap_records", "max_lat_g REAL NOT NULL DEFAULT 0.0"),
    ("lap_records", "off_track_count INTEGER NOT NULL DEFAULT 0"),
    ("lap_records", "tyre_temp_avg REAL NOT NULL DEFAULT 0.0"),
    ("lap_records", "is_out_lap INTEGER NOT NULL DEFAULT 0"),
    ("lap_records", "is_pit_lap INTEGER NOT NULL DEFAULT 0"),
    ("lap_records", "delta_ms INTEGER NOT NULL DEFAULT 0"),
    ("lap_records", "position INTEGER NOT NULL DEFAULT 0"),
    ("lap_records", "session_type TEXT NOT NULL DEFAULT ''"),
    ("lap_records", "event_positions_json TEXT NOT NULL DEFAULT '{}'"),
    # ai_interactions
    ("ai_interactions", "car_id INTEGER NOT NULL DEFAULT 0"),
    ("ai_interactions", "track TEXT NOT NULL DEFAULT ''"),
]

# Columns added in schema version 2.
_V2_ALTER_COLUMNS: list[tuple[str, str]] = [
    ("lap_records", "fuel_start REAL NOT NULL DEFAULT 0.0"),
    ("lap_records", "fuel_end   REAL NOT NULL DEFAULT 0.0"),
]

# Columns added in schema version 3 — per-corner tyre temperature averages.
_V3_ALTER_COLUMNS: list[tuple[str, str]] = [
    ("lap_records", "tyre_temp_fl_avg REAL NOT NULL DEFAULT 0.0"),
    ("lap_records", "tyre_temp_fr_avg REAL NOT NULL DEFAULT 0.0"),
    ("lap_records", "tyre_temp_rl_avg REAL NOT NULL DEFAULT 0.0"),
    ("lap_records", "tyre_temp_rr_avg REAL NOT NULL DEFAULT 0.0"),
]

# DDL — new table added in schema version 4 (corner-level telemetry learning).
_DDL_V4 = """
CREATE TABLE IF NOT EXISTS corner_issues (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    car_id       INTEGER NOT NULL,
    track        TEXT    NOT NULL,
    corner_id    TEXT    NOT NULL,
    issue_type   TEXT    NOT NULL,
    phase        TEXT    NOT NULL DEFAULT '',
    lap_count    INTEGER NOT NULL DEFAULT 0,
    total_laps   INTEGER NOT NULL DEFAULT 0,
    severity     REAL    NOT NULL DEFAULT 0.0,
    confidence   REAL    NOT NULL DEFAULT 0.0,
    evidence     TEXT    NOT NULL DEFAULT '',
    session_id   INTEGER NOT NULL DEFAULT 0,
    detected_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_corner_issues_car_track
    ON corner_issues (car_id, track);
"""

_DDL_V5 = """
CREATE TABLE IF NOT EXISTS setup_recommendations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ai_interaction_id   INTEGER,
    session_id          INTEGER NOT NULL DEFAULT 0,
    car_id              INTEGER NOT NULL DEFAULT 0,
    track               TEXT    NOT NULL DEFAULT '',
    layout_id           TEXT    NOT NULL DEFAULT '',
    feature             TEXT    NOT NULL DEFAULT '',
    recommendation_text TEXT    NOT NULL DEFAULT '',
    status              TEXT    NOT NULL DEFAULT 'proposed',
    outcome             TEXT    NOT NULL DEFAULT 'not_verified',
    outcome_session_id  INTEGER,
    created_at          TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_setup_recs_car_track
    ON setup_recommendations (car_id, track);
"""

_DDL_V6 = ""  # Schema changes applied via ALTER TABLE in _migrate_v6

_DDL_V8 = """
CREATE TABLE IF NOT EXISTS race_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    car_id INTEGER NOT NULL,
    setup_id INTEGER,
    plan_name TEXT NOT NULL,
    stints_json TEXT NOT NULL,
    strategy_rank INTEGER,
    strategy_name TEXT,
    estimated_time_s REAL,
    ai_summary TEXT,
    ai_risks TEXT,
    ai_positives TEXT,
    ai_negatives TEXT,
    driver_notes TEXT NOT NULL DEFAULT '',
    setup_name TEXT,
    created_at TEXT NOT NULL
);
"""

_DDL = _DDL_BASE + _DDL_V1 + _DDL_V4 + _DDL_V5 + _DDL_V6 + _DDL_V8

def ms_to_str(ms: int) -> str:
    if ms <= 0:
        return "—"
    total_s = ms / 1000.0
    m = int(total_s // 60)
    s = total_s - m * 60
    return f"{m}:{s:06.3f}"


class SessionDB:
    """Persistent store for lap telemetry, session metadata and car setups."""

    def __init__(self, db_path: str = "data/gt7_sessions.db") -> None:
        self._path = db_path
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        self._open()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _open(self) -> None:
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(
            self._path, check_same_thread=False, isolation_level=None
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_DDL)
        self._migrate()

    def _migrate(self) -> None:
        """Apply pending schema migrations using PRAGMA user_version as a guard."""
        version = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if version < 1:
            self._migrate_v1()
            self._conn.execute("PRAGMA user_version = 1")
        if version < 2:
            self._migrate_v2()
            self._conn.execute("PRAGMA user_version = 2")
        if version < 3:
            self._migrate_v3()
            self._conn.execute("PRAGMA user_version = 3")
        if version < 4:
            self._migrate_v4()
            self._conn.execute("PRAGMA user_version = 4")
        if version < 5:
            self._migrate_v5()
            self._conn.execute("PRAGMA user_version = 5")
            self._conn.commit()
        if version < 6:
            self._migrate_v6()
            self._conn.execute("PRAGMA user_version = 6")
            self._conn.commit()
        if version < 7:
            self._migrate_v7()
            self._conn.execute("PRAGMA user_version = 7")
            self._conn.commit()
        if version < 8:
            self._migrate_v8()
            self._conn.execute("PRAGMA user_version = 8")
            self._conn.commit()

    def _migrate_v2(self) -> None:
        """Add fuel_start and fuel_end to lap_records (schema version 2)."""
        for table, col_def in _V2_ALTER_COLUMNS:
            try:
                self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e).lower():
                    raise

    def _migrate_v3(self) -> None:
        """Add per-corner tyre temperature averages to lap_records (schema version 3)."""
        for table, col_def in _V3_ALTER_COLUMNS:
            try:
                self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e).lower():
                    raise

    def _migrate_v4(self) -> None:
        """Create corner_issues table and index (schema version 4)."""
        self._conn.executescript(_DDL_V4)

    def _migrate_v7(self) -> None:
        for sql in [
            "ALTER TABLE setup_recommendations ADD COLUMN after_metrics TEXT NOT NULL DEFAULT '{}'",
            "ALTER TABLE setup_recommendations ADD COLUMN corner_issue_ids TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE cars ADD COLUMN rev_limit_threshold_pct REAL NOT NULL DEFAULT 0.9",
        ]:
            try:
                with self._conn:
                    self._conn.execute(sql)
            except Exception as e:
                if "duplicate column" not in str(e).lower():
                    raise

    def _migrate_v8(self) -> None:
        """Create race_plans table (schema version 8)."""
        self._conn.executescript(_DDL_V8)

    def _migrate_v6(self) -> None:
        try:
            self._conn.execute(
                "ALTER TABLE setup_recommendations ADD COLUMN before_metrics TEXT NOT NULL DEFAULT '{}'"
            )
        except Exception as e:
            if "duplicate column" not in str(e).lower():
                raise

    def _migrate_v5(self) -> None:
        try:
            self._conn.execute(
                "ALTER TABLE ai_interactions ADD COLUMN session_id INTEGER NOT NULL DEFAULT 0"
            )
        except Exception as e:
            if "duplicate column" not in str(e).lower():
                raise
        self._conn.executescript(_DDL_V5)

    def _migrate_v1(self) -> None:
        """Add new columns to existing tables for schema version 1.

        Uses try/except per column so that columns already present (from the
        current DDL on a fresh install, or from the old ad-hoc migration code)
        are silently skipped.
        """
        for table, col_def in _V1_ALTER_COLUMNS:
            col_name = col_def.split()[0]
            try:
                self._conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN {col_def}"
                )
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e).lower():
                    raise

    # ------------------------------------------------------------------
    # Race Plans CRUD (schema version 8)
    # ------------------------------------------------------------------

    def save_race_plan(
        self,
        event_id: int,
        car_id: int,
        setup_id,
        plan_name: str,
        stints_json: str,
        strategy_rank,
        strategy_name,
        estimated_time_s,
        ai_summary,
        ai_risks,
        ai_positives,
        ai_negatives,
        driver_notes: str,
        setup_name,
    ) -> int:
        """Insert and return the new plan id."""
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO race_plans
                       (event_id, car_id, setup_id, plan_name, stints_json,
                        strategy_rank, strategy_name, estimated_time_s,
                        ai_summary, ai_risks, ai_positives, ai_negatives,
                        driver_notes, setup_name, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    event_id, car_id, setup_id, plan_name, stints_json,
                    strategy_rank, strategy_name, estimated_time_s,
                    ai_summary, ai_risks, ai_positives, ai_negatives,
                    driver_notes, setup_name, created_at,
                ),
            )
            self._conn.commit()
            return cur.lastrowid or 0

    def get_race_plans(self, event_id: int, car_id: int) -> list[dict]:
        """Return all plans for event+car, ordered by created_at DESC, id DESC."""
        with self._lock:
            rows = self._conn.execute(
                """SELECT * FROM race_plans
                   WHERE event_id=? AND car_id=?
                   ORDER BY created_at DESC, id DESC""",
                (event_id, car_id),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_latest_race_plan(self, event_id: int, car_id: int) -> Optional[dict]:
        """Return the most recent plan for event+car, or None."""
        with self._lock:
            row = self._conn.execute(
                """SELECT * FROM race_plans
                   WHERE event_id=? AND car_id=?
                   ORDER BY created_at DESC, id DESC LIMIT 1""",
                (event_id, car_id),
            ).fetchone()
        return dict(row) if row else None

    def close(self) -> None:
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None

    def clear_all_sessions(self) -> int:
        """Delete every session and lap record. Returns the number of sessions deleted."""
        with self._lock:
            count = self._conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            self._conn.execute("DELETE FROM lap_records")
            self._conn.execute("DELETE FROM lap_telemetry")
            self._conn.execute("DELETE FROM sessions")
            self._conn.execute("DELETE FROM setup_snapshots")
            self._conn.commit()
            self._conn.execute(
                "DELETE FROM sqlite_sequence WHERE name IN "
                "('sessions','lap_records','setup_snapshots','lap_telemetry')"
            )
            self._conn.commit()
            return count

    def delete_session(self, session_id: int) -> None:
        """Delete a single session and all its lap records."""
        with self._lock:
            self._conn.execute(
                "DELETE FROM lap_telemetry WHERE session_id = ?", (session_id,)
            )
            self._conn.execute(
                "DELETE FROM lap_records WHERE session_id = ?", (session_id,)
            )
            self._conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            self._conn.commit()

    # ------------------------------------------------------------------
    # Events CRUD
    # ------------------------------------------------------------------

    def upsert_event(self, evt: dict) -> int:
        """Insert or replace an event by name. Returns the event id."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock:
            existing = self._conn.execute(
                "SELECT id FROM events WHERE name = ?", (evt["name"],)
            ).fetchone()
            if existing:
                self._conn.execute(
                    """UPDATE events SET
                           track=?, race_type=?, laps=?, duration_mins=?,
                           tyre_wear=?, fuel_mult=?, refuel_rate_lps=?,
                           mandatory_stops=?, bop=?, tuning=?,
                           weather=?, damage=?,
                           avail_tyres=?, req_tyres=?, allowed_tuning=?,
                           notes=?, updated_at=?
                       WHERE name=?""",
                    (
                        evt.get("track", ""),
                        evt.get("race_type", "lap"),
                        evt.get("laps", 25),
                        evt.get("duration_mins", 60),
                        evt.get("tyre_wear", 1.0),
                        evt.get("fuel_mult", 1.0),
                        evt.get("refuel_rate_lps", 10.0),
                        evt.get("mandatory_stops", 0),
                        1 if evt.get("bop") else 0,
                        1 if evt.get("tuning", True) else 0,
                        evt.get("weather", "Fixed Dry"),
                        evt.get("damage", "None"),
                        json.dumps(evt.get("avail_tyres", [])),
                        json.dumps(evt.get("req_tyres", [])),
                        json.dumps(evt.get("allowed_tuning_categories", [])),
                        evt.get("notes", ""),
                        now,
                        evt["name"],
                    ),
                )
                return existing[0]
            else:
                cur = self._conn.execute(
                    """INSERT INTO events
                           (name, track, race_type, laps, duration_mins,
                            tyre_wear, fuel_mult, refuel_rate_lps,
                            mandatory_stops, bop, tuning,
                            weather, damage,
                            avail_tyres, req_tyres, allowed_tuning,
                            notes, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        evt["name"],
                        evt.get("track", ""),
                        evt.get("race_type", "lap"),
                        evt.get("laps", 25),
                        evt.get("duration_mins", 60),
                        evt.get("tyre_wear", 1.0),
                        evt.get("fuel_mult", 1.0),
                        evt.get("refuel_rate_lps", 10.0),
                        evt.get("mandatory_stops", 0),
                        1 if evt.get("bop") else 0,
                        1 if evt.get("tuning", True) else 0,
                        evt.get("weather", "Fixed Dry"),
                        evt.get("damage", "None"),
                        json.dumps(evt.get("avail_tyres", [])),
                        json.dumps(evt.get("req_tyres", [])),
                        json.dumps(evt.get("allowed_tuning_categories", [])),
                        evt.get("notes", ""),
                        now,
                        now,
                    ),
                )
                return cur.lastrowid or 0

    def get_event(self, name: str) -> dict | None:
        """Return a single event by name, or None if not found."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM events WHERE name = ?", (name,)
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        for key in ("avail_tyres", "req_tyres", "allowed_tuning"):
            try:
                d[key] = json.loads(d.get(key) or "[]")
            except (json.JSONDecodeError, TypeError):
                d[key] = []
        d["allowed_tuning_categories"] = d.pop("allowed_tuning", [])
        return d

    def get_all_events(self) -> list[dict]:
        """Return all events ordered by name."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM events ORDER BY name"
            ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            for key in ("avail_tyres", "req_tyres", "allowed_tuning"):
                try:
                    d[key] = json.loads(d.get(key) or "[]")
                except (json.JSONDecodeError, TypeError):
                    d[key] = []
            d["allowed_tuning_categories"] = d.pop("allowed_tuning", [])
            result.append(d)
        return result

    def delete_event(self, name: str) -> None:
        """Delete an event by name."""
        with self._lock:
            self._conn.execute("DELETE FROM events WHERE name = ?", (name,))

    def get_event_id(self, name: str) -> int:
        """Return the DB id for an event name, or 0 if not found."""
        with self._lock:
            row = self._conn.execute(
                "SELECT id FROM events WHERE name = ?", (name,)
            ).fetchone()
        return row[0] if row else 0

    # ------------------------------------------------------------------
    # Cars CRUD
    # ------------------------------------------------------------------

    def upsert_car(self, car: dict) -> int:
        """Insert or replace a car by name. Returns the car id."""
        with self._lock:
            existing = self._conn.execute(
                "SELECT id FROM cars WHERE name = ?", (car["name"],)
            ).fetchone()
            if existing:
                self._conn.execute(
                    """UPDATE cars SET
                           manufacturer=?, category=?, drivetrain=?,
                           power_hp=?, weight_kg=?, pp=?, notes=?
                       WHERE name=?""",
                    (
                        car.get("manufacturer", ""),
                        car.get("category", ""),
                        car.get("drivetrain", ""),
                        car.get("power_hp", 0.0),
                        car.get("weight_kg", 0.0),
                        car.get("pp", 0.0),
                        car.get("notes", ""),
                        car["name"],
                    ),
                )
                return existing[0]
            else:
                cur = self._conn.execute(
                    """INSERT INTO cars
                           (name, manufacturer, category, drivetrain,
                            power_hp, weight_kg, pp, notes)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        car["name"],
                        car.get("manufacturer", ""),
                        car.get("category", ""),
                        car.get("drivetrain", ""),
                        car.get("power_hp", 0.0),
                        car.get("weight_kg", 0.0),
                        car.get("pp", 0.0),
                        car.get("notes", ""),
                    ),
                )
                return cur.lastrowid or 0

    def get_car_id(self, name: str) -> int:
        """Return the DB id for a car name, or 0 if not found."""
        with self._lock:
            row = self._conn.execute(
                "SELECT id FROM cars WHERE name = ?", (name,)
            ).fetchone()
        return row[0] if row else 0

    def get_all_cars(self) -> list[dict]:
        """Return all cars ordered by name."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM cars ORDER BY name"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_rev_limit_threshold_for_car(self, car_name: str) -> float:
        """Return rev_limit_threshold_pct for a car looked up by name, defaulting to 0.90."""
        if not car_name:
            return 0.90
        with self._lock:
            row = self._conn.execute(
                "SELECT rev_limit_threshold_pct FROM cars WHERE name = ?",
                (car_name,),
            ).fetchone()
        if row is None or row[0] is None:
            return 0.90
        return float(row[0])

    # ------------------------------------------------------------------
    # User Profile
    # ------------------------------------------------------------------

    def get_user_profile(self) -> dict:
        """Return the single driver profile row, creating a default if absent."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM user_profile LIMIT 1"
            ).fetchone()
            if row:
                return dict(row)
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            self._conn.execute(
                """INSERT INTO user_profile
                       (name, driving_style_summary, setup_preferences,
                        brake_bias_preference, throttle_style,
                        trail_braking_preference, stability_preference,
                        rotation_preference, updated_at)
                   VALUES ('Leon','','','','','','','',?)""",
                (now,),
            )
            return dict(self._conn.execute(
                "SELECT * FROM user_profile LIMIT 1"
            ).fetchone())

    def update_user_profile(self, fields: dict) -> None:
        """Update named fields on the single user profile row."""
        allowed = {
            "name", "driving_style_summary", "setup_preferences",
            "brake_bias_preference", "throttle_style",
            "trail_braking_preference", "stability_preference",
            "rotation_preference",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        updates["updated_at"] = now
        sets = ", ".join(f"{k}=?" for k in updates)
        vals = list(updates.values())
        with self._lock:
            existing = self._conn.execute(
                "SELECT id FROM user_profile LIMIT 1"
            ).fetchone()
            if existing:
                self._conn.execute(
                    f"UPDATE user_profile SET {sets} WHERE id=?",
                    vals + [existing[0]],
                )
            else:
                self.get_user_profile()
                self._conn.execute(
                    f"UPDATE user_profile SET {sets}",
                    vals,
                )

    # ------------------------------------------------------------------
    # Setups CRUD
    # ------------------------------------------------------------------

    def save_setup(
        self,
        car_id: int,
        event_id: int,
        name: str,
        setup_dict: dict,
        ai_notes: str = "",
    ) -> int:
        """Persist a named setup. Returns the new setup id."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO setups
                       (car_id, event_id, name, setup_json, ai_notes, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (car_id, event_id, name, json.dumps(setup_dict), ai_notes, now, now),
            )
            return cur.lastrowid or 0

    def get_setups_for_car(self, car_id: int) -> list[dict]:
        """Return all setups for a given car, newest first."""
        with self._lock:
            rows = self._conn.execute(
                """SELECT id, car_id, event_id, name, ai_notes, created_at, updated_at
                   FROM setups WHERE car_id=? ORDER BY updated_at DESC""",
                (car_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_setup(self, setup_id: int) -> dict | None:
        """Return a single setup including the full setup_json, or None."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM setups WHERE id=?", (setup_id,)
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["setup_dict"] = json.loads(d.get("setup_json") or "{}")
        except (json.JSONDecodeError, TypeError):
            d["setup_dict"] = {}
        return d

    def delete_setup(self, setup_id: int) -> None:
        """Delete a setup by id."""
        with self._lock:
            self._conn.execute("DELETE FROM setups WHERE id=?", (setup_id,))

    def get_all_setups_legacy(self) -> list[dict]:
        """Return all saved setups in the legacy _saved_setups dict format.

        Each dict has: name (car name), setup_label, setup_id (DB PK),
        captured_at (= updated_at), plus all setup fields from setup_json.
        Used for backward-compatible loading at startup.
        """
        with self._lock:
            rows = self._conn.execute(
                """SELECT s.id, s.car_id, s.event_id, s.name AS setup_label,
                          s.setup_json, s.ai_notes, s.updated_at,
                          c.name AS car_name
                   FROM setups s
                   LEFT JOIN cars c ON c.id = s.car_id
                   ORDER BY s.updated_at DESC"""
            ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            try:
                setup_fields = json.loads(d.get("setup_json") or "{}")
            except (json.JSONDecodeError, TypeError):
                setup_fields = {}
            entry = {
                "name":        d.get("car_name") or "",
                "setup_label": d.get("setup_label", ""),
                "setup_id":    d.get("id", 0),
                "captured_at": d.get("updated_at", ""),
                "ai_notes":    d.get("ai_notes", ""),
            }
            entry.update(setup_fields)
            result.append(entry)
        return result

    def update_setup(
        self,
        setup_id: int,
        name: str,
        setup_dict: dict,
        ai_notes: str = "",
    ) -> None:
        """Update an existing setup."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock:
            self._conn.execute(
                """UPDATE setups SET name=?, setup_json=?, ai_notes=?, updated_at=?
                   WHERE id=?""",
                (name, json.dumps(setup_dict), ai_notes, now, setup_id),
            )

    # ------------------------------------------------------------------
    # AI interactions
    # ------------------------------------------------------------------

    def log_ai_interaction(self, entry: dict) -> int:
        """Persist an AI call record. Returns the new row id."""
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO ai_interactions
                   (timestamp, feature, model, prompt, structured_payload, response,
                    success, duration_ms, prompt_tokens, response_tokens,
                    estimated_cost, error_msg, validation_warnings, car_id, track,
                    session_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (entry.get("timestamp", ""),
                 entry.get("feature", ""),
                 entry.get("model", ""),
                 entry.get("prompt", ""),
                 entry.get("structured_payload", "{}"),
                 entry.get("response", ""),
                 1 if entry.get("success", True) else 0,
                 entry.get("duration_ms", 0),
                 entry.get("prompt_tokens", 0),
                 entry.get("response_tokens", 0),
                 entry.get("estimated_cost", 0.0),
                 entry.get("error_msg", ""),
                 json.dumps(entry.get("validation_warnings", [])),
                 entry.get("car_id", 0),
                 entry.get("track", ""),
                 entry.get("session_id", 0)),
            )
            self._conn.commit()
            return cur.lastrowid

    def get_ai_interactions(self, limit: int = 100) -> list:
        """Return recent AI call records newest-first."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM ai_interactions ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_recent_ai_recommendations(
        self,
        feature: str,
        car_id: int,
        track: str,
        limit: int = 2,
    ) -> list[str]:
        """Return recent successful AI responses for this feature + car + track."""
        with self._lock:
            rows = self._conn.execute(
                """SELECT response FROM ai_interactions
                   WHERE feature=? AND car_id=? AND track=? AND success=1
                   ORDER BY id DESC LIMIT ?""",
                (feature, car_id, track, limit),
            ).fetchall()
        return [r[0] for r in rows if r[0]]

    def insert_setup_recommendations(self, recs: list[dict]) -> None:
        if not recs:
            return
        with self._lock:
            self._conn.executemany(
                """INSERT INTO setup_recommendations
                   (ai_interaction_id, session_id, car_id, track, layout_id,
                    feature, recommendation_text, created_at)
                   VALUES (:ai_interaction_id, :session_id, :car_id, :track,
                           :layout_id, :feature, :recommendation_text, :created_at)""",
                recs,
            )
            self._conn.commit()

    def get_recommendations_for_context(self, car_id: int, track: str, limit: int = 2) -> str:
        with self._lock:
            rows = self._conn.execute(
                """SELECT recommendation_text FROM setup_recommendations
                   WHERE car_id = ? AND track = ?
                   ORDER BY id DESC LIMIT ?""",
                (car_id, track, limit),
            ).fetchall()
        if not rows:
            return ""
        return "\n\n---\n\n".join(r[0] for r in rows)

    def get_best_lap_for_session(self, session_id: int) -> int | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT MIN(lap_time_ms) FROM lap_records "
                "WHERE session_id = ? AND lap_time_ms > 0 AND is_pit_lap = 0",
                (session_id,),
            ).fetchone()
        if row is None or row[0] is None:
            return None
        return int(row[0])

    def update_recommendation_outcome(self, rec_id: int, outcome: str, outcome_session_id: int) -> None:
        import json as _json
        with self._lock:
            self._conn.execute(
                "UPDATE setup_recommendations SET outcome = ?, outcome_session_id = ? WHERE id = ?",
                (outcome, outcome_session_id, rec_id),
            )
            self._conn.commit()

            # Only write after_metrics once — preserve first capture (Q1 answer)
            row = self._conn.execute(
                "SELECT after_metrics FROM setup_recommendations WHERE id = ?", (rec_id,)
            ).fetchone()
            if row and row[0] in ("{}", ""):
                # Capture after metrics from outcome session (inline — lock already held)
                best_row = self._conn.execute(
                    "SELECT MIN(lap_time_ms) FROM lap_records "
                    "WHERE session_id = ? AND lap_time_ms > 0 AND is_pit_lap = 0",
                    (outcome_session_id,),
                ).fetchone()
                best_lap = int(best_row[0]) if best_row and best_row[0] is not None else 0
                fuel_row = self._conn.execute(
                    "SELECT AVG(fuel_used) FROM lap_records WHERE session_id = ? AND fuel_used > 0 AND is_pit_lap = 0",
                    (outcome_session_id,)
                ).fetchone()
                lap_count_row = self._conn.execute(
                    "SELECT COUNT(*) FROM lap_records WHERE session_id = ? AND is_pit_lap = 0",
                    (outcome_session_id,)
                ).fetchone()
                after = {
                    "best_lap_ms": best_lap,
                    "avg_fuel_per_lap": round(float(fuel_row[0] or 0), 3),
                    "lap_count": int(lap_count_row[0] or 0),
                }
                self._conn.execute(
                    "UPDATE setup_recommendations SET after_metrics = ? WHERE id = ?",
                    (_json.dumps(after), rec_id)
                )
                self._conn.commit()

    def set_recommendation_corner_issues(self, rec_id: int, corner_issue_ids: list) -> None:
        """Store the corner issue IDs that this recommendation was intended to fix."""
        import json as _json
        with self._lock:
            self._conn.execute(
                "UPDATE setup_recommendations SET corner_issue_ids = ? WHERE id = ?",
                (_json.dumps(corner_issue_ids), rec_id)
            )
            self._conn.commit()

    def get_last_recommendation_ids(self, car_id: int, track: str, limit: int) -> list[int]:
        """Return the IDs of the most recently inserted recommendations for a car+track."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT id FROM setup_recommendations WHERE car_id = ? AND track = ? ORDER BY id DESC LIMIT ?",
                (car_id, track, limit)
            ).fetchall()
        return [r[0] for r in rows]

    def apply_recommendation_for_car_track(
        self, car_id: int, track: str, session_id: int
    ) -> int | None:
        import json as _json
        with self._lock:
            row = self._conn.execute(
                """SELECT id, session_id FROM setup_recommendations
                   WHERE car_id = ? AND track = ? AND status = 'proposed'
                   ORDER BY id DESC LIMIT 1""",
                (car_id, track),
            ).fetchone()
        if row is None:
            return None
        rec_id, rec_session_id = row[0], row[1]

        best_lap = self.get_best_lap_for_session(rec_session_id)
        with self._lock:
            fuel_row = self._conn.execute(
                "SELECT AVG(fuel_used) FROM lap_records WHERE session_id = ? AND fuel_used > 0 AND is_pit_lap = 0",
                (rec_session_id,),
            ).fetchone()
            count_row = self._conn.execute(
                "SELECT COUNT(*) FROM lap_records WHERE session_id = ?",
                (rec_session_id,),
            ).fetchone()
        avg_fuel = round(float(fuel_row[0]), 3) if fuel_row and fuel_row[0] is not None else None
        lap_count = int(count_row[0]) if count_row else 0

        before_metrics = _json.dumps({
            "best_lap_ms": best_lap,
            "avg_fuel_per_lap": avg_fuel,
            "lap_count": lap_count,
        })

        with self._lock:
            self._conn.execute(
                """UPDATE setup_recommendations
                   SET status = 'applied', outcome_session_id = ?, before_metrics = ?
                   WHERE id = ?""",
                (session_id, before_metrics, rec_id),
            )
            self._conn.commit()
        return rec_id

    def get_setup_history_for_car_track(
        self, car_id: int, track: str, limit: int = 10
    ) -> str:
        import json as _json

        # --- Step 1: fetch all recommendation rows (lock acquired then released) ---
        with self._lock:
            rows = self._conn.execute(
                """SELECT id, recommendation_text, status, outcome, before_metrics,
                          after_metrics, corner_issue_ids, created_at
                   FROM setup_recommendations
                   WHERE car_id = ? AND track = ?
                   ORDER BY id ASC LIMIT ?""",
                (car_id, track, limit),
            ).fetchall()
        if not rows:
            return ""

        # --- Step 2: collect all corner_issue_ids that need resolving ---
        all_issue_ids: list[int] = []
        for row in rows:
            issue_ids_json = row[6]
            issue_ids_raw = issue_ids_json or "[]"
            if issue_ids_raw not in ("[]", ""):
                try:
                    ids = _json.loads(issue_ids_raw)
                    if isinstance(ids, list):
                        all_issue_ids.extend(int(i) for i in ids)
                except Exception:
                    pass

        # --- Step 3: bulk-fetch corner_issues in a single separate lock block ---
        corner_issue_map: dict[int, tuple] = {}
        if all_issue_ids:
            unique_ids = list(dict.fromkeys(all_issue_ids))  # deduplicate, preserve order
            placeholders = ",".join("?" * len(unique_ids))
            with self._lock:
                issue_rows = self._conn.execute(
                    f"SELECT id, issue_type, corner_id, severity FROM corner_issues"
                    f" WHERE id IN ({placeholders})",
                    unique_ids,
                ).fetchall()
            for ir in issue_rows:
                corner_issue_map[ir[0]] = (ir[1], ir[2], ir[3])

        # --- Step 4: render all rows using already-fetched data ---
        parts: list[str] = []
        for rec_id, rec_text, status, outcome, metrics_json, after_json, issue_ids_json, created_at in rows:
            try:
                metrics = _json.loads(metrics_json or "{}")
            except Exception:
                metrics = {}

            header = f"[{created_at}] Status: {status} | Outcome: {outcome}"
            lines = [header]

            best_ms = metrics.get("best_lap_ms")
            avg_fuel = metrics.get("avg_fuel_per_lap")
            lap_count = metrics.get("lap_count", 0)
            if best_ms is not None:
                mins, secs = divmod(best_ms // 1000, 60)
                ms = best_ms % 1000
                fuel_str = f", avg fuel {avg_fuel:.2f} L/lap" if avg_fuel is not None else ""
                lines.append(
                    f"Before metrics: best lap {mins}:{secs:02d}.{ms:03d}{fuel_str}, {lap_count} laps"
                )

            # Delta block: only when both before and after metrics are populated
            after_raw = after_json or "{}"
            before_raw = metrics_json or "{}"
            if after_raw not in ("{}", "") and before_raw not in ("{}", ""):
                try:
                    before = _json.loads(before_raw)
                    after = _json.loads(after_raw)
                    lap_delta_ms = after["best_lap_ms"] - before["best_lap_ms"]
                    if lap_delta_ms < 0:
                        direction = "faster"
                    elif lap_delta_ms > 0:
                        direction = "slower"
                    else:
                        direction = "unchanged"
                    fuel_delta = after["avg_fuel_per_lap"] - before["avg_fuel_per_lap"]
                    lines.append(
                        f"  Outcome metrics: {lap_delta_ms:+d} ms lap ({direction}), "
                        f"{fuel_delta:+.2f} L/lap fuel, {after['lap_count']} laps sampled"
                    )
                except Exception:
                    pass

            # Target issues block — use pre-fetched corner_issue_map (no nested lock)
            issue_ids_raw = issue_ids_json or "[]"
            if issue_ids_raw not in ("[]", ""):
                try:
                    issue_ids = _json.loads(issue_ids_raw)
                    if issue_ids:
                        issue_parts = []
                        for iid in issue_ids:
                            entry = corner_issue_map.get(int(iid))
                            if entry:
                                issue_type, corner_id, severity = entry
                                issue_parts.append(f"{issue_type} at {corner_id} (sev {severity:.0%})")
                        if issue_parts:
                            lines.append(f"  Target issues: {'; '.join(issue_parts)}")
                except Exception:
                    pass

            truncated = rec_text[:500] + ("…" if len(rec_text) > 500 else "")
            lines.append(f"Recommendation: {truncated}")
            parts.append("\n".join(lines))

        return "\n\n---\n\n".join(parts)

    # ------------------------------------------------------------------
    # Write API
    # ------------------------------------------------------------------

    def open_session(
        self,
        car_id: int,
        track: str,
        session_type: str,
        car_name: str = "",
        config_id: str = "",
        event_id: int = 0,
    ) -> int:
        """Create a new session row and return its id."""
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO sessions
                       (car_id, car_name, config_id, track, session_type, date_utc, event_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    car_id, car_name, config_id, track, session_type,
                    datetime.now(timezone.utc).isoformat(),
                    event_id,
                ),
            )
            return cur.lastrowid

    def write_lap(
        self,
        session_id: int,
        lap_num: int,
        lap_time_ms: int,
        fuel_used: float,
        stats: "LapStats | None",
        compound: str = "",
        event_id: int = 0,
        setup_id: int = 0,
        is_out_lap: bool = False,
        is_pit_lap: bool = False,
        delta_ms: int = 0,
        position: int = 0,
        session_type: str = "",
        frames: "list | None" = None,
        fuel_start: float = 0.0,
        fuel_end: float = 0.0,
    ) -> int:
        """Persist one lap's telemetry stats. Returns the new lap_record id.

        When stats is None, writes a metadata-only row (zeros for all telemetry
        fields). This preserves outlap/pit-lap metadata even when the recorder
        has no stats for that lap number (e.g. manual Save Session after clear).
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT car_id, track FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            car_id, track = row if row else (0, "")

            positions_blob = json.dumps({
                "lock_up":       (getattr(stats, "lock_up_positions", []) if stats else []),
                "wheelspin":     (getattr(stats, "wheelspin_positions", []) if stats else []),
                "oversteer":     (getattr(stats, "oversteer_positions", []) if stats else []),
                "snap_throttle": (getattr(stats, "snap_throttle_positions", []) if stats else []),
                "over_braking":  (getattr(stats, "over_braking_positions", []) if stats else []),
            })

            cur = self._conn.execute(
                """INSERT INTO lap_records
                   (session_id, car_id, track, lap_num, lap_time_ms, fuel_used,
                    lock_up_count, wheelspin_count, brake_consistency_m,
                    max_speed_kmh, avg_throttle_pct, avg_brake_pct, compound,
                    setup_id,
                    oversteer_count, oversteer_throttle_on,
                    kerb_count, bottoming_count, snap_throttle_count,
                    over_braking_count, abrupt_release_count, rev_limiter_count,
                    max_lat_g, off_track_count, tyre_temp_avg,
                    is_out_lap, is_pit_lap, delta_ms, position,
                    session_type, event_positions_json,
                    fuel_start, fuel_end,
                    tyre_temp_fl_avg, tyre_temp_fr_avg,
                    tyre_temp_rl_avg, tyre_temp_rr_avg)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    session_id, car_id, track, lap_num, lap_time_ms,
                    round(float(fuel_used), 4),
                    (stats.lock_up_count if stats else 0),
                    (stats.wheelspin_count if stats else 0),
                    round(float(stats.brake_consistency_m if stats else 0.0), 3),
                    round(float(stats.max_speed_kmh if stats else 0.0), 1),
                    round(float(stats.avg_throttle_pct if stats else 0.0), 1),
                    round(float(stats.avg_brake_pct if stats else 0.0), 1),
                    compound,
                    setup_id,
                    getattr(stats, "oversteer_count", 0),
                    getattr(stats, "oversteer_throttle_on_count", 0),
                    getattr(stats, "kerb_count", 0),
                    getattr(stats, "bottoming_count", 0),
                    getattr(stats, "snap_throttle_count", 0),
                    getattr(stats, "over_braking_count", 0),
                    getattr(stats, "abrupt_release_count", 0),
                    getattr(stats, "rev_limiter_count", 0),
                    round(float(getattr(stats, "max_lat_g", 0.0)), 3),
                    getattr(stats, "off_track_count", 0),
                    round(float(getattr(stats, "tyre_temp_avg", 0.0)), 1),
                    1 if is_out_lap else 0,
                    1 if is_pit_lap else 0,
                    delta_ms,
                    position,
                    session_type,
                    positions_blob,
                    round(float(fuel_start), 4),
                    round(float(fuel_end), 4),
                    round(float(getattr(stats, "tyre_temp_fl_avg", 0.0)), 1),
                    round(float(getattr(stats, "tyre_temp_fr_avg", 0.0)), 1),
                    round(float(getattr(stats, "tyre_temp_rl_avg", 0.0)), 1),
                    round(float(getattr(stats, "tyre_temp_rr_avg", 0.0)), 1),
                ),
            )
            lap_record_id = cur.lastrowid or 0

            self._conn.execute(
                "UPDATE sessions SET total_laps = total_laps + 1 WHERE id = ?",
                (session_id,),
            )

            # Persist compressed frame blob if provided
            if frames:
                try:
                    payload = json.dumps(
                        [_dc_asdict(f) for f in frames]
                    ).encode()
                    compressed = zlib.compress(payload, level=6)
                    now_str = datetime.now(timezone.utc).isoformat(timespec="seconds")
                    self._conn.execute(
                        """INSERT INTO lap_telemetry
                               (lap_record_id, session_id, lap_num, sample_hz,
                                frame_count, frames_blob, captured_at)
                           VALUES (?,?,?,?,?,?,?)""",
                        (
                            lap_record_id, session_id, lap_num, 10.0,
                            len(frames), compressed, now_str,
                        ),
                    )
                except Exception as _e:
                    print(f"[SessionDB] Frame storage failed for lap {lap_num}: {_e}")

        return lap_record_id

    def get_lap_telemetry(self, lap_record_id: int) -> list[dict]:
        """Return decompressed TelemetryFrame dicts for a lap, or [] on miss."""
        with self._lock:
            row = self._conn.execute(
                "SELECT frames_blob FROM lap_telemetry WHERE lap_record_id=?",
                (lap_record_id,),
            ).fetchone()
        if not row or not row[0]:
            return []
        try:
            return json.loads(zlib.decompress(row[0]).decode())
        except Exception as _e:
            print(f"[SessionDB] Frame decompress failed for record {lap_record_id}: {_e}")
            return []

    def write_setup(
        self,
        session_id: int,
        car_id: int,
        track: str,
        setup_dict: dict,
    ) -> None:
        """Persist a car setup snapshot (legacy AI snapshot path)."""
        with self._lock:
            self._conn.execute(
                """INSERT INTO setup_snapshots
                   (session_id, car_id, track, name, setup_json, captured_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    car_id,
                    track,
                    setup_dict.get("name", "Unnamed"),
                    json.dumps(setup_dict),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def update_lap_compound(self, session_id: int, lap_num: int, compound: str) -> None:
        """Persist a user-tagged tyre compound back to the lap record."""
        with self._lock:
            self._conn.execute(
                "UPDATE lap_records SET compound = ? WHERE session_id = ? AND lap_num = ?",
                (compound, session_id, lap_num),
            )
            self._conn.commit()

    def update_lap_setup_id(self, session_id: int, lap_num: int, setup_id: int) -> None:
        """Persist a setup ID tag back to the lap record."""
        with self._lock:
            self._conn.execute(
                "UPDATE lap_records SET setup_id=? WHERE session_id=? AND lap_num=?",
                (setup_id, session_id, lap_num),
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # Read API
    # ------------------------------------------------------------------

    def get_sessions_for_track(
        self, track: str, car_name: str = "", session_type: str = "", config_id: str = ""
    ) -> list:
        """Return recent sessions for this track, optionally filtered by race config."""
        clauses = ["s.track = ?"]
        params: list = [track]
        if config_id:
            clauses.append("s.config_id = ?")
            params.append(config_id)
        elif car_name:
            clauses.append("s.car_name = ?")
            params.append(car_name)
        if session_type:
            clauses.append("s.session_type = ?")
            params.append(session_type)
        where = " AND ".join(clauses)
        with self._lock:
            rows = self._conn.execute(
                f"""SELECT s.id, s.date_utc, s.total_laps, s.car_id, s.car_name,
                          s.config_id, s.track,
                          COUNT(CASE WHEN l.compound != '' THEN 1 END) AS tagged_laps
                   FROM sessions s
                   LEFT JOIN lap_records l ON l.session_id = s.id
                   WHERE {where}
                   GROUP BY s.id
                   ORDER BY s.date_utc DESC
                   LIMIT 30""",
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def get_all_sessions(self, limit: int = 60) -> list:
        """Return all sessions newest-first with car, track, config_id and compound count."""
        with self._lock:
            rows = self._conn.execute(
                """SELECT s.id, s.date_utc, s.total_laps, s.car_id, s.car_name,
                          s.config_id, s.track, s.session_type,
                          COUNT(CASE WHEN l.compound != '' THEN 1 END) AS tagged_laps
                   FROM sessions s
                   LEFT JOIN lap_records l ON l.session_id = s.id
                   WHERE s.total_laps > 0
                   GROUP BY s.id
                   ORDER BY s.date_utc DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_practice_sessions(self, car_id: int, track: str) -> list:
        """Return recent sessions for this car+track, newest first, with compound tag count."""
        with self._lock:
            rows = self._conn.execute(
                """SELECT s.id, s.date_utc, s.total_laps,
                          COUNT(CASE WHEN l.compound != '' THEN 1 END) AS tagged_laps
                   FROM sessions s
                   LEFT JOIN lap_records l ON l.session_id = s.id
                   WHERE s.car_id = ? AND s.track = ?
                   GROUP BY s.id
                   ORDER BY s.date_utc DESC
                   LIMIT 20""",
                (car_id, track),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_session_laps(
        self,
        session_id: int,
        exclude_pit: bool = False,
        exclude_out: bool = False,
        limit: int = 0,
    ) -> list:
        """Return valid lap records for a session, ordered by lap number.

        When exclude_pit/exclude_out are True the respective lap types are
        filtered out.  limit=0 means no limit.  Returns telemetry fields used
        by the per-lap AI prompt table (Phase 2-A / Group 16).
        """
        where = "session_id = ? AND lap_time_ms > 0"
        if exclude_pit:
            where += " AND is_pit_lap = 0"
        if exclude_out:
            where += " AND is_out_lap = 0"
        sql = (
            f"SELECT lap_num, lap_time_ms, compound, fuel_used,"
            f" is_pit_lap, is_out_lap, fuel_start, fuel_end,"
            f" lock_up_count, wheelspin_count, oversteer_count,"
            f" oversteer_throttle_on, kerb_count, max_lat_g,"
            f" tyre_temp_fl_avg, tyre_temp_fr_avg,"
            f" tyre_temp_rl_avg, tyre_temp_rr_avg,"
            f" event_positions_json"
            f" FROM lap_records"
            f" WHERE {where}"
            f" ORDER BY lap_num"
        )
        if limit > 0:
            sql += f" LIMIT {int(limit)}"
        with self._lock:
            rows = self._conn.execute(sql, (session_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_recent_fuel_sequence(self, car_id: int, track: str, limit: int = 15) -> list:
        """Return per-lap fuel consumption values (L/lap) for this car+track.

        Newest-first from DB, returned in chronological order (oldest first)
        for display in the AI prompt fuel trend block (Phase 2-B / Group 16).
        Excludes pit laps and out-laps.  Only laps where fuel_used > 0.
        """
        with self._lock:
            rows = self._conn.execute(
                """SELECT fuel_used FROM lap_records
                   WHERE car_id = ? AND track = ?
                     AND is_pit_lap = 0 AND is_out_lap = 0
                     AND fuel_used > 0
                   ORDER BY id DESC LIMIT ?""",
                (car_id, track, limit),
            ).fetchall()
        return [round(r["fuel_used"], 3) for r in reversed(rows)]

    def get_compound_lap_sequences(
        self,
        car_id: int,
        track: str,
        session_id: int = 0,
        limit_per_compound: int = 25,
    ) -> dict:
        """Return per-compound lap-time sequences (ms) for this car+track.

        When session_id > 0, filters to that session only; otherwise uses all
        history for the car+track.  Returns {compound_code: [lap_time_ms, ...]}
        in chronological order per compound (Phase 2-C / Group 16).
        Excludes pit laps, out-laps, and blank compound tags.
        """
        params: tuple
        if session_id > 0:
            where = "car_id = ? AND track = ? AND session_id = ?"
            params = (car_id, track, session_id)
        else:
            where = "car_id = ? AND track = ?"
            params = (car_id, track)
        with self._lock:
            rows = self._conn.execute(
                f"""SELECT compound, lap_time_ms FROM lap_records
                    WHERE {where}
                      AND is_pit_lap = 0 AND is_out_lap = 0
                      AND lap_time_ms > 0 AND compound != ''
                    ORDER BY id ASC""",
                params,
            ).fetchall()
        seqs: dict[str, list[int]] = {}
        for r in rows:
            seqs.setdefault(r["compound"], []).append(r["lap_time_ms"])
        # Cap each compound to the most recent limit_per_compound laps
        return {c: times[-limit_per_compound:] for c, times in seqs.items()}

    def get_strategy_lap_data(
        self,
        car_id: int,
        track: str,
        session_id: int,
        ui_table_data: dict[str, list[float]],
    ) -> dict[str, list[float]]:
        """Return per-compound lap times (ms) for strategy analysis.

        DB data is authoritative. UI table data fills in compounds the DB
        has no data for. Returns {} if both sources are empty.
        """
        db_data: dict[str, list[float]] = {}
        if car_id > 0 and track:
            try:
                raw = self.get_compound_lap_sequences(
                    car_id, track, session_id=session_id
                )
                db_data = {c: [float(t) for t in times] for c, times in raw.items()}
            except Exception:
                db_data = {}

        merged: dict[str, list[float]] = dict(db_data)
        for compound, times in ui_table_data.items():
            if compound and compound not in merged:
                merged[compound] = list(times)

        return merged

    # ------------------------------------------------------------------
    # Corner-issue learning (Group 16 / schema v4)
    # ------------------------------------------------------------------

    def save_corner_issues(self, issues: list) -> None:
        """Persist a list of CornerIssue objects (or dicts) for the current session.

        Accepts both CornerIssue dataclass instances and plain dicts so tests
        can use lightweight dicts without importing the dataclass.
        """
        if not issues:
            return

        def _val(issue, key: str, default=None):
            return getattr(issue, key, None) if not isinstance(issue, dict) else issue.get(key, default)

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock:
            self._conn.executemany(
                """INSERT INTO corner_issues
                   (car_id, track, corner_id, issue_type, phase,
                    lap_count, total_laps, severity, confidence,
                    evidence, session_id, detected_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        _val(i, "car_id", 0),
                        _val(i, "track", ""),
                        _val(i, "corner_id", ""),
                        _val(i, "issue_type", ""),
                        _val(i, "phase", ""),
                        _val(i, "lap_count", 0),
                        _val(i, "total_laps", 0),
                        _val(i, "severity", 0.0),
                        _val(i, "confidence", 0.0),
                        _val(i, "evidence", ""),
                        _val(i, "session_id", 0),
                        _val(i, "detected_at", None) or now,
                    )
                    for i in issues
                ],
            )
            self._conn.commit()

    def get_corner_issues(
        self, car_id: int, track: str, session_id: int = 0
    ) -> list[dict]:
        """Return corner issues for this car+track, optionally filtered to one session."""
        if session_id > 0:
            where = "car_id = ? AND track = ? AND session_id = ?"
            params: tuple = (car_id, track, session_id)
        else:
            where = "car_id = ? AND track = ?"
            params = (car_id, track)
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM corner_issues WHERE {where} ORDER BY severity DESC",
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def get_previous_corner_issues(
        self, car_id: int, track: str, exclude_session_id: int
    ) -> list[dict]:
        """Return corner issues from all sessions EXCEPT the current one.

        Used for fix verification: compare the previous session's patterns
        against what was just detected.
        """
        with self._lock:
            rows = self._conn.execute(
                """SELECT * FROM corner_issues
                   WHERE car_id = ? AND track = ? AND session_id != ?
                   ORDER BY detected_at DESC""",
                (car_id, track, exclude_session_id),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_car_track_summary(
        self, car_id: int, track: str, limit: int = 50
    ) -> dict:
        """Return aggregated historical stats for a car+track combination."""
        with self._lock:
            rows = self._conn.execute(
                """SELECT lap_time_ms, fuel_used, lock_up_count, wheelspin_count,
                          brake_consistency_m, max_speed_kmh, compound
                   FROM lap_records
                   WHERE car_id = ? AND track = ? AND lap_time_ms > 0
                   ORDER BY id DESC LIMIT ?""",
                (car_id, track, limit),
            ).fetchall()

            if not rows:
                return {}

            session_count = self._conn.execute(
                """SELECT COUNT(DISTINCT s.id) FROM sessions s
                   JOIN lap_records l ON l.session_id = s.id
                   WHERE l.car_id = ? AND l.track = ?""",
                (car_id, track),
            ).fetchone()[0]

        times  = [r[0] for r in rows if r[0] > 0]
        fuels  = [r[1] for r in rows if r[1] is not None and r[1] > 0]
        lkups  = [r[2] for r in rows if r[2] is not None]
        spins  = [r[3] for r in rows if r[3] is not None]

        compound_times: dict[str, list[int]] = {}
        for r in rows:
            c = r[6] or ""
            if c and r[0] > 0:
                compound_times.setdefault(c, []).append(r[0])

        return {
            "best_lap_ms":    min(times) if times else 0,
            "avg_lap_ms":     int(_mean(times)) if times else 0,
            "avg_fuel":       round(_mean(fuels), 3) if fuels else 0.0,
            "avg_lockups":    round(_mean(lkups), 2) if lkups else 0.0,
            "avg_wheelspin":  round(_mean(spins), 2) if spins else 0.0,
            "total_laps":     len(rows),
            "sessions_count": session_count,
            "compound_refs":  {c: int(_mean(t)) for c, t in compound_times.items()},
        }

    def get_all_laps_summary(self, recent_n: int = 30) -> dict:
        """Aggregate telemetry stats across all cars and tracks for the driver profile."""
        with self._lock:
            all_rows = self._conn.execute(
                """SELECT lock_up_count, wheelspin_count, brake_consistency_m,
                          track, compound
                   FROM lap_records WHERE lap_time_ms > 0
                   ORDER BY id ASC"""
            ).fetchall()

            recent_rows = self._conn.execute(
                """SELECT lock_up_count, wheelspin_count, brake_consistency_m
                   FROM lap_records WHERE lap_time_ms > 0
                   ORDER BY id DESC LIMIT ?""", (recent_n,)
            ).fetchall()

            session_info = self._conn.execute(
                "SELECT COUNT(*), MIN(date_utc), MAX(date_utc) FROM sessions WHERE total_laps > 0"
            ).fetchone()

            track_rows = self._conn.execute(
                """SELECT track, COUNT(*) as cnt, MIN(lap_time_ms),
                          AVG(lock_up_count), AVG(wheelspin_count)
                   FROM lap_records WHERE lap_time_ms > 0 AND track != ''
                   GROUP BY track ORDER BY cnt DESC LIMIT 8"""
            ).fetchall()

            compound_rows = self._conn.execute(
                """SELECT compound, MIN(lap_time_ms), COUNT(*)
                   FROM lap_records WHERE lap_time_ms > 0 AND compound != ''
                   GROUP BY compound"""
            ).fetchall()

        if not all_rows:
            return {}

        lkups   = [r[0] for r in all_rows if r[0] is not None]
        spins   = [r[1] for r in all_rows if r[1] is not None]
        consist = [r[2] for r in all_rows if r[2] is not None and r[2] >= 0]

        r_lkups   = [r[0] for r in recent_rows if r[0] is not None]
        r_spins   = [r[1] for r in recent_rows if r[1] is not None]
        r_consist = [r[2] for r in recent_rows if r[2] is not None and r[2] >= 0]

        def _trend(all_avg: float, recent_avg: float) -> str:
            if all_avg == 0:
                return "stable"
            diff_pct = (recent_avg - all_avg) / all_avg
            if abs(diff_pct) < 0.10:
                return "stable"
            return "improving" if recent_avg < all_avg else "worsening"

        avg_lkups   = round(_mean(lkups), 2)   if lkups   else 0.0
        avg_spins   = round(_mean(spins), 2)   if spins   else 0.0
        avg_consist = round(_mean(consist), 1) if consist else -1.0
        rec_lkups   = round(_mean(r_lkups), 2)   if r_lkups   else avg_lkups
        rec_spins   = round(_mean(r_spins), 2)   if r_spins   else avg_spins
        rec_consist = round(_mean(r_consist), 1) if r_consist else avg_consist

        return {
            "total_sessions":    session_info[0] if session_info else 0,
            "total_laps":        len(all_rows),
            "first_session":     (session_info[1] or "")[:10],
            "last_session":      (session_info[2] or "")[:10],
            "avg_lockups":       avg_lkups,
            "avg_wheelspin":     avg_spins,
            "avg_consistency_m": avg_consist,
            "recent_lockups":    rec_lkups,
            "recent_wheelspin":  rec_spins,
            "recent_consistency_m": rec_consist,
            "lockup_trend":      _trend(avg_lkups, rec_lkups),
            "wheelspin_trend":   _trend(avg_spins, rec_spins),
            "consistency_trend": _trend(avg_consist, rec_consist) if avg_consist >= 0 else "stable",
            "track_breakdown": [
                {"track": r[0], "laps": r[1], "best_ms": r[2],
                 "avg_lockups": round(r[3] or 0, 1), "avg_wheelspin": round(r[4] or 0, 1)}
                for r in track_rows
            ],
            "compound_bests": {
                r[0]: {"best_ms": r[1], "laps": r[2]} for r in compound_rows
            },
        }

    def get_setup_comparison(self, car_id: int, track: str) -> list[dict]:
        """Return per-setup, per-compound averages for AI comparison prompts."""
        with self._lock:
            rows = self._conn.execute(
                """SELECT setup_id, compound,
                          COUNT(*)             AS laps,
                          AVG(lap_time_ms)     AS avg_ms,
                          MIN(lap_time_ms)     AS best_ms,
                          AVG(fuel_used)       AS avg_fuel,
                          AVG(wheelspin_count) AS avg_wheelspin,
                          AVG(lock_up_count)   AS avg_lockup
                   FROM lap_records
                   WHERE car_id=? AND track=? AND setup_id>0 AND compound!='' AND is_pit_lap=0
                   GROUP BY setup_id, compound
                   ORDER BY setup_id, compound""",
                (car_id, track),
            ).fetchall()
        return [dict(r) for r in rows]

    def format_history_for_prompt(self, car_id: int, track: str) -> str:
        """Return a human-readable summary string for injection into AI prompts."""
        h = self.get_car_track_summary(car_id, track)
        if not h or h.get("total_laps", 0) == 0:
            return "(No historical data for this car and track combination.)"

        best_str = ms_to_str(h["best_lap_ms"])
        avg_str  = ms_to_str(h["avg_lap_ms"])

        compound_parts: list[str] = []
        for c, ms in sorted(h.get("compound_refs", {}).items()):
            compound_parts.append(f"{c}: {ms_to_str(ms)}")
        compound_str = ", ".join(compound_parts) if compound_parts else "N/A"

        lines = [
            f"Historical data — Car #{car_id} at {track or 'unknown track'}:",
            f"  {h['total_laps']} laps across {h['sessions_count']} session(s)",
            f"  Best lap: {best_str}  |  Average lap: {avg_str}",
            f"  Average fuel per lap: {h['avg_fuel']:.2f} L",
            f"  Average lock-ups per lap: {h['avg_lockups']:.1f}",
            f"  Average wheelspin events per lap: {h['avg_wheelspin']:.1f}",
            f"  Compound lap time references: {compound_str}",
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Driver feedback
    # ------------------------------------------------------------------

    def write_feedback(
        self,
        session_id: int,
        lap_num: int,
        feedback: dict,
        config_id: str = "",
    ) -> int:
        submitted_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO driver_feedback
                       (session_id, lap_num, submitted_at,
                        corner_entry, mid_corner, exit_stability,
                        rear_braking, tyre_condition, fuel_use,
                        notes, config_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    session_id, lap_num, submitted_at,
                    feedback.get("corner_entry", ""),
                    feedback.get("mid_corner", ""),
                    feedback.get("exit_stability", ""),
                    feedback.get("rear_braking", ""),
                    feedback.get("tyre_condition", ""),
                    feedback.get("fuel_use", ""),
                    feedback.get("notes", ""),
                    config_id,
                ),
            )
            self._conn.commit()
            return cur.lastrowid or 0

    def get_recent_feedback(
        self,
        car_id: int,
        track: str,
        limit: int = 5,
    ) -> list[dict]:
        """Return most recent driver_feedback rows for this car + track."""
        with self._lock:
            rows = self._conn.execute(
                """SELECT df.* FROM driver_feedback df
                   JOIN sessions s ON s.id = df.session_id
                   WHERE s.car_id = ? AND s.track = ?
                   ORDER BY df.submitted_at DESC LIMIT ?""",
                (car_id, track, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Grip alerts
    # ------------------------------------------------------------------

    def write_grip_alert(
        self,
        session_id: int,
        lap_num: int,
        score: int,
        alert_type: str,
    ) -> None:
        fired_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock:
            self._conn.execute(
                """INSERT INTO grip_alerts
                       (session_id, lap_num, score, alert_type, fired_at)
                   VALUES (?,?,?,?,?)""",
                (session_id, lap_num, score, alert_type, fired_at),
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # Strategy snapshots
    # ------------------------------------------------------------------

    def write_strategy_snapshot(
        self,
        config_id: str,
        strategies_json: str,
    ) -> int:
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO strategy_snapshots
                       (config_id, created_at, strategies_json, selected_rank)
                   VALUES (?,?,?,0)""",
                (config_id, created_at, strategies_json),
            )
            self._conn.commit()
            return cur.lastrowid or 0

    def update_strategy_selection(self, snapshot_id: int, rank: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE strategy_snapshots SET selected_rank=? WHERE id=?",
                (rank, snapshot_id),
            )
            self._conn.commit()
