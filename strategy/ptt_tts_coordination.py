"""PTT / TTS coordination + binding workflow (Program 2, Phase 67, pure domain).

Deterministic policy for coordinating push-to-talk with the Phase-47 voice controller, plus the PTT
binding-workflow logic (conflict detection, restore-default) and stale-recognition rejection on event /
activity change. Pure: no Qt, no DB, no audio, no wall clock; never raises. It DECIDES; the impure PTT
runtime controller (voice/) drives the actual ports + `VoiceController`.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Optional, Sequence, Tuple

from strategy.push_to_talk import (
    PushToTalkBinding, PushToTalkState, PttInputKind, read_ptt_binding, write_ptt_binding,
)

PTT_TTS_COORDINATION_VERSION = "ptt_tts_coordination_v1"


def _fp(payload) -> str:
    return (f"{PTT_TTS_COORDINATION_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        ensure_ascii=True, default=str).encode()).hexdigest()[:24])


# safety/critical priorities that must be preserved even while PTT is active (from Phase 63).
_STOP_CRITICAL_PRIORITIES = (1, 2)


class PttTtsAction(str, Enum):
    NONE = "none"
    PAUSE_ROUTINE = "pause_routine"     # PTT engaged: pause/cancel routine speech
    PRESERVE_URGENT = "preserve_urgent"  # keep an active safety/critical message
    RESUME = "resume"                   # PTT released: routine speech may resume per policy


@dataclass(frozen=True)
class PttTtsDecision:
    action: str
    reason: str
    fingerprint: str = ""

    def to_dict(self) -> dict:
        return {"action": self.action, "reason": self.reason, "fingerprint": self.fingerprint}


def decide_ptt_tts_action(*, ptt_active: bool, active_message_priority: Optional[int] = None,
                          just_released: bool = False) -> PttTtsDecision:
    """When PTT activates: pause/cancel routine speech but PRESERVE an active safety/critical message and
    never talk over the driver. On release, resume only per deterministic policy. Never raises."""
    try:
        if ptt_active:
            if active_message_priority is not None and int(active_message_priority) in _STOP_CRITICAL_PRIORITIES:
                return PttTtsDecision(PttTtsAction.PRESERVE_URGENT.value,
                                      "safety/critical message preserved while PTT active",
                                      _fp({"a": "preserve"}))
            return PttTtsDecision(PttTtsAction.PAUSE_ROUTINE.value,
                                  "routine speech paused/cancelled while PTT active", _fp({"a": "pause"}))
        if just_released:
            return PttTtsDecision(PttTtsAction.RESUME.value,
                                  "PTT released — routine speech may resume per policy", _fp({"a": "resume"}))
        return PttTtsDecision(PttTtsAction.NONE.value, "no coordination change", _fp({"a": "none"}))
    except Exception:  # pragma: no cover - defensive
        return PttTtsDecision(PttTtsAction.NONE.value, "coordination error", _fp({"a": "err"}))


def is_stale_recognition(recognition_nav_key, current_nav_key) -> bool:
    """A recognition result captured for one (event, activity) must be rejected when the current selection
    has changed since. Mirrors the dashboard stale-worker guard. Never raises."""
    try:
        if recognition_nav_key is None or current_nav_key is None:
            return False
        return tuple(recognition_nav_key) != tuple(current_nav_key)
    except Exception:  # pragma: no cover - defensive
        return False


# --------------------------------------------------------------------------- #
# Binding workflow
# --------------------------------------------------------------------------- #
class BindingConflict(str, Enum):
    NONE = "none"
    RESERVED_KEY = "reserved_key"          # a system/app-reserved control
    ALREADY_BOUND = "already_bound"        # the same control is bound elsewhere


# reserved keyboard virtual-key codes that must not be captured as PTT (Esc, Enter, system keys).
_RESERVED_VK = {0x1B, 0x0D, 0x5B, 0x5C, 0x09, 0x12}   # Esc, Enter, Win L/R, Tab, Alt


@dataclass(frozen=True)
class BindingValidation:
    ok: bool
    conflict: str
    message: str
    fingerprint: str = ""

    def to_dict(self) -> dict:
        return {"ok": bool(self.ok), "conflict": self.conflict, "message": self.message,
                "fingerprint": self.fingerprint}


def validate_binding(binding: PushToTalkBinding, *,
                     other_bindings: Optional[Sequence[PushToTalkBinding]] = None) -> BindingValidation:
    """Validate a proposed PTT binding: reject reserved keyboard keys and controls already bound elsewhere.
    Never raises."""
    try:
        if not binding.is_bound:
            return BindingValidation(False, BindingConflict.NONE.value, "no control bound",
                                     _fp({"v": "unbound"}))
        if binding.kind == PttInputKind.KEYBOARD:
            try:
                vk = int(binding.input_code, 0)
            except (TypeError, ValueError):
                vk = None
            if vk is not None and vk in _RESERVED_VK:
                return BindingValidation(False, BindingConflict.RESERVED_KEY.value,
                                         "that key is reserved by the system — choose another",
                                         _fp({"v": "reserved"}))
        for other in (other_bindings or ()):
            if isinstance(other, PushToTalkBinding) and other.is_bound \
                    and other.kind == binding.kind and other.input_code == binding.input_code:
                return BindingValidation(False, BindingConflict.ALREADY_BOUND.value,
                                         "that control is already bound elsewhere",
                                         _fp({"v": "dup"}))
        return BindingValidation(True, BindingConflict.NONE.value, "binding ok", _fp({"v": "ok"}))
    except Exception:  # pragma: no cover - defensive
        return BindingValidation(False, BindingConflict.NONE.value, "validation error", _fp({"v": "err"}))


def default_binding() -> PushToTalkBinding:
    """The safe default PTT binding: keyboard F13 (0x7C) — an uncommon key unlikely to conflict."""
    return PushToTalkBinding(kind=PttInputKind.KEYBOARD, input_code="0x7C",
                             label="F13 (default)")


def apply_binding(config: dict, binding: PushToTalkBinding, *,
                  other_bindings: Optional[Sequence[PushToTalkBinding]] = None) -> BindingValidation:
    """Validate then write the binding to config (explicit user action). Only a valid binding is written.
    Never raises."""
    v = validate_binding(binding, other_bindings=other_bindings)
    if v.ok:
        write_ptt_binding(config, binding)
    return v


def clear_binding(config: dict) -> None:
    """Clear the PTT binding (mic returns to not-listening / unbound). Never raises."""
    try:
        if isinstance(config, dict):
            config.pop("ptt_binding", None)
    except Exception:  # pragma: no cover - defensive
        pass


def ptt_tts_coordination_versions() -> dict:
    return {"ptt_tts_coordination": PTT_TTS_COORDINATION_VERSION}
