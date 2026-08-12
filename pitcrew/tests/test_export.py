"""The gt7-pitcrew/1.3 payload: assembly, validation and refusal."""
from __future__ import annotations

import json
from dataclasses import replace

import pytest

from pitcrew.analysis import thresholds
from pitcrew.analysis.session import LapInput
from pitcrew.analysis.wear import (
    PHASE_CLIFF,
    PHASE_FLAT,
    PHASE_LINEAR,
    modelled_stint_laps,
    phase_for,
    wear_export,
    wear_per_lap,
)
from pitcrew.export.payload import (
    APP_VERSION,
    FORMAT,
    Derived,
    ExportRefused,
    Meta,
    build_payload,
    to_json,
    validate,
)

from .test_corners import frame


def a_meta(**overrides) -> Meta:
    fields = dict(
        car="Porsche 911 RSR (991) '17",
        circuit="Fuji Speedway (Full)",
        date="2026-08-11",
        session_type="practice",
        packet="C",
        car_category="GR3",
        game_version="1.70",
        compound_front="Racing Medium",
        compound_rear="Racing Medium",
        abs_setting="Weak",
        tcs=1,
        countersteer=False,
        tyre_wear_mult="4x",
        fuel_mult="2x",
    )
    fields.update(overrides)
    return Meta(**fields)


def a_corner(**overrides) -> dict:
    base = {"id": "T1", "name": "Turn 1", "samples": 9, "minSpeedKph": 96.0}
    base.update(overrides)
    return base


def a_lap_row(**overrides) -> dict:
    base = {"lap": 3, "timeMs": 93_912, "valid": True}
    base.update(overrides)
    return base


def a_wear_lap(lap_num: int, **overrides) -> LapInput:
    """One lap, with the tank where it would be that far into a run.

    The fuel channel is what says where one run ends and the next begins, so a
    fixture whose tank refills itself every lap is a fixture of consecutive
    pit stops. Descending from a full tank is what a real run looks like and
    is what the run splitter reads.
    """
    fields = dict(lap_num=lap_num, lap_time_ms=94_000,
                  fuel_start=round(100.0 - 3.4 * (lap_num - 1), 2),
                  fuel_end=round(100.0 - 3.4 * lap_num, 2))
    fields.update(overrides)
    return LapInput(**fields)


def a_stint(laps: int, **final_lap) -> list[LapInput]:
    """A run of `laps` on one set, the gauge read on the last of them.

    Built as a real run rather than as one lap carrying a high lap number,
    because the wear *rate* is per lap the set actually ran. A reading of 60%
    at lap 20 means one thing if the tyres went on at lap 1 and something very
    different if they went on at lap 12.
    """
    return ([a_wear_lap(n, compound="RM") for n in range(1, laps)]
            + [a_wear_lap(laps, compound="RM", **final_lap)])


# ------------------------------------------------------------------ assembly

def test_minimal_payload_is_valid():
    payload = build_payload(a_meta())
    assert validate(payload) == []
    assert payload["format"] == FORMAT
    assert payload["meta"]["appVersion"] == APP_VERSION


def test_sections_the_app_lacks_are_omitted_not_nulled():
    """An omitted section reads as 'not built yet'. Nulls would read as
    'built but nothing measured', which is a different claim."""
    payload = build_payload(a_meta())
    for section in ("setup", "rangeRecord", "session", "laps", "corners",
                    "wear", "strategy", "derived", "notes"):
        assert section not in payload


def test_meta_carries_compound_assists_and_multipliers():
    meta = a_meta().as_export()
    assert meta["compound"]["front"] == "Racing Medium"
    assert meta["assists"]["abs"] == "Weak"
    assert meta["multipliers"]["tyreWear"] == "4x"
    assert meta["carCategory"] == "GR3"


def test_driver_changes_ride_with_the_setup_section():
    payload = build_payload(
        a_meta(),
        setup={"sheetName": "Fuji race v2", "values": {"rh_f": 62}},
        driver_changes=[{"fromLap": 5, "key": "arb_r", "from": 4, "to": 3}])
    assert payload["setup"]["driverChanges"][0]["fromLap"] == 5


def test_derived_restates_the_thresholds():
    """So retuning a detector reads as a change in the detector, not the car."""
    payload = build_payload(a_meta(), derived=Derived(thresholds.as_export()))
    assert payload["derived"]["thresholds"]["lockupPct"] == thresholds.LOCKUP_PCT
    assert payload["derived"]["steerSource"] == "wheelRotation"
    assert payload["derived"]["steerRotationDeg"] == 1080.0


def test_bottoming_reference_travels_with_its_source():
    payload = build_payload(a_meta(), derived=Derived(
        thresholds.as_export(), bottoming_ref_mm={"fl": 31.0}))
    assert payload["derived"]["bottomingRefMm"]["fl"] == 31.0
    assert payload["derived"]["bottomingRefSource"]


def test_json_round_trips():
    payload = build_payload(
        a_meta(corner_model={"source": "auto-segment", "id": "fuji-full",
                             "version": 1}),
        corners=[a_corner()])
    assert json.loads(to_json(payload)) == payload


# ---------------------------------------------------------------- validation

def test_missing_required_meta_is_refused():
    problems = validate(build_payload(a_meta(car="")))
    assert any("meta.car" in p for p in problems)


def test_unknown_session_type_is_refused():
    problems = validate(build_payload(a_meta(session_type="warmup")))
    assert any("sessionType" in p for p in problems)


def test_unknown_packet_format_is_refused():
    problems = validate(build_payload(a_meta(packet="Z")))
    assert any("packet" in p for p in problems)


def test_bad_date_shape_is_refused():
    problems = validate(build_payload(a_meta(date="11/08/2026")))
    assert any("YYYY-MM-DD" in p for p in problems)


def test_numeric_multiplier_is_refused():
    """A string keeps 'Off' representable; a number cannot express it."""
    payload = build_payload(a_meta())
    payload["meta"]["multipliers"]["tyreWear"] = 4
    assert any("must be a string" in p for p in validate(payload))


def test_off_is_a_valid_multiplier():
    assert validate(build_payload(a_meta(tyre_wear_mult="Off"))) == []


def test_bad_abs_setting_is_refused():
    assert any("assists.abs" in p for p in validate(build_payload(a_meta(abs_setting="On"))))


def test_tcs_out_of_range_is_refused():
    assert any("tcs" in p for p in validate(build_payload(a_meta(tcs=9))))


def test_corners_without_a_corner_model_are_refused():
    """Corner ids are meaningless across sessions without the model that made them."""
    problems = validate(build_payload(a_meta(), corners=[a_corner()]))
    assert any("cornerModel is required" in p for p in problems)


def test_corner_without_a_sample_count_is_refused():
    payload = build_payload(
        a_meta(corner_model={"source": "auto-segment", "id": "x", "version": 1}),
        corners=[a_corner(samples=None)])
    assert any("sample count" in p for p in validate(payload))


def test_unknown_corner_model_source_is_refused():
    payload = build_payload(
        a_meta(corner_model={"source": "vibes", "id": "x", "version": 1}),
        corners=[a_corner()])
    assert any("cornerModel.source" in p for p in validate(payload))


def test_formatted_lap_time_string_is_refused():
    payload = build_payload(a_meta(), laps=[a_lap_row(timeMs="1:33.912")])
    assert any("integer milliseconds" in p for p in validate(payload))


def test_to_json_refuses_rather_than_emitting_something_wrong():
    with pytest.raises(ExportRefused, match="would be misread"):
        to_json(build_payload(a_meta(session_type="warmup")))


def test_refusal_lists_every_problem_at_once():
    with pytest.raises(ExportRefused) as excinfo:
        to_json(build_payload(a_meta(session_type="warmup", packet="Z")))
    assert "sessionType" in str(excinfo.value)
    assert "packet" in str(excinfo.value)


# ---------------------------------------------------------------------- wear

def test_wear_channel_is_always_declared_unavailable():
    """GT7 exposes no tyre wear channel in any packet format."""
    assert wear_export([a_wear_lap(1)])["channelAvailable"] is False


def test_phases_are_piecewise_not_linear():
    assert phase_for(0.2) == PHASE_FLAT
    assert phase_for(0.7) == PHASE_LINEAR
    assert phase_for(0.95) == PHASE_CLIFF
    assert phase_for(None) is None


def test_wear_per_lap_needs_a_gauge_reading():
    assert wear_per_lap([a_wear_lap(1), a_wear_lap(2)]) is None


def test_wear_per_lap_uses_the_worst_corner_not_an_average():
    """The stint ends when one tyre is done, not when the car averages done.

    The front-left here is at 80% while the other three are healthy. Averaging
    the axle would call it 60% and the car average 50%, either of which plans
    a longer stint than the front-left can actually survive - and overshooting
    the cliff costs far more than undershooting (CLAUDE.md 5.1).
    """
    laps = a_stint(10, wear_fl=0.8, wear_fr=0.4, wear_rl=0.4, wear_rr=0.4)
    assert wear_per_lap(laps) == 0.08


def test_the_limiting_corner_is_named_not_just_the_number():
    """Which corner is going is the setup finding; the rate is the strategy one."""
    laps = a_stint(10, wear_fl=0.8, wear_fr=0.4, wear_rl=0.4, wear_rr=0.4)
    payload = wear_export(laps)
    assert payload["byDriverGauge"][0]["worstCorner"] == "fl"
    assert payload["byCorner"]["worstCorner"] == "fl"
    assert payload["byCorner"]["frontMinusRear"] == 0.2


def test_the_rate_is_per_lap_the_set_ran_not_per_lap_number():
    """The second stint's tyres did not go on at lap 1.

    Ten laps on the first set to 50% worn, then a stop, then ten laps on the
    second to 50%. Both sets wore at 5% a lap. Dividing by the lap number
    would call the second set 2.5% a lap - half as aggressive as it is - and
    plan a stint twice as long as the tyres can survive.
    """
    laps = (
        [a_wear_lap(n, compound="RM") for n in range(1, 10)]
        + [a_wear_lap(10, compound="RM", wear_fl=0.5, is_pit_lap=True)]
        + [a_wear_lap(n, compound="RM") for n in range(11, 20)]
        + [a_wear_lap(20, compound="RM", wear_fl=0.5)]
    )
    assert wear_per_lap(laps) == 0.05


def test_a_corner_that_was_not_read_stays_null():
    """Null is unread. A zero would read as a fresh tyre and be believed."""
    laps = a_stint(10, wear_fl=0.8)
    reading = wear_export(laps)["byDriverGauge"][0]
    assert reading["fl"] == 0.8
    assert reading["fr"] is None and reading["rl"] is None
    # One corner read is still a usable rate - it is the worst one known.
    assert wear_per_lap(laps) == 0.08
    # But an axle comparison needs both ends, so it declines to invent one.
    assert wear_export(laps)["byCorner"]["frontMinusRear"] is None


def test_stint_length_carries_the_safety_margin():
    """0.85/w, not 1.0/w - the cliff's onset is sharp and asymmetric."""
    laps = a_stint(10, wear_fl=0.5, wear_fr=0.5, wear_rl=0.4, wear_rr=0.4)
    assert modelled_stint_laps(laps) == 17


def test_no_gauge_reading_gives_an_assumed_model_not_a_number():
    payload = wear_export([a_wear_lap(1), a_wear_lap(2)])
    assert payload["modelledStintLaps"] is None
    assert payload["modelConfidence"] == "assumed"


def test_a_reading_at_the_race_multiplier_is_measured():
    """Measured only once the driver has said the set went on fresh.

    Without that, the rate divides a reading by laps whose set could have been
    half worn when the run started - which is arithmetic on an assumption, and
    the roll-up says so rather than calling it measured.
    """
    laps = a_stint(10, wear_fl=0.5, wear_fr=0.5, wear_rl=0.4, wear_rr=0.4)
    laps[0] = replace(laps[0], tyres_fresh=True)
    payload = wear_export(laps)
    assert payload["modelConfidence"] == "measured"


def test_an_undeclared_set_is_assumed_not_measured():
    payload = wear_export(a_stint(10, wear_fl=0.5, wear_fr=0.5, wear_rl=0.4,
                                  wear_rr=0.4))
    assert payload["modelConfidence"] == "assumed"
    assert "byRun" in payload["modelConfidenceBasis"]
    assert payload["byRun"][0]["assumesFreshAtLap"] == 1
    assert payload["byDriverGauge"][0]["source"] == "driver-gauge"


def test_a_converted_figure_is_never_presented_as_measured():
    """Multiplier linearity is assumed, never demonstrated."""
    laps = a_stint(10, wear_fl=0.5, wear_fr=0.5, wear_rl=0.4, wear_rr=0.4)
    laps[0] = replace(laps[0], tyres_fresh=True)
    payload = wear_export(laps, calibrated_at_race_multiplier=False)
    assert payload["modelConfidence"] == "converted"
    assert "ASSUMED" in payload["modelBasis"]


def test_degradation_is_reported_with_the_phase_it_was_fitted_in():
    laps = [a_wear_lap(1, lap_time_ms=93_000),
            a_wear_lap(2, lap_time_ms=93_200),
            a_wear_lap(3, lap_time_ms=93_600),
            a_wear_lap(4, lap_time_ms=93_800),
            a_wear_lap(5, lap_time_ms=94_000),
            a_wear_lap(6, lap_time_ms=94_200, wear_fl=0.7, wear_fr=0.7,
                       wear_rl=0.6, wear_rr=0.6)]
    payload = wear_export(laps)
    assert payload["byLapTime"]["degradationMsPerLap"] > 0
    assert payload["byLapTime"]["phase"] == PHASE_LINEAR
    assert payload["byLapTime"]["confidence"] == "low"


def test_temperature_trend_reports_front_rear_asymmetry():
    frames = [frame(i * 2.0, 200.0, i, temp_fl=95.0, temp_fr=95.0,
                    temp_rl=85.0, temp_rr=85.0) for i in range(20)]
    laps = [a_wear_lap(n, frames=frames) for n in (1, 2, 3)]
    payload = wear_export(laps)
    assert payload["byTemp"]["frontRearAsymmetryC"] == 10.0
    assert payload["byTemp"]["confidence"] == "low"


def test_wear_section_validates_inside_a_payload():
    laps = a_stint(10, wear_fl=0.5, wear_fr=0.5, wear_rl=0.4, wear_rr=0.4)
    payload = build_payload(a_meta(), wear=wear_export(laps))
    assert validate(payload) == []


def test_wear_fraction_above_one_is_refused():
    payload = build_payload(a_meta(), wear={
        "channelAvailable": False,
        "byDriverGauge": [{"lap": 6, "fl": 55, "fr": 0.4,
                           "rl": 0.4, "rr": 0.4}],
    })
    assert any("fraction consumed" in p for p in validate(payload))


def test_a_gauge_entry_naming_no_corner_is_refused():
    """A row of nulls dressed as evidence is worse than no row."""
    payload = build_payload(a_meta(), wear={
        "channelAvailable": False,
        "byDriverGauge": [{"lap": 6, "fl": None, "fr": None,
                           "rl": None, "rr": None}],
    })
    assert any("no corner reading" in p for p in validate(payload))


def test_claiming_a_wear_channel_exists_is_refused():
    payload = build_payload(a_meta(), wear={"channelAvailable": True})
    assert any("no tyre wear channel" in p for p in validate(payload))
