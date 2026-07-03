"""Group 18A — Track Truth Foundation: core model, validation, JSON round-trip.

Scenarios
---------
1.  All 12 public types + guard importable; enums are (str, Enum); no PyQt6 in source.
2.  JSON round-trip: full TrackTruthModel → to_dict → from_dict → equal original.
3a. from_dict with wrong top-level schema → None, no raise.
3b. from_dict(non-dict) → None, no raise.
4.  Validation blocker: non-monotonic station_m.
5.  Validation blocker: station progress_pct outside [0, 100].
6.  Validation blocker: lap_length_m == 0.
7.  Validation blocker: corner window apex outside [start, end].
8.  Validation blocker: complex references missing corner_id "T99".
9.  Validation blocker: sector end_progress_pct > 100.
10. Validation blocker: corners_expected=1 with empty corner_windows.
11. Curvature-unverified: accepted but is_usable_for_live_mapping False.
12. Metadata-only (stations=[]) → NO_COORDINATE_GEOMETRY blocker, exact string, summary no "accepted".
13. Fully valid model → is_accepted, is_usable_for_live_mapping, is_usable_for_ai_corner_context all True.
14. Daytona manifest: availability.seed_geometry is False.
15. Daytona resolve + validate → NO_COORDINATE_GEOMETRY blocker exact string.
16. Daytona T10/T11 complex present in resolved model; no COMPLEX_MISSING_MEMBER for it.
17. Edge: corners_expected=0, no windows, valid stations, seed verified → is_accepted True.
18. resolve_track_truth_model on Daytona does not raise (corrupt/empty geometry handled).
19. AI guard truth table (four cases).
20. AI guard with None → False, no raise (explicit).
21. format_track_truth_status(None, None) → all value keys "—", all color keys "#888888"; 20 keys.
22. format for metadata-only → status_label correct; phrase "lap offset calibration" absent.
23. format for accepted-live-mapping → status_label contains "Live Mapping Ready".
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_minimal_model(
    lap_length_m=1000.0,
    corners_expected=1,
    seed_geometry_available=False,
    corners_are_seed_verified=False,
    stations=None,
    corner_windows=None,
    corner_complexes=None,
    sectors=None,
    pit_lane=None,
):
    from data.track_truth import (
        TrackTruthManifest, TrackTruthModel,
        TrackStation, CornerWindow, CornerComplex, SectorMarker,
    )
    manifest = TrackTruthManifest(
        track_id="test_track",
        layout_id="test_layout",
        display_name="Test Layout",
        lap_length_m=lap_length_m,
        corners_expected=corners_expected,
        seed_geometry_available=seed_geometry_available,
        corners_are_seed_verified=corners_are_seed_verified,
    )
    default_station = TrackStation(
        station_id="s0",
        station_m=0.0,
        progress_pct=0.0,
        x=0.0, y=0.0, z=0.0,
    )
    default_window = CornerWindow(
        corner_id="C1",
        start_progress_pct=10.0,
        apex_progress_pct=15.0,
        end_progress_pct=20.0,
    )
    return TrackTruthModel(
        manifest=manifest,
        corner_windows=corner_windows if corner_windows is not None else [default_window],
        corner_complexes=corner_complexes if corner_complexes is not None else [],
        sectors=sectors if sectors is not None else [],
        stations=stations if stations is not None else [default_station],
        pit_lane=pit_lane,
    )


def _make_valid_accepted_model(
    seed_geometry_available=True,
    corners_are_seed_verified=True,
):
    """Return a model that passes all validation checks."""
    from data.track_truth import (
        TrackTruthManifest, TrackTruthModel,
        TrackStation, CornerWindow, SectorMarker,
    )
    manifest = TrackTruthManifest(
        track_id="test_track",
        layout_id="test_layout",
        display_name="Test Layout",
        lap_length_m=1000.0,
        corners_expected=1,
        seed_geometry_available=seed_geometry_available,
        corners_are_seed_verified=corners_are_seed_verified,
    )
    stations = [
        TrackStation(station_id="s0", station_m=0.0,   progress_pct=0.0,  x=0.0, y=0.0, z=0.0),
        TrackStation(station_id="s1", station_m=100.0, progress_pct=10.0, x=10.0, y=0.0, z=0.0),
        TrackStation(station_id="s2", station_m=200.0, progress_pct=20.0, x=20.0, y=0.0, z=0.0,
                     corner_id="C1", corner_phase="apex", sector_id="S1"),
        TrackStation(station_id="s3", station_m=300.0, progress_pct=30.0, x=30.0, y=0.0, z=0.0),
    ]
    corner_windows = [
        CornerWindow(
            corner_id="C1",
            display_name="Turn 1",
            start_progress_pct=10.0,
            apex_progress_pct=15.0,
            end_progress_pct=20.0,
            sector_id="S1",
        )
    ]
    sectors = [
        SectorMarker(sector_id="S1", start_progress_pct=0.0, end_progress_pct=50.0),
    ]
    return TrackTruthModel(
        manifest=manifest,
        corner_windows=corner_windows,
        corner_complexes=[],
        sectors=sectors,
        stations=stations,
        pit_lane=None,
    )


# ---------------------------------------------------------------------------
# Test 1 — Importability and enum types
# ---------------------------------------------------------------------------

class TestImports:
    def test_1_all_types_importable_and_enums_are_str_enum(self):
        from enum import Enum
        from data.track_truth import (
            TRUTH_MODEL_SCHEMA, TRUTH_MANIFEST_SCHEMA,
            TrackTruthStatus, TrackTruthConfidence, TrackTruthSource,
            TrackTruthValidationIssue,
            TrackStation, CornerWindow, CornerComplex, SectorMarker,
            PitLaneDefinition, TrackTruthManifest, TrackTruthModel,
            TrackTruthValidationResult,
            can_use_track_truth_for_ai_corner_context,
        )
        # 4 enums, 7 dataclasses, 1 guard = 12 types
        assert TRUTH_MODEL_SCHEMA == "track_truth_model_v1"
        assert TRUTH_MANIFEST_SCHEMA == "track_truth_manifest_v1"

        for enum_cls in (TrackTruthStatus, TrackTruthConfidence,
                         TrackTruthSource, TrackTruthValidationIssue):
            assert issubclass(enum_cls, str), f"{enum_cls} must be (str, Enum)"
            assert issubclass(enum_cls, Enum), f"{enum_cls} must be (str, Enum)"
            # enum value accessible as .value
            first = list(enum_cls)[0]
            assert isinstance(first.value, str)

    def test_1_no_pyqt_in_source(self):
        import pathlib
        import re
        src = pathlib.Path("C:/Projects/VR_Dashboard/data/track_truth.py").read_text(encoding="utf-8")
        # Must not have an actual PyQt import statement (docstring mentions are OK)
        has_pyqt_import = bool(re.search(r"^\s*(import|from)\s+PyQt", src, re.MULTILINE))
        assert not has_pyqt_import, "data/track_truth.py must not import PyQt"


# ---------------------------------------------------------------------------
# Test 2 — JSON round-trip
# ---------------------------------------------------------------------------

class TestJsonRoundTrip:
    def test_2_full_model_round_trips(self):
        import tempfile
        from pathlib import Path
        from data.track_truth import (
            TrackTruthManifest, TrackTruthModel,
            TrackStation, CornerWindow, CornerComplex, SectorMarker,
            PitLaneDefinition,
            track_truth_model_to_dict, track_truth_model_from_dict,
            export_track_truth_model_json, import_track_truth_model_json,
        )

        manifest = TrackTruthManifest(
            track_id="daytona",
            layout_id="daytona__road",
            display_name="Daytona Road Course",
            lap_length_m=5729.0,
            corners_expected=2,
            seed_geometry_available=False,
            corners_are_seed_verified=False,
            source="estimated",
            confidence="low",
        )
        stations = [
            TrackStation(station_id="s0", station_m=0.0,   progress_pct=0.0,   x=100.0, y=5.0, z=-200.0,
                         heading_rad=0.1, curvature=0.01, left_width_m=4.0, right_width_m=4.0,
                         corner_id="T1", corner_phase="entry", complex_id="BusStop",
                         sector_id="S1", pit_context=None),
            TrackStation(station_id="s1", station_m=100.0, progress_pct=1.74,  x=110.0, y=5.0, z=-200.0),
        ]
        corner_windows = [
            CornerWindow(corner_id="T1", display_name="T1 Bus Stop Entry",
                         start_progress_pct=5.5, apex_progress_pct=8.2, end_progress_pct=11.0,
                         corner_type="chicane", expected_gear_min=3, expected_gear_max=4,
                         direction="left", sector_id="S1", source="estimated", confidence="low",
                         notes="Estimated from layout"),
        ]
        corner_complexes = [
            CornerComplex(complex_id="BusStop", display_name="Bus Stop Chicane",
                          corner_ids=["T1", "T2"],
                          start_progress_pct=5.5, end_progress_pct=15.0,
                          coaching_name="Bus Stop", sector_id="S1",
                          notes="T1 and T2"),
        ]
        # T2 also needed so complex doesn't trigger missing-member
        corner_windows.append(
            CornerWindow(corner_id="T2", display_name="T2 Bus Stop Exit",
                         start_progress_pct=11.0, apex_progress_pct=12.8, end_progress_pct=15.0)
        )
        sectors = [
            SectorMarker(sector_id="S1", start_progress_pct=0.0, end_progress_pct=33.0,
                         display_name="Sector 1", source="estimated", confidence="low"),
        ]
        pit_lane = PitLaneDefinition(
            entry_start_progress_pct=95.0,
            entry_end_progress_pct=97.0,
            lane_start_progress_pct=97.0,
            lane_end_progress_pct=99.0,
            exit_start_progress_pct=99.0,
            exit_end_progress_pct=100.0,
            notes="Pit lane test",
        )
        model = TrackTruthModel(
            manifest=manifest,
            corner_windows=corner_windows,
            corner_complexes=corner_complexes,
            sectors=sectors,
            stations=stations,
            pit_lane=pit_lane,
        )

        # Dict round-trip
        d = track_truth_model_to_dict(model)
        restored = track_truth_model_from_dict(d)
        assert restored is not None
        assert restored.manifest.track_id == model.manifest.track_id
        assert restored.manifest.lap_length_m == model.manifest.lap_length_m
        assert restored.manifest.corners_expected == model.manifest.corners_expected
        assert restored.manifest.seed_geometry_available == model.manifest.seed_geometry_available
        assert len(restored.stations) == 2
        assert restored.stations[0].station_id == "s0"
        assert restored.stations[0].corner_id == "T1"
        assert restored.stations[0].pit_context is None
        assert len(restored.corner_windows) == 2
        assert restored.corner_windows[0].expected_gear_min == 3
        assert len(restored.corner_complexes) == 1
        assert restored.corner_complexes[0].corner_ids == ["T1", "T2"]
        assert len(restored.sectors) == 1
        assert restored.pit_lane is not None
        assert restored.pit_lane.notes == "Pit lane test"

        # File round-trip
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "truth.json"
            export_track_truth_model_json(model, p)
            file_restored = import_track_truth_model_json(p)
            assert file_restored is not None
            assert file_restored.manifest.track_id == "daytona"


# ---------------------------------------------------------------------------
# Test 3 — from_dict guard
# ---------------------------------------------------------------------------

class TestFromDictGuard:
    def test_3a_wrong_schema_returns_none(self):
        from data.track_truth import track_truth_model_from_dict
        result = track_truth_model_from_dict({"schema": "wrong_schema_xyz", "manifest": {}})
        assert result is None

    def test_3b_non_dict_returns_none(self):
        from data.track_truth import track_truth_model_from_dict
        for bad in (None, "string", 42, [], True):
            result = track_truth_model_from_dict(bad)
            assert result is None, f"Expected None for input {bad!r}"


# ---------------------------------------------------------------------------
# Tests 4–10 — Validation blockers
# ---------------------------------------------------------------------------

class TestValidationBlockers:

    def test_4_non_monotonic_stations(self):
        from data.track_truth import (
            TrackStation, validate_track_truth_model, TrackTruthValidationIssue,
        )
        stations = [
            TrackStation(station_id="s0", station_m=0.0,   progress_pct=0.0),
            TrackStation(station_id="s1", station_m=100.0, progress_pct=10.0),
            TrackStation(station_id="s2", station_m=50.0,  progress_pct=5.0),   # non-monotonic
        ]
        model = _make_minimal_model(stations=stations, corner_windows=[])
        result = validate_track_truth_model(model)
        assert result.is_accepted is False
        assert len(result.blockers) >= 1
        assert TrackTruthValidationIssue.NON_MONOTONIC_STATIONS.value in result.issues

    def test_5_station_progress_out_of_range(self):
        from data.track_truth import (
            TrackStation, validate_track_truth_model, TrackTruthValidationIssue,
        )
        stations = [
            TrackStation(station_id="s0", station_m=0.0,   progress_pct=0.0),
            TrackStation(station_id="s1", station_m=100.0, progress_pct=101.0),  # > 100
        ]
        model = _make_minimal_model(stations=stations, corner_windows=[])
        result = validate_track_truth_model(model)
        assert result.is_accepted is False
        assert len(result.blockers) >= 1
        assert TrackTruthValidationIssue.PROGRESS_OUT_OF_RANGE.value in result.issues

    def test_6_lap_length_zero(self):
        from data.track_truth import validate_track_truth_model, TrackTruthValidationIssue
        model = _make_minimal_model(lap_length_m=0.0)
        result = validate_track_truth_model(model)
        assert result.is_accepted is False
        assert len(result.blockers) >= 1
        assert TrackTruthValidationIssue.LAP_LENGTH_ZERO_OR_NEG.value in result.issues

    def test_7_apex_outside_corner_window(self):
        from data.track_truth import (
            CornerWindow, TrackStation, validate_track_truth_model,
            TrackTruthValidationIssue,
        )
        # apex (5%) is outside [10%, 20%]
        windows = [
            CornerWindow(corner_id="C1", start_progress_pct=10.0, apex_progress_pct=5.0, end_progress_pct=20.0)
        ]
        stations = [
            TrackStation(station_id="s0", station_m=0.0,   progress_pct=0.0),
            TrackStation(station_id="s1", station_m=100.0, progress_pct=10.0),
        ]
        model = _make_minimal_model(stations=stations, corner_windows=windows)
        result = validate_track_truth_model(model)
        assert result.is_accepted is False
        assert len(result.blockers) >= 1
        assert TrackTruthValidationIssue.APEX_OUTSIDE_WINDOW.value in result.issues

    def test_8_complex_references_missing_corner(self):
        from data.track_truth import (
            CornerWindow, CornerComplex, TrackStation, validate_track_truth_model,
            TrackTruthValidationIssue,
        )
        windows = [
            CornerWindow(corner_id="C1", start_progress_pct=10.0, apex_progress_pct=15.0, end_progress_pct=20.0)
        ]
        complexes = [
            CornerComplex(complex_id="CX1", display_name="Complex 1",
                          corner_ids=["C1", "T99"])  # "T99" not in windows
        ]
        stations = [
            TrackStation(station_id="s0", station_m=0.0,   progress_pct=0.0),
            TrackStation(station_id="s1", station_m=100.0, progress_pct=10.0),
        ]
        model = _make_minimal_model(stations=stations, corner_windows=windows, corner_complexes=complexes)
        result = validate_track_truth_model(model)
        assert result.is_accepted is False
        assert len(result.blockers) >= 1
        assert TrackTruthValidationIssue.COMPLEX_MISSING_MEMBER.value in result.issues

    def test_9_sector_progress_out_of_range(self):
        from data.track_truth import (
            SectorMarker, TrackStation, validate_track_truth_model,
            TrackTruthValidationIssue,
        )
        sectors = [
            SectorMarker(sector_id="S1", start_progress_pct=0.0, end_progress_pct=105.0)  # > 100
        ]
        stations = [
            TrackStation(station_id="s0", station_m=0.0,   progress_pct=0.0),
            TrackStation(station_id="s1", station_m=100.0, progress_pct=10.0),
        ]
        model = _make_minimal_model(stations=stations, sectors=sectors, corner_windows=[])
        result = validate_track_truth_model(model)
        assert result.is_accepted is False
        assert len(result.blockers) >= 1
        assert TrackTruthValidationIssue.SECTOR_PROGRESS_OUT_RANGE.value in result.issues

    def test_10_corners_expected_but_no_windows(self):
        from data.track_truth import (
            TrackStation, validate_track_truth_model, TrackTruthValidationIssue,
        )
        stations = [
            TrackStation(station_id="s0", station_m=0.0,   progress_pct=0.0),
            TrackStation(station_id="s1", station_m=100.0, progress_pct=10.0),
        ]
        # corners_expected=1 but corner_windows=[]
        model = _make_minimal_model(stations=stations, corner_windows=[], corners_expected=1)
        result = validate_track_truth_model(model)
        assert result.is_accepted is False
        assert len(result.blockers) >= 1
        assert TrackTruthValidationIssue.CORNERS_EXPECTED_NO_WINDOWS.value in result.issues


# ---------------------------------------------------------------------------
# Test 11 — Curvature-unverified
# ---------------------------------------------------------------------------

class TestCurvatureUnverified:
    def test_11_accepted_but_not_usable_for_live_mapping(self):
        from data.track_truth import validate_track_truth_model
        # corners_are_seed_verified=False → not usable for live mapping or AI
        model = _make_valid_accepted_model(
            seed_geometry_available=True,
            corners_are_seed_verified=False,
        )
        result = validate_track_truth_model(model)
        # No blockers (apart from missing coordinate geometry if stations empty)
        # The model has stations, so the geometry blocker won't fire.
        # But corners_are_seed_verified=False → is_usable_for_live_mapping=False
        assert result.is_usable_for_live_mapping is False
        assert result.is_usable_for_ai_corner_context is False


# ---------------------------------------------------------------------------
# Test 12 — Metadata-only (no stations)
# ---------------------------------------------------------------------------

class TestMetadataOnly:
    def test_12_metadata_only_blockers_and_summary(self):
        from data.track_truth import (
            validate_track_truth_model, TrackTruthValidationIssue, TrackTruthStatus,
        )
        _NO_GEO_BLOCKER = (
            "Coordinate geometry unavailable — high-confidence corner mapping is blocked"
        )
        model = _make_minimal_model(stations=[], corner_windows=[])
        result = validate_track_truth_model(model)
        assert result.is_accepted is False
        assert result.is_usable_for_live_mapping is False
        # NO_COORDINATE_GEOMETRY blocker
        assert TrackTruthValidationIssue.NO_COORDINATE_GEOMETRY.value in result.issues
        # Exact blocker string
        assert any(_NO_GEO_BLOCKER in b for b in result.blockers), (
            f"Expected exact blocker string not found in: {result.blockers}"
        )
        # status is METADATA_ONLY
        assert result.status == TrackTruthStatus.METADATA_ONLY
        # summary must NOT contain "accepted" (case-insensitive)
        assert "accepted" not in result.summary.lower(), (
            f"summary must not contain 'accepted' when not accepted; got: {result.summary!r}"
        )


# ---------------------------------------------------------------------------
# Test 13 — Fully valid model
# ---------------------------------------------------------------------------

class TestFullyValid:
    def test_13_fully_valid_all_flags_true(self):
        from data.track_truth import validate_track_truth_model
        model = _make_valid_accepted_model(
            seed_geometry_available=True,
            corners_are_seed_verified=True,
        )
        result = validate_track_truth_model(model)
        assert result.is_accepted is True, f"Expected accepted; blockers={result.blockers}"
        assert result.is_usable_for_live_mapping is True
        assert result.is_usable_for_ai_corner_context is True
        assert len(result.blockers) == 0


# ---------------------------------------------------------------------------
# Tests 14–16 — Daytona track library integration
# ---------------------------------------------------------------------------

class TestDaytonaLibrary:

    def test_14_daytona_manifest_seed_geometry_false(self):
        from data.track_library import resolve_track_layout_manifest
        manifest = resolve_track_layout_manifest(
            "daytona_international_speedway",
            "daytona_international_speedway__road_course",
        )
        assert manifest is not None, "Daytona manifest must load"
        assert manifest.availability.seed_geometry is False

    def test_15_daytona_resolve_and_validate_has_no_geometry_blocker(self):
        from data.track_truth import (
            resolve_track_truth_model, validate_track_truth_model,
            TrackTruthValidationIssue,
        )
        _NO_GEO_BLOCKER = (
            "Coordinate geometry unavailable — high-confidence corner mapping is blocked"
        )
        model = resolve_track_truth_model(
            "daytona_international_speedway",
            "daytona_international_speedway__road_course",
        )
        assert model is not None, "resolve_track_truth_model must return a model for Daytona"
        result = validate_track_truth_model(model)
        # Daytona has no seed geometry → stations empty → NO_COORDINATE_GEOMETRY blocker
        assert TrackTruthValidationIssue.NO_COORDINATE_GEOMETRY.value in result.issues
        assert any(_NO_GEO_BLOCKER in b for b in result.blockers)

    def test_16_daytona_t10t11_complex_present_no_missing_member(self):
        from data.track_truth import (
            resolve_track_truth_model, validate_track_truth_model,
            TrackTruthValidationIssue,
        )
        model = resolve_track_truth_model(
            "daytona_international_speedway",
            "daytona_international_speedway__road_course",
        )
        assert model is not None
        # Find the T10T11 complex
        t10t11 = next(
            (cc for cc in model.corner_complexes if "T10" in cc.corner_ids and "T11" in cc.corner_ids),
            None,
        )
        assert t10t11 is not None, "T10T11 complex not found in resolved Daytona model"
        # Ensure no COMPLEX_MISSING_MEMBER blocker in validation issues
        result = validate_track_truth_model(model)
        assert TrackTruthValidationIssue.COMPLEX_MISSING_MEMBER.value not in result.issues, (
            f"COMPLEX_MISSING_MEMBER should not fire for T10T11; issues={result.issues}"
        )


# ---------------------------------------------------------------------------
# Test 17 — Edge: corners_expected=0, no windows, valid stations
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_17_zero_corners_expected_no_windows_is_accepted(self):
        from data.track_truth import (
            TrackStation, validate_track_truth_model,
        )
        stations = [
            TrackStation(station_id="s0", station_m=0.0,   progress_pct=0.0,  x=0.0, z=0.0),
            TrackStation(station_id="s1", station_m=100.0, progress_pct=10.0, x=10.0, z=0.0),
            TrackStation(station_id="s2", station_m=200.0, progress_pct=20.0, x=20.0, z=0.0),
        ]
        model = _make_minimal_model(
            stations=stations,
            corner_windows=[],
            corners_expected=0,
            seed_geometry_available=True,
            corners_are_seed_verified=True,
        )
        result = validate_track_truth_model(model)
        assert result.is_accepted is True, (
            f"corners_expected=0 + no windows should be accepted; blockers={result.blockers}"
        )

    def test_18_resolve_daytona_does_not_raise(self):
        from data.track_truth import resolve_track_truth_model
        # Daytona has no seed geometry — must not raise; returns model with empty stations
        model = resolve_track_truth_model(
            "daytona_international_speedway",
            "daytona_international_speedway__road_course",
        )
        assert model is not None
        # Stations should be empty (no seed geometry file)
        assert len(model.stations) == 0


# ---------------------------------------------------------------------------
# Tests 19–20 — AI guard truth table
# ---------------------------------------------------------------------------

class TestAiGuard:
    def test_19_ai_guard_truth_table(self):
        from data.track_truth import (
            validate_track_truth_model, can_use_track_truth_for_ai_corner_context,
        )
        # Case 1: None → False
        assert can_use_track_truth_for_ai_corner_context(None) is False

        # Case 2: result with is_accepted=False → False
        model_bad = _make_minimal_model(stations=[], corner_windows=[])
        result_bad = validate_track_truth_model(model_bad)
        assert result_bad.is_accepted is False
        assert can_use_track_truth_for_ai_corner_context(result_bad) is False

        # Case 3: accepted but not usable for AI corner context → False
        model_mid = _make_valid_accepted_model(
            seed_geometry_available=False,
            corners_are_seed_verified=True,
        )
        result_mid = validate_track_truth_model(model_mid)
        # is_usable_for_ai_corner_context requires seed_geometry_available=True
        assert result_mid.is_usable_for_ai_corner_context is False
        assert can_use_track_truth_for_ai_corner_context(result_mid) is False

        # Case 4: fully valid → True
        model_ok = _make_valid_accepted_model(
            seed_geometry_available=True,
            corners_are_seed_verified=True,
        )
        result_ok = validate_track_truth_model(model_ok)
        assert result_ok.is_usable_for_ai_corner_context is True
        assert can_use_track_truth_for_ai_corner_context(result_ok) is True

    def test_20_ai_guard_none_returns_false_no_raise(self):
        from data.track_truth import can_use_track_truth_for_ai_corner_context
        result = can_use_track_truth_for_ai_corner_context(None)
        assert result is False


# ---------------------------------------------------------------------------
# Tests 21–23 — VM: format_track_truth_status
# ---------------------------------------------------------------------------

class TestFormatTrackTruthStatus:
    _ALL_KEYS = {
        "track_id", "layout_id",
        "library_availability", "library_availability_color",
        "seed_geometry", "seed_geometry_color",
        "corner_metadata", "corner_metadata_color",
        "complex_metadata", "complex_metadata_color",
        "geometry_acceptance", "geometry_acceptance_color",
        "live_mapping_ready", "live_mapping_ready_color",
        "ai_context_ready", "ai_context_ready_color",
        "blockers", "warnings",
        "status_label", "status_color",
    }

    def test_21_none_model_all_dash_and_grey(self):
        from ui.track_modelling_vm import format_track_truth_status
        result = format_track_truth_status(None, None)
        assert set(result.keys()) == self._ALL_KEYS, (
            f"Expected 20 keys, got {len(result.keys())}: {result.keys()}"
        )
        color_keys = {k for k in self._ALL_KEYS if k.endswith("_color")}
        value_keys = self._ALL_KEYS - color_keys
        for k in value_keys:
            assert result[k] == "—", f"Key {k!r} should be '—' when model=None, got {result[k]!r}"
        for k in color_keys:
            assert result[k] == "#888888", (
                f"Key {k!r} should be '#888888' when model=None, got {result[k]!r}"
            )

    def test_22_metadata_only_status_label_and_no_lap_offset_phrase(self):
        from data.track_truth import validate_track_truth_model
        from ui.track_modelling_vm import format_track_truth_status
        # Metadata-only: no stations
        model = _make_minimal_model(stations=[], corner_windows=[])
        validation = validate_track_truth_model(model)
        result = format_track_truth_status(model, validation)
        assert result["status_label"] == "Metadata only — no coordinate geometry", (
            f"Unexpected status_label: {result['status_label']!r}"
        )
        for v in result.values():
            assert "lap offset calibration" not in v.lower(), (
                f"Phrase 'lap offset calibration' must not appear; found in: {v!r}"
            )

    def test_23_accepted_live_mapping_status_label(self):
        from data.track_truth import validate_track_truth_model
        from ui.track_modelling_vm import format_track_truth_status
        model = _make_valid_accepted_model(
            seed_geometry_available=True,
            corners_are_seed_verified=True,
        )
        validation = validate_track_truth_model(model)
        result = format_track_truth_status(model, validation)
        assert "Live Mapping Ready" in result["status_label"], (
            f"Expected 'Live Mapping Ready' in status_label, got: {result['status_label']!r}"
        )


# ---------------------------------------------------------------------------
# Test 24 — Regression: rejected model with corner_windows must NOT be
#           CURVATURE_PROVISIONAL or any accepted state
# ---------------------------------------------------------------------------

class TestRejectedModelStatusNotProvisional:
    def test_24_rejected_model_status_not_provisional(self):
        """A model with corner_windows + stations but a blocker (non-monotonic station_m)
        must yield is_accepted=False and status must NOT be CURVATURE_PROVISIONAL or
        any ACCEPTED_* state — it must be NO_DATA (or METADATA_ONLY if stations empty,
        which this case is not)."""
        from data.track_truth import (
            TrackStation, validate_track_truth_model,
            TrackTruthStatus,
        )
        # Non-monotonic stations → blocker → is_accepted=False
        stations = [
            TrackStation(station_id="s0", station_m=0.0,   progress_pct=0.0),
            TrackStation(station_id="s1", station_m=200.0, progress_pct=20.0),
            TrackStation(station_id="s2", station_m=100.0, progress_pct=10.0),  # non-monotonic
        ]
        # corner_windows present + corners_are_seed_verified=False
        model = _make_minimal_model(
            stations=stations,
            corners_are_seed_verified=False,
        )
        result = validate_track_truth_model(model)

        assert result.is_accepted is False, (
            f"Expected is_accepted=False; blockers={result.blockers}"
        )

        _accepted_statuses = {
            TrackTruthStatus.CURVATURE_PROVISIONAL,
            TrackTruthStatus.ACCEPTED_SEED_MAP,
            TrackTruthStatus.ACCEPTED_LIVE_MAPPING,
        }
        assert result.status not in _accepted_statuses, (
            f"Rejected model must not have an accepted/provisional status; "
            f"got status={result.status!r}"
        )
        # Must be the non-usable fallback (stations present but validation failed)
        assert result.status == TrackTruthStatus.NO_DATA, (
            f"Expected NO_DATA for rejected model with stations; got {result.status!r}"
        )
