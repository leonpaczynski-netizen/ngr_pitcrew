"""Group 22A — set_recommendation_corner_issues.

Tests:
  1. set_recommendation_corner_issues writes a JSON list correctly.
  2. Empty list writes '[]' not NULL.
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


def _insert_session(db: SessionDB) -> int:
    return db.open_session(1, "Silverstone", "Race", car_name="TestCar")


def _insert_rec(db: SessionDB, session_id: int) -> int:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with db._lock:
        cur = db._conn.execute(
            """INSERT INTO setup_recommendations
               (ai_interaction_id, session_id, car_id, track, layout_id,
                feature, recommendation_text, status, outcome,
                before_metrics, after_metrics, corner_issue_ids, created_at)
               VALUES (NULL,?,1,'Silverstone','','setup','Test rec.','proposed',
                       'not_verified','{}','{}','[]',?)""",
            (session_id, now),
        )
        db._conn.commit()
        return cur.lastrowid


class TestSetRecommendationCornerIssues(unittest.TestCase):

    def test_writes_json_list(self):
        """set_recommendation_corner_issues persists the provided ID list."""
        db = _make_db()
        sid = _insert_session(db)
        rec_id = _insert_rec(db, sid)

        db.set_recommendation_corner_issues(rec_id, [10, 20, 30])

        with db._lock:
            row = db._conn.execute(
                "SELECT corner_issue_ids FROM setup_recommendations WHERE id = ?",
                (rec_id,),
            ).fetchone()
        stored = json.loads(row[0])
        self.assertEqual(stored, [10, 20, 30])

    def test_empty_list_writes_json_empty_array(self):
        """Empty list stores '[]', not NULL."""
        db = _make_db()
        sid = _insert_session(db)
        rec_id = _insert_rec(db, sid)

        db.set_recommendation_corner_issues(rec_id, [])

        with db._lock:
            row = db._conn.execute(
                "SELECT corner_issue_ids FROM setup_recommendations WHERE id = ?",
                (rec_id,),
            ).fetchone()
        self.assertIsNotNone(row[0])
        stored = json.loads(row[0])
        self.assertEqual(stored, [])


if __name__ == "__main__":
    unittest.main()
