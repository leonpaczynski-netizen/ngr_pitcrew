"""
Group 17B — Track Modelling UI view model tests.

Tests the pure-Python view model layer (ui/track_modelling_vm.py) that
powers the Track Modelling tab without requiring a running QApplication.

All tests run against the real seed YAML so they validate the integration
between the seed loader and the UI formatting layer.
"""
import pytest
from unittest.mock import MagicMock

import data.track_intelligence as _ti
from data.track_intelligence import (
    TrackModellingStatus,
    TrackLayoutSeed,
    TrackLocationSeed,
    CalibrationCarProfile,
    TrackSeedLoadResult,
    TrackSeedMetadata,
    load_track_seed,
)
from ui.track_modelling_vm import (
    UNKNOWN_VALUE,
    CALIBRATION_CAR_BOUNDARY_NOTE,
    SEED_WARNING_TEXT,
    format_layout_facts,
    format_readiness,
    format_calibration_car,
    get_seed_warning_text,
    is_seed_only,
    build_location_display_items,
    build_layout_display_items,
    get_selected_location,
    get_selected_layout,
    build_prompt_preview,
    describe_seed_load_status,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_cache():
    """Reset module-level seed cache before/after each test."""
    _ti._CACHE = None
    yield
    _ti._CACHE = None


@pytest.fixture
def seed_result():
    """Load the real seed once per test."""
    return load_track_seed()


@pytest.fixture
def fuji_loc(seed_result):
    return get_selected_location(seed_result, "fuji_international_speedway")


@pytest.fixture
def fuji_full(seed_result):
    return get_selected_layout(
        seed_result,
        "fuji_international_speedway",
        "fuji_international_speedway__full_course",
    )


@pytest.fixture
def fuji_unknown_loc(seed_result):
    """A layout with not_modelled status (all layouts are not_modelled in seed)."""
    return get_selected_location(seed_result, "bathurst")


@pytest.fixture
def fuji_unknown_lay(seed_result):
    return get_selected_layout(
        seed_result, "bathurst", "bathurst__full_course"
    )


@pytest.fixture
def porsche_car(seed_result):
    return seed_result.calibration_cars[0]


def _make_layout(**overrides) -> TrackLayoutSeed:
    """Build a minimal TrackLayoutSeed for unit tests."""
    defaults = dict(
        layout_id="test_track__full",
        display_name="Full Course",
        track_location_id="test_track",
        modelling_status=TrackModellingStatus.NOT_MODELLED,
    )
    defaults.update(overrides)
    return TrackLayoutSeed(**defaults)


def _make_loc(**overrides) -> TrackLocationSeed:
    defaults = dict(
        track_location_id="test_track",
        display_name="Test Track",
        aliases=[],
        layouts=[],
    )
    defaults.update(overrides)
    return TrackLocationSeed(**defaults)


def _make_failed_seed() -> TrackSeedLoadResult:
    return TrackSeedLoadResult(
        success=False,
        errors=["File not found"],
    )


def _make_success_seed(locs=None) -> TrackSeedLoadResult:
    meta = TrackSeedMetadata(
        schema_name="track_modelling_seed",
        schema_version="1.0",
        generated_utc="2026-01-01T00:00:00Z",
        purpose="test",
        track_count=1,
        layout_count_in_seed=1,
    )
    return TrackSeedLoadResult(
        success=True,
        metadata=meta,
        track_locations=locs or [],
    )


# ---------------------------------------------------------------------------
# format_layout_facts
# ---------------------------------------------------------------------------

class TestFormatLayoutFacts:
    def test_returns_list_of_tuples(self, fuji_loc, fuji_full):
        result = format_layout_facts(fuji_full, fuji_loc)
        assert isinstance(result, list)
        assert all(isinstance(t, tuple) and len(t) == 2 for t in result)

    def test_labels_are_strings(self, fuji_loc, fuji_full):
        for label, _ in format_layout_facts(fuji_full, fuji_loc):
            assert isinstance(label, str) and label

    def test_values_are_strings(self, fuji_loc, fuji_full):
        for _, value in format_layout_facts(fuji_full, fuji_loc):
            assert isinstance(value, str)

    def test_track_location_present(self, fuji_loc, fuji_full):
        rows = dict(format_layout_facts(fuji_full, fuji_loc))
        assert "Fuji International Speedway" in rows["Track Location"]

    def test_layout_display_name(self, fuji_loc, fuji_full):
        rows = dict(format_layout_facts(fuji_full, fuji_loc))
        assert "Full Course" in rows["Layout"]

    def test_length_formatted_with_unit(self, fuji_loc, fuji_full):
        rows = dict(format_layout_facts(fuji_full, fuji_loc))
        # YAML stores length as int; _fmt_int produces "4563 m" (no decimal)
        assert rows["Length"] == "4563 m"

    def test_corners_formatted(self, fuji_loc, fuji_full):
        rows = dict(format_layout_facts(fuji_full, fuji_loc))
        assert rows["Corners"] == "16"

    def test_pit_delta_formatted(self, fuji_loc, fuji_full):
        rows = dict(format_layout_facts(fuji_full, fuji_loc))
        assert rows["Pit Delta"] == "17 s"

    def test_rain_yes(self, fuji_loc, fuji_full):
        rows = dict(format_layout_facts(fuji_full, fuji_loc))
        assert rows["Rain Supported"] == "Yes"

    def test_none_field_shows_unknown(self):
        loc = _make_loc(country=None)
        lay = _make_layout()
        rows = dict(format_layout_facts(lay, loc))
        assert rows["Country"] == UNKNOWN_VALUE

    def test_none_bool_shows_unknown(self):
        loc = _make_loc()
        lay = _make_layout(rain_supported=None)
        rows = dict(format_layout_facts(lay, loc))
        assert rows["Rain Supported"] == UNKNOWN_VALUE

    def test_false_bool_shows_no(self):
        loc = _make_loc()
        lay = _make_layout(night_supported=False)
        rows = dict(format_layout_facts(lay, loc))
        assert rows["Night Supported"] == "No"

    def test_true_bool_shows_yes(self):
        loc = _make_loc()
        lay = _make_layout(full_24h_supported=True)
        rows = dict(format_layout_facts(lay, loc))
        assert rows["24h Supported"] == "Yes"

    def test_aliases_joined(self):
        loc = _make_loc(aliases=["Fuji", "FSW"])
        lay = _make_layout()
        rows = dict(format_layout_facts(lay, loc))
        assert rows["Aliases"] == "Fuji, FSW"

    def test_no_aliases_shows_unknown(self):
        loc = _make_loc(aliases=[])
        lay = _make_layout()
        rows = dict(format_layout_facts(lay, loc))
        assert rows["Aliases"] == UNKNOWN_VALUE

    def test_modelling_status_shows_value(self, fuji_loc, fuji_full):
        rows = dict(format_layout_facts(fuji_full, fuji_loc))
        assert rows["Modelling Status"] == fuji_full.modelling_status.value

    def test_all_27_rows_present(self, fuji_loc, fuji_full):
        rows = format_layout_facts(fuji_full, fuji_loc)
        labels = [r[0] for r in rows]
        assert len(labels) == 27

    def test_fuji_country(self, fuji_loc, fuji_full):
        rows = dict(format_layout_facts(fuji_full, fuji_loc))
        assert rows["Country"] == "Japan"

    def test_fuji_region(self, fuji_loc, fuji_full):
        rows = dict(format_layout_facts(fuji_full, fuji_loc))
        assert rows["Region"] in ("Asia", "Asia Pacific", UNKNOWN_VALUE)

    def test_elevation_formatted(self, fuji_loc, fuji_full):
        rows = dict(format_layout_facts(fuji_full, fuji_loc))
        assert " m" in rows["Elevation Change"] or rows["Elevation Change"] == UNKNOWN_VALUE

    def test_source_confidence_present(self, fuji_loc, fuji_full):
        rows = dict(format_layout_facts(fuji_full, fuji_loc))
        assert "Source Confidence" in {r[0] for r in format_layout_facts(fuji_full, fuji_loc)}

    def test_notes_present_in_rows(self, fuji_loc, fuji_full):
        labels = {r[0] for r in format_layout_facts(fuji_full, fuji_loc)}
        assert "Notes" in labels

    def test_reversible_none_is_unknown(self):
        loc = _make_loc()
        lay = _make_layout(reversible=None)
        rows = dict(format_layout_facts(lay, loc))
        assert rows["Reversible"] == UNKNOWN_VALUE


# ---------------------------------------------------------------------------
# format_readiness
# ---------------------------------------------------------------------------

class TestFormatReadiness:
    def test_returns_list_of_tuples(self, fuji_full):
        result = format_readiness(fuji_full)
        assert isinstance(result, list)
        assert all(isinstance(t, tuple) and len(t) == 2 for t in result)

    def test_includes_modelling_status(self, fuji_full):
        rows = dict(format_readiness(fuji_full))
        assert "Modelling Status" in rows

    def test_not_modelled_seed_only_true(self):
        lay = _make_layout(modelling_status=TrackModellingStatus.NOT_MODELLED)
        rows = dict(format_readiness(lay))
        assert rows["Seed Data Only"] == "Yes"

    def test_seed_only_seed_only_true(self):
        lay = _make_layout(modelling_status=TrackModellingStatus.SEED_ONLY)
        rows = dict(format_readiness(lay))
        assert rows["Seed Data Only"] == "Yes"

    def test_telemetry_sampled_seed_only_false(self):
        lay = _make_layout(modelling_status=TrackModellingStatus.TELEMETRY_SAMPLED)
        rows = dict(format_readiness(lay))
        assert rows["Seed Data Only"] == "No"

    def test_not_modelled_ready_for_calibration_false(self):
        lay = _make_layout(modelling_status=TrackModellingStatus.NOT_MODELLED)
        rows = dict(format_readiness(lay))
        assert "No" in rows["Ready for Calibration"]

    def test_telemetry_sampled_ready_for_calibration_yes(self):
        lay = _make_layout(modelling_status=TrackModellingStatus.TELEMETRY_SAMPLED)
        rows = dict(format_readiness(lay))
        assert rows["Ready for Calibration"] == "Yes"

    def test_not_modelled_not_ready_for_ai(self):
        lay = _make_layout(modelling_status=TrackModellingStatus.NOT_MODELLED)
        rows = dict(format_readiness(lay))
        assert "No" in rows["Ready for AI Use"]

    def test_segment_detected_ready_for_ai(self):
        lay = _make_layout(modelling_status=TrackModellingStatus.SEGMENT_DETECTED)
        rows = dict(format_readiness(lay))
        assert rows["Ready for AI Use"] == "Yes"

    def test_missing_steps_present(self):
        lay = _make_layout(modelling_status=TrackModellingStatus.NOT_MODELLED)
        rows = dict(format_readiness(lay))
        assert "Missing Steps" in rows

    def test_missing_steps_non_zero_for_not_modelled(self):
        lay = _make_layout(modelling_status=TrackModellingStatus.NOT_MODELLED)
        rows = dict(format_readiness(lay))
        assert "remaining" in rows["Missing Steps"]

    def test_engineer_grade_no_missing_steps(self):
        lay = _make_layout(modelling_status=TrackModellingStatus.ENGINEER_GRADE)
        rows = dict(format_readiness(lay))
        assert "None" in rows["Missing Steps"]

    def test_step_rows_listed_for_not_modelled(self):
        lay = _make_layout(modelling_status=TrackModellingStatus.NOT_MODELLED)
        rows = format_readiness(lay)
        step_rows = [r for r in rows if r[0].strip().startswith("Step")]
        assert len(step_rows) > 0

    def test_engineer_grade_has_no_step_rows(self):
        lay = _make_layout(modelling_status=TrackModellingStatus.ENGINEER_GRADE)
        rows = format_readiness(lay)
        step_rows = [r for r in rows if r[0].strip().startswith("Step")]
        assert len(step_rows) == 0

    def test_minimum_5_rows(self, fuji_full):
        rows = format_readiness(fuji_full)
        assert len(rows) >= 5


# ---------------------------------------------------------------------------
# format_calibration_car
# ---------------------------------------------------------------------------

class TestFormatCalibrationCar:
    def test_returns_list_of_tuples(self, porsche_car):
        result = format_calibration_car(porsche_car)
        assert isinstance(result, list)
        assert all(isinstance(t, tuple) and len(t) == 2 for t in result)

    def test_car_display_name(self, porsche_car):
        rows = dict(format_calibration_car(porsche_car))
        assert porsche_car.display_name in rows["Car"]

    def test_power_bhp(self, porsche_car):
        rows = dict(format_calibration_car(porsche_car))
        assert "509 BHP" == rows["Power"]

    def test_weight_kg(self, porsche_car):
        rows = dict(format_calibration_car(porsche_car))
        assert "1243 kg" == rows["Weight"]

    def test_tyres(self, porsche_car):
        rows = dict(format_calibration_car(porsche_car))
        assert rows["Tyres"] == "RH"

    def test_class(self, porsche_car):
        rows = dict(format_calibration_car(porsche_car))
        assert "Gr.3" in rows["Class"]

    def test_drivetrain(self, porsche_car):
        rows = dict(format_calibration_car(porsche_car))
        assert rows["Drivetrain"] == "MR"

    def test_purpose_present(self, porsche_car):
        rows = dict(format_calibration_car(porsche_car))
        assert "Purpose" in rows

    def test_no_stock_pp_key_if_none(self):
        car = CalibrationCarProfile(
            profile_id="test_car",
            display_name="Test Car",
            manufacturer="Test",
            year=2020,
            car_class="Gr.3",
            drivetrain="MR",
            stock_power_bhp=500,
            stock_weight_kg=1200,
            stock_tyres="RH",
            purpose="calibration",
        )
        rows = dict(format_calibration_car(car))
        assert "PP (stock)" not in rows

    def test_stock_pp_shown_if_set(self):
        car = CalibrationCarProfile(
            profile_id="test_car",
            display_name="Test Car",
            manufacturer="Test",
            year=2020,
            car_class="Gr.3",
            drivetrain="MR",
            stock_power_bhp=509,
            stock_weight_kg=1243,
            stock_tyres="RH",
            purpose="calibration",
            stock_pp=720.74,
        )
        rows = dict(format_calibration_car(car))
        assert "PP (stock)" in rows
        assert "720.74" in rows["PP (stock)"]


# ---------------------------------------------------------------------------
# get_seed_warning_text
# ---------------------------------------------------------------------------

class TestGetSeedWarningText:
    def test_none_returns_no_layout_selected(self):
        text = get_seed_warning_text(None)
        assert "No layout selected" in text

    def test_not_modelled_returns_seed_warning(self):
        lay = _make_layout(modelling_status=TrackModellingStatus.NOT_MODELLED)
        text = get_seed_warning_text(lay)
        assert "SEED DATA ONLY" in text

    def test_seed_only_returns_seed_warning(self):
        lay = _make_layout(modelling_status=TrackModellingStatus.SEED_ONLY)
        text = get_seed_warning_text(lay)
        assert "SEED DATA ONLY" in text

    def test_engineer_grade_returns_empty(self):
        lay = _make_layout(modelling_status=TrackModellingStatus.ENGINEER_GRADE)
        text = get_seed_warning_text(lay)
        assert text == ""

    def test_telemetry_sampled_returns_partial_warning(self):
        lay = _make_layout(modelling_status=TrackModellingStatus.TELEMETRY_SAMPLED)
        text = get_seed_warning_text(lay)
        assert "PARTIAL TELEMETRY" in text

    def test_reference_path_built_returns_partial_warning(self):
        lay = _make_layout(modelling_status=TrackModellingStatus.REFERENCE_PATH_BUILT)
        text = get_seed_warning_text(lay)
        assert "PARTIAL TELEMETRY" in text

    def test_segment_detected_returns_empty(self):
        lay = _make_layout(modelling_status=TrackModellingStatus.SEGMENT_DETECTED)
        text = get_seed_warning_text(lay)
        assert text == ""


# ---------------------------------------------------------------------------
# is_seed_only
# ---------------------------------------------------------------------------

class TestIsSeedOnly:
    def test_none_is_seed_only(self):
        assert is_seed_only(None) is True

    def test_not_modelled_is_seed_only(self):
        lay = _make_layout(modelling_status=TrackModellingStatus.NOT_MODELLED)
        assert is_seed_only(lay) is True

    def test_seed_only_status_is_seed_only(self):
        lay = _make_layout(modelling_status=TrackModellingStatus.SEED_ONLY)
        assert is_seed_only(lay) is True

    def test_telemetry_sampled_not_seed_only(self):
        lay = _make_layout(modelling_status=TrackModellingStatus.TELEMETRY_SAMPLED)
        assert is_seed_only(lay) is False

    def test_engineer_grade_not_seed_only(self):
        lay = _make_layout(modelling_status=TrackModellingStatus.ENGINEER_GRADE)
        assert is_seed_only(lay) is False


# ---------------------------------------------------------------------------
# build_location_display_items
# ---------------------------------------------------------------------------

class TestBuildLocationDisplayItems:
    def test_returns_list(self, seed_result):
        items = build_location_display_items(seed_result)
        assert isinstance(items, list)

    def test_all_are_two_tuples(self, seed_result):
        items = build_location_display_items(seed_result)
        assert all(isinstance(t, tuple) and len(t) == 2 for t in items)

    def test_count_matches_seed(self, seed_result):
        items = build_location_display_items(seed_result)
        assert len(items) == 41

    def test_sorted_alphabetically(self, seed_result):
        items = build_location_display_items(seed_result)
        names = [t[0] for t in items]
        assert names == sorted(names)

    def test_fuji_present(self, seed_result):
        items = build_location_display_items(seed_result)
        ids = [t[1] for t in items]
        assert "fuji_international_speedway" in ids

    def test_display_name_is_first(self, seed_result):
        items = build_location_display_items(seed_result)
        for display, loc_id in items:
            assert display  # not empty
            assert loc_id  # not empty

    def test_failed_seed_returns_empty(self):
        failed = _make_failed_seed()
        assert build_location_display_items(failed) == []

    def test_location_id_is_track_location_id(self, seed_result):
        items = build_location_display_items(seed_result)
        ids = {t[1] for t in items}
        assert "mount_panorama_circuit" in ids


# ---------------------------------------------------------------------------
# build_layout_display_items
# ---------------------------------------------------------------------------

class TestBuildLayoutDisplayItems:
    def test_fuji_has_two_layouts(self, seed_result):
        items = build_layout_display_items(seed_result, "fuji_international_speedway")
        assert len(items) == 2

    def test_returns_display_name_and_id(self, seed_result):
        items = build_layout_display_items(seed_result, "fuji_international_speedway")
        for display, lay_id in items:
            assert display
            assert lay_id

    def test_first_fuji_layout_is_full_course(self, seed_result):
        items = build_layout_display_items(seed_result, "fuji_international_speedway")
        assert "Full Course" in items[0][0]

    def test_unknown_location_returns_empty(self, seed_result):
        items = build_layout_display_items(seed_result, "nonexistent_track_xyz")
        assert items == []

    def test_failed_seed_returns_empty(self):
        failed = _make_failed_seed()
        items = build_layout_display_items(failed, "fuji_international_speedway")
        assert items == []

    def test_layout_ids_correct_format(self, seed_result):
        items = build_layout_display_items(seed_result, "fuji_international_speedway")
        for _, lay_id in items:
            assert lay_id.startswith("fuji_international_speedway")

    def test_spa_has_two_layouts(self, seed_result):
        items = build_layout_display_items(seed_result, "circuit_de_spa_francorchamps")
        assert len(items) >= 2


# ---------------------------------------------------------------------------
# get_selected_location
# ---------------------------------------------------------------------------

class TestGetSelectedLocation:
    def test_resolves_known_location(self, seed_result):
        loc = get_selected_location(seed_result, "fuji_international_speedway")
        assert loc is not None
        assert loc.track_location_id == "fuji_international_speedway"

    def test_unknown_location_returns_none(self, seed_result):
        loc = get_selected_location(seed_result, "nonexistent_xyz")
        assert loc is None

    def test_empty_string_returns_none(self, seed_result):
        loc = get_selected_location(seed_result, "")
        assert loc is None


# ---------------------------------------------------------------------------
# get_selected_layout
# ---------------------------------------------------------------------------

class TestGetSelectedLayout:
    def test_resolves_fuji_full_course(self, seed_result):
        lay = get_selected_layout(
            seed_result,
            "fuji_international_speedway",
            "fuji_international_speedway__full_course",
        )
        assert lay is not None
        assert lay.length_m == 4563.0

    def test_unknown_location_returns_none(self, seed_result):
        lay = get_selected_layout(seed_result, "nonexistent_xyz", "some_lay")
        assert lay is None

    def test_unknown_layout_returns_none(self, seed_result):
        lay = get_selected_layout(
            seed_result, "fuji_international_speedway", "fuji__nonexistent"
        )
        assert lay is None

    def test_empty_location_returns_none(self, seed_result):
        lay = get_selected_layout(seed_result, "", "fuji_international_speedway__full_course")
        assert lay is None


# ---------------------------------------------------------------------------
# build_prompt_preview
# ---------------------------------------------------------------------------

class TestBuildPromptPreview:
    def test_empty_ids_return_placeholder(self, seed_result):
        text = build_prompt_preview(seed_result, "", "")
        assert "Select" in text

    def test_empty_location_returns_placeholder(self, seed_result):
        text = build_prompt_preview(seed_result, "", "fuji_international_speedway__full_course")
        assert "Select" in text

    def test_fuji_full_course_returns_content(self, seed_result):
        text = build_prompt_preview(
            seed_result,
            "fuji_international_speedway",
            "fuji_international_speedway__full_course",
        )
        assert "Fuji" in text
        assert len(text) > 100

    def test_failed_seed_returns_error_text(self):
        failed = _make_failed_seed()
        text = build_prompt_preview(failed, "fuji", "fuji__full")
        assert "failed" in text.lower() or "error" in text.lower()

    def test_prompt_contains_data_caveat_for_not_modelled(self, seed_result):
        text = build_prompt_preview(
            seed_result,
            "fuji_international_speedway",
            "fuji_international_speedway__full_course",
        )
        assert "CAVEAT" in text or "seed" in text.lower() or "calibrat" in text.lower()

    def test_prompt_is_string(self, seed_result):
        text = build_prompt_preview(
            seed_result,
            "fuji_international_speedway",
            "fuji_international_speedway__full_course",
        )
        assert isinstance(text, str)


# ---------------------------------------------------------------------------
# describe_seed_load_status
# ---------------------------------------------------------------------------

class TestDescribeSeedLoadStatus:
    def test_success_contains_version(self, seed_result):
        text = describe_seed_load_status(seed_result)
        assert "1.0" in text or "v" in text

    def test_success_contains_location_count(self, seed_result):
        text = describe_seed_load_status(seed_result)
        assert "41" in text

    def test_success_contains_layout_count(self, seed_result):
        text = describe_seed_load_status(seed_result)
        assert "121" in text

    def test_failed_seed_shows_failed(self):
        failed = _make_failed_seed()
        text = describe_seed_load_status(failed)
        assert "FAILED" in text

    def test_failed_seed_contains_error(self):
        failed = _make_failed_seed()
        text = describe_seed_load_status(failed)
        assert "File not found" in text

    def test_no_warnings_no_warning_str(self, seed_result):
        text = describe_seed_load_status(seed_result)
        if not seed_result.warnings:
            assert "warning" not in text.lower()

    def test_with_warnings_shows_count(self):
        meta = TrackSeedMetadata(
            schema_name="track_modelling_seed",
            schema_version="1.0",
            generated_utc="2026-01-01T00:00:00Z",
            purpose="test",
            track_count=1,
            layout_count_in_seed=1,
        )
        sr = TrackSeedLoadResult(
            success=True,
            metadata=meta,
            track_locations=[],
            warnings=["W1", "W2"],
        )
        text = describe_seed_load_status(sr)
        assert "2 warning" in text


# ---------------------------------------------------------------------------
# CALIBRATION_CAR_BOUNDARY_NOTE
# ---------------------------------------------------------------------------

class TestBoundaryNote:
    def test_boundary_note_is_non_empty_string(self):
        assert isinstance(CALIBRATION_CAR_BOUNDARY_NOTE, str)
        assert len(CALIBRATION_CAR_BOUNDARY_NOTE) > 50

    def test_boundary_note_mentions_porsche(self):
        assert "Porsche" in CALIBRATION_CAR_BOUNDARY_NOTE or "911" in CALIBRATION_CAR_BOUNDARY_NOTE

    def test_boundary_note_mentions_car_independence(self):
        note = CALIBRATION_CAR_BOUNDARY_NOTE.lower()
        assert "car-independent" in note or "independent" in note or "geometry" in note


# ---------------------------------------------------------------------------
# SEED_WARNING_TEXT
# ---------------------------------------------------------------------------

class TestSeedWarningText:
    def test_seed_warning_is_non_empty(self):
        assert isinstance(SEED_WARNING_TEXT, str)
        assert len(SEED_WARNING_TEXT) > 30

    def test_seed_warning_mentions_seed(self):
        assert "SEED" in SEED_WARNING_TEXT or "seed" in SEED_WARNING_TEXT

    def test_seed_warning_mentions_calibration(self):
        assert "calibrat" in SEED_WARNING_TEXT.lower()
