"""Push to talk.

Hold the button, ask, let go, get an answer. The driver is in a headset with
his hands on the wheel, so this is the only way he can ask anything.

There were two recognisers here and now there are three states, because
Windows Speech Recognition is being retired. The SAPI path used a **bounded
grammar**: given the exact phrase list from `intents`, it could only ever
return one of them, which turned "did it hear me correctly" into "did it hear
me at all". That property was free, and it is the one thing that made free
dictation unacceptable - confident nonsense is the worst thing an engineer can
produce.

Moonshine replaces the engine and `gate.py` replaces the property. Free
dictation now passes a staged gate, and the outcome is one of three rather
than two: **act**, **ask one word**, or **say again**. The middle state is the
point. Rejecting an ambiguous question costs the driver a whole repeat with
his hands full; asking him to confirm costs him one syllable.

Input and recognition are both injectable, so the whole path can be driven in
tests, and so a machine without a microphone still runs the app.

The microphone stream is declared to `audio_devices` while it is open, the
same way the engineer's spoken line is - see `CUT_BY_REBUILD` below for why,
and for what a press the app cut short comes back as.
"""
from __future__ import annotations

import os
import pathlib
import threading

from pitcrew.diagnostics import log
from pitcrew.engineer import audio_devices, gate
from pitcrew.engineer import radio as radio_static
from pitcrew.settings import SPEECH_SAPI
from pitcrew.engineer.audio_devices import open_input
from pitcrew.engineer.intents import (
    PHRASES,
    UNKNOWN,
    answer,
    known_phrases,
    match_intent,
)

# How long the driver can hold the button before we stop listening anyway.
# This is a real cap: the capture stops feeding the decoder and the stream
# stops itself at the limit, so a stuck button costs the tail of the question
# rather than the whole of it. It used to be applied only afterwards, in
# `gate.check_audio`, which threw away the entire transcript for being long.
MAX_CAPTURE_S = 6.0
SAMPLE_RATE = 16_000

# What the microphone calls itself while it holds a stream open, for the log
# line a deferred device rebuild writes. See `audio_devices.begin_playback`.
MICROPHONE = "the driver's question"

# Why there was no question, when the reason was the app's own doing.
#
# `audio_devices._reinitialise` calls `sd._terminate()`, and PortAudio closes
# **every open stream in the process** when it does - measured here on 15 Aug
# 2026: two streams open, terminate, re-init, both to zero callbacks with
# nothing raised, `.active` afterwards giving `PortAudioError -9988`. `a6006cd`
# fixed that for the engineer's voice, whose line IS a short-lived stream. The
# microphone is the same shape of stream from the other direction:
# `MoonshineRecogniser` opens it on button-down and closes it on button-up, so
# a rebuild landing inside a press closes the driver's microphone in the middle
# of his question and nothing raises.
#
# The route in is not exotic. `ui/settings_screen.py::_audio_plate` fills its
# two pickers by calling `devices("output")` and then `devices("input")` while
# the screen is being built, and `devices` re-enumerates on every call on
# purpose so a headset plugged in a moment ago appears - so the driver opening
# settings while holding the button runs the teardown twice. The transducer
# watchdog is a second way in.
#
# **The voice's answer to being cut is not available here.** It re-speaks the
# line, because it knows what the line was. The app does not know what the
# driver was about to ask, so the only two things it can do with a cut press
# are tell him or not tell him. It tells him, and it throws away whatever the
# decoder had rather than answering it. Three things decide that:
#
# * **Silence is the one outcome he cannot act on.** A press that produces
#   nothing is indistinguishable from a press the app never heard, and that is
#   the failure mode `CLAUDE.md` §7 names outright - the thing that must fail
#   loudly rather than degrade into zeros. He is in a headset with both hands
#   on the wheel: one short line is a channel he has, and the log is not.
# * **Half a question is worse than no question.** The audio stops the instant
#   `_terminate()` runs and the transcript keeps only what arrived before it,
#   so what would reach `gate.judge` is the front of a sentence. `intents.py`'s
#   rule is that an engineer who confidently mis-hears is worse than one who
#   says "say again", and a truncated question is precisely how a confident
#   mis-hearing gets manufactured. Asking again costs him a corner; being
#   answered on a question he never finished can cost him the race.
# * **It is not "say again" in the gate's existing words.** `NOTHING_HEARD`
#   says "I didn't catch that", which puts it on the recogniser; `NO_INPUT` and
#   `NO_DEVICE` send him to check a device that is working perfectly. Naming
#   the reason accurately is the whole argument of `gate.SPOKEN`, so this
#   reason gets its own line rather than borrowing one that is wrong.
#
# **Holding the rebuild off for the length of the press is not the rejected
# alternative - it is the first half of the fix.** Declaring the stream is what
# makes a rebuild wait, and it waits up to `audio_devices.DEFER_CAP_S`, which
# is why a cut press should now be rare rather than routine. What that wait
# cannot be is unbounded: a press is driver-paced, and one stuck button would
# otherwise starve a transducer recovery for the rest of the race. This is what
# happens when the bounded wait runs out.
CUT_BY_REBUILD = "the audio devices were rebuilt mid-question"

# The rejection reasons this module owns, spoken in their own words.
#
# Separate from `gate.SPOKEN` only because this is the half of the fix that
# lives here. HANDOFF: it belongs in `gate.py` beside the other nine - as a
# constant, a `SPOKEN` line and an `ALL_REASONS` entry - and until it is
# there, `phrase_manifest.rejection_lines` will not pre-render it, so this one
# line falls through to live synthesis. That is a pause at the moment the
# driver has just failed to get an answer, which is exactly the pause
# `rejection_lines` exists to remove.
OWN_SPOKEN: dict[str, str] = {
    # §5.5 form: the instruction first, the reason second and short. It
    # deliberately does not say "check the device" the way the two device
    # reasons do - his microphone is fine, and sending him to unplug a working
    # headset mid-race would be the cost of borrowing their words.
    CUT_BY_REBUILD: "Say that again. I lost the microphone for a moment.",
}


def spoken_reason(reason: str | None) -> str:
    """What the driver hears about a rejection, including this module's own."""
    return OWN_SPOKEN.get(reason or "") or gate.spoken_reason(reason)


# Answers to "did you mean X?". One syllable each, because he is mid-corner
# and both hands are busy. Kept separate from the ACCEPT/KEEP intents, which
# are about a re-plan offer rather than about what the engineer just heard.
_YES = {"yes", "yeah", "yep", "correct", "affirmative", "right", "copy"}
_NO = {"no", "nope", "negative", "wrong"}


class PushToTalk:
    """Ties the button, the recogniser and the answer together."""

    def __init__(self, *, snapshot, speak, recogniser=None, listener=None,
                 on_answer=None, matcher=None,
                 sensitivity: str = gate.DEFAULT_SENSITIVITY,
                 toggle: bool = True, bursts=None) -> None:
        self._snapshot = snapshot          # callable -> dict
        self._speak = speak                # callable(str)
        self._recogniser = recogniser
        self._listener = listener
        self._on_answer = on_answer
        # None means literal phrase matching, which is what the closed grammar
        # always did. It is exact by construction, so it needs no gate.
        self._matcher = matcher
        self._sensitivity = sensitivity
        self._busy = threading.Lock()
        self.last_call: str | None = None
        self.pending_replan: str | None = None
        # The intent waiting on a one-word yes. Cleared by either answer.
        self.pending_confirmation: str | None = None
        self.transcript: list[tuple[str, str]] = []   # (heard, said)
        self.last_verdict: gate.Verdict | None = None
        # Why the last press produced no question. One of `gate`'s reasons,
        # and now spoken rather than only stored.
        self.last_reason: str | None = None
        self._listening = False
        # **Tap to open, tap to close.** "I don't have time to hold the
        # button" - and he is right: holding it occupies a hand that is on a
        # wheel through a corner, which is where the questions happen.
        self._toggle = toggle
        self._recording = False
        self._deadline: threading.Timer | None = None
        # Never built under pytest: rendering one opens a real PortAudio
        # output stream, which `conftest` forbids and is right to. A test that
        # wants the bursts injects them.
        opening, closing = (bursts if bursts is not None
                            else (None, None) if _under_pytest()
                            else radio_static.bursts())
        # With the button no longer held, nothing else tells him the
        # microphone is open. These are that signal, and they are why toggle
        # mode is usable without a screen at all.
        self._open_burst, self._close_burst = opening, closing

    @property
    def recording(self) -> bool:
        """Whether the radio is open right now. False in hold mode between
        presses, and in toggle mode until he taps."""
        return self._recording

    @property
    def available(self) -> bool:
        return self._recogniser is not None

    @property
    def has_listener(self) -> bool:
        """Whether the button can be read at all on this machine."""
        return self._listener is not None

    @property
    def listening(self) -> bool:
        """Whether the hook is actually running, which is not the same thing
        as one existing - rebinding the key used to leave the second true and
        the first false, with the UI reporting the second."""
        return self._listening and self._listener is not None

    def set_listener(self, listener) -> None:
        """Swap the button.

        The old hook is stopped first, or it keeps firing on the key the driver
        just changed away from - and the new one is started if the old one was
        running, or rebinding mid-session kills the button on both keys while
        `has_listener` goes on reporting it loaded.
        """
        was_listening = self.listening
        if self._listener is not None:
            self._listener.stop()
        self._listener = listener
        self._listening = False
        if was_listening:
            self.start()

    def start(self) -> None:
        if self._listener is not None:
            if self._toggle:
                # Button-up does nothing: one tap opens, the next closes.
                self._listener.start(self.tap, lambda: None)
            else:
                self._listener.start(self.begin, self.end)
            self._listening = True

    def tap(self) -> None:
        """One press of the button, in toggle mode.

        Open the radio, or close it and answer. Guarded the same way `begin`
        and `end` are, because this is the outermost frame on pynput's hook
        thread and an escaping exception there kills the button for the race.
        """
        try:
            if self._recording:
                self._close_radio()
            else:
                self._open_radio()
        except Exception as exc:                # noqa: BLE001 - see above
            log("ptt").error("push to talk failed: %s: %s",
                             type(exc).__name__, exc, exc_info=True)
            self._recording = False
            self._cancel_deadline()
            try:
                self.rejected(gate.FAILED)
            except Exception:                   # noqa: BLE001
                log("ptt").error("could not report the failure either",
                                 exc_info=True)

    def _open_radio(self) -> None:
        """The static first, then the microphone.

        In that order on purpose: the burst plays into a microphone that is
        not open yet, so it cannot end up in the transcript.
        """
        self._burst(self._open_burst)
        self.begin()
        if self.last_reason is not None:
            # The stream never opened. Say so now rather than leaving him
            # talking to a radio that is not on.
            self.rejected(self.last_reason)
            return
        self._recording = True
        # **He may never press again.** In hold mode the button coming up is
        # guaranteed; here it is not, and a radio left open would swallow the
        # capture cap and then sit there. The cap closes it and answers.
        self._cancel_deadline()
        self._deadline = threading.Timer(MAX_CAPTURE_S + 0.5, self._expired)
        self._deadline.daemon = True
        self._deadline.start()

    def _close_radio(self) -> None:
        self._recording = False
        self._cancel_deadline()
        self.end()

    def _expired(self) -> None:
        """The capture cap reached with no second press."""
        if not self._recording:
            return
        log("ptt").info("radio closed on the %.0fs cap - no second press",
                        MAX_CAPTURE_S)
        self._close_radio()

    @staticmethod
    def _burst(tone) -> None:
        """Play a static burst, and never let it cost him an answer.

        Confirmation is not the question. A card that will not render 130 ms
        of noise must still deliver the radio call it was asked for.
        """
        if tone is None:
            return
        try:
            tone.play_blocking()
        except Exception as exc:                # noqa: BLE001
            log("ptt").warning("radio static did not play: %s: %s",
                               type(exc).__name__, exc)

    def _cancel_deadline(self) -> None:
        if self._deadline is not None:
            self._deadline.cancel()
            self._deadline = None

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
        self._listening = False

    # ------------------------------------------------------------- the cycle
    #
    # `begin` and `end` are the OUTERMOST FRAME on pynput's hook thread, and
    # pynput does not treat an escaping exception as an error to report: its
    # `_emitter.inner` catches it, queues the exc_info, calls `self.stop()` and
    # re-raises into `ListenerMixin._run`, which swallows it in a bare
    # `except:`. The listener is then stopped for good, surfaced only through
    # `join()`, which nothing here calls - so an unguarded raise means the
    # button goes dead for the rest of the race while `has_listener` still
    # reports the hook loaded. `sd.InputStream` is a genuine raiser (no device,
    # device claimed, device removed) and none of that is detectable when the
    # recogniser is constructed. Note the contrast the code already showed: the
    # audio callback INSIDE `begin` was carefully guarded and the frame that
    # owns it was not.

    def begin(self) -> None:
        """Button down."""
        self.last_reason = None
        if self._recogniser is None:
            return
        try:
            self._recogniser.begin()
        except Exception as exc:                # noqa: BLE001 - see above
            self.last_reason = gate.NO_DEVICE
            log("ptt").error("could not open the microphone: %s: %s",
                             type(exc).__name__, exc, exc_info=True)

    def end(self) -> None:
        """Button up: recognise what was said and answer it."""
        try:
            self._end()
        except Exception as exc:                # noqa: BLE001 - see above
            log("ptt").error("push to talk failed: %s: %s",
                             type(exc).__name__, exc, exc_info=True)
            try:
                self.rejected(gate.FAILED)
            except Exception:                   # noqa: BLE001
                # Speaking about the failure failed too. Nothing left to try,
                # and taking the hook thread down would cost him the button.
                log("ptt").error("could not report the failure either",
                                 exc_info=True)

    def _end(self) -> None:
        if self._recogniser is None:
            self._reply("Speech isn't available on this machine.", "")
            return
        if self.last_reason == gate.NO_DEVICE:
            # The stream never opened, so there is nothing to close and
            # nothing to transcribe. Say which of the two it was.
            self.rejected(gate.NO_DEVICE)
            return
        # One question at a time; a second press while answering is ignored
        # rather than queued, because the answer to the first is already stale.
        if not self._busy.acquire(blocking=False):
            return
        try:
            heard = self._recogniser.end() or ""
            # The microphone is shut at this point and the answer has not been
            # spoken yet, which is the one moment the closing burst belongs
            # in: it confirms the radio is off, and it does not get recorded.
            self._burst(self._close_burst)
            reason = getattr(self._recogniser, "last_reason", None)
            if not heard and reason:
                self.rejected(reason)
                return
            self.ask(heard)
        finally:
            self._busy.release()

    def rejected(self, reason: str) -> str:
        """Say why there was no question, in that reason's own words.

        The five gate reasons were computed, stored in `last_reason` and read
        nowhere: all of them arrived as "Say again.", which is the one reply
        that cannot distinguish a brushed button from a microphone that is not
        plugged in. `gate.py`'s own rationale is that a driver told "I didn't
        hear you" learns to press the button properly while one told nothing
        learns the app is unreliable.
        """
        self.last_reason = reason
        self.last_verdict = gate.Verdict(gate.REJECT, UNKNOWN, "", reason)
        text = spoken_reason(reason)
        self._reply(text, "")
        return text

    def ask(self, heard: str) -> str:
        """Answer a question already turned into text. The testable seam.

        Everything downstream of recognition happens here, so the whole gate
        can be driven from a string in a test - no microphone, no model, no
        audio device.
        """
        if self.pending_confirmation is not None:
            resolved = self._resolve_confirmation(heard)
            if resolved is not None:
                return resolved

        intent, distance = self._match(heard)
        verdict = gate.judge(heard, intent=intent, distance=distance,
                             sensitivity=self._sensitivity)
        self.last_verdict = verdict

        if verdict.action == gate.CONFIRM:
            # Ask rather than reject: he can say "yes" in a second, where
            # repeating the whole question costs him a corner.
            self.pending_confirmation = verdict.intent
            question = gate.confirmation_question(verdict.intent)
            log("ptt").info("confirming %r as %s (distance %.3f)",
                            heard, verdict.intent, verdict.distance or 0.0)
            self._reply(question, heard)
            return question

        # **Every outcome, including the good one.** Only failures were logged,
        # so a 1.3 MB log covering ten days held three press outcomes and all
        # three were failures - which made "it doesn't understand me"
        # impossible to investigate after the fact. A press that worked is the
        # measurement that says the rest of them should have.
        log("ptt").info("%s %r as %s (distance %s)", verdict.action.lower(),
                        heard, verdict.intent,
                        f"{verdict.distance:.3f}" if verdict.distance
                        is not None else "literal")
        return self._answer(verdict.intent, heard)

    def _match(self, heard: str):
        """(intent, distance). Falls back to literal matching, always."""
        if self._matcher is None:
            return match_intent(heard), None
        try:
            return self._matcher.match(heard)
        except Exception as exc:                 # noqa: BLE001
            # A semantic matcher that throws must not cost the driver an
            # answer the literal matcher could have given him.
            log("ptt").warning("semantic match failed for %r: %s: %s",
                               heard, type(exc).__name__, exc)
            return match_intent(heard), None

    def _resolve_confirmation(self, heard: str) -> str | None:
        """Yes or no to "did you mean X?". None if it was neither.

        Neither means he ignored the question and asked something else, which
        is answered on its own terms rather than treated as a refusal.
        """
        words = set(heard.lower().replace("?", " ").split())
        if words & _YES:
            intent = self.pending_confirmation
            self.pending_confirmation = None
            return self._answer(intent, heard)
        if words & _NO:
            self.pending_confirmation = None
            return self._answer(UNKNOWN, heard)
        self.pending_confirmation = None
        return None

    def _answer(self, intent: str, heard: str) -> str:
        reply = answer(intent, self._snapshot() or {},
                       last_call=self.last_call,
                       pending_replan=self.pending_replan)
        if intent in ("accept", "keep") and self.pending_replan:
            self.pending_replan = None
        self._reply(reply.text, heard)
        return reply.text

    def _reply(self, text: str, heard: str) -> None:
        self.transcript.append((heard, text))
        self._speak(text)
        if self._on_answer is not None:
            self._on_answer(heard, text)


class SapiGrammarRecogniser:
    """Windows SAPI, constrained to the phrases the engineer can answer.

    A closed grammar cannot return a phrase that is not in it, so a
    misrecognition becomes "nothing heard" rather than a wrong answer given
    confidently.
    """

    name = "sapi-grammar"

    def __init__(self, phrases=None) -> None:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        self._engine = win32com.client.Dispatch("SAPI.SpSharedRecognizer")
        self._context = self._engine.CreateRecoContext()
        self._grammar = self._context.CreateGrammar()
        self._grammar.DictationSetState(0)

        self._grammar.CmdLoadFromMemory  # probe the interface exists
        rule = self._grammar.Rules.Add(
            "pitcrew", 0x00000001 | 0x00000020, 0)   # TopLevel | Dynamic
        for phrase in (phrases or known_phrases()):
            rule.InitialState.AddWordTransition(None, phrase)
        self._grammar.Rules.Commit()
        self._heard: str | None = None

    def begin(self) -> None:
        self._heard = None
        self._grammar.CmdSetRuleState("pitcrew", 1)

    def end(self) -> str | None:
        self._grammar.CmdSetRuleState("pitcrew", 0)
        return self._heard


class KeyboardListener:
    """A held key, via pynput. Works with a wheel button mapped to a key."""

    def __init__(self, key: str = "f8") -> None:
        from pynput import keyboard

        self._keyboard = keyboard
        self._key = key.lower()
        self._listener = None
        self._down = False

    def start(self, on_press, on_release) -> None:
        def pressed(key):
            if self._matches(key) and not self._down:
                self._down = True
                on_press()

        def released(key):
            if self._matches(key) and self._down:
                self._down = False
                on_release()

        self._listener = self._keyboard.Listener(
            on_press=pressed, on_release=released)
        self._listener.daemon = True
        self._listener.start()

    def _matches(self, key) -> bool:
        name = getattr(key, "name", None) or getattr(key, "char", None)
        return (name or "").lower() == self._key

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None


def best_recogniser(phrases=None):
    """A constrained recogniser, or None where speech is unavailable."""
    try:
        return SapiGrammarRecogniser(phrases)
    except Exception as exc:                    # noqa: BLE001
        log("ptt").warning("speech recognition unavailable: %s: %s",
                          type(exc).__name__, exc)
        return None


def best_listener(key: str = "f8"):
    try:
        return KeyboardListener(key)
    except Exception as exc:                    # noqa: BLE001
        log("ptt").warning("no keyboard hook: %s: %s",
                          type(exc).__name__, exc)
        return None


class MoonshineRecogniser:
    """Free dictation, streamed while the button is held.

    Windows Speech Recognition is being retired - the WSR user experience is
    already gone from this machine and Windows now says so out loud - so the
    closed SAPI grammar is on borrowed time. This replaces it.

    **Audio is transcribed during the hold, not after it.** Measured on this
    machine, one-shot transcription of a 1.5 s question takes 1.3-1.6 s, which
    would arrive after the corner it was asked in. Fed block by block while the
    driver is still talking, the same question is finished about 4 ms after he
    lets go, because the work happened while he spoke. That is the whole reason
    this class holds a stream rather than a buffer.

    `tiny-streaming-en` is the model, not the default `medium-streaming-en`.
    Measured on this CPU - integrated graphics, no CUDA - tiny runs at 0.46x
    real time and medium at 1.32x. Anything above 1.0 falls behind the driver
    and never catches up.

    Losing the closed grammar loses its safety property, so `gate.py` replaces
    it. This class owns the stages that need the audio; the rest happen in
    `PushToTalk.ask()`, which stays the testable seam.
    """

    name = "moonshine"
    SAMPLE_RATE = 16_000
    BLOCK = 1600                    # 100 ms, the granularity the VAD counts in
    # **Trailing silence, because the radio shuts on the last syllable.**
    # The button is a tap, not a hold: press, static, listen, static. The
    # second tap ends the capture, and it lands where his sentence does.
    # A streaming recogniser decides a word is finished when it hears what
    # comes after it, and nothing comes after the last one: the mic closes and
    # the final pass runs on audio that stops mid-word. Measured over ten
    # phrases run three times each (`tools/stt_bench.py`), feeding six tenths
    # of a second of silence before that pass took the tiny model from 5 exact
    # transcripts in 30 to 19, and its median word error rate from 25% to
    # zero. **It is a larger improvement than any model in the family gives**,
    # because the errors it removes are all the same error: "box this lap"
    # came back as "box this side", "the rear is loose on entry" as "the rear
    # is loose on". Silence is fed rather than waited for, so what it costs is
    # only the final pass looking at a little more audio - ~300 ms against the
    # ~4 ms of a pass that had nothing left to decide, and still less than any
    # larger model's.
    TAIL_PAD_S = 0.6

    def __init__(self, *, max_capture_s: float = MAX_CAPTURE_S,
                 silence_rms: float = 0.012) -> None:
        import numpy  # noqa: F401 - the capture path is numpy throughout
        import sounddevice  # noqa: F401
        import moonshine_voice as moonshine
        from moonshine_voice.moonshine_api import ModelArch
        from moonshine_voice.transcriber import Transcriber

        # **Tiny stays, and that is a measurement rather than the default it
        # used to be.** Once the tail is padded (see `TAIL_PAD_S`) the three
        # streaming models are level on accuracy over thirty trials of
        # `tools/stt_bench.py` - tiny 19 exact transcripts, small 18, medium 21
        # - and the median word error rate of all three is zero. They are not
        # level on waiting: tiny finishes its last pass in ~300 ms, small in
        # ~770, medium in ~1240, and the worst case runs 0.6 / 1.5 / 2.1
        # seconds. Nothing is bought by the bigger models here, so nothing is
        # worth paying for them.
        #
        # This was briefly changed to small on a single ten-phrase pass that
        # showed a large gap. Repeating it three times removed the gap: ten
        # samples of a noisy quantity looked like a finding and was scatter.
        path, arch = moonshine.get_model_for_language(
            "en", ModelArch.TINY_STREAMING)
        self._transcriber = Transcriber(path, arch)
        self._max_capture_s = max_capture_s
        # Energy, not Silero. moonshine-voice 0.1.1 exposes no VAD threshold -
        # its voice activity detection is internal to the streaming line
        # splitter - so this counts blocks above a floor instead. It is a
        # coarser test, and it only has to answer one question: was there
        # anything here, or did the button get brushed?
        self._silence_rms = silence_rms
        self._stream = None
        # The `audio_devices.Playback` standing for the open microphone, for
        # as long as the button is held. None between presses.
        self._capture = None
        self._speech_blocks = 0
        self._total_blocks = 0
        # Latched when the capture callback raises, so the error is said once
        # rather than at every block of a stream that is already dead.
        self._callback_failed = False
        self._truncated = False
        self.last_reason: str | None = None

    @property
    def _max_blocks(self) -> int:
        return max(1, int(self._max_capture_s * self.SAMPLE_RATE / self.BLOCK))

    def begin(self) -> None:
        """Button down: open the mic and start feeding the decoder."""
        import numpy as np
        import sounddevice as sd

        # A press whose button-up never arrived would otherwise leave the last
        # declaration standing behind this one, and it would never come down -
        # `end` only releases the current one. Every device rebuild for the
        # rest of the session would then wait the whole cap for it.
        if self._capture is not None:
            self._release_capture()

        self._speech_blocks = 0
        self._total_blocks = 0
        # Latched when the capture callback raises, so the error is said once
        # rather than at every block of a stream that is already dead.
        self._callback_failed = False
        self._truncated = False
        self.last_reason = None
        self._transcriber.start()

        def on_audio(indata, _frames, _time, status) -> None:
            if status:
                log("ptt").debug("capture status: %s", status)
            if self._total_blocks >= self._max_blocks:
                # The cap, applied where it can still keep the question: the
                # first MAX_CAPTURE_S of audio is transcribed and the tail is
                # dropped. CallbackStop is PortAudio's own way to end a stream
                # from inside its callback; stopping it any other way from here
                # deadlocks the host.
                self._truncated = True
                raise sd.CallbackStop
            try:
                block = np.asarray(indata, dtype=np.float32).reshape(-1)
                if not self._total_blocks:
                    # **Once, so that "the stream is alive" is a fact in the
                    # log rather than an inference from its absence.** Every
                    # push-to-talk failure on file reports `0.00s captured`,
                    # which cannot distinguish a microphone that delivered
                    # silence from a stream that never called back at all -
                    # and those need opposite fixes.
                    log("ptt").info(
                        "capture is alive: first block, %s frames, %s",
                        block.size, block.dtype)
                self._total_blocks += 1
                if float(np.sqrt(np.mean(block * block))) >= self._silence_rms:
                    self._speech_blocks += 1
                self._transcriber.add_audio(block.tolist(), self.SAMPLE_RATE)
            except Exception as exc:             # noqa: BLE001
                # **The whole body, not just `add_audio`.** On the audio
                # callback thread an escaping exception aborts the stream, and
                # PortAudio does it silently: the press then ends with
                # `0.00s captured` and nothing anywhere saying why. The two
                # lines above this guard used to sit outside it, so a route
                # that opened with an unexpected channel count or dtype - which
                # is exactly what a fallback route can do - killed the capture
                # on its first block and left no trace at all.
                if not self._callback_failed:
                    self._callback_failed = True
                    log("ptt").error(
                        "the capture callback raised on its first block and "
                        "the stream will deliver nothing: %s: %s",
                        type(exc).__name__, exc, exc_info=True)

        # Opened and declared as one step, under the enumeration lock, so that
        # a device rebuild can neither close the microphone while he is
        # talking into it nor slip into the gap between the stream starting
        # and the declaration going up. Both halves are argued in
        # `audio_devices.begin_playback`; what a rebuild that runs out of
        # patience anyway costs him is argued at `CUT_BY_REBUILD`.
        #
        # The declaration outlives this call - it stands until the button
        # comes up - but the enumeration lock does not, so nothing here holds
        # a lock across the driver's finger.
        self._stream, self._capture = audio_devices.open_and_declare(
            MICROPHONE,
            lambda: open_input(
                self.SAMPLE_RATE, channels=1, dtype="float32",
                blocksize=self.BLOCK, callback=on_audio))
        # **What actually opened, said out loud.** Every output path in this
        # app logs this - the transducer, the voice, the beep - and the
        # microphone never has. So a push-to-talk failure could not be told
        # apart from a routing failure: the log recorded that WASAPI refused
        # the rate and then nothing whatsoever about the route that took over.
        # `describe_stream` compares what was granted against what was asked
        # for and never raises.
        try:
            log("ptt").info("microphone open: %s", audio_devices.describe_stream(
                self._stream, samplerate=self.SAMPLE_RATE, channels=1,
                dtype="float32", blocksize=self.BLOCK))
        except Exception as exc:                 # noqa: BLE001
            log("ptt").debug("could not describe the capture stream: %s", exc)

    def _release_capture(self):
        """Close the microphone and take its declaration down. Both, always.

        Guarded because the failure it covers is the one this exists for: a
        stream `sd._terminate()` has already closed raises `PortAudioError
        -9988` from `stop()`, and that raise escaping would leave the playback
        declared for the rest of the session. Every device rebuild afterwards
        would then wait the whole of `DEFER_CAP_S` for a stream nobody is
        using, and this press would reach the driver as `gate.FAILED` - "check
        the log" - rather than as the "say it again" he can act on.
        """
        stream, self._stream = self._stream, None
        capture, self._capture = self._capture, None
        try:
            if stream is not None:
                stream.stop()
                stream.close()
        except Exception as exc:                 # noqa: BLE001 - see above
            log("ptt").info(
                "the microphone stream would not close cleanly (%s: %s) - "
                "which is what a device rebuild having already closed it "
                "looks like from here", type(exc).__name__, exc)
        finally:
            if capture is not None:
                audio_devices.end_playback(capture)
        return capture

    def _feed_tail_silence(self):
        """Give the decoder something after his last word. See `TAIL_PAD_S`.

        Guarded, and deliberately not fatal: if this raises, the transcript is
        the one we would have had anyway - a word short, not absent - and
        losing the whole question over an accuracy improvement would be the
        worse trade.
        """
        try:
            import numpy as np

            quiet = np.zeros(int(self.SAMPLE_RATE * self.TAIL_PAD_S),
                             dtype=np.float32)
            for at in range(0, quiet.size, self.BLOCK):
                self._transcriber.add_audio(
                    quiet[at:at + self.BLOCK].tolist(), self.SAMPLE_RATE)
        except Exception as exc:                 # noqa: BLE001 - see above
            log("ptt").debug("could not pad the tail: %s: %s",
                             type(exc).__name__, exc)

    def end(self) -> str:
        """Button up: close the mic and return what was said, or nothing.

        Empty rather than None on a rejection, so `ask("")` takes the existing
        UNKNOWN path and the engineer says "say again" - the behaviour that was
        already there, reached the same way.
        """
        capture = self._release_capture()

        if capture is not None and capture.interrupted:
            # The app closed his microphone in the middle of his question -
            # see `CUT_BY_REBUILD`. Whatever the decoder holds is the front of
            # a sentence, so it is dropped rather than judged, and he is told
            # once, here, on the way out of the press. Told once and not per
            # attempt: two rebuilds inside one hold both set the same sticky
            # flag, and this reads it a single time.
            self._transcriber.stop()
            self.last_reason = CUT_BY_REBUILD
            log("ptt").warning(
                "a device rebuild closed the microphone while the button was "
                "still held. %.2fs of audio reached the decoder before it "
                "went; a question cannot be asked again on his behalf, so it "
                "is discarded rather than answered and he is asked to say it "
                "again.", self._total_blocks * self.BLOCK / self.SAMPLE_RATE)
            return ""

        if self._truncated:
            log("ptt").info("capture reached the %.0fs limit - transcribing "
                            "what was said up to it", self._max_capture_s)

        seconds = self._total_blocks * self.BLOCK / self.SAMPLE_RATE
        speech = self._speech_blocks * self.BLOCK / self.SAMPLE_RATE
        # `seconds` cannot now exceed the limit, so TOO_LONG will not fire from
        # this recogniser. The check stays: it is the backstop for any other
        # capture source, and it is the stage that decides what to say.
        reason = gate.check_audio(duration_s=seconds, speech_s=speech,
                                  max_capture_s=self._max_capture_s)
        if reason is not None:
            self._transcriber.stop()
            self.last_reason = reason
            log("ptt").info("rejected before transcribing: %s "
                            "(%.2fs captured, %.2fs speech)",
                            reason, seconds, speech)
            return ""

        try:
            self._feed_tail_silence()
            result = self._transcriber.update_transcription()
            text = " ".join(line.text for line in
                            getattr(result, "lines", [])).strip()
        except Exception as exc:                 # noqa: BLE001
            log("ptt").error("transcription failed: %s: %s",
                             type(exc).__name__, exc, exc_info=True)
            text = ""
        finally:
            self._transcriber.stop()

        reason = gate.check_transcript(text, duration_s=seconds)
        if reason is not None:
            self.last_reason = reason
            log("ptt").info("rejected %r: %s", text, reason)
            return ""
        return text

    def close(self) -> None:
        # A press that never gets its button-up - the app shutting down, or
        # the listener being swapped mid-hold - would otherwise leave the
        # declaration standing, and every device rebuild for the rest of the
        # session would wait the whole cap for a microphone nobody is holding.
        if getattr(self, "_capture", None) is not None:
            self._release_capture()
        transcriber = getattr(self, "_transcriber", None)
        if transcriber is not None:
            transcriber.close()


class SemanticMatcher:
    """Routes a transcript to an intent by meaning, and says how close it was.

    This is what replaces the closed grammar. The grammar could not return a
    phrase that was not in it; free dictation can return anything, so the
    defence moves from "could this have been said" to "does this mean one of
    the things he can ask". The distance is the confidence signal that
    `gate.judge()` bands.

    Deliberately not Moonshine's own `AgentFlow` or `intent_recognizer`.
    `AgentFlow` owns the microphone, the speech synthesis and the dialog, and
    handing it the audio stack would break the properties `voice.py` documents
    as hard requirements. `intent_recognizer` does not import at all in 0.1.1 -
    it asks `moonshine_api` for a symbol that release does not define.
    """

    def __init__(self, phrases=None, *, model=None, cache=True) -> None:
        self._phrases = phrases or PHRASES
        # Resolved before the weights are loaded, and remembered, because the
        # cache key needs the path and the model cannot supply it. Skipped
        # entirely when a model is handed in, which is what the tests do.
        self._source = None if model is not None else self._model_source()
        self._model = model if model is not None else self._load(self._source)
        self._embeddings: dict[str, tuple[str, object]] = {}
        if self._model is None:
            return
        if cache and self._load_cached():
            return
        self._embed_phrases()
        if cache:
            self._write_cache()

    # ------------------------------------------------------------ the cache
    #
    # **The whole of this exists because embedding the phrase list cost about
    # twenty seconds of every launch, on the Qt thread, before the window was
    # shown.** Measured 22 Aug 2026: 230 phrases at 66-99 ms each. The comment
    # below reasons about "forty-six short phrases" - the list has grown five
    # times since and the cost assumption never moved with it.
    #
    # The output is deterministic: `PHRASES` is a frozen module constant and
    # the q4 weights are a fixed file, so every launch recomputed the same
    # 230 vectors. It is a pure function of two things that rarely change,
    # which is the definition of something that should be cached rather than
    # threaded - no worker, no handoff, no "still loading" state to get wrong.

    CACHE_VERSION = 1
    # Between a phrase and the next, so that two different phrase lists
    # cannot hash the same by running into each other. A byte no phrase
    # can contain.
    SEPARATOR = bytes([0])

    @staticmethod
    def _cache_path():
        from pitcrew.paths import DATA_DIR

        return DATA_DIR / "ptt_embeddings.npz"

    def _cache_key(self) -> str:
        """What the cached vectors were computed from.

        The phrase list AND the model. A phrase edited, added or removed
        changes the first; a different model or variant changes the second.
        Either one invalidates every vector, so both are in the key and a
        miss simply recomputes.
        """
        import hashlib

        digest = hashlib.sha256()
        digest.update(str(self.CACHE_VERSION).encode())
        for intent in sorted(self._phrases):
            digest.update(intent.encode("utf-8"))
            for phrase in self._phrases[intent]:
                digest.update(self.SEPARATOR)
                digest.update(phrase.encode("utf-8"))
        # **From the source, not from the model.** This read
        # `getattr(self._model, "model_path", ...)` and `EmbeddingModel` has
        # no such attribute - nothing on it matches `*path*` - so the model
        # contributed NOTHING to the key and swapping it would have been
        # answered from the old one's vectors. The unit test passed only
        # because its fake carried an attribute the real class does not,
        # which is the shape of a test that assures you of nothing.
        #
        # A test model handed in directly still gets whatever it declares, so
        # the fakes keep working; the real path is resolved once and costs
        # 53 ms against the 753 ms of loading the weights it names.
        model_file = (getattr(self._model, "model_path", None)
                      or getattr(self._model, "path", None))
        if model_file is None:
            source = self._source if self._source is not None \
                else self._model_source()
            model_file = source[0] if source else None
        if model_file:
            digest.update(str(model_file).encode("utf-8"))
            # **Size and mtime only for a FILE, never for the directory.**
            # `get_embedding_model` returns a DIRECTORY, and loading the
            # weights creates and removes lock files inside it -
            # `model_q4.ort.lock`, `tokenizer.bin.lock` - so its mtime moves
            # on every single load. Stat'ing it made the key different every
            # run: the cache was written, never matched, and recomputed for
            # fifteen seconds each launch while appearing to work.
            #
            # The path names the model and the variant, which is the identity
            # that matters. `CACHE_VERSION` covers a deliberate change of
            # what is stored; a model replaced in place under the same name
            # is the one case neither catches, and is not one that happens
            # without someone knowing.
            try:
                found = pathlib.Path(str(model_file))
                if found.is_file():
                    stat = found.stat()
                    digest.update(f":{stat.st_size}:{stat.st_mtime_ns}"
                                  .encode("utf-8"))
            except OSError:
                pass
        return digest.hexdigest()

    def _load_cached(self) -> bool:
        path = self._cache_path()
        try:
            if not path.exists():
                return False
            import numpy as np

            with np.load(path, allow_pickle=False) as stored:
                if str(stored["key"]) != self._cache_key():
                    log("ptt").info(
                        "the phrase embeddings on disk are for a different "
                        "phrase list or model - recomputing them")
                    return False
                phrases = [str(p) for p in stored["phrases"]]
                intents = [str(i) for i in stored["intents"]]
                vectors = stored["vectors"]
            # Back to lists, which is what `calculate_embedding` returns and
            # therefore what `distance` has always been handed. Verified to
            # give a bit-identical distance either way, but matching the type
            # the model produces costs nothing and removes the question.
            self._embeddings = {
                phrase: (intent, vectors[row].tolist())
                for row, (phrase, intent) in enumerate(zip(phrases, intents))}
        except Exception as exc:                 # noqa: BLE001
            # A cache that will not load is not a failure - it is a slow
            # start. Never let it be more than that.
            log("ptt").info("could not read the phrase embeddings (%s: %s) - "
                            "recomputing them", type(exc).__name__, exc)
            self._embeddings = {}
            return False
        log("ptt").info("phrase embeddings read from %s (%d phrases)",
                        path.name, len(self._embeddings))
        return bool(self._embeddings)

    def _write_cache(self) -> None:
        if not self._embeddings:
            return
        path = self._cache_path()
        try:
            import numpy as np

            phrases = list(self._embeddings)
            intents = [self._embeddings[p][0] for p in phrases]
            vectors = np.asarray([self._embeddings[p][1] for p in phrases],
                                 dtype=np.float32)
            path.parent.mkdir(parents=True, exist_ok=True)
            # Written beside itself and moved into place, so a launch
            # interrupted here leaves the old cache rather than half a file.
            spare = path.with_suffix(".npz.tmp")
            with open(spare, "wb") as handle:
                np.savez_compressed(handle, key=np.array(self._cache_key()),
                                    phrases=np.array(phrases),
                                    intents=np.array(intents),
                                    vectors=vectors)
            spare.replace(path)
            log("ptt").info("phrase embeddings written to %s (%d phrases)",
                            path.name, len(phrases))
        except Exception as exc:                 # noqa: BLE001
            log("ptt").info("could not save the phrase embeddings (%s: %s) - "
                            "they will be recomputed next time",
                            type(exc).__name__, exc)

    @staticmethod
    def _model_source() -> tuple | None:
        """Where the weights are, WITHOUT loading them.

        Split out because the two halves cost wildly different amounts and
        the cheap half is what the cache key needs: measured 53 ms to resolve
        the path against 753 ms to construct the model from it.

        **The cache key needs the path and cannot get it from the model.**
        `EmbeddingModel` exposes no path attribute at all - checked, there is
        nothing on it matching `*path*` - so keying on `getattr(model,
        "model_path", ...)` silently contributed NOTHING, and a change of
        model or variant would have been answered from the old model's
        vectors. Every distance would then be measured in the wrong space,
        quietly, and the only symptom is the engineer mishearing him.
        """
        try:
            import moonshine_voice as moonshine

            # Returns (path, arch), and the q4 variant is 200 MB against
            # 1.2 GB for fp32 - a sensible weight for deciding between a
            # couple of hundred short phrases.
            return moonshine.get_embedding_model(variant="q4")
        except Exception as exc:                 # noqa: BLE001
            log("ptt").info("no embedding model available (%s: %s)",
                            type(exc).__name__, exc)
            return None

    @staticmethod
    def _load(source: tuple | None = None):
        try:
            from moonshine_voice.embedding_model import EmbeddingModel

            found = source or SemanticMatcher._model_source()
            if found is None:
                return None
            path, arch = found
            # The variant has to be passed here as well as to the download:
            # the q4 weights land as `model_q4.ort` and the loader looks for
            # `model.ort` unless it is told which one it wants.
            return EmbeddingModel(path, arch, "q4")
        except Exception as exc:                 # noqa: BLE001
            log("ptt").info(
                "no semantic matcher (%s: %s) - falling back to literal "
                "phrase matching", type(exc).__name__, exc)
            return None

    @property
    def available(self) -> bool:
        return self._model is not None and bool(self._embeddings)

    def _embed_phrases(self) -> None:
        for intent, phrases in self._phrases.items():
            for phrase in phrases:
                try:
                    self._embeddings[phrase] = (
                        intent, self._model.calculate_embedding(phrase))
                except Exception as exc:         # noqa: BLE001
                    log("ptt").warning("could not embed %r: %s", phrase, exc)

    def match(self, heard: str):
        """(intent, distance). Distance is None when there is no model, and
        the caller then trusts the literal match instead."""
        if not heard or not self.available:
            return match_intent(heard), None
        try:
            probe = self._model.calculate_embedding(heard)
        except Exception as exc:                 # noqa: BLE001
            log("ptt").warning("embedding failed for %r: %s", heard, exc)
            return match_intent(heard), None

        # Moonshine's `distance()` is misnamed: it returns cosine SIMILARITY,
        # where higher means closer. Measured: "when do i box" against "when
        # box" is 0.786, and against "the fridge is making a noise" 0.392.
        # It is converted here so that everything downstream reads the way it
        # says it does - `gate.judge` bands a distance, and smaller is closer.
        best_intent, best_similarity = UNKNOWN, None
        for intent, embedding in self._embeddings.values():
            similarity = self._model.distance(probe, embedding)
            if best_similarity is None or similarity > best_similarity:
                best_intent, best_similarity = intent, similarity
        if best_similarity is None:
            return match_intent(heard), None
        return best_intent, 1.0 - best_similarity


def best_semantic_matcher():
    """A semantic matcher, or None where the model is not available."""
    matcher = SemanticMatcher()
    return matcher if matcher.available else None


# Recognisers that cannot return a phrase outside the list they were built
# with. Exact by construction, so they need no semantic gate - and every other
# recogniser does, including any added later, which is why this is a list of
# the exceptions rather than a list of the engines that need one.
CLOSED_GRAMMAR = (SapiGrammarRecogniser.name,)


def matcher_for(recogniser):
    """The semantic gate the recogniser that was actually BUILT needs.

    Not the one the setting asked for. The chain falls back - SAPI is the
    shipped default and it genuinely fails on this machine, timing out after
    five seconds - so choosing the matcher from `settings.speech_backend`
    means the app runs Moonshine free dictation with `matcher=None`, and
    `gate.judge` short-circuits on `distance is None` straight to ACT, past
    all five stages. The recogniser knows what it is: both classes carry
    `name`. Ask it.
    """
    if recogniser is None:
        return None
    if getattr(recogniser, "name", "") in CLOSED_GRAMMAR:
        return None
    return best_semantic_matcher()


# How long a recogniser gets to come up before the app gives up on it.
#
# This is a deadline, not a courtesy. `Dispatch("SAPI.SpSharedRecognizer")`
# does not raise when Windows Speech Recognition is unconfigured - it never
# returns at all, which `except Exception` cannot catch. Measured on this
# machine: the call was still blocked after 60 s, outside pytest, with no Qt
# event loop involved. Since `Controller.__init__` builds the recogniser and
# the default backend is SAPI, that hang is the app failing to start.
RECOGNISER_TIMEOUT_S = 5.0


def _under_pytest() -> bool:
    """Whether a test is driving us right now.

    Tests build a Controller dozens of times and must not each pay a five
    second speech probe, nor depend on how Windows Speech happens to be
    configured on the machine running them. A test that wants a recogniser
    injects one; `PushToTalk` already takes it as an argument.
    """
    return "PYTEST_CURRENT_TEST" in os.environ


class LateArrival:
    """A recogniser that is still loading, and will be usable when it lands.

    **The deadline was discarding work that finished a second later.** Over ten
    days of logs, `MoonshineRecogniser` timed out thirteen times - and it loads
    in 2.3 to 2.7 seconds every time it is measured on its own. What beat it
    was boot contention, not the model: a five second race lost by half a
    second left push-to-talk dead for the whole session, while the loaded model
    sat in an abandoned thread with nobody holding it.

    So the deadline now stops the app *blocking*. It does not stop the load.
    The probe thread keeps going, and the first press after it finishes gets a
    working recogniser - which is the difference between a race with no radio
    and a race whose radio works from lap two.
    """

    #: Factory name -> the `name` the built recogniser will report. Callers
    #: branch on that name (`free_dictation`, `CLOSED_GRAMMAR`), so answering
    #: with the factory's name while it loads would build the wrong matcher.
    NAMES = {"MoonshineRecogniser": "moonshine",
             "SapiGrammarRecogniser": "sapi-grammar"}

    def __init__(self, outcome: dict, thread, name: str) -> None:
        self._outcome = outcome
        self._thread = thread
        self._name = self.NAMES.get(name, name)
        self._announced = False

    @property
    def _real(self):
        got = self._outcome.get("value")
        if got is not None and not self._announced:
            self._announced = True
            log("ptt").info("%s arrived late and is now available", self._name)
        return got

    @property
    def name(self) -> str:
        real = self._real
        return getattr(real, "name", self._name) if real else self._name

    @property
    def last_reason(self):
        real = self._real
        return getattr(real, "last_reason", None) if real else gate.NOT_READY

    def begin(self) -> None:
        real = self._real
        if real is not None:
            real.begin()

    def end(self):
        """The transcript, or nothing and a reason he can act on."""
        real = self._real
        if real is None:
            return ""
        return real.end()


def build_within(factory, timeout_s: float, *args):
    """Construct on a side thread, or hand back one that is still coming.

    The thread is deliberately left running when the deadline passes. A blocked
    COM call cannot be cancelled from outside, so the only honest options are
    to abandon the *wait* or to hang with it - and it is a daemon, so leaving
    it running does not keep the process alive at exit.

    What it no longer does is abandon the *result*. See `LateArrival`.
    """
    outcome: dict = {}

    def attempt() -> None:
        try:
            outcome["value"] = factory(*args)
        except BaseException as exc:              # noqa: BLE001
            outcome["error"] = exc

    probe = threading.Thread(target=attempt, daemon=True,
                             name=f"probe-{factory.__name__}")
    probe.start()
    probe.join(timeout_s)
    if probe.is_alive():
        return LateArrival(outcome, probe, factory.__name__)
    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("value")


def best_recogniser_for(backend: str, phrases=None):
    """The recogniser the driver asked for, or the next one that loads.

    ### What ten days of logs say

    `SapiGrammarRecogniser` was tried first on **fifty-nine consecutive
    launches and came up on none of them.** It does not raise: measured here,
    `Dispatch("SAPI.SpSharedRecognizer")` was still blocked after four minutes
    with no Qt event loop involved. `MoonshineRecogniser`, measured on its own,
    comes up in 2.3 to 2.7 seconds every time.

    So SAPI is no longer tried first for anyone who has not asked for it by
    name. Trying it first cost five seconds of every launch and then handed
    Moonshine a contended machine to load on - which is how a model that takes
    2.3 seconds managed to miss a five second deadline thirteen times.

    ### Why a candidate that is still loading does not win

    `build_within` now returns a `LateArrival` rather than raising, so a
    candidate that is merely slow is kept. But a `LateArrival` from SAPI would
    otherwise pre-empt a Moonshine that is ready **now**, and SAPI's late
    arrival never comes. So the loop prefers anything that is genuinely up, and
    falls back to the first still-loading candidate only when nothing is.
    """
    if _under_pytest():
        return None

    order = ((SapiGrammarRecogniser, MoonshineRecogniser)
             if backend == SPEECH_SAPI
             else (MoonshineRecogniser, SapiGrammarRecogniser))
    still_coming = None
    for factory in order:
        args = (phrases,) if factory is SapiGrammarRecogniser else ()
        try:
            built = build_within(factory, RECOGNISER_TIMEOUT_S, *args)
        except Exception as exc:                  # noqa: BLE001
            log("ptt").warning("%s unavailable: %s: %s", factory.__name__,
                               type(exc).__name__, exc)
            continue
        if isinstance(built, LateArrival):
            log("ptt").info("%s is still loading after %.0fs - keeping it and "
                            "trying the next one", factory.__name__,
                            RECOGNISER_TIMEOUT_S)
            still_coming = still_coming or built
            continue
        if built is not None:
            return built
    return still_coming
