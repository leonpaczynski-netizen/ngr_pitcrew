"""SimHub's ARQ serial framing, rebuilt from the wire rather than the source.

The wind simulator is a Sector 17 / Redion WSP: an Arduino Uno behind a CH340,
driving two fans through an Adafruit Motor Shield V2. It was flashed by SimHub
and speaks SimHub's own framing, so talking to it means speaking that framing.

**Provenance, stated plainly.** SimHub generated the sketch into
`_Addons/Arduino/DisplayClientV2/`, and that folder was deleted on 15 Aug 2026
when a wedged SimHub process finally exited; SimHub was uninstalled shortly
after. `reference/simhub-baseline/DisplayClientV2.ino` survives and is the
only record of *this device's* configuration, but the framing lived in the
`.h` files beside it and those are gone. So the layout below comes from the
published reimplementations rather than from the firmware, and one constant -
the CRC polynomial - could not be verified at all.

That is why `CRC_VARIANTS` is a list and not a number. The device answers a
bad checksum with `NACK` reason 4, which names the fault precisely, so the
handshake tries candidates until one is acknowledged. A protocol constant
nobody can verify is not the same as a protocol constant nobody can
determine - and asking the device settled it in one connection: it speaks
**DVB-S2**, having rejected the three more obvious candidates first. That
answer is now measured, and the probe stays because it was measured on one
board and a reflash could change it.

What is verified, from `DisplayClientV2.ino` in the repo:

* the command dispatch reads a header byte, then one command character, and
  `'V'` is `Command_Motors` (the sketch's serial loop);
* five seconds of total silence triggers `Command_Shutdown`;
* and from `SHShakeitBase.h`, read before it was lost:
  `#define SHShakeitBaseSafetyDelay 1000` - more than a second without a
  successful motors read and the firmware zeroes every channel itself.

That last one is the safety property this whole layer leans on: the fans
cannot stick on if the PC side dies. It is also a hard requirement in the
other direction, and the reason `wind.py` transmits unconditionally rather
than only when the value changes.
"""
from __future__ import annotations

from dataclasses import dataclass

# Frame: 0x01 0x01 <packet id> <length> <data...> <crc8>
FRAME_HEADER = b"\x01\x01"
# Every command payload starts with this, then one character of command.
MESSAGE_HEADER = 0x03
# `Command_Motors`. 'C' asks how many channels there are and what board is
# driving them; 'S' sets them.
CMD_MOTORS = b"V"
MOTORS_COUNT = b"C"
MOTORS_SET = b"S"
# `Command_Hello`, which answers with the firmware's version letter. The
# device on this rig reported 'j'.
CMD_HELLO = b"1"

# Device -> host. ACK and NACK are the two that matter; the others appear in
# replies to queries this module does not need.
REPLY_ACK = 0x03
REPLY_NACK = 0x04
REPLY_STRING = 0x06
REPLY_VALUE = 0x08

# Why a frame was rejected. Reason 4 is the one that makes the CRC knowable:
# the device distinguishes "your checksum is wrong" from every other fault, so
# a wrong polynomial fails loudly and specifically instead of looking like a
# dead cable.
NACK_REASONS = {
    1: "could not read the packet id",
    2: "bad length",
    3: "no checksum arrived",
    4: "checksum did not match",
    5: "the frame was incomplete",
}
NACK_BAD_CRC = 4

# Payload length is a single byte and the firmware rejects anything outside
# this, which is `NACK` reason 2.
MAX_PAYLOAD = 32

# The most channels a count reply is allowed to claim. Nothing on this rig or
# any SimHub fan board approaches it; a parse that produces more than this
# has read the wrong byte, and the caller must not act on it.
MAX_CHANNELS = 8

# 255 is a broadcast id the firmware accepts whatever it was expecting next.
# It is the resync escape hatch, and it is what the handshake opens with -
# there is no way to know where the sequence stands on a device that has been
# talking to something else all week.
BROADCAST_ID = 255
MAX_SEQUENCE_ID = 127


def _table(polynomial: int, *, reflected: bool) -> tuple[int, ...]:
    table = []
    for byte in range(256):
        value = byte
        for _ in range(8):
            if reflected:
                value = (value >> 1) ^ (polynomial if value & 1 else 0)
            else:
                value = ((value << 1) ^ (polynomial if value & 0x80 else 0)) \
                    & 0xFF
        table.append(value & 0xFF)
    return tuple(table)


@dataclass(frozen=True)
class CrcVariant:
    """One candidate checksum, with the name to report when it is the one."""
    name: str
    polynomial: int
    reflected: bool

    def __call__(self, data: bytes) -> int:
        table = _table(self.polynomial, reflected=self.reflected)
        crc = 0
        for byte in data:
            crc = table[crc ^ byte]
        return crc


# **DVB-S2 leads because the device said so.** Asked on 15 Aug 2026, the
# Redion on COM5 rejected Dallas/Maxim, CRC-8/ATM and SAE-J1850 in turn - each
# with NACK reason 4, "checksum did not match" - and acknowledged DVB-S2. That
# rejection pattern is itself the proof the framing is right: the firmware
# parsed all four frames well enough to say precisely what was wrong with the
# first three.
#
# Worth dwelling on, because it is the reason this is a list. Dallas/Maxim is
# what avr-libc's `_crc_ibutton_update` computes and what nearly every Arduino
# project reaches for, so it is what a reasonable person would have hardcoded
# after losing the firmware source - and it would have silently driven nothing
# at all.
#
# The others stay, and the probe stays, because this was measured on one
# device and a reflash or a replacement board could answer differently.
CRC_VARIANTS: tuple[CrcVariant, ...] = (
    CrcVariant("crc8-dvb-s2", 0xD5, reflected=False),
    CrcVariant("dallas-maxim", 0x8C, reflected=True),
    CrcVariant("crc8-atm", 0x07, reflected=False),
    CrcVariant("crc8-sae-j1850", 0x1D, reflected=False),
)
# The one this rig speaks. Still probed rather than assumed at connect time.
DEFAULT_CRC = CRC_VARIANTS[0]


def build_frame(packet_id: int, payload: bytes,
                crc: CrcVariant = DEFAULT_CRC) -> bytes:
    """One framed command, ready for the wire.

    The checksum covers the id, the length and the data - **not** the two
    header bytes. Including them is the obvious mistake and it produces a
    device that NACKs everything with reason 4, which at least says so.
    """
    if not 0 <= packet_id <= 255:
        raise ValueError(f"packet id {packet_id} is not a byte")
    if not payload:
        raise ValueError("a frame with no payload has nothing to say")
    if len(payload) > MAX_PAYLOAD:
        raise ValueError(
            f"payload is {len(payload)} bytes and the firmware rejects "
            f"anything over {MAX_PAYLOAD}")
    body = bytes([packet_id, len(payload)]) + payload
    return FRAME_HEADER + body + bytes([crc(body)])


def motors_payload(values: list[int] | tuple[int, ...]) -> bytes:
    """`0x03 'V' 'S'` then one raw byte per channel, in order.

    Every channel every time. The firmware reads exactly `motorCount()` bytes
    with no delimiters and no way to address one of them, so a short write
    leaves it waiting mid-frame for bytes that never come. This device
    declares four channels even though only two fans are wired.
    """
    if not values:
        raise ValueError("no channels to set")
    for value in values:
        if not 0 <= value <= 255:
            raise ValueError(f"channel value {value} is not a byte")
    return bytes([MESSAGE_HEADER]) + CMD_MOTORS + MOTORS_SET + bytes(values)


def motors_count_payload() -> bytes:
    """Ask how many channels there are and which board drives them."""
    return bytes([MESSAGE_HEADER]) + CMD_MOTORS + MOTORS_COUNT


def hello_payload() -> bytes:
    """Ask for the firmware version letter. This rig answered 'j'."""
    return bytes([MESSAGE_HEADER]) + CMD_HELLO


def parse_motors_count(raw: bytes) -> int | None:
    """The bytes that follow the acknowledgement of a `'V' 'C'` query, read
    as a channel count. None where they cannot be, never a guess.

    **The format is not known from source.** `Command_Motors` lives in a
    header SimHub deleted, and the reply's shape could not be recovered.
    What is known is what SimHub logged from the same query on this board -
    `"MotorsCount": 4, "MotorsBoard": "Adafruit Motor Shield V2"` - so a
    count and a board name come back, count first. This accepts the two
    encodings a count at the head of that reply could plausibly take, a raw
    byte or an ASCII digit, and bounds it at `MAX_CHANNELS`. Anything else is
    None, and the caller logs the raw bytes so the format is measured the
    first time a board answers rather than assumed here.

    **A count is never trusted on its own.** Whoever calls this must confirm
    it against the board - `WindLink.confirm_channels` - because a wrong
    width does not fail loudly: a frame one byte too long leaves a byte over
    that corrupts the next, and one too short leaves the firmware waiting
    mid-command. Both end with the deadman zeroing the fans.
    """
    if not raw:
        return None
    head = raw[0]
    if head == REPLY_VALUE:
        # A value packet: the marker, then the value. **Measured 3 Sep 2026
        # on this board: the two bytes after a count query were `08 6a`, and
        # the first version of this read the marker as a count of eight.**
        # The board then acknowledged 26,875 eight-wide frames, so nothing
        # downstream could tell. A marker is never a count.
        if len(raw) < 2:
            return None
        count = raw[1]
    elif head in (REPLY_ACK, REPLY_NACK, REPLY_STRING):
        # A reply marker at the head is a reply, not a number that happens
        # to be small. A bare 0x04 is indistinguishable from a NACK, so a
        # bare count in that range is refused rather than guessed.
        return None
    elif 0x30 <= head <= 0x39:          # an ASCII digit
        count = head - 0x30
    else:
        count = head
    if count > MAX_CHANNELS:
        return None
    return count


@dataclass(frozen=True)
class Reply:
    """What came back, in terms the caller can act on."""
    kind: int
    packet_id: int | None = None
    reason: int | None = None

    @property
    def acknowledged(self) -> bool:
        return self.kind == REPLY_ACK

    @property
    def bad_checksum(self) -> bool:
        """The one rejection that means "try a different polynomial"."""
        return self.kind == REPLY_NACK and self.reason == NACK_BAD_CRC

    def describe(self) -> str:
        if self.kind == REPLY_ACK:
            return f"acknowledged frame {self.packet_id}"
        if self.kind == REPLY_NACK:
            why = NACK_REASONS.get(self.reason, f"reason {self.reason}")
            return (f"rejected the frame - {why} "
                    f"(last good frame was {self.packet_id})")
        return f"replied {self.kind:#04x}, which is not an acknowledgement"


def parse_reply(data: bytes) -> Reply | None:
    """Read one ACK or NACK. None means not enough bytes yet.

    Anything that is not an acknowledgement is returned rather than raised:
    the device emits string and value markers in reply to other queries, and a
    stray one of those is not a reason to tear the connection down.
    """
    if not data:
        return None
    kind = data[0]
    if kind == REPLY_ACK:
        if len(data) < 2:
            return None
        return Reply(kind=REPLY_ACK, packet_id=data[1])
    if kind == REPLY_NACK:
        if len(data) < 3:
            return None
        return Reply(kind=REPLY_NACK, packet_id=data[1], reason=data[2])
    return Reply(kind=kind)


def next_id(previous: int) -> int:
    """Sequential 0-127, wrapping. `BROADCAST_ID` is outside the sequence."""
    if previous >= MAX_SEQUENCE_ID or previous < 0:
        return 0
    return previous + 1
