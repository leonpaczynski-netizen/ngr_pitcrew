"""Opt-In Voice Delivery — pure request/port/queue (Program 2, Phase 47).

Voice is a controlled DELIVERY ADAPTER for advisories that already passed the Phase-44 and Phase-46
gates. It never creates, rewrites, paraphrases or reinterprets engineering advice - it speaks the EXACT
approved message. This module is PURE: it defines the request, the abstract output port (with a disabled
default and a deterministic fake for tests), and the deterministic delivery queue (priority,
stop-critical interruption, routine non-interruption, dedup, cooldown, cancellation on stale context /
plan change, flush on session end, acknowledgement + mute). The concrete Windows offline adapter lives
outside strategy (it is the only module that imports Windows/TTS libraries).

Purity: Qt-free, DB-free, UI-free, network-free, AI-free, TTS-free; no random, no WALL-CLOCK (runtime
timing is injected); deterministic; never raises. Speaks nothing itself.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

VOICE_DELIVERY_VERSION = "voice_delivery_v1"

_STOP_CRITICAL_PRIORITY = 1


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _fp(payload) -> str:
    return (f"{VOICE_DELIVERY_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        default=str).encode()).hexdigest()[:24])


@dataclass(frozen=True)
class VoiceDeliveryRequest:
    message: str
    priority: int
    prompt_class: str
    suppression_key: str
    ack_required: bool = False
    cooldown_seconds: float = 30.0
    prompt_type: str = ""

    @property
    def is_stop_critical(self) -> bool:
        return self.prompt_class == "stop_critical" or self.priority == _STOP_CRITICAL_PRIORITY

    def to_dict(self) -> dict:
        return {"message": self.message, "priority": self.priority, "prompt_class": self.prompt_class,
                "suppression_key": self.suppression_key, "ack_required": self.ack_required,
                "cooldown_seconds": self.cooldown_seconds, "prompt_type": self.prompt_type}

    @classmethod
    def from_prompt(cls, prompt: Optional[Mapping]) -> "VoiceDeliveryRequest":
        p = prompt if isinstance(prompt, Mapping) else {}
        cd = p.get("cooldown_seconds")
        return cls(message=_norm(p.get("message")), priority=int(p.get("priority") or 7),
                   prompt_class=_norm(p.get("prompt_class")),
                   suppression_key=_norm(p.get("suppression_key") or p.get("prompt_type")),
                   ack_required=bool(p.get("ack_required")),
                   cooldown_seconds=(float(cd) if cd is not None else 30.0),
                   prompt_type=_norm(p.get("prompt_type")))


# --------------------------------------------------------------------------- #
# Output port abstraction (pure) - concrete Windows adapter lives outside strategy
# --------------------------------------------------------------------------- #
class VoiceOutputPort:
    """Abstract voice output. Implementations must never raise into the caller."""

    name = "abstract"

    def is_available(self) -> bool:  # pragma: no cover - interface
        return False

    def speak(self, message: str) -> bool:  # pragma: no cover - interface
        return False

    def stop(self) -> None:  # pragma: no cover - interface
        pass


class DisabledVoicePort(VoiceOutputPort):
    """The DEFAULT port: speaks nothing. Starting the app / opening the panel uses this."""

    name = "disabled"

    def is_available(self) -> bool:
        return False

    def speak(self, message: str) -> bool:
        return False

    def stop(self) -> None:
        pass


class FakeVoicePort(VoiceOutputPort):
    """Deterministic test adapter: records spoken messages; can simulate an unrecoverable failure."""

    name = "fake"

    def __init__(self, *, available: bool = True, fail: bool = False):
        self._available = bool(available)
        self._fail = bool(fail)
        self.spoken: List[str] = []
        self.stopped = 0

    def is_available(self) -> bool:
        return self._available and not self._fail

    def speak(self, message: str) -> bool:
        if self._fail or not self._available:
            return False
        self.spoken.append(_norm(message))
        return True

    def stop(self) -> None:
        self.stopped += 1


# --------------------------------------------------------------------------- #
# Deterministic delivery queue (pure state machine)
# --------------------------------------------------------------------------- #
class QueueAction(str, Enum):
    SPEAK = "speak"
    INTERRUPT = "interrupt"      # stop-critical interrupts a routine active message
    HOLD = "hold"               # nothing to speak now (active busy or gated)
    CANCELLED = "cancelled"      # queue flushed (stale/session-end/voice disabled)


@dataclass(frozen=True)
class VoiceQueueDecision:
    action: str
    request: Optional[dict]
    cancelled_keys: Tuple[str, ...]
    reason: str

    def to_dict(self) -> dict:
        return {"action": self.action, "request": dict(self.request) if self.request else None,
                "cancelled_keys": list(self.cancelled_keys), "reason": self.reason}


class VoiceQueue:
    """Pure, deterministic voice queue. All runtime timing is injected via ``now`` (monotonic seconds).
    It decides WHICH request to speak; the adapter/UI drives the actual port. Never raises."""

    def __init__(self):
        self._pending: List[VoiceDeliveryRequest] = []
        self._active: Optional[VoiceDeliveryRequest] = None
        self._last_spoken: Dict[str, float] = {}
        self._acknowledged: set = set()
        self._muted_types: set = set()
        self._muted_coaching_lap: Optional[int] = None

    # ---- submission ---- #
    def submit(self, prompt: Optional[Mapping]) -> None:
        req = VoiceDeliveryRequest.from_prompt(prompt)
        if not req.message or not req.suppression_key:
            return
        # dedup: do not queue a semantic key already pending or active.
        keys = {r.suppression_key for r in self._pending}
        if self._active is not None:
            keys.add(self._active.suppression_key)
        if req.suppression_key not in keys:
            self._pending.append(req)

    # ---- runtime state changes ---- #
    def acknowledge(self, suppression_key: str) -> None:
        self._acknowledged.add(_norm(suppression_key))
        self._drop(_norm(suppression_key))

    def mute_type(self, suppression_key: str) -> None:
        self._muted_types.add(_norm(suppression_key))
        self._drop(_norm(suppression_key))

    def mute_coaching_for_lap(self, lap: int) -> None:
        self._muted_coaching_lap = int(lap)

    def clear_cooldown(self, key: str) -> None:
        """Clear the cooldown for a key (used by an explicit user 'repeat once')."""
        self._last_spoken.pop(_norm(key), None)
        self._acknowledged.discard(_norm(key))

    def on_finished_speaking(self) -> None:
        self._active = None

    def _drop(self, key: str) -> None:
        self._pending = [r for r in self._pending if r.suppression_key != key]

    def cancel_all(self, reason: str) -> VoiceQueueDecision:
        cancelled = tuple(sorted({r.suppression_key for r in self._pending}
                                 | ({self._active.suppression_key} if self._active else set())))
        self._pending = []
        self._active = None
        return VoiceQueueDecision(QueueAction.CANCELLED.value, None, cancelled, reason)

    # ---- the poll: which request to speak now ---- #
    def poll(self, now: float, *, voice_enabled: bool = False, gates_ok: bool = True,
             current_lap: Optional[int] = None) -> VoiceQueueDecision:
        try:
            now = float(now)
            if not voice_enabled:
                return self.cancel_all("voice disabled")
            if not gates_ok:
                return self.cancel_all("delivery gate not satisfied (stale/context/plan/session)")

            # eligible = not muted, not acknowledged, not in cooldown, lap-mute respected.
            def eligible(r: VoiceDeliveryRequest) -> bool:
                if r.suppression_key in self._muted_types or r.suppression_key in self._acknowledged:
                    return False
                if (self._muted_coaching_lap is not None and current_lap == self._muted_coaching_lap
                        and _lc(r.prompt_type).startswith("coach")):
                    return False
                last = self._last_spoken.get(r.suppression_key)
                if last is not None and (now - last) < r.cooldown_seconds:
                    return False
                return True

            pending = [r for r in self._pending if eligible(r)]
            pending.sort(key=lambda r: (r.priority, r.suppression_key))

            # stop-critical always wins and may interrupt a routine active message.
            stop_crit = next((r for r in pending if r.is_stop_critical), None)
            if stop_crit is not None:
                if self._active is not None and not self._active.is_stop_critical:
                    self._active = stop_crit
                    self._drop(stop_crit.suppression_key)
                    self._last_spoken[stop_crit.suppression_key] = now
                    return VoiceQueueDecision(QueueAction.INTERRUPT.value, stop_crit.to_dict(), (),
                                              "stop-critical interrupts the active routine message")
                if self._active is None:
                    self._active = stop_crit
                    self._drop(stop_crit.suppression_key)
                    self._last_spoken[stop_crit.suppression_key] = now
                    return VoiceQueueDecision(QueueAction.SPEAK.value, stop_crit.to_dict(), (),
                                              "stop-critical")
                # active is already stop-critical -> hold the new one.
                return VoiceQueueDecision(QueueAction.HOLD.value, None, (),
                                          "a stop-critical message is already active")

            # routine: never interrupt an active message.
            if self._active is not None:
                return VoiceQueueDecision(QueueAction.HOLD.value, None, (),
                                          "a message is already being spoken")
            if not pending:
                return VoiceQueueDecision(QueueAction.HOLD.value, None, (), "nothing eligible to speak")
            top = pending[0]
            self._active = top
            self._drop(top.suppression_key)
            self._last_spoken[top.suppression_key] = now
            return VoiceQueueDecision(QueueAction.SPEAK.value, top.to_dict(), (), "next routine prompt")
        except Exception:  # pragma: no cover - defensive
            return VoiceQueueDecision(QueueAction.HOLD.value, None, (), "queue error")

    def snapshot(self) -> dict:
        return {"pending": len(self._pending), "active": self._active.to_dict() if self._active else None,
                "muted_types": sorted(self._muted_types), "acknowledged": sorted(self._acknowledged)}


def voice_delivery_versions() -> dict:
    return {"voice_delivery": VOICE_DELIVERY_VERSION}
