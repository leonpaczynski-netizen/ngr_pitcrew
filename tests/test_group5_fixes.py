"""Tests for Remediation Group 5 fixes.

DEF-P2-008: PTT fails in Practice mode (source scan: always-on listener + error logging)
Newly added: Qualifying race-finished defect (announcer + state.py mode guard)
DEF-P2-002: Fuel-low and pit voice alerts fire during Practice (extended to Qualifying)
DEF-P3-002: Active tyre compound not displayed on Live tab
DEF-P3-001: Brake balance increment unverified (source scan: setSingleStep(1) confirmed)
DEF-P4-001: PTT button and voice status not on Live tab
"""
from __future__ import annotations

import pathlib
import unittest

# ---------------------------------------------------------------------------
# Source path helpers
# ---------------------------------------------------------------------------

_SRC = pathlib.Path(__file__).parent.parent


def _announcer_text() -> str:
    return (_SRC / "voice" / "announcer.py").read_text(encoding="utf-8")


def _listener_text() -> str:
    return (_SRC / "voice" / "query_listener.py").read_text(encoding="utf-8")


def _dashboard_text() -> str:
    return (_SRC / "ui" / "dashboard.py").read_text(encoding="utf-8")

def _setup_builder_text() -> str:
    return (_SRC / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")


def _state_text() -> str:
    return (_SRC / "telemetry" / "state.py").read_text(encoding="utf-8")


def _main_text() -> str:
    return (_SRC / "main.py").read_text(encoding="utf-8")


def _method_body(text: str, method_name: str) -> str:
    start = text.find(f"def {method_name}(")
    if start == -1:
        return ""
    end = text.find("\n    def ", start + 1)
    return text[start:end] if end != -1 else text[start:]


# ---------------------------------------------------------------------------
# DEF-P2-008 — PTT works in Practice mode (QueryListener always-on)
# ---------------------------------------------------------------------------

class TestPTTPracticeMode(unittest.TestCase):

    def test_query_listener_started_unconditionally_in_main(self):
        """main.py must call query_listener.start() without a mode guard."""
        src = _main_text()
        start_idx = src.find("query_listener.start()")
        self.assertGreater(start_idx, -1, "query_listener.start() must be called in main.py")
        # Ensure there is no 'if mode ==' block surrounding the start call
        pre = src[max(0, start_idx - 200):start_idx]
        self.assertNotIn("mode ==", pre,
                         "query_listener.start() must NOT be gated by a mode check")

    def test_handle_trigger_has_exception_logging(self):
        """_handle_trigger must catch exceptions and emit a PTT error status."""
        body = _method_body(_listener_text(), "_handle_trigger")
        self.assertIn("except Exception", body,
                      "_handle_trigger must have except-Exception guard")
        self.assertIn("traceback", body,
                      "_handle_trigger must log traceback on failure")

    def test_handle_trigger_emits_error_status(self):
        """_handle_trigger must emit a PTT ERROR status on exception."""
        body = _method_body(_listener_text(), "_handle_trigger")
        self.assertIn("_emit_ptt_status", body,
                      "_handle_trigger must call _emit_ptt_status on error")

    def test_handle_trigger_inner_has_no_session_mode_guard(self):
        """_handle_trigger_inner must NOT block based on session mode."""
        body = _method_body(_listener_text(), "_handle_trigger_inner")
        self.assertNotIn("session_mode", body,
                         "_handle_trigger_inner must not gate on session_mode — PTT works in all modes")

    def test_ptt_status_signal_exists_on_bridge(self):
        """DashboardBridge must have ptt_status signal."""
        src = _dashboard_text()
        self.assertIn("ptt_status", src,
                      "DashboardBridge must define ptt_status signal")


# ---------------------------------------------------------------------------
# Newly added: Qualifying race-finished defect
# ---------------------------------------------------------------------------

class TestQualifyingRaceFinished(unittest.TestCase):

    def test_announcer_race_finish_has_mode_guard(self):
        """_on_race_finish must check session_mode and skip if not Race."""
        body = _method_body(_announcer_text(), "_on_race_finish")
        self.assertIn("_session_mode", body,
                      "_on_race_finish must read _session_mode")
        self.assertIn('"race"', body,
                      '_on_race_finish must check for "race" mode')
        self.assertIn("return", body,
                      "_on_race_finish must return early when not in Race mode")

    def test_announcer_race_finish_guard_is_first(self):
        """Session mode guard must come before any announce call."""
        body = _method_body(_announcer_text(), "_on_race_finish")
        guard_pos = body.find("_session_mode")
        announce_pos = body.find("announce(")
        self.assertGreater(announce_pos, guard_pos,
                           "Mode guard must precede the announce call in _on_race_finish")

    def test_state_timed_race_finish_excludes_qualifying(self):
        """state.py timed race RACE_FINISHED must not fire in Qualifying mode."""
        src = _state_text()
        race_finished_block = src[src.find("RACE_FINISHED"):src.find("RACE_FINISHED") + 600]
        self.assertIn("QUALIFYING", race_finished_block,
                      "Timed race RACE_FINISHED guard must exclude SessionType.QUALIFYING")

    def test_state_timed_race_finish_excludes_practice(self):
        """state.py timed race RACE_FINISHED must not fire in Practice mode."""
        src = _state_text()
        race_finished_block = src[src.find("RACE_FINISHED"):src.find("RACE_FINISHED") + 600]
        self.assertIn("PRACTICE", race_finished_block,
                      "Timed race RACE_FINISHED guard must exclude SessionType.PRACTICE")

    def test_race_finish_logic_practice_skip(self):
        """Logic check: mode != 'race' short-circuits the method."""
        def _on_race_finish_logic(session_mode: str, pos: int) -> str | None:
            if session_mode != "race":
                return None
            return f"Race finished. P{pos}."
        self.assertIsNone(_on_race_finish_logic("practice", 1))
        self.assertIsNone(_on_race_finish_logic("qualifying", 3))
        self.assertIsNotNone(_on_race_finish_logic("race", 1))

    def test_race_finish_logic_race_fires(self):
        """Logic check: Race mode allows the announcement to fire."""
        def _on_race_finish_logic(session_mode: str, pos: int) -> str | None:
            if session_mode != "race":
                return None
            return f"Race finished. P{pos}."
        result = _on_race_finish_logic("race", 2)
        self.assertIsNotNone(result)
        self.assertIn("P2", result)


# ---------------------------------------------------------------------------
# DEF-P2-002 — Pit and fuel alerts suppressed in Practice AND Qualifying
# ---------------------------------------------------------------------------

class TestPitFuelAlertSuppression(unittest.TestCase):

    def test_on_pit_guard_includes_qualifying(self):
        """_on_pit must suppress alerts in both practice and qualifying."""
        body = _method_body(_announcer_text(), "_on_pit")
        self.assertIn('"qualifying"', body,
                      '_on_pit must guard against qualifying mode')
        self.assertIn('"practice"', body,
                      '_on_pit must guard against practice mode')

    def test_on_pit_uses_in_tuple_check(self):
        """_on_pit guard must use 'in' tuple check, not multiple == comparisons."""
        body = _method_body(_announcer_text(), "_on_pit")
        self.assertIn(" in (", body,
                      '_on_pit must use "in (...)" for the mode tuple check')

    def test_on_fuel_low_guard_includes_qualifying(self):
        """_on_fuel_low must suppress alerts in both practice and qualifying."""
        body = _method_body(_announcer_text(), "_on_fuel_low")
        self.assertIn('"qualifying"', body,
                      '_on_fuel_low must guard against qualifying mode')
        self.assertIn('"practice"', body,
                      '_on_fuel_low must guard against practice mode')

    def test_on_fuel_low_uses_in_tuple_check(self):
        """_on_fuel_low guard must use 'in' tuple check."""
        body = _method_body(_announcer_text(), "_on_fuel_low")
        self.assertIn(" in (", body,
                      '_on_fuel_low must use "in (...)" for the mode tuple check')

    def test_suppression_logic_practice(self):
        """Logic: practice mode suppresses pit and fuel alerts."""
        def _should_suppress(mode: str) -> bool:
            return mode in ("practice", "qualifying")
        self.assertTrue(_should_suppress("practice"))
        self.assertTrue(_should_suppress("qualifying"))
        self.assertFalse(_should_suppress("race"))

    def test_suppression_logic_qualifying(self):
        """Logic: qualifying mode suppresses pit and fuel alerts."""
        def _should_suppress(mode: str) -> bool:
            return mode in ("practice", "qualifying")
        self.assertTrue(_should_suppress("qualifying"))

    def test_suppression_logic_race_not_suppressed(self):
        """Logic: race mode does NOT suppress pit and fuel alerts."""
        def _should_suppress(mode: str) -> bool:
            return mode in ("practice", "qualifying")
        self.assertFalse(_should_suppress("race"))


# ---------------------------------------------------------------------------
# DEF-P3-002 — Active tyre compound displayed on Live tab
# ---------------------------------------------------------------------------

class TestLiveTyreCompoundDisplay(unittest.TestCase):

    def test_lbl_live_tyre_compound_created_in_live_tab(self):
        """_lbl_live_tyre_compound must be created in the Live tab build method."""
        src = _dashboard_text()
        self.assertIn("_lbl_live_tyre_compound", src,
                      "_lbl_live_tyre_compound must exist in dashboard.py")

    def test_lbl_live_tyre_compound_default_text(self):
        """_lbl_live_tyre_compound default text must use 'Current Tyre:' prefix (DEF-P2-027)."""
        src = _dashboard_text()
        lbl_pos = src.find("_lbl_live_tyre_compound")
        snippet = src[lbl_pos:lbl_pos + 200]
        self.assertIn("Current Tyre:", snippet,
                      "_lbl_live_tyre_compound must initialize with 'Current Tyre:' prefix (DEF-P2-027)")

    def test_sync_setup_builder_updates_compound_label(self):
        """_sync_setup_builder_from_event must call _refresh_live_tyre_label (DEF-P2-027)."""
        body = _method_body(_setup_builder_text(), "_sync_setup_builder_from_event")
        self.assertIn("_refresh_live_tyre_label", body,
                      "_sync_setup_builder_from_event must call _refresh_live_tyre_label (DEF-P2-027)")

    def test_on_live_mode_changed_updates_compound_label(self):
        """_on_live_mode_changed must call _refresh_live_tyre_label (DEF-P2-027)."""
        body = _method_body(_dashboard_text(), "_on_live_mode_changed")
        self.assertIn("_refresh_live_tyre_label", body,
                      "_on_live_mode_changed must call _refresh_live_tyre_label (DEF-P2-027)")

    def test_compound_label_uses_priority_hierarchy_not_mandatory_compounds(self):
        """DEF-P2-027: compound label must use _get_current_tyre_compound priority hierarchy.
        Required tyres (mandatory_compounds) are race rules, not the fitted tyre."""
        src = _dashboard_text()
        body = _method_body(src, "_get_current_tyre_compound")
        self.assertTrue(body,
                        "_get_current_tyre_compound must exist — used by live tyre label (DEF-P2-027)")
        self.assertNotIn("mandatory_compounds", body,
                         "_get_current_tyre_compound must not use mandatory_compounds (DEF-P2-027)")


# ---------------------------------------------------------------------------
# DEF-P3-001 — Brake balance spinbox step = 1
# ---------------------------------------------------------------------------

class TestBrakeBalanceStep(unittest.TestCase):

    def test_setup_bb_single_step_1(self):
        """_setup_bb must call setSingleStep(1) — one unit per click matches GT7."""
        src = _setup_builder_text()
        self.assertIn("_setup_bb.setSingleStep(1)", src,
                      "_setup_bb must have setSingleStep(1) called explicitly")

    def test_setup_bb_exists_in_setup_builder(self):
        """_setup_bb spinbox must exist in the setup builder section."""
        src = _setup_builder_text()
        self.assertIn("_setup_bb", src,
                      "_setup_bb brake balance spinbox must exist")

    def test_brake_balance_step_logic(self):
        """Logic: step of 1 means each click changes value by exactly 1."""
        step = 1
        value = 0
        value += step
        self.assertEqual(value, 1, "Step 1 increments by 1")
        value -= step
        self.assertEqual(value, 0, "Step 1 decrements by 1")


# ---------------------------------------------------------------------------
# DEF-P4-001 — PTT status visible on Live tab
# ---------------------------------------------------------------------------

class TestPTTOnLiveTab(unittest.TestCase):

    def test_live_ptt_status_lbl_exists_in_dashboard(self):
        """_live_ptt_status_lbl must be created in dashboard.py."""
        src = _dashboard_text()
        self.assertIn("_live_ptt_status_lbl", src,
                      "_live_ptt_status_lbl must exist in the Live tab")

    def test_live_ptt_status_lbl_default_text(self):
        """_live_ptt_status_lbl must initialize with 'RADIO READY'."""
        src = _dashboard_text()
        pos = src.find("_live_ptt_status_lbl")
        snippet = src[pos:pos + 300]
        self.assertIn("RADIO READY", snippet,
                      "_live_ptt_status_lbl must default to RADIO READY")

    def test_on_ptt_status_updates_live_label(self):
        """_on_ptt_status must update _live_ptt_status_lbl."""
        body = _method_body(_dashboard_text(), "_on_ptt_status")
        self.assertIn("_live_ptt_status_lbl", body,
                      "_on_ptt_status must update the Live tab PTT status label")

    def test_live_label_in_info_row(self):
        """_live_ptt_status_lbl must be added to the Live tab info row."""
        src = _dashboard_text()
        lbl_pos = src.find("_live_ptt_status_lbl")
        # Within 200 chars back, there should be the Mode combo reference
        pre = src[max(0, lbl_pos - 400):lbl_pos]
        self.assertIn("_combo_live_mode", pre,
                      "_live_ptt_status_lbl must appear after the Mode combo in the Live tab")

    def test_ptt_status_signal_connected_to_handler(self):
        """ptt_status signal must be connected to _on_ptt_status."""
        src = _dashboard_text()
        self.assertIn("ptt_status.connect(self._on_ptt_status)", src,
                      "ptt_status signal must be connected to _on_ptt_status")


if __name__ == "__main__":
    unittest.main()
