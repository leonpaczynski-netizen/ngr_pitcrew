"""Live pit-wall integration — voice status, single advisory, garage return (Program 2, Phase 58).

Wires the driver pit wall to the existing authorities:
  * voice status derives from the Phase-47 controller readiness + the Phase-46 ``voice_gate_allows``
    gate — a UI button can NEVER manufacture ``VOICE_ELIGIBLE``;
  * the single coordinated advisory is selected from the live-advisory decisions (one message, not
    several competing voices), suppressed on stale/blocked;
  * garage-return / recovery presents explicit choices at session end and telemetry loss (never
    auto-binds, never auto-completes).

Purity: Qt-free, DB-free, offline, deterministic, no wall-clock, never raises. No setup values.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Sequence, Tuple

from strategy.shadow_advisory import voice_gate_allows
from strategy.activity_binding import DebriefKind
from strategy.ngr_live_pit_wall import VoiceStatus
from strategy.live_runtime_authority import LiveRuntimeTransition, LiveRuntimeTransitionResult


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def derive_voice_status(*, enabled: bool, readiness_value: str = "", adapter_health: str = "disabled",
                        muted: bool = False, speaking: bool = False) -> VoiceStatus:
    """Deterministic voice status. A UI button cannot manufacture eligibility — ELIGIBLE requires the
    canonical ``voice_gate_allows`` (VOICE_ELIGIBLE readiness). Adapter failure falls back to visual."""
    if _norm(adapter_health).lower() == "failed":
        return VoiceStatus.ADAPTER_FAILURE
    if not enabled:
        return VoiceStatus.DISABLED
    if muted:
        return VoiceStatus.MUTED
    if not voice_gate_allows(_norm(readiness_value)):
        return VoiceStatus.GATED          # enabled but below VOICE_ELIGIBLE
    if speaking:
        return VoiceStatus.ACTIVE
    return VoiceStatus.ELIGIBLE


def coordinate_single_advisory(advisory_decisions: Optional[Sequence], *, suppressed: bool) -> str:
    """Pick ONE coordinated advisory message. Empty when suppressed (stale/blocked). Chooses the highest-
    priority DELIVERED decision; ties broken deterministically by message text. Never several voices."""
    if suppressed or not advisory_decisions:
        return ""
    delivered = []
    for d in advisory_decisions:
        if isinstance(d, dict):
            if d.get("delivered") or d.get("deliver"):
                delivered.append((int(d.get("priority", 0)), _norm(d.get("message") or d.get("text"))))
        else:
            msg = _norm(getattr(d, "message", "") or getattr(d, "text", ""))
            if getattr(d, "delivered", False) or getattr(d, "deliver", False):
                delivered.append((int(getattr(d, "priority", 0)), msg))
    if not delivered:
        return ""
    delivered.sort(key=lambda t: (-t[0], t[1]))
    return delivered[0][1]


class GarageReturnChoice(str, Enum):
    BIND_SESSION = "bind_session"
    REVIEW_WITH_LIMITATIONS = "review_with_limitations"
    RECOVER = "recover"
    REPLACEMENT_RUN = "replacement_run"
    MARK_INVALID = "mark_invalid"
    ABANDON = "abandon"
    RESUME = "resume"


@dataclass(frozen=True)
class LiveGarageReturnDecision:
    active: bool
    primary_choice: Optional[GarageReturnChoice]
    choices: Tuple[GarageReturnChoice, ...]
    debrief_kind: DebriefKind
    note: str

    def as_payload(self) -> dict:
        return {"active": bool(self.active),
                "primary_choice": (self.primary_choice.value if self.primary_choice else None),
                "choices": [c.value for c in self.choices], "debrief_kind": self.debrief_kind.value,
                "note": _norm(self.note)}


def resolve_garage_return(transition: LiveRuntimeTransitionResult,
                          debrief_kind: DebriefKind = DebriefKind.NONE) -> LiveGarageReturnDecision:
    """Explicit garage-return / recovery choices. Never auto-binds or auto-completes."""
    C = GarageReturnChoice
    tr = transition.transition
    if tr == LiveRuntimeTransition.ENDED_BINDING_REQUIRED:
        return LiveGarageReturnDecision(True, C.BIND_SESSION,
                                        (C.BIND_SESSION, C.REVIEW_WITH_LIMITATIONS, C.ABANDON),
                                        debrief_kind, "session ended — bind explicitly")
    if tr == LiveRuntimeTransition.ENDED_INSUFFICIENT:
        return LiveGarageReturnDecision(True, C.REVIEW_WITH_LIMITATIONS,
                                        (C.REVIEW_WITH_LIMITATIONS, C.MARK_INVALID, C.ABANDON),
                                        debrief_kind, "no bindable evidence")
    if tr == LiveRuntimeTransition.STALE:
        return LiveGarageReturnDecision(True, C.RESUME,
                                        (C.RESUME, C.BIND_SESSION, C.REPLACEMENT_RUN,
                                         C.REVIEW_WITH_LIMITATIONS, C.MARK_INVALID, C.ABANDON),
                                        debrief_kind, "telemetry lost — choose explicitly")
    return LiveGarageReturnDecision(False, None, (), debrief_kind, "run in progress")
