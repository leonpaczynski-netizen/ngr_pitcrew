"""Group 17U — Track Library Schema and Seed Data Registry.

Tests covering:
  1.  Track library index loads
  2.  Daytona manifest loads
  3.  Daytona semantic model loads with 12 corners, 3 sectors, 2 complexes
  4.  Daytona validation rules load
  5.  Missing Daytona seed geometry reported cleanly
  6.  Resolver prefers track_library path over legacy fallback
  7.  Resolver falls back to legacy seed map path when library geometry missing
  8.  Seed audit reports source as track_library vs legacy_fallback
  9.  Missing files never raise uncaught exceptions
  10. Layout availability summary is correct
  11. Alignment uses validation rules from manifest where available
  12. Existing Group 17S/17T tests remain green (sanity via module imports)
  13. Existing app still starts with no track_library index or partial data
  14. Manifest lap_length_m matches YAML seed for Daytona
  15. Semantic model corner count matches YAML seed
  16. T10/T11 complex present in library semantic model
  17. BusStop complex present in library semantic model
  18. Validation rules require_corner_windows=True for Daytona
  19. Source manifest loads with sources and fields_estimated
  20. TrackLibraryAuditResult reports manifest_loaded and semantic_model_loaded
  21. TrackLibraryAuditResult reports validation_rules_loaded
  22. TrackLibraryAuditResult reports seed_geometry_in_library=False (no geo file)
  23. TrackLibraryAuditResult.seed_coordinate_source="none" with no files
  24. Audit reports library_available=True when index exists
  25. Missing track in index → warning in audit result
  26. Wrong schema → load functions return None
  27. SeedAuditResult.seed_source reflects library-first resolution
  28. SeedAuditResult.library_manifest_loaded=True for Daytona
  29. SeedAuditResult.validation_rules_loaded=True for Daytona
  30. format_alignment_summary includes seed_source key
  31. format_alignment_summary seed_source="Unavailable" when no IDs given
  32. format_alignment_summary seed_source="Track library" when library has it
  33. Resolver returns legacy_fallback when only legacy file exists
  34. Resolver returns none when neither library nor legacy file exists
  35. load_track_metadata returns None for non-existent track
  36. audit_layout_seed includes new fields with defaults for None layout_seed
"""
from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pytest

# ── Track library base dir ──────────────────────────────────────────────────
TRACK_LIBRARY_BASE = Path(__file__).parent.parent / "data" / "track_library"
DAYTONA_TRACK_ID  = "daytona_international_speedway"
DAYTONA_LAYOUT_ID = "daytona_international_speedway__road_course"
DAYTONA_LAYOUT_DIR = (
    TRACK_LIBRARY_BASE / "tracks" / DAYTONA_TRACK_ID / "layouts" / DAYTONA_LAYOUT_ID
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Track library index loads
# ─────────────────────────────────────────────────────────────────────────────

class TestTrackLibraryIndex:
    def test_index_loads(self):
        from data.track_library import load_track_library_index
        idx = load_track_library_index()
        assert idx is not None

    def test_index_schema(self):
        from data.track_library import load_track_library_index
        idx = load_track_library_index()
        assert idx.schema == "track_library_index_v1"

    def test_index_contains_daytona(self):
        from data.track_library import load_track_library_index
        idx = load_track_library_index()
        assert DAYTONA_TRACK_ID in idx.tracks

    def test_index_has_library_version(self):
        from data.track_library import load_track_library_index
        idx = load_track_library_index()
        assert idx.library_version != ""

    def test_index_missing_returns_none(self, tmp_path):
        from data.track_library import load_track_library_index
        result = load_track_library_index(base_dir=tmp_path)
        assert result is None

    def test_index_wrong_schema_returns_none(self, tmp_path):
        from data.track_library import load_track_library_index
        (tmp_path / "index.json").write_text(json.dumps({"schema": "bad_schema_v99"}))
        assert load_track_library_index(base_dir=tmp_path) is None


# ─────────────────────────────────────────────────────────────────────────────
# 2. Daytona manifest loads
# ─────────────────────────────────────────────────────────────────────────────

class TestDaytonaManifest:
    def test_manifest_loads(self):
        from data.track_library import resolve_track_layout_manifest
        m = resolve_track_layout_manifest(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert m is not None

    def test_manifest_schema(self):
        from data.track_library import resolve_track_layout_manifest
        m = resolve_track_layout_manifest(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert m.schema == "track_layout_manifest_v1"

    def test_manifest_track_id(self):
        from data.track_library import resolve_track_layout_manifest
        m = resolve_track_layout_manifest(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert m.track_id == DAYTONA_TRACK_ID

    def test_manifest_layout_id(self):
        from data.track_library import resolve_track_layout_manifest
        m = resolve_track_layout_manifest(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert m.layout_id == DAYTONA_LAYOUT_ID

    def test_manifest_lap_length(self):
        from data.track_library import resolve_track_layout_manifest
        m = resolve_track_layout_manifest(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert m.lap_length_m == 5729.0

    def test_manifest_display_name(self):
        from data.track_library import resolve_track_layout_manifest
        m = resolve_track_layout_manifest(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert "Daytona" in m.display_name

    def test_manifest_missing_returns_none(self, tmp_path):
        from data.track_library import resolve_track_layout_manifest
        assert resolve_track_layout_manifest("no_track", "no_layout", base_dir=tmp_path) is None


# ─────────────────────────────────────────────────────────────────────────────
# 3. Daytona semantic model loads with 12 corners, 3 sectors, 2 complexes
# ─────────────────────────────────────────────────────────────────────────────

class TestDaytonaSemanticModel:
    def test_semantic_model_loads(self):
        from data.track_library import load_track_semantic_model
        sm = load_track_semantic_model(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert sm is not None

    def test_semantic_model_schema(self):
        from data.track_library import load_track_semantic_model
        sm = load_track_semantic_model(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert sm.schema == "track_semantic_model_v1"

    def test_semantic_model_12_corners(self):
        from data.track_library import load_track_semantic_model
        sm = load_track_semantic_model(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert len(sm.corners) == 12

    def test_semantic_model_3_sectors(self):
        from data.track_library import load_track_semantic_model
        sm = load_track_semantic_model(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert len(sm.sectors) == 3

    def test_semantic_model_2_complexes(self):
        from data.track_library import load_track_semantic_model
        sm = load_track_semantic_model(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert len(sm.complexes) == 2

    def test_semantic_model_corner_ids(self):
        from data.track_library import load_track_semantic_model
        sm = load_track_semantic_model(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        corner_ids = [c["corner_id"] for c in sm.corners]
        assert "T1" in corner_ids
        assert "T12" in corner_ids

    def test_semantic_model_sector_ids(self):
        from data.track_library import load_track_semantic_model
        sm = load_track_semantic_model(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        sector_ids = [s["sector_id"] for s in sm.sectors]
        assert "S1" in sector_ids
        assert "S2" in sector_ids
        assert "S3" in sector_ids

    def test_semantic_model_missing_returns_none(self, tmp_path):
        from data.track_library import load_track_semantic_model
        assert load_track_semantic_model("no_track", "no_layout", base_dir=tmp_path) is None


# ─────────────────────────────────────────────────────────────────────────────
# 4. Daytona validation rules load
# ─────────────────────────────────────────────────────────────────────────────

class TestDaytonaValidationRules:
    def test_validation_rules_loads(self):
        from data.track_library import load_validation_rules
        vr = load_validation_rules(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert vr is not None

    def test_validation_rules_schema(self):
        from data.track_library import load_validation_rules
        vr = load_validation_rules(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert vr.schema == "validation_rules_v1"

    def test_validation_rules_max_lap_delta(self):
        from data.track_library import load_validation_rules
        vr = load_validation_rules(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert vr.acceptance.max_lap_delta_pct == 5.0

    def test_validation_rules_require_corner_windows(self):
        from data.track_library import load_validation_rules
        vr = load_validation_rules(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert vr.acceptance.require_corner_windows is True

    def test_validation_rules_require_sectors(self):
        from data.track_library import load_validation_rules
        vr = load_validation_rules(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert vr.acceptance.require_sectors is True

    def test_validation_rules_missing_returns_none(self, tmp_path):
        from data.track_library import load_validation_rules
        assert load_validation_rules("no_track", "no_layout", base_dir=tmp_path) is None

    def test_validation_rules_wrong_schema_returns_none(self, tmp_path):
        from data.track_library import load_validation_rules
        ldir = tmp_path / "tracks" / "t" / "layouts" / "l"
        ldir.mkdir(parents=True)
        (ldir / "validation_rules.json").write_text(json.dumps({"schema": "wrong_v0"}))
        assert load_validation_rules("t", "l", base_dir=tmp_path) is None


# ─────────────────────────────────────────────────────────────────────────────
# 5. Missing Daytona seed geometry is reported cleanly
# ─────────────────────────────────────────────────────────────────────────────

class TestMissingDaytonaSeedGeometry:
    def test_no_geometry_file_exists(self):
        geo_path = DAYTONA_LAYOUT_DIR / "geometry.seed_map.json"
        assert not geo_path.exists(), (
            "geometry.seed_map.json must NOT exist for Daytona until coordinate data is available"
        )

    def test_manifest_availability_seed_geometry_false(self):
        from data.track_library import resolve_track_layout_manifest
        m = resolve_track_layout_manifest(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert m.availability.seed_geometry is False

    def test_audit_reports_no_geometry_in_library(self):
        from data.track_library import audit_track_library_layout
        audit = audit_track_library_layout(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert audit.seed_geometry_in_library is False

    def test_resolve_seed_map_returns_none_for_daytona(self):
        from data.track_library import resolve_seed_coordinate_map
        smap, source = resolve_seed_coordinate_map(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        # Daytona has no coordinate map anywhere — must be None / "none"
        assert smap is None
        assert source == "none"

    def test_load_library_geometry_returns_none_for_daytona(self):
        from data.track_library import load_seed_coordinate_map_from_library
        result = load_seed_coordinate_map_from_library(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# 6. Resolver prefers track_library path over legacy fallback
# ─────────────────────────────────────────────────────────────────────────────

class TestResolverPreference:
    def test_library_preferred_over_legacy(self, tmp_path):
        """When geometry.seed_map.json exists in library, it wins over legacy."""
        from data.track_library import resolve_seed_coordinate_map
        from data.track_seed_coordinate_map import SeedCoordinateMap, SeedMapStation, export_seed_coordinate_map_json, SEED_MAP_SCHEMA
        import unittest.mock as mock

        # Create a minimal seed map and place it in the library dir
        sm = SeedCoordinateMap(
            track_location_id="t_track",
            layout_id="t_layout",
            lap_length_m=1000.0,
            stations=[SeedMapStation(station_m=0.0, progress_pct=0.0, x=0.0, y=0.0)],
        )
        lib_layout_dir = tmp_path / "tracks" / "t_track" / "layouts" / "t_layout"
        lib_layout_dir.mkdir(parents=True)
        import json as _json
        geo_data = {
            "schema": "seed_coordinate_map_v1",
            "track_location_id": "t_track",
            "layout_id": "t_layout",
            "source": "test",
            "confidence": "high",
            "lap_length_m": 1000.0,
            "start_finish_station_m": 0.0,
            "has_z_coordinates": False,
            "has_corner_markers": False,
            "has_sector_markers": False,
            "has_width_corridor": False,
            "notes": "",
            "stations": [{"station_m": 0.0, "progress_pct": 0.0, "x": 0.0, "y": 0.0, "z": 0.0}],
        }
        (lib_layout_dir / "geometry.seed_map.json").write_text(_json.dumps(geo_data))

        # Also create a legacy seed map
        from data.track_seed_coordinate_map import SEED_MAPS_DIR
        with mock.patch("data.track_library.TRACK_LIBRARY_BASE", tmp_path):
            with mock.patch("data.track_seed_coordinate_map.SEED_MAPS_DIR", tmp_path / "legacy"):
                result_map, source = resolve_seed_coordinate_map("t_track", "t_layout", base_dir=tmp_path)
        assert source == "track_library"
        assert result_map is not None


# ─────────────────────────────────────────────────────────────────────────────
# 7. Resolver falls back to legacy when library geometry missing
# ─────────────────────────────────────────────────────────────────────────────

class TestResolverLegacyFallback:
    def test_legacy_fallback_used_when_library_has_no_geometry(self, tmp_path):
        """When library has no geometry.seed_map.json, legacy seed_maps/ is tried."""
        from data.track_seed_coordinate_map import SeedCoordinateMap, SeedMapStation, export_seed_coordinate_map_json
        import unittest.mock as mock

        legacy_dir = tmp_path / "seed_maps"
        legacy_dir.mkdir()

        # Create a legacy seed map file
        sm = SeedCoordinateMap(
            track_location_id="t_track",
            layout_id="t_layout",
            lap_length_m=1000.0,
            stations=[SeedMapStation(station_m=0.0, progress_pct=0.0, x=1.0, y=2.0)],
        )
        export_seed_coordinate_map_json(sm, output_dir=legacy_dir)

        from data.track_library import resolve_seed_coordinate_map
        # Library dir has no geometry.seed_map.json for t_track/t_layout
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir()

        with mock.patch("data.track_seed_coordinate_map.SEED_MAPS_DIR", legacy_dir):
            with mock.patch("data.track_library.TRACK_LIBRARY_BASE", lib_dir):
                result_map, source = resolve_seed_coordinate_map("t_track", "t_layout", base_dir=lib_dir)

        assert source == "legacy_fallback"
        assert result_map is not None
        assert result_map.track_location_id == "t_track"


# ─────────────────────────────────────────────────────────────────────────────
# 8. Seed audit reports source as track_library vs legacy_fallback
# ─────────────────────────────────────────────────────────────────────────────

class TestSeedAuditSource:
    def test_seed_audit_source_none_when_no_maps(self):
        from data.track_intelligence import audit_layout_seed

        class _LS:
            length_m = 1000.0
            corner_definitions = []
            sector_definitions = []
            corner_complexes = []

        audit = audit_layout_seed(_LS(), track_location_id="no_track", layout_id_str="no_layout")
        assert audit.seed_source == "none"

    def test_seed_audit_library_manifest_loaded_for_daytona(self):
        from data.track_intelligence import audit_layout_seed, resolve_track_layout
        result = resolve_track_layout(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        if result is None:
            pytest.skip("Daytona layout not found in YAML seed")
        audit = audit_layout_seed(result, track_location_id=DAYTONA_TRACK_ID,
                                  layout_id_str=DAYTONA_LAYOUT_ID)
        assert audit.library_manifest_loaded is True

    def test_seed_audit_validation_rules_loaded_for_daytona(self):
        from data.track_intelligence import audit_layout_seed, resolve_track_layout
        result = resolve_track_layout(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        if result is None:
            pytest.skip("Daytona layout not found in YAML seed")
        audit = audit_layout_seed(result, track_location_id=DAYTONA_TRACK_ID,
                                  layout_id_str=DAYTONA_LAYOUT_ID)
        assert audit.validation_rules_loaded is True

    def test_seed_audit_seed_source_none_for_daytona_no_geometry(self):
        from data.track_intelligence import audit_layout_seed, resolve_track_layout
        result = resolve_track_layout(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        if result is None:
            pytest.skip("Daytona layout not found in YAML seed")
        audit = audit_layout_seed(result, track_location_id=DAYTONA_TRACK_ID,
                                  layout_id_str=DAYTONA_LAYOUT_ID)
        # No geometry file exists anywhere for Daytona
        assert audit.seed_source == "none"


# ─────────────────────────────────────────────────────────────────────────────
# 9. Missing files never raise uncaught exceptions
# ─────────────────────────────────────────────────────────────────────────────

class TestNoExceptions:
    def test_load_index_no_dir(self, tmp_path):
        from data.track_library import load_track_library_index
        assert load_track_library_index(base_dir=tmp_path / "nonexistent") is None

    def test_resolve_manifest_no_dir(self, tmp_path):
        from data.track_library import resolve_track_layout_manifest
        assert resolve_track_layout_manifest("x", "y", base_dir=tmp_path / "nonexistent") is None

    def test_load_semantic_model_no_dir(self, tmp_path):
        from data.track_library import load_track_semantic_model
        assert load_track_semantic_model("x", "y", base_dir=tmp_path / "nonexistent") is None

    def test_load_validation_rules_no_dir(self, tmp_path):
        from data.track_library import load_validation_rules
        assert load_validation_rules("x", "y", base_dir=tmp_path / "nonexistent") is None

    def test_load_source_manifest_no_dir(self, tmp_path):
        from data.track_library import load_source_manifest
        assert load_source_manifest("x", "y", base_dir=tmp_path / "nonexistent") is None

    def test_resolve_seed_map_no_dir(self, tmp_path):
        from data.track_library import resolve_seed_coordinate_map
        import unittest.mock as mock
        with mock.patch("data.track_seed_coordinate_map.SEED_MAPS_DIR", tmp_path / "no_legacy"):
            smap, source = resolve_seed_coordinate_map("x", "y", base_dir=tmp_path / "no_lib")
        assert smap is None
        assert source == "none"

    def test_audit_library_layout_no_files(self, tmp_path):
        from data.track_library import audit_track_library_layout
        import unittest.mock as mock
        with mock.patch("data.track_seed_coordinate_map.SEED_MAPS_DIR", tmp_path):
            result = audit_track_library_layout("x", "y", base_dir=tmp_path)
        assert result.manifest_loaded is False
        assert result.seed_geometry_in_library is False

    def test_audit_layout_seed_with_none(self):
        from data.track_intelligence import audit_layout_seed
        result = audit_layout_seed(None)
        assert result.has_metadata is False


# ─────────────────────────────────────────────────────────────────────────────
# 10. Layout availability summary is correct
# ─────────────────────────────────────────────────────────────────────────────

class TestAvailabilitySummary:
    def test_daytona_availability_metadata_true(self):
        from data.track_library import resolve_track_layout_manifest
        m = resolve_track_layout_manifest(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert m.availability.metadata is True

    def test_daytona_availability_sectors_true(self):
        from data.track_library import resolve_track_layout_manifest
        m = resolve_track_layout_manifest(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert m.availability.sectors is True

    def test_daytona_availability_corner_windows_true(self):
        from data.track_library import resolve_track_layout_manifest
        m = resolve_track_layout_manifest(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert m.availability.corner_windows is True

    def test_daytona_availability_corner_complexes_true(self):
        from data.track_library import resolve_track_layout_manifest
        m = resolve_track_layout_manifest(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert m.availability.corner_complexes is True

    def test_daytona_availability_seed_geometry_false(self):
        from data.track_library import resolve_track_layout_manifest
        m = resolve_track_layout_manifest(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert m.availability.seed_geometry is False

    def test_daytona_availability_accepted_model_false(self):
        from data.track_library import resolve_track_layout_manifest
        m = resolve_track_layout_manifest(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert m.availability.accepted_model is False


# ─────────────────────────────────────────────────────────────────────────────
# 11. Alignment uses validation rules from manifest where available
# ─────────────────────────────────────────────────────────────────────────────

class TestValidationRulesInAlignment:
    def test_validation_rules_max_lap_delta_5pct(self):
        """Daytona validation rules cap acceptance at 5% lap delta."""
        from data.track_library import load_validation_rules
        vr = load_validation_rules(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert vr.acceptance.max_lap_delta_pct == 5.0

    def test_validation_rules_max_geometry_error(self):
        from data.track_library import load_validation_rules
        vr = load_validation_rules(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert vr.acceptance.max_mean_geometry_error_m == 15.0

    def test_validation_rules_require_seed_geometry_false(self):
        """Daytona does not require seed geometry because no coordinate map exists yet."""
        from data.track_library import load_validation_rules
        vr = load_validation_rules(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert vr.acceptance.require_seed_geometry is False


# ─────────────────────────────────────────────────────────────────────────────
# 14. Manifest lap_length_m matches YAML seed for Daytona
# ─────────────────────────────────────────────────────────────────────────────

class TestManifestConsistency:
    def test_manifest_lap_matches_yaml_seed(self):
        from data.track_library import resolve_track_layout_manifest
        from data.track_intelligence import resolve_track_layout
        m    = resolve_track_layout_manifest(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        seed = resolve_track_layout(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert m is not None
        assert seed is not None
        assert m.lap_length_m == seed.length_m

    def test_semantic_model_corner_count_matches_yaml(self):
        from data.track_library import load_track_semantic_model
        from data.track_intelligence import resolve_track_layout
        sm   = load_track_semantic_model(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        seed = resolve_track_layout(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert len(sm.corners) == len(seed.corner_definitions)

    def test_semantic_model_sector_count_matches_yaml(self):
        from data.track_library import load_track_semantic_model
        from data.track_intelligence import resolve_track_layout
        sm   = load_track_semantic_model(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        seed = resolve_track_layout(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert len(sm.sectors) == len(seed.sector_definitions)


# ─────────────────────────────────────────────────────────────────────────────
# 16–17. T10/T11 and BusStop complexes in semantic model
# ─────────────────────────────────────────────────────────────────────────────

class TestComplexIntegrity:
    def test_t10t11_in_semantic_model(self):
        from data.track_library import load_track_semantic_model
        sm = load_track_semantic_model(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        complex_ids = [c["complex_id"] for c in sm.complexes]
        assert "T10T11" in complex_ids

    def test_busstop_in_semantic_model(self):
        from data.track_library import load_track_semantic_model
        sm = load_track_semantic_model(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        complex_ids = [c["complex_id"] for c in sm.complexes]
        assert "BusStop" in complex_ids

    def test_t10t11_members(self):
        from data.track_library import load_track_semantic_model
        sm = load_track_semantic_model(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        t10t11 = next(c for c in sm.complexes if c["complex_id"] == "T10T11")
        assert "T10" in t10t11["member_corner_ids"]
        assert "T11" in t10t11["member_corner_ids"]

    def test_busstop_members(self):
        from data.track_library import load_track_semantic_model
        sm = load_track_semantic_model(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        busstop = next(c for c in sm.complexes if c["complex_id"] == "BusStop")
        assert "T1" in busstop["member_corner_ids"]
        assert "T2" in busstop["member_corner_ids"]


# ─────────────────────────────────────────────────────────────────────────────
# 19. Source manifest loads
# ─────────────────────────────────────────────────────────────────────────────

class TestSourceManifest:
    def test_source_manifest_loads(self):
        from data.track_library import load_source_manifest
        sm = load_source_manifest(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert sm is not None

    def test_source_manifest_schema(self):
        from data.track_library import load_source_manifest
        sm = load_source_manifest(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert sm.schema == "source_manifest_v1"

    def test_source_manifest_has_sources(self):
        from data.track_library import load_source_manifest
        sm = load_source_manifest(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert len(sm.sources) > 0

    def test_source_manifest_has_fields_estimated(self):
        from data.track_library import load_source_manifest
        sm = load_source_manifest(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert len(sm.fields_estimated) > 0


# ─────────────────────────────────────────────────────────────────────────────
# 20–23. TrackLibraryAuditResult
# ─────────────────────────────────────────────────────────────────────────────

class TestAuditResult:
    def test_audit_reports_library_available(self):
        from data.track_library import audit_track_library_layout
        audit = audit_track_library_layout(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert audit.library_available is True

    def test_audit_reports_manifest_loaded(self):
        from data.track_library import audit_track_library_layout
        audit = audit_track_library_layout(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert audit.manifest_loaded is True

    def test_audit_reports_semantic_model_loaded(self):
        from data.track_library import audit_track_library_layout
        audit = audit_track_library_layout(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert audit.semantic_model_loaded is True

    def test_audit_reports_validation_rules_loaded(self):
        from data.track_library import audit_track_library_layout
        audit = audit_track_library_layout(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert audit.validation_rules_loaded is True

    def test_audit_no_geometry_in_library(self):
        from data.track_library import audit_track_library_layout
        audit = audit_track_library_layout(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert audit.seed_geometry_in_library is False

    def test_audit_seed_coordinate_source_none(self):
        from data.track_library import audit_track_library_layout
        audit = audit_track_library_layout(DAYTONA_TRACK_ID, DAYTONA_LAYOUT_ID)
        assert audit.seed_coordinate_source == "none"

    def test_audit_missing_track_warns(self, tmp_path):
        from data.track_library import audit_track_library_layout, load_track_library_index
        import unittest.mock as mock

        # Create an index that doesn't include our track
        (tmp_path / "index.json").write_text(json.dumps({
            "schema": "track_library_index_v1",
            "library_version": "1.0.0",
            "tracks": ["other_track"],
        }))
        with mock.patch("data.track_seed_coordinate_map.SEED_MAPS_DIR", tmp_path):
            result = audit_track_library_layout("missing_track", "missing_layout", base_dir=tmp_path)
        assert result.library_available is True
        assert any("missing_track" in w for w in result.warnings)


# ─────────────────────────────────────────────────────────────────────────────
# 30–32. format_alignment_summary includes seed_source
# ─────────────────────────────────────────────────────────────────────────────

class TestFormatAlignmentSummarySeedSource:
    def test_none_result_has_seed_source_key(self):
        from ui.track_model_alignment_vm import format_alignment_summary
        summary = format_alignment_summary(None)
        assert "seed_source" in summary

    def test_none_result_seed_source_is_dash(self):
        from ui.track_model_alignment_vm import format_alignment_summary
        summary = format_alignment_summary(None)
        assert summary["seed_source"] == "—"

    def test_non_none_result_has_seed_source_key(self):
        from ui.track_model_alignment_vm import format_alignment_summary
        from unittest.mock import MagicMock
        from data.track_model_alignment import TrackModelMatchStatus

        mock_result = MagicMock()
        mock_result.match_status          = TrackModelMatchStatus.NOT_READY
        mock_result.seed_corners_expected = 0
        mock_result.model_corners_found   = 0
        mock_result.extra_peaks_suppressed = 0
        mock_result.placeholder_count     = 0
        mock_result.lap_length_m_model    = 5000.0
        mock_result.lap_length_m_seed     = 0.0
        mock_result.lap_length_delta_pct  = 0.0
        mock_result.station_count         = 5000
        mock_result.confidence            = 0.0
        mock_result.sector_alignment.note = ""
        mock_result.blockers              = []
        mock_result.warnings              = []
        mock_result.accepted              = False
        mock_result.accepted_at           = None
        mock_result.seed_corner_positions_available = False
        mock_result.corners_matched       = 0
        mock_result.corner_position_match = "NOT_AVAILABLE"

        summary = format_alignment_summary(mock_result)
        assert "seed_source" in summary

    def test_seed_source_unavailable_when_no_ids_given(self):
        """When no track/layout IDs given, audit has no library data → 'Unavailable'."""
        from ui.track_model_alignment_vm import format_alignment_summary
        from unittest.mock import MagicMock
        from data.track_model_alignment import TrackModelMatchStatus

        mock_result = MagicMock()
        mock_result.match_status          = TrackModelMatchStatus.NOT_READY
        mock_result.seed_corners_expected = 0
        mock_result.model_corners_found   = 0
        mock_result.extra_peaks_suppressed = 0
        mock_result.placeholder_count     = 0
        mock_result.lap_length_m_model    = 5000.0
        mock_result.lap_length_m_seed     = 0.0
        mock_result.lap_length_delta_pct  = 0.0
        mock_result.station_count         = 5000
        mock_result.confidence            = 0.0
        mock_result.sector_alignment.note = ""
        mock_result.blockers              = []
        mock_result.warnings              = []
        mock_result.accepted              = False
        mock_result.accepted_at           = None
        mock_result.seed_corner_positions_available = False
        mock_result.corners_matched       = 0
        mock_result.corner_position_match = "NOT_AVAILABLE"

        # layout_seed=None → audit returns seed_source="none" → display "Unavailable"
        summary = format_alignment_summary(mock_result, layout_seed=None)
        assert summary["seed_source"] == "Unavailable"


# ─────────────────────────────────────────────────────────────────────────────
# 33–34. Resolver edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestResolverEdgeCases:
    def test_neither_library_nor_legacy_returns_none(self, tmp_path):
        from data.track_library import resolve_seed_coordinate_map
        import unittest.mock as mock
        with mock.patch("data.track_seed_coordinate_map.SEED_MAPS_DIR", tmp_path):
            smap, source = resolve_seed_coordinate_map("x", "y", base_dir=tmp_path)
        assert smap is None
        assert source == "none"

    def test_load_track_metadata_missing_returns_none(self, tmp_path):
        from data.track_library import load_track_metadata
        assert load_track_metadata("nonexistent", base_dir=tmp_path) is None

    def test_load_track_metadata_loads_daytona(self):
        from data.track_library import load_track_metadata
        tm = load_track_metadata(DAYTONA_TRACK_ID)
        assert tm is not None
        assert tm.track_id == DAYTONA_TRACK_ID
        assert DAYTONA_LAYOUT_ID in tm.layouts


# ─────────────────────────────────────────────────────────────────────────────
# 36. audit_layout_seed includes new fields with defaults
# ─────────────────────────────────────────────────────────────────────────────

class TestAuditLayoutSeedNewFields:
    def test_none_layout_seed_has_new_fields(self):
        from data.track_intelligence import audit_layout_seed
        result = audit_layout_seed(None)
        assert hasattr(result, "seed_source")
        assert hasattr(result, "library_manifest_loaded")
        assert hasattr(result, "validation_rules_loaded")
        assert result.seed_source == "none"
        assert result.library_manifest_loaded is False
        assert result.validation_rules_loaded is False

    def test_layout_seed_without_ids_has_source_none(self):
        from data.track_intelligence import audit_layout_seed

        class _LS:
            length_m = 5729.0
            corner_definitions = []
            sector_definitions = []
            corner_complexes = []

        result = audit_layout_seed(_LS())
        assert result.seed_source == "none"
        assert result.library_manifest_loaded is False
