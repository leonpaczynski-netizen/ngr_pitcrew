"""The voice has to let the shift beep through, and it did not.

Measured on the rendered pack: every clip is longer than the beep's 0.4 s
deadline and the median is 1.88 s. Both writers handed PortAudio a whole clip
in one blocking `write`, so `_yield_to_priority` - documented since it was
written as being checked "between written chunks" - could only fire between
whole sentences. The beep lost the race roughly four times in five, and the
driver's log carries seven drops in one evening:

    beep failed: TimeoutError: the card was still busy 0.4s after the beep
                 asked for it - dropped rather than played at the wrong rpm
"""
from __future__ import annotations

import numpy as np
import pytest

from pitcrew.engineer import voice
from pitcrew.engineer.shift_beep import PRIORITY_WAIT_S

RATE = 22_050
# The pack's median clip. The whole point is that this is far longer than the
# beep is willing to wait.
MEDIAN_CLIP_S = 1.88


class FakeStream:
    """Records what it was handed, and how long each write would have taken."""

    def __init__(self) -> None:
        self.writes: list[int] = []

    def write(self, samples) -> None:
        self.writes.append(len(samples))

    @property
    def longest_block_s(self) -> float:
        return max(self.writes) / RATE if self.writes else 0.0


class FakeLine:
    def __init__(self) -> None:
        self.interrupted = False


def a_clip(seconds: float = MEDIAN_CLIP_S):
    return np.zeros(int(RATE * seconds), dtype=np.int16)


@pytest.fixture()
def no_priority(monkeypatch):
    monkeypatch.setattr(voice.audio_devices, "output_device", lambda: 0)
    monkeypatch.setattr(voice.audio_devices, "priority_wanted", lambda _d: False)


def test_a_clip_is_written_in_chunks_not_in_one_block(no_priority):
    stream, line = FakeStream(), FakeLine()

    cut = voice._write_yielding(stream, a_clip(), RATE, line)

    assert cut is False
    assert len(stream.writes) > 1, "one write per clip is the whole defect"
    assert sum(stream.writes) == len(a_clip()), "every sample still played"


def test_the_beep_deadline_is_met_with_room_to_spare(no_priority):
    """The measurement that matters: how long the beep can be made to wait."""
    stream, line = FakeStream(), FakeLine()

    voice._write_yielding(stream, a_clip(), RATE, line)

    assert stream.longest_block_s < PRIORITY_WAIT_S, (
        f"a write of {stream.longest_block_s:.2f}s cannot let a beep in "
        f"inside its {PRIORITY_WAIT_S}s deadline")
    # Four chances inside the deadline rather than one at the end of a
    # sentence.
    assert PRIORITY_WAIT_S / stream.longest_block_s >= 3


def test_a_waiting_beep_stops_the_line_partway_through(monkeypatch):
    monkeypatch.setattr(voice.audio_devices, "output_device", lambda: 0)
    monkeypatch.setattr(voice.audio_devices, "priority_wanted", lambda _d: True)
    stream, line = FakeStream(), FakeLine()

    cut = voice._write_yielding(stream, a_clip(), RATE, line)

    assert cut is True
    assert line.interrupted is True, "cutting the line is a deferral, not a loss"
    assert sum(stream.writes) < len(a_clip()), "it stopped early"
    # And it stopped at the FIRST opportunity, not at the end of the clip.
    assert len(stream.writes) == 1


def test_a_clip_shorter_than_one_chunk_still_plays(no_priority):
    stream, line = FakeStream(), FakeLine()
    short = np.zeros(200, dtype=np.int16)

    assert voice._write_yielding(stream, short, RATE, line) is False
    assert stream.writes == [200]


def test_an_empty_clip_writes_nothing_and_does_not_hang(no_priority):
    stream, line = FakeStream(), FakeLine()

    assert voice._write_yielding(stream, np.zeros(0, dtype=np.int16),
                                 RATE, line) is False
    assert stream.writes == []


def test_the_chunk_is_derived_from_the_rate_not_a_frame_count(no_priority):
    """A 48 kHz clip must yield as often in TIME as a 22 kHz one."""
    at_22k, at_48k = FakeStream(), FakeStream()

    voice._write_yielding(at_22k, np.zeros(RATE, dtype=np.int16), RATE,
                          FakeLine())
    voice._write_yielding(at_48k, np.zeros(48_000, dtype=np.int16), 48_000,
                          FakeLine())

    assert len(at_22k.writes) == len(at_48k.writes)
    assert at_22k.longest_block_s == pytest.approx(
        max(at_48k.writes) / 48_000, abs=0.01)
