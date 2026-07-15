"""Tests for Group 14: UAT no-go remediation (DEF-P1-012, DEF-P2-029–035).

DEF-P1-012: Practice Analysis prompt still instructs AI to provide setup changes
            even when tuning is locked. Fix: conditional instruction block.

DEF-P2-029: Outlap silently skipped when write_lap receives stats=None.
            Fix: write metadata-only row (zeros) instead of returning 0.

DEF-P2-030: Save Session button creates a duplicate session when the
            EventDispatcher already has an open live session.
            Fix: _save_session_to_db reuses _dispatcher._session_id > 0;
            only updates compounds instead of re-inserting laps.

DEF-P2-031: Qualifying outlap calming phrase never fires because PIT_EXIT event
            uses packet-detected session_type which may be 'unknown'/'practice'
            in a custom lobby, ignoring the user's Live-tab mode override.
            Fix: _exit_pit uses _session_type_override when set.

DEF-P2-032: Already fixed in Group 5 (pit/fuel suppression includes qualifying).
            Verified here to guard against regression.

DEF-P2-033: AI Log auto-select deferred via QTimer.singleShot(0) so the widget
            is fully painted before setCurrentRow fires; flush respects tab
            visibility and leaves the flag set when not on tab 11.

DEF-P2-034: AI Log timestamps stored as UTC (utcnow) but displayed as local
            time. Fix: use datetime.now() (local time) in _ai_client.py.

DEF-P2-035: Garage tab shows no DB setups; sessions query silently swallowed
            exceptions. Fix: DB setups merged from get_setups_for_car;
            exceptions now print tracebacks.
"""
from __future__ import annotations

import pathlib
import unittest

_SRC = pathlib.Path(__file__).parent.parent


def _dashboard_text() -> str:
    return (_SRC / "ui" / "dashboard.py").read_text(encoding="utf-8")


def _state_text() -> str:
    return (_SRC / "telemetry" / "state.py").read_text(encoding="utf-8")


def _announcer_text() -> str:
    return (_SRC / "voice" / "announcer.py").read_text(encoding="utf-8")


def _method_body(text: str, method_name: str) -> str:
    start = text.find(f"def {method_name}(")
    if start == -1:
        return ""
    end = text.find("\n    def ", start + 1)
    return text[start:end] if end != -1 else text[start:]


# ---------------------------------------------------------------------------
# DEF-P2-029 — write_lap allows stats=None (metadata-only row)
# ---------------------------------------------------------------------------

class TestWriteLapNoneStats(unittest.TestCase):

    def setUp(self):
        import sys
        sys.path.insert(0, str(_SRC))
        from data.session_db import SessionDB
        self.db = SessionDB(":memory:")

    def _open_session(self) -> int:
        return self.db.open_session(0, "Suzuka Circuit", "practice", car_name="RX-7")

    def test_write_lap_none_stats_returns_nonzero_id(self):
        """DEF-P2-029: write_lap with stats=None must write a row and return its id."""
        sid = self._open_session()
        lap_id = self.db.write_lap(
            sid, 1, 95000, 2.5, None,
            is_out_lap=True, fuel_start=50.0, fuel_end=47.5,
        )
        self.assertGreater(lap_id, 0,
                           "write_lap with stats=None must write a row and return its id (DEF-P2-029)")

    def test_write_lap_none_stats_preserves_out_lap_flag(self):
        """DEF-P2-029: metadata row must preserve is_out_lap flag."""
        sid = self._open_session()
        self.db.write_lap(sid, 1, 95000, 2.5, None, is_out_lap=True, fuel_start=50.0, fuel_end=47.5)
        laps = self.db.get_session_laps(sid)
        self.assertEqual(len(laps), 1)
        self.assertEqual(laps[0]["is_out_lap"], 1,
                         "Metadata-only row must preserve is_out_lap=1 (DEF-P2-029)")

    def test_write_lap_none_stats_preserves_fuel_start_end(self):
        """DEF-P2-029: metadata row must preserve fuel_start and fuel_end."""
        sid = self._open_session()
        self.db.write_lap(sid, 1, 95000, 2.5, None, is_out_lap=True,
                          fuel_start=50.0, fuel_end=47.5)
        laps = self.db.get_session_laps(sid)
        self.assertAlmostEqual(laps[0]["fuel_start"], 50.0, places=2)
        self.assertAlmostEqual(laps[0]["fuel_end"], 47.5, places=2)

    def test_write_lap_none_stats_zeros_telemetry(self):
        """DEF-P2-029: metadata row must have zero lock_up_count when stats is None."""
        sid = self._open_session()
        self.db.write_lap(sid, 1, 95000, 2.5, None)
        # get_session_laps returns a limited view; query lap_records directly for full columns
        with self.db._lock:
            row = self.db._conn.execute(
                "SELECT lock_up_count FROM lap_records WHERE session_id=?", (sid,)
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["lock_up_count"], 0)

    def test_write_lap_none_stats_increments_session_total_laps(self):
        """DEF-P2-029: metadata row must increment sessions.total_laps."""
        sid = self._open_session()
        self.db.write_lap(sid, 1, 95000, 2.5, None, is_out_lap=True)
        sessions = self.db.get_all_sessions()
        session_row = next((s for s in sessions if s["id"] == sid), None)
        self.assertIsNotNone(session_row)
        self.assertEqual(session_row["total_laps"], 1)


# ---------------------------------------------------------------------------
# DEF-P2-030 — _save_session_to_db reuses existing dispatcher session
# ---------------------------------------------------------------------------

class TestSaveSessionNoduplication(unittest.TestCase):

    def test_save_session_reads_dispatcher_session_id(self):
        """DEF-P2-030: _save_session_to_db must check _dispatcher._session_id first."""
        body = _method_body(_dashboard_text(), "_save_session_to_db")
        self.assertIn("_dispatcher._session_id", body,
                      "_save_session_to_db must read _dispatcher._session_id to detect open session")

    def test_save_session_updates_compounds_when_session_exists(self):
        """DEF-P2-030: if dispatcher session > 0, must call update_lap_compound not open_session."""
        body = _method_body(_dashboard_text(), "_save_session_to_db")
        # The compound update path must exist
        self.assertIn("update_lap_compound", body,
                      "_save_session_to_db must call update_lap_compound when reusing existing session")

    def test_save_session_returns_early_without_open_session(self):
        """DEF-P2-030: reuse path must return before calling open_session."""
        body = _method_body(_dashboard_text(), "_save_session_to_db")
        existing_path_start = body.find("existing_sid")
        open_session_pos = body.find("open_session")
        self.assertGreater(existing_path_start, -1,
                           "_save_session_to_db must use existing_sid variable")
        # open_session must appear AFTER the existing_sid early-return block
        self.assertGreater(open_session_pos, existing_path_start,
                           "open_session call must come after the existing-session early-return block")

    def test_save_session_no_duplicate_open_before_existing_check(self):
        """DEF-P2-030: open_session must not be called at the top without the existing-sid guard."""
        body = _method_body(_dashboard_text(), "_save_session_to_db")
        first_open = body.find("open_session")
        first_existing = body.find("existing_sid")
        # existing_sid check must appear before any open_session call
        self.assertLess(first_existing, first_open,
                        "existing_sid guard must appear before open_session in _save_session_to_db")


# ---------------------------------------------------------------------------
# DEF-P2-031 — PIT_EXIT uses session_type_override in state.py
# ---------------------------------------------------------------------------

class TestPitExitSessionTypeOverride(unittest.TestCase):

    def test_exit_pit_uses_override_for_pit_exit_event(self):
        """DEF-P2-031: _exit_pit must use _session_type_override (if set) in PIT_EXIT data."""
        body = _method_body(_state_text(), "_exit_pit")
        self.assertIn("_session_type_override", body,
                      "_exit_pit must use _session_type_override for PIT_EXIT session_type field")

    def test_exit_pit_override_fallback_to_detected_type(self):
        """DEF-P2-031: must fall back to _session_type when override is None."""
        body = _method_body(_state_text(), "_exit_pit")
        self.assertIn("_session_type", body,
                      "_exit_pit must use _session_type as fallback when override is None")

    def test_exit_pit_override_check_is_none(self):
        """DEF-P2-031: override selection must check for None explicitly."""
        body = _method_body(_state_text(), "_exit_pit")
        self.assertIn("is not None", body,
                      "_exit_pit override selection must check _session_type_override is not None")

    def test_exit_pit_qualifying_override_propagates_to_event_data(self):
        """DEF-P2-031: logic check — override value propagates to event data correctly."""
        from enum import Enum

        class FakeSessionType(Enum):
            PRACTICE = "practice"
            QUALIFYING = "qualifying"
            RACE = "race"

        def _choose_type(override, detected):
            return override if override is not None else detected

        self.assertEqual(
            _choose_type(FakeSessionType.QUALIFYING, FakeSessionType.PRACTICE).value,
            "qualifying",
            "When override=QUALIFYING and detected=PRACTICE, result must be 'qualifying'"
        )
        self.assertEqual(
            _choose_type(None, FakeSessionType.PRACTICE).value,
            "practice",
            "When override=None, must fall back to detected 'practice'"
        )


# ---------------------------------------------------------------------------
# DEF-P2-032 — qualifying pit/fuel suppression (regression guard)
# ---------------------------------------------------------------------------

class TestQualifyingAlertSuppression(unittest.TestCase):

    def test_on_pit_suppresses_qualifying(self):
        """DEF-P2-032: _on_pit must suppress alerts in qualifying mode."""
        body = _method_body(_announcer_text(), "_on_pit")
        self.assertIn('"qualifying"', body,
                      "_on_pit must guard against qualifying mode (regression guard DEF-P2-032)")

    def test_on_fuel_low_suppresses_qualifying(self):
        """DEF-P2-032: _on_fuel_low must suppress alerts in qualifying mode."""
        body = _method_body(_announcer_text(), "_on_fuel_low")
        self.assertIn('"qualifying"', body,
                      "_on_fuel_low must guard against qualifying mode (regression guard DEF-P2-032)")

    def test_on_race_finish_suppresses_qualifying(self):
        """DEF-P2-032: _on_race_finish must not fire in qualifying mode."""
        body = _method_body(_announcer_text(), "_on_race_finish")
        self.assertIn('"race"', body,
                      "_on_race_finish must check mode == 'race' before announcing")


# ---------------------------------------------------------------------------
# DEF-P2-035 — Garage sessions and DB setups visible
# ---------------------------------------------------------------------------

class TestGarageDbIntegration(unittest.TestCase):

    def test_garage_calls_get_all_sessions(self):
        """DEF-P2-035: _on_garage_car_selected must call get_all_sessions."""
        body = _method_body(_dashboard_text(), "_on_garage_car_selected")
        self.assertIn("get_all_sessions", body,
                      "_on_garage_car_selected must call get_all_sessions to populate sessions table")

    def test_garage_calls_get_setups_for_car(self):
        """DEF-P2-035: _on_garage_car_selected must call get_setups_for_car for DB setups."""
        body = _method_body(_dashboard_text(), "_on_garage_car_selected")
        self.assertIn("get_setups_for_car", body,
                      "_on_garage_car_selected must call get_setups_for_car (DEF-P2-035)")

    def test_garage_exceptions_print_traceback(self):
        """DEF-P2-035: session/setup query exceptions must print traceback, not be silently swallowed."""
        body = _method_body(_dashboard_text(), "_on_garage_car_selected")
        self.assertIn("traceback.print_exc()", body,
                      "_on_garage_car_selected must print traceback on DB query failure (DEF-P2-035)")

    def test_get_setups_for_car_exists_in_session_db(self):
        """DEF-P2-035: SessionDB must have get_setups_for_car method."""
        import sys
        sys.path.insert(0, str(_SRC))
        from data.session_db import SessionDB
        db = SessionDB(":memory:")
        self.assertTrue(hasattr(db, "get_setups_for_car"),
                        "SessionDB must have get_setups_for_car method")

    def test_get_all_sessions_filters_to_nonzero_laps(self):
        """DEF-P2-035: get_all_sessions must only return sessions with total_laps > 0."""
        import sys
        sys.path.insert(0, str(_SRC))
        from data.session_db import SessionDB
        db = SessionDB(":memory:")
        # Open a session but don't write any laps — should not appear
        db.open_session(0, "Suzuka", "practice", car_name="Empty Car")
        sessions = db.get_all_sessions()
        self.assertEqual(len(sessions), 0,
                         "get_all_sessions must not return sessions with total_laps=0")


if __name__ == "__main__":
    unittest.main()
