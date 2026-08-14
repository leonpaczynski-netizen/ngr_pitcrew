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

SCHEMA_VERSION = 5

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
    -- Where in the game day the race starts, as an hour 0-24, and how fast
    -- GT7's clock runs against the real one. A 2-hour race at x12 covers a
    -- full day and night: the track cools, stints lengthen, and a harder
    -- compound can drop below its working range. GT7 broadcasts neither track
    -- nor air temperature, so these two numbers plus the recorded clock are
    -- the only way to know whether practice has been in the race's conditions.
    start_hour          REAL,
    time_multiplier     REAL,
    -- The league's weather regulation: 'Fixed' (the round runs one setting
    -- whatever the circuit offers) or 'Random' (the circuit throws up whatever
    -- it has). Fixed sunny makes every circuit's rain irrelevant.
    weather_rule        TEXT,
    -- Whether this circuit can produce rain at all. **Declared, not measured**
    -- - GT7 broadcasts no weather channel in any packet format, so there is
    -- nothing in the stream to read it from or check it against. Null means
    -- the driver has not answered, which is not the same as "no rain".
    rain_possible       INTEGER,
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
-- What a lobby's time-of-day preset actually does at one circuit.
--
-- GT7's lobby offers names, not hours - "Late Morning", "Afternoon" - and what
-- hour each means differs by circuit and is documented nowhere reliable. It is
-- broadcast, though, so it is measured off the game clock the first time the
-- setting is run and kept here: the hour it starts at, the rate the clock runs
-- against real time, and the hour it stops.
--
-- That last one is the finding no table carries. A circuit without a 24-hour
-- cycle runs its clock to the end of its range and holds it there rather than
-- rolling into the next morning, so it is a hard ceiling on the conditions any
-- race there can reach - whatever the multiplier.
CREATE TABLE IF NOT EXISTS track_clock (
    circuit_key   TEXT NOT NULL,
    preset        TEXT NOT NULL,
    start_hour    REAL,
    multiplier    REAL,
    stops_at_hour REAL,
    laps_sampled  INTEGER NOT NULL DEFAULT 0,
    updated_at    TEXT    NOT NULL,
    PRIMARY KEY (circuit_key, preset)
);

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
        ("start_hour", "REAL"),
        ("time_multiplier", "REAL"),
        ("weather_rule", "TEXT"),
        ("rain_possible", "INTEGER"),
        ("start_type", "TEXT"),
        ("time_of_day", "TEXT"),
        ("priority", "TEXT"),
        ("pp_cap", "REAL"),
    ),
    "laps": (
        ("gear_ratios", "TEXT"),
        ("tyres_fresh", "INTEGER"),
        # Observed at the stop, not declared by the driver. `tyres_fresh` is
        # his word and outranks this; these two are kept apart so a
        # disagreement between them stays visible instead of one overwriting
        # the other. Null where the lap carried no stop: the question was
        # never asked, so it has no answer.
        ("tyres_changed", "INTEGER"),
        ("fuel_added_l", "REAL"),
        # GT7's own clock at the lap's first and last frame. On the lap rather
        # than inside the frame blob because reading the clock needs every lap
        # of a session and none of the other channels; see `LapFrames` for the
        # cached reading this being unreachable produced.
        ("tod_start_ms", "INTEGER"),
        ("tod_end_ms", "INTEGER"),
        ("standing_start_ms", "INTEGER"),
        # What the frames of this lap showed, taken once at capture: the
        # longest unbroken spell below walking pace, off the road, and
        # rotating. Three numbers instead of a 400 KB decode, so the lap rack
        # can say which laps had something happen in them without reading a
        # single blob. Null on a lap whose frames were never captured, which
        # is not the same as a lap where nothing happened.
        ("crawl_s", "REAL"),
        ("off_track_s", "REAL"),
        ("spin_s", "REAL"),
    ),
    "sessions": (
        # **Which kind of practice this was**, because it decides whether the
        # session's opening lap is an out-lap. Out of the box in a lobby it
        # always is. In a time trial the car starts on the track ahead of the
        # start/finish line, so the first lap is timed from the line like any
        # other - and striking it would throw away the session's best lap,
        # which it is in six of the eight time trials on record.
        #
        # Declared by the driver, never guessed from the game. Null on every
        # session recorded before the question was asked.
        ("practice_mode", "TEXT"),
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


def _migrate_v4_lap_clock(conn: sqlite3.Connection) -> None:
    """Lift GT7's clock out of the stored frames and onto the lap.

    Two things are repaired here, and the second is the reason for the first.

    **The clock could only be read from laps something else had decoded.**
    `strategy/evidence._laps_to_hydrate` decodes the last six counted laps per
    compound, which is the right window for a tyre-temperature question and
    the wrong one for a clock. At Monza those six laps were the ones after the
    14 Aug pit stop, where GT7's clock had already run to the end of the
    circuit's range and stopped. The reader saw six laps that did not move,
    concluded the lobby holds a fixed time of day, and cached it.

    **So the cached readings go.** A `track_clock` row is a measurement, and
    these were taken through a keyhole. They are deleted rather than
    recalculated in place: the next time evidence is built for the circuit it
    is measured again, from every lap, and a row that is absent says "not
    measured yet" while a row that is wrong says nothing at all.

    The back-fill decodes each stored lap once. That is the cost of not having
    recorded the two numbers at the time, and it is paid once.
    """
    columns = _columns(conn, "laps")
    if "tod_start_ms" not in columns:
        return                              # ADDED_COLUMNS has not run yet

    pending = conn.execute(
        "SELECT l.id FROM laps l JOIN lap_frames f ON f.lap_id = l.id "
        "WHERE l.tod_start_ms IS NULL").fetchall()
    if pending:
        # Imported here rather than at module scope: `store.schema` is the
        # bottom of the dependency stack and telemetry sits above it.
        from pitcrew.telemetry.recorder import decode_frames

        for (lap_id,) in pending:
            row = conn.execute(
                "SELECT blob FROM lap_frames WHERE lap_id = ?", (lap_id,)).fetchone()
            if row is None:
                continue
            try:
                frames = decode_frames(row[0])
            except Exception:               # noqa: BLE001 - a bad blob is not fatal
                continue
            stamps = [f["time_of_day_ms"] for f in frames
                      if f.get("time_of_day_ms") is not None]
            if not stamps:
                continue
            conn.execute(
                "UPDATE laps SET tod_start_ms = ?, tod_end_ms = ? WHERE id = ?",
                (stamps[0], stamps[-1], lap_id))

    conn.execute("DELETE FROM track_clock")


def _migrate_v5_incident_evidence(conn: sqlite3.Connection) -> None:
    """Read the off-and-spin evidence out of every stored lap, once.

    Same reasoning as v4: a question the lap rack asks on every redraw cannot
    be answered by decompressing a 400 KB buffer per row. Three numbers per
    lap, taken once here for laps recorded before the columns existed.

    A lap whose frames are absent, or whose blob will not decode, is left null
    rather than zeroed. Null means the lap was never measured; zero would mean
    it was measured and nothing happened, and an incident detector that reads
    the first as the second silently clears every lap it cannot see.
    """
    columns = _columns(conn, "laps")
    if "crawl_s" not in columns:
        return

    pending = conn.execute(
        "SELECT l.id, f.sample_hz FROM laps l JOIN lap_frames f ON f.lap_id = l.id "
        "WHERE l.crawl_s IS NULL").fetchall()
    if not pending:
        return

    from pitcrew.analysis.incidents import read_evidence
    from pitcrew.telemetry.recorder import decode_frames

    for lap_id, sample_hz in pending:
        row = conn.execute(
            "SELECT blob FROM lap_frames WHERE lap_id = ?", (lap_id,)).fetchone()
        if row is None:
            continue
        try:
            frames = decode_frames(row[0])
        except Exception:               # noqa: BLE001 - a bad blob is not fatal
            continue
        seen = read_evidence(frames, sample_hz or 60.0)
        conn.execute(
            "UPDATE laps SET crawl_s = ?, off_track_s = ?, spin_s = ? WHERE id = ?",
            (seen.crawl_s, seen.off_track_s, seen.spin_s, lap_id))


MIGRATIONS: dict[int, tuple[str, object]] = {
    3: ("per-corner tyre wear", _migrate_v3_wear_per_corner),
    4: ("the game clock onto the lap, and the readings taken through a keyhole",
        _migrate_v4_lap_clock),
    5: ("the off-and-spin evidence onto the lap", _migrate_v5_incident_evidence),
}
