"""The last word of a press, which the recogniser used to eat.

A streaming recogniser decides a word is finished when it hears what follows
it, and after the last word nothing follows. The button is a tap - press,
static, listen, static - and the second tap closes the microphone, so the final
pass runs on audio that stops mid-syllable.
Measured over thirty trials through `tools/stt_bench.py`, that single failure
accounted for most of every model's error - "box this lap" came back as "box
this side", "the rear is loose on entry" as "the rear is loose on", "when am I
boxing" as "when am I" - and feeding six tenths of a second of silence before
the final pass took the tiny model from five exact transcripts in thirty to
nineteen, and its median word error rate from 25% to zero.

**It is worth a test because the symptom is invisible.** A transcript one word
short still reads like a sentence, still reaches the matcher, and still gets
answered - just answered as if he had asked something else. Nothing in a log
distinguishes it from him having said the shorter thing.
"""
from __future__ import annotations

import pytest

from pitcrew.engineer import ptt


class FakeTranscriber:
    """Records the shape of what it was fed, not the audio itself."""

    def __init__(self):
        self.fed = []
        self.finalised_after = None
        self.stopped = False

    def start(self):
        pass

    def add_audio(self, samples, rate):
        self.fed.append(list(samples))

    def update_transcription(self):
        self.finalised_after = sum(len(block) for block in self.fed)

        class Line:
            text = "box this lap"

        class Transcript:
            lines = [Line()]

        return Transcript()

    def stop(self):
        self.stopped = True


def _recogniser():
    """A `MoonshineRecogniser` without the model, the mic or the imports."""
    rec = ptt.MoonshineRecogniser.__new__(ptt.MoonshineRecogniser)
    rec._transcriber = FakeTranscriber()
    rec.SAMPLE_RATE = ptt.MoonshineRecogniser.SAMPLE_RATE
    rec.BLOCK = ptt.MoonshineRecogniser.BLOCK
    rec.TAIL_PAD_S = ptt.MoonshineRecogniser.TAIL_PAD_S
    return rec


def test_silence_reaches_the_decoder_before_the_final_pass():
    rec = _recogniser()
    rec._feed_tail_silence()
    fed = [s for block in rec._transcriber.fed for s in block]
    assert fed, "nothing was fed - the last word has no context to finish on"
    assert all(s == 0.0 for s in fed), "the pad must be silence, not audio"
    wanted = int(ptt.MoonshineRecogniser.SAMPLE_RATE
                 * ptt.MoonshineRecogniser.TAIL_PAD_S)
    assert len(fed) == wanted


def test_the_pad_is_long_enough_to_be_the_measured_one():
    """Six tenths, because three tenths was measured and was not enough.

    At 300 ms the small model gained but the tiny model did not move at all;
    at 600 ms both did. A shorter pad here would silently be a different
    change from the one the benchmark justified.
    """
    assert ptt.MoonshineRecogniser.TAIL_PAD_S >= 0.6


def test_a_failure_to_pad_never_costs_the_question():
    """Better a transcript one word short than no transcript at all."""
    rec = _recogniser()

    class Refuses(FakeTranscriber):
        def add_audio(self, samples, rate):
            raise RuntimeError("stream closed")

    rec._transcriber = Refuses()
    rec._feed_tail_silence()          # must not raise
    assert rec._transcriber.update_transcription().lines[0].text


def test_the_app_asks_for_a_model_it_measured():
    """Tiny, now on evidence rather than because it was the smallest of six.

    With the tail padded the three streaming models are level on accuracy over
    thirty trials - 19, 18 and 21 exact transcripts - and separated only by
    what he waits: ~300 ms, ~770 ms, ~1240 ms. A future change to a larger one
    needs a measurement showing accuracy that padding does not already give,
    because the first attempt at this change rested on ten samples and did not
    survive being repeated.
    """
    pytest.importorskip("moonshine_voice")
    import inspect

    source = inspect.getsource(ptt.MoonshineRecogniser.__init__)
    assert "TINY_STREAMING" in source
