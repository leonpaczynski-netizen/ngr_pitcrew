"""Pit Crew database schema, version 1.

A clean start.  The previous database carried 43 migrations covering setup
authoring, evidence, assurance and a knowledge graph — none of which exist any
more.  Nothing is inherited from it except the reference catalogs, which are
files rather than rows.

Design notes worth keeping in mind when extending this:

* Per-lap telemetry lives in `lap_frames` as one compressed blob per lap, not
  as rows per sample.  A lap is ~7,200 samples; a row-per-sample table would be
  millions of rows for a single practice session and buys nothing, because the
  frames are always read whole.
* Derived per-lap events (lock-ups, wheelspin, off-track) are **not** stored.
  They are computed from the frames on demand.  Storing them would create a
  second source of truth that goes stale whenever the detection thresholds are
  tuned.
* `pit_loss_secs` is an event field.  It used to hide in `config.json` with one
  code path defaulting to 20 s and another to 23 s.
"""
from __future__ import annotations

SCHEMA_VERSION = 1

DDL = """
CREATE TABLE IF NOT EXISTS events (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT    NOT NULL UNIQUE,
    track               TEXT    NOT NULL,
    layout              TEXT,
    car_id              INTEGER,
    car_name            TEXT,
    race_type           TEXT    NOT NULL DEFAULT 'laps',   -- 'laps' | 'time'
    race_laps           INTEGER,
    race_minutes        REAL,
    weather             TEXT    NOT NULL DEFAULT 'dry',
    tyre_wear_mult      REAL    NOT NULL DEFAULT 1.0,
    fuel_mult           REAL    NOT NULL DEFAULT 1.0,
    refuel_rate_lps     REAL    NOT NULL DEFAULT 2.5,
    pit_loss_secs       REAL    NOT NULL DEFAULT 20.0,
    mandatory_stops     INTEGER NOT NULL DEFAULT 0,
    available_compounds TEXT    NOT NULL DEFAULT '[]',     -- JSON array of codes
    required_compounds  TEXT    NOT NULL DEFAULT '[]',     -- JSON array of codes
    tune_label          TEXT,                              -- which Claude-built tune is fitted
    notes               TEXT,
    created_at          TEXT    NOT NULL,
    updated_at          TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id    INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    kind        TEXT    NOT NULL,          -- 'practice' | 'race'
    tune_label  TEXT,
    started_at  TEXT    NOT NULL,
    ended_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_event ON sessions(event_id, kind);

CREATE TABLE IF NOT EXISTS laps (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    lap_num       INTEGER NOT NULL,
    lap_time_ms   INTEGER NOT NULL,
    delta_ms      INTEGER NOT NULL DEFAULT 0,
    fuel_start    REAL    NOT NULL DEFAULT 0.0,
    fuel_end      REAL    NOT NULL DEFAULT 0.0,
    fuel_used     REAL    NOT NULL DEFAULT 0.0,
    position      INTEGER NOT NULL DEFAULT 0,
    compound      TEXT,                    -- tagged by the driver after the session
    is_pit_lap    INTEGER NOT NULL DEFAULT 0,
    is_out_lap    INTEGER NOT NULL DEFAULT 0,
    recorded_at   TEXT    NOT NULL,
    UNIQUE(session_id, lap_num)
);
CREATE INDEX IF NOT EXISTS idx_laps_session ON laps(session_id);

CREATE TABLE IF NOT EXISTS lap_frames (
    lap_id      INTEGER PRIMARY KEY REFERENCES laps(id) ON DELETE CASCADE,
    sample_hz   REAL    NOT NULL,
    frame_count INTEGER NOT NULL,
    blob        BLOB    NOT NULL
);

CREATE TABLE IF NOT EXISTS strategies (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id    INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    status      TEXT    NOT NULL DEFAULT 'candidate',   -- 'candidate' | 'approved'
    label       TEXT,
    plan_json   TEXT    NOT NULL,
    evidence_json TEXT,
    created_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_strategies_event ON strategies(event_id, status);

CREATE TABLE IF NOT EXISTS race_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id     INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    strategy_id  INTEGER REFERENCES strategies(id),
    session_id   INTEGER REFERENCES sessions(id),
    started_at   TEXT    NOT NULL,
    finished_at  TEXT
);

-- Immutable chain: a live re-plan appends, never updates.  parent_id lets the
-- whole race be reconstructed afterwards, including plans that were offered
-- and declined.
CREATE TABLE IF NOT EXISTS race_revisions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    race_run_id  INTEGER NOT NULL REFERENCES race_runs(id) ON DELETE CASCADE,
    parent_id    INTEGER REFERENCES race_revisions(id),
    lap_num      INTEGER NOT NULL,
    reason       TEXT    NOT NULL,
    accepted     INTEGER NOT NULL DEFAULT 0,
    plan_json    TEXT    NOT NULL,
    created_at   TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_revisions_run ON race_revisions(race_run_id);
"""
