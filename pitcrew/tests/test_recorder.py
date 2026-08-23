"""Full-rate capture, slip derivation and the on-disk frame format."""
from __future__ import annotations

import math

from pitcrew.telemetry import recorder
from pitcrew.telemetry.recorder import (
    BLOB_FORMAT,
    FRAME_FIELDS,
    SAMPLE_HZ,
    LapRecorder,
    _VERSION_KEY,
    decode_frames,
    encode_frames,
    repair_frames,
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
    # A decoded frame carries the blob's schema version as well as its
    # channels; `repair_frames` strips it once it has decided what to repair.
    assert set(frames[0]) == set(FRAME_FIELDS) | {_VERSION_KEY}
    assert set(repair_frames(frames)[0]) == set(FRAME_FIELDS)
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


def test_slip_is_null_not_one_when_nearly_stopped():
    """1.0 is this channel's zero -- exactly "rolling true".

    The floor used to store a synthetic 1.0, which is the most benign real
    reading the channel has and carried nothing to say it was not measured.
    """
    rec = LapRecorder()
    rec.record_frame(make_packet(speed_ms=0.5, wheel_rps_fl=0.0))
    frames = decode_frames(rec.take_lap().blob)
    for corner in ("slip_fl", "slip_fr", "slip_rl", "slip_rr"):
        assert frames[0][corner] is None


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


# ------------------------------------------------------------------- rotation

def test_yaw_rate_is_the_yaw_axis_not_the_roll_axis():
    """`angvel_y` is rotation about the vertical; `angvel_z` is roll.

    The column held `angvel_z` in every lap recorded up to now, which is why
    spin detection - thresholded at 1.2 rad/s against a channel whose rms is
    0.07 - had never fired on a real lap, and why `lat_g` peaked at 8.46 g on a
    car that makes two and a half.
    """
    rec = LapRecorder()
    rec.record_frame(rolling_packet(speed_ms=40.0, angvel_y=0.5, angvel_z=0.9))
    frames = decode_frames(rec.take_lap().blob)
    assert frames[0]["yaw_rate"] == 0.5
    assert frames[0]["lat_g"] == round(40.0 * 0.5 / 9.81, 3)


def test_a_dropped_excursion_is_charged_to_neither_distance_nor_the_clock():
    """Thirty seconds paused mid-lap used to record 1,600 m for 100 m driven.

    Both counters are measured against the packet id, so a frame that is not
    recorded still has to close its own gap or the next recorded frame pays
    for the whole excursion at its own speed.
    """
    rec = LapRecorder()
    rec.record_frame(rolling_packet(packet_id=100, speed_ms=50.0))
    for offset in range(1, 1_800):
        rec.record_frame(rolling_packet(packet_id=100 + offset,
                                        flags_raw=0x0003))   # on track, paused
    rec.record_frame(rolling_packet(packet_id=1_900, speed_ms=50.0))

    frames = decode_frames(rec.take_lap().blob)
    assert len(frames) == 2
    # One frame of driving either side of the pause, not 1,800.
    assert frames[1]["t_ms"] == 17
    assert frames[1]["lap_distance_m"] - frames[0]["lap_distance_m"] < 1.0


# ------------------------------------------------- repairing what is on disk

def v1_blob(rows: list[list]) -> bytes:
    """A blob as the recorder wrote them before the yaw and slip fixes.

    Same columns, no version stamp - which is exactly how a v1 lap is
    recognised on disk.
    """
    import json
    import zlib

    from pitcrew.telemetry.recorder import BLOB_FORMAT
    payload = {"format": BLOB_FORMAT, "fields": list(FRAME_FIELDS), "rows": rows}
    return zlib.compress(json.dumps(payload, separators=(",", ":")).encode("utf-8"), 6)


def circling_v1_rows(count: int = 120, radius: float = 50.0,
                     speed_ms: float = 25.0) -> list[list]:
    """A car going round a constant circle, stored the way v1 stored it.

    `speed / radius` is the yaw rate, so the answer the repair has to find is
    known exactly.  Slip is written 2pi too large and `yaw_rate` holds a roll
    rate, as v1 did.
    """
    rows = []
    step = (speed_ms / radius) / SAMPLE_HZ
    for index in range(count):
        angle = index * step
        row = [None] * len(FRAME_FIELDS)
        row[FRAME_FIELDS.index("t_ms")] = int(round(index * 1000.0 / SAMPLE_HZ))
        row[FRAME_FIELDS.index("speed_kph")] = round(speed_ms * 3.6, 2)
        row[FRAME_FIELDS.index("yaw_rate")] = 0.07        # roll, as stored
        row[FRAME_FIELDS.index("lat_g")] = 0.178
        row[FRAME_FIELDS.index("pos_x")] = round(radius * math.cos(angle), 2)
        row[FRAME_FIELDS.index("pos_y")] = 0.0
        row[FRAME_FIELDS.index("pos_z")] = round(radius * math.sin(angle), 2)
        for corner in ("slip_fl", "slip_fr", "slip_rl", "slip_rr"):
            row[FRAME_FIELDS.index(corner)] = round(2.0 * math.pi, 4)
        row[FRAME_FIELDS.index("lap_distance_m")] = round(
            speed_ms * index / SAMPLE_HZ, 2)
        rows.append(row)
    return rows


def test_a_blob_with_no_version_stamp_is_a_v1_lap():
    assert decode_frames(v1_blob(circling_v1_rows(2)))[0][_VERSION_KEY] == 1


def test_a_v1_lap_gets_a_real_yaw_rate_back_from_its_own_path():
    """132 recorded laps are repaired rather than re-driven.

    `pos_x`/`pos_z` are stored at 1 cm and 60 Hz, so the heading derivative
    recovers ground-track yaw to well inside 0.01 rad/s.  Not body yaw - the
    two differ by the rate of change of sideslip, which is second order here
    and is not second order for anything built on chassis attitude.

    The circle here runs with `atan2(z, x)` increasing, so the y component of
    angular velocity is negative -- and on the real capture set the same rule
    integrates to -360.3 deg over a lap of three circuits that are all
    clockwise.
    """
    frames = repair_frames(decode_frames(v1_blob(circling_v1_rows())))
    middle = frames[len(frames) // 2]
    assert abs(middle["yaw_rate"] + 0.5) < 0.01
    assert abs(middle["lat_g"] - 25.0 * 0.5 / 9.81) < 0.02


def test_a_v1_lap_has_the_2pi_divided_back_out_of_its_slip():
    frames = repair_frames(decode_frames(v1_blob(circling_v1_rows())))
    for corner in ("slip_fl", "slip_fr", "slip_rl", "slip_rr"):
        assert abs(frames[0][corner] - 1.0) < 0.001


def test_a_v2_lap_is_left_exactly_as_recorded():
    """The repair must not fire twice.  A v2 slip divided by 2pi again would
    read as a permanently locked wheel."""
    rec = LapRecorder()
    for index in range(30):
        rec.record_frame(rolling_packet(packet_id=index, speed_ms=50.0,
                                        angvel_y=0.25))
    frames = repair_frames(decode_frames(rec.take_lap().blob))
    assert abs(frames[0]["slip_fl"] - 1.0) < 0.001
    assert frames[0]["yaw_rate"] == 0.25


def test_a_stationary_v1_lap_gets_no_yaw_at_all():
    """Heading is undefined when the car is not moving.

    A zero would satisfy every "not rotating any harder" test downstream, so
    the understeer detector would read a parked car as understeering.
    """
    rows = circling_v1_rows(60)
    for row in rows:
        row[FRAME_FIELDS.index("pos_x")] = 10.0
        row[FRAME_FIELDS.index("pos_z")] = 20.0
        row[FRAME_FIELDS.index("speed_kph")] = 0.0
    frames = repair_frames(decode_frames(v1_blob(rows)))
    assert all(frame["yaw_rate"] is None for frame in frames)
    assert all(frame["lat_g"] is None for frame in frames)
    assert all(frame["slip_fl"] is None for frame in frames)


# ------------------------------------------------------- feed health

def test_a_gap_in_the_packet_id_is_counted_not_just_absorbed():
    """CLAUDE.md 7: the connection must fail loudly.

    The distance arithmetic handles a gap correctly - it steps by the gap so
    the loss is paid for once rather than displacing everything after it -
    and that is exactly why it needed counting separately. A lap that lost
    half a second of stream came out looking clean, while lap distance, which
    corner windows are keyed on, had integrated across the hole.
    """
    recorder = LapRecorder()
    recorder.record_frame(make_packet(packet_id=100, speed_ms=50.0))
    recorder.record_frame(make_packet(packet_id=101, speed_ms=50.0))
    # Ids 102-130 never arrived: twenty-nine packets, half a second of feed.
    recorder.record_frame(make_packet(packet_id=131, speed_ms=50.0))

    assert recorder.stream_gaps == 1
    assert recorder.lost_packets == 29


def test_a_clean_stream_reports_no_loss():
    recorder = LapRecorder()
    for packet_id in range(100, 110):
        recorder.record_frame(make_packet(packet_id=packet_id, speed_ms=50.0))
    assert recorder.stream_gaps == 0
    assert recorder.lost_packets == 0


def test_time_in_the_menus_is_not_reported_as_a_dropped_feed():
    """The off-track skip closes its own packet-id gap deliberately. Counting
    that as stream loss would report every garage visit as a broken network."""
    recorder = LapRecorder()
    recorder.record_frame(make_packet(packet_id=100, speed_ms=50.0))
    for packet_id in range(101, 141):
        recorder.record_frame(
            make_packet(packet_id=packet_id, on_track=False))
    recorder.record_frame(make_packet(packet_id=141, speed_ms=50.0))

    assert recorder.stream_gaps == 0
    assert recorder.lost_packets == 0


# ----------------------------------- the lap crossing that starved the seat

def _lap_rows(count: int = 400) -> list[list]:
    """Rows shaped like a real lap: every column filled, speeds varying."""
    rows = []
    for index in range(count):
        row = [None] * len(FRAME_FIELDS)
        row[FRAME_FIELDS.index("t_ms")] = index * 17
        row[FRAME_FIELDS.index("speed_kph")] = round(80.0 + (index % 150), 2)
        row[FRAME_FIELDS.index("throttle_pct")] = float(index % 101)
        row[FRAME_FIELDS.index("lat_g")] = round((index % 30) / 10.0, 3)
        rows.append(row)
    return rows


def test_the_chunked_encode_writes_byte_identical_json():
    """**`json` does not release the GIL and `zlib` does.**

    Measured 22 Aug 2026 against a 100 Hz probe standing in for the audio
    callback, with `sys.setswitchinterval(0.0005)` already in force: one
    `json.dumps` of a lap held the GIL for 85 ms and cost 39 of 73 audio
    blocks. The same rows in slices cost 0.6 ms and none. That underfeed is
    what degrades the transducer's endpoint until the machine is rebooted, so
    the lap crossing is a hardware fault with a software cause.

    The blob's contract is "zlib of this JSON". The compressed framing may
    differ - streaming deflate is a different but equally valid stream - but
    the JSON inside it must not, or a stored lap depends on which code path
    wrote it.
    """
    import json
    import zlib

    # A column that mixes an int with floats cannot be packed exactly, so
    # this is the shape that takes the JSON path - which is the path the
    # chunking is about.
    rows = _lap_rows()
    speed = FRAME_FIELDS.index("speed_kph")
    rows[3][speed] = 100          # int among floats
    assert recorder._encode_columnar(rows, recorder.FRAME_SCHEMA_VERSION) is None, (
        "this no longer exercises the JSON fallback")

    single = json.dumps(
        {"format": BLOB_FORMAT, "v": recorder.FRAME_SCHEMA_VERSION,
         "fields": list(FRAME_FIELDS), "rows": rows},
        separators=(",", ":")).encode("utf-8")

    assert zlib.decompress(encode_frames(rows)) == single, (
        "the chunked encode changed the stored JSON, not just its framing")


def test_the_chunked_encode_round_trips():
    rows = _lap_rows()
    assert decode_frames(encode_frames(rows)) == decode_frames(
        encode_frames(rows)), "not deterministic"
    decoded = decode_frames(encode_frames(rows))
    assert len(decoded) == len(rows)
    assert decoded[7]["speed_kph"] == rows[7][FRAME_FIELDS.index("speed_kph")]


def test_a_lap_carries_its_own_top_speed():
    """**Taken off the rows, not read back out of the blob.**

    `Store._note_top_speed` used to `decode_frames` the lap it had just
    encoded three lines earlier, to take one maximum: 99 ms, about 30 ms of
    it `json.loads` holding the GIL, on the Qt thread, at every crossing. The
    same answer off the rows in hand is 0.9 ms - 108x - and it is the pattern
    `crawl_s`, `off_track_s` and `spin_s` already follow.
    """
    rows = _lap_rows()
    off_rows = recorder.top_speed_kph(rows)
    off_blob = max(f["speed_kph"] for f in decode_frames(encode_frames(rows))
                   if f["speed_kph"] is not None)
    assert off_rows == round(off_blob, 1), (
        f"the fast path disagrees with the blob: {off_rows} vs {off_blob}")


def test_a_spike_and_an_empty_lap_are_both_refused():
    """The ratchet only ever goes up and feeds a divisor for every future
    session at this circuit, so one bad frame must not move it - and nothing
    plausible must return null rather than zero."""
    spike = _lap_rows(10)
    spike[4][FRAME_FIELDS.index("speed_kph")] = 9_999.0
    assert recorder.top_speed_kph(spike) < recorder.MAX_PLAUSIBLE_KPH

    blank = [[None] * len(FRAME_FIELDS) for _ in range(5)]
    assert recorder.top_speed_kph(blank) is None, "missing is null, never zero"

    zeros = _lap_rows(5)
    for row in zeros:
        row[FRAME_FIELDS.index("speed_kph")] = 0.0
    assert recorder.top_speed_kph(zeros) is None, (
        "a stationary lap reported a top speed of zero, which would ratchet "
        "the event's reference down")


# ------------------------------------------------- the columnar blob format

def test_the_columnar_blob_round_trips_every_channel_kind_exactly():
    """**Exactly, not closely.** These numbers are the evidence every setup
    recommendation is built on, and a lap that changed in the fourth decimal
    on being re-read would be undetectable and wrong.

    Verified against the real database as well: 363 laps, 2,621,938 frames
    re-encoded columnar and decoded, zero differences, zero fallbacks.
    """
    rows = _lap_rows(120)
    # One of each kind the channels actually carry.
    for index, row in enumerate(rows):
        row[FRAME_FIELDS.index("t_ms")] = index * 17          # int
        row[FRAME_FIELDS.index("speed_kph")] = 80.0 + index / 3.0   # float
        row[FRAME_FIELDS.index("surf_fl")] = "TCDGSs"[index % 6]    # char
        # Nulls in the slip channels, as the real stream has them.
        row[FRAME_FIELDS.index("slip_fl")] = (None if index % 3
                                              else 0.9 + index / 1000.0)

    blob = encode_frames(rows)
    assert recorder._decode_columnar(__import__("zlib").decompress(blob)) \
        is not None, "this did not take the columnar path"

    back = decode_frames(blob)
    assert len(back) == len(rows)
    for index, (row, frame) in enumerate(zip(rows, back)):
        for position, name in enumerate(FRAME_FIELDS):
            assert frame[name] == row[position], (
                f"{name} changed at frame {index}: "
                f"{row[position]!r} -> {frame[name]!r}")
            # An int must come back an int, not a float that compares equal.
            assert type(frame[name]) is type(row[position]), (
                f"{name} changed TYPE at frame {index}: "
                f"{type(row[position])} -> {type(frame[name])}")


def test_a_column_that_cannot_be_packed_exactly_falls_back():
    """A mixed column is stored the old way rather than coerced. Coercion
    here is silent loss in the one table that cannot be regenerated."""
    rows = _lap_rows(20)
    speed = FRAME_FIELDS.index("speed_kph")
    rows[5][speed] = 100                     # int among floats

    assert recorder._encode_columnar(rows, recorder.FRAME_SCHEMA_VERSION) is None
    back = decode_frames(encode_frames(rows))
    assert back[5]["speed_kph"] == 100
    assert type(back[5]["speed_kph"]) is int, "the fallback coerced it anyway"


def test_a_boolean_is_refused_rather_than_stored_as_a_number():
    """`bool` is an `int` subclass, so it would pack into an integer column
    and come back as 0 or 1. Refused instead."""
    rows = _lap_rows(8)
    rows[2][FRAME_FIELDS.index("rev_limiter")] = True
    assert recorder._encode_columnar(rows, recorder.FRAME_SCHEMA_VERSION) is None
    assert decode_frames(encode_frames(rows))[2]["rev_limiter"] is True


def test_an_all_null_channel_survives():
    """A channel the packet never carried is null everywhere, and null is not
    zero - the export refuses to read one as the other."""
    rows = _lap_rows(30)
    for row in rows:
        row[FRAME_FIELDS.index("slip_rr")] = None
    back = decode_frames(encode_frames(rows))
    assert all(frame["slip_rr"] is None for frame in back)


def test_the_old_json_blobs_stay_readable():
    """363 laps on disk are v1 and the raw stream cannot be regenerated, so
    the reader knows both formats for good rather than the blobs being
    migrated."""
    import json
    import zlib

    rows = _lap_rows(15)
    legacy = zlib.compress(json.dumps(
        {"format": BLOB_FORMAT, "v": 1, "fields": list(FRAME_FIELDS),
         "rows": rows}, separators=(",", ":")).encode("utf-8"), 6)

    back = decode_frames(legacy)
    assert len(back) == 15
    assert back[0]["_v"] == 1, "the blob's own schema version was lost"
    assert back[9]["speed_kph"] == rows[9][FRAME_FIELDS.index("speed_kph")]


def test_a_re_encode_that_drops_the_schema_version_changes_the_physics():
    """**The one door nobody had closed.**

    The blob's schema version decides how the analysis reads the lap:
    `grip.yaw_source_for` takes yaw from the stored path below version 2 and
    off the packet at 2 and above, and the two differ by 3-4% at the top of
    the acceleration distribution - the same size as the compound step the
    tyre model exists to detect.

    A throwaway migration script re-encoded the database columnar without
    carrying it across. Every v1 lap came back stamped 2, and one event's
    export moved `yawDeficitPct` from 0.2 to 42.0 with wheelspin flag counts
    changed on nearly every corner. Nothing raised.

    So the version is a parameter now, and this is what holds it.
    """
    rows = _lap_rows(12)
    assert decode_frames(encode_frames(rows, version=1))[0]["_v"] == 1
    assert decode_frames(encode_frames(rows, version=2))[0]["_v"] == 2
    # The default is for a freshly recorded lap, which is genuinely current.
    assert (decode_frames(encode_frames(rows))[0]["_v"]
            == recorder.FRAME_SCHEMA_VERSION)

    # And the fallback path must carry it too, or a mixed column would lose
    # the stamp while a clean one kept it.
    mixed = _lap_rows(12)
    mixed[4][FRAME_FIELDS.index("speed_kph")] = 100
    assert recorder._encode_columnar(mixed, 1) is None
    assert decode_frames(encode_frames(mixed, version=1))[0]["_v"] == 1
