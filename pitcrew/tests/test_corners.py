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
    aggregate_corners,
    bottoming_inferable,
    bottoming_reference,
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


def test_trail_brake_instability_is_countersteer_under_brake():
    frames = synthetic_lap(apex_positions=(600.0,))
    for i, f in enumerate(frames):
        if 580.0 <= f["lap_distance_m"] <= 620.0:
            f["steering_deg"] = 40.0 if i % 4 < 2 else -40.0
            f["steering_norm"] = 0.4 if i % 4 < 2 else -0.4
            f["brake_pct"] = 40.0
    laps = [CountedLap(1, frames)]
    flags = aggregate_corners(a_model([Corner("T1", "Turn 1", 480, 600, 720)]), laps)[0]["flags"]
    assert "trail-brake-instability" in flags


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

def test_bottoming_reference_is_the_observed_minimum():
    frames = synthetic_lap(apex_positions=(600.0,))
    frames[100]["susp_mm_fl"] = 31.0
    reference = bottoming_reference([CountedLap(1, frames)])
    assert reference["fl"] == 31.0
    assert reference["rl"] == 65.0


def test_bottoming_reference_is_none_without_suspension_data():
    frames = synthetic_lap(apex_positions=(600.0,), susp_mm_fl=None,
                           susp_mm_fr=None, susp_mm_rl=None, susp_mm_rr=None)
    assert bottoming_reference([CountedLap(1, frames)]) is None


def test_a_suspension_trace_that_never_moves_cannot_infer_bottoming():
    """Otherwise the inference is circular: the floor is the observed minimum,
    so a constant height sits in the band on every frame of every corner."""
    laps = [CountedLap(1, synthetic_lap(apex_positions=(600.0,)))]
    reference = bottoming_reference(laps)
    assert reference is not None
    assert bottoming_inferable(laps, reference) == set()


def test_a_wheel_that_moves_is_inferable():
    frames = synthetic_lap(apex_positions=(600.0,))
    for f in frames:
        if 595.0 <= f["lap_distance_m"] <= 610.0:
            f["susp_mm_fl"] = 30.0
    laps = [CountedLap(1, frames)]
    assert bottoming_inferable(laps, bottoming_reference(laps)) == {"fl"}


def test_sustained_time_at_the_reference_flags_bottoming():
    frames = synthetic_lap(apex_positions=(600.0,))
    for f in frames:
        if 595.0 <= f["lap_distance_m"] <= 610.0:
            f["susp_mm_fl"] = 30.0
    laps = [CountedLap(1, frames)]
    corner = aggregate_corners(a_model([Corner("T1", "Turn 1", 480, 600, 720)]), laps)[0]
    assert "bottoming" in corner["flags"]
    assert corner["suspHeightMinMm"]["fl"] == 30.0


# ----------------------------------------------------------------- contract

def test_thresholds_export_matches_the_contract_keys():
    payload = thresholds.as_export()
    for key in ("wheelspinPct", "lockupPct", "countersteerDeg",
                "trailBrakeSteerPct", "kerbStrikeMm", "apexDefinition"):
        assert key in payload
    assert payload["apexDefinition"] == thresholds.APEX_DEFINITION


def test_corner_object_has_every_contract_field():
    laps = [CountedLap(n, synthetic_lap(apex_positions=(600.0,))) for n in (1, 2)]
    corner = aggregate_corners(a_model([Corner("T1", "Turn 1", 480, 600, 720)]), laps)[0]
    for key in ("id", "name", "samples", "entrySpeedKph", "minSpeedKph",
                "exitSpeedKph", "brakePeakPct", "brakePointM", "trailBrakeMs",
                "steerPeakDeg", "steerPeakNorm", "throttleOnPct",
                "timeLossVsBestMs", "consistencyMs", "suspHeightMinMm",
                "surfaceMix", "flags"):
        assert key in corner
