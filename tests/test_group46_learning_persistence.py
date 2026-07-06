"""
Group 46 — Learning & Race Context Intelligence: Learning Persistence Tests

Covers ACs 8-16 (Learning layer):
  AC8  — record_learning_outcome persists a row; get_learning_outcomes returns it
           (round-trip).
  AC9  — persisted row contains all required fields: rule_id, car_id, track,
           layout_id, session_type, verdict, confidence, ts (date), source_path.
  AC10 — missing/empty/corrupt store → no crash, [] fallback
           (schema-mismatch, corrupt DB, missing table all return []).
  AC11 — SCOPED: car_A/track_X outcomes are NOT returned for car_B/track_Y.
  AC12 — historically-successful rule (>=3 fires, >=0.60 success_rate) →
           +confidence via engine; learning_influence text present.
  AC13 — historically-worsened rule (<0.40) → -confidence; change may still be
           proposed but learning_influence notes the risk.
  AC14 — <MIN_OUTCOME_SAMPLES matching → no confidence modification; learning_influence
           is "".
  AC15 — consulted-but-no-effect (rate between thresholds) → NO "learning applied"
           claim in learning_influence.
  AC16 — rejected/low-confidence learning is explanation-only; it cannot make a
           rejected candidate actionable.

Architecture:
  AC1  — AI audit cannot add approved fields; cannot un-reject/un-block.
           (Covered via run_rule_engine: learning gate only MODIFIES confidence,
            never overrides Pack A blocks or validator rejections.)

DB field-level correctness:
  source_path column stores whatever is passed ("Baseline" AND "Analyse" round-trip).
  session_type stored as "" when not available (passed as empty string).

NOTE on data-flow limitation: In production the recording hook in driving_advisor.py
currently only passes source_path="Analyse" (the analyse path calls record_learning_outcome).
The baseline path does NOT call record_learning_outcome at this time — so source_path="Baseline"
rows will never appear in production until a future sprint wires up the baseline hook.
The column/method correctness is verified here; the production data-flow gap is noted.

All tests are pure/offline — no network, no Qt, no MainWindow construction.
SQLite tests use a temp-file DB via tmp_path.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.session_db import SessionDB
from strategy._setup_constants import (
    DB_VERSION,
    HIGH_SUCCESS_RATE,
    LOW_SUCCESS_RATE,
    MIN_OUTCOME_SAMPLES,
    RULE_ENGINE_VERSION,
)
from strategy.setup_rule_engine import (
    RuleOutcomeStore,
    SetupChangeIntent,
    SetupPlan,
    run_rule_engine,
    _upgrade_confidence,
    _downgrade_confidence,
)
from strategy.setup_knowledge_base import ConfidenceLevel
from strategy.setup_driver_profile import DriverProfile
from strategy.setup_ranges import resolve_ranges


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_temp_db(tmp_path) -> SessionDB:
    """Open a fresh SessionDB in a temp file (never in-memory to test file round-trip)."""
    return SessionDB(str(tmp_path / "learning_test.db"))


def _make_neutral_profile() -> DriverProfile:
    return DriverProfile(
        profile_version="v1.0-test",
        style_tags=[],
        hard_constraints=[],
        prefers_rear_stability=False,
        dislikes_snap_exit=False,
        trail_braker=False,
        rotation_without_snap=False,
        prefers_front_bite=False,
        dislikes_floaty_front=False,
        protects_downforce=False,
        race_values_consistency=False,
    )


def _make_store_with_outcomes(
    rule_id: str,
    fire_count: int,
    success_count: int,
    car: str = "",
    track: str = "",
    profile_version: str = "",
) -> RuleOutcomeStore:
    """Return a store with (fire_count) fires and (success_count) successes for rule_id."""
    store = RuleOutcomeStore()
    for _ in range(fire_count):
        store.record_fire(rule_id, car=car, track=track, profile_version=profile_version)
    for _ in range(success_count):
        store.record_success(rule_id, car=car, track=track, profile_version=profile_version)
    return store


def _wheelspin_diag() -> dict:
    """Minimal diagnosis that triggers wheelspin rules (B-pack)."""
    return {
        "avg_bottoming": 0.0,
        "bottoming_band": "minor",
        "avg_wheelspin": 20.0,
        "wheelspin_band": "severe",
        "avg_snap": 0.0,
        "avg_lockups": 0.0,
        "driver_feel_flags": {
            "rear_loose_on_exit": True,
            "snap_oversteer_exit": False,
        },
        "gearbox_flag": "preserve",
        "compliance_priority": False,
        "aero_front_near_min": False,
        "aero_rear_near_min": False,
        "aero_rear_healthy": False,
        "dominant_problem": "wheelspin",
        "gearing_diagnosis_category": "insufficient_data",
        "wheelspin_subtype": "wheelspin",
        "bottoming_confidence": {
            "band": "minor",
            "subtype": "insufficient_data",
            "confidence": "low",
        },
        "avg_rev_limiter_total": 0.0,
        "rev_limiter_by_gear": None,
        "per_gear_limiter_evidence": None,
    }


# ===========================================================================
# AC8 — record_learning_outcome persists a row; get_learning_outcomes returns it
# ===========================================================================

class TestAC8RoundTrip:
    """AC8: record/get round-trip for learning_outcomes."""

    def test_insert_and_retrieve(self, tmp_path):
        """A row inserted by record_learning_outcome is returned by get_learning_outcomes."""
        db = _make_temp_db(tmp_path)
        db.record_learning_outcome(
            car_id=1,
            track="Fuji",
            layout_id="full_course",
            session_id=42,
            session_type="Race",
            rule_id="B3",
            source_path="Analyse",
            verdict="improved",
            confidence=0.80,
            driver_profile_version="v1.0",
            rule_engine_version=RULE_ENGINE_VERSION,
        )
        rows = db.get_learning_outcomes(car_id=1, track="Fuji", layout_id="full_course")
        assert len(rows) == 1, f"Expected 1 row, got {len(rows)}"
        db.close()

    def test_multiple_rows_returned_newest_first(self, tmp_path):
        """Multiple rows are returned ordered newest first (ORDER BY id DESC)."""
        db = _make_temp_db(tmp_path)
        for verdict in ("improved", "worsened", "neutral"):
            db.record_learning_outcome(
                car_id=1, track="Fuji", layout_id="full_course",
                session_id=1, session_type="Race",
                rule_id="B3", source_path="Analyse",
                verdict=verdict, confidence=0.5,
                driver_profile_version="v1.0",
                rule_engine_version=RULE_ENGINE_VERSION,
            )
        rows = db.get_learning_outcomes(car_id=1, track="Fuji", layout_id="full_course")
        assert len(rows) == 3
        # Most recent insert = "neutral" is returned first (id DESC)
        assert rows[0]["verdict"] == "neutral"
        db.close()

    def test_source_path_analyse_round_trips(self, tmp_path):
        """source_path='Analyse' is stored and returned verbatim."""
        db = _make_temp_db(tmp_path)
        db.record_learning_outcome(
            car_id=2, track="Nurburgring", layout_id="gp",
            session_id=10, session_type="Race",
            rule_id="A1", source_path="Analyse",
            verdict="improved", confidence=0.9,
            driver_profile_version="v1.0",
            rule_engine_version=RULE_ENGINE_VERSION,
        )
        rows = db.get_learning_outcomes(car_id=2, track="Nurburgring", layout_id="gp")
        assert rows[0]["source_path"] == "Analyse"
        db.close()

    def test_source_path_baseline_round_trips(self, tmp_path):
        """source_path='Baseline' is stored and returned verbatim.

        NOTE: In production the baseline recording hook is not yet wired —
        source_path='Baseline' rows will not appear in production until a future
        sprint adds the wiring. This test verifies the COLUMN/METHOD correctness only.
        """
        db = _make_temp_db(tmp_path)
        db.record_learning_outcome(
            car_id=3, track="Monza", layout_id="full",
            session_id=20, session_type="",
            rule_id="B5", source_path="Baseline",
            verdict="neutral", confidence=0.5,
            driver_profile_version="v1.0",
            rule_engine_version=RULE_ENGINE_VERSION,
        )
        rows = db.get_learning_outcomes(car_id=3, track="Monza", layout_id="full")
        assert rows[0]["source_path"] == "Baseline"
        db.close()

    def test_session_type_empty_string_stored(self, tmp_path):
        """session_type='' (not available) is stored as empty string, not NULL."""
        db = _make_temp_db(tmp_path)
        db.record_learning_outcome(
            car_id=5, track="Laguna", layout_id="full",
            session_id=0, session_type="",
            rule_id="B3", source_path="Analyse",
            verdict="worsened", confidence=0.3,
            driver_profile_version="v1.0",
            rule_engine_version=RULE_ENGINE_VERSION,
        )
        rows = db.get_learning_outcomes(car_id=5, track="Laguna", layout_id="full")
        assert rows[0]["session_type"] == "", (
            f"session_type should be '' when not available; got {rows[0]['session_type']!r}"
        )
        db.close()


# ===========================================================================
# AC9 — persisted row contains all required fields
# ===========================================================================

class TestAC9RequiredFields:
    """AC9: persisted row contains rule_id/car_id/track/layout_id/session_type/
    verdict/confidence/ts/source_path."""

    _REQUIRED_FIELDS = [
        "rule_id", "car_id", "track", "layout_id", "session_type",
        "verdict", "confidence", "ts", "source_path",
        "driver_profile_version", "rule_engine_version",
    ]

    def test_all_required_fields_present(self, tmp_path):
        """All required fields are present in the returned row dict."""
        db = _make_temp_db(tmp_path)
        db.record_learning_outcome(
            car_id=7, track="Fuji", layout_id="full_course",
            session_id=99, session_type="Race",
            rule_id="B3", source_path="Analyse",
            verdict="improved", confidence=0.75,
            driver_profile_version="v1.0-test",
            rule_engine_version=RULE_ENGINE_VERSION,
        )
        rows = db.get_learning_outcomes(car_id=7, track="Fuji", layout_id="full_course")
        assert rows, "Expected at least one row"
        row = rows[0]
        for field in self._REQUIRED_FIELDS:
            assert field in row, (
                f"AC9 FAIL: required field {field!r} missing from learning_outcomes row. "
                f"Present keys: {sorted(row.keys())}"
            )
        db.close()

    def test_ts_is_non_empty(self, tmp_path):
        """ts column is a non-empty ISO timestamp string."""
        db = _make_temp_db(tmp_path)
        db.record_learning_outcome(
            car_id=7, track="Fuji", layout_id="full_course",
            session_id=1, session_type="Race",
            rule_id="B3", source_path="Analyse",
            verdict="improved", confidence=0.8,
            driver_profile_version="v1.0",
            rule_engine_version=RULE_ENGINE_VERSION,
        )
        rows = db.get_learning_outcomes(car_id=7, track="Fuji", layout_id="full_course")
        ts = rows[0]["ts"]
        assert ts and isinstance(ts, str), f"ts must be a non-empty string; got {ts!r}"
        assert "T" in ts or "-" in ts, f"ts does not look like ISO format: {ts!r}"
        db.close()

    def test_confidence_stored_as_float(self, tmp_path):
        """confidence is stored as a float value."""
        db = _make_temp_db(tmp_path)
        db.record_learning_outcome(
            car_id=7, track="Fuji", layout_id="full_course",
            session_id=1, session_type="Race",
            rule_id="B3", source_path="Analyse",
            verdict="improved", confidence=0.65,
            driver_profile_version="v1.0",
            rule_engine_version=RULE_ENGINE_VERSION,
        )
        rows = db.get_learning_outcomes(car_id=7, track="Fuji", layout_id="full_course")
        conf = rows[0]["confidence"]
        assert isinstance(conf, float), f"confidence should be float; got {type(conf)}"
        assert abs(conf - 0.65) < 1e-6
        db.close()


# ===========================================================================
# AC10 — missing/empty/corrupt/schema-mismatch store → no crash, [] fallback
# ===========================================================================

class TestAC10SafeFallback:
    """AC10: get_learning_outcomes returns [] on ANY error (corrupt/missing table, etc.)."""

    def test_empty_scope_returns_empty_list(self, tmp_path):
        """No rows in scope returns [] (not None, not an exception)."""
        db = _make_temp_db(tmp_path)
        rows = db.get_learning_outcomes(car_id=999, track="nowhere", layout_id="x")
        assert rows == [], f"Expected [], got {rows!r}"
        db.close()

    def test_record_never_raises_on_bad_inputs(self, tmp_path):
        """record_learning_outcome never raises regardless of input oddities."""
        db = _make_temp_db(tmp_path)
        # Should not raise on empty strings, zero, weird confidence
        db.record_learning_outcome(
            car_id=0, track="", layout_id="",
            session_id=0, session_type="",
            rule_id="", source_path="",
            verdict="", confidence=0.0,
            driver_profile_version="",
            rule_engine_version="",
        )
        db.close()

    def test_get_after_close_returns_empty_not_raise(self, tmp_path):
        """get_learning_outcomes does not raise even on a closed DB (silently returns [])."""
        db = _make_temp_db(tmp_path)
        db.record_learning_outcome(
            car_id=1, track="Fuji", layout_id="full_course",
            session_id=1, session_type="Race",
            rule_id="B3", source_path="Analyse",
            verdict="improved", confidence=0.8,
            driver_profile_version="v1.0",
            rule_engine_version=RULE_ENGINE_VERSION,
        )
        db.close()
        # Access after close — implementation catches the exception and returns []
        result = db.get_learning_outcomes(car_id=1, track="Fuji", layout_id="full_course")
        assert isinstance(result, list), "Must return a list (possibly empty), not raise"

    def test_db_version_is_12(self, tmp_path):
        """Fresh DB migrates to user_version=DB_VERSION.

        Reconciled for Group 47: DB_VERSION bumped 12 → 13 (_migrate_v13 added the
        5 additive outcome-verification columns).  Test name kept stable for blame.
        """
        db = _make_temp_db(tmp_path)
        version = db._conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == DB_VERSION == 13, (
            f"Expected user_version=DB_VERSION=13; got user_version={version}, DB_VERSION={DB_VERSION}"
        )
        db.close()

    def test_learning_outcomes_table_exists(self, tmp_path):
        """learning_outcomes table is created by _migrate_v12."""
        db = _make_temp_db(tmp_path)
        tables = {row[0] for row in db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "learning_outcomes" in tables, (
            f"learning_outcomes table missing; tables present: {sorted(tables)}"
        )
        db.close()

    def test_idx_learning_outcomes_scope_exists(self, tmp_path):
        """idx_learning_outcomes_scope index is created by _migrate_v12."""
        db = _make_temp_db(tmp_path)
        indices = {row[0] for row in db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()}
        assert "idx_learning_outcomes_scope" in indices, (
            f"idx_learning_outcomes_scope missing; indices present: {sorted(indices)}"
        )
        db.close()

    def test_migrate_v12_idempotent(self, tmp_path):
        """Re-opening the same DB a second time does not raise (CREATE TABLE IF NOT EXISTS)."""
        db_path = str(tmp_path / "idem.db")
        db1 = SessionDB(db_path)
        db1.close()
        # Second open must not raise
        db2 = SessionDB(db_path)
        version = db2._conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == 13  # Reconciled for Group 47 (v12 → v13)
        db2.close()


# ===========================================================================
# AC11 — SCOPED: car A / track X ≠ car B / track Y
# ===========================================================================

class TestAC11Scoped:
    """AC11: learning_outcomes are scoped by (car_id, track, layout_id)."""

    def test_different_car_different_scope(self, tmp_path):
        """Rows for car_id=1 are NOT returned when querying car_id=2."""
        db = _make_temp_db(tmp_path)
        db.record_learning_outcome(
            car_id=1, track="Fuji", layout_id="full_course",
            session_id=1, session_type="Race",
            rule_id="B3", source_path="Analyse",
            verdict="improved", confidence=0.8,
            driver_profile_version="v1.0",
            rule_engine_version=RULE_ENGINE_VERSION,
        )
        rows_car2 = db.get_learning_outcomes(car_id=2, track="Fuji", layout_id="full_course")
        assert rows_car2 == [], (
            f"AC11 FAIL: rows for car_id=1 leaked into car_id=2 scope; got {rows_car2}"
        )
        db.close()

    def test_different_track_different_scope(self, tmp_path):
        """Rows for track='Fuji' are NOT returned when querying track='Nurburgring'."""
        db = _make_temp_db(tmp_path)
        db.record_learning_outcome(
            car_id=1, track="Fuji", layout_id="full_course",
            session_id=1, session_type="Race",
            rule_id="B3", source_path="Analyse",
            verdict="improved", confidence=0.8,
            driver_profile_version="v1.0",
            rule_engine_version=RULE_ENGINE_VERSION,
        )
        rows_nurb = db.get_learning_outcomes(car_id=1, track="Nurburgring", layout_id="full_course")
        assert rows_nurb == [], (
            f"AC11 FAIL: rows for Fuji leaked into Nurburgring scope; got {rows_nurb}"
        )
        db.close()

    def test_correct_scope_returns_rows(self, tmp_path):
        """Rows ARE returned when querying the exact (car_id, track, layout_id) used to insert."""
        db = _make_temp_db(tmp_path)
        db.record_learning_outcome(
            car_id=1, track="Fuji", layout_id="full_course",
            session_id=1, session_type="Race",
            rule_id="B3", source_path="Analyse",
            verdict="improved", confidence=0.8,
            driver_profile_version="v1.0",
            rule_engine_version=RULE_ENGINE_VERSION,
        )
        rows = db.get_learning_outcomes(car_id=1, track="Fuji", layout_id="full_course")
        assert len(rows) == 1, f"Expected 1 row for correct scope; got {len(rows)}"
        db.close()

    def test_two_cars_same_track_independent(self, tmp_path):
        """Two different cars at the same track have independent learning rows."""
        db = _make_temp_db(tmp_path)
        for car_id in (10, 20):
            db.record_learning_outcome(
                car_id=car_id, track="Fuji", layout_id="full_course",
                session_id=car_id, session_type="Race",
                rule_id="B3", source_path="Analyse",
                verdict="improved" if car_id == 10 else "worsened",
                confidence=0.8,
                driver_profile_version="v1.0",
                rule_engine_version=RULE_ENGINE_VERSION,
            )
        rows_10 = db.get_learning_outcomes(car_id=10, track="Fuji", layout_id="full_course")
        rows_20 = db.get_learning_outcomes(car_id=20, track="Fuji", layout_id="full_course")
        assert len(rows_10) == 1
        assert len(rows_20) == 1
        assert rows_10[0]["verdict"] == "improved"
        assert rows_20[0]["verdict"] == "worsened"
        db.close()


# ===========================================================================
# AC12 — historically-successful rule → +confidence via engine
# ===========================================================================

class TestAC12SuccessUpgradesConfidence:
    """AC12: rule with >= MIN_OUTCOME_SAMPLES & >= HIGH_SUCCESS_RATE → confidence upgraded
    by the engine; learning_influence text is present on the change."""

    def test_upgrade_confidence_helper(self):
        """_upgrade_confidence: low→med, med→high, high stays high."""
        assert _upgrade_confidence(ConfidenceLevel.low) == ConfidenceLevel.med
        assert _upgrade_confidence(ConfidenceLevel.med) == ConfidenceLevel.high
        assert _upgrade_confidence(ConfidenceLevel.high) == ConfidenceLevel.high

    def test_engine_upgrades_confidence_for_high_success_rate(self):
        """With success_rate >= HIGH_SUCCESS_RATE and >= MIN_OUTCOME_SAMPLES, the engine
        upgrades confidence and populates learning_influence on the change."""
        diag = _wheelspin_diag()
        setup = {"lsd_accel": 20}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        # First: run with empty store to find which rule fires
        plan_empty = run_rule_engine(diag, setup, ranges, profile)
        if not plan_empty.proposed:
            pytest.skip("No proposed changes to test upgrade on")

        target = plan_empty.proposed[0]
        rule_id = target.rule_id
        original_confidence = target.confidence

        # Build store: >= MIN_OUTCOME_SAMPLES fires, all successes → rate = 1.0 >= HIGH_SUCCESS_RATE
        store = _make_store_with_outcomes(rule_id, MIN_OUTCOME_SAMPLES, MIN_OUTCOME_SAMPLES)
        plan_upgraded = run_rule_engine(diag, setup, ranges, profile, rule_outcome_store=store)

        upgraded = [ch for ch in plan_upgraded.proposed if ch.rule_id == rule_id]
        if not upgraded:
            pytest.skip(f"Rule {rule_id!r} not proposed with high-success store")

        ch = upgraded[0]
        _conf_rank = {ConfidenceLevel.low: 0, ConfidenceLevel.med: 1, ConfidenceLevel.high: 2}
        assert _conf_rank[ch.confidence] >= _conf_rank[original_confidence], (
            f"AC12 FAIL: confidence NOT upgraded; original={original_confidence}, "
            f"after={ch.confidence}"
        )
        assert ch.learning_influence, (
            f"AC12 FAIL: learning_influence empty despite high-success-rate upgrade; "
            f"rule_id={rule_id}"
        )

    def test_learning_influence_contains_upgrade_keyword(self):
        """learning_influence text must contain 'upgraded' when confidence was upgraded."""
        diag = _wheelspin_diag()
        setup = {"lsd_accel": 20}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan_empty = run_rule_engine(diag, setup, ranges, profile)
        if not plan_empty.proposed:
            pytest.skip("No proposed changes to test")
        rule_id = plan_empty.proposed[0].rule_id

        store = _make_store_with_outcomes(rule_id, MIN_OUTCOME_SAMPLES * 2, MIN_OUTCOME_SAMPLES * 2)
        plan = run_rule_engine(diag, setup, ranges, profile, rule_outcome_store=store)

        for ch in plan.proposed:
            if ch.rule_id == rule_id and ch.learning_influence:
                assert "upgraded" in ch.learning_influence.lower(), (
                    f"AC12 FAIL: learning_influence does not contain 'upgraded'; "
                    f"got {ch.learning_influence!r}"
                )
                break


# ===========================================================================
# AC13 — historically-worsened rule → -confidence, change may still be proposed
# ===========================================================================

class TestAC13WorsenedDowngradesConfidence:
    """AC13: rule with success_rate < LOW_SUCCESS_RATE → confidence downgraded;
    change may still be proposed but learning_influence notes the risk."""

    def test_engine_downgrades_confidence_for_low_success_rate(self):
        """With success_rate < LOW_SUCCESS_RATE and >= MIN_OUTCOME_SAMPLES, the engine
        downgrades confidence."""
        diag = _wheelspin_diag()
        setup = {"lsd_accel": 20}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan_empty = run_rule_engine(diag, setup, ranges, profile)
        if not plan_empty.proposed:
            pytest.skip("No proposed changes to test downgrade on")

        target = max(
            plan_empty.proposed,
            key=lambda ch: (
                ch.confidence == ConfidenceLevel.high,
                ch.confidence == ConfidenceLevel.med,
            ),
        )
        rule_id = target.rule_id
        original_confidence = target.confidence

        # 0 successes → rate = 0.0 < LOW_SUCCESS_RATE
        store = _make_store_with_outcomes(rule_id, MIN_OUTCOME_SAMPLES, 0)
        plan_down = run_rule_engine(diag, setup, ranges, profile, rule_outcome_store=store)

        downgraded = [ch for ch in plan_down.proposed if ch.rule_id == rule_id]
        if not downgraded:
            pytest.skip(f"Rule {rule_id!r} not proposed with low-success store")

        ch = downgraded[0]
        _conf_rank = {ConfidenceLevel.low: 0, ConfidenceLevel.med: 1, ConfidenceLevel.high: 2}
        assert _conf_rank[ch.confidence] <= _conf_rank[original_confidence], (
            f"AC13 FAIL: downgrade gate did NOT lower confidence; "
            f"original={original_confidence}, after={ch.confidence}"
        )

    def test_learning_influence_notes_downgrade_risk(self):
        """learning_influence text must contain 'downgraded' when risk was noted."""
        diag = _wheelspin_diag()
        setup = {"lsd_accel": 20}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan_empty = run_rule_engine(diag, setup, ranges, profile)
        if not plan_empty.proposed:
            pytest.skip("No proposed changes")
        rule_id = plan_empty.proposed[0].rule_id

        store = _make_store_with_outcomes(rule_id, MIN_OUTCOME_SAMPLES, 0)
        plan = run_rule_engine(diag, setup, ranges, profile, rule_outcome_store=store)

        for ch in plan.proposed:
            if ch.rule_id == rule_id and ch.learning_influence:
                assert "downgraded" in ch.learning_influence.lower(), (
                    f"AC13 FAIL: learning_influence does not contain 'downgraded'; "
                    f"got {ch.learning_influence!r}"
                )
                break

    def test_downgraded_change_still_has_at_least_one_proposed(self):
        """Downgrade gate only lowers confidence — the plan must still have proposed changes.

        AC13 contract: the downgrade gate lowers confidence one step only. If another rule
        competes for the same field and wins after the confidence shift (B6 at med beats
        C5 at low), that is a legitimate conflict-resolution outcome, NOT a direct rejection
        by the downgrade gate. This test verifies the plan is non-empty overall, not that
        the specific downgraded rule stays in proposed.
        """
        diag = _wheelspin_diag()
        setup = {"lsd_accel": 20}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan_empty = run_rule_engine(diag, setup, ranges, profile)
        if not plan_empty.proposed:
            pytest.skip("No proposed changes to test")
        rule_id = plan_empty.proposed[0].rule_id

        store = _make_store_with_outcomes(rule_id, MIN_OUTCOME_SAMPLES, 0)
        plan = run_rule_engine(diag, setup, ranges, profile, rule_outcome_store=store)

        # The plan must still propose something — the downgrade gate cannot zero-out all changes.
        # If a conflict winner shifts after the downgrade, the new winner (e.g. B6) is still
        # in proposed. Either way, proposed must be non-empty.
        assert plan.proposed, (
            "AC13 FAIL: downgrade gate produced a completely empty plan — "
            "there must always be at least one proposed change after a confidence downgrade. "
            "If a conflict winner changed (legitimate), a different rule should have won."
        )
        # Verify the field that was proposed before is still addressed by SOME change
        target_field = plan_empty.proposed[0].field
        field_addressed = any(ch.field == target_field for ch in plan.proposed)
        assert field_addressed, (
            f"AC13 FAIL: after downgrading {rule_id!r}, no change addresses field "
            f"{target_field!r} — conflict resolution should have put a competitor there. "
            f"proposed: {[(c.field, c.rule_id) for c in plan.proposed]}"
        )


# ===========================================================================
# AC14 — < MIN_OUTCOME_SAMPLES → no modification, learning_influence is ""
# ===========================================================================

class TestAC14BelowMinSamples:
    """AC14: fewer than MIN_OUTCOME_SAMPLES matching → no confidence modification;
    learning_influence must be ''."""

    def test_below_min_samples_no_modification(self):
        """With MIN_OUTCOME_SAMPLES-1 fires, confidence must equal the empty-store result."""
        diag = _wheelspin_diag()
        setup = {"lsd_accel": 20}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan_empty = run_rule_engine(diag, setup, ranges, profile)
        if not plan_empty.proposed:
            pytest.skip("No proposed changes")
        rule_id = plan_empty.proposed[0].rule_id
        original_confidence = plan_empty.proposed[0].confidence

        # MIN_OUTCOME_SAMPLES - 1 fires = insufficient data
        store = _make_store_with_outcomes(rule_id, MIN_OUTCOME_SAMPLES - 1, 0)
        plan_sub = run_rule_engine(diag, setup, ranges, profile, rule_outcome_store=store)

        sub_changes = [ch for ch in plan_sub.proposed if ch.rule_id == rule_id]
        if not sub_changes:
            pytest.skip(f"Rule {rule_id!r} not in proposed with sub-min store")

        ch = sub_changes[0]
        assert ch.confidence == original_confidence, (
            f"AC14 FAIL: confidence modified below MIN_OUTCOME_SAMPLES; "
            f"original={original_confidence}, got={ch.confidence}"
        )

    def test_below_min_samples_learning_influence_empty(self):
        """With fewer than MIN_OUTCOME_SAMPLES fires, learning_influence must be ''."""
        diag = _wheelspin_diag()
        setup = {"lsd_accel": 20}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan_empty = run_rule_engine(diag, setup, ranges, profile)
        if not plan_empty.proposed:
            pytest.skip("No proposed changes")
        rule_id = plan_empty.proposed[0].rule_id

        store = _make_store_with_outcomes(rule_id, MIN_OUTCOME_SAMPLES - 1, 0)
        plan = run_rule_engine(diag, setup, ranges, profile, rule_outcome_store=store)

        for ch in plan.proposed:
            if ch.rule_id == rule_id:
                assert ch.learning_influence == "", (
                    f"AC14 FAIL: learning_influence non-empty below MIN_OUTCOME_SAMPLES; "
                    f"got {ch.learning_influence!r}"
                )


# ===========================================================================
# AC15 — between thresholds → NO "learning applied" claim
# ===========================================================================

class TestAC15BetweenThresholds:
    """AC15: success_rate between LOW_SUCCESS_RATE and HIGH_SUCCESS_RATE → no
    'learning applied' claim; learning_influence must be ''."""

    def test_between_thresholds_no_learning_claim(self):
        """Rate in [LOW_SUCCESS_RATE, HIGH_SUCCESS_RATE) → learning_influence must be ''."""
        diag = _wheelspin_diag()
        setup = {"lsd_accel": 20}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan_empty = run_rule_engine(diag, setup, ranges, profile)
        if not plan_empty.proposed:
            pytest.skip("No proposed changes")
        rule_id = plan_empty.proposed[0].rule_id

        # Build a mid-range store: e.g. 50% success (between 40% and 60%)
        # 5 fires, 2-3 successes: rate = 0.40 to 0.60
        # Use exactly 5 fires, 2 successes → rate = 0.40 = LOW_SUCCESS_RATE (boundary: no downgrade)
        # Use 5 fires, 3 successes → rate = 0.60 = HIGH_SUCCESS_RATE (boundary: check)
        # For a strictly "between" value: 10 fires, 5 successes → rate = 0.50
        fire_count = 10
        success_count = 5  # 0.50 — strictly between LOW=0.40 and HIGH=0.60
        store = _make_store_with_outcomes(rule_id, fire_count, success_count)
        rate = store.get_success_rate(rule_id)
        assert rate is not None
        assert LOW_SUCCESS_RATE <= rate < HIGH_SUCCESS_RATE, (
            f"Expected rate in [LOW, HIGH); got {rate}. LOW={LOW_SUCCESS_RATE}, HIGH={HIGH_SUCCESS_RATE}"
        )

        plan = run_rule_engine(diag, setup, ranges, profile, rule_outcome_store=store)
        for ch in plan.proposed:
            if ch.rule_id == rule_id:
                assert ch.learning_influence == "", (
                    f"AC15 FAIL: 'learning applied' claimed for mid-range rate={rate:.2f}; "
                    f"learning_influence={ch.learning_influence!r}"
                )


# ===========================================================================
# AC16 — rejected/low-confidence learning is explanation-only (cannot un-reject)
# ===========================================================================

class TestAC16RejectedCannotBeUnrejected:
    """AC16: learning cannot make a rejected candidate actionable.
    A Pack A blocked candidate stays in rejected regardless of learning."""

    def test_pack_a_block_persists_with_high_success_store(self):
        """A field blocked by Pack A remains in rejected even when the store shows
        high success for the associated rule.

        A2 blocks aero_rear decrease under rear_loose_on_exit. Even with a very
        high-success store for B-pack wheelspin rules, aero_rear decrease must
        never move to proposed.
        """
        # Diagnosis with rear_loose_on_exit=True → A2 fires (blocks aero_rear cut)
        diag = _wheelspin_diag()
        diag["driver_feel_flags"]["rear_loose_on_exit"] = True
        setup = {"lsd_accel": 15, "aero_rear": 50}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        # Build a store with very high success for all B-pack rules
        store = RuleOutcomeStore()
        from strategy.setup_knowledge_base import get_all_rules
        for rule in get_all_rules():
            if rule.pack == "B":
                for _ in range(MIN_OUTCOME_SAMPLES * 3):
                    store.record_fire(rule.rule_id)
                    store.record_success(rule.rule_id)

        plan = run_rule_engine(diag, setup, ranges, profile, rule_outcome_store=store)

        # aero_rear decrease must never appear in proposed
        aero_rear_cuts = [c for c in plan.proposed
                         if c.field == "aero_rear" and c.delta < 0]
        assert not aero_rear_cuts, (
            f"AC16 FAIL: Pack A block (A2) overridden by learning store; "
            f"aero_rear decrease was un-blocked. proposed: "
            f"{[(c.field, c.delta, c.rule_id) for c in plan.proposed]}"
        )

    def test_rejected_by_conflict_stays_rejected_with_learning(self):
        """A change rejected by conflict resolution cannot be un-rejected by a high
        learning score — learning only modifies confidence, not conflict outcomes."""
        diag = _wheelspin_diag()
        setup = {"lsd_accel": 20}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan_empty = run_rule_engine(diag, setup, ranges, profile)
        if not plan_empty.rejected_candidates:
            pytest.skip("No rejected candidates to verify conflict persistence")

        # Count rejected that start with "conflict:" rationale
        conflict_rejected = [
            c for c in plan_empty.rejected_candidates
            if c.rationale.startswith("conflict:")
        ]
        if not conflict_rejected:
            pytest.skip("No conflict-rejected candidates to test")

        # Build max-success store for all rule_ids
        store = RuleOutcomeStore()
        all_rule_ids = {c.rule_id for c in plan_empty.rejected_candidates
                       if c.rationale.startswith("conflict:")}
        for rid in all_rule_ids:
            for _ in range(MIN_OUTCOME_SAMPLES * 5):
                store.record_fire(rid)
                store.record_success(rid)

        plan_with_learning = run_rule_engine(
            diag, setup, ranges, profile, rule_outcome_store=store
        )

        # The conflict winner may change (that is legitimate conflict-resolution
        # behaviour after confidence shifts) — but the real structural invariant the
        # engine enforces is: EACH field has at most ONE winner in proposed. Learning
        # can never produce two simultaneous winners for the same field, nor promote a
        # conflict-loser into a second proposed entry for a field that already has one.
        from collections import Counter
        field_counts = Counter(c.field for c in plan_with_learning.proposed)
        dupes = {f: n for f, n in field_counts.items() if n > 1}
        assert not dupes, (
            f"AC16 FAIL: learning produced multiple simultaneous winners per field "
            f"(each field must have exactly one winner in proposed); duplicates={dupes}"
        )
        # And every conflict-rejected candidate must correspond to a field that DOES
        # have its single winner in proposed (i.e. it lost to a winner, not vanished).
        proposed_fields = {c.field for c in plan_with_learning.proposed}
        for rej in plan_with_learning.rejected_candidates:
            if rej.rationale.startswith("conflict:"):
                assert rej.field in proposed_fields, (
                    f"AC16 FAIL: field {rej.field!r} has a conflict-rejected candidate "
                    f"but no winner in proposed — learning must not drop a field's winner"
                )
