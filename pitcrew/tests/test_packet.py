"""Packet decoding, including the extended 368-byte tail."""
from __future__ import annotations

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


def test_steering_is_none_until_the_offset_is_verified():
    """The offset is unverified, so steering must report absence, not a guess."""
    assert packet_mod.STEERING_TAIL_OFFSET is None
    assert make_packet(extended=True).steering is None
    assert make_packet(extended=False).steering is None


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
