"""Full-rate capture, slip derivation and the on-disk frame format."""
from __future__ import annotations

import math

from pitcrew.telemetry.recorder import (
    FRAME_FIELDS,
    SAMPLE_HZ,
    LapRecorder,
    decode_frames,
)

from .conftest import make_packet, rolling_wheel_rps


def rolling_packet(speed_ms: float = 50.0, **overrides):
    rps = rolling_wheel_rps(speed_ms)
    fields = {
        "speed_ms": speed_ms,
        "wheel_rps_fl": rps, "wheel_rps_fr": rps,
        "wheel_rps_rl": rps, "wheel_rps_rr": rps,
    }
    fields.update(overrides)
    return make_packet(**fields)


def test_records_every_packet_by_default():
    rec = LapRecorder()
    for i in range(10):
        rec.record_frame(rolling_packet(time_of_day_ms=i * 16))
    assert rec.frame_count == 10
    assert rec.take_lap().sample_hz == SAMPLE_HZ


def test_off_track_frames_are_dropped():
    rec = LapRecorder()
    rec.record_frame(rolling_packet())
    rec.record_frame(rolling_packet(on_track=False))
    rec.record_frame(rolling_packet())
    assert rec.frame_count == 2


def test_take_lap_round_trips_through_the_blob():
    rec = LapRecorder()
    rec.record_frame(rolling_packet(packet_id=1000, throttle_raw=255, gear_raw=0x14))
    rec.record_frame(rolling_packet(packet_id=1001, brake_raw=128))
    lap = rec.take_lap()

    frames = decode_frames(lap.blob)
    assert lap.frame_count == 2
    assert len(frames) == 2
    assert set(frames[0]) == set(FRAME_FIELDS)
    assert frames[0]["t_ms"] == 0
    assert frames[1]["t_ms"] == 17
    assert frames[0]["gear"] == 4


def test_the_clock_is_the_packet_counter_not_the_game_clock():
    """GT7's time of day is frozen in one event and accelerated in another.

    A day-to-night transition runs the in-game clock at many times real speed,
    so laps timed against it came out spanning 970 s where the lap took 110 -
    and every corner metric measured in milliseconds was scaled by whatever
    multiplier the event happened to use.
    """
    rec = LapRecorder()
    rec.record_frame(rolling_packet(packet_id=500, time_of_day_ms=0))
    rec.record_frame(rolling_packet(packet_id=501, time_of_day_ms=60_000))
    rec.record_frame(rolling_packet(packet_id=502, time_of_day_ms=0))
    frames = decode_frames(rec.take_lap().blob)
    assert [f["t_ms"] for f in frames] == [0, 17, 33]


def test_lap_distance_is_integrated_because_gt7_broadcasts_none():
    """A corner is a window of lap distance, and GT7 sends no such channel.

    What the recorder used to store as distance was the road plane's fourth
    coefficient, which is why no session ever produced a corner model.
    """
    rec = LapRecorder()
    for index in range(60):
        rec.record_frame(rolling_packet(packet_id=index, speed_ms=50.0))
    frames = decode_frames(rec.take_lap().blob)
    # 50 m/s for one second of packets, less the first frame's step.
    assert 48.0 < frames[-1]["lap_distance_m"] <= 50.0
    assert frames[0]["lap_distance_m"] < frames[-1]["lap_distance_m"]


def test_pedals_are_stored_as_percent():
    """The feed gives 0-255; the export contract fixes percent 0-100."""
    rec = LapRecorder()
    rec.record_frame(rolling_packet(throttle_raw=255))
    rec.record_frame(rolling_packet(brake_raw=128))
    frames = decode_frames(rec.take_lap().blob)
    assert frames[0]["throttle_pct"] == 100.0
    assert round(frames[1]["brake_pct"]) == 50


def test_suspension_and_body_height_are_stored_in_mm():
    """The feed gives metres of absolute height, not travel remaining."""
    rec = LapRecorder()
    rec.record_frame(rolling_packet(
        suspension_fl=0.0342, suspension_fr=0.0360,
        suspension_rl=0.0410, suspension_rr=0.0420,
        body_height=0.0755))
    frames = decode_frames(rec.take_lap().blob)
    assert frames[0]["susp_mm_fl"] == 34.2
    assert frames[0]["susp_mm_rr"] == 42.0
    assert frames[0]["body_height_mm"] == 75.5


def test_speed_is_stored_in_kph():
    rec = LapRecorder()
    rec.record_frame(rolling_packet(speed_ms=50.0))
    frames = decode_frames(rec.take_lap().blob)
    assert frames[0]["speed_kph"] == 180.0


def test_take_lap_clears_the_buffer():
    rec = LapRecorder()
    rec.record_frame(rolling_packet())
    assert rec.take_lap() is not None
    assert rec.take_lap() is None
    assert rec.frame_count == 0


def test_elapsed_restarts_each_lap():
    rec = LapRecorder()
    rec.record_frame(rolling_packet(time_of_day_ms=500_000))
    rec.record_frame(rolling_packet(time_of_day_ms=500_100))
    rec.take_lap()
    rec.record_frame(rolling_packet(time_of_day_ms=600_000))
    frames = decode_frames(rec.take_lap().blob)
    assert frames[0]["t_ms"] == 0


def test_rolling_wheels_give_unit_slip():
    rec = LapRecorder()
    rec.record_frame(rolling_packet(speed_ms=50.0))
    frames = decode_frames(rec.take_lap().blob)
    for corner in ("slip_fl", "slip_fr", "slip_rl", "slip_rr"):
        assert abs(frames[0][corner] - 1.0) < 0.001


def test_locked_front_wheels_show_as_low_slip():
    rec = LapRecorder()
    rps = rolling_wheel_rps(50.0)
    rec.record_frame(make_packet(
        speed_ms=50.0,
        wheel_rps_fl=0.0, wheel_rps_fr=0.0,
        wheel_rps_rl=rps, wheel_rps_rr=rps,
    ))
    frames = decode_frames(rec.take_lap().blob)
    assert frames[0]["slip_fl"] == 0.0
    assert abs(frames[0]["slip_rl"] - 1.0) < 0.001


def test_spinning_rear_wheels_show_as_high_slip():
    rec = LapRecorder()
    rps = rolling_wheel_rps(50.0)
    rec.record_frame(make_packet(
        speed_ms=50.0,
        wheel_rps_fl=rps, wheel_rps_fr=rps,
        wheel_rps_rl=rps * 1.3, wheel_rps_rr=rps * 1.3,
    ))
    frames = decode_frames(rec.take_lap().blob)
    assert round(frames[0]["slip_rr"], 2) == 1.3


def test_slip_is_not_computed_when_nearly_stopped():
    rec = LapRecorder()
    rec.record_frame(make_packet(speed_ms=0.5, wheel_rps_fl=0.0))
    frames = decode_frames(rec.take_lap().blob)
    assert frames[0]["slip_fl"] == 1.0


def test_channels_the_packet_format_lacks_are_null_not_zero():
    """The 'A' format carries no steering or surface. A zero would read
    downstream as a real measurement of a centred wheel on tarmac."""
    rec = LapRecorder()
    rec.record_frame(rolling_packet(extended=False))
    frames = decode_frames(rec.take_lap().blob)
    for channel in ("steering_deg", "steering_norm",
                    "surf_fl", "surf_fr", "surf_rl", "surf_rr"):
        assert frames[0][channel] is None


def test_a_padded_tail_does_not_invent_surfaces():
    """Four NULs are not four wheels on an unknown surface."""
    rec = LapRecorder()
    rec.record_frame(rolling_packet(extended=True))
    frames = decode_frames(rec.take_lap().blob)
    assert frames[0]["surf_fl"] is None


def test_steering_is_captured_in_degrees_and_normalised():
    import struct as _struct

    from pitcrew.telemetry.packet import parse_packet

    from .conftest import raw_packet
    data = bytearray(raw_packet(extended=True))
    _struct.pack_into("<f", data, 296, math.pi / 2)
    _struct.pack_into("<H", data, 142, 0x0001)          # on track
    packet = parse_packet(bytes(data))

    rec = LapRecorder()
    rec.record_frame(packet)
    frames = decode_frames(rec.take_lap().blob)
    assert round(frames[0]["steering_deg"]) == 90
    assert round(frames[0]["steering_norm"], 3) == 0.5


def test_a_full_lap_compresses_to_a_sane_size():
    """~7,200 frames is one lap at 60 Hz; guard against a runaway blob."""
    rec = LapRecorder()
    for i in range(7_200):
        rec.record_frame(rolling_packet(
            time_of_day_ms=i * 16,
            pos_x=float(i % 500), pos_z=float(i % 300),
            road_distance=float(i) * 0.8,
        ))
    lap = rec.take_lap()
    assert lap.frame_count == 7_200
    assert lap.size_bytes < 1_500_000
    assert len(decode_frames(lap.blob)) == 7_200


def test_discard_drops_the_lap():
    rec = LapRecorder()
    rec.record_frame(rolling_packet())
    rec.discard()
    assert rec.take_lap() is None
