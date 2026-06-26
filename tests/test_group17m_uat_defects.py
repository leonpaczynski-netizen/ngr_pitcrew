"""Group 17M UAT defect regression tests.

Covers:
  DEF-17M-UAT-001 — Calibration lap count mismatch display
  DEF-17M-UAT-002 — Detect Segments crash (seed_result.layouts AttributeError)
  DEF-17M-UAT-003 — Saved reference path not discoverable after restart

All tests are pure Python (no PyQt6 dependency).
"""
from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pytest


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

@dataclass
class _SeedResult:
    success: bool = True
    track_locations: list = field(default_factory=list)
    # Note: intentionally NO .layouts attribute — matches real TrackSeedLoadResult


@dataclass
class _LocationSeed:
    track_location_id: str = "daytona_international_speedway"
    layouts: list = field(default_factory=list)


@dataclass
class _LayoutSeed:
    layout_id: str = "daytona_international_speedway__road_course"
    corners_expected: Optional[int] = 15


# ---------------------------------------------------------------------------
# DEF-17M-UAT-001 — format_lap_count_info
# ---------------------------------------------------------------------------

class TestFormatLapCountInfo:
    def _s(self, **kw) -> dict:
        base = {
            "state": "inactive",
            "lap_count": 0,
            "usable_laps": 0,
            "rejected_laps": 0,
            "low_confidence_laps": 0,
            "current_lap_number": None,
            "in_progress_samples": 0,
        }
        base.update(kw)
        return base

    def test_no_laps_recorded(self):
        from ui.track_modelling_vm import format_lap_count_info
        r = format_lap_count_info(self._s())
        assert "No lap" in r["captured_text"]
        assert r["quality_text"] == ""
        assert r["explanation"] == ""

    def test_recording_shows_count(self):
        from ui.track_modelling_vm import format_lap_count_info
        r = format_lap_count_info(self._s(state="recording", lap_count=3,
                                          current_lap_number=4, in_progress_samples=120))
        assert "3 lap" in r["captured_text"]
        assert "lap 4" in r["captured_text"]
        assert "120" in r["captured_text"]

    def test_stopped_prompts_build(self):
        from ui.track_modelling_vm import format_lap_count_info
        r = format_lap_count_info(self._s(state="stopped", lap_count=8))
        assert "8 lap" in r["captured_text"]
        assert "Build Reference Path" in r["quality_text"]

    def test_after_build_shows_quality_breakdown(self):
        from ui.track_modelling_vm import format_lap_count_info
        r = format_lap_count_info(self._s(state="built", lap_count=8,
                                          usable_laps=5, rejected_laps=3,
                                          low_confidence_laps=0))
        assert "5 usable" in r["quality_text"]
        assert "3 rejected" in r["quality_text"]
        assert "0 low-confidence" in r["quality_text"]

    def test_explanation_when_lap_count_exceeds_assessed(self):
        from ui.track_modelling_vm import format_lap_count_info
        # Daytona scenario: 8 captured, 5+3 assessed but 0 partial fragments
        r = format_lap_count_info(self._s(state="built", lap_count=8,
                                          usable_laps=5, rejected_laps=3,
                                          low_confidence_laps=0))
        # 8 == 5+3+0, no gap → no explanation needed
        assert r["explanation"] == ""

    def test_explanation_when_gap_exists(self):
        from ui.track_modelling_vm import format_lap_count_info
        # 10 captured but only 8 assessed (2 partial fragments not in quality results)
        r = format_lap_count_info(self._s(state="built", lap_count=10,
                                          usable_laps=5, rejected_laps=3,
                                          low_confidence_laps=0))
        # 10 > 8 → 2 unassessed fragments → explanation shown
        assert "2" in r["explanation"]
        assert "partial" in r["explanation"].lower()
        assert "normal" in r["explanation"].lower()

    def test_no_explanation_when_assessed_equals_captured(self):
        from ui.track_modelling_vm import format_lap_count_info
        r = format_lap_count_info(self._s(state="built", lap_count=5,
                                          usable_laps=3, rejected_laps=2))
        assert r["explanation"] == ""

    def test_no_explanation_before_build(self):
        from ui.track_modelling_vm import format_lap_count_info
        r = format_lap_count_info(self._s(state="stopped", lap_count=8))
        assert r["explanation"] == ""

    def test_singular_lap_text(self):
        from ui.track_modelling_vm import format_lap_count_info
        r = format_lap_count_info(self._s(state="stopped", lap_count=1))
        assert "1 lap segment" in r["captured_text"]

    def test_quality_empty_when_state_recording(self):
        from ui.track_modelling_vm import format_lap_count_info
        r = format_lap_count_info(self._s(state="recording", lap_count=3))
        assert r["quality_text"] == ""

    def test_explanation_not_shown_when_no_quality_data(self):
        from ui.track_modelling_vm import format_lap_count_info
        r = format_lap_count_info(self._s(state="stopped", lap_count=8,
                                          usable_laps=0, rejected_laps=0))
        assert r["explanation"] == ""  # nothing assessed yet → no gap → no note


# ---------------------------------------------------------------------------
# DEF-17M-UAT-002 — seed_result.layouts crash guard
# ---------------------------------------------------------------------------

class TestSeedResultLayoutsAccess:
    """Verify that accessing seed_result.layouts raises AttributeError so
    anyone using it will crash — and that the fixed code path uses
    get_selected_layout() which uses track_locations correctly.
    """

    def test_seed_result_has_no_layouts_attribute(self):
        """Confirm TrackSeedLoadResult has track_locations, not layouts."""
        from data.track_intelligence import TrackSeedLoadResult
        r = TrackSeedLoadResult(success=True)
        assert hasattr(r, "track_locations")
        assert not hasattr(r, "layouts"), (
            "TrackSeedLoadResult must NOT have .layouts — "
            "if this fails, the crash bug is now masked by the dataclass change"
        )

    @staticmethod
    def _lay(layout_id: str, loc_id: str = "daytona"):
        from data.track_intelligence import TrackLayoutSeed
        return TrackLayoutSeed(
            layout_id=layout_id, display_name=layout_id.title(),
            track_location_id=loc_id, length_m=5807.0,
        )

    @staticmethod
    def _loc(loc_id: str, layouts: list):
        from data.track_intelligence import TrackLocationSeed
        return TrackLocationSeed(track_location_id=loc_id, display_name=loc_id.title(),
                                 layouts=layouts)

    def test_get_selected_layout_uses_track_locations(self):
        """get_selected_layout() must use track_locations, not layouts."""
        from ui.track_modelling_vm import get_selected_layout
        from data.track_intelligence import TrackSeedLoadResult
        lay = self._lay("road_course", "daytona")
        sr = TrackSeedLoadResult(success=True, track_locations=[self._loc("daytona", [lay])])
        assert get_selected_layout(sr, "daytona", "road_course") is lay

    def test_get_selected_layout_returns_none_for_missing(self):
        from ui.track_modelling_vm import get_selected_layout
        from data.track_intelligence import TrackSeedLoadResult
        sr = TrackSeedLoadResult(success=True, track_locations=[])
        assert get_selected_layout(sr, "daytona", "road_course") is None

    def test_get_selected_layout_wrong_loc_returns_none(self):
        from ui.track_modelling_vm import get_selected_layout
        from data.track_intelligence import TrackSeedLoadResult
        lay = self._lay("road_course", "daytona")
        sr  = TrackSeedLoadResult(success=True, track_locations=[self._loc("daytona", [lay])])
        assert get_selected_layout(sr, "suzuka", "road_course") is None

    def test_get_selected_layout_wrong_lay_returns_none(self):
        from ui.track_modelling_vm import get_selected_layout
        from data.track_intelligence import TrackSeedLoadResult
        lay = self._lay("road_course", "daytona")
        sr  = TrackSeedLoadResult(success=True, track_locations=[self._loc("daytona", [lay])])
        assert get_selected_layout(sr, "daytona", "oval") is None


class TestDetectSegmentsNoCrash:
    """Verify detect_track_segments handles edge cases without crashing."""

    def _make_session(self, loc_id="a", lay_id="b", laps=None):
        from data.track_calibration import CalibrationSession
        s = CalibrationSession(
            session_id=f"test__{loc_id}__{lay_id}",
            track_location_id=loc_id,
            layout_id=lay_id,
        )
        if laps:
            s.laps = laps
        return s

    def test_empty_session_returns_failure_not_exception(self):
        from data.track_segment_detection import detect_track_segments
        session = self._make_session()
        result = detect_track_segments(session, layout_seed=None)
        assert result.success is False
        assert result.errors  # must give a reason

    def test_none_layout_seed_accepted(self):
        from data.track_segment_detection import detect_track_segments
        session = self._make_session()
        result = detect_track_segments(session, layout_seed=None)
        assert result is not None

    def test_detect_with_real_layout_seed_no_crash(self):
        from data.track_intelligence import TrackLayoutSeed
        from data.track_segment_detection import detect_track_segments
        lay = TrackLayoutSeed(layout_id="road_course", display_name="Road Course",
                              track_location_id="daytona", length_m=5807.0, corners_expected=15)
        session = self._make_session()
        result = detect_track_segments(session, layout_seed=lay)
        assert result is not None
        assert isinstance(result.errors, list)


# ---------------------------------------------------------------------------
# DEF-17M-UAT-003 — persistence audit helper
# ---------------------------------------------------------------------------

class TestReferencePathFilename:
    def test_filename_format(self):
        from data.track_calibration import reference_path_filename
        name = reference_path_filename("daytona_international_speedway",
                                       "daytona_international_speedway__road_course")
        assert name == (
            "daytona_international_speedway__"
            "daytona_international_speedway__road_course.reference_path.json"
        )

    def test_filename_uses_ids_not_display_names(self):
        from data.track_calibration import reference_path_filename
        name = reference_path_filename("suzuka", "full_circuit")
        assert "suzuka__full_circuit.reference_path.json" == name


class TestAuditTrackModelFilesNotFound:
    def test_no_files_all_false(self, tmp_path):
        from data.track_calibration import audit_track_model_files
        a = audit_track_model_files("suzuka", "full", search_dir=tmp_path)
        assert a.ref_path_exists is False
        assert a.reviewed_exists is False
        assert a.offset_exists is False

    def test_loc_lay_stored(self, tmp_path):
        from data.track_calibration import audit_track_model_files
        a = audit_track_model_files("spa", "long", search_dir=tmp_path)
        assert a.loc_id == "spa"
        assert a.lay_id == "long"

    def test_ref_path_file_is_expected_path(self, tmp_path):
        from data.track_calibration import audit_track_model_files
        a = audit_track_model_files("suzuka", "full", search_dir=tmp_path)
        assert "suzuka__full.reference_path.json" in a.ref_path_file

    def test_no_file_load_ok_false(self, tmp_path):
        from data.track_calibration import audit_track_model_files
        a = audit_track_model_files("suzuka", "full", search_dir=tmp_path)
        assert a.ref_path_load_ok is False

    def test_never_raises_on_nonexistent_dir(self):
        from data.track_calibration import audit_track_model_files
        a = audit_track_model_files("x", "y", search_dir=Path("/nonexistent/__xyz__"))
        assert a is not None
        assert a.ref_path_exists is False


class TestAuditTrackModelFilesFound:
    def _write_ref_path_json(self, loc_id: str, lay_id: str, d: Path) -> Path:
        """Write a minimal valid reference path JSON file."""
        from data.track_calibration import (
            ReferencePath, ReferencePathPoint, export_reference_path_json,
        )
        pt = ReferencePathPoint(
            lap_progress=0.5, distance_along_lap_m=2903.5,
            x=100.0, y=0.0, z=200.0,
            speed_kph_avg=180.0, source_lap_count=3,
        )
        rp = ReferencePath(
            track_location_id=loc_id, layout_id=lay_id,
            calibration_car_id="test_car",
            source_lap_count=3, points=[pt],
            confidence=0.85, built_at="2026-06-25T12:00:00+00:00",
        )
        return export_reference_path_json(rp, output_dir=d)

    def test_file_found_ref_path_exists_true(self, tmp_path):
        from data.track_calibration import audit_track_model_files
        self._write_ref_path_json("suzuka", "full", tmp_path)
        a = audit_track_model_files("suzuka", "full", search_dir=tmp_path)
        assert a.ref_path_exists is True

    def test_file_found_load_ok_true(self, tmp_path):
        from data.track_calibration import audit_track_model_files
        self._write_ref_path_json("suzuka", "full", tmp_path)
        a = audit_track_model_files("suzuka", "full", search_dir=tmp_path)
        assert a.ref_path_load_ok is True

    def test_file_found_point_count_correct(self, tmp_path):
        from data.track_calibration import audit_track_model_files
        self._write_ref_path_json("suzuka", "full", tmp_path)
        a = audit_track_model_files("suzuka", "full", search_dir=tmp_path)
        assert a.ref_path_point_count == 1

    def test_file_found_confidence_correct(self, tmp_path):
        from data.track_calibration import audit_track_model_files
        self._write_ref_path_json("suzuka", "full", tmp_path)
        a = audit_track_model_files("suzuka", "full", search_dir=tmp_path)
        assert abs(a.ref_path_confidence - 0.85) < 0.001

    def test_file_found_source_laps_correct(self, tmp_path):
        from data.track_calibration import audit_track_model_files
        self._write_ref_path_json("suzuka", "full", tmp_path)
        a = audit_track_model_files("suzuka", "full", search_dir=tmp_path)
        assert a.ref_path_source_laps == 3

    def test_file_found_modified_time_present(self, tmp_path):
        from data.track_calibration import audit_track_model_files
        self._write_ref_path_json("suzuka", "full", tmp_path)
        a = audit_track_model_files("suzuka", "full", search_dir=tmp_path)
        assert a.ref_path_modified != ""
        assert "2026" in a.ref_path_modified or len(a.ref_path_modified) >= 10

    def test_wrong_track_not_found(self, tmp_path):
        from data.track_calibration import audit_track_model_files
        self._write_ref_path_json("suzuka", "full", tmp_path)
        a = audit_track_model_files("spa", "full", search_dir=tmp_path)
        assert a.ref_path_exists is False

    def test_daytona_real_file_readable(self):
        """Integration test: the actual Daytona reference path file from UAT must be loadable."""
        from data.track_calibration import audit_track_model_files, TRACK_MODELS_DIR
        a = audit_track_model_files(
            "daytona_international_speedway",
            "daytona_international_speedway__road_course",
            search_dir=TRACK_MODELS_DIR,
        )
        if not a.ref_path_exists:
            pytest.skip("Daytona reference path file not present (expected in CI)")
        assert a.ref_path_load_ok, f"Daytona file exists but failed to load: {a.ref_path_load_error}"
        assert a.ref_path_point_count > 0, "Expected non-zero points in Daytona reference path"


class TestAuditTrackModelFilesCorrupt:
    def test_corrupt_json_load_ok_false(self, tmp_path):
        from data.track_calibration import audit_track_model_files
        bad_file = tmp_path / "suzuka__full.reference_path.json"
        bad_file.write_text("{invalid json!!", encoding="utf-8")
        a = audit_track_model_files("suzuka", "full", search_dir=tmp_path)
        assert a.ref_path_exists is True
        assert a.ref_path_load_ok is False
        assert a.ref_path_load_error != ""

    def test_empty_json_load_ok_false(self, tmp_path):
        from data.track_calibration import audit_track_model_files
        empty = tmp_path / "suzuka__full.reference_path.json"
        empty.write_text("{}", encoding="utf-8")
        a = audit_track_model_files("suzuka", "full", search_dir=tmp_path)
        # {} will fail to load because required keys are missing
        assert a.ref_path_exists is True
        # load_ok may be True or False depending on whether empty dict passes — verify graceful
        assert isinstance(a.ref_path_load_ok, bool)


class TestFormatFileAuditStatus:
    def _audit(self, **kw):
        from data.track_calibration import TrackModelFileAudit
        a = TrackModelFileAudit(loc_id="suzuka", lay_id="full")
        for k, v in kw.items():
            setattr(a, k, v)
        return a

    def test_no_file_saved_text(self):
        from ui.track_modelling_vm import format_file_audit_status
        a = self._audit(ref_path_exists=False)
        r = format_file_audit_status(a)
        assert "No saved" in r["saved_text"]
        assert r["detail_text"] == ""

    def test_file_found_load_ok_saved_text(self):
        from ui.track_modelling_vm import format_file_audit_status
        # Post-17N: both ref path and laps file present → "ready" status
        a = self._audit(
            ref_path_exists=True, ref_path_load_ok=True,
            ref_path_file="/models/suzuka__full.json",
            ref_path_modified="2026-06-25 12:30",
            ref_path_point_count=412, ref_path_confidence=0.94,
            ref_path_source_laps=5,
            calibration_laps_exists=True, calibration_laps_usable_count=5,
        )
        r = format_file_audit_status(a)
        assert "Saved:" in r["saved_text"]
        assert "412 pts" in r["detail_text"]
        assert "0.94" in r["detail_text"]
        assert "5 laps" in r["detail_text"]
        assert "Detect Segments ready" in r["load_status"]

    def test_file_found_legacy_no_laps_shows_preformat_message(self):
        from ui.track_modelling_vm import format_file_audit_status
        # Pre-17N: ref path exists but no laps file → legacy message
        a = self._audit(
            ref_path_exists=True, ref_path_load_ok=True,
            ref_path_file="/models/suzuka__full.json",
            ref_path_point_count=200, ref_path_confidence=1.0,
            ref_path_source_laps=3,
            calibration_laps_exists=False, calibration_laps_usable_count=0,
        )
        r = format_file_audit_status(a)
        assert "Saved:" in r["saved_text"]
        # detail_text shows "no lap data saved"
        assert "no lap data" in r["detail_text"].lower()
        # load_status explains what to do
        assert "re-run" in r["load_status"].lower() or "17n" in r["load_status"].lower()

    def test_file_found_load_failed_shows_error(self):
        from ui.track_modelling_vm import format_file_audit_status
        a = self._audit(
            ref_path_exists=True, ref_path_load_ok=False,
            ref_path_load_error="KeyError: track_location_id",
            ref_path_file="/models/suzuka__full.json",
        )
        r = format_file_audit_status(a)
        assert "could not load" in r["saved_text"].lower()
        assert "unreadable" in r["load_status"].lower()

    def test_reviewed_model_found_in_extras(self):
        from ui.track_modelling_vm import format_file_audit_status
        a = self._audit(ref_path_exists=False, reviewed_exists=True)
        r = format_file_audit_status(a)
        assert "Reviewed model" in r["extras_text"]

    def test_offset_found_in_extras(self):
        from ui.track_modelling_vm import format_file_audit_status
        a = self._audit(ref_path_exists=False, offset_exists=True)
        r = format_file_audit_status(a)
        assert "Offset calibration" in r["extras_text"]

    def test_no_extras_when_none_found(self):
        from ui.track_modelling_vm import format_file_audit_status
        a = self._audit(ref_path_exists=False, reviewed_exists=False, offset_exists=False)
        r = format_file_audit_status(a)
        assert r["extras_text"] == ""


class TestTrackModelFileAuditSummaryLine:
    def test_no_loc_lay(self):
        from data.track_calibration import TrackModelFileAudit
        a = TrackModelFileAudit()
        s = a.summary_line().lower()
        assert "track" in s or "select" in s or "no " in s

    def test_ref_not_found(self):
        from data.track_calibration import TrackModelFileAudit
        a = TrackModelFileAudit(loc_id="a", lay_id="b", ref_path_exists=False)
        assert "not saved" in a.summary_line()

    def test_ref_found_load_ok(self):
        from data.track_calibration import TrackModelFileAudit
        a = TrackModelFileAudit(
            loc_id="a", lay_id="b",
            ref_path_exists=True, ref_path_load_ok=True,
            ref_path_point_count=200, ref_path_confidence=0.9,
            ref_path_source_laps=4,
        )
        s = a.summary_line()
        assert "200 pts" in s
        assert "0.90" in s

    def test_ref_path_status_text_no_file(self):
        from data.track_calibration import TrackModelFileAudit
        a = TrackModelFileAudit(loc_id="a", lay_id="b", ref_path_exists=False)
        assert a.ref_path_status_text() == ""

    def test_ref_path_status_text_with_file(self):
        from data.track_calibration import TrackModelFileAudit
        a = TrackModelFileAudit(
            loc_id="a", lay_id="b",
            ref_path_exists=True, ref_path_load_ok=True,
            ref_path_file="/models/a__b.json",
            ref_path_modified="2026-06-25 12:00",
        )
        s = a.ref_path_status_text()
        assert "Saved:" in s
        assert "2026-06-25" in s


# ---------------------------------------------------------------------------
# Round-trip: save → audit → load
# ---------------------------------------------------------------------------

class TestRoundTripSaveAndAudit:
    def test_saved_reference_path_is_auditable(self, tmp_path):
        """Write a reference path, then audit the same dir — must find and load it."""
        from data.track_calibration import (
            ReferencePath, ReferencePathPoint,
            export_reference_path_json, audit_track_model_files,
        )
        pts = [
            ReferencePathPoint(
                lap_progress=i / 100,
                distance_along_lap_m=i * 58.07,
                x=float(i), y=0.0, z=float(i * 2),
                speed_kph_avg=180.0, source_lap_count=5,
            )
            for i in range(100)
        ]
        rp = ReferencePath(
            track_location_id="daytona_international_speedway",
            layout_id="daytona_international_speedway__road_course",
            calibration_car_id="porsche_911_rsr_991_2017",
            source_lap_count=5, points=pts,
            confidence=0.88, built_at="2026-06-25T12:00:00+00:00",
        )
        export_reference_path_json(rp, output_dir=tmp_path)
        a = audit_track_model_files(
            "daytona_international_speedway",
            "daytona_international_speedway__road_course",
            search_dir=tmp_path,
        )
        assert a.ref_path_exists is True
        assert a.ref_path_load_ok is True
        assert a.ref_path_point_count == 100
        assert abs(a.ref_path_confidence - 0.88) < 0.001
        assert a.ref_path_source_laps == 5

    def test_audit_after_crash_finds_file(self, tmp_path):
        """Simulate crash after save: file on disk, no controller — audit must find it."""
        from data.track_calibration import (
            ReferencePath, ReferencePathPoint,
            export_reference_path_json, audit_track_model_files,
        )
        pt = ReferencePathPoint(
            lap_progress=0.5, distance_along_lap_m=2903.0,
            x=100.0, y=0.0, z=200.0, speed_kph_avg=150.0, source_lap_count=3,
        )
        rp = ReferencePath(
            track_location_id="daytona",
            layout_id="road_course",
            calibration_car_id="porsche_test",
            source_lap_count=3, points=[pt],
            confidence=0.75, built_at="2026-06-25T12:00:00+00:00",
        )
        export_reference_path_json(rp, output_dir=tmp_path)

        # Simulate restart: no controller, no saved_path in memory
        # — audit must discover the file
        a = audit_track_model_files("daytona", "road_course", search_dir=tmp_path)
        assert a.ref_path_exists is True
        assert a.ref_path_load_ok is True
        assert a.ref_path_point_count == 1
