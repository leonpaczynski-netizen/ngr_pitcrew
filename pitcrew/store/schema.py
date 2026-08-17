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
* **v6** adds `grip_observations` and `tyre_models`: the app's own longitudinal
  tyre model, derived offline from frames already on disk.  **Two new tables and
  nothing else** — `laps` is not touched, and it must never be, because
  `lap_frames` cascades off it and rebuilding it would destroy every recorded
  blob in the file.  There is deliberately **no migration function for v6**: two
  brand-new tables are exactly what `CREATE TABLE IF NOT EXISTS` in the DDL
  below already expresses, and a no-op entry in `MIGRATIONS` would only suggest
  otherwise.  The version number moves so that the guard in
  `Store._init_schema` still refuses to open a file this build predates.
* **v7** adds `tracks`, `track_layouts`, `cars` and `identity_repairs`: one
  canonical row per car and per circuit, with an integer key.  The tables are
  new, so `CREATE TABLE IF NOT EXISTS` covers them and the four columns on
  `events` and `sessions` are pure `ADDED_COLUMNS` — but the **seed and the
  back-fill** are work neither can express, so `_migrate_v7_canonical_identity`
  exists.  `laps` is not read, written, altered or rebuilt: it has no identity
  column, and `lap_frames` cascades off it.
* **v8** moves `purpose` inside `setup_sheets`' uniqueness key.  A race sheet
  and a qualifying sheet of the same name were one row, because the upsert's
  conflict target did not include the column that tells them apart — so
  loading the second overwrote the first and relabelled it.  This is the only
  migration here that rebuilds a table; see its docstring for why that is safe
  for `setup_sheets` and would not be for `laps`.

`CREATE ... IF NOT EXISTS` plus `ADDED_COLUMNS` covers anything additive, and
that carried v1 -> v2.  **v3 is the first change it cannot express** — it drops
two columns and back-fills four — so `MIGRATIONS` below exists, and anything
that changes or removes an existing column belongs there from now on rather
than in one more `IF NOT EXISTS`.
"""
from __future__ import annotations

import datetime
import sqlite3

SCHEMA_VERSION = 8

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
    -- **`race` or `qualifying`, and it is part of the key.**
    --
    -- It was outside it, and that lost sheets. The prompts ask the tune
    -- builder for both sheets in one reply and `parse_reply` returns both, so
    -- one paste routinely carries two - and with `UNIQUE(car_name,
    -- sheet_name)` the second upserted over the first and flipped its
    -- purpose. Load a race sheet then a qualifying sheet of the same name and
    -- only the qualifying one exists; the race sheet is gone, not shadowed.
    --
    -- NOT NULL with a default rather than nullable, and that is the whole
    -- reason the rebuild was worth it: **sqlite counts two NULLs as distinct
    -- in a UNIQUE constraint**, so a nullable column in the key would let an
    -- untagged sheet accumulate a new row on every save while the upsert
    -- silently stopped matching. 'race' is the right default because it is
    -- already the convention `sheet_for` documents - a sheet stored before
    -- the question was asked is a race sheet.
    purpose      TEXT    NOT NULL DEFAULT 'race',
    values_json  TEXT    NOT NULL DEFAULT '{}',
    gears_json   TEXT,                      -- JSON array, 1st..nth
    performance_json TEXT,                  -- restrictor, ECU, ballast
    build_json   TEXT,                      -- bhp, weight, PP
    notes        TEXT,
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL,
    UNIQUE(car_name, sheet_name, purpose)
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
-- The reply is stored whole, verbatim, and that is deliberate: what is kept
-- here is the record of what came back, which has to stay findable and
-- unedited.  It *is* also read - `setup/parse.py` lifts the sheets out of it
-- and loads them onto the Event screen - but that is a separate act on the
-- same text, not a reason to store anything less than all of it.
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

-- ------------------------------------------------------------------ the tyre model
--
-- GT7 broadcasts no tyre wear channel, in any packet format. The app's answer
-- is to measure the *effect* instead: `grip_g` is a percentile of the combined
-- acceleration vector over a lap, which is a friction envelope the driver
-- actually reached. It is **derived, never measured** - `grip_stat` names the
-- derivation on every single row so no reader can forget that.
--
-- Why this observable and not lap time: measured over 95 clean laps, lap time's
-- elasticity to grip is 0.07-0.30 where a friction-envelope percentile's is 1.0
-- by construction, at a comparable lap-to-lap CV. Resolving a 1% grip change
-- needs 16-74 laps here against 478-4204 on the stopwatch. Lap time is not
-- noisy, it is deaf.
--
-- One row per (lap, unit). `unit_kind='LAP'` carries `unit_id='LAP'`;
-- `unit_kind='CORNER'` carries the corner model's stable id, 'T7'.
CREATE TABLE IF NOT EXISTS grip_observations (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    lap_id                INTEGER NOT NULL REFERENCES laps(id) ON DELETE CASCADE,
    unit_kind             TEXT    NOT NULL,        -- 'LAP' | 'CORNER'
    unit_id               TEXT    NOT NULL,

    -- WHAT MAKES A ROW REPRODUCIBLE. Bump `derivation_version` and rebuild
    -- wholesale; never patch a row in place, or a fitted model stops resolving
    -- the observations it was actually fitted on.
    derivation_version    INTEGER NOT NULL,
    frame_schema_version  INTEGER NOT NULL,        -- 1 or 2, read off the blob
    -- **Mandatory, and the reason is a measurement.** v1 blobs stored the roll
    -- rate where the yaw rate belonged; `repair_frames` reconstructs ground-
    -- track yaw from the stored path, and that stencil attenuates the peak of
    -- the acceleration distribution by 3-4% against a v2 lap that carries the
    -- packet's own `angvel_y`. Measured on identical setup sheets: Yas +2.5 to
    -- +4.3%, Monza +3.7%. **That offset is the same size as the compound step
    -- this table exists to detect**, so a fit that pooled across it would read
    -- a storage-format change as a physics finding.
    yaw_source            TEXT    NOT NULL,        -- 'packet-angvel-y' | 'path-reconstructed'
    corner_model_version  INTEGER,                 -- NULL on a LAP row
    sample_frames         INTEGER NOT NULL,        -- frames behind this row (rule 4)

    -- SCOPE. Denormalised onto the row because these are the keys a fit may
    -- never pool across, and a join is one more place to forget one.
    car_key               TEXT    NOT NULL,
    circuit_key           TEXT    NOT NULL,
    compound              TEXT,                    -- NULL where he never tagged it
    session_id            INTEGER NOT NULL,
    lap_num               INTEGER NOT NULL,
    -- `session_id:ordinal`, the ordinal rising at each observed tyre change.
    -- NULL where the set's identity is genuinely unknown, which is most of the
    -- archive: GT7 broadcasts no tyre-change event.
    stint_key             TEXT,
    lap_in_stint          INTEGER,

    -- THE OBSERVABLE. Derived. `grip_stat` says which derivation.
    grip_g                REAL,                    -- comb_p95 (LAP) | comb_p90 (CORNER)
    grip_stat             TEXT    NOT NULL,
    lat_p95_g             REAL,
    decel_p90_g           REAL,
    min_speed_kph         REAL,
    lap_time_ms           INTEGER,

    -- THE COVARIATES, each NULL when unmeasured. Never 0.
    --
    -- Both temperature aggregates are stored, and that is deliberate: the one
    -- external wear-onset figure in existence (RS 88 / RM 90 / RH 93 degC) never
    -- states whether it means an axle mean or the hottest moment, and the answer
    -- decides everything - on lap-axle means this driver reaches 88 degC on 1 of
    -- 76 laps, on corner windows on 18 of 719 observations. **A threshold whose
    -- aggregate is unstated is not a threshold**, so both are on the row and any
    -- claim has to name one.
    temp_front_c          REAL,   temp_rear_c          REAL,
    temp_front_max_c      REAL,   temp_rear_max_c      REAL,
    entry_temp_front_c    REAL,   entry_temp_rear_c    REAL,   -- CORNER only
    fuel_l                REAL,
    laps_on_set           INTEGER,                 -- NULL when the set's age is unknown
    -- The driver's own gauge reading on this lap, worst corner, fraction
    -- consumed. **The only wear number anchored to the game's own figure, and
    -- the only bridge to a wear dependent variable that exists** - there is no
    -- wear channel, so without this the model can measure grip falling and can
    -- never say what fraction of the tyre that is. NULL on the 160 of 175
    -- archived laps where he did not read it.
    gauge_worst_frac      REAL,
    -- GT7's in-game clock. **A STRATIFIER, NEVER A TEMPERATURE.** There is no
    -- ambient or track temperature channel in any packet format - the full
    -- 368-byte struct is accounted for and there is no unclaimed float where one
    -- could hide. The clock says when an observation was taken and nothing more.
    tod_ms                INTEGER,
    -- 1 where the clock stopped advancing while the car kept driving. A circuit
    -- runs its day to the end of its range and holds it there; reading that as a
    -- multiplier of zero is how a poisoned `track_clock` row got cached once.
    clock_frozen          INTEGER,
    session_elapsed_s     REAL,
    commit_brake_pct      REAL,   commit_full_thr_frac REAL,
    kerb_frac             REAL,                    -- NULL on packet formats 'A'/'B'

    -- CORNER IDENTITY, anchored on the apex he actually drove rather than the
    -- one auto-segmentation guessed. The anchor is stored per row so a row can
    -- always be explained by the window that produced it.
    apex_m_model          REAL,
    apex_m_observed       REAL,
    apex_anchor_laps      INTEGER,
    apex_anchor_sd_m      REAL,
    identity_stable       INTEGER,

    -- ELIGIBILITY, and the reason, so an exclusion can be explained rather than
    -- guessed at. A lap that does not count is still written: a fuel-save lap is
    -- a measurement of something, just not of grip.
    counts_toward_fit     INTEGER NOT NULL DEFAULT 0,
    exclusion_reason      TEXT,

    derived_at            TEXT    NOT NULL,
    UNIQUE(lap_id, unit_kind, unit_id, derivation_version)
);
CREATE INDEX IF NOT EXISTS idx_grip_obs_lap ON grip_observations(lap_id);
CREATE INDEX IF NOT EXISTS idx_grip_obs_fit
    ON grip_observations(counts_toward_fit, unit_kind);
CREATE INDEX IF NOT EXISTS idx_grip_obs_scope
    ON grip_observations(car_key, circuit_key, compound, yaw_source);

-- ONE ROW PER FITTED MODEL. The scope keys are what may never be pooled: a
-- coefficient fitted at one car and circuit is a local measurement, and this
-- table's shape is what stops it being promoted to a law by accident.
CREATE TABLE IF NOT EXISTS tyre_models (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    car_key            TEXT    NOT NULL,
    circuit_key        TEXT    NOT NULL,   -- matches corner_models.circuit_key
    compound           TEXT,               -- NULL = a compound-agnostic fit
    yaw_source         TEXT    NOT NULL,   -- a fit spans exactly ONE source
    model_kind         TEXT    NOT NULL,   -- 'baseline' | 'degradation'
                                           -- | 'warmup' | 'temperature-response'
    model_json         TEXT    NOT NULL,   -- coefficients and their standard errors
    -- Rule 4 as columns rather than as a habit.
    samples            INTEGER NOT NULL,
    sessions           INTEGER NOT NULL,
    stints             INTEGER NOT NULL,
    confidence         TEXT    NOT NULL,   -- 'none' | 'low' | 'medium' | 'high'
    -- **Written here, at fit time, by the code that checked the sample counts.**
    -- The voice layer reads a boolean; it does not get to decide.
    speakable          INTEGER NOT NULL DEFAULT 0,
    gate_json          TEXT    NOT NULL,   -- which staged gate, its thresholds, what failed
    unknowns_json      TEXT    NOT NULL,   -- what this model explicitly cannot say
    provenance_json    TEXT    NOT NULL,   -- derivation_version, lap ids, multipliers
    game_version       TEXT,
    derivation_version INTEGER NOT NULL,
    fitted_at          TEXT    NOT NULL,
    UNIQUE(car_key, circuit_key, compound, yaw_source, model_kind, derivation_version)
);
CREATE INDEX IF NOT EXISTS idx_tyre_models_scope
    ON tyre_models(car_key, circuit_key, model_kind);

-- --------------------------------------------------- canonical identity (v7)
--
-- Before these three tables, nothing in the app had a stable identifier for a
-- car or a circuit. Every identity was a display string or a slug composed
-- from one, by one of four incompatible rules, and three bugs of that family
-- landed inside a single day: a Gr.3-tagged session feeding an approved road-
-- car race plan its fuel figure, a tyre call that never fired because its
-- scope named a circuit the events table does not contain, and one car slugged
-- two ways because `str.isalnum()` keeps an accent.
--
-- The rule these tables enforce: **the slug is a COLUMN, written once, and
-- every later use reads it.** Nothing recomposes a key. That is what makes the
-- family of bug structurally impossible rather than merely fixed.

CREATE TABLE IF NOT EXISTS tracks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL UNIQUE,   -- 'Autodromo Nazionale Monza'
    kind       TEXT,                      -- 'Real' | 'Original' | 'City' | ...
    slug       TEXT    NOT NULL UNIQUE,
    -- A track constant, not a car variable (CLAUDE.md 5.4). It lives here
    -- rather than on the layout because it is measured once per circuit; it
    -- is nullable because unmeasured is null and never a default 20 s.
    pit_loss_secs REAL,
    created_at TEXT    NOT NULL
);

-- **The layout is the circuit identity, and it is its own row.**
--
-- Not a suffix concatenated onto a track key, for three reasons in order of
-- weight. A corner model belongs to a layout: Monza Full Course and Monza No
-- Chicane share nothing at the corner level. A NULL layout was representable
-- in the old shape and event 1 carried one for weeks, with 763 grip
-- observations and a corner model keyed off its absence - making the layout a
-- mandatory column of its own row makes "Monza, layout unstated"
-- unrepresentable rather than merely discouraged. And a reversed
-- configuration shares its track's name and length while needing its own
-- corner sequence.
CREATE TABLE IF NOT EXISTS track_layouts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id   INTEGER NOT NULL REFERENCES tracks(id),
    layout     TEXT    NOT NULL,          -- 'Full Course'; never null
    reverse    INTEGER NOT NULL DEFAULT 0,
    length_m   REAL,                      -- catalogue figure, for the +/-50 m check
    -- Null means the catalogue does not say, which is not the same claim as
    -- "it cannot rain here".
    rain       INTEGER,
    -- `slugify(track + ' ' + layout)`. **This spelling is load-bearing**: it
    -- is exactly what `corner_models.circuit_key`, `track_clock.circuit_key`
    -- and 1,459 `grip_observations` rows already hold on disk, so stage 3
    -- resolves them against this column by plain equality.
    slug       TEXT    NOT NULL UNIQUE,
    -- 'canonical' is selectable. 'quarantined' exists, holds its data, and is
    -- offered to nobody.
    status     TEXT    NOT NULL DEFAULT 'canonical',
    created_at TEXT    NOT NULL,
    UNIQUE(track_id, layout)
);
CREATE INDEX IF NOT EXISTS idx_layouts_track ON track_layouts(track_id);

-- **The natural key is `gt7_car_id`; the primary key is the surrogate `id`.**
--
-- Deliberate, and it resolves most of the tension in this design by itself.
-- The 608 catalogue cars are known by name and none of them has a verified
-- packet id, so they seed with `gt7_car_id = NULL` and are all immediately
-- selectable. The id is filled in the first time the car is driven -
-- **learned from the stream, never imported.** `data/car_id_map.json` looks
-- like the game's id space and is not: the Shelby streams 3391, that file
-- says 473, and its whole range stops at 712. Because every foreign key
-- points at the surrogate, learning or correcting a `gt7_car_id` later
-- rewrites nothing.
CREATE TABLE IF NOT EXISTS cars (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    gt7_car_id  INTEGER UNIQUE,           -- the PACKET's id. NULL until observed.
    name        TEXT    NOT NULL UNIQUE,  -- GT7's own spelling
    category    TEXT,                     -- 'Gr.3' | 'Road Car' | ...
    maker       TEXT,
    year        TEXT,
    drivetrain  TEXT,
    pp_rating   REAL,
    slug        TEXT    NOT NULL UNIQUE,
    -- 'observed-on-stream' or NULL. There is no 'catalogue' source and there
    -- must never be one: the only file that carries ids carries wrong ones.
    gt7_id_source       TEXT,
    -- Which GT7 version the id was seen under. Packet id stability across a
    -- version bump is **unproven** - one car, one version (1.70) - so a
    -- renumbering has to show up as a flagged session rather than silently.
    gt7_id_game_version TEXT,
    status      TEXT    NOT NULL DEFAULT 'canonical',
    created_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cars_status ON cars(status);

-- Every identity assignment the app derived rather than was told, and every
-- repair the driver later made. This is what makes v7 reversible in the sense
-- that matters: no column is dropped, renamed or retyped anywhere in it, so
-- the schema rolls back by being ignored - and every value it *derived* can be
-- read back off this table row by row.
CREATE TABLE IF NOT EXISTS identity_repairs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name  TEXT NOT NULL,
    row_id      TEXT NOT NULL,
    field       TEXT NOT NULL,
    old_value   TEXT,
    new_value   TEXT,
    reason      TEXT NOT NULL,
    -- 'migration-v7' | 'observed-on-stream' | 'driver'. Never blank: an
    -- assignment with no author cannot be audited.
    resolved_by TEXT NOT NULL,
    resolved_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_identity_repairs_row
    ON identity_repairs(table_name, row_id);
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
        # Whether `start_hour` and `time_multiplier` were typed or measured
        # off the game clock. Without it a figure the app wrote back is
        # indistinguishable from one he entered, and the app would overwrite
        # his own declaration the next time it went out.
        ("clock_source", "TEXT"),
        # `refuel_rate_lps` and `pit_loss_secs` are declared NOT NULL with the
        # app's own defaults, so the column cannot say "he never entered one" -
        # 2.5 L/s and 20 s look exactly like figures he typed, and the export
        # was labelling the pit loss `measured-this-track` on that basis.  These
        # two carry the provenance instead: NULL means untouched, and no reader
        # may treat the value as declared without one.  Making the value columns
        # nullable would mean rebuilding `events`, and four tables cascade off
        # it, so the fact lives beside the number rather than in it.
        ("refuel_rate_source", "TEXT"),
        ("pit_loss_source", "TEXT"),
        # **The hub, at last with keys.** `events.id` was already what
        # `sessions`, `strategies`, `race_runs` and `prompt_issues` hang off;
        # what it lacked was any link of its own to a canonical car or
        # circuit. `car_name` and `track`/`layout` stay beside these and are
        # written from the canonical row on every future write - they become
        # derived display columns rather than the identity. Dropping them
        # would mean rebuilding `events`, and four tables cascade off it.
        #
        # `car_id` (already present, NULL on every row, written by nothing)
        # is NOT this. It is a dead column from an older shape; `car_ref`
        # points at `cars.id`, which is a surrogate, not the packet's id.
        ("car_ref", "INTEGER"),
        ("layout_id", "INTEGER"),
        # 'ok' | 'quarantined'. Quarantined means the event could not be
        # resolved to canonical rows - a car or a layout the catalogue does
        # not carry. The event keeps every one of its sessions and laps.
        ("identity_status", "TEXT"),
        # **The fastest frame this event has ever recorded**, which is the
        # speed the wind fans should reach full at. `car_max_speed_raw` is the
        # CAR's top speed and the circuit is always slower: the Huracan
        # broadcasts 299 and the quickest frame of the whole Watkins race was
        # 273.5, so the top 6% of fan range was unreachable by construction.
        # An event is one car at one circuit, so the pair's measured maximum
        # belongs here. NULL until a lap has been recorded, and then the wind
        # curve falls back to the car's figure and says which it used.
        ("observed_top_kph", "REAL"),
        # **Which wheels are driven.** GT7 broadcasts no drivetrain channel in
        # any packet format and the torque-vector channels that might have
        # inferred it read zero on this stream, so it is declared or it is
        # unknown. Without it `wheelspin` watches all four wheels: at Watkins
        # T2 that was 15 laps of 17 flagged with a kerb strike on all 17, and
        # what it was seeing was a front wheel lifted over the kerb.
        ("drivetrain", "TEXT"),
        # The fuel map the car ran, 1-6, 1 richest. No channel carries it and
        # the whole fuel model is expressed per map, so `laps.fuel_map` was
        # null on every lap ever recorded. Declared on the event because it is
        # a property of how the round is being driven.
        ("fuel_map", "INTEGER"),
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
        # **How far the shift beep was dropped while this lap was driven, in
        # rpm.** Null where it was never recorded, 0.0 where the lap was
        # driven on the normal threshold, positive where he was short-
        # shifting - and the three are genuinely different claims, which is
        # why this is not a boolean.
        #
        # It exists because a lap driven under the app's own fuel-saving
        # instruction is not evidence about the car. A short-shift costs
        # around half a second, the same size as the pace deficit the stint
        # calls hunt for, so a pace series that cannot see this measures the
        # app's own radio calls and then boxes him for them.
        ("short_shift_rpm", "REAL"),
    ),
    "setup_sheets": (
        # `race` or `qualifying`. Two sheets for one car are two different
        # objects, not two versions of one - they answer different
        # questions and the tune builder issues them separately. Null on
        # every sheet stored before the question was asked, which reads as
        # "not stated" rather than as a race sheet.
        ("purpose", "TEXT"),
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
        # **What this session was for**, which is a different question
        # from where the car started. The two are orthogonal - a
        # qualifying simulation is usually a time trial and race running
        # is usually a lobby, but neither is implied by the other.
        #
        # It decides what the numbers mean rather than which laps count.
        # A qualifying session is one lap on low fuel and fresh rubber:
        # degradation across it is noise. A race session is the opposite -
        # the single fastest lap is the noise and the shape of the stint
        # is the measurement. Reporting both the same way is how a
        # one-lap car gets built for a race.
        ("practice_intent", "TEXT"),
        # A full race run against the AI to rehearse the plan. It is a
        # race session in every mechanical sense - it makes real stops
        # under race conditions, which is the only place that evidence
        # comes from - but it is not the league race, and an outcome
        # post-mortem must not read it as one.
        ("rehearsal", "INTEGER"),
        # **What the wire said the car was.** `packet.car_id` is in the base
        # 296-byte struct, so it arrives in every packet format A/B/~/C - it
        # costs nothing to record and it is the only automatically-verifiable
        # identity in the system. Null on every archived session because
        # nothing wrote it; 0 is never stored, because 0 is GT7's "the car has
        # not loaded" sentinel and not a car.
        ("car_id_observed", "INTEGER"),
        # **The wheelbase the packet broadcasts, and it was never stored.**
        # `understeer-mid` divides expected yaw by it, and with nothing on
        # file it used `thresholds.DEFAULT_WHEELBASE_M` - which is 2.516 m,
        # the Porsche RSR's, measured off a real packet and then applied to
        # every car. The Huracan is about 2.62, so expected yaw ran ~4% high
        # and the bias pointed at reporting understeer, on a flag the driver
        # had contradicted across four sessions. Extended packets carry it at
        # offset 360; it is a per-car constant, so it belongs on the session
        # rather than in every frame of the blob.
        ("wheelbase_m", "REAL"),
        # The `cars.id` that observation resolved to. Null where it resolved
        # to nothing, which is a real state and not a failure.
        ("car_ref_observed", "INTEGER"),
        # 'ok' | 'car-mismatch' | 'car-unknown' | 'no-reading'.
        #
        # **This is the column that closes bug 1.** Session 11 streamed GR3 on
        # a Road Car event and its lap 4 burn became the approved plan's
        # `fuelPerLapL` of 7.563, because `list_evidence_laps` scoped on the
        # event alone and no code anywhere compared a session's car to its
        # event's. Nothing is deleted: the session, its 7 laps and its frames
        # all stay, and it is excluded from evidence rather than lost.
        ("identity_status", "TEXT"),
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


def _repair(conn: sqlite3.Connection, now: str, table: str, row_id,
            field: str, old, new, reason: str,
            by: str = "migration-v7") -> None:
    """Log one derived identity assignment, so it can be read back."""
    conn.execute(
        "INSERT INTO identity_repairs (table_name, row_id, field, old_value, "
        "new_value, reason, resolved_by, resolved_at) VALUES (?,?,?,?,?,?,?,?)",
        (table, str(row_id), field,
         None if old is None else str(old),
         None if new is None else str(new), reason, by, now))


def _migrate_v7_canonical_identity(conn: sqlite3.Connection) -> None:
    """Seed the canonical car and circuit tables, and key the archive to them.

    **Nothing is dropped, guessed or discarded.** Every existing row is
    mapped, and anything that does not map is flagged where it stands rather
    than deleted - the project's own precedent is quarantine, never delete.

    Three back-fills, in order:

    1. **Seed.** 41 tracks, 121 layout rows (84 catalogue layouts plus 37
       reverse configurations) and 608 cars, every car with `gt7_car_id NULL`
       because no verified packet id exists for any of them yet.
    2. **Events.** Resolve `car_name` against `cars.name` and `(track, layout)`
       against `track_layouts`, both by exact string equality - the catalogue
       is where those strings came from. An event that resolves neither half
       is `identity_status = 'quarantined'` and keeps everything it has.
    3. **Sessions.** Here the migration is working with one hand tied:
       **`car_id` was never recorded on any archived session**, so the only
       evidence of what car actually ran is `car_category`, the class token
       off the stream. A class is shared by dozens of cars, so this can catch
       a road car tagged Gr.3 and cannot tell two Gr.3 cars apart. That is a
       real limit and it is why the fix going forward is the id, not the
       class. A flagged session **cannot be identified retroactively** and is
       not guessed at: it is quarantined, and stays quarantined until the
       driver says what it was.

    **The mismatch class had TWO instances at migration time, not one.**
    Session 11 is the expensive one - `GR3` on event 2's road car, 7 laps, and
    its lap 4 is the approved plan's fuel figure - and it is the one every
    write-up names. Session 5 is the other: `GRN` on event 1, whose Porsche
    911 RSR is Gr.3. It has zero laps, so it cost nothing and nobody noticed,
    which is exactly why it is written down here. **This is a class of defect
    with more than one member, not an incident with a name.** Nothing
    downstream may special-case session 11.

    `laps` is not read, written, altered or rebuilt anywhere in here.
    """
    from pitcrew.store.identity import (
        IDENTITY_MISMATCH,
        IDENTITY_NO_READING,
        IDENTITY_OK,
        IDENTITY_QUARANTINED,
        expected_stream_token,
        seed_catalogue,
    )

    if "car_ref" not in _columns(conn, "events"):
        return                          # ADDED_COLUMNS has not run yet

    now = datetime.datetime.now().isoformat(timespec="seconds")
    seed_catalogue(conn, now)

    # --- events -------------------------------------------------------------
    for event in conn.execute(
            "SELECT id, track, layout, car_name, car_ref, layout_id, "
            "identity_status FROM events").fetchall():
        event_id, track, layout, car_name = event[0], event[1], event[2], event[3]
        car_ref, layout_id, status = event[4], event[5], event[6]
        if car_ref is not None and layout_id is not None and status:
            continue                    # already keyed; the migration is idempotent

        if car_ref is None and car_name:
            row = conn.execute(
                "SELECT id FROM cars WHERE name = ?", (car_name,)).fetchone()
            if row is not None:
                car_ref = int(row[0])
                _repair(conn, now, "events", event_id, "car_ref", None, car_ref,
                        f"exact name match on {car_name!r}")

        if layout_id is None and track and layout:
            row = conn.execute(
                "SELECT tl.id FROM track_layouts tl JOIN tracks t "
                "ON t.id = tl.track_id WHERE t.name = ? AND tl.layout = ?",
                (track, layout)).fetchone()
            if row is not None:
                layout_id = int(row[0])
                _repair(conn, now, "events", event_id, "layout_id", None,
                        layout_id, f"exact match on {track!r} / {layout!r}")

        # **A layout the event never stated is not resolved here.** Which of
        # Monza's two layouts a run was on is a fact about the world, and
        # `CLAUDE.md` 4.1 says a disagreement between sources is the finding.
        # It goes to the driver, quarantined, with its data intact.
        resolved = car_ref is not None and layout_id is not None
        conn.execute(
            "UPDATE events SET car_ref = ?, layout_id = ?, identity_status = ? "
            "WHERE id = ?",
            (car_ref, layout_id,
             IDENTITY_OK if resolved else IDENTITY_QUARANTINED, event_id))
        if not resolved:
            _repair(conn, now, "events", event_id, "identity_status", status,
                    IDENTITY_QUARANTINED,
                    "no canonical car" if car_ref is None else "no canonical layout")

    # --- sessions -----------------------------------------------------------
    for session in conn.execute(
            "SELECT s.id, s.car_category, s.identity_status, c.category, c.name "
            "FROM sessions s LEFT JOIN events e ON e.id = s.event_id "
            "LEFT JOIN cars c ON c.id = e.car_ref "
            "WHERE s.identity_status IS NULL").fetchall():
        session_id, observed_token = session[0], session[1]
        declared_category, declared_name = session[3], session[4]
        expected = expected_stream_token(declared_category)

        if observed_token is None:
            # **`no-reading` is not `car-mismatch`, and conflating them would
            # accuse five sessions of something no evidence supports.** GT7
            # streamed no class here: either it never streamed at all
            # (sessions 4 and 21 have no packet format) or the packet landed
            # before the car loaded (13, 36 and 42 all read a 0 L tank too).
            status = IDENTITY_NO_READING
            reason = "GT7 reported no car class for this run"
        elif expected is None or observed_token.strip().upper() == expected:
            status, reason = IDENTITY_OK, ""
        else:
            status = IDENTITY_MISMATCH
            reason = (f"the stream reported class {observed_token}; "
                      f"{declared_name} is {declared_category}, which GT7 "
                      f"streams as {expected}")

        conn.execute("UPDATE sessions SET identity_status = ? WHERE id = ?",
                     (status, session_id))
        if status != IDENTITY_OK:
            _repair(conn, now, "sessions", session_id, "identity_status",
                    None, status, reason)


def _migrate_v8_sheet_purpose(conn: sqlite3.Connection) -> None:
    """Put `purpose` inside `setup_sheets`' uniqueness key.

    **The defect, in the driver's words:** "trying to load both a race setup
    and quali setup into app it only accepts the last setup you add even
    though you can select race or quali."

    Exactly that. `UNIQUE(car_name, sheet_name)` left `purpose` outside the
    key while `save_setup_sheet` upserted on that key and assigned
    `purpose=excluded.purpose`, so the qualifying sheet did not become a
    second row - it overwrote the race sheet and relabelled it. And all seven
    archived sheets carried `purpose IS NULL`, so even where two survived,
    `sheet_for`'s documented "an untagged sheet predates the question and is
    therefore a race sheet" rule made both of them race candidates.

    **This is the one migration in this file that rebuilds a table**, and it
    is worth stating why that is allowed here when the note at the top of the
    migrations section forbids it. That warning is about `laps`: `lap_frames`
    references it `ON DELETE CASCADE`, so dropping it destroys every recorded
    telemetry blob. `sessions.setup_sheet_id` references `setup_sheets` with
    **no ON DELETE clause at all**, so nothing cascades - and the ids are
    copied across verbatim, so every reference still resolves. A UNIQUE
    constraint cannot be altered in sqlite any other way: it is an implicit
    index that `DROP INDEX` will not touch.

    Foreign keys are off for the whole upgrade pass (see `_init_schema`) and
    `PRAGMA foreign_key_check` runs after it, so a reference that failed to
    survive would be loud rather than silent.
    """
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='setup_sheets'"
    ).fetchone()
    if row is None or "sheet_name, purpose" in (row[0] or ""):
        return                          # already v8, or built fresh from the DDL

    columns = _columns(conn, "setup_sheets")
    if "purpose" not in columns:        # ADDED_COLUMNS has not run yet
        return

    before = conn.execute("SELECT COUNT(*), COALESCE(MAX(id), 0) "
                          "FROM setup_sheets").fetchone()

    conn.execute("""
        CREATE TABLE setup_sheets_v8 (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            car_name     TEXT    NOT NULL,
            sheet_name   TEXT    NOT NULL,
            purpose      TEXT    NOT NULL DEFAULT 'race',
            values_json  TEXT    NOT NULL DEFAULT '{}',
            gears_json   TEXT,
            performance_json TEXT,
            build_json   TEXT,
            notes        TEXT,
            created_at   TEXT    NOT NULL,
            updated_at   TEXT    NOT NULL,
            UNIQUE(car_name, sheet_name, purpose)
        )""")
    # **`id` is copied, not regenerated.** Five sessions on file point at
    # sheets 1, 3, 5, 9 and 12; renumbering would silently re-point every one
    # of them at a different setup, which is precisely the "which sheet
    # produced these symptoms" ambiguity the sheet-as-run section exists to
    # remove.
    conn.execute("""
        INSERT INTO setup_sheets_v8
            (id, car_name, sheet_name, purpose, values_json, gears_json,
             performance_json, build_json, notes, created_at, updated_at)
        SELECT id, car_name, sheet_name, COALESCE(purpose, 'race'),
               values_json, gears_json, performance_json, build_json, notes,
               created_at, updated_at
          FROM setup_sheets""")

    after = conn.execute("SELECT COUNT(*), COALESCE(MAX(id), 0) "
                         "FROM setup_sheets_v8").fetchone()
    if tuple(before) != tuple(after):
        # Refuse rather than half-convert. A row or an id lost here is a
        # session pointing at a setup that is not the one it ran.
        raise RuntimeError(
            f"setup_sheets rebuild would lose data: {tuple(before)} -> "
            f"{tuple(after)}")

    # **The AUTOINCREMENT high-water mark is carried across too.** Dropping the
    # table takes its `sqlite_sequence` row with it, and re-inserting rows 1-12
    # would reset the mark to 12 - so the next sheet saved would be handed id
    # 13, which three deleted sheets already used. Ids that have been issued
    # once are not issued again; that is the whole reason the column is
    # AUTOINCREMENT rather than a plain rowid.
    sequence = conn.execute(
        "SELECT seq FROM sqlite_sequence WHERE name = 'setup_sheets'").fetchone()

    conn.execute("DROP TABLE setup_sheets")
    conn.execute("ALTER TABLE setup_sheets_v8 RENAME TO setup_sheets")

    if sequence is not None:
        conn.execute("UPDATE sqlite_sequence SET seq = ? WHERE name = ? "
                     "AND seq < ?",
                     (sequence[0], "setup_sheets", sequence[0]))


MIGRATIONS: dict[int, tuple[str, object]] = {
    3: ("per-corner tyre wear", _migrate_v3_wear_per_corner),
    4: ("the game clock onto the lap, and the readings taken through a keyhole",
        _migrate_v4_lap_clock),
    5: ("the off-and-spin evidence onto the lap", _migrate_v5_incident_evidence),
    7: ("canonical car and circuit identity", _migrate_v7_canonical_identity),
    8: ("a race sheet and a qualifying sheet are two sheets",
        _migrate_v8_sheet_purpose),
}
