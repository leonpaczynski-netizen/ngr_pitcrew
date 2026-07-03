"""DEF-17U-UAT-007 acceptance tests — data / build layer.

Regression tests for the partial-lap detection fix in data/track_calibration.py
and the pit-detection opt-in gate introduced in build_reference_path().

Coverage:
  AC1  — UAT regression: 7-lap session (short-start + 5 full + short-stop) builds OK
  AC2  — detect_pit_lap_raw NOT called when pit_detection_enabled=False (default)
  AC2b — detect_pit_lap_raw IS called and excludes laps when pit_detection_enabled=True
  AC3  — First short boundary lap gets PARTIAL_START with reason "partial start lap"
  AC4  — Last short boundary lap gets PARTIAL_STOP with reason "partial stop lap"
  AC5  — Session median computed from complete laps; full laps remain USABLE
  AC6  — Build succeeds with exactly 2 complete laps even when partials exist
  AC7  — Each partial lap carries exactly ONE quality_reason entry
  AC8  — 0 usable laps + pit detection off → no "pit-in" in warnings/errors; result.pit_detection_enabled==False
  AC9  — diagnose_calibration_session surfaces partial_start_count/partial_stop_count, per-lap quality strings
  AC10 — Backward-compat: session round-tripped through to_dict/from_dict (if available) builds without error
  EXTRA — ≤2-lap guard: 2-lap session is NOT classified as partial

All tests are pure Python — no PyQt6 import required.
"""
from __future__ import annotations

import math
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from data.track_calibration import (
    MIN_CALIBRATION_SAMPLES,
    MIN_USABLE_LAPS_FOR_PATH,
    CalibrationLap,
    CalibrationLapQuality,
    CalibrationSession,
    TelemetrySample,
    assess_session_laps,
    build_reference_path,
    diagnose_calibration_session,
    export_reference_path_json,
    import_reference_path_json,
)


# ---------------------------------------------------------------------------
# Shared factories (mirror style from test_group17c_track_calibration.py)
# ---------------------------------------------------------------------------

def _sample(
    lap: int = 1,
    t: int = 0,
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.0,
    speed: float = 100.0,
    gear: int = 4,
    rpm: float = 7000.0,
    throttle: float = 0.7,
    brake: float = 0.0,
    road_plane_y: float = 1.0,
) -> TelemetrySample:
    return TelemetrySample(
        timestamp_ms=t,
        lap_number=lap,
        x=x,
        y=y,
        z=z,
        speed_kph=speed,
        gear=gear,
        rpm=rpm,
        throttle=throttle,
        brake=brake,
        road_plane_y=road_plane_y,
    )


def _circular_samples(
    n: int,
    lap: int = 1,
    radius: float = 500.0,
    speed: float = 150.0,
    cx: float = 0.0,
    cz: float = 0.0,
) -> list[TelemetrySample]:
    """n samples distributed around a circle — closed approximate lap."""
    samples = []
    for i in range(n):
        angle = 2 * math.pi * i / n
        x = cx + radius * math.cos(angle)
        z = cz + radius * math.sin(angle)
        samples.append(_sample(lap=lap, t=i * 100, x=x, y=0.0, z=z, speed=speed))
    return samples


def _make_lap(
    lap_num: int,
    samples: list[TelemetrySample],
    lap_time_ms: int = 90_000,
) -> CalibrationLap:
    return CalibrationLap(
        lap_number=lap_num,
        lap_time_ms=lap_time_ms,
        samples=samples,
    )


def _make_full_lap(lap_num: int, n_samples: int = 200, lap_time_ms: int = 128_000) -> CalibrationLap:
    """A full-quality lap traced on a ~6171 m circle (radius ~982 m)."""
    return _make_lap(
        lap_num,
        _circular_samples(n_samples, lap=lap_num, radius=982.0),
        lap_time_ms=lap_time_ms,
    )


def _make_short_partial_lap(lap_num: int, n_samples: int = 60, lap_time_ms: int = 20_000) -> CalibrationLap:
    """A short lap covering ~20% of the full circuit (radius still 982 m but n_samples tiny).

    Path length is << 50% of the full_circuit_path (the partial threshold), so it
    will be classified as partial when it is the first or last lap and the
    session has > 2 laps.
    """
    # Use only a fraction of the arc (first 20% of a circle)
    samples = []
    n = n_samples
    radius = 982.0
    for i in range(n):
        # Traverse only 20% of the full circle so path is ~0.2 * circumference
        angle = 2 * math.pi * 0.20 * i / n
        x = radius * math.cos(angle)
        z = radius * math.sin(angle)
        samples.append(_sample(lap=lap_num, t=i * 100, x=x, y=0.0, z=z))
    return _make_lap(lap_num, samples, lap_time_ms=lap_time_ms)


def _make_uat_session() -> CalibrationSession:
    """7-lap session: 1 partial start + 5 full laps + 1 partial stop.

    Mirrors the exact UAT scenario from DEF-17U-UAT-007.
    """
    laps = [
        _make_short_partial_lap(lap_num=1),           # partial start
        _make_full_lap(lap_num=2),
        _make_full_lap(lap_num=3),
        _make_full_lap(lap_num=4),
        _make_full_lap(lap_num=5),
        _make_full_lap(lap_num=6),
        _make_short_partial_lap(lap_num=7),           # partial stop
    ]
    return CalibrationSession(
        session_id="uat_def17u_007",
        track_location_id="fuji_international_speedway",
        layout_id="fuji_international_speedway__full_course",
        laps=laps,
    )


# ---------------------------------------------------------------------------
# AC1 — UAT regression: 7-lap session builds successfully with >= 5 usable laps
# ---------------------------------------------------------------------------

class TestAC1UatRegression:
    def test_ac1_seven_lap_session_builds_successfully(self):
        """AC1: Time Trial session (short start + 5 full + short stop) builds a reference path.

        usable_lap_count must be 5 (the 5 complete laps) and success must be True.
        The partial boundary laps must NOT be counted as usable and NOT cause failure.
        """
        session = _make_uat_session()
        result = build_reference_path(session)

        assert result.success is True, (
            f"Expected successful build. Errors: {result.errors}. Warnings: {result.warnings}"
        )
        assert result.reference_path is not None
        assert result.usable_lap_count == 5, (
            f"Expected 5 usable laps (the 5 full laps); got {result.usable_lap_count}"
        )


# ---------------------------------------------------------------------------
# AC2 — detect_pit_lap_raw NOT called when pit_detection_enabled defaults to False
# ---------------------------------------------------------------------------

class TestAC2PitDetectionDefaultOff:
    def test_ac2_detect_pit_lap_raw_not_called_by_default(self):
        """AC2: With pit_detection_enabled=False (default), detect_pit_lap_raw is never called.

        Patching detect_pit_lap_raw to raise ensures any accidental call would fail the test.
        """
        session = _make_uat_session()

        def _must_not_be_called(*args, **kwargs):
            raise AssertionError(
                "detect_pit_lap_raw was called despite pit_detection_enabled=False"
            )

        with patch("data.track_calibration.detect_pit_lap_raw", side_effect=_must_not_be_called):
            result = build_reference_path(session)

        assert result.success is True
        assert result.pit_detection_enabled is False

    def test_ac2_is_pit_lap_stays_false_when_detection_off(self):
        """AC2: All lap.is_pit_lap flags remain False when pit detection is off."""
        session = _make_uat_session()
        build_reference_path(session)
        for lap in session.laps:
            assert lap.is_pit_lap is False, (
                f"Lap {lap.lap_number} got is_pit_lap=True but pit detection was off"
            )


# ---------------------------------------------------------------------------
# AC2b — With pit_detection_enabled=True, pit laps ARE excluded
# ---------------------------------------------------------------------------

class TestAC2bPitDetectionOptIn:
    def test_ac2b_pit_lap_excluded_when_opt_in(self):
        """AC2b: With pit_detection_enabled=True a patched pit lap is excluded and flagged."""
        # Build a 3-lap session where lap 3 will be declared a pit lap by the mock.
        laps = [_make_full_lap(i + 1) for i in range(3)]
        session = CalibrationSession(
            session_id="opt_in_pit_test",
            track_location_id="monza",
            layout_id="monza__full_course",
            laps=laps,
        )

        call_count = [0]

        def fake_detect(samples, threshold_seconds=10.0):
            call_count[0] += 1
            return call_count[0] == 3  # only the third call (lap 3) returns True

        with patch("data.track_calibration.detect_pit_lap_raw", side_effect=fake_detect):
            result = build_reference_path(session, pit_detection_enabled=True)

        assert result.pit_detection_enabled is True
        # Lap 3 (index 2) must be flagged as pit
        assert session.laps[2].is_pit_lap is True, (
            "Pit lap was not flagged with is_pit_lap=True when pit_detection_enabled=True"
        )
        # detect_pit_lap_raw must have been called (at least once for the usable laps)
        assert call_count[0] >= 1


# ---------------------------------------------------------------------------
# AC3 — First short boundary lap is PARTIAL_START with reason "partial start lap"
# ---------------------------------------------------------------------------

class TestAC3PartialStart:
    def test_ac3_first_short_lap_classified_partial_start(self):
        """AC3: In a >2 lap session, the first short lap gets PARTIAL_START quality."""
        session = _make_uat_session()
        quality_results = assess_session_laps(session)

        first = quality_results[0]
        assert first.quality == CalibrationLapQuality.PARTIAL_START, (
            f"Expected PARTIAL_START for lap 1; got {first.quality!r}"
        )

    def test_ac3_partial_start_reason_is_exact_string(self):
        """AC3: PARTIAL_START reason must be exactly 'partial start lap' — not pit-in or outlier."""
        session = _make_uat_session()
        quality_results = assess_session_laps(session)

        first = quality_results[0]
        assert len(first.reasons) == 1, (
            f"Expected exactly 1 reason; got {first.reasons!r}"
        )
        assert first.reasons[0] == "partial start lap", (
            f"Reason must be 'partial start lap'; got {first.reasons[0]!r}"
        )

    def test_ac3_partial_start_reason_not_pit_in(self):
        """AC3: PARTIAL_START reason must not mention pit-in."""
        session = _make_uat_session()
        quality_results = assess_session_laps(session)
        assert "pit" not in quality_results[0].reasons[0].lower()

    def test_ac3_partial_start_reason_not_too_few_samples(self):
        """AC3: PARTIAL_START must not be 'too few samples' (assumes lap has >= MIN_CALIBRATION_SAMPLES)."""
        session = _make_uat_session()
        # Verify the partial start lap itself has enough samples
        assert len(session.laps[0].samples) >= MIN_CALIBRATION_SAMPLES
        quality_results = assess_session_laps(session)
        assert "Too few" not in quality_results[0].reasons[0]


# ---------------------------------------------------------------------------
# AC4 — Last short boundary lap is PARTIAL_STOP with reason "partial stop lap"
# ---------------------------------------------------------------------------

class TestAC4PartialStop:
    def test_ac4_last_short_lap_classified_partial_stop(self):
        """AC4: In a >2 lap session, the last short lap gets PARTIAL_STOP quality."""
        session = _make_uat_session()
        quality_results = assess_session_laps(session)

        last = quality_results[-1]
        assert last.quality == CalibrationLapQuality.PARTIAL_STOP, (
            f"Expected PARTIAL_STOP for lap 7; got {last.quality!r}"
        )

    def test_ac4_partial_stop_reason_is_exact_string(self):
        """AC4: PARTIAL_STOP reason must be exactly 'partial stop lap'."""
        session = _make_uat_session()
        quality_results = assess_session_laps(session)

        last = quality_results[-1]
        assert len(last.reasons) == 1, (
            f"Expected exactly 1 reason; got {last.reasons!r}"
        )
        assert last.reasons[0] == "partial stop lap", (
            f"Reason must be 'partial stop lap'; got {last.reasons[0]!r}"
        )

    def test_ac4_partial_stop_reason_not_pit_in(self):
        """AC4: PARTIAL_STOP reason must not mention pit-in."""
        session = _make_uat_session()
        quality_results = assess_session_laps(session)
        assert "pit" not in quality_results[-1].reasons[0].lower()


# ---------------------------------------------------------------------------
# AC5 — Median computed from complete laps; full laps remain USABLE despite partials
# ---------------------------------------------------------------------------

class TestAC5MedianFromCompleteLapsOnly:
    def test_ac5_full_laps_are_usable_not_outliers(self):
        """AC5: Full laps in the UAT session remain USABLE after partial exclusion from median.

        If partials were included in the median they would drag it down and the full laps
        would be flagged as path-length outliers.  With exclusion the full laps are USABLE.
        """
        session = _make_uat_session()
        quality_results = assess_session_laps(session)

        # Laps 2-6 (indices 1-5) are the full laps
        for idx in range(1, 6):
            q = quality_results[idx].quality
            assert q == CalibrationLapQuality.USABLE, (
                f"Lap {idx + 1} expected USABLE but got {q!r}. "
                f"Reasons: {quality_results[idx].reasons}"
            )

    def test_ac5_build_result_confirms_five_usable(self):
        """AC5: CalibrationBuildResult reports exactly 5 usable laps."""
        session = _make_uat_session()
        result = build_reference_path(session)
        assert result.usable_lap_count == 5


# ---------------------------------------------------------------------------
# AC6 — Build succeeds with exactly 2 complete laps even when partials exist
# ---------------------------------------------------------------------------

class TestAC6MinimumTwoLapsWithPartials:
    def test_ac6_two_full_laps_plus_partials_succeeds(self):
        """AC6: Session with 1 partial-start + 2 full + 1 partial-stop builds successfully.

        Tests the MIN_USABLE_LAPS_FOR_PATH=2 boundary with boundary partial laps present.
        """
        laps = [
            _make_short_partial_lap(lap_num=1),
            _make_full_lap(lap_num=2),
            _make_full_lap(lap_num=3),
            _make_short_partial_lap(lap_num=4),
        ]
        session = CalibrationSession(
            session_id="ac6_min_boundary",
            track_location_id="fuji_international_speedway",
            layout_id="fuji_international_speedway__full_course",
            laps=laps,
        )
        result = build_reference_path(session)
        assert result.success is True, (
            f"Expected success with 2 full laps + partials. Errors: {result.errors}"
        )
        assert result.usable_lap_count == MIN_USABLE_LAPS_FOR_PATH

    def test_ac6_partial_counts_excluded_from_usable(self):
        """AC6: Partial laps are NOT counted toward usable_lap_count in the build result."""
        session = _make_uat_session()
        result = build_reference_path(session)

        # 7 laps total: 1 partial-start + 5 full + 1 partial-stop
        # partial_start_count + partial_stop_count must NOT inflate usable_lap_count
        assert result.partial_start_count == 1
        assert result.partial_stop_count == 1
        # Usable count reflects only the 5 full laps
        assert result.usable_lap_count == 5
        # Partial laps are NOT counted in rejected_lap_count either
        assert result.rejected_lap_count == 0


# ---------------------------------------------------------------------------
# AC7 — Each partial lap carries exactly ONE quality_reason entry
# ---------------------------------------------------------------------------

class TestAC7SingleReasonPerPartialLap:
    def test_ac7_partial_start_has_exactly_one_reason(self):
        """AC7: PARTIAL_START lap has exactly one quality_reason entry."""
        session = _make_uat_session()
        build_reference_path(session)  # also writes back quality to lap objects

        first_lap = session.laps[0]
        assert first_lap.quality == CalibrationLapQuality.PARTIAL_START
        assert len(first_lap.quality_reasons) == 1, (
            f"Expected 1 quality_reason; got {first_lap.quality_reasons!r}"
        )

    def test_ac7_partial_stop_has_exactly_one_reason(self):
        """AC7: PARTIAL_STOP lap has exactly one quality_reason entry."""
        session = _make_uat_session()
        build_reference_path(session)

        last_lap = session.laps[-1]
        assert last_lap.quality == CalibrationLapQuality.PARTIAL_STOP
        assert len(last_lap.quality_reasons) == 1, (
            f"Expected 1 quality_reason; got {last_lap.quality_reasons!r}"
        )

    def test_ac7_laps_from_assess_session_laps_also_single_reason(self):
        """AC7: assess_session_laps partial results also carry exactly one reason."""
        session = _make_uat_session()
        results = assess_session_laps(session)

        # First lap = partial start
        assert len(results[0].reasons) == 1
        # Last lap = partial stop
        assert len(results[-1].reasons) == 1


# ---------------------------------------------------------------------------
# AC8 — 0 usable laps + pit detection off → no "pit-in" anywhere; pit_detection_enabled=False
# ---------------------------------------------------------------------------

class TestAC8NoPitInWhenDetectionOff:
    def _make_zero_usable_session(self) -> CalibrationSession:
        """Session with only partial start + partial stop, no complete laps."""
        laps = [
            _make_short_partial_lap(lap_num=1),
            _make_full_lap(lap_num=2),
            _make_short_partial_lap(lap_num=3),
        ]
        return CalibrationSession(
            session_id="zero_usable_off",
            track_location_id="fuji_international_speedway",
            layout_id="fuji_international_speedway__full_course",
            laps=laps,
        )

    def test_ac8_result_pit_detection_enabled_is_false_by_default(self):
        """AC8: CalibrationBuildResult.pit_detection_enabled defaults to False."""
        session = self._make_zero_usable_session()
        result = build_reference_path(session)
        assert result.pit_detection_enabled is False

    def test_ac8_no_pit_in_in_warnings(self):
        """AC8: When pit detection is off, no warning contains 'pit-in'."""
        session = self._make_zero_usable_session()
        result = build_reference_path(session)
        for w in result.warnings:
            assert "pit-in" not in w.lower(), (
                f"Found 'pit-in' in warning despite pit detection off: {w!r}"
            )

    def test_ac8_no_pit_in_in_errors(self):
        """AC8: When pit detection is off, no error contains 'pit-in'."""
        session = self._make_zero_usable_session()
        result = build_reference_path(session)
        for e in result.errors:
            assert "pit-in" not in e.lower(), (
                f"Found 'pit-in' in error despite pit detection off: {e!r}"
            )

    def test_ac8_no_drive_clean_lap_first_when_pit_detection_off(self):
        """AC8: 'Drive a clean lap first' phrase must not appear when pit detection off."""
        session = self._make_zero_usable_session()
        result = build_reference_path(session)
        all_text = " ".join(result.warnings + result.errors).lower()
        assert "drive a clean lap first" not in all_text

    def test_ac8_ui_format_no_usable_laps_no_pit_in(self):
        """AC8: format_no_usable_laps renders result without 'pit-in' when detection off."""
        from ui.track_modelling_vm import format_no_usable_laps
        session = self._make_zero_usable_session()
        result = build_reference_path(session)
        msg = format_no_usable_laps(result)
        assert "pit-in" not in msg.lower(), (
            f"Found 'pit-in' in format_no_usable_laps output: {msg!r}"
        )
        assert result.pit_detection_enabled is False

    def test_ac8_three_lap_short_full_short_counts_are_exact(self):
        """AC8 (count integrity): a 3-lap short/full/short session yields exactly
        1 usable lap and 2 partials, and fails the MIN_USABLE_LAPS_FOR_PATH check.

        Guards the interior-median partial detection against a regression that would
        let short boundary slices masquerade as complete laps (or vice versa).
        """
        session = self._make_zero_usable_session()
        result = build_reference_path(session)
        assert result.success is False
        assert result.usable_lap_count == 1, (
            f"Expected exactly 1 usable (the single full lap); got {result.usable_lap_count}"
        )
        assert result.partial_start_count == 1
        assert result.partial_stop_count == 1
        assert result.rejected_lap_count == 0


# ---------------------------------------------------------------------------
# AC9 — diagnose_calibration_session surfaces partial counts and per-lap quality strings
# ---------------------------------------------------------------------------

class TestAC9DiagnoseSession:
    def test_ac9_partial_start_count_in_diagnosis(self):
        """AC9: diagnose_calibration_session reports partial_start_count."""
        session = _make_uat_session()
        diag = diagnose_calibration_session(session)
        assert "partial_start_count" in diag, "Key 'partial_start_count' missing from diagnosis"
        assert diag["partial_start_count"] == 1, (
            f"Expected partial_start_count=1; got {diag['partial_start_count']}"
        )

    def test_ac9_partial_stop_count_in_diagnosis(self):
        """AC9: diagnose_calibration_session reports partial_stop_count."""
        session = _make_uat_session()
        diag = diagnose_calibration_session(session)
        assert "partial_stop_count" in diag
        assert diag["partial_stop_count"] == 1, (
            f"Expected partial_stop_count=1; got {diag['partial_stop_count']}"
        )

    def test_ac9_per_lap_quality_partial_start_string(self):
        """AC9: First per-lap entry quality is 'partial_start' (string value for UI)."""
        session = _make_uat_session()
        diag = diagnose_calibration_session(session)
        first_lap_entry = diag["per_lap"][0]
        assert first_lap_entry["quality"] == "partial_start", (
            f"Expected 'partial_start'; got {first_lap_entry['quality']!r}"
        )

    def test_ac9_per_lap_quality_partial_stop_string(self):
        """AC9: Last per-lap entry quality is 'partial_stop' (string value for UI)."""
        session = _make_uat_session()
        diag = diagnose_calibration_session(session)
        last_lap_entry = diag["per_lap"][-1]
        assert last_lap_entry["quality"] == "partial_stop", (
            f"Expected 'partial_stop'; got {last_lap_entry['quality']!r}"
        )

    def test_ac9_pit_detection_enabled_false_in_diagnosis(self):
        """AC9: diagnose_calibration_session always reports pit_detection_enabled=False."""
        session = _make_uat_session()
        diag = diagnose_calibration_session(session)
        assert "pit_detection_enabled" in diag
        assert diag["pit_detection_enabled"] is False

    def test_ac9_middle_laps_quality_usable_in_diagnosis(self):
        """AC9: Full middle laps are 'usable' in the per_lap list."""
        session = _make_uat_session()
        diag = diagnose_calibration_session(session)
        for entry in diag["per_lap"][1:6]:   # laps 2-6 are the 5 full laps
            assert entry["quality"] == "usable", (
                f"Lap {entry['lap_number']} expected 'usable'; got {entry['quality']!r}"
            )


# ---------------------------------------------------------------------------
# AC10 — Backward-compat: round-trip through JSON export/import then build
# ---------------------------------------------------------------------------

class TestAC10BackwardCompat:
    def test_ac10_build_after_json_roundtrip_succeeds(self):
        """AC10: A reference path exported then re-imported allows a second build without error.

        Also verifies that directly constructing a session from previously-saved
        calibration data (mimicking what a loaded/persisted session looks like)
        produces a successful build.
        """
        # Step 1: Build from the UAT session
        session = _make_uat_session()
        result = build_reference_path(session)
        assert result.success is True

        # Step 2: Export and re-import the reference path
        with tempfile.TemporaryDirectory() as td:
            json_file = export_reference_path_json(result.reference_path, output_dir=Path(td))
            loaded_path = import_reference_path_json(json_file)

        assert loaded_path.track_location_id == "fuji_international_speedway"
        assert loaded_path.source_lap_count == 5

    def test_ac10_fresh_session_from_saved_laps_builds(self):
        """AC10: A CalibrationSession constructed to resemble a reloaded persisted session builds OK.

        Partial start/stop laps included as they would be in a loaded calibration.
        """
        # Simulate what a session loaded from disk looks like: same laps, no in-memory state
        saved_laps = [
            _make_short_partial_lap(lap_num=1),
            _make_full_lap(lap_num=2),
            _make_full_lap(lap_num=3),
            _make_full_lap(lap_num=4),
            _make_short_partial_lap(lap_num=5),
        ]
        session = CalibrationSession(
            session_id="loaded_session",
            track_location_id="fuji_international_speedway",
            layout_id="fuji_international_speedway__full_course",
            laps=saved_laps,
        )
        result = build_reference_path(session)
        assert result.success is True, (
            f"Expected successful build from reloaded session. Errors: {result.errors}"
        )
        assert result.usable_lap_count == 3


# ---------------------------------------------------------------------------
# EXTRA — ≤2-lap guard: a 2-lap session is NOT classified as partial
# ---------------------------------------------------------------------------

class TestExtraTwoLapGuard:
    def test_two_lap_session_neither_lap_is_partial(self):
        """EXTRA (≤2-lap guard): With exactly 2 laps, partial classification is skipped.

        Both laps should be evaluated as normal laps (USABLE for full laps).
        """
        laps = [
            _make_full_lap(lap_num=1),
            _make_full_lap(lap_num=2),
        ]
        session = CalibrationSession(
            session_id="two_lap_guard",
            track_location_id="fuji_international_speedway",
            layout_id="fuji_international_speedway__full_course",
            laps=laps,
        )
        results = assess_session_laps(session)

        for i, r in enumerate(results):
            assert r.quality not in (
                CalibrationLapQuality.PARTIAL_START,
                CalibrationLapQuality.PARTIAL_STOP,
            ), (
                f"Lap {i + 1} was classified as {r.quality!r} in a 2-lap session; "
                "partial detection should be skipped for sessions with <= 2 laps"
            )

    def test_two_lap_session_short_laps_evaluated_normally(self):
        """EXTRA: Even short laps in a 2-lap session are evaluated normally (not as partials)."""
        laps = [
            _make_short_partial_lap(lap_num=1),
            _make_short_partial_lap(lap_num=2),
        ]
        session = CalibrationSession(
            session_id="two_short_laps",
            track_location_id="fuji_international_speedway",
            layout_id="fuji_international_speedway__full_course",
            laps=laps,
        )
        results = assess_session_laps(session)

        # Neither lap should be PARTIAL_START or PARTIAL_STOP
        for i, r in enumerate(results):
            assert r.quality not in (
                CalibrationLapQuality.PARTIAL_START,
                CalibrationLapQuality.PARTIAL_STOP,
            ), (
                f"Lap {i + 1} got {r.quality!r} in a 2-lap session; expected normal evaluation"
            )

    def test_four_lap_session_does_detect_partials(self):
        """EXTRA: A 4-lap session (> 2) DOES apply partial detection (guard boundary check).

        With [short, full, full, short], the median path is full-lap length, so the
        two short boundary laps are well below 50% of median and get partial classification.
        """
        laps = [
            _make_short_partial_lap(lap_num=1),
            _make_full_lap(lap_num=2),
            _make_full_lap(lap_num=3),
            _make_short_partial_lap(lap_num=4),
        ]
        session = CalibrationSession(
            session_id="four_lap_check",
            track_location_id="fuji_international_speedway",
            layout_id="fuji_international_speedway__full_course",
            laps=laps,
        )
        results = assess_session_laps(session)

        # 4-lap session (> 2): first and last short laps must be partial
        assert results[0].quality == CalibrationLapQuality.PARTIAL_START, (
            f"Expected PARTIAL_START for first lap in 4-lap session; got {results[0].quality!r}"
        )
        assert results[-1].quality == CalibrationLapQuality.PARTIAL_STOP, (
            f"Expected PARTIAL_STOP for last lap in 4-lap session; got {results[-1].quality!r}"
        )
