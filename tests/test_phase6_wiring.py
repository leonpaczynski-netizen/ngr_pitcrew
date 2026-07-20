"""Engineering-Brain Phase 6 — runtime wiring + threading + architecture safety."""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_PURE = ("engineering_issue", "engineering_state", "experiment_planning")


# --- runtime wiring (structural) -------------------------------------------
def test_review_and_learn_builds_plan():
    src = (ROOT / "data" / "session_db.py").read_text(encoding="utf-8")
    assert "def build_engineering_plan(" in src
    assert 'review["engineering_plan"] = self.build_engineering_plan(' in src


def test_plan_built_off_thread_via_review_worker():
    src = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
    # the plan is produced inside review_and_learn, called on the worker thread
    assert "db.review_and_learn(" in src
    assert "threading.Thread(target=_worker, daemon=True)" in src


def test_render_shows_state_and_plan():
    src = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
    assert "engineering_plan" in src
    assert "Engineering state:" in src and "Development plan" in src
    assert "advisory" in src.lower()


def test_render_does_no_heavy_work():
    src = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
    disp_start = src.index("def _display_outcome_result")
    disp_end = src.index("def _refresh_apply_status_for_form")
    disp = src[disp_start:disp_end]
    # render only reads the pre-computed result dict — no DB/eval calls
    assert "build_engineering_plan" not in disp
    assert "review_and_learn" not in disp
    assert "evaluate_setup_experiment" not in disp


# --- Phase 4/5 precedence (subordination) ----------------------------------
def test_planning_subordinate_to_decision_authority():
    src = (ROOT / "data" / "session_db.py").read_text(encoding="utf-8")
    # build_engineering_plan consults resolve_setup_decision + decision_blocks
    plan_start = src.index("def build_engineering_plan(")
    plan_end = src.index("def get_learning_outcomes(", plan_start)
    body = src[plan_start:plan_end]
    assert "resolve_setup_decision" in body
    assert "decision_blocks" in body


def test_no_migration_no_new_telemetry_table():
    """Phase 6 (residual detection) is pure and introduced NO telemetry persistence. The ORIGINAL
    assertion ('_DDL_V26'/'_migrate_v26' absent) became stale once Phase 19 legitimately introduced
    database version 26 (and Phase 45 version 27) - it forbade the whole legitimate migration chain
    rather than the actual Phase-6 invariant. This corrected test proves the real invariant against a
    freshly-created database: Phase 6 created no telemetry table, the legitimate migration chain is
    allowed, the schema version is coherent, and no unexpected telemetry table exists. It does not
    weaken migration safety generally."""
    import os
    import tempfile

    from strategy._setup_constants import DB_VERSION
    from data.session_db import SessionDB

    p = tempfile.mktemp(suffix=".db")
    db = SessionDB(p)
    try:
        uv = db._conn.execute("PRAGMA user_version").fetchone()[0]
        tables = {r[0] for r in db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    finally:
        db.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(p + suffix)
            except OSError:
                pass

    # the schema version is coherent with the (legitimate) migration chain, including v26/v27.
    assert uv == DB_VERSION, (uv, DB_VERSION)
    # Phase 6 introduced no residual/telemetry persistence table.
    forbidden = {"residual_issues", "phase6_residuals", "telemetry_residuals", "residual_detection",
                 "engineering_residuals"}
    assert not (tables & forbidden), tables & forbidden
    # no telemetry table exists beyond the canonical base telemetry stores.
    telemetry_tables = {t for t in tables if "telemetry" in t.lower()}
    assert telemetry_tables <= {"lap_telemetry", "corner_slip_telemetry"}, telemetry_tables


# --- architecture safety (20.11) -------------------------------------------
def test_pure_modules_no_qt_db_network_ai():
    for mod in _PURE:
        s = (ROOT / "strategy" / f"{mod}.py").read_text(encoding="utf-8")
        for banned in ("PyQt6", "PyQt5", "from ui.", "import sqlite3",
                       "from data.session_db", "requests", "urllib", "anthropic",
                       "openai", "api_key"):
            assert banned not in s, f"{mod}: {banned}"


def test_pure_modules_no_wallclock_random_filewrite():
    for mod in _PURE:
        s = (ROOT / "strategy" / f"{mod}.py").read_text(encoding="utf-8")
        assert "datetime.now" not in s and "time.time" not in s
        assert "import random" not in s and "random." not in s
        assert ".write(" not in s and "open(" not in s


def test_pure_modules_no_setup_authoring_or_apply():
    for mod in _PURE:
        s = (ROOT / "strategy" / f"{mod}.py").read_text(encoding="utf-8")
        assert "mark_applied" not in s and "save_applied_checkpoint" not in s
        assert "apply_revert" not in s and "record_recommendation_experiment" not in s


def test_phase1_fingerprint_not_recomputed():
    for mod in _PURE:
        s = (ROOT / "strategy" / f"{mod}.py").read_text(encoding="utf-8")
        assert "compute_config_id" not in s
        assert "def scope_fingerprint" not in s


def test_no_invented_telemetry_channels():
    for mod in _PURE:
        s = (ROOT / "strategy" / f"{mod}.py").read_text(encoding="utf-8")
        for banned in ("steering_angle", "slip_angle", "tyre_wear_pct", "brake_temp"):
            assert banned not in s, f"{mod}: {banned}"


def test_planner_reuses_phase5_candidate_authority():
    # Phase 6 does not create a competing selector — the plan consumes Phase 5's
    # select_next_experiment / generate_candidates via the DB orchestrator.
    src = (ROOT / "data" / "session_db.py").read_text(encoding="utf-8")
    plan_start = src.index("def build_engineering_plan(")
    body = src[plan_start:src.index("def get_learning_outcomes(", plan_start)]
    assert "self.select_next_experiment(" in body
    # experiment_planning does not import a candidate generator of its own
    ep = (ROOT / "strategy" / "experiment_planning.py").read_text(encoding="utf-8")
    assert "def generate_candidates" not in ep and "def select_experiment" not in ep
