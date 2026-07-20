"""Live runtime session start/end authority (Program 2, Phase 57).

Ties the live runtime evaluation (Phase 57 adapter) to the canonical session-end detection (Phase 55).
Detects session start, running, probable session end and stale/dropout transitions from immutable
runtime evaluations. A probable session end freezes the final snapshot and hands over to EXPLICIT
binding (candidate search) — it NEVER auto-completes the activity and NEVER auto-binds.

Purity: Qt-free, DB-free, offline, deterministic, no wall-clock, never raises. No setup values.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from strategy.gt7_live_adapter import LiveRuntimeEvaluation
from strategy.live_activity_bridge import match_permits_evidence
from strategy.live_session_detection import detect_session_end, SessionEndDetection, SessionEndState

LIVE_RUNTIME_AUTHORITY_VERSION = "live_runtime_authority_v1"


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _fp(payload) -> str:
    return (f"{LIVE_RUNTIME_AUTHORITY_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        ensure_ascii=True, default=str).encode()).hexdigest()[:24])


class LiveRuntimeTransition(str, Enum):
    NOT_SELECTED = "not_selected"
    STARTED = "started"
    RUNNING = "running"
    STALE = "stale"                          # telemetry lost while not previously running
    BLOCKED = "blocked"                      # hard mismatch — activity blocked
    ENDED_BINDING_REQUIRED = "ended_binding_required"
    ENDED_INSUFFICIENT = "ended_insufficient"


@dataclass(frozen=True)
class LiveRuntimeTransitionResult:
    transition: LiveRuntimeTransition
    now_running: bool
    session_end: Optional[SessionEndDetection]
    frozen_snapshot_fingerprint: str
    activity_completed: bool                 # ALWAYS False
    note: str
    fingerprint: str = ""

    def as_payload(self) -> dict:
        return {"transition": self.transition.value, "now_running": bool(self.now_running),
                "session_end": (self.session_end.as_payload() if self.session_end else None),
                "frozen_snapshot_fingerprint": _norm(self.frozen_snapshot_fingerprint),
                "activity_completed": bool(self.activity_completed), "note": _norm(self.note)}


# hard-mismatch matches that block the activity (routine advisories suppressed)
from strategy.live_activity_bridge import LiveActivityMatch as _M
_BLOCKING = frozenset({_M.SETUP_MISMATCH, _M.CAR_MISMATCH, _M.TRACK_MISMATCH, _M.LAYOUT_MISMATCH,
                       _M.DISCIPLINE_MISMATCH, _M.CONTEXT_MISMATCH})


def evaluate_runtime_transition(evaluation: LiveRuntimeEvaluation, *,
                                was_running: bool) -> LiveRuntimeTransitionResult:
    """Deterministic session transition from one immutable runtime evaluation + the previous running
    flag. A probable session end (fresh->stale while running, or session_state 'ended') hands over to
    explicit binding; it never completes the activity."""
    snap = evaluation.snapshot
    match = evaluation.match.match

    def _result(transition, now_running, session_end, note):
        r = LiveRuntimeTransitionResult(transition, now_running, session_end,
                                        snap.fingerprint(), False, note, "")
        return LiveRuntimeTransitionResult(r.transition, r.now_running, r.session_end,
                                           r.frozen_snapshot_fingerprint, False, r.note, _fp(r.as_payload()))

    if not snap.activity_selected:
        return _result(LiveRuntimeTransition.NOT_SELECTED, False, None, "no activity selected")

    ended = (not snap.telemetry_fresh) or (_norm(snap.session_state).lower() == "ended")
    if ended and was_running:
        # probable session end -> freeze + hand to explicit binding (canonical detector).
        # Evidence permission: a clean end keeps the (fresh) match's permission; a telemetry-dropout end
        # makes the current match STALE, but the valid laps collected BEFORE the dropout are still
        # bindable (a recoverable session), so permit when valid laps exist and it wasn't a hard mismatch.
        permits = match_permits_evidence(evaluation.match)
        if not snap.telemetry_fresh and match not in _BLOCKING and snap.valid_laps > 0:
            permits = True
        se = detect_session_end(
            was_running=True, telemetry_fresh=snap.telemetry_fresh, session_state=snap.session_state,
            valid_laps=snap.valid_laps, evidence_permitted=permits)
        if se.state == SessionEndState.BINDING_REQUIRED:
            return _result(LiveRuntimeTransition.ENDED_BINDING_REQUIRED, False, se,
                           "session ended — awaiting explicit binding")
        return _result(LiveRuntimeTransition.ENDED_INSUFFICIENT, False, se,
                       "session ended without bindable evidence")

    if not snap.telemetry_fresh:
        return _result(LiveRuntimeTransition.STALE, False, None,
                       "telemetry stale — routine advisories suppressed")

    if match in _BLOCKING:
        return _result(LiveRuntimeTransition.BLOCKED, was_running, None,
                       f"activity blocked ({match.value}) — routine advisories suppressed")

    if not was_running:
        return _result(LiveRuntimeTransition.STARTED, True, None, "live run started")
    return _result(LiveRuntimeTransition.RUNNING, True, None, "live run in progress")
