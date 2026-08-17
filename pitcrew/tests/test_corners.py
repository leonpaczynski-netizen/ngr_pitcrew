"""Corner detection and aggregation."""
from __future__ import annotations

import math

from pitcrew.analysis import thresholds
from pitcrew.analysis.corner_model import (
    SOURCE_AUTO_SEGMENT,
    Corner,
    CornerModel,
    detect_corners,
    model_id_for,
)
from pitcrew.analysis.corners import (
    CountedLap,
    _frames_for_ms,
    aggregate_corners,
    bottoming_inferable,
    bottoming_reference,
    bottoming_references,
    observed_minimum,
)

INTERVAL_MS = 16.67


def frame(distance_m: float, speed_kph: float, index: int, **overrides) -> dict:
    """One telemetry frame with everything present and benign."""
    base = {
        "t_ms": round(index * INTERVAL_MS),
        "lap_distance_m": distance_m,
        # The road plane's fourth coefficient. Present because the on-disk
        # format carries it; nothing reads it.
        "road_plane_d": -180.0,
        # GT7's in-game clock: where in the game day this frame was driven.
        "time_of_day_ms": 50_400_000,
        "fuel_l": 60.0,
        "speed_kph": speed_kph,
        "throttle_pct": 100.0,
        "brake_pct": 0.0,
        "steering_deg": 0.0,
        "steering_norm": 0.0,
        "gear": 4,
        "rpm": 7000.0,
        "yaw_rate": 0.0,
        "lat_g": 0.0,
        "pos_x": 0.0, "pos_y": 0.0, "pos_z": 0.0,
        "slip_fl": 1.0, "slip_fr": 1.0, "slip_rl": 1.0, "slip_rr": 1.0,
        "susp_mm_fl": 60.0, "susp_mm_fr": 60.0,
        "susp_mm_rl": 65.0, "susp_mm_rr": 65.0,
        "temp_fl": 80.0, "temp_fr": 80.0, "temp_rl": 80.0, "temp_rr": 80.0,
        "body_height_mm": 70.0,
        "surf_fl": "T", "surf_fr": "T", "surf_rl": "T", "surf_rr": "T",
        "road_plane_y": 1.0,
        "rev_limiter": 0,
        "tyre_radius_m": 0.35,
    }
    base.update(overrides)
    return base


def synthetic_lap(apex_positions=(300.0, 900.0, 1500.0), *,
                  lap_length_m: float = 2000.0,
                  straight_kph: float = 240.0,
                  apex_kph: float = 90.0,
                  corner_half_width_m: float = 120.0,
                  **frame_overrides) -> list[dict]:
    """A lap whose speed dips smoothly at each named apex."""
    frames = []
    step = 2.0
    index = 0
    distance = 0.0
    while distance <= lap_length_m:
        speed = straight_kph
        for apex in apex_positions:
            offset = abs(distance - apex)
            if offset < corner_half_width_m:
                # cosine bowl: slowest at the apex, back to straight speed at the edge
                depth = (straight_kph - apex_kph) * 0.5 * (
                    1.0 + math.cos(math.pi * offset / corner_half_width_m))
                speed = min(speed, straight_kph - depth)
        frames.append(frame(distance, speed, index, **frame_overrides))
        distance += step
        index += 1
    return frames


def a_model(corners=None) -> CornerModel:
    corners = corners or (
        Corner("T1", "Turn 1", 200.0, 300.0, 400.0),
    )
    return CornerModel("test-track", 1, SOURCE_AUTO_SEGMENT, 2000.0, tuple(corners))


def one_corner(frames, corner=None, **kwargs) -> dict:
    """The aggregate for a single-corner model over a single lap."""
    corner = corner or Corner("T1", "Turn 1", 480, 600, 720)
    return aggregate_corners(a_model([corner]), [CountedLap(1, frames)],
                             **kwargs)[0]


# ------------------------------------------------------------------ detection

def test_detects_each_corner_once():
    model = detect_corners(synthetic_lap(), "test-track")
    assert model is not None
    assert [c.id for c in model.corners] == ["T1", "T2", "T3"]


def test_corners_are_numbered_in_lap_order():
    model = detect_corners(synthetic_lap(), "test-track")
    apexes = [c.apex_m for c in model.corners]
    assert apexes == sorted(apexes)
    assert model.corners[0].apex_m < 400
    assert model.corners[2].apex_m > 1400


def test_apex_is_the_minimum_speed_point():
    model = detect_corners(synthetic_lap(apex_positions=(600.0,)), "test-track")
    assert abs(model.corners[0].apex_m - 600.0) < 20.0


def test_corner_windows_bracket_the_apex():
    model = detect_corners(synthetic_lap(), "test-track")
    for corner in model.corners:
        assert corner.start_m < corner.apex_m < corner.end_m


def test_corner_windows_do_not_overlap():
    model = detect_corners(synthetic_lap(), "test-track")
    for earlier, later in zip(model.corners, model.corners[1:]):
        assert earlier.end_m <= later.start_m


def test_a_shallow_lift_is_not_a_corner():
    """Below the prominence threshold it is a lift, not a corner."""
    shallow = synthetic_lap(apex_positions=(600.0,), straight_kph=240.0,
                            apex_kph=235.0)
    assert detect_corners(shallow, "test-track") is None


def test_prominence_is_measured_against_the_neighbouring_apexes():
    """A minimum the car never accelerates away from is one corner, not two.

    The test used to scan to the ends of the lap, so the main straight
    satisfied every candidate and the filter was a near no-op: the second half
    of a complex came out as its own corner and renumbered everything after it.
    """
    def speed_at(distance: float) -> float:
        for lo, hi, a, b in ((0.0, 400.0, 240.0, 240.0),
                             (400.0, 500.0, 240.0, 90.0),     # into the corner
                             (500.0, 700.0, 90.0, 110.0),     # a partial pickup
                             (700.0, 800.0, 110.0, 110.0),    # never a straight
                             (800.0, 1000.0, 110.0, 98.0),    # second minimum
                             (1000.0, 1200.0, 98.0, 240.0),   # and away
                             (1200.0, 2000.0, 240.0, 240.0)):
            if lo <= distance <= hi:
                return a + (b - a) * (distance - lo) / (hi - lo)
        return 240.0

    frames = [frame(d * 2.0, speed_at(d * 2.0), d) for d in range(1000)]
    model = detect_corners(frames, "test-track")
    assert [c.id for c in model.corners] == ["T1"]


def test_a_flat_out_lap_yields_no_model():
    flat = [frame(d * 2.0, 240.0, d) for d in range(400)]
    assert detect_corners(flat, "test-track") is None


def test_too_few_frames_yields_no_model():
    assert detect_corners([frame(i, 100.0, i) for i in range(10)], "t") is None


def test_frames_without_distance_are_ignored():
    frames = synthetic_lap()
    for f in frames[:50]:
        f["lap_distance_m"] = None
    assert detect_corners(frames, "test-track") is not None


def test_model_declares_its_source_and_identity():
    model = detect_corners(synthetic_lap(), "fuji-full", version=3)
    assert model.as_meta() == {
        "source": "auto-segment", "id": "fuji-full", "version": 3}


def test_model_id_is_slugged_from_track_and_layout():
    assert model_id_for("Fuji Speedway", "Full") == "fuji-speedway-full"
    assert model_id_for("Autodromo Nazionale Monza") == "autodromo-nazionale-monza"


def test_model_round_trips_through_a_dict():
    model = detect_corners(synthetic_lap(), "test-track")
    restored = CornerModel.from_dict(model.as_dict())
    assert restored == model


def test_a_model_only_applies_to_the_same_lap_length():
    model = detect_corners(synthetic_lap(), "test-track")
    assert model.applies_to(model.lap_length_m + 10)
    assert not model.applies_to(model.lap_length_m + 500)


# ---------------------------------------------------------------- aggregation

def test_every_corner_carries_its_sample_count():
    laps = [CountedLap(n, synthetic_lap()) for n in (1, 2, 3)]
    model = detect_corners(laps[0].frames, "test-track")
    for corner in aggregate_corners(model, laps):
        assert corner["samples"] == 3


def test_speeds_are_measured_through_the_window():
    laps = [CountedLap(1, synthetic_lap(apex_positions=(600.0,)))]
    model = detect_corners(laps[0].frames, "test-track")
    corner = aggregate_corners(model, laps)[0]
    assert round(corner["minSpeedKph"]) == 90
    assert corner["entrySpeedKph"] > corner["minSpeedKph"]
    assert corner["exitSpeedKph"] > corner["minSpeedKph"]


def test_brake_point_is_metres_before_the_apex():
    frames = synthetic_lap(apex_positions=(600.0,))
    for f in frames:
        if 500.0 <= f["lap_distance_m"] <= 600.0:
            f["brake_pct"] = 90.0
    laps = [CountedLap(1, frames)]
    corner = aggregate_corners(a_model([Corner("T1", "Turn 1", 480, 600, 720)]), laps)[0]
    assert 95 <= corner["brakePointM"] <= 105
    assert corner["brakePeakPct"] == 90.0


def test_brake_point_is_measured_from_outside_the_corner_window():
    """Braking begins on the straight. Measuring only inside the window
    systematically under-reports it, which matters most for a deep braker."""
    frames = synthetic_lap(apex_positions=(600.0,))
    for f in frames:
        if 400.0 <= f["lap_distance_m"] <= 600.0:
            f["brake_pct"] = 95.0
    laps = [CountedLap(1, frames)]
    # The window opens at 540, well after braking began at 400.
    corner = aggregate_corners(a_model([Corner("T1", "Turn 1", 540, 600, 660)]), laps)[0]
    assert 195 <= corner["brakePointM"] <= 205


def test_an_earlier_unrelated_brake_does_not_move_the_brake_point():
    """Only the last continuous run into the apex counts."""
    frames = synthetic_lap(apex_positions=(600.0,))
    for f in frames:
        if 100.0 <= f["lap_distance_m"] <= 150.0:
            f["brake_pct"] = 80.0        # a lift-and-dab far up the road
        if 520.0 <= f["lap_distance_m"] <= 600.0:
            f["brake_pct"] = 95.0
    laps = [CountedLap(1, frames)]
    corner = aggregate_corners(a_model([Corner("T1", "Turn 1", 540, 600, 660)]), laps)[0]
    assert 75 <= corner["brakePointM"] <= 85


def test_a_corner_taken_without_braking_reports_null_not_zero():
    laps = [CountedLap(1, synthetic_lap(apex_positions=(600.0,)))]
    corner = aggregate_corners(a_model([Corner("T1", "Turn 1", 480, 600, 720)]), laps)[0]
    assert corner["brakePointM"] is None


def test_the_previous_corner_braking_is_not_this_corner_brake_point():
    """The shipped export said he brakes 560 m before T3 beside a peak brake of
    2.8% - a corner he takes flat, wearing the braking for the corner before
    it. A corner taken without braking is a finding, and reads null."""
    frames = synthetic_lap(apex_positions=(600.0,))
    for f in frames:
        if 200.0 <= f["lap_distance_m"] <= 260.0:
            f["brake_pct"] = 95.0
    corner = one_corner(frames)
    assert corner["brakePointM"] is None
    assert corner["brakePointSamples"] == 0


def test_a_sparse_mean_carries_its_own_sample_count():
    """`upshiftRpm 7787` shipped under `samples: 23` was a two-lap figure."""
    braked = synthetic_lap(apex_positions=(600.0,))
    for f in braked:
        if 500.0 <= f["lap_distance_m"] <= 600.0:
            f["brake_pct"] = 90.0
    laps = [CountedLap(1, braked),
            CountedLap(2, synthetic_lap(apex_positions=(600.0,)))]
    corner = aggregate_corners(
        a_model([Corner("T1", "Turn 1", 480, 600, 720)]), laps)[0]
    assert corner["samples"] == 2
    assert corner["brakePointSamples"] == 1
    assert corner["brakePointM"] is not None


def test_trail_brake_is_null_when_steering_is_unavailable():
    """Zero would read as 'he does not trail brake'."""
    frames = synthetic_lap(apex_positions=(600.0,),
                           steering_deg=None, steering_norm=None)
    for f in frames:
        f["brake_pct"] = 50.0
    laps = [CountedLap(1, frames)]
    corner = aggregate_corners(a_model([Corner("T1", "Turn 1", 480, 600, 720)]), laps)[0]
    assert corner["trailBrakeMs"] is None
    assert corner["steerPeakDeg"] is None


def test_trail_brake_is_timed_when_steering_is_available():
    frames = synthetic_lap(apex_positions=(600.0,))
    for f in frames:
        if 520.0 <= f["lap_distance_m"] <= 600.0:
            f["brake_pct"] = 40.0
            f["steering_deg"] = 60.0
            f["steering_norm"] = 0.4
    laps = [CountedLap(1, frames)]
    corner = aggregate_corners(a_model([Corner("T1", "Turn 1", 480, 600, 720)]), laps)[0]
    assert corner["trailBrakeMs"] > 0
    assert corner["steerPeakNorm"] == 0.4


def test_throttle_on_is_a_percentage_through_the_corner():
    frames = synthetic_lap(apex_positions=(600.0,), throttle_pct=0.0)
    for f in frames:
        if f["lap_distance_m"] >= 600.0:
            f["throttle_pct"] = 80.0
    laps = [CountedLap(1, frames)]
    corner = aggregate_corners(a_model([Corner("T1", "Turn 1", 480, 600, 720)]), laps)[0]
    assert 45 <= corner["throttleOnPct"] <= 55


def test_consistency_is_none_from_a_single_lap():
    laps = [CountedLap(1, synthetic_lap(apex_positions=(600.0,)))]
    corner = aggregate_corners(a_model([Corner("T1", "Turn 1", 480, 600, 720)]), laps)[0]
    assert corner["consistencyMs"] is None
    assert corner["timeLossVsBestMs"] == 0


def test_corners_no_lap_reached_are_omitted():
    laps = [CountedLap(1, synthetic_lap(apex_positions=(600.0,)))]
    model = a_model([Corner("T9", "Turn 9", 9000, 9100, 9200)])
    assert aggregate_corners(model, laps) == []


# ---------------------------------------------------------------------- flags

def flags_for(**frame_changes) -> list[str]:
    frames = synthetic_lap(apex_positions=(600.0,))
    for f in frames:
        if 550.0 <= f["lap_distance_m"] <= 650.0:
            f.update(frame_changes)
    laps = [CountedLap(1, frames)]
    return aggregate_corners(a_model([Corner("T1", "Turn 1", 480, 600, 720)]), laps)[0]["flags"]


def test_clean_corner_raises_no_flags():
    laps = [CountedLap(1, synthetic_lap(apex_positions=(600.0,)))]
    corner = aggregate_corners(a_model([Corner("T1", "Turn 1", 480, 600, 720)]), laps)[0]
    assert corner["flags"] == []


def test_wheelspin_needs_throttle():
    assert "wheelspin" in flags_for(throttle_pct=80.0, slip_rr=1.2)
    assert "wheelspin" not in flags_for(throttle_pct=0.0, slip_rr=1.2)


def test_wheelspin_is_tested_on_the_driven_wheels():
    """Contract 7.1 says driven wheels. A front wheel light over a kerb under
    throttle is not a rear-driven car spinning up."""
    frames = synthetic_lap(apex_positions=(600.0,))
    for f in frames:
        if 550.0 <= f["lap_distance_m"] <= 650.0:
            f["throttle_pct"] = 80.0
            f["slip_fl"] = 1.2
    assert "wheelspin" not in one_corner(frames, drivetrain="rwd")["flags"]
    # GT7 broadcasts no drivetrain channel, so with nothing declared the
    # detector keeps the all-wheel test - and says so in `derived.thresholds`.
    assert "wheelspin" in one_corner(frames)["flags"]


def test_an_undeclared_drivetrain_is_declared_as_such():
    assert "all four" in thresholds.as_export()["wheelspinWheels"]
    assert "rwd" in thresholds.as_export("rwd")["wheelspinWheels"]


def test_lockup_needs_brake():
    assert "lockup" in flags_for(brake_pct=90.0, slip_fl=0.6)
    assert "lockup" not in flags_for(brake_pct=0.0, slip_fl=0.6)


def test_off_track_reads_the_surface_character():
    assert "off-track" in flags_for(surf_rl="G")
    assert "off-track" not in flags_for(surf_rl="C")   # kerb is still on track


def test_kerb_strike_is_a_fast_height_step():
    frames = synthetic_lap(apex_positions=(600.0,))
    for i, f in enumerate(frames):
        if 590.0 <= f["lap_distance_m"] <= 600.0:
            f["susp_mm_fl"] = 60.0 if i % 2 else 30.0
    laps = [CountedLap(1, frames)]
    corner = aggregate_corners(a_model([Corner("T1", "Turn 1", 480, 600, 720)]), laps)[0]
    assert "kerb-strike" in corner["flags"]


def test_countersteer_needs_a_sign_reversal():
    frames = synthetic_lap(apex_positions=(600.0,))
    for i, f in enumerate(frames):
        if 580.0 <= f["lap_distance_m"] <= 620.0:
            f["steering_deg"] = 40.0 if i % 4 < 2 else -40.0
    laps = [CountedLap(1, frames)]
    corner = aggregate_corners(a_model([Corner("T1", "Turn 1", 480, 600, 720)]), laps)[0]
    assert "countersteer" in corner["flags"]


def test_a_chicane_direction_change_is_not_a_countersteer():
    """An auto-segmented corner is one speed minimum, so a chicane is one
    window and its left-right transition clears 10 deg by construction. On the
    owner's Monza laps the bare reversal test marked all three chicanes and
    almost nothing else."""
    frames = synthetic_lap(apex_positions=(600.0,))
    for f in frames:
        distance = f["lap_distance_m"]
        if 500.0 <= distance <= 600.0:
            f["steering_deg"], f["steering_norm"] = 60.0, 0.33
        elif 600.0 < distance <= 720.0:
            f["steering_deg"], f["steering_norm"] = -55.0, -0.31
    assert "countersteer" not in one_corner(frames)["flags"]


def test_a_dab_of_opposite_lock_is_a_countersteer():
    frames = synthetic_lap(apex_positions=(600.0,))
    for f in frames:
        distance = f["lap_distance_m"]
        if 500.0 <= distance <= 700.0:
            f["steering_deg"], f["steering_norm"] = 60.0, 0.33
        if 610.0 <= distance <= 620.0:
            f["steering_deg"], f["steering_norm"] = -20.0, -0.11
    assert "countersteer" in one_corner(frames)["flags"]


def test_trail_brake_instability_is_countersteer_under_brake():
    frames = synthetic_lap(apex_positions=(600.0,))
    for i, f in enumerate(frames):
        if 580.0 <= f["lap_distance_m"] <= 620.0:
            f["steering_deg"] = 40.0 if i % 4 < 2 else -40.0
            f["steering_norm"] = 0.4 if i % 4 < 2 else -0.4
            f["brake_pct"] = 40.0
    assert "trail-brake-instability" in one_corner(frames)["flags"]


def test_trail_brake_instability_needs_the_two_to_coincide():
    """A correction on the exit and a trail-brake on the entry are not one
    event. ANDing two whole-window tests made the flag an alias for
    `countersteer` on a driver whose whole technique is trail-braking deep."""
    frames = synthetic_lap(apex_positions=(600.0,))
    for f in frames:
        distance = f["lap_distance_m"]
        if 500.0 <= distance <= 700.0:
            f["steering_deg"], f["steering_norm"] = 40.0, 0.4
        if 500.0 <= distance <= 560.0:                 # trail braking, no dab
            f["brake_pct"] = 40.0
        if 640.0 <= distance <= 660.0:                 # the dab, off the brakes
            f["steering_deg"], f["steering_norm"] = -40.0, -0.4
    flags = one_corner(frames)["flags"]
    assert "countersteer" in flags
    assert "trail-brake-instability" not in flags


def rising_lock(yaw_rate, *, rise_deg_per_frame: float = 0.5) -> list[dict]:
    """A corner taken on an ever-increasing steering angle."""
    frames = synthetic_lap(apex_positions=(600.0,))
    lock = 20.0
    for f in frames:
        if 500.0 <= f["lap_distance_m"] <= 700.0:
            lock += rise_deg_per_frame
            f["steering_deg"] = lock
            f["steering_norm"] = lock / 180.0
            f["yaw_rate"] = yaw_rate
    return frames


def test_understeer_needs_the_car_to_be_short_of_the_rotation_the_lock_implies():
    assert "understeer-mid" in one_corner(rising_lock(0.05))["flags"]


def test_adding_lock_alone_is_not_understeer():
    """The v2 detector had a magnitude on neither side, so the steering term
    could not fail: it fired on 49% of the owner's real corner windows and on
    every corner object in the export."""
    assert "understeer-mid" not in one_corner(rising_lock(2.0))["flags"]


def test_a_slow_steering_input_is_not_understeer():
    assert "understeer-mid" not in one_corner(
        rising_lock(0.05, rise_deg_per_frame=0.05))["flags"]


def test_an_unmeasurable_yaw_is_not_understeer():
    """Heading is undefined when the car is not moving. Reading that as
    'not rotating any harder' makes a standstill the strongest understeer
    signal the detector has."""
    assert "understeer-mid" not in one_corner(rising_lock(None))["flags"]


def test_flags_are_null_safe_without_steering_or_surface():
    frames = synthetic_lap(apex_positions=(600.0,), steering_deg=None,
                           steering_norm=None, surf_fl=None, surf_fr=None,
                           surf_rl=None, surf_rr=None)
    laps = [CountedLap(1, frames)]
    corner = aggregate_corners(a_model([Corner("T1", "Turn 1", 480, 600, 720)]), laps)[0]
    assert "countersteer" not in corner["flags"]
    assert "off-track" not in corner["flags"]
    assert corner["surfaceMix"] is None


def test_surface_mix_is_a_fraction_per_character():
    frames = synthetic_lap(apex_positions=(600.0,))
    for f in frames:
        if 595.0 <= f["lap_distance_m"] <= 605.0:
            f["surf_rl"] = "C"
    laps = [CountedLap(1, frames)]
    corner = aggregate_corners(a_model([Corner("T1", "Turn 1", 480, 600, 720)]), laps)[0]
    assert corner["surfaceMix"]["T"] > corner["surfaceMix"]["C"] > 0
    assert abs(sum(corner["surfaceMix"].values()) - 1.0) < 0.01


# --------------------------------------------------------------- bottoming

def test_bottoming_reference_is_the_straight_line_peak_compression():
    """**`susp_mm_*` is compression, not height** - measured on session 49,
    where `body_height_mm` falls 61 -> 50 mm from 120 to 260 km/h while every
    `susp_mm_*` rises. So the bottoming end of the trace is the maximum, and
    taking the minimum took the most EXTENDED the wheel ever got."""
    frames = synthetic_lap(apex_positions=(600.0,))
    frames[100]["susp_mm_fl"] = 89.0        # lap distance 200 m, on the straight
    reference = bottoming_reference([CountedLap(1, frames)])
    assert reference["fl"] == 89.0
    assert reference["rl"] == 65.0


def test_the_reference_is_held_out_of_the_corner_windows():
    """A corner cannot define the floor it is then judged against.

    The reference used to be the observed minimum of the very frames the flag
    is tested against, so the deepest corner of the session reported bottoming
    by construction and every other corner was measured against its floor.
    """
    frames = synthetic_lap(apex_positions=(600.0,))
    for f in frames:
        if 560.0 <= f["lap_distance_m"] <= 640.0:
            f["susp_mm_fl"] = 75.0
    laps = [CountedLap(1, frames)]
    model = a_model([Corner("T1", "Turn 1", 480, 600, 720)])
    assert bottoming_reference(laps, model)["fl"] == 60.0
    # The excursion is still exported - separately, and as a measurement.
    assert observed_minimum(laps)["fl"] == 75.0


def test_each_setup_sheet_gets_its_own_reference():
    """Ride height and spring rate are setup values, so the compression a
    wheel bottoms at belongs to the sheet, not to the event."""
    laps = [
        CountedLap(1, synthetic_lap(apex_positions=(600.0,), susp_mm_fl=40.0),
                   setup_sheet_id=1),
        CountedLap(2, synthetic_lap(apex_positions=(600.0,), susp_mm_fl=60.0),
                   setup_sheet_id=3),
    ]
    references = bottoming_references(laps)
    assert references[1]["fl"] == 40.0
    assert references[3]["fl"] == 60.0


def test_bottoming_reference_is_none_without_suspension_data():
    frames = synthetic_lap(apex_positions=(600.0,), susp_mm_fl=None,
                           susp_mm_fr=None, susp_mm_rl=None, susp_mm_rr=None)
    assert bottoming_reference([CountedLap(1, frames)]) is None


def test_a_suspension_trace_that_never_moves_cannot_infer_bottoming():
    """Otherwise the inference is circular: the limit is the observed peak, so
    a constant trace sits in the band on every frame of every corner."""
    laps = [CountedLap(1, synthetic_lap(apex_positions=(600.0,)))]
    reference = bottoming_reference(laps)
    assert reference is not None
    assert bottoming_inferable(laps, reference) == set()


def test_a_wheel_that_moves_is_inferable():
    frames = synthetic_lap(apex_positions=(600.0,))
    for f in frames:
        if 595.0 <= f["lap_distance_m"] <= 610.0:
            f["susp_mm_fl"] = 90.0
    laps = [CountedLap(1, frames)]
    assert bottoming_inferable(laps, bottoming_reference(laps)) == {"fl"}


def test_sustained_time_at_the_reference_flags_bottoming():
    """Reaching in a corner the compression the car only reaches on the
    straight - where `susp_mm_*` runs HIGH, because it is travel and not
    height. See `corners._most_compressed`."""
    frames = synthetic_lap(apex_positions=(600.0,))
    for f in frames:
        # The straight-line limit: the dive under braking, outside the window.
        if 100.0 <= f["lap_distance_m"] <= 140.0:
            f["susp_mm_fl"] = 95.0
        if 595.0 <= f["lap_distance_m"] <= 610.0:
            f["susp_mm_fl"] = 95.0
    corner = one_corner(frames)
    assert "bottoming" in corner["flags"]


def test_a_corner_short_of_the_straight_line_limit_does_not_flag():
    """And this is the case the inverted test got backwards: a corner where
    the wheel is LESS compressed than it gets on the straight is a corner
    nowhere near the floor. Under the old direction that was the flag."""
    frames = synthetic_lap(apex_positions=(600.0,))
    for f in frames:
        if 100.0 <= f["lap_distance_m"] <= 140.0:
            f["susp_mm_fl"] = 95.0
        if 595.0 <= f["lap_distance_m"] <= 610.0:
            f["susp_mm_fl"] = 75.0
    assert "bottoming" not in one_corner(frames)["flags"]


# ----------------------------------------------------------------- contract

def test_thresholds_export_matches_the_contract_keys():
    payload = thresholds.as_export()
    for key in ("wheelspinPct", "lockupPct", "countersteerDeg",
                "trailBrakeSteerPct", "kerbStrikeMm", "apexDefinition"):
        assert key in payload
    assert payload["apexDefinition"] == thresholds.APEX_DEFINITION


def test_every_constant_that_gates_a_flag_is_exported():
    """Twelve were missing, including the whole bottoming rule and an
    understeer rule that was hardcoded in the detector and did not exist in
    `thresholds` at all - so it could never be declared."""
    payload = thresholds.as_export()
    for key in ("bottomingMinMs", "bottomingBandMm", "bottomingRefMaxSteerPct",
                "countersteerWindowMs", "countersteerReturnFraction",
                "kerbStrikeWindowMs", "trailBrakeMinBrakePct",
                "throttleOnPct", "brakeOnPct", "onTrackSurfaces",
                "understeerYawGain", "understeerYawDeficit",
                "understeerSteerRiseDegS", "understeerMinMs",
                "understeerWheelbaseM", "wheelspinWheels", "brakeLookbackM"):
        assert key in payload, key
    assert payload["detectorVersion"] == thresholds.DETECTOR_VERSION


def test_ms_windows_round_up_and_come_from_the_lap_sample_rate():
    """`int(50 / 16.67)` truncated a 50 ms rule to 33 ms, and re-deriving the
    interval per window from `t_ms` gave 2 frames on 254 windows of one session
    and 3 on 495 - two corners of a circuit under different rules."""
    assert _frames_for_ms(50, 1000.0 / 60.0) == 3
    assert _frames_for_ms(300, 1000.0 / 60.0) == 18
    assert CountedLap(1, [], sample_hz=60.0).interval_ms == 1000.0 / 60.0
    assert CountedLap(1, []).interval_ms == 1000.0 / 60.0


def test_corner_object_has_every_contract_field():
    laps = [CountedLap(n, synthetic_lap(apex_positions=(600.0,))) for n in (1, 2)]
    corner = aggregate_corners(a_model([Corner("T1", "Turn 1", 480, 600, 720)]), laps)[0]
    for key in ("id", "name", "samples", "entrySpeedKph", "minSpeedKph",
                "exitSpeedKph", "brakePeakPct", "brakePointM", "trailBrakeMs",
                "steerPeakDeg", "steerPeakNorm", "throttleOnPct",
                "timeLossVsBestMs", "consistencyMs", "suspHeightMinMm",
                "surfaceMix", "flags"):
        assert key in corner
