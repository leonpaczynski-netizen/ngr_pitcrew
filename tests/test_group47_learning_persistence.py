"""Group 47 — learning-outcome persistence tests.

Proves the v13 migration is additive & idempotent, that old databases upgrade
safely without data loss, that the richer outcome-verification evidence
round-trips through SQLite only, and that setup_history.json is NOT part of the
learning path.

Pure/offline except for temp-file SQLite (no Qt, no network).
"""
from __future__ import annotations

import sqlite3
import sys
import inspect
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.session_db import SessionDB
from strategy._setup_constants import DB_VERSION


# v12 learning_outcomes schema (BEFORE the Group 47 columns) — used to fabricate a
# realistic pre-upgrade database.
_V12_LEARNING_OUTCOMES_DDL = """
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
"""

_V13_COLUMNS = {
    "target_issue", "evidence_summary", "driver_feedback", "safety_notes",
    "outcome_kind",
}


def _cols(db: SessionDB, table: str) -> set:
    return {r[1] for r in db._conn.execute(f"PRAGMA table_info({table})").fetchall()}


# ---------------------------------------------------------------------------
# Fresh DB
# ---------------------------------------------------------------------------

class TestFreshDb:
    def test_fresh_db_at_v13(self, tmp_path):
        db = SessionDB(str(tmp_path / "fresh.db"))
        version = db._conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == DB_VERSION
        db.close()

    def test_v13_columns_present(self, tmp_path):
        db = SessionDB(str(tmp_path / "fresh.db"))
        cols = _cols(db, "learning_outcomes")
        assert _V13_COLUMNS <= cols, f"Missing v13 columns: {_V13_COLUMNS - cols}"
        db.close()


# ---------------------------------------------------------------------------
# Migration idempotency & old-DB upgrade
# ---------------------------------------------------------------------------

class TestMigration:
    def test_migration_idempotent(self, tmp_path):
        p = str(tmp_path / "idem.db")
        db1 = SessionDB(p); db1.close()
        db2 = SessionDB(p)  # second open must not raise
        assert db2._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION
        db2.close()
        db3 = SessionDB(p)  # third open still fine
        assert _V13_COLUMNS <= _cols(db3, "learning_outcomes")
        db3.close()

    def test_old_v12_db_upgrades_without_data_loss(self, tmp_path):
        p = str(tmp_path / "v12.db")
        # Fabricate a v12 database with a learning_outcomes row and NO v13 columns.
        raw = sqlite3.connect(p)
        raw.executescript(_V12_LEARNING_OUTCOMES_DDL)
        raw.execute(
            "INSERT INTO learning_outcomes (ts, car_id, track, layout_id, rule_id, verdict, confidence) "
            "VALUES ('2026-01-01T00:00:00', 7, 'Fuji', 'full_course', 'P1', 'improved', 0.8)"
        )
        raw.execute("PRAGMA user_version = 12")
        raw.commit()
        raw.close()

        # Confirm the fabricated DB really lacks the v13 columns.
        chk = sqlite3.connect(p)
        pre_cols = {r[1] for r in chk.execute("PRAGMA table_info(learning_outcomes)").fetchall()}
        chk.close()
        assert not (_V13_COLUMNS & pre_cols), "fixture should predate v13 columns"

        # Open with SessionDB → migrates to the current schema (Group 62: v14).
        db = SessionDB(p)
        assert db._conn.execute("PRAGMA user_version").fetchone()[0] == DB_VERSION
        assert _V13_COLUMNS <= _cols(db, "learning_outcomes")
        # Old row survived, with new columns defaulted to ''.
        rows = db.get_learning_outcomes(7, "Fuji", "full_course")
        assert len(rows) == 1
        assert rows[0]["rule_id"] == "P1"
        assert rows[0]["verdict"] == "improved"
        assert rows[0]["target_issue"] == ""  # defaulted
        db.close()

    def test_reopen_preserves_rows(self, tmp_path):
        p = str(tmp_path / "reopen.db")
        db = SessionDB(p)
        db.record_learning_outcome(
            car_id=7, track="Fuji", layout_id="full_course", session_id=1,
            session_type="Race", rule_id="P1", source_path="Analyse",
            verdict="improved", confidence=0.7, driver_profile_version="v1",
            rule_engine_version="46.0", target_issue="exit_traction",
            evidence_summary="wheelspin 10->4", outcome_kind="IMPROVED",
        )
        db.close()
        db2 = SessionDB(p)
        rows = db2.get_learning_outcomes(7, "Fuji", "full_course")
        assert len(rows) == 1 and rows[0]["outcome_kind"] == "IMPROVED"
        db2.close()


# ---------------------------------------------------------------------------
# Richer evidence round-trips through SQLite only
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_group47_fields_round_trip(self, tmp_path):
        db = SessionDB(str(tmp_path / "rt.db"))
        db.record_learning_outcome(
            car_id=7, track="Fuji", layout_id="full_course", session_id=1,
            session_type="Race", rule_id="P1", source_path="Analyse",
            verdict="worsened", confidence=0.6, driver_profile_version="v1",
            rule_engine_version="46.0",
            target_issue="brake_stability",
            evidence_summary="lock_up 2->8/lap (worse)",
            driver_feedback="made braking worse",
            safety_notes="telemetry safety-monitor regression detected",
            outcome_kind="WORSE",
        )
        row = db.get_learning_outcomes(7, "Fuji", "full_course")[0]
        assert row["target_issue"] == "brake_stability"
        assert row["evidence_summary"].startswith("lock_up")
        assert row["driver_feedback"] == "made braking worse"
        assert "regression" in row["safety_notes"]
        assert row["outcome_kind"] == "WORSE"
        db.close()

    def test_old_group46_call_signature_still_works(self, tmp_path):
        """The Group 46 call (no Group 47 kwargs) must still persist cleanly."""
        db = SessionDB(str(tmp_path / "compat.db"))
        db.record_learning_outcome(
            car_id=7, track="Fuji", layout_id="full_course", session_id=1,
            session_type="Race", rule_id="B3", source_path="Analyse",
            verdict="improved", confidence=0.75, driver_profile_version="v1",
            rule_engine_version="46.0",
        )
        rows = db.get_learning_outcomes(7, "Fuji", "full_course")
        assert len(rows) == 1
        assert rows[0]["target_issue"] == ""  # defaulted, no crash
        db.close()


# ---------------------------------------------------------------------------
# setup_history.json is NOT part of the learning path
# ---------------------------------------------------------------------------

class TestNoJsonLearningPath:
    def test_recording_creates_no_setup_history_json(self, tmp_path, monkeypatch):
        # Run entirely inside tmp_path; assert no setup_history.json appears.
        monkeypatch.chdir(tmp_path)
        db = SessionDB(str(tmp_path / "s.db"))
        db.record_learning_outcome(
            car_id=7, track="Fuji", layout_id="full_course", session_id=1,
            session_type="Race", rule_id="P1", source_path="Analyse",
            verdict="improved", confidence=0.7, driver_profile_version="v1",
            rule_engine_version="46.0", target_issue="exit_traction",
        )
        db.close()
        stray = list(tmp_path.rglob("setup_history.json"))
        assert not stray, f"learning path must not touch setup_history.json; found {stray}"

    def test_learning_crud_source_has_no_setup_history_reference(self):
        """The learning-outcome CRUD methods reference SQLite only — never the
        JSON runtime history file."""
        import data.session_db as mod
        for fn_name in ("record_learning_outcome", "get_learning_outcomes"):
            src = inspect.getsource(getattr(mod.SessionDB, fn_name))
            assert "setup_history" not in src, (
                f"{fn_name} must not reference setup_history.json"
            )
            assert "learning_outcomes" in src, (
                f"{fn_name} must operate on the learning_outcomes SQLite table"
            )
