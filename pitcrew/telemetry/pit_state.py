"""Group 54 — Race Strategy Brain Phase 8: pure live pit & stint state model.

WHY IT EXISTS
  The Group 53 live replan capped at LOW_CONFIDENCE because the app tracked neither
  pit-stop count nor tyre age. The `RaceStateTracker` DOES already detect pit
  entry/exit (fuel-refuel + a conservative speed-stop heuristic — GT7 broadcasts no
  pit flag), it just never counted stops or aged the current stint. This module is
  the small, pure, deterministic state machine the tracker feeds those existing
  events into, so live replan can judge tyre age and pit count honestly.

WHAT THIS MODULE IS
  A pure function-over-frozen-dataclass model: `apply` functions take the current
  `PitStintState` and an event, and return the next state. It writes no files, calls
  no AI, applies no action, and never fabricates a pit stop — it only counts events
  it is explicitly given, each carrying an honest detection confidence.

HONESTY RULES (Group 54 §2/§3)
  • Before any pit, `pit_stops_completed == 0` is CERTAIN and `laps_since_pit`
    equals the stint age (the tyres are the ones started on) → confidence HIGH.
  • A pit detected via a real refuel is MEDIUM; a speed-only no-refuel stop is LOW.
  • Duplicate pit events on the same lap do not double-count.
  • Invalid / negative laps are ignored (never advance the counter).
  • Unknown state (tracking never started) stays UNKNOWN — never assumed safe.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Optional


class PitEvent(str, Enum):
    NONE = "none"
    ENTER = "enter"
    EXIT = "exit"          # a completed pit stop (car returned to track)
    MANUAL = "manual"      # user-asserted pit marker


class PitDetectionConfidence(str, Enum):
    HIGH = "HIGH"          # certain (no pit yet, or an explicit source)
    MEDIUM = "MEDIUM"      # refuel-based pit detection (reliable)
    LOW = "LOW"            # speed-only heuristic (uncertain)
    UNKNOWN = "UNKNOWN"    # tracking not started → pit/tyre state unknown


@dataclass(frozen=True)
class PitStintState:
    """Runtime-only pit + stint state. Frozen — updaters return new instances."""
    pit_stops_completed: int = 0
    current_stint_index: int = 0
    current_stint_start_lap: int = 0
    laps_since_pit: int = 0
    last_pit_lap: Optional[int] = None
    last_pit_event: PitEvent = PitEvent.NONE
    pit_detection_confidence: PitDetectionConfidence = PitDetectionConfidence.UNKNOWN
    pit_detection_source: str = ""
    tracking_active: bool = False
    warnings: tuple[str, ...] = ()

    @property
    def tyre_age_laps(self) -> Optional[int]:
        """Laps on the current tyre set (== laps_since_pit) or None when unknown.

        This ASSUMES a detected pit stop included a tyre change (GT7 does not report
        whether tyres were changed). Before the first pit it is exact. Advisory only.
        """
        return self.laps_since_pit if self.tracking_active else None

    @property
    def pit_count_known(self) -> bool:
        return self.tracking_active

    @property
    def missing_state(self) -> tuple[str, ...]:
        if self.tracking_active:
            return ()
        return ("pit_stops_completed", "tyre_age_laps")


class PitStateUpdateResult(tuple):
    """(state, counted) — the next state and whether a pit was counted this update."""
    __slots__ = ()

    def __new__(cls, state: PitStintState, counted: bool):
        return super().__new__(cls, (state, counted))

    @property
    def state(self) -> PitStintState:
        return self[0]

    @property
    def counted(self) -> bool:
        return self[1]


# ---------------------------------------------------------------------------
# Pure updaters
# ---------------------------------------------------------------------------

def start_stint_tracking(state: PitStintState, *, start_lap: int = 0) -> PitStintState:
    """Begin tracking at race start: 0 pits (certain), stint age from start_lap."""
    try:
        sl = int(start_lap) if start_lap is not None and int(start_lap) >= 0 else 0
    except (TypeError, ValueError):
        sl = 0
    return PitStintState(
        pit_stops_completed=0,
        current_stint_index=0,
        current_stint_start_lap=sl,
        laps_since_pit=0,
        last_pit_lap=None,
        last_pit_event=PitEvent.NONE,
        pit_detection_confidence=PitDetectionConfidence.HIGH,   # 0 pits so far is certain
        pit_detection_source="race start (no pit yet)",
        tracking_active=True,
        warnings=(),
    )


def apply_lap_completed(state: PitStintState, lap_num: Optional[int] = None) -> PitStintState:
    """Advance the current stint age by one lap. Ignores invalid laps and no-ops
    when tracking has not started."""
    if not state.tracking_active:
        return state
    if lap_num is not None:
        try:
            if int(lap_num) < 0:
                return replace(state, warnings=_add(state.warnings,
                              "Ignored a lap update with a negative lap number."))
        except (TypeError, ValueError):
            return state
    return replace(state, laps_since_pit=state.laps_since_pit + 1)


def apply_pit_event(
    state: PitStintState,
    *,
    pit_lap: int,
    confidence: PitDetectionConfidence,
    source: str,
    event: PitEvent = PitEvent.EXIT,
) -> PitStateUpdateResult:
    """Count one completed pit stop and reset the stint age.

    Deduplicates: a pit event on the SAME lap as the last counted stop is not
    double-counted. Only ENTER/EXIT/MANUAL events count; NONE never counts.
    ``confidence`` is the certainty of the resulting count (MEDIUM refuel / LOW
    speed-only / HIGH manual-or-explicit). Returns (next_state, counted).
    """
    if event not in (PitEvent.ENTER, PitEvent.EXIT, PitEvent.MANUAL):
        return PitStateUpdateResult(state, False)
    if not state.tracking_active:
        # Allow a manual marker to implicitly start tracking honestly.
        if event == PitEvent.MANUAL:
            state = start_stint_tracking(state, start_lap=_safe_lap(pit_lap))
        else:
            return PitStateUpdateResult(state, False)

    pl = _safe_lap(pit_lap)
    if state.last_pit_lap is not None and pl == state.last_pit_lap and state.pit_stops_completed > 0:
        return PitStateUpdateResult(state, False)  # duplicate on the same lap

    conf = confidence if isinstance(confidence, PitDetectionConfidence) else PitDetectionConfidence.LOW
    new = replace(
        state,
        pit_stops_completed=state.pit_stops_completed + 1,
        current_stint_index=state.current_stint_index + 1,
        current_stint_start_lap=pl,
        laps_since_pit=0,
        last_pit_lap=pl,
        last_pit_event=event,
        pit_detection_confidence=conf,
        pit_detection_source=str(source or ""),
    )
    return PitStateUpdateResult(new, True)


def apply_manual_pit(state: PitStintState, *, pit_lap: int) -> PitStintState:
    """Convenience: record a user-asserted pit marker (labelled manual)."""
    return apply_pit_event(state, pit_lap=pit_lap, confidence=PitDetectionConfidence.MEDIUM,
                           source="manual", event=PitEvent.MANUAL).state


# ---------------------------------------------------------------------------
# Detection-confidence classifier (used by the tracker at pit exit)
# ---------------------------------------------------------------------------

def classify_pit_confidence(fuel_added: float, pit_threshold: float) -> PitDetectionConfidence:
    """MEDIUM when a real refuel was detected; LOW for a speed-only (no-refuel) stop.

    A refuel is the most reliable pit signal the app has (GT7 has no pit flag), so it
    earns MEDIUM; a stop detected purely from low speed is LOW confidence.
    """
    try:
        if fuel_added is not None and pit_threshold is not None and float(fuel_added) >= float(pit_threshold):
            return PitDetectionConfidence.MEDIUM
    except (TypeError, ValueError):
        pass
    return PitDetectionConfidence.LOW


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _safe_lap(x) -> int:
    try:
        v = int(x)
        return v if v >= 0 else 0
    except (TypeError, ValueError):
        return 0


def _add(warnings: tuple, msg: str) -> tuple:
    return warnings + (msg,) if msg not in warnings else warnings
