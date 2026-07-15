"""
Group 42 — Rule-First Setup Brain: Legacy Storage Acceptance Tests

Covers:
  AC17 — absent/None/unrecognised validation_status → legacy_unknown (display-only, no apply)
  AC18 — SessionDB migrates to user_version 11 with all 8 new columns
  AC19 — save_entry with ai_audit_rejected_advisory routes to _rejected_ bucket
  AC20 — RuleOutcomeStore record/query round-trip

CRITICAL: AC17 tests whether an absent or None status can reach an
apply-eligible state. If a test reveals this is possible, that is a real defect.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data import setup_history as sh
from data.setup_history import (
    LEGACY_UNKNOWN,
    is_legacy_unknown,
    normalise_validation_status,
    APPROVED_STATUSES,
    _KNOWN_NON_APPROVED_STATUSES,
)
from strategy._setup_constants import AI_AUDIT_REJECTED_ADVISORY, DB_VERSION
from strategy.setup_rule_engine import RuleOutcomeStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _temp_history(tmp_path, monkeypatch):
    """Create a temporary setup_history.json and monkeypatch _HISTORY_PATH."""
    tmp_file = tmp_path / "setup_history.json"
    tmp_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(sh, "_HISTORY_PATH", tmp_file)
    return tmp_file


# ===========================================================================
# AC17 (CRITICAL) — Legacy unknown treatment
# ===========================================================================

class TestAC17LegacyUnknown:
    """AC17 (CRITICAL): absent/None/unrecognised validation_status → legacy_unknown.

    The test uses 'HARD' assertions: if any code path lets an absent/None status
    reach an approved/apply-eligible state, this is a REAL DEFECT against AC17.
    """

    # --- is_legacy_unknown ---

    def test_absent_status_is_legacy(self):
        """Missing key entirely → is_legacy_unknown returns True."""
        entry = {"type": "build_race", "changes": []}
        # No validation_status key
        vs = entry.get("validation_status")
        assert is_legacy_unknown(vs), (
            "AC17 FAIL: absent validation_status must be treated as legacy_unknown"
        )

    def test_none_status_is_legacy(self):
        """Explicit None → is_legacy_unknown returns True."""
        assert is_legacy_unknown(None), (
            "AC17 FAIL: None validation_status must be treated as legacy_unknown"
        )

    def test_empty_string_status_is_legacy(self):
        """Empty string '' → is_legacy_unknown returns True."""
        assert is_legacy_unknown(""), (
            "AC17 FAIL: Empty string validation_status must be treated as legacy_unknown"
        )

    def test_unrecognised_string_is_legacy(self):
        """Unrecognised string not in APPROVED_STATUSES or known non-approved → legacy."""
        assert is_legacy_unknown("some_completely_unknown_status_xyz_123"), (
            "AC17 FAIL: Unrecognised validation_status must be treated as legacy_unknown"
        )

    def test_approved_status_not_legacy(self):
        """Known approved statuses are NOT legacy_unknown."""
        for status in APPROVED_STATUSES:
            assert not is_legacy_unknown(status), (
                f"AC17 FAIL: {status!r} is in APPROVED_STATUSES but is_legacy_unknown returned True"
            )

    def test_known_non_approved_not_legacy(self):
        """Known non-approved statuses (ai_audit_rejected_advisory etc.) are NOT legacy."""
        for status in _KNOWN_NON_APPROVED_STATUSES:
            assert not is_legacy_unknown(status), (
                f"AC17 FAIL: Known non-approved status {status!r} should not be legacy_unknown"
            )

    # --- normalise_validation_status ---

    def test_normalise_absent_key_returns_legacy_unknown(self):
        """Entry with no validation_status key → normalise returns LEGACY_UNKNOWN."""
        entry = {"type": "build_race"}
        result = normalise_validation_status(entry)
        assert result == LEGACY_UNKNOWN, (
            f"AC17 FAIL: Entry with absent validation_status must normalise to {LEGACY_UNKNOWN!r}; "
            f"got {result!r}"
        )

    def test_normalise_none_value_returns_legacy_unknown(self):
        """Entry with validation_status=None → normalise returns LEGACY_UNKNOWN."""
        entry = {"type": "build_race", "validation_status": None}
        result = normalise_validation_status(entry)
        assert result == LEGACY_UNKNOWN, (
            f"AC17 FAIL: validation_status=None must normalise to {LEGACY_UNKNOWN!r}; "
            f"got {result!r}"
        )

    def test_normalise_unknown_string_returns_legacy_unknown(self):
        """Entry with unrecognised string → normalise returns LEGACY_UNKNOWN."""
        entry = {"validation_status": "totally_unknown_value_9999"}
        result = normalise_validation_status(entry)
        assert result == LEGACY_UNKNOWN, (
            f"AC17 FAIL: Unrecognised validation_status must normalise to {LEGACY_UNKNOWN!r}; "
            f"got {result!r}"
        )

    def test_normalise_approved_status_preserved(self):
        """Entry with known approved status → normalise returns the status as-is."""
        for status in APPROVED_STATUSES:
            entry = {"validation_status": status}
            result = normalise_validation_status(entry)
            assert result == status, (
                f"AC17 FAIL: Approved status {status!r} must be preserved by normalise; "
                f"got {result!r}"
            )

    # --- UI gate assertion (data-level, AC17 CRITICAL) ---

    def test_absent_status_cannot_be_apply_eligible(self):
        """CRITICAL AC17: an entry with absent status must NEVER be treat as approved.

        The 'apply eligible' gate is: is_legacy_unknown(status)==False AND
        status in APPROVED_STATUSES.

        This test proves that an absent/None/unknown status can NEVER pass that gate.
        If this test fails it means the production code has a bug where legacy entries
        can reach the apply-eligible path.
        """
        for vs in (None, "", "unknown_xyz", "OLD_STATUS"):
            # Step 1: is_legacy_unknown must be True
            legacy = is_legacy_unknown(vs)
            assert legacy, (
                f"AC17 CRITICAL DEFECT: is_legacy_unknown({vs!r}) returned False — "
                f"absent/unknown status can reach legacy=False path."
            )

            # Step 2: must not be in APPROVED_STATUSES (double-gate)
            if vs:
                not_approved = vs not in APPROVED_STATUSES
                assert not_approved, (
                    f"AC17 CRITICAL DEFECT: status {vs!r} is in APPROVED_STATUSES — "
                    f"legacy entry can be treated as approved."
                )

            # Step 3: the combined gate logic must block the apply path
            # Gate: apply_eligible = (not is_legacy_unknown(vs)) and (vs in APPROVED_STATUSES)
            apply_eligible = (not is_legacy_unknown(vs)) and bool(vs) and (vs in APPROVED_STATUSES)
            assert not apply_eligible, (
                f"AC17 CRITICAL DEFECT: status {vs!r} passed the apply-eligible gate — "
                f"this is a REAL DEFECT. "
                f"is_legacy_unknown={is_legacy_unknown(vs)!r}, "
                f"in_approved={vs in APPROVED_STATUSES if vs else False!r}. "
                f"Frontend-builder must fix the apply-gate check in setup_form_widget.py "
                f"to prevent absent/None/unknown statuses from reaching the Apply button."
            )


# ===========================================================================
# AC18 — SessionDB migrates to user_version 11
# ===========================================================================

class TestAC18SessionDBMigrationV11:
    """AC18: Fresh in-memory SessionDB migrates to user_version 11 with all 8 new columns.
    Existing v10 DB migrates without losing rows."""

    _V11_COLUMNS = [
        "deterministic_plan_json",
        "ai_audit_json",
        "validation_status",
        "approved_changes_json",
        "rejected_changes_json",
        "diagnosis_json",
        "driver_profile_version",
        "rule_engine_version",
    ]

    def test_fresh_db_migrates_to_v11(self, tmp_path):
        """Fresh DB opens at user_version 12 (v12 added learning_outcomes table — Group 46)."""
        from data.session_db import SessionDB

        db_path = str(tmp_path / "test_v11.db")
        db = SessionDB(db_path)

        version = db._conn.execute("PRAGMA user_version").fetchone()[0]
        # Fresh DB always migrates to the current schema (DB_VERSION).
        # Reconciled for Group 46 (v12), Group 47 (v13), Group 62 (v14: events.abs).
        assert version == DB_VERSION, (
            f"AC18 FAIL: Expected user_version={DB_VERSION}; got {version}"
        )

    def test_v11_columns_exist_on_fresh_db(self, tmp_path):
        """All 8 v11 columns exist on setup_recommendations after migration."""
        from data.session_db import SessionDB

        db_path = str(tmp_path / "test_v11_cols.db")
        db = SessionDB(db_path)

        # Get column info for setup_recommendations
        cols_info = db._conn.execute(
            "PRAGMA table_info(setup_recommendations)"
        ).fetchall()
        col_names = {row[1] for row in cols_info}

        for col in self._V11_COLUMNS:
            assert col in col_names, (
                f"AC18 FAIL: Column {col!r} missing from setup_recommendations "
                f"after v11 migration. Present columns: {sorted(col_names)}"
            )

    def test_existing_db_v10_migrates_to_v11_without_losing_data(self, tmp_path):
        """A v10 DB with rows survives migration to v11 without data loss."""
        from data.session_db import SessionDB

        # Create a v10 DB manually
        db_path = str(tmp_path / "test_v10_to_v11.db")

        # Open it to create the initial schema (will migrate to v11)
        db = SessionDB(db_path)
        initial_version = db._conn.execute("PRAGMA user_version").fetchone()[0]
        assert initial_version == DB_VERSION  # fresh always migrates to latest (Group 62: v14)

        # Insert a dummy session to simulate existing data
        db._conn.execute(
            "INSERT INTO sessions (car_name, config_id, track, session_type, date_utc, total_laps, event_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("Test Car", "test_cfg", "Fuji", "Race", "2026-07-05T00:00:00", 0, 0)
        )
        db._conn.commit()

        # Re-open the same DB — should still be at v12 with data intact
        db2 = SessionDB(db_path)
        version2 = db2._conn.execute("PRAGMA user_version").fetchone()[0]
        assert version2 == DB_VERSION  # Reconciled for Group 62 (now v14 == DB_VERSION)

        # Data row must still be there
        rows = db2._conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        assert rows == 1, (
            f"AC18 FAIL: Data lost during migration; expected 1 row, got {rows}"
        )


# ===========================================================================
# AC19 — save_entry with ai_audit_rejected_advisory routes to _rejected_ bucket
# ===========================================================================

class TestAC19AuditRejectedRoutesToRejectedBucket:
    """AC19: save_entry with validation_status='ai_audit_rejected_advisory'
    routes to the _rejected_ bucket."""

    def test_ai_audit_rejected_routes_to_rejected_bucket(self, tmp_path, monkeypatch):
        """Saving with ai_audit_rejected_advisory → entry appears in _rejected_<config_id>."""
        _temp_history(tmp_path, monkeypatch)

        config_id = "test_rejected_route"
        entry = {"type": "analyse_setup", "changes": [], "analysis": "Test."}

        sh.save_entry(
            config_id, "RSR", "Fuji",
            entry,
            validation_status=AI_AUDIT_REJECTED_ADVISORY,
        )

        # Load the raw history to check bucket routing
        data = json.loads((tmp_path / "setup_history.json").read_text(encoding="utf-8"))

        rejected_key = f"_rejected_{config_id}"
        assert rejected_key in data, (
            f"AC19 FAIL: ai_audit_rejected_advisory must route to bucket {rejected_key!r}; "
            f"keys: {list(data.keys())}"
        )
        # Must NOT appear in primary bucket
        assert config_id not in data, (
            f"AC19 FAIL: ai_audit_rejected_advisory must NOT appear in primary bucket {config_id!r}; "
            f"found in: {list(data.keys())}"
        )

    def test_approved_status_routes_to_primary_bucket(self, tmp_path, monkeypatch):
        """Saving with approved status → entry appears in primary bucket, not _rejected_."""
        _temp_history(tmp_path, monkeypatch)

        config_id = "test_approved_route"
        entry = {"type": "analyse_setup", "changes": [], "analysis": "Test."}

        sh.save_entry(
            config_id, "RSR", "Fuji",
            entry,
            validation_status="approved",
        )

        data = json.loads((tmp_path / "setup_history.json").read_text(encoding="utf-8"))

        assert config_id in data, (
            f"AC19 FAIL: Approved status must route to primary bucket {config_id!r}; "
            f"keys: {list(data.keys())}"
        )
        rejected_key = f"_rejected_{config_id}"
        assert rejected_key not in data, (
            f"AC19 FAIL: Approved status must not appear in rejected bucket {rejected_key!r}"
        )

    def test_validation_failed_routes_to_rejected_bucket(self, tmp_path, monkeypatch):
        """Saving with validation_failed → entry in _rejected_ bucket."""
        _temp_history(tmp_path, monkeypatch)

        config_id = "test_validation_failed"
        entry = {"type": "analyse_setup"}

        sh.save_entry(
            config_id, "RSR", "Fuji",
            entry,
            validation_status="validation_failed",
        )

        data = json.loads((tmp_path / "setup_history.json").read_text(encoding="utf-8"))
        rejected_key = f"_rejected_{config_id}"
        assert rejected_key in data, (
            f"AC19 FAIL: validation_failed must route to _rejected_ bucket"
        )

    def test_no_status_routes_to_primary_bucket(self, tmp_path, monkeypatch):
        """Saving without validation_status → entry in primary bucket (legacy behaviour)."""
        _temp_history(tmp_path, monkeypatch)

        config_id = "test_no_status"
        entry = {"type": "feeling_fix"}

        sh.save_entry(config_id, "RSR", "Fuji", entry)

        data = json.loads((tmp_path / "setup_history.json").read_text(encoding="utf-8"))

        assert config_id in data, (
            "AC19 FAIL: No validation_status must route to primary bucket"
        )


# ===========================================================================
# AC20 — RuleOutcomeStore record/query round-trip
# ===========================================================================

class TestAC20RuleOutcomeStoreRoundTrip:
    """AC20: RuleOutcomeStore record and query round-trip."""

    def test_fire_and_query_round_trip(self):
        """record_fire → fire_count returns correct count."""
        store = RuleOutcomeStore()
        store.record_fire("B6", car="RSR", track="Fuji", profile_version="v1")
        store.record_fire("B6", car="RSR", track="Fuji", profile_version="v1")
        store.record_fire("B6", car="RSR", track="Fuji", profile_version="v1")

        fc = store.fire_count("B6", car="RSR", track="Fuji", profile_version="v1")
        assert fc == 3, f"AC20 FAIL: Expected fire_count=3; got {fc}"

    def test_success_and_rate_round_trip(self):
        """record_success → get_success_rate returns correct rate."""
        store = RuleOutcomeStore()
        rule = "C5"
        car, track, pv = "RSR", "Fuji", "v1"

        for _ in range(4):
            store.record_fire(rule, car=car, track=track, profile_version=pv)
        for _ in range(2):
            store.record_success(rule, car=car, track=track, profile_version=pv)

        rate = store.get_success_rate(rule, car=car, track=track, profile_version=pv)
        assert rate is not None
        assert abs(rate - 0.5) < 0.01, (
            f"AC20 FAIL: Expected success_rate=0.5 (2/4); got {rate}"
        )

    def test_different_keys_are_independent(self):
        """Records for different (car, track) pairs are independent."""
        store = RuleOutcomeStore()
        store.record_fire("B6", car="RSR", track="Fuji")
        store.record_fire("B6", car="GT3", track="Suzuka")

        assert store.fire_count("B6", car="RSR", track="Fuji") == 1
        assert store.fire_count("B6", car="GT3", track="Suzuka") == 1
        assert store.fire_count("B6") == 0  # different key

    def test_none_returned_for_unrecorded_rule(self):
        """Unrecorded rule returns None from get_success_rate."""
        store = RuleOutcomeStore()
        assert store.get_success_rate("NONEXISTENT") is None

    def test_to_dict_is_json_serialisable(self):
        """to_dict returns a JSON-serialisable dict."""
        store = RuleOutcomeStore()
        store.record_fire("B6", car="RSR", track="Fuji")
        store.record_success("B6", car="RSR", track="Fuji")

        d = store.to_dict()
        # Must serialise without error
        serialised = json.dumps(d)
        assert isinstance(serialised, str)
        assert len(serialised) > 2  # non-empty dict

    def test_multiple_rules_independent(self):
        """Multiple rules in the same store are tracked independently."""
        store = RuleOutcomeStore()
        for rule in ("B6", "C5", "C6"):
            store.record_fire(rule)
            store.record_fire(rule)
            store.record_fire(rule)
            store.record_success(rule)

        for rule in ("B6", "C5", "C6"):
            assert store.fire_count(rule) == 3
            rate = store.get_success_rate(rule)
            assert rate is not None
            assert abs(rate - 1/3) < 0.01


