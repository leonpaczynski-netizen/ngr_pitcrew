"""Live GT7 bridge views — Practice / Qualifying / Race (Program 2, Phase 55).

Combines the immutable runtime snapshot + the activity-match classification with the Phase-52 low-density
live views. A hard mismatch (car/track/layout/discipline/setup/context) or stale telemetry BLOCKS the
activity and permits no evidence; advisories are suppressed when telemetry is not fresh. These builders
change no state and issue no pit/tyre/fuel command.

Purity: Qt-free, DB-free, offline, deterministic, no wall-clock, never raises. No setup values.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Tuple

from strategy.live_activity_bridge import (
    LiveActivityRuntimeSnapshot, LiveActivityMatch, LiveActivityMatchResult, match_permits_evidence)
from strategy.live_activity_modes import (
    LiveMode, build_practice_live_view, build_qualifying_live_view, build_race_live_view)

LIVE_BRIDGE_VIEWS_VERSION = "live_bridge_views_v1"


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _fp(payload) -> str:
    return (f"{LIVE_BRIDGE_VIEWS_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        ensure_ascii=True, default=str).encode()).hexdigest()[:24])


# match outcomes that BLOCK the activity (no evidence; the run cannot proceed as this activity)
_BLOCKING_MATCHES = frozenset({
    LiveActivityMatch.SETUP_MISMATCH, LiveActivityMatch.CAR_MISMATCH, LiveActivityMatch.TRACK_MISMATCH,
    LiveActivityMatch.LAYOUT_MISMATCH, LiveActivityMatch.DISCIPLINE_MISMATCH,
    LiveActivityMatch.CONTEXT_MISMATCH, LiveActivityMatch.TELEMETRY_STALE,
    LiveActivityMatch.ACTIVITY_NOT_SELECTED,
})


def bridge_blocked(match_result: LiveActivityMatchResult) -> bool:
    return match_result.match in _BLOCKING_MATCHES


@dataclass(frozen=True)
class LiveBridgeView:
    mode: LiveMode
    blocked: bool
    evidence_permitted: bool
    match: str
    telemetry_fresh: bool
    view: object                 # the underlying Phase-52 low-density view
    fingerprint: str = ""

    def as_stable_payload(self) -> dict:
        return {"mode": self.mode.value, "blocked": bool(self.blocked),
                "evidence_permitted": bool(self.evidence_permitted), "match": _norm(self.match),
                "telemetry_fresh": bool(self.telemetry_fresh)}


def _advisory(snap: LiveActivityRuntimeSnapshot, blocked: bool) -> str:
    if not snap.telemetry_fresh:
        return ""  # advisories suppressed on stale telemetry
    if blocked:
        return "Blocked: live session does not match the selected activity."
    return ""


def build_practice_bridge(snap: LiveActivityRuntimeSnapshot,
                          match: LiveActivityMatchResult) -> LiveBridgeView:
    blocked = bridge_blocked(match)
    view = build_practice_live_view(
        activity_title=_norm(snap.activity_type).replace("_", " ").title(), objective=snap.objective,
        active_setup_fingerprint=snap.live_setup_fingerprint, target_laps=snap.target_laps,
        valid_laps=snap.valid_laps, current_advisory=_advisory(snap, blocked),
        stop_condition="return to garage after the target laps", return_to_garage=snap.session_state == "ended")
    v = LiveBridgeView(LiveMode.PRACTICE, blocked, match_permits_evidence(match) and not blocked,
                       match.match.value, snap.telemetry_fresh, view, "")
    return LiveBridgeView(v.mode, v.blocked, v.evidence_permitted, v.match, v.telemetry_fresh, v.view,
                          _fp(v.as_stable_payload()))


def build_qualifying_bridge(snap: LiveActivityRuntimeSnapshot,
                            match: LiveActivityMatchResult) -> LiveBridgeView:
    blocked = bridge_blocked(match)
    view = build_qualifying_live_view(
        setup_confirmation=("confirmed" if match.match == LiveActivityMatch.EXACT_ACTIVITY_MATCH
                            else "verify setup"), tyre_preparation=snap.tyre_compound,
        out_lap_status=snap.session_state, lap_validity=("invalid" if snap.invalid_lap else "valid"),
        target_info=snap.objective, current_advisory=_advisory(snap, blocked),
        session_complete=snap.session_state == "ended")
    v = LiveBridgeView(LiveMode.QUALIFYING, blocked, match_permits_evidence(match) and not blocked,
                       match.match.value, snap.telemetry_fresh, view, "")
    return LiveBridgeView(v.mode, v.blocked, v.evidence_permitted, v.match, v.telemetry_fresh, v.view,
                          _fp(v.as_stable_payload()))


def build_race_bridge(snap: LiveActivityRuntimeSnapshot,
                      match: LiveActivityMatchResult) -> LiveBridgeView:
    blocked = bridge_blocked(match)
    warnings = []
    if blocked:
        warnings.append(f"{match.match.value.replace('_', ' ')}")
    view = build_race_live_view(
        race_setup_match=(match.match == LiveActivityMatch.EXACT_ACTIVITY_MATCH),
        primary_strategy=snap.objective, plan_status=snap.session_state,
        tyre_awareness=snap.tyre_compound, fuel_awareness=snap.fuel,
        car_condition="", current_advisory=_advisory(snap, blocked),
        voice_state=("ready" if snap.voice_ready else "disabled"), critical_warnings=tuple(warnings))
    v = LiveBridgeView(LiveMode.RACE, blocked, match_permits_evidence(match) and not blocked,
                       match.match.value, snap.telemetry_fresh, view, "")
    return LiveBridgeView(v.mode, v.blocked, v.evidence_permitted, v.match, v.telemetry_fresh, v.view,
                          _fp(v.as_stable_payload()))
