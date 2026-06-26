"""Group 22A — car_name forwarding to rev_limit_threshold_pct resolution.

Tests:
  1. get_track_context_for_ai with car_name calls SessionDB to resolve threshold.
  2. The resolved threshold is forwarded to build_resolved_track_context_for_prompt.
  3. Empty car_name skips the SessionDB lookup (no error raised).
  4. SessionDB error during threshold lookup falls back to 0.90 default.
  5. analyse_strategy forwards car_name to get_track_context_for_ai.
  6. analyse_practice_session forwards car_name to get_track_context_for_ai.
  7. build_car_setup forwards the car string to get_track_context_for_ai.
  8. get_setup_history_for_car_track no longer deadlocks when corner_issue_ids
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
# Class 1 — get_track_context_for_ai car_name → SessionDB → resolver
# ---------------------------------------------------------------------------

class TestGetTrackContextCarNameForwarding(unittest.TestCase):

    def test_car_name_triggers_db_lookup(self):
        """When car_name is provided, SessionDB.get_rev_limit_threshold_for_car is called."""
        from strategy.track_context_prompt import get_track_context_for_ai

        mock_db = MagicMock()
        mock_db.get_rev_limit_threshold_for_car.return_value = 0.88

        with patch("data.session_db.SessionDB", return_value=mock_db), \
             patch("data.track_model_resolver.build_resolved_track_context_for_prompt",
                   return_value="ctx") as mock_resolver:
            result = get_track_context_for_ai(_SEED_LOC, _SEED_LAY, car_name="Porsche 911")

        mock_db.get_rev_limit_threshold_for_car.assert_called_once_with("Porsche 911")
        # Resolver must receive the resolved threshold, not the default
        _, kwargs = mock_resolver.call_args
        self.assertAlmostEqual(kwargs.get("rev_limit_threshold_pct", 0.90), 0.88, places=4)
        # active_car_name must be forwarded so the resolver can use it
        self.assertEqual(kwargs.get("active_car_name"), "Porsche 911")

    def test_empty_car_name_skips_db_lookup(self):
        """Empty car_name must not instantiate SessionDB at all."""
        from strategy.track_context_prompt import get_track_context_for_ai

        with patch("data.session_db.SessionDB") as mock_cls, \
             patch("data.track_model_resolver.build_resolved_track_context_for_prompt",
                   return_value="ctx"):
            get_track_context_for_ai(_SEED_LOC, _SEED_LAY, car_name="")

        mock_cls.assert_not_called()

    def test_db_error_falls_back_to_default(self):
        """SessionDB error during lookup must fall back to 0.90 without raising."""
        from strategy.track_context_prompt import get_track_context_for_ai

        with patch("data.session_db.SessionDB", side_effect=RuntimeError("db down")), \
             patch("data.track_model_resolver.build_resolved_track_context_for_prompt",
                   return_value="ctx") as mock_resolver:
            result = get_track_context_for_ai(_SEED_LOC, _SEED_LAY, car_name="Any Car")

        # Must not raise and must use the default threshold
        self.assertIsInstance(result, str)
        _, kwargs = mock_resolver.call_args
        self.assertAlmostEqual(kwargs.get("rev_limit_threshold_pct", 0.90), 0.90, places=4)

    def test_resolver_receives_threshold_as_kwarg(self):
        """rev_limit_threshold_pct resolved from DB is forwarded to the resolver."""
        from strategy.track_context_prompt import get_track_context_for_ai

        mock_db = MagicMock()
        mock_db.get_rev_limit_threshold_for_car.return_value = 0.92

        captured = {}

        def _fake_resolver(loc, lay, **kwargs):
            captured.update(kwargs)
            return "resolved"

        with patch("data.session_db.SessionDB", return_value=mock_db), \
             patch("data.track_model_resolver.build_resolved_track_context_for_prompt",
                   side_effect=_fake_resolver):
            get_track_context_for_ai(_SEED_LOC, _SEED_LAY, car_name="GT-R")

        self.assertAlmostEqual(captured.get("rev_limit_threshold_pct", 0.90), 0.92, places=4)
        self.assertEqual(captured.get("active_car_name"), "GT-R")

    def test_missing_ids_does_not_call_db(self):
        """When track/layout IDs are absent, SessionDB must not be called."""
        from strategy.track_context_prompt import get_track_context_for_ai

        with patch("data.session_db.SessionDB") as mock_cls:
            get_track_context_for_ai(None, None, car_name="Any Car")

        mock_cls.assert_not_called()


# ---------------------------------------------------------------------------
# Class 2 — ai_planner callers forward car_name
# ---------------------------------------------------------------------------

class TestAiPlannerCarNameForwarding(unittest.TestCase):

    def _minimal_params(self, **kwargs):
        from strategy.ai_planner import RaceParams
        defaults = dict(
            track="Test Track",
            total_laps=10,
            tyre_wear_multiplier=1.0,
            fuel_burn_per_lap=2.0,
            refuel_speed_lps=10.0,
            pit_loss_secs=23.0,
            track_location_id=_SEED_LOC,
            layout_id=_SEED_LAY,
        )
        defaults.update(kwargs)
        return RaceParams(**defaults)

    def test_analyse_strategy_forwards_car_name(self):
        """analyse_strategy passes car_name to get_track_context_for_ai."""
        from strategy.ai_planner import analyse_strategy

        captured = {}

        def _fake_get_tc(loc, lay, car_name=""):
            captured["car_name"] = car_name
            return "ctx"

        with patch("strategy.track_context_prompt.get_track_context_for_ai",
                   side_effect=_fake_get_tc), \
             patch("strategy.ai_planner.call_api", side_effect=RuntimeError("no api")):
            try:
                analyse_strategy(
                    self._minimal_params(),
                    {"RM": [90000.0]},
                    "key",
                    car_name="Ferrari 296",
                )
            except RuntimeError:
                pass

        self.assertEqual(captured.get("car_name"), "Ferrari 296")

    def test_analyse_practice_session_forwards_car_name(self):
        """analyse_practice_session passes car_name to get_track_context_for_ai."""
        from strategy.ai_planner import analyse_practice_session

        captured = {}

        def _fake_get_tc(loc, lay, car_name=""):
            captured["car_name"] = car_name
            return "ctx"

        with patch("strategy.track_context_prompt.get_track_context_for_ai",
                   side_effect=_fake_get_tc), \
             patch("strategy.ai_planner.call_api", side_effect=RuntimeError("no api")):
            try:
                analyse_practice_session(
                    self._minimal_params(),
                    {"RM": [90000.0]},
                    {},
                    {},
                    "key",
                    car_name="Mazda RX-7",
                )
            except RuntimeError:
                pass

        self.assertEqual(captured.get("car_name"), "Mazda RX-7")

    def test_build_car_setup_forwards_car_name(self):
        """build_car_setup passes the car string to get_track_context_for_ai."""
        from strategy.ai_planner import build_car_setup

        captured = {}

        def _fake_get_tc(loc, lay, car_name=""):
            captured["car_name"] = car_name
            return "ctx"

        with patch("strategy.track_context_prompt.get_track_context_for_ai",
                   side_effect=_fake_get_tc), \
             patch("strategy.ai_planner._build_setup_from_scratch_prompt",
                   return_value="prompt"), \
             patch("strategy.ai_planner.call_api",
                   side_effect=RuntimeError("no api")), \
             patch("strategy.ai_planner._parse_setup_recommendation",
                   return_value=MagicMock()):
            try:
                build_car_setup(
                    car="Nissan GT-R Nismo",
                    track="Suzuka",
                    session_type="Race",
                    race_laps=10,
                    min_weight_kg=1200.0,
                    max_power_hp=500.0,
                    api_key="key",
                    track_location_id=_SEED_LOC,
                    layout_id=_SEED_LAY,
                )
            except RuntimeError:
                pass

        self.assertEqual(captured.get("car_name"), "Nissan GT-R Nismo")


# ---------------------------------------------------------------------------
# Class 3 — deadlock regression guard
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
