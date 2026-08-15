"""Packet decoding, including the extended 368-byte tail."""
from __future__ import annotations

import math
import struct

from pitcrew.telemetry import packet as packet_mod
from pitcrew.telemetry.packet import PACKET_SIZE, parse_packet

from .conftest import MAGIC, make_packet, raw_packet


def test_short_packet_is_rejected():
    assert parse_packet(b"0S7G" + bytes(10)) is None


def test_classic_packet_has_no_tail():
    pkt = parse_packet(raw_packet(extended=False))
    assert pkt is not None
    assert pkt.tail is None
    assert pkt.has_extended_tail is False


def test_extended_packet_keeps_the_tail():
    pkt = parse_packet(raw_packet(extended=True))
    assert pkt is not None
    assert pkt.has_extended_tail is True
    assert len(pkt.tail) == 72


def measured_tail_packet(**overrides):
    """A packet carrying the bytes actually observed on a live GT7 v1.70 stream.

    Captured 11 Aug 2026 with a Porsche 911 RSR parked on tarmac, lap clock
    running, wheel centred. These exact bytes are what pinned the offsets, so
    they are the regression: if a future change moves an offset, this fails.
    """
    data = bytearray(raw_packet(extended=True))
    struct.pack_into("<f", data, 296, overrides.get("steering", 0.0))
    data[344:348] = overrides.get("surface", b"TTTT")
    struct.pack_into("<i", data, 348, overrides.get("lap_ms", 69716))
    struct.pack_into("<f", data, 360, 2.516)
    data[364:368] = overrides.get("category", b"GR3\x00")
    return parse_packet(bytes(data))


def test_steering_reads_the_measured_offset():
    assert packet_mod.STEERING_TAIL_OFFSET == 296
    assert measured_tail_packet(steering=0.0).steering == 0.0
    assert round(measured_tail_packet(steering=1.5708).steering, 4) == 1.5708


def test_steering_saturates_at_pi_and_normalises_to_one():
    """wheelRotation is the in-game wheel: full lock is +-pi, not +-540 deg."""
    assert measured_tail_packet(steering=math.pi).steering_norm == 1.0
    assert measured_tail_packet(steering=-math.pi).steering_norm == -1.0
    assert measured_tail_packet(steering=0.0).steering_norm == 0.0
    assert round(measured_tail_packet(steering=math.pi / 2).steering_norm, 3) == 0.5


def test_steering_norm_is_clamped():
    assert measured_tail_packet(steering=4.0).steering_norm == 1.0


def test_steering_is_absent_on_the_classic_packet():
    assert make_packet(extended=False).steering is None
    assert make_packet(extended=False).steering_norm is None


def test_surface_types_decode_per_wheel():
    assert measured_tail_packet().surface_types == ("T", "T", "T", "T")
    assert measured_tail_packet(surface=b"TTGC").surface_types == ("T", "T", "G", "C")


def test_surface_types_absent_on_the_classic_packet():
    assert make_packet(extended=False).surface_types is None


def test_current_lap_time_is_a_millisecond_clock():
    assert measured_tail_packet(lap_ms=69_716).current_lap_time_ms == 69_716
    assert measured_tail_packet(lap_ms=69_700).current_lap_time_ms == 69_700


def test_current_lap_time_negative_reads_as_absent():
    assert measured_tail_packet(lap_ms=-1).current_lap_time_ms is None


def test_car_category_decodes_and_strips_padding():
    assert measured_tail_packet().car_category == "GR3"
    assert measured_tail_packet(category=b"GR4\x00").car_category == "GR4"
    assert measured_tail_packet(category=b"\x00\x00\x00\x00").car_category is None


def test_wheelbase_matches_the_car():
    assert round(measured_tail_packet().wheelbase_m, 3) == 2.516


def test_tail_float_reads_a_known_value():
    data = bytearray(raw_packet(extended=True))
    struct.pack_into("<f", data, PACKET_SIZE + 8, -0.75)
    pkt = parse_packet(bytes(data))
    assert pkt.tail_float(PACKET_SIZE + 8) == -0.75


def test_tail_float_out_of_range_returns_none():
    pkt = parse_packet(raw_packet(extended=True))
    assert pkt.tail_float(PACKET_SIZE - 4) is None
    assert pkt.tail_float(PACKET_SIZE + 80) is None


def test_tail_float_rejects_nan():
    data = bytearray(raw_packet(extended=True))
    struct.pack_into("<f", data, PACKET_SIZE + 4, float("nan"))
    pkt = parse_packet(bytes(data))
    assert pkt.tail_float(PACKET_SIZE + 4) is None


def test_flag_bits():
    pkt = make_packet(flags_raw=0x0001 | 0x0004)
    assert pkt.car_on_track is True
    assert pkt.loading is True
    assert pkt.paused is False


def test_speed_conversion():
    assert make_packet(speed_ms=10.0).speed_kmh == 36.0


def test_magic_is_required():
    assert parse_packet(b"XXXX" + bytes(PACKET_SIZE - 4)) is None
    assert parse_packet(MAGIC + bytes(PACKET_SIZE - 4)) is not None
