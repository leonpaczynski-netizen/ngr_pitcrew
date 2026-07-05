"""Tests for Remediation Group 6 fixes.

DEF-P2-015: Top speed target in AI prompt shows invalid value (~11 km/h)
DEF-P2-010: Driver feedback form embedded in Setup Builder instead of Practice Review

Register corrections (code already correct, register was stale):
  DEF-P2-003: Required Tyres checkbox grid — confirmed implemented
  DEF-P2-017: Qualifying RACE_FINISHED — confirmed fixed via DEF-P2-QRF (Group 5)
  DEF-P3-004: Race type mutual exclusivity — confirmed implemented
"""
from __future__ import annotations

import pathlib
import unittest

_SRC = pathlib.Path(__file__).parent.parent


def _dashboard_text() -> str:
    return (_SRC / "ui" / "dashboard.py").read_text(encoding="utf-8")

def _setup_builder_text() -> str:
    # Setup builder UI now spans two files: the mixin and the extracted form widget.
    # Source-scan tests search the combined text to preserve coverage after refactor.
    return (
        (_SRC / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
        + "\n"
        + (_SRC / "ui" / "setup_form_widget.py").read_text(encoding="utf-8")
    )


def _state_text() -> str:
    return (_SRC / "telemetry" / "state.py").read_text(encoding="utf-8")


def _method_body(text: str, method_name: str) -> str:
    start = text.find(f"def {method_name}(")
    if start == -1:
        return ""
    end = text.find("\n    def ", start + 1)
    return text[start:end] if end != -1 else text[start:]


# ---------------------------------------------------------------------------
# DEF-P2-015 — Top speed target invalid value guard
# ---------------------------------------------------------------------------

class TestTopSpeedGuard(unittest.TestCase):

    def test_refresh_gear_ratios_has_50kmh_threshold(self):
        """_refresh_gear_ratios must reject top speed values below 50 km/h."""
        src = _dashboard_text()
        body = _method_body(src, "_refresh_gear_ratios")
        self.assertGreater(len(body), 0,
                           "_refresh_gear_ratios must exist in dashboard.py")
        self.assertIn("50", body,
                      "_refresh_gear_ratios must reference the 50 km/h minimum threshold")
        self.assertNotIn("ms > 0", body,
                         "_refresh_gear_ratios must NOT use 'ms > 0' (allows invalid ~11 km/h value)")

    def test_threshold_is_ge_50(self):
        """The guard must use >= 50 so values like 11 km/h are excluded."""
        src = _dashboard_text()
        body = _method_body(src, "_refresh_gear_ratios")
        self.assertIn("ms >= 50", body,
                      "_refresh_gear_ratios must use 'ms >= 50' as the validity threshold")

    def test_spin_top_speed_special_value_text(self):
        """_spin_top_speed must show '—' when value is 0 (no valid capture)."""
        src = _setup_builder_text()
        pos = src.find("self._spin_top_speed = QDoubleSpinBox()")
        self.assertGreater(pos, -1, "_spin_top_speed QDoubleSpinBox creation must exist")
        snippet = src[pos:pos + 400]
        self.assertIn("setSpecialValueText", snippet,
                      "_spin_top_speed must have setSpecialValueText for zero-value display")
        self.assertIn('"—"', snippet,
                      "_spin_top_speed special value text must be '—'")

    def test_top_speed_guard_logic(self):
        """Logic: only values >= 50 are written to the spinbox."""
        def _should_capture(ms: float) -> bool:
            return ms >= 50

        self.assertFalse(_should_capture(11.0), "11 km/h raw artefact must be rejected")
        self.assertFalse(_should_capture(0.0), "0 must be rejected")
        self.assertFalse(_should_capture(49.9), "49.9 km/h must be rejected")
        self.assertTrue(_should_capture(50.0), "50.0 km/h is the boundary — accept")
        self.assertTrue(_should_capture(250.0), "250 km/h typical GT7 top speed — accept")
        self.assertTrue(_should_capture(120.0), "120 km/h minimum realistic GT7 speed — accept")

    def test_current_setup_dict_includes_transmission_max_speed(self):
        """_current_setup_dict must still include transmission_max_speed_kmh key."""
        src = _setup_builder_text()
        body = _method_body(src, "_current_setup_dict")
        self.assertIn("transmission_max_speed_kmh", body,
                      "_current_setup_dict must include transmission_max_speed_kmh in the setup dict")


# ---------------------------------------------------------------------------
# DEF-P2-010 — Driver feedback form location
# ---------------------------------------------------------------------------

class TestDriverFeedbackLocation(unittest.TestCase):

    def test_feedback_form_in_practice_review(self):
        """_build_driver_feedback_form must be called from _build_practice_review_tab."""
        body = _method_body(_dashboard_text(), "_build_practice_review_tab")
        self.assertIn("_build_driver_feedback_form", body,
                      "_build_practice_review_tab must include the driver feedback form")

    def test_feedback_form_not_in_setup_builder(self):
        """_build_driver_feedback_form must NOT be called from _build_setup_builder_tab."""
        body = _method_body(_setup_builder_text(), "_build_setup_builder_tab")
        self.assertNotIn("_build_driver_feedback_form", body,
                         "_build_setup_builder_tab must not call _build_driver_feedback_form")

    def test_submit_handler_guards_setup_feeling_input(self):
        """_on_driver_feedback_submit must not access _setup_feeling_input unconditionally."""
        body = _method_body(_dashboard_text(), "_on_driver_feedback_submit")
        if "_setup_feeling_input" in body:
            self.assertIn("hasattr", body,
                          "_on_driver_feedback_submit must guard _setup_feeling_input with hasattr "
                          "since the form may live in Practice Review (no Setup Builder context)")

    def test_submit_handler_uses_session_id(self):
        """_on_driver_feedback_submit must use _session_id (not hardcoded 0) for DB write."""
        body = _method_body(_dashboard_text(), "_on_driver_feedback_submit")
        self.assertNotIn("session_id=0", body,
                         "_on_driver_feedback_submit must not hardcode session_id=0")
        self.assertIn("_session_id", body,
                      "_on_driver_feedback_submit must use _session_id for the DB write")

    def test_feedback_form_title(self):
        """Driver feedback form must have a recognisable group title."""
        src = _dashboard_text()
        form_pos = src.find("def _build_driver_feedback_form(")
        self.assertGreater(form_pos, -1)
        snippet = src[form_pos:form_pos + 300]
        self.assertIn("Driver Feedback", snippet,
                      "_build_driver_feedback_form must create a QGroupBox with 'Driver Feedback' in the title")

    def test_feedback_combos_created(self):
        """_build_driver_feedback_form must create _feedback_combos dict."""
        src = _dashboard_text()
        body = _method_body(src, "_build_driver_feedback_form")
        self.assertIn("_feedback_combos", body,
                      "_build_driver_feedback_form must create the _feedback_combos dict")

    def test_submit_button_present(self):
        """_build_driver_feedback_form must include a submit button."""
        src = _dashboard_text()
        body = _method_body(src, "_build_driver_feedback_form")
        self.assertIn("_on_driver_feedback_submit", body,
                      "_build_driver_feedback_form must connect a button to _on_driver_feedback_submit")


# ---------------------------------------------------------------------------
# Register correctness checks — DEF-P2-003, DEF-P2-017, DEF-P3-004
# ---------------------------------------------------------------------------

class TestRegisterCorrections(unittest.TestCase):
    """Verify that defects marked 'Open' in the register are actually fixed in code."""

    def test_req_tyre_checks_is_checkbox_grid(self):
        """DEF-P2-003: _req_tyre_checks must be a checkbox grid, not a QComboBox."""
        src = _dashboard_text()
        self.assertIn("_req_tyre_checks", src,
                      "DEF-P2-003: _req_tyre_checks checkbox grid must exist in dashboard.py")
        # Confirm it's a dict of QCheckBox, not a QComboBox
        pos = src.find("_req_tyre_checks")
        snippet = src[pos:pos + 500]
        self.assertIn("QCheckBox", snippet,
                      "DEF-P2-003: _req_tyre_checks must be built from QCheckBox widgets")

    def test_avail_tyre_subset_enforcement(self):
        """DEF-P2-003: unchecking Available must disable the matching Required checkbox."""
        src = _dashboard_text()
        self.assertIn("_avail_toggled", src,
                      "DEF-P2-003: _avail_toggled callback must enforce Available→Required subset")

    def test_qualifying_race_finished_guard_in_state(self):
        """DEF-P2-017: state.py must exclude QUALIFYING from RACE_FINISHED condition."""
        src = _state_text()
        block = src[src.find("RACE_FINISHED"):src.find("RACE_FINISHED") + 600]
        self.assertIn("QUALIFYING", block,
                      "DEF-P2-017: state.py RACE_FINISHED timed-race guard must exclude QUALIFYING")

    def test_race_type_mutual_exclusivity_in_event_planner(self):
        """DEF-P3-004: _on_race_type_changed must disable laps or duration based on race type."""
        src = _dashboard_text()
        body = _method_body(src, "_on_race_type_changed")
        self.assertIn("setEnabled", body,
                      "DEF-P3-004: _on_race_type_changed must call setEnabled to enforce mutual exclusivity")
        self.assertIn("is_timed", body,
                      "DEF-P3-004: _on_race_type_changed must branch on is_timed flag")

    def test_race_type_toggle_applied_on_init(self):
        """DEF-P3-004: mutual exclusivity must be applied immediately on tab build."""
        src = _dashboard_text()
        # _on_race_type_changed must be called once at init after creation
        pos = src.find("_on_race_type_changed")
        calls = src.count("_on_race_type_changed(")
        self.assertGreaterEqual(calls, 2,
                                "DEF-P3-004: _on_race_type_changed must be called at init "
                                "as well as connected to signal")


if __name__ == "__main__":
    unittest.main()
