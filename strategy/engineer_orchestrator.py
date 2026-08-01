"""Engineer Orchestrator (Program 3 Phase E12).

One pure entry point that, given the canonical live context, resolves the single
engineer mode and produces one coordinated engineer line — replacing the scattered
routing (``normalise_session_mode`` + ``session_engineer_call`` + the announcer's
own ``_session_mode`` + the track-modelling callout path). It composes the Phase-E
pieces:

  * ``resolve_engineer_mode`` (E1)         — the one mode authority.
  * ``qualifying_state_machine`` (E16)     — used when a qualifying state is supplied.
  * ``practice_brief`` (E14)               — used when a live brief is supplied.
  * ``session_engineer_call`` (existing)   — the fallback line for practice/qualifying.
  * track-modelling callout (existing)     — passed through from the caller.
  * RACE                                   — defers to the strategy engine ("").

It PREFERS the richer state machines when their state is available and otherwise
reproduces today's behaviour exactly, so it is a strict superset and can be adopted
by the live path incrementally. Pure, deterministic, offline, never raises, advisory
only — it emits an intent (a line + the resolved mode); delivery stays with the
announcer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from strategy.engineer_mode import EngineerMode, resolve_engineer_mode
from strategy.live_engineer_session import session_engineer_call
from strategy.practice_brief import PracticeBriefState, practice_status
from strategy.qualifying_state_machine import QualifyingState, qualifying_cue


@dataclass(frozen=True)
class EngineerContext:
    """The single input the engineer needs, formalising what the bridge's ``_feed_live``
    assembles ad hoc each tick. Every field is optional so a partial context still
    yields a safe result."""

    # mode inputs (driver-declared; never inferred)
    live_session_mode: Optional[str] = None
    race_phase: str = ""
    track_modelling_active: bool = False

    # telemetry / lap status (the fallback line's inputs)
    connected: bool = False
    lap_count: int = 0
    last_lap_s: Optional[float] = None
    best_lap_s: Optional[float] = None
    out_lap: bool = False

    # richer per-mode state (preferred when present)
    qualifying_state: Optional[QualifyingState] = None
    practice_brief: Optional[PracticeBriefState] = None
    practice_best_ms: int = 0

    # track modelling — the callout the caller computed via track_convergence
    track_callout: str = ""


@dataclass(frozen=True)
class EngineerOutput:
    mode: EngineerMode
    line: str = ""                      # "" = no line (race defers, or nothing to say)
    defers_to_strategy: bool = False    # True in RACE — the strategy engine drives


def orchestrate(context: EngineerContext) -> EngineerOutput:
    """Resolve the mode and produce one coordinated engineer line. Never raises."""
    try:
        mode = resolve_engineer_mode(
            live_session_mode=context.live_session_mode,
            race_phase=context.race_phase,
            track_modelling_active=context.track_modelling_active,
        )

        if mode == EngineerMode.RACE:
            # the adaptive strategy engine owns the race
            return EngineerOutput(mode=mode, line="", defers_to_strategy=True)

        if mode == EngineerMode.TRACK_MODELLING:
            line = str(context.track_callout or "") if context.connected else ""
            return EngineerOutput(mode=mode, line=line)

        if mode == EngineerMode.QUALIFYING:
            if not context.connected:
                return EngineerOutput(mode=mode, line="")
            if context.qualifying_state is not None:
                line = qualifying_cue(context.qualifying_state,
                                      practice_best_ms=context.practice_best_ms)
            else:
                line = session_engineer_call(
                    "qualifying", connected=context.connected, lap_count=context.lap_count,
                    last_lap_s=context.last_lap_s, best_lap_s=context.best_lap_s,
                    out_lap=context.out_lap)
            return EngineerOutput(mode=mode, line=line)

        # PRACTICE
        if not context.connected:
            return EngineerOutput(mode=mode, line="")
        if context.practice_brief is not None:
            line = practice_status(context.practice_brief)
        else:
            line = session_engineer_call(
                "practice", connected=context.connected, lap_count=context.lap_count,
                last_lap_s=context.last_lap_s, best_lap_s=context.best_lap_s,
                out_lap=context.out_lap)
        return EngineerOutput(mode=mode, line=line)
    except Exception:
        return EngineerOutput(mode=EngineerMode.PRACTICE, line="")
