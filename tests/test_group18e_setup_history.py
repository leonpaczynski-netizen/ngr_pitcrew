"""Group 18E — Setup history, before_metrics, and apply recommendation.

Covers:
  1.  get_best_lap_for_session returns minimum lap time
  2.  get_best_lap_for_session returns None when no laps
  3.  get_best_lap_for_session ignores zero lap_time_ms
  4.  update_recommendation_outcome updates correctly
  5.  apply_recommendation_for_car_track marks status='applied'
  6.  apply_recommendation_for_car_track returns None when no proposed row
  7.  apply_recommendation_for_car_track captures metrics in before_metrics
  8.  get_setup_history_for_car_track formats output correctly
  9.  get_setup_history_for_car_track returns "" when no rows
  10. schema v7 migration adds after_metrics/corner_issue_ids columns, PRAGMA user_version=7
  11. build_car_setup signature has setup_history and setup_comparison params
"""
from __future__ import annotations

import inspect
import json
import sqlite3
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

from data.session_db import SessionDB


# ---------------------------------------------------------------------------
# Helper: open an in-memory SessionDB
# ---------------------------------------------------------------------------

def _make_db() -> SessionDB:
    db = SessionDB(":memory:")
    return db


def _insert_session(db: SessionDB, car_id: int = 1, track: str = "Sardegna") -> int:
    return db.open_session(car_id, track, "Race", car_name="TestCar")


def _insert_lap(db: SessionDB, session_id: int, lap_time_ms: int, fuel_used: float = 1.5) -> None:
    with db._lock:
        db._conn.execute(
            """INSERT INTO lap_records
               (session_id, car_id, track, lap_num, lap_time_ms, fuel_used,
                lock_up_count, wheelspin_count, brake_consistency_m,
                max_speed_kmh, avg_throttle_pct, avg_brake_pct, compound)
               VALUES (?,1,'Sardegna',1,?,?,0,0,0.0,200.0,60.0,20.0,'')""",
            (session_id, lap_time_ms, fuel_used),
        )
        db._conn.commit()


def _insert_rec(
    db: SessionDB,
    car_id: int = 1,
    track: str = "Sardegna",
    session_id: int = 1,
    status: str = "proposed",
    rec_text: str = "Lower ride height.",
    before_metrics: str = "{}",
) -> int:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with db._lock:
        cur = db._conn.execute(
            """INSERT INTO setup_recommendations
               (ai_interaction_id, session_id, car_id, track, layout_id,
                feature, recommendation_text, status, outcome, before_metrics, created_at)
               VALUES (NULL,?,?,?,'','setup',?,?,'not_verified',?,?)""",
            (session_id, car_id, track, rec_text, status, before_metrics, now),
        )
        db._conn.commit()
        return cur.lastrowid


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGetBestLap(unittest.TestCase):

    def test_get_best_lap_returns_minimum(self):
        db = _make_db()
        sid = _insert_session(db)
        _insert_lap(db, sid, 90000)
        _insert_lap(db, sid, 85000)
        _insert_lap(db, sid, 92000)
        result = db.get_best_lap_for_session(sid)
        self.assertEqual(result, 85000)

    def test_get_best_lap_returns_none_no_laps(self):
        db = _make_db()
        sid = _insert_session(db)
        result = db.get_best_lap_for_session(sid)
        self.assertIsNone(result)

    def test_get_best_lap_ignores_zero(self):
        db = _make_db()
        sid = _insert_session(db)
        _insert_lap(db, sid, 0)
        result = db.get_best_lap_for_session(sid)
        self.assertIsNone(result)


class TestUpdateOutcome(unittest.TestCase):

    def test_update_outcome_updates_correctly(self):
        db = _make_db()
        sid = _insert_session(db)
        rec_id = _insert_rec(db, session_id=sid)
        db.update_recommendation_outcome(rec_id, "improved", sid)
        with db._lock:
            row = db._conn.execute(
                "SELECT outcome, outcome_session_id FROM setup_recommendations WHERE id = ?",
                (rec_id,),
            ).fetchone()
        self.assertEqual(row[0], "improved")
        self.assertEqual(row[1], sid)


class TestApplyRecommendation(unittest.TestCase):

    def test_apply_recommendation_marks_applied(self):
        db = _make_db()
        sid = _insert_session(db)
        _insert_lap(db, sid, 88000)
        rec_id = _insert_rec(db, session_id=sid)
        new_sid = _insert_session(db)
        returned = db.apply_recommendation_for_car_track(1, "Sardegna", new_sid)
        self.assertEqual(returned, rec_id)
        with db._lock:
            row = db._conn.execute(
                "SELECT status, before_metrics FROM setup_recommendations WHERE id = ?",
                (rec_id,),
            ).fetchone()
        self.assertEqual(row[0], "applied")
        metrics = json.loads(row[1])
        self.assertIn("best_lap_ms", metrics)

    def test_apply_recommendation_returns_none_no_proposed(self):
        db = _make_db()
        sid = _insert_session(db)
        _insert_rec(db, session_id=sid, status="applied")
        new_sid = _insert_session(db)
        result = db.apply_recommendation_for_car_track(1, "Sardegna", new_sid)
        self.assertIsNone(result)

    def test_apply_recommendation_captures_metrics(self):
        db = _make_db()
        sid = _insert_session(db)
        _insert_lap(db, sid, 91000, fuel_used=2.1)
        _insert_lap(db, sid, 89000, fuel_used=1.9)
        _insert_rec(db, session_id=sid)
        new_sid = _insert_session(db)
        rec_id = db.apply_recommendation_for_car_track(1, "Sardegna", new_sid)
        self.assertIsNotNone(rec_id)
        with db._lock:
            row = db._conn.execute(
                "SELECT before_metrics FROM setup_recommendations WHERE id = ?",
                (rec_id,),
            ).fetchone()
        metrics = json.loads(row[0])
        self.assertEqual(metrics["best_lap_ms"], 89000)
        self.assertAlmostEqual(metrics["avg_fuel_per_lap"], 2.0, places=1)


class TestGetSetupHistory(unittest.TestCase):

    def test_get_setup_history_formats_correctly(self):
        db = _make_db()
        sid = _insert_session(db)
        before = json.dumps({"best_lap_ms": 87500, "avg_fuel_per_lap": 1.75, "lap_count": 10})
        _insert_rec(db, session_id=sid, status="applied", rec_text="Soften front springs.",
                    before_metrics=before)
        _insert_rec(db, session_id=sid, status="proposed", rec_text="Increase brake bias.",
                    before_metrics="{}")
        result = db.get_setup_history_for_car_track(1, "Sardegna")
        self.assertIn("Status: applied", result)
        self.assertIn("Status: proposed", result)
        self.assertIn("Soften front springs.", result)
        self.assertIn("Increase brake bias.", result)
        self.assertIn("1:27.500", result)

    def test_get_setup_history_empty(self):
        db = _make_db()
        result = db.get_setup_history_for_car_track(99, "NoTrack")
        self.assertEqual(result, "")


class TestMigrationV6(unittest.TestCase):

    def test_migration_v6_adds_column(self):
        db = _make_db()
        # Check column exists
        with db._lock:
            cols = db._conn.execute(
                "PRAGMA table_info(setup_recommendations)"
            ).fetchall()
        col_names = [c[1] for c in cols]
        self.assertIn("before_metrics", col_names)
        # Check user_version — v10 is the current schema (driver_feedback gained
        # setup_id + rating on top of the OFR-1 scoring columns).
        with db._lock:
            version = db._conn.execute("PRAGMA user_version").fetchone()[0]
        self.assertEqual(version, 10)


class TestBuildCarSetupSignature(unittest.TestCase):

    def test_build_car_setup_has_new_params(self):
        from strategy.ai_planner import build_car_setup
        sig = inspect.signature(build_car_setup)
        params = sig.parameters
        self.assertIn("setup_history", params)
        self.assertIn("setup_comparison", params)
        self.assertEqual(params["setup_history"].default, "")
        self.assertEqual(params["setup_comparison"].default, "")

    def test_build_car_setup_injects_history_and_comparison_into_prompt(self):
        """AC1: setup_history and setup_comparison are actually placed in the prompt text."""
        from strategy.ai_planner import _build_setup_from_scratch_prompt
        history_text = "HISTORY_SENTINEL_XYZ"
        comparison_text = "COMPARISON_SENTINEL_ABC"
        prompt = _build_setup_from_scratch_prompt(
            car="TestCar",
            track="Sardegna",
            session_type="Race",
            race_laps=10,
            min_weight_kg=0,
            max_power_hp=0,
            setup_history=history_text,
            setup_comparison=comparison_text,
        )
        self.assertIn(history_text, prompt,
                      "setup_history sentinel not found in generated prompt")
        self.assertIn(comparison_text, prompt,
                      "setup_comparison sentinel not found in generated prompt")

    def test_build_car_setup_omits_history_blocks_when_empty(self):
        """AC1 edge case: empty strings produce no spurious section headers."""
        from strategy.ai_planner import _build_setup_from_scratch_prompt
        prompt = _build_setup_from_scratch_prompt(
            car="TestCar",
            track="Sardegna",
            session_type="Race",
            race_laps=10,
            min_weight_kg=0,
            max_power_hp=0,
            setup_history="",
            setup_comparison="",
        )
        self.assertNotIn("Previous Setup Recommendations", prompt)
        self.assertNotIn("Setup Performance Comparison", prompt)


if __name__ == "__main__":
    unittest.main()
