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
"""
from __future__ import annotations

import os
import threading

from pitcrew.diagnostics import log
from pitcrew.engineer import gate
from pitcrew.engineer.intents import (
    PHRASES,
    UNKNOWN,
    answer,
    known_phrases,
    match_intent,
)

# How long the driver can hold the button before we stop listening anyway.
MAX_CAPTURE_S = 6.0
SAMPLE_RATE = 16_000

# Answers to "did you mean X?". One syllable each, because he is mid-corner
# and both hands are busy. Kept separate from the ACCEPT/KEEP intents, which
# are about a re-plan offer rather than about what the engineer just heard.
_YES = {"yes", "yeah", "yep", "correct", "affirmative", "right", "copy"}
_NO = {"no", "nope", "negative", "wrong"}


class PushToTalk:
    """Ties the button, the recogniser and the answer together."""

    def __init__(self, *, snapshot, speak, recogniser=None, listener=None,
                 on_answer=None, matcher=None,
                 sensitivity: str = gate.DEFAULT_SENSITIVITY) -> None:
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

    @property
    def available(self) -> bool:
        return self._recogniser is not None

    @property
    def has_listener(self) -> bool:
        """Whether the button can be read at all on this machine."""
        return self._listener is not None

    def set_listener(self, listener) -> None:
        """Swap the button. The old hook is stopped first, or it keeps firing
        on the key the driver just changed away from."""
        if self._listener is not None:
            self._listener.stop()
        self._listener = listener

    def start(self) -> None:
        if self._listener is not None:
            self._listener.start(self.begin, self.end)

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()

    # ------------------------------------------------------------- the cycle

    def begin(self) -> None:
        """Button down."""
        if self._recogniser is not None:
            self._recogniser.begin()

    def end(self) -> None:
        """Button up: recognise what was said and answer it."""
        if self._recogniser is None:
            self._reply("Speech isn't available on this machine.", "")
            return
        # One question at a time; a second press while answering is ignored
        # rather than queued, because the answer to the first is already stale.
        if not self._busy.acquire(blocking=False):
            return
        try:
            heard = self._recogniser.end() or ""
            self.ask(heard)
        finally:
            self._busy.release()

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

    def __init__(self, *, max_capture_s: float = MAX_CAPTURE_S,
                 silence_rms: float = 0.012) -> None:
        import numpy  # noqa: F401 - the capture path is numpy throughout
        import sounddevice  # noqa: F401
        import moonshine_voice as moonshine
        from moonshine_voice.moonshine_api import ModelArch
        from moonshine_voice.transcriber import Transcriber

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
        self._speech_blocks = 0
        self._total_blocks = 0
        self.last_reason: str | None = None

    def begin(self) -> None:
        """Button down: open the mic and start feeding the decoder."""
        import numpy as np
        import sounddevice as sd

        self._speech_blocks = 0
        self._total_blocks = 0
        self.last_reason = None
        self._transcriber.start()

        def on_audio(indata, _frames, _time, status) -> None:
            if status:
                log("ptt").debug("capture status: %s", status)
            block = np.asarray(indata, dtype=np.float32).reshape(-1)
            self._total_blocks += 1
            if float(np.sqrt(np.mean(block * block))) >= self._silence_rms:
                self._speech_blocks += 1
            try:
                self._transcriber.add_audio(block.tolist(), self.SAMPLE_RATE)
            except Exception as exc:             # noqa: BLE001
                # On the audio callback thread: raising here kills the stream
                # mid-question, and PortAudio takes the process with it.
                log("ptt").warning("add_audio raised: %s: %s",
                                   type(exc).__name__, exc)

        self._stream = sd.InputStream(
            samplerate=self.SAMPLE_RATE, channels=1, dtype="float32",
            blocksize=self.BLOCK, callback=on_audio)
        self._stream.start()

    def end(self) -> str:
        """Button up: close the mic and return what was said, or nothing.

        Empty rather than None on a rejection, so `ask("")` takes the existing
        UNKNOWN path and the engineer says "say again" - the behaviour that was
        already there, reached the same way.
        """
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None

        seconds = self._total_blocks * self.BLOCK / self.SAMPLE_RATE
        speech = self._speech_blocks * self.BLOCK / self.SAMPLE_RATE
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

    def __init__(self, phrases=None, *, model=None) -> None:
        self._phrases = phrases or PHRASES
        self._model = model if model is not None else self._load()
        self._embeddings: dict[str, tuple[str, object]] = {}
        if self._model is not None:
            self._embed_phrases()

    @staticmethod
    def _load():
        try:
            import moonshine_voice as moonshine
            from moonshine_voice.embedding_model import EmbeddingModel

            # Returns (path, arch), and the q4 variant is 200 MB against
            # 1.2 GB for fp32 - a sensible weight for deciding between
            # forty-six short phrases.
            path, arch = moonshine.get_embedding_model(variant="q4")
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


def build_within(factory, timeout_s: float, *args):
    """Construct on a side thread, or give up when the deadline passes.

    The thread is deliberately left running when it times out. A blocked COM
    call cannot be cancelled from outside, so the only honest options are to
    abandon it or to hang with it - and it is a daemon, so abandoning it does
    not keep the process alive at exit.
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
        raise TimeoutError(
            f"{factory.__name__} did not come up within {timeout_s:.0f}s "
            f"and was abandoned")
    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("value")


def best_recogniser_for(backend: str, phrases=None):
    """The recogniser the driver asked for, or the next one that loads.

    Moonshine first when it is chosen, then SAPI, then nothing - and nothing
    is a running app that says "speech isn't available on this machine"
    rather than one that will not start.

    Each candidate is built under a deadline, because "will not start" turned
    out to include the case this fallback chain was written to prevent: SAPI
    hanging rather than raising meant the chain never advanced to Moonshine
    and the app never opened a window.
    """
    if _under_pytest():
        return None

    order = ((MoonshineRecogniser, SapiGrammarRecogniser)
             if backend == "moonshine"
             else (SapiGrammarRecogniser, MoonshineRecogniser))
    for factory in order:
        args = (phrases,) if factory is SapiGrammarRecogniser else ()
        try:
            return build_within(factory, RECOGNISER_TIMEOUT_S, *args)
        except Exception as exc:                 # noqa: BLE001
            log("ptt").warning("%s unavailable: %s: %s", factory.__name__,
                               type(exc).__name__, exc)
    return None
