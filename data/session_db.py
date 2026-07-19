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
    config_id       TEXT    NOT NULL DEFAULT '',
    setup_id        INTEGER NOT NULL DEFAULT 0,
    rating          TEXT    NOT NULL DEFAULT ''
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
    abs             INTEGER NOT NULL DEFAULT 1,
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

# Columns added in schema version 9 — OFR-1 scoring fields on setup_recommendations.
_V9_ALTER_COLUMNS: list[tuple[str, str]] = [
    ("setup_recommendations", "score_confidence REAL NOT NULL DEFAULT -1.0"),
    ("setup_recommendations", "score_verdict    TEXT NOT NULL DEFAULT ''"),
    ("setup_recommendations", "score_details    TEXT NOT NULL DEFAULT '{}'"),
]

# v10: attribute per-stint driver feedback to the setup that was running and
# carry the driver's subjective rating (moved out of the Setup Builder).
_V10_ALTER_COLUMNS: list[tuple[str, str]] = [
    ("driver_feedback", "setup_id INTEGER NOT NULL DEFAULT 0"),
    ("driver_feedback", "rating   TEXT    NOT NULL DEFAULT ''"),
]

# v11: Group 42 — Rule-First Setup Brain.
# Additive nullable columns on setup_recommendations for the new deterministic
# pipeline.  recommendation_text is preserved; these are foundation-only columns
# (no existing query breaks).  All new columns are nullable TEXT so old rows
# survive as NULL without constraint violations.
_V11_ALTER_COLUMNS: list[tuple[str, str]] = [
    ("setup_recommendations", "deterministic_plan_json  TEXT"),
    ("setup_recommendations", "ai_audit_json            TEXT"),
    ("setup_recommendations", "validation_status        TEXT"),
    ("setup_recommendations", "approved_changes_json    TEXT"),
    ("setup_recommendations", "rejected_changes_json    TEXT"),
    ("setup_recommendations", "diagnosis_json           TEXT"),
    ("setup_recommendations", "driver_profile_version   TEXT"),
    ("setup_recommendations", "rule_engine_version      TEXT"),
]

# v13: Group 47 — Outcome Verification & Learning Loop 2.
# Additive nullable-with-default TEXT columns on learning_outcomes so each row can
# carry the richer outcome-verification evidence (target issue, before/after
# evidence summary, optional driver feedback, safety notes, and the typed
# OutcomeVerdict).  All columns default to '' so existing v12 rows survive
# untouched and no back-fill is needed.  A "duplicate column" guard makes the
# migration idempotent on already-upgraded databases.
_V13_ALTER_COLUMNS: list[tuple[str, str]] = [
    ("learning_outcomes", "target_issue      TEXT NOT NULL DEFAULT ''"),
    ("learning_outcomes", "evidence_summary  TEXT NOT NULL DEFAULT ''"),
    ("learning_outcomes", "driver_feedback   TEXT NOT NULL DEFAULT ''"),
    ("learning_outcomes", "safety_notes      TEXT NOT NULL DEFAULT ''"),
    ("learning_outcomes", "outcome_kind      TEXT NOT NULL DEFAULT ''"),
]

# v14: Group 62 — ABS Regulation.
# Additive INTEGER column on events so each event can record whether ABS is
# allowed (1) or disabled (0).  DEFAULT 1 means all existing events keep ABS
# allowed — the safe, non-restrictive default.  Duplicate-column guard follows
# the V13 pattern.
_V14_ALTER_COLUMNS: list[tuple[str, str]] = [
    ("events", "abs INTEGER NOT NULL DEFAULT 1"),
]

# v16: Engineering-Brain Phase 7 — structured Practice Review capture.
# Additive TEXT columns on driver_feedback so a stint can record the DIRECTIONAL
# outcome vs the previous setup (better/worse/unchanged) and an optional corner+phase
# for per-corner diagnosis. Duplicate-column guard follows the v14 pattern.
_V16_ALTER_COLUMNS: list[tuple[str, str]] = [
    ("driver_feedback", "vs_previous TEXT NOT NULL DEFAULT ''"),
    ("driver_feedback", "corner      TEXT NOT NULL DEFAULT ''"),
    ("driver_feedback", "phase       TEXT NOT NULL DEFAULT ''"),
]

# v15: Engineering-Brain Phase 1 — closed-loop setup lineage.
# A dedicated, ADDITIVE table (touches no existing table) recording each applied
# setup as a node derived from a PARENT node by a set of field changes, with the
# measured outcome once scored. This gives a clean parent→child chain for rollback
# and per-change attribution. CREATE IF NOT EXISTS makes the migration idempotent.
_DDL_V15 = """
CREATE TABLE IF NOT EXISTS setup_lineage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    car_id INTEGER NOT NULL,
    track TEXT NOT NULL DEFAULT '',
    layout_id TEXT NOT NULL DEFAULT '',
    objective TEXT NOT NULL DEFAULT '',
    parent_id INTEGER,                       -- prior setup_lineage.id this was derived from
    rec_id INTEGER,                          -- setup_recommendations.id that produced it
    session_id INTEGER,                      -- the session it was applied for
    changes_json TEXT NOT NULL DEFAULT '[]', -- [{field, from, to}] applied vs the parent
    label TEXT NOT NULL DEFAULT '',
    outcome_verdict TEXT NOT NULL DEFAULT '', -- improved/worsened/neutral/'' (unscored)
    outcome_session_id INTEGER
);
CREATE INDEX IF NOT EXISTS idx_setup_lineage_scope
    ON setup_lineage (car_id, track, layout_id);
"""

# Engineering-Brain (live telemetry): cross-session per-corner slip accumulation.
# One row per (car, track, layout, segment, run). UPSERT on the unique key so a run's
# totals are replaced (never duplicated) when re-saved mid-session; reads SUM across
# runs to accumulate the driver's slip history at each corner across sessions.
_DDL_V17 = """
CREATE TABLE IF NOT EXISTS corner_slip_telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    car_id INTEGER NOT NULL,
    track TEXT NOT NULL DEFAULT '',
    layout_id TEXT NOT NULL DEFAULT '',
    segment_id TEXT NOT NULL DEFAULT '',
    run_id INTEGER NOT NULL DEFAULT 0,
    turn INTEGER,
    display_name TEXT NOT NULL DEFAULT '',
    direction TEXT NOT NULL DEFAULT '',
    samples INTEGER NOT NULL DEFAULT 0,
    wheelspin_events INTEGER NOT NULL DEFAULT 0,
    lockup_events INTEGER NOT NULL DEFAULT 0,
    wheelspin_by_phase TEXT NOT NULL DEFAULT '{}',
    lockup_by_phase TEXT NOT NULL DEFAULT '{}',
    spin_axle_counts TEXT NOT NULL DEFAULT '{}',
    lock_axle_counts TEXT NOT NULL DEFAULT '{}',
    throttle_sum REAL NOT NULL DEFAULT 0.0,
    brake_sum REAL NOT NULL DEFAULT 0.0,
    exit_gear INTEGER,
    exit_rpm_avg REAL,
    updated_at TEXT NOT NULL DEFAULT '',
    UNIQUE (car_id, track, layout_id, segment_id, run_id)
);
CREATE INDEX IF NOT EXISTS idx_corner_slip_scope
    ON corner_slip_telemetry (car_id, track, layout_id);
"""

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

_DDL_V18 = """
CREATE TABLE IF NOT EXISTS corner_issue_occurrences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    car_id INTEGER NOT NULL,
    track TEXT NOT NULL DEFAULT '',
    layout_id TEXT NOT NULL DEFAULT '',
    session_id INTEGER NOT NULL DEFAULT 0,
    setup_checkpoint_id TEXT NOT NULL DEFAULT '',
    lap_number INTEGER NOT NULL DEFAULT 0,
    segment_id TEXT NOT NULL DEFAULT '',
    corner_phase TEXT NOT NULL DEFAULT '',
    issue_type TEXT NOT NULL DEFAULT '',
    issue_subtype TEXT NOT NULL DEFAULT '',
    axle TEXT NOT NULL DEFAULT '',
    duration_s REAL NOT NULL DEFAULT 0.0,
    severity REAL NOT NULL DEFAULT 0.0,
    confidence REAL NOT NULL DEFAULT 0.0,
    throttle REAL NOT NULL DEFAULT 0.0,
    brake REAL NOT NULL DEFAULT 0.0,
    speed_kmh REAL NOT NULL DEFAULT 0.0,
    gear INTEGER NOT NULL DEFAULT 0,
    compound TEXT NOT NULL DEFAULT '',
    tyre_age INTEGER NOT NULL DEFAULT 0,
    exclusion_reason TEXT NOT NULL DEFAULT '',
    provenance TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_corner_issue_occ_scope
    ON corner_issue_occurrences (car_id, track, layout_id);
"""

_DDL_V19 = """
CREATE TABLE IF NOT EXISTS applied_setup_checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    car_id INTEGER NOT NULL DEFAULT 0,
    track TEXT NOT NULL DEFAULT '',
    layout_id TEXT NOT NULL DEFAULT '',
    purpose TEXT NOT NULL DEFAULT '',
    setup_id TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL DEFAULT '',
    setup_hash TEXT NOT NULL DEFAULT '',
    fields_json TEXT NOT NULL DEFAULT '',
    changed_fields_json TEXT NOT NULL DEFAULT '',
    confirmed_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_applied_setup_cp_scope
    ON applied_setup_checkpoints (car_id, track, layout_id, purpose);
"""

# Engineering-Brain Phase 1 — canonical engineering identity spine (schema v20).
# Two ADDITIVE standalone tables (touch no existing table):
#   engineering_context       — one row per distinct canonical context, keyed by
#                               its versioned full `fingerprint` (UNIQUE). Stores
#                               the 13 identity components (NULL = genuinely
#                               unknown, never a guessed placeholder), the stable
#                               `scope_fingerprint` join key, the resolution
#                               status, and JSON provenance/unresolved/ambiguous/
#                               warnings for evidence honesty.
#   engineering_context_links — a compatibility BRIDGE from an existing record
#                               (source_kind, source_id) to a context fingerprint,
#                               so historical rows resolve WITHOUT a destructive
#                               column migration. UNIQUE(source_kind, source_id)
#                               makes linking idempotent.
# All columns nullable / defaulted; CREATE IF NOT EXISTS ⇒ idempotent migration.
_DDL_V20 = """
CREATE TABLE IF NOT EXISTS engineering_context (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint          TEXT    NOT NULL UNIQUE,
    scope_fingerprint    TEXT    NOT NULL DEFAULT '',
    fingerprint_version  TEXT    NOT NULL DEFAULT '',
    driver_id            TEXT,
    car_id               TEXT,
    track_location_id    TEXT,
    layout_id            TEXT,
    event_id             TEXT,
    discipline           TEXT,
    gt7_version          TEXT,
    config_id            TEXT,
    setup_id             TEXT,
    applied_checkpoint_id TEXT,
    lineage_id           TEXT,
    session_id           TEXT,
    run_id               TEXT,
    status               TEXT    NOT NULL DEFAULT '',
    provenance_json      TEXT    NOT NULL DEFAULT '{}',
    unresolved_json      TEXT    NOT NULL DEFAULT '[]',
    ambiguous_json       TEXT    NOT NULL DEFAULT '[]',
    warnings_json        TEXT    NOT NULL DEFAULT '[]',
    created_at           TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_eng_context_scope
    ON engineering_context (scope_fingerprint);
CREATE INDEX IF NOT EXISTS idx_eng_context_car_track
    ON engineering_context (car_id, track_location_id, layout_id);
CREATE INDEX IF NOT EXISTS idx_eng_context_config
    ON engineering_context (config_id);

CREATE TABLE IF NOT EXISTS engineering_context_links (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    source_kind          TEXT    NOT NULL DEFAULT '',
    source_id            TEXT    NOT NULL DEFAULT '',
    context_fingerprint  TEXT    NOT NULL DEFAULT '',
    scope_fingerprint    TEXT    NOT NULL DEFAULT '',
    created_at           TEXT    NOT NULL DEFAULT '',
    UNIQUE (source_kind, source_id)
);
CREATE INDEX IF NOT EXISTS idx_eng_link_fingerprint
    ON engineering_context_links (context_fingerprint);
CREATE INDEX IF NOT EXISTS idx_eng_link_scope
    ON engineering_context_links (scope_fingerprint);
"""

# Engineering-Brain Phase 2 — persisted setup experiments & recommendation
# evidence ledger (schema v21). SIX additive standalone tables (touch no existing
# table; CREATE IF NOT EXISTS ⇒ idempotent migration `_migrate_v21`):
#   setup_experiments                     — the immutable creation record; every
#                                           experiment references the Phase 1
#                                           canonical context via scope_fingerprint.
#                                           idempotency_key is UNIQUE (duplicate
#                                           rendering/reopen never re-creates one).
#   setup_experiment_changes              — append-only structured proposed deltas
#                                           (source-of-truth, NOT rendered text).
#   setup_experiment_protected_behaviours — confirmed-good behaviours to preserve.
#   setup_experiment_test_protocol        — 1:1 deterministic test plan.
#   setup_experiment_evidence             — append-only evidence ledger (references
#                                           + structured summaries, never blobs).
#   setup_experiment_state_history        — append-only lifecycle transitions.
# Unknown numeric values are NULL (not placeholder strings). Core join fields
# (scope/context fingerprint, parent setup, lineage, checkpoint, session, status,
# created_at, idempotency_key) are first-class indexed columns.
_DDL_V21 = """
CREATE TABLE IF NOT EXISTS setup_experiments (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    schema_version          TEXT    NOT NULL DEFAULT '',
    scope_fingerprint       TEXT    NOT NULL DEFAULT '',
    context_fingerprint     TEXT    NOT NULL DEFAULT '',
    context_schema_version  TEXT    NOT NULL DEFAULT '',
    context_status          TEXT    NOT NULL DEFAULT '',
    context_unresolved_json TEXT    NOT NULL DEFAULT '[]',
    context_warnings_json   TEXT    NOT NULL DEFAULT '[]',
    label                   TEXT    NOT NULL DEFAULT '',
    recommendation_source   TEXT    NOT NULL DEFAULT '',
    recommendation_status   TEXT    NOT NULL DEFAULT '',
    rule_engine_version     TEXT    NOT NULL DEFAULT '',
    driver_profile_version  TEXT    NOT NULL DEFAULT '',
    parent_setup_id         TEXT    NOT NULL DEFAULT '',
    proposed_setup_id       TEXT    NOT NULL DEFAULT '',
    applied_checkpoint_id   TEXT    NOT NULL DEFAULT '',
    lineage_id              TEXT    NOT NULL DEFAULT '',
    session_id              TEXT,
    run_id                  TEXT,
    status                  TEXT    NOT NULL DEFAULT 'draft',
    hypothesis_json         TEXT    NOT NULL DEFAULT '{}',
    deferred_diagnoses_json TEXT    NOT NULL DEFAULT '[]',
    rollback_target         TEXT    NOT NULL DEFAULT '',
    applied_match_state     TEXT    NOT NULL DEFAULT '',
    applied_comparison_json TEXT    NOT NULL DEFAULT '',
    idempotency_key         TEXT    NOT NULL UNIQUE,
    created_at              TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_setup_exp_scope
    ON setup_experiments (scope_fingerprint);
CREATE INDEX IF NOT EXISTS idx_setup_exp_context
    ON setup_experiments (context_fingerprint);
CREATE INDEX IF NOT EXISTS idx_setup_exp_parent
    ON setup_experiments (parent_setup_id);
CREATE INDEX IF NOT EXISTS idx_setup_exp_lineage
    ON setup_experiments (lineage_id);
CREATE INDEX IF NOT EXISTS idx_setup_exp_checkpoint
    ON setup_experiments (applied_checkpoint_id);
CREATE INDEX IF NOT EXISTS idx_setup_exp_session
    ON setup_experiments (session_id);
CREATE INDEX IF NOT EXISTS idx_setup_exp_status
    ON setup_experiments (status);
CREATE INDEX IF NOT EXISTS idx_setup_exp_created
    ON setup_experiments (created_at);

CREATE TABLE IF NOT EXISTS setup_experiment_changes (
    id                        INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id             INTEGER NOT NULL,
    field                     TEXT    NOT NULL DEFAULT '',
    subsystem                 TEXT    NOT NULL DEFAULT '',
    from_value                TEXT,
    to_value                  TEXT,
    delta_direction           TEXT    NOT NULL DEFAULT '',
    delta_magnitude           REAL,
    unit                      TEXT    NOT NULL DEFAULT '',
    rationale                 TEXT    NOT NULL DEFAULT '',
    expected_effect           TEXT    NOT NULL DEFAULT '',
    side_effects              TEXT    NOT NULL DEFAULT '',
    contraindications_checked TEXT    NOT NULL DEFAULT '',
    role                      TEXT    NOT NULL DEFAULT '',
    kind                      TEXT,
    change_order              INTEGER NOT NULL DEFAULT 0,
    rule_id                   TEXT    NOT NULL DEFAULT '',
    source_label              TEXT    NOT NULL DEFAULT '',
    symptom                   TEXT    NOT NULL DEFAULT '',
    risk_level                TEXT    NOT NULL DEFAULT '',
    confidence_level          TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_setup_exp_changes_exp
    ON setup_experiment_changes (experiment_id);

CREATE TABLE IF NOT EXISTS setup_experiment_protected_behaviours (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id       INTEGER NOT NULL,
    description         TEXT    NOT NULL DEFAULT '',
    field               TEXT    NOT NULL DEFAULT '',
    source_evidence     TEXT    NOT NULL DEFAULT '',
    corners_json        TEXT    NOT NULL DEFAULT '[]',
    baseline_confidence TEXT    NOT NULL DEFAULT '',
    regression_threshold TEXT   NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_setup_exp_protected_exp
    ON setup_experiment_protected_behaviours (experiment_id);

CREATE TABLE IF NOT EXISTS setup_experiment_test_protocol (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id         INTEGER NOT NULL,
    min_clean_laps        INTEGER,
    preferred_clean_laps  INTEGER,
    warmup_exclusion_laps INTEGER,
    tyre_compound         TEXT    NOT NULL DEFAULT '',
    fuel_state            TEXT    NOT NULL DEFAULT '',
    weather_assumption    TEXT    NOT NULL DEFAULT '',
    target_corners_json   TEXT    NOT NULL DEFAULT '[]',
    metrics_json          TEXT    NOT NULL DEFAULT '[]',
    driver_questions_json TEXT    NOT NULL DEFAULT '[]',
    success_criteria_json TEXT    NOT NULL DEFAULT '[]',
    failure_criteria_json TEXT    NOT NULL DEFAULT '[]',
    confounders_json      TEXT    NOT NULL DEFAULT '[]',
    rollback_target       TEXT    NOT NULL DEFAULT '',
    notes                 TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_setup_exp_protocol_exp
    ON setup_experiment_test_protocol (experiment_id);

CREATE TABLE IF NOT EXISTS setup_experiment_evidence (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id INTEGER NOT NULL,
    evidence_type TEXT    NOT NULL DEFAULT '',
    phase         TEXT    NOT NULL DEFAULT '',
    source_table  TEXT    NOT NULL DEFAULT '',
    source_id     TEXT    NOT NULL DEFAULT '',
    summary       TEXT    NOT NULL DEFAULT '',
    confidence    TEXT    NOT NULL DEFAULT '',
    provenance    TEXT    NOT NULL DEFAULT '',
    corner        TEXT    NOT NULL DEFAULT '',
    lap           INTEGER,
    session_id    TEXT,
    run_id        TEXT,
    stance        TEXT    NOT NULL DEFAULT 'neutral',
    created_at    TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_setup_exp_evidence_exp
    ON setup_experiment_evidence (experiment_id);
CREATE INDEX IF NOT EXISTS idx_setup_exp_evidence_phase
    ON setup_experiment_evidence (experiment_id, phase);

CREATE TABLE IF NOT EXISTS setup_experiment_state_history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id INTEGER NOT NULL,
    from_status   TEXT    NOT NULL DEFAULT '',
    to_status     TEXT    NOT NULL DEFAULT '',
    reason        TEXT    NOT NULL DEFAULT '',
    source        TEXT    NOT NULL DEFAULT '',
    created_at    TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_setup_exp_state_exp
    ON setup_experiment_state_history (experiment_id);
"""

# Engineering-Brain Phase 3 — closed-loop outcome evaluation, regression detection
# and failed-direction learning (schema v22). FIVE additive standalone tables
# (touch no existing table; CREATE IF NOT EXISTS ⇒ idempotent migration
# `_migrate_v22`):
#   setup_experiment_outcomes            — the IMMUTABLE evaluated outcome (one per
#                                          evaluation; UNIQUE idempotency_key; a
#                                          superseding correction sets superseded_by
#                                          on the prior, never overwrites it).
#   setup_experiment_outcome_criteria    — per-criterion verdicts (append-only).
#   setup_experiment_outcome_protected   — protected-behaviour verdicts.
#   setup_experiment_outcome_corners     — per-corner before/after comparison.
#   setup_experiment_failed_directions   — scoped failed-direction learning
#                                          (lockout/caution) for confirmed regressions.
# Every row references the Phase 1 scope_fingerprint + the Phase 2 experiment id.
# Core join fields are first-class indexed columns; unknowns are NULL.
_DDL_V22 = """
CREATE TABLE IF NOT EXISTS setup_experiment_outcomes (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id          INTEGER NOT NULL,
    scope_fingerprint      TEXT    NOT NULL DEFAULT '',
    parent_setup_id        TEXT    NOT NULL DEFAULT '',
    applied_checkpoint_id  TEXT    NOT NULL DEFAULT '',
    test_session_id        TEXT,
    test_run_id            TEXT,
    eval_version           TEXT    NOT NULL DEFAULT '',
    status                 TEXT    NOT NULL DEFAULT '',
    confidence             REAL    NOT NULL DEFAULT 0.0,
    confidence_level       TEXT    NOT NULL DEFAULT '',
    evidence_completeness  TEXT    NOT NULL DEFAULT '',
    validity_json          TEXT    NOT NULL DEFAULT '{}',
    whole_lap_json         TEXT    NOT NULL DEFAULT '{}',
    regressions_json       TEXT    NOT NULL DEFAULT '[]',
    improvements_json      TEXT    NOT NULL DEFAULT '[]',
    neutral_json           TEXT    NOT NULL DEFAULT '[]',
    confounders_json       TEXT    NOT NULL DEFAULT '[]',
    missing_evidence_json  TEXT    NOT NULL DEFAULT '[]',
    driver_agreement       TEXT    NOT NULL DEFAULT '',
    driver_review_summary  TEXT    NOT NULL DEFAULT '',
    decision_rationale     TEXT    NOT NULL DEFAULT '',
    next_action            TEXT    NOT NULL DEFAULT '',
    next_action_detail     TEXT    NOT NULL DEFAULT '',
    rollback_eligible      INTEGER NOT NULL DEFAULT 0,
    rollback_target        TEXT    NOT NULL DEFAULT '',
    learning_eligible      INTEGER NOT NULL DEFAULT 0,
    superseded_by          INTEGER,
    invalidated_reason     TEXT    NOT NULL DEFAULT '',
    idempotency_key        TEXT    NOT NULL UNIQUE,
    created_at             TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_exp_outcome_experiment
    ON setup_experiment_outcomes (experiment_id);
CREATE INDEX IF NOT EXISTS idx_exp_outcome_scope
    ON setup_experiment_outcomes (scope_fingerprint);
CREATE INDEX IF NOT EXISTS idx_exp_outcome_checkpoint
    ON setup_experiment_outcomes (applied_checkpoint_id);
CREATE INDEX IF NOT EXISTS idx_exp_outcome_session
    ON setup_experiment_outcomes (test_session_id);
CREATE INDEX IF NOT EXISTS idx_exp_outcome_status
    ON setup_experiment_outcomes (status);

CREATE TABLE IF NOT EXISTS setup_experiment_outcome_criteria (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    outcome_id      INTEGER NOT NULL,
    criterion_id    TEXT    NOT NULL DEFAULT '',
    description     TEXT    NOT NULL DEFAULT '',
    metric          TEXT    NOT NULL DEFAULT '',
    expected        TEXT    NOT NULL DEFAULT '',
    observed        TEXT    NOT NULL DEFAULT '',
    sample_count    INTEGER NOT NULL DEFAULT 0,
    confidence      TEXT    NOT NULL DEFAULT '',
    verdict         TEXT    NOT NULL DEFAULT '',
    missing_evidence TEXT   NOT NULL DEFAULT '',
    rationale       TEXT    NOT NULL DEFAULT '',
    is_target       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_exp_outcome_criteria_oid
    ON setup_experiment_outcome_criteria (outcome_id);

CREATE TABLE IF NOT EXISTS setup_experiment_outcome_protected (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    outcome_id          INTEGER NOT NULL,
    behaviour           TEXT    NOT NULL DEFAULT '',
    field               TEXT    NOT NULL DEFAULT '',
    baseline_state      TEXT    NOT NULL DEFAULT '',
    test_state          TEXT    NOT NULL DEFAULT '',
    comparison          TEXT    NOT NULL DEFAULT '',
    confidence          TEXT    NOT NULL DEFAULT '',
    verdict             TEXT    NOT NULL DEFAULT '',
    supporting_evidence TEXT    NOT NULL DEFAULT '',
    corners_json        TEXT    NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_exp_outcome_protected_oid
    ON setup_experiment_outcome_protected (outcome_id);

CREATE TABLE IF NOT EXISTS setup_experiment_outcome_corners (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    outcome_id        INTEGER NOT NULL,
    segment_id        TEXT    NOT NULL DEFAULT '',
    corner_name       TEXT    NOT NULL DEFAULT '',
    issue_type        TEXT    NOT NULL DEFAULT '',
    phase             TEXT    NOT NULL DEFAULT '',
    baseline_class    TEXT    NOT NULL DEFAULT '',
    test_class        TEXT    NOT NULL DEFAULT '',
    baseline_affected INTEGER NOT NULL DEFAULT 0,
    test_affected     INTEGER NOT NULL DEFAULT 0,
    sample_count      INTEGER NOT NULL DEFAULT 0,
    confidence        TEXT    NOT NULL DEFAULT '',
    verdict           TEXT    NOT NULL DEFAULT '',
    is_target         INTEGER NOT NULL DEFAULT 0,
    is_protected      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_exp_outcome_corners_oid
    ON setup_experiment_outcome_corners (outcome_id);

CREATE TABLE IF NOT EXISTS setup_experiment_failed_directions (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    outcome_id            INTEGER NOT NULL,
    experiment_id         INTEGER NOT NULL,
    scope_fingerprint     TEXT    NOT NULL DEFAULT '',
    driver                TEXT    NOT NULL DEFAULT '',
    car                   TEXT    NOT NULL DEFAULT '',
    track                 TEXT    NOT NULL DEFAULT '',
    layout_id             TEXT    NOT NULL DEFAULT '',
    discipline            TEXT    NOT NULL DEFAULT '',
    parent_setup_id       TEXT    NOT NULL DEFAULT '',
    field                 TEXT    NOT NULL DEFAULT '',
    from_value            TEXT,
    to_value              TEXT,
    direction             TEXT    NOT NULL DEFAULT '',
    magnitude             REAL,
    symptom               TEXT    NOT NULL DEFAULT '',
    regression_observed   TEXT    NOT NULL DEFAULT '',
    affected_protected    TEXT    NOT NULL DEFAULT '',
    corners_json          TEXT    NOT NULL DEFAULT '[]',
    strength              TEXT    NOT NULL DEFAULT '',
    confidence            TEXT    NOT NULL DEFAULT '',
    attribution_confidence TEXT   NOT NULL DEFAULT '',
    evidence_count        INTEGER NOT NULL DEFAULT 0,
    rule_id               TEXT    NOT NULL DEFAULT '',
    rule_engine_version   TEXT    NOT NULL DEFAULT '',
    superseded_by         INTEGER,
    created_at            TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_exp_failed_dir_scope
    ON setup_experiment_failed_directions (scope_fingerprint);
CREATE INDEX IF NOT EXISTS idx_exp_failed_dir_experiment
    ON setup_experiment_failed_directions (experiment_id);
CREATE INDEX IF NOT EXISTS idx_exp_failed_dir_field
    ON setup_experiment_failed_directions (car, track, layout_id, field);
"""

# Engineering-Brain Phase 5 — learned working-window persistence (schema v23).
# TWO additive standalone tables (touch no existing table; CREATE IF NOT EXISTS ⇒
# idempotent migration `_migrate_v23`):
#   setup_working_window_evidence — the APPEND-ONLY source-of-truth ledger: one row
#     per (context_key, experiment_id, outcome_id) contribution. UNIQUE on that
#     triple ⇒ replaying the same outcome contributes exactly once (idempotent).
#   setup_working_windows — the MATERIALISED window cache (a deterministic function
#     of its evidence ledger; recomputed on each learn). UNIQUE(context_key).
# Every learned update traces to an experiment + outcome + applied checkpoint +
# scope fingerprint + delta. Unknown numeric values are NULL.
_DDL_V23 = """
CREATE TABLE IF NOT EXISTS setup_working_window_evidence (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    context_key            TEXT    NOT NULL DEFAULT '',
    experiment_id          TEXT    NOT NULL DEFAULT '',
    outcome_id             TEXT    NOT NULL DEFAULT '',
    scope_fingerprint      TEXT    NOT NULL DEFAULT '',
    driver                 TEXT    NOT NULL DEFAULT '',
    car                    TEXT    NOT NULL DEFAULT '',
    track                  TEXT    NOT NULL DEFAULT '',
    layout_id              TEXT    NOT NULL DEFAULT '',
    discipline             TEXT    NOT NULL DEFAULT '',
    field                  TEXT    NOT NULL DEFAULT '',
    from_value             TEXT,
    to_value               TEXT,
    direction              TEXT    NOT NULL DEFAULT '',
    magnitude              REAL,
    outcome_status         TEXT    NOT NULL DEFAULT '',
    contribution           TEXT    NOT NULL DEFAULT '',
    is_compound            INTEGER NOT NULL DEFAULT 0,
    attribution_confidence TEXT    NOT NULL DEFAULT '',
    symptom                TEXT    NOT NULL DEFAULT '',
    corners_json           TEXT    NOT NULL DEFAULT '[]',
    checkpoint_id          TEXT    NOT NULL DEFAULT '',
    session_id             TEXT    NOT NULL DEFAULT '',
    is_direct              INTEGER NOT NULL DEFAULT 1,
    created_at             TEXT    NOT NULL DEFAULT '',
    UNIQUE (context_key, experiment_id, outcome_id)
);
CREATE INDEX IF NOT EXISTS idx_ww_evidence_context
    ON setup_working_window_evidence (context_key);
CREATE INDEX IF NOT EXISTS idx_ww_evidence_scope_field
    ON setup_working_window_evidence (scope_fingerprint, field);
CREATE INDEX IF NOT EXISTS idx_ww_evidence_experiment
    ON setup_working_window_evidence (experiment_id);

CREATE TABLE IF NOT EXISTS setup_working_windows (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    context_key            TEXT    NOT NULL UNIQUE,
    scope_fingerprint      TEXT    NOT NULL DEFAULT '',
    driver                 TEXT    NOT NULL DEFAULT '',
    car                    TEXT    NOT NULL DEFAULT '',
    track                  TEXT    NOT NULL DEFAULT '',
    layout_id              TEXT    NOT NULL DEFAULT '',
    discipline             TEXT    NOT NULL DEFAULT '',
    field                  TEXT    NOT NULL DEFAULT '',
    window_json            TEXT    NOT NULL DEFAULT '{}',
    confidence             TEXT    NOT NULL DEFAULT '',
    valid_experiment_count INTEGER NOT NULL DEFAULT 0,
    improvement_count      INTEGER NOT NULL DEFAULT 0,
    regression_count       INTEGER NOT NULL DEFAULT 0,
    updated_at             TEXT    NOT NULL DEFAULT '',
    eval_version           TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_ww_scope
    ON setup_working_windows (scope_fingerprint);
CREATE INDEX IF NOT EXISTS idx_ww_scope_field
    ON setup_working_windows (car, track, layout_id, discipline, field);
"""

# Engineering-Brain Phase 8 — permanent cross-session engineering memory.
# ONE append-only, IMMUTABLE row per completed engineering review, captured WITH its
# full memory context (driver/car/track/layout/discipline/gt7/compound). The row is
# never UPDATEd or DELETEd; re-recording the same review is a no-op (UNIQUE record_key).
# Long-term memory, history, metrics and the scorecard are deterministic FOLDS over
# these rows — regenerable, so a restart reproduces identical fingerprints.
_DDL_V24 = """
CREATE TABLE IF NOT EXISTS engineering_development_records (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    record_key               TEXT    NOT NULL UNIQUE,
    memory_context_key       TEXT    NOT NULL DEFAULT '',
    scope_fingerprint        TEXT    NOT NULL DEFAULT '',
    driver                   TEXT    NOT NULL DEFAULT '',
    car                      TEXT    NOT NULL DEFAULT '',
    track                    TEXT    NOT NULL DEFAULT '',
    layout_id                TEXT    NOT NULL DEFAULT '',
    discipline               TEXT    NOT NULL DEFAULT '',
    gt7_version              TEXT    NOT NULL DEFAULT '',
    compound                 TEXT    NOT NULL DEFAULT '',
    experiment_id            TEXT    NOT NULL DEFAULT '',
    outcome_id               TEXT    NOT NULL DEFAULT '',
    outcome_status           TEXT    NOT NULL DEFAULT '',
    confidence_level         TEXT    NOT NULL DEFAULT '',
    recorded_at              TEXT    NOT NULL DEFAULT '',
    session_date             TEXT    NOT NULL DEFAULT '',
    test_session_id          TEXT    NOT NULL DEFAULT '',
    record_json              TEXT    NOT NULL DEFAULT '{}',
    content_fingerprint      TEXT    NOT NULL DEFAULT '',
    eval_version             TEXT    NOT NULL DEFAULT '',
    created_at               TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_dev_record_ctx
    ON engineering_development_records (memory_context_key);
CREATE INDEX IF NOT EXISTS idx_dev_record_scope
    ON engineering_development_records (scope_fingerprint);
CREATE INDEX IF NOT EXISTS idx_dev_record_experiment
    ON engineering_development_records (experiment_id);
CREATE INDEX IF NOT EXISTS idx_dev_record_context_cols
    ON engineering_development_records (car, track, layout_id, discipline, compound);
"""

# Engineering-Brain Phase 11 — immutable pre-flight/actual calibration records.
# ONE append-only, IMMUTABLE row per completed experiment comparing the Phase-10
# prediction with the Phase-3 actual outcome + Phase-6 residuals. The row is never
# UPDATEd or DELETEd; re-recording the same reconciliation is a no-op (UNIQUE
# record_key). The prediction is a point-in-time input that is not reliably
# regenerable after the outcome exists, so the calibration history is persisted.
_DDL_V25 = """
CREATE TABLE IF NOT EXISTS engineering_reconciliation_records (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    record_key               TEXT    NOT NULL UNIQUE,
    memory_context_key       TEXT    NOT NULL DEFAULT '',
    experiment_id            TEXT    NOT NULL DEFAULT '',
    outcome_id               TEXT    NOT NULL DEFAULT '',
    predicted_risk           TEXT    NOT NULL DEFAULT '',
    outcome_status           TEXT    NOT NULL DEFAULT '',
    overall_accuracy         REAL    NOT NULL DEFAULT 0.0,
    prediction_fingerprint   TEXT    NOT NULL DEFAULT '',
    recorded_at              TEXT    NOT NULL DEFAULT '',
    record_json              TEXT    NOT NULL DEFAULT '{}',
    content_fingerprint      TEXT    NOT NULL DEFAULT '',
    eval_version             TEXT    NOT NULL DEFAULT '',
    created_at               TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_recon_record_ctx
    ON engineering_reconciliation_records (memory_context_key);
CREATE INDEX IF NOT EXISTS idx_recon_record_experiment
    ON engineering_reconciliation_records (experiment_id);
"""

_DDL_V26 = """
CREATE TABLE IF NOT EXISTS engineering_campaign_registry (
    campaign_id                TEXT    PRIMARY KEY,
    car                        TEXT    NOT NULL DEFAULT '',
    track                      TEXT    NOT NULL DEFAULT '',
    layout                     TEXT    NOT NULL DEFAULT '',
    discipline                 TEXT    NOT NULL DEFAULT '',
    objective_family           TEXT    NOT NULL DEFAULT '',
    objective_region           TEXT    NOT NULL DEFAULT '',
    gt7_version                TEXT    NOT NULL DEFAULT '',
    creation_session           TEXT    NOT NULL DEFAULT '',
    first_seen                 TEXT    NOT NULL DEFAULT '',
    last_seen                  TEXT    NOT NULL DEFAULT '',
    last_updated               TEXT    NOT NULL DEFAULT '',
    notes                      TEXT    NOT NULL DEFAULT '',
    manual_archive_flag        INTEGER NOT NULL DEFAULT 0,
    completion_state           TEXT    NOT NULL DEFAULT '',
    abandonment_reason         TEXT    NOT NULL DEFAULT '',
    linked_development_records TEXT    NOT NULL DEFAULT '[]',
    linked_experiments         TEXT    NOT NULL DEFAULT '[]',
    linked_outcomes            TEXT    NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_campaign_registry_scope
    ON engineering_campaign_registry (car, track, layout, discipline);
"""

_DDL = (_DDL_BASE + _DDL_V1 + _DDL_V4 + _DDL_V5 + _DDL_V6 + _DDL_V8 + _DDL_V15
        + _DDL_V17 + _DDL_V18 + _DDL_V19 + _DDL_V20 + _DDL_V21 + _DDL_V22 + _DDL_V23
        + _DDL_V24 + _DDL_V25 + _DDL_V26)

def ms_to_str(ms: int) -> str:
    if ms <= 0:
        return "—"
    total_s = ms / 1000.0
    m = int(total_s // 60)
    s = total_s - m * 60
    return f"{m}:{s:06.3f}"


def _json_loads_list(v) -> list:
    if isinstance(v, (list, tuple)):
        return list(v)
    try:
        d = json.loads(v) if v else []
        return list(d) if isinstance(d, (list, tuple)) else []
    except Exception:
        return []


def _rehydrate_window(wd: dict):
    """Reconstruct a LearnedWorkingWindow from its stored to_dict() (Phase 5)."""
    from strategy.working_window import (
        LearnedWorkingWindow, WindowContextKey, WindowConfidence,
        DirectionalEvidence, DirectionEffect)
    c = wd.get("context") or {}
    ctx = WindowContextKey(
        scope_fingerprint=c.get("scope_fingerprint", ""), driver=c.get("driver", ""),
        car=c.get("car", ""), track=c.get("track", ""),
        layout_id=c.get("layout_id", ""), discipline=c.get("discipline", ""),
        field=c.get("field", ""))
    try:
        conf = WindowConfidence(wd.get("confidence") or "none")
    except ValueError:
        conf = WindowConfidence.NONE
    directional = []
    for d in (wd.get("directional") or []):
        try:
            eff = DirectionEffect(d.get("effect") or "unknown")
        except ValueError:
            eff = DirectionEffect.UNKNOWN
        directional.append(DirectionalEvidence(
            direction=d.get("direction", ""), effect=eff,
            improved_count=int(d.get("improved_count") or 0),
            worsened_count=int(d.get("worsened_count") or 0),
            no_effect_count=int(d.get("no_effect_count") or 0),
            locked_out=bool(d.get("locked_out")),
            lockout_reason=d.get("lockout_reason", "")))
    return LearnedWorkingWindow(
        context=ctx, field=wd.get("field", ""),
        successful_values=tuple(wd.get("successful_values") or ()),
        unsuccessful_values=tuple(wd.get("unsuccessful_values") or ()),
        ineffective_values=tuple(wd.get("ineffective_values") or ()),
        low_bound=wd.get("low_bound"), high_bound=wd.get("high_bound"),
        preferred_center=wd.get("preferred_center"),
        valid_experiment_count=int(wd.get("valid_experiment_count") or 0),
        improvement_count=int(wd.get("improvement_count") or 0),
        regression_count=int(wd.get("regression_count") or 0),
        unchanged_count=int(wd.get("unchanged_count") or 0),
        inconclusive_count=int(wd.get("inconclusive_count") or 0),
        confidence=conf, provenance=tuple(wd.get("provenance") or ()),
        supporting_experiment_ids=tuple(wd.get("supporting_experiment_ids") or ()),
        supporting_checkpoint_ids=tuple(wd.get("supporting_checkpoint_ids") or ()),
        supporting_session_ids=tuple(wd.get("supporting_session_ids") or ()),
        corners=tuple(wd.get("corners") or ()),
        directional=tuple(directional), contradiction=bool(wd.get("contradiction")),
        has_direct_evidence=bool(wd.get("has_direct_evidence", True)),
        warnings=tuple(wd.get("warnings") or ()))


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
        if version < 9:
            self._migrate_v9()
            self._conn.execute("PRAGMA user_version = 9")
            self._conn.commit()
        if version < 10:
            self._migrate_v10()
            self._conn.execute("PRAGMA user_version = 10")
            self._conn.commit()
        if version < 11:
            self._migrate_v11()
            self._conn.execute("PRAGMA user_version = 11")
            self._conn.commit()
        if version < 12:
            self._migrate_v12()
            self._conn.execute("PRAGMA user_version = 12")
            self._conn.commit()
        if version < 13:
            self._migrate_v13()
            self._conn.execute("PRAGMA user_version = 13")
            self._conn.commit()
        if version < 14:
            self._migrate_v14()
            self._conn.execute("PRAGMA user_version = 14")
            self._conn.commit()
        if version < 15:
            self._migrate_v15()
            self._conn.execute("PRAGMA user_version = 15")
            self._conn.commit()
        if version < 16:
            self._migrate_v16()
            self._conn.execute("PRAGMA user_version = 16")
            self._conn.commit()
        if version < 17:
            self._migrate_v17()
            self._conn.execute("PRAGMA user_version = 17")
            self._conn.commit()
        if version < 18:
            self._migrate_v18()
            self._conn.execute("PRAGMA user_version = 18")
            self._conn.commit()
        if version < 19:
            self._migrate_v19()
            self._conn.execute("PRAGMA user_version = 19")
            self._conn.commit()
        if version < 20:
            self._migrate_v20()
            self._conn.execute("PRAGMA user_version = 20")
            self._conn.commit()
        if version < 21:
            self._migrate_v21()
            self._conn.execute("PRAGMA user_version = 21")
            self._conn.commit()
        if version < 22:
            self._migrate_v22()
            self._conn.execute("PRAGMA user_version = 22")
            self._conn.commit()
        if version < 23:
            self._migrate_v23()
            self._conn.execute("PRAGMA user_version = 23")
            self._conn.commit()
        if version < 24:
            self._migrate_v24()
            self._conn.execute("PRAGMA user_version = 24")
            self._conn.commit()
        if version < 25:
            self._migrate_v25()
            self._conn.execute("PRAGMA user_version = 25")
            self._conn.commit()
        if version < 26:
            self._migrate_v26()
            self._conn.execute("PRAGMA user_version = 26")
            self._conn.commit()

    def _migrate_v26(self) -> None:
        """Engineering-Brain Phase 19 — campaign persistence registry (schema v26). Adds ONE
        standalone additive table (engineering_campaign_registry) storing metadata-only
        campaign identity (creation session, first/last seen, notes, manual archive flag,
        completion state, links). Touches no existing table, alters no existing query, and
        rewrites no historical data. CREATE IF NOT EXISTS throughout ⇒ idempotent."""
        self._conn.executescript(_DDL_V26)

    def _migrate_v25(self) -> None:
        """Engineering-Brain Phase 11 — pre-flight/actual calibration records (schema
        v25). Adds ONE standalone additive table (engineering_reconciliation_records)
        storing one immutable, append-only row per completed experiment reconciliation.
        Touches no existing table and rewrites no historical data. CREATE IF NOT EXISTS
        throughout ⇒ the migration is idempotent."""
        self._conn.executescript(_DDL_V25)

    def _migrate_v24(self) -> None:
        """Engineering-Brain Phase 8 — permanent cross-session engineering memory
        (schema v24). Adds ONE standalone additive table
        (engineering_development_records) that stores one immutable, append-only row
        per completed engineering review. Touches no existing table and rewrites no
        historical data. CREATE IF NOT EXISTS throughout ⇒ the migration is
        idempotent."""
        self._conn.executescript(_DDL_V24)

    def _migrate_v22(self) -> None:
        """Engineering-Brain Phase 3 — closed-loop outcome evaluation (schema v22).
        Adds five standalone additive tables (setup_experiment_outcomes + criteria/
        protected/corners child tables + setup_experiment_failed_directions).
        Touches no existing table, rewrites no historical data. CREATE IF NOT
        EXISTS throughout ⇒ the migration is idempotent."""
        self._conn.executescript(_DDL_V22)

    def _migrate_v23(self) -> None:
        """Engineering-Brain Phase 5 — learned working-window persistence (schema
        v23). Adds two standalone additive tables (setup_working_window_evidence +
        setup_working_windows). Touches no existing table, rewrites no historical
        data. CREATE IF NOT EXISTS throughout ⇒ the migration is idempotent."""
        self._conn.executescript(_DDL_V23)

    def _migrate_v21(self) -> None:
        """Engineering-Brain Phase 2 — persisted setup experiments & recommendation
        evidence ledger (schema v21). Adds six standalone additive tables
        (setup_experiments + changes/protected/test_protocol/evidence/state_history).
        Touches no existing table and rewrites no historical data. CREATE IF NOT
        EXISTS throughout ⇒ the migration is idempotent."""
        self._conn.executescript(_DDL_V21)

    def _migrate_v20(self) -> None:
        """Engineering-Brain Phase 1 — canonical engineering identity spine
        (schema v20). Adds two standalone additive tables (engineering_context +
        engineering_context_links). Touches no existing table and rewrites no
        historical data, so it is behaviour-preserving for all prior records.
        CREATE IF NOT EXISTS throughout ⇒ the migration is idempotent."""
        self._conn.executescript(_DDL_V20)

    def _migrate_v19(self) -> None:
        """Saved-vs-applied-in-GT7 checkpoint (Sprint 10 UI) — additive
        applied_setup_checkpoints table (schema v19). Stores one append-only row
        each time the driver confirms a setup was applied in GT7 ("Changes Applied
        in Game"), so the three-state apply status survives restart and telemetry
        can be attributed to the setup that was actually in the car. Standalone
        table (CREATE IF NOT EXISTS, idempotent); touches no existing table."""
        self._conn.executescript(_DDL_V19)

    def _migrate_v18(self) -> None:
        """Cross-lap persistence (Sprint 5) — additive corner_issue_occurrences
        table (schema v18). Stores one row per admissible/suppressed issue
        episode so the pure persistence engine can compute same-corner recurrence
        and cross-session confirmation from stored data. Standalone table
        (CREATE IF NOT EXISTS, idempotent); touches no existing table."""
        self._conn.executescript(_DDL_V18)

    def _migrate_v17(self) -> None:
        """Engineering-Brain (live telemetry) — additive corner_slip_telemetry table
        (schema v17). Cross-session per-corner slip accumulation. Standalone table
        (CREATE IF NOT EXISTS, idempotent); touches no existing table."""
        self._conn.executescript(_DDL_V17)

    def _migrate_v16(self) -> None:
        """Engineering-Brain Phase 7 — additive driver_feedback columns (schema v16).

        Adds vs_previous / corner / phase TEXT columns (DEFAULT '') for structured
        Practice Review capture. Existing rows keep '' — behaviour-preserving. A
        duplicate-column guard makes the migration idempotent."""
        for table, col_def in _V16_ALTER_COLUMNS:
            try:
                self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
            except Exception as exc:
                if "duplicate column" not in str(exc).lower():
                    raise

    def _migrate_v15(self) -> None:
        """Engineering-Brain Phase 1 — additive setup_lineage table (schema v15).

        Creates a new, standalone lineage table (CREATE IF NOT EXISTS, idempotent).
        Touches no existing table, so it is behaviour-preserving for all prior data.
        """
        self._conn.executescript(_DDL_V15)

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

    def _migrate_v9(self) -> None:
        """Add OFR-1 scoring columns to setup_recommendations (schema version 9).

        score_confidence: sentinel -1.0 means unscored.
        score_verdict:    '' means unscored; values: improved/worsened/neutral/insufficient_data.
        score_details:    JSON blob with lap-delta, per-event rates, assumptions.
        """
        for table, col_def in _V9_ALTER_COLUMNS:
            try:
                self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
            except Exception as exc:
                if "duplicate column" not in str(exc).lower():
                    raise

    def _migrate_v6(self) -> None:
        try:
            self._conn.execute(
                "ALTER TABLE setup_recommendations ADD COLUMN before_metrics TEXT NOT NULL DEFAULT '{}'"
            )
        except Exception as e:
            if "duplicate column" not in str(e).lower():
                raise

    def _migrate_v10(self) -> None:
        """Add setup_id + rating to driver_feedback (schema version 10).

        setup_id: which saved setup was running for the stint (0 = unattributed).
        rating:   driver's subjective take on that setup ('' | liked | hated | neutral),
                  moved here from the Setup Builder's rate-this-result control.
        Existing rows backfill via DEFAULT and are treated as unrated.
        """
        for table, col_def in _V10_ALTER_COLUMNS:
            try:
                self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
            except Exception as exc:
                if "duplicate column" not in str(exc).lower():
                    raise

    def _migrate_v11(self) -> None:
        """Group 42 — Rule-First Setup Brain additive columns (schema version 11).

        Adds 8 nullable TEXT columns to setup_recommendations:
          deterministic_plan_json  — JSON summary of the SetupPlan (proposed_count,
                                     rejected_candidate_count, protected_fields).
          ai_audit_json            — JSON of the AuditResult._asdict().
          validation_status        — SetupRecommendationResult.status string.
          approved_changes_json    — JSON list of approved changes.
          rejected_changes_json    — JSON list of rejected candidates.
          diagnosis_json           — JSON of the diagnosis dict.
          driver_profile_version   — e.g. "v1.0-hardcoded".
          rule_engine_version      — e.g. "42.0".

        All are nullable TEXT (no DEFAULT) so existing rows keep NULL without
        constraint violation and no back-fill is needed.
        A "duplicate column" guard follows the V9 pattern.
        """
        for table, col_def in _V11_ALTER_COLUMNS:
            try:
                self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
            except Exception as exc:
                if "duplicate column" not in str(exc).lower():
                    raise

    def _migrate_v12(self) -> None:
        """Group 46 — Learning & Race Context Intelligence (schema version 12).

        Creates learning_outcomes table to persist cross-session rule outcome
        records.  Each row ties a rule_id to a car/track/layout scope and records
        a verdict (improved / worsened / neutral / insufficient_data) so the
        confidence-upgrade gate can query real historical success rates.

        Idempotent — uses IF NOT EXISTS throughout; no ALTER TABLE.
        """
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS learning_outcomes (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                ts                   TEXT    NOT NULL DEFAULT '',
                car_id               INTEGER NOT NULL DEFAULT 0,
                track                TEXT    NOT NULL DEFAULT '',
                layout_id            TEXT    NOT NULL DEFAULT '',
                session_id           INTEGER NOT NULL DEFAULT 0,
                session_type         TEXT    NOT NULL DEFAULT '',
                rule_id              TEXT    NOT NULL DEFAULT '',
                source_path          TEXT    NOT NULL DEFAULT '',
                verdict              TEXT    NOT NULL DEFAULT '',
                confidence           REAL    NOT NULL DEFAULT 0.0,
                driver_profile_version TEXT  NOT NULL DEFAULT '',
                rule_engine_version  TEXT    NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_learning_outcomes_scope
                ON learning_outcomes (car_id, track, layout_id);
        """)

    def _migrate_v13(self) -> None:
        """Group 47 — Outcome Verification & Learning Loop 2 (schema version 13).

        Adds 5 additive TEXT columns to learning_outcomes carrying the richer
        outcome-verification evidence (target_issue, evidence_summary,
        driver_feedback, safety_notes, outcome_kind).

        Additive and idempotent — all columns are NOT NULL DEFAULT '' so existing
        v12 rows survive without back-fill, and the duplicate-column guard (V9
        pattern) makes re-running the migration a no-op.  If the learning_outcomes
        table does not yet exist (older DB opened straight to v13) the CREATE in
        _migrate_v12 runs first because migrations apply in ascending order.
        """
        for table, col_def in _V13_ALTER_COLUMNS:
            try:
                self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
            except Exception as exc:
                if "duplicate column" not in str(exc).lower():
                    raise

    def _migrate_v14(self) -> None:
        """Group 62 — ABS Regulation additive column (schema version 14).

        Adds abs INTEGER NOT NULL DEFAULT 1 to the events table so each event
        can flag whether ABS is permitted.  Existing rows receive the default
        value 1 (ABS allowed), leaving behaviour unchanged.  A duplicate-column
        guard makes the migration idempotent on already-upgraded databases.
        """
        for table, col_def in _V14_ALTER_COLUMNS:
            try:
                self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
            except Exception as exc:
                if "duplicate column" not in str(exc).lower():
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

    # ------------------------------------------------------------------
    # Learning outcomes CRUD (schema version 12)
    # ------------------------------------------------------------------

    def record_learning_outcome(
        self,
        car_id: int,
        track: str,
        layout_id: str,
        session_id: int,
        session_type: str,
        rule_id: str,
        source_path: str,
        verdict: str,
        confidence: float,
        driver_profile_version: str,
        rule_engine_version: str,
        *,
        target_issue: str = "",
        evidence_summary: str = "",
        driver_feedback: str = "",
        safety_notes: str = "",
        outcome_kind: str = "",
    ) -> None:
        """Insert a single learning outcome row.

        The Group 47 fields (target_issue, evidence_summary, driver_feedback,
        safety_notes, outcome_kind) are keyword-only with empty-string defaults so
        every existing Group 46 caller keeps working unchanged; when supplied they
        persist the richer outcome-verification evidence into the v13 columns.

        Never raises — any error (corrupt DB, missing table, type error) is
        silently swallowed so callers cannot be disrupted by persistence failures.
        """
        try:
            ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
            with self._lock:
                self._conn.execute(
                    """INSERT INTO learning_outcomes
                           (ts, car_id, track, layout_id, session_id, session_type,
                            rule_id, source_path, verdict, confidence,
                            driver_profile_version, rule_engine_version,
                            target_issue, evidence_summary, driver_feedback,
                            safety_notes, outcome_kind)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        ts, car_id, track, layout_id, session_id, session_type,
                        rule_id, source_path, verdict, float(confidence),
                        driver_profile_version, rule_engine_version,
                        target_issue, evidence_summary, driver_feedback,
                        safety_notes, outcome_kind,
                    ),
                )
                self._conn.commit()
        except Exception:
            pass  # never raise outward — learning persistence is best-effort

    def record_lineage(
        self,
        car_id: int,
        track: str,
        layout_id: str,
        *,
        objective: str = "",
        rec_id: "int | None" = None,
        session_id: "int | None" = None,
        changes_json: str = "[]",
        label: str = "",
    ) -> "int | None":
        """Insert a setup_lineage node, auto-resolving its PARENT as the most-recent
        existing node at this car+track+layout scope. Returns the new node id, or None
        on any error (never raises — lineage is best-effort, like learning outcomes)."""
        try:
            ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
            with self._lock:
                prow = self._conn.execute(
                    """SELECT id FROM setup_lineage
                       WHERE car_id=? AND track=? AND layout_id=?
                       ORDER BY id DESC LIMIT 1""",
                    (car_id, track, layout_id),
                ).fetchone()
                parent_id = prow[0] if prow else None
                cur = self._conn.execute(
                    """INSERT INTO setup_lineage
                           (ts, car_id, track, layout_id, objective, parent_id, rec_id,
                            session_id, changes_json, label)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (ts, car_id, track, layout_id, objective, parent_id, rec_id,
                     session_id, changes_json, label),
                )
                self._conn.commit()
                node_id = int(cur.lastrowid)
        except Exception:
            return None
        # Phase 1: bridge this lineage node to its canonical engineering context
        # (best-effort, outside the write lock).
        try:
            from data.engineering_context_key import resolve_from_lineage
            res = resolve_from_lineage({
                "id": node_id, "car_id": car_id, "track": track,
                "layout_id": layout_id, "objective": objective,
                "session_id": session_id,
            })
            self.resolve_and_link_engineering_context(res, "setup_lineage", node_id)
        except Exception:
            pass
        return node_id

    def record_lineage_outcome(
        self, lineage_id: int, verdict: str, outcome_session_id: "int | None" = None
    ) -> None:
        """Stamp the measured verdict (improved/worsened/neutral) onto a lineage node."""
        try:
            with self._lock:
                self._conn.execute(
                    """UPDATE setup_lineage
                       SET outcome_verdict=?, outcome_session_id=? WHERE id=?""",
                    (str(verdict or ""), outcome_session_id, int(lineage_id)),
                )
                self._conn.commit()
        except Exception:
            pass

    def record_lineage_outcome_by_rec(
        self, rec_id: int, verdict: str, outcome_session_id: "int | None" = None
    ) -> None:
        """Stamp the verdict onto the lineage node produced by a given recommendation
        (used by the scoring pass, which knows the rec_id). Best-effort, never raises."""
        try:
            with self._lock:
                self._conn.execute(
                    """UPDATE setup_lineage
                       SET outcome_verdict=?, outcome_session_id=? WHERE rec_id=?""",
                    (str(verdict or ""), outcome_session_id, int(rec_id)),
                )
                self._conn.commit()
        except Exception:
            pass

    def record_latest_lineage_outcome(
        self, car_id: int, track: str, layout_id: str, verdict: str,
        outcome_session_id: "int | None" = None
    ) -> None:
        """Stamp the verdict onto the MOST RECENT lineage node at this scope — used when
        the driver gives an explicit better/worse-vs-previous report (Phase 7). Only
        overwrites an unscored node so a measured telemetry verdict is not clobbered.
        Best-effort, never raises."""
        try:
            with self._lock:
                row = self._conn.execute(
                    """SELECT id FROM setup_lineage
                       WHERE car_id=? AND track=? AND layout_id=? AND outcome_verdict=''
                       ORDER BY id DESC LIMIT 1""",
                    (car_id, track, layout_id),
                ).fetchone()
                if row is not None:
                    self._conn.execute(
                        """UPDATE setup_lineage
                           SET outcome_verdict=?, outcome_session_id=? WHERE id=?""",
                        (str(verdict or ""), outcome_session_id, int(row[0])),
                    )
                    self._conn.commit()
        except Exception:
            pass

    def get_lineage(
        self, car_id: int, track: str, layout_id: str, limit: int = 50
    ) -> list[dict]:
        """Return setup_lineage nodes for a scope, newest first. [] on any error."""
        try:
            with self._lock:
                rows = self._conn.execute(
                    """SELECT * FROM setup_lineage
                       WHERE car_id=? AND track=? AND layout_id=?
                       ORDER BY id DESC LIMIT ?""",
                    (car_id, track, layout_id, int(limit)),
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Canonical engineering identity spine (Engineering-Brain Phase 1, v20)
    # ------------------------------------------------------------------
    _ECK_COMPONENTS = (
        "driver_id", "car_id", "track_location_id", "layout_id", "event_id",
        "discipline", "gt7_version", "config_id", "setup_id",
        "applied_checkpoint_id", "lineage_id", "session_id", "run_id",
    )

    def upsert_engineering_context(self, resolution) -> "str | None":
        """Persist a resolved canonical engineering context. Idempotent, atomic.

        ``resolution`` is an ``EngineeringContextResolution`` (duck-typed). The
        row is keyed by its versioned full ``fingerprint`` (UNIQUE): re-resolving
        the SAME context is a no-op (INSERT OR IGNORE), never a duplicate or a
        partial write. A malformed/unresolvable/invalid resolution is NOT stored
        (unknown identity is not a manufactured row). Returns the fingerprint on
        success, else None. Best-effort — never raises outward."""
        import json as _json
        try:
            ctx = resolution.context
            status = getattr(resolution.status, "value", resolution.status)
            # Refuse to persist an identity with no known component — an empty
            # context is not authoritative and would collide across records.
            if not ctx.known_fields or str(status) == "invalid":
                return None
            fp = ctx.fingerprint()
            scope = ctx.scope_fingerprint()
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            values = {n: getattr(ctx, n) for n in self._ECK_COMPONENTS}
            with self._lock:
                # Single statement ⇒ a context is never partially written.
                self._conn.execute(
                    """INSERT OR IGNORE INTO engineering_context
                       (fingerprint, scope_fingerprint, fingerprint_version,
                        driver_id, car_id, track_location_id, layout_id, event_id,
                        discipline, gt7_version, config_id, setup_id,
                        applied_checkpoint_id, lineage_id, session_id, run_id,
                        status, provenance_json, unresolved_json, ambiguous_json,
                        warnings_json, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (fp, scope,
                     getattr(resolution, "fingerprint_version", ""),
                     values["driver_id"], values["car_id"],
                     values["track_location_id"], values["layout_id"],
                     values["event_id"], values["discipline"],
                     values["gt7_version"], values["config_id"],
                     values["setup_id"], values["applied_checkpoint_id"],
                     values["lineage_id"], values["session_id"], values["run_id"],
                     str(status),
                     _json.dumps(dict(resolution.provenance), sort_keys=True),
                     _json.dumps(list(resolution.unresolved)),
                     _json.dumps(list(resolution.ambiguous)),
                     _json.dumps(list(resolution.warnings)),
                     now))
                self._conn.commit()
            return fp
        except Exception:
            return None

    def link_engineering_context(
        self, source_kind: str, source_id, context_fingerprint: str,
        scope_fingerprint: str = "",
    ) -> None:
        """Bridge an existing record to a canonical context, idempotently.

        ``(source_kind, source_id)`` is UNIQUE, so re-linking replaces the prior
        link rather than duplicating it — a historical row can be resolved and
        bridged without any destructive column migration. Best-effort."""
        try:
            if not context_fingerprint:
                return
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            with self._lock:
                self._conn.execute(
                    """INSERT OR REPLACE INTO engineering_context_links
                       (source_kind, source_id, context_fingerprint,
                        scope_fingerprint, created_at)
                       VALUES (?,?,?,?,?)""",
                    (str(source_kind or ""),
                     str(source_id if source_id is not None else ""),
                     str(context_fingerprint), str(scope_fingerprint or ""), now))
                self._conn.commit()
        except Exception:
            pass

    def resolve_and_link_engineering_context(
        self, resolution, source_kind: str, source_id
    ) -> "str | None":
        """Upsert a resolved context AND bridge the source record to it in one
        best-effort call. Returns the context fingerprint, or None if the
        resolution carried no usable identity (in which case NO link is made —
        an unresolved record stays honestly unlinked, still queryable via its
        own table). Never raises outward."""
        fp = self.upsert_engineering_context(resolution)
        if fp is None:
            return None
        try:
            scope = resolution.context.scope_fingerprint()
        except Exception:
            scope = ""
        self.link_engineering_context(source_kind, source_id, fp, scope)
        return fp

    def get_engineering_context(self, fingerprint: str) -> "dict | None":
        """Return a stored canonical context by its full fingerprint, or None."""
        try:
            with self._lock:
                row = self._conn.execute(
                    "SELECT * FROM engineering_context WHERE fingerprint = ?",
                    (str(fingerprint),)).fetchone()
            return dict(row) if row is not None else None
        except Exception:
            return None

    def get_engineering_context_for_source(
        self, source_kind: str, source_id
    ) -> "dict | None":
        """Return the canonical context linked to a source record, or None.

        Joins the bridge to the context table so a session / applied-checkpoint /
        lineage / driver-feedback row can be resolved to its shared context
        without touching that record's own schema."""
        try:
            with self._lock:
                row = self._conn.execute(
                    """SELECT c.* FROM engineering_context_links l
                       JOIN engineering_context c
                         ON c.fingerprint = l.context_fingerprint
                       WHERE l.source_kind = ? AND l.source_id = ?""",
                    (str(source_kind or ""),
                     str(source_id if source_id is not None else ""))).fetchone()
            return dict(row) if row is not None else None
        except Exception:
            return None

    def get_engineering_contexts_by_scope(
        self, scope_fingerprint: str
    ) -> list[dict]:
        """Return all canonical contexts sharing a physical-scope join key.

        This is the future before/after setup-comparison join: every session,
        applied setup, lineage node and feedback record for the same
        driver/car/track/layout/physics shares one ``scope_fingerprint``."""
        try:
            with self._lock:
                rows = self._conn.execute(
                    """SELECT * FROM engineering_context
                       WHERE scope_fingerprint = ? ORDER BY id ASC""",
                    (str(scope_fingerprint),)).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def get_engineering_context_links_by_scope(
        self, scope_fingerprint: str
    ) -> list[dict]:
        """Return every source record (kind + id) bridged to a physical scope."""
        try:
            with self._lock:
                rows = self._conn.execute(
                    """SELECT * FROM engineering_context_links
                       WHERE scope_fingerprint = ? ORDER BY id ASC""",
                    (str(scope_fingerprint),)).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Setup experiments & recommendation evidence ledger (Phase 2, v21)
    # ------------------------------------------------------------------
    def create_setup_experiment(self, exp) -> "int | None":
        """Persist a SetupExperiment atomically + idempotently. Returns its id.

        Idempotent by ``exp.idempotency_key`` (UNIQUE): if an experiment with the
        same key already exists, its id is returned and NO duplicate is written.
        Otherwise the parent row + all child rows (changes, protected behaviours,
        test protocol, recommendation-time evidence) + the creation state-history
        row are written in ONE transaction — a failed child write rolls back the
        WHOLE experiment (never a partial record). Returns None on error or when
        the experiment fails validation (e.g. not actionable / no scope)."""
        import json as _json
        try:
            from strategy.setup_experiment import validate_experiment
            v = validate_experiment(exp)
            if not v.ok:
                return None
        except Exception:
            return None
        try:
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            with self._lock:
                existing = self._conn.execute(
                    "SELECT id FROM setup_experiments WHERE idempotency_key = ?",
                    (exp.idempotency_key,)).fetchone()
                if existing is not None:
                    return int(existing[0])
                try:
                    self._conn.execute("BEGIN")
                    cur = self._conn.execute(
                        """INSERT INTO setup_experiments
                           (schema_version, scope_fingerprint, context_fingerprint,
                            context_schema_version, context_status,
                            context_unresolved_json, context_warnings_json, label,
                            recommendation_source, recommendation_status,
                            rule_engine_version, driver_profile_version,
                            parent_setup_id, proposed_setup_id, applied_checkpoint_id,
                            lineage_id, session_id, run_id, status, hypothesis_json,
                            deferred_diagnoses_json, rollback_target,
                            idempotency_key, created_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (exp.schema_version, exp.scope_fingerprint,
                         exp.context_fingerprint, exp.context_schema_version,
                         exp.context_status,
                         _json.dumps(list(exp.context_unresolved)),
                         _json.dumps(list(exp.context_warnings)), exp.label,
                         exp.recommendation_source, exp.recommendation_status,
                         exp.rule_engine_version, exp.driver_profile_version,
                         exp.parent_setup_id, exp.proposed_setup_id,
                         exp.applied_checkpoint_id, str(exp.lineage_id or ""),
                         exp.session_id, exp.run_id, exp.status.value,
                         _json.dumps(exp.hypothesis.to_dict()),
                         _json.dumps(list(exp.deferred_diagnoses)),
                         exp.rollback_target, exp.idempotency_key, now))
                    eid = int(cur.lastrowid)
                    for c in exp.changes:
                        self._conn.execute(
                            """INSERT INTO setup_experiment_changes
                               (experiment_id, field, subsystem, from_value, to_value,
                                delta_direction, delta_magnitude, unit, rationale,
                                expected_effect, side_effects, contraindications_checked,
                                role, kind, change_order, rule_id, source_label,
                                symptom, risk_level, confidence_level)
                               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (eid, c.field, c.subsystem, c.from_value, c.to_value,
                             c.delta_direction, c.delta_magnitude, c.unit, c.rationale,
                             c.expected_effect, c.side_effects,
                             c.contraindications_checked, c.role.value,
                             c.kind.value if c.kind else None, c.order, c.rule_id,
                             c.source_label, c.symptom, c.risk_level, c.confidence_level))
                    for p in exp.protected_behaviours:
                        self._conn.execute(
                            """INSERT INTO setup_experiment_protected_behaviours
                               (experiment_id, description, field, source_evidence,
                                corners_json, baseline_confidence, regression_threshold)
                               VALUES (?,?,?,?,?,?,?)""",
                            (eid, p.description, p.field, p.source_evidence,
                             _json.dumps(list(p.corners)), p.baseline_confidence,
                             p.regression_threshold))
                    tp = exp.test_protocol
                    self._conn.execute(
                        """INSERT INTO setup_experiment_test_protocol
                           (experiment_id, min_clean_laps, preferred_clean_laps,
                            warmup_exclusion_laps, tyre_compound, fuel_state,
                            weather_assumption, target_corners_json, metrics_json,
                            driver_questions_json, success_criteria_json,
                            failure_criteria_json, confounders_json, rollback_target,
                            notes)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (eid, tp.min_clean_laps, tp.preferred_clean_laps,
                         tp.warmup_exclusion_laps, tp.tyre_compound, tp.fuel_state,
                         tp.weather_assumption, _json.dumps(list(tp.target_corners)),
                         _json.dumps(list(tp.metrics_to_observe)),
                         _json.dumps(list(tp.driver_questions)),
                         _json.dumps(list(tp.success_criteria)),
                         _json.dumps(list(tp.failure_criteria)),
                         _json.dumps(list(tp.confounders)), tp.rollback_target,
                         tp.notes))
                    for ev in exp.evidence:
                        self._conn.execute(
                            """INSERT INTO setup_experiment_evidence
                               (experiment_id, evidence_type, phase, source_table,
                                source_id, summary, confidence, provenance, corner,
                                lap, session_id, run_id, stance, created_at)
                               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (eid, ev.evidence_type, ev.phase.value, ev.source_table,
                             ev.source_id, ev.summary, ev.confidence, ev.provenance,
                             ev.corner, ev.lap, ev.session_id, ev.run_id,
                             ev.stance.value, now))
                    self._conn.execute(
                        """INSERT INTO setup_experiment_state_history
                           (experiment_id, from_status, to_status, reason, source,
                            created_at)
                           VALUES (?,?,?,?,?,?)""",
                        (eid, "", exp.status.value, "experiment created",
                         exp.recommendation_source, now))
                    self._conn.execute("COMMIT")
                    return eid
                except Exception:
                    try:
                        self._conn.execute("ROLLBACK")
                    except Exception:
                        pass
                    return None
        except Exception:
            return None

    def _experiment_row(self, experiment_id: int) -> "dict | None":
        row = self._conn.execute(
            "SELECT * FROM setup_experiments WHERE id = ?",
            (int(experiment_id),)).fetchone()
        return dict(row) if row is not None else None

    def get_setup_experiment(self, experiment_id: int) -> "dict | None":
        """Return a full experiment (parent + changes + protected + protocol +
        evidence + state history), or None."""
        try:
            with self._lock:
                parent = self._experiment_row(experiment_id)
                if parent is None:
                    return None
                eid = int(experiment_id)
                parent["changes"] = [dict(r) for r in self._conn.execute(
                    "SELECT * FROM setup_experiment_changes WHERE experiment_id=? "
                    "ORDER BY change_order ASC, id ASC", (eid,)).fetchall()]
                parent["protected_behaviours"] = [dict(r) for r in self._conn.execute(
                    "SELECT * FROM setup_experiment_protected_behaviours "
                    "WHERE experiment_id=? ORDER BY id ASC", (eid,)).fetchall()]
                pr = self._conn.execute(
                    "SELECT * FROM setup_experiment_test_protocol WHERE experiment_id=?",
                    (eid,)).fetchone()
                parent["test_protocol"] = dict(pr) if pr is not None else None
                parent["evidence"] = [dict(r) for r in self._conn.execute(
                    "SELECT * FROM setup_experiment_evidence WHERE experiment_id=? "
                    "ORDER BY id ASC", (eid,)).fetchall()]
                parent["state_history"] = [dict(r) for r in self._conn.execute(
                    "SELECT * FROM setup_experiment_state_history WHERE experiment_id=? "
                    "ORDER BY id ASC", (eid,)).fetchall()]
            return parent
        except Exception:
            return None

    def get_setup_experiment_by_idempotency_key(self, key: str) -> "dict | None":
        try:
            with self._lock:
                row = self._conn.execute(
                    "SELECT id FROM setup_experiments WHERE idempotency_key=?",
                    (str(key),)).fetchone()
            return self.get_setup_experiment(int(row[0])) if row is not None else None
        except Exception:
            return None

    def _list_experiments_where(self, where: str, params: tuple) -> list[dict]:
        try:
            with self._lock:
                rows = self._conn.execute(
                    f"SELECT * FROM setup_experiments WHERE {where} "
                    "ORDER BY id DESC", params).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def list_setup_experiments_by_scope(self, scope_fingerprint: str) -> list[dict]:
        return self._list_experiments_where(
            "scope_fingerprint = ?", (str(scope_fingerprint),))

    def list_setup_experiments_by_parent_setup(self, parent_setup_id: str) -> list[dict]:
        return self._list_experiments_where(
            "parent_setup_id = ?", (str(parent_setup_id),))

    def list_setup_experiments_by_lineage(self, lineage_id) -> list[dict]:
        return self._list_experiments_where("lineage_id = ?", (str(lineage_id or ""),))

    def list_setup_experiments_by_checkpoint(self, checkpoint_id: str) -> list[dict]:
        return self._list_experiments_where(
            "applied_checkpoint_id = ?", (str(checkpoint_id),))

    def list_setup_experiments_by_session(self, session_id) -> list[dict]:
        return self._list_experiments_where("session_id = ?", (str(session_id or ""),))

    def get_experiment_state_history(self, experiment_id: int) -> list[dict]:
        try:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT * FROM setup_experiment_state_history WHERE experiment_id=? "
                    "ORDER BY id ASC", (int(experiment_id),)).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def get_experiment_evidence(self, experiment_id: int,
                                phase: str = "") -> list[dict]:
        try:
            with self._lock:
                if phase:
                    rows = self._conn.execute(
                        "SELECT * FROM setup_experiment_evidence WHERE experiment_id=? "
                        "AND phase=? ORDER BY id ASC",
                        (int(experiment_id), str(phase))).fetchall()
                else:
                    rows = self._conn.execute(
                        "SELECT * FROM setup_experiment_evidence WHERE experiment_id=? "
                        "ORDER BY id ASC", (int(experiment_id),)).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def append_experiment_evidence(self, experiment_id: int, evidence) -> "int | None":
        """Append ONE evidence record (append-only ledger). ``evidence`` is an
        ExperimentEvidence (duck-typed). Returns the new row id, or None."""
        try:
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            with self._lock:
                if self._experiment_row(experiment_id) is None:
                    return None
                phase = getattr(evidence.phase, "value", evidence.phase)
                stance = getattr(evidence.stance, "value", evidence.stance)
                cur = self._conn.execute(
                    """INSERT INTO setup_experiment_evidence
                       (experiment_id, evidence_type, phase, source_table, source_id,
                        summary, confidence, provenance, corner, lap, session_id,
                        run_id, stance, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (int(experiment_id), evidence.evidence_type, str(phase),
                     evidence.source_table, evidence.source_id, evidence.summary,
                     evidence.confidence, evidence.provenance, evidence.corner,
                     evidence.lap, evidence.session_id, evidence.run_id,
                     str(stance), now))
                self._conn.commit()
                return int(cur.lastrowid)
        except Exception:
            return None

    def _experiment_gate_state(self, experiment_id: int) -> dict:
        """Compute the honest transition-gate predicates from stored DB state
        (callers cannot fake them). Assumes the lock is already held."""
        eid = int(experiment_id)
        row = self._experiment_row(eid)
        if row is None:
            return {}
        n_changes = self._conn.execute(
            "SELECT COUNT(*) FROM setup_experiment_changes WHERE experiment_id=? "
            "AND role IN ('primary','supporting')", (eid,)).fetchone()[0]
        n_test = self._conn.execute(
            "SELECT COUNT(*) FROM setup_experiment_evidence WHERE experiment_id=? "
            "AND phase IN ('test','driver_review')", (eid,)).fetchone()[0]
        # Phase 3: COMPLETED is honestly gated on a persisted (non-invalidated,
        # non-superseded) outcome record actually existing for this experiment.
        try:
            n_outcome = self._conn.execute(
                "SELECT COUNT(*) FROM setup_experiment_outcomes WHERE experiment_id=? "
                "AND superseded_by IS NULL AND invalidated_reason=''", (eid,)).fetchone()[0]
        except Exception:
            n_outcome = 0
        return {
            "status": row.get("status", ""),
            "has_actionable_changes": n_changes > 0,
            "has_applied_checkpoint": bool(row.get("applied_checkpoint_id")),
            "has_test_evidence": n_test > 0,
            "has_outcome_record": n_outcome > 0,
        }

    def transition_experiment_state(
        self, experiment_id: int, to_status: str, *, reason: str = "",
        source: str = "admin",
    ) -> bool:
        """Validate + apply a deterministic lifecycle transition, appending a
        state-history row. Gate predicates are computed from stored DB state, so
        an APPLIED/READY_FOR_REVIEW/COMPLETED transition cannot be faked. Returns
        True on success, False if the transition is not permitted."""
        try:
            from strategy.setup_experiment import (
                ExperimentStatus, validate_transition)
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            with self._lock:
                gate = self._experiment_gate_state(experiment_id)
                if not gate:
                    return False
                try:
                    frm = ExperimentStatus(gate["status"])
                    to = ExperimentStatus(str(to_status))
                except ValueError:
                    return False
                chk = validate_transition(
                    frm, to,
                    has_actionable_changes=gate["has_actionable_changes"],
                    has_applied_checkpoint=gate["has_applied_checkpoint"],
                    has_test_evidence=gate["has_test_evidence"],
                    has_outcome_record=gate["has_outcome_record"])
                if not chk.ok:
                    return False
                self._conn.execute(
                    "UPDATE setup_experiments SET status=? WHERE id=?",
                    (to.value, int(experiment_id)))
                self._conn.execute(
                    """INSERT INTO setup_experiment_state_history
                       (experiment_id, from_status, to_status, reason, source, created_at)
                       VALUES (?,?,?,?,?,?)""",
                    (int(experiment_id), frm.value, to.value,
                     reason or chk.reason, source, now))
                self._conn.commit()
                return True
        except Exception:
            return False

    def find_applyable_experiment_for_scope(
        self, scope_fingerprint: str, parent_setup_id: str = "",
    ) -> "dict | None":
        """Return the most-recent experiment for a scope that is awaiting apply
        (DRAFT or READY_FOR_APPLY), optionally constrained to a parent setup, or
        None. Used by the Apply boundary to find which experiment to link."""
        try:
            with self._lock:
                if parent_setup_id:
                    row = self._conn.execute(
                        """SELECT * FROM setup_experiments
                           WHERE scope_fingerprint=? AND parent_setup_id=?
                             AND status IN ('draft','ready_for_apply')
                           ORDER BY id DESC LIMIT 1""",
                        (str(scope_fingerprint), str(parent_setup_id))).fetchone()
                else:
                    row = self._conn.execute(
                        """SELECT * FROM setup_experiments
                           WHERE scope_fingerprint=?
                             AND status IN ('draft','ready_for_apply')
                           ORDER BY id DESC LIMIT 1""",
                        (str(scope_fingerprint),)).fetchone()
            return dict(row) if row is not None else None
        except Exception:
            return None

    def _experiment_proposed_values(self, experiment_id: int) -> dict:
        """{field: to_value} for the actionable changes. Assumes lock held."""
        rows = self._conn.execute(
            "SELECT field, to_value FROM setup_experiment_changes "
            "WHERE experiment_id=? AND role IN ('primary','supporting')",
            (int(experiment_id),)).fetchall()
        return {r[0]: r[1] for r in rows if r[1] is not None}

    def link_experiment_applied_checkpoint(
        self, experiment_id: int, checkpoint_id: str, applied_fields: dict, *,
        reason: str = "confirmed applied in GT7", source: str = "apply",
    ) -> "dict | None":
        """Link an applied-setup checkpoint to an experiment and transition it to
        APPLIED. Computes the deterministic proposed-vs-applied comparison and
        stores it (applied_match_state + comparison JSON) WITHOUT altering the
        original recommendation. Idempotent: re-linking the SAME checkpoint_id is a
        no-op that returns the stored comparison. Returns a dict with the match
        state + comparison, or None on error / invalid transition."""
        import json as _json
        try:
            from strategy.setup_experiment import compare_proposed_vs_applied
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            with self._lock:
                row = self._experiment_row(experiment_id)
                if row is None:
                    return None
                # Idempotency: same checkpoint already linked → return stored result.
                if (row.get("applied_checkpoint_id") == str(checkpoint_id)
                        and row.get("applied_match_state")):
                    try:
                        cmp = _json.loads(row.get("applied_comparison_json") or "{}")
                    except Exception:
                        cmp = {}
                    return {"match_state": row.get("applied_match_state"),
                            "comparison": cmp, "already_linked": True}
                proposed = self._experiment_proposed_values(experiment_id)
                comparison = compare_proposed_vs_applied(proposed, applied_fields or {})
                gate = self._experiment_gate_state(experiment_id)
                # Only DRAFT / READY_FOR_APPLY may transition to APPLIED.
                if gate.get("status") not in ("draft", "ready_for_apply"):
                    # Still record the checkpoint + comparison for provenance, but
                    # do not force an illegal state change.
                    self._conn.execute(
                        "UPDATE setup_experiments SET applied_checkpoint_id=?, "
                        "applied_match_state=?, applied_comparison_json=? WHERE id=?",
                        (str(checkpoint_id), comparison.state.value,
                         _json.dumps(comparison.to_dict()), int(experiment_id)))
                    self._conn.commit()
                    return {"match_state": comparison.state.value,
                            "comparison": comparison.to_dict(),
                            "state_changed": False}
                try:
                    self._conn.execute("BEGIN")
                    self._conn.execute(
                        "UPDATE setup_experiments SET applied_checkpoint_id=?, "
                        "status='applied', applied_match_state=?, "
                        "applied_comparison_json=? WHERE id=?",
                        (str(checkpoint_id), comparison.state.value,
                         _json.dumps(comparison.to_dict()), int(experiment_id)))
                    self._conn.execute(
                        """INSERT INTO setup_experiment_state_history
                           (experiment_id, from_status, to_status, reason, source,
                            created_at)
                           VALUES (?,?,?,?,?,?)""",
                        (int(experiment_id), gate.get("status", ""), "applied",
                         reason, source, now))
                    self._conn.execute("COMMIT")
                except Exception:
                    try:
                        self._conn.execute("ROLLBACK")
                    except Exception:
                        pass
                    return None
                return {"match_state": comparison.state.value,
                        "comparison": comparison.to_dict(), "state_changed": True}
        except Exception:
            return None

    def invalidate_setup_experiment(self, experiment_id: int, reason: str) -> bool:
        """Administratively invalidate an experiment (append-only; never mutates
        the original hypothesis/changes/evidence)."""
        return self.transition_experiment_state(
            experiment_id, "invalid", reason=reason or "invalidated", source="admin")

    def cancel_setup_experiment(self, experiment_id: int, reason: str) -> bool:
        """Administratively cancel an experiment before completion."""
        return self.transition_experiment_state(
            experiment_id, "cancelled", reason=reason or "cancelled", source="admin")

    def record_recommendation_experiment(
        self, data: dict, *, recommendation_source: str = "analyse",
        car_id=None, track: str = "", layout_id: str = "", discipline: str = "",
        parent_setup_id: str = "", proposed_setup_id: str = "", lineage_id="",
        session_id=None, driver_id=None, gt7_version=None, event_id=None,
        config_id: str = "", label: str = "",
    ) -> "int | None":
        """Orchestration seam for the Setup Builder Analyse path: build a
        SetupExperiment from a parsed recommendation ``data`` dict (source-of-truth
        JSON, NOT rendered HTML) and persist it idempotently.

        Returns the experiment id (existing or new — duplicate rendering/reopen
        does not create a second experiment), or None when the recommendation is
        NOT a valid actionable experiment (blocked/empty/evidence-required). The
        experiment references the Phase 1 canonical scope_fingerprint. Best-effort;
        never raises outward."""
        try:
            from strategy.setup_experiment import build_experiment_from_recommendation
            exp = build_experiment_from_recommendation(
                data, recommendation_source=recommendation_source, car_id=car_id,
                track=track, layout_id=layout_id, discipline=discipline,
                driver_id=driver_id, gt7_version=gt7_version, event_id=event_id,
                config_id=config_id, parent_setup_id=parent_setup_id,
                proposed_setup_id=proposed_setup_id, lineage_id=lineage_id,
                session_id=session_id, label=label)
            if exp is None:
                return None
            return self.create_setup_experiment(exp)
        except Exception:
            return None

    def link_apply_to_experiment(
        self, *, car_id=None, track: str = "", layout_id: str = "",
        discipline: str = "", driver_id=None, gt7_version=None,
        parent_setup_id: str = "", checkpoint_id: str = "",
        applied_fields: dict = None,
    ) -> "dict | None":
        """Orchestration seam for the Apply-in-GT7 path: resolve the Phase 1
        scope_fingerprint from the same identity inputs used at analyse time, find
        the experiment for that scope awaiting apply, and link the applied
        checkpoint (transition → APPLIED + proposed-vs-applied comparison).

        Returns the comparison dict (with the linked experiment id), or None when
        there is no applyable experiment for the scope. Best-effort; never raises."""
        try:
            from data.engineering_context_key import build_engineering_context
            res = build_engineering_context(
                car_id=car_id, free_text_track=track, layout_id=layout_id,
                discipline=discipline, driver_id=driver_id, gt7_version=gt7_version)
            scope_fp = res.scope_fingerprint
            exp = self.find_applyable_experiment_for_scope(scope_fp, parent_setup_id)
            if exp is None and parent_setup_id:
                # Fall back to any applyable experiment in the scope (the parent
                # label may differ from the recommendation's parent).
                exp = self.find_applyable_experiment_for_scope(scope_fp, "")
            if exp is None:
                # Idempotency: a duplicate Apply of the SAME checkpoint finds the
                # already-applied experiment (no longer DRAFT/READY) by checkpoint.
                for row in self.list_setup_experiments_by_checkpoint(str(checkpoint_id)):
                    if row.get("scope_fingerprint") == scope_fp:
                        exp = row
                        break
            if exp is None:
                return None
            result = self.link_experiment_applied_checkpoint(
                int(exp["id"]), str(checkpoint_id), applied_fields or {})
            if isinstance(result, dict):
                result = dict(result)
                result["experiment_id"] = int(exp["id"])
            return result
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Setup experiment OUTCOMES + failed-direction learning (Phase 3, v22)
    # ------------------------------------------------------------------
    def create_experiment_outcome(
        self, outcome, *, car: str = "", track: str = "", layout_id: str = "",
        discipline: str = "", driver: str = "", rule_engine_version: str = "",
    ) -> "int | None":
        """Persist a SetupExperimentOutcome atomically + idempotently. Returns id.

        Idempotent by ``outcome.idempotency_key`` (UNIQUE): re-evaluating the same
        experiment against the same evidence returns the existing id and writes NO
        duplicate. The parent outcome + all child rows (criteria, protected,
        corners, failed_directions) are written in ONE transaction — a failed
        child write rolls back the WHOLE outcome (never a partial record). The
        outcome is IMMUTABLE once written. Best-effort; None on error."""
        import json as _json
        try:
            key = outcome.idempotency_key
            if not key:
                return None
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            with self._lock:
                existing = self._conn.execute(
                    "SELECT id FROM setup_experiment_outcomes WHERE idempotency_key=?",
                    (key,)).fetchone()
                if existing is not None:
                    return int(existing[0])
                try:
                    self._conn.execute("BEGIN")
                    cur = self._conn.execute(
                        """INSERT INTO setup_experiment_outcomes
                           (experiment_id, scope_fingerprint, parent_setup_id,
                            applied_checkpoint_id, test_session_id, test_run_id,
                            eval_version, status, confidence, confidence_level,
                            evidence_completeness, validity_json, whole_lap_json,
                            regressions_json, improvements_json, neutral_json,
                            confounders_json, missing_evidence_json, driver_agreement,
                            driver_review_summary, decision_rationale, next_action,
                            next_action_detail, rollback_eligible, rollback_target,
                            learning_eligible, idempotency_key, created_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (int(outcome.experiment_id), outcome.scope_fingerprint,
                         outcome.parent_setup_id, outcome.applied_checkpoint_id,
                         outcome.test_session_id, outcome.test_run_id,
                         outcome.eval_version, outcome.status.value,
                         float(outcome.confidence), outcome.confidence_level.value,
                         outcome.evidence_completeness,
                         _json.dumps(outcome.validity.to_dict()),
                         _json.dumps(outcome.whole_lap.to_dict()),
                         _json.dumps(list(outcome.regressions)),
                         _json.dumps(list(outcome.improvements)),
                         _json.dumps(list(outcome.neutral_findings)),
                         _json.dumps(list(outcome.confounders)),
                         _json.dumps(list(outcome.missing_evidence)),
                         outcome.driver_agreement.value, outcome.driver_review_summary,
                         outcome.decision_rationale, outcome.next_action.value,
                         outcome.next_action_detail, 1 if outcome.rollback_eligible else 0,
                         outcome.rollback_target, 1 if outcome.learning_eligible else 0,
                         key, now))
                    oid = int(cur.lastrowid)
                    for c in outcome.criteria:
                        self._conn.execute(
                            """INSERT INTO setup_experiment_outcome_criteria
                               (outcome_id, criterion_id, description, metric, expected,
                                observed, sample_count, confidence, verdict,
                                missing_evidence, rationale, is_target)
                               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (oid, c.criterion_id, c.description, c.metric, c.expected,
                             c.observed, int(c.sample_count), c.confidence,
                             c.verdict.value, c.missing_evidence, c.rationale,
                             1 if c.is_target else 0))
                    for p in outcome.protected:
                        self._conn.execute(
                            """INSERT INTO setup_experiment_outcome_protected
                               (outcome_id, behaviour, field, baseline_state, test_state,
                                comparison, confidence, verdict, supporting_evidence,
                                corners_json)
                               VALUES (?,?,?,?,?,?,?,?,?,?)""",
                            (oid, p.behaviour, p.field, p.baseline_state, p.test_state,
                             p.comparison, p.confidence, p.verdict.value,
                             p.supporting_evidence, _json.dumps(list(p.corners))))
                    for cc in outcome.corner_comparisons:
                        self._conn.execute(
                            """INSERT INTO setup_experiment_outcome_corners
                               (outcome_id, segment_id, corner_name, issue_type, phase,
                                baseline_class, test_class, baseline_affected,
                                test_affected, sample_count, confidence, verdict,
                                is_target, is_protected)
                               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (oid, cc.segment_id, cc.corner_name, cc.issue_type, cc.phase,
                             cc.baseline_class, cc.test_class, int(cc.baseline_affected),
                             int(cc.test_affected), int(cc.sample_count), cc.confidence,
                             cc.verdict.value, 1 if cc.is_target else 0,
                             1 if cc.is_protected else 0))
                    for fd in outcome.failed_directions:
                        self._conn.execute(
                            """INSERT INTO setup_experiment_failed_directions
                               (outcome_id, experiment_id, scope_fingerprint, driver,
                                car, track, layout_id, discipline, parent_setup_id,
                                field, from_value, to_value, direction, magnitude,
                                symptom, regression_observed, affected_protected,
                                corners_json, strength, confidence,
                                attribution_confidence, evidence_count, rule_id,
                                rule_engine_version, created_at)
                               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (oid, int(outcome.experiment_id), outcome.scope_fingerprint,
                             driver, car, track, layout_id, discipline,
                             outcome.parent_setup_id, fd.field, fd.from_value,
                             fd.to_value, fd.direction, fd.magnitude, fd.symptom,
                             fd.regression_observed, fd.affected_protected,
                             _json.dumps(list(fd.corners)), fd.strength.value,
                             fd.confidence, fd.attribution_confidence,
                             int(fd.evidence_count), fd.rule_id, rule_engine_version,
                             now))
                    self._conn.execute("COMMIT")
                    return oid
                except Exception:
                    try:
                        self._conn.execute("ROLLBACK")
                    except Exception:
                        pass
                    return None
        except Exception:
            return None

    def get_experiment_outcome(self, outcome_id: int) -> "dict | None":
        """Return a full outcome (parent + criteria + protected + corners +
        failed_directions), or None."""
        try:
            with self._lock:
                row = self._conn.execute(
                    "SELECT * FROM setup_experiment_outcomes WHERE id=?",
                    (int(outcome_id),)).fetchone()
                if row is None:
                    return None
                oid = int(outcome_id)
                out = dict(row)
                out["criteria"] = [dict(r) for r in self._conn.execute(
                    "SELECT * FROM setup_experiment_outcome_criteria WHERE outcome_id=? "
                    "ORDER BY id ASC", (oid,)).fetchall()]
                out["protected"] = [dict(r) for r in self._conn.execute(
                    "SELECT * FROM setup_experiment_outcome_protected WHERE outcome_id=? "
                    "ORDER BY id ASC", (oid,)).fetchall()]
                out["corners"] = [dict(r) for r in self._conn.execute(
                    "SELECT * FROM setup_experiment_outcome_corners WHERE outcome_id=? "
                    "ORDER BY id ASC", (oid,)).fetchall()]
                out["failed_directions"] = [dict(r) for r in self._conn.execute(
                    "SELECT * FROM setup_experiment_failed_directions WHERE outcome_id=? "
                    "ORDER BY id ASC", (oid,)).fetchall()]
            return out
        except Exception:
            return None

    def get_latest_experiment_outcome(self, experiment_id: int) -> "dict | None":
        """Return the most-recent non-superseded, non-invalidated outcome, or None."""
        try:
            with self._lock:
                row = self._conn.execute(
                    "SELECT id FROM setup_experiment_outcomes WHERE experiment_id=? "
                    "AND superseded_by IS NULL AND invalidated_reason='' "
                    "ORDER BY id DESC LIMIT 1", (int(experiment_id),)).fetchone()
            return self.get_experiment_outcome(int(row[0])) if row is not None else None
        except Exception:
            return None

    def list_experiment_outcomes(self, experiment_id: int) -> list[dict]:
        """All outcomes for an experiment (incl. superseded), newest first."""
        try:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT * FROM setup_experiment_outcomes WHERE experiment_id=? "
                    "ORDER BY id DESC", (int(experiment_id),)).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def supersede_experiment_outcome(self, old_outcome_id: int,
                                     new_outcome_id: int) -> None:
        """Audited superseding — points the prior outcome at its replacement
        WITHOUT deleting or mutating the historical conclusion. Best-effort."""
        try:
            with self._lock:
                self._conn.execute(
                    "UPDATE setup_experiment_outcomes SET superseded_by=? WHERE id=?",
                    (int(new_outcome_id), int(old_outcome_id)))
                self._conn.commit()
        except Exception:
            pass

    def invalidate_experiment_outcome(self, outcome_id: int, reason: str) -> None:
        """Audited invalidation (records a reason; never erases the row)."""
        try:
            with self._lock:
                self._conn.execute(
                    "UPDATE setup_experiment_outcomes SET invalidated_reason=? WHERE id=?",
                    (str(reason or "invalidated"), int(outcome_id)))
                self._conn.commit()
        except Exception:
            pass

    def list_failed_directions_by_scope(self, scope_fingerprint: str) -> list[dict]:
        """Scoped failed-direction learning (lockout/caution), newest first."""
        try:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT * FROM setup_experiment_failed_directions "
                    "WHERE scope_fingerprint=? AND superseded_by IS NULL "
                    "ORDER BY id DESC", (str(scope_fingerprint),)).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def list_failed_directions_for_field(
        self, car: str, track: str, layout_id: str, field: str,
    ) -> list[dict]:
        """Failed-direction learning for a specific field within one car/track/layout
        scope only (never cross-car/cross-track). Newest first."""
        try:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT * FROM setup_experiment_failed_directions "
                    "WHERE car=? AND track=? AND layout_id=? AND field=? "
                    "AND superseded_by IS NULL ORDER BY id DESC",
                    (str(car), str(track), str(layout_id), str(field))).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def evaluate_setup_experiment(
        self, experiment_id: int, *,
        test_session_id=None, baseline_session_id=None,
        corner_baseline=None, corner_test=None, driver_review=None,
        confounders=None, test_scope_fingerprint=None, test_checkpoint_id=None,
        test_session_started_after_apply: bool = True,
        candidate_experiment_ids=(), complete_on_success: bool = True,
        car: str = "", track: str = "", layout_id: str = "", discipline: str = "",
        driver: str = "", force: bool = False,
    ) -> dict:
        """High-level Phase-3 orchestration: evaluate one applied experiment against
        measured test evidence, persist an immutable outcome + failed-direction
        learning, drive the Phase-2 lifecycle, and feed the EXISTING lockout/lineage
        consumers. Structured result; never raises for ordinary missing-evidence.

        Evidence is gathered from the DB (clean-lap windows via the OFR-1 authority
        `aggregate_lap_window`) for the given baseline/test sessions; per-corner
        observations + the deterministically-parsed driver review are passed in by
        the caller (the Setup Builder/Practice worker) so this method stays pure of
        telemetry threading. Runs OFF the telemetry UDP thread by contract."""
        try:
            from strategy.setup_experiment_outcome import (
                ExperimentSnapshot, OutcomeInputs, LapAggregate, ConfounderInput,
                resolve_experiment_evidence_association, evaluate_lap_validity,
                evaluate_outcome, OutcomeStatus,
            )
            from data.recommendation_scoring import aggregate_lap_window
            from strategy._setup_constants import RULE_ENGINE_VERSION
        except Exception as exc:  # pragma: no cover - import/infrastructure failure
            return {"ok": False, "error": f"phase3 import failed: {exc}"}

        exp = self.get_setup_experiment(int(experiment_id))
        if exp is None:
            return {"ok": False, "status": "insufficient_evidence",
                    "reason": "experiment not found"}
        if exp.get("status") not in ("applied", "test_in_progress", "ready_for_review"):
            return {"ok": False, "status": "insufficient_evidence",
                    "reason": f"experiment not evaluable in state {exp.get('status')!r}"}

        snap = ExperimentSnapshot.from_experiment(exp)

        # --- gather clean-lap windows from the DB (OFR-1 authority) ----------
        def _agg(session_id):
            if session_id is None:
                return LapAggregate(), 0
            rows = self.get_laps_for_scoring(int(session_id))
            w = aggregate_lap_window(rows)
            return LapAggregate.from_lap_window(w, rows), len(rows)

        test_agg, test_total = _agg(test_session_id)
        base_agg, _ = _agg(baseline_session_id)
        has_parent_baseline = (baseline_session_id is not None) or base_agg.clean_count > 0

        # --- authoritative association --------------------------------------
        assoc = resolve_experiment_evidence_association(
            snap,
            test_scope_fingerprint=(test_scope_fingerprint
                                    if test_scope_fingerprint is not None
                                    else snap.scope_fingerprint),
            test_checkpoint_id=(test_checkpoint_id or ""),
            test_session_started_after_apply=test_session_started_after_apply,
            candidate_experiment_ids=candidate_experiment_ids,
            has_parent_baseline=has_parent_baseline)

        min_req = snap.min_clean_laps or 3
        validity = evaluate_lap_validity(
            test_agg, total_laps=test_total, min_required=min_req,
            setup_identity_confidence=("high" if not (confounders and getattr(
                confounders, "setup_identity_uncertain", False)) else "low"))

        inputs = OutcomeInputs(
            experiment=snap, association=assoc, validity=validity,
            baseline=base_agg, test=test_agg,
            corner_baseline=tuple(corner_baseline or ()),
            corner_test=tuple(corner_test or ()),
            driver_review=driver_review,
            confounders=confounders or ConfounderInput(),
            test_session_id=(str(test_session_id) if test_session_id is not None else None))

        outcome = evaluate_outcome(inputs)

        # --- persist immutable outcome (atomic) -----------------------------
        prior = self.get_latest_experiment_outcome(int(experiment_id))
        outcome_id = self.create_experiment_outcome(
            outcome, car=car, track=track, layout_id=layout_id,
            discipline=discipline, driver=driver,
            rule_engine_version=RULE_ENGINE_VERSION)
        if outcome_id is None:
            return {"ok": False, "status": outcome.status.value,
                    "reason": "outcome persistence failed"}
        # Audited superseding: a genuinely-new evaluation supersedes the prior one.
        if prior is not None and int(prior.get("id")) != outcome_id:
            self.supersede_experiment_outcome(int(prior["id"]), outcome_id)

        # --- attach evidence to the Phase-2 append-only ledger --------------
        self._attach_outcome_evidence(int(experiment_id), outcome, test_session_id,
                                      driver_review)

        # --- drive the Phase-2 lifecycle (validated, append-only) -----------
        transitioned = self._advance_experiment_lifecycle(
            int(experiment_id), outcome.status, complete_on_success)

        # --- feed EXISTING consumers for confirmed regressions --------------
        learning = self._record_failed_direction_learning(
            outcome, car=car, track=track, layout_id=layout_id,
            test_session_id=test_session_id)

        return {
            "ok": True,
            "experiment_id": int(experiment_id),
            "outcome_id": outcome_id,
            "status": outcome.status.value,
            "confidence": outcome.confidence,
            "confidence_level": outcome.confidence_level.value,
            "association": assoc.status.value,
            "valid_laps": validity.valid_laps,
            "next_action": outcome.next_action.value,
            "rollback_eligible": outcome.rollback_eligible,
            "rollback_target": outcome.rollback_target,
            "learning_eligible": outcome.learning_eligible,
            "failed_directions": [fd.to_dict() for fd in outcome.failed_directions],
            "regressions": list(outcome.regressions),
            "improvements": list(outcome.improvements),
            "lifecycle": transitioned,
            "learning_written": learning,
            "superseded_prior": (int(prior["id"]) if prior is not None
                                 and int(prior.get("id")) != outcome_id else None),
        }

    def find_latest_reviewable_experiment(
        self, car_id: int, track: str, layout_id: str = "", discipline: str = "",
    ) -> "dict | None":
        """Return the most-recent experiment awaiting outcome review (APPLIED /
        TEST_IN_PROGRESS / READY_FOR_REVIEW) for a scope, or None. Used by the
        driver-triggered 'Review Test Outcome' action. Resolves the Phase 1
        scope_fingerprint from the identity so it never matches on free-text."""
        try:
            from data.engineering_context_key import build_engineering_context
            res = build_engineering_context(
                car_id=car_id, free_text_track=track, layout_id=layout_id,
                discipline=discipline)
            scope_fp = res.scope_fingerprint
            with self._lock:
                row = self._conn.execute(
                    """SELECT * FROM setup_experiments
                       WHERE scope_fingerprint=?
                         AND status IN ('applied','test_in_progress','ready_for_review')
                       ORDER BY id DESC LIMIT 1""",
                    (scope_fp,)).fetchone()
            return dict(row) if row is not None else None
        except Exception:
            return None

    def _attach_outcome_evidence(self, experiment_id, outcome, test_session_id,
                                 driver_review) -> None:
        """Append TEST / DRIVER_REVIEW / OUTCOME evidence to the Phase-2 ledger
        (append-only; references + structured summaries, never blobs)."""
        try:
            from strategy.setup_experiment import (
                ExperimentEvidence, EvidencePhase, EvidenceStance)
            v = outcome.validity
            self.append_experiment_evidence(experiment_id, ExperimentEvidence(
                evidence_type="test_evidence", phase=EvidencePhase.TEST,
                source_table="lap_records",
                source_id=(str(test_session_id) if test_session_id is not None else ""),
                summary=(f"{v.valid_laps} valid / {v.rejected_laps} rejected laps; "
                         f"repeatability_assessable={v.repeatability_assessable}"),
                confidence=v.setup_identity_confidence,
                provenance="recommendation_scoring.aggregate_lap_window",
                session_id=(str(test_session_id) if test_session_id is not None else None),
                stance=EvidenceStance.NEUTRAL))
            if driver_review is not None:
                self.append_experiment_evidence(experiment_id, ExperimentEvidence(
                    evidence_type="driver_review", phase=EvidencePhase.DRIVER_REVIEW,
                    source_table="driver_feedback",
                    source_id=str(getattr(driver_review, "feedback_id", "") or ""),
                    summary=outcome.driver_review_summary,
                    provenance="setup_diagnosis._parse_driver_feel",
                    stance=(EvidenceStance.SUPPORTS
                            if getattr(driver_review, "refers_to_correct_setup", True)
                            else EvidenceStance.NEUTRAL)))
            self.append_experiment_evidence(experiment_id, ExperimentEvidence(
                evidence_type="outcome", phase=EvidencePhase.OUTCOME,
                source_table="setup_experiment_outcomes",
                summary=f"{outcome.status.value} (confidence {outcome.confidence}); "
                        f"next: {outcome.next_action.value}",
                confidence=outcome.confidence_level.value,
                provenance="setup_experiment_outcome.evaluate_outcome",
                stance=EvidenceStance.NEUTRAL))
        except Exception:
            pass

    def _advance_experiment_lifecycle(self, experiment_id, status,
                                      complete_on_success) -> list:
        """Drive APPLIED → TEST_IN_PROGRESS → READY_FOR_REVIEW → COMPLETED/REJECTED
        via the Phase-2 validated transitions (never bypasses validation; each step
        appends to the audited state history). Inconclusive outcomes stay in
        READY_FOR_REVIEW. Returns the ordered list of applied transitions."""
        applied = []
        try:
            from strategy.setup_experiment_outcome import OutcomeStatus

            def _cur():
                r = self._experiment_row(experiment_id) if hasattr(self, "_experiment_row") else None
                return (r or {}).get("status", "")

            # Advance to READY_FOR_REVIEW (test evidence now exists).
            if _cur() == "applied":
                if self.transition_experiment_state(
                        experiment_id, "test_in_progress", source="phase3"):
                    applied.append("test_in_progress")
            if _cur() in ("applied", "test_in_progress"):
                if self.transition_experiment_state(
                        experiment_id, "ready_for_review", source="phase3",
                        reason="Phase 3 evaluation attached test evidence"):
                    applied.append("ready_for_review")

            # Terminal transition by outcome (COMPLETED needs the persisted outcome,
            # which now exists → the gate passes honestly).
            if status in (OutcomeStatus.CONFIRMED_IMPROVEMENT,
                          OutcomeStatus.PARTIAL_IMPROVEMENT,
                          OutcomeStatus.NO_MEANINGFUL_CHANGE) and complete_on_success:
                if self.transition_experiment_state(
                        experiment_id, "completed", source="phase3",
                        reason=f"outcome={status.value}"):
                    applied.append("completed")
            elif status == OutcomeStatus.REGRESSION:
                if self.transition_experiment_state(
                        experiment_id, "rejected", source="phase3",
                        reason="confirmed regression"):
                    applied.append("rejected")
            # CONFOUNDED / INSUFFICIENT_EVIDENCE: remain in READY_FOR_REVIEW.
        except Exception:
            pass
        return applied

    def _record_failed_direction_learning(self, outcome, *, car, track, layout_id,
                                          test_session_id) -> dict:
        """Feed the EXISTING deterministic consumers so Phase 3 learning is not a
        competing engine: a LOCKOUT-strength failed direction writes a 'worsened'
        row to learning_outcomes (consumed by blocked_rules_from_outcomes) and
        stamps the latest lineage node 'worsened' (consumed by rollback_from_lineage).
        A CAUTION writes neither a hard block nor a lineage worsening — the
        setup_experiment_failed_directions row (already persisted) is the caution
        record. Never fires for non-regression / insufficient / confounded."""
        from strategy.setup_experiment_outcome import LearningStrength
        written = {"learning_outcomes": 0, "lineage": 0, "caution": 0}
        try:
            car_id = 0
            try:
                car_id = int(self.get_car_id(car) or 0) if car else 0
            except Exception:
                car_id = 0
            sess = int(test_session_id) if test_session_id is not None else 0
            for fd in outcome.failed_directions:
                if fd.strength == LearningStrength.LOCKOUT and fd.rule_id:
                    self.record_learning_outcome(
                        car_id, track, layout_id, sess, "", fd.rule_id,
                        "phase3_outcome", "worsened",
                        0.8 if fd.confidence == "high" else 0.6, "", "",
                        target_issue=fd.symptom,
                        evidence_summary=fd.regression_observed,
                        outcome_kind="failed_direction")
                    written["learning_outcomes"] += 1
                elif fd.strength == LearningStrength.CAUTION:
                    written["caution"] += 1
            # Stamp lineage 'worsened' once for a confirmed regression (rollback consumer).
            if any(fd.strength == LearningStrength.LOCKOUT
                   for fd in outcome.failed_directions):
                self.record_latest_lineage_outcome(
                    car_id, track, layout_id, "worsened",
                    outcome_session_id=(sess or None))
                written["lineage"] = 1
        except Exception:
            pass
        return written

    # ------------------------------------------------------------------
    # Canonical evidence assembly + live review (Phase 4)
    # ------------------------------------------------------------------
    def _checkpoint_scope_row(self, checkpoint_id: str) -> "dict | None":
        """Resolve car_id/track/layout for an applied checkpoint id. Assumes no lock."""
        try:
            with self._lock:
                row = self._conn.execute(
                    "SELECT car_id, track, layout_id, setup_id FROM "
                    "applied_setup_checkpoints WHERE checkpoint_id=? "
                    "ORDER BY id DESC LIMIT 1", (str(checkpoint_id),)).fetchone()
            return dict(row) if row is not None else None
        except Exception:
            return None

    def assemble_setup_experiment_evidence(
        self, experiment_id: int, *, test_session_id=None, baseline_session_id=None,
    ) -> dict:
        """Assemble canonical baseline/test evidence for a Phase-2 experiment in the
        EXACT form Phase 3 consumes — using the canonical lap-validity + per-corner
        authorities over persisted `corner_issue_occurrences` (checkpoint-tagged,
        session-keyed). Deterministic; never raises; never silently picks among
        equally plausible sessions (returns AMBIGUOUS). Does NOT decide the outcome."""
        try:
            from strategy.engineering_lap_validity import (
                evaluate_session_laps, LapPurpose)
            from strategy.corner_evidence import (
                from_issue_occurrence_row, to_phase3_observations)
            from strategy.setup_evidence_assembly import (
                SessionCandidate, select_test_session, select_baseline_session,
                summarise_valid_laps, SelectionStatus)
        except Exception as exc:  # pragma: no cover
            return {"ok": False, "error": f"phase4 import failed: {exc}"}

        exp = self.get_setup_experiment(int(experiment_id))
        if exp is None:
            return {"ok": False, "reason": "experiment not found"}
        applied_cp = str(exp.get("applied_checkpoint_id") or "")
        scope = str(exp.get("scope_fingerprint") or "")
        parent = str(exp.get("parent_setup_id") or "")
        if not applied_cp:
            return {"ok": False, "reason": "experiment has no applied checkpoint"}
        cp_scope = self._checkpoint_scope_row(applied_cp)
        if cp_scope is None:
            return {"ok": False, "reason": "applied checkpoint scope not resolvable"}
        car_id = int(cp_scope.get("car_id") or 0)
        track = str(cp_scope.get("track") or "")
        layout_id = str(cp_scope.get("layout_id") or "")

        # All occurrences for this physical scope; group per session + checkpoint set.
        occ_rows = self.get_issue_occurrences(car_id, track, layout_id)
        by_session: dict = {}
        cp_by_session: dict = {}
        for r in occ_rows:
            sid = str(r.get("session_id"))
            by_session.setdefault(sid, []).append(r)
            cp = str(r.get("setup_checkpoint_id") or "")
            if cp:
                cp_by_session.setdefault(sid, set()).add(cp)

        # Build candidate sessions with a canonical valid-lap count each.
        session_ids = set(by_session)
        for extra in (test_session_id, baseline_session_id):
            if extra is not None:
                session_ids.add(str(extra))
        candidates = []
        validity_by_session: dict = {}
        laps_by_session: dict = {}
        for sid in session_ids:
            laps = self.get_laps_for_scoring(int(sid)) if sid.isdigit() else []
            _, summ = evaluate_session_laps(
                laps, purpose=LapPurpose.OUTCOME_COMPARISON,
                scope_fingerprint=scope, expected_track=track)
            validity_by_session[sid] = summ
            laps_by_session[sid] = laps
            candidates.append(SessionCandidate(
                session_id=sid, checkpoint_ids=tuple(sorted(cp_by_session.get(sid, ()))),
                valid_lap_count=summ.usable_laps, track=track, layout_id=layout_id,
                scope_fingerprint=scope))

        test_sel = select_test_session(
            candidates, applied_checkpoint_id=applied_cp, scope_fingerprint=scope,
            explicit_session_id=(str(test_session_id) if test_session_id is not None else None))
        base_sel = select_baseline_session(
            candidates, applied_checkpoint_id=applied_cp,
            scope_fingerprint=scope,
            explicit_session_id=(str(baseline_session_id) if baseline_session_id is not None else None))

        def _corner_obs(sid, *, tag_checkpoint):
            if sid is None:
                return ()
            rows = by_session.get(str(sid), [])
            if tag_checkpoint:
                rows = [r for r in rows
                        if str(r.get("setup_checkpoint_id") or "") == applied_cp] or rows
            recs = [from_issue_occurrence_row(r, scope_fingerprint=scope,
                                              experiment_id=str(experiment_id))
                    for r in rows]
            summ = validity_by_session.get(str(sid))
            valid_nums = getattr(summ, "valid_lap_numbers", ()) if summ else ()
            total_valid = getattr(summ, "usable_laps", 0) if summ else 0
            return to_phase3_observations(recs, total_valid_laps=total_valid,
                                          valid_lap_numbers=valid_nums)

        corner_test = _corner_obs(test_sel.session_id, tag_checkpoint=True)
        corner_baseline = _corner_obs(base_sel.session_id, tag_checkpoint=False)

        def _summary(sid):
            if sid is None:
                return None
            summ = validity_by_session.get(str(sid))
            return summarise_valid_laps(
                laps_by_session.get(str(sid), []), summ,
                setup_identity_confidence="high", track_identity_confidence="high")

        missing = []
        if not test_sel.ok:
            missing.append(f"test evidence {test_sel.status.value}: "
                           + "; ".join(test_sel.reasons))
        if not base_sel.ok:
            missing.append(f"baseline evidence {base_sel.status.value}: "
                           + "; ".join(base_sel.reasons))
        if test_sel.ok and not corner_test:
            missing.append("no per-corner test evidence assembled")

        return {
            "ok": True, "experiment_id": int(experiment_id),
            "applied_checkpoint_id": applied_cp, "scope_fingerprint": scope,
            "car_id": car_id, "track": track, "layout_id": layout_id,
            "parent_setup_id": parent,
            "test_session_id": test_sel.session_id,
            "baseline_session_id": base_sel.session_id,
            "test_selection": test_sel.to_dict(),
            "baseline_selection": base_sel.to_dict(),
            "corner_test": corner_test, "corner_baseline": corner_baseline,
            "test_whole_lap": (_summary(test_sel.session_id) or None),
            "baseline_whole_lap": (_summary(base_sel.session_id) or None),
            "missing_evidence": missing,
        }

    def review_experiment_outcome(
        self, experiment_id: int, *, test_session_id=None, baseline_session_id=None,
        driver_review=None, confounders=None, complete_on_success: bool = True,
        driver: str = "",
    ) -> dict:
        """Production review path (Phase 4): assemble canonical per-corner evidence
        from persisted stores, then call the Phase-3 evaluator with it. This is what
        the off-thread 'Review Test Outcome' action calls — no test-only manual
        CornerObservation objects required. Never raises for missing evidence; an
        infrastructure failure is surfaced distinctly (never a fabricated verdict)."""
        assembled = self.assemble_setup_experiment_evidence(
            int(experiment_id), test_session_id=test_session_id,
            baseline_session_id=baseline_session_id)
        if not assembled.get("ok"):
            return {"ok": False, "phase": "assembly",
                    "reason": assembled.get("reason") or assembled.get("error"),
                    "assembly": assembled}
        car_name = ""
        try:
            with self._lock:
                crow = self._conn.execute(
                    "SELECT name FROM cars WHERE id=?",
                    (int(assembled["car_id"]),)).fetchone()
            car_name = str(crow[0]) if crow is not None else ""
        except Exception:
            car_name = ""
        result = self.evaluate_setup_experiment(
            int(experiment_id),
            test_session_id=assembled["test_session_id"],
            baseline_session_id=assembled["baseline_session_id"],
            corner_baseline=assembled["corner_baseline"],
            corner_test=assembled["corner_test"],
            driver_review=driver_review, confounders=confounders,
            test_checkpoint_id=assembled["applied_checkpoint_id"],
            car=car_name, track=assembled["track"],
            layout_id=assembled["layout_id"], driver=driver,
            complete_on_success=complete_on_success)
        if isinstance(result, dict):
            result = dict(result)
            result["assembly"] = {
                "test_selection": assembled["test_selection"],
                "baseline_selection": assembled["baseline_selection"],
                "missing_evidence": assembled["missing_evidence"],
                "test_whole_lap": (assembled["test_whole_lap"].to_dict()
                                   if assembled.get("test_whole_lap") else None),
                "baseline_whole_lap": (assembled["baseline_whole_lap"].to_dict()
                                       if assembled.get("baseline_whole_lap") else None),
                "corner_test_count": len(assembled["corner_test"]),
                "corner_baseline_count": len(assembled["corner_baseline"]),
            }
        return result

    # ------------------------------------------------------------------
    # Working-window learning + experiment selection (Phase 5, v23)
    # ------------------------------------------------------------------
    def _experiment_context_scope(self, experiment_id: int):
        """Resolve (WindowContextKey base + car_id/car) for an experiment from its
        applied checkpoint scope. Returns (exp_dict, scope_dict) or (None, None)."""
        exp = self.get_setup_experiment(int(experiment_id))
        if exp is None:
            return None, None
        cp = self._checkpoint_scope_row(str(exp.get("applied_checkpoint_id") or ""))
        car_id = int((cp or {}).get("car_id") or 0)
        car_name = ""
        try:
            with self._lock:
                crow = self._conn.execute(
                    "SELECT name FROM cars WHERE id=?", (car_id,)).fetchone()
            car_name = str(crow[0]) if crow is not None else ""
        except Exception:
            car_name = ""
        # discipline from the experiment's hypothesis/test protocol is not stored on
        # the row; derive from the checkpoint purpose where available.
        discipline = ""
        try:
            with self._lock:
                prow = self._conn.execute(
                    "SELECT purpose FROM applied_setup_checkpoints WHERE checkpoint_id=? "
                    "ORDER BY id DESC LIMIT 1",
                    (str(exp.get("applied_checkpoint_id") or ""),)).fetchone()
            discipline = str(prow[0]) if prow is not None else ""
        except Exception:
            discipline = ""
        return exp, {
            "car_id": car_id, "car": car_name,
            "track": str((cp or {}).get("track") or ""),
            "layout_id": str((cp or {}).get("layout_id") or ""),
            "discipline": discipline,
            "scope_fingerprint": str(exp.get("scope_fingerprint") or ""),
        }

    def learn_from_experiment_outcome(self, experiment_id: int) -> dict:
        """Phase 5 orchestrator: consume the experiment + its canonical Phase-3
        outcome, map to per-field window evidence, persist it (append-only,
        idempotent), and recompute the materialised learned windows. Only a
        completed, canonically-evaluated outcome teaches; confounded/insufficient
        contribute metadata only. Never raises; deterministic; idempotent replay."""
        try:
            from strategy.working_window import (
                WindowContextKey, outcome_to_window_evidence, recompute_working_window)
            from strategy.setup_ranges import resolve_ranges
        except Exception as exc:  # pragma: no cover
            return {"ok": False, "error": f"phase5 import failed: {exc}"}
        exp, scope = self._experiment_context_scope(int(experiment_id))
        if exp is None:
            return {"ok": False, "reason": "experiment not found"}
        outcome = self.get_latest_experiment_outcome(int(experiment_id))
        if outcome is None:
            return {"ok": False, "reason": "no persisted outcome to learn from"}
        base_ctx = WindowContextKey(
            scope_fingerprint=scope["scope_fingerprint"], car=scope["car"],
            track=scope["track"], layout_id=scope["layout_id"],
            discipline=scope["discipline"])
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        evidence = outcome_to_window_evidence(exp, outcome, context=base_ctx, created_at=now)
        try:
            ranges = resolve_ranges(scope["car"]) if scope["car"] else {}
        except Exception:
            ranges = {}
        updated_fields = []
        for ev in evidence:
            # persist evidence (append-only, idempotent by UNIQUE triple)
            self._record_window_evidence(ev, scope, now)
        # recompute each touched field's window from its full ledger
        touched = {ev.field for ev in evidence}
        for fld in sorted(touched):
            ctx = WindowContextKey(
                scope_fingerprint=base_ctx.scope_fingerprint, driver=base_ctx.driver,
                car=base_ctx.car, track=base_ctx.track, layout_id=base_ctx.layout_id,
                discipline=base_ctx.discipline, field=fld)
            rows = self._get_window_evidence(ctx.key())
            rng = ranges.get(fld)
            lo = hi = None
            if isinstance(rng, (tuple, list)) and len(rng) == 2:
                try:
                    lo, hi = float(rng[0]), float(rng[1])
                except (TypeError, ValueError):
                    lo = hi = None
            window = recompute_working_window(rows, ctx, legal_low=lo, legal_high=hi)
            self._upsert_working_window(window, scope, now)
            updated_fields.append(fld)
        return {"ok": True, "experiment_id": int(experiment_id),
                "outcome_status": str(outcome.get("status") or ""),
                "updated_fields": updated_fields,
                "contributions": [e.contribution.value for e in evidence]}

    def _record_window_evidence(self, ev, scope, now) -> None:
        import json as _json
        try:
            with self._lock:
                self._conn.execute(
                    """INSERT OR IGNORE INTO setup_working_window_evidence
                       (context_key, experiment_id, outcome_id, scope_fingerprint,
                        driver, car, track, layout_id, discipline, field, from_value,
                        to_value, direction, magnitude, outcome_status, contribution,
                        is_compound, attribution_confidence, symptom, corners_json,
                        checkpoint_id, session_id, is_direct, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (ev.context_key, ev.experiment_id, ev.outcome_id,
                     scope["scope_fingerprint"], "", scope["car"], scope["track"],
                     scope["layout_id"], scope["discipline"], ev.field, ev.from_value,
                     ev.to_value, ev.direction.value, ev.magnitude, ev.outcome_status,
                     ev.contribution.value, 1 if ev.is_compound else 0,
                     ev.attribution_confidence, ev.symptom,
                     _json.dumps(list(ev.corners)), ev.checkpoint_id, ev.session_id,
                     1 if ev.is_direct else 0, ev.created_at or now))
                self._conn.commit()
        except Exception:
            pass

    def _get_window_evidence(self, context_key: str) -> list:
        """Load a context's evidence ledger as WindowEvidence objects (source-of-truth)."""
        from strategy.working_window import (
            WindowEvidence, Direction, WindowContribution)
        import json as _json
        out = []
        try:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT * FROM setup_working_window_evidence WHERE context_key=? "
                    "ORDER BY id ASC", (str(context_key),)).fetchall()
            for r in rows:
                d = dict(r)
                try:
                    corners = tuple(_json.loads(d.get("corners_json") or "[]"))
                except Exception:
                    corners = ()
                try:
                    direction = Direction(d.get("direction") or "none")
                except ValueError:
                    direction = Direction.NONE
                try:
                    contrib = WindowContribution(d.get("contribution") or "none")
                except ValueError:
                    contrib = WindowContribution.NONE
                out.append(WindowEvidence(
                    context_key=d.get("context_key", ""),
                    experiment_id=d.get("experiment_id", ""),
                    outcome_id=d.get("outcome_id", ""), field=d.get("field", ""),
                    from_value=d.get("from_value"), to_value=d.get("to_value"),
                    direction=direction, magnitude=d.get("magnitude"),
                    outcome_status=d.get("outcome_status", ""), contribution=contrib,
                    is_compound=bool(d.get("is_compound")),
                    attribution_confidence=d.get("attribution_confidence", ""),
                    symptom=d.get("symptom", ""), corners=corners,
                    checkpoint_id=d.get("checkpoint_id", ""),
                    session_id=d.get("session_id", ""),
                    is_direct=bool(d.get("is_direct", 1)),
                    created_at=d.get("created_at", "")))
        except Exception:
            return []
        return out

    def _upsert_working_window(self, window, scope, now) -> None:
        import json as _json
        try:
            ctx = window.context
            with self._lock:
                self._conn.execute(
                    """INSERT INTO setup_working_windows
                       (context_key, scope_fingerprint, driver, car, track, layout_id,
                        discipline, field, window_json, confidence,
                        valid_experiment_count, improvement_count, regression_count,
                        updated_at, eval_version)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(context_key) DO UPDATE SET
                         window_json=excluded.window_json,
                         confidence=excluded.confidence,
                         valid_experiment_count=excluded.valid_experiment_count,
                         improvement_count=excluded.improvement_count,
                         regression_count=excluded.regression_count,
                         updated_at=excluded.updated_at""",
                    (ctx.key(), scope["scope_fingerprint"], "", scope["car"],
                     scope["track"], scope["layout_id"], scope["discipline"],
                     window.field, _json.dumps(window.to_dict()),
                     window.confidence.value, window.valid_experiment_count,
                     window.improvement_count, window.regression_count, now,
                     window.eval_version))
                self._conn.commit()
        except Exception:
            pass

    def get_working_window(self, scope_fingerprint: str, field: str, *,
                           car: str = "", track: str = "", layout_id: str = "",
                           discipline: str = "") -> "dict | None":
        """Return a learned window dict for a field in a context, or None."""
        from strategy.working_window import WindowContextKey
        ctx = WindowContextKey(scope_fingerprint=scope_fingerprint, car=car,
                               track=track, layout_id=layout_id,
                               discipline=discipline, field=field)
        try:
            with self._lock:
                row = self._conn.execute(
                    "SELECT window_json FROM setup_working_windows WHERE context_key=?",
                    (ctx.key(),)).fetchone()
            import json as _json
            return _json.loads(row[0]) if row is not None else None
        except Exception:
            return None

    def list_working_windows(self, scope_fingerprint: str) -> list:
        """All learned windows for a scope (materialised), newest-updated first."""
        import json as _json
        try:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT window_json FROM setup_working_windows WHERE "
                    "scope_fingerprint=? ORDER BY updated_at DESC", (str(scope_fingerprint),)).fetchall()
            out = []
            for r in rows:
                try:
                    out.append(_json.loads(r[0]))
                except Exception:
                    continue
            return out
        except Exception:
            return []

    def select_next_experiment(
        self, experiment_id: int, *, dominant_issue: str = "", target_phase: str = "",
        target_corners=(), recurrence_class: str = "", valid_lap_count: int = 0,
        current_setup=None, decision_blocks: bool = False,
    ) -> dict:
        """Phase 5 orchestrator: build a SelectionContext from persisted learned
        windows + failed-direction learning + the current setup, generate
        minimum-effective candidates, and select the next experiment deterministically
        — subordinate to the canonical decision authority. Returns a structured
        result incl. an honest no-selection state. Never raises."""
        try:
            from strategy.experiment_selection import (
                SelectionContext, generate_candidates, select_experiment,
                build_test_protocol)
            from strategy.working_window import WindowContextKey
            from strategy.setup_ranges import resolve_ranges
        except Exception as exc:  # pragma: no cover
            return {"ok": False, "error": f"phase5 import failed: {exc}"}
        exp, scope = self._experiment_context_scope(int(experiment_id))
        if exp is None:
            return {"ok": False, "reason": "experiment not found"}
        car = scope["car"]; track = scope["track"]; layout = scope["layout_id"]
        discipline = scope["discipline"]; scope_fp = scope["scope_fingerprint"]
        try:
            ranges = resolve_ranges(car) if car else {}
        except Exception:
            ranges = {}
        # learned windows for this scope, keyed by field
        windows = {}
        from strategy.working_window import (
            LearnedWorkingWindow, WindowConfidence, DirectionalEvidence,
            DirectionEffect)
        for wd in self.list_working_windows(scope_fp):
            fld = str(wd.get("field") or "")
            if fld:
                windows[fld] = _rehydrate_window(wd)
        # failed + ineffective directions from Phase 3 failed-direction learning +
        # the learned windows' directional lockouts
        failed = set()
        ineffective = set()
        try:
            for fd in self.list_failed_directions_by_scope(scope_fp):
                f = str(fd.get("field") or ""); d = str(fd.get("direction") or "")
                if f and d in ("increase", "decrease") and fd.get("strength") == "lockout":
                    failed.add((f, d))
        except Exception:
            pass
        for fld, w in windows.items():
            for d in getattr(w, "locked_directions", lambda: ())():
                failed.add((fld, d))
            for de in getattr(w, "directional", ()):
                if de.effect == DirectionEffect.NO_EFFECT:
                    ineffective.add((fld, de.direction))
        # protected behaviours from the experiment
        protected = tuple(
            {"behaviour": p.get("description", ""), "field": p.get("field", ""),
             "corners": _json_loads_list(p.get("corners_json"))}
            for p in (exp.get("protected_behaviours") or []))
        cur = dict(current_setup or {})
        ctx = SelectionContext(
            scope_fingerprint=scope_fp, car=car, track=track, layout_id=layout,
            discipline=discipline, dominant_issue=dominant_issue,
            target_phase=target_phase, target_corners=tuple(target_corners),
            recurrence_class=recurrence_class, valid_lap_count=valid_lap_count,
            current_setup=cur, ranges=ranges, working_windows=windows,
            failed_directions=tuple(sorted(failed)),
            ineffective_directions=tuple(sorted(ineffective)),
            protected_behaviours=protected)
        candidates = generate_candidates(ctx)
        result = select_experiment(
            candidates, decision_blocks=decision_blocks,
            recurrence_class=recurrence_class, valid_lap_count=valid_lap_count)
        out = result.to_dict()
        out["ok"] = True
        if result.selected is not None:
            out["test_protocol"] = build_test_protocol(
                result.selected, parent_setup_id=str(exp.get("parent_setup_id") or ""),
                rollback_target=str(exp.get("rollback_target") or ""))
        return out

    def review_and_learn(
        self, experiment_id: int, *, test_session_id=None, baseline_session_id=None,
        driver_review=None, confounders=None, complete_on_success: bool = True,
        driver: str = "",
    ) -> dict:
        """Full Phase 3→4→5 runtime step: review the outcome (canonical evidence
        assembly + Phase 3 evaluation), LEARN working-window updates from the
        canonical outcome, then SELECT the minimum-effective next experiment —
        subordinate to the canonical decision authority. Read-only w.r.t. the setup:
        never applies or reverts. Returns the review dict augmented with
        ``learning`` and ``next_experiment``. Never raises."""
        review = self.review_experiment_outcome(
            int(experiment_id), test_session_id=test_session_id,
            baseline_session_id=baseline_session_id, driver_review=driver_review,
            confounders=confounders, complete_on_success=complete_on_success,
            driver=driver)
        if not isinstance(review, dict) or not review.get("ok"):
            return review
        status = str(review.get("status") or "")
        learn = self.learn_from_experiment_outcome(int(experiment_id))
        review["learning"] = learn

        # Build selection inputs from the reviewed experiment.
        exp, scope = self._experiment_context_scope(int(experiment_id))
        dominant = ""
        target_corners = ()
        try:
            hyp = json.loads((exp or {}).get("hypothesis_json") or "{}")
            dominant = str(hyp.get("primary_diagnosis") or "")
            target_corners = tuple(hyp.get("target_corners") or [])
        except Exception:
            dominant = ""
        # current setup = what is actually in the car (the applied checkpoint fields)
        current_setup = {}
        try:
            cprow = self.get_latest_applied_checkpoint(
                int((scope or {}).get("car_id") or 0), (scope or {}).get("track", ""),
                (scope or {}).get("layout_id", ""), (scope or {}).get("discipline", ""))
            if cprow and cprow.get("fields_json"):
                current_setup = json.loads(cprow["fields_json"]) or {}
                current_setup = {k: (v[0] if isinstance(v, list) and v else v)
                                 for k, v in current_setup.items()}
        except Exception:
            current_setup = {}
        # The decision authority is subordinate: a non-actionable outcome blocks a
        # setup change; the target is unresolved only when it did not improve.
        decision_blocks = status in ("insufficient_evidence", "confounded") \
            or str(review.get("association") or "resolved") != "resolved"
        still_recurring = status in ("regression", "no_meaningful_change",
                                     "partial_improvement")
        recurrence = "recurring" if still_recurring else "isolated"
        review["next_experiment"] = self.select_next_experiment(
            int(experiment_id), dominant_issue=dominant, target_phase="",
            target_corners=target_corners, recurrence_class=recurrence,
            valid_lap_count=int(review.get("valid_laps") or 0),
            current_setup=current_setup, decision_blocks=decision_blocks)
        # Phase 6: full residual snapshot + multi-symptom development plan.
        review["engineering_plan"] = self.build_engineering_plan(
            int(experiment_id), association_status=str(review.get("association") or "resolved"),
            decision_state=str((review.get("next_experiment") or {}).get("decision_state") or ""),
            current_setup=current_setup)
        # Phase 8: capture this completed review as an immutable cross-session
        # development record (permanent engineering memory). Best-effort, idempotent,
        # read-only w.r.t. all prior evidence — a capture failure never breaks review.
        try:
            review["development_record"] = self.record_engineering_development(
                int(experiment_id), driver=driver)
        except Exception:
            review["development_record"] = {"ok": False, "reason": "capture skipped"}
        return review

    def build_engineering_plan(
        self, experiment_id: int, *, association_status: str = "resolved",
        decision_state: str = "", current_setup=None,
    ) -> dict:
        """Phase 6 orchestrator: build the current engineering-state snapshot +
        multi-symptom development plan from the persisted Phase-3 outcome, Phase-4
        evidence and Phase-5 working windows/candidates. Deterministic + regenerable
        (NO persistence — the plan is a pure function of persisted state). Read-only:
        selects at most ONE immediate experiment (via Phase 5) and queues the rest.
        Never raises."""
        try:
            from strategy.engineering_state import build_engineering_state, ValidLapSummary
            from strategy.experiment_planning import (
                prioritise_issues, build_development_plan, ActionKind)
            from strategy.setup_decision_status import resolve_setup_decision
        except Exception as exc:  # pragma: no cover
            return {"ok": False, "error": f"phase6 import failed: {exc}"}
        exp, scope = self._experiment_context_scope(int(experiment_id))
        if exp is None:
            return {"ok": False, "reason": "experiment not found"}
        outcome = self.get_latest_experiment_outcome(int(experiment_id))
        if outcome is None:
            return {"ok": False, "reason": "no persisted outcome"}
        scope_fp = str(exp.get("scope_fingerprint") or "")
        discipline = str((scope or {}).get("discipline") or "")
        exp_status = str(exp.get("status") or "")
        outcome_status = str(outcome.get("status") or "")
        # canonical decision state (Phase 4 authority)
        try:
            dstate = decision_state or resolve_setup_decision(
                experiment_status=exp_status, outcome_status=outcome_status).state.value
        except Exception:
            dstate = decision_state
        decision_blocks = outcome_status in ("insufficient_evidence", "confounded") \
            or str(association_status or "resolved") != "resolved"
        # valid-lap summary from the outcome validity
        import json as _json
        try:
            validity = _json.loads(outcome.get("validity_json") or "{}")
        except Exception:
            validity = {}
        try:
            whole = _json.loads(outcome.get("whole_lap_json") or "{}")
        except Exception:
            whole = {}
        vls = ValidLapSummary(
            valid_lap_count=int(validity.get("valid_laps") or 0),
            rejected_lap_count=int(validity.get("rejected_laps") or 0),
            median_lap_ms=int(whole.get("test_median_ms") or 0),
            rejection_distribution={r: 1 for r in validity.get("rejection_reasons") or []})
        # working-window fields for this scope
        ww_fields = []
        try:
            ww_fields = [str(w.get("field") or "")
                         for w in self.list_working_windows(scope_fp) if w.get("field")]
        except Exception:
            ww_fields = []
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        snapshot = build_engineering_state(
            outcome=outcome, scope_fingerprint=scope_fp,
            car=str((scope or {}).get("car") or ""),
            track=str((scope or {}).get("track") or ""),
            layout_id=str((scope or {}).get("layout_id") or ""), discipline=discipline,
            applied_checkpoint_id=str(exp.get("applied_checkpoint_id") or ""),
            experiment_id=str(experiment_id), association_status=association_status,
            decision_state=dstate, valid_laps=vls, working_window_fields=ww_fields,
            generated_at=now)
        prioritised = prioritise_issues(snapshot.residual_issues,
                                        decision_blocks=decision_blocks)

        cur = dict(current_setup or {})
        if not cur:
            try:
                cprow = self.get_latest_applied_checkpoint(
                    int((scope or {}).get("car_id") or 0), (scope or {}).get("track", ""),
                    (scope or {}).get("layout_id", ""), discipline)
                if cprow and cprow.get("fields_json"):
                    raw = _json.loads(cprow["fields_json"]) or {}
                    cur = {k: (v[0] if isinstance(v, list) and v else v)
                           for k, v in raw.items()}
            except Exception:
                cur = {}

        # setup-actionable issues in priority order
        setup_issues = [p for p in prioritised if p.actionable_as_setup]
        issue_by_key = {ri.key: ri for ri in snapshot.residual_issues}
        immediate_selection = None
        queued_candidates = []
        valid_laps = int(validity.get("valid_laps") or 0)
        for idx, p in enumerate(setup_issues):
            ri = issue_by_key.get(p.issue_key)
            if ri is None:
                continue
            corners = tuple(c for c in (ri.identity.corner_name,
                                        ri.identity.segment_id) if c)
            rc = ("recurring" if ri.test_class in ("recurring", "strongly_recurring")
                  else ("strongly_recurring" if ri.residual_state.value == "new"
                        and ri.test_affected >= 3 else "recurring"))
            sel = self.select_next_experiment(
                int(experiment_id), dominant_issue=ri.identity.issue_type,
                target_phase=ri.identity.phase, target_corners=corners,
                recurrence_class=rc, valid_lap_count=valid_laps,
                current_setup=cur, decision_blocks=decision_blocks)
            if idx == 0 and sel.get("selected"):
                immediate_selection = sel
            elif sel.get("selected"):
                cand = dict(sel["selected"])
                cand["_issue_key"] = p.issue_key
                queued_candidates.append(cand)
            if len(queued_candidates) >= 3:
                break

        plan = build_development_plan(
            snapshot, prioritised, immediate_selection=immediate_selection,
            queued_candidates=queued_candidates,
            rollback_target=str(exp.get("rollback_target") or ""),
            generated_at=now, decision_blocks=decision_blocks)
        return {"ok": True, "snapshot": snapshot.to_dict(), "plan": plan.to_dict()}

    # ------------------------------------------------------------------
    # Live Engineering State Monitor + Session Development Ledger
    # (Phase 7 — READ-ONLY OBSERVER, no migration, DB stays v23)
    # ------------------------------------------------------------------
    def build_live_engineering_state(
        self, session_id: int, *, car_id: "int | None" = None, track: str = "",
        layout_id: str = "", scope_fingerprint: str = "", discipline: str = "",
        protected_keys: "Sequence[str] | None" = None,
    ) -> dict:
        """Phase 7 orchestrator: fold the persisted per-corner evidence for ONE live
        session into the current Live Engineering State + append-only Session
        Development Ledger.

        Pure OBSERVER: it decides nothing, selects no experiment, authors no setup
        value and writes nothing. It regenerates deterministically from
        ``corner_issue_occurrences`` (session-keyed, per-lap) + the canonical
        lap-validity authority — so no migration is required (the state and ledger
        are a pure function of already-persisted rows; a restart rebuild yields the
        SAME content fingerprints). Never raises."""
        try:
            from strategy.engineering_lap_validity import (
                evaluate_session_laps, LapPurpose)
            from strategy.corner_evidence import from_issue_occurrence_row
            from strategy.live_engineering_state import update_live_state
            from strategy.session_development import build_session_ledger
        except Exception as exc:  # pragma: no cover
            return {"ok": False, "error": f"phase7 import failed: {exc}"}

        sid = int(session_id or 0)
        if not sid:
            return {"ok": False, "reason": "no session id"}
        # Resolve physical scope (car/track) when not supplied.
        if car_id is None or not track:
            meta = self.get_session_meta(sid) or {}
            car_id = int(meta.get("car_id") or 0) if car_id is None else car_id
            track = track or str(meta.get("track") or "")
        if not track:
            return {"ok": False, "reason": "session scope not resolvable"}

        # All persisted occurrences for this scope, restricted to THIS session.
        occ_rows = [r for r in self.get_issue_occurrences(int(car_id or 0), track,
                                                          layout_id)
                    if str(r.get("session_id")) == str(sid)]
        # Canonical comparable-lap window (formation/pit/invalid/outlier removed by
        # the Phase-4 authority — this observer trusts that, it does not re-judge laps).
        laps = self.get_laps_for_scoring(sid)
        _, summ = evaluate_session_laps(
            laps, purpose=LapPurpose.PRACTICE_PATTERN,
            scope_fingerprint=scope_fingerprint, expected_track=track)
        valid_nums = tuple(getattr(summ, "valid_lap_numbers", ()) or ())

        records = [from_issue_occurrence_row(r, scope_fingerprint=scope_fingerprint)
                   for r in occ_rows]

        # Current live state over the full comparable window.
        state = update_live_state(
            records, valid_nums, scope_fingerprint=scope_fingerprint,
            discipline=discipline, session_id=sid, protected_keys=protected_keys)

        # Deterministic development timeline: one snapshot per growing valid-lap
        # prefix (a lap only ever appends events — append-only ledger contract).
        snapshots = []
        for i in range(1, len(valid_nums) + 1):
            prefix = valid_nums[:i]
            prefix_set = set(prefix)
            prefix_recs = [rec for rec in records
                           if rec.lap_number is not None
                           and rec.lap_number in prefix_set]
            snap = update_live_state(
                prefix_recs, prefix, scope_fingerprint=scope_fingerprint,
                discipline=discipline, session_id=sid, protected_keys=protected_keys)
            snapshots.append((prefix[-1], snap))
        ledger = build_session_ledger(
            snapshots, session_id=sid, scope_fingerprint=scope_fingerprint)

        return {
            "ok": True, "session_id": sid, "car_id": int(car_id or 0),
            "track": track, "layout_id": layout_id,
            "valid_lap_count": len(valid_nums),
            "live_state": state.to_dict(), "ledger": ledger.to_dict(),
        }

    # ------------------------------------------------------------------
    # Cross-session engineering development memory (Phase 8, DB v24)
    # READ-ONLY intelligence: records immutable review facts + folds them
    # into permanent memory / history / metrics. Decides nothing, authors
    # no setup value, evaluates no lap, mutates no prior evidence.
    # ------------------------------------------------------------------
    def _dominant_compound(self, test_session_id) -> str:
        """Most-frequent non-empty tyre compound over a session's laps (or '')."""
        try:
            sid = int(test_session_id)
        except (TypeError, ValueError):
            return ""
        if not sid:
            return ""
        counts: dict = {}
        for lap in self.get_laps_for_scoring(sid):
            c = str(lap.get("compound") or "").strip()
            if c:
                counts[c] = counts.get(c, 0) + 1
        if not counts:
            return ""
        return max(sorted(counts), key=lambda k: counts[k])

    def _windows_for_record(self, scope_fingerprint: str) -> list:
        """Learned working windows for a scope, normalised to the record shape
        (low_bound/high_bound → min/max). Read-only."""
        out = []
        for w in self.list_working_windows(scope_fingerprint):
            if not isinstance(w, dict) or not w.get("field"):
                continue
            out.append({
                "field": str(w.get("field")),
                "min": w.get("low_bound"), "max": w.get("high_bound"),
                "confidence": str(w.get("confidence") or ""),
                "valid_experiment_count": int(w.get("valid_experiment_count") or 0),
                "improvement_count": int(w.get("improvement_count") or 0),
                "regression_count": int(w.get("regression_count") or 0),
            })
        return out

    def _memory_context_for_experiment(self, experiment_id: int, outcome: dict, *,
                                       driver: str, gt7_version: str, compound: str):
        """Build the Phase-8 MemoryContextKey for an experiment's review."""
        from strategy.development_history import MemoryContextKey
        _, scope = self._experiment_context_scope(int(experiment_id))
        scope = scope or {}
        comp = compound or self._dominant_compound(outcome.get("test_session_id"))
        return MemoryContextKey(
            driver=str(driver or ""), car=str(scope.get("car") or ""),
            track=str(scope.get("track") or ""),
            layout_id=str(scope.get("layout_id") or ""),
            discipline=str(scope.get("discipline") or ""),
            gt7_version=str(gt7_version or ""), compound=str(comp or "")), scope

    def record_engineering_development(
        self, experiment_id: int, *, recorded_at: "str | None" = None,
        driver: str = "", gt7_version: str = "", compound: str = "",
        session_date: str = "",
    ) -> dict:
        """Capture ONE completed engineering review as an immutable development record
        (permanent cross-session memory). Idempotent: re-recording the same review is a
        no-op (UNIQUE record_key). Read-only w.r.t. all prior evidence; never rewrites
        history; never raises. Returns the record dict (or a reason)."""
        try:
            from strategy.development_history import build_development_record
            from strategy.engineering_issue import residual_issues_from_outcome
        except Exception as exc:  # pragma: no cover
            return {"ok": False, "error": f"phase8 import failed: {exc}"}
        exp = self.get_setup_experiment(int(experiment_id))
        if exp is None:
            return {"ok": False, "reason": "experiment not found"}
        outcome = self.get_latest_experiment_outcome(int(experiment_id))
        if outcome is None:
            return {"ok": False, "reason": "no persisted outcome to record"}
        ctx, scope = self._memory_context_for_experiment(
            int(experiment_id), outcome, driver=driver, gt7_version=gt7_version,
            compound=compound)
        scope_fp = str((scope or {}).get("scope_fingerprint")
                       or outcome.get("scope_fingerprint") or "")
        residuals = residual_issues_from_outcome(
            outcome, discipline=str((scope or {}).get("discipline") or ""),
            scope=scope_fp,
            association_status="resolved")
        windows = self._windows_for_record(scope_fp)
        now = recorded_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
        record = build_development_record(
            outcome, exp, context=ctx, scope_fingerprint=scope_fp,
            working_windows=windows, residuals=residuals, recorded_at=now,
            session_date=session_date)
        if record is None:
            return {"ok": False, "reason": "outcome not recordable"}
        inserted = self._persist_development_record(record, created_at=now)
        return {"ok": True, "recorded": inserted, "record": record.to_dict()}

    def _persist_development_record(self, record, *, created_at: str) -> bool:
        """Append-only insert (idempotent by UNIQUE record_key). Returns True when a
        NEW row was written, False when the review was already recorded. Never
        UPDATEs or DELETEs an existing row (history is immutable). Never raises."""
        import json as _json
        ctx = record.context
        try:
            with self._lock:
                cur = self._conn.execute(
                    """INSERT OR IGNORE INTO engineering_development_records
                       (record_key, memory_context_key, scope_fingerprint, driver,
                        car, track, layout_id, discipline, gt7_version, compound,
                        experiment_id, outcome_id, outcome_status, confidence_level,
                        recorded_at, session_date, test_session_id, record_json,
                        content_fingerprint, eval_version, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (record.record_key, record.memory_context_key,
                     record.scope_fingerprint, ctx.driver, ctx.car, ctx.track,
                     ctx.layout_id, ctx.discipline, ctx.gt7_version, ctx.compound,
                     record.experiment_id, record.outcome_id, record.outcome_status,
                     record.confidence_level, record.recorded_at, record.session_date,
                     record.test_session_id, _json.dumps(record.to_dict()),
                     record.content_fingerprint, record.eval_version, created_at))
                self._conn.commit()
                return cur.rowcount > 0
        except Exception:
            return False

    def get_development_records(
        self, memory_context_key: str = "", *, car: str = "", track: str = "",
        layout_id: str = "", discipline: str = "", compound: str = "",
        driver: str = "", gt7_version: str = "",
    ) -> list[dict]:
        """Return the immutable development records for ONE memory context, oldest
        first. Provide either a ``memory_context_key`` or the context components
        (they are combined into the same key so incompatible contexts never mix).
        Reconstructed purely from the stored record_json. Never raises."""
        import json as _json
        key = str(memory_context_key or "")
        if not key:
            from strategy.development_history import MemoryContextKey
            key = MemoryContextKey(
                driver=driver, car=car, track=track, layout_id=layout_id,
                discipline=discipline, gt7_version=gt7_version, compound=compound).key()
        try:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT record_json FROM engineering_development_records "
                    "WHERE memory_context_key=? ORDER BY id ASC", (key,)).fetchall()
            out = []
            for r in rows:
                try:
                    out.append(_json.loads(r[0]))
                except Exception:
                    continue
            return out
        except Exception:
            return []

    def build_development_history(self, memory_context_key: str = "", **ctx) -> dict:
        """Fold the persisted immutable records into a chronological
        ``DevelopmentHistory`` (regenerable; restart-deterministic). Never raises."""
        try:
            from strategy.development_history import (
                build_history, MemoryContextKey)
        except Exception as exc:  # pragma: no cover
            return {"ok": False, "error": f"phase8 import failed: {exc}"}
        records = self.get_development_records(memory_context_key, **ctx)
        context = None
        if not memory_context_key and ctx:
            context = MemoryContextKey(
                driver=ctx.get("driver", ""), car=ctx.get("car", ""),
                track=ctx.get("track", ""), layout_id=ctx.get("layout_id", ""),
                discipline=ctx.get("discipline", ""),
                gt7_version=ctx.get("gt7_version", ""),
                compound=ctx.get("compound", ""))
        history = build_history(records, context=context)
        return {"ok": True, "history": history.to_dict(),
                "record_count": history.review_count}

    def build_cross_session_memory(self, memory_context_key: str = "", **ctx) -> dict:
        """Fold the persisted records into permanent ``EngineeringMemory`` +
        long-term ``ProgressMetrics`` + an ``EngineeringScorecard`` + the latest
        session comparison + the engineering timeline. Deterministic + regenerable;
        the whole result is a pure function of the immutable records. Never raises."""
        try:
            from strategy.development_history import build_history, build_timeline, MemoryContextKey
            from strategy.engineering_memory import build_engineering_memory
            from strategy.progress_metrics import (
                build_progress_metrics, build_scorecard, compare_latest_sessions)
        except Exception as exc:  # pragma: no cover
            return {"ok": False, "error": f"phase8 import failed: {exc}"}
        records = self.get_development_records(memory_context_key, **ctx)
        context = None
        if not memory_context_key and ctx:
            context = MemoryContextKey(
                driver=ctx.get("driver", ""), car=ctx.get("car", ""),
                track=ctx.get("track", ""), layout_id=ctx.get("layout_id", ""),
                discipline=ctx.get("discipline", ""),
                gt7_version=ctx.get("gt7_version", ""),
                compound=ctx.get("compound", ""))
        history = build_history(records, context=context)
        memory = build_engineering_memory(history)
        metrics = build_progress_metrics(history, memory)
        scorecard = build_scorecard(history, memory, metrics)
        comparison = compare_latest_sessions(history)
        timeline = build_timeline(history)
        return {
            "ok": True, "history": history.to_dict(), "memory": memory.to_dict(),
            "metrics": metrics.to_dict(), "scorecard": scorecard.to_dict(),
            "comparison": (comparison.to_dict() if comparison else None),
            "timeline": [e.to_dict() for e in timeline],
            "record_count": history.review_count,
        }

    # ------------------------------------------------------------------
    # Cross-context engineering transfer + regression-risk intelligence
    # (Phase 9 — READ-ONLY OBSERVER, NO migration; regenerates from the
    # immutable Phase-8 records). Reports; decides nothing.
    # ------------------------------------------------------------------
    def _car_class_map(self) -> dict:
        """{car name → category} from the cars table (e.g. 'Gr.3'). Read-only; the
        Phase-9 RELATED tier only fires when a category is actually known."""
        try:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT name, category FROM cars WHERE category != ''").fetchall()
            return {str(r[0]): str(r[1]) for r in rows}
        except Exception:
            return {}

    def get_development_records_for_context_search(
        self, *, car: str = "", track: str = "", driver: str = "",
    ) -> list[dict]:
        """Return the immutable development records that share ANY of car / track /
        (non-empty) driver with the query — the candidate pool for Phase-9 context
        matching (the pure module classifies + filters). Read-only; never raises."""
        import json as _json
        clauses, params = [], []
        if car:
            clauses.append("car = ?"); params.append(str(car))
        if track:
            clauses.append("track = ?"); params.append(str(track))
        if driver:
            clauses.append("(driver = ? AND driver != '')"); params.append(str(driver))
        if not clauses:
            return []
        try:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT record_json FROM engineering_development_records "
                    "WHERE " + " OR ".join(clauses) + " ORDER BY id ASC",
                    tuple(params)).fetchall()
            out = []
            for r in rows:
                try:
                    out.append(_json.loads(r[0]))
                except Exception:
                    continue
            return out
        except Exception:
            return []

    def build_engineering_context(
        self, *, car: str = "", track: str = "", layout_id: str = "",
        discipline: str = "", driver: str = "", gt7_version: str = "",
        compound: str = "", proposed_change: "dict | None" = None,
    ) -> dict:
        """Phase 9 orchestrator: before an experiment is proposed, surface every
        relevant lesson from COMPATIBLE historical contexts — ranked transfers,
        engineering constraints, and (for a proposed change) regression risks.

        READ-ONLY: evaluates no evidence, creates/chooses no experiment, modifies no
        working window, mutates nothing, and NEVER blocks. Deterministic + regenerable
        from the immutable Phase-8 records (NO migration). Never raises."""
        try:
            from strategy.development_history import MemoryContextKey
            from strategy.context_transfer import (
                group_matched_records, build_context_transfers, transfer_fingerprint)
            from strategy.engineering_constraints import (
                derive_constraints, constraints_fingerprint)
            from strategy.regression_risk import assess_regression_risk, risk_fingerprint
        except Exception as exc:  # pragma: no cover
            return {"ok": False, "error": f"phase9 import failed: {exc}"}
        query = MemoryContextKey(
            driver=str(driver or ""), car=str(car or ""), track=str(track or ""),
            layout_id=str(layout_id or ""), discipline=str(discipline or ""),
            gt7_version=str(gt7_version or ""), compound=str(compound or ""))
        records = self.get_development_records_for_context_search(
            car=car, track=track, driver=driver)
        car_class = self._car_class_map()
        matched = group_matched_records(query, records, car_class_of=car_class)
        transfers = build_context_transfers(query, records, car_class_of=car_class,
                                            matched=matched)
        constraints = derive_constraints(query, records, car_class_of=car_class,
                                        matched=matched)
        risks = assess_regression_risk(constraints, transfers,
                                       proposed_change=proposed_change)
        return {
            "ok": True, "query_context": query.to_dict(),
            "matched_contexts": [
                {"context": m.context.to_dict(), "strength": m.strength.value,
                 "reason": m.reason, "record_count": len(m.records)}
                for m in matched],
            "transfers": [t.to_dict() for t in transfers],
            "constraints": [c.to_dict() for c in constraints],
            "regression_risks": [r.to_dict() for r in risks],
            "proposed_change": (dict(proposed_change) if proposed_change else None),
            "fingerprints": {
                "transfers": transfer_fingerprint(transfers),
                "constraints": constraints_fingerprint(constraints),
                "risks": risk_fingerprint(risks),
            },
            "candidate_record_count": len(records),
        }

    # ------------------------------------------------------------------
    # Engineering experiment pre-flight review (Phase 10 — READ-ONLY,
    # NO migration; regenerates from Phase-8/9 outputs). Reviews the EXACT
    # Phase-5 selection; re-selects nothing, changes nothing, blocks nothing.
    # ------------------------------------------------------------------
    def build_experiment_preflight(
        self, selection: dict, *, car: str = "", track: str = "", layout_id: str = "",
        discipline: str = "", driver: str = "", gt7_version: str = "",
        compound: str = "",
    ) -> dict:
        """Phase 10 orchestrator: perform a deterministic engineering pre-flight review
        of the EXACT Phase-5 selected experiment before it is shown to the driver.

        ``selection`` is the Phase-5 candidate dict (``select_next_experiment`` →
        ``selected``); it is echoed verbatim and never re-selected or modified. Read-only:
        builds the Phase-9 context for the proposed change + the Phase-8 memory, then
        assembles the review. Regenerable (NO migration); never raises; NEVER blocks."""
        try:
            from strategy.preflight_review import build_preflight_review
            from strategy.setup_synthesis import PARAMETER_INTERACTIONS
        except Exception as exc:  # pragma: no cover
            return {"ok": False, "error": f"phase10 import failed: {exc}"}
        if not isinstance(selection, dict) or not str(selection.get("field") or ""):
            return {"ok": False, "reason": "no selected experiment to review"}
        proposed_change = {
            "field": str(selection.get("field") or ""),
            "direction": str(selection.get("direction") or ""),
            "value": selection.get("proposed_value"),
        }
        context = self.build_engineering_context(
            car=car, track=track, layout_id=layout_id, discipline=discipline,
            driver=driver, gt7_version=gt7_version, compound=compound,
            proposed_change=proposed_change)
        memory = self.build_cross_session_memory(
            car=car, track=track, layout_id=layout_id, discipline=discipline,
            gt7_version=gt7_version, compound=compound, driver=driver)
        review = build_preflight_review(
            selection, context=context, memory=memory,
            interactions=PARAMETER_INTERACTIONS)
        return {"ok": True, "review": review.to_dict(),
                "context_fingerprints": context.get("fingerprints", {})}

    # ------------------------------------------------------------------
    # Post-flight reconciliation + prediction calibration (Phase 11, DB v25)
    # READ-ONLY: compares the Phase-10 prediction with the Phase-3 actual
    # outcome; persists an immutable append-only calibration record. Changes
    # no experiment, outcome, memory, working window, or setup value.
    # ------------------------------------------------------------------
    def _residual_dicts_for_outcome(self, outcome: dict, *, discipline: str = "",
                                    scope: str = "") -> list:
        """Normalise Phase-6 residuals for an outcome into the stable dict shape the
        Phase-11 reconciler consumes. Read-only."""
        try:
            from strategy.engineering_issue import residual_issues_from_outcome
        except Exception:  # pragma: no cover
            return []
        out = []
        for ri in residual_issues_from_outcome(outcome, discipline=discipline, scope=scope):
            ident = ri.identity
            out.append({
                "issue_key": ident.key(), "family": ident.issue_family.value,
                "issue_type": ident.issue_type, "axle": ident.axle,
                "phase": ident.phase, "corner": ident.corner_name or ident.segment_id,
                "residual_state": ri.residual_state.value, "is_new": bool(ri.is_new),
                "is_regression": bool(ri.is_regression),
                "still_present": bool(ri.still_present),
                "protected_good": bool(ri.protected_good),
            })
        return out

    def record_experiment_reconciliation(
        self, experiment_id: int, preflight_review: dict, *,
        recorded_at: "str | None" = None, driver: str = "", gt7_version: str = "",
        compound: str = "",
    ) -> dict:
        """Reconcile the Phase-10 pre-flight prediction for ``experiment_id`` against its
        completed Phase-3 outcome + Phase-6 residuals, and persist an immutable append-only
        calibration record. ``preflight_review`` is the exact Phase-10 review captured at
        proposal time. Idempotent (UNIQUE record_key). Read-only w.r.t. all prior evidence;
        never rewrites history; never raises."""
        try:
            from strategy.postflight_reconciliation import build_reconciliation_record
        except Exception as exc:  # pragma: no cover
            return {"ok": False, "error": f"phase11 import failed: {exc}"}
        if not isinstance(preflight_review, dict) or not preflight_review:
            return {"ok": False, "reason": "no pre-flight prediction supplied"}
        outcome = self.get_latest_experiment_outcome(int(experiment_id))
        if outcome is None:
            return {"ok": False, "reason": "no completed outcome to reconcile"}
        exp = self.get_setup_experiment(int(experiment_id))
        ctx, scope = self._memory_context_for_experiment(
            int(experiment_id), outcome, driver=driver, gt7_version=gt7_version,
            compound=compound)
        scope_fp = str((scope or {}).get("scope_fingerprint")
                       or outcome.get("scope_fingerprint") or "")
        residuals = self._residual_dicts_for_outcome(
            outcome, discipline=str((scope or {}).get("discipline") or ""), scope=scope_fp)
        # ensure the record carries the real experiment id (the review echoes candidate_id)
        review = dict(preflight_review.get("review") or preflight_review)
        exp_block = dict(review.get("experiment") or {})
        exp_block.setdefault("candidate_id", str(experiment_id))
        review["experiment"] = exp_block
        outcome = dict(outcome); outcome.setdefault("experiment_id", int(experiment_id))
        now = recorded_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
        record = build_reconciliation_record(
            {"review": review}, outcome, residuals,
            memory_context_key=ctx.key(), context=ctx.to_dict(), recorded_at=now)
        if record is None:
            return {"ok": False, "reason": "reconciliation not computable"}
        inserted = self._persist_reconciliation_record(record, created_at=now)
        return {"ok": True, "recorded": inserted, "record": record.to_dict()}

    def _persist_reconciliation_record(self, record, *, created_at: str) -> bool:
        """Append-only insert (idempotent by UNIQUE record_key). Returns True when a NEW
        row was written, False when already recorded. Never UPDATE/DELETE. Never raises."""
        import json as _json
        try:
            with self._lock:
                cur = self._conn.execute(
                    """INSERT OR IGNORE INTO engineering_reconciliation_records
                       (record_key, memory_context_key, experiment_id, outcome_id,
                        predicted_risk, outcome_status, overall_accuracy,
                        prediction_fingerprint, recorded_at, record_json,
                        content_fingerprint, eval_version, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (record.record_key, record.memory_context_key, record.experiment_id,
                     record.outcome_id, record.predicted_risk, record.outcome_status,
                     float(record.accuracy.overall_accuracy),
                     record.prediction_fingerprint, record.recorded_at,
                     _json.dumps(record.to_dict()), record.content_fingerprint,
                     record.eval_version, created_at))
                self._conn.commit()
                return cur.rowcount > 0
        except Exception:
            return False

    def get_reconciliation_records(self, memory_context_key: str = "", **ctx) -> list[dict]:
        """Return the immutable calibration records for a memory context, oldest first.
        Reconstructed purely from the stored record_json. Read-only; never raises."""
        import json as _json
        key = str(memory_context_key or "")
        if not key:
            from strategy.development_history import MemoryContextKey
            key = MemoryContextKey(
                driver=ctx.get("driver", ""), car=ctx.get("car", ""),
                track=ctx.get("track", ""), layout_id=ctx.get("layout_id", ""),
                discipline=ctx.get("discipline", ""),
                gt7_version=ctx.get("gt7_version", ""),
                compound=ctx.get("compound", "")).key()
        try:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT record_json FROM engineering_reconciliation_records "
                    "WHERE memory_context_key=? ORDER BY id ASC", (key,)).fetchall()
            out = []
            for r in rows:
                try:
                    out.append(_json.loads(r[0]))
                except Exception:
                    continue
            return out
        except Exception:
            return []

    def build_prediction_calibration(self, memory_context_key: str = "", **ctx) -> dict:
        """Aggregate the immutable calibration records for a context into a deterministic
        prediction-calibration summary (mean accuracies + confirmed/contradicted counts).
        Regenerable from the stored records; restart-deterministic. Read-only."""
        records = self.get_reconciliation_records(memory_context_key, **ctx)
        n = len(records)
        if not n:
            return {"ok": True, "record_count": 0, "records": [],
                    "calibration": {"reconciliations": 0}}

        def _avg(path):
            vals = []
            for r in records:
                acc = r.get("accuracy") or {}
                v = acc.get(path)
                if isinstance(v, (int, float)):
                    vals.append(float(v))
            return round(sum(vals) / len(vals), 4) if vals else 0.0

        confirmed = sum(int((r.get("accuracy") or {}).get("confirmed_count") or 0)
                        for r in records)
        contradicted = sum(int((r.get("accuracy") or {}).get("contradicted_count") or 0)
                           for r in records)
        risk_hits = sum(1 for r in records
                        if r.get("predicted_risk") in ("high", "moderate")
                        and r.get("outcome_status") == "regression")
        calibration = {
            "reconciliations": n,
            "overall_accuracy": _avg("overall_accuracy"),
            "primary_consequence_accuracy": _avg("primary_consequence_accuracy"),
            "side_effect_accuracy": _avg("side_effect_accuracy"),
            "risk_accuracy": _avg("risk_accuracy"),
            "constraint_accuracy": _avg("constraint_accuracy"),
            "historical_transfer_usefulness": _avg("historical_transfer_usefulness"),
            "checklist_usefulness": _avg("checklist_usefulness"),
            "confirmed_total": confirmed, "contradicted_total": contradicted,
            "elevated_risk_regressions": risk_hits,
        }
        return {"ok": True, "record_count": n, "records": records,
                "calibration": calibration}

    # ------------------------------------------------------------------
    # Mechanism-annotated diagnosis (Program 2, Phase 13 — READ-ONLY).
    # Explains the vehicle-dynamics MECHANISMS behind each canonical Program-1
    # diagnosis by querying the Phase-12 knowledge authority. Regenerates purely
    # from the immutable Phase-8 development records + Phase-11 reconciliation
    # records + the static Phase-12 knowledge; NO migration (DB stays v25). It
    # changes no outcome, working window, lockout or prediction calibration, and
    # authors no setup value. Never raises.
    # ------------------------------------------------------------------
    def build_mechanism_annotations(self, memory_context_key: str = "", **ctx) -> dict:
        """Annotate every eligible canonical diagnosis for a context with its
        physical mechanisms. Deterministic + regenerable + restart-identical: a pure
        function of the immutable records and the static Phase-12 knowledge. Read-only."""
        try:
            from strategy.mechanism_annotation import annotations_from_memory
        except Exception as exc:  # pragma: no cover - defensive
            return {"ok": False, "error": f"phase13 import failed: {exc}"}
        memory_result = self.build_cross_session_memory(memory_context_key, **ctx)
        if not isinstance(memory_result, dict) or not memory_result.get("ok"):
            return {"ok": True, "annotations": [], "count": 0, "supported_count": 0,
                    "record_count": 0}
        calibration = self.build_prediction_calibration(memory_context_key, **ctx)
        context = {
            "driver": ctx.get("driver", ""), "car": ctx.get("car", ""),
            "track": ctx.get("track", ""), "layout": ctx.get("layout_id", ""),
            "discipline": ctx.get("discipline", ""),
            "context_fingerprint": memory_context_key or "",
        }
        result = annotations_from_memory(
            memory_result.get("memory") or {}, calibration=calibration, context=context)
        result["record_count"] = int(memory_result.get("record_count") or 0)
        return result

    # ------------------------------------------------------------------
    # Mechanism-constrained intervention hypotheses (Program 2, Phase 14 —
    # READ-ONLY). Converts each Phase-13 mechanism-annotated diagnosis into
    # scientifically-defensible controlled-test DIRECTIONS constrained by the
    # supported physical mechanism. It authors NO setup value, applies/approves
    # nothing, and mutates no diagnosis/outcome/working-window/calibration/
    # setup-history/active-setup. Reuses the Phase-13 annotation aggregate ONCE
    # (no per-hypothesis / per-experiment queries). NO migration (DB stays v25).
    # Never raises.
    # ------------------------------------------------------------------
    def build_intervention_hypotheses(self, memory_context_key: str = "", *,
                                      gearbox_state: str = "", speed_context: str = "",
                                      driver_preference: "dict | None" = None,
                                      outcome_history=None, **ctx) -> dict:
        """Build mechanism-constrained intervention hypotheses for a context. Composes the
        Phase-13 ``build_mechanism_annotations`` aggregate exactly once, then runs the pure
        Phase-14 reasoning. Deterministic + regenerable + restart-identical. Read-only."""
        try:
            from strategy.intervention_hypothesis import hypotheses_from_report
        except Exception as exc:  # pragma: no cover - defensive
            return {"ok": False, "error": f"phase14 import failed: {exc}"}
        report = self.build_mechanism_annotations(memory_context_key, **ctx)
        if not isinstance(report, dict) or not report.get("ok"):
            return {"ok": True, "hypothesis_sets": [], "count": 0, "sets_with_testable": 0}
        result = hypotheses_from_report(
            report, gearbox_state=gearbox_state, speed_context=speed_context,
            driver_preference=driver_preference, outcome_history=outcome_history)
        result["record_count"] = int(report.get("record_count") or 0)
        return result

    # ------------------------------------------------------------------
    # Minimum-effective bounded setup-experiment synthesis (Program 2,
    # Phase 15 - READ-ONLY). Converts each eligible Phase-14 intervention
    # hypothesis into the SMALLEST legal, reversible numeric setup experiment
    # off the canonical applied setup baseline. It authors no final tune,
    # applies/approves/persists nothing, mutates no diagnosis/mechanism/outcome/
    # calibration/setup-history/active-setup, and reuses the Phase-14
    # intervention aggregate ONCE (no per-hypothesis / per-field queries). The
    # canonical applied setup is supplied by the caller's ActiveSetupAuthority
    # (SessionDB does not own it). NO migration (DB stays v25). Never raises.
    # ------------------------------------------------------------------
    def build_bounded_setup_experiments(self, memory_context_key: str = "", *,
                                        applied_setup: "dict | None" = None,
                                        session_identity: "dict | None" = None,
                                        gearbox_state: str = "", speed_context: str = "",
                                        driver_preference: "dict | None" = None,
                                        outcome_history=None,
                                        larger_step_justifications: "dict | None" = None,
                                        **ctx) -> dict:
        """Synthesise bounded setup experiments for a context. Composes the Phase-14
        ``build_intervention_hypotheses`` aggregate exactly once and runs the pure Phase-15
        reasoning against the canonical applied setup baseline + legal ranges. Deterministic
        + regenerable + restart-identical. Read-only."""
        try:
            from strategy.experiment_synthesis import synthesize_from_report
            from strategy.setup_ranges import resolve_ranges
        except Exception as exc:  # pragma: no cover - defensive
            return {"ok": False, "error": f"phase15 import failed: {exc}"}
        report = self.build_intervention_hypotheses(
            memory_context_key, gearbox_state=gearbox_state, speed_context=speed_context,
            driver_preference=driver_preference, outcome_history=outcome_history, **ctx)
        if not isinstance(report, dict) or not report.get("ok"):
            return {"ok": True, "synthesis_results": [], "count": 0, "ready_for_preflight": 0}
        car = str(ctx.get("car", "") or "")
        try:
            ranges = resolve_ranges(car) if car else {}
        except Exception:
            ranges = {}
        identity = session_identity or {
            "car": car, "track": str(ctx.get("track", "") or ""),
            "layout_id": str(ctx.get("layout_id", "") or "")}
        result = synthesize_from_report(
            report, applied_setup=applied_setup, session_identity=identity, ranges=ranges,
            working_windows={}, gearbox_state=gearbox_state,
            larger_step_justifications=larger_step_justifications)
        result["record_count"] = int(report.get("record_count") or 0)
        return result

    # ------------------------------------------------------------------
    # Guarded experiment lifecycle & postflight loop closure (Program 2,
    # Phase 16 - READ-ONLY orchestration). Connects existing authorities: it
    # converts a READY Phase-15 bounded experiment into a canonical
    # SetupExperiment request (via build_experiment_from_recommendation), routes
    # it through the EXISTING Phase-10 preflight, and assembles a read-only
    # closed-loop summary from the EXISTING Phase-3 outcome + Phase-11
    # reconciliation + prediction calibration. It APPLIES nothing, PERSISTS no
    # experiment, records no outcome/reconciliation, and mutates nothing - the
    # frozen Apply gate remains the sole mutation route. NO migration (DB v25).
    # Never raises.
    # ------------------------------------------------------------------
    def build_experiment_execution(self, candidate: dict, *, diagnosis_key: str = "",
                                   car: str = "", track: str = "", layout_id: str = "",
                                   discipline: str = "", driver: str = "",
                                   gt7_version: str = "", compound: str = "") -> dict:
        """Convert ONE READY Phase-15 candidate into a canonical experiment request and route
        it through the EXISTING Phase-10 preflight. Read-only: builds + validates only, writes
        nothing, applies nothing. Deterministic."""
        try:
            from strategy.experiment_lifecycle import (
                build_execution_request, assemble_execution_result)
        except Exception as exc:  # pragma: no cover - defensive
            return {"ok": False, "error": f"phase16 import failed: {exc}"}
        scope = {"car": car, "track": track, "layout_id": layout_id, "discipline": discipline,
                 "issue_type": str((candidate or {}).get("canonical_issue", {}).get("issue_type")
                                   or "")}
        request = build_execution_request(candidate, diagnosis_key=diagnosis_key, scope=scope)
        review = None
        if request.actionable and request.selection.get("field"):
            review = self.build_experiment_preflight(
                request.selection, car=car, track=track, layout_id=layout_id,
                discipline=discipline, driver=driver, gt7_version=gt7_version,
                compound=compound)
        result = assemble_execution_result(request, review)
        return {"ok": True, **result.to_dict()}

    def build_engineering_lifecycle(self, memory_context_key: str = "", *,
                                    applied_setup: "dict | None" = None,
                                    session_identity: "dict | None" = None,
                                    gearbox_state: str = "", speed_context: str = "",
                                    **ctx) -> dict:
        """Aggregate read-only lifecycle overview for a context: for each diagnosis, the full
        chain diagnosis -> mechanism -> hypothesis -> synthesis (forward) plus the EXISTING
        aggregate closed-loop state (prediction calibration + reconciliation records). Reuses
        the Phase-15 aggregate ONCE (no per-diagnosis DB scan). Read-only; never writes."""
        try:
            from strategy.experiment_lifecycle import (
                assemble_lifecycle_summary, EXPERIMENT_LIFECYCLE_VERSION, knowledge_versions)
        except Exception as exc:  # pragma: no cover - defensive
            return {"ok": False, "error": f"phase16 import failed: {exc}"}
        synth = self.build_bounded_setup_experiments(
            memory_context_key, applied_setup=applied_setup, session_identity=session_identity,
            gearbox_state=gearbox_state, speed_context=speed_context, **ctx)
        if not isinstance(synth, dict) or not synth.get("ok"):
            return {"ok": True, "stages": [], "count": 0, "ready_count": 0,
                    "calibration": {"reconciliations": 0}, "reconciliation_count": 0}
        calibration = self.build_prediction_calibration(memory_context_key, **ctx) or {}
        recon_records = self.get_reconciliation_records(memory_context_key, **ctx) or []
        calib_summary = calibration.get("calibration") or {}
        latest_recon = recon_records[-1] if recon_records else {}

        stages = []
        ready = 0
        for res in synth.get("synthesis_results") or []:
            hset = res.get("source_hypothesis_set") or {}
            candidate = res.get("selected_candidate") or (
                res.get("alternative_candidates") or [None])[0]
            if res.get("overall_status") == "ready_for_preflight":
                ready += 1
            summary = assemble_lifecycle_summary(
                candidate=candidate or {}, hypothesis_set=hset,
                annotation=hset.get("source_annotation") or {},
                calibration=calib_summary, reconciliation=latest_recon,
                preflight_state=("ready" if candidate and
                                 candidate.get("status") == "ready_for_preflight" else "n/a"),
                diagnosis_key=str(hset.get("source_diagnosis_key") or ""))
            stages.append(summary.to_dict())

        kv = knowledge_versions()
        import hashlib as _h
        import json as _j
        fp = (f"{EXPERIMENT_LIFECYCLE_VERSION}:lifecycle:"
              + _h.sha256(_j.dumps(
                  {"n": len(stages), "fps": [s["content_fingerprint"] for s in stages],
                   "calib": calib_summary.get("reconciliations", 0), "kv": kv},
                  sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()[:24])
        return {"ok": True, "version": EXPERIMENT_LIFECYCLE_VERSION, "stages": stages,
                "count": len(stages), "ready_count": ready,
                "calibration": calib_summary,
                "reconciliation_count": len(recon_records),
                "knowledge_versions": kv, "content_fingerprint": fp,
                "record_count": int(synth.get("record_count") or 0)}

    # ------------------------------------------------------------------
    # Experiment portfolio optimisation & information-gain selection
    # (Program 2, Phase 17 - READ-ONLY planner). Ranks the legal Phase-15
    # bounded experiments by ENGINEERING VALUE (information gain first), models
    # dependencies, retires experiments with no remaining value, and emits an
    # advisory roadmap. It replaces no authority - it CONSUMES the Phase-15
    # synthesis aggregate (reused ONCE) + the prediction calibration. It applies
    # nothing, writes nothing, and mutates no setup/experiment/outcome/
    # calibration. NO migration (DB v25). Never raises.
    # ------------------------------------------------------------------
    def build_experiment_portfolio(self, memory_context_key: str = "", *,
                                   applied_setup: "dict | None" = None,
                                   session_identity: "dict | None" = None,
                                   gearbox_state: str = "", speed_context: str = "",
                                   session_context: "dict | None" = None,
                                   outcome_history=None, **ctx) -> dict:
        """Rank the legal experiments for a context by engineering value. Composes the
        Phase-15 ``build_bounded_setup_experiments`` aggregate exactly once + the prediction
        calibration, then runs the pure Phase-17 planner. Deterministic + regenerable +
        restart-identical. Read-only."""
        try:
            from strategy.experiment_portfolio import build_portfolio
        except Exception as exc:  # pragma: no cover - defensive
            return {"ok": False, "error": f"phase17 import failed: {exc}"}
        synth = self.build_bounded_setup_experiments(
            memory_context_key, applied_setup=applied_setup, session_identity=session_identity,
            gearbox_state=gearbox_state, speed_context=speed_context, **ctx)
        if not isinstance(synth, dict) or not synth.get("ok"):
            return {"ok": True, "portfolio": None, "count": 0}
        calibration = self.build_prediction_calibration(memory_context_key, **ctx) or {}
        portfolio = build_portfolio(
            synth, outcome_history=outcome_history, calibration=calibration,
            session_context=session_context or {})
        result = portfolio.to_dict()
        return {"ok": True, "portfolio": result,
                "count": len(result.get("valuations") or []),
                "content_fingerprint": result.get("content_fingerprint"),
                "record_count": int(synth.get("record_count") or 0)}

    # ------------------------------------------------------------------
    # Engineering campaigns & multi-session development planning (Program 2,
    # Phase 18 - READ-ONLY). Groups the Phase-17 experiment portfolio into
    # coherent multi-session engineering CAMPAIGNS and projects the existing
    # outcome / reconciliation / calibration evidence. It ranks nothing itself
    # (Phase 17 owns ranking), executes nothing (Phase 16 owns the lifecycle),
    # applies nothing, writes nothing, and never marks a successful-but-
    # unvalidated objective complete. Reuses the Phase-17 portfolio aggregate
    # ONCE + one development-record read + one calibration read (no per-campaign
    # / per-diagnosis query). NO migration (DB v25). Never raises.
    # ------------------------------------------------------------------
    def build_engineering_campaign_programme(self, memory_context_key: str = "", *,
                                             applied_setup: "dict | None" = None,
                                             session_identity: "dict | None" = None,
                                             gearbox_state: str = "", speed_context: str = "",
                                             session_context: "dict | None" = None, **ctx) -> dict:
        """Build the read-only engineering-campaign programme for a context. Composes the
        Phase-17 ``build_experiment_portfolio`` aggregate exactly once, projects the immutable
        development records (multi-session outcomes) + prediction calibration, and runs the
        pure Phase-18 planner. Deterministic + regenerable + restart-identical. Read-only."""
        try:
            from strategy.engineering_campaign import build_campaign_programme
        except Exception as exc:  # pragma: no cover - defensive
            return {"ok": False, "error": f"phase18 import failed: {exc}"}
        # multi-session outcome history from the immutable development records (one read).
        # Fed to Phase 17 so its retirement/dependency logic (the ranking authority) sees the
        # prior confirmed / regressed directions, and to Phase 18 for the campaign projection.
        outcome_history = self._campaign_outcome_history(memory_context_key, **ctx)
        portfolio_result = self.build_experiment_portfolio(
            memory_context_key, applied_setup=applied_setup, session_identity=session_identity,
            gearbox_state=gearbox_state, speed_context=speed_context,
            outcome_history=outcome_history, **ctx)
        if not isinstance(portfolio_result, dict) or not portfolio_result.get("ok"):
            return {"ok": True, "programme": None, "campaign_count": 0}
        portfolio = portfolio_result.get("portfolio") or {}
        calibration = self.build_prediction_calibration(memory_context_key, **ctx) or {}
        scope = {
            "driver": str(ctx.get("driver", "") or ""), "car": str(ctx.get("car", "") or ""),
            "track": str(ctx.get("track", "") or ""),
            "layout_id": str(ctx.get("layout_id", "") or ""),
            "discipline": str(ctx.get("discipline", "") or ""),
            "gt7_version": str(ctx.get("gt7_version", "") or ""),
        }
        active_context = dict(scope)
        if isinstance(applied_setup, dict):
            # detect a stale campaign context from the actual applied-setup identity.
            active_context = {
                "car": str(applied_setup.get("car", scope["car"]) or ""),
                "track": str(applied_setup.get("track", scope["track"]) or ""),
                "layout_id": str(applied_setup.get("layout_id", scope["layout_id"]) or ""),
                "discipline": scope["discipline"], "gt7_version": scope["gt7_version"],
                "driver": scope["driver"],
            }
        programme = build_campaign_programme(
            portfolio, outcome_history=outcome_history, calibration=calibration,
            active_context=active_context, session_context=session_context or {}, scope=scope)
        result = programme.to_dict()
        return {"ok": True, "programme": result,
                "campaign_count": len(result.get("campaigns") or []),
                "content_fingerprint": result.get("content_fingerprint"),
                "record_count": int(portfolio_result.get("record_count") or 0)}

    def _campaign_outcome_history(self, memory_context_key: str = "", **ctx) -> list:
        """Project the immutable Phase-8 development records into the {fields, direction,
        outcome_status, session, single_field} shape the Phase-18 planner consumes. Read-only;
        one query; never raises; never invents facts."""
        try:
            records = self.get_development_records(memory_context_key, **ctx)
        except Exception:  # pragma: no cover
            return []
        out = []
        for rec in records or []:
            if not isinstance(rec, dict):
                continue
            status = str(rec.get("outcome_status") or "").strip().lower()
            changes = rec.get("changes") or []
            single = len(changes) == 1
            for ch in changes:
                if not isinstance(ch, dict):
                    continue
                fld = str(ch.get("field") or "").strip().lower()
                if not fld:
                    continue
                direction = ""
                try:
                    fv = ch.get("from_value")
                    tv = ch.get("to_value")
                    if fv not in (None, "") and tv not in (None, ""):
                        direction = "increase" if float(tv) > float(fv) else "decrease"
                except (TypeError, ValueError):
                    direction = ""
                out.append({
                    "fields": [fld], "direction": direction, "outcome_status": status,
                    "session_id": str(rec.get("test_session_id") or rec.get("session_date") or ""),
                    "single_field": single, "experiment_id": str(rec.get("experiment_id") or ""),
                    "compatible": True,
                })
        return out

    # ------------------------------------------------------------------
    # Campaign persistence, evidence saturation & cost of knowledge
    # (Program 2, Phase 19). The engineering NOTEBOOK: an additive,
    # metadata-only campaign registry (DB v26) that lets campaigns survive
    # across sessions, plus a READ-ONLY "engineering efficiency" advisory
    # (campaign age + evidence saturation + cost-of-knowledge + budget fit).
    # It owns no engineering logic, ranks nothing, applies/approves/freezes/
    # creates/executes nothing, and mutates no setup / experiment / outcome /
    # calibration. The ONLY write here is the metadata registry upsert
    # (record_engineering_campaigns), which is idempotent and additive.
    # ------------------------------------------------------------------
    def record_engineering_campaigns(self, programme: dict, *, session_id: str = "",
                                     recorded_at: str = "") -> dict:
        """Persist the METADATA of a Phase-18 campaign programme into the additive campaign
        registry (DB v26). Idempotent: ``first_seen`` / ``creation_session`` are preserved on
        re-record; ``last_seen`` / ``last_updated`` / ``completion_state`` / links are refreshed.
        Metadata only — it writes no setup / experiment / outcome. ``recorded_at`` is supplied
        (never the clock). Never raises."""
        try:
            from strategy.campaign_persistence import registry_entry_from_campaign
        except Exception as exc:  # pragma: no cover - defensive
            return {"ok": False, "error": f"phase19 import failed: {exc}"}
        if not isinstance(programme, dict):
            return {"ok": True, "recorded": 0}
        import json as _json
        recorded = 0
        with self._lock:
            for camp in programme.get("campaigns") or []:
                try:
                    e = registry_entry_from_campaign(camp, session_id=session_id,
                                                     recorded_at=recorded_at)
                except Exception:
                    continue
                if not e.campaign_id:
                    continue
                # INSERT OR IGNORE preserves first_seen/creation_session on re-record.
                self._conn.execute(
                    "INSERT OR IGNORE INTO engineering_campaign_registry "
                    "(campaign_id, car, track, layout, discipline, objective_family, "
                    "objective_region, gt7_version, creation_session, first_seen, last_seen, "
                    "last_updated, completion_state, linked_development_records, "
                    "linked_experiments, linked_outcomes) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (e.campaign_id, e.car, e.track, e.layout, e.discipline, e.objective_family,
                     e.objective_region, e.gt7_version, e.creation_session, e.first_seen,
                     e.last_seen, e.last_updated, e.completion_state,
                     _json.dumps(list(e.linked_development_records)),
                     _json.dumps(list(e.linked_experiments)),
                     _json.dumps(list(e.linked_outcomes))))
                # Refresh only the mutable-metadata columns (never first_seen / notes /
                # manual_archive_flag which are user/point-in-time owned).
                self._conn.execute(
                    "UPDATE engineering_campaign_registry SET last_seen=?, last_updated=?, "
                    "completion_state=?, linked_experiments=? WHERE campaign_id=?",
                    (e.last_seen, e.last_updated, e.completion_state,
                     _json.dumps(list(e.linked_experiments)), e.campaign_id))
                recorded += 1
            self._conn.commit()
        return {"ok": True, "recorded": recorded}

    def get_campaign_registry(self, *, car: str = "", track: str = "", layout_id: str = "",
                              discipline: str = "") -> list[dict]:
        """Return campaign-registry rows scoped to the context (all when unscoped). Read-only;
        deterministic order (campaign_id); never raises."""
        clauses, params = [], []
        if car:
            clauses.append("car = ?"); params.append(str(car))
        if track:
            clauses.append("track = ?"); params.append(str(track))
        if layout_id:
            clauses.append("layout = ?"); params.append(str(layout_id))
        if discipline:
            clauses.append("discipline = ?"); params.append(str(discipline))
        sql = "SELECT * FROM engineering_campaign_registry"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY campaign_id ASC"
        try:
            with self._lock:
                rows = self._conn.execute(sql, tuple(params)).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def set_campaign_note(self, campaign_id: str, *, notes: str | None = None,
                          manual_archive_flag: bool | None = None,
                          abandonment_reason: str | None = None) -> dict:
        """Explicit user-authored campaign-notebook metadata update (notes / archive flag /
        abandonment reason). Metadata only; never touches engineering records. Idempotent."""
        sets, params = [], []
        if notes is not None:
            sets.append("notes = ?"); params.append(str(notes))
        if manual_archive_flag is not None:
            sets.append("manual_archive_flag = ?"); params.append(1 if manual_archive_flag else 0)
        if abandonment_reason is not None:
            sets.append("abandonment_reason = ?"); params.append(str(abandonment_reason))
        if not sets:
            return {"ok": True, "updated": 0}
        try:
            with self._lock:
                cur = self._conn.execute(
                    "UPDATE engineering_campaign_registry SET " + ", ".join(sets)
                    + " WHERE campaign_id = ?", tuple(params) + (str(campaign_id),))
                self._conn.commit()
            return {"ok": True, "updated": cur.rowcount}
        except Exception as exc:  # pragma: no cover - defensive
            return {"ok": False, "error": str(exc)}

    def build_engineering_efficiency(self, memory_context_key: str = "", *,
                                     applied_setup: "dict | None" = None,
                                     session_identity: "dict | None" = None,
                                     gearbox_state: str = "", speed_context: str = "",
                                     session_context: "dict | None" = None,
                                     session_budget: "dict | None" = None,
                                     now_date: str = "",
                                     register_session_id: str = "",
                                     recorded_at: str = "", **ctx) -> dict:
        """Build the Engineering Efficiency advisory: campaign age (from the registry) +
        evidence saturation + cost of knowledge + budget fit. Composes the Phase-18 campaign
        programme ONCE + the campaign registry read; runs the pure Phase-19 estimators.
        Deterministic; regenerable; never raises.

        READ-ONLY by default: writes nothing. When (and only when) ``register_session_id`` is a
        non-empty string, it additionally performs the phase's single, idempotent, additive
        registry capture (``record_engineering_campaigns``) as a best-effort side effect BEFORE
        reading the registry — so a freshly observed campaign's age/first-seen provenance is
        available. The write never governs completion, never mutates a setup/experiment/outcome,
        and never affects the returned advisory beyond the age/first-seen provenance it records."""
        try:
            from strategy.campaign_persistence import build_engineering_efficiency as _eff
        except Exception as exc:  # pragma: no cover - defensive
            return {"ok": False, "error": f"phase19 import failed: {exc}"}
        prog_result = self.build_engineering_campaign_programme(
            memory_context_key, applied_setup=applied_setup, session_identity=session_identity,
            gearbox_state=gearbox_state, speed_context=speed_context,
            session_context=session_context, **ctx)
        if not isinstance(prog_result, dict) or not prog_result.get("ok"):
            return {"ok": True, "efficiency": None, "campaign_count": 0}
        programme = prog_result.get("programme") or {}
        # OPT-IN registry capture (the only Phase-19 write). Best-effort: a capture failure
        # never breaks the advisory. Absent register_session_id → this method writes nothing.
        if str(register_session_id or "").strip():
            try:
                self.record_engineering_campaigns(
                    programme, session_id=str(register_session_id),
                    recorded_at=str(recorded_at or ""))
            except Exception:  # pragma: no cover - defensive
                pass
        registry = self.get_campaign_registry(
            car=str(ctx.get("car", "") or ""), track=str(ctx.get("track", "") or ""),
            layout_id=str(ctx.get("layout_id", "") or ""),
            discipline=str(ctx.get("discipline", "") or ""))
        efficiency = _eff(programme, registry=registry, session_budget=session_budget or {},
                          now_date=now_date)
        result = efficiency.to_dict()
        return {"ok": True, "efficiency": result,
                "campaign_count": len(result.get("campaigns") or []),
                "content_fingerprint": result.get("content_fingerprint"),
                "record_count": int(prog_result.get("record_count") or 0)}

    def build_engineering_knowledge_quality(self, memory_context_key: str = "", *,
                                            applied_setup: "dict | None" = None,
                                            session_identity: "dict | None" = None,
                                            gearbox_state: str = "", speed_context: str = "",
                                            session_context: "dict | None" = None,
                                            session_budget: "dict | None" = None,
                                            now_date: str = "", **ctx) -> dict:
        """Build the READ-ONLY Engineering Knowledge Quality advisory (Program 2, Phase 20):
        per-campaign confidence-weighted knowledge quality + development ROI + campaign
        opportunity. Composes the Phase-19 Engineering Efficiency view ONCE (which itself reuses
        the Phase-18 programme once — no N+1) plus one Phase-11 prediction-calibration read, then
        runs the pure Phase-20 estimators. It ranks / prioritises / sorts NOTHING, writes
        nothing, completes nothing; deterministic; regenerable; never raises."""
        try:
            from strategy.knowledge_quality import build_knowledge_quality as _bkq
        except Exception as exc:  # pragma: no cover - defensive
            return {"ok": False, "error": f"phase20 import failed: {exc}"}
        # READ-ONLY efficiency (no register_session_id -> no registry write).
        eff_result = self.build_engineering_efficiency(
            memory_context_key, applied_setup=applied_setup, session_identity=session_identity,
            gearbox_state=gearbox_state, speed_context=speed_context,
            session_context=session_context, session_budget=session_budget, now_date=now_date,
            **ctx)
        if not isinstance(eff_result, dict) or not eff_result.get("ok"):
            return {"ok": True, "knowledge_quality": None, "campaign_count": 0}
        efficiency = eff_result.get("efficiency")
        if not isinstance(efficiency, dict) or not (efficiency.get("campaigns") or []):
            return {"ok": True, "knowledge_quality": None, "campaign_count": 0}
        calibration = self.build_prediction_calibration(memory_context_key, **ctx) or {}
        quality = _bkq(efficiency, calibration=calibration)
        result = quality.to_dict()
        return {"ok": True, "knowledge_quality": result,
                "campaign_count": len(result.get("campaigns") or []),
                "content_fingerprint": result.get("content_fingerprint")}

    def build_season_engineering_report(self, memory_context_key: str = "", *,
                                        applied_setup: "dict | None" = None,
                                        session_identity: "dict | None" = None,
                                        gearbox_state: str = "", speed_context: str = "",
                                        session_context: "dict | None" = None,
                                        session_budget: "dict | None" = None,
                                        now_date: str = "", **ctx) -> dict:
        """Build the READ-ONLY Season Engineering Report (Program 2, Phase 21): the Engineering
        Director's whole-programme view — season summary + cross-campaign relationship map +
        per-campaign knowledge map. Composes the Phase-18 campaign programme ONCE, derives the
        Phase-19 efficiency and Phase-20 knowledge-quality views purely from it (+ one registry
        read + one calibration read — no N+1, no double programme build), then runs the pure
        Phase-21 aggregators. It schedules / ranks / prioritises / completes / writes NOTHING;
        deterministic; regenerable; never raises."""
        try:
            from strategy.campaign_persistence import build_engineering_efficiency as _eff
            from strategy.knowledge_quality import build_knowledge_quality as _bkq
            from strategy.season_engineering_report import build_season_report as _bsr
        except Exception as exc:  # pragma: no cover - defensive
            return {"ok": False, "error": f"phase21 import failed: {exc}"}
        prog_result = self.build_engineering_campaign_programme(
            memory_context_key, applied_setup=applied_setup, session_identity=session_identity,
            gearbox_state=gearbox_state, speed_context=speed_context,
            session_context=session_context, **ctx)
        if not isinstance(prog_result, dict) or not prog_result.get("ok"):
            return {"ok": True, "season_report": None, "campaign_count": 0}
        programme = prog_result.get("programme") or {}
        if not (programme.get("campaigns") or []):
            return {"ok": True, "season_report": None, "campaign_count": 0}
        # READ-ONLY: reuse the campaign registry (no write) so campaign age is available to the
        # Phase-19 view; then derive efficiency + quality purely (no further programme build).
        registry = self.get_campaign_registry(
            car=str(ctx.get("car", "") or ""), track=str(ctx.get("track", "") or ""),
            layout_id=str(ctx.get("layout_id", "") or ""),
            discipline=str(ctx.get("discipline", "") or ""))
        efficiency = _eff(programme, registry=registry, session_budget=session_budget or {},
                          now_date=now_date).to_dict()
        calibration = self.build_prediction_calibration(memory_context_key, **ctx) or {}
        quality = _bkq(efficiency, calibration=calibration).to_dict()
        report = _bsr(programme, efficiency, quality).to_dict()
        return {"ok": True, "season_report": report,
                "campaign_count": len(report.get("campaigns") or []),
                "content_fingerprint": report.get("content_fingerprint")}

    def _distinct_engineering_contexts(self) -> list:
        """Return the distinct event contexts present in the immutable development records — one
        SELECT DISTINCT (bounded by number of events, not campaigns). Read-only; never raises."""
        try:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT DISTINCT car, track, layout_id, discipline, driver, gt7_version, "
                    "compound, memory_context_key FROM engineering_development_records "
                    "ORDER BY car, discipline, gt7_version, driver, track, layout_id").fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def build_programme_knowledge_report(self, memory_context_key: str = "", *,
                                         applied_setup: "dict | None" = None,
                                         session_identity: "dict | None" = None,
                                         gearbox_state: str = "", speed_context: str = "",
                                         session_context: "dict | None" = None,
                                         session_budget: "dict | None" = None,
                                         now_date: str = "", **ctx) -> dict:
        """Build the READ-ONLY Programme Knowledge Report (Program 2, Phase 22): the Engineering
        Knowledge Graph rolled up across compatible events. Enumerates the distinct event contexts
        (one SELECT DISTINCT), builds the Phase-21 season report ONCE for each context COMPATIBLE
        with the current one (same car / discipline / GT7 version / driver — different tracks may
        merge), enriches each campaign with its Phase-21 knowledge state, and runs the pure
        Phase-22 aggregators. Incompatible contexts are surfaced as separate programme groups (with
        the reason) but not merged. It ranks / schedules / completes / writes NOTHING; DB stays
        v26 (no persistence); deterministic; regenerable; never raises."""
        try:
            from strategy.programme_knowledge_report import build_programme_knowledge as _bpk
            from strategy.multi_event_rollup import COMPATIBILITY_FIELDS
        except Exception as exc:  # pragma: no cover - defensive
            return {"ok": False, "error": f"phase22 import failed: {exc}"}

        def _compat(d):
            return tuple(str(d.get(f, "") or "").strip().lower() for f in COMPATIBILITY_FIELDS)

        primary_ctx = {"car": str(ctx.get("car", "") or ""),
                       "discipline": str(ctx.get("discipline", "") or ""),
                       "gt7_version": str(ctx.get("gt7_version", "") or ""),
                       "driver": str(ctx.get("driver", "") or "")}
        primary_key = _compat(primary_ctx)

        contexts = self._distinct_engineering_contexts()
        if not contexts:
            # fall back to the caller's context alone (empty DB / no records)
            contexts = [{"car": primary_ctx["car"], "track": str(ctx.get("track", "") or ""),
                         "layout_id": str(ctx.get("layout_id", "") or ""),
                         "discipline": primary_ctx["discipline"],
                         "driver": primary_ctx["driver"],
                         "gt7_version": primary_ctx["gt7_version"],
                         "compound": str(ctx.get("compound", "") or ""),
                         "memory_context_key": memory_context_key}]

        events = []
        for row in contexts:
            ev_ctx = {"car": row.get("car", ""), "track": row.get("track", ""),
                      "layout": row.get("layout_id", ""), "discipline": row.get("discipline", ""),
                      "gt7_version": row.get("gt7_version", ""), "driver": row.get("driver", "")}
            # Only build the (heavy) season report for events in the PRIMARY compatibility group;
            # incompatible events are listed as separate groups without campaigns.
            if _compat({**ev_ctx, "car": row.get("car", "")}) == primary_key:
                season = self.build_season_engineering_report(
                    str(row.get("memory_context_key", "") or ""), applied_setup=applied_setup,
                    session_identity=session_identity, gearbox_state=gearbox_state,
                    speed_context=speed_context, session_context=session_context,
                    session_budget=session_budget, now_date=now_date,
                    car=row.get("car", ""), track=row.get("track", ""),
                    layout_id=row.get("layout_id", ""), discipline=row.get("discipline", ""),
                    driver=row.get("driver", ""), gt7_version=row.get("gt7_version", ""),
                    compound=row.get("compound", ""))
                campaigns = self._enrich_campaigns_with_state(season)
                events.append({"context": ev_ctx, "campaigns": campaigns})
            else:
                events.append({"context": ev_ctx, "campaigns": []})

        report = _bpk(events, primary_context=primary_ctx).to_dict()
        graph = report.get("knowledge_graph") or {}
        return {"ok": True, "programme_knowledge": report,
                "known_domain_count": len(graph.get("known_domains") or []),
                "content_fingerprint": report.get("content_fingerprint")}

    @staticmethod
    def _enrich_campaigns_with_state(season_result: dict) -> list:
        """Attach each campaign's Phase-21 knowledge_state (from the season report's knowledge_map)
        to its normalised record — a join, NOT a recomputation. Never raises."""
        if not isinstance(season_result, dict) or not season_result.get("ok"):
            return []
        report = season_result.get("season_report") or {}
        if not isinstance(report, dict):
            return []
        states = {}
        for k in report.get("knowledge_map") or []:
            if isinstance(k, dict):
                states[str(k.get("campaign_id") or "")] = str(k.get("state") or "")
        out = []
        for c in report.get("campaigns") or []:
            if not isinstance(c, dict):
                continue
            rec = dict(c)
            rec["knowledge_state"] = states.get(str(c.get("campaign_id") or ""), "")
            out.append(rec)
        return out

    def build_programme_transfer_report(self, memory_context_key: str = "", *,
                                        applied_setup: "dict | None" = None,
                                        session_identity: "dict | None" = None,
                                        gearbox_state: str = "", speed_context: str = "",
                                        session_context: "dict | None" = None,
                                        session_budget: "dict | None" = None,
                                        now_date: str = "", **ctx) -> dict:
        """Build the READ-ONLY Programme Transfer Report (Program 2, Phase 23): whether the
        current programme's ESTABLISHED domain knowledge is likely reusable in other engineering
        contexts (other cars / disciplines). Composes the Phase-22 programme knowledge report ONCE
        (its established source domains + the other compatibility groups as targets), then runs the
        pure Phase-23 transfer evaluation + reuse summary. It transfers NO setup values, recommends
        applying NOTHING, writes NOTHING; DB stays v26 (no persistence); deterministic; never
        raises."""
        try:
            from strategy.programme_transfer_report import build_transfer_report as _btr
        except Exception as exc:  # pragma: no cover - defensive
            return {"ok": False, "error": f"phase23 import failed: {exc}"}
        pk_result = self.build_programme_knowledge_report(
            memory_context_key, applied_setup=applied_setup, session_identity=session_identity,
            gearbox_state=gearbox_state, speed_context=speed_context,
            session_context=session_context, session_budget=session_budget, now_date=now_date,
            **ctx)
        if not isinstance(pk_result, dict) or not pk_result.get("ok"):
            return {"ok": True, "transfer_report": None, "candidate_count": 0}
        programme = pk_result.get("programme_knowledge")
        if not isinstance(programme, dict) or not programme.get("knowledge_graph"):
            return {"ok": True, "transfer_report": None, "candidate_count": 0}
        graph = programme.get("knowledge_graph") or {}
        compatibility = programme.get("compatibility") or {}
        source_ctx = dict(compatibility.get("primary_key") or {})
        # targets = the OTHER compatibility groups surfaced by Phase 22 (other cars / disciplines).
        targets = [dict(g.get("compatibility_key") or {})
                   for g in (compatibility.get("other_groups") or [])
                   if isinstance(g, dict) and (g.get("compatibility_key") or {})]
        report = _btr(graph, source_ctx, targets).to_dict()
        return {"ok": True, "transfer_report": report,
                "candidate_count": len(report.get("candidates") or []),
                "content_fingerprint": report.get("content_fingerprint")}

    def build_programme_engineering_playbook(self, memory_context_key: str = "", *,
                                             applied_setup: "dict | None" = None,
                                             session_identity: "dict | None" = None,
                                             gearbox_state: str = "", speed_context: str = "",
                                             session_context: "dict | None" = None,
                                             session_budget: "dict | None" = None,
                                             now_date: str = "", **ctx) -> dict:
        """Build the READ-ONLY cross-programme Engineering Playbook (Program 2, Phase 24): the
        reusable engineering knowledge across the driver's car stable, assembled into a
        deterministic INVESTIGATION playbook (never a baseline setup).

        Composes the Phase-22 programme knowledge report EXACTLY ONCE (the only heavy DB
        reconstruction), derives the Phase-23 transfer report PURELY from that same programme (no
        second Phase-22 build), then runs the pure Phase-24 assembler. It generates NO setup
        values, copies NO fields, applies / schedules / persists NOTHING; DB stays v26 (no
        persistence); deterministic; regenerable; never raises. No N+1 - the per-target work is
        pure (no reads inside any target loop)."""
        try:
            from strategy.programme_transfer_report import build_transfer_report as _btr
            from strategy.engineering_playbook import build_engineering_playbook as _bep
        except Exception as exc:  # pragma: no cover - defensive
            return {"ok": False, "error": f"phase24 import failed: {exc}"}
        # ONE Phase-22 DB reconstruction.
        pk_result = self.build_programme_knowledge_report(
            memory_context_key, applied_setup=applied_setup, session_identity=session_identity,
            gearbox_state=gearbox_state, speed_context=speed_context,
            session_context=session_context, session_budget=session_budget, now_date=now_date,
            **ctx)
        if not isinstance(pk_result, dict) or not pk_result.get("ok"):
            return {"ok": True, "playbook": None, "theme_count": 0}
        programme = pk_result.get("programme_knowledge")
        graph = programme.get("knowledge_graph") if isinstance(programme, dict) else None
        if not isinstance(graph, dict) or not (graph.get("known_domains") or []):
            # honest empty state — no established engineering knowledge to build a playbook from.
            return {"ok": True, "playbook": None, "theme_count": 0}
        compatibility = programme.get("compatibility") or {}
        source_ctx = dict(compatibility.get("primary_key") or {})
        targets = [dict(g.get("compatibility_key") or {})
                   for g in (compatibility.get("other_groups") or [])
                   if isinstance(g, dict) and (g.get("compatibility_key") or {})]
        # PURE Phase-23 transfer build (no DB) + PURE Phase-24 assembly.
        transfer = _btr(graph, source_ctx, targets).to_dict()
        playbook = _bep(programme, transfer).to_dict()
        return {"ok": True, "playbook": playbook,
                "theme_count": len(playbook.get("stable_themes") or []),
                "content_fingerprint": playbook.get("content_fingerprint")}

    def _timeline_evidence_records(self, car: str = "", discipline: str = "",
                                   gt7_version: str = "", driver: str = "") -> list:
        """ONE bounded bulk read of the immutable development records for a compatibility group
        (car + discipline + gt7-version + driver, across all tracks/layouts/compounds). A single
        SELECT — its result grows with records but its query COUNT does not. Read-only; oldest
        first for stable retrieval (the pure layer re-orders deterministically). Never raises."""
        import json as _json
        clauses, params = [], []
        for col, val in (("car", car), ("discipline", discipline), ("gt7_version", gt7_version),
                         ("driver", driver)):
            if str(val or ""):
                clauses.append(f"{col}=?")
                params.append(str(val))
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        try:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT record_json FROM engineering_development_records" + where
                    + " ORDER BY id ASC", tuple(params)).fetchall()
            out = []
            for r in rows:
                try:
                    out.append(_json.loads(r[0]))
                except Exception:
                    continue
            return out
        except Exception:
            return []

    def build_programme_knowledge_timeline(self, memory_context_key: str = "", *,
                                           applied_setup: "dict | None" = None,
                                           session_identity: "dict | None" = None,
                                           gearbox_state: str = "", speed_context: str = "",
                                           session_context: "dict | None" = None,
                                           session_budget: "dict | None" = None,
                                           now_date: str = "", **ctx) -> dict:
        """Build the READ-ONLY Programme Knowledge Timeline (Program 2, Phase 25): how engineering
        understanding evolved across compatible events, where evidence genuinely converged (through
        independent repeated evidence), where it remains unresolved, and where apparent repetition
        is only duplicated / dependent evidence.

        Composes the Phase-22 programme knowledge report EXACTLY ONCE (the only heavy DB
        reconstruction), derives the Phase-23 transfer report and the Phase-24 playbook PURELY from
        that same in-memory programme (never calls the Phase-23 or Phase-24 SessionDB entry points),
        performs ONE bounded bulk read of the immutable development records for the compatibility
        group, then runs the pure Phase-25 assembler. Read-only; no writes; no migration; no
        persistence; no N+1 (no reads inside any timeline / convergence loop); DB stays v26;
        deterministic; restart-identical; never raises."""
        try:
            from strategy.programme_transfer_report import build_transfer_report as _btr
            from strategy.engineering_playbook import build_engineering_playbook as _bep
            from strategy.programme_timeline_report import build_programme_timeline as _bpt
        except Exception as exc:  # pragma: no cover - defensive
            return {"ok": False, "error": f"phase25 import failed: {exc}"}
        # ONE Phase-22 DB reconstruction.
        pk_result = self.build_programme_knowledge_report(
            memory_context_key, applied_setup=applied_setup, session_identity=session_identity,
            gearbox_state=gearbox_state, speed_context=speed_context,
            session_context=session_context, session_budget=session_budget, now_date=now_date,
            **ctx)
        if not isinstance(pk_result, dict) or not pk_result.get("ok"):
            return {"ok": True, "timeline": None, "point_count": 0}
        programme = pk_result.get("programme_knowledge")
        graph = programme.get("knowledge_graph") if isinstance(programme, dict) else None
        if not isinstance(graph, dict) or not (graph.get("known_domains") or []):
            return {"ok": True, "timeline": None, "point_count": 0}
        compatibility = programme.get("compatibility") or {}
        source_ctx = dict(compatibility.get("primary_key") or {})
        targets = [dict(g.get("compatibility_key") or {})
                   for g in (compatibility.get("other_groups") or [])
                   if isinstance(g, dict) and (g.get("compatibility_key") or {})]
        # PURE Phase-23 + PURE Phase-24 (reuse the same in-memory programme; no recursion).
        transfer = _btr(graph, source_ctx, targets).to_dict()
        playbook = _bep(programme, transfer).to_dict()
        # ONE bounded bulk read of the historical evidence for this compatibility group.
        records = self._timeline_evidence_records(
            car=str(source_ctx.get("car", "") or ""),
            discipline=str(source_ctx.get("discipline", "") or ""),
            gt7_version=str(source_ctx.get("gt7_version", "") or ""),
            driver=str(source_ctx.get("driver", "") or ""))
        timeline = _bpt(programme, playbook, records).to_dict()
        return {"ok": True, "timeline": timeline,
                "point_count": len(timeline.get("timeline_points") or []),
                "content_fingerprint": timeline.get("content_fingerprint")}

    def _build_knowledge_chain(self, memory_context_key: str = "", *,
                               applied_setup=None, session_identity=None, gearbox_state="",
                               speed_context="", session_context=None, session_budget=None,
                               now_date="", **ctx):
        """Shared read-only in-memory chain for Phases 26+: build the Phase-22 programme knowledge
        report EXACTLY ONCE, derive the Phase-23 transfer, Phase-24 playbook and Phase-25 timeline
        PURELY from that same programme (+ one bounded evidence bulk read). It never calls the
        Phase-23/24/25 SessionDB entry points. Returns a dict {programme, transfer, playbook,
        timeline} or None when there is no known knowledge. Read-only; no N+1; never raises."""
        try:
            from strategy.programme_transfer_report import build_transfer_report as _btr
            from strategy.engineering_playbook import build_engineering_playbook as _bep
            from strategy.programme_timeline_report import build_programme_timeline as _bpt
        except Exception:  # pragma: no cover - defensive
            return None
        pk_result = self.build_programme_knowledge_report(
            memory_context_key, applied_setup=applied_setup, session_identity=session_identity,
            gearbox_state=gearbox_state, speed_context=speed_context,
            session_context=session_context, session_budget=session_budget, now_date=now_date,
            **ctx)
        if not isinstance(pk_result, dict) or not pk_result.get("ok"):
            return None
        programme = pk_result.get("programme_knowledge")
        graph = programme.get("knowledge_graph") if isinstance(programme, dict) else None
        if not isinstance(graph, dict) or not (graph.get("known_domains") or []):
            return None
        compatibility = programme.get("compatibility") or {}
        source_ctx = dict(compatibility.get("primary_key") or {})
        targets = [dict(g.get("compatibility_key") or {})
                   for g in (compatibility.get("other_groups") or [])
                   if isinstance(g, dict) and (g.get("compatibility_key") or {})]
        transfer = _btr(graph, source_ctx, targets).to_dict()
        playbook = _bep(programme, transfer).to_dict()
        records = self._timeline_evidence_records(
            car=str(source_ctx.get("car", "") or ""),
            discipline=str(source_ctx.get("discipline", "") or ""),
            gt7_version=str(source_ctx.get("gt7_version", "") or ""),
            driver=str(source_ctx.get("driver", "") or ""))
        timeline = _bpt(programme, playbook, records).to_dict()
        # Expose the bounded evidence records read here (the single bulk read) so later read-only
        # layers (Phase 27+) can derive per-domain context breadth WITHOUT a second DB query.
        return {"programme": programme, "transfer": transfer, "playbook": playbook,
                "timeline": timeline, "records": [dict(r) for r in records]}

    def build_programme_revalidation_report(self, memory_context_key: str = "", *,
                                            applied_setup=None, session_identity=None,
                                            gearbox_state="", speed_context="", session_context=None,
                                            session_budget=None, now_date="", **ctx) -> dict:
        """Build the READ-ONLY Programme Re-validation Report (Program 2, Phase 26): which
        established knowledge remains current and which may need re-validation because context /
        version changed or evidence weakened. Reuses the in-memory knowledge chain (Phase-22 built
        ONCE; Phase-23/24/25 derived purely; never calls their SessionDB entries), then runs the
        pure Phase-26 assembler. Read-only; no N+1; no writes; no migration; no wall-clock; DB stays
        v26; deterministic; never raises."""
        try:
            from strategy.programme_revalidation_report import build_revalidation_report as _brr
        except Exception as exc:  # pragma: no cover - defensive
            return {"ok": False, "error": f"phase26 import failed: {exc}"}
        chain = self._build_knowledge_chain(
            memory_context_key, applied_setup=applied_setup, session_identity=session_identity,
            gearbox_state=gearbox_state, speed_context=speed_context,
            session_context=session_context, session_budget=session_budget, now_date=now_date, **ctx)
        if chain is None:
            return {"ok": True, "revalidation": None, "domain_count": 0}
        report = _brr(chain["timeline"], chain["programme"]).to_dict()
        return {"ok": True, "revalidation": report,
                "domain_count": len(report.get("items") or []),
                "content_fingerprint": report.get("content_fingerprint")}

    def build_programme_evidence_coverage_report(self, memory_context_key: str = "", *,
                                                 applied_setup=None, session_identity=None,
                                                 gearbox_state="", speed_context="",
                                                 session_context=None, session_budget=None,
                                                 now_date="", **ctx) -> dict:
        """Build the READ-ONLY Programme Evidence Coverage & Blind-Spot Report (Program 2, Phase 27):
        where each known engineering domain's evidence is well supported and where MORE evidence
        would help (a blind spot is not a fault, and missing coverage means untested, never wrong).
        Reuses the in-memory knowledge chain (Phase-22 built ONCE; Phase-23/24/25 derived purely),
        the Phase-26 re-validation (computed purely in memory), and the SAME bounded evidence records
        the chain read (context breadth) - via the canonical Phase-25 record→domain mapping. Read-only;
        no N+1; no writes; no migration; no wall-clock; DB stays v26; deterministic; never raises."""
        try:
            from strategy.programme_revalidation_report import build_revalidation_report as _brr
            from strategy.programme_coverage_report import (
                build_programme_evidence_coverage_report as _bcov)
        except Exception as exc:  # pragma: no cover - defensive
            return {"ok": False, "error": f"phase27 import failed: {exc}"}
        chain = self._build_knowledge_chain(
            memory_context_key, applied_setup=applied_setup, session_identity=session_identity,
            gearbox_state=gearbox_state, speed_context=speed_context,
            session_context=session_context, session_budget=session_budget, now_date=now_date, **ctx)
        if chain is None:
            return {"ok": True, "coverage": None, "domain_count": 0, "blind_spot_count": 0}
        revalidation = _brr(chain["timeline"], chain["programme"]).to_dict()
        report = _bcov(chain["timeline"], chain["programme"], revalidation,
                       chain.get("records") or []).to_dict()
        return {"ok": True, "coverage": report,
                "domain_count": len(report.get("domain_coverage") or []),
                "blind_spot_count": len(report.get("blind_spots") or []),
                "content_fingerprint": report.get("content_fingerprint")}

    def build_programme_knowledge_readiness_report(self, memory_context_key: str = "", *,
                                                   applied_setup=None, session_identity=None,
                                                   gearbox_state="", speed_context="",
                                                   session_context=None, session_budget=None,
                                                   now_date="", **ctx) -> dict:
        """Build the READ-ONLY Programme Knowledge Readiness Report (Program 2, Phase 28): the
        executive-summary capstone stating, per known domain, whether the evidence supports relying
        on the knowledge, plus a transparent rule-based programme grade. Reuses the in-memory
        knowledge chain (Phase-22 built ONCE; Phase-23/24/25 derived purely) and computes the
        Phase-26 re-validation + Phase-27 coverage purely in memory - it never calls their SessionDB
        entries. Read-only; no N+1; no writes; no migration; no wall-clock; DB stays v26;
        deterministic; never raises."""
        try:
            from strategy.programme_revalidation_report import build_revalidation_report as _brr
            from strategy.programme_coverage_report import (
                build_programme_evidence_coverage_report as _bcov)
            from strategy.programme_readiness_report import (
                build_programme_knowledge_readiness_report as _brdy)
        except Exception as exc:  # pragma: no cover - defensive
            return {"ok": False, "error": f"phase28 import failed: {exc}"}
        chain = self._build_knowledge_chain(
            memory_context_key, applied_setup=applied_setup, session_identity=session_identity,
            gearbox_state=gearbox_state, speed_context=speed_context,
            session_context=session_context, session_budget=session_budget, now_date=now_date, **ctx)
        if chain is None:
            return {"ok": True, "readiness": None, "grade": "insufficient_evidence",
                    "domain_count": 0}
        revalidation = _brr(chain["timeline"], chain["programme"]).to_dict()
        coverage = _bcov(chain["timeline"], chain["programme"], revalidation,
                         chain.get("records") or []).to_dict()
        report = _brdy(chain["timeline"], chain["programme"], revalidation, coverage).to_dict()
        return {"ok": True, "readiness": report, "grade": report.get("programme_grade"),
                "domain_count": len(report.get("items") or []),
                "content_fingerprint": report.get("content_fingerprint")}

    def get_learning_outcomes(
        self, car_id: int, track: str, layout_id: str
    ) -> list[dict]:
        """Return learning outcome rows scoped to car_id+track+layout_id, newest first.

        Returns [] on ANY error (corrupt/missing table, schema mismatch, etc.) —
        callers must tolerate an empty list gracefully.

        Each dict includes: verdict, rule_id, car_id, track, layout_id,
        session_type, source_path, driver_profile_version (plus all other columns).
        """
        try:
            with self._lock:
                rows = self._conn.execute(
                    """SELECT * FROM learning_outcomes
                       WHERE car_id=? AND track=? AND layout_id=?
                       ORDER BY id DESC""",
                    (car_id, track, layout_id),
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []  # silent fallback — corrupt/missing table/schema-mismatch

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
                           mandatory_stops=?, bop=?, tuning=?, abs=?,
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
                        1 if evt.get("abs", True) else 0,
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
                            mandatory_stops, bop, tuning, abs,
                            weather, damage,
                            avail_tyres, req_tyres, allowed_tuning,
                            notes, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
                        1 if evt.get("abs", True) else 0,
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

    def get_best_practice_lap_ms(self, car_id: int, track: str) -> Optional[int]:
        """Return best non-pit-lap practice lap time in ms for this car+track, or None."""
        with self._lock:
            row = self._conn.execute(
                "SELECT MIN(lr.lap_time_ms) AS best "
                "FROM lap_records lr "
                "JOIN sessions s ON lr.session_id = s.id "
                "WHERE s.car_id=? AND s.track=? "
                "AND lr.session_type='Practice' AND lr.is_pit_lap=0",
                (car_id, track)
            ).fetchone()
        if row and row["best"]:
            return int(row["best"])
        return None

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
        # Ensure each rec has a status key so the column is written explicitly
        # (SQLite default is 'proposed', but callers that provide a final validated
        # status must have it stored rather than defaulting to the pre-validation value).
        # v11 (Group 42): also populate the 8 new structured columns when present
        # in the rec dict (best-effort; old callers that lack the keys get NULL).
        recs_with_status = []
        for rec in recs:
            r = dict(rec)
            r.setdefault("status", "proposed")
            # v11 defaults — ensures named params never raise KeyError for old callers
            r.setdefault("deterministic_plan_json", None)
            r.setdefault("ai_audit_json", None)
            r.setdefault("validation_status", None)
            r.setdefault("approved_changes_json", None)
            r.setdefault("rejected_changes_json", None)
            r.setdefault("diagnosis_json", None)
            r.setdefault("driver_profile_version", None)
            r.setdefault("rule_engine_version", None)
            recs_with_status.append(r)
        with self._lock:
            self._conn.executemany(
                """INSERT INTO setup_recommendations
                   (ai_interaction_id, session_id, car_id, track, layout_id,
                    feature, recommendation_text, status, created_at,
                    deterministic_plan_json, ai_audit_json, validation_status,
                    approved_changes_json, rejected_changes_json, diagnosis_json,
                    driver_profile_version, rule_engine_version)
                   VALUES (:ai_interaction_id, :session_id, :car_id, :track,
                           :layout_id, :feature, :recommendation_text, :status, :created_at,
                           :deterministic_plan_json, :ai_audit_json, :validation_status,
                           :approved_changes_json, :rejected_changes_json, :diagnosis_json,
                           :driver_profile_version, :rule_engine_version)""",
                recs_with_status,
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

    def get_tracks_for_car_recommendations(self, car_id: int) -> list[str]:
        """Return distinct tracks with setup recommendations for this car, sorted."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT DISTINCT track FROM setup_recommendations "
                "WHERE car_id=? AND track != '' ORDER BY track",
                (car_id,)
            ).fetchall()
        return [r["track"] for r in rows]

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

        # Engineering-Brain Phase 1: record a lineage node for this applied change set
        # (auto-parented to the prior node at this scope). Best-effort — never blocks
        # the apply. Pulls the applied changes + layout/objective off the rec row.
        try:
            with self._lock:
                meta = self._conn.execute(
                    """SELECT approved_changes_json, layout_id
                       FROM setup_recommendations WHERE id = ?""",
                    (rec_id,),
                ).fetchone()
            if meta is not None:
                changes_json = meta[0] or "[]"
                layout_id = meta[1] or ""
                self.record_lineage(
                    car_id, track, layout_id, rec_id=rec_id,
                    session_id=session_id, changes_json=changes_json,
                    label=f"rec {rec_id}")
        except Exception:
            pass
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
    # OFR-1 Between-Race Learning Loop (schema v9)
    # ------------------------------------------------------------------

    def get_applied_unverified_recs(
        self, car_id: int, track: str, layout_id: str
    ) -> list[dict]:
        """Return applied, unscored recommendations for this car+track+layout.

        Only rows where status='applied' AND score_verdict='' AND the layout_id
        matches exactly (cross-layout scoring excluded; empty-string matches
        empty-string rows).
        """
        try:
            with self._lock:
                rows = self._conn.execute(
                    """SELECT * FROM setup_recommendations
                       WHERE car_id = ? AND track = ? AND layout_id = ?
                         AND status = 'applied'
                         AND score_verdict = ''
                       ORDER BY id ASC""",
                    (car_id, track, layout_id),
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def get_laps_for_scoring(self, session_id: int) -> list[dict]:
        """Return lap_records fields needed for OFR-1 scoring for a session.

        Includes pit/out-lap flags so the caller can filter; never raises.
        """
        try:
            with self._lock:
                rows = self._conn.execute(
                    """SELECT id, lap_num, lap_time_ms, is_pit_lap, is_out_lap,
                              compound, lock_up_count, wheelspin_count,
                              oversteer_count, oversteer_throttle_on,
                              bottoming_count, brake_consistency_m
                       FROM lap_records
                       WHERE session_id = ? AND lap_time_ms > 0
                       ORDER BY lap_num ASC""",
                    (session_id,),
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def get_previous_session_id(
        self, car_id: int, track: str, before_session_id: int
    ) -> int:
        """Return the most recent session id for car+track with id < before_session_id.

        Returns 0 when no such session exists.  Used by the UI trigger to
        resolve the creation ("before") session for a just-finished session.
        """
        try:
            with self._lock:
                row = self._conn.execute(
                    """SELECT MAX(s.id)
                       FROM sessions s
                       WHERE s.car_id = ? AND s.track = ? AND s.id < ?""",
                    (car_id, track, before_session_id),
                ).fetchone()
            if row and row[0] is not None:
                return int(row[0])
            return 0
        except Exception:
            return 0

    def persist_score(
        self,
        rec_id: int,
        verdict: str,
        confidence: float,
        details: dict,
    ) -> bool:
        """Write score columns for one recommendation — write-once guard.

        Returns True if the row was written, False if it already had a verdict
        (write-once: first caller wins).  Never raises outward.
        """
        try:
            with self._lock:
                existing = self._conn.execute(
                    "SELECT score_verdict FROM setup_recommendations WHERE id = ?",
                    (rec_id,),
                ).fetchone()
                if existing is None:
                    return False
                if existing[0] not in ("", None):
                    # Already scored — skip.
                    return False
                self._conn.execute(
                    """UPDATE setup_recommendations
                       SET score_verdict = ?, score_confidence = ?, score_details = ?
                       WHERE id = ?""",
                    (verdict, float(confidence), json.dumps(details), rec_id),
                )
                self._conn.commit()
            return True
        except Exception:
            return False

    def has_learning_for_car_track(self, car_id: int, track: str) -> bool:
        """True if any scored recommendation exists for this car+track.

        'Scored' means score_verdict is not '' and not 'insufficient_data'.
        """
        try:
            with self._lock:
                row = self._conn.execute(
                    """SELECT 1 FROM setup_recommendations
                       WHERE car_id = ? AND track = ?
                         AND score_verdict NOT IN ('', 'insufficient_data')
                       LIMIT 1""",
                    (car_id, track),
                ).fetchone()
            return row is not None
        except Exception:
            return False

    def get_scored_recs_for_prompt(
        self, car_id: int, track: str, layout_id: str
    ) -> list[dict]:
        """Return high-confidence, layout-matched scored recs for prompt injection.

        Filters: score_confidence >= 0.5, score_verdict not '' or
        'insufficient_data', layout_id exact match.  Returns newest-first,
        limited to 5 rows for prompt economy.
        """
        try:
            with self._lock:
                rows = self._conn.execute(
                    """SELECT * FROM setup_recommendations
                       WHERE car_id = ? AND track = ? AND layout_id = ?
                         AND score_confidence >= 0.5
                         AND score_verdict != ''
                         AND score_verdict != 'insufficient_data'
                       ORDER BY id DESC LIMIT 5""",
                    (car_id, track, layout_id),
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

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
        *,
        layout_id: str = "",
        driver_id: str = "",
        gt7_version: str = "",
    ) -> int:
        """Create a new session row and return its id.

        The optional ``layout_id`` / ``driver_id`` / ``gt7_version`` are used ONLY
        to resolve the canonical engineering context (Phase 1) — they do not
        alter the sessions row. When absent, the corresponding identity component
        stays honestly unknown."""
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
            sid = cur.lastrowid
        # Phase 1: bridge this new session to its canonical engineering context.
        # Best-effort, OUTSIDE the write lock (the context methods re-lock).
        self._attach_session_context(
            sid, car_id=car_id, track=track, session_type=session_type,
            config_id=config_id, event_id=event_id, layout_id=layout_id,
            driver_id=driver_id, gt7_version=gt7_version)
        return sid

    def _attach_session_context(
        self, session_id, *, car_id, track, session_type, config_id, event_id,
        layout_id="", driver_id="", gt7_version="",
    ) -> None:
        """Resolve + bridge a session row to its canonical engineering context.
        Best-effort; a failure here never affects session creation."""
        try:
            from data.engineering_context_key import resolve_from_session_row
            row = {
                "id": session_id, "car_id": car_id, "track": track,
                "session_type": session_type, "config_id": config_id,
                "event_id": event_id,
            }
            res = resolve_from_session_row(
                row, driver_id=(driver_id or None), layout_id=(layout_id or None),
                gt7_version=(gt7_version or None))
            self.resolve_and_link_engineering_context(res, "session", session_id)
        except Exception:
            pass

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

    def get_laps_with_telemetry(
        self, car_id: int, track: str, *, session_type: str = "",
        limit: int = 40, compound: str = "", exclude_pit: bool = True,
    ) -> list[dict]:
        """Recent laps (newest first) WITH their decompressed frames — the batch
        counterpart to ``get_lap_telemetry`` (which is single-lap only), for
        cross-session frame analysis (holistic brain, Phase 1+).

        Each item: ``{lap_record_id, session_id, lap_num, lap_time_ms, setup_id,
        compound, is_pit_lap, session_type, frames: [dict, ...]}``. Laps without a
        stored telemetry blob come back with ``frames == []``.
        """
        where = ["lr.car_id = ?", "lr.track = ?", "lr.lap_time_ms > 0"]
        params: list = [int(car_id or 0), track or ""]
        if session_type:
            where.append("lr.session_type = ?")
            params.append(session_type)
        if compound:
            where.append("lr.compound = ?")
            params.append(compound)
        if exclude_pit:
            where.append("lr.is_pit_lap = 0")
        sql = (
            "SELECT lr.id AS lap_record_id, lr.session_id, lr.lap_num, "
            "lr.lap_time_ms, lr.setup_id, lr.compound, lr.is_pit_lap, "
            "lr.session_type, lr.wheelspin_count, lr.lock_up_count "
            "FROM lap_records lr "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY lr.id DESC LIMIT ?"
        )
        params.append(int(limit))
        with self._lock:
            rows = [dict(r) for r in self._conn.execute(sql, params).fetchall()]
        # Fetch frames OUTSIDE the lock (get_lap_telemetry re-acquires it).
        for d in rows:
            d["frames"] = self.get_lap_telemetry(int(d["lap_record_id"]))
        return rows

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
        latest: bool = False,
    ) -> list:
        """Return valid lap records for a session, ordered by lap number.

        When exclude_pit/exclude_out are True the respective lap types are
        filtered out.  limit=0 means no limit.  Returns telemetry fields used
        by the per-lap AI prompt table (Phase 2-A / Group 16).

        latest=False (default): ORDER BY lap_num ASC — first ``limit`` laps.
        latest=True: select the LAST ``limit`` laps (ORDER BY lap_num DESC
        LIMIT ?) then reverse so the returned slice is in ascending lap order.
        All existing callers pass no ``latest`` keyword so their behaviour is
        byte-identical.
        """
        where = "session_id = ? AND lap_time_ms > 0"
        if exclude_pit:
            where += " AND is_pit_lap = 0"
        if exclude_out:
            where += " AND is_out_lap = 0"

        if latest and limit > 0:
            # Fetch the last `limit` laps in DESC order, then reverse for display.
            sql = (
                f"SELECT lap_num, lap_time_ms, compound, fuel_used,"
                f" is_pit_lap, is_out_lap, fuel_start, fuel_end,"
                f" lock_up_count, wheelspin_count, oversteer_count,"
                f" oversteer_throttle_on, kerb_count, max_lat_g,"
                f" tyre_temp_fl_avg, tyre_temp_fr_avg,"
                f" tyre_temp_rl_avg, tyre_temp_rr_avg,"
                f" snap_throttle_count, brake_consistency_m,"
                f" event_positions_json"
                f" FROM lap_records"
                f" WHERE {where}"
                f" ORDER BY lap_num DESC"
                f" LIMIT {int(limit)}"
            )
            with self._lock:
                rows = self._conn.execute(sql, (session_id,)).fetchall()
            return list(reversed([dict(r) for r in rows]))

        sql = (
            f"SELECT lap_num, lap_time_ms, compound, fuel_used,"
            f" is_pit_lap, is_out_lap, fuel_start, fuel_end,"
            f" lock_up_count, wheelspin_count, oversteer_count,"
            f" oversteer_throttle_on, kerb_count, max_lat_g,"
            f" tyre_temp_fl_avg, tyre_temp_fr_avg,"
            f" tyre_temp_rl_avg, tyre_temp_rr_avg,"
            f" snap_throttle_count, brake_consistency_m,"
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

    def get_session_type(self, session_id: int) -> str:
        """Return the session_type stored for the given session.

        Returns '' when session_id is 0, missing, or the query fails.  An
        empty string is treated as UNKNOWN by normalise_purpose, matching the
        documented defensive contract ('' → UNKNOWN → generic block).
        """
        if not session_id:
            return ""
        try:
            with self._lock:
                row = self._conn.execute(
                    "SELECT session_type FROM sessions WHERE id = ?",
                    (session_id,),
                ).fetchone()
            if row is None:
                return ""
            return str(row[0] or "")
        except Exception:
            return ""

    def get_session_meta(self, session_id: int) -> Optional[dict]:
        """Return the sessions row for ``session_id`` as a dict, or None.

        READ-ONLY. Added for the Group 49 race-strategy SessionDB adapter so the
        pure strategy layer can resolve a session's car/track/config without
        touching private state. Returns None when session_id is 0/missing or the
        query fails (never raises).
        """
        if not session_id:
            return None
        try:
            with self._lock:
                row = self._conn.execute(
                    "SELECT id, car_id, car_name, config_id, track, "
                    "session_type, total_laps, event_id "
                    "FROM sessions WHERE id = ?",
                    (session_id,),
                ).fetchone()
            return dict(row) if row is not None else None
        except Exception:
            return None

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

    def save_corner_slip_aggregates(self, car_id: int, track: str, layout_id: str,
                                    run_id: int, aggregates: list) -> None:
        """Upsert this run's per-corner slip aggregates (idempotent per run).

        Accepts CornerTelemetryAggregate instances or plain dicts. Re-saving the same
        (car, track, layout, segment, run) REPLACES the row, so calling this repeatedly
        during a session never double-counts. Reads accumulate across runs.
        """
        if not aggregates or not track:
            return

        def _v(a, k, default=None):
            return getattr(a, k, default) if not isinstance(a, dict) else a.get(k, default)

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rows = []
        for a in aggregates:
            samples = int(_v(a, "samples", 0) or 0)
            rows.append((
                int(car_id or 0), track, layout_id or "", str(_v(a, "segment_id", "") or ""),
                int(run_id or 0), _v(a, "turn"), str(_v(a, "display_name", "") or ""),
                str(_v(a, "direction", "") or ""), samples,
                int(_v(a, "wheelspin_events", 0) or 0), int(_v(a, "lockup_events", 0) or 0),
                json.dumps(_v(a, "wheelspin_by_phase", {}) or {}),
                json.dumps(_v(a, "lockup_by_phase", {}) or {}),
                json.dumps(_v(a, "spin_axle_counts", {}) or {}),
                json.dumps(_v(a, "lock_axle_counts", {}) or {}),
                float(_v(a, "avg_throttle", 0.0) or 0.0) * samples,
                float(_v(a, "avg_brake", 0.0) or 0.0) * samples,
                _v(a, "exit_gear"), _v(a, "exit_rpm_avg"), now,
            ))
        with self._lock:
            self._conn.executemany(
                """INSERT INTO corner_slip_telemetry
                   (car_id, track, layout_id, segment_id, run_id, turn, display_name,
                    direction, samples, wheelspin_events, lockup_events,
                    wheelspin_by_phase, lockup_by_phase, spin_axle_counts,
                    lock_axle_counts, throttle_sum, brake_sum, exit_gear, exit_rpm_avg,
                    updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(car_id, track, layout_id, segment_id, run_id) DO UPDATE SET
                     turn=excluded.turn, display_name=excluded.display_name,
                     direction=excluded.direction, samples=excluded.samples,
                     wheelspin_events=excluded.wheelspin_events,
                     lockup_events=excluded.lockup_events,
                     wheelspin_by_phase=excluded.wheelspin_by_phase,
                     lockup_by_phase=excluded.lockup_by_phase,
                     spin_axle_counts=excluded.spin_axle_counts,
                     lock_axle_counts=excluded.lock_axle_counts,
                     throttle_sum=excluded.throttle_sum, brake_sum=excluded.brake_sum,
                     exit_gear=excluded.exit_gear, exit_rpm_avg=excluded.exit_rpm_avg,
                     updated_at=excluded.updated_at""",
                rows)
            self._conn.commit()

    def save_issue_occurrences(self, car_id: int, track: str, layout_id: str,
                               occurrences) -> int:
        """Insert per-episode issue occurrences (Sprint 5, additive).

        ``occurrences`` are duck-typed (IssueOccurrence or dicts). Both admissible
        and suppressed episodes are stored (suppressed carry exclusion_reason) so
        the record stays honest and visible. Returns the number of rows inserted.
        Never raises out — a persistence failure must not break a session save.
        """
        rows = []
        import datetime as _dt
        now = _dt.datetime.now().isoformat(timespec="seconds")
        for o in (occurrences or []):
            def g(name, default=None):
                if isinstance(o, dict):
                    return o.get(name, default)
                return getattr(o, name, default)
            rows.append((
                int(car_id or 0), track or "", layout_id or "",
                int(g("session_id", 0) or 0), str(g("setup_checkpoint_id", "") or ""),
                int(g("lap_number", 0) or 0), str(g("segment_id", "") or ""),
                str(g("corner_phase", "") or ""), str(g("issue_type", "") or ""),
                str(g("issue_subtype", "") or ""), str(g("axle", "") or ""),
                float(g("duration_s", 0.0) or 0.0), float(g("severity", 0.0) or 0.0),
                float(g("confidence", 0.0) or 0.0), float(g("throttle", 0.0) or 0.0),
                float(g("brake", 0.0) or 0.0), float(g("speed_kmh", 0.0) or 0.0),
                int(g("gear", 0) or 0), str(g("compound", "") or ""),
                int(g("tyre_age", 0) or 0), str(g("exclusion_reason", "") or ""),
                str(g("provenance", "") or ""), now,
            ))
        if not rows:
            return 0
        try:
            with self._lock:
                self._conn.executemany(
                    """INSERT INTO corner_issue_occurrences
                       (car_id, track, layout_id, session_id, setup_checkpoint_id,
                        lap_number, segment_id, corner_phase, issue_type, issue_subtype,
                        axle, duration_s, severity, confidence, throttle, brake,
                        speed_kmh, gear, compound, tyre_age, exclusion_reason,
                        provenance, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    rows)
                self._conn.commit()
            return len(rows)
        except Exception:
            return 0

    def get_issue_occurrences(self, car_id: int, track: str,
                              layout_id: str = "") -> list[dict]:
        """Return stored issue-occurrence rows for this car/track(/layout).

        Rows are plain dicts; the caller rebuilds IssueOccurrence and feeds the
        pure cross-lap persistence engine (enables cross-session confirmation).
        """
        if not track:
            return []
        if layout_id:
            where = "car_id = ? AND track = ? AND layout_id = ?"
            params: tuple = (int(car_id or 0), track, layout_id)
        else:
            where = "car_id = ? AND track = ?"
            params = (int(car_id or 0), track)
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM corner_issue_occurrences WHERE {where} ORDER BY id",
                params).fetchall()
        return [dict(r) for r in rows]

    def save_applied_checkpoint(self, car_id: int, track: str, layout_id: str,
                                purpose: str, checkpoint) -> int:
        """Record that a setup was confirmed applied in GT7 (Sprint 10, additive).

        ``checkpoint`` is duck-typed (AppliedCheckpoint or dict). Append-only: each
        confirmation inserts a new row, so the applied history stays honest and the
        latest row is the current GT7-confirmed state. Returns the inserted rowid
        (0 on failure). Never raises out — a persistence failure must not break the
        UI action."""
        import json as _json
        import datetime as _dt

        def g(name, default=None):
            if isinstance(checkpoint, dict):
                return checkpoint.get(name, default)
            return getattr(checkpoint, name, default)

        try:
            now = _dt.datetime.now().isoformat(timespec="seconds")
            with self._lock:
                cur = self._conn.execute(
                    """INSERT INTO applied_setup_checkpoints
                       (car_id, track, layout_id, purpose, setup_id, checkpoint_id,
                        setup_hash, fields_json, changed_fields_json, confirmed_at,
                        created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (int(car_id or 0), track or "", layout_id or "", purpose or "",
                     str(g("setup_id", "") or ""), str(g("checkpoint_id", "") or ""),
                     str(g("setup_hash", "") or ""),
                     _json.dumps(g("fields", {}) or {}, sort_keys=True),
                     _json.dumps(list(g("changed_fields", ()) or [])),
                     str(g("confirmed_at", "") or ""), now))
                self._conn.commit()
                cp_rowid = int(cur.lastrowid or 0)
        except Exception:
            return 0
        # Phase 1: bridge this applied-setup checkpoint to its canonical
        # engineering context (best-effort, outside the write lock).
        try:
            from data.engineering_context_key import resolve_from_applied_checkpoint
            row = {
                "id": cp_rowid, "car_id": car_id, "track": track,
                "layout_id": layout_id, "purpose": purpose,
                "setup_id": g("setup_id", ""),
                "checkpoint_id": g("checkpoint_id", ""),
            }
            res = resolve_from_applied_checkpoint(row)
            self.resolve_and_link_engineering_context(
                res, "applied_checkpoint", cp_rowid)
        except Exception:
            pass
        return cp_rowid

    def get_latest_applied_checkpoint(self, car_id: int, track: str,
                                      layout_id: str = "",
                                      purpose: str = "") -> dict | None:
        """Return the most-recent applied-in-GT7 checkpoint for this scope, or None.

        The Setup Builder rebuilds an ``AppliedCheckpoint`` from this dict and feeds
        the pure ``compute_apply_status`` to resolve the three-state apply status.
        """
        try:
            where = "car_id = ? AND track = ? AND layout_id = ? AND purpose = ?"
            params: tuple = (int(car_id or 0), track or "", layout_id or "",
                             purpose or "")
            with self._lock:
                row = self._conn.execute(
                    f"SELECT * FROM applied_setup_checkpoints WHERE {where} "
                    "ORDER BY id DESC LIMIT 1", params).fetchone()
            return dict(row) if row is not None else None
        except Exception:
            return None

    def get_corner_slip_rows(self, car_id: int, track: str,
                             layout_id: str = "") -> list[dict]:
        """Return raw per-run per-corner slip rows for this car/track(/layout).

        JSON columns are returned as strings; the pure merger parses + accumulates them.
        """
        if not track:
            return []
        if layout_id:
            where = "car_id = ? AND track = ? AND layout_id = ?"
            params: tuple = (int(car_id or 0), track, layout_id)
        else:
            where = "car_id = ? AND track = ?"
            params = (int(car_id or 0), track)
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM corner_slip_telemetry WHERE {where}", params).fetchall()
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
        setup_id: int = 0,
        rating: str = "",
    ) -> int:
        submitted_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO driver_feedback
                       (session_id, lap_num, submitted_at,
                        corner_entry, mid_corner, exit_stability,
                        rear_braking, tyre_condition, fuel_use,
                        notes, config_id, setup_id, rating,
                        vs_previous, corner, phase)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
                    int(setup_id or 0),
                    rating or "",
                    # Phase 7: directional outcome vs the previous setup + optional corner.
                    feedback.get("vs_previous", ""),
                    feedback.get("corner", ""),
                    feedback.get("phase", ""),
                ),
            )
            self._conn.commit()
            fb_id = cur.lastrowid or 0
            sess = self._conn.execute(
                "SELECT id, car_id, track, session_type, config_id, event_id "
                "FROM sessions WHERE id = ?", (session_id,)).fetchone()
            session_row = dict(sess) if sess is not None else None
        # Phase 1: bridge this feedback row to the SAME canonical context as its
        # session — INHERITING the session's already-resolved identity (so it
        # shares the session's stable scope_fingerprint), enriched with the
        # feedback's own config_id/setup_id. No free-text coincidence. If the
        # session has no stored context (legacy), fall back to resolving from the
        # joined session row. Best-effort, outside the write lock.
        try:
            from data.engineering_context_key import (
                engineering_context_from_stored_row,
                resolve_feedback_against_session_context,
                resolve_from_driver_feedback,
            )
            stored = self.get_engineering_context_for_source("session", session_id)
            if stored is not None:
                session_ctx = engineering_context_from_stored_row(stored)
                res = resolve_feedback_against_session_context(
                    session_ctx,
                    config_id=(config_id or None),
                    setup_id=(setup_id or None))
            else:
                res = resolve_from_driver_feedback(
                    {"session_id": session_id, "config_id": config_id,
                     "setup_id": setup_id},
                    session_row=session_row)
            self.resolve_and_link_engineering_context(res, "driver_feedback", fb_id)
        except Exception:
            pass
        return fb_id

    def get_lap_count_for_setup(self, setup_id: int) -> int:
        """Number of laps (any session) tagged with this setup_id.

        This is the "was it actually driven?" signal that replaces the old
        manual 'Applied' checkbox: a setup with >=1 tagged lap was applied.
        """
        if not setup_id:
            return 0
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM lap_records WHERE setup_id = ?",
                (int(setup_id),),
            ).fetchone()
        return int(row[0]) if row else 0

    def get_dominant_setup_id(self, session_id: int) -> int:
        """Return the most-frequently tagged non-zero setup_id for a session.

        Used to attribute a per-stint feedback submission to the setup the
        driver was actually running. Returns 0 when no laps are tagged yet.
        """
        if not session_id:
            return 0
        with self._lock:
            row = self._conn.execute(
                """SELECT setup_id, COUNT(*) AS c FROM lap_records
                   WHERE session_id = ? AND setup_id > 0
                   GROUP BY setup_id ORDER BY c DESC, setup_id DESC LIMIT 1""",
                (int(session_id),),
            ).fetchone()
        return int(row[0]) if row else 0

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
