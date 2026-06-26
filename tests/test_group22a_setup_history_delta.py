"""Group 22A — get_setup_history_for_car_track delta block and issue list.

Tests:
  1. Delta block present when both before/after_metrics are set; lap delta sign
     correct; fuel delta has sign.
  2. Delta block absent when after_metrics is '{}'.
  3. Target issues line present when corner_issue_ids populated.
"""
from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

from data.session_db import SessionDB


def _make_db() -> SessionDB:
    return SessionDB(":memory:")


def _insert_session(db: SessionDB, car_id: int = 1, track: str = "Monza") -> int:
    return db.open_session(car_id, track, "Race", car_name="TestCar")


def _insert_rec_full(
    db: SessionDB,
    car_id: int = 1,
    track: str = "Monza",
    session_id: int = 1,
    before_metrics: str = "{}",
    after_metrics: str = "{}",
    corner_issue_ids: str = "[]",
    rec_text: str = "Stiffen rear.",
) -> int:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with db._lock:
        cur = db._conn.execute(
            """INSERT INTO setup_recommendations
               (ai_interaction_id, session_id, car_id, track, layout_id,
                feature, recommendation_text, status, outcome,
                before_metrics, after_metrics, corner_issue_ids, created_at)
               VALUES (NULL,?,?,?,'','setup',?,'applied','improved',?,?,?,?)""",
            (session_id, car_id, track, rec_text,
             before_metrics, after_metrics, corner_issue_ids, now),
        )
        db._conn.commit()
        return cur.lastrowid


class TestDeltaBlock(unittest.TestCase):

    def test_delta_block_present_with_correct_signs(self):
        """Delta block appears; lap delta sign is correct; fuel delta has sign."""
        db = _make_db()
        sid = _insert_session(db)
        before = json.dumps({"best_lap_ms": 90000, "avg_fuel_per_lap": 2.0, "lap_count": 5})
        after = json.dumps({"best_lap_ms": 88000, "avg_fuel_per_lap": 1.8, "lap_count": 7})
        _insert_rec_full(db, session_id=sid, before_metrics=before, after_metrics=after)

        result = db.get_setup_history_for_car_track(1, "Monza")

        self.assertIn("Outcome metrics", result)
        # lap_delta_ms = 88000 - 90000 = -2000 (faster)
        self.assertIn("-2000", result)
        self.assertIn("faster", result)
        # fuel_delta = 1.8 - 2.0 = -0.20
        self.assertIn("-0.20", result)

    def test_delta_block_slower(self):
        """Delta block shows 'slower' when after best_lap_ms is larger."""
        db = _make_db()
        sid = _insert_session(db)
        before = json.dumps({"best_lap_ms": 85000, "avg_fuel_per_lap": 1.5, "lap_count": 4})
        after = json.dumps({"best_lap_ms": 87000, "avg_fuel_per_lap": 1.6, "lap_count": 4})
        _insert_rec_full(db, session_id=sid, before_metrics=before, after_metrics=after)

        result = db.get_setup_history_for_car_track(1, "Monza")

        self.assertIn("slower", result)
        self.assertIn("+2000", result)

    def test_delta_block_absent_when_after_metrics_empty(self):
        """Delta block must not appear when after_metrics is '{}'."""
        db = _make_db()
        sid = _insert_session(db)
        before = json.dumps({"best_lap_ms": 90000, "avg_fuel_per_lap": 2.0, "lap_count": 5})
        _insert_rec_full(db, session_id=sid, before_metrics=before, after_metrics="{}")

        result = db.get_setup_history_for_car_track(1, "Monza")

        self.assertNotIn("Outcome metrics", result)

    def test_target_issues_line_present_when_populated(self):
        """Target issues line appears when corner_issue_ids has valid IDs."""
        db = _make_db()
        sid = _insert_session(db)

        # Insert a corner issue directly
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with db._lock:
            cur = db._conn.execute(
                """INSERT INTO corner_issues
                   (car_id, track, corner_id, issue_type, phase,
                    lap_count, total_laps, severity, confidence,
                    evidence, session_id, detected_at)
                   VALUES (1,'Monza','T1','oversteer','exit',3,10,0.75,0.9,'',?,?)""",
                (sid, now),
            )
            db._conn.commit()
            issue_id = cur.lastrowid

        ids_json = json.dumps([issue_id])
        before = json.dumps({"best_lap_ms": 90000, "avg_fuel_per_lap": 2.0, "lap_count": 5})
        after = json.dumps({"best_lap_ms": 88000, "avg_fuel_per_lap": 1.9, "lap_count": 5})
        _insert_rec_full(
            db, session_id=sid,
            before_metrics=before, after_metrics=after,
            corner_issue_ids=ids_json,
        )

        result = db.get_setup_history_for_car_track(1, "Monza")

        self.assertIn("Target issues", result)
        self.assertIn("oversteer", result)
        self.assertIn("T1", result)


if __name__ == "__main__":
    unittest.main()
