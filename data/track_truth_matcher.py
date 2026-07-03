"""Track Truth Matcher — Group 18A.

Maps a real-time XYZ telemetry position to the nearest TrackStation in a
TrackTruthModel, enriching it with corner, sector, complex, and pit context.

Pure Python — no PyQt6 dependency.

Scoring constants (tunable — no magic numbers buried in logic)
--------------------------------------------------------------
W_SPATIAL    = 0.60  — XZ-plane distance score
W_HEADING    = 0.15  — heading alignment score
W_PROGRESS   = 0.15  — monotonic-progress preference score
W_BACKWARD   = 0.05  — backward-move penalty component
W_JUMP       = 0.05  — implausible-jump penalty component

These weights are designed to be swapped for a full HMM / Viterbi hidden-state
filter in a later group without changing the public API.

Public API
----------
match_track_truth_position(inp, model, validation=None) -> TrackTruthMatchResult
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

from data.track_truth import (
    TrackTruthModel,
    TrackTruthConfidence,
    TrackTruthValidationResult,
    can_use_track_truth_for_ai_corner_context,
    TrackStation,
)


# ---------------------------------------------------------------------------
# Scoring weight constants (swap for HMM/Viterbi in a later group)
# ---------------------------------------------------------------------------
W_SPATIAL:   float = 0.60
W_HEADING:   float = 0.15
W_PROGRESS:  float = 0.15
W_BACKWARD:  float = 0.05
W_JUMP:      float = 0.05

# Spatial confidence band thresholds (mirror track_map_matching.py constants)
CONFIDENCE_HIGH_M: float = 5.0
CONFIDENCE_MED_M:  float = 20.0
PIT_DISTANCE_M:    float = 60.0

# Speed below which a position is likely parked/pit-stopped
MIN_SPEED_KPH: float = 8.0

# For monotonic-progress: lap-wrap threshold
_LAP_WRAP_PREV_PCT:  float = 90.0
_LAP_WRAP_CAND_PCT:  float = 10.0


# ---------------------------------------------------------------------------
# Input / output dataclasses
# ---------------------------------------------------------------------------

@dataclass
class TrackTruthMatchInput:
    """Telemetry position + context used to match against a TrackTruthModel."""
    x:                    float
    y:                    float
    z:                    float = 0.0
    speed_kph:            float = 0.0
    heading_rad:          Optional[float] = None
    lap_count:            Optional[int]   = None
    previous_station_id:  Optional[str]   = None
    previous_progress_pct: Optional[float] = None
    dt_s:                 Optional[float] = None
    pit_state:            Optional[str]   = None


@dataclass
class TrackTruthMatchResult:
    """Result of matching one telemetry position to a TrackTruthModel."""
    station_id:                  Optional[str]
    distance_m:                  Optional[float]
    progress_pct:                Optional[float]
    corner_id:                   Optional[str]
    corner_phase:                str
    complex_id:                  Optional[str]
    sector_id:                   Optional[str]
    pit_context:                 Optional[str]
    lateral_offset_m:            float
    heading_delta_rad:           float
    confidence:                  TrackTruthConfidence
    is_usable_for_ai_corner_context: bool
    warnings:                    List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Private scoring helper
# ---------------------------------------------------------------------------

def _score_candidate(
    station:           TrackStation,
    inp:               TrackTruthMatchInput,
    prev_progress_pct: Optional[float],
    prev_station:      Optional[TrackStation],
) -> float:
    """Score one candidate station against the match input.

    Returns a float in approximately [0, 1] — higher is better.
    Designed to be swapped for a HMM / Viterbi transition model later.
    """
    # ── Spatial score ────────────────────────────────────────────────────
    dist_xz = math.sqrt((inp.x - station.x) ** 2 + (inp.z - station.z) ** 2)
    if dist_xz <= CONFIDENCE_HIGH_M:
        spatial_score = 1.0
    elif dist_xz <= CONFIDENCE_MED_M:
        spatial_score = 0.7
    elif dist_xz <= PIT_DISTANCE_M:
        spatial_score = 0.3
    else:
        spatial_score = 0.0

    # ── Heading score ────────────────────────────────────────────────────
    if inp.heading_rad is not None and station.heading_rad != 0.0:
        delta = inp.heading_rad - station.heading_rad
        # Wrap to [-π, π]
        delta = (delta + math.pi) % (2 * math.pi) - math.pi
        heading_score = max(0.0, math.cos(delta))
    else:
        heading_score = 0.5   # neutral: no reward or penalty

    # ── Progress / monotonic score ───────────────────────────────────────
    progress_score  = 1.0
    backward_score  = 1.0   # 1.0 = no backward penalty, 0.0 = max penalty

    if prev_progress_pct is not None:
        cand_pct = station.progress_pct
        # Detect lap wrap: previous near end, candidate near start
        is_lap_wrap = (
            prev_progress_pct > _LAP_WRAP_PREV_PCT
            and cand_pct < _LAP_WRAP_CAND_PCT
        )
        if cand_pct >= prev_progress_pct:
            # Forward progress — preferred
            progress_score = 1.0
        elif is_lap_wrap:
            # Lap wrap — not penalised
            progress_score = 1.0
        else:
            # Backward move
            backward_delta = prev_progress_pct - cand_pct
            if backward_delta > 1.0:
                backward_score = max(0.0, 1.0 - backward_delta / 10.0)
                progress_score = 0.5
            else:
                # Small (<1%) backward jitter — mild reduction
                progress_score = 0.9

    # ── Jump penalty ─────────────────────────────────────────────────────
    jump_score = 1.0
    if (
        prev_station is not None
        and inp.dt_s is not None and inp.dt_s > 0.0
        and inp.speed_kph > 0.0
    ):
        # Maximum plausible movement in dt_s at current speed
        max_movement_m = (inp.speed_kph / 3.6) * inp.dt_s * 2.5   # 2.5× safety factor
        # Distance between previous station and candidate station
        jump_dist_m = math.sqrt(
            (station.x - prev_station.x) ** 2
            + (station.z - prev_station.z) ** 2
        )
        if jump_dist_m > max_movement_m and max_movement_m > 0:
            overshoot = jump_dist_m / max_movement_m
            jump_score = max(0.0, 1.0 - (overshoot - 1.0) / 5.0)

    # ── Weighted sum ─────────────────────────────────────────────────────
    score = (
        W_SPATIAL   * spatial_score
        + W_HEADING * heading_score
        + W_PROGRESS * progress_score
        + W_BACKWARD * backward_score
        + W_JUMP     * jump_score
    )
    return score


def _lateral_offset(
    px: float, pz: float,
    sx: float, sz: float,
    heading_rad: float,
) -> float:
    """Signed lateral offset of (px, pz) from station at (sx, sz) with given heading.

    Positive = left of centreline (in direction of travel), matching track_map_matching.py.
    """
    dx = px - sx
    dz = pz - sz
    left_x =  math.cos(heading_rad)
    left_z = -math.sin(heading_rad)
    return dx * left_x + dz * left_z


# ---------------------------------------------------------------------------
# Public match function
# ---------------------------------------------------------------------------

def match_track_truth_position(
    inp:        TrackTruthMatchInput,
    model:      Optional[TrackTruthModel],
    validation: Optional[TrackTruthValidationResult] = None,
) -> TrackTruthMatchResult:
    """Match a telemetry position to the nearest station in model.

    Never raises — the whole body is wrapped in try/except.
    Returns a placeholder result on any error or when model is None / has no stations.
    """
    _placeholder_warnings: List[str] = []

    def _placeholder(extra: str = "") -> TrackTruthMatchResult:
        w = list(_placeholder_warnings)
        if extra:
            w.append(extra)
        return TrackTruthMatchResult(
            station_id               = None,
            distance_m               = None,
            progress_pct             = None,
            corner_id                = None,
            corner_phase             = "unknown",
            complex_id               = None,
            sector_id                = None,
            pit_context              = None,
            lateral_offset_m         = 0.0,
            heading_delta_rad        = 0.0,
            confidence               = TrackTruthConfidence.NONE,
            is_usable_for_ai_corner_context = False,
            warnings                 = w,
        )

    try:
        if model is None:
            return _placeholder("TrackTruthModel is None")

        if not model.stations:
            return _placeholder("TrackTruthModel has no stations — cannot match position")

        # Build a lookup from station_id to station for the jump-penalty check
        station_by_id = {st.station_id: st for st in model.stations}
        prev_station: Optional[TrackStation] = (
            station_by_id.get(inp.previous_station_id)
            if inp.previous_station_id else None
        )

        # Score every station
        best_station: Optional[TrackStation] = None
        best_score = -float("inf")

        for station in model.stations:
            score = _score_candidate(
                station,
                inp,
                inp.previous_progress_pct,
                prev_station,
            )
            if score > best_score:
                best_score    = score
                best_station  = station

        if best_station is None:
            return _placeholder("No best station found (empty model)")

        # ── Distance and confidence ──────────────────────────────────────
        dist_xz = math.sqrt(
            (inp.x - best_station.x) ** 2
            + (inp.z - best_station.z) ** 2
        )

        if dist_xz <= CONFIDENCE_HIGH_M:
            confidence = TrackTruthConfidence.HIGH
        elif dist_xz <= CONFIDENCE_MED_M:
            confidence = TrackTruthConfidence.MEDIUM
        elif dist_xz <= PIT_DISTANCE_M:
            confidence = TrackTruthConfidence.LOW
        else:
            confidence = TrackTruthConfidence.NONE

        # ── Backward-move confidence downgrade ───────────────────────────
        match_warnings: List[str] = []
        if inp.previous_progress_pct is not None:
            cand_pct   = best_station.progress_pct
            prev_pct   = inp.previous_progress_pct
            is_lap_wrap = (prev_pct > _LAP_WRAP_PREV_PCT and cand_pct < _LAP_WRAP_CAND_PCT)
            if cand_pct < prev_pct - 1.0 and not is_lap_wrap:
                match_warnings.append(
                    f"Backward progress detected ({prev_pct:.1f}% → {cand_pct:.1f}%)"
                )
                if confidence == TrackTruthConfidence.HIGH:
                    confidence = TrackTruthConfidence.MEDIUM

        # ── Pit awareness ────────────────────────────────────────────────
        is_pit_likely = inp.speed_kph < MIN_SPEED_KPH or dist_xz > PIT_DISTANCE_M
        pit_context = best_station.pit_context
        if is_pit_likely:
            pit_context = pit_context or "pit_likely"
            match_warnings.append(
                f"Pit/stop likely — speed {inp.speed_kph:.1f} kph, "
                f"dist {dist_xz:.1f} m from centreline"
            )

        # ── Lateral offset ───────────────────────────────────────────────
        lateral_m = _lateral_offset(
            inp.x, inp.z,
            best_station.x, best_station.z,
            best_station.heading_rad,
        )

        # ── Heading delta ────────────────────────────────────────────────
        heading_delta = 0.0
        if inp.heading_rad is not None:
            raw_delta = inp.heading_rad - best_station.heading_rad
            heading_delta = (raw_delta + math.pi) % (2 * math.pi) - math.pi

        # ── AI usability guard ───────────────────────────────────────────
        ai_usable = bool(
            validation is not None
            and can_use_track_truth_for_ai_corner_context(validation)
        )

        return TrackTruthMatchResult(
            station_id               = best_station.station_id,
            distance_m               = dist_xz,
            progress_pct             = best_station.progress_pct,
            corner_id                = best_station.corner_id,
            corner_phase             = best_station.corner_phase or "unknown",
            complex_id               = best_station.complex_id,
            sector_id                = best_station.sector_id,
            pit_context              = pit_context,
            lateral_offset_m         = lateral_m,
            heading_delta_rad        = heading_delta,
            confidence               = confidence,
            is_usable_for_ai_corner_context = ai_usable,
            warnings                 = match_warnings,
        )

    except Exception as exc:
        return _placeholder(f"match_track_truth_position internal error: {exc}")
