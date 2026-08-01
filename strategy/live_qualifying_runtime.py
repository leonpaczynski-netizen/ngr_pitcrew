"""Live Activation 2 — the Qualifying recording coordinator (Program 3).

The qualifying analogue of ``LivePracticeCoordinator``: it composes the SAME generic recording
lifecycle (LiveRunState FSM, reconnect, event-switch, lap guard, persistence port) with the
qualifying PHASE machine (preparation → out-lap → flying lap → lap-complete → cooldown) and its
engineer cue. A qualifying engineer talks by phase, not by lap count, and cares about ONE thing —
the best flying lap — so this coordinator tracks the phase + personal best rather than a valid-lap
target.

Qt-free, DB-free (the port is the only I/O), never raises.
"""
from __future__ import annotations

from typing import Mapping, Tuple

from strategy.live_practice_activation import (
    ActivationVerdict, EventSwitchAction, LiveLapDecision, LivePracticeActivation, LiveRunEvent,
    LiveRunState, ReconnectAction, advance_live_run, evaluate_live_lap, resolve_event_switch,
    resolve_live_qualifying_activation, resolve_reconnect,
)
from strategy.live_practice_runtime import LapOutcome, LivePracticePort
from strategy.qualifying_state_machine import (
    QualifyingPhase, QualifyingState, on_box, on_cooldown, on_lap_completed, on_pit_exit,
    qualifying_cue,
)


class LiveQualifyingCoordinator:
    def __init__(self, port: LivePracticePort):
        self._port = port
        self.state: LiveRunState = LiveRunState.NOT_STARTED       # recording lifecycle
        self.qstate: QualifyingState = QualifyingState.initial()  # qualifying phase machine
        self.run_id: str = ""
        self.stint_id: str = ""
        self.identity: dict = {}
        self.last_finalised_lap: int = 0

    # -- properties -------------------------------------------------------- #
    @property
    def event_id(self) -> str:
        return str(self.identity.get("event_id", ""))

    @property
    def session_plan_id(self) -> str:
        return str(self.identity.get("session_plan_id", ""))

    @property
    def is_recording(self) -> bool:
        return self.state == LiveRunState.RECORDING

    @property
    def best_lap_ms(self) -> int:
        return int(self.qstate.best_lap_ms)

    @property
    def phase(self) -> str:
        return self.qstate.phase.value

    @property
    def attempt(self) -> int:
        return int(self.qstate.attempt)

    def cue(self, *, practice_best_ms: int = 0) -> str:
        """The engineer's phase-appropriate line for the current qualifying state."""
        return qualifying_cue(self.qstate, practice_best_ms=practice_best_ms)

    # -- lifecycle --------------------------------------------------------- #
    def activate(self) -> LivePracticeActivation:
        """Resolve context, gate it as QUALIFYING, and open the authoritative run. A blocked
        gate leaves the state untouched and creates nothing."""
        ctx = self._port.resolve_activation_context()
        ctx = ctx if isinstance(ctx, Mapping) else {}
        act = resolve_live_qualifying_activation(
            ctx, planned_session_type=ctx.get("planned_session_type") or ctx.get("session_type"))
        if not act.ok:
            return act
        started = advance_live_run(self.state, LiveRunEvent.START)
        if not started.ok:
            return LivePracticeActivation(
                verdict=ActivationVerdict.BLOCKED_INCOMPLETE_CONTEXT,
                reason=f"cannot start a new run while {self.state.value}")
        self.state = started.state
        self.identity = dict(act.identity)
        self.run_id, self.stint_id = self._port.create_run(act.identity)
        self.qstate = QualifyingState.initial()
        self.last_finalised_lap = 0
        return act

    def telemetry_connected(self) -> bool:
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
        d = resolve_reconnect(
            authorised_run_id=self.run_id, run_state=self.state,
            incoming_event_id=incoming_event_id, incoming_session_plan_id=incoming_session_plan_id,
            authorised_event_id=self.event_id, authorised_session_plan_id=self.session_plan_id)
        if d.action == ReconnectAction.RESUME_SAME_RUN:
            self.telemetry_connected()
        return d.action

    # -- qualifying phase events ------------------------------------------- #
    def pit_exit(self) -> None:
        """Driver left the pits — begin a new attempt's out-lap."""
        if self.is_recording:
            self.qstate = on_pit_exit(self.qstate)

    def box(self) -> None:
        """Driver returned to the pits — back to preparation."""
        self.qstate = on_box(self.qstate)

    def cooldown(self) -> None:
        self.qstate = on_cooldown(self.qstate)

    def on_lap(self, *, session_run_id: str, event_id, lap_number: int, lap_time_ms: int,
               valid: bool = True, invalidation_reason: str = "",
               is_out_lap: bool = False, is_pit_lap: bool = False,
               telemetry_complete: bool = True) -> LapOutcome:
        """Evaluate + persist one completed lap, and advance the qualifying phase machine. The
        out-lap advances OUT_LAP → FLYING_LAP; the flying lap records the attempt (PB / deleted)."""
        d: LiveLapDecision = evaluate_live_lap(
            run_state=self.state, lap_session_run_id=session_run_id,
            active_session_run_id=self.run_id, lap_event_id=event_id,
            active_event_id=self.event_id, lap_number=lap_number,
            last_finalised_lap=self.last_finalised_lap, lap_time_ms=lap_time_ms,
            is_out_lap=is_out_lap, is_pit_lap=is_pit_lap, telemetry_complete=telemetry_complete)
        if not d.record:
            return LapOutcome(False, False, d.reason)
        # Advance the phase machine. Timing validity for PB detection = the lap guard's verdict
        # AND the caller's explicit validity (a track-limits deletion GT7 reports).
        timing_valid = bool(d.valid and valid)
        self.qstate = on_lap_completed(
            self.qstate, int(lap_time_ms), valid=timing_valid, invalidation_reason=invalidation_reason)
        self._port.persist_lap(
            run_id=self.run_id, stint_id=self.stint_id, lap_number=int(lap_number),
            lap_time_ms=int(lap_time_ms), valid=timing_valid, invalid_reasons=d.invalid_reasons)
        self.last_finalised_lap = int(lap_number)
        return LapOutcome(True, timing_valid, d.reason, d.invalid_reasons)

    def complete(self) -> bool:
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
