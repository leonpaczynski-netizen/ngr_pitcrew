"""Tests for Group 13: Live session defects (DEF-P2-023 through DEF-P2-027).

DEF-P2-023: Pit Lap Not Captured — fuel-only pit detection misses no-refuel stops.
            Fix: speed-based fallback triggers _enter_pit() when car stationary
            (speed < 10 km/h) for 3+ seconds in RACING phase.

DEF-P2-024: Outlap Metadata Lost After History Reload — _save_session_to_db()
            called write_lap() without is_out_lap. Fix: pass is_out_lap kwarg.

DEF-P2-025: Fuel Data Lost After History Reload — _save_session_to_db() called
            write_lap() without fuel_start/fuel_end. Fix: pass both kwargs.

DEF-P2-026: Tyre Compound Propagation — _on_compound_selected() broke at the first
            subsequent row with any different compound (every row has the default
            pre-set), preventing propagation. Fix: stop at is_pit_lap boundary
            instead of at a different compound string.

DEF-P2-027: Live Tab Wrong Tyre — label read mandatory_compounds (event required
            tyre) instead of actual fitted compound. Fix: update label in
            _on_compound_selected() with the user-selected compound.
"""
from __future__ import annotations

import pathlib
import unittest

_SRC = pathlib.Path(__file__).parent.parent


def _dashboard_text() -> str:
    return (_SRC / "ui" / "dashboard.py").read_text(encoding="utf-8") + (_SRC / "ui" / "live_ui.py").read_text(encoding="utf-8")


def _state_text() -> str:
    return (_SRC / "telemetry" / "state.py").read_text(encoding="utf-8")


def _method_body(text: str, method_name: str) -> str:
    start = text.find(f"def {method_name}(")
    if start == -1:
        return ""
    end = text.find("\n    def ", start + 1)
    return text[start:end] if end != -1 else text[start:]


# ---------------------------------------------------------------------------
# 13a — DEF-P2-023: Speed-based pit detection
# ---------------------------------------------------------------------------

class TestSpeedBasedPitDetection(unittest.TestCase):

    def setUp(self):
        self._state = _state_text()

    def test_low_speed_start_initialized_in_reset(self):
        """DEF-P2-023: _low_speed_start must be initialized in _reset() for no-refuel detection."""
        body = _method_body(self._state, "_reset")
        self.assertIn("_low_speed_start", body,
                      "_reset must initialize _low_speed_start for speed-based pit detection")

    def test_speed_threshold_10_kmh(self):
        """DEF-P2-023: speed-based detection must use 10 km/h as the near-stationary threshold."""
        body = _method_body(self._state, "_phase_transitions")
        self.assertIn("speed_kmh < 10", body,
                      "_phase_transitions must check speed_kmh < 10 for no-refuel pit detection")

    def test_timeout_3_seconds(self):
        """DEF-P2-023: speed-based detection must require 3+ seconds before firing."""
        body = _method_body(self._state, "_phase_transitions")
        self.assertIn("3.0", body,
                      "_phase_transitions speed-based pit detection must wait 3.0 seconds")

    def test_low_speed_start_checked_and_set(self):
        """DEF-P2-023: _low_speed_start must be read and set in _phase_transitions."""
        body = _method_body(self._state, "_phase_transitions")
        self.assertIn("_low_speed_start", body,
                      "_phase_transitions must use _low_speed_start to track stationary duration")

    def test_speed_detection_gated_on_racing_phase(self):
        """DEF-P2-023: speed-based fallback must only fire in RACING phase, not PRE_RACE."""
        body = _method_body(self._state, "_phase_transitions")
        self.assertIn("RacePhase.RACING", body,
                      "_phase_transitions speed-based detection must be gated on RACING phase only")

    def test_low_speed_start_reset_in_enter_pit(self):
        """DEF-P2-023: _enter_pit must reset _low_speed_start to prevent double-firing."""
        body = _method_body(self._state, "_enter_pit")
        self.assertIn("_low_speed_start", body,
                      "_enter_pit must reset _low_speed_start = 0.0 to avoid double-trigger")


# ---------------------------------------------------------------------------
# 13b — DEF-P2-024 + DEF-P2-025: Save Session passes all fields
# ---------------------------------------------------------------------------

class TestSaveSessionPassesAllFields(unittest.TestCase):

    def setUp(self):
        self._body = _method_body(_dashboard_text(), "_save_session_to_db")

    def test_passes_fuel_start(self):
        """DEF-P2-025: _save_session_to_db must pass fuel_start to write_lap."""
        self.assertIn("fuel_start=", self._body,
                      "_save_session_to_db must pass fuel_start= to write_lap (DEF-P2-025)")

    def test_passes_fuel_end(self):
        """DEF-P2-025: _save_session_to_db must pass fuel_end to write_lap."""
        self.assertIn("fuel_end=", self._body,
                      "_save_session_to_db must pass fuel_end= to write_lap (DEF-P2-025)")

    def test_passes_is_pit_lap(self):
        """DEF-P2-024: _save_session_to_db must pass is_pit_lap to write_lap."""
        self.assertIn("is_pit_lap=", self._body,
                      "_save_session_to_db must pass is_pit_lap= to write_lap")

    def test_passes_is_out_lap(self):
        """DEF-P2-024: _save_session_to_db must pass is_out_lap to write_lap."""
        self.assertIn("is_out_lap=", self._body,
                      "_save_session_to_db must pass is_out_lap= to write_lap (DEF-P2-024)")

    def test_passes_delta_ms(self):
        """_save_session_to_db must pass delta_ms to write_lap for completeness."""
        self.assertIn("delta_ms=", self._body,
                      "_save_session_to_db must pass delta_ms= to write_lap")

    def test_passes_session_type(self):
        """_save_session_to_db must pass session_type to write_lap for correct History label."""
        self.assertIn("session_type=", self._body,
                      "_save_session_to_db must pass session_type= to write_lap")

    def test_uses_getattr_for_lap_fields(self):
        """_save_session_to_db must use getattr() to safely read LapRecord fields."""
        self.assertIn("getattr(lap,", self._body,
                      "_save_session_to_db must use getattr(lap, ...) to safely read LapRecord fields")


# ---------------------------------------------------------------------------
# 13c — DEF-P2-026: Compound propagation stops at pit lap boundary
# ---------------------------------------------------------------------------

class TestCompoundPropagationStopsAtPitLap(unittest.TestCase):

    def setUp(self):
        self._body = _method_body(_dashboard_text(), "_on_compound_selected")

    def test_stops_at_is_pit_lap_flag(self):
        """DEF-P2-026: propagation must stop at is_pit_lap boundary, not at any different compound."""
        self.assertIn("is_pit_lap", self._body,
                      "_on_compound_selected must check is_pit_lap to determine propagation stop")

    def test_reads_user_role_data_for_pit_flag(self):
        """DEF-P2-026: must read UserRole data from col 0 to get is_pit_lap flag."""
        self.assertIn("UserRole", self._body,
                      "_on_compound_selected must read Qt.ItemDataRole.UserRole to get pit lap flags")

    def test_no_break_on_existing_different_compound(self):
        """DEF-P2-026: must NOT break propagation based on a pre-existing different compound string."""
        self.assertNotIn('existing and existing != norm', self._body,
                         '_on_compound_selected must not break on "existing and existing != norm" — '
                         'that stops propagation at every row with the default compound pre-set')


# ---------------------------------------------------------------------------
# 13d — DEF-P2-027: Live tyre label uses priority hierarchy, not mandatory tyre
# ---------------------------------------------------------------------------

class TestLiveTyreLabelPriorityHierarchy(unittest.TestCase):

    def setUp(self):
        self._text = _dashboard_text()

    def test_get_current_tyre_compound_method_exists(self):
        """DEF-P2-027: _get_current_tyre_compound helper must exist."""
        body = _method_body(self._text, "_get_current_tyre_compound")
        self.assertTrue(body, "_get_current_tyre_compound method must exist for live tyre priority logic")

    def test_priority1_reads_from_strategy_engine(self):
        """DEF-P2-027 P1: first priority must read active stint compound from strategy engine."""
        body = _method_body(self._text, "_get_current_tyre_compound")
        self.assertIn("_strategy_engine", body,
                      "_get_current_tyre_compound must check _strategy_engine for active stint compound")

    def test_priority1_reads_completed_flag(self):
        """DEF-P2-027 P1: must look for first incomplete stint (not just first stint)."""
        body = _method_body(self._text, "_get_current_tyre_compound")
        self.assertIn("completed", body,
                      "_get_current_tyre_compound must check stint.completed to find active stint")

    def test_priority2_reads_from_setup_tyre_f(self):
        """DEF-P2-027 P2: fallback must read tyre from Setup Builder front tyre widget."""
        body = _method_body(self._text, "_get_current_tyre_compound")
        self.assertIn("_setup_tyre_f", body,
                      "_get_current_tyre_compound must fall back to Setup Builder _setup_tyre_f")

    def test_priority3_returns_not_set(self):
        """DEF-P2-027 P3: if no plan and no setup tyre, must return 'Not Set'."""
        body = _method_body(self._text, "_get_current_tyre_compound")
        self.assertIn("Not Set", body,
                      '_get_current_tyre_compound must return "Not Set" when no source available')

    def test_refresh_live_tyre_label_method_exists(self):
        """DEF-P2-027: _refresh_live_tyre_label helper must exist."""
        body = _method_body(self._text, "_refresh_live_tyre_label")
        self.assertTrue(body, "_refresh_live_tyre_label method must exist")

    def test_refresh_calls_get_current_tyre_compound(self):
        """DEF-P2-027: _refresh_live_tyre_label must call _get_current_tyre_compound."""
        body = _method_body(self._text, "_refresh_live_tyre_label")
        self.assertIn("_get_current_tyre_compound", body,
                      "_refresh_live_tyre_label must call _get_current_tyre_compound()")

    def test_refresh_sets_current_tyre_prefix(self):
        """DEF-P2-027: label text must use 'Current Tyre:' prefix not 'Tyre:' or mandatory."""
        body = _method_body(self._text, "_refresh_live_tyre_label")
        self.assertIn("Current Tyre:", body,
                      '_refresh_live_tyre_label must set label text starting with "Current Tyre:"')

    def test_on_tyre_preset_changed_calls_refresh(self):
        """DEF-P2-027: _on_tyre_preset_changed must call _refresh_live_tyre_label on stint change."""
        body = _method_body(self._text, "_on_tyre_preset_changed")
        self.assertIn("_refresh_live_tyre_label", body,
                      "_on_tyre_preset_changed must call _refresh_live_tyre_label so label updates on stint change")

    def test_mandatory_compounds_not_used_for_current_tyre(self):
        """DEF-P2-027: _get_current_tyre_compound must NOT read mandatory_compounds."""
        body = _method_body(self._text, "_get_current_tyre_compound")
        self.assertNotIn("mandatory_compounds", body,
                         "_get_current_tyre_compound must not use mandatory_compounds — "
                         "those are race rule requirements, not the fitted tyre")


if __name__ == "__main__":
    unittest.main()
