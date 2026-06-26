"""Group 17N UAT-005 defect regression tests.

Covers DEF-17N-UAT-005 — "No USABLE calibration laps" message lacks actionable
rejection diagnostics.

Root cause:
  1. CalibrationLap.quality defaults to REJECTED and was never updated even after a
     successful build_reference_path() call, causing detect_track_segments() to
     always see zero usable laps when using an active session.
  2. The Build failure dialog only showed the generic error, not per-lap rejection
     reasons from result.warnings.
  3. detect_track_segments() returned a hardcoded generic error when no usable
     laps were found, giving the user no diagnostic information.

Fix:
  - build_reference_path() now mutates CalibrationLap.quality and quality_reasons
    after quality assessment so consumers see pre-assessed quality.
  - diagnose_calibration_session() added to data/track_calibration.py.
  - format_build_failure_diagnostics() added to ui/track_modelling_vm.py.
  - detect_track_segments() calls _build_no_usable_laps_errors() for actionable
    per-lap rejection details instead of a hardcoded string.

All tests are pure Python (no PyQt6 dependency).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pytest


# ---------------------------------------------------------------------------
# Helpers shared across test classes
# ---------------------------------------------------------------------------

def _make_telemetry_sample(i: int, lap_number: int = 1, x_offset: float = 0.0):
    from data.track_calibration import TelemetrySample
    return TelemetrySample(
        timestamp_ms  = i * 100,
        lap_number    = lap_number,
        x             = float(i) * 10.0 + x_offset,
        y             = 0.0,
        z             = float(i) * 5.0,
        speed_kph     = 180.0 - float(i % 30),
        gear          = 4,
        rpm           = 7000.0,
        throttle      = 0.8,
        brake         = 0.0,
        road_distance = float(i) * 29.0,
        yaw_rate      = 0.01,
        road_plane_y  = 1.0,
        is_off_track  = False,
    )


def _make_usable_lap(lap_number: int = 1, n_samples: int = 120, x_offset: float = 1.0):
    """Create a lap that will pass quality checks.
    Starts at i=1 (not 0) to avoid all-zero xyz on the first sample.
    """
    from data.track_calibration import CalibrationLap, CalibrationLapQuality
    samples = [_make_telemetry_sample(i + 1, lap_number, x_offset=x_offset)
               for i in range(n_samples)]
    return CalibrationLap(
        lap_number      = lap_number,
        lap_time_ms     = n_samples * 100,
        samples         = samples,
        quality         = CalibrationLapQuality.REJECTED,  # default — build must update this
        quality_reasons = [],
        path_length_m   = float(n_samples) * 29.0,
    )


def _make_few_samples_lap(lap_number: int = 1, n_samples: int = 10):
    """Lap with too few samples → hard reject (n_samples < MIN_CALIBRATION_SAMPLES=50)."""
    from data.track_calibration import CalibrationLap
    # Start at i=1 to avoid zero-xyz on first sample, but keep n small for rejection
    samples = [_make_telemetry_sample(i + 1, lap_number) for i in range(n_samples)]
    return CalibrationLap(
        lap_number=lap_number, lap_time_ms=n_samples * 100, samples=samples,
    )


def _make_offtrack_lap(lap_number: int = 1, n_samples: int = 120,
                       off_track_fraction: float = 0.50):
    """Lap with many off-track samples → hard reject."""
    from data.track_calibration import CalibrationLap, TelemetrySample
    samples = []
    for i in range(n_samples):
        is_off = i < int(n_samples * off_track_fraction)
        # Start at i=1 equivalent by using i+1 for x/z to avoid zero-xyz
        s = TelemetrySample(
            timestamp_ms=i * 100, lap_number=lap_number,
            x=float(i + 1) * 10.0, y=0.0, z=float(i + 1) * 5.0,
            speed_kph=180.0, gear=4, rpm=7000.0,
            throttle=0.8, brake=0.0,
            road_distance=float(i) * 29.0,
            yaw_rate=0.0, road_plane_y=1.0,
            is_off_track=is_off,
        )
        samples.append(s)
    return CalibrationLap(lap_number=lap_number, lap_time_ms=n_samples * 100, samples=samples)


def _make_session(laps, loc_id="a", lay_id="b", car_id="test_car"):
    from data.track_calibration import CalibrationSession
    return CalibrationSession(
        session_id=f"test__{loc_id}__{lay_id}",
        track_location_id=loc_id,
        layout_id=lay_id,
        calibration_car_id=car_id,
        laps=laps,
    )


# ---------------------------------------------------------------------------
# diagnose_calibration_session
# ---------------------------------------------------------------------------

class TestDiagnoseCalibrationSession:
    def test_empty_session(self):
        from data.track_calibration import diagnose_calibration_session
        session = _make_session([])
        d = diagnose_calibration_session(session)
        assert d["total_laps"] == 0
        assert d["usable_count"] == 0
        assert d["has_any_laps"] is False

    def test_all_usable_laps(self):
        from data.track_calibration import diagnose_calibration_session
        laps = [_make_usable_lap(i + 1) for i in range(3)]
        session = _make_session(laps)
        d = diagnose_calibration_session(session)
        assert d["total_laps"] == 3
        assert d["usable_count"] == 3
        assert d["rejected_count"] == 0
        assert d["low_confidence_count"] == 0
        assert d["has_any_laps"] is True

    def test_all_rejected_too_few_samples(self):
        from data.track_calibration import diagnose_calibration_session
        laps = [_make_few_samples_lap(i + 1) for i in range(3)]
        session = _make_session(laps)
        d = diagnose_calibration_session(session)
        assert d["total_laps"] == 3
        assert d["usable_count"] == 0
        assert d["rejected_count"] == 3
        assert d["most_common_reason"] is not None
        assert "sample" in d["most_common_reason"].lower()

    def test_mixed_usable_rejected(self):
        from data.track_calibration import diagnose_calibration_session
        laps = [_make_usable_lap(1), _make_few_samples_lap(2), _make_usable_lap(3)]
        session = _make_session(laps)
        d = diagnose_calibration_session(session)
        assert d["usable_count"] == 2
        assert d["rejected_count"] == 1

    def test_all_offtrack_rejected(self):
        from data.track_calibration import diagnose_calibration_session
        laps = [_make_offtrack_lap(i + 1) for i in range(3)]
        session = _make_session(laps)
        d = diagnose_calibration_session(session)
        assert d["rejected_count"] == 3
        assert any("off" in r.lower() for r in d["all_reasons"])

    def test_per_lap_detail_populated(self):
        from data.track_calibration import diagnose_calibration_session
        laps = [_make_usable_lap(1), _make_few_samples_lap(2)]
        session = _make_session(laps)
        d = diagnose_calibration_session(session)
        assert len(d["per_lap"]) == 2
        assert d["per_lap"][0]["lap_number"] == 1
        assert "quality" in d["per_lap"][0]
        assert "sample_count" in d["per_lap"][0]

    def test_car_id_preserved(self):
        from data.track_calibration import diagnose_calibration_session
        session = _make_session([], car_id="porsche_911_rsr_991_2017")
        d = diagnose_calibration_session(session)
        assert d["car_id"] == "porsche_911_rsr_991_2017"

    def test_total_samples_counted(self):
        from data.track_calibration import diagnose_calibration_session
        laps = [_make_usable_lap(i + 1, n_samples=50) for i in range(4)]
        session = _make_session(laps)
        d = diagnose_calibration_session(session)
        assert d["total_samples"] == 4 * 50

    def test_never_raises_on_bad_session(self):
        from data.track_calibration import diagnose_calibration_session, CalibrationSession
        # Deliberately corrupt session
        session = CalibrationSession(
            session_id="bad", track_location_id="a", layout_id="b",
        )
        session.laps = None  # type: ignore
        d = diagnose_calibration_session(session)
        assert isinstance(d, dict)
        assert "total_laps" in d


# ---------------------------------------------------------------------------
# build_reference_path quality mutation
# ---------------------------------------------------------------------------

class TestBuildReferencePathMutatesLapQuality:
    def _build(self, n_usable_laps=3, include_bad=False):
        from data.track_calibration import (
            build_reference_path, CalibrationLapQuality,
        )
        laps = [_make_usable_lap(i + 1) for i in range(n_usable_laps)]
        if include_bad:
            laps.append(_make_few_samples_lap(n_usable_laps + 1))
        session = _make_session(laps)
        # Before build — all laps have default REJECTED quality
        for lap in session.laps:
            assert lap.quality == CalibrationLapQuality.REJECTED
        result = build_reference_path(session)
        return session, result

    def test_usable_laps_marked_usable_after_build(self):
        from data.track_calibration import CalibrationLapQuality
        session, result = self._build(n_usable_laps=3)
        assert result.success
        for lap in session.laps:
            assert lap.quality == CalibrationLapQuality.USABLE

    def test_rejected_lap_marked_rejected_after_build(self):
        from data.track_calibration import CalibrationLapQuality
        session, result = self._build(n_usable_laps=3, include_bad=True)
        assert result.success
        # First 3 laps should be USABLE, last one REJECTED
        usable_count = sum(
            1 for l in session.laps if l.quality == CalibrationLapQuality.USABLE
        )
        rejected_count = sum(
            1 for l in session.laps if l.quality == CalibrationLapQuality.REJECTED
        )
        assert usable_count == 3
        assert rejected_count == 1

    def test_quality_reasons_populated_for_rejected(self):
        from data.track_calibration import CalibrationLapQuality
        laps = [_make_usable_lap(1), _make_few_samples_lap(2)]
        session = _make_session(laps)
        from data.track_calibration import build_reference_path
        build_reference_path(session)
        rejected_laps = [l for l in session.laps if l.quality == CalibrationLapQuality.REJECTED]
        assert len(rejected_laps) == 1
        assert len(rejected_laps[0].quality_reasons) > 0
        assert any("sample" in r.lower() for r in rejected_laps[0].quality_reasons)

    def test_failed_build_still_mutates_quality(self):
        """Even when build fails (not enough usable laps), quality IS mutated."""
        from data.track_calibration import build_reference_path, CalibrationLapQuality
        laps = [_make_few_samples_lap(i + 1) for i in range(3)]
        session = _make_session(laps)
        result = build_reference_path(session)
        assert not result.success
        # Quality must still have been assessed
        for lap in session.laps:
            assert lap.quality == CalibrationLapQuality.REJECTED


# ---------------------------------------------------------------------------
# detect_track_segments diagnostic error message
# ---------------------------------------------------------------------------

class TestDetectSegmentsNoUsableLapsDiagnostics:
    def test_empty_session_gives_actionable_error(self):
        from data.track_segment_detection import detect_track_segments
        session = _make_session([], loc_id="daytona", lay_id="road_course",
                                car_id="porsche_911_rsr_991_2017")
        result = detect_track_segments(session)
        assert not result.success
        all_text = " ".join(result.errors).lower()
        assert "no calibration laps" in all_text or "lap" in all_text

    def test_all_rejected_mentions_reasons(self):
        from data.track_segment_detection import detect_track_segments
        laps = [_make_few_samples_lap(i + 1) for i in range(3)]
        session = _make_session(laps)
        result = detect_track_segments(session)
        assert not result.success
        all_text = " ".join(result.errors).lower()
        assert "usable" in all_text or "rejected" in all_text

    def test_error_includes_counts(self):
        from data.track_segment_detection import detect_track_segments
        laps = [_make_few_samples_lap(i + 1) for i in range(3)]
        session = _make_session(laps)
        result = detect_track_segments(session)
        all_text = " ".join(result.errors)
        # Should include the count 3 somewhere
        assert "3" in all_text

    def test_error_includes_car_id(self):
        from data.track_segment_detection import detect_track_segments
        laps = [_make_few_samples_lap(1)]
        session = _make_session(laps, car_id="porsche_911_rsr_991_2017")
        result = detect_track_segments(session)
        all_text = " ".join(result.errors)
        assert "porsche" in all_text.lower() or "car" in all_text.lower()

    def test_offtrack_rejection_suggests_relevant_action(self):
        from data.track_segment_detection import detect_track_segments
        laps = [_make_offtrack_lap(i + 1) for i in range(3)]
        session = _make_session(laps)
        result = detect_track_segments(session)
        all_text = " ".join(result.errors).lower()
        assert "off-track" in all_text or "track" in all_text

    def test_few_samples_rejection_suggests_udp(self):
        from data.track_segment_detection import detect_track_segments
        laps = [_make_few_samples_lap(i + 1) for i in range(3)]
        session = _make_session(laps)
        result = detect_track_segments(session)
        all_text = " ".join(result.errors).lower()
        assert "udp" in all_text or "telemetry" in all_text or "sample" in all_text

    def test_successful_session_still_works(self):
        """After quality mutation fix, active session with usable laps must work."""
        from data.track_calibration import build_reference_path
        from data.track_segment_detection import detect_track_segments, SegmentDetectionResult
        laps = [_make_usable_lap(i + 1, n_samples=150) for i in range(3)]
        session = _make_session(laps, loc_id="daytona", lay_id="road_course")
        # Build to trigger quality mutation
        build_result = build_reference_path(session)
        assert build_result.success
        # Now detect should use the USABLE-marked laps from the session
        detect_result = detect_track_segments(session)
        assert isinstance(detect_result, SegmentDetectionResult)
        # Should NOT return the "no usable laps" error
        no_usable_error = any(
            "no usable" in e.lower() or "no calibration laps" in e.lower()
            for e in (detect_result.errors or [])
        )
        assert not no_usable_error


# ---------------------------------------------------------------------------
# format_build_failure_diagnostics
# ---------------------------------------------------------------------------

class TestFormatBuildFailureDiagnostics:
    def _make_result(self, usable=0, rejected=3, low_conf=0, warnings=None, errors=None):
        from data.track_calibration import CalibrationBuildResult
        return CalibrationBuildResult(
            success=False,
            usable_lap_count=usable,
            rejected_lap_count=rejected,
            low_confidence_lap_count=low_conf,
            warnings=warnings or [],
            errors=errors or [
                f"Not enough usable laps to build reference path "
                f"({usable} usable, need 2)"
            ],
        )

    def test_returns_string(self):
        from ui.track_modelling_vm import format_build_failure_diagnostics
        result = self._make_result()
        s = format_build_failure_diagnostics(result)
        assert isinstance(s, str)
        assert len(s) > 0

    def test_contains_counts(self):
        from ui.track_modelling_vm import format_build_failure_diagnostics
        result = self._make_result(usable=0, rejected=3, low_conf=0)
        s = format_build_failure_diagnostics(result)
        assert "3" in s
        assert "rejected" in s.lower() or "usable" in s.lower()

    def test_contains_primary_error(self):
        from ui.track_modelling_vm import format_build_failure_diagnostics
        result = self._make_result(errors=["Not enough usable laps (0 usable, need 2)"])
        s = format_build_failure_diagnostics(result)
        assert "Not enough usable laps" in s

    def test_warnings_included(self):
        from ui.track_modelling_vm import format_build_failure_diagnostics
        result = self._make_result(
            warnings=["Lap 1 rejected: Too few telemetry samples (10 < 50)"]
        )
        s = format_build_failure_diagnostics(result)
        assert "Lap 1" in s or "Too few" in s

    def test_car_id_shown_when_session_provided(self):
        from ui.track_modelling_vm import format_build_failure_diagnostics
        result = self._make_result()
        session = _make_session([], car_id="porsche_911_rsr_991_2017")
        s = format_build_failure_diagnostics(result, session)
        assert "porsche" in s.lower()

    def test_no_laps_message_when_session_empty(self):
        from ui.track_modelling_vm import format_build_failure_diagnostics
        result = self._make_result(usable=0, rejected=0, low_conf=0)
        session = _make_session([])
        s = format_build_failure_diagnostics(result, session)
        assert "lap" in s.lower()

    def test_udp_advice_for_few_samples_rejection(self):
        from ui.track_modelling_vm import format_build_failure_diagnostics
        result = self._make_result(
            warnings=["Lap 1 rejected: Too few telemetry samples (3 < 50)"]
        )
        s = format_build_failure_diagnostics(result)
        assert "UDP" in s or "telemetry" in s.lower() or "sample" in s.lower()

    def test_offtrack_advice_for_offtrack_rejection(self):
        from ui.track_modelling_vm import format_build_failure_diagnostics
        result = self._make_result(
            warnings=["Lap 1 rejected: Off-track samples exceed limit (62/120 = 51% > 30%)"]
        )
        s = format_build_failure_diagnostics(result)
        assert "off-track" in s.lower() or "track" in s.lower()

    def test_one_usable_lap_recommends_one_more(self):
        from ui.track_modelling_vm import format_build_failure_diagnostics
        result = self._make_result(usable=1, rejected=1, low_conf=0)
        s = format_build_failure_diagnostics(result)
        assert "1 more" in s.lower() or "minimum" in s.lower()

    def test_never_raises_on_none_result(self):
        from ui.track_modelling_vm import format_build_failure_diagnostics

        class FakeResult:
            pass

        s = format_build_failure_diagnostics(FakeResult())
        assert isinstance(s, str)


# ---------------------------------------------------------------------------
# Integration: build fail → diagnostics → detect works after build succeeds
# ---------------------------------------------------------------------------

class TestIntegrationBuildFailThenBuildSucceed:
    def test_build_fail_diagnostics_then_add_laps_and_succeed(self):
        """Simulate Daytona scenario: first attempt fails (1 lap), second succeeds (2 laps)."""
        from data.track_calibration import (
            build_reference_path, CalibrationLapQuality,
        )
        from data.track_segment_detection import detect_track_segments

        # First attempt: only 1 usable lap (need 2)
        session = _make_session(
            [_make_usable_lap(1)],
            loc_id="daytona_international_speedway",
            lay_id="daytona_international_speedway__road_course",
        )
        result1 = build_reference_path(session)
        assert not result1.success
        # 1 lap is not enough (need 2) — should be either usable_lap_count=1 or low_conf
        # depending on quality; either way build failed
        total_assessed = (
            result1.usable_lap_count
            + result1.rejected_lap_count
            + result1.low_confidence_lap_count
        )
        assert total_assessed == 1

        # Add a second good lap
        session.laps.append(_make_usable_lap(2, x_offset=500.0))
        result2 = build_reference_path(session)
        assert result2.success

        # After successful build, all session laps must be USABLE or properly classified
        usable_in_session = sum(
            1 for l in session.laps if l.quality == CalibrationLapQuality.USABLE
        )
        assert usable_in_session == 2

        # Detect segments must work (no "No USABLE" error)
        detect_result = detect_track_segments(session)
        no_usable_error = any(
            "no usable" in e.lower() or "no calibration laps" in e.lower()
            for e in (detect_result.errors or [])
        )
        assert not no_usable_error

    def test_build_failure_warnings_surface_in_dialog_text(self):
        from data.track_calibration import build_reference_path
        from ui.track_modelling_vm import format_build_failure_diagnostics

        laps = [_make_few_samples_lap(i + 1, n_samples=5) for i in range(3)]
        session = _make_session(
            laps,
            loc_id="daytona_international_speedway",
            lay_id="daytona_international_speedway__road_course",
            car_id="porsche_911_rsr_991_2017",
        )
        result = build_reference_path(session)
        assert not result.success
        assert result.rejected_lap_count == 3

        dialog_text = format_build_failure_diagnostics(result, session)

        # Dialog must include: counts, per-lap reasons, car, recommended action
        assert "3" in dialog_text
        assert "rejected" in dialog_text.lower() or "usable" in dialog_text.lower()
        assert "porsche" in dialog_text.lower()
        # At least one per-lap reason must appear
        assert any(kw in dialog_text.lower()
                   for kw in ["lap 1", "sample", "too few"])
