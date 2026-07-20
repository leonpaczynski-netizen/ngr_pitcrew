"""Windows offline voice adapter for race-engineer advisories (Program 2, Phase 47).

The ONLY module that binds advisory voice delivery to a concrete offline Windows TTS engine. It
implements the pure ``strategy.voice_delivery.VoiceOutputPort`` using the SAME offline Windows SAPI5
engine (win32com) the project already uses for the pit announcer - it introduces no new / cloud TTS,
no external API and no network. It imports win32com LAZILY so importing this module never fails on a
non-Windows box and never speaks on import.

Failure behaviour: on any adapter error the port disables itself (``is_available`` becomes False) and
returns False from ``speak`` - callers fall back to visual-only. It never raises into the caller and
never retries continuously.

Safety: offline only. Speaks nothing on construction. No API keys, no cloud, no LLM.
"""
from __future__ import annotations

from strategy.voice_delivery import VoiceOutputPort


class WindowsOfflineVoicePort(VoiceOutputPort):
    """Offline SAPI5 (win32com) voice port. Disabled + silent until :meth:`enable` is called and the
    engine initialises successfully. Any unrecoverable failure permanently disables the port for the
    session (visual-only fallback)."""

    name = "windows_sapi5_offline"

    def __init__(self, *, rate: int = 0, volume: int = 100):
        self._voice = None
        self._enabled = False
        self._failed = False
        self._rate = int(rate)
        self._volume = int(max(0, min(100, volume)))

    def enable(self) -> bool:
        """Explicitly initialise the offline engine. Returns True on success. Never raises."""
        if self._failed:
            return False
        try:
            import win32com.client  # lazy; Windows-only, offline SAPI5
            self._voice = win32com.client.Dispatch("SAPI.SpVoice")
            try:
                self._voice.Rate = self._rate
                self._voice.Volume = self._volume
            except Exception:
                pass
            self._enabled = True
            return True
        except Exception:
            self._voice = None
            self._enabled = False
            self._failed = True
            return False

    def disable(self) -> None:
        self._enabled = False
        try:
            self.stop()
        except Exception:
            pass

    def is_available(self) -> bool:
        return bool(self._enabled and self._voice is not None and not self._failed)

    def speak(self, message: str) -> bool:
        """Speak the EXACT approved message asynchronously. Returns False (and disables the port) on any
        failure - never raises."""
        if not self.is_available() or not str(message or "").strip():
            return False
        try:
            # SVSFlagsAsync (1) so a stop-critical interrupt can pre-empt; SVSFPurgeBeforeSpeak (2).
            self._voice.Speak(str(message), 1)
            return True
        except Exception:
            self._failed = True
            self._enabled = True and False
            return False

    def stop(self) -> None:
        try:
            if self._voice is not None:
                self._voice.Speak("", 3)   # async + purge => stops current utterance
        except Exception:
            self._failed = True

    def set_rate(self, rate: int) -> None:
        self._rate = int(rate)
        try:
            if self._voice is not None:
                self._voice.Rate = self._rate
        except Exception:
            pass

    def set_volume(self, volume: int) -> None:
        self._volume = int(max(0, min(100, volume)))
        try:
            if self._voice is not None:
                self._voice.Volume = self._volume
        except Exception:
            pass


def make_voice_port(kind: str = "disabled", **kwargs) -> VoiceOutputPort:
    """Factory. Default 'disabled' (silent). 'windows' returns the offline SAPI5 port (still disabled
    until enable()). 'fake' returns the deterministic test port. Never raises."""
    k = str(kind or "disabled").lower()
    try:
        if k == "windows":
            return WindowsOfflineVoicePort(**kwargs)
        if k == "fake":
            from strategy.voice_delivery import FakeVoicePort
            return FakeVoicePort(**kwargs)
        from strategy.voice_delivery import DisabledVoicePort
        return DisabledVoicePort()
    except Exception:  # pragma: no cover - defensive
        from strategy.voice_delivery import DisabledVoicePort
        return DisabledVoicePort()
