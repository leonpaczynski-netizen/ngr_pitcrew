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
-- Small key/value store for things like which event is active. Not a settings
-- system; if it grows past a handful of keys it wants a real table.
CREATE TABLE IF NOT EXISTS app_state (
    key   TEXT PRIMARY KEY,
    value TEXT
);

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
    -- Strings, not numbers, because "Off" is a real setting and a number
    -- cannot express it. Parsed to a factor where the maths needs one.
    tyre_wear_mult      TEXT    NOT NULL DEFAULT 'Off',
    fuel_mult           TEXT    NOT NULL DEFAULT 'Off',
    game_version        TEXT,
    abs_setting         TEXT,          -- 'Off' | 'Weak' | 'Default'
    tcs                 INTEGER,       -- 0-5
    countersteer        INTEGER,       -- assist on/off
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

-- The sheet as run.  Pure app state: no telemetry, no derivation, no advice.
-- Keys inside values_json are the export contract's shared vocabulary, so a
-- sheet round-trips to the tune builder and back with no translation.
CREATE TABLE IF NOT EXISTS setup_sheets (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    car_name     TEXT    NOT NULL,
    sheet_name   TEXT    NOT NULL,
    values_json  TEXT    NOT NULL DEFAULT '{}',
    gears_json   TEXT,                      -- JSON array, 1st..nth
    performance_json TEXT,                  -- restrictor, ECU, ballast
    build_json   TEXT,                      -- bhp, weight, PP
    notes        TEXT,
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL,
    UNIQUE(car_name, sheet_name)
);

-- Mid-session changes, structured rather than prose: they are exactly what
-- invalidates a corner aggregate, so they have to be machine-legible.
CREATE TABLE IF NOT EXISTS setup_changes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    from_lap   INTEGER NOT NULL,
    key        TEXT    NOT NULL,
    from_value REAL,
    to_value   REAL,
    created_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_changes_session ON setup_changes(session_id);

-- The car's slider limits, read off its settings screen once and never
-- re-entered.  Worth more than the setup values themselves: they are what
-- makes a returned recommendation enterable without clamping.
CREATE TABLE IF NOT EXISTS range_records (
    car_name      TEXT PRIMARY KEY,
    measured_date TEXT NOT NULL,
    game_version  TEXT,
    verified      INTEGER NOT NULL DEFAULT 0,   -- 1 = read off the screen
    ranges_json   TEXT NOT NULL DEFAULT '{}',
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id    INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    kind        TEXT    NOT NULL,          -- 'practice' | 'race'
    setup_sheet_id INTEGER REFERENCES setup_sheets(id),
    tune_label  TEXT,
    -- Observed from the stream, not configured: which packet format actually
    -- arrived, and the car class the game reported. The export must declare
    -- the format so a null channel reads as "not offered by this format"
    -- rather than "not measured".
    packet_format TEXT,
    car_category  TEXT,
    -- 100 L for almost every car, 5 for karts, 0 for electric. Zero is a real
    -- value, so the divide is guarded rather than the field.
    fuel_capacity_l REAL,
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
    -- GT7 does not broadcast the fuel map, so this is null unless the driver
    -- says what he was running. Never inferred.
    fuel_map      INTEGER,
    is_pit_lap    INTEGER NOT NULL DEFAULT 0,
    is_out_lap    INTEGER NOT NULL DEFAULT 0,
    -- Excluded from the counted set: out-lap, in-lap, an off, traffic. The
    -- reason travels to the export's notes, because it is cheaper to explain
    -- an exclusion than to have a setup built on a misread aggregate.
    excluded         INTEGER NOT NULL DEFAULT 0,
    exclusion_reason TEXT,
    -- Driver's reading of the in-game tyre gauge, fraction consumed 0-1. The
    -- only wear figure anchored to the game's own number.
    wear_front    REAL,
    wear_rear     REAL,
    recorded_at   TEXT    NOT NULL,
    UNIQUE(session_id, lap_num)
);

-- Corner definitions per circuit. Stored rather than re-detected each session:
-- re-detection renumbers the corners the first time the driver takes a
-- different line, and a corner aggregate is worthless if T3 means a different
-- corner next week.
CREATE TABLE IF NOT EXISTS corner_models (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    circuit_key  TEXT    NOT NULL UNIQUE,   -- track + layout, slugged
    model_id     TEXT    NOT NULL,
    version      INTEGER NOT NULL DEFAULT 1,
    source       TEXT    NOT NULL,          -- 'auto-segment' | 'track-map'
    lap_length_m REAL    NOT NULL,
    corners_json TEXT    NOT NULL,
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL
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
