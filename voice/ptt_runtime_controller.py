"""PTT runtime controller (Program 2, Phase 67).

The impure boundary that drives the PTT lifecycle: it polls a ``PushToTalkInputPort`` (press-and-hold or
toggle), gates a ``SpeechRecognitionPort`` so the mic is active ONLY while PTT is held, classifies a
recognised utterance with the deterministic Phase-64 grammar, applies the Phase-67 PTT/TTS coordination to
the Phase-47 ``VoiceController`` (pause routine speech, preserve urgent), and rejects stale recognition
after an event/activity change. Deterministic given the injected port states; never raises; installs no
global hook; persists no raw audio; makes no engineering mutation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from strategy.push_to_talk import (
    PushToTalkState, DriverUtterance, DriverCommandIntent, recognize_command, decide_readback,
)
from strategy.ptt_tts_coordination import decide_ptt_tts_action, is_stale_recognition, PttTtsAction


@dataclass(frozen=True)
class PttLifecycleResult:
    state: str
    intent: Optional[dict]
    readback: Optional[dict]
    coordination: str
    stale_rejected: bool
    reason: str

    def to_dict(self) -> dict:
        return {"state": self.state, "intent": self.intent, "readback": self.readback,
                "coordination": self.coordination, "stale_rejected": bool(self.stale_rejected),
                "reason": self.reason}


class PttRuntimeController:
    """Drives one PTT input + recognition port against a VoiceController. Poll it from the UI cadence.
    ``voice_controller`` is optional (coordination is skipped if absent)."""

    def __init__(self, input_port, recognition_port=None, voice_controller=None):
        self._input = input_port
        self._recog = recognition_port
        self._vc = voice_controller
        self._was_pressed = False
        self._state = PushToTalkState.IDLE

    @property
    def available(self) -> bool:
        try:
            return bool(self._input is not None and self._input.is_available())
        except Exception:  # pragma: no cover - defensive
            return False

    def poll(self, *, nav_key=None, current_nav_key=None,
             active_message_priority: Optional[int] = None) -> PttLifecycleResult:
        """Poll one PTT cycle. On a press edge: start listening + pause routine speech. On a release edge:
        stop listening, recognise, classify, decide read-back, reject stale recognition. Never raises."""
        try:
            if not self.available:
                self._state = PushToTalkState.UNAVAILABLE
                return PttLifecycleResult(self._state.value, None, None, PttTtsAction.NONE.value, False,
                                          "no PTT input device / recogniser")
            pressed = bool(self._input.is_pressed())
            press_edge = pressed and not self._was_pressed
            release_edge = (not pressed) and self._was_pressed
            self._was_pressed = pressed

            if press_edge:
                self._state = PushToTalkState.LISTENING
                try:
                    if self._recog is not None and hasattr(self._recog, "start_listening"):
                        self._recog.start_listening()
                except Exception:
                    pass
                coord = decide_ptt_tts_action(ptt_active=True,
                                              active_message_priority=active_message_priority)
                self._apply_coordination(coord.action)
                return PttLifecycleResult(self._state.value, None, None, coord.action, False,
                                          "PTT pressed — listening")

            if release_edge:
                try:
                    if self._recog is not None and hasattr(self._recog, "stop_listening"):
                        self._recog.stop_listening()
                except Exception:
                    pass
                self._state = PushToTalkState.RECOGNISING
                result = self._recog.recognize() if self._recog is not None else None
                coord = decide_ptt_tts_action(ptt_active=False, just_released=True)
                self._apply_coordination(coord.action)
                if result is None:
                    self._state = PushToTalkState.TIMED_OUT
                    return PttLifecycleResult(self._state.value, None, None, coord.action, False,
                                              "no recognition")
                # stale recognition after an event/activity switch is rejected.
                if is_stale_recognition(nav_key, current_nav_key):
                    self._state = PushToTalkState.CANCELLED
                    return PttLifecycleResult(self._state.value, None, None, coord.action, True,
                                              "stale recognition rejected (event/activity changed)")
                intent = recognize_command(DriverUtterance(text=result.text, confidence=result.confidence,
                                                           ptt_held=True))
                if intent.ambiguous or intent.command_class.value == "unrecognised":
                    self._state = PushToTalkState.AMBIGUOUS
                    return PttLifecycleResult(self._state.value, intent.to_dict(), None, coord.action,
                                              False, "ambiguous recognition")
                rb = decide_readback(intent)
                self._state = (PushToTalkState.AWAITING_CONFIRMATION if rb.required
                               else PushToTalkState.RECOGNISED)
                return PttLifecycleResult(self._state.value, intent.to_dict(),
                                          rb.to_dict() if rb.required else None, coord.action, False,
                                          "recognised")

            # steady state
            self._state = PushToTalkState.LISTENING if pressed else PushToTalkState.IDLE
            return PttLifecycleResult(self._state.value, None, None, PttTtsAction.NONE.value, False,
                                      "idle" if not pressed else "holding")
        except Exception:  # pragma: no cover - defensive
            return PttLifecycleResult(PushToTalkState.IDLE.value, None, None, PttTtsAction.NONE.value,
                                      False, "controller error")

    def _apply_coordination(self, action: str) -> None:
        try:
            if self._vc is None:
                return
            if action == PttTtsAction.PAUSE_ROUTINE.value and hasattr(self._vc, "on_context_change"):
                # pause/cancel routine speech (urgent messages are preserved by the queue's priority rules)
                self._vc.on_context_change()
        except Exception:  # pragma: no cover - defensive
            pass

    def shutdown(self) -> None:
        try:
            if self._input is not None:
                self._input.shutdown()
            if self._recog is not None:
                self._recog.shutdown()
        except Exception:  # pragma: no cover - defensive
            pass
