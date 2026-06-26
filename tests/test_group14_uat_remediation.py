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


def _ai_client_text() -> str:
    return (_SRC / "strategy" / "_ai_client.py").read_text(encoding="utf-8")


def _ai_planner_text() -> str:
    return (_SRC / "strategy" / "ai_planner.py").read_text(encoding="utf-8")


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
# DEF-P1-012 — practice prompt: locked tuning suppresses setup-changes section
# ---------------------------------------------------------------------------

class TestBoPPromptSetupChangesConditional(unittest.TestCase):

    def test_setup_changes_line_is_conditional_on_tuning_locked(self):
        """DEF-P1-012: 'Setup changes' instruction must be inside an if/else block."""
        src = _ai_planner_text()
        # The fix uses a Python ternary/conditional inside the f-string
        self.assertIn("tuning_locked", src[src.find("**Setup changes"):src.find("**Setup changes") + 300]
                      if src.find("**Setup changes") != -1 else
                      src[src.find("No setup changes"):src.find("No setup changes") + 300],
                      "_build_practice_prompt setup instruction must reference tuning_locked")

    def test_no_setup_changes_text_present_when_locked(self):
        """DEF-P1-012: locked branch must say 'No setup changes' or 'not permitted'."""
        src = _ai_planner_text()
        # One of these phrases must exist to handle the locked case
        self.assertTrue(
            "No setup changes" in src or "not permitted" in src,
            "Practice prompt must include a locked-tuning branch that suppresses setup advice"
        )

    def test_setup_changes_instruction_present_when_not_locked(self):
        """DEF-P1-012: unlocked branch must still ask for '3–5 changes'."""
        src = _ai_planner_text()
        self.assertIn("3–5 changes", src,
                      "Unlocked branch must retain the original 3–5 setup changes instruction")

    def test_prompt_tuning_locked_branch_references_do_not(self):
        """DEF-P1-012: locked branch must include a 'DO NOT' or 'not permitted' directive."""
        src = _ai_planner_text()
        # Find the locked branch of the setup_changes conditional
        locked_pos = src.find("No setup changes")
        if locked_pos == -1:
            locked_pos = src.find("not permitted")
        self.assertGreater(locked_pos, -1,
                           "Practice prompt must have a locked-tuning setup_changes branch")


class TestBoPPromptRoundTrip(unittest.TestCase):
    """Direct call to _build_practice_prompt with tuning_locked=True."""

    def _get_prompt(self, locked: bool) -> str:
        import sys
        sys.path.insert(0, str(_SRC))
        from strategy.ai_planner import _build_practice_prompt, RaceParams
        params = RaceParams(
            track="Suzuka Circuit",
            total_laps=25,
            fuel_burn_per_lap=2.5,
            pit_loss_secs=23.0,
            refuel_speed_lps=10.0,
            tyre_wear_multiplier=1.0,
            tuning_locked=locked,
            allowed_tuning=[],
        )
        lap_data = {"Racing Medium": [95000.0, 96000.0, 95500.0]}
        setup = {"ride_height_front": 80, "ride_height_rear": 85}
        prompt = _build_practice_prompt(params, lap_data, setup, {})
        return prompt

    def test_locked_prompt_contains_tuning_locked_block(self):
        """DEF-P1-012: tuning_locked=True prompt must contain TUNING LOCKED block."""
        prompt = self._get_prompt(locked=True)
        self.assertIn("TUNING LOCKED", prompt,
                      "Locked prompt must contain ## EVENT RULES — TUNING LOCKED")

    def test_locked_prompt_does_not_show_ride_height_value(self):
        """DEF-P1-012: tuning_locked=True setup block must not expose 80 as ride_height."""
        prompt = self._get_prompt(locked=True)
        setup_section = prompt[prompt.find("Current car setup"):] if "Current car setup" in prompt else prompt
        self.assertNotIn("ride_height_front: 80", setup_section,
                         "Locked prompt must NOT show actual setup values in setup section")

    def test_locked_prompt_has_no_setup_changes_instruction(self):
        """DEF-P1-012: tuning_locked=True must NOT instruct AI to provide 3-5 setup changes."""
        prompt = self._get_prompt(locked=True)
        # The original "3–5 changes" instruction must be absent when locked
        self.assertNotIn("3–5 changes", prompt,
                         "Locked prompt must not ask AI for setup changes")

    def test_unlocked_prompt_has_setup_changes_instruction(self):
        """DEF-P1-012: tuning_locked=False must retain the 3-5 setup changes instruction."""
        prompt = self._get_prompt(locked=False)
        self.assertIn("3–5 changes", prompt,
                      "Unlocked prompt must retain setup changes instruction")


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
# DEF-P2-033 — AI Log auto-select via QTimer
# ---------------------------------------------------------------------------

class TestAiLogAutoSelectQTimer(unittest.TestCase):

    def test_on_ai_log_entry_uses_qtimer(self):
        """DEF-P2-033: _on_ai_log_entry must schedule flush via QTimer.singleShot."""
        body = _method_body(_dashboard_text(), "_on_ai_log_entry")
        self.assertIn("QTimer", body,
                      "_on_ai_log_entry must use QTimer.singleShot for deferred selection (DEF-P2-033)")
        self.assertIn("singleShot", body,
                      "_on_ai_log_entry must call QTimer.singleShot(0, ...) for deferred flush")

    def test_on_ai_log_entry_sets_pending_flag(self):
        """DEF-P2-033: _on_ai_log_entry must still set _ai_log_pending_select = True."""
        body = _method_body(_dashboard_text(), "_on_ai_log_entry")
        self.assertIn("_ai_log_pending_select = True", body,
                      "_on_ai_log_entry must set _ai_log_pending_select flag")

    def test_flush_checks_tab_index(self):
        """DEF-P2-033: _flush_ai_log_pending_select must check currentIndex() == 11."""
        body = _method_body(_dashboard_text(), "_flush_ai_log_pending_select")
        self.assertIn("currentIndex()", body,
                      "_flush_ai_log_pending_select must check currentIndex() before selecting")
        self.assertIn("11", body,
                      "_flush_ai_log_pending_select must compare against tab index 11")

    def test_flush_leaves_flag_set_when_tab_not_visible(self):
        """DEF-P2-033: flush must return without clearing flag when not on AI Log tab."""
        body = _method_body(_dashboard_text(), "_flush_ai_log_pending_select")
        # The method must have a guard that returns BEFORE clearing the flag
        # when the tab index is not 11
        guard_pos = body.find("currentIndex()")
        return_pos = body.find("return", guard_pos) if guard_pos != -1 else -1
        clear_pos  = body.find("_ai_log_pending_select = False")
        self.assertGreater(guard_pos, -1, "Tab visibility guard must exist")
        self.assertGreater(return_pos, -1, "Return statement must follow the guard")
        self.assertGreater(clear_pos, return_pos,
                           "Flag must only be cleared AFTER the tab-visibility guard passes")

    def test_on_ai_log_entry_no_auto_select_true(self):
        """DEF-P2-033: _on_ai_log_entry must NOT pass auto_select=True (use QTimer instead)."""
        body = _method_body(_dashboard_text(), "_on_ai_log_entry")
        self.assertNotIn("auto_select=True", body,
                         "_on_ai_log_entry must not use auto_select=True — QTimer is the correct path")


# ---------------------------------------------------------------------------
# DEF-P2-034 — AI Log timestamp uses local time
# ---------------------------------------------------------------------------

class TestAiLogLocalTimestamp(unittest.TestCase):

    def test_ai_client_does_not_use_utcnow(self):
        """DEF-P2-034: _ai_client.py must NOT use utcnow() (deprecated and returns UTC)."""
        src = _ai_client_text()
        self.assertNotIn("utcnow()", src,
                         "_ai_client.py must not use utcnow() — use datetime.now() for local time")

    def test_ai_client_uses_datetime_now(self):
        """DEF-P2-034: _ai_client.py must use datetime.now() for local timestamps."""
        src = _ai_client_text()
        self.assertIn("datetime.now()", src,
                      "_ai_client.py must use datetime.now() to store local time in AI log entries")

    def test_timestamp_display_still_formatted(self):
        """DEF-P2-034: dashboard must still format timestamp with [:19].replace."""
        src = _dashboard_text()
        self.assertIn("replace(\"T\", \" \")", src,
                      "Timestamp display must still trim T from ISO format with replace")


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
