"""Group 17N UAT defect regression tests.

Covers DEF-17N-UAT-004 — Detect Segments requires live session despite saved
reference path existing.

Root cause: save_reference_path() only persisted the aggregated 200-point
ReferencePath; raw CalibrationLap samples were discarded.  detect_track_segments()
needs raw per-sample data (speed, brake, throttle, XYZ) to find corners.

Fix: export_calibration_laps_json() saves USABLE CalibrationLap objects alongside
the reference path.  save_reference_path() now writes both files.
import_calibration_laps_json() reconstructs a CalibrationSession from the laps
file so detect_track_segments() can run without a live session.

All tests are pure Python (no PyQt6 dependency).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from data.track_calibration import CalibrationSession


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_telemetry_sample(i: int, lap_number: int = 1):
    from data.track_calibration import TelemetrySample
    return TelemetrySample(
        timestamp_ms  = i * 100,
        lap_number    = lap_number,
        x             = float(i) * 10.0,
        y             = 0.0,
        z             = float(i) * 5.0,
        speed_kph     = 180.0 - float(i % 30),
        gear          = 4 + (i % 3),
        rpm           = 7000.0 - float(i % 500),
        throttle      = 0.8 if i % 5 != 0 else 0.0,
        brake         = 0.0 if i % 5 != 0 else 0.8,
        road_distance = float(i) * 29.0,
        yaw_rate      = 0.01 if i % 10 == 0 else 0.0,
        road_plane_y  = 1.0,
        is_off_track  = False,
    )


def _make_usable_lap(lap_number: int = 1, n_samples: int = 120):
    from data.track_calibration import CalibrationLap, CalibrationLapQuality
    samples = [_make_telemetry_sample(i, lap_number) for i in range(n_samples)]
    return CalibrationLap(
        lap_number      = lap_number,
        lap_time_ms     = n_samples * 100,
        samples         = samples,
        quality         = CalibrationLapQuality.USABLE,
        quality_reasons = [],
        path_length_m   = float(n_samples) * 29.0,
    )


def _make_rejected_lap(lap_number: int = 99):
    from data.track_calibration import CalibrationLap, CalibrationLapQuality
    return CalibrationLap(
        lap_number      = lap_number,
        lap_time_ms     = 5000,
        samples         = [],
        quality         = CalibrationLapQuality.REJECTED,
        quality_reasons = ["Too short"],
    )


# ---------------------------------------------------------------------------
# calibration_laps_filename
# ---------------------------------------------------------------------------

class TestCalibrationLapsFilename:
    def test_filename_format(self):
        from data.track_calibration import calibration_laps_filename
        name = calibration_laps_filename(
            "daytona_international_speedway",
            "daytona_international_speedway__road_course",
        )
        assert name == (
            "daytona_international_speedway__"
            "daytona_international_speedway__road_course.calibration_laps.json"
        )

    def test_distinct_from_ref_path_filename(self):
        from data.track_calibration import calibration_laps_filename, reference_path_filename
        laps = calibration_laps_filename("a", "b")
        ref  = reference_path_filename("a", "b")
        assert laps != ref
        assert "calibration_laps" in laps
        assert "reference_path"   in ref


# ---------------------------------------------------------------------------
# export_calibration_laps_json
# ---------------------------------------------------------------------------

class TestExportCalibrationLapsJson:
    def test_creates_file(self, tmp_path):
        from data.track_calibration import export_calibration_laps_json, calibration_laps_filename
        lap = _make_usable_lap(1)
        out = export_calibration_laps_json([lap], "suzuka", "full", output_dir=tmp_path)
        assert out.exists()
        assert out.name == calibration_laps_filename("suzuka", "full")

    def test_only_usable_laps_exported(self, tmp_path):
        from data.track_calibration import export_calibration_laps_json
        usable  = _make_usable_lap(1)
        rejected = _make_rejected_lap(2)
        out = export_calibration_laps_json([usable, rejected], "a", "b", output_dir=tmp_path)
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["usable_lap_count"] == 1
        assert len(payload["laps"]) == 1
        assert payload["laps"][0]["quality"] == "usable"

    def test_sample_fields_preserved(self, tmp_path):
        from data.track_calibration import export_calibration_laps_json
        lap = _make_usable_lap(1, n_samples=5)
        out = export_calibration_laps_json([lap], "a", "b", output_dir=tmp_path)
        payload = json.loads(out.read_text(encoding="utf-8"))
        s = payload["laps"][0]["samples"][0]
        assert "x" in s and "y" in s and "z" in s
        assert "speed_kph" in s
        assert "brake" in s and "throttle" in s
        assert "gear" in s and "rpm" in s

    def test_metadata_fields_present(self, tmp_path):
        from data.track_calibration import export_calibration_laps_json
        lap = _make_usable_lap(1)
        out = export_calibration_laps_json([lap], "spa", "long", "porsche_test",
                                           output_dir=tmp_path)
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["track_location_id"] == "spa"
        assert payload["layout_id"]         == "long"
        assert payload["calibration_car_id"] == "porsche_test"
        assert payload["format_version"]    == 1
        assert "saved_at" in payload

    def test_empty_laps_list_writes_zero(self, tmp_path):
        from data.track_calibration import export_calibration_laps_json
        out = export_calibration_laps_json([], "a", "b", output_dir=tmp_path)
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["usable_lap_count"] == 0
        assert payload["laps"] == []

    def test_multiple_usable_laps(self, tmp_path):
        from data.track_calibration import export_calibration_laps_json
        laps = [_make_usable_lap(i) for i in range(1, 6)]
        out  = export_calibration_laps_json(laps, "a", "b", output_dir=tmp_path)
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["usable_lap_count"] == 5
        assert len(payload["laps"]) == 5

    def test_sample_count_preserved(self, tmp_path):
        from data.track_calibration import export_calibration_laps_json
        lap = _make_usable_lap(1, n_samples=80)
        out = export_calibration_laps_json([lap], "a", "b", output_dir=tmp_path)
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert len(payload["laps"][0]["samples"]) == 80

    def test_creates_output_dir_if_missing(self, tmp_path):
        from data.track_calibration import export_calibration_laps_json
        new_dir = tmp_path / "nested" / "deep"
        assert not new_dir.exists()
        export_calibration_laps_json([_make_usable_lap(1)], "a", "b", output_dir=new_dir)
        assert new_dir.exists()


# ---------------------------------------------------------------------------
# import_calibration_laps_json
# ---------------------------------------------------------------------------

class TestImportCalibrationLapsJson:
    def _write_and_read(self, tmp_path, laps, loc="a", lay="b", car="test_car"):
        from data.track_calibration import export_calibration_laps_json, import_calibration_laps_json, calibration_laps_filename
        out = export_calibration_laps_json(laps, loc, lay, car, output_dir=tmp_path)
        return import_calibration_laps_json(out)

    def test_returns_calibration_session(self, tmp_path):
        from data.track_calibration import CalibrationSession
        session = self._write_and_read(tmp_path, [_make_usable_lap(1)])
        assert isinstance(session, CalibrationSession)

    def test_track_ids_preserved(self, tmp_path):
        session = self._write_and_read(tmp_path, [_make_usable_lap(1)],
                                       loc="suzuka", lay="full")
        assert session.track_location_id == "suzuka"
        assert session.layout_id         == "full"

    def test_car_id_preserved(self, tmp_path):
        session = self._write_and_read(tmp_path, [_make_usable_lap(1)],
                                       car="ferrari_488_gte_2017")
        assert session.calibration_car_id == "ferrari_488_gte_2017"

    def test_lap_count_correct(self, tmp_path):
        laps = [_make_usable_lap(i) for i in range(1, 4)]
        session = self._write_and_read(tmp_path, laps)
        assert len(session.laps) == 3

    def test_sample_fields_round_trip(self, tmp_path):
        lap = _make_usable_lap(1, n_samples=10)
        session = self._write_and_read(tmp_path, [lap])
        s0 = session.laps[0].samples[0]
        orig = lap.samples[0]
        assert abs(s0.x - orig.x) < 0.001
        assert abs(s0.speed_kph - orig.speed_kph) < 0.001
        assert abs(s0.brake - orig.brake) < 0.001
        assert abs(s0.throttle - orig.throttle) < 0.001
        assert s0.gear == orig.gear

    def test_quality_is_usable(self, tmp_path):
        from data.track_calibration import CalibrationLapQuality
        session = self._write_and_read(tmp_path, [_make_usable_lap(1)])
        assert session.laps[0].quality == CalibrationLapQuality.USABLE

    def test_raises_file_not_found(self, tmp_path):
        from data.track_calibration import import_calibration_laps_json
        with pytest.raises(FileNotFoundError):
            import_calibration_laps_json(tmp_path / "does_not_exist.json")

    def test_raises_json_decode_error_on_corrupt(self, tmp_path):
        from data.track_calibration import import_calibration_laps_json
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid json!!", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            import_calibration_laps_json(bad)

    def test_session_id_contains_loaded_marker(self, tmp_path):
        session = self._write_and_read(tmp_path, [_make_usable_lap(1)],
                                       loc="spa", lay="full")
        assert "loaded" in session.session_id or "spa" in session.session_id

    def test_sample_yaw_rate_round_trip(self, tmp_path):
        lap = _make_usable_lap(1, n_samples=5)
        session = self._write_and_read(tmp_path, [lap])
        for loaded_s, orig_s in zip(session.laps[0].samples, lap.samples):
            if orig_s.yaw_rate is not None:
                assert abs(loaded_s.yaw_rate - orig_s.yaw_rate) < 0.0001
            else:
                assert loaded_s.yaw_rate is None


# ---------------------------------------------------------------------------
# save_reference_path also saves laps (TrackCalibrationCaptureController)
# ---------------------------------------------------------------------------

class TestSaveReferencePathAlsoSavesLaps:
    def _build_controller_with_laps(self, tmp_path, n_usable_laps=3):
        """Build a controller that has a session with usable laps and a built ref path."""
        from data.track_calibration import (
            CalibrationSession, CalibrationLap, CalibrationLapQuality,
            ReferencePath, ReferencePathPoint, CalibrationBuildResult,
        )
        from data.track_calibration_runtime import TrackCalibrationCaptureController, CalibrationCaptureState

        ctrl = TrackCalibrationCaptureController()
        loc_id = "daytona_international_speedway"
        lay_id = "daytona_international_speedway__road_course"
        ctrl.start_session(loc_id, lay_id)

        # Inject usable laps directly (bypasses live feed)
        laps = [_make_usable_lap(i + 1, n_samples=120) for i in range(n_usable_laps)]
        ctrl._session.laps = laps

        # Inject a mock build result
        pt = ReferencePathPoint(
            lap_progress=0.5, distance_along_lap_m=2903.0,
            x=100.0, y=0.0, z=200.0,
            speed_kph_avg=180.0, source_lap_count=n_usable_laps,
        )
        rp = ReferencePath(
            track_location_id  = loc_id,
            layout_id          = lay_id,
            calibration_car_id = ctrl._session.calibration_car_id,
            source_lap_count   = n_usable_laps,
            points             = [pt],
            confidence         = 0.9,
        )
        ctrl._last_build_result = CalibrationBuildResult(
            success             = True,
            reference_path      = rp,
            usable_lap_count    = n_usable_laps,
            rejected_lap_count  = 0,
        )
        ctrl._state = CalibrationCaptureState.BUILT
        return ctrl, loc_id, lay_id

    def test_both_files_written(self, tmp_path):
        from data.track_calibration import reference_path_filename, calibration_laps_filename
        ctrl, loc, lay = self._build_controller_with_laps(tmp_path, n_usable_laps=3)
        result = ctrl.save_reference_path(output_dir=tmp_path)
        assert result is not None
        assert (tmp_path / reference_path_filename(loc, lay)).exists()
        assert (tmp_path / calibration_laps_filename(loc, lay)).exists()

    def test_laps_file_usable_count_matches(self, tmp_path):
        from data.track_calibration import calibration_laps_filename
        ctrl, loc, lay = self._build_controller_with_laps(tmp_path, n_usable_laps=4)
        ctrl.save_reference_path(output_dir=tmp_path)
        laps_file = tmp_path / calibration_laps_filename(loc, lay)
        payload = json.loads(laps_file.read_text(encoding="utf-8"))
        assert payload["usable_lap_count"] == 4

    def test_laps_file_has_samples(self, tmp_path):
        from data.track_calibration import calibration_laps_filename
        ctrl, loc, lay = self._build_controller_with_laps(tmp_path, n_usable_laps=2)
        ctrl.save_reference_path(output_dir=tmp_path)
        laps_file = tmp_path / calibration_laps_filename(loc, lay)
        payload = json.loads(laps_file.read_text(encoding="utf-8"))
        assert all(len(lap["samples"]) > 0 for lap in payload["laps"])


# ---------------------------------------------------------------------------
# audit_track_model_files includes calibration laps
# ---------------------------------------------------------------------------

class TestAuditIncludesCalibrationLaps:
    def _write_ref_and_laps(self, tmp_path, n_laps=3):
        from data.track_calibration import (
            ReferencePath, ReferencePathPoint,
            export_reference_path_json, export_calibration_laps_json,
        )
        laps = [_make_usable_lap(i + 1) for i in range(n_laps)]
        pt = ReferencePathPoint(
            lap_progress=0.5, distance_along_lap_m=2903.0,
            x=100.0, y=0.0, z=200.0,
            speed_kph_avg=180.0, source_lap_count=n_laps,
        )
        rp = ReferencePath(
            track_location_id="a", layout_id="b",
            calibration_car_id="test", source_lap_count=n_laps,
            points=[pt], confidence=0.85,
        )
        export_reference_path_json(rp, output_dir=tmp_path)
        export_calibration_laps_json(laps, "a", "b", output_dir=tmp_path)

    def test_laps_file_detected(self, tmp_path):
        from data.track_calibration import audit_track_model_files
        self._write_ref_and_laps(tmp_path, n_laps=3)
        a = audit_track_model_files("a", "b", search_dir=tmp_path)
        assert a.calibration_laps_exists is True

    def test_laps_usable_count_correct(self, tmp_path):
        from data.track_calibration import audit_track_model_files
        self._write_ref_and_laps(tmp_path, n_laps=5)
        a = audit_track_model_files("a", "b", search_dir=tmp_path)
        assert a.calibration_laps_usable_count == 5

    def test_no_laps_file_exists_false(self, tmp_path):
        from data.track_calibration import (
            ReferencePath, ReferencePathPoint,
            export_reference_path_json, audit_track_model_files,
        )
        pt = ReferencePathPoint(
            lap_progress=0.5, distance_along_lap_m=2903.0,
            x=100.0, y=0.0, z=200.0, speed_kph_avg=180.0, source_lap_count=3,
        )
        rp = ReferencePath(
            track_location_id="a", layout_id="b",
            calibration_car_id="test", source_lap_count=3,
            points=[pt], confidence=0.9,
        )
        export_reference_path_json(rp, output_dir=tmp_path)
        a = audit_track_model_files("a", "b", search_dir=tmp_path)
        assert a.calibration_laps_exists is False
        assert a.calibration_laps_usable_count == 0

    def test_can_detect_segments_true_when_both_files(self, tmp_path):
        from data.track_calibration import audit_track_model_files
        self._write_ref_and_laps(tmp_path, n_laps=3)
        a = audit_track_model_files("a", "b", search_dir=tmp_path)
        assert a.can_detect_segments is True

    def test_can_detect_segments_false_when_only_ref_path(self, tmp_path):
        from data.track_calibration import (
            ReferencePath, ReferencePathPoint,
            export_reference_path_json, audit_track_model_files,
        )
        pt = ReferencePathPoint(
            lap_progress=0.5, distance_along_lap_m=2903.0,
            x=100.0, y=0.0, z=200.0, speed_kph_avg=180.0, source_lap_count=3,
        )
        rp = ReferencePath(
            track_location_id="a", layout_id="b",
            calibration_car_id="test", source_lap_count=3,
            points=[pt], confidence=0.9,
        )
        export_reference_path_json(rp, output_dir=tmp_path)
        a = audit_track_model_files("a", "b", search_dir=tmp_path)
        assert a.can_detect_segments is False

    def test_is_legacy_ref_path_only_true(self, tmp_path):
        from data.track_calibration import (
            ReferencePath, ReferencePathPoint,
            export_reference_path_json, audit_track_model_files,
        )
        pt = ReferencePathPoint(
            lap_progress=0.5, distance_along_lap_m=2903.0,
            x=100.0, y=0.0, z=200.0, speed_kph_avg=180.0, source_lap_count=3,
        )
        rp = ReferencePath(
            track_location_id="a", layout_id="b",
            calibration_car_id="test", source_lap_count=3,
            points=[pt], confidence=0.9,
        )
        export_reference_path_json(rp, output_dir=tmp_path)
        a = audit_track_model_files("a", "b", search_dir=tmp_path)
        assert a.is_legacy_ref_path_only is True

    def test_is_legacy_ref_path_only_false_when_laps_exist(self, tmp_path):
        from data.track_calibration import audit_track_model_files
        self._write_ref_and_laps(tmp_path, n_laps=3)
        a = audit_track_model_files("a", "b", search_dir=tmp_path)
        assert a.is_legacy_ref_path_only is False

    def test_laps_file_path_in_audit(self, tmp_path):
        from data.track_calibration import audit_track_model_files, calibration_laps_filename
        self._write_ref_and_laps(tmp_path, n_laps=2)
        a = audit_track_model_files("a", "b", search_dir=tmp_path)
        assert calibration_laps_filename("a", "b") in a.calibration_laps_file


# ---------------------------------------------------------------------------
# detect_track_segments from loaded laps (round-trip integration)
# ---------------------------------------------------------------------------

class TestDetectSegmentsFromLoadedLaps:
    def _make_session_for_detection(self, tmp_path, n_laps=3, n_samples=200) -> "CalibrationSession":
        """Export laps then reload them into a fresh session."""
        from data.track_calibration import (
            export_calibration_laps_json, import_calibration_laps_json,
            calibration_laps_filename,
        )
        laps = [_make_usable_lap(i + 1, n_samples=n_samples) for i in range(n_laps)]
        out  = export_calibration_laps_json(laps, "daytona", "road_course",
                                            output_dir=tmp_path)
        return import_calibration_laps_json(out)

    def test_loaded_session_has_usable_laps(self, tmp_path):
        from data.track_calibration import CalibrationLapQuality
        session = self._make_session_for_detection(tmp_path, n_laps=3)
        usable = [l for l in session.laps if l.quality == CalibrationLapQuality.USABLE]
        assert len(usable) == 3

    def test_detect_segments_does_not_raise(self, tmp_path):
        from data.track_segment_detection import detect_track_segments
        session = self._make_session_for_detection(tmp_path, n_laps=3, n_samples=200)
        result = detect_track_segments(session)
        assert result is not None

    def test_detect_segments_returns_result_object(self, tmp_path):
        from data.track_segment_detection import detect_track_segments, SegmentDetectionResult
        session = self._make_session_for_detection(tmp_path, n_laps=3, n_samples=200)
        result  = detect_track_segments(session)
        assert isinstance(result, SegmentDetectionResult)

    def test_detect_segments_on_empty_loaded_session_returns_failure(self, tmp_path):
        from data.track_calibration import export_calibration_laps_json, import_calibration_laps_json
        from data.track_segment_detection import detect_track_segments
        # Save zero laps (session with all laps rejected)
        out  = export_calibration_laps_json([], "a", "b", output_dir=tmp_path)
        sess = import_calibration_laps_json(out)
        result = detect_track_segments(sess)
        assert result.success is False
        assert result.errors


# ---------------------------------------------------------------------------
# format_file_audit_status for new laps-aware fields
# ---------------------------------------------------------------------------

class TestFormatFileAuditStatusWithLaps:
    def _audit(self, **kw):
        from data.track_calibration import TrackModelFileAudit
        a = TrackModelFileAudit(loc_id="a", lay_id="b")
        for k, v in kw.items():
            setattr(a, k, v)
        return a

    def test_laps_present_in_detail_text(self):
        from ui.track_modelling_vm import format_file_audit_status
        a = self._audit(
            ref_path_exists=True, ref_path_load_ok=True,
            ref_path_point_count=200, ref_path_confidence=1.0, ref_path_source_laps=5,
            calibration_laps_exists=True, calibration_laps_usable_count=5,
        )
        r = format_file_audit_status(a)
        assert "5 laps persisted" in r["detail_text"]
        assert "Detect Segments ready" in r["load_status"]

    def test_legacy_format_shown_in_load_status(self):
        from ui.track_modelling_vm import format_file_audit_status
        a = self._audit(
            ref_path_exists=True, ref_path_load_ok=True,
            ref_path_point_count=200, ref_path_confidence=1.0, ref_path_source_laps=5,
            calibration_laps_exists=False, calibration_laps_usable_count=0,
        )
        r = format_file_audit_status(a)
        assert "no lap data" in r["detail_text"].lower() or "17n" in r["load_status"].lower() or "re-run" in r["load_status"].lower()

    def test_no_ref_path_shows_none_message(self):
        from ui.track_modelling_vm import format_file_audit_status
        a = self._audit(ref_path_exists=False)
        r = format_file_audit_status(a)
        assert "No saved" in r["saved_text"]


# ---------------------------------------------------------------------------
# Daytona integration: existing Daytona file is legacy format
# ---------------------------------------------------------------------------

class TestDaytonaBehaviourWithExistingFile:
    def test_daytona_ref_path_is_legacy_until_resaved(self):
        """The Daytona file saved before Group 17N must be detected as legacy."""
        from data.track_calibration import audit_track_model_files, TRACK_MODELS_DIR
        a = audit_track_model_files(
            "daytona_international_speedway",
            "daytona_international_speedway__road_course",
            search_dir=TRACK_MODELS_DIR,
        )
        if not a.ref_path_exists:
            pytest.skip("Daytona reference path file not present")
        assert a.ref_path_load_ok, f"Daytona ref path unreadable: {a.ref_path_load_error}"
        # Three possible states for the Daytona laps file on disk:
        # 1. No laps file at all (pre-17N save) → is_legacy_ref_path_only
        # 2. Laps file exists with 0 usable laps (saved after a failed calibration run)
        # 3. Laps file exists with >0 usable laps (saved after a successful calibration)
        if not a.calibration_laps_exists:
            # State 1: legacy format — no laps file
            assert a.is_legacy_ref_path_only is True
            assert a.can_detect_segments is False
        elif a.calibration_laps_usable_count == 0:
            # State 2: laps file written but all laps were rejected → cannot detect
            assert a.can_detect_segments is False
            assert a.is_legacy_ref_path_only is False
        else:
            # State 3: laps file with usable laps → Detect Segments ready
            assert a.calibration_laps_usable_count > 0
            assert a.can_detect_segments is True


# ---------------------------------------------------------------------------
# Round-trip: save → reload → detect (no live session)
# ---------------------------------------------------------------------------

class TestRoundTripSaveReloadDetect:
    def test_full_pipeline_no_live_session(self, tmp_path):
        """Simulate the UAT scenario: save → restart → detect without live session."""
        from data.track_calibration import (
            ReferencePath, ReferencePathPoint,
            export_reference_path_json, export_calibration_laps_json,
            import_calibration_laps_json, calibration_laps_filename,
            audit_track_model_files,
        )
        from data.track_segment_detection import detect_track_segments

        loc_id = "daytona_international_speedway"
        lay_id = "daytona_international_speedway__road_course"

        # Step 1: "calibration session complete" — write both files
        laps = [_make_usable_lap(i + 1, n_samples=150) for i in range(3)]
        pts  = [
            ReferencePathPoint(
                lap_progress=i / 200, distance_along_lap_m=i * 29.0,
                x=float(i) * 10.0, y=0.0, z=float(i) * 5.0,
                speed_kph_avg=175.0, source_lap_count=3,
            )
            for i in range(200)
        ]
        rp = ReferencePath(
            track_location_id=loc_id, layout_id=lay_id,
            calibration_car_id="porsche_911_rsr_991_2017",
            source_lap_count=3, points=pts, confidence=0.90,
        )
        export_reference_path_json(rp, output_dir=tmp_path)
        export_calibration_laps_json(laps, loc_id, lay_id, output_dir=tmp_path)

        # Step 2: "app restart" — no controller in memory; audit discovers both files
        audit = audit_track_model_files(loc_id, lay_id, search_dir=tmp_path)
        assert audit.can_detect_segments is True, "Audit must report Detect Segments is ready"

        # Step 3: load persisted laps, reconstruct session
        session = import_calibration_laps_json(
            tmp_path / calibration_laps_filename(loc_id, lay_id)
        )
        assert len(session.laps) == 3

        # Step 4: run detection — must not raise
        result = detect_track_segments(session)
        assert result is not None
        assert isinstance(result.success, bool)  # either True or False is fine; no crash

    def test_controller_save_produces_both_files(self, tmp_path):
        """Verify controller.save_reference_path() produces both files in one call."""
        from data.track_calibration import (
            ReferencePath, ReferencePathPoint, CalibrationBuildResult,
            reference_path_filename, calibration_laps_filename, audit_track_model_files,
        )
        from data.track_calibration_runtime import (
            TrackCalibrationCaptureController, CalibrationCaptureState,
        )

        loc_id = "spa_francorchamps"
        lay_id = "spa_francorchamps__full_circuit"

        ctrl = TrackCalibrationCaptureController()
        ctrl.start_session(loc_id, lay_id)
        ctrl._session.laps = [_make_usable_lap(i + 1, n_samples=100) for i in range(3)]

        pt = ReferencePathPoint(
            lap_progress=0.5, distance_along_lap_m=3500.0,
            x=100.0, y=0.0, z=200.0, speed_kph_avg=220.0, source_lap_count=3,
        )
        rp = ReferencePath(
            track_location_id  = loc_id,
            layout_id          = lay_id,
            calibration_car_id = ctrl._session.calibration_car_id,
            source_lap_count   = 3,
            points             = [pt],
            confidence         = 0.88,
        )
        ctrl._last_build_result = CalibrationBuildResult(
            success=True, reference_path=rp,
            usable_lap_count=3, rejected_lap_count=0,
        )
        ctrl._state = CalibrationCaptureState.BUILT

        saved = ctrl.save_reference_path(output_dir=tmp_path)
        assert saved is not None

        audit = audit_track_model_files(loc_id, lay_id, search_dir=tmp_path)
        assert audit.ref_path_exists            is True
        assert audit.calibration_laps_exists    is True
        assert audit.calibration_laps_usable_count == 3
        assert audit.can_detect_segments        is True
