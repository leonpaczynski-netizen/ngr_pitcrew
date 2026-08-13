"""Pit Crew database schema, version 3.

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

Versions, and what upgrading means here:

* **v1** the clean start.
* **v2** adds `prompt_issues` — the log of every prompt the Race Engineer
  screen produced and whatever the knowledge base sent back.
* **v3** replaces the per-axle tyre gauge (`wear_front`, `wear_rear`) with
  per-corner (`wear_fl`, `wear_fr`, `wear_rl`, `wear_rr`).  GT7 wears the four
  corners at different rates and shows them separately on its own gauge; an
  axle pair could not express a car eating its front-left in particular, which
  is exactly the finding an open-tuning no-BoP setup produces.

`CREATE ... IF NOT EXISTS` plus `ADDED_COLUMNS` covers anything additive, and
that carried v1 -> v2.  **v3 is the first change it cannot express** — it drops
two columns and back-fills four — so `MIGRATIONS` below exists, and anything
that changes or removes an existing column belongs there from now on rather
than in one more `IF NOT EXISTS`.
"""
from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 3

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
    -- Timed races only. What GT7 allows for completing the lap in progress
    -- once the clock expires, in seconds. The race ends at the first line
    -- crossing after the limit, so its longest possible duration is the limit
    -- plus one lap, or plus this, whichever is shorter. Null means the lap is
    -- the only ceiling.
    extra_time_s        REAL,
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
    -- Declared event facts the race-engineering prompts carry. They exist
    -- here rather than as questions on a form because the app is meant to
    -- know them: asking for them again at prompt time is the transcription
    -- step this whole feature removes.
    start_type          TEXT,          -- 'Rolling' | 'Standing' | ...
    time_of_day         TEXT,          -- 'Fixed day' | 'Day to night' | ...
    priority            TEXT,          -- what this round is being tuned for
    pp_cap              REAL,          -- league PP ceiling, null when none
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
    -- Driver's reading of the in-game tyre gauge, fraction consumed 0-1, one
    -- per corner. The only wear figure anchored to the game's own number.
    --
    -- Per corner rather than per axle because the four wear at different
    -- rates and the stint ends when the *worst single tyre* is done, not when
    -- an axle average is. Null is a corner he did not read, and stays null.
    wear_fl       REAL,
    wear_fr       REAL,
    wear_rl       REAL,
    wear_rr       REAL,
    gear_ratios   TEXT,          -- JSON array, the ratios fitted
    -- The driver's declaration that this lap went out on a fresh set. GT7
    -- broadcasts no tyre-change event, so nothing else can fill this in: a
    -- refuel is visible in the feed, a tyre change is not. Null means he has
    -- not said, and null is not 0 - a 0 here would claim the set carried over,
    -- which the app has no evidence for either way.
    tyres_fresh   INTEGER,
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

-- Every prompt the Race Engineer screen issued, and what came back.
--
-- Same reasoning as `race_revisions`: advice that is never recorded cannot be
-- audited.  The body is stored whole rather than as the fields it was built
-- from, because the point is to know exactly what was asked -- and
-- `prompt_version` is what makes a returned setup sheet traceable to the
-- template that asked for it.
--
-- The reply is not parsed and is not meant to be.  It needs to be findable,
-- not machine-legible: the setup values inside it re-enter the app through
-- the Event screen's existing paste box.
CREATE TABLE IF NOT EXISTS prompt_issues (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id       INTEGER REFERENCES events(id) ON DELETE CASCADE,
    -- Null for a setup brief: it is written before anything has been run.
    session_id     INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
    kind           TEXT    NOT NULL,   -- 'brief' | 'refinement' | 'outcome'
    car_name       TEXT,
    circuit        TEXT,
    prompt_version TEXT    NOT NULL,
    app_version    TEXT    NOT NULL,
    body           TEXT    NOT NULL,
    reply          TEXT,
    replied_at     TEXT,
    issued_at      TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_prompt_issues_event
    ON prompt_issues(event_id, issued_at DESC);
"""

# Columns added to tables that already existed in an earlier version.
#
# `CREATE TABLE IF NOT EXISTS` does nothing to a table that is already there,
# so a new column in the DDL above would never reach an existing file. These
# are applied by `Store._init_schema` with `ALTER TABLE ... ADD COLUMN`, which
# sqlite does in place and which cannot fail destructively - the new column
# reads null on every existing row, which is exactly what it means.
#
# Only nullable columns with no default belong here. Anything that needs a
# back-fill, a type change or a drop needs a real numbered migration instead.
ADDED_COLUMNS: dict[str, tuple[tuple[str, str], ...]] = {
    "events": (
        ("extra_time_s", "REAL"),
        ("start_type", "TEXT"),
        ("time_of_day", "TEXT"),
        ("priority", "TEXT"),
        ("pp_cap", "REAL"),
    ),
    "laps": (
        ("gear_ratios", "TEXT"),
        ("tyres_fresh", "INTEGER"),
    ),
}


# ---------------------------------------------------------------- migrations
#
# Numbered, ordered, and run once each by `Store._init_schema`. A migration
# here is for the changes `ADDED_COLUMNS` cannot express: a column that has to
# change type, be dropped, or be back-filled from another.
#
# Two rules, both learned the hard way:
#
# * **Guard on the current shape, not on the version number.** A brand new file
#   is created from the DDL above at `user_version` 0, so it already has the
#   v3 layout before any migration runs. Every migration must therefore be a
#   no-op when its work is already done, or a fresh database breaks on its
#   first open.
# * **Never rebuild a table to drop a column from it.** The 12-step
#   create-copy-drop-rename dance is the textbook answer, and here it would
#   destroy data: `lap_frames` references `laps` with `ON DELETE CASCADE` and
#   foreign keys are on, so dropping `laps` silently takes every recorded
#   telemetry blob with it. `ALTER TABLE ... DROP COLUMN` (sqlite 3.35+) is
#   in place and cascades nothing.


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _migrate_v3_wear_per_corner(conn: sqlite3.Connection) -> None:
    """Per-axle tyre gauge becomes per-corner.

    The back-fill spreads each axle reading across both of its corners. That
    is what was actually meant when the number was entered — he read one
    figure per axle off the gauge and both wheels on that axle were described
    by it — so it is a restatement rather than an invention. It does overstate
    precision on the better corner of a pair, which no later reading can
    correct; there is no way to recover a per-corner truth that was never
    recorded, and discarding the readings entirely would be worse.
    """
    columns = _columns(conn, "laps")
    if "wear_front" not in columns:
        return                      # already v3, or a file built fresh from the DDL

    for corner in ("wear_fl", "wear_fr", "wear_rl", "wear_rr"):
        if corner not in columns:
            conn.execute(f"ALTER TABLE laps ADD COLUMN {corner} REAL")

    conn.execute(
        "UPDATE laps SET wear_fl = wear_front, wear_fr = wear_front "
        "WHERE wear_front IS NOT NULL")
    conn.execute(
        "UPDATE laps SET wear_rl = wear_rear, wear_rr = wear_rear "
        "WHERE wear_rear IS NOT NULL")

    conn.execute("ALTER TABLE laps DROP COLUMN wear_front")
    conn.execute("ALTER TABLE laps DROP COLUMN wear_rear")


MIGRATIONS: dict[int, tuple[str, object]] = {
    3: ("per-corner tyre wear", _migrate_v3_wear_per_corner),
}
