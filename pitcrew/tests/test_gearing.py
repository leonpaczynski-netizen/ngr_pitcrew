"""The gearbox as fitted, and the questions it answers."""
from __future__ import annotations

import math

import pytest

from pitcrew.analysis.gearing import (
    final_drive,
    fitted_ratios,
    gearbox_changed_mid_session,
    gearing_export,
    limiter_rpm,
    matches_sheet,
)
from pitcrew.analysis.session import LapInput
from pitcrew.export.payload import Meta, build_payload, validate

from .test_corners import frame, synthetic_lap

RATIOS = [2.727, 1.925, 1.529, 1.288, 1.152, 1.062]
RADIUS = 0.35
FINAL = 3.55


def geared_frames(*, gear: int = 6, speed_kph: float = 300.0,
                  limiter: bool = False, count: int = 20) -> list[dict]:
    """Frames whose rpm is consistent with the ratios, radius and final drive."""
    wheel_hz = speed_kph / 3.6 / (2 * math.pi * RADIUS)
    rpm = wheel_hz * RATIOS[gear - 1] * FINAL * 60.0
    return [frame(i * 2.0, speed_kph, i, gear=gear, rpm=round(rpm, 0),
                  rev_limiter=1 if limiter else 0, tyre_radius_m=RADIUS)
            for i in range(count)]


_UNSET = object()


def a_lap(lap_num: int = 1, *, frames=_UNSET, ratios=RATIOS,
          **overrides) -> LapInput:
    fields = dict(lap_num=lap_num, lap_time_ms=94_000, fuel_start=90.0,
                  fuel_end=86.6, gear_ratios=list(ratios) if ratios else None,
                  frames=geared_frames() if frames is _UNSET else frames)
    fields.update(overrides)
    return LapInput(**fields)


# ------------------------------------------------------------------- ratios

def test_fitted_ratios_come_off_the_stream():
    assert fitted_ratios([a_lap()]) == RATIOS


def test_no_ratios_recorded_reads_as_unknown():
    assert fitted_ratios([a_lap(ratios=None)]) is None


def test_matching_the_sheet_is_reported():
    """The question that is otherwise invisible until a session is wasted."""
    assert matches_sheet([a_lap()], RATIOS) is True


def test_a_different_gearbox_is_caught():
    sheet = [2.9, 1.9, 1.5, 1.3, 1.15, 1.06]
    assert matches_sheet([a_lap()], sheet) is False


def test_float_noise_is_not_a_different_gearbox():
    sheet = [r + 0.001 for r in RATIOS]
    assert matches_sheet([a_lap()], sheet) is True


def test_no_sheet_means_no_verdict_rather_than_a_guess():
    assert matches_sheet([a_lap()], None) is None
    assert matches_sheet([a_lap(ratios=None)], RATIOS) is None


def test_a_mid_session_gearbox_change_is_flagged():
    other = [r * 1.1 for r in RATIOS]
    laps = [a_lap(1), a_lap(2, ratios=other)]
    assert gearbox_changed_mid_session(laps) is True


def test_one_gearbox_throughout_is_not_flagged():
    assert gearbox_changed_mid_session([a_lap(1), a_lap(2)]) is False


# ------------------------------------------------------------------ limiter

def test_the_limiter_is_only_reported_when_it_fired():
    """The highest rpm observed is not the limiter; it is the highest rpm."""
    assert limiter_rpm([a_lap(frames=geared_frames(limiter=False))]) is None


def test_the_limiter_reads_where_the_flag_fired():
    laps = [a_lap(frames=geared_frames(limiter=True))]
    assert limiter_rpm(laps) == pytest.approx(
        laps[0].frames[0]["rpm"], abs=1.0)


# --------------------------------------------------------------- final drive

def test_final_drive_is_derived_from_rpm_against_wheel_speed():
    """GT7 sends the gear ratios but not the final drive, so it is computed."""
    assert final_drive([a_lap()], RATIOS) == pytest.approx(FINAL, abs=0.02)


def test_final_drive_needs_ratios():
    assert final_drive([a_lap()], None) is None


def test_slow_frames_are_ignored_for_final_drive():
    slow = geared_frames(speed_kph=40.0)
    assert final_drive([a_lap(frames=slow)], RATIOS) is None


# -------------------------------------------------------------------- export

def test_gearing_section_shape():
    payload = gearing_export([a_lap(frames=geared_frames(limiter=True))], RATIOS)
    assert payload["fittedRatios"] == RATIOS
    assert payload["ratioSource"] == "telemetry"
    assert payload["matchesSheet"] is True
    assert payload["fittedFinalGear"] == pytest.approx(FINAL, abs=0.02)
    assert "derived" in payload["finalGearSource"]
    assert payload["maxSpeedGear"] == 6
    assert payload["samples"] == 1


def test_the_gearing_constant_needs_top_gear_at_the_limiter():
    """Anywhere else the car simply was not going as fast as the gearing allows."""
    without = gearing_export([a_lap(frames=geared_frames(limiter=False))], RATIOS)
    assert "gearingConstantK" not in without

    with_limiter = gearing_export(
        [a_lap(frames=geared_frames(limiter=True))], RATIOS)
    assert with_limiter["gearingConstantK"] > 0
    assert "top gear" in with_limiter["gearingConstantSource"] or \
        "gear 6" in with_limiter["gearingConstantSource"]


def test_a_session_that_never_hit_the_limiter_says_so():
    payload = gearing_export([a_lap(frames=geared_frames(limiter=False))], RATIOS)
    assert payload["limiterRpm"] is None
    assert "never fired" in payload["limiterRpmSource"]


def test_nothing_known_about_the_box_omits_the_section():
    assert gearing_export([a_lap(ratios=None, frames=None)], None) is None


# ------------------------------------------------------------------ the tow

def test_a_tow_key_anywhere_is_refused():
    """GT7 has no proximity, closing speed or opponents. A tow field would be
    a fabrication by definition."""
    meta = Meta(car="C", circuit="T", date="2026-08-11",
                session_type="practice", packet="C")
    payload = build_payload(meta, gearing={"maxSpeedKph": 300.0,
                                           "towSpeedKph": 312.0})
    problems = validate(payload)
    assert any("tow" in problem for problem in problems)


def test_a_tow_key_nested_deep_is_still_refused():
    meta = Meta(car="C", circuit="T", date="2026-08-11",
                session_type="practice", packet="C")
    payload = build_payload(meta, laps=[{"lap": 1, "timeMs": 1,
                                         "inTow": True}])
    assert any("tow" in problem for problem in validate(payload))


def test_an_honest_gearing_section_passes():
    meta = Meta(car="C", circuit="T", date="2026-08-11",
                session_type="practice", packet="C")
    payload = build_payload(meta, gearing=gearing_export([a_lap()], RATIOS))
    assert validate(payload) == []


# ------------------------------------------------------------- corner gears

def test_corner_gear_fields_are_modal_not_mean():
    """A mean gear of 2.6 is not a gear."""
    from pitcrew.analysis.corner_model import Corner
    from pitcrew.analysis.corners import CountedLap, aggregate_corners
    from pitcrew.analysis.corner_model import CornerModel, SOURCE_AUTO_SEGMENT

    laps = []
    for lap_num, gear in ((1, 2), (2, 2), (3, 3)):
        frames = synthetic_lap(apex_positions=(600.0,))
        for f in frames:
            f["gear"] = gear
        laps.append(CountedLap(lap_num, frames))

    model = CornerModel("t", 1, SOURCE_AUTO_SEGMENT, 2000.0,
                        (Corner("T1", "Turn 1", 480, 600, 720),))
    corner = aggregate_corners(model, laps)[0]
    assert corner["gearMin"] == 2
    assert corner["gearAtApex"] == 2


def test_shifts_in_a_corner_are_counted():
    """Answers 'does 2nd cover all three chicanes without an upshift'."""
    from pitcrew.analysis.corner_model import (
        SOURCE_AUTO_SEGMENT, Corner, CornerModel)
    from pitcrew.analysis.corners import CountedLap, aggregate_corners

    frames = synthetic_lap(apex_positions=(600.0,))
    for f in frames:
        f["gear"] = 2 if f["road_distance_m"] < 620 else 3
    model = CornerModel("t", 1, SOURCE_AUTO_SEGMENT, 2000.0,
                        (Corner("T1", "Turn 1", 480, 600, 720),))
    corner = aggregate_corners(model, [CountedLap(1, frames)])[0]
    assert corner["shiftsInCorner"] == 1


def test_a_corner_taken_in_one_gear_reports_no_shift():
    from pitcrew.analysis.corner_model import (
        SOURCE_AUTO_SEGMENT, Corner, CornerModel)
    from pitcrew.analysis.corners import CountedLap, aggregate_corners

    frames = synthetic_lap(apex_positions=(600.0,))
    for f in frames:
        f["gear"] = 2
    model = CornerModel("t", 1, SOURCE_AUTO_SEGMENT, 2000.0,
                        (Corner("T1", "Turn 1", 480, 600, 720),))
    corner = aggregate_corners(model, [CountedLap(1, frames)])[0]
    assert corner["shiftsInCorner"] == 0
    assert corner["upshiftRpm"] is None


def test_the_upshift_rpm_makes_short_shifting_visible():
    from pitcrew.analysis.corner_model import (
        SOURCE_AUTO_SEGMENT, Corner, CornerModel)
    from pitcrew.analysis.corners import CountedLap, aggregate_corners

    frames = synthetic_lap(apex_positions=(600.0,))
    for f in frames:
        short = f["road_distance_m"] >= 620
        f["gear"] = 3 if short else 2
        f["rpm"] = 6200.0 if short else 7000.0
    model = CornerModel("t", 1, SOURCE_AUTO_SEGMENT, 2000.0,
                        (Corner("T1", "Turn 1", 480, 600, 720),))
    corner = aggregate_corners(model, [CountedLap(1, frames)])[0]
    assert corner["upshiftRpm"] == 6200
