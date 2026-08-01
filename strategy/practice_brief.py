"""Live practice brief (Program 3 Phase E14).

A practice run must have an explicit objective, controlled variables, a lap target
and stop conditions — and the engineer must track progress against them, not just
pile up laps. The static content already exists as ``RunBrief`` (objective,
how-to-drive, monitor, fuel/tyre, target_laps, invalidation); this adds the LIVE
state on top: valid-lap progress toward the target, completion, and an explicit stop.

Crucially, completion counts VALID laps only — an anomalous (invalid) lap is tracked
but never counts toward the target and never derails the run, so one bad lap cannot
dominate the read. Pure, deterministic, offline, never raises. Advisory only.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from strategy.run_brief import (
    RunBrief, brief_for_domain, brief_for_run_type, lap_progress_note,
    _target_lap_bounds,
)


@dataclass(frozen=True)
class PracticeBriefState:
    brief: RunBrief
    target_min: int = 0          # laps needed for a read (lower bound of the brief)
    target_max: int = 0          # upper bound
    valid_laps: int = 0          # clean laps banked — the only thing completion counts
    invalid_laps: int = 0        # anomalies, tracked but never counted toward the target
    stopped: bool = False
    stop_reason: str = ""

    @property
    def is_complete(self) -> bool:
        return (not self.stopped) and self.target_min > 0 and self.valid_laps >= self.target_min

    @property
    def needs_another_lap(self) -> bool:
        """Whether the engineer should ask for another lap."""
        return (not self.stopped) and (not self.is_complete)


def start_practice_brief(*, domain: str = "", activity_type: str = "") -> PracticeBriefState:
    """Open a live brief from an evidence domain (command-centre objective) or an
    activity type. The lap target is parsed from the brief's ``target_laps``."""
    try:
        brief = brief_for_domain(domain) if domain else brief_for_run_type(activity_type)
        lo, hi = _target_lap_bounds(brief.target_laps)
        return PracticeBriefState(brief=brief, target_min=int(lo or 0), target_max=int(hi or 0))
    except Exception:
        return PracticeBriefState(brief=RunBrief())


def on_valid_lap(state: PracticeBriefState) -> PracticeBriefState:
    if state.stopped:
        return state
    return replace(state, valid_laps=int(state.valid_laps) + 1)


def on_invalid_lap(state: PracticeBriefState, reason: str = "") -> PracticeBriefState:
    """Record an anomalous lap. It does NOT count toward the target — one bad lap
    must never dominate the read — but it is tracked so the driver knows why."""
    if state.stopped:
        return state
    return replace(state, invalid_laps=int(state.invalid_laps) + 1)


def stop_practice(state: PracticeBriefState, reason: str) -> PracticeBriefState:
    return replace(state, stopped=True, stop_reason=str(reason or "stopped"))


def practice_status(state: PracticeBriefState) -> str:
    """The engineer's progress line for the run card. Never raises."""
    try:
        banked = int(state.valid_laps)
        if state.stopped:
            return (f"Stopped — {state.stop_reason}. {banked} clean lap"
                    f"{'' if banked == 1 else 's'} banked.")
        if state.is_complete:
            return (f"Target met — {banked} clean lap{'' if banked == 1 else 's'}. "
                    "Bring it in and tell me how the balance feels; that's enough for a read.")
        note = lap_progress_note(state.brief.target_laps, banked)
        if state.invalid_laps:
            note = (f"{note} ({state.invalid_laps} lap"
                    f"{'' if state.invalid_laps == 1 else 's'} didn't count)")
        return note
    except Exception:
        return ""


def conclude_practice(state: PracticeBriefState) -> dict:
    """A structured result the debrief/review can consume. Never raises."""
    try:
        return {
            "domain": state.brief.domain,
            "objective": state.brief.objective,
            "valid_laps": int(state.valid_laps),
            "invalid_laps": int(state.invalid_laps),
            "target_min": int(state.target_min),
            "target_max": int(state.target_max),
            "complete": bool(state.is_complete),
            "stopped": bool(state.stopped),
            "stop_reason": state.stop_reason,
            "reports": list(state.brief.reports),
        }
    except Exception:
        return {"complete": False, "valid_laps": 0}
