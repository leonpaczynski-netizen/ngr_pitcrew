"""Golden-fixture tests for the GT7 telemetry decrypt/parse core (telemetry/packet.py).

The Salsa20 decrypt + 60-offset struct unpack is the most correctness-critical,
hardest-to-eyeball code in the app: a single silent offset or mask regression
would corrupt every downstream reading. Previously it was only exercised
indirectly. These build real encrypted packets (both IV masks + the 296- and
368-byte formats) with known field values and assert they decode back exactly,
and that malformed input is rejected (never raises, returns None).
"""
from __future__ import annotations

import struct

import pytest

from Crypto.Cipher import Salsa20

from telemetry.packet import (
    parse_packet, PACKET_SIZE, PACKET_SIZE_NEW, _FMT, VALID_MAGIC,
    _SALSA_KEY, _IV_MASK_NEW, _IV_MASK_OLD,
)

# Documented byte offsets (telemetry/packet.py struct map).
_OFF = {
    "engine_rpm": (60, "<f", 8500.0),
    "fuel_level": (68, "<f", 42.5),
    "speed_ms":   (76, "<f", 61.1),
    "packet_id":  (112, "<I", 12345),
    "car_id":     (292, "<i", 999),
}


def _plaintext(size=PACKET_SIZE) -> bytearray:
    buf = bytearray(size)
    buf[0:4] = b"0S7G"  # valid magic
    for off, fmt, val in _OFF.values():
        struct.pack_into(fmt, buf, off, val)
    return buf


def make_encrypted(*, iv1=0x11223344, mask=_IV_MASK_NEW, size=PACKET_SIZE) -> bytes:
    """Build a real GT7-style encrypted packet decoding to the known values.

    The nonce is carried plaintext at offset 64 in the *encrypted* packet, so we
    force ciphertext[64:68] == iv1 exactly as the game does.
    """
    buf = _plaintext(size)
    iv2 = iv1 ^ mask
    nonce = struct.pack("<II", iv2, iv1)
    keystream = Salsa20.new(key=_SALSA_KEY, nonce=nonce).decrypt(bytes(size))
    buf[64:68] = bytes(a ^ b for a, b in zip(struct.pack("<I", iv1), keystream[64:68]))
    return bytes(a ^ b for a, b in zip(bytes(buf), keystream))


def _assert_known_fields(pkt):
    assert pkt is not None
    assert pkt.magic in VALID_MAGIC
    assert pkt.engine_rpm == 8500.0
    assert pkt.fuel_level == 42.5
    assert round(pkt.speed_ms, 1) == 61.1
    assert pkt.packet_id == 12345
    assert pkt.car_id == 999


def test_struct_size_invariant():
    # Guards against offset drift in the field map.
    assert _FMT.size == PACKET_SIZE == 296


def test_roundtrip_new_mask_296():
    _assert_known_fields(parse_packet(make_encrypted(mask=_IV_MASK_NEW)))


def test_roundtrip_legacy_mask_296():
    # Pre-2024 packets used the old IV mask; decrypt must fall back to it.
    _assert_known_fields(parse_packet(make_encrypted(mask=_IV_MASK_OLD)))


def test_roundtrip_extended_368():
    pkt = parse_packet(make_encrypted(size=PACKET_SIZE_NEW))
    _assert_known_fields(pkt)


@pytest.mark.parametrize("iv1", [0x00000000, 0x0000DEAD, 0xFFFFFFFF, 0x89ABCDEF])
def test_roundtrip_various_nonces(iv1):
    _assert_known_fields(parse_packet(make_encrypted(iv1=iv1)))


def test_pre_decrypted_packet_parses_without_decrypt():
    # Bytes that already carry a valid magic are parsed as-is (rare relay case).
    _assert_known_fields(parse_packet(bytes(_plaintext())))


def test_short_packet_returns_none():
    assert parse_packet(b"\x00" * (PACKET_SIZE - 1)) is None
    assert parse_packet(b"") is None


def test_garbage_returns_none_not_raise():
    # Random bytes won't decrypt to a valid magic → None, and must never raise.
    assert parse_packet(b"\x00" * PACKET_SIZE) is None
    result = parse_packet(bytes(range(256)) * 2)
    assert result is None or hasattr(result, "magic")


def test_bad_magic_after_decrypt_returns_none():
    enc = bytearray(make_encrypted())
    # Corrupt the magic region so post-decrypt magic check fails.
    enc[0:4] = b"\xAA\xBB\xCC\xDD"
    assert parse_packet(bytes(enc)) is None
