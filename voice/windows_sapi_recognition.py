"""Concrete offline Windows SAPI recognition adapter (Program 2, Phase 67).

Implements the Phase-64 ``SpeechRecognitionPort`` using the OFFLINE Windows SAPI 5.4 in-process recogniser
(win32com — the same COM stack the project already uses for TTS). It is grammar-based (the deterministic
Phase-64 command phrases), PTT-controlled (recognition is only polled while PTT is held), never listens
continuously, persists no raw audio, and never contacts a network or a cloud service.

HONEST LIMITATION
  Windows SAPI dictation/recognition reliability varies by machine and installed language pack; free-form
  natural-language understanding is NOT provided. This adapter attempts a fixed command grammar and returns
  the recognised phrase + confidence for the Phase-64 grammar to classify. Where the local SAPI recogniser
  is unavailable or unreliable, ``is_available`` is False and the app falls back to the deterministic fake
  / disabled port. This is recorded in the certification as needing physical-microphone UAT — it is never
  presented as certified.

Safety: offline; lazy win32com import (importing on a non-Windows box never fails); disabled + silent on
construction; never raises into the caller.
"""
from __future__ import annotations

from typing import List, Optional, Sequence

from voice.speech_recognition_port import (
    SpeechRecognitionPort, RecognitionResult, RecognitionKind,
)


class WindowsSapiRecognitionPort(SpeechRecognitionPort):
    """Offline SAPI in-process command-grammar recogniser. Disabled until :meth:`enable` succeeds; a
    reliability failure permanently falls back (visual + fake-port). PTT-gated: :meth:`recognize` returns
    the most recent recognised command captured while listening, else None."""

    name = "windows_sapi_recognition"
    recognition_kind = RecognitionKind.COMMAND_GRAMMAR

    def __init__(self, phrases: Optional[Sequence[str]] = None):
        self._phrases = tuple(str(p) for p in (phrases or _default_phrases()))
        self._ctx = None
        self._grammar = None
        self._recognizer = None
        self._enabled = False
        self._failed = False
        self._pending: List[RecognitionResult] = []

    def enable(self) -> bool:
        """Initialise the offline in-process recogniser + command grammar. Never raises. Returns True only
        when a local recogniser genuinely initialised."""
        if self._failed:
            return False
        try:
            import win32com.client  # lazy; Windows-only, offline SAPI

            # In-process recogniser keeps recognition local to this app (no shared OS recogniser UI).
            self._recognizer = win32com.client.Dispatch("SAPI.SpInprocRecognizer")
            self._ctx = self._recognizer.CreateRecoContext()
            self._grammar = self._ctx.CreateGrammar()
            # Build a rule from the fixed command phrases (command-and-control, not dictation).
            rule = self._grammar.Rules.Add("ptt_commands", 0x1 | 0x20)  # TopLevel | Dynamic
            for ph in self._phrases:
                rule.InitialState.AddWordTransition(None, ph)
            self._grammar.Rules.Commit()
            self._grammar.CmdSetRuleState("ptt_commands", 0)  # inactive until listening (PTT held)
            self._enabled = True
            return True
        except Exception:
            self._recognizer = self._ctx = self._grammar = None
            self._enabled = False
            self._failed = True
            return False

    def is_available(self) -> bool:
        return bool(self._enabled and self._grammar is not None and not self._failed)

    def start_listening(self) -> None:
        """Activate the grammar (called when PTT is pressed). Never continuous — deactivated on release."""
        try:
            if self.is_available():
                self._grammar.CmdSetRuleState("ptt_commands", 1)  # active
        except Exception:
            self._failed = True

    def stop_listening(self) -> None:
        try:
            if self._grammar is not None:
                self._grammar.CmdSetRuleState("ptt_commands", 0)  # inactive
        except Exception:
            pass

    def push_recognition(self, text: str, confidence: float) -> None:
        """SAPI recognition-event sink hook (wired by the controller). Kept tiny + deterministic; stores no
        raw audio, only the recognised phrase + confidence."""
        if str(text or "").strip():
            self._pending.append(RecognitionResult(text=str(text), confidence=float(confidence), final=True))

    def recognize(self) -> Optional[RecognitionResult]:
        """Return the most recent recognised command (consumed once) while PTT was held, else None."""
        if not self.is_available() or not self._pending:
            return None
        return self._pending.pop(0)

    def shutdown(self) -> None:
        self.stop_listening()
        self._recognizer = self._ctx = self._grammar = None
        self._enabled = False
        self._pending = []


def _default_phrases() -> List[str]:
    """The fixed command phrases the grammar recognises (mirrors the Phase-64 deterministic grammar)."""
    try:
        from strategy.push_to_talk import _GRAMMAR
        out: List[str] = []
        for _action, _klass, phrases in _GRAMMAR:
            out.extend(phrases)
        # de-dup preserving order
        seen = set()
        uniq = []
        for p in out:
            if p not in seen:
                seen.add(p)
                uniq.append(p)
        return uniq
    except Exception:  # pragma: no cover - defensive
        return ["acknowledge", "repeat", "status", "current plan", "next pit window",
                "strategy update", "rain starting", "mute coaching"]
