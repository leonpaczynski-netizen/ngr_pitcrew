"""Group 17A — Track Intelligence Seed Loader and Track Modelling Foundation tests."""
import pytest
from pathlib import Path
import tempfile
import textwrap
import yaml

from data.track_intelligence import (
    TrackModellingStatus,
    TrackSeedMetadata,
    CalibrationCarProfile,
    TrackLayoutSeed,
    TrackLocationSeed,
    TrackSeedLoadResult,
    load_track_seed,
    get_track_locations,
    get_track_layouts,
    resolve_track_layout,
    search_track_layouts,
    build_seed_track_context_for_prompt,
    SEED_YAML_PATH,
)
import data.track_intelligence as _ti

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_seed_yaml(tracks=None, calibration_cars=None, extra_meta=None) -> str:
    """Build a minimal valid seed YAML string."""
    cars = calibration_cars or [
        {
            "profile_id": "test_car",
            "display_name": "Test Car",
            "manufacturer": "Porsche",
            "country": "Germany",
            "year": 2017,
            "class": "Gr.3",
            "drivetrain": "MR",
            "stock_power_bhp": 500,
            "stock_weight_kg": 1200,
            "stock_tyres": "RH",
            "purpose": "primary_tarmac_track_modelling_car",
        }
    ]
    track_list = tracks or [
        {
            "track_location_id": "test_circuit",
            "display_name": "Test Circuit",
            "aliases": ["TC", "Test Track"],
            "region": "Europe",
            "country": "Germany",
            "real_or_fictional": "real",
            "surface": "tarmac",
            "track_type": "circuit",
            "opened_year": 2000,
            "altitude_m": 200,
            "gtplus_layout_count": 1,
            "dg_edge_variant_count": 1,
            "gt_engine_layout_count_in_seed": 1,
            "source_count_conflict": False,
            "rain_supported_track_level": True,
            "night_supported_track_level": False,
            "full_24h_supported_track_level": False,
            "reversible_supported_track_level": False,
            "update_version": None,
            "official_url": None,
            "source_confidence": "source_public",
            "validation_status": "seed_only",
            "layouts": [
                {
                    "layout_id": "test_circuit__full_course",
                    "display_name": "Full Course",
                    "direction": "forward_or_native",
                    "length_m": 4500,
                    "longest_straight_m": 900,
                    "elevation_change_m": 30,
                    "average_gradient_percent": 0.67,
                    "pit_delta_seconds": 20,
                    "corners_expected": 14,
                    "sectors": 3,
                    "bop_applied": "Mid",
                    "oval": False,
                    "reversible": False,
                    "rain_supported": True,
                    "night_supported": False,
                    "full_24h_supported": False,
                    "update_version": None,
                    "source_url": "https://example.com",
                    "source_confidence": "source_public_gtplus_layout_page",
                    "validation_status": "seed_only",
                    "modelling_status": "not_modelled",
                    "needs_telemetry_reference_path": True,
                    "needs_segment_detection": True,
                    "notes": None,
                }
            ],
        }
    ]
    base = {
        "schema_name": "ngr_pit_crew_gt7_track_modelling_seed",
        "schema_version": "0.1.0",
        "generated_utc": "2026-06-24T00:00:00+00:00",
        "purpose": "Test seed",
        "track_count": len(track_list),
        "layout_count_in_seed": sum(len(t.get("layouts", [])) for t in track_list),
        "calibration_car_profiles": cars,
        "tracks": track_list,
    }
    if extra_meta:
        base.update(extra_meta)
    return yaml.dump(base, allow_unicode=True)


def _tmp_seed(content: str) -> Path:
    """Write seed YAML to a temp file and return its path."""
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    )
    f.write(content)
    f.flush()
    return Path(f.name)


# ---------------------------------------------------------------------------
# Reset cache between tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_cache():
    """Ensure the module-level cache is cleared before each test."""
    _ti._CACHE = None
    yield
    _ti._CACHE = None


# ---------------------------------------------------------------------------
# TestTrackModellingStatus
# ---------------------------------------------------------------------------

class TestTrackModellingStatus:
    def test_all_enum_values_exist(self):
        values = {e.value for e in TrackModellingStatus}
        assert "not_modelled" in values
        assert "seed_only" in values
        assert "telemetry_sampled" in values
        assert "reference_path_built" in values
        assert "segment_detected" in values
        assert "user_reviewed" in values
        assert "practice_refined" in values
        assert "race_validated" in values
        assert "engineer_grade" in values

    def test_is_ready_for_calibration_false_below_threshold(self):
        assert not TrackModellingStatus.NOT_MODELLED.is_ready_for_calibration()
        assert not TrackModellingStatus.SEED_ONLY.is_ready_for_calibration()

    def test_is_ready_for_calibration_true_at_threshold(self):
        assert TrackModellingStatus.TELEMETRY_SAMPLED.is_ready_for_calibration()
        assert TrackModellingStatus.ENGINEER_GRADE.is_ready_for_calibration()

    def test_is_ready_for_ai_false_below_threshold(self):
        assert not TrackModellingStatus.NOT_MODELLED.is_ready_for_ai()
        assert not TrackModellingStatus.TELEMETRY_SAMPLED.is_ready_for_ai()
        assert not TrackModellingStatus.REFERENCE_PATH_BUILT.is_ready_for_ai()

    def test_is_ready_for_ai_true_at_threshold(self):
        assert TrackModellingStatus.SEGMENT_DETECTED.is_ready_for_ai()
        assert TrackModellingStatus.ENGINEER_GRADE.is_ready_for_ai()

    def test_missing_calibration_requirements_not_modelled(self):
        reqs = TrackModellingStatus.NOT_MODELLED.missing_calibration_requirements()
        assert len(reqs) > 0
        assert any("calibration" in r.lower() for r in reqs)

    def test_missing_calibration_requirements_engineer_grade_empty(self):
        reqs = TrackModellingStatus.ENGINEER_GRADE.missing_calibration_requirements()
        assert reqs == []

    def test_missing_calibration_requirements_seed_only_includes_telemetry(self):
        reqs = TrackModellingStatus.SEED_ONLY.missing_calibration_requirements()
        assert any("calibration" in r.lower() for r in reqs)

    def test_enum_is_string(self):
        assert isinstance(TrackModellingStatus.SEED_ONLY, str)
        assert TrackModellingStatus.SEED_ONLY == "seed_only"


# ---------------------------------------------------------------------------
# TestLoadTrackSeedFromRealFile
# ---------------------------------------------------------------------------

class TestLoadTrackSeedFromRealFile:
    def test_seed_file_exists(self):
        assert SEED_YAML_PATH.exists(), f"Seed YAML not found: {SEED_YAML_PATH}"

    def test_load_succeeds(self):
        result = load_track_seed()
        assert result.success, f"Load failed: {result.errors}"

    def test_metadata_present(self):
        result = load_track_seed()
        assert result.metadata is not None
        assert result.metadata.schema_name == "ngr_pit_crew_gt7_track_modelling_seed"
        assert result.metadata.schema_version

    def test_track_count_matches_metadata(self):
        result = load_track_seed()
        assert result.metadata is not None
        assert result.metadata.track_count == 41
        assert len(result.track_locations) == 41

    def test_layout_count_matches_metadata(self):
        result = load_track_seed()
        all_layouts = get_track_layouts()
        assert len(all_layouts) == 121

    def test_calibration_car_present(self):
        result = load_track_seed()
        assert len(result.calibration_cars) >= 1
        car = result.calibration_cars[0]
        assert car.display_name == "Porsche 911 RSR (991) '17"

    def test_calibration_car_stats(self):
        result = load_track_seed()
        car = result.calibration_cars[0]
        assert car.stock_power_bhp == 509
        assert car.stock_weight_kg == 1243
        assert car.stock_tyres == "RH"
        assert car.car_class == "Gr.3"
        assert car.drivetrain == "MR"

    def test_no_errors_on_real_file(self):
        result = load_track_seed()
        assert result.errors == []

    def test_no_duplicate_layout_ids(self):
        result = load_track_seed()
        assert result.duplicate_layout_ids == []

    def test_fuji_full_course_present(self):
        layout = resolve_track_layout(
            "fuji_international_speedway", "fuji_international_speedway__full_course"
        )
        assert layout is not None
        assert layout.length_m == 4563
        assert layout.corners_expected == 16
        assert layout.pit_delta_seconds == 17
        assert layout.rain_supported is True

    def test_daytona_road_course_present(self):
        layout = resolve_track_layout(
            "daytona_international_speedway",
            "daytona_international_speedway__road_course",
        )
        assert layout is not None
        assert layout.length_m == 5729

    def test_deep_forest_reverse_notes_populated(self):
        layout = resolve_track_layout(
            "deep_forest_raceway", "deep_forest_raceway__full_course_reverse"
        )
        assert layout is not None
        assert layout.notes is not None
        assert "reverse" in layout.notes.lower()

    def test_all_layouts_have_modelling_status(self):
        for layout in get_track_layouts():
            assert isinstance(layout.modelling_status, TrackModellingStatus)


# ---------------------------------------------------------------------------
# TestLoadTrackSeedValidation
# ---------------------------------------------------------------------------

class TestLoadTrackSeedValidation:
    def test_missing_file_returns_failure(self):
        result = load_track_seed(yaml_path=Path("/nonexistent/path/seed.yaml"))
        assert not result.success
        assert any("not found" in e.lower() for e in result.errors)

    def test_invalid_yaml_returns_failure(self):
        p = _tmp_seed(":: invalid: yaml: [\n")
        result = load_track_seed(yaml_path=p)
        assert not result.success
        assert any("parse" in e.lower() or "yaml" in e.lower() for e in result.errors)

    def test_missing_schema_name_returns_error(self):
        content = _make_seed_yaml()
        data = yaml.safe_load(content)
        del data["schema_name"]
        p = _tmp_seed(yaml.dump(data))
        result = load_track_seed(yaml_path=p)
        assert not result.success
        assert any("schema_name" in e for e in result.errors)

    def test_missing_calibration_car_returns_error(self):
        content = _make_seed_yaml()
        data = yaml.safe_load(content)
        data["calibration_car_profiles"] = []
        p = _tmp_seed(yaml.dump(data))
        result = load_track_seed(yaml_path=p)
        assert not result.success
        assert any("calibration" in e.lower() for e in result.errors)

    def test_empty_tracks_returns_error(self):
        content = _make_seed_yaml()
        data = yaml.safe_load(content)
        data["tracks"] = []
        p = _tmp_seed(yaml.dump(data))
        result = load_track_seed(yaml_path=p)
        assert not result.success
        assert any("track" in e.lower() for e in result.errors)

    def test_unknown_modelling_status_preserved(self):
        content = _make_seed_yaml()
        data = yaml.safe_load(content)
        data["tracks"][0]["layouts"][0]["modelling_status"] = "future_unknown_status"
        p = _tmp_seed(yaml.dump(data))
        result = load_track_seed(yaml_path=p)
        assert "future_unknown_status" in result.unknown_modelling_statuses

    def test_duplicate_layout_id_detected(self):
        content = _make_seed_yaml()
        data = yaml.safe_load(content)
        dup_layout = dict(data["tracks"][0]["layouts"][0])
        data["tracks"][0]["layouts"].append(dup_layout)
        p = _tmp_seed(yaml.dump(data))
        result = load_track_seed(yaml_path=p)
        assert len(result.duplicate_layout_ids) >= 1

    def test_root_not_dict_returns_failure(self):
        p = _tmp_seed("- item1\n- item2\n")
        result = load_track_seed(yaml_path=p)
        assert not result.success

    def test_success_flag_true_on_valid_seed(self):
        p = _tmp_seed(_make_seed_yaml())
        result = load_track_seed(yaml_path=p)
        assert result.success


# ---------------------------------------------------------------------------
# TestGetTrackLocations
# ---------------------------------------------------------------------------

class TestGetTrackLocations:
    def test_returns_list(self):
        locs = get_track_locations()
        assert isinstance(locs, list)

    def test_count_is_41(self):
        locs = get_track_locations()
        assert len(locs) == 41

    def test_fuji_in_locations(self):
        ids = {loc.track_location_id for loc in get_track_locations()}
        assert "fuji_international_speedway" in ids

    def test_all_locations_have_ids(self):
        for loc in get_track_locations():
            assert loc.track_location_id
            assert loc.display_name

    def test_location_has_layouts(self):
        locs = get_track_locations()
        for loc in locs:
            assert len(loc.layouts) >= 1


# ---------------------------------------------------------------------------
# TestGetTrackLayouts
# ---------------------------------------------------------------------------

class TestGetTrackLayouts:
    def test_returns_flat_list(self):
        layouts = get_track_layouts()
        assert isinstance(layouts, list)
        assert all(isinstance(l, TrackLayoutSeed) for l in layouts)

    def test_count_is_121(self):
        assert len(get_track_layouts()) == 121

    def test_layouts_have_track_location_id(self):
        for layout in get_track_layouts():
            assert layout.track_location_id


# ---------------------------------------------------------------------------
# TestResolveTrackLayout
# ---------------------------------------------------------------------------

class TestResolveTrackLayout:
    def test_resolve_known_layout(self):
        layout = resolve_track_layout(
            "high_speed_ring", "high_speed_ring__full_course"
        )
        assert layout is not None
        assert layout.display_name == "Full Course"
        assert layout.length_m == 4345

    def test_resolve_returns_none_for_unknown_location(self):
        result = resolve_track_layout("does_not_exist", "does_not_exist__full_course")
        assert result is None

    def test_resolve_returns_none_for_unknown_layout(self):
        result = resolve_track_layout("fuji_international_speedway", "fuji__nonexistent_layout")
        assert result is None

    def test_resolve_layout_id_matches(self):
        layout = resolve_track_layout(
            "fuji_international_speedway", "fuji_international_speedway__short_course"
        )
        assert layout is not None
        assert layout.layout_id == "fuji_international_speedway__short_course"


# ---------------------------------------------------------------------------
# TestSearchTrackLayouts
# ---------------------------------------------------------------------------

class TestSearchTrackLayouts:
    def test_search_by_display_name(self):
        results = search_track_layouts("Fuji")
        assert len(results) >= 2
        ids = {r.layout_id for r in results}
        assert "fuji_international_speedway__full_course" in ids

    def test_search_case_insensitive(self):
        lower = search_track_layouts("fuji")
        upper = search_track_layouts("FUJI")
        assert {r.layout_id for r in lower} == {r.layout_id for r in upper}

    def test_search_by_location_id_substring(self):
        results = search_track_layouts("daytona")
        assert len(results) >= 2

    def test_search_empty_query_returns_empty(self):
        assert search_track_layouts("") == []

    def test_search_no_match_returns_empty(self):
        results = search_track_layouts("xyzqrst_nonexistent_track_999")
        assert results == []

    def test_search_by_alias(self):
        p = _tmp_seed(_make_seed_yaml())
        results = search_track_layouts("TC", yaml_path=p)
        assert len(results) >= 1

    def test_search_reverse_layouts(self):
        results = search_track_layouts("Reverse")
        assert len(results) > 0
        assert all("reverse" in r.display_name.lower() or "reverse" in r.layout_id.lower() for r in results)


# ---------------------------------------------------------------------------
# TestBuildSeedTrackContextForPrompt
# ---------------------------------------------------------------------------

class TestBuildSeedTrackContextForPrompt:
    def test_returns_string(self):
        ctx = build_seed_track_context_for_prompt(
            "fuji_international_speedway", "fuji_international_speedway__full_course"
        )
        assert isinstance(ctx, str)
        assert len(ctx) > 0

    def test_contains_track_name(self):
        ctx = build_seed_track_context_for_prompt(
            "fuji_international_speedway", "fuji_international_speedway__full_course"
        )
        assert "Fuji" in ctx

    def test_contains_layout_name(self):
        ctx = build_seed_track_context_for_prompt(
            "fuji_international_speedway", "fuji_international_speedway__full_course"
        )
        assert "Full Course" in ctx

    def test_contains_seed_data_caveat_for_unmodelled(self):
        ctx = build_seed_track_context_for_prompt(
            "fuji_international_speedway", "fuji_international_speedway__full_course"
        )
        assert "seed" in ctx.lower() or "caveat" in ctx.lower() or "NOT" in ctx

    def test_contains_calibration_car_boundary_note(self):
        ctx = build_seed_track_context_for_prompt(
            "fuji_international_speedway", "fuji_international_speedway__full_course"
        )
        assert "Porsche" in ctx or "calibration" in ctx.lower()

    def test_unknown_location_returns_error_string(self):
        ctx = build_seed_track_context_for_prompt("no_such_place", "no_such_place__full")
        assert "not found" in ctx.lower()

    def test_unknown_layout_returns_error_string(self):
        ctx = build_seed_track_context_for_prompt(
            "fuji_international_speedway", "fuji__nonexistent"
        )
        assert "not found" in ctx.lower()

    def test_fuji_length_in_context(self):
        ctx = build_seed_track_context_for_prompt(
            "fuji_international_speedway", "fuji_international_speedway__full_course"
        )
        assert "4563" in ctx

    def test_modelling_status_in_context(self):
        ctx = build_seed_track_context_for_prompt(
            "high_speed_ring", "high_speed_ring__full_course"
        )
        assert "not_modelled" in ctx or "seed_only" in ctx or "Modelling" in ctx


# ---------------------------------------------------------------------------
# TestCaching
# ---------------------------------------------------------------------------

class TestCaching:
    def test_second_call_uses_cache(self):
        r1 = load_track_seed()
        r2 = load_track_seed()
        assert r1 is r2

    def test_force_reload_bypasses_cache(self):
        r1 = load_track_seed()
        r2 = load_track_seed(force_reload=True)
        assert r1 is not r2
        assert r1.metadata == r2.metadata

    def test_custom_path_does_not_pollute_cache(self):
        p = _tmp_seed(_make_seed_yaml())
        load_track_seed(yaml_path=p)
        assert _ti._CACHE is None  # custom path doesn't write to global cache

    def test_cache_is_none_after_reset(self):
        load_track_seed()
        _ti._CACHE = None
        assert _ti._CACHE is None
