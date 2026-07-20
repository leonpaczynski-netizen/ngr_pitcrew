"""NGR Live Pit Wall domain (Program 2, Phase 58).

The driver-facing live experience for Practice / Qualifying / Race. It assembles ONE coordinated NGR team
message from the live runtime evaluation + transition (never several competing engineering voices), in a
strict low-density hierarchy. It changes no state, issues no pit/tyre/fuel/setup command, and cannot
manufacture voice eligibility.

Primary live hierarchy: (1) NGR event + activity, (2) objective, (3) context + setup match, (4) telemetry
state, (5) critical warning or single advisory, (6) evidence progress, (7) stop condition / next action,
(8) voice status. Detailed analysis belongs in the debrief, not here.

Purity: Qt-free, DB-free, offline, deterministic, no wall-clock, never raises. No setup values.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple

from strategy.gt7_live_adapter import LiveRuntimeEvaluation
from strategy.live_activity_bridge import LiveActivityMatch
from strategy.live_runtime_authority import LiveRuntimeTransitionResult, LiveRuntimeTransition

NGR_LIVE_PIT_WALL_VERSION = "ngr_live_pit_wall_v1"


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _fp(payload) -> str:
    return (f"{NGR_LIVE_PIT_WALL_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        ensure_ascii=True, default=str).encode()).hexdigest()[:24])


class LivePitWallMode(str, Enum):
    IDLE = "idle"
    PRACTICE = "practice"
    QUALIFYING = "qualifying"
    RACE = "race"
    TRANSITION = "transition"       # probable session end -> binding
    RECOVERY = "recovery"           # telemetry lost


class VoiceStatus(str, Enum):
    VISUAL_ONLY = "visual_only"
    DISABLED = "disabled"
    GATED = "gated"
    ELIGIBLE = "eligible"
    ACTIVE = "active"
    MUTED = "muted"
    ADAPTER_FAILURE = "adapter_failure"


# purpose -> a short driver-facing note (respect activity purpose; no mid-run setup-change encouragement)
_PURPOSE_NOTE = {
    "setup_experiment": "Testing a setup change — hold the setup constant; no mid-run changes.",
    "coaching_run": "Coaching focus — one objective; setup held constant.",
    "tyre_test": "Tyre test — collect degradation evidence; no setup conclusions from this run alone.",
    "fuel_test": "Fuel test — collect consumption evidence; no setup conclusions from this run alone.",
    "qualifying_simulation": "Qualifying simulation — low-fuel peak pace.",
    "long_race_run": "Race simulation — representative race pace and consistency.",
    "strategy_validation_run": "Strategy validation run.",
    "free_practice": "Free practice.",
}


@dataclass(frozen=True)
class NgrLivePitWall:
    mode: LivePitWallMode
    event_line: str                 # (1) NGR event + activity
    objective: str                  # (2)
    purpose_note: str
    match_summary: str              # (3) context + setup match
    blocked: bool
    telemetry_state: str            # (4)
    advisory: str                   # (5) ONE coordinated advisory (empty when suppressed)
    advisory_suppressed: bool
    evidence_progress: float        # (6) 0..1
    valid_laps: int
    target_laps: int
    next_action: str                # (7) stop condition / bind / recover
    voice_status: VoiceStatus       # (8)
    fingerprint: str = ""

    def as_stable_payload(self) -> dict:
        # volatile live counters (valid_laps, evidence_progress) are display; the stable identity is the
        # coordinated mode + match + suppression + voice status.
        return {"mode": self.mode.value, "event_line": _norm(self.event_line),
                "objective": _norm(self.objective), "match_summary": _norm(self.match_summary),
                "blocked": bool(self.blocked), "advisory_suppressed": bool(self.advisory_suppressed),
                "next_action": _norm(self.next_action), "voice_status": self.voice_status.value}


# live mode is driven by the ACTIVITY TYPE (the run's operational character), not the setup discipline:
# a setup experiment developing the race setup is a Practice-mode run, while a race simulation / the
# official race is Race-mode.
_ACTIVITY_MODE = {
    "qualifying": LivePitWallMode.QUALIFYING, "qualifying_simulation": LivePitWallMode.QUALIFYING,
    "race": LivePitWallMode.RACE, "long_race_run": LivePitWallMode.RACE,
    "strategy_validation_run": LivePitWallMode.RACE,
}


def _match_summary(match: LiveActivityMatch) -> Tuple[str, bool]:
    """A concise driver-facing context+setup match line + whether the activity is blocked."""
    M = LiveActivityMatch
    if match == M.EXACT_ACTIVITY_MATCH:
        return "Car, track, layout and setup confirmed.", False
    if match == M.MATCH_WITH_LIMITATIONS:
        return "Match confirmed with limitations.", False
    if match == M.SETUP_MISMATCH:
        return "SETUP MISMATCH — wrong setup active.", True
    if match == M.CAR_MISMATCH:
        return "CAR MISMATCH.", True
    if match == M.TRACK_MISMATCH:
        return "TRACK MISMATCH.", True
    if match == M.LAYOUT_MISMATCH:
        return "LAYOUT MISMATCH.", True
    if match == M.DISCIPLINE_MISMATCH:
        return "DISCIPLINE MISMATCH.", True
    if match == M.CONTEXT_MISMATCH:
        return "CONTEXT MISMATCH.", True
    if match == M.TELEMETRY_STALE:
        return "Telemetry stale.", False
    if match == M.ACTIVITY_NOT_SELECTED:
        return "No activity selected.", False
    return "Unverifiable — some required data unknown.", False


def build_ngr_live_pit_wall(
    evaluation: LiveRuntimeEvaluation,
    transition: LiveRuntimeTransitionResult,
    *,
    event_line: str = "",
    voice_status: VoiceStatus = VoiceStatus.DISABLED,
    advisory_text: str = "",
) -> NgrLivePitWall:
    """Assemble ONE coordinated pit-wall view. The single advisory is suppressed on stale telemetry or a
    blocked (hard mismatch) activity. Mode is driven by the transition + the selected activity discipline
    (purpose comes only from the selected activity). ``voice_status`` is supplied by the voice controller
    readiness — the pit wall can never manufacture ELIGIBLE."""
    snap = evaluation.snapshot
    match = evaluation.match.match
    summary, blocked = _match_summary(match)

    # mode
    tr = transition.transition
    if not snap.activity_selected:
        mode = LivePitWallMode.IDLE
    elif tr in (LiveRuntimeTransition.ENDED_BINDING_REQUIRED, LiveRuntimeTransition.ENDED_INSUFFICIENT):
        mode = LivePitWallMode.TRANSITION
    elif tr == LiveRuntimeTransition.STALE:
        mode = LivePitWallMode.RECOVERY
    else:
        mode = _ACTIVITY_MODE.get(_lc(snap.activity_type), LivePitWallMode.PRACTICE)

    # single advisory: suppressed on stale/blocked
    suppressed = (not snap.telemetry_fresh) or blocked or mode in (LivePitWallMode.TRANSITION,
                                                                   LivePitWallMode.RECOVERY)
    advisory = "" if suppressed else _norm(advisory_text)

    # telemetry state
    telem = "fresh" if snap.telemetry_fresh else "stale"

    # next action
    if mode == LivePitWallMode.TRANSITION:
        next_action = ("Session appears complete — bind the telemetry session."
                       if tr == LiveRuntimeTransition.ENDED_BINDING_REQUIRED
                       else "Session ended without bindable evidence — review with limitations or abandon.")
    elif mode == LivePitWallMode.RECOVERY:
        next_action = "Telemetry lost — recover, run a replacement, review with limitations, or abandon."
    elif blocked:
        next_action = "Correct the mismatch before collecting evidence."
    else:
        target = int(snap.target_laps or 0)
        next_action = (f"Collect {max(0, target - int(snap.valid_laps or 0))} more valid lap(s)."
                       if target > 0 else "Continue the run.")

    pw = NgrLivePitWall(
        mode=mode, event_line=_norm(event_line), objective=_norm(snap.objective),
        purpose_note=_PURPOSE_NOTE.get(_lc(snap.activity_type), ""),
        match_summary=summary, blocked=blocked, telemetry_state=telem, advisory=advisory,
        advisory_suppressed=suppressed, evidence_progress=evaluation.evidence_progress,
        valid_laps=int(snap.valid_laps or 0), target_laps=int(snap.target_laps or 0),
        next_action=next_action, voice_status=voice_status, fingerprint="")
    return NgrLivePitWall(**{**pw.__dict__, "fingerprint": _fp(pw.as_stable_payload())})


def pit_wall_to_dict(pw: NgrLivePitWall) -> dict:
    """Serialise the pit wall to the immutable view dict the UI worker hands to the panel."""
    return {
        "ok": True, "mode": pw.mode.value, "event_line": pw.event_line, "objective": pw.objective,
        "purpose_note": pw.purpose_note, "match_summary": pw.match_summary, "blocked": pw.blocked,
        "telemetry_state": pw.telemetry_state, "advisory": pw.advisory,
        "advisory_suppressed": pw.advisory_suppressed, "evidence_progress": pw.evidence_progress,
        "valid_laps": pw.valid_laps, "target_laps": pw.target_laps, "next_action": pw.next_action,
        "voice_status": pw.voice_status.value, "fingerprint": pw.fingerprint,
    }
