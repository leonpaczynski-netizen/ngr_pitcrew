"""Programme resume, interruption & telemetry-dropout recovery (Program 2, Phase 53).

Makes the Event Preparation Cycle resilient for real multi-week use. Deterministic, read-only: it
classifies what a restart / interruption / telemetry gap means and what the user must decide. It NEVER
automatically marks an interrupted activity complete, never fabricates a completion, never creates a
duplicate session, and never increases confidence from a dropout. Voice is restored disabled by default.

Purity: Qt-free, DB-free, offline, deterministic, no wall-clock, never raises. No setup values.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Sequence, Tuple

from strategy.live_activity import LiveActivityState

PROGRAMME_RESUME_VERSION = "programme_resume_v1"


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{PROGRAMME_RESUME_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


class InterruptedActivityResolution(str, Enum):
    RESUMABLE = "resumable"
    SESSION_RECOVERABLE = "session_recoverable"
    BINDING_REQUIRED = "binding_required"
    INVALID = "invalid"
    ABANDONED = "abandoned"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


@dataclass(frozen=True)
class ProgrammeResumeState:
    """The state restored after an application restart. Nothing here advances a cycle; an interrupted
    activity is NEVER restored as complete. Voice is always restored disabled unless an existing policy
    explicitly and safely preserves it (represented by ``voice_preserved`` — default False)."""
    selected_cycle_id: str
    current_phase: str
    completed_activity_ids: Tuple[str, ...]
    next_activity_id: str
    interrupted_activity_id: str
    interrupted_state: LiveActivityState
    pending_binding: bool
    pending_debrief: bool
    setup_locks: Tuple[str, ...]
    strategy_finalised: bool
    voice_preserved: bool = False
    fingerprint: str = ""

    def as_payload(self) -> dict:
        return {
            "selected_cycle_id": _norm(self.selected_cycle_id), "current_phase": _norm(self.current_phase),
            "completed_activity_ids": sorted(_norm(a) for a in self.completed_activity_ids if _norm(a)),
            "next_activity_id": _norm(self.next_activity_id),
            "interrupted_activity_id": _norm(self.interrupted_activity_id),
            "interrupted_state": self.interrupted_state.value,
            "pending_binding": bool(self.pending_binding), "pending_debrief": bool(self.pending_debrief),
            "setup_locks": sorted(_norm(l) for l in self.setup_locks if _norm(l)),
            "strategy_finalised": bool(self.strategy_finalised), "voice_preserved": bool(self.voice_preserved)}


def build_resume_state(*, selected_cycle_id="", current_phase="", completed_activity_ids=(),
                       next_activity_id="", interrupted_activity_id="",
                       interrupted_state: LiveActivityState = LiveActivityState.PLANNED,
                       pending_binding=False, pending_debrief=False, setup_locks=(),
                       strategy_finalised=False, voice_preserved=False) -> ProgrammeResumeState:
    """Restore the programme state after restart. An interrupted activity is never restored COMPLETED —
    if a COMPLETED state is passed for an interrupted activity it is downgraded to INTERRUPTED."""
    st = interrupted_state
    if _norm(interrupted_activity_id) and st == LiveActivityState.COMPLETED:
        st = LiveActivityState.INTERRUPTED  # restart cannot fabricate a completion
    r = ProgrammeResumeState(
        selected_cycle_id=_norm(selected_cycle_id), current_phase=_norm(current_phase),
        completed_activity_ids=tuple(completed_activity_ids), next_activity_id=_norm(next_activity_id),
        interrupted_activity_id=_norm(interrupted_activity_id), interrupted_state=st,
        pending_binding=bool(pending_binding), pending_debrief=bool(pending_debrief),
        setup_locks=tuple(setup_locks), strategy_finalised=bool(strategy_finalised),
        voice_preserved=bool(voice_preserved), fingerprint="")
    return ProgrammeResumeState(**{**r.__dict__, "fingerprint": _fp(r.as_payload())})


def classify_interrupted_activity(*, telemetry_recoverable: bool, has_partial_session: bool,
                                  min_evidence_met: bool, user_abandon: bool = False,
                                  user_invalid: bool = False) -> InterruptedActivityResolution:
    """Deterministic classification of an interrupted activity. Never auto-completes; the user still
    decides (bind recovered / continue new run / abandon / mark invalid / debrief with limitations)."""
    R = InterruptedActivityResolution
    if user_abandon:
        return R.ABANDONED
    if user_invalid:
        return R.INVALID
    if telemetry_recoverable and has_partial_session:
        return R.BINDING_REQUIRED if min_evidence_met else R.SESSION_RECOVERABLE
    if has_partial_session and not min_evidence_met:
        return R.INSUFFICIENT_EVIDENCE
    return R.RESUMABLE


@dataclass(frozen=True)
class TelemetryDropoutResolution:
    advisories_suppressed: bool
    evidence_preserved: bool
    duplicate_session_created: bool
    activity_completed: bool
    recovery_state: str
    note: str
    fingerprint: str = ""

    def as_payload(self) -> dict:
        return {"advisories_suppressed": bool(self.advisories_suppressed),
                "evidence_preserved": bool(self.evidence_preserved),
                "duplicate_session_created": bool(self.duplicate_session_created),
                "activity_completed": bool(self.activity_completed),
                "recovery_state": _norm(self.recovery_state), "note": _norm(self.note)}


def resolve_telemetry_dropout(*, gap_detected: bool) -> TelemetryDropoutResolution:
    """A telemetry gap suppresses live advisories, preserves existing evidence, creates NO duplicate
    session, does NOT complete the activity, and shows an honest recovery state. When no gap is detected
    it is a no-op honest 'live' state."""
    if gap_detected:
        r = TelemetryDropoutResolution(
            advisories_suppressed=True, evidence_preserved=True, duplicate_session_created=False,
            activity_completed=False, recovery_state="telemetry_lost",
            note="telemetry gap — advisories suppressed; evidence preserved; awaiting recovery")
    else:
        r = TelemetryDropoutResolution(
            advisories_suppressed=False, evidence_preserved=True, duplicate_session_created=False,
            activity_completed=False, recovery_state="live", note="telemetry live")
    return TelemetryDropoutResolution(**{**r.__dict__, "fingerprint": _fp(r.as_payload())})
