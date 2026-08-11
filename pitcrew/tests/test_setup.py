"""Setup sheets, mid-session changes and car range records."""
from __future__ import annotations

import pytest

from pitcrew.setup.sheet import (
    RangeRecord,
    SetupChange,
    SetupError,
    SetupSheet,
)
from pitcrew.setup.vocabulary import (
    RANGE_KEY_NAMES,
    SETUP_KEY_NAMES,
    describe,
    unknown_keys,
)
from pitcrew.store.db import Store


def a_sheet(**overrides) -> SetupSheet:
    fields = dict(
        car_name="Porsche 911 RSR (991) '17",
        sheet_name="Fuji race v2",
        values={"rh_f": 62, "rh_r": 70, "arb_f": 6, "arb_r": 4,
                "toe_f": 0.00, "toe_r": 0.08, "bb": -1},
        gears=[3.10, 2.28, 1.79, 1.46, 1.22, 1.04],
        performance={"powerRestrictor": 100, "ecuOutput": 100, "ballastKg": 0},
        build={"bhp": 525, "weightKg": 1300, "pp": 730.12},
    )
    fields.update(overrides)
    return SetupSheet(**fields)


def a_range(**overrides) -> RangeRecord:
    fields = dict(
        car_name="Porsche 911 RSR (991) '17",
        measured_date="2026-08-11",
        ranges={"rh_f": [55, 80], "arb_f": [1, 10], "toe_f": [-1, 1],
                "bb": [-5, 5]},
        game_version="1.70",
        verified=True,
    )
    fields.update(overrides)
    return RangeRecord(**fields)


# ---------------------------------------------------------------- vocabulary

def test_vocabulary_matches_the_contract():
    """These exact keys are what the tune builder's range library uses."""
    assert set(SETUP_KEY_NAMES) == {
        "rh_f", "rh_r", "nf_f", "nf_r", "arb_f", "arb_r",
        "dc_f", "dc_r", "de_f", "de_r", "cam_f", "cam_r",
        "toe_f", "toe_r", "lsd_i", "lsd_a", "lsd_b", "awd",
        "df_f", "df_r", "bb", "top", "fg",
    }


def test_awd_has_no_slider_range():
    assert "awd" in SETUP_KEY_NAMES
    assert "awd" not in RANGE_KEY_NAMES


def test_no_channels_gt7_does_not_have():
    """Tyre pressure, caster, brake pressure and damper splits do not exist."""
    forbidden = {"pressure", "caster", "brake_pressure", "bump_hs", "bump_ls"}
    assert forbidden.isdisjoint(SETUP_KEY_NAMES)


def test_keys_carry_a_unit_and_a_group():
    for key in SETUP_KEY_NAMES:
        spec = describe(key)
        assert spec is not None
        assert spec.group


def test_unknown_keys_are_reported():
    assert unknown_keys({"rh_f": 1, "tyre_psi": 30}) == ("tyre_psi",)


# --------------------------------------------------------------------- sheet

def test_sheet_exports_in_contract_shape():
    payload = a_sheet().as_export()
    assert payload["sheetName"] == "Fuji race v2"
    assert payload["values"]["rh_f"] == 62
    assert payload["gears"][0] == 3.10
    assert payload["build"]["pp"] == 730.12


def test_unentered_values_are_absent_not_zero():
    """A zero rear toe and an unentered rear toe are different claims."""
    sheet = a_sheet(values={"rh_f": 62, "toe_r": None})
    payload = sheet.as_export()
    assert payload["values"]["toe_r"] is None
    assert "cam_r" not in payload["values"]
    assert sheet.entered_values() == {"rh_f": 62}
    assert "cam_r" in sheet.missing_keys()


def test_a_key_outside_the_vocabulary_is_refused():
    with pytest.raises(SetupError, match="shared setup vocabulary"):
        a_sheet(values={"tyre_psi": 30}).validate()


def test_a_sheet_needs_a_car_and_a_name():
    with pytest.raises(SetupError, match="needs a car"):
        a_sheet(car_name=" ").validate()
    with pytest.raises(SetupError, match="needs a name"):
        a_sheet(sheet_name="").validate()


def test_gears_must_descend():
    """An ascending pair means the sheet was transcribed out of order."""
    with pytest.raises(SetupError, match="not shorter than"):
        a_sheet(gears=[3.10, 2.28, 2.50]).validate()


def test_gears_must_be_positive():
    with pytest.raises(SetupError, match="must be positive"):
        a_sheet(gears=[3.10, 0.0]).validate()


def test_too_many_gears_is_refused():
    with pytest.raises(SetupError, match="more than GT7 allows"):
        a_sheet(gears=[10 - i * 0.5 for i in range(12)]).validate()


def test_empty_subsections_are_omitted():
    payload = a_sheet(gears=[], performance={}, build={}).as_export()
    assert "gears" not in payload
    assert "performance" not in payload
    assert "build" not in payload


# ------------------------------------------------------------------- changes

def test_change_exports_in_contract_shape():
    change = SetupChange(from_lap=5, key="arb_r", from_value=4, to_value=3)
    assert change.as_export() == {
        "fromLap": 5, "key": "arb_r", "from": 4, "to": 3}


def test_change_key_must_be_in_the_vocabulary():
    with pytest.raises(SetupError, match="shared setup vocabulary"):
        SetupChange(from_lap=5, key="wing", from_value=1, to_value=2).validate()


def test_change_cannot_precede_lap_one():
    with pytest.raises(SetupError, match="lap 1 at the earliest"):
        SetupChange(from_lap=0, key="bb", from_value=-1, to_value=-2).validate()


# -------------------------------------------------------------- range record

def test_range_record_exports_in_contract_shape():
    payload = a_range().as_export()
    assert payload["car"] == "Porsche 911 RSR (991) '17"
    assert payload["verified"] is True
    assert payload["r"]["rh_f"] == [55, 80]


def test_unverified_ranges_say_so():
    """Verified means read off the screen; it decides whether a sheet is enterable."""
    assert a_range(verified=False).as_export()["verified"] is False


def test_inverted_range_is_refused():
    with pytest.raises(SetupError, match="inverted"):
        a_range(ranges={"rh_f": [80, 55]}).validate()


def test_malformed_range_is_refused():
    with pytest.raises(SetupError, match=r"\[min, max\]"):
        a_range(ranges={"rh_f": [55]}).validate()


def test_range_key_must_bear_a_range():
    with pytest.raises(SetupError, match="range-bearing"):
        a_range(ranges={"awd": [0, 100]}).validate()


def test_fraction_of_range_reasons_in_percent_not_absolutes():
    record = a_range()
    assert record.fraction_of_range("rh_f", 55) == 0.0
    assert record.fraction_of_range("rh_f", 80) == 1.0
    assert round(record.fraction_of_range("toe_f", 0.0), 3) == 0.5


def test_fraction_is_none_for_an_uncovered_key():
    assert a_range().fraction_of_range("nf_f", 3.5) is None
    assert a_range().covers("nf_f") is False


# --------------------------------------------------------------------- store

def test_sheet_round_trips(store: Store):
    sheet_id = store.save_setup_sheet(a_sheet())
    loaded = store.get_setup_sheet(sheet_id)
    assert loaded.sheet_name == "Fuji race v2"
    assert loaded.values["rh_f"] == 62
    assert loaded.gears == [3.10, 2.28, 1.79, 1.46, 1.22, 1.04]
    assert loaded.build["bhp"] == 525


def test_saving_the_same_sheet_twice_updates_it(store: Store):
    first = store.save_setup_sheet(a_sheet())
    second = store.save_setup_sheet(a_sheet(values={"rh_f": 64}))
    assert first == second
    assert store.get_setup_sheet(first).values["rh_f"] == 64
    assert len(store.list_setup_sheets()) == 1


def test_sheets_list_per_car(store: Store):
    store.save_setup_sheet(a_sheet())
    store.save_setup_sheet(a_sheet(car_name="BMW M6 GT3", sheet_name="Spa v1"))
    assert len(store.list_setup_sheets()) == 2
    assert len(store.list_setup_sheets("BMW M6 GT3")) == 1


def test_an_invalid_sheet_never_reaches_the_database(store: Store):
    with pytest.raises(SetupError):
        store.save_setup_sheet(a_sheet(values={"tyre_psi": 30}))
    assert store.list_setup_sheets() == []


def test_session_records_which_sheet_was_fitted(store: Store, event_id: int):
    sheet_id = store.save_setup_sheet(a_sheet())
    session_id = store.start_session(event_id, "practice", setup_sheet_id=sheet_id)
    assert store.get_session(session_id)["setup_sheet_id"] == sheet_id


def test_changes_round_trip_in_lap_order(store: Store, event_id: int):
    session_id = store.start_session(event_id, "practice")
    store.add_setup_change(session_id, SetupChange(6, "bb", -1, -2))
    store.add_setup_change(session_id, SetupChange(5, "arb_r", 4, 3))

    changes = store.list_setup_changes(session_id)
    assert [c.from_lap for c in changes] == [5, 6]
    assert changes[0].key == "arb_r"


def test_range_record_round_trips(store: Store):
    store.save_range_record(a_range())
    loaded = store.get_range_record("Porsche 911 RSR (991) '17")
    assert loaded.verified is True
    assert loaded.ranges["arb_f"] == [1, 10]
    assert loaded.game_version == "1.70"


def test_range_record_is_one_per_car(store: Store):
    store.save_range_record(a_range())
    store.save_range_record(a_range(ranges={"rh_f": [50, 90]}, verified=False))
    loaded = store.get_range_record("Porsche 911 RSR (991) '17")
    assert loaded.ranges["rh_f"] == [50, 90]
    assert loaded.verified is False
    assert store.cars_with_ranges() == ["Porsche 911 RSR (991) '17"]


def test_unknown_car_has_no_range_record(store: Store):
    assert store.get_range_record("Nothing At All") is None
