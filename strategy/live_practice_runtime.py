"""Live Activation 1 — the Practice recording coordinator (Program 3).

A small stateful orchestration object that composes the pure decisions in
``live_practice_activation`` with persistence side effects behind an injected PORT. It is
Qt-free and DB-free (the port is the only I/O), so the production shell bridge AND the
wired-stack simulation drive the SAME orchestration — no mock re-implementation of the
recording/engineer pathways.

One coordinator owns exactly one live recording at a time. It enforces:
  * a recording starts only on an authoritative activation (full context + Practice plan);
  * exactly one canonical session run owns the recording;
  * laps persist against that run only, gated by the lap-completion guard;
  * reconnect resumes the same run or requires an explicit new one — never "latest session";
  * event switching is blocked while a run is active.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Protocol, Tuple

from strategy.live_practice_activation import (
    ActivationVerdict, EventSwitchAction, LiveLapDecision, LivePracticeActivation,
    LiveRunEvent, LiveRunState, ReconnectAction, advance_live_run, evaluate_live_lap,
    resolve_event_switch, resolve_live_practice_activation, resolve_reconnect,
)


class LivePracticePort(Protocol):
    """The only I/O the coordinator performs. A real port talks to SessionDB; a fake port
    lets the whole orchestration be tested offline."""

    def resolve_activation_context(self) -> Mapping:
        """Return the resolved canonical context, INCLUDING ``planned_session_type`` taken
        from the persisted planned session (never inferred)."""

    def create_run(self, identity: Mapping) -> Tuple[str, str]:
        """Create ONE authoritative session run (+ opening stint) and return (run_id, stint_id)."""

    def persist_lap(self, *, run_id: str, stint_id: str, lap_number: int, lap_time_ms: int,
                    valid: bool, invalid_reasons: Tuple[str, ...]) -> None:
        """Persist one accepted lap bound to the run + stint."""

    def set_run_status(self, run_id: str, status: str) -> None:
        """Persist the run's lifecycle status."""


@dataclass(frozen=True)
class LapOutcome:
    recorded: bool
    valid: bool
    reason: str
    invalid_reasons: Tuple[str, ...] = ()


class LivePracticeCoordinator:
    def __init__(self, port: LivePracticePort):
        self._port = port
        self.state: LiveRunState = LiveRunState.NOT_STARTED
        self.run_id: str = ""
        self.stint_id: str = ""
        self.identity: dict = {}
        self.last_finalised_lap: int = 0
        self._valid_laps: int = 0
        self._invalid_laps: int = 0
        self._last_invalid_reason: str = ""

    # -- properties -------------------------------------------------------- #
    @property
    def event_id(self) -> str:
        return str(self.identity.get("event_id", ""))

    @property
    def session_plan_id(self) -> str:
        return str(self.identity.get("session_plan_id", ""))

    @property
    def valid_lap_count(self) -> int:
        return self._valid_laps

    @property
    def invalid_lap_count(self) -> int:
        return self._invalid_laps

    @property
    def last_invalid_reason(self) -> str:
        return self._last_invalid_reason

    @property
    def is_recording(self) -> bool:
        return self.state == LiveRunState.RECORDING

    # -- lifecycle --------------------------------------------------------- #
    def activate(self) -> LivePracticeActivation:
        """Resolve context, gate it, and open the authoritative run. On a blocked gate the
        state is untouched and NOTHING is created."""
        ctx = self._port.resolve_activation_context()
        ctx = ctx if isinstance(ctx, Mapping) else {}
        act = resolve_live_practice_activation(
            ctx, planned_session_type=ctx.get("planned_session_type") or ctx.get("session_type"))
        if not act.ok:
            return act
        started = advance_live_run(self.state, LiveRunEvent.START)
        if not started.ok:
            return LivePracticeActivation(
                verdict=ActivationVerdict.BLOCKED_INCOMPLETE_CONTEXT,
                reason=f"cannot start a new run while {self.state.value}")
        self.state = started.state                       # STARTING
        self.identity = dict(act.identity)
        self.run_id, self.stint_id = self._port.create_run(act.identity)
        self.last_finalised_lap = 0
        self._valid_laps = 0
        return act

    def telemetry_connected(self) -> bool:
        """Confirm recording once telemetry is live (STARTING → RECORDING, or resume)."""
        t = advance_live_run(self.state, LiveRunEvent.CONFIRM_RECORDING)
        if not t.ok and self.state == LiveRunState.DISCONNECTED:
            t = advance_live_run(self.state, LiveRunEvent.TELEMETRY_RESTORED)
        if t.ok:
            self.state = t.state
            self._port.set_run_status(self.run_id, self.state.value)
        return t.ok

    def telemetry_lost(self) -> bool:
        t = advance_live_run(self.state, LiveRunEvent.TELEMETRY_LOST)
        if t.ok:
            self.state = t.state
            self._port.set_run_status(self.run_id, self.state.value)
        return t.ok

    def reconnect(self, *, incoming_event_id, incoming_session_plan_id) -> ReconnectAction:
        """Deterministic reconnect. Same event+plan → resume the same run; otherwise the
        caller must run the activation gate again for an explicit new run."""
        d = resolve_reconnect(
            authorised_run_id=self.run_id, run_state=self.state,
            incoming_event_id=incoming_event_id, incoming_session_plan_id=incoming_session_plan_id,
            authorised_event_id=self.event_id, authorised_session_plan_id=self.session_plan_id)
        if d.action == ReconnectAction.RESUME_SAME_RUN:
            self.telemetry_connected()
        return d.action

    def on_lap(self, *, session_run_id: str, event_id, lap_number: int, lap_time_ms: int,
               is_out_lap: bool = False, is_pit_lap: bool = False,
               telemetry_complete: bool = True) -> LapOutcome:
        """Evaluate + persist one completed lap. A rejected lap writes nothing."""
        d: LiveLapDecision = evaluate_live_lap(
            run_state=self.state, lap_session_run_id=session_run_id,
            active_session_run_id=self.run_id, lap_event_id=event_id,
            active_event_id=self.event_id, lap_number=lap_number,
            last_finalised_lap=self.last_finalised_lap, lap_time_ms=lap_time_ms,
            is_out_lap=is_out_lap, is_pit_lap=is_pit_lap, telemetry_complete=telemetry_complete)
        if not d.record:
            return LapOutcome(False, False, d.reason)
        self._port.persist_lap(
            run_id=self.run_id, stint_id=self.stint_id, lap_number=int(lap_number),
            lap_time_ms=int(lap_time_ms), valid=d.valid, invalid_reasons=d.invalid_reasons)
        self.last_finalised_lap = int(lap_number)
        if d.valid:
            self._valid_laps += 1
        else:
            self._invalid_laps += 1
            self._last_invalid_reason = d.invalid_reasons[0] if d.invalid_reasons else ""
        return LapOutcome(True, d.valid, d.reason, d.invalid_reasons)

    def complete(self) -> bool:
        """Driver ends the run: RECORDING/PAUSED/DISCONNECTED → COMPLETING → COMPLETED."""
        t = advance_live_run(self.state, LiveRunEvent.BEGIN_COMPLETE)
        if not t.ok:
            return False
        self.state = t.state
        self._port.set_run_status(self.run_id, self.state.value)
        f = advance_live_run(self.state, LiveRunEvent.FINALIZE)
        if f.ok:
            self.state = f.state
            self._port.set_run_status(self.run_id, self.state.value)
        return f.ok

    def abandon(self) -> bool:
        t = advance_live_run(self.state, LiveRunEvent.ABANDON)
        if not t.ok:
            return False
        self.state = t.state
        self._port.set_run_status(self.run_id, self.state.value)
        return True

    def can_switch_event(self) -> Tuple[bool, str]:
        d = resolve_event_switch(run_state=self.state)
        return (d.action == EventSwitchAction.ALLOW, d.reason)
