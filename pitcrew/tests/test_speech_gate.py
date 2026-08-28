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
    verdict = gate.judge("when box thing", intent=BOX_WHEN, distance=0.50)
    assert verdict.action == gate.CONFIRM
    assert verdict.intent == BOX_WHEN


def test_nonsense_is_rejected():
    # 0.65, not the 0.45 this used to use. The fridge sentence itself now
    # measures 0.400 and is *asked about* rather than refused, which is the
    # deliberate consequence of a band set on the cost of being wrong: he
    # pressed a button to talk to his engineer, and refusing a real question
    # costs more than answering a stray one.
    verdict = gate.judge("the fridge is making a noise", intent=BOX_WHEN,
                         distance=0.65)
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
    ("low", 0.40, gate.CONFIRM),
    ("low", 0.55, gate.REJECT),
    ("medium", 0.25, gate.ACT),
    ("medium", 0.50, gate.CONFIRM),
    ("medium", 0.65, gate.REJECT),
    ("high", 0.45, gate.ACT),
    ("high", 0.65, gate.CONFIRM),
    ("high", 0.80, gate.REJECT),
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
    ptt, said = talker(Matcher(BOX_WHEN, 0.50))
    reply = ptt.ask("when box thing")
    assert reply == "Did you mean box when?"
    assert said == ["Did you mean box when?"]
    assert ptt.pending_confirmation == BOX_WHEN


def test_yes_to_a_confirmation_answers_the_question():
    ptt, said = talker(Matcher(BOX_WHEN, 0.50))
    ptt.ask("when box thing")
    assert ptt.ask("yes") == "Box in 3 laps."
    assert ptt.pending_confirmation is None


def test_no_to_a_confirmation_says_again():
    ptt, said = talker(Matcher(BOX_WHEN, 0.50))
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
    ptt, said = talker(Matcher(BOX_WHEN, 0.75))
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

    def start(self, _press, _release, **_options):
        # `**_options` is the lost-key-up cap - see `ptt.LOST_KEY_UP_S`. These
        # tests are about which hook is running, not about what it was told.
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


def test_the_bands_are_ordered_and_act_on_the_questions_measured():
    """**There is no gap to sit inside any more, and that is the finding.**

    The old calibration asserted a 0.172 gap between real questions and
    unrelated speech. Re-measured against the rewritten vocabulary it is gone:
    real questions run 0.066-0.505, unrelated speech 0.170-0.573. The overlap
    is not noise - "remind me to buy milk" collides with "remind me of the
    plan" and no distance threshold separates those. A best-versus-second-best
    margin was measured too and does no better.

    So what is asserted is what the bands are actually for: that each is
    ordered, that they get stricter as the driver asks for stricter, and that
    at `medium` the phrasing he was measured using is acted on rather than
    questioned back at him.
    """
    for name in ("low", "medium", "high"):
        act, confirm = gate.bands(name)
        assert act < confirm, f"{name} would confirm before it acts"

    assert gate.bands("low")[0] < gate.bands("medium")[0]         < gate.bands("high")[0], "sensitivity does not order the act bands"

    # Sixteen fresh held-out questions measured 0.162 to 0.505, thirteen of
    # them matched to the right intent. At medium, all but the two furthest
    # act; nothing measured is refused outright. Under the old 0.30/0.40 band
    # only four of the sixteen acted and twelve came back as "did you mean".
    measured = [0.162, 0.171, 0.172, 0.201, 0.212, 0.216, 0.256, 0.310,
                0.316, 0.326, 0.336, 0.346, 0.400, 0.402, 0.406, 0.505]
    act, confirm = gate.bands("medium")
    assert sum(1 for d in measured if d <= act) >= 14, (
        "medium refuses to act on questions the driver actually asks")
    assert sum(1 for d in measured if d > confirm) == 0, (
        "a real question is refused outright rather than asked about")

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


def test_a_factory_that_never_returns_stops_the_wait_not_the_load():
    """The case that stopped the app starting - and the case that then killed
    push-to-talk for a whole session.

    **The deadline binds on the wait only.** It used to discard the result too,
    and `MoonshineRecogniser` - which loads in 2.3 s measured on its own -
    lost the five second race thirteen times under boot contention. Each of
    those was a race with no radio, while the loaded model sat in an abandoned
    thread with nobody holding it.
    """
    forever = threading.Event()          # never set

    def blocks():
        forever.wait()

    started = time.perf_counter()
    got = ptt.build_within(blocks, 0.2)
    assert time.perf_counter() - started < 3.0, "the deadline did not bind"
    assert isinstance(got, ptt.LateArrival)
    assert got.last_reason == gate.NOT_READY, (
        "a recogniser that is still loading must say so, not fail silently")


def test_a_late_arrival_becomes_usable_when_the_load_finishes():
    """Ask again in a moment, and it works."""
    landed = threading.Event()

    class Ready:
        name = "ready"
        last_reason = None

        def begin(self): pass

        def end(self): return "how are my tyres"

    def slow():
        landed.wait(5.0)
        return Ready()

    got = ptt.build_within(slow, 0.1)
    assert isinstance(got, ptt.LateArrival)
    assert got.end() == "", "not ready yet"
    landed.set()
    for _ in range(200):                          # let the probe finish
        if got.last_reason is None:
            break
        time.sleep(0.01)
    assert got.end() == "how are my tyres"
    assert got.name == "ready"


def test_the_abandoned_thread_is_a_daemon_and_cannot_hold_the_process_open():
    """A blocked COM call cannot be cancelled, so it is abandoned deliberately."""
    forever = threading.Event()
    before = {t.name for t in threading.enumerate()}
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


# ---------------------------------------------------------- which one wins

def test_a_candidate_still_loading_never_beats_one_that_is_ready(monkeypatch):
    """**The regression `LateArrival` would otherwise have introduced.**

    SAPI is tried first for anyone who asked for it, and on this machine it
    blocks forever - fifty-nine launches, fifty-nine hangs. Now that a slow
    candidate is kept rather than discarded, the first one must not win by
    merely being first: SAPI's late arrival never comes, and returning it would
    leave push-to-talk permanently dead with a working Moonshine untried.
    """
    forever = threading.Event()

    class Ready:
        name = "moonshine"

    monkeypatch.setattr(ptt, "_under_pytest", lambda: False)
    monkeypatch.setattr(ptt, "SapiGrammarRecogniser",
                        lambda *a: forever.wait())
    monkeypatch.setattr(ptt, "MoonshineRecogniser", Ready)
    monkeypatch.setattr(ptt, "RECOGNISER_TIMEOUT_S", 0.1)

    got = ptt.best_recogniser_for("sapi")
    assert isinstance(got, Ready), (
        "a recogniser that hangs pre-empted one that was ready")


def test_nothing_ready_falls_back_to_the_one_still_coming(monkeypatch):
    """Better a radio that works from lap two than no radio at all."""
    forever = threading.Event()
    monkeypatch.setattr(ptt, "_under_pytest", lambda: False)
    monkeypatch.setattr(ptt, "SapiGrammarRecogniser",
                        lambda *a: forever.wait())
    monkeypatch.setattr(ptt, "MoonshineRecogniser",
                        lambda: forever.wait())
    monkeypatch.setattr(ptt, "RECOGNISER_TIMEOUT_S", 0.1)
    assert isinstance(ptt.best_recogniser_for("moonshine"), ptt.LateArrival)


def test_the_default_backend_is_the_one_that_has_ever_come_up():
    from pitcrew.settings import SPEECH_MOONSHINE, Settings
    assert Settings().speech_backend == SPEECH_MOONSHINE


# ---------------------------------------------------------------------------
# Why every press on file reports 0.00s captured
#
# Road Atlanta, 23 Aug 2026, and Yas before it. Two input opens exist in a week
# of logs and both ended the same way:
#
#     input device 33 'Microphone (JBL Endurance Run 3C)' via Windows WASAPI
#     would not open (Invalid sample rate) - trying the next route
#     rejected before transcribing: the microphone delivered no audio
#     (0.00s captured, 0.00s speech)
#
# Nothing between those two lines. Which route took over, what it granted, and
# whether a single block ever arrived were all unrecorded - and `0.00s
# captured` cannot tell a microphone that delivered silence from a stream that
# never called back, which need opposite fixes.
#
# It also had a silent-abort path: `np.asarray(...).reshape(-1)` and the RMS
# line sat OUTSIDE the callback's try. An exception there aborts the stream,
# PortAudio does it without a word, `_total_blocks` stays 0, and the press ends
# with exactly the message above and no trace of the cause.
# ---------------------------------------------------------------------------

def test_a_callback_that_raises_is_reported_rather_than_silently_aborting():
    """The whole body is guarded, not just `add_audio`."""
    import inspect

    from pitcrew.engineer import ptt as ptt_module

    body = inspect.getsource(ptt_module.MoonshineRecogniser.begin)
    guarded = body[body.index("def on_audio"):]
    reshape_at = guarded.index("np.asarray(indata")
    try_at = guarded.index("try:")
    assert try_at < reshape_at, (
        "the array conversion is outside the guard, so a route that grants an "
        "unexpected shape kills the capture with no log line at all")


def test_the_failure_is_latched_and_said_once():
    """A dead stream can call back many times before it stops. One error line
    per press, not one per block."""
    import inspect

    from pitcrew.engineer import ptt as ptt_module

    body = inspect.getsource(ptt_module.MoonshineRecogniser.begin)
    assert "if not self._callback_failed:" in body


def test_the_latch_is_cleared_for_every_press():
    """Otherwise one bad press silences the diagnosis for the whole session."""
    import inspect

    from pitcrew.engineer import ptt as ptt_module

    for where in (ptt_module.MoonshineRecogniser.__init__, ptt_module.MoonshineRecogniser.begin):
        assert "_callback_failed = False" in inspect.getsource(where)


def test_what_the_microphone_actually_opened_is_logged():
    """Every output path in the app logs this and the microphone never has -
    which is why a routing failure and a capture failure looked identical."""
    import inspect

    from pitcrew.engineer import ptt as ptt_module

    body = inspect.getsource(ptt_module.MoonshineRecogniser.begin)
    assert "describe_stream" in body
