"""Group 22A — get_setup_history_for_car_track deadlock regression guard.

The generative-AI track-context / ai_planner car_name forwarding tests
(strategy.track_context_prompt.get_track_context_for_ai, analyse_strategy,
analyse_practice_session, build_car_setup) were removed with the AI purge.
The deterministic SessionDB deadlock regression guard survives:

  get_setup_history_for_car_track no longer deadlocks when corner_issue_ids
  are present (regression guard against nested lock acquisition).
"""
from __future__ import annotations

import json
import sys
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, call, patch

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

_SEED_LOC = "suzuka_circuit"
_SEED_LAY = "suzuka_circuit__full_course"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _open_mem_db():
    from data.session_db import SessionDB
    return SessionDB(":memory:")


# ---------------------------------------------------------------------------
# Deadlock regression guard
# ---------------------------------------------------------------------------

class TestGetSetupHistoryNoDeadlock(unittest.TestCase):

    def _insert_corner_issue(self, db, session_id: int, car_id: int = 1,
                             track: str = "Monza") -> int:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with db._lock:
            cur = db._conn.execute(
                """INSERT INTO corner_issues
                   (car_id, track, corner_id, issue_type, phase,
                    lap_count, total_laps, severity, confidence,
                    evidence, session_id, detected_at)
                   VALUES (?,?,'T1','oversteer','exit',3,10,0.75,0.9,'',?,?)""",
                (car_id, track, session_id, now),
            )
            db._conn.commit()
            return cur.lastrowid

    def _insert_rec(self, db, session_id: int, car_id: int = 1, track: str = "Monza",
                    corner_issue_ids: str = "[]") -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        before = json.dumps({"best_lap_ms": 90000, "avg_fuel_per_lap": 2.0, "lap_count": 5})
        after = json.dumps({"best_lap_ms": 88000, "avg_fuel_per_lap": 1.9, "lap_count": 6})
        with db._lock:
            db._conn.execute(
                """INSERT INTO setup_recommendations
                   (ai_interaction_id, session_id, car_id, track, layout_id,
                    feature, recommendation_text, status, outcome,
                    before_metrics, after_metrics, corner_issue_ids, created_at)
                   VALUES (NULL,?,?,?,'','setup','Stiffen rear.','applied','improved',?,?,?,?)""",
                (session_id, car_id, track, before, after, corner_issue_ids, now),
            )
            db._conn.commit()

    def test_no_deadlock_with_corner_issue_ids(self):
        """get_setup_history_for_car_track must complete without deadlocking
        when a recommendation has populated corner_issue_ids."""
        db = _open_mem_db()
        sid = db.open_session(1, "Monza", "Race", car_name="TestCar")
        issue_id = self._insert_corner_issue(db, sid)
        self._insert_rec(db, sid, corner_issue_ids=json.dumps([issue_id]))

        # Run in a thread with a timeout to catch deadlocks
        result_holder = []
        exc_holder = []

        def _run():
            try:
                result_holder.append(db.get_setup_history_for_car_track(1, "Monza"))
            except Exception as e:
                exc_holder.append(e)

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout=5.0)

        self.assertFalse(t.is_alive(), "get_setup_history_for_car_track deadlocked")
        self.assertEqual(exc_holder, [], f"Unexpected exception: {exc_holder}")
        self.assertTrue(result_holder, "Expected a non-empty result list")
        self.assertIn("oversteer", result_holder[0])
        self.assertIn("T1", result_holder[0])

    def test_no_deadlock_with_empty_corner_issue_ids(self):
        """No deadlock when corner_issue_ids is empty (regression guard)."""
        db = _open_mem_db()
        sid = db.open_session(1, "Monza", "Race", car_name="TestCar")
        self._insert_rec(db, sid, corner_issue_ids="[]")

        result_holder = []

        def _run():
            result_holder.append(db.get_setup_history_for_car_track(1, "Monza"))

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout=5.0)

        self.assertFalse(t.is_alive(), "Deadlock even without corner_issue_ids")
        self.assertTrue(result_holder)

    def test_multiple_recommendations_with_corner_issues(self):
        """Bulk corner_issue lookup works across multiple recommendations."""
        db = _open_mem_db()
        sid = db.open_session(1, "Monza", "Race", car_name="TestCar")
        issue_id1 = self._insert_corner_issue(db, sid)
        issue_id2 = self._insert_corner_issue(db, sid)
        self._insert_rec(db, sid, corner_issue_ids=json.dumps([issue_id1]))
        self._insert_rec(db, sid, corner_issue_ids=json.dumps([issue_id2]))

        result = db.get_setup_history_for_car_track(1, "Monza")

        self.assertIn("Target issues", result)
        self.assertEqual(result.count("Target issues"), 2)


if __name__ == "__main__":
    unittest.main()
