"""Qualifying state machine (Program 3 Phase E16).

A real qualifying engineer talks by PHASE, not by lap count: focus the driver in the
pits, guide the out-lap tyre prep, go quiet on the flying lap, report the completed
attempt (personal best / deleted), then manage the cooldown and the next attempt.

Today only lap-counter fragments exist (the announcer's ``_qualifying_lap_count`` /
``_is_flying_lap``); there is no formal machine. This is that machine: a pure,
deterministic, offline reducer over explicit driver events (pit exit, lap completed,
box) plus a cue generator for the current phase. Never raises. Advisory only — it
issues no command and changes no state beyond its own immutable snapshot.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, replace
from typing import Optional


class QualifyingPhase(str, enum.Enum):
    PREPARATION = "preparation"    # in the pits / garage, before the out-lap
    OUT_LAP = "out_lap"            # left the pits, bringing tyres up to temperature
    FLYING_LAP = "flying_lap"      # the timed lap is underway — minimal chatter
    LAP_COMPLETE = "lap_complete"  # just crossed the line; report the attempt
    COOLDOWN = "cooldown"          # backing off / deciding the next attempt or box


def _fmt(ms: int) -> str:
    ms = int(ms or 0)
    if ms <= 0:
        return "—"
    return f"{ms / 1000.0:.3f}"


@dataclass(frozen=True)
class QualifyingState:
    phase: QualifyingPhase = QualifyingPhase.PREPARATION
    attempt: int = 0                    # flying-lap attempt number (1-based once out)
    laps_since_pit_exit: int = 0        # 0 while on the out-lap
    best_lap_ms: int = 0                # personal best this session (0 = none)
    last_lap_ms: int = 0
    last_lap_valid: bool = True
    last_lap_was_pb: bool = False
    last_invalidation_reason: str = ""

    @classmethod
    def initial(cls) -> "QualifyingState":
        return cls()


# --- transitions (pure; the caller detects the edge and calls the event) -------

def on_pit_exit(state: QualifyingState) -> QualifyingState:
    """Driver left the pits — a new attempt's out-lap begins."""
    try:
        return replace(state, phase=QualifyingPhase.OUT_LAP,
                       attempt=int(state.attempt) + 1, laps_since_pit_exit=0)
    except Exception:
        return state


def on_lap_completed(state: QualifyingState, lap_ms: int, valid: bool = True,
                     invalidation_reason: str = "") -> QualifyingState:
    """A lap crossed the line. Out-lap → the flying lap is now underway; flying lap →
    record the attempt (PB / deleted) and enter LAP_COMPLETE."""
    try:
        lsp = int(state.laps_since_pit_exit) + 1
        if state.phase == QualifyingPhase.OUT_LAP:
            return replace(state, phase=QualifyingPhase.FLYING_LAP, laps_since_pit_exit=lsp)
        if state.phase == QualifyingPhase.FLYING_LAP:
            ms = int(lap_ms or 0)
            is_pb = bool(valid) and ms > 0 and (state.best_lap_ms == 0 or ms < state.best_lap_ms)
            best = ms if is_pb else state.best_lap_ms
            return replace(
                state, phase=QualifyingPhase.LAP_COMPLETE, laps_since_pit_exit=lsp,
                last_lap_ms=ms, last_lap_valid=bool(valid), last_lap_was_pb=is_pb,
                best_lap_ms=best, last_invalidation_reason=("" if valid else str(invalidation_reason or "")))
        # a lap completed while cooling down / preparing → stay in cooldown
        return replace(state, phase=QualifyingPhase.COOLDOWN, laps_since_pit_exit=lsp)
    except Exception:
        return state


def on_cooldown(state: QualifyingState) -> QualifyingState:
    """After a completed attempt, settle into the cooldown / next-attempt decision."""
    if state.phase == QualifyingPhase.LAP_COMPLETE:
        return replace(state, phase=QualifyingPhase.COOLDOWN)
    return state


def on_box(state: QualifyingState) -> QualifyingState:
    """Driver returned to the pits — back to preparation for a fresh set / attempt."""
    return replace(state, phase=QualifyingPhase.PREPARATION)


# --- cue (the engineer's line for the current phase) ---------------------------

def qualifying_cue(state: QualifyingState, *, practice_best_ms: int = 0) -> str:
    """The engineer's minimal, phase-appropriate line. Flying-lap feedback is
    deliberately terse (non-distracting); invalidation and viability are always
    reported on completion. ``practice_best_ms`` lets the out-lap recall the
    driver's practice reference. Never raises."""
    try:
        p = state.phase
        if p == QualifyingPhase.PREPARATION:
            ref = (f" Your practice best was {_fmt(practice_best_ms)} — that's the target."
                   if practice_best_ms and practice_best_ms > 0 else "")
            return ("Focus — this is one lap. When you're ready, head out for your "
                    "out-lap." + ref)
        if p == QualifyingPhase.OUT_LAP:
            return ("Out-lap — build tyre temperature and keep it clean. Your flying "
                    "lap is next.")
        if p == QualifyingPhase.FLYING_LAP:
            return "This is your lap — commit."  # minimal, non-distracting
        if p == QualifyingPhase.LAP_COMPLETE:
            if not state.last_lap_valid:
                reason = state.last_invalidation_reason or "lap deleted"
                return (f"Lap deleted — {reason}. Reset, cool the tyres and we go again.")
            if state.last_lap_was_pb:
                return (f"Personal best, {_fmt(state.last_lap_ms)}. Tyres are in — "
                        "you've got another one in you.")
            gap = ""
            if state.best_lap_ms and state.last_lap_ms > state.best_lap_ms:
                gap = f" — {(state.last_lap_ms - state.best_lap_ms) / 1000.0:.3f} off your best"
            return f"Lap in at {_fmt(state.last_lap_ms)}{gap}."
        # COOLDOWN
        return ("Cool the tyres — one clean lap, then go again, or box for a fresh "
                "set if you want new rubber.")
    except Exception:
        return ""
