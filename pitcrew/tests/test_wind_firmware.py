"""The board's firmware and the host that drives it, checked against each other.

`firmware/wind/wind.ino` is ours now - written 6 Sep 2026 to replace SimHub's
generated sketch, because SimHub is no longer installed and its 106 KB file
pulls in headers it keeps inside its own DLLs. The firmware and
`pitcrew/rig/arq.py` are two halves of one wire format, maintained in two
languages, and **nothing at runtime will tell us they have drifted**: a
mismatched constant produces a board that NACKs everything, or worse,
acknowledges frames and drives nothing.

There is no C compiler on this machine that targets the host, so the firmware
cannot be run here - only avr-g++, which builds for the board. That bounds
what these tests can be. They do two things:

* **Check the checksum against the old firmware's own table.** This is the
  real proof, not a source-shape assertion. The polynomial was never
  documented; `arq.py` had to ask the board, which rejected three candidates
  before acknowledging DVB-S2. The recovered `ArqSerial.h` carries the 256
  constants SimHub actually shipped, so the new bitwise routine can be
  checked against all 256 of them.
* **Pin the constants both halves must share**, by reading them out of the
  firmware source. The precedent is `test_spread.py`'s crawl-filter test:
  where the defect is a value that drifts between two files, the source text
  is the thing to assert on.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from pitcrew.rig import arq

FIRMWARE = Path("firmware/wind/wind.ino")
BASELINE = Path("reference/simhub-baseline/sketch-src/ArqSerial.h")


@pytest.fixture(scope="module")
def source() -> str:
    return FIRMWARE.read_text(encoding="utf-8")


def define(source: str, name: str) -> str:
    """The value of one `#define`, as written."""
    match = re.search(rf"^#define\s+{re.escape(name)}\s+(\S+)", source,
                      re.MULTILINE)
    assert match, f"{name} is not defined in {FIRMWARE}"
    return match.group(1)


# ----------------------------------------------------- the checksum, proved

def firmware_crc(data: bytes) -> int:
    """`crc8Update` from the firmware, transcribed.

    Bitwise, exactly as the firmware computes it - the firmware carries no
    table, deliberately, because a 256-entry table is 256 chances to mistype
    a constant. This transcription is what the next test checks against the
    256 constants SimHub actually shipped.
    """
    crc = 0
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = ((crc << 1) ^ 0xD5) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def test_the_new_bitwise_checksum_reproduces_the_old_firmware_table():
    """**The one constant nobody could guess, checked all 256 ways.**

    Dallas/Maxim is what avr-libc computes and what nearly every Arduino
    project reaches for. It would have been the reasonable choice, and it
    would have driven nothing at all - the board would have NACKed every
    frame with reason 4. The old firmware's table is the only surviving
    record of the right answer, so it is what the new routine is measured
    against.
    """
    text = BASELINE.read_text(encoding="utf-8")
    match = re.search(r"crc_table_crc8\[256\]\s*PROGMEM\s*=\s*\{([^}]*)\}", text)
    assert match, "the shipped CRC table is not in the recovered header"
    shipped = [int(n) for n in match.group(1).split(",") if n.strip()]
    assert len(shipped) == 256, f"read {len(shipped)} entries, not 256"

    # table[b] is the checksum of a single byte b against an initial crc of 0,
    # which is exactly what the bitwise routine computes for a one-byte input.
    ours = [firmware_crc(bytes([b])) for b in range(256)]
    assert ours == shipped


def test_the_firmware_and_the_host_compute_the_same_checksum():
    """Both halves, over the payloads that actually go across."""
    for payload in (arq.hello_payload(),
                    arq.motors_count_payload(),
                    arq.motors_payload([0, 0, 0, 0]),
                    arq.motors_payload([255, 128, 7, 0])):
        body = bytes([12, len(payload)]) + payload
        assert firmware_crc(body) == arq.DEFAULT_CRC(body)


def test_the_polynomial_is_written_out_in_the_firmware(source):
    """A different polynomial in the sketch is the failure this catches, and
    it is invisible until the board is on the bench refusing frames."""
    assert "0xD5" in source, "the firmware is not using the DVB-S2 polynomial"


# --------------------------------------------- constants both halves share

def test_the_frame_layout_matches(source):
    assert define(source, "MAX_PAYLOAD") == str(arq.MAX_PAYLOAD)
    assert int(define(source, "MESSAGE_HEADER"), 16) == arq.MESSAGE_HEADER
    # The two header bytes and the broadcast id are written inline rather
    # than as defines, so they are checked as text.
    assert "0x01" in source
    assert "packetId == 255" in source, "the broadcast id is not accepted"


def test_the_rejection_reasons_match(source):
    """The host distinguishes them, and reason 4 is what made the polynomial
    discoverable at all - so these are wire format, not diagnostics."""
    named = {
        "NACK_NO_PACKET_ID": 1,
        "NACK_BAD_LENGTH": 2,
        "NACK_NO_CHECKSUM": 3,
        "NACK_BAD_CHECKSUM": 4,
        "NACK_INCOMPLETE": 5,
    }
    for name, value in named.items():
        assert int(define(source, name), 16) == value
        assert value in arq.NACK_REASONS
    assert int(define(source, "NACK_BAD_CHECKSUM"), 16) == arq.NACK_BAD_CRC


def test_the_reply_markers_match(source):
    """`split_packets` cuts the device's stream on these four bytes."""
    for marker in (arq.REPLY_ACK, arq.REPLY_NACK,
                   arq.REPLY_STRING, arq.REPLY_VALUE):
        assert f"Serial.write(0x{marker:02X})" in source, \
            f"marker 0x{marker:02X} is not emitted by the firmware"


def test_the_channel_count_is_four_not_two(source):
    """**Two fans are wired and four channels are sent.** The host reads
    exactly `motorCount()` bytes with no delimiters, so trimming the count
    to the hardware would leave the board waiting mid-frame forever."""
    assert define(source, "CHANNELS") == "4"


def test_the_deadman_is_unchanged(source):
    """The safety property the whole wind layer leans on: the fans cannot
    stick on if the PC side dies. `wind.py` transmits unconditionally at
    better than 1 Hz because of this number."""
    from pitcrew.rig.wind import DEADMAN_S
    assert int(define(source, "SAFETY_DELAY_MS")) == int(DEADMAN_S * 1000)


def test_the_baud_rate_is_the_one_the_host_opens_at(source):
    from pitcrew.rig.wind import BOOT_BAUD
    assert int(define(source, "BOOT_BAUD")) == BOOT_BAUD


# ------------------------------------------------- the replies, end to end

def test_the_count_reply_parses_to_four_channels_and_the_board_name():
    """The exact bytes `commandMotorsCount` emits, run through the host's
    own parsers. Measured off the old board on 3 Sep 2026 and recorded in
    `arq.py`; the new firmware has to reproduce it marker for marker.

    **The leading 255 is a marker, not a count.** A host that read it as one
    saw eight channels, sent eight-wide frames, had every one of them
    acknowledged, and drove nothing for a whole session.
    """
    name = b"Adafruit Motor Shield V2;"
    reply = (bytes([arq.REPLY_VALUE, 255])
             + bytes([arq.REPLY_VALUE, 4])
             + bytes([arq.REPLY_STRING, len(name)]) + name + b"\x20"
             + bytes([arq.REPLY_VALUE, 0x0A]))

    assert arq.parse_motors_count(reply) == 4
    assert arq.parse_motors_board(reply) == "Adafruit Motor Shield V2"


def test_the_firmware_emits_that_reply_in_that_order(source):
    """Order is the part a reader cannot check by eye: the string packet
    carries its own length, so a value emitted before it shifts nothing and
    fails silently."""
    body = source[source.index("void commandMotorsCount"):]
    body = body[:body.index("\n}")]
    emitted = re.findall(r"write(?:Value|String)\(([^)]*)\)", body)
    assert emitted == ["255", "CHANNELS", 'MOTOR_BOARD_NAME ";"', "'\\n'"]


def test_the_hello_still_pops_the_padding_byte(source):
    """**Not a bug, and it must stay.** `Command_Hello` reads one byte before
    answering, so the host sends a three-byte hello whose third byte is
    padding. Dropping the read here would make the firmware eat the first
    byte of whatever packet came next - the fault that made the first motors
    frame after every reconnect read as `replied 0x08`, which ran for weeks.
    """
    body = source[source.index("static void commandHello"):]
    body = body[:body.index("\n}")]
    assert "arqRead();" in body, "the hello no longer consumes its padding byte"
    assert len(arq.hello_payload()) == 3, "the host stopped sending it"


def test_the_version_letter_is_the_one_on_file(source):
    assert define(source, "FIRMWARE_VERSION") == "'j'"


def test_the_unique_id_is_unchanged(source):
    """The board's identity to anything that has seen it before. A new id
    makes it a new device."""
    assert "c3bcb391-760c-4eee-89cb-232246fce7dc" in source


# --------------------------------------------------------- the actual change

def test_the_pwm_frequency_is_the_highest_the_part_can_reach(source):
    """**The one behavioural change in this firmware, and its ceiling.**

    The PCA9685's prescale has a datasheet floor of 3:

        prescale = round(25e6 / (4096 * f)) - 1,  minimum 3

    so 25e6/(4096*4) = 1525.9 Hz is the most it can produce. SimHub's field
    was labelled "1900hz max" and defaulted to 1900 - a value the chip cannot
    reach, which is worth knowing before anyone tries to raise this again.
    This rig was set to 1200, landing on prescale 4 and 1220.7 Hz.
    """
    requested = int(define(source, "WIND_PWM_HZ"))
    prescale = max(3, round(25_000_000 / (4096 * requested)) - 1)
    achieved = 25_000_000 / (4096 * (prescale + 1))

    assert prescale == 3, "not asking for the fastest chop the part allows"
    assert achieved == pytest.approx(1525.9, abs=0.1)

    was = 25_000_000 / (4096 * (max(3, round(25_000_000 / (4096 * 1200)) - 1) + 1))
    assert was == pytest.approx(1220.7, abs=0.1), "the old setting moved"
    assert achieved / was > 1.2, "the change is not worth a reflash"


def test_the_ramp_limiter_is_off(source):
    """**Deliberately.** It is the next hypothesis if the frequency alone
    does not fix the dropouts, and shipping both at once would mean learning
    nothing from either."""
    assert define(source, "WIND_RAMP_STEP") == "0"

def test_the_shield_frequency_can_be_read_back_off_the_chip(source):
    """**Measured on the board, 6 Sep 2026: PRESCALE 3, MODE1 0x20.**

    Without this command the "1526 Hz" claim rested on the number in the
    source reaching the part, and nothing verified that - an I2C write that
    goes nowhere is silent, and the board would acknowledge every frame
    exactly as it does when the shield is working. Asked over `X shieldfreq`
    it answered `08 03 08 20`: prescale 3, so 25e6/(4096*4) = 1525.9 Hz, and
    MODE1 awake with auto-increment on.

    A prescale of 0 is the failure signal - nothing answered at 0x60 - and
    cannot be a real setting, the datasheet floor being 3.
    """
    assert "shieldfreq" in source, "the readback command is gone"
    body = source[source.index("static void commandShieldFreq"):]
    body = body[:body.index("\n}")]
    assert "PCA9685_PRESCALE" in body and "PCA9685_MODE1" in body
