"""Raw session capture — every datagram, exactly as it arrived, timestamped.

This is deliberately *not* the lap-frame store in `recorder.py`. That store
serialises a chosen set of channels per lap, and `FRAME_FIELDS` carries no fuel
column at all — so it cannot answer the one question M0 exists to settle. It
also keys everything to laps, and a pit stop is a thing that happens *inside*
one.

So this writes the datagram, undecoded, with a clock. Two consequences worth
having:

* **Next month's question is answerable.** Every channel GT7 sends is on disk,
  including the ones nobody has thought to look at, and including the ones a
  future packet format adds. A measurement run is half an hour of someone's
  evening; re-running it because the capture dropped a column is not a trade
  worth making.
* **No parsing decision is baked in.** Decryption and parsing stay in
  `packet.py` where they are already tested, and a capture recorded today
  re-analyses correctly under a parser fixed tomorrow.

The cost is size: 368 bytes plus 10 of framing at 60 Hz is ~1.4 MB a minute,
so a 30-minute run is ~40 MB. That is nothing against re-running the race.

Format, version 1::

    b"pitcrew.capture.v1\\n"        magic line
    <json metadata>\\n              one line, UTF-8
    repeated: <d: seconds><H: len><len bytes>

Timestamps are seconds from the first datagram, from a monotonic clock, so the
file has no wall-clock in it and replays identically. The metadata line is
where a wall-clock stamp goes, because it is a label rather than an input.
"""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

MAGIC = b"pitcrew.capture.v1\n"
_RECORD = struct.Struct("<dH")

# A GT7 datagram is 296-368 bytes. Anything wildly outside that is a truncated
# file or a different protocol, and reading on would produce plausible garbage.
MAX_DATAGRAM = 4096


class CaptureError(ValueError):
    """The file is not a capture, or not one this version can read."""


@dataclass(frozen=True)
class Datagram:
    """One packet as received, and when."""
    t_s: float
    data: bytes


class CaptureWriter:
    """Append datagrams to a capture file.

    Used as a context manager. `write` takes the raw bytes off the socket and a
    monotonic timestamp; the first one seen sets the origin, so the caller does
    not have to remember to zero anything.
    """

    def __init__(self, path: str | Path, **metadata) -> None:
        self.path = Path(path)
        self._metadata = dict(metadata)
        self._handle = None
        self._origin: float | None = None
        self.count = 0

    def __enter__(self) -> "CaptureWriter":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("wb")
        self._handle.write(MAGIC)
        self._handle.write(
            json.dumps(self._metadata, sort_keys=True).encode("utf-8") + b"\n")
        return self

    def write(self, data: bytes, t_monotonic: float) -> None:
        if self._handle is None:
            raise CaptureError("writer is not open")
        if len(data) > MAX_DATAGRAM:
            raise CaptureError(
                f"datagram of {len(data)} bytes is not GT7 telemetry")
        if self._origin is None:
            self._origin = t_monotonic
        self._handle.write(_RECORD.pack(t_monotonic - self._origin, len(data)))
        self._handle.write(data)
        self.count += 1

    def flush(self) -> None:
        if self._handle is not None:
            self._handle.flush()

    def __exit__(self, *exc) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None


def read_metadata(path: str | Path) -> dict:
    with Path(path).open("rb") as handle:
        if handle.readline() != MAGIC:
            raise CaptureError(f"{path} is not a pitcrew capture file")
        return json.loads(handle.readline().decode("utf-8"))


def read_datagrams(path: str | Path) -> Iterator[Datagram]:
    """Every datagram in the file, in order.

    A truncated final record is dropped silently — a capture is closed by the
    session ending, sometimes by the process dying, and half a datagram at the
    tail is expected rather than exceptional. A truncation anywhere *else*
    cannot be told from that, which is why `gaps` (below) exists: the analysis
    checks the timeline for holes rather than trusting the file to be whole.
    """
    with Path(path).open("rb") as handle:
        if handle.readline() != MAGIC:
            raise CaptureError(f"{path} is not a pitcrew capture file")
        handle.readline()                       # metadata
        while True:
            header = handle.read(_RECORD.size)
            if len(header) < _RECORD.size:
                return
            t_s, length = _RECORD.unpack(header)
            if length > MAX_DATAGRAM:
                raise CaptureError(
                    f"record claims {length} bytes; the file is corrupt")
            data = handle.read(length)
            if len(data) < length:
                return
            yield Datagram(t_s=t_s, data=data)
