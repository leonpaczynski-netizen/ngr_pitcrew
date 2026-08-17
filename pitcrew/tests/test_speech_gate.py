"""The staged confidence gate, at every band.

The closed SAPI grammar could not return a phrase that was not in it. Free
dictation can return anything, so this is what stands between a hallucinated
sentence and an answer the driver acts on. `intents.py` states the rule these
enforce: an engineer who confidently mis-hears is worse than one who says "say
again" - and its converse, that a driver with his hands full can say "yes" in
a second where repeating a question costs him a corner.

Every stage is a pure function of numbers or strings, so all of it runs with
no microphone, no model and no audio device.
"""
from __future__ import annotations

import threading
import time

import pytest

from pitcrew.engineer import audio_devices
from pitcrew.engineer import gate
from pitcrew.engineer import ptt
from pitcrew.engineer.intents import BOX_WHEN, FUEL, UNKNOWN
from pitcrew.engineer.ptt import PushToTalk

MAX_CAPTURE = 6.0


# ------------------------------------------- stage 0: did the device deliver

def test_a_capture_of_nothing_at_all_is_the_device_not_the_driver():
    """Measured on this machine: the default input is a Bluetooth earbud that
    is not connected. `InputStream` opens without error and delivers zero
    callbacks over six consecutive three-second holds, where the built-in
    array delivers 19-75. Reported as "no speech in the capture", it told the
    driver to speak up at a microphone that was not there."""
    assert gate.check_audio(duration_s=0.0, speech_s=0.0,
                            max_capture_s=MAX_CAPTURE) == gate.NO_INPUT


def test_a_quiet_capture_is_still_a_quiet_capture():
    """Stage 0 must not swallow stage 1: some audio arrived, he just did not
    speak into it."""
    assert gate.check_audio(duration_s=2.0, speech_s=0.0,
                            max_capture_s=MAX_CAPTURE) == gate.NO_SPEECH


# --------------------------------------------------- stage 1: was there speech

def test_silence_is_rejected_before_anything_is_transcribed():
    """The dangerous one. A recogniser given silence does not return silence -
    it returns a plausible sentence."""
    assert gate.check_audio(duration_s=2.0, speech_s=0.0,
                            max_capture_s=MAX_CAPTURE) == gate.NO_SPEECH


def test_a_brushed_button_is_rejected():
    assert gate.check_audio(duration_s=1.5, speech_s=0.10,
                            max_capture_s=MAX_CAPTURE) == gate.NO_SPEECH


def test_speech_is_checked_before_length():
    """Two seconds of engine noise passes a duration test and is exactly the
    input that produces a confident hallucination."""
    assert gate.check_audio(duration_s=0.1, speech_s=0.0,
                            max_capture_s=MAX_CAPTURE) == gate.NO_SPEECH


# ------------------------------------------------------ stage 2: was it sane

def test_too_short_to_be_a_question_is_rejected():
    assert gate.check_audio(duration_s=0.35, speech_s=0.35,
                            max_capture_s=MAX_CAPTURE) == gate.TOO_SHORT


def test_longer_than_the_capture_limit_is_rejected():
    assert gate.check_audio(duration_s=7.0, speech_s=6.5,
                            max_capture_s=MAX_CAPTURE) == gate.TOO_LONG


def test_a_normal_question_passes():
    assert gate.check_audio(duration_s=1.5, speech_s=1.2,
                            max_capture_s=MAX_CAPTURE) is None


# ------------------------------------------- stages 3 and 4: what came back

def test_an_empty_transcript_is_a_rejection_not_an_intent():
    assert gate.check_transcript("", duration_s=1.5) == gate.NOTHING_HEARD
    assert gate.check_transcript("   ", duration_s=1.5) == gate.NOTHING_HEARD


def test_a_repeat_loop_is_caught_by_words_per_second():
    """A decoder that loses its place emits the same token forever. Nobody
    speaks at nine words a second."""
    runaway = " ".join(["box"] * 20)
    assert gate.check_transcript(runaway, duration_s=2.0) == gate.REPEAT_LOOP


def test_normal_speech_is_not_mistaken_for_a_repeat_loop():
    assert gate.check_transcript("how much fuel do i take",
                                 duration_s=2.0) is None


# ------------------------------------------------- stage 5: did it mean this

def test_a_close_match_is_acted_on():
    verdict = gate.judge("when do i box", intent=BOX_WHEN, distance=0.10)
    assert verdict.action == gate.ACT
    assert verdict.intent == BOX_WHEN


def test_an_ambiguous_match_is_confirmed_rather_than_rejected():
    """One syllable from him beats a whole repeated question."""
    verdict = gate.judge("when box thing", intent=BOX_WHEN, distance=0.36)
    assert verdict.action == gate.CONFIRM
    assert verdict.intent == BOX_WHEN


def test_nonsense_is_rejected():
    verdict = gate.judge("the fridge is making a noise", intent=BOX_WHEN,
                         distance=0.45)
    assert verdict.action == gate.REJECT
    assert verdict.intent == UNKNOWN
    assert verdict.reason == gate.NOT_UNDERSTOOD


def test_an_unmatched_intent_is_rejected_whatever_the_distance():
    verdict = gate.judge("blah", intent=UNKNOWN, distance=0.01)
    assert verdict.action == gate.REJECT


def test_no_semantic_model_falls_back_to_the_literal_match():
    """Which is exact by construction - the closed-grammar behaviour, and
    never the unsafe part."""
    verdict = gate.judge("when do i box", intent=BOX_WHEN, distance=None)
    assert verdict.action == gate.ACT


@pytest.mark.parametrize("sensitivity,distance,expected", [
    ("low", 0.20, gate.ACT),
    ("low", 0.30, gate.CONFIRM),
    ("low", 0.40, gate.REJECT),
    ("medium", 0.25, gate.ACT),
    ("medium", 0.36, gate.CONFIRM),
    ("medium", 0.50, gate.REJECT),
    ("high", 0.35, gate.ACT),
    ("high", 0.45, gate.CONFIRM),
    ("high", 0.60, gate.REJECT),
])
def test_sensitivity_moves_the_bands(sensitivity, distance, expected):
    verdict = gate.judge("x", intent=FUEL, distance=distance,
                         sensitivity=sensitivity)
    assert verdict.action == expected


def test_an_unknown_sensitivity_falls_back_to_the_default():
    assert gate.bands("nonsense") == gate.bands(gate.DEFAULT_SENSITIVITY)


def test_low_sensitivity_acts_less_readily_than_high():
    """The named settings have to mean what they say."""
    low_act, low_confirm = gate.bands("low")
    high_act, high_confirm = gate.bands("high")
    assert low_act < high_act
    assert low_confirm < high_confirm


# ------------------------------------------------ the gate, through the seam

class Matcher:
    def __init__(self, intent, distance):
        self._result = (intent, distance)

    def match(self, _heard):
        return self._result


def talker(matcher=None, snapshot=None, **kwargs):
    said = []
    ptt = PushToTalk(snapshot=lambda: snapshot or {"lapsToStop": 3},
                     speak=said.append, matcher=matcher, **kwargs)
    return ptt, said


def test_a_confident_question_is_answered():
    ptt, said = talker(Matcher(BOX_WHEN, 0.10))
    assert ptt.ask("when do i box") == "Box in 3 laps."
    assert said == ["Box in 3 laps."]
    assert ptt.pending_confirmation is None


def test_an_ambiguous_question_asks_one_word_back():
    ptt, said = talker(Matcher(BOX_WHEN, 0.36))
    reply = ptt.ask("when box thing")
    assert reply == "Did you mean box when?"
    assert said == ["Did you mean box when?"]
    assert ptt.pending_confirmation == BOX_WHEN


def test_yes_to_a_confirmation_answers_the_question():
    ptt, said = talker(Matcher(BOX_WHEN, 0.36))
    ptt.ask("when box thing")
    assert ptt.ask("yes") == "Box in 3 laps."
    assert ptt.pending_confirmation is None


def test_no_to_a_confirmation_says_again():
    ptt, said = talker(Matcher(BOX_WHEN, 0.36))
    ptt.ask("when box thing")
    assert ptt.ask("no") == "Say again."
    assert ptt.pending_confirmation is None


def test_a_different_question_during_a_confirmation_is_answered_on_its_merits():
    """He ignored the question and asked something else. That is not a no."""
    ptt, said = talker(Matcher(BOX_WHEN, 0.36),
                       snapshot={"lapsToStop": 3, "position": 4})
    ptt.ask("when box thing")
    ptt._matcher = Matcher("position", 0.08)
    assert ptt.ask("what position am i") == "P4."
    assert ptt.pending_confirmation is None


def test_nonsense_says_again_rather_than_guessing():
    ptt, said = talker(Matcher(BOX_WHEN, 0.55))
    assert ptt.ask("the fridge is making a noise") == "Say again."


def test_a_rejected_capture_reaches_the_same_say_again():
    """The recogniser returns "" on a gate rejection, and that path already
    existed - it is the UNKNOWN branch."""
    ptt, said = talker(Matcher(UNKNOWN, None))
    assert ptt.ask("") == "Say again."


def test_a_matcher_that_throws_does_not_cost_the_answer():
    class Broken:
        def match(self, _heard):
            raise RuntimeError("model gone")

    ptt, said = talker(Broken())
    # Falls through to literal matching, which knows this phrase.
    assert ptt.ask("when do i box") == "Box in 3 laps."


def test_with_no_matcher_at_all_the_literal_path_still_works():
    ptt, said = talker(None)
    assert ptt.ask("how much fuel") == "I don't have a fuel rate yet."


def test_sensitivity_reaches_the_seam():
    ptt, _ = talker(Matcher(BOX_WHEN, 0.33), sensitivity="high")
    assert ptt.ask("when box") == "Box in 3 laps."       # acts at high
    ptt.pending_confirmation = None
    ptt._sensitivity = "low"
    assert ptt.ask("when box") == "Did you mean box when?"


def test_the_verdict_is_kept_for_the_log():
    ptt, _ = talker(Matcher(FUEL, 0.12))
    ptt.ask("how much fuel")
    assert ptt.last_verdict.intent == FUEL
    assert ptt.last_verdict.distance == 0.12


# ------------------------------------------- the reasons reach the driver
#
# All five were computed, stored in `last_reason` and read nowhere: every one
# of them spoke "Say again." `gate.py`'s own rationale is that a driver told
# "I didn't hear you" learns to press the button properly while one told
# nothing learns the app is unreliable - and he is in a headset, so the log
# these were written to is a channel he does not have.

def test_every_rejection_reason_has_its_own_words():
    spoken = [gate.spoken_reason(reason) for reason in gate.ALL_REASONS]
    assert all(spoken)
    # The two that matter most are the two that used to be indistinguishable
    # from each other and from a driver who simply said nothing.
    assert (gate.spoken_reason(gate.NO_INPUT)
            != gate.spoken_reason(gate.NO_SPEECH))
    assert "microphone" in gate.spoken_reason(gate.NO_INPUT)
    assert "microphone" in gate.spoken_reason(gate.NO_DEVICE)


def test_an_unnamed_reason_still_says_something_honest():
    assert gate.spoken_reason(None) == gate.SPOKEN[gate.NOT_UNDERSTOOD]
    assert gate.spoken_reason("something new") == gate.SPOKEN[
        gate.NOT_UNDERSTOOD]


class Recogniser:
    """A recogniser that returns what it is told to, and why."""

    name = "fake"

    def __init__(self, heard="", reason=None, on_begin=None):
        self.heard = heard
        self.last_reason = reason
        self.began = 0
        self._on_begin = on_begin

    def begin(self):
        self.began += 1
        if self._on_begin is not None:
            self._on_begin()

    def end(self):
        return self.heard


def test_a_dead_microphone_is_said_in_its_own_words():
    said = []
    talk = PushToTalk(snapshot=dict, speak=said.append,
                      recogniser=Recogniser(reason=gate.NO_INPUT))
    talk.end()
    assert said == [gate.spoken_reason(gate.NO_INPUT)]
    assert talk.last_reason == gate.NO_INPUT
    assert "Say again." not in said


@pytest.mark.parametrize("reason", [
    gate.NO_SPEECH, gate.TOO_SHORT, gate.TOO_LONG, gate.NOTHING_HEARD,
    gate.REPEAT_LOOP,
])
def test_each_gate_reason_reaches_him_as_itself(reason):
    said = []
    talk = PushToTalk(snapshot=dict, speak=said.append,
                      recogniser=Recogniser(reason=reason))
    talk.end()
    assert said == [gate.spoken_reason(reason)]


def test_a_real_question_still_takes_the_normal_path():
    said = []
    talk = PushToTalk(snapshot=lambda: {"lapsToStop": 3, "hasPlan": True},
                      speak=said.append,
                      recogniser=Recogniser(heard="when do i box"))
    talk.end()
    assert said == ["Box in 3 laps."]


# ------------------------------------------- the hook thread's outermost frame
#
# pynput turns an escaping exception into a permanently stopped listener,
# re-raised only from `join()`, which nothing calls. So the button goes dead
# for the rest of the race and `has_listener` goes on reporting it loaded.

def test_a_microphone_that_will_not_open_does_not_kill_the_button():
    def explode():
        raise OSError("PortAudioError: device unavailable")

    said = []
    talk = PushToTalk(snapshot=dict, speak=said.append,
                      recogniser=Recogniser(on_begin=explode))
    talk.begin()                    # must not raise
    talk.end()
    assert said == [gate.spoken_reason(gate.NO_DEVICE)]


def test_a_failure_anywhere_in_the_answer_is_caught_and_said():
    class Exploding:
        name = "fake"

        def begin(self):
            pass

        def end(self):
            raise RuntimeError("the transcriber died")

    said = []
    talk = PushToTalk(snapshot=dict, speak=said.append,
                      recogniser=Exploding())
    talk.begin()
    talk.end()                      # must not raise
    assert said == [gate.spoken_reason(gate.FAILED)]


def test_the_lock_is_released_even_when_the_recogniser_raises():
    """Or the button answers exactly once for the rest of the race."""
    class Exploding:
        name = "fake"

        def __init__(self):
            self.calls = 0

        def begin(self):
            pass

        def end(self):
            self.calls += 1
            raise RuntimeError("boom")

    engine = Exploding()
    talk = PushToTalk(snapshot=dict, speak=lambda _t: None,
                      recogniser=engine)
    talk.begin(); talk.end()
    talk.begin(); talk.end()
    assert engine.calls == 2


# ------------------------------------------------------------ rebinding the key

class Hook:
    def __init__(self):
        self.running = False

    def start(self, _press, _release):
        self.running = True

    def stop(self):
        self.running = False


def test_rebinding_the_key_mid_session_leaves_the_button_working():
    """`set_listener` stopped the old hook and never started the new one, so
    rebinding during a live session killed the button on both keys while
    `has_listener` - which only tests `is not None` - went on saying the hook
    was loaded."""
    old, new = Hook(), Hook()
    talk = PushToTalk(snapshot=dict, speak=lambda _t: None, listener=old)
    talk.start()
    assert old.running is True

    talk.set_listener(new)
    assert old.running is False
    assert new.running is True
    assert talk.listening is True


def test_rebinding_before_the_session_does_not_start_listening_early():
    """The common order is rebind-then-start, and that must stay a no-op."""
    old, new = Hook(), Hook()
    talk = PushToTalk(snapshot=dict, speak=lambda _t: None, listener=old)
    talk.set_listener(new)
    assert new.running is False
    assert talk.listening is False
    talk.start()
    assert new.running is True


def test_stopping_is_reported_as_not_listening():
    hook = Hook()
    talk = PushToTalk(snapshot=dict, speak=lambda _t: None, listener=hook)
    talk.start()
    talk.stop()
    assert talk.listening is False
    assert talk.has_listener is True         # it exists; it is not running


# ------------------------------------------------ the gate is wired to the
# recogniser that was built, not the one that was configured

def test_the_matcher_follows_the_recogniser_not_the_setting(monkeypatch):
    """SAPI is the shipped default and it times out on this machine, so the
    app runs Moonshine free dictation. Choosing the matcher from the SETTING
    then leaves `matcher=None`, and `gate.judge` short-circuits on
    `distance is None` straight to ACT - past all five stages."""
    built = object()
    monkeypatch.setattr(ptt, "best_semantic_matcher", lambda: built)

    class Free:
        name = ptt.MoonshineRecogniser.name

    class Closed:
        name = ptt.SapiGrammarRecogniser.name

    assert ptt.matcher_for(Free()) is built
    assert ptt.matcher_for(Closed()) is None
    assert ptt.matcher_for(None) is None


def test_an_unrecognised_recogniser_gets_the_gate(monkeypatch):
    """The list is of the exceptions - closed grammars - so anything added
    later is gated rather than silently trusted."""
    built = object()
    monkeypatch.setattr(ptt, "best_semantic_matcher", lambda: built)

    class Future:
        name = "something-new"

    assert ptt.matcher_for(Future()) is built


# ------------------------------------------------------------ the capture cap

def test_the_capture_limit_is_a_cap_and_not_a_verdict():
    """MAX_CAPTURE_S was documented as "how long he can hold the button before
    we stop listening anyway" and nothing truncated anything: the limit was
    applied afterwards, in `check_audio`, which returned TOO_LONG and threw
    away the ENTIRE transcript rather than its tail."""
    blocks = ptt.MoonshineRecogniser.SAMPLE_RATE / ptt.MoonshineRecogniser.BLOCK
    recogniser = ptt.MoonshineRecogniser.__new__(ptt.MoonshineRecogniser)
    recogniser._max_capture_s = 6.0
    assert recogniser._max_blocks == int(6.0 * blocks)


# ------------------------------------------------- a machine with no speech

def test_no_recogniser_still_constructs_and_runs():
    """A machine without a microphone must still run the app."""
    said = []
    ptt = PushToTalk(snapshot=dict, speak=said.append, recogniser=None,
                     listener=None)
    ptt.start()          # must not raise
    ptt.end()
    ptt.stop()
    assert said == ["Speech isn't available on this machine."]


def test_the_bands_sit_inside_the_measured_gap():
    """The calibration is the safety property, so it is asserted, not trusted.

    Measured against embeddinggemma-300m q4 and the real phrase list: genuine
    questions land at 0.028-0.244, unrelated speech at 0.416-0.473. Every
    band has to keep those two apart, or a sentence about the fridge gets
    answered as a fuel question.
    """
    real_worst, junk_best = 0.244, 0.416

    # low and medium refuse unrelated speech outright.
    for name in ("low", "medium"):
        assert gate.bands(name)[1] < junk_best, (
            f"{name} would confirm unrelated speech instead of refusing it")

    # `high` is allowed to ask about unrelated speech - that is what "acts
    # readily" costs, and one syllable is the price. It must never *act* on it.
    assert gate.bands("high")[0] < junk_best, (
        "high would answer a sentence about the fridge as a fuel question")

    # At medium, every real question measured acts outright rather than
    # asking - the whole point of putting the band inside the gap.
    assert gate.bands("medium")[0] > real_worst - 0.06


# ------------------------------------- the app closing his own microphone
#
# `audio_devices._reinitialise` calls `sd._terminate()`, and PortAudio closes
# every open stream in the process when it does - measured here 15 Aug 2026:
# two streams open, terminate, re-init, both to zero callbacks with nothing
# raised, `.active` afterwards `PortAudioError -9988`. `a6006cd` covered the
# engineer's voice. The microphone is the same shape of stream from the other
# side: opened on button-down, closed on button-up. The route in is the
# shipped app - `ui/settings_screen.py::_audio_plate` enumerates output and
# then input while the screen is being built - so the driver opening settings
# with the button held used to lose his question, twice, in silence.
#
# None of these needs a sound card, a decoder or a model.

@pytest.fixture(autouse=True)
def _no_capture_left_behind():
    """A leaked declaration would make the next test wait out the whole cap."""
    yield
    with audio_devices._PLAYING_STATE:
        audio_devices._PLAYING.clear()
        audio_devices._PLAYING_STATE.notify_all()


class PortAudio:
    """Enough of `sounddevice` for a device-list rebuild and nothing else."""

    def _terminate(self):
        pass

    def _initialize(self):
        pass


class Mic:
    """An input stream. Optionally one PortAudio has already closed."""

    def __init__(self, already_closed: bool = False) -> None:
        self.stopped = False
        self.closed = False
        self._already_closed = already_closed

    def stop(self):
        if self._already_closed:
            # What `stop()` really does on a stream `_terminate()` has taken:
            # -9988, invalid stream pointer, and the first word anything says
            # about it.
            raise RuntimeError("PortAudioError -9988: invalid stream pointer")
        self.stopped = True

    def close(self):
        self.closed = True


class Transcriber:
    """Moonshine's streaming decoder, reduced to what it was given and said."""

    def __init__(self, text: str = "when do i box") -> None:
        self.text = text
        self.started = 0
        self.stopped = 0

    def start(self):
        self.started += 1

    def add_audio(self, _block, _rate):
        pass

    def stop(self):
        self.stopped += 1

    def update_transcription(self):
        from types import SimpleNamespace
        return SimpleNamespace(lines=[SimpleNamespace(text=self.text)])

    def close(self):
        pass


def microphone(heard: str = "when do i box"):
    """A `MoonshineRecogniser` with no model, no numpy and no sound card."""
    mic = ptt.MoonshineRecogniser.__new__(ptt.MoonshineRecogniser)
    mic._max_capture_s = MAX_CAPTURE
    mic._silence_rms = 0.012
    mic._stream = None
    mic._capture = None
    mic._speech_blocks = 0
    mic._total_blocks = 0
    mic._truncated = False
    mic.last_reason = None
    mic._transcriber = Transcriber(heard)
    return mic


def spoke(mic, seconds: float = 2.0) -> None:
    """Two seconds of a man asking a question, as the block counters see it.

    Without this every press below would be rejected at stage 0 for delivering
    no audio, and the thing under test would never be reached.
    """
    blocks = int(seconds * mic.SAMPLE_RATE / mic.BLOCK)
    mic._total_blocks = blocks
    mic._speech_blocks = blocks


def rebuilding():
    """A device rebuild on a thread that is not holding the button.

    On another thread on purpose, twice over: it is where the settings screen
    and the transducer watchdog really run, and `_wait_for_playback`
    deliberately never waits on its own thread, so a rebuild driven from the
    test thread would not exercise the wait at all.
    """
    done = threading.Event()

    def run():
        audio_devices._reinitialise(PortAudio())
        done.set()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, done


def rebuilt():
    """A rebuild, waited out. Fails rather than hangs if it never returns."""
    thread, done = rebuilding()
    assert done.wait(10.0), "the rebuild never finished"
    thread.join(timeout=5.0)


def test_a_rebuild_waits_for_the_button_to_come_up(monkeypatch):
    """The first half of the fix, and the half that should nearly always be
    enough. The microphone is declared for as long as it is open, so a rebuild
    holds off instead of closing it under him - the same gate the engineer's
    line goes behind, reached from the input side."""
    mic = microphone()
    monkeypatch.setattr(ptt, "open_input", lambda *a, **k: Mic())
    mic.begin()
    spoke(mic)

    thread, done = rebuilding()
    assert not done.wait(0.4), "the rebuild went ahead over the top of him"
    assert mic.end() == "when do i box", "the question did not survive"
    assert mic.last_reason is None
    assert done.wait(5.0), "the rebuild never got through afterwards"
    thread.join(timeout=5.0)


def test_a_rebuild_between_presses_is_not_delayed_at_all():
    """The common case, and it must cost nothing. Nothing is declared between
    presses, so a rebuild is exactly as free as it was before any of this."""
    started = time.monotonic()
    rebuilt()
    assert time.monotonic() - started < 0.5


def test_a_press_with_no_rebuild_still_answers_normally(monkeypatch):
    """The whole mechanism has to be invisible when nothing collides."""
    mic = microphone("how much fuel")
    monkeypatch.setattr(ptt, "open_input", lambda *a, **k: Mic())
    mic.begin()
    spoke(mic)
    assert mic.end() == "how much fuel"
    assert mic.last_reason is None
    assert audio_devices._PLAYING == []


def test_a_cut_press_throws_the_half_question_away(monkeypatch):
    """The decision this fix had to make, and the reason for it.

    The voice re-speaks a line it had; the app cannot re-ask a question it
    never knew. What it holds after a cut is whatever reached the decoder
    before `_terminate()` ran, which is the front of a sentence - and
    `intents.py`'s rule is that an engineer who confidently mis-hears is worse
    than one who says "say again". So a complete-looking transcript is
    discarded anyway, because there is no way to tell it from a truncated one.
    """
    mic = microphone("when do i box")
    monkeypatch.setattr(ptt, "open_input", lambda *a, **k: Mic())
    monkeypatch.setattr(audio_devices, "DEFER_CAP_S", 0.05)
    mic.begin()
    spoke(mic)
    rebuilt()                       # runs out of patience and cuts him off

    assert mic.end() == "", "half a question was handed to the gate"
    assert mic.last_reason == ptt.CUT_BY_REBUILD
    assert mic._transcriber.stopped == 1, "the decoder was left running"


def test_a_cut_press_asks_him_to_say_it_again_in_words_of_its_own(monkeypatch):
    """Silence is the one outcome he cannot act on: a press that produces
    nothing is indistinguishable from a press the app never heard, which is
    the failure mode `CLAUDE.md` §7 names. He is in a headset, so one short
    line is a channel he has and the log is not."""
    mic = microphone()
    monkeypatch.setattr(ptt, "open_input", lambda *a, **k: Mic())
    monkeypatch.setattr(audio_devices, "DEFER_CAP_S", 0.05)
    said = []
    talk = PushToTalk(snapshot=dict, speak=said.append, recogniser=mic)

    talk.begin()
    spoke(mic)
    rebuilt()
    talk.end()

    assert said == [ptt.spoken_reason(ptt.CUT_BY_REBUILD)]
    assert talk.last_reason == ptt.CUT_BY_REBUILD
    assert "again" in said[0].lower(), "he was not told what to do about it"


def test_the_cut_does_not_borrow_another_reason_s_words():
    """`NOTHING_HEARD` puts it on the recogniser and `NO_INPUT` sends him to
    check a device that is working perfectly. Naming the reason accurately is
    the whole argument of `gate.SPOKEN`."""
    ours = ptt.spoken_reason(ptt.CUT_BY_REBUILD)
    assert ours not in [gate.spoken_reason(r) for r in gate.ALL_REASONS]
    assert "check the device" not in ours.lower()
    # Everything gate.py does know about still comes back from gate.py.
    for reason in gate.ALL_REASONS:
        assert ptt.spoken_reason(reason) == gate.spoken_reason(reason)
    assert ptt.spoken_reason(None) == gate.spoken_reason(None)


def test_two_rebuilds_in_one_press_are_one_line_not_two(monkeypatch):
    """`_audio_plate` calls `devices("output")` and then `devices("input")`,
    so the shipped path is two teardowns inside one press. He is told on the
    way out of the press, once, not once per attempt."""
    mic = microphone()
    monkeypatch.setattr(ptt, "open_input", lambda *a, **k: Mic())
    monkeypatch.setattr(audio_devices, "DEFER_CAP_S", 0.05)
    said = []
    talk = PushToTalk(snapshot=dict, speak=said.append, recogniser=mic)

    talk.begin()
    spoke(mic)
    rebuilt()
    rebuilt()
    talk.end()

    assert said == [ptt.spoken_reason(ptt.CUT_BY_REBUILD)]


def test_the_declaration_comes_down_even_when_the_stream_is_already_dead(
        monkeypatch):
    """A stream `_terminate()` has taken raises -9988 from `stop()`. If that
    escaped, the declaration would stand for the rest of the session and every
    later rebuild would wait the whole cap for a microphone nobody is holding -
    and this press would reach him as "check the log" instead of "say it
    again"."""
    mic = microphone()
    monkeypatch.setattr(ptt, "open_input",
                        lambda *a, **k: Mic(already_closed=True))
    monkeypatch.setattr(audio_devices, "DEFER_CAP_S", 0.05)
    said = []
    talk = PushToTalk(snapshot=dict, speak=said.append, recogniser=mic)

    talk.begin()
    spoke(mic)
    rebuilt()
    talk.end()                                  # must not raise

    assert audio_devices._PLAYING == [], "the microphone is still declared"
    assert said == [ptt.spoken_reason(ptt.CUT_BY_REBUILD)]
    assert talk.last_reason != gate.FAILED

    # And the next rebuild is free again, which is the point of the above.
    started = time.monotonic()
    rebuilt()
    assert time.monotonic() - started < 0.5


def test_closing_mid_press_does_not_leave_the_microphone_declared(monkeypatch):
    """A press that never gets its button-up - the app stopping, or the key
    being rebound mid-hold - is the other way to leak the declaration."""
    mic = microphone()
    monkeypatch.setattr(ptt, "open_input", lambda *a, **k: Mic())
    mic.begin()
    mic.close()
    assert audio_devices._PLAYING == []
    started = time.monotonic()
    rebuilt()
    assert time.monotonic() - started < 0.5


def test_a_held_button_and_a_rebuild_cannot_deadlock(monkeypatch):
    """Two locks and two threads, in the order `enumeration_lock` warns about.

    `open_and_declare` takes the enumeration lock and then the playback gate;
    `_reinitialise` takes the enumeration lock and waits on that same gate. So
    the press must be able to finish while a rebuild is holding the lock and
    waiting for it - `end_playback` deliberately needs only the gate - and the
    next press must open cleanly once the rebuild has been through.
    """
    mic = microphone()
    monkeypatch.setattr(ptt, "open_input", lambda *a, **k: Mic())
    mic.begin()
    spoke(mic)

    thread, done = rebuilding()
    assert not done.wait(0.3)
    # Button up while the rebuild sits on the lock waiting for it.
    assert mic.end() == "when do i box"
    assert done.wait(10.0), "the rebuild never came out of the wait"
    thread.join(timeout=5.0)

    # And the button still works afterwards, which is the other half of a
    # deadlock: an enumeration lock left held would hang the next press here.
    again = microphone("how much fuel")
    again.begin()
    spoke(again)
    assert again.end() == "how much fuel"
    assert audio_devices._PLAYING == []


# ------------------------------------------------ the recogniser deadline (E6)
#
# `Dispatch("SAPI.SpSharedRecognizer")` does not raise when Windows Speech is
# unconfigured - it never returns. `except Exception` cannot catch that, so
# the fallback chain never advanced to Moonshine and `Controller.__init__`
# never finished. Measured: still blocked after 60 s, outside pytest, no Qt.

def test_a_quick_factory_is_returned_as_normal():
    assert ptt.build_within(lambda: "engine", 5.0) == "engine"


def test_a_factory_that_raises_still_raises():
    """The deadline must not swallow a real failure into a timeout."""
    def broken():
        raise RuntimeError("no microphone")

    with pytest.raises(RuntimeError, match="no microphone"):
        ptt.build_within(broken, 5.0)


def test_a_factory_that_never_returns_is_abandoned():
    """The case that stopped the app starting."""
    forever = threading.Event()          # never set

    def blocks():
        forever.wait()

    started = time.perf_counter()
    with pytest.raises(TimeoutError, match="did not come up"):
        ptt.build_within(blocks, 0.2)
    assert time.perf_counter() - started < 3.0, "the deadline did not bind"


def test_the_abandoned_thread_is_a_daemon_and_cannot_hold_the_process_open():
    """A blocked COM call cannot be cancelled, so it is abandoned deliberately."""
    forever = threading.Event()
    before = {t.name for t in threading.enumerate()}
    with pytest.raises(TimeoutError):
        ptt.build_within(lambda: forever.wait(), 0.1)
    leaked = [t for t in threading.enumerate()
              if t.name not in before and t.name.startswith("probe-")]
    assert leaked and all(t.daemon for t in leaked)
    forever.set()


def test_the_factory_argument_is_passed_through():
    assert ptt.build_within(lambda phrases: phrases, 5.0, ("box", "fuel")) == (
        "box", "fuel")


def test_speech_is_not_constructed_under_pytest():
    """The seam that lets a Controller be built at all in a test.

    Tests construct one dozens of times; none should pay a five second probe
    or depend on how Windows Speech happens to be set up on the machine. A
    test that wants a recogniser injects one.
    """
    assert ptt._under_pytest() is True
    assert ptt.best_recogniser_for("sapi") is None
    assert ptt.best_recogniser_for("moonshine") is None
