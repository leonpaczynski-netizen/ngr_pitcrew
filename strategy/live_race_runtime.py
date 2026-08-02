"""Live Activation 3 — the Race recording coordinator (Program 3).

The race analogue of ``LivePracticeCoordinator`` / ``LiveQualifyingCoordinator``: it composes the
SAME generic recording lifecycle (LiveRunState FSM, reconnect, event-switch, lap guard,
persistence port) with the race ENGINEER phase machine (waiting → race-start → racing → pit
entry/in-pit/pit-exit → finished) and its cue. A race engineer tracks laps completed, pit stops
made and the running best lap, and — critically — the race must not even START unless the active
race plan belongs to THIS event/car/track/layout (``validate_race_plan_context``).

Qt-free, DB-free (the port is the only I/O), never raises. Advisory only: the coordinator records
the run and choreographs the engineer's voice; it calls no pit, changes no setup, executes nothing.
"""
from __future__ import annotations

from typing import Mapping, Tuple

from strategy.live_practice_activation import (
    ActivationVerdict, EventSwitchAction, LiveLapDecision, LivePracticeActivation, LiveRunEvent,
    LiveRunState, ReconnectAction, advance_live_run, evaluate_live_lap, resolve_event_switch,
    resolve_live_race_activation, resolve_reconnect, validate_race_plan_context,
)
from strategy.live_practice_runtime import LapOutcome, LivePracticePort
from strategy.race_engineer_state_machine import (
    RaceEngineerEvent, RaceEngineerState, apply_event, on_lap_completed, race_cue,
)


class LiveRaceCoordinator:
    def __init__(self, port: LivePracticePort):
        self._port = port
        self.state: LiveRunState = LiveRunState.NOT_STARTED       # recording lifecycle
        self.rstate: RaceEngineerState = RaceEngineerState.initial()  # race phase machine
        self.run_id: str = ""
        self.stint_id: str = ""
        self.identity: dict = {}
        self.last_finalised_lap: int = 0
        self._valid_laps: int = 0
        self._invalid_laps: int = 0
        self._last_invalid_reason: str = ""
        self._plan_block: str = ""

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
    def valid_lap_count(self) -> int:
        return self._valid_laps

    @property
    def invalid_lap_count(self) -> int:
        return self._invalid_laps

    @property
    def last_invalid_reason(self) -> str:
        return self._last_invalid_reason

    @property
    def completed_laps(self) -> int:
        return int(self.rstate.completed_laps)

    @property
    def current_lap(self) -> int:
        return int(self.rstate.current_lap)

    @property
    def pit_stops_completed(self) -> int:
        return int(self.rstate.pit_stops_completed)

    @property
    def best_lap_ms(self) -> int:
        return int(self.rstate.best_lap_ms)

    @property
    def phase(self) -> str:
        return self.rstate.phase.value

    @property
    def plan_block(self) -> str:
        """The race-plan mismatch reason, if activation was blocked on plan coherence."""
        return self._plan_block

    def cue(self, *, advisory: str = "") -> str:
        """The engineer's phase-appropriate line for the current race state."""
        return race_cue(self.rstate, advisory=advisory)

    # -- lifecycle --------------------------------------------------------- #
    def activate(self) -> LivePracticeActivation:
        """Resolve context, gate it as RACE, verify the race plan belongs to this event, and open
        the authoritative run. A blocked gate (wrong session, incomplete context, or a mis-scoped
        race plan) leaves the state untouched and creates nothing."""
        ctx = self._port.resolve_activation_context()
        ctx = ctx if isinstance(ctx, Mapping) else {}
        act = resolve_live_race_activation(
            ctx, planned_session_type=ctx.get("planned_session_type") or ctx.get("session_type"))
        if not act.ok:
            return act
        # Race-specific coherence: the active race plan must be built for THIS event/car/track/
        # layout. A mismatch blocks with a distinct, honest reason (never "incomplete context").
        plan = validate_race_plan_context(ctx)
        if not plan.ok:
            self._plan_block = plan.reason
            return LivePracticeActivation(
                verdict=ActivationVerdict.BLOCKED_INCOMPLETE_CONTEXT, reason=plan.reason)
        self._plan_block = ""
        started = advance_live_run(self.state, LiveRunEvent.START)
        if not started.ok:
            return LivePracticeActivation(
                verdict=ActivationVerdict.BLOCKED_INCOMPLETE_CONTEXT,
                reason=f"cannot start a new run while {self.state.value}")
        self.state = started.state
        self.identity = dict(act.identity)
        # Carry the resolved race-plan identity into the run identity for the diagnostics header.
        for k in ("race_plan_id", "race_plan_revision_id"):
            if k in ctx:
                self.identity[k] = str(ctx.get(k) or "")
        self.run_id, self.stint_id = self._port.create_run(act.identity)
        self.rstate = RaceEngineerState.initial()
        self.last_finalised_lap = 0
        self._valid_laps = 0
        self._invalid_laps = 0
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

    # -- race phase events ------------------------------------------------- #
    def apply_race_event(self, event: RaceEngineerEvent) -> None:
        """Advance the race engineer phase machine on a telemetry-derived event. Phase events act
        only while recording (a stray edge outside the run never mutates the machine)."""
        if self.is_recording or event == RaceEngineerEvent.FINISH:
            self.rstate = apply_event(self.rstate, event)

    def on_lap(self, *, session_run_id: str, event_id, lap_number: int, lap_time_ms: int,
               is_out_lap: bool = False, is_pit_lap: bool = False,
               telemetry_complete: bool = True) -> LapOutcome:
        """Evaluate + persist one completed race lap, and advance the race phase machine. A
        rejected lap writes nothing and never advances the machine."""
        d: LiveLapDecision = evaluate_live_lap(
            run_state=self.state, lap_session_run_id=session_run_id,
            active_session_run_id=self.run_id, lap_event_id=event_id,
            active_event_id=self.event_id, lap_number=lap_number,
            last_finalised_lap=self.last_finalised_lap, lap_time_ms=lap_time_ms,
            is_out_lap=is_out_lap, is_pit_lap=is_pit_lap, telemetry_complete=telemetry_complete)
        if not d.record:
            return LapOutcome(False, False, d.reason)
        self.rstate = on_lap_completed(
            self.rstate, int(lap_time_ms), lap_number=int(lap_number), valid=bool(d.valid))
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
        """Driver ends the race: RECORDING/PAUSED/DISCONNECTED → COMPLETING → COMPLETED, and the
        engineer machine reaches its terminal FINISHED phase."""
        t = advance_live_run(self.state, LiveRunEvent.BEGIN_COMPLETE)
        if not t.ok:
            return False
        self.state = t.state
        self._port.set_run_status(self.run_id, self.state.value)
        f = advance_live_run(self.state, LiveRunEvent.FINALIZE)
        if f.ok:
            self.state = f.state
            self._port.set_run_status(self.run_id, self.state.value)
            self.rstate = apply_event(self.rstate, RaceEngineerEvent.FINISH)
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
