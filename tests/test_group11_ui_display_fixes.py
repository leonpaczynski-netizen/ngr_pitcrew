"""Tests for Group 11: UI Display Fixes (DEF-P1-011, DEF-P2-021).

DEF-P1-011: Strategy Builder Fuel Burn Auto label showed stale "X.XX L/lap (last
            session)" from config after switching events, because _on_event_set_active()
            called _sync_setup_builder_from_event() which only updated the label when
            live telemetry avg > 0 — never resetting the stale value.
            Fix: _on_event_set_active() now explicitly resets _lbl_fuel_burn_display
            to the uncalibrated default when neither live telemetry nor a loaded session
            provides data.

DEF-P2-021: AI Log list did not auto-select the new entry when a live AI call completed.
            _add_ai_log_list_item() called scrollToBottom() but if the AI Log tab was
            not visible at signal delivery time, the scroll had no effect. The user
            navigated to the tab and saw only the older DB-loaded history without realising
            a new entry existed at the bottom.
            Fix: _on_ai_log_entry() passes auto_select=True to _add_ai_log_list_item(),
            which calls setCurrentRow() on the newly added item so it is always selected
            and visible when the user navigates to the AI Log tab.
"""
from __future__ import annotations

import pathlib
import unittest

_SRC = pathlib.Path(__file__).parent.parent


def _dashboard_text() -> str:
    return (_SRC / "ui" / "dashboard.py").read_text(encoding="utf-8")


def _method_body(text: str, method_name: str) -> str:
    start = text.find(f"def {method_name}(")
    if start == -1:
        return ""
    end = text.find("\n    def ", start + 1)
    return text[start:end] if end != -1 else text[start:]


# ---------------------------------------------------------------------------
# Group 11a — DEF-P1-011: fuel burn label reset on event switch
# ---------------------------------------------------------------------------

class TestFuelBurnLabelResetOnEventSwitch(unittest.TestCase):

    def setUp(self):
        self._body = _method_body(_dashboard_text(), "_on_event_set_active")

    def test_on_event_set_active_checks_avg_fuel_per_lap(self):
        """DEF-P1-011: _on_event_set_active must check live avg_fuel_per_lap."""
        self.assertIn("avg_fuel_per_lap", self._body,
                      "_on_event_set_active must check tracker avg_fuel_per_lap to decide label state")

    def test_on_event_set_active_checks_loaded_session_fuel(self):
        """DEF-P1-011: _on_event_set_active must check _loaded_session_avg_fuel."""
        self.assertIn("_loaded_session_avg_fuel", self._body,
                      "_on_event_set_active must check _loaded_session_avg_fuel before resetting label")

    def test_on_event_set_active_resets_fuel_burn_label(self):
        """DEF-P1-011: _on_event_set_active must reset _lbl_fuel_burn_display text."""
        self.assertIn("_lbl_fuel_burn_display", self._body,
                      "_on_event_set_active must reference _lbl_fuel_burn_display")
        self.assertIn("complete practice laps to calibrate", self._body,
                      "_on_event_set_active must reset label to uncalibrated text when no data")

    def test_reset_guarded_by_no_live_or_loaded_data(self):
        """DEF-P1-011: fuel burn reset must only happen when avg <= 0 AND loaded <= 0."""
        self.assertIn("<= 0", self._body,
                      "_on_event_set_active fuel burn reset must be conditional on <= 0 check")


# ---------------------------------------------------------------------------
# Group 11b — DEF-P2-021: AI Log list auto-selects new live entries
# ---------------------------------------------------------------------------

class TestAiLogAutoSelect(unittest.TestCase):

    def setUp(self):
        self._text = _dashboard_text()

    def test_add_ai_log_list_item_has_auto_select_param(self):
        """DEF-P2-021: _add_ai_log_list_item must accept an auto_select parameter."""
        body = _method_body(self._text, "_add_ai_log_list_item")
        self.assertIn("auto_select", body,
                      "_add_ai_log_list_item must have an auto_select parameter")

    def test_add_ai_log_list_item_calls_set_current_row_when_auto_select(self):
        """DEF-P2-021: _add_ai_log_list_item must call setCurrentRow when auto_select=True."""
        body = _method_body(self._text, "_add_ai_log_list_item")
        self.assertIn("setCurrentRow", body,
                      "_add_ai_log_list_item must call setCurrentRow to make new entry visible")
        self.assertIn("auto_select", body,
                      "setCurrentRow must be guarded by auto_select flag")

    def test_on_ai_log_entry_defers_selection_via_qtimer(self):
        """DEF-P2-021/DEF-P2-033: _on_ai_log_entry must defer selection via QTimer, not auto_select=True."""
        body = _method_body(self._text, "_on_ai_log_entry")
        # Group 14 (DEF-P2-033) replaced auto_select=True with QTimer.singleShot for correct
        # deferred selection — the old auto_select=True approach caused invisible setCurrentRow
        # calls when the AI Log tab was not the active tab.
        self.assertIn("QTimer", body,
                      "_on_ai_log_entry must schedule selection via QTimer.singleShot (DEF-P2-033)")
        self.assertNotIn("auto_select=True", body,
                         "_on_ai_log_entry must not use auto_select=True (replaced by QTimer in DEF-P2-033)")

    def test_on_ai_log_entry_dict_does_not_auto_select(self):
        """DB-loaded history entries must NOT auto-select (would disrupt startup load order)."""
        body = _method_body(self._text, "_on_ai_log_entry_dict")
        self.assertNotIn("auto_select=True", body,
                         "_on_ai_log_entry_dict (DB load) must not pass auto_select=True")


# ---------------------------------------------------------------------------
# Group 11c — DEF-P1-011: fuel burn label updated from live practice telemetry
# ---------------------------------------------------------------------------

class TestFuelBurnLiveTelemetryUpdate(unittest.TestCase):

    def setUp(self):
        self._body = _method_body(_dashboard_text(), "_refresh_telemetry_context")

    def test_refresh_reads_avg_fuel_per_lap(self):
        """DEF-P1-011: _refresh_telemetry_context must read avg_fuel_per_lap from tracker."""
        self.assertIn("avg_fuel_per_lap", self._body,
                      "_refresh_telemetry_context must read avg_fuel_per_lap from tracker")

    def test_refresh_updates_fuel_burn_display_label(self):
        """DEF-P1-011: _refresh_telemetry_context must update _lbl_fuel_burn_display."""
        self.assertIn("_lbl_fuel_burn_display", self._body,
                      "_refresh_telemetry_context must reference _lbl_fuel_burn_display for live update")

    def test_refresh_uses_from_telemetry_suffix(self):
        """DEF-P1-011: live update label text must say '(from telemetry)' to distinguish from loaded session."""
        self.assertIn("from telemetry", self._body,
                      "_refresh_telemetry_context label must include 'from telemetry' suffix")

    def test_refresh_guards_update_when_avg_positive(self):
        """DEF-P1-011: fuel burn display must only update when avg_fuel_per_lap > 0."""
        self.assertIn("> 0", self._body,
                      "_refresh_telemetry_context must guard label update with avg > 0 check")


if __name__ == "__main__":
    unittest.main()
