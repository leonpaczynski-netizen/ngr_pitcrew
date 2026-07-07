"""Group 60 — Correctness-preserving live-progress stabilisation (pure).

WHY IT EXISTS
  Live map-matched progress can jitter (nearest-station flip-flop) and can jump when
  a sample is noisy or a lap wraps. This module reduces false certainty WITHOUT ever
  lying about position: it keeps the GLOBAL nearest station as the correctness anchor
  and only (a) reports whether a local continuity window agreed, and (b) DOWNGRADES
  confidence when a progress jump is implausible.

HARD INVARIANTS (Group 60 Goal 3/4)
  • The GLOBAL nearest is always the returned match — a local/continuity candidate
    NEVER replaces it. This is safe on crossings, hairpins, chicanes, and parallel
    sections, where a naive local window could otherwise pick a wrong-but-near station.
  • Confidence is only ever DOWNGRADED, never inflated. Fallback progress is never
    made HIGH. Unknown stays unknown.
  • The reported progress VALUE is never changed (no smoothing that moves position).
  • It touches NO pit-lane state: it never corroborates a pit, never lifts pit
    confidence, never creates or mutates a pit count.
  • Pure: no Qt, no DB, no AI, no filesystem. Never raises.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple

from data.live_track_progress import (
    LiveTrackProgressResult,
    TrackPathStation,
    TrackProgressConfidence,
    nearest_station,
)

# Confidence ordering (for min-only downgrades).
_CONF_ORDER = {
    TrackProgressConfidence.UNKNOWN: 0,
    TrackProgressConfidence.LOW: 1,
    TrackProgressConfidence.MEDIUM: 2,
    TrackProgressConfidence.HIGH: 3,
}
_CONF_BY_ORDER = {v: k for k, v in _CONF_ORDER.items()}

# A forward progress step larger than this (and not a near-zero backward jitter or a
# lap wrap) is treated as implausible → confidence downgraded.
_DEFAULT_MAX_JUMP = 0.15
# Local continuity window is accepted as "agreeing" only within this XZ tolerance (m)
# of the global-nearest distance — it never overrides the global result regardless.
_CONTINUITY_TOL_M = 2.0


@dataclass(frozen=True)
class StabilisedProgress:
    """A live progress result with a (possibly downgraded) stabilised confidence."""
    result: LiveTrackProgressResult
    stabilised_confidence: TrackProgressConfidence
    jumped: bool = False
    continuity_ok: bool = False
    notes: Tuple[str, ...] = ()

    @property
    def progress(self) -> Optional[float]:
        return self.result.progress if self.result is not None else None


def _min_conf(a: TrackProgressConfidence, b: TrackProgressConfidence) -> TrackProgressConfidence:
    return _CONF_BY_ORDER[min(_CONF_ORDER[a], _CONF_ORDER[b])]


# ---------------------------------------------------------------------------
# Nearest station with an OPTIONAL continuity hint (global result always wins)
# ---------------------------------------------------------------------------

def nearest_station_stabilised(
    position,
    stations,
    *,
    hint_index: Optional[int] = None,
    window: int = 8,
) -> Optional[Tuple[int, float, bool]]:
    """Return ``(global_index, global_distance, continuity_ok)`` or None. Never raises.

    The returned index/distance are ALWAYS the true GLOBAL nearest (full scan) — the
    local window is used only to compute ``continuity_ok`` (whether a station within
    ``window`` of ``hint_index`` is the same as, or within a strict tolerance of, the
    global nearest). A local candidate never replaces the global result.
    """
    try:
        g = nearest_station(position, stations)
        if g is None:
            return None
        g_idx, g_dist = g
        continuity_ok = False
        if hint_index is not None:
            valid = [s for s in (stations or []) if isinstance(s, TrackPathStation)]
            n = len(valid)
            if n:
                try:
                    h = int(hint_index)
                except (TypeError, ValueError):
                    h = None
                if h is not None:
                    coords = _coords(position)
                    if coords is not None:
                        px, pz = coords
                        best_local = None
                        best_local_idx = None
                        for off in range(-abs(int(window)), abs(int(window)) + 1):
                            j = (h + off) % n
                            s = valid[j]
                            d = math.hypot(px - s.x, pz - s.z)
                            if best_local is None or d < best_local:
                                best_local = d
                                best_local_idx = s.index
                        # Continuity holds only when the local best IS the global best,
                        # or is within a strict tolerance of it (never overrides global).
                        if best_local_idx == g_idx or (
                                best_local is not None and abs(best_local - g_dist) <= _CONTINUITY_TOL_M):
                            continuity_ok = True
        return (g_idx, g_dist, continuity_ok)
    except Exception:
        return None


def _coords(position) -> Optional[Tuple[float, float]]:
    """(x, z) from a (x,y,z)/(x,z) tuple, object, or dict; None if unusable."""
    try:
        if position is None:
            return None
        if isinstance(position, (tuple, list)):
            if len(position) == 2:
                x, z = position[0], position[1]
            elif len(position) >= 3:
                x, z = position[0], position[2]
            else:
                return None
        else:
            def _pick(*names):
                for nm in names:
                    if isinstance(position, dict) and nm in position:
                        return position[nm]
                    if not isinstance(position, dict) and hasattr(position, nm):
                        return getattr(position, nm)
                return None
            x = _pick("x", "pos_x")
            z = _pick("z", "pos_z")
        fx, fz = float(x), float(z)
        if fx != fx or fz != fz or fx in (float("inf"), float("-inf")) or fz in (float("inf"), float("-inf")):
            return None
        return (fx, fz)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Progress stabilisation (confidence-only; never changes the reported value)
# ---------------------------------------------------------------------------

def _forward_delta(prev_p: float, cur_p: float) -> float:
    """Forward progress step in [0,1): small values = normal forward / lap wrap."""
    d = (cur_p - prev_p) % 1.0
    if d < 0.0:
        d += 1.0
    return d


def stabilise_progress(
    current: LiveTrackProgressResult,
    previous: Optional[LiveTrackProgressResult] = None,
    *,
    max_progress_jump: float = _DEFAULT_MAX_JUMP,
    continuity_ok: Optional[bool] = None,
) -> StabilisedProgress:
    """Return a stabilised view of ``current``. Never raises.

    Rules (all safety-preserving):
      • The progress VALUE is passed through unchanged (never smoothed/moved).
      • If the step from ``previous`` is an implausible jump (large, not a lap wrap,
        not near-zero backward jitter) → confidence is DOWNGRADED (cap at LOW) and a
        note is added. Confidence is never inflated.
      • ``continuity_ok`` (from ``nearest_station_stabilised``) is recorded but never
        raises confidence — it only annotates a stable match.
    """
    try:
        if current is None:
            return StabilisedProgress(
                result=LiveTrackProgressResult(), stabilised_confidence=TrackProgressConfidence.UNKNOWN,
                notes=("no current progress",))

        conf = current.confidence
        notes: list = []
        jumped = False

        if (previous is not None and getattr(previous, "has_progress", False)
                and getattr(current, "has_progress", False)
                and previous.progress is not None and current.progress is not None):
            fd = _forward_delta(previous.progress, current.progress)
            # Plausible: small forward step (incl. lap wrap) OR near-zero backward jitter.
            plausible = fd <= max_progress_jump or fd >= (1.0 - max_progress_jump)
            if not plausible:
                jumped = True
                conf = _min_conf(conf, TrackProgressConfidence.LOW)
                notes.append("implausible progress jump — confidence downgraded "
                             "(position value unchanged)")
        elif previous is not None and getattr(current, "has_progress", False):
            notes.append("no previous progress to compare — continuity unknown")

        if continuity_ok:
            notes.append("stable match (local continuity agrees with global nearest)")

        # Never inflate: the stabilised confidence can only be <= the current one.
        conf = _min_conf(conf, current.confidence)

        return StabilisedProgress(
            result=current, stabilised_confidence=conf, jumped=jumped,
            continuity_ok=bool(continuity_ok), notes=tuple(notes))
    except Exception:
        # On any error, pass the input through untouched (never fabricate certainty).
        c = current if isinstance(current, LiveTrackProgressResult) else LiveTrackProgressResult()
        return StabilisedProgress(result=c, stabilised_confidence=c.confidence,
                                  notes=("stabiliser error — passthrough",))


# ---------------------------------------------------------------------------
# Stateful holder (Group 61) — retains previous progress across live refreshes
# ---------------------------------------------------------------------------

class LiveProgressStabiliserState:
    """A tiny, explicit state holder that carries previous progress between updates.

    Pure logic (Qt-free, no I/O). It resets automatically when the identity key
    (track/layout/car/session) changes, so state never bleeds across sessions,
    tracks, or cars. It only ever produces a ``StabilisedProgress`` — it never
    changes the reported progress value, never inflates confidence, and touches no
    pit state. Never raises.
    """

    def __init__(self, *, max_progress_jump: float = _DEFAULT_MAX_JUMP):
        self._max_jump = float(max_progress_jump)
        self._prev: Optional[LiveTrackProgressResult] = None
        self._identity_key: str = ""

    def reset(self) -> None:
        self._prev = None
        self._identity_key = ""

    @property
    def identity_key(self) -> str:
        return self._identity_key

    def update(self, current: LiveTrackProgressResult, *,
               identity_key: str = "", continuity_ok: Optional[bool] = None
               ) -> StabilisedProgress:
        """Stabilise ``current`` against the retained previous result. Never raises."""
        try:
            key = str(identity_key or "")
            if key != self._identity_key:
                # New session/track/car → drop stale history.
                self._prev = None
                self._identity_key = key
            sp = stabilise_progress(current, self._prev,
                                    max_progress_jump=self._max_jump,
                                    continuity_ok=continuity_ok)
            # Retain only real progress as the next comparison anchor.
            if current is not None and getattr(current, "has_progress", False):
                self._prev = current
            return sp
        except Exception:
            c = current if isinstance(current, LiveTrackProgressResult) else LiveTrackProgressResult()
            return StabilisedProgress(result=c, stabilised_confidence=c.confidence,
                                      notes=("stabiliser state error — passthrough",))
