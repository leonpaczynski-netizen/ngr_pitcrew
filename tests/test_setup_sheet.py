"""The setup sheet as DATA — the keystone of removing the classic UI.

The authoritative value of every setup field currently lives in a QDoubleSpinBox on the
classic form, which is precisely why the old UI cannot be deleted: the app's setup state
IS the old UI. These tests pin the pure model that replaces it.
"""

from strategy.setup_sheet import (
    ALL_FIELDS, CONTEXT_FIELDS, DISCIPLINES, NUMERIC_FIELDS, PURPOSE, SetupSheet,
    empty_sheet, normalise_discipline, sheet_from_dict,
)


class TestNormalisation:
    def test_an_empty_dict_yields_complete_defaults(self):
        s = empty_sheet()
        for name, default, dp in NUMERIC_FIELDS:
            assert s.get(name) == round(float(default), dp)
        assert s.get("tyre_front") == "Racing Medium"
        assert s.gear_ratios == ()

    def test_values_are_coerced_and_rounded_to_their_field_precision(self):
        s = sheet_from_dict({"springs_front": "3.500000001", "arb_front": "5",
                             "camber_front": 1.44})
        assert s.get("springs_front") == 3.5
        assert s.get("arb_front") == 5.0
        assert s.get("camber_front") == 1.4

    def test_garbage_falls_back_to_the_default_instead_of_raising(self):
        s = sheet_from_dict({"arb_front": "not a number", "toe_rear": None})
        assert s.get("arb_front") == 5.0
        assert s.get("toe_rear") == 0.05

    def test_none_input_is_a_valid_empty_sheet(self):
        assert sheet_from_dict(None).get("arb_front") == 5.0

    def test_gear_ratios_drop_unset_entries_and_keep_order(self):
        s = sheet_from_dict({"gear_ratios": [3.91, 2.29, 0, None, 1.65, "1.30"]})
        assert s.gear_ratios == (3.91, 2.29, 1.65, 1.30)

    def test_unknown_fields_are_preserved_not_dropped(self):
        """The advisor and the DB round-trip fields this model does not know."""
        s = sheet_from_dict({"some_future_field": "keep me", "arb_front": 6})
        assert s.get("some_future_field") == "keep me"
        assert s.as_dict()["some_future_field"] == "keep me"

    def test_text_is_stripped(self):
        assert sheet_from_dict({"setup_label": "  Setup 3  "}).get("setup_label") == "Setup 3"


class TestAuthored:
    def test_a_default_sheet_is_not_an_authored_setup(self):
        assert empty_sheet().is_authored is False

    def test_any_real_value_makes_it_authored(self):
        assert sheet_from_dict({"arb_front": 7}).is_authored is True

    def test_gears_alone_make_it_authored(self):
        assert sheet_from_dict({"gear_ratios": [3.9, 2.3]}).is_authored is True

    def test_context_alone_does_not(self):
        """Knowing the car and track is not the same as having a setup."""
        s = sheet_from_dict({"car": "Porsche Cayman GT4", "track": "Watkins Glen",
                             "captured_at": "2026-07-23 15:00"})
        assert s.is_authored is False


class TestDiff:
    def test_identical_sheets_do_not_differ(self):
        a = sheet_from_dict({"arb_front": 5, "springs_front": 3.5})
        b = sheet_from_dict({"arb_front": 5.0, "springs_front": "3.50"})
        assert a.diff(b) == {}
        assert a.matches(b) is True

    def test_a_real_change_is_reported_both_ways(self):
        a = sheet_from_dict({"arb_front": 5})
        b = sheet_from_dict({"arb_front": 4})
        assert a.diff(b) == {"arb_front": (5.0, 4.0)}
        assert a.matches(b) is False

    def test_recapturing_the_same_setup_later_is_not_a_change(self):
        a = sheet_from_dict({"arb_front": 5, "captured_at": "2026-07-23 15:00"})
        b = sheet_from_dict({"arb_front": 5, "captured_at": "2026-07-23 15:30"})
        assert a.matches(b) is True

    def test_context_fields_are_excluded_from_the_diff(self):
        for name in CONTEXT_FIELDS:
            assert name not in sheet_from_dict({name: "x"}).diff(empty_sheet())

    def test_gear_changes_are_detected(self):
        a = sheet_from_dict({"gear_ratios": [3.9, 2.3]})
        b = sheet_from_dict({"gear_ratios": [3.9, 2.2]})
        assert "gear_ratios" in a.diff(b)

    def test_diffing_a_non_sheet_is_empty_not_an_error(self):
        assert empty_sheet().diff(None) == {}


class TestMerge:
    def test_merge_returns_a_new_normalised_sheet(self):
        base = sheet_from_dict({"arb_front": 5})
        merged = base.merge({"arb_front": "4", "arb_rear": 3})
        assert merged.get("arb_front") == 4.0
        assert merged.get("arb_rear") == 3.0
        assert base.get("arb_front") == 5.0        # the original is untouched
        assert isinstance(merged, SetupSheet)

    def test_merging_nothing_is_the_same_sheet(self):
        base = sheet_from_dict({"arb_front": 5})
        assert base.merge(None) is base
        assert base.merge({}) is base

    def test_merge_preserves_unknown_fields(self):
        s = sheet_from_dict({"custom": "x"}).merge({"arb_front": 6})
        assert s.get("custom") == "x"


class TestDisciplines:
    def test_there_are_exactly_two(self):
        assert DISCIPLINES == ("race", "qualifying")

    def test_each_maps_to_an_authority_purpose(self):
        assert PURPOSE == {"race": "Race", "qualifying": "Qualifying"}

    def test_anything_unknown_falls_back_to_race(self):
        assert normalise_discipline("base") == "race"
        assert normalise_discipline(None) == "race"
        assert normalise_discipline("Qualifying") == "qualifying"


class TestFieldCoverage:
    def test_the_model_covers_every_field_the_classic_form_serialises(self):
        """Pinned against SetupBuilderMixin._current_setup_dict so a sheet round-trips
        through the existing save/apply paths unchanged."""
        classic = {
            "name", "car", "setup_label", "track", "condition", "setup_type",
            "ride_height_front", "ride_height_rear", "springs_front", "springs_rear",
            "dampers_front_comp", "dampers_front_ext", "dampers_rear_comp",
            "dampers_rear_ext", "arb_front", "arb_rear", "camber_front", "camber_rear",
            "toe_front", "toe_rear", "aero_front", "aero_rear", "lsd_initial",
            "lsd_accel", "lsd_decel", "lsd_front_initial", "lsd_front_accel",
            "lsd_front_decel", "tvcd", "torque_distribution_rear", "brake_bias_front",
            "ballast_kg", "ballast_position", "power_restrictor", "tyre_front",
            "tyre_rear", "ecu_ingame", "ecu_ingame_output", "transmission_type",
            "nitrous_type", "nitrous_output", "notes", "ecu_recommendation",
            "bop_race", "gear_ratios", "final_drive", "transmission_max_speed_kmh",
            "captured_at",
        }
        assert classic - set(ALL_FIELDS) == set()
