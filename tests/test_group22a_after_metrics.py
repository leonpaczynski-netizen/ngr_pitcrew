"""Group 22A — after_metrics population on update_recommendation_outcome.

Tests:
  1. after_metrics is populated from the outcome session on first call.
  2. after_metrics is NOT overwritten when update_recommendation_outcome is
     called again with a different session (preserve first capture).
  3. after_metrics contains the required keys: best_lap_ms, avg_fuel_per_lap,
     lap_count.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

from data.session_db import SessionDB


def _make_db() -> SessionDB:
    return SessionDB(":memory:")


def _insert_session(db: SessionDB, car_id: int = 1, track: str = "Spa") -> int:
    return db.open_session(car_id, track, "Race", car_name="TestCar")


def _insert_lap(
    db: SessionDB,
    session_id: int,
    lap_time_ms: int,
    fuel_used: float = 1.8,
    is_pit_lap: int = 0,
) -> None:
    with db._lock:
        db._conn.execute(
            """INSERT INTO lap_records
               (session_id, car_id, track, lap_num, lap_time_ms, fuel_used,
                lock_up_count, wheelspin_count, brake_consistency_m,
                max_speed_kmh, avg_throttle_pct, avg_brake_pct, compound,
                is_pit_lap)
               VALUES (?,1,'Spa',1,?,?,0,0,0.0,200.0,60.0,20.0,'',?)""",
            (session_id, lap_time_ms, fuel_used, is_pit_lap),
        )
        db._conn.commit()


def _insert_rec(
    db: SessionDB,
    car_id: int = 1,
    track: str = "Spa",
    session_id: int = 1,
    after_metrics: str = "{}",
) -> int:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with db._lock:
        cur = db._conn.execute(
            """INSERT INTO setup_recommendations
               (ai_interaction_id, session_id, car_id, track, layout_id,
                feature, recommendation_text, status, outcome,
                before_metrics, after_metrics, created_at)
               VALUES (NULL,?,?,?,'','setup','Lower ride height.','proposed',
                       'not_verified','{}',?,?)""",
            (session_id, car_id, track, after_metrics, now),
        )
        db._conn.commit()
        return cur.lastrowid


class TestAfterMetricsPopulated(unittest.TestCase):

    def test_after_metrics_populated_on_first_call(self):
        """after_metrics is filled from outcome session on first update call."""
        db = _make_db()
        rec_session = _insert_session(db)
        outcome_session = _insert_session(db)
        _insert_lap(db, outcome_session, 85000, fuel_used=1.9)
        _insert_lap(db, outcome_session, 83000, fuel_used=2.1)
        rec_id = _insert_rec(db, session_id=rec_session)

        db.update_recommendation_outcome(rec_id, "improved", outcome_session)

        with db._lock:
            row = db._conn.execute(
                "SELECT after_metrics FROM setup_recommendations WHERE id = ?",
                (rec_id,),
            ).fetchone()
        after = json.loads(row[0])
        self.assertEqual(after["best_lap_ms"], 83000)
        self.assertGreater(after["avg_fuel_per_lap"], 0)
        self.assertEqual(after["lap_count"], 2)

    def test_after_metrics_not_overwritten_on_second_call(self):
        """after_metrics is preserved — second call with different session must not change it."""
        db = _make_db()
        rec_session = _insert_session(db)
        first_outcome = _insert_session(db)
        second_outcome = _insert_session(db)

        _insert_lap(db, first_outcome, 80000, fuel_used=1.5)
        _insert_lap(db, second_outcome, 95000, fuel_used=3.0)

        rec_id = _insert_rec(db, session_id=rec_session)

        # First call — populates after_metrics
        db.update_recommendation_outcome(rec_id, "improved", first_outcome)

        with db._lock:
            row = db._conn.execute(
                "SELECT after_metrics FROM setup_recommendations WHERE id = ?",
                (rec_id,),
            ).fetchone()
        first_after = json.loads(row[0])

        # Second call — must NOT overwrite
        db.update_recommendation_outcome(rec_id, "worsened", second_outcome)

        with db._lock:
            row = db._conn.execute(
                "SELECT after_metrics FROM setup_recommendations WHERE id = ?",
                (rec_id,),
            ).fetchone()
        second_after = json.loads(row[0])

        # The best_lap_ms should still be from the first outcome session
        self.assertEqual(second_after["best_lap_ms"], first_after["best_lap_ms"])
        self.assertEqual(second_after["best_lap_ms"], 80000)

    def test_after_metrics_contains_required_keys(self):
        """after_metrics dict always contains best_lap_ms, avg_fuel_per_lap, lap_count."""
        db = _make_db()
        rec_session = _insert_session(db)
        outcome_session = _insert_session(db)
        _insert_lap(db, outcome_session, 90000, fuel_used=2.0)
        rec_id = _insert_rec(db, session_id=rec_session)

        db.update_recommendation_outcome(rec_id, "improved", outcome_session)

        with db._lock:
            row = db._conn.execute(
                "SELECT after_metrics FROM setup_recommendations WHERE id = ?",
                (rec_id,),
            ).fetchone()
        after = json.loads(row[0])
        for key in ("best_lap_ms", "avg_fuel_per_lap", "lap_count"):
            self.assertIn(key, after, f"Key '{key}' missing from after_metrics")


if __name__ == "__main__":
    unittest.main()
