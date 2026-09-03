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
    """Ask for the firmware version letter. This rig answered 'j'.

    **Three bytes, not two, and the third is the fix for a fault that ran
    for weeks.** The firmware's handler, from the recovered source
    (`reference/simhub-baseline/sketch-src/SHCommands.h`):

        void Command_Hello() {
            FlowSerialTimedRead();      // reads ONE MORE byte
            delay(10);
            FlowSerialPrint(VERSION);   // 0x08 'j'
            FlowSerialFlush();
        }

    `FlowSerialTimedRead` pops from a buffer that every accepted packet's
    payload is appended to, and waits up to 400 ms for a byte to arrive.
    Sent as two bytes, the hello made the firmware sit in that wait - the
    417 ms version-packet latency measured on 3 Sep 2026 - and if anything
    else was sent inside the window, its FIRST PAYLOAD BYTE was eaten as
    the hello's third byte and the rest of that packet was discarded as
    stray headers. That is what swallowed the count query's reply, and
    what made the first motors frame after every reconnect read as
    "replied 0x08, which is not an acknowledgement". The padding byte is
    discarded by the firmware; its value does not matter.
    """
    return bytes([MESSAGE_HEADER]) + CMD_HELLO + b"\x00"


def split_packets(raw: bytes) -> list[tuple[int, bytes]]:
    """The device's outgoing stream, cut into the packets it is made of.

    **Measured on the board, 3 Sep 2026, byte by byte with timestamps** -
    `Command_Motors` lives in a header SimHub deleted, so this was read off
    the wire rather than the source. Three kinds appear:

        03 <id>            ACK          06 <len> <bytes>   STRING
        04 <id> <reason>   NACK         08 <value>         VALUE

    A byte that is none of those is returned alone as kind -1 and skipped -
    the count reply carries a bare 0x20 between its string and its last
    value packet. The reply to a count query on this board was, after the
    acknowledgement:

        08 ff  08 04  06 19 "Adafruit Motor Shield V2;"  20  08 0a

    and the reply to a hello is `08 6a` - a value packet carrying the version
    letter - arriving up to 417 ms after the acknowledgement.
    """
    packets: list[tuple[int, bytes]] = []
    i = 0
    while i < len(raw):
        kind = raw[i]
        if kind == REPLY_ACK and i + 1 < len(raw):
            packets.append((kind, raw[i + 1:i + 2])); i += 2
        elif kind == REPLY_NACK and i + 2 < len(raw):
            packets.append((kind, raw[i + 1:i + 3])); i += 3
        elif kind == REPLY_VALUE and i + 1 < len(raw):
            packets.append((kind, raw[i + 1:i + 2])); i += 2
        elif kind == REPLY_STRING and i + 1 < len(raw):
            length = raw[i + 1]
            packets.append((kind, raw[i + 2:i + 2 + length])); i += 2 + length
        else:
            packets.append((-1, raw[i:i + 1])); i += 1
    return packets


def parse_motors_count(raw: bytes) -> int | None:
    """The channel count in a count reply: the first value packet whose
    value is a plausible count. None where there is none, never a guess.

    **The first version of this read the marker byte as the count.** The two
    bytes it saw were `08 6a` - the hello's late version packet, not the
    count reply at all - and it read 0x08 as eight. The board then
    acknowledged 26,875 eight-wide frames, so nothing downstream could tell.
    Now the stream is cut into packets first, and a marker is never a
    number. `08 ff` (255) and `08 0a` (10) are skipped as implausible; `08 04`
    is the count.

    **A count is never trusted into a narrower frame.** Also measured: a
    frame two bytes short of the board's width is acknowledged at once and
    so is the frame after it, so an acknowledgement proves nothing about
    width in either direction. `WindLink.discover_channels` treats the count
    on file as a floor.
    """
    for kind, body in split_packets(raw):
        if kind == REPLY_VALUE and body and 1 <= body[0] <= MAX_CHANNELS:
            return body[0]
    return None


def parse_motors_board(raw: bytes) -> str | None:
    """The board name in a count reply: the first string packet, trimmed of
    the trailing separator the firmware prints after it."""
    for kind, body in split_packets(raw):
        if kind == REPLY_STRING and body:
            name = body.decode("ascii", "replace").strip().rstrip(";").strip()
            return name or None
    return None


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
