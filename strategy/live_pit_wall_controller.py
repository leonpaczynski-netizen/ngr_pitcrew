"""Production Live-Pit-Wall controller state (Program 2, Phase 60).

A PURE, deterministic reducer for the production Live-tab state machine. The dashboard's off-thread
worker (Phase 60, implemented in the dashboard) computes runtime evaluations; this reducer maps the
navigation context + evaluation + transition into the production Live state. It advances nothing on its
own, starts no activity by opening Live, and completes no activity on refresh.

Purity: Qt-free, DB-free, offline, deterministic, no wall-clock, never raises. No setup values.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from strategy.gt7_live_adapter import LiveRuntimeEvaluation
from strategy.live_activity_bridge import LiveActivityMatch
from strategy.live_runtime_authority import LiveRuntimeTransitionResult, LiveRuntimeTransition

LIVE_PIT_WALL_CONTROLLER_VERSION = "live_pit_wall_controller_v1"


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _fp(payload) -> str:
    return (f"{LIVE_PIT_WALL_CONTROLLER_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        ensure_ascii=True, default=str).encode()).hexdigest()[:24])


class LivePitWallRuntimeState(str, Enum):
    NO_ACTIVE_EVENT = "no_active_event"
    NO_SELECTED_ACTIVITY = "no_selected_activity"
    AWAITING_START = "awaiting_start"
    STARTING = "starting"
    EXACT_MATCH = "exact_match"
    LIMITED_MATCH = "limited_match"
    HARD_MISMATCH = "hard_mismatch"
    LIVE = "live"
    TELEMETRY_STALE = "telemetry_stale"
    TELEMETRY_LOST = "telemetry_lost"
    PROBABLE_SESSION_END = "probable_session_end"
    BINDING_REQUIRED = "binding_required"
    REVIEW_WITH_LIMITATIONS = "review_with_limitations"
    ACTIVITY_ABANDONED = "activity_abandoned"
    RETURNING_TO_GARAGE = "returning_to_garage"


@dataclass(frozen=True)
class LivePitWallNavigationContext:
    """Operational navigation state (never enters an engineering fingerprint). ``entered_live`` is set by
    an EXPLICIT 'Enter Live' action; ``started`` by an EXPLICIT 'Start' action — opening the Live tab
    never starts the activity."""
    active_event_id: str = ""
    selected_activity_id: str = ""
    entered_live: bool = False
    started: bool = False
    abandoned: bool = False
    returning: bool = False


_BLOCKING = frozenset({
    LiveActivityMatch.SETUP_MISMATCH, LiveActivityMatch.CAR_MISMATCH, LiveActivityMatch.TRACK_MISMATCH,
    LiveActivityMatch.LAYOUT_MISMATCH, LiveActivityMatch.DISCIPLINE_MISMATCH,
    LiveActivityMatch.CONTEXT_MISMATCH,
})


@dataclass(frozen=True)
class LivePitWallRuntimeStateResult:
    state: LivePitWallRuntimeState
    activity_completed: bool          # ALWAYS False
    note: str
    fingerprint: str = ""

    def as_payload(self) -> dict:
        return {"state": self.state.value, "activity_completed": bool(self.activity_completed),
                "note": _norm(self.note)}


def reduce_live_state(
    nav: LivePitWallNavigationContext,
    evaluation: Optional[LiveRuntimeEvaluation] = None,
    transition: Optional[LiveRuntimeTransitionResult] = None,
) -> LivePitWallRuntimeStateResult:
    """Deterministic production Live state. Opening Live (entered_live) never starts the activity;
    starting requires the explicit ``started`` flag; refresh never completes the activity."""
    S = LivePitWallRuntimeState

    def _r(state, note):
        r = LivePitWallRuntimeStateResult(state, False, note, "")
        return LivePitWallRuntimeStateResult(r.state, False, r.note, _fp(r.as_payload()))

    if nav.abandoned:
        return _r(S.ACTIVITY_ABANDONED, "activity explicitly abandoned")
    if nav.returning:
        return _r(S.RETURNING_TO_GARAGE, "returning to the Event Command Centre")
    if not _norm(nav.active_event_id):
        return _r(S.NO_ACTIVE_EVENT, "no active NGR event")
    if not _norm(nav.selected_activity_id):
        return _r(S.NO_SELECTED_ACTIVITY, "no selected activity")
    if not nav.started:
        # opening Live never starts the activity
        return _r(S.STARTING if nav.entered_live and evaluation is not None else S.AWAITING_START,
                  "awaiting explicit activity start")

    if evaluation is None or transition is None:
        return _r(S.AWAITING_START, "no runtime evaluation yet")

    tr = transition.transition
    if tr == LiveRuntimeTransition.ENDED_BINDING_REQUIRED:
        # a stale-derived end is a recoverable DROPOUT (telemetry lost); a clean end (fresh + session
        # ended) is a genuine session end awaiting binding. Both keep binding available; the driver may
        # recover first on a dropout.
        if not evaluation.snapshot.telemetry_fresh:
            return _r(S.TELEMETRY_LOST, "telemetry lost mid-run — recover or bind the recovered session")
        return _r(S.BINDING_REQUIRED, "session ended — explicit binding required")
    if tr == LiveRuntimeTransition.ENDED_INSUFFICIENT:
        return _r(S.REVIEW_WITH_LIMITATIONS, "session ended without bindable evidence")
    if tr == LiveRuntimeTransition.STALE:
        return _r(S.TELEMETRY_LOST if nav.started else S.TELEMETRY_STALE, "telemetry lost")

    match = evaluation.match.match
    if match == LiveActivityMatch.TELEMETRY_STALE:
        return _r(S.TELEMETRY_STALE, "telemetry stale")
    if match in _BLOCKING:
        return _r(S.HARD_MISMATCH, f"hard mismatch ({match.value})")
    if match == LiveActivityMatch.EXACT_ACTIVITY_MATCH:
        return _r(S.EXACT_MATCH, "exact activity match — live")
    if match in (LiveActivityMatch.MATCH_WITH_LIMITATIONS, LiveActivityMatch.UNVERIFIABLE):
        # UNVERIFIABLE = a required field unknown -> cannot verify an exact match -> limited
        return _r(S.LIMITED_MATCH, "match with limitations — live")
    return _r(S.LIVE, "live")
