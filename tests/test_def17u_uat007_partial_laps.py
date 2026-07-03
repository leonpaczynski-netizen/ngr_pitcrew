"""DEF-17U-UAT-007 regression tests.

Covers the UI-layer fix for the false "pit-in" diagnostic shown on clean Time
Trial calibration laps when pit detection is disabled (the default since Group 18A).

Changes tested:
  A. format_no_usable_laps(result) — count-based message, pit-detection state,
     no "pit-in" text when pit detection is off.
  B. format_build_failure_diagnostics(result) — consumes partial_start_count,
     partial_stop_count, rejected_too_few_samples, rejected_path_length,
     pit_detection_enabled; suppresses pit recommendations when off.
  C. _CAL_LAP_QUALITY_LABELS — partial_start / partial_stop entries present and
     distinct from "Rejected" / "Pit-in".
  D. get_workflow_error_message("no_usable_laps") — static fallback no longer
     contains the old "pit-in" wording or "Drive a clean lap first" phrase.

All tests are pure Python (no PyQt6 dependency).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import pytest


# ---------------------------------------------------------------------------
# Minimal stubs for CalibrationBuildResult
# ---------------------------------------------------------------------------

@dataclass
class _BuildResult:
    """Minimal stub matching the CalibrationBuildResult fields we consume."""
    success: bool = False
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    usable_lap_count: int = 0
    rejected_lap_count: int = 0
    low_confidence_lap_count: int = 0
    partial_start_count: int = 0
    partial_stop_count: int = 0
    rejected_too_few_samples: int = 0
    rejected_path_length: int = 0
    pit_detection_enabled: bool = False
    reference_path: Optional[object] = None


# ---------------------------------------------------------------------------
# A. format_no_usable_laps
# ---------------------------------------------------------------------------

class TestFormatNoUsableLaps:
    """Tests for the new format_no_usable_laps() helper."""

    def _r(self, **kw) -> _BuildResult:
        return _BuildResult(**kw)

    def test_returns_string(self):
        from ui.track_modelling_vm import format_no_usable_laps
        msg = format_no_usable_laps(self._r())
        assert isinstance(msg, str)

    def test_no_usable_text_present(self):
        from ui.track_modelling_vm import format_no_usable_laps
        msg = format_no_usable_laps(self._r())
        assert "No usable laps" in msg

    def test_pit_detection_off_shown(self):
        from ui.track_modelling_vm import format_no_usable_laps
        msg = format_no_usable_laps(self._r(pit_detection_enabled=False))
        assert "Pit detection: off" in msg

    def test_pit_detection_on_shown(self):
        from ui.track_modelling_vm import format_no_usable_laps
        msg = format_no_usable_laps(self._r(pit_detection_enabled=True))
        assert "Pit detection: on" in msg

    def test_no_pit_in_text_when_detection_off(self):
        """The UAT scenario: Time Trial laps, pit detection off — no pit-in wording."""
        from ui.track_modelling_vm import format_no_usable_laps
        msg = format_no_usable_laps(self._r(pit_detection_enabled=False))
        assert "pit-in" not in msg.lower()
        assert "pit in" not in msg.lower()
        assert "all calibration laps appear to be pit" not in msg.lower()

    def test_no_drive_clean_lap_first_when_candidates_exist(self):
        """When complete candidates exist but all rejected, don't say 'Drive a clean lap first'."""
        from ui.track_modelling_vm import format_no_usable_laps
        # 2 complete candidates, both rejected for path length
        msg = format_no_usable_laps(self._r(
            rejected_lap_count=2,
            rejected_path_length=2,
            pit_detection_enabled=False,
        ))
        assert "Drive a clean lap first" not in msg

    def test_shows_complete_candidate_count(self):
        from ui.track_modelling_vm import format_no_usable_laps
        msg = format_no_usable_laps(self._r(
            rejected_lap_count=3,
            pit_detection_enabled=False,
        ))
        # complete candidates = 0 usable + 3 rejected + 0 low_conf = 3
        assert "3" in msg

    def test_shows_partial_start_count(self):
        from ui.track_modelling_vm import format_no_usable_laps
        msg = format_no_usable_laps(self._r(partial_start_count=1))
        assert "1" in msg
        assert "partial-start" in msg.lower() or "partial_start" in msg.lower()

    def test_shows_partial_stop_count(self):
        from ui.track_modelling_vm import format_no_usable_laps
        msg = format_no_usable_laps(self._r(partial_stop_count=1))
        assert "partial-stop" in msg.lower() or "partial_stop" in msg.lower()

    def test_shows_rejected_too_few_samples(self):
        from ui.track_modelling_vm import format_no_usable_laps
        msg = format_no_usable_laps(self._r(
            rejected_lap_count=2,
            rejected_too_few_samples=2,
        ))
        assert "too few" in msg.lower() or "samples" in msg.lower()

    def test_shows_rejected_path_length(self):
        from ui.track_modelling_vm import format_no_usable_laps
        msg = format_no_usable_laps(self._r(
            rejected_lap_count=1,
            rejected_path_length=1,
        ))
        assert "path-length" in msg.lower() or "outlier" in msg.lower()

    def test_uat_scenario_1_partial_start_1_partial_stop_no_usable(self):
        """UAT scenario: 0 usable, 1 partial-start, 1 partial-stop, pit detection off."""
        from ui.track_modelling_vm import format_no_usable_laps
        msg = format_no_usable_laps(self._r(
            partial_start_count=1,
            partial_stop_count=1,
            pit_detection_enabled=False,
        ))
        # Must report pit detection off
        assert "Pit detection: off" in msg
        # Must mention partial laps
        assert "partial" in msg.lower()
        # Must NOT contain pit-in wording
        assert "pit-in" not in msg.lower()
        # Must NOT say "Drive a clean lap first"
        assert "Drive a clean lap first" not in msg
        # Complete candidates = 0 (no full laps) — guide user to drive complete laps
        assert "lap" in msg.lower()

    def test_drives_laps_recommendation_when_no_complete_candidates(self):
        from ui.track_modelling_vm import format_no_usable_laps
        msg = format_no_usable_laps(self._r(partial_start_count=1, partial_stop_count=1))
        assert "complete" in msg.lower() or "lap" in msg.lower()

    def test_diagnostics_recommendation_when_candidates_rejected(self):
        from ui.track_modelling_vm import format_no_usable_laps
        msg = format_no_usable_laps(self._r(
            rejected_lap_count=2,
            rejected_path_length=2,
        ))
        # Should recommend checking diagnostics, not driving more laps when laps exist
        assert "diagnostic" in msg.lower() or "build" in msg.lower()

    def test_no_pit_in_substring_in_any_case_when_detection_off(self):
        from ui.track_modelling_vm import format_no_usable_laps
        for r in [
            self._r(pit_detection_enabled=False),
            self._r(rejected_lap_count=5, pit_detection_enabled=False),
            self._r(partial_start_count=1, partial_stop_count=1, pit_detection_enabled=False),
        ]:
            msg = format_no_usable_laps(r)
            assert "pit-in" not in msg.lower(), f"Found 'pit-in' in message: {msg!r}"


# ---------------------------------------------------------------------------
# B. format_build_failure_diagnostics — new fields
# ---------------------------------------------------------------------------

class TestFormatBuildFailureDiagnosticsPartialCounts:
    """Tests for DEF-17U-UAT-007 additions to format_build_failure_diagnostics."""

    def _r(self, **kw) -> _BuildResult:
        return _BuildResult(**kw)

    def test_shows_partial_start_in_breakdown(self):
        from ui.track_modelling_vm import format_build_failure_diagnostics
        result = self._r(
            rejected_lap_count=0,
            partial_start_count=1,
            partial_stop_count=0,
        )
        msg = format_build_failure_diagnostics(result)
        assert "partial-start" in msg.lower() or "partial_start" in msg.lower()
        assert "1" in msg

    def test_shows_partial_stop_in_breakdown(self):
        from ui.track_modelling_vm import format_build_failure_diagnostics
        result = self._r(
            rejected_lap_count=0,
            partial_start_count=0,
            partial_stop_count=1,
        )
        msg = format_build_failure_diagnostics(result)
        assert "partial-stop" in msg.lower() or "partial_stop" in msg.lower()

    def test_shows_too_few_samples_sub_reason(self):
        from ui.track_modelling_vm import format_build_failure_diagnostics
        result = self._r(
            rejected_lap_count=2,
            rejected_too_few_samples=2,
        )
        msg = format_build_failure_diagnostics(result)
        assert "too few" in msg.lower() or "samples" in msg.lower()

    def test_shows_path_length_sub_reason(self):
        from ui.track_modelling_vm import format_build_failure_diagnostics
        result = self._r(
            rejected_lap_count=1,
            rejected_path_length=1,
        )
        msg = format_build_failure_diagnostics(result)
        assert "path-length" in msg.lower() or "outlier" in msg.lower()

    def test_shows_pit_detection_state_off(self):
        from ui.track_modelling_vm import format_build_failure_diagnostics
        result = self._r(rejected_lap_count=1, pit_detection_enabled=False)
        msg = format_build_failure_diagnostics(result)
        assert "pit detection: off" in msg.lower()

    def test_shows_pit_detection_state_on(self):
        from ui.track_modelling_vm import format_build_failure_diagnostics
        result = self._r(rejected_lap_count=1, pit_detection_enabled=True)
        msg = format_build_failure_diagnostics(result)
        assert "pit detection: on" in msg.lower()

    def test_no_pit_recommendation_when_detection_off(self):
        """Outlier-rejection case with pit detection off must NOT say 'avoid pit stops'."""
        from ui.track_modelling_vm import format_build_failure_diagnostics
        result = self._r(
            rejected_lap_count=2,
            rejected_path_length=2,
            pit_detection_enabled=False,
        )
        msg = format_build_failure_diagnostics(result)
        assert "avoid pit stops" not in msg.lower()
        assert "pit stop" not in msg.lower()

    def test_pit_recommendation_present_when_detection_on_and_outlier(self):
        """When pit detection ran and outlier warnings exist, pit recommendation IS shown."""
        from ui.track_modelling_vm import format_build_failure_diagnostics
        result = self._r(
            rejected_lap_count=2,
            pit_detection_enabled=True,
            warnings=["Lap 1: path length outlier"],
        )
        msg = format_build_failure_diagnostics(result)
        assert "avoid pit" in msg.lower() or "pit stop" in msg.lower()

    def test_pit_warnings_filtered_from_rejection_details_when_off(self):
        """Pit-related warning strings in result.warnings are suppressed when pit detection off."""
        from ui.track_modelling_vm import format_build_failure_diagnostics
        result = self._r(
            rejected_lap_count=1,
            pit_detection_enabled=False,
            warnings=["Lap 1: detected as pit-in lap — excluded"],
        )
        msg = format_build_failure_diagnostics(result)
        # The "pit-in" string from the warning must not appear in the rendered output
        assert "pit-in" not in msg.lower()

    def test_uat_scenario_diagnostics(self):
        """UAT scenario: 0 usable, 1 partial-start, 1 partial-stop, pit detection off."""
        from ui.track_modelling_vm import format_build_failure_diagnostics
        result = self._r(
            usable_lap_count=0,
            rejected_lap_count=0,
            low_confidence_lap_count=0,
            partial_start_count=1,
            partial_stop_count=1,
            pit_detection_enabled=False,
        )
        msg = format_build_failure_diagnostics(result)
        # Pit detection off shown
        assert "pit detection: off" in msg.lower()
        # Partial laps mentioned
        assert "partial" in msg.lower()
        # No pit-in wording
        assert "pit-in" not in msg.lower()
        assert "all calibration laps appear to be pit" not in msg.lower()
        # Does NOT say "Drive a clean lap first"
        assert "drive a clean lap first" not in msg.lower()

    def test_partial_excluded_not_in_rejected_total(self):
        """Partial laps should be clearly noted as separate from the rejected total."""
        from ui.track_modelling_vm import format_build_failure_diagnostics
        result = self._r(
            usable_lap_count=0,
            rejected_lap_count=0,
            partial_start_count=1,
            partial_stop_count=1,
            pit_detection_enabled=False,
        )
        msg = format_build_failure_diagnostics(result)
        # The note about partial not being counted in rejected must appear
        assert "not counted" in msg.lower() or "excluded" in msg.lower()


# ---------------------------------------------------------------------------
# C. _CAL_LAP_QUALITY_LABELS — per-lap status display mapping
# ---------------------------------------------------------------------------

class TestCalLapQualityLabels:
    """Tests for the new _CAL_LAP_QUALITY_LABELS mapping."""

    def test_dict_exists(self):
        from ui.track_modelling_vm import _CAL_LAP_QUALITY_LABELS
        assert isinstance(_CAL_LAP_QUALITY_LABELS, dict)

    def test_partial_start_maps_to_partial_start_label(self):
        from ui.track_modelling_vm import _CAL_LAP_QUALITY_LABELS
        label = _CAL_LAP_QUALITY_LABELS.get("partial_start", "")
        assert label, "partial_start key must be present"
        assert "partial" in label.lower() or "start" in label.lower()

    def test_partial_stop_maps_to_partial_stop_label(self):
        from ui.track_modelling_vm import _CAL_LAP_QUALITY_LABELS
        label = _CAL_LAP_QUALITY_LABELS.get("partial_stop", "")
        assert label, "partial_stop key must be present"
        assert "partial" in label.lower() or "stop" in label.lower()

    def test_partial_start_label_distinct_from_rejected(self):
        from ui.track_modelling_vm import _CAL_LAP_QUALITY_LABELS
        partial_start_lbl = _CAL_LAP_QUALITY_LABELS.get("partial_start", "")
        rejected_lbl      = _CAL_LAP_QUALITY_LABELS.get("rejected", "")
        assert partial_start_lbl != rejected_lbl, (
            "partial_start label must differ from generic Rejected label"
        )

    def test_partial_stop_label_distinct_from_rejected(self):
        from ui.track_modelling_vm import _CAL_LAP_QUALITY_LABELS
        partial_stop_lbl = _CAL_LAP_QUALITY_LABELS.get("partial_stop", "")
        rejected_lbl     = _CAL_LAP_QUALITY_LABELS.get("rejected", "")
        assert partial_stop_lbl != rejected_lbl

    def test_partial_start_label_never_pit_in(self):
        from ui.track_modelling_vm import _CAL_LAP_QUALITY_LABELS
        label = _CAL_LAP_QUALITY_LABELS.get("partial_start", "")
        assert "pit" not in label.lower(), (
            "partial_start label must not contain 'pit'"
        )

    def test_partial_stop_label_never_pit_in(self):
        from ui.track_modelling_vm import _CAL_LAP_QUALITY_LABELS
        label = _CAL_LAP_QUALITY_LABELS.get("partial_stop", "")
        assert "pit" not in label.lower(), (
            "partial_stop label must not contain 'pit'"
        )

    def test_all_existing_quality_keys_present(self):
        """Existing usable/rejected/low_confidence/recording mappings must still be present."""
        from ui.track_modelling_vm import _CAL_LAP_QUALITY_LABELS
        for key in ("usable", "rejected", "low_confidence", "recording"):
            assert key in _CAL_LAP_QUALITY_LABELS, f"Missing key: {key!r}"

    def test_partial_start_display_string(self):
        """Exact display string for partial_start should be 'Partial (start)'."""
        from ui.track_modelling_vm import _CAL_LAP_QUALITY_LABELS
        assert _CAL_LAP_QUALITY_LABELS["partial_start"] == "Partial (start)"

    def test_partial_stop_display_string(self):
        """Exact display string for partial_stop should be 'Partial (stop)'."""
        from ui.track_modelling_vm import _CAL_LAP_QUALITY_LABELS
        assert _CAL_LAP_QUALITY_LABELS["partial_stop"] == "Partial (stop)"


# ---------------------------------------------------------------------------
# D. Static fallback in _WORKFLOW_ERROR_MESSAGES["no_usable_laps"]
# ---------------------------------------------------------------------------

class TestNoUsableLapsStaticFallback:
    """Tests for the updated static 'no_usable_laps' message."""

    def test_message_exists(self):
        from ui.track_modelling_vm import get_workflow_error_message
        msg = get_workflow_error_message("no_usable_laps")
        assert isinstance(msg, str)
        assert msg  # non-empty

    def test_no_pit_in_text(self):
        """Old wording had 'pit-in' when pit detection was the assumed cause."""
        from ui.track_modelling_vm import get_workflow_error_message
        msg = get_workflow_error_message("no_usable_laps")
        assert "pit-in" not in msg.lower()
        assert "pit in" not in msg.lower()

    def test_no_drive_clean_lap_first(self):
        """Old wording said 'Drive a clean lap first' — removed."""
        from ui.track_modelling_vm import get_workflow_error_message
        msg = get_workflow_error_message("no_usable_laps")
        assert "Drive a clean lap first" not in msg

    def test_does_not_contain_all_calibration_laps_pit(self):
        """The exact old false-positive message must no longer appear."""
        from ui.track_modelling_vm import get_workflow_error_message
        msg = get_workflow_error_message("no_usable_laps")
        assert "All calibration laps appear to be pit-in" not in msg

    def test_format_no_usable_laps_importable(self):
        """format_no_usable_laps must be importable from ui.track_modelling_vm."""
        from ui.track_modelling_vm import format_no_usable_laps
        assert callable(format_no_usable_laps)


# ---------------------------------------------------------------------------
# E. Pit warning filter guard (unit test for the logic, not the Qt widget)
# ---------------------------------------------------------------------------

class TestPitWarningFilterLogic:
    """Tests for the pit_detection_enabled gate on pit-warning display.

    These tests exercise the logic of the gate without instantiating any Qt widgets.
    They verify that pit_detection_enabled=False means no pit warnings should surface.
    """

    def _r(self, **kw) -> _BuildResult:
        return _BuildResult(**kw)

    def test_pit_detection_off_no_pit_warning_in_diagnostics(self):
        """When pit detection is off, build diagnostics contain no pit-related text."""
        from ui.track_modelling_vm import format_build_failure_diagnostics
        result = self._r(
            rejected_lap_count=1,
            pit_detection_enabled=False,
            warnings=["Lap 1: classified as pit-in lap"],
        )
        msg = format_build_failure_diagnostics(result)
        assert "pit-in lap" not in msg.lower()

    def test_pit_detection_on_pit_warning_passes_through(self):
        """When pit detection is on, pit-related warnings are NOT filtered."""
        from ui.track_modelling_vm import format_build_failure_diagnostics
        result = self._r(
            rejected_lap_count=1,
            pit_detection_enabled=True,
            warnings=["Lap 1: classified as pit-in lap"],
        )
        msg = format_build_failure_diagnostics(result)
        assert "pit-in lap" in msg.lower()

    def test_pit_detection_enabled_attribute_on_stub_defaults_false(self):
        """CalibrationBuildResult default pit_detection_enabled is False."""
        r = self._r()
        assert r.pit_detection_enabled is False
