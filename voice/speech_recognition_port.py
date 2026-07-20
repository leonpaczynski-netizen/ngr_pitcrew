"""Offline speech-recognition port (Program 2, Phase 64).

A pure recognition PORT with a DISABLED default and a deterministic fake for tests. Recognition is
OFFLINE-ONLY: no cloud speech API, no network, no API key, no remote transcript upload. A concrete local
Windows offline adapter may be added later behind this boundary.

If reliable free-form local dictation is not implemented, the deterministic command grammar in
``strategy.push_to_talk`` is the honest capability, and this port yields transcripts + confidence that the
grammar classifies. This module NEVER pretends a command grammar is natural-language understanding —
callers read ``recognition_kind`` to report the true capability.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple


class RecognitionKind:
    NONE = "none"
    COMMAND_GRAMMAR = "command_grammar"     # deterministic fixed-phrase grammar (the honest local default)
    LOCAL_DICTATION = "local_dictation"     # a real local free-form recogniser (only if genuinely reliable)


@dataclass(frozen=True)
class RecognitionResult:
    text: str
    confidence: float
    final: bool = True


class SpeechRecognitionPort:
    """Abstract offline recogniser. ``recognize`` is called with a captured audio window while PTT is held
    and returns a transcript + confidence; implementations must never raise, never touch the network, and
    never upload audio."""

    name = "abstract"
    recognition_kind = RecognitionKind.NONE

    def is_available(self) -> bool:  # pragma: no cover - interface
        return False

    def recognize(self) -> Optional[RecognitionResult]:  # pragma: no cover - interface
        return None

    def shutdown(self) -> None:  # pragma: no cover - interface
        pass


class DisabledSpeechRecognitionPort(SpeechRecognitionPort):
    """The DEFAULT: no recogniser. Recognises nothing."""

    name = "disabled"
    recognition_kind = RecognitionKind.NONE

    def is_available(self) -> bool:
        return False

    def recognize(self) -> Optional[RecognitionResult]:
        return None

    def shutdown(self) -> None:
        pass


class FakeSpeechRecognitionPort(SpeechRecognitionPort):
    """Deterministic test adapter. A scripted queue of (text, confidence) results is returned in order;
    can simulate an unavailable device or a recognition failure (a None result)."""

    name = "fake"
    recognition_kind = RecognitionKind.COMMAND_GRAMMAR

    def __init__(self, scripted: Optional[Sequence[Tuple[str, float]]] = None, *, available: bool = True):
        self._available = bool(available)
        self._queue: List[Tuple[str, float]] = list(scripted or [])
        self.recognize_calls = 0
        self.shutdowns = 0

    def is_available(self) -> bool:
        return self._available

    def push(self, text: str, confidence: float) -> None:
        self._queue.append((str(text), float(confidence)))

    def recognize(self) -> Optional[RecognitionResult]:
        self.recognize_calls += 1
        if not self._available or not self._queue:
            return None
        text, conf = self._queue.pop(0)
        if text is None:
            return None
        return RecognitionResult(text=str(text), confidence=float(conf), final=True)

    def shutdown(self) -> None:
        self._queue.clear()
        self.shutdowns += 1
