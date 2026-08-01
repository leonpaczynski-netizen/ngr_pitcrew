"""Race engineer state machine (Live Activation 3, Program 3).

The race analogue of ``qualifying_state_machine``. A race engineer talks by PHASE and by
strategy-relevant EVENT — the grid formation, the lights-out getaway, the settled racing
rhythm, the pit sequence, and the finish — not by a fixed lap cadence. This is that machine:
a pure, deterministic, offline reducer over explicit driver/telemetry events plus a cue
generator for the current phase. Never raises. Advisory only — it issues no command, calls no
pit, changes no setup, and writes nothing beyond its own immutable snapshot.

It deliberately does NOT invent a second physical phase machine. The engineer phases below are
derived from the vocabulary that already exists — ``telemetry.state.RacePhase`` (IDLE / PRE_RACE
/ RACING / IN_PIT / FINISHED) and ``canonical_live_race_state.PitPhase`` — via ``events_from_race_signals``,
so the caller feeds the SAME canonical race-state signals the strategy surface already reads.
Detailed strategy numbers (fuel target, pit window, replan) stay in the deterministic replan
pipeline; this machine only choreographs the engineer's spoken presence around them.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, replace
from typing import Optional, Tuple


class RaceEngineerPhase(str, enum.Enum):
    WAITING = "waiting"          # pre-race: grid / formation, engine not yet racing
    RACE_START = "race_start"    # lights out — the getaway lap
    RACING = "racing"            # settled green-flag racing
    PIT_ENTRY = "pit_entry"      # entering the pit lane
    IN_PIT = "in_pit"            # stationary / in the box
    PIT_EXIT = "pit_exit"        # rejoining after a stop
    FINISHED = "finished"        # chequered flag


class RaceEngineerEvent(str, enum.Enum):
    GRID = "grid"                # sitting on the grid / formation (pre-race)
    LIGHTS_OUT = "lights_out"    # race has started
    SETTLE = "settle"            # first racing lap done — settle into the race
    PIT_ENTRY = "pit_entry"      # crossed the pit-entry line
    PIT_STOPPED = "pit_stopped"  # confirmed stationary in the box
    PIT_EXIT = "pit_exit"        # left the box / rejoining
    REJOINED = "rejoined"        # back to green-flag racing after the stop
    FINISH = "finish"            # chequered flag


def _fmt(ms: int) -> str:
    ms = int(ms or 0)
    if ms <= 0:
        return "—"
    return f"{ms / 1000.0:.3f}"


@dataclass(frozen=True)
class RaceEngineerState:
    phase: RaceEngineerPhase = RaceEngineerPhase.WAITING
    current_lap: int = 0                 # laps started (1-based once racing)
    completed_laps: int = 0              # laps the run has finalised
    pit_stops_completed: int = 0         # confirmed stops so far
    last_lap_ms: int = 0
    best_lap_ms: int = 0
    started: bool = False                # has the race gone green?
    finished: bool = False

    @classmethod
    def initial(cls) -> "RaceEngineerState":
        return cls()


# --- transitions (pure; the caller detects the edge and calls the event) -------

def on_grid(state: RaceEngineerState) -> RaceEngineerState:
    """Pre-race: sitting on the grid / formation lap. Only meaningful before the start."""
    if state.started or state.finished:
        return state
    return replace(state, phase=RaceEngineerPhase.WAITING)


def on_lights_out(state: RaceEngineerState) -> RaceEngineerState:
    """Lights out — the race has begun. Idempotent: a second start signal is ignored."""
    if state.finished or state.started:
        return state
    return replace(state, phase=RaceEngineerPhase.RACE_START, started=True)


def on_settle(state: RaceEngineerState) -> RaceEngineerState:
    """The getaway lap is done — settle into green-flag racing."""
    if state.finished:
        return state
    if state.phase == RaceEngineerPhase.RACE_START:
        return replace(state, phase=RaceEngineerPhase.RACING)
    return state


def on_pit_entry(state: RaceEngineerState) -> RaceEngineerState:
    if state.finished:
        return state
    return replace(state, phase=RaceEngineerPhase.PIT_ENTRY)


def on_pit_stopped(state: RaceEngineerState) -> RaceEngineerState:
    if state.finished:
        return state
    return replace(state, phase=RaceEngineerPhase.IN_PIT)


def on_pit_exit(state: RaceEngineerState) -> RaceEngineerState:
    """Left the box after a stop — count the completed stop and rejoin."""
    if state.finished:
        return state
    # Count the stop only when we were actually in the box / entering the pits, so a spurious
    # pit-exit edge with no preceding stop can never inflate the count.
    counted = state.phase in (RaceEngineerPhase.IN_PIT, RaceEngineerPhase.PIT_ENTRY)
    return replace(state, phase=RaceEngineerPhase.PIT_EXIT,
                   pit_stops_completed=state.pit_stops_completed + (1 if counted else 0))


def on_rejoined(state: RaceEngineerState) -> RaceEngineerState:
    if state.finished:
        return state
    if state.phase == RaceEngineerPhase.PIT_EXIT:
        return replace(state, phase=RaceEngineerPhase.RACING)
    return state


def on_lap_completed(state: RaceEngineerState, lap_ms: int, lap_number: int = 0,
                     valid: bool = True) -> RaceEngineerState:
    """A racing lap crossed the line. Advances the completed-lap total and best lap. Does not
    itself change phase (pit/finish edges do that) beyond leaving RACE_START once a lap is in."""
    try:
        ms = int(lap_ms or 0)
        ln = int(lap_number or 0)
        completed = ln if ln > 0 else int(state.completed_laps) + 1
        is_pb = bool(valid) and ms > 0 and (state.best_lap_ms == 0 or ms < state.best_lap_ms)
        best = ms if is_pb else state.best_lap_ms
        phase = state.phase
        # The first completed racing lap moves us out of the getaway into settled racing.
        if phase == RaceEngineerPhase.RACE_START:
            phase = RaceEngineerPhase.RACING
        return replace(state, completed_laps=completed, current_lap=max(state.current_lap, completed),
                       last_lap_ms=ms, best_lap_ms=best, phase=phase, started=True)
    except Exception:
        return state


def on_finish(state: RaceEngineerState) -> RaceEngineerState:
    """Chequered flag — terminal. Never reopens."""
    return replace(state, phase=RaceEngineerPhase.FINISHED, finished=True)


# --- signal → events mapping (reuse the canonical race-state vocabulary) --------

def events_from_race_signals(
    prev_race_phase: Optional[str],
    race_phase: Optional[str],
    *,
    prev_pit_phase: Optional[str] = None,
    pit_phase: Optional[str] = None,
    finished: bool = False,
) -> Tuple[RaceEngineerEvent, ...]:
    """Translate an edge in the canonical race-state signals into ordered engineer events.

    ``race_phase`` values are ``telemetry.state.RacePhase`` names (idle/pre_race/racing/in_pit/
    finished, case-insensitive); ``pit_phase`` values are ``canonical_live_race_state.PitPhase``
    names. Deterministic and edge-based: an unchanged signal yields no event, so the machine only
    ever advances on a genuine transition. Never raises."""
    def _n(v) -> str:
        return "" if v is None else str(v).strip().lower()

    rp, prp = _n(race_phase), _n(prev_race_phase)
    events: list = []
    if finished or rp == "finished":
        return (RaceEngineerEvent.FINISH,)
    if rp != prp:
        if rp == "pre_race":
            events.append(RaceEngineerEvent.GRID)
        elif rp == "racing" and prp in ("", "idle", "pre_race"):
            events.append(RaceEngineerEvent.LIGHTS_OUT)
        elif rp == "in_pit":
            events.append(RaceEngineerEvent.PIT_ENTRY)
        elif rp == "racing" and prp == "in_pit":
            events.append(RaceEngineerEvent.PIT_EXIT)
    # Finer pit sequence from the pit-phase confidence machine, if provided.
    pp, ppp = _n(pit_phase), _n(prev_pit_phase)
    if pp != ppp:
        if pp in ("pit_entry_suspected",):
            events.append(RaceEngineerEvent.PIT_ENTRY)
        elif pp in ("pit_confirmed", "stop_completed"):
            events.append(RaceEngineerEvent.PIT_STOPPED)
        elif pp == "pit_exit":
            events.append(RaceEngineerEvent.PIT_EXIT)
    return tuple(events)


def apply_event(state: RaceEngineerState, event: RaceEngineerEvent) -> RaceEngineerState:
    """Dispatch one engineer event to its reducer. Unknown events leave state unchanged."""
    return {
        RaceEngineerEvent.GRID: on_grid,
        RaceEngineerEvent.LIGHTS_OUT: on_lights_out,
        RaceEngineerEvent.SETTLE: on_settle,
        RaceEngineerEvent.PIT_ENTRY: on_pit_entry,
        RaceEngineerEvent.PIT_STOPPED: on_pit_stopped,
        RaceEngineerEvent.PIT_EXIT: on_pit_exit,
        RaceEngineerEvent.REJOINED: on_rejoined,
        RaceEngineerEvent.FINISH: on_finish,
    }.get(event, lambda s: s)(state)


# --- cue (the engineer's line for the current phase) ---------------------------

def race_cue(state: RaceEngineerState, *, advisory: str = "") -> str:
    """The engineer's minimal, phase-appropriate line. Race chatter is disciplined: a short line
    on each phase edge, calm under pressure, never burying a strategy advisory. ``advisory`` is an
    optional deterministic strategy line (from the replan pipeline) the engineer may relay verbatim
    — this machine authors no strategy of its own. Never raises."""
    try:
        p = state.phase
        if p == RaceEngineerPhase.WAITING:
            return "On the grid. Systems checked — stay calm, we race our own race."
        if p == RaceEngineerPhase.RACE_START:
            return "Lights out. Clean getaway, look after the tyres through lap one."
        if p == RaceEngineerPhase.RACING:
            base = "Settle in — hit your marks and keep it consistent."
            return (advisory.strip() or base) if advisory else base
        if p == RaceEngineerPhase.PIT_ENTRY:
            return "Pit entry — pit lane speed limiter on."
        if p == RaceEngineerPhase.IN_PIT:
            return "In the box. We'll get you back out clean."
        if p == RaceEngineerPhase.PIT_EXIT:
            n = state.pit_stops_completed
            tail = f" That's stop {n}." if n else ""
            return f"Out you go — mind the cold tyres for a lap.{tail}"
        if p == RaceEngineerPhase.FINISHED:
            best = _fmt(state.best_lap_ms)
            return f"Chequered flag — that's the race done. Best lap {best}. Well driven."
        return ""
    except Exception:
        return ""
