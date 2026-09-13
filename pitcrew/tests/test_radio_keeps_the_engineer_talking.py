"""Pressing the radio must not cost the driver the line George is saying.

Suzuka, 13 Sep 2026 (session 166). George was two seconds into an uncovered
line when the driver pressed the radio:

    20:37:12,388 the audio devices were rebuilt mid-line and cut 'Tyres are up
                 to temperature. ...' off after 2.2s - saying it again.
    20:37:12,998 microphone open ...
    20:37:19,507 radio closed on the 6s cap - no second press
    20:37:19,925 the audio devices were rebuilt mid-line and cut 'Tyres are up
                 to temperature. ...' off. It is 9.8s old now, so it is
                 dropped rather than said late.

**No device was rebuilt.** There is no `pitcrew.audio` line anywhere near it,
and the rebuild path always writes one. The cut was the radio static: the
bursts are `_TonePlayer`s built from a fixed waveform, so they had no recipe to
hand to the mixer and fell through to `priority_on` - the shift beep's
pre-emption fallback, which asks the voice to stand aside. The opening burst
cut the line, the closing burst cut the re-speak, and by then the line was old
enough to be dropped. The log called both a device rebuild because every
`LineCut` was logged as one.

So the static now plays over the top of the line the way the shift beep does
(25 Aug, the driver: "both sounds are played at the same time"), and a line is
never cut to make room for it.
"""
from __future__ import annotations

import threading
import time

import numpy as np
import pytest

from pitcrew.engineer import audio_devices, radio, voice

RATE = 22_050
DEVICE = 0


class SlowStream:
    """Writes take a little real time, so a burst can arrive mid-line."""

    def __init__(self) -> None:
        self.chunks: list[np.ndarray] = []

    def write(self, samples) -> None:
        self.chunks.append(np.asarray(samples).copy())
        time.sleep(0.01)

    @property
    def played(self):
        return np.concatenate(self.chunks) if self.chunks else np.zeros(0)


class Line:
    def __init__(self) -> None:
        self.interrupted = False


class Opens:
    """Stands in for `open_output`, so a burst that plays itself is counted."""

    def __init__(self) -> None:
        self.streams: list = []

    def __call__(self, rate, **_kwargs):
        stream = _BurstStream()
        self.streams.append(stream)
        return stream


class _BurstStream:
    def __init__(self) -> None:
        self.written = 0

    def write(self, samples) -> None:
        self.written += len(samples)

    def stop(self) -> None:
        pass

    def close(self) -> None:
        pass


@pytest.fixture(autouse=True)
def one_card(monkeypatch):
    monkeypatch.setattr(audio_devices, "_MIX", {})
    monkeypatch.setattr(audio_devices, "_MIXERS", {})
    monkeypatch.setattr(audio_devices, "_PRIORITY", {})
    monkeypatch.setattr(audio_devices, "_OUTPUT", DEVICE)
    opens = Opens()
    monkeypatch.setattr(audio_devices, "open_output", opens)
    return opens


def _speak_in_background(seconds: float, *, started: threading.Event,
                         result: dict):
    """What `VoicePackEngine._play` does, minus the wav and the card."""

    def run() -> None:
        stream, line = SlowStream(), Line()
        clip = np.full(int(RATE * seconds), 8_000, dtype=np.int16)
        with audio_devices.lock_for(DEVICE), \
                audio_devices.mixing_on(DEVICE):
            started.set()
            cut = voice._write_yielding(stream, clip, RATE, line,
                                        voice._Mixer(DEVICE))
        result.update(cut=cut, line=line, stream=stream, clip=clip)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


@pytest.mark.parametrize("which", [0, 1], ids=["opening", "closing"])
def test_the_static_does_not_cut_a_line_in_progress(one_card, which):
    """The defect, stated as a test. Both bursts, because in the race the
    opening one cut the line and the closing one cut the re-speak."""
    burst = radio.bursts(rate=44_100)[which]
    started, result = threading.Event(), {}
    thread = _speak_in_background(1.5, started=started, result=result)
    assert started.wait(2.0)
    time.sleep(0.05)

    burst.play_blocking()
    thread.join(5.0)

    assert result["cut"] is False, "the static stopped the sentence"
    assert result["line"].interrupted is False, (
        "a line marked cut is re-spoken from the start, and in the race the "
        "second attempt was dropped")
    assert len(result["stream"].played) == len(result["clip"]), (
        "every sample of the line reached the card")
    assert one_card.streams == [], (
        "the static opened its own stream over a line that could carry it")
    line_level = int(voice._louder(result["clip"][:10])[0])
    assert np.abs(result["stream"].played).max() > line_level, (
        "the static was never heard")


def test_the_static_never_raises_a_priority_claim(one_card, monkeypatch):
    """`priority_on` is the thing that cuts a line. The radio has no business
    asking for it: nothing it plays is more urgent than what George says."""
    claims: list = []
    real = audio_devices.priority_on

    def watched(device):
        claims.append(device)
        return real(device)

    monkeypatch.setattr(audio_devices, "priority_on", watched)
    started, result = threading.Event(), {}
    thread = _speak_in_background(0.8, started=started, result=result)
    assert started.wait(2.0)
    time.sleep(0.05)
    radio.bursts()[0].play_blocking()
    thread.join(5.0)
    assert claims == []


def test_with_the_card_free_the_static_plays_on_its_own_stream(one_card):
    """The common case is unchanged: no line, so the burst opens and plays."""
    burst = radio.bursts(rate=44_100)[0]
    burst.play_blocking()
    assert len(one_card.streams) == 1
    assert one_card.streams[0].written > 0


def test_a_burst_the_line_ended_before_collecting_still_plays(one_card):
    """The mailbox is emptied when its writer leaves. A burst offered in the
    last moments of a line would be dropped there - and a dropped opening
    burst is a driver who does not know the radio is open. So it plays on its
    own once the card is free, exactly once."""
    burst = radio.bursts(rate=44_100)[0]
    lock = audio_devices.lock_for(DEVICE)
    holding, release = threading.Event(), threading.Event()

    def a_line_that_ends_without_writing() -> None:
        with lock, audio_devices.mixing_on(DEVICE):
            holding.set()
            release.wait(2.0)

    thread = threading.Thread(target=a_line_that_ends_without_writing,
                              daemon=True)
    thread.start()
    assert holding.wait(2.0)
    threading.Timer(0.1, release.set).start()

    burst.play_blocking()
    thread.join(2.0)

    assert len(one_card.streams) == 1, "the burst was lost with the line"


class _NeverCollects:
    """A line holding the card that does not drain the mailbox - George still
    synthesising a pack miss live, which was every line at Suzuka."""

    def __init__(self, seconds: float = 3.0) -> None:
        self._release = threading.Event()
        self._holding = threading.Event()
        self._seconds = seconds
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        with audio_devices.lock_for(DEVICE), audio_devices.mixing_on(DEVICE):
            self._holding.set()
            self._release.wait(self._seconds)

    def __enter__(self):
        self._thread.start()
        assert self._holding.wait(2.0)
        return self

    def __exit__(self, *_exc):
        self._release.set()
        self._thread.join(2.0)
        return False


class _TimedRecogniser:
    name = "moonshine"
    last_reason = None

    def __init__(self) -> None:
        self.opened_at = None

    def begin(self) -> None:
        self.opened_at = time.monotonic()

    def end(self) -> str:
        return "laps left"


def _radio():
    from pitcrew.engineer.ptt import PushToTalk

    recogniser = _TimedRecogniser()
    answered: list[float] = []
    talk = PushToTalk(snapshot=lambda: {"lapsRemaining": 12},
                      speak=lambda _text: answered.append(time.monotonic()),
                      recogniser=recogniser, bursts=radio.bursts())
    return talk, recogniser, answered


def test_a_busy_card_does_not_hold_the_microphone_shut(one_card, caplog):
    """Review of 8b0deb2: waiting for a line that never collects the static
    opened the microphone up to ten seconds after the press, and the start
    of his question went nowhere. The static is skipped instead."""
    talk, recogniser, _ = _radio()
    with _NeverCollects(), caplog.at_level("INFO", logger="pitcrew.beep"):
        pressed = time.monotonic()
        talk._open_radio()
        talk._cancel_deadline()
    assert recogniser.opened_at is not None
    assert recogniser.opened_at - pressed < 0.6, (
        f"the mic opened {recogniser.opened_at - pressed:.2f}s after the press")
    assert one_card.streams == [], "the static cut in or waited for the card"
    assert "static skipped" in caplog.text


def test_a_busy_card_does_not_hold_the_answer(one_card):
    talk, _, answered = _radio()
    talk._recording = True
    with _NeverCollects():
        closed = time.monotonic()
        talk._close_radio()
    assert answered, "no answer was given"
    assert answered[0] - closed < 0.6, (
        f"the answer came {answered[0] - closed:.2f}s after the close")


def test_an_offer_withdrawn_on_timeout_is_not_played_later():
    """A burst that gave up waiting and played itself must not also turn up
    in the next chunk of the line - that is the static twice."""
    with audio_devices.mixing_on(DEVICE):
        taken = audio_devices.mix_and_wait(
            DEVICE, lambda rate: np.zeros(10, dtype=np.int16),
            stale_after_s=5.0, wait_s=0.05)
        assert taken is False
        assert audio_devices.take_mix(DEVICE) == []


def test_mix_and_wait_reports_a_collected_offer():
    collected = threading.Event()

    def writer() -> None:
        for _ in range(100):
            if audio_devices.take_mix(DEVICE):
                collected.set()
                return
            time.sleep(0.01)

    with audio_devices.mixing_on(DEVICE):
        thread = threading.Thread(target=writer, daemon=True)
        thread.start()
        taken = audio_devices.mix_and_wait(
            DEVICE, lambda rate: np.zeros(10, dtype=np.int16),
            stale_after_s=5.0, wait_s=2.0)
        thread.join(2.0)
    assert taken is True
    assert collected.is_set()


def test_the_bursts_render_the_same_sound_at_the_writers_rate():
    """The mixer rebuilds a sound at whatever rate the line is playing, so
    the burst carries a recipe - and the recipe has to be the burst, not a
    different noise every time."""
    opening = radio.bursts(rate=44_100)[0]
    assert opening._recipe is not None
    at_pack_rate = opening._recipe(RATE)
    assert at_pack_rate.dtype == np.int16
    assert len(at_pack_rate) == int(RATE * radio.BURST_MS / 1000)
    assert np.array_equal(at_pack_rate, opening._recipe(RATE))


# ------------------------------------------------------ what the log says

def test_a_line_that_stood_aside_does_not_claim_a_device_rebuild(
        monkeypatch):
    """The race log said "the audio devices were rebuilt" twice, about a cut
    that had nothing to do with the device list - which sent the diagnosis
    to the wrong module. The cut says what cut it."""
    monkeypatch.setattr(voice.audio_devices, "output_device", lambda: DEVICE)
    monkeypatch.setattr(voice.audio_devices, "priority_wanted",
                        lambda _d: True)
    line = Line()
    assert voice._yield_to_priority(line) is True
    reason = voice.cut_reason(line)
    assert "rebuilt" not in reason
    assert "shift beep" in reason or "urgent" in reason


def test_a_rebuild_cut_still_says_it_was_a_rebuild():
    playback = audio_devices.Playback("the engineer's line")
    playback.interrupted = True
    assert "rebuilt" in voice.cut_reason(playback)


def test_the_voice_logs_the_reason_it_was_given(caplog):
    class Engine:
        name = "fake"

        def __init__(self) -> None:
            self.calls = 0

        def speak(self, text: str) -> None:
            self.calls += 1
            if self.calls == 1:
                raise voice.LineCut("a more urgent sound took the card")

    engine = Engine()
    speaker = voice.Voice(engine=engine)
    try:
        with caplog.at_level("INFO", logger="pitcrew.voice"):
            speaker.say("Box this lap.")
            deadline = time.monotonic() + 2.0
            while engine.calls < 2 and time.monotonic() < deadline:
                time.sleep(0.01)
    finally:
        speaker.stop()
    assert engine.calls == 2, "the cut line was not said again"
    assert "a more urgent sound took the card" in caplog.text
    assert "rebuilt" not in caplog.text
