"""Push to talk.

Hold the button, ask, let go, get an answer. The driver is in a headset with
his hands on the wheel, so this is the only way he can ask anything.

The recogniser is deliberately a **bounded grammar**, not free dictation.
Windows' SAPI recogniser is given the exact phrase list from `intents` and will
only return one of them, which turns "did it hear me correctly" into "did it
hear me at all". Free dictation at racing speed with engine noise produces
confident nonsense, and confident nonsense is the one thing an engineer must
never produce.

Input and recognition are both injectable, so the whole path can be driven in
tests, and so a machine without a microphone still runs the app.
"""
from __future__ import annotations

import threading

from pitcrew.engineer.intents import answer, known_phrases, match_intent

# How long the driver can hold the button before we stop listening anyway.
MAX_CAPTURE_S = 6.0
SAMPLE_RATE = 16_000


class PushToTalk:
    """Ties the button, the recogniser and the answer together."""

    def __init__(self, *, snapshot, speak, recogniser=None, listener=None,
                 on_answer=None) -> None:
        self._snapshot = snapshot          # callable -> dict
        self._speak = speak                # callable(str)
        self._recogniser = recogniser
        self._listener = listener
        self._on_answer = on_answer
        self._busy = threading.Lock()
        self.last_call: str | None = None
        self.pending_replan: str | None = None
        self.transcript: list[tuple[str, str]] = []   # (heard, said)

    @property
    def available(self) -> bool:
        return self._recogniser is not None

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
        """Answer a question already turned into text. The testable seam."""
        intent = match_intent(heard)
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
        print(f"[ptt] speech recognition unavailable: "
              f"{type(exc).__name__}: {exc}")
        return None


def best_listener(key: str = "f8"):
    try:
        return KeyboardListener(key)
    except Exception as exc:                    # noqa: BLE001
        print(f"[ptt] no keyboard hook: {type(exc).__name__}: {exc}")
        return None
