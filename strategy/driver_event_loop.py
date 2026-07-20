"""Driver event loop — briefing, launch & loop transitions (Program 2, Phase 61).

Completes the real driver workflow from activity preparation through live running, session binding,
debrief and Command Centre update. It reuses the canonical authorities (start readiness, session-end
detection, candidate ranking, debrief handover, cumulative-update gate, consistency) and orchestrates the
loop deterministically. It advances nothing on its own: opening a briefing does not start the activity,
and the loop never reaches cumulative update without an explicitly-confirmed outcome.

Purity: Qt-free, DB-free, offline, deterministic, no wall-clock, never raises. No setup values.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Sequence, Tuple

from strategy.live_activity import ActivityStartReadiness

DRIVER_EVENT_LOOP_VERSION = "driver_event_loop_v1"


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _fp(payload) -> str:
    return (f"{DRIVER_EVENT_LOOP_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        ensure_ascii=True, default=str).encode()).hexdigest()[:24])


@dataclass(frozen=True)
class ActivityBriefing:
    """The pre-live activity briefing. Assembled from the selected activity + canonical readiness; the
    driver explicitly confirms start."""
    event: str
    activity: str
    objective: str
    setup: str
    run_plan: str
    target_laps: int
    target_corners: Tuple[str, ...]
    evidence_required: Tuple[str, ...]
    held_constant: Tuple[str, ...]
    stop_conditions: Tuple[str, ...]
    readiness_blockers: Tuple[str, ...]
    fingerprint: str = ""

    def as_payload(self) -> dict:
        return {"event": _norm(self.event), "activity": _norm(self.activity),
                "objective": _norm(self.objective), "setup": _norm(self.setup),
                "run_plan": _norm(self.run_plan), "target_laps": int(self.target_laps),
                "target_corners": [_norm(c) for c in self.target_corners],
                "evidence_required": sorted(_norm(e) for e in self.evidence_required if _norm(e)),
                "held_constant": sorted(_norm(h) for h in self.held_constant if _norm(h)),
                "stop_conditions": sorted(_norm(s) for s in self.stop_conditions if _norm(s)),
                "readiness_blockers": sorted(_norm(b) for b in self.readiness_blockers if _norm(b))}


def build_activity_briefing(*, event="", activity="", objective="", setup="", run_plan="", target_laps=0,
                            target_corners=(), evidence_required=(), held_constant=(), stop_conditions=(),
                            readiness_blockers=()) -> ActivityBriefing:
    b = ActivityBriefing(
        event=_norm(event), activity=_norm(activity), objective=_norm(objective), setup=_norm(setup),
        run_plan=_norm(run_plan), target_laps=int(target_laps or 0), target_corners=tuple(target_corners),
        evidence_required=tuple(evidence_required), held_constant=tuple(held_constant),
        stop_conditions=tuple(stop_conditions), readiness_blockers=tuple(readiness_blockers), fingerprint="")
    return ActivityBriefing(**{**b.__dict__, "fingerprint": _fp(b.as_payload())})


@dataclass(frozen=True)
class ActivityLaunchDecision:
    can_launch: bool
    requires_confirmation: bool
    blockers: Tuple[str, ...]
    reason: str

    def as_payload(self) -> dict:
        return {"can_launch": bool(self.can_launch),
                "requires_confirmation": bool(self.requires_confirmation),
                "blockers": sorted(_norm(b) for b in self.blockers if _norm(b)), "reason": _norm(self.reason)}


def decide_activity_launch(readiness: ActivityStartReadiness, *, confirmed: bool) -> ActivityLaunchDecision:
    """Launch requires start-readiness to be satisfied AND an explicit driver confirmation. Opening the
    briefing never launches; a blocked readiness never launches even when confirmed."""
    if not readiness.can_start:
        return ActivityLaunchDecision(False, False, tuple(readiness.blocking_reasons),
                                      "start readiness not satisfied")
    if not confirmed:
        return ActivityLaunchDecision(False, True, (), "explicit driver confirmation required to start")
    return ActivityLaunchDecision(True, False, (), "launched by explicit driver confirmation")


# ---------------------------------------------------------------------------
# Event-loop transitions
# ---------------------------------------------------------------------------

class EventLoopStage(str, Enum):
    BRIEFING = "briefing"
    READINESS = "readiness"
    LIVE = "live"
    SESSION_END = "session_end"
    BINDING = "binding"
    DEBRIEF = "debrief"
    CUMULATIVE_UPDATE = "cumulative_update"
    COMMAND_CENTRE_RETURN = "command_centre_return"


@dataclass(frozen=True)
class EventLoopSignals:
    launched: bool = False
    session_ended: bool = False
    bound: bool = False
    debrief_confirmed: bool = False
    outcome_recorded: bool = False


@dataclass(frozen=True)
class EventLoopTransition:
    stage: EventLoopStage
    note: str
    fingerprint: str = ""

    def as_payload(self) -> dict:
        return {"stage": self.stage.value, "note": _norm(self.note)}


def advance_event_loop(current: EventLoopStage, signals: EventLoopSignals) -> EventLoopTransition:
    """Deterministic loop transition. The loop NEVER skips binding or debrief, and NEVER reaches
    cumulative update without an explicitly-confirmed outcome. Missing a signal holds the current stage."""
    S = EventLoopStage

    def _t(stage, note):
        t = EventLoopTransition(stage, note, "")
        return EventLoopTransition(t.stage, t.note, _fp(t.as_payload()))

    if current == S.BRIEFING:
        return _t(S.READINESS, "briefing reviewed") if signals.launched else _t(S.BRIEFING, "awaiting launch")
    if current == S.READINESS:
        return _t(S.LIVE, "launched") if signals.launched else _t(S.READINESS, "awaiting explicit start")
    if current == S.LIVE:
        return _t(S.SESSION_END, "session ended") if signals.session_ended else _t(S.LIVE, "running")
    if current == S.SESSION_END:
        return _t(S.BINDING, "binding required") if not signals.bound else _t(S.DEBRIEF, "already bound")
    if current == S.BINDING:
        return _t(S.DEBRIEF, "session bound") if signals.bound else _t(S.BINDING, "awaiting explicit binding")
    if current == S.DEBRIEF:
        # cumulative update requires an explicitly-confirmed outcome
        if signals.debrief_confirmed and signals.outcome_recorded:
            return _t(S.CUMULATIVE_UPDATE, "outcome confirmed")
        return _t(S.DEBRIEF, "awaiting explicit outcome confirmation")
    if current == S.CUMULATIVE_UPDATE:
        return _t(S.COMMAND_CENTRE_RETURN, "cumulative event knowledge updated")
    return _t(S.COMMAND_CENTRE_RETURN, "returned to the Event Command Centre")
