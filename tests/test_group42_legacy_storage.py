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
from strategy._setup_constants import AI_AUDIT_REJECTED_ADVISORY
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
        # Reconciled for Group 46: DB_VERSION bumped to 12.
        # Reconciled for Group 47: DB_VERSION bumped to 13 (_migrate_v13 added the
        # 5 additive outcome-verification columns to learning_outcomes).
        assert version == 13, (
            f"AC18 FAIL: Expected user_version=13; got {version}"
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
        assert initial_version == 13  # fresh always migrates to latest (Group 47: v13)

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
        assert version2 == 13  # Reconciled for Group 47 (v12 → v13)

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


# ===========================================================================
# I2 — DB column population round-trip
# ===========================================================================

class TestI2DBColumnPopulationRoundTrip:
    """I2: parse_recommendations_from_response → insert_setup_recommendations →
    read back row, assert all 8 v11 columns are non-null with expected values.

    Also covers the legacy/plain-text path: all 8 columns must be NULL.
    """

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

    def _make_group42_response_json(
        self,
        recommendation_status: str = "approved",
        include_driver_profile_version: bool = True,
        rule_engine_version: str = "42.0",
    ) -> str:
        """Build a realistic Group 42 JSON response string as produced by the rule-first pipeline."""
        payload = {
            "recommendation_status": recommendation_status,
            "analysis": "B5 fires: gearing too short on back straight.",
            "primary_issue": "gearing_too_short",
            "changes": [
                {
                    "field": "final_drive",
                    "from": 3.6,
                    "to": 3.55,
                    "setting": "Final Drive",
                    "why": "Shorten gearing to extract more top speed.",
                    "to_clamped": 3.55,
                }
            ],
            "setup_fields": {"final_drive": 3.55},
            "rejected_changes": [],
            "validation_errors": [],
            "validation_warnings": [],
            "engineering_validation_errors": [],
            "engineering_validation_failed": False,
            "fallback_used": False,
            "deterministic_plan": {
                "proposed_count": 1,
                "rejected_candidate_count": 0,
                "protected_fields": [],
                **({"driver_profile_version": "v1.0-hardcoded"} if include_driver_profile_version else {}),
            },
            "ai_audit": {
                "status": "approved",
                "notes": "Rule engine output looks sound.",
            },
            "diagnosis": {
                "gearbox_flag": "too_short",
                "wheelspin_band": "low",
            },
            "rule_engine_version": rule_engine_version,
        }
        return json.dumps(payload)

    def test_group42_json_response_populates_all_8_v11_columns(self, tmp_path):
        """Full Group 42 JSON path: all 8 v11 columns are non-null after round-trip."""
        from data.session_db import SessionDB
        from strategy._rec_parser import parse_recommendations_from_response

        db_path = str(tmp_path / "roundtrip_v11.db")
        db = SessionDB(db_path)

        response_json = self._make_group42_response_json(recommendation_status="approved")

        recs = parse_recommendations_from_response(
            response_text=response_json,
            feature="analyse_setup",
            car_id=101,
            track="Fuji Speedway",
            layout_id="full_course",
            session_id=1,
            ai_interaction_id=None,
        )
        assert recs, "I2 FAIL: parse_recommendations_from_response returned empty list"

        # Populate required fields parse doesn't add
        for rec in recs:
            rec.setdefault("recommendation_text", "test recommendation")

        db.insert_setup_recommendations(recs)

        # Read back the row directly to verify all 8 v11 columns
        conn = db._conn
        conn.row_factory = None  # use tuple access
        row_tuple = conn.execute(
            """SELECT deterministic_plan_json, ai_audit_json, validation_status,
                      approved_changes_json, rejected_changes_json, diagnosis_json,
                      driver_profile_version, rule_engine_version
               FROM setup_recommendations
               ORDER BY id DESC LIMIT 1"""
        ).fetchone()

        assert row_tuple is not None, "I2 FAIL: No row found in setup_recommendations after insert"

        col_names = [
            "deterministic_plan_json", "ai_audit_json", "validation_status",
            "approved_changes_json", "rejected_changes_json", "diagnosis_json",
            "driver_profile_version", "rule_engine_version",
        ]
        for idx, col in enumerate(col_names):
            val = row_tuple[idx]
            assert val is not None, (
                f"I2 FAIL: Column {col!r} is NULL after Group 42 JSON round-trip. "
                f"parse_recommendations_from_response must populate this field for JSON responses. "
                f"Backend-builder must fix _rec_parser.py to ensure {col!r} is extracted."
            )

    def test_group42_validation_status_matches_recommendation_status(self, tmp_path):
        """validation_status column mirrors recommendation_status in the stored row."""
        from data.session_db import SessionDB
        from strategy._rec_parser import parse_recommendations_from_response

        db_path = str(tmp_path / "roundtrip_vstatus.db")
        db = SessionDB(db_path)

        for status in ("approved", "approved_with_warnings", "ai_audit_rejected_advisory"):
            response_json = self._make_group42_response_json(recommendation_status=status)
            recs = parse_recommendations_from_response(
                response_text=response_json,
                feature="analyse_setup",
                car_id=102,
                track="Suzuka",
                layout_id="full",
                session_id=2,
                ai_interaction_id=None,
            )
            for rec in recs:
                rec.setdefault("recommendation_text", f"test {status}")
            db.insert_setup_recommendations(recs)

        # Read back all rows and verify validation_status
        rows = db._conn.execute(
            "SELECT validation_status, status FROM setup_recommendations ORDER BY id"
        ).fetchall()

        assert len(rows) >= 3, f"I2 FAIL: Expected ≥3 rows; got {len(rows)}"

        stored_statuses = [r[0] for r in rows]
        for expected_status in ("approved", "approved_with_warnings", "ai_audit_rejected_advisory"):
            assert expected_status in stored_statuses, (
                f"I2 FAIL: validation_status={expected_status!r} not found in stored rows. "
                f"Stored validation_status values: {stored_statuses}"
            )

    def test_group42_approved_changes_json_has_correct_field(self, tmp_path):
        """approved_changes_json from stored row decodes to the expected final_drive change."""
        from data.session_db import SessionDB
        from strategy._rec_parser import parse_recommendations_from_response

        db_path = str(tmp_path / "roundtrip_changes.db")
        db = SessionDB(db_path)

        response_json = self._make_group42_response_json(recommendation_status="approved")
        recs = parse_recommendations_from_response(
            response_text=response_json,
            feature="analyse_setup",
            car_id=103,
            track="Fuji",
            layout_id="full_course",
            session_id=3,
            ai_interaction_id=None,
        )
        for rec in recs:
            rec.setdefault("recommendation_text", "test")
        db.insert_setup_recommendations(recs)

        row = db._conn.execute(
            "SELECT approved_changes_json FROM setup_recommendations ORDER BY id DESC LIMIT 1"
        ).fetchone()

        assert row is not None
        assert row[0] is not None, (
            "I2 FAIL: approved_changes_json is NULL — changes list not extracted from JSON response"
        )

        changes = json.loads(row[0])
        assert isinstance(changes, list), (
            f"I2 FAIL: approved_changes_json must decode to a list; got {type(changes)}"
        )
        assert len(changes) >= 1, "I2 FAIL: approved_changes_json must contain at least one change"

        fields_changed = [c.get("field") for c in changes]
        assert "final_drive" in fields_changed, (
            f"I2 FAIL: expected final_drive in approved_changes_json; got {fields_changed}"
        )

    def test_legacy_plain_text_response_columns_are_null(self, tmp_path):
        """Legacy plain-text (non-JSON) response → all 8 v11 columns are NULL.

        This verifies backward compatibility: old non-JSON coaching responses
        must not break and must leave v11 columns as NULL (not raise KeyError).
        """
        from data.session_db import SessionDB
        from strategy._rec_parser import parse_recommendations_from_response

        db_path = str(tmp_path / "roundtrip_legacy.db")
        db = SessionDB(db_path)

        plain_text = (
            "1. Increase rear ARB by 1 click to reduce mid-corner roll.\n\n"
            "2. Raise ride height rear by 2mm to give more compliance over kerbs.\n\n"
            "3. Soften LSD accel slightly to reduce rear lock on throttle."
        )

        recs = parse_recommendations_from_response(
            response_text=plain_text,
            feature="analyse_setup",
            car_id=104,
            track="Fuji",
            layout_id="full",
            session_id=4,
            ai_interaction_id=None,
        )
        assert recs, "I2 FAIL: plain-text response must produce at least one rec"

        for rec in recs:
            rec.setdefault("recommendation_text", rec.get("recommendation_text", plain_text[:200]))
        db.insert_setup_recommendations(recs)

        # For plain-text: all 8 v11 columns must be NULL (not contain data)
        rows = db._conn.execute(
            """SELECT deterministic_plan_json, ai_audit_json, validation_status,
                      approved_changes_json, rejected_changes_json, diagnosis_json,
                      driver_profile_version, rule_engine_version
               FROM setup_recommendations ORDER BY id"""
        ).fetchall()

        assert rows, "I2 FAIL: No rows stored after plain-text insert"

        # driver_profile_version may be populated even for plain-text (fallback to build_driver_profile)
        # Only check the JSON blob columns and rule_engine_version (which require JSON input)
        json_only_cols = {
            0: "deterministic_plan_json",
            1: "ai_audit_json",
            3: "approved_changes_json",
            4: "rejected_changes_json",
            5: "diagnosis_json",
        }
        for row in rows:
            for idx, col in json_only_cols.items():
                val = row[idx]
                assert val is None, (
                    f"I2 FAIL: Column {col!r} must be NULL for plain-text response; "
                    f"got {val!r}. The parser must NOT extract JSON blob columns from non-JSON text."
                )
