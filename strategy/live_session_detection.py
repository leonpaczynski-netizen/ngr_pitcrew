"""Session-end detection, telemetry recovery & binding handover (Program 2, Phase 55).

Detects when a live GT7 run has ended WITHOUT completing the activity, freezes the runtime, and hands
over to explicit session binding (reusing the canonical ranker) and the correct debrief. It never
auto-completes, never auto-binds, never selects the newest session, and never creates a duplicate
session on a telemetry gap. Telemetry-dropout resolution reuses ``programme_resume.resolve_telemetry_dropout``.

Purity: Qt-free, DB-free, offline, deterministic, no wall-clock, never raises. No setup values.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Sequence, Tuple

from strategy.activity_binding import (
    rank_activity_sessions, assess_debrief_readiness, DebriefKind, debrief_kind_for)
from strategy.event_preparation_cycle import PreparationActivityType
from strategy.programme_resume import resolve_telemetry_dropout, TelemetryDropoutResolution

LIVE_SESSION_DETECTION_VERSION = "live_session_detection_v1"


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _fp(payload) -> str:
    return (f"{LIVE_SESSION_DETECTION_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        ensure_ascii=True, default=str).encode()).hexdigest()[:24])


class SessionEndState(str, Enum):
    LIVE = "live"
    POTENTIAL_END = "potential_end"
    BINDING_REQUIRED = "binding_required"
    ENDED_INSUFFICIENT = "ended_insufficient"    # ran but produced no bindable evidence


@dataclass(frozen=True)
class SessionEndDetection:
    state: SessionEndState
    binding_required: bool
    activity_completed: bool          # ALWAYS False — session end never completes an activity
    snapshot_frozen: bool
    note: str
    fingerprint: str = ""

    def as_payload(self) -> dict:
        return {"state": self.state.value, "binding_required": bool(self.binding_required),
                "activity_completed": bool(self.activity_completed),
                "snapshot_frozen": bool(self.snapshot_frozen), "note": _norm(self.note)}


def detect_session_end(*, was_running: bool, telemetry_fresh: bool, session_state: str,
                       valid_laps: int, evidence_permitted: bool) -> SessionEndDetection:
    """Detect a potential session end. Ending the live run never completes the activity: a run that
    produced permitted evidence becomes BINDING_REQUIRED (the snapshot is frozen and candidates are
    ranked for EXPLICIT selection); a run with no bindable evidence becomes ENDED_INSUFFICIENT."""
    ended = (not telemetry_fresh) or (_norm(session_state).lower() == "ended")
    if not ended:
        d = SessionEndDetection(SessionEndState.LIVE, False, False, False, "run is live")
    elif not was_running:
        d = SessionEndDetection(SessionEndState.POTENTIAL_END, False, False, True,
                                "no active run to end; snapshot frozen")
    elif evidence_permitted and int(valid_laps) > 0:
        d = SessionEndDetection(SessionEndState.BINDING_REQUIRED, True, False, True,
                                "run ended with evidence — awaiting EXPLICIT session binding")
    else:
        d = SessionEndDetection(SessionEndState.ENDED_INSUFFICIENT, False, False, True,
                                "run ended without bindable evidence")
    return SessionEndDetection(d.state, d.binding_required, d.activity_completed, d.snapshot_frozen,
                               d.note, _fp(d.as_payload()))


@dataclass(frozen=True)
class BindingHandover:
    binding_required: bool
    ranking: dict                     # the canonical session_binding ranking (auto-bind forbidden)
    debrief_kind: DebriefKind
    fingerprint: str = ""

    def as_payload(self) -> dict:
        return {"binding_required": bool(self.binding_required),
                "ranking": self.ranking, "debrief_kind": self.debrief_kind.value}


def build_binding_handover(activity_type: PreparationActivityType, candidate_sessions,
                           run_plan_context, *, expected_setup_fingerprint: str = "",
                           min_clean_laps: int = 0) -> BindingHandover:
    """After a run ends, rank candidate sessions (reusing the canonical ranker — the newest is never
    auto-selected) and route to the correct debrief. Binds nothing."""
    ranking = rank_activity_sessions(candidate_sessions, run_plan_context,
                                     expected_setup_fingerprint=expected_setup_fingerprint,
                                     min_clean_laps=min_clean_laps).to_dict()
    kind = debrief_kind_for(activity_type)
    h = BindingHandover(True, ranking, kind, "")
    return BindingHandover(h.binding_required, h.ranking, h.debrief_kind, _fp({"n": len(ranking.get("candidates", [])),
                                                                              "k": kind.value}))


def handle_telemetry_dropout(*, gap_detected: bool) -> TelemetryDropoutResolution:
    """Reuse the canonical dropout resolver: suppress advisories, preserve evidence, no duplicate session,
    no completion, honest recovery state."""
    return resolve_telemetry_dropout(gap_detected=gap_detected)
