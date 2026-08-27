"""The shift beep plays over the engineer, not instead of him.

Measured in the Fuji race (session 88, 24 Aug 2026): nine calls were cut
mid-sentence and re-spoken from the beginning, and the race-start call was
truncated and restarted four times inside six seconds -

    20:18:26 the audio devices were rebuilt mid-line and cut
             'Green, green, green. 20 laps.' off after 0.7s - saying it again.
    20:18:27 ... off after 1.6s - saying it again.
    20:18:29 ... off after 3.2s - saying it again.
    20:18:31 ... off after 5.6s - saying it again.

That was pre-emption working as designed: the beep raised a priority flag, the
voice closed its stream between chunks, and the whole line went back on the
queue. The driver's instruction, 25 Aug 2026: "shift beep should come in but
engineer resumes from where he was at or both sounds are played at the same
time beep is just louder than engineer."

Both sounds at once is the stronger of the two - there is nothing to resume
from if the line never stopped - and the card can carry it, because both are
int16 PCM and summing them is addition.
"""
from __future__ import annotations

import numpy as np
import pytest

from pitcrew.engineer import audio_devices, voice

RATE = 22_050
DEVICE = 0
BEEP_MS = 60


def a_beep(rate: int):
    """A full-scale tone, so the ducking and the gain are easy to read off."""
    return np.full(int(rate * BEEP_MS / 1000), 10_000, dtype=np.int16)


def a_line(seconds: float = 1.88):
    """The rendered pack's median clip, at a steady level."""
    return np.full(int(RATE * seconds), 8_000, dtype=np.int16)


# What `a_line` is by the time the mixer sees it. Every spoken line passes
# through `voice.LINE_GAIN` on its way to the card, so the level the duck
# applies to is this one and not the 8,000 the fixture writes. Read off the
# real function rather than restated, so re-tuning the gain re-tunes the test
# instead of breaking it.
LINE_LEVEL = int(voice._louder(a_line(0.01))[0])


class FakeStream:
    def __init__(self) -> None:
        self.chunks: list[np.ndarray] = []

    def write(self, samples) -> None:
        self.chunks.append(np.asarray(samples).copy())

    @property
    def played(self):
        return np.concatenate(self.chunks) if self.chunks else np.zeros(0)


class FakeLine:
    def __init__(self) -> None:
        self.interrupted = False


@pytest.fixture(autouse=True)
def clean_mailbox(monkeypatch):
    """Never let one test's undelivered beep reach the next one."""
    monkeypatch.setattr(audio_devices, "_MIX", {})
    monkeypatch.setattr(audio_devices, "_MIXERS", {})
    monkeypatch.setattr(voice.audio_devices, "output_device", lambda: DEVICE)
    monkeypatch.setattr(voice.audio_devices, "priority_wanted", lambda _d: False)


# ----------------------------------------------------------- the mailbox

def test_nobody_mixing_means_the_offer_is_refused():
    """So the beep knows to fall back to pre-empting, exactly as before."""
    assert audio_devices.offer_mix(DEVICE, a_beep) is False


def test_a_writer_that_declared_itself_takes_the_offer():
    with audio_devices.mixing_on(DEVICE):
        assert audio_devices.offer_mix(DEVICE, a_beep) is True
        assert len(audio_devices.take_mix(DEVICE)) == 1


def test_taking_drains_so_one_beep_sounds_once():
    with audio_devices.mixing_on(DEVICE):
        audio_devices.offer_mix(DEVICE, a_beep)
        assert len(audio_devices.take_mix(DEVICE)) == 1
        assert audio_devices.take_mix(DEVICE) == []


def test_a_beep_older_than_its_deadline_is_dropped_not_played_late(monkeypatch):
    """A beep played late names a shift point the engine has already passed."""
    clock = [1000.0]
    monkeypatch.setattr(audio_devices, "_mix_now", lambda: clock[0])
    with audio_devices.mixing_on(DEVICE):
        audio_devices.offer_mix(DEVICE, a_beep)
        clock[0] += audio_devices.MIX_STALE_AFTER_S + 0.01
        assert audio_devices.take_mix(DEVICE) == []


def test_a_beep_nobody_collected_does_not_outlive_its_writer():
    with audio_devices.mixing_on(DEVICE):
        audio_devices.offer_mix(DEVICE, a_beep)
    with audio_devices.mixing_on(DEVICE):
        assert audio_devices.take_mix(DEVICE) == [], (
            "a beep for an rpm two corners ago must not open the next line")


def test_nested_writers_keep_the_card_claimed_until_the_last_one_leaves():
    with audio_devices.mixing_on(DEVICE):
        with audio_devices.mixing_on(DEVICE):
            pass
        assert audio_devices.offer_mix(DEVICE, a_beep) is True


# ------------------------------------------------- mixing into the line

def test_a_beep_mid_line_does_not_cut_the_line():
    """The defect, stated as a test: the line used to stop and start again."""
    stream, line = FakeStream(), FakeLine()
    mixer = voice._Mixer(DEVICE)
    clip = a_line()

    with audio_devices.mixing_on(DEVICE):
        audio_devices.offer_mix(DEVICE, a_beep)
        cut = voice._write_yielding(stream, clip, RATE, line, mixer)

    assert cut is False, "the beep must not stop the sentence"
    assert line.interrupted is False, "nothing to re-speak means nothing cut"
    assert len(stream.played) == len(clip), "every sample of the line played"


def test_the_beep_is_audible_over_the_line_and_louder_than_it():
    stream, line = FakeStream(), FakeLine()
    mixer = voice._Mixer(DEVICE)

    with audio_devices.mixing_on(DEVICE):
        audio_devices.offer_mix(DEVICE, a_beep)
        voice._write_yielding(stream, a_line(), RATE, line, mixer)

    played = stream.played
    overlap = int(RATE * BEEP_MS / 1000)
    during, after = played[:overlap], played[overlap + 10:]

    assert during.max() > after.max(), "the beep has to rise above the line"
    # Once the tone ends the line comes straight back to its own level - the
    # duck lasts exactly as long as the beep does.
    assert after.max() == pytest.approx(LINE_LEVEL, abs=2)

    beep_alone = 10_000 * audio_devices.MIX_GAIN
    ducked_line = LINE_LEVEL * audio_devices.MIX_DUCK
    # Both are in there: the sum is above the beep on its own, so the engineer
    # is audible underneath rather than replaced by the tone.
    assert during.min() == pytest.approx(beep_alone + ducked_line, abs=2)
    assert during.min() > beep_alone
    # And the beep is the louder of the two, which is the driver's instruction.
    assert beep_alone > ducked_line


def test_a_beep_straddling_a_chunk_boundary_finishes_on_the_next_one():
    """A 60 ms beep does not fit a chunk boundary just because one arrives."""
    stream, line = FakeStream(), FakeLine()
    mixer = voice._Mixer(DEVICE)
    # One chunk long, so a 60 ms beep offered now must run past its end.
    short = int(RATE * voice._YIELD_CHUNK_S * 0.5)

    with audio_devices.mixing_on(DEVICE):
        audio_devices.offer_mix(DEVICE, a_beep)
        voice._write_yielding(stream, np.full(short, 8_000, dtype=np.int16),
                              RATE, line, mixer)
        assert mixer.active, "the tail of the beep is still owed"
        voice._write_yielding(stream, np.full(short, 8_000, dtype=np.int16),
                              RATE, line, mixer)

    # It ran continuously across the boundary rather than restarting.
    assert stream.played.max() > LINE_LEVEL


def test_a_line_with_no_beep_in_it_is_passed_through_untouched():
    """The common case must not pay for the arithmetic of the rare one.

    Untouched by the *mixer*, that is. The gain is not the rare case - it is
    on every line - so what comes out is the line at `LINE_GAIN` and nothing
    summed into it.
    """
    stream, line = FakeStream(), FakeLine()
    mixer = voice._Mixer(DEVICE)
    clip = a_line(0.5)

    with audio_devices.mixing_on(DEVICE):
        voice._write_yielding(stream, clip, RATE, line, mixer)

    assert np.array_equal(stream.played, voice._louder(clip))
    assert stream.chunks[0].dtype == np.int16


def test_a_beep_that_cannot_be_built_is_dropped_and_the_line_survives():
    stream, line = FakeStream(), FakeLine()
    mixer = voice._Mixer(DEVICE)

    def broken(_rate):
        raise ValueError("no numpy today")

    with audio_devices.mixing_on(DEVICE):
        audio_devices.offer_mix(DEVICE, broken)
        cut = voice._write_yielding(stream, a_line(0.5), RATE, line, mixer)

    assert cut is False
    assert line.interrupted is False
    assert len(stream.played) == len(a_line(0.5))


def test_the_beep_is_rebuilt_at_the_rate_the_writer_is_using():
    """Resampling a square wave is how you get the click it ramps to avoid."""
    asked: list[int] = []

    def recipe(rate: int):
        asked.append(rate)
        return a_beep(rate)

    for rate in (22_050, 48_000):
        mixer = voice._Mixer(DEVICE)
        with audio_devices.mixing_on(DEVICE):
            audio_devices.offer_mix(DEVICE, recipe)
            voice._write_yielding(FakeStream(),
                                  np.full(rate, 8_000, dtype=np.int16),
                                  rate, mixer.device and 0 or FakeLine(),
                                  mixer)

    assert asked == [22_050, 48_000]


def test_a_sounding_beep_is_not_cut_short_by_a_second_priority_claim(
        monkeypatch):
    """Standing aside mid-tone would clip the beep that is playing right now.

    Reachable with two beeps close together: the first is mixed, the second
    finds no free card and falls through to `priority_on`. Cutting the line
    then would also cut the tone still draining through it.
    """
    monkeypatch.setattr(voice.audio_devices, "priority_wanted", lambda _d: True)
    stream, line = FakeStream(), FakeLine()
    mixer = voice._Mixer(DEVICE)
    # Longer than one chunk, so it is genuinely still in flight at the first
    # boundary - a 60 ms tone inside a 100 ms chunk has already been written.
    long_tone = lambda rate: np.full(int(rate * voice._YIELD_CHUNK_S * 2.5),
                                     10_000, dtype=np.int16)

    with audio_devices.mixing_on(DEVICE):
        audio_devices.offer_mix(DEVICE, long_tone)
        voice._write_yielding(stream, a_line(0.5), RATE, line, mixer)

    # The line may still be pre-empted for the second beep - that is the
    # fallback doing its job. What must not happen is the tone being clipped
    # partway through: every sample of it reached the card first.
    assert not mixer.active, "the tone was still owed when the line stopped"
    assert len(stream.played) >= len(long_tone(RATE)), (
        "the line stopped before the tone it was carrying had finished")


def test_pre_emption_still_happens_when_there_is_no_mixer(monkeypatch):
    """The fallback is intact for anything that cannot be mixed."""
    monkeypatch.setattr(voice.audio_devices, "priority_wanted", lambda _d: True)
    stream, line = FakeStream(), FakeLine()

    cut = voice._write_yielding(stream, a_line(), RATE, line, None)

    assert cut is True
    assert line.interrupted is True
