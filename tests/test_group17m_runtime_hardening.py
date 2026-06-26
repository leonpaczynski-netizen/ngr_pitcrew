"""Group 17M — Runtime UAT and Calibration Workflow Hardening tests.

All tests are pure Python (no PyQt6).  Tests cover:
  - get_workflow_error_message()
  - get_calibration_button_states() for all workflow states and transitions
  - format_calibration_status_extended()
  - format_lap_offset_status()
  - format_live_resolver_status_summary()
  - RuntimeCheckResult.summary_text()
  - run_track_modelling_runtime_check()
  - create_offset_zero() integration
  - Existing 17A–17L imports continue to work
"""
from __future__ import annotations

import pytest
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Helpers — lightweight stubs for duck-typed interfaces
# ---------------------------------------------------------------------------

@dataclass
class _Calibration:
    """Stub for LapStartOffsetCalibration."""
    track_location_id: str = "suzuka"
    layout_id: str = "full"
    calibration_source: str = "zero_offset"
    track_length_m: float = 5807.0
    offset_m: float = 0.0
    confidence: object = None
    warnings: list = field(default_factory=list)

    def __post_init__(self):
        if self.confidence is None:
            self.confidence = _Enum("low")


@dataclass
class _Enum:
    value: str

    def __str__(self):
        return self.value


@dataclass
class _ResolvedModel:
    source_type: object = None
    ai_ready: bool = False
    blockers: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def __post_init__(self):
        if self.source_type is None:
            self.source_type = _Enum("seed_only")


@dataclass
class _ResolverResult:
    resolved_model: Optional[_ResolvedModel] = None
    resolution_status: object = None
    all_candidate_paths: list = field(default_factory=list)


@dataclass
class _LivePosition:
    road_distance_m: Optional[float] = None
    speed_kph: Optional[float] = None
    pos_x: Optional[float] = None
    pos_y: Optional[float] = None
    pos_z: Optional[float] = None


@dataclass
class _SegmentMatch:
    segment_id: str = "T1_braking"
    display_name: str = "T1 Braking Zone"


@dataclass
class _LiveSegResult:
    resolution_status: object = None
    match: Optional[_SegmentMatch] = None

    def __post_init__(self):
        if self.resolution_status is None:
            self.resolution_status = _Enum("matched")


# ---------------------------------------------------------------------------
# 1. Workflow error messages
# ---------------------------------------------------------------------------

class TestWorkflowErrorMessages:
    def test_all_known_keys_return_nonempty(self):
        from ui.track_modelling_vm import get_workflow_error_message
        keys = [
            "no_gt7_telemetry", "no_track_selected", "seed_file_missing",
            "no_usable_laps", "build_failed", "segment_detection_failed",
            "no_reviewed_model", "malformed_review_file", "missing_track_length",
            "road_distance_unavailable", "live_segment_unresolved",
        ]
        for k in keys:
            msg = get_workflow_error_message(k)
            assert isinstance(msg, str) and len(msg) > 10, f"Empty message for key: {k}"

    def test_unknown_key_returns_safe_string(self):
        from ui.track_modelling_vm import get_workflow_error_message
        msg = get_workflow_error_message("nonexistent_key_xyz")
        assert "nonexistent_key_xyz" in msg

    def test_no_track_selected_mentions_track(self):
        from ui.track_modelling_vm import get_workflow_error_message
        msg = get_workflow_error_message("no_track_selected")
        assert "track" in msg.lower() or "layout" in msg.lower()

    def test_no_gt7_telemetry_mentions_gt7(self):
        from ui.track_modelling_vm import get_workflow_error_message
        msg = get_workflow_error_message("no_gt7_telemetry")
        assert "GT7" in msg or "telemetry" in msg.lower()


# ---------------------------------------------------------------------------
# 2. Calibration button states
# ---------------------------------------------------------------------------

class TestCalibrationButtonStatesInactive:
    def test_start_enabled_with_track(self):
        from ui.track_modelling_vm import get_calibration_button_states
        s = get_calibration_button_states("inactive", True, False, False, False)
        assert s["start"] is True

    def test_start_disabled_without_track(self):
        from ui.track_modelling_vm import get_calibration_button_states
        s = get_calibration_button_states("inactive", False, False, False, False)
        assert s["start"] is False

    def test_stop_disabled_when_inactive(self):
        from ui.track_modelling_vm import get_calibration_button_states
        s = get_calibration_button_states("inactive", True, False, False, False)
        assert s["stop"] is False

    def test_build_disabled_when_inactive(self):
        from ui.track_modelling_vm import get_calibration_button_states
        s = get_calibration_button_states("inactive", True, True, False, False)
        assert s["build"] is False

    def test_all_review_disabled_when_no_model(self):
        from ui.track_modelling_vm import get_calibration_button_states
        s = get_calibration_button_states("inactive", True, False, False, False)
        for k in ("confirm", "rename", "reject", "needs_more_laps", "split_required", "merge_required"):
            assert s[k] is False, f"{k} should be disabled"


class TestCalibrationButtonStatesRecording:
    def test_stop_enabled_while_recording(self):
        from ui.track_modelling_vm import get_calibration_button_states
        s = get_calibration_button_states("recording", True, True, False, False)
        assert s["stop"] is True

    def test_start_disabled_while_recording(self):
        from ui.track_modelling_vm import get_calibration_button_states
        s = get_calibration_button_states("recording", True, True, False, False)
        assert s["start"] is False

    def test_build_disabled_while_recording(self):
        from ui.track_modelling_vm import get_calibration_button_states
        s = get_calibration_button_states("recording", True, True, False, False)
        assert s["build"] is False


class TestCalibrationButtonStatesStopped:
    def test_build_enabled_when_stopped_with_laps(self):
        from ui.track_modelling_vm import get_calibration_button_states
        s = get_calibration_button_states("stopped", True, True, False, False)
        assert s["build"] is True

    def test_build_disabled_when_stopped_no_laps(self):
        from ui.track_modelling_vm import get_calibration_button_states
        s = get_calibration_button_states("stopped", True, False, False, False)
        assert s["build"] is False

    def test_start_enabled_when_stopped_with_track(self):
        from ui.track_modelling_vm import get_calibration_button_states
        s = get_calibration_button_states("stopped", True, True, False, False)
        assert s["start"] is True

    def test_stop_disabled_when_stopped(self):
        from ui.track_modelling_vm import get_calibration_button_states
        s = get_calibration_button_states("stopped", True, True, False, False)
        assert s["stop"] is False


class TestCalibrationButtonStatesBuilt:
    def test_save_path_enabled_when_built(self):
        from ui.track_modelling_vm import get_calibration_button_states
        s = get_calibration_button_states("built", True, True, True, False)
        assert s["save_path"] is True

    def test_detect_segments_enabled_after_build(self):
        from ui.track_modelling_vm import get_calibration_button_states
        s = get_calibration_button_states("built", True, True, True, False)
        assert s["detect_segments"] is True

    def test_detect_segments_disabled_before_build(self):
        from ui.track_modelling_vm import get_calibration_button_states
        s = get_calibration_button_states("stopped", True, True, False, False)
        assert s["detect_segments"] is False

    def test_save_path_disabled_without_ref_path(self):
        from ui.track_modelling_vm import get_calibration_button_states
        s = get_calibration_button_states("stopped", True, True, False, False)
        assert s["save_path"] is False


class TestCalibrationButtonStatesReview:
    def test_confirm_enabled_with_model_and_selection(self):
        from ui.track_modelling_vm import get_calibration_button_states
        s = get_calibration_button_states("built", True, True, True, True, "seg_001")
        assert s["confirm"] is True

    def test_confirm_disabled_without_selection(self):
        from ui.track_modelling_vm import get_calibration_button_states
        s = get_calibration_button_states("built", True, True, True, True, None)
        assert s["confirm"] is False

    def test_save_review_enabled_with_model(self):
        from ui.track_modelling_vm import get_calibration_button_states
        s = get_calibration_button_states("built", True, True, True, True, None)
        assert s["save_review"] is True

    def test_save_review_disabled_without_model(self):
        from ui.track_modelling_vm import get_calibration_button_states
        s = get_calibration_button_states("built", True, True, True, False, None)
        assert s["save_review"] is False


class TestCalibrationButtonStatesOffsetActions:
    def test_create_zero_offset_enabled_with_track_and_length(self):
        from ui.track_modelling_vm import get_calibration_button_states
        s = get_calibration_button_states("inactive", True, False, False, False,
                                           None, True)
        assert s["create_zero_offset"] is True

    def test_create_zero_offset_disabled_without_track(self):
        from ui.track_modelling_vm import get_calibration_button_states
        s = get_calibration_button_states("inactive", False, False, False, False,
                                           None, True)
        assert s["create_zero_offset"] is False

    def test_create_zero_offset_disabled_without_length(self):
        from ui.track_modelling_vm import get_calibration_button_states
        s = get_calibration_button_states("inactive", True, False, False, False,
                                           None, False)
        assert s["create_zero_offset"] is False

    def test_load_offset_enabled_with_track(self):
        from ui.track_modelling_vm import get_calibration_button_states
        s = get_calibration_button_states("inactive", True, False, False, False)
        assert s["load_offset"] is True

    def test_load_offset_disabled_without_track(self):
        from ui.track_modelling_vm import get_calibration_button_states
        s = get_calibration_button_states("inactive", False, False, False, False)
        assert s["load_offset"] is False


# ---------------------------------------------------------------------------
# 3. format_calibration_status_extended
# ---------------------------------------------------------------------------

class TestFormatCalibrationStatusExtended:
    def _make_summary(self, **overrides) -> dict:
        base = {
            "state": "inactive", "current_lap_number": None,
            "total_samples": 0, "in_progress_samples": 0,
            "lap_count": 0, "usable_laps": 0, "rejected_laps": 0,
            "low_confidence_laps": 0, "reference_path_points": 0,
            "confidence": 0.0, "saved_path": "", "error": "",
        }
        base.update(overrides)
        return base

    def test_inactive_state_text(self):
        from ui.track_modelling_vm import format_calibration_status_extended
        result = format_calibration_status_extended(self._make_summary())
        assert "No calibration" in result["state_text"]

    def test_recording_state_text(self):
        from ui.track_modelling_vm import format_calibration_status_extended
        s = self._make_summary(state="recording", current_lap_number=3,
                                total_samples=1200, in_progress_samples=80,
                                lap_count=2)
        result = format_calibration_status_extended(s)
        assert "Recording" in result["state_text"]
        assert "3" in result["state_text"]
        assert result["recording_indicator"] == "● RECORDING"

    def test_stopped_state_text(self):
        from ui.track_modelling_vm import format_calibration_status_extended
        s = self._make_summary(state="stopped", lap_count=4,
                                usable_laps=3, rejected_laps=1)
        result = format_calibration_status_extended(s)
        assert "Stopped" in result["state_text"]
        assert "4" in result["state_text"]

    def test_built_state_text(self):
        from ui.track_modelling_vm import format_calibration_status_extended
        s = self._make_summary(state="built", reference_path_points=200,
                                confidence=0.91)
        result = format_calibration_status_extended(s)
        assert "built" in result["state_text"].lower()
        assert "200" in result["path_info"]
        assert "0.91" in result["path_info"]

    def test_no_packet_age_returns_no_packets_when_inactive(self):
        from ui.track_modelling_vm import format_calibration_status_extended
        result = format_calibration_status_extended(self._make_summary())
        assert "No packets" in result["packet_age"]

    def test_packet_age_under_1s_shown_as_ms(self):
        from ui.track_modelling_vm import format_calibration_status_extended
        s = self._make_summary(state="recording")
        result = format_calibration_status_extended(s, last_packet_age_s=0.35)
        assert "ms" in result["packet_age"]

    def test_packet_age_over_10s_warns(self):
        from ui.track_modelling_vm import format_calibration_status_extended
        result = format_calibration_status_extended(self._make_summary(), last_packet_age_s=25.0)
        assert "check" in result["packet_age"].lower() or "25" in result["packet_age"]

    def test_sample_count_formatted_with_commas(self):
        from ui.track_modelling_vm import format_calibration_status_extended
        s = self._make_summary(state="stopped", total_samples=12345)
        result = format_calibration_status_extended(s)
        assert "12,345" in result["sample_count"]

    def test_zero_samples_returns_no_samples(self):
        from ui.track_modelling_vm import format_calibration_status_extended
        result = format_calibration_status_extended(self._make_summary())
        assert "No samples" in result["sample_count"]

    def test_no_recording_indicator_when_stopped(self):
        from ui.track_modelling_vm import format_calibration_status_extended
        s = self._make_summary(state="stopped")
        result = format_calibration_status_extended(s)
        assert result["recording_indicator"] == ""

    def test_saved_path_propagated(self):
        from ui.track_modelling_vm import format_calibration_status_extended
        s = self._make_summary(saved_path="/some/path/to/file.json")
        result = format_calibration_status_extended(s)
        assert result["saved_path"] == "/some/path/to/file.json"


# ---------------------------------------------------------------------------
# 4. format_lap_offset_status
# ---------------------------------------------------------------------------

class TestFormatLapOffsetStatus:
    def test_no_calibration_returns_none_status(self):
        from ui.track_modelling_vm import format_lap_offset_status
        result = format_lap_offset_status(None, None)
        assert result["status"] == "No offset calibration"

    def test_no_calibration_offset_is_dash(self):
        from ui.track_modelling_vm import format_lap_offset_status
        result = format_lap_offset_status(None, None)
        assert result["offset_m"] == "—"

    def test_no_track_length_shows_warning_in_track_length(self):
        from ui.track_modelling_vm import format_lap_offset_status
        result = format_lap_offset_status(None, None)
        assert "Unknown" in result["track_length"] or "check" in result["track_length"].lower()

    def test_track_length_shown_when_provided(self):
        from ui.track_modelling_vm import format_lap_offset_status
        result = format_lap_offset_status(None, 5807.0)
        assert "5807" in result["track_length"]

    def test_zero_offset_calibration_shows_provisional_status(self):
        from ui.track_modelling_vm import format_lap_offset_status
        cal = _Calibration(calibration_source="zero_offset", offset_m=0.0,
                            confidence=_Enum("low"), track_length_m=5807.0)
        result = format_lap_offset_status(cal)
        assert "provisional" in result["status"].lower() or "zero" in result["status"].lower()

    def test_zero_offset_has_provisional_note(self):
        from ui.track_modelling_vm import format_lap_offset_status
        cal = _Calibration(calibration_source="zero_offset", offset_m=0.0,
                            confidence=_Enum("low"), track_length_m=5807.0)
        result = format_lap_offset_status(cal)
        assert result["provisional_note"] != ""

    def test_high_confidence_non_zero_no_provisional_note(self):
        from ui.track_modelling_vm import format_lap_offset_status
        cal = _Calibration(calibration_source="reference_path", offset_m=123.4,
                            confidence=_Enum("high"), track_length_m=5807.0)
        result = format_lap_offset_status(cal)
        assert result["provisional_note"] == ""

    def test_offset_m_formatted(self):
        from ui.track_modelling_vm import format_lap_offset_status
        cal = _Calibration(calibration_source="reference_path", offset_m=456.789,
                            confidence=_Enum("medium"), track_length_m=5807.0)
        result = format_lap_offset_status(cal)
        assert "456.79" in result["offset_m"]

    def test_warnings_shown_when_present(self):
        from ui.track_modelling_vm import format_lap_offset_status
        cal = _Calibration(warnings=["Wrap detected", "Low sample count"])
        result = format_lap_offset_status(cal, 5807.0)
        assert "Wrap detected" in result["warnings"]

    def test_no_warnings_when_empty(self):
        from ui.track_modelling_vm import format_lap_offset_status
        cal = _Calibration(warnings=[])
        result = format_lap_offset_status(cal, 5807.0)
        assert result["warnings"] == ""


# ---------------------------------------------------------------------------
# 5. format_live_resolver_status_summary
# ---------------------------------------------------------------------------

class TestFormatLiveResolverStatusSummary:
    def test_no_track_returns_safe_string(self):
        from ui.track_modelling_vm import format_live_resolver_status_summary
        result = format_live_resolver_status_summary("", "")
        assert "not selected" in result.lower()

    def test_no_track_does_not_crash(self):
        from ui.track_modelling_vm import format_live_resolver_status_summary
        result = format_live_resolver_status_summary("", "", None, None, None, None)
        assert isinstance(result, str)

    def test_track_shown_in_output(self):
        from ui.track_modelling_vm import format_live_resolver_status_summary
        result = format_live_resolver_status_summary("suzuka", "full")
        assert "suzuka" in result
        assert "full" in result

    def test_no_resolver_shows_not_checked(self):
        from ui.track_modelling_vm import format_live_resolver_status_summary
        result = format_live_resolver_status_summary("suzuka", "full", None)
        assert "not checked" in result

    def test_resolver_with_model_shows_source(self):
        from ui.track_modelling_vm import format_live_resolver_status_summary
        rr = _ResolverResult(
            resolved_model=_ResolvedModel(source_type=_Enum("reviewed_model"), ai_ready=True)
        )
        result = format_live_resolver_status_summary("suzuka", "full", rr)
        assert "reviewed_model" in result
        assert "Yes" in result

    def test_no_offset_calibration_shown(self):
        from ui.track_modelling_vm import format_live_resolver_status_summary
        result = format_live_resolver_status_summary("suzuka", "full", None, None)
        assert "none" in result.lower() or "unavailable" in result.lower()

    def test_offset_calibration_shows_offset_value(self):
        from ui.track_modelling_vm import format_live_resolver_status_summary
        cal = _Calibration(offset_m=123.4, confidence=_Enum("medium"))
        result = format_live_resolver_status_summary("suzuka", "full", None, cal)
        assert "123.4" in result

    def test_no_live_position_shown(self):
        from ui.track_modelling_vm import format_live_resolver_status_summary
        result = format_live_resolver_status_summary("suzuka", "full", None, None, None)
        assert "no data" in result.lower()

    def test_road_distance_shown_in_position(self):
        from ui.track_modelling_vm import format_live_resolver_status_summary
        pos = _LivePosition(road_distance_m=2345.6, speed_kph=142.0)
        result = format_live_resolver_status_summary("suzuka", "full", None, None, pos)
        assert "2345.6" in result

    def test_no_live_segment_shows_unresolved(self):
        from ui.track_modelling_vm import format_live_resolver_status_summary
        result = format_live_resolver_status_summary("suzuka", "full")
        assert "unresolved" in result.lower() or "not resolved" in result.lower()

    def test_matched_segment_shows_name(self):
        from ui.track_modelling_vm import format_live_resolver_status_summary
        seg = _LiveSegResult(match=_SegmentMatch(display_name="T1 Braking Zone"),
                              resolution_status=_Enum("matched"))
        result = format_live_resolver_status_summary("suzuka", "full", None, None, None, seg)
        assert "T1 Braking Zone" in result

    def test_with_no_reviewed_model_resolver_none(self):
        from ui.track_modelling_vm import format_live_resolver_status_summary
        rr = _ResolverResult(resolved_model=None)
        result = format_live_resolver_status_summary("suzuka", "full", rr)
        assert "no model" in result.lower()


# ---------------------------------------------------------------------------
# 6. RuntimeCheckResult
# ---------------------------------------------------------------------------

class TestRuntimeCheckResult:
    def test_summary_text_no_track(self):
        from data.track_modelling_runtime_check import RuntimeCheckResult
        r = RuntimeCheckResult(has_track=False)
        text = r.summary_text()
        assert "not selected" in text.lower()

    def test_summary_text_with_track(self):
        from data.track_modelling_runtime_check import RuntimeCheckResult
        r = RuntimeCheckResult(loc_id="suzuka", lay_id="full", has_track=True,
                                resolver_source="reviewed_model", resolver_ai_ready=True,
                                offset_status="provisional", offset_m=0.0,
                                has_road_distance=True, live_segment_id="T1",
                                live_segment_name="T1 Braking", live_resolution_status="matched")
        text = r.summary_text()
        assert "suzuka" in text
        assert "reviewed_model" in text
        assert "Yes" in text
        assert "T1 Braking" in text
        assert "matched" in text

    def test_summary_text_with_warnings(self):
        from data.track_modelling_runtime_check import RuntimeCheckResult
        r = RuntimeCheckResult(has_track=True, loc_id="a", lay_id="b",
                                warnings=["Wrap detected"])
        text = r.summary_text()
        assert "Wrap detected" in text

    def test_summary_text_with_errors(self):
        from data.track_modelling_runtime_check import RuntimeCheckResult
        r = RuntimeCheckResult(has_track=True, loc_id="a", lay_id="b",
                                errors=["Resolver exploded"])
        text = r.summary_text()
        assert "Resolver exploded" in text

    def test_offset_m_shown_in_summary(self):
        from data.track_modelling_runtime_check import RuntimeCheckResult
        r = RuntimeCheckResult(has_track=True, loc_id="a", lay_id="b",
                                offset_status="provisional", offset_m=123.4)
        text = r.summary_text()
        assert "123.4" in text


# ---------------------------------------------------------------------------
# 7. run_track_modelling_runtime_check
# ---------------------------------------------------------------------------

class TestRunTrackModellingRuntimeCheck:
    def test_no_track_has_track_false(self):
        from data.track_modelling_runtime_check import run_track_modelling_runtime_check
        r = run_track_modelling_runtime_check("", "")
        assert r.has_track is False

    def test_with_track_has_track_true(self):
        from data.track_modelling_runtime_check import run_track_modelling_runtime_check
        r = run_track_modelling_runtime_check("suzuka", "full")
        assert r.has_track is True

    def test_loc_id_and_lay_id_stored(self):
        from data.track_modelling_runtime_check import run_track_modelling_runtime_check
        r = run_track_modelling_runtime_check("suzuka", "full")
        assert r.loc_id == "suzuka"
        assert r.lay_id == "full"

    def test_no_resolver_leaves_source_empty(self):
        from data.track_modelling_runtime_check import run_track_modelling_runtime_check
        r = run_track_modelling_runtime_check("a", "b")
        assert r.resolver_source == ""

    def test_resolver_with_model_extracts_source(self):
        from data.track_modelling_runtime_check import run_track_modelling_runtime_check
        rr = _ResolverResult(
            resolved_model=_ResolvedModel(source_type=_Enum("ai_ready_reviewed_model"),
                                           ai_ready=True)
        )
        r = run_track_modelling_runtime_check("a", "b", resolver_result=rr)
        assert r.resolver_source == "ai_ready_reviewed_model"
        assert r.resolver_ai_ready is True

    def test_resolver_with_no_model_marks_missing(self):
        from data.track_modelling_runtime_check import run_track_modelling_runtime_check
        rr = _ResolverResult(resolved_model=None)
        r = run_track_modelling_runtime_check("a", "b", resolver_result=rr)
        assert r.resolver_source == "missing"

    def test_zero_offset_calibration_is_provisional(self):
        from data.track_modelling_runtime_check import run_track_modelling_runtime_check
        cal = _Calibration(calibration_source="zero_offset", offset_m=0.0,
                            confidence=_Enum("low"), track_length_m=5807.0)
        r = run_track_modelling_runtime_check("a", "b", offset_calibration=cal)
        assert r.offset_status == "provisional"
        assert r.offset_m == 0.0

    def test_high_confidence_non_zero_offset_is_validated(self):
        from data.track_modelling_runtime_check import run_track_modelling_runtime_check
        cal = _Calibration(calibration_source="reference_path", offset_m=123.4,
                            confidence=_Enum("high"), track_length_m=5807.0)
        r = run_track_modelling_runtime_check("a", "b", offset_calibration=cal)
        assert r.offset_status == "validated"

    def test_no_offset_calibration_is_none(self):
        from data.track_modelling_runtime_check import run_track_modelling_runtime_check
        r = run_track_modelling_runtime_check("a", "b")
        assert r.offset_status == "none"

    def test_live_position_with_road_distance(self):
        from data.track_modelling_runtime_check import run_track_modelling_runtime_check
        pos = _LivePosition(road_distance_m=1234.5)
        r = run_track_modelling_runtime_check("a", "b", live_position=pos)
        assert r.has_road_distance is True

    def test_live_position_without_road_distance(self):
        from data.track_modelling_runtime_check import run_track_modelling_runtime_check
        pos = _LivePosition(road_distance_m=None)
        r = run_track_modelling_runtime_check("a", "b", live_position=pos)
        assert r.has_road_distance is False

    def test_no_live_position_road_distance_false(self):
        from data.track_modelling_runtime_check import run_track_modelling_runtime_check
        r = run_track_modelling_runtime_check("a", "b", live_position=None)
        assert r.has_road_distance is False

    def test_live_segment_matched_extracts_ids(self):
        from data.track_modelling_runtime_check import run_track_modelling_runtime_check
        seg = _LiveSegResult(
            match=_SegmentMatch(segment_id="T1_braking", display_name="T1 Braking"),
            resolution_status=_Enum("matched")
        )
        r = run_track_modelling_runtime_check("a", "b", live_segment_result=seg)
        assert r.live_segment_id == "T1_braking"
        assert r.live_segment_name == "T1 Braking"
        assert r.live_resolution_status == "matched"

    def test_live_segment_unresolved_no_match(self):
        from data.track_modelling_runtime_check import run_track_modelling_runtime_check
        seg = _LiveSegResult(match=None, resolution_status=_Enum("no_reviewed_model"))
        r = run_track_modelling_runtime_check("a", "b", live_segment_result=seg)
        assert r.live_segment_id is None
        assert r.live_resolution_status == "no_reviewed_model"

    def test_never_raises_on_none_inputs(self):
        from data.track_modelling_runtime_check import run_track_modelling_runtime_check
        r = run_track_modelling_runtime_check()
        assert r is not None

    def test_never_raises_on_bad_object(self):
        from data.track_modelling_runtime_check import run_track_modelling_runtime_check

        class _Bad:
            @property
            def resolved_model(self):
                raise RuntimeError("boom")

        r = run_track_modelling_runtime_check("a", "b", resolver_result=_Bad())
        assert r is not None
        assert len(r.errors) >= 1


# ---------------------------------------------------------------------------
# 8. Zero-offset calibration integration
# ---------------------------------------------------------------------------

class TestZeroOffsetCalibrationCreation:
    def test_create_offset_zero_with_valid_length(self):
        from data.lap_distance_mapper import create_offset_zero
        cal = create_offset_zero("suzuka", "full", 5807.0)
        assert cal is not None
        assert cal.offset_m == 0.0
        assert cal.track_length_m == 5807.0
        assert cal.calibration_source == "zero_offset"

    def test_create_offset_zero_sets_track_ids(self):
        from data.lap_distance_mapper import create_offset_zero
        cal = create_offset_zero("spa", "long", 7004.0)
        assert cal.track_location_id == "spa"
        assert cal.layout_id == "long"

    def test_create_offset_zero_confidence_is_low_or_unknown(self):
        from data.lap_distance_mapper import create_offset_zero, LapDistanceMappingConfidence
        cal = create_offset_zero("suzuka", "full", 5807.0)
        assert cal.confidence in (
            LapDistanceMappingConfidence.LOW,
            LapDistanceMappingConfidence.UNKNOWN,
        )

    def test_create_offset_zero_fails_on_zero_length(self):
        from data.lap_distance_mapper import create_offset_zero
        with pytest.raises(Exception):
            create_offset_zero("suzuka", "full", 0.0)

    def test_create_offset_zero_fails_on_negative_length(self):
        from data.lap_distance_mapper import create_offset_zero
        with pytest.raises(Exception):
            create_offset_zero("suzuka", "full", -100.0)


# ---------------------------------------------------------------------------
# 9. Regression — 17A-17L imports still work
# ---------------------------------------------------------------------------

class TestRegressionImports:
    def test_lap_distance_mapper_imports(self):
        from data.lap_distance_mapper import (
            normalise_distance, calculate_lap_start_offset,
            map_road_distance_to_lap_distance, map_road_distance_to_lap_progress,
            create_offset_zero, create_offset_from_reference_path,
            load_offset_calibration_for_track,
            LapStartOffsetCalibration, LapDistanceMappingStatus,
            LapDistanceMappingConfidence,
        )

    def test_live_segment_resolver_imports(self):
        from data.live_segment_resolver import (
            LivePosition, resolve_live_segment, packet_to_live_position,
            enrich_position_with_road_distance,
        )
        assert hasattr(LivePosition, "road_distance_m")

    def test_live_segment_coaching_imports(self):
        from data.live_segment_coaching import (
            build_live_coaching_decision, LiveCoachingCueType,
            LiveCoachingConfig, LiveCoachingDecision,
        )

    def test_track_modelling_runtime_check_imports(self):
        from data.track_modelling_runtime_check import (
            RuntimeCheckResult, run_track_modelling_runtime_check,
        )

    def test_track_modelling_vm_new_functions(self):
        from ui.track_modelling_vm import (
            get_workflow_error_message,
            get_calibration_button_states,
            format_calibration_status_extended,
            format_lap_offset_status,
            format_live_resolver_status_summary,
        )

    def test_existing_vm_functions_unchanged(self):
        from ui.track_modelling_vm import (
            format_layout_facts, format_readiness, format_calibration_car,
            get_seed_warning_text, is_seed_only, describe_seed_load_status,
            format_segment_row, format_review_summary, format_resolver_summary,
            get_review_button_states,
        )
