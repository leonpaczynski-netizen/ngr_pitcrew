"""Live Activation 1 — authoritative Practice recording decisions (Program 3).

The FIRST production telemetry seam through the canonical event spine. This module holds
the DETERMINISTIC decisions that gate and govern a live Practice recording; it performs no
I/O and creates no session run — the caller (the shell bridge / session DB) acts on these
verdicts. Purity: Qt-free, DB-free, offline, no wall-clock, never raises.

Five decisions live here:

  A. ``resolve_live_practice_activation`` — a live recording may start ONLY when the app has
     resolved the full canonical identity AND the PLANNED session type is PRACTICE. Practice
     mode is NEVER inferred from the visible page, telemetry packets, session history, the
     last DB row, a cached engineer mode, a button name or PTT wording. The planned session
     is authoritative; missing context blocks with the exact requirement.
  B. ``advance_live_run`` — the explicit session-run lifecycle state machine.
  C. ``resolve_reconnect`` — resume the SAME authorised run or require an explicit new one;
     never choose silently by "latest session".
  D. ``evaluate_live_lap`` — one authoritative lap-completion guard.
  E. ``resolve_event_switch`` — atomic, explicit event switching; never a silent switch
     during an active recording.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Optional, Tuple


def _norm(v) -> str:
    return "" if v is None else str(v).strip()


def _present(v) -> bool:
    """A canonical identity component is 'resolved' when it is a non-empty, non-zero token."""
    s = _norm(v)
    return s not in ("", "0", "0.0", "none", "None", "null")


# --------------------------------------------------------------------------- #
# A. Authoritative activation gate
# --------------------------------------------------------------------------- #

#: Hard requirements — a live Practice recording must not start unless every one is resolved.
REQUIRED_CONTEXT: Tuple[str, ...] = (
    "event_programme_id",
    "event_id",
    "session_plan_id",
    "car_id",
    "car_spec_revision_id",
    "driver_profile_version_id",
    "context_revision_id",
)

#: Recorded when available but NOT blocking (the run is honest about their absence).
OPTIONAL_CONTEXT: Tuple[str, ...] = (
    "setup_snapshot_id",
    "track_model_version_id",
)

PRACTICE = "practice"


class ActivationVerdict(str, Enum):
    ACTIVATED = "activated"
    BLOCKED_WRONG_SESSION_TYPE = "blocked_wrong_session_type"
    BLOCKED_INCOMPLETE_CONTEXT = "blocked_incomplete_context"


@dataclass(frozen=True)
class LivePracticeActivation:
    """The verdict on whether a live Practice recording may start, plus the authorised identity."""
    verdict: ActivationVerdict = ActivationVerdict.BLOCKED_INCOMPLETE_CONTEXT
    reason: str = ""
    missing: Tuple[str, ...] = ()
    identity: Mapping[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.verdict == ActivationVerdict.ACTIVATED


def resolve_live_practice_activation(
    context: Optional[Mapping],
    *,
    planned_session_type: str,
) -> LivePracticeActivation:
    """Decide whether the resolved ``context`` authorises a live Practice recording.

    ``planned_session_type`` MUST come from the persisted planned session — never from the
    page, a packet, history, the last row, a cached mode, a button or PTT. It is the only
    session-type input this function trusts.
    """
    ctx = context if isinstance(context, Mapping) else {}

    # Session type is authoritative and checked first — a non-Practice plan can never be
    # activated as Practice, regardless of how complete the rest of the context is.
    if _norm(planned_session_type).lower() != PRACTICE:
        return LivePracticeActivation(
            verdict=ActivationVerdict.BLOCKED_WRONG_SESSION_TYPE,
            reason=f"Planned session type is {_norm(planned_session_type) or 'unknown'!r}, not Practice — "
                   f"a live Practice recording cannot start.")

    missing = tuple(f for f in REQUIRED_CONTEXT if not _present(ctx.get(f)))
    if missing:
        return LivePracticeActivation(
            verdict=ActivationVerdict.BLOCKED_INCOMPLETE_CONTEXT,
            reason="Recording is blocked — unresolved: " + ", ".join(missing),
            missing=missing)

    identity = {f: _norm(ctx.get(f)) for f in REQUIRED_CONTEXT}
    identity["session_type"] = PRACTICE
    for f in OPTIONAL_CONTEXT:                       # present-if-known, honest when absent
        identity[f] = _norm(ctx.get(f))
    return LivePracticeActivation(
        verdict=ActivationVerdict.ACTIVATED,
        reason="Authoritative Practice context resolved.",
        identity=identity)


# --------------------------------------------------------------------------- #
# B. Session-run lifecycle state machine
# --------------------------------------------------------------------------- #

class LiveRunState(str, Enum):
    NOT_STARTED = "not_started"
    STARTING = "starting"
    RECORDING = "recording"
    PAUSED = "paused"
    DISCONNECTED = "disconnected"
    COMPLETING = "completing"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class LiveRunEvent(str, Enum):
    START = "start"                       # authorised activation → open the run
    CONFIRM_RECORDING = "confirm_recording"
    TELEMETRY_LOST = "telemetry_lost"
    TELEMETRY_RESTORED = "telemetry_restored"
    PAUSE = "pause"
    RESUME = "resume"
    BEGIN_COMPLETE = "begin_complete"
    FINALIZE = "finalize"
    ABANDON = "abandon"


TERMINAL_STATES = frozenset({LiveRunState.COMPLETED, LiveRunState.ABANDONED})

#: The only legal (state, event) → state transitions. Anything absent is rejected, which is
#: how the machine prevents: two active runs for one action (START only from NOT_STARTED),
#: a completed run silently reactivating (no transition out of COMPLETED), duplicate run
#: creation on reconnect (reconnect is TELEMETRY_RESTORED, not START), and finalising twice.
_TRANSITIONS: dict = {
    (LiveRunState.NOT_STARTED, LiveRunEvent.START): LiveRunState.STARTING,
    (LiveRunState.STARTING, LiveRunEvent.CONFIRM_RECORDING): LiveRunState.RECORDING,
    (LiveRunState.STARTING, LiveRunEvent.ABANDON): LiveRunState.ABANDONED,
    (LiveRunState.RECORDING, LiveRunEvent.TELEMETRY_LOST): LiveRunState.DISCONNECTED,
    (LiveRunState.RECORDING, LiveRunEvent.PAUSE): LiveRunState.PAUSED,
    (LiveRunState.RECORDING, LiveRunEvent.BEGIN_COMPLETE): LiveRunState.COMPLETING,
    (LiveRunState.RECORDING, LiveRunEvent.ABANDON): LiveRunState.ABANDONED,
    (LiveRunState.PAUSED, LiveRunEvent.RESUME): LiveRunState.RECORDING,
    (LiveRunState.PAUSED, LiveRunEvent.TELEMETRY_LOST): LiveRunState.DISCONNECTED,
    (LiveRunState.PAUSED, LiveRunEvent.BEGIN_COMPLETE): LiveRunState.COMPLETING,
    (LiveRunState.PAUSED, LiveRunEvent.ABANDON): LiveRunState.ABANDONED,
    (LiveRunState.DISCONNECTED, LiveRunEvent.TELEMETRY_RESTORED): LiveRunState.RECORDING,
    (LiveRunState.DISCONNECTED, LiveRunEvent.BEGIN_COMPLETE): LiveRunState.COMPLETING,
    (LiveRunState.DISCONNECTED, LiveRunEvent.ABANDON): LiveRunState.ABANDONED,
    (LiveRunState.COMPLETING, LiveRunEvent.FINALIZE): LiveRunState.COMPLETED,
    (LiveRunState.COMPLETING, LiveRunEvent.ABANDON): LiveRunState.ABANDONED,
}


@dataclass(frozen=True)
class LiveRunTransition:
    ok: bool
    state: LiveRunState
    reason: str = ""


def advance_live_run(state, event) -> LiveRunTransition:
    """Advance the run lifecycle. An illegal transition leaves the state unchanged and is
    reported — the machine never jumps or silently reactivates a terminal run."""
    try:
        st = state if isinstance(state, LiveRunState) else LiveRunState(_norm(state).lower())
    except ValueError:
        return LiveRunTransition(False, LiveRunState.NOT_STARTED, f"unknown state {state!r}")
    try:
        ev = event if isinstance(event, LiveRunEvent) else LiveRunEvent(_norm(event).lower())
    except ValueError:
        return LiveRunTransition(False, st, f"unknown event {event!r}")
    if st in TERMINAL_STATES:
        return LiveRunTransition(False, st, f"run is {st.value} — a terminal run never reopens")
    nxt = _TRANSITIONS.get((st, ev))
    if nxt is None:
        return LiveRunTransition(False, st, f"{ev.value} is not allowed while {st.value}")
    return LiveRunTransition(True, nxt, f"{st.value} → {nxt.value}")


def is_recording_open(state) -> bool:
    """True while the run owns the live recording (laps may be finalised only here)."""
    try:
        st = state if isinstance(state, LiveRunState) else LiveRunState(_norm(state).lower())
    except ValueError:
        return False
    return st == LiveRunState.RECORDING


# --------------------------------------------------------------------------- #
# C. Reconnect rule — resume the same authorised run, or an EXPLICIT new one
# --------------------------------------------------------------------------- #

class ReconnectAction(str, Enum):
    RESUME_SAME_RUN = "resume_same_run"
    REQUIRE_NEW_RUN = "require_new_run"
    REJECT = "reject"


@dataclass(frozen=True)
class ReconnectDecision:
    action: ReconnectAction
    reason: str = ""
    run_id: str = ""


def resolve_reconnect(
    *,
    authorised_run_id: str,
    run_state,
    incoming_event_id,
    incoming_session_plan_id: str,
    authorised_event_id,
    authorised_session_plan_id: str,
) -> ReconnectDecision:
    """When telemetry returns, decide deterministically — never by "latest session".

    The SAME authorised run resumes only when the run is still disconnected AND the returning
    telemetry belongs to the same event + planned session. A reconnect that carries a
    different event/plan is an event change, not a resume: it requires an explicit new
    authorised run (handled by the activation gate), never a silent adoption.
    """
    aid = _norm(authorised_run_id)
    if not aid:
        return ReconnectDecision(ReconnectAction.REQUIRE_NEW_RUN,
                                 "No authorised run to resume — start one explicitly.")
    try:
        st = run_state if isinstance(run_state, LiveRunState) else LiveRunState(_norm(run_state).lower())
    except ValueError:
        return ReconnectDecision(ReconnectAction.REJECT, f"unknown run state {run_state!r}", aid)
    if st in TERMINAL_STATES:
        return ReconnectDecision(ReconnectAction.REQUIRE_NEW_RUN,
                                 f"the authorised run is {st.value}; a reconnect cannot reopen it", aid)
    same_event = _norm(incoming_event_id) == _norm(authorised_event_id) and _present(authorised_event_id)
    same_plan = _norm(incoming_session_plan_id) == _norm(authorised_session_plan_id) \
        and _present(authorised_session_plan_id)
    if same_event and same_plan:
        return ReconnectDecision(ReconnectAction.RESUME_SAME_RUN,
                                 "same event + planned session — resume the authorised run", aid)
    return ReconnectDecision(
        ReconnectAction.REQUIRE_NEW_RUN,
        "telemetry returned under a different event/plan — an explicit new run is required", aid)


# --------------------------------------------------------------------------- #
# D. Live lap-completion guard
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class LiveLapDecision:
    record: bool                      # persist this lap at all?
    valid: bool = False               # counts toward practice progress?
    reason: str = ""
    invalid_reasons: Tuple[str, ...] = ()


def evaluate_live_lap(
    *,
    run_state,
    lap_session_run_id: str,
    active_session_run_id: str,
    lap_event_id,
    active_event_id,
    lap_number,
    last_finalised_lap,
    lap_time_ms,
    is_out_lap: bool = False,
    is_pit_lap: bool = False,
    telemetry_complete: bool = True,
) -> LiveLapDecision:
    """One authoritative lap-completion decision.

    REJECTS (records nothing) a lap that cannot belong to this run: recording not open,
    a stale/other session run, a different event (switch cross-write), a replayed/duplicate
    or counter-reset lap number, or a zero-length lap. Otherwise the lap is RECORDED, and
    flagged invalid (with reasons) for out/pit/incomplete-telemetry laps so progress counts
    only genuine valid laps while the evidence trail keeps everything that happened.
    """
    if not is_recording_open(run_state):
        return LiveLapDecision(False, reason="recording is not open — no lap is finalised now")
    if _norm(lap_session_run_id) != _norm(active_session_run_id) or not _present(active_session_run_id):
        return LiveLapDecision(False, reason="lap belongs to a different/stale session run")
    if _norm(lap_event_id) != _norm(active_event_id) or not _present(active_event_id):
        return LiveLapDecision(False, reason="lap belongs to a different event — rejected")
    try:
        ln = int(lap_number)
        last = int(last_finalised_lap)
    except (TypeError, ValueError):
        return LiveLapDecision(False, reason="lap number is not an integer")
    if ln <= 0:
        return LiveLapDecision(False, reason="non-positive lap number")
    if ln <= last:
        return LiveLapDecision(False, reason=f"lap {ln} already finalised or replayed (last {last})")
    try:
        t = int(lap_time_ms)
    except (TypeError, ValueError):
        t = 0
    if t <= 0:
        return LiveLapDecision(False, reason="zero-length lap time")

    invalid: list = []
    if is_out_lap:
        invalid.append("out_lap")
    if is_pit_lap:
        invalid.append("pit_lap")
    if not telemetry_complete:
        invalid.append("incomplete_telemetry")
    return LiveLapDecision(True, valid=not invalid,
                           reason=f"lap {ln} finalised", invalid_reasons=tuple(invalid))


# --------------------------------------------------------------------------- #
# E. Event switching during a live state
# --------------------------------------------------------------------------- #

class EventSwitchAction(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"


@dataclass(frozen=True)
class EventSwitchDecision:
    action: EventSwitchAction
    reason: str = ""


def resolve_event_switch(*, run_state) -> EventSwitchDecision:
    """Switching to another event is atomic and explicit. It is ALLOWED only when no run
    owns the recording (not started, or already completed/abandoned). While a run is
    starting, recording, paused, disconnected or completing, the switch is BLOCKED — the
    driver must explicitly complete or abandon first, so no lap can cross event boundaries
    and the new event never inherits the old run or objective."""
    try:
        st = run_state if isinstance(run_state, LiveRunState) else LiveRunState(_norm(run_state).lower())
    except ValueError:
        return EventSwitchDecision(EventSwitchAction.BLOCK, f"unknown run state {run_state!r}")
    if st == LiveRunState.NOT_STARTED or st in TERMINAL_STATES:
        return EventSwitchDecision(EventSwitchAction.ALLOW, f"no active run ({st.value}) — safe to switch")
    return EventSwitchDecision(
        EventSwitchAction.BLOCK,
        f"a Practice run is {st.value} — complete or abandon it before switching event")
