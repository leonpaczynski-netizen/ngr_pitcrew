"""Track Segment Detection — automatic segment detection from calibration telemetry.

Pure Python, no PyQt6 dependency.

Architecture boundary:
  - Depends on: data.track_calibration (models, helpers)
  - Depends on: data.track_intelligence (TrackLayoutSeed — corner count hint)
  - Does NOT own: session capture, reference path building, AI prompt integration
  - Detected segments are CANDIDATE outputs requiring user review before use

GT7 protocol limitations (preserved, not worked around):
  - steering: not in GT7 packet → corner direction is heading-derived or UNKNOWN
  - is_in_pit_lane: no per-sample flag → cannot exclude pit-in laps at sample level
  - yaw_rate (angvel_z): available but noisy — used as secondary curvature evidence

Car-behaviour vs track-geometry boundary:
  - Braking zones, gear zones, traction zones, limiter zones, fuel-saving candidates
    are tagged with calibration_car_id (Porsche 911 RSR (991) '17 by default) — they
    reflect calibration-car behaviour, NOT universal track truth.
  - Apex zones, corner geometry, straight zones can become track-model evidence but
    still require user review before engineer-grade status is assigned.
"""
from __future__ import annotations

import json
import math
import statistics
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from data.track_calibration import (
    PRIMARY_CALIBRATION_CAR_ID,
    CalibrationLap,
    CalibrationLapQuality,
    CalibrationSession,
    ReferencePath,
    TelemetrySample,
    assess_session_laps,
    cumulative_distances,
    normalize_to_lap_progress,
    point_distance_3d,
)
from data.track_intelligence import TrackLayoutSeed


# ---------------------------------------------------------------------------
# Constants (all overridable via SegmentDetectionConfig)
# ---------------------------------------------------------------------------

_DEFAULT_MIN_CORNER_SPEED_DROP_KPH: float = 15.0
_DEFAULT_BRAKE_THRESHOLD: float           = 0.15
_DEFAULT_THROTTLE_HIGH: float             = 0.75
_DEFAULT_THROTTLE_TRAILING: float         = 0.30
_DEFAULT_CURVATURE_THRESHOLD: float       = 0.015   # rad/m
_DEFAULT_RPM_LIMITER_FRACTION: float      = 0.92
_DEFAULT_KERB_Z_SPIKE_M: float            = 0.30
_DEFAULT_FUEL_SAVE_MIN_PROGRESS: float    = 0.08    # 8 % of lap
_DEFAULT_STRAIGHT_MIN_PROGRESS: float     = 0.04    # 4 % of lap
_DEFAULT_CORNER_LOOK_BACK: float          = 0.20    # 20 % of lap
_DEFAULT_CORNER_LOOK_FORWARD: float       = 0.20
_DEFAULT_APEX_MERGE_RADIUS: float         = 0.025   # 2.5 % of lap
_DEFAULT_MIN_SEGMENT_SAMPLES: int         = 3
_DEFAULT_SMOOTH_WINDOW: int               = 5

SEGMENT_MODELS_DIR: Path = Path(__file__).parent.parent / "data" / "track_models"


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TrackSegmentType(str, Enum):
    START_FINISH           = "start_finish"
    STRAIGHT               = "straight"
    BRAKING_ZONE           = "braking_zone"
    CORNER_ENTRY           = "corner_entry"
    APEX_ZONE              = "apex_zone"
    CORNER_EXIT            = "corner_exit"
    TRACTION_ZONE          = "traction_zone"
    GEAR_ZONE              = "gear_zone"
    LIMITER_ZONE           = "limiter_zone"
    FUEL_SAVING_CANDIDATE  = "fuel_saving_candidate"
    KERB_OR_BUMP_CANDIDATE = "kerb_or_bump_candidate"
    PIT_LANE               = "pit_lane"
    UNKNOWN                = "unknown"


class TrackSegmentDirection(str, Enum):
    LEFT    = "left"
    RIGHT   = "right"
    UNKNOWN = "unknown"


class TrackSegmentDetectionConfidence(str, Enum):
    HIGH         = "high"    # ≥ 3 laps + curvature/yaw evidence
    MEDIUM       = "medium"  # ≥ 2 laps consistent, or 1 lap + curvature
    LOW          = "low"     # single lap, speed/throttle/brake only
    INSUFFICIENT = "insufficient"  # not enough data


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SegmentDetectionConfig:
    """Tunable thresholds for segment detection."""
    # Corner detection
    min_corner_speed_drop_kph: float = _DEFAULT_MIN_CORNER_SPEED_DROP_KPH
    brake_threshold: float           = _DEFAULT_BRAKE_THRESHOLD
    throttle_high_threshold: float   = _DEFAULT_THROTTLE_HIGH
    throttle_trailing_threshold: float = _DEFAULT_THROTTLE_TRAILING
    curvature_corner_threshold: float  = _DEFAULT_CURVATURE_THRESHOLD
    corner_max_look_back: float        = _DEFAULT_CORNER_LOOK_BACK
    corner_max_look_forward: float     = _DEFAULT_CORNER_LOOK_FORWARD
    apex_merge_radius: float           = _DEFAULT_APEX_MERGE_RADIUS
    # Auxiliary detections
    rpm_limiter_fraction: float        = _DEFAULT_RPM_LIMITER_FRACTION
    kerb_z_spike_threshold_m: float    = _DEFAULT_KERB_Z_SPIKE_M
    fuel_save_min_progress: float      = _DEFAULT_FUEL_SAVE_MIN_PROGRESS
    straight_min_progress: float       = _DEFAULT_STRAIGHT_MIN_PROGRESS
    # Output
    min_segment_samples: int           = _DEFAULT_MIN_SEGMENT_SAMPLES
    smooth_window: int                 = _DEFAULT_SMOOTH_WINDOW


@dataclass
class DetectedTrackSegment:
    """One detected track segment."""
    segment_id: str
    segment_type: TrackSegmentType
    display_name: str
    lap_progress_start: float          # 0.0 – 1.0
    lap_progress_end: float
    lap_progress_mid: float
    confidence: TrackSegmentDetectionConfidence
    evidence: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_lap_count: int = 0
    turn_number: Optional[int] = None
    track_location_id: Optional[str] = None
    layout_id: Optional[str] = None
    distance_start_m: Optional[float] = None
    distance_end_m: Optional[float] = None
    direction: Optional[TrackSegmentDirection] = None
    calibration_car_id: Optional[str] = None  # set for car-behaviour segments


@dataclass
class SegmentDetectionResult:
    """Output of detect_track_segments()."""
    success: bool
    track_location_id: str
    layout_id: str
    segments: list[DetectedTrackSegment] = field(default_factory=list)
    detected_corner_count: int = 0
    expected_corner_count: Optional[int] = None
    corner_count_matches_expected: Optional[bool] = None
    source_lap_count: int = 0
    confidence: TrackSegmentDetectionConfidence = TrackSegmentDetectionConfidence.INSUFFICIENT
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    detected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    calibration_car_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Private signal helpers
# ---------------------------------------------------------------------------

def _smooth(values: list[float], window: int = 5) -> list[float]:
    """Centre-weighted rolling average.  Returns a list of same length."""
    if not values:
        return []
    result: list[float] = []
    half = window // 2
    n = len(values)
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        result.append(sum(values[lo:hi]) / (hi - lo))
    return result


def _compute_headings_xz(samples: list[TelemetrySample]) -> list[float]:
    """Heading in XZ plane (radians) at each sample using forward differences.

    Returns all-zeros when positions are constant (no heading computable).
    """
    n = len(samples)
    if n < 2:
        return [0.0] * n

    headings: list[float] = []
    for i in range(n):
        if i < n - 1:
            dx = samples[i + 1].x - samples[i].x
            dz = samples[i + 1].z - samples[i].z
        else:
            dx = samples[i].x - samples[i - 1].x
            dz = samples[i].z - samples[i - 1].z

        if abs(dx) < 1e-6 and abs(dz) < 1e-6:
            headings.append(headings[-1] if headings else 0.0)
        else:
            headings.append(math.atan2(dz, dx))

    return headings


def _angular_diff(a: float, b: float) -> float:
    """Signed angular difference (a - b) normalised to (-π, π]."""
    d = a - b
    while d > math.pi:
        d -= 2.0 * math.pi
    while d <= -math.pi:
        d += 2.0 * math.pi
    return d


def _compute_curvature(
    headings: list[float],
    cum_dists: list[float],
) -> list[float]:
    """Heading-change rate per metre (rad/m) — curvature proxy.

    Positive = left turn, negative = right turn.  Returns zeros where
    distance between samples is negligible.
    """
    n = len(headings)
    if n < 2:
        return [0.0] * n

    result = [0.0]
    for i in range(1, n):
        dist = cum_dists[i] - cum_dists[i - 1]
        if dist < 0.01:
            result.append(0.0)
        else:
            result.append(_angular_diff(headings[i], headings[i - 1]) / dist)
    return result


def _find_local_minima(values: list[float], min_drop: float = 0.0) -> list[int]:
    """Indices of local minima where the drop from nearest preceding max >= min_drop."""
    minima = []
    n = len(values)
    if n < 3:
        return minima

    for i in range(1, n - 1):
        if values[i] < values[i - 1] and values[i] <= values[i + 1]:
            look = min(40, i)
            local_max = max(values[max(0, i - look): i + 1])
            if local_max - values[i] >= min_drop:
                minima.append(i)
    return minima


def _find_local_maxima(values: list[float]) -> list[int]:
    """Indices of local maxima."""
    maxima = []
    n = len(values)
    for i in range(1, n - 1):
        if values[i] > values[i - 1] and values[i] >= values[i + 1]:
            maxima.append(i)
    return maxima


def _has_position_variation(samples: list[TelemetrySample]) -> bool:
    """True if samples have non-trivial XZ position movement."""
    if len(samples) < 2:
        return False
    total_dist = 0.0
    for i in range(1, len(samples)):
        dx = samples[i].x - samples[i - 1].x
        dz = samples[i].z - samples[i - 1].z
        total_dist += math.sqrt(dx * dx + dz * dz)
        if total_dist > 1.0:
            return True
    return False


# ---------------------------------------------------------------------------
# Corner cluster detection (per lap)
# ---------------------------------------------------------------------------

def _detect_corner_apex_candidates(
    samples: list[TelemetrySample],
    progress: list[float],
    smoothed_speed: list[float],
    config: SegmentDetectionConfig,
) -> list[dict]:
    """Return a list of corner candidate dicts from a single lap.

    Each dict contains:
      entry_idx, apex_idx, exit_idx,
      progress_start, progress_apex, progress_end,
      has_brake_evidence, has_curvature_evidence, direction,
      min_speed_kph
    """
    n = len(samples)
    if n < config.min_segment_samples:
        return []

    cum_dists = cumulative_distances(samples)
    headings = _compute_headings_xz(samples)
    raw_curvatures = _compute_curvature(headings, cum_dists)
    curvatures = _smooth(raw_curvatures, window=config.smooth_window)

    apex_indices = _find_local_minima(smoothed_speed, config.min_corner_speed_drop_kph)
    if not apex_indices:
        return []

    corners: list[dict] = []

    for apex_idx in apex_indices:
        apex_progress = progress[apex_idx]
        apex_speed    = smoothed_speed[apex_idx]

        # ── Find entry start ─────────────────────────────────────────────
        entry_idx = apex_idx
        for j in range(apex_idx - 1, -1, -1):
            if apex_progress - progress[j] > config.corner_max_look_back:
                break
            # Stop when speed is clearly high enough that we're back on the straight
            if smoothed_speed[j] > apex_speed + config.min_corner_speed_drop_kph:
                entry_idx = j
                break
            # Also accept braking as entry start
            if samples[j].brake > config.brake_threshold:
                entry_idx = j

        # ── Find exit end ─────────────────────────────────────────────────
        exit_idx = apex_idx
        for j in range(apex_idx + 1, n):
            if progress[j] - apex_progress > config.corner_max_look_forward:
                break
            exit_idx = j
            # Stop when throttle is high and speed has recovered meaningfully
            if (samples[j].throttle > config.throttle_high_threshold
                    and smoothed_speed[j] > apex_speed + config.min_corner_speed_drop_kph * 0.4):
                break

        if exit_idx <= entry_idx:
            continue

        # ── Evidence ────────────────────────────────────────────────────
        region_samples = samples[entry_idx: exit_idx + 1]
        has_brake = any(s.brake > config.brake_threshold for s in region_samples)

        region_curvatures = curvatures[entry_idx: exit_idx + 1]
        max_abs_curv = max((abs(c) for c in region_curvatures), default=0.0)
        has_curvature = max_abs_curv > config.curvature_corner_threshold

        # Direction from mean curvature in the tightest part of the corner
        apex_window = curvatures[max(0, apex_idx - 3): apex_idx + 4]
        avg_curv = (sum(apex_window) / len(apex_window)) if apex_window else 0.0
        if has_curvature and abs(avg_curv) > config.curvature_corner_threshold:
            direction = (TrackSegmentDirection.LEFT if avg_curv > 0
                         else TrackSegmentDirection.RIGHT)
        else:
            direction = None

        corners.append({
            "entry_idx"             : entry_idx,
            "apex_idx"              : apex_idx,
            "exit_idx"              : exit_idx,
            "progress_start"        : progress[entry_idx],
            "progress_apex"         : progress[apex_idx],
            "progress_end"          : progress[exit_idx],
            "has_brake_evidence"    : has_brake,
            "has_curvature_evidence": has_curvature,
            "direction"             : direction,
            "min_speed_kph"         : apex_speed,
        })

    # Merge corners whose windows overlap or are very close
    corners = _merge_corner_candidates(corners, config.apex_merge_radius)
    return corners


def _merge_corner_candidates(corners: list[dict], merge_radius: float) -> list[dict]:
    """Merge corner candidates whose apex progress values are within merge_radius."""
    if len(corners) <= 1:
        return corners

    # Sort by apex progress
    corners = sorted(corners, key=lambda c: c["progress_apex"])
    merged: list[dict] = [corners[0]]

    for cur in corners[1:]:
        prev = merged[-1]
        if cur["progress_apex"] - prev["progress_apex"] < merge_radius:
            # Merge: keep the one with the lower min speed (deeper corner)
            if cur["min_speed_kph"] < prev["min_speed_kph"]:
                merged[-1] = {
                    **cur,
                    "entry_idx"  : min(cur["entry_idx"], prev["entry_idx"]),
                    "exit_idx"   : max(cur["exit_idx"], prev["exit_idx"]),
                    "progress_start": min(cur["progress_start"], prev["progress_start"]),
                    "progress_end"  : max(cur["progress_end"], prev["progress_end"]),
                    "has_brake_evidence"    : cur["has_brake_evidence"] or prev["has_brake_evidence"],
                    "has_curvature_evidence": cur["has_curvature_evidence"] or prev["has_curvature_evidence"],
                }
            else:
                merged[-1]["entry_idx"]   = min(cur["entry_idx"], prev["entry_idx"])
                merged[-1]["exit_idx"]    = max(cur["exit_idx"], prev["exit_idx"])
                merged[-1]["progress_start"] = min(cur["progress_start"], prev["progress_start"])
                merged[-1]["progress_end"]   = max(cur["progress_end"], prev["progress_end"])
                merged[-1]["has_brake_evidence"]     = cur["has_brake_evidence"] or prev["has_brake_evidence"]
                merged[-1]["has_curvature_evidence"] = cur["has_curvature_evidence"] or prev["has_curvature_evidence"]
        else:
            merged.append(cur)

    return merged


# ---------------------------------------------------------------------------
# Auxiliary detectors (per lap)
# ---------------------------------------------------------------------------

def _detect_limiter_zones_from_lap(
    samples: list[TelemetrySample],
    progress: list[float],
    track_location_id: str,
    layout_id: str,
    car_id: str,
    config: SegmentDetectionConfig,
) -> list[DetectedTrackSegment]:
    """Detect regions where RPM is near the observed max (limiter approach)."""
    if not samples:
        return []

    rpms = [s.rpm for s in samples]
    session_max_rpm = max(rpms) if rpms else 0.0
    if session_max_rpm < 100.0:
        return []

    limiter_threshold = session_max_rpm * config.rpm_limiter_fraction

    segments: list[DetectedTrackSegment] = []
    in_zone = False
    zone_start_idx = 0

    for i, s in enumerate(samples):
        above = s.rpm >= limiter_threshold
        if above and not in_zone:
            in_zone = True
            zone_start_idx = i
        elif not above and in_zone:
            in_zone = False
            seg = _make_limiter_segment(
                samples, progress, zone_start_idx, i - 1,
                track_location_id, layout_id, car_id
            )
            if seg:
                segments.append(seg)

    if in_zone:
        seg = _make_limiter_segment(
            samples, progress, zone_start_idx, len(samples) - 1,
            track_location_id, layout_id, car_id
        )
        if seg:
            segments.append(seg)

    return segments


def _make_limiter_segment(
    samples: list[TelemetrySample],
    progress: list[float],
    start_idx: int,
    end_idx: int,
    track_location_id: str,
    layout_id: str,
    car_id: str,
) -> Optional[DetectedTrackSegment]:
    if end_idx < start_idx:
        return None
    count = end_idx - start_idx + 1
    if count < 2:
        return None
    p_start = progress[start_idx]
    p_end   = progress[end_idx]
    p_mid   = (p_start + p_end) / 2.0
    seg_id  = f"limiter_{p_start:.3f}"
    avg_rpm = sum(samples[start_idx: end_idx + 1][i].rpm
                  for i in range(count)) / count
    return DetectedTrackSegment(
        segment_id        = seg_id,
        segment_type      = TrackSegmentType.LIMITER_ZONE,
        display_name      = f"Limiter approach ({p_start:.1%}–{p_end:.1%})",
        lap_progress_start= p_start,
        lap_progress_end  = p_end,
        lap_progress_mid  = p_mid,
        confidence        = TrackSegmentDetectionConfidence.LOW,
        evidence          = [f"Mean RPM {avg_rpm:.0f} in zone — near observed max"],
        warnings          = ["Car-specific behaviour — Porsche RSR rev ceiling, not universal"],
        source_lap_count  = 1,
        track_location_id = track_location_id,
        layout_id         = layout_id,
        calibration_car_id= car_id,
    )


def _detect_kerb_candidates_multi_lap(
    usable_laps: list[CalibrationLap],
    track_location_id: str,
    layout_id: str,
    car_id: str,
    config: SegmentDetectionConfig,
) -> list[DetectedTrackSegment]:
    """Detect Z-coordinate spikes that repeat at the same lap progress across laps."""
    if len(usable_laps) < 2:
        return []

    # Build per-lap lists of (progress, z) for samples with significant Z spikes
    lap_spike_progresses: list[list[float]] = []
    for lap in usable_laps:
        if not lap.samples:
            continue
        z_vals = [s.z for s in lap.samples]
        if not z_vals:
            continue
        z_smooth = _smooth(z_vals, window=5)
        progress = normalize_to_lap_progress(lap.samples)
        spikes = []
        for i, (s, z_s) in enumerate(zip(lap.samples, z_smooth)):
            if abs(s.z - z_s) > config.kerb_z_spike_threshold_m:
                spikes.append(progress[i])
        lap_spike_progresses.append(spikes)

    if not lap_spike_progresses:
        return []

    # Cluster spike progress values across laps
    all_spikes = []
    for spikes in lap_spike_progresses:
        all_spikes.extend(spikes)
    all_spikes.sort()

    # Group spikes within 2% of each other
    clusters: list[list[float]] = []
    for p in all_spikes:
        placed = False
        for cluster in clusters:
            if abs(p - statistics.mean(cluster)) < 0.02:
                cluster.append(p)
                placed = True
                break
        if not placed:
            clusters.append([p])

    # Keep clusters that appear across multiple laps
    segments = []
    cluster_id = 0
    for cluster in clusters:
        if len(cluster) < 2:
            continue
        p_mid = statistics.mean(cluster)
        p_start = max(0.0, p_mid - 0.01)
        p_end   = min(1.0, p_mid + 0.01)
        cluster_id += 1
        segments.append(DetectedTrackSegment(
            segment_id        = f"kerb_{p_mid:.3f}",
            segment_type      = TrackSegmentType.KERB_OR_BUMP_CANDIDATE,
            display_name      = f"Kerb/bump candidate ({p_mid:.1%})",
            lap_progress_start= p_start,
            lap_progress_end  = p_end,
            lap_progress_mid  = p_mid,
            confidence        = TrackSegmentDetectionConfidence.LOW,
            evidence          = [f"Z-coordinate spike detected in {len(cluster)} samples across ≥ 2 laps"],
            warnings          = ["Candidate only — requires visual confirmation on track"],
            source_lap_count  = len(cluster),
            track_location_id = track_location_id,
            layout_id         = layout_id,
        ))

    return segments


def _detect_gear_zones_from_lap(
    samples: list[TelemetrySample],
    progress: list[float],
    corner_clusters: list[dict],
    track_location_id: str,
    layout_id: str,
    car_id: str,
) -> list[DetectedTrackSegment]:
    """Detect corner regions with consistently used gear."""
    segments: list[DetectedTrackSegment] = []

    for c in corner_clusters:
        entry_idx = c["entry_idx"]
        exit_idx  = c["exit_idx"]
        apex_idx  = c["apex_idx"]

        # Look at the apex region ± a few samples for consistent gear
        a_start = max(0, apex_idx - 3)
        a_end   = min(len(samples) - 1, apex_idx + 3)
        apex_samples = samples[a_start: a_end + 1]
        if not apex_samples:
            continue

        gears = [s.gear for s in apex_samples if s.gear > 0]
        if not gears:
            continue
        modal_gear = max(set(gears), key=gears.count)
        consistent = sum(1 for g in gears if g == modal_gear) >= len(gears) * 0.7

        if consistent and modal_gear > 0:
            p_s = progress[a_start]
            p_e = progress[a_end]
            segments.append(DetectedTrackSegment(
                segment_id        = f"gear_{p_s:.3f}_{modal_gear}",
                segment_type      = TrackSegmentType.GEAR_ZONE,
                display_name      = f"Gear {modal_gear} zone ({p_s:.1%}–{p_e:.1%})",
                lap_progress_start= p_s,
                lap_progress_end  = p_e,
                lap_progress_mid  = (p_s + p_e) / 2.0,
                confidence        = TrackSegmentDetectionConfidence.LOW,
                evidence          = [f"Gear {modal_gear} used in ≥ 70% of apex samples"],
                warnings          = ["Car-specific gear choice — Porsche RSR gearbox, not universal"],
                source_lap_count  = 1,
                track_location_id = track_location_id,
                layout_id         = layout_id,
                calibration_car_id= car_id,
            ))

    return segments


# ---------------------------------------------------------------------------
# Per-lap segment list builder
# ---------------------------------------------------------------------------

def detect_segments_from_lap(
    lap: CalibrationLap,
    config: Optional[SegmentDetectionConfig] = None,
    track_location_id: str = "",
    layout_id: str = "",
) -> list[DetectedTrackSegment]:
    """Detect segments from a single calibration lap.

    Returns a list of DetectedTrackSegment objects ordered by lap_progress_start.
    Confidence is always LOW (single lap) except when curvature evidence is present
    (MEDIUM).  Use detect_track_segments() for multi-lap aggregation.
    """
    if config is None:
        config = SegmentDetectionConfig()

    samples = lap.samples
    if len(samples) < config.min_segment_samples:
        return []

    car_id = PRIMARY_CALIBRATION_CAR_ID
    progress = normalize_to_lap_progress(samples)
    if not progress or max(progress) < 0.001:
        return []

    speeds = [s.speed_kph for s in samples]
    smoothed_speed = _smooth(speeds, config.smooth_window)

    corner_clusters = _detect_corner_apex_candidates(
        samples, progress, smoothed_speed, config
    )

    segments: list[DetectedTrackSegment] = []

    # ── Build segments from corner clusters ──────────────────────────────────
    for c in corner_clusters:
        apex_idx  = c["apex_idx"]
        entry_idx = c["entry_idx"]
        exit_idx  = c["exit_idx"]

        p_start   = c["progress_start"]
        p_apex    = c["progress_apex"]
        p_end     = c["progress_end"]

        has_brake = c["has_brake_evidence"]
        has_curv  = c["has_curvature_evidence"]
        direction = c["direction"]

        conf = (TrackSegmentDetectionConfidence.MEDIUM if has_curv
                else TrackSegmentDetectionConfidence.LOW)
        evidence: list[str] = []
        if has_brake:
            evidence.append("Brake signal > threshold before apex")
        if has_curv:
            evidence.append("Path curvature evidence in XZ plane")
        evidence.append(f"Speed drops ≥ {config.min_corner_speed_drop_kph:.0f} kph to apex")

        # Braking zone: from entry to just before apex (80% of the way)
        braking_end_progress = p_start + (p_apex - p_start) * 0.80
        seg_braking = DetectedTrackSegment(
            segment_id         = f"braking_{p_start:.3f}",
            segment_type       = TrackSegmentType.BRAKING_ZONE,
            display_name       = f"Braking zone ({p_start:.1%}–{braking_end_progress:.1%})",
            lap_progress_start = p_start,
            lap_progress_end   = braking_end_progress,
            lap_progress_mid   = (p_start + braking_end_progress) / 2.0,
            confidence         = conf,
            evidence           = list(evidence),
            warnings           = ["Car-specific braking point — Porsche RSR, not universal"],
            source_lap_count   = 1,
            track_location_id  = track_location_id,
            layout_id          = layout_id,
            direction          = direction,
            calibration_car_id = car_id,
        )
        segments.append(seg_braking)

        # Corner entry: from 80% to apex
        if braking_end_progress < p_apex:
            seg_entry = DetectedTrackSegment(
                segment_id         = f"entry_{braking_end_progress:.3f}",
                segment_type       = TrackSegmentType.CORNER_ENTRY,
                display_name       = f"Corner entry ({braking_end_progress:.1%}–{p_apex:.1%})",
                lap_progress_start = braking_end_progress,
                lap_progress_end   = p_apex,
                lap_progress_mid   = (braking_end_progress + p_apex) / 2.0,
                confidence         = conf,
                evidence           = ["Brake tapering / trail braking phase"],
                source_lap_count   = 1,
                track_location_id  = track_location_id,
                layout_id          = layout_id,
                direction          = direction,
            )
            segments.append(seg_entry)

        # Apex zone: tight window ± 3% around apex
        ap_win_start = max(p_start, p_apex - 0.03)
        ap_win_end   = min(p_end,   p_apex + 0.03)
        seg_apex = DetectedTrackSegment(
            segment_id         = f"apex_{p_apex:.3f}",
            segment_type       = TrackSegmentType.APEX_ZONE,
            display_name       = f"Apex ({ap_win_start:.1%}–{ap_win_end:.1%})",
            lap_progress_start = ap_win_start,
            lap_progress_end   = ap_win_end,
            lap_progress_mid   = p_apex,
            confidence         = conf,
            evidence           = [f"Local speed minimum: {c['min_speed_kph']:.0f} kph"] + list(evidence),
            source_lap_count   = 1,
            track_location_id  = track_location_id,
            layout_id          = layout_id,
            direction          = direction,
        )
        segments.append(seg_apex)

        # Corner exit: from apex to 60% of the way to exit
        traction_start_progress = p_apex + (p_end - p_apex) * 0.40
        seg_exit = DetectedTrackSegment(
            segment_id         = f"exit_{p_apex:.3f}",
            segment_type       = TrackSegmentType.CORNER_EXIT,
            display_name       = f"Corner exit ({p_apex:.1%}–{traction_start_progress:.1%})",
            lap_progress_start = p_apex,
            lap_progress_end   = traction_start_progress,
            lap_progress_mid   = (p_apex + traction_start_progress) / 2.0,
            confidence         = conf,
            evidence           = ["Speed increasing, throttle opening"],
            source_lap_count   = 1,
            track_location_id  = track_location_id,
            layout_id          = layout_id,
            direction          = direction,
        )
        segments.append(seg_exit)

        # Traction zone: from 60% of exit to exit end
        if traction_start_progress < p_end:
            seg_traction = DetectedTrackSegment(
                segment_id         = f"traction_{traction_start_progress:.3f}",
                segment_type       = TrackSegmentType.TRACTION_ZONE,
                display_name       = f"Traction zone ({traction_start_progress:.1%}–{p_end:.1%})",
                lap_progress_start = traction_start_progress,
                lap_progress_end   = p_end,
                lap_progress_mid   = (traction_start_progress + p_end) / 2.0,
                confidence         = conf,
                evidence           = ["Throttle rising, speed increasing — power application phase"],
                warnings           = ["Car-specific — Porsche RSR traction characteristics"],
                source_lap_count   = 1,
                track_location_id  = track_location_id,
                layout_id          = layout_id,
                calibration_car_id = car_id,
            )
            segments.append(seg_traction)

    # ── Fill inter-corner gaps with straight / fuel-saving candidates ─────────
    # Collect occupied ranges from corner clusters
    occupied = sorted(
        [(c["progress_start"], c["progress_end"]) for c in corner_clusters],
        key=lambda x: x[0],
    )

    # Build list of free ranges
    free_ranges: list[tuple[float, float]] = []
    cursor = 0.0
    for o_start, o_end in occupied:
        if cursor < o_start - 0.001:
            free_ranges.append((cursor, o_start))
        cursor = max(cursor, o_end)
    if cursor < 1.0 - 0.001:
        free_ranges.append((cursor, 1.0))

    for fr_start, fr_end in free_ranges:
        span = fr_end - fr_start
        if span < config.straight_min_progress:
            continue

        # Find samples in this range to check throttle
        range_samples = [
            s for s, p in zip(samples, progress)
            if fr_start <= p <= fr_end
        ]
        avg_throttle = (
            sum(s.throttle for s in range_samples) / len(range_samples)
            if range_samples else 0.0
        )

        if span >= config.fuel_save_min_progress and avg_throttle > 0.70:
            seg_type = TrackSegmentType.FUEL_SAVING_CANDIDATE
            seg_name = f"Fuel-save candidate ({fr_start:.1%}–{fr_end:.1%})"
            evidence = [
                f"Straight span {span:.1%} of lap, avg throttle {avg_throttle:.0%}",
                "Long high-throttle section — lift/coast evaluation possible",
            ]
            warn = ["Car-specific fuel window — Porsche RSR fuel load/strategy, not universal"]
            cal_car = car_id
        else:
            seg_type = TrackSegmentType.STRAIGHT
            seg_name = f"Straight ({fr_start:.1%}–{fr_end:.1%})"
            evidence = [f"No corner event detected; span {span:.1%}"]
            warn = []
            cal_car = None

        seg_straight = DetectedTrackSegment(
            segment_id         = f"straight_{fr_start:.3f}",
            segment_type       = seg_type,
            display_name       = seg_name,
            lap_progress_start = fr_start,
            lap_progress_end   = fr_end,
            lap_progress_mid   = (fr_start + fr_end) / 2.0,
            confidence         = TrackSegmentDetectionConfidence.LOW,
            evidence           = evidence,
            warnings           = warn,
            source_lap_count   = 1,
            track_location_id  = track_location_id,
            layout_id          = layout_id,
            calibration_car_id = cal_car,
        )
        segments.append(seg_straight)

    segments.sort(key=lambda s: s.lap_progress_start)
    return segments


# ---------------------------------------------------------------------------
# Corner numbering
# ---------------------------------------------------------------------------

def assign_corner_numbers(
    segments: list[DetectedTrackSegment],
    expected_corner_count: Optional[int] = None,
) -> list[DetectedTrackSegment]:
    """Assign turn numbers (T1, T2 …) to apex zones by lap_progress order.

    Returns a new list with turn_number and display_name updated on apex segments.
    Non-apex segments are returned unchanged.  Segments must already be sorted by
    lap_progress_start (detect_track_segments guarantees this).

    If expected_corner_count is provided and the detected count differs by more
    than 2, warnings are added to all apex segments.
    """
    apex_segs = [s for s in segments if s.segment_type == TrackSegmentType.APEX_ZONE]
    apex_segs_sorted = sorted(apex_segs, key=lambda s: s.lap_progress_mid)

    detected_count = len(apex_segs_sorted)
    count_warning = ""
    if expected_corner_count is not None:
        diff = abs(detected_count - expected_corner_count)
        if diff > 2:
            count_warning = (
                f"Detected {detected_count} corners vs expected {expected_corner_count} "
                f"(difference {diff}) — missing corners may need more calibration laps; "
                f"do NOT invent corners to reach expected count"
            )

    # Build a mapping: old segment_id → (turn_number, new display_name)
    turn_map: dict[str, tuple[int, str]] = {}
    for turn_num, apex in enumerate(apex_segs_sorted, start=1):
        turn_map[apex.segment_id] = (turn_num, f"T{turn_num} Apex ({apex.lap_progress_mid:.1%})")

    result: list[DetectedTrackSegment] = []
    for seg in segments:
        if seg.segment_id in turn_map:
            turn_num, new_name = turn_map[seg.segment_id]
            new_warnings = list(seg.warnings)
            if count_warning and count_warning not in new_warnings:
                new_warnings.append(count_warning)
            result.append(DetectedTrackSegment(
                segment_id         = seg.segment_id,
                segment_type       = seg.segment_type,
                display_name       = new_name,
                lap_progress_start = seg.lap_progress_start,
                lap_progress_end   = seg.lap_progress_end,
                lap_progress_mid   = seg.lap_progress_mid,
                confidence         = seg.confidence,
                evidence           = list(seg.evidence),
                warnings           = new_warnings,
                source_lap_count   = seg.source_lap_count,
                turn_number        = turn_num,
                track_location_id  = seg.track_location_id,
                layout_id          = seg.layout_id,
                distance_start_m   = seg.distance_start_m,
                distance_end_m     = seg.distance_end_m,
                direction          = seg.direction,
                calibration_car_id = seg.calibration_car_id,
            ))
        else:
            result.append(seg)

    return result


# ---------------------------------------------------------------------------
# Multi-lap aggregation
# ---------------------------------------------------------------------------

def _cluster_apex_progress(
    per_lap_corners: list[list[dict]],
    merge_radius: float,
) -> list[list[dict]]:
    """Group corner dicts from multiple laps by apex_progress proximity."""
    flat: list[dict] = []
    for lap_corners in per_lap_corners:
        flat.extend(lap_corners)
    flat.sort(key=lambda c: c["progress_apex"])

    clusters: list[list[dict]] = []
    for c in flat:
        placed = False
        for cluster in clusters:
            mean_p = statistics.mean(x["progress_apex"] for x in cluster)
            if abs(c["progress_apex"] - mean_p) <= merge_radius:
                cluster.append(c)
                placed = True
                break
        if not placed:
            clusters.append([c])

    return clusters


def _confidence_from_cluster(cluster: list[dict]) -> TrackSegmentDetectionConfidence:
    """Determine confidence from how many laps agree and what evidence is available."""
    n = len(cluster)
    has_curv = any(c.get("has_curvature_evidence", False) for c in cluster)
    if n >= 3 and has_curv:
        return TrackSegmentDetectionConfidence.HIGH
    if n >= 2:
        return TrackSegmentDetectionConfidence.MEDIUM
    if has_curv:
        return TrackSegmentDetectionConfidence.MEDIUM
    return TrackSegmentDetectionConfidence.LOW


def _build_segments_from_clusters(
    clusters: list[list[dict]],
    session: CalibrationSession,
    config: SegmentDetectionConfig,
    has_position_var: bool,
) -> tuple[list[DetectedTrackSegment], list[str]]:
    """Build confirmed DetectedTrackSegment objects from multi-lap apex clusters."""
    track_loc = session.track_location_id
    layout    = session.layout_id
    car_id    = session.calibration_car_id
    segments: list[DetectedTrackSegment] = []
    warnings: list[str] = []

    if not has_position_var:
        warnings.append(
            "No X/Z position variation detected — heading/curvature unavailable; "
            "corner direction is UNKNOWN and confidence is limited"
        )

    # Confirmed corners: appear in >= 2 laps
    confirmed = [cl for cl in clusters if len(cl) >= 2]
    unconfirmed = [cl for cl in clusters if len(cl) < 2]

    if unconfirmed:
        warnings.append(
            f"{len(unconfirmed)} candidate corner(s) appeared in only 1 lap "
            "and were excluded — record more laps to confirm"
        )

    occupied_ranges: list[tuple[float, float]] = []

    for cluster in confirmed:
        conf = _confidence_from_cluster(cluster)
        has_curv = any(c.get("has_curvature_evidence", False) for c in cluster)
        has_brake = any(c.get("has_brake_evidence", False) for c in cluster)

        p_start = statistics.mean(c["progress_start"] for c in cluster)
        p_apex  = statistics.mean(c["progress_apex"]  for c in cluster)
        p_end   = statistics.mean(c["progress_end"]   for c in cluster)
        min_spd = statistics.mean(c["min_speed_kph"]  for c in cluster)
        n_laps  = len(cluster)

        # Determine direction
        directions = [c.get("direction") for c in cluster if c.get("direction")]
        direction: Optional[TrackSegmentDirection] = None
        if directions:
            left_count  = sum(1 for d in directions if d == TrackSegmentDirection.LEFT)
            right_count = sum(1 for d in directions if d == TrackSegmentDirection.RIGHT)
            if left_count > right_count:
                direction = TrackSegmentDirection.LEFT
            elif right_count > left_count:
                direction = TrackSegmentDirection.RIGHT

        evidence: list[str] = [
            f"Confirmed across {n_laps} usable laps",
            f"Speed minimum ~{min_spd:.0f} kph",
        ]
        if has_brake:
            evidence.append("Brake signal detected")
        if has_curv:
            evidence.append("Path curvature evidence in XZ plane")
        if not has_curv and not has_position_var:
            evidence.append("No heading data — curvature not computable")

        seg_warn: list[str] = []
        if not has_position_var or not has_curv:
            seg_warn.append("Corner direction UNKNOWN — no reliable heading/curvature data")

        braking_end  = p_start + (p_apex - p_start) * 0.80
        traction_srt = p_apex  + (p_end   - p_apex)  * 0.40

        # Braking zone
        segments.append(DetectedTrackSegment(
            segment_id         = f"braking_{p_start:.3f}",
            segment_type       = TrackSegmentType.BRAKING_ZONE,
            display_name       = f"Braking zone ({p_start:.1%}–{braking_end:.1%})",
            lap_progress_start = p_start,
            lap_progress_end   = braking_end,
            lap_progress_mid   = (p_start + braking_end) / 2.0,
            confidence         = conf,
            evidence           = list(evidence),
            warnings           = ["Car-specific — Porsche RSR braking point, not universal"] + seg_warn,
            source_lap_count   = n_laps,
            track_location_id  = track_loc,
            layout_id          = layout,
            direction          = direction,
            calibration_car_id = car_id,
        ))

        # Corner entry
        if braking_end < p_apex:
            segments.append(DetectedTrackSegment(
                segment_id         = f"entry_{braking_end:.3f}",
                segment_type       = TrackSegmentType.CORNER_ENTRY,
                display_name       = f"Corner entry ({braking_end:.1%}–{p_apex:.1%})",
                lap_progress_start = braking_end,
                lap_progress_end   = p_apex,
                lap_progress_mid   = (braking_end + p_apex) / 2.0,
                confidence         = conf,
                evidence           = ["Trail braking / low throttle phase"] + list(evidence),
                warnings           = seg_warn,
                source_lap_count   = n_laps,
                track_location_id  = track_loc,
                layout_id          = layout,
                direction          = direction,
            ))

        # Apex zone
        ap_win_start = max(p_start, p_apex - 0.03)
        ap_win_end   = min(p_end,   p_apex + 0.03)
        segments.append(DetectedTrackSegment(
            segment_id         = f"apex_{p_apex:.3f}",
            segment_type       = TrackSegmentType.APEX_ZONE,
            display_name       = f"Apex ({ap_win_start:.1%}–{ap_win_end:.1%})",
            lap_progress_start = ap_win_start,
            lap_progress_end   = ap_win_end,
            lap_progress_mid   = p_apex,
            confidence         = conf,
            evidence           = list(evidence),
            warnings           = seg_warn,
            source_lap_count   = n_laps,
            track_location_id  = track_loc,
            layout_id          = layout,
            direction          = direction,
        ))

        # Corner exit
        segments.append(DetectedTrackSegment(
            segment_id         = f"exit_{p_apex:.3f}",
            segment_type       = TrackSegmentType.CORNER_EXIT,
            display_name       = f"Corner exit ({p_apex:.1%}–{traction_srt:.1%})",
            lap_progress_start = p_apex,
            lap_progress_end   = traction_srt,
            lap_progress_mid   = (p_apex + traction_srt) / 2.0,
            confidence         = conf,
            evidence           = ["Speed increasing, throttle opening"],
            warnings           = seg_warn,
            source_lap_count   = n_laps,
            track_location_id  = track_loc,
            layout_id          = layout,
            direction          = direction,
        ))

        # Traction zone
        if traction_srt < p_end:
            segments.append(DetectedTrackSegment(
                segment_id         = f"traction_{traction_srt:.3f}",
                segment_type       = TrackSegmentType.TRACTION_ZONE,
                display_name       = f"Traction zone ({traction_srt:.1%}–{p_end:.1%})",
                lap_progress_start = traction_srt,
                lap_progress_end   = p_end,
                lap_progress_mid   = (traction_srt + p_end) / 2.0,
                confidence         = conf,
                evidence           = ["High throttle / power application phase"],
                warnings           = ["Car-specific — Porsche RSR traction limit"] + seg_warn,
                source_lap_count   = n_laps,
                track_location_id  = track_loc,
                layout_id          = layout,
                calibration_car_id = car_id,
            ))

        occupied_ranges.append((p_start, p_end))

    # ── Fill straight / fuel-save zones between corners ─────────────────────
    occupied_ranges.sort(key=lambda x: x[0])
    cursor = 0.0
    free_ranges: list[tuple[float, float]] = []
    for o_s, o_e in occupied_ranges:
        if cursor < o_s - 0.001:
            free_ranges.append((cursor, o_s))
        cursor = max(cursor, o_e)
    if cursor < 1.0 - 0.001:
        free_ranges.append((cursor, 1.0))

    for fr_start, fr_end in free_ranges:
        span = fr_end - fr_start
        if span < config.straight_min_progress:
            continue
        seg_type = (TrackSegmentType.FUEL_SAVING_CANDIDATE
                    if span >= config.fuel_save_min_progress
                    else TrackSegmentType.STRAIGHT)
        evidence = [f"No confirmed corner in this {span:.1%} span"]
        seg_warn2: list[str] = []
        cal_car_str: Optional[str] = None
        if seg_type == TrackSegmentType.FUEL_SAVING_CANDIDATE:
            evidence.append("Long straight — lift/coast may save fuel without significant lap time cost")
            seg_warn2 = ["Car-specific fuel window — Porsche RSR, not universal"]
            cal_car_str = car_id

        segments.append(DetectedTrackSegment(
            segment_id         = f"straight_{fr_start:.3f}",
            segment_type       = seg_type,
            display_name       = (f"Straight ({fr_start:.1%}–{fr_end:.1%})" if seg_type == TrackSegmentType.STRAIGHT
                                  else f"Fuel-save candidate ({fr_start:.1%}–{fr_end:.1%})"),
            lap_progress_start = fr_start,
            lap_progress_end   = fr_end,
            lap_progress_mid   = (fr_start + fr_end) / 2.0,
            confidence         = TrackSegmentDetectionConfidence.MEDIUM,
            evidence           = evidence,
            warnings           = seg_warn2,
            source_lap_count   = len(confirmed),
            track_location_id  = track_loc,
            layout_id          = layout,
            calibration_car_id = cal_car_str,
        ))

    segments.sort(key=lambda s: s.lap_progress_start)
    return segments, warnings


# ---------------------------------------------------------------------------
# Diagnostics helpers
# ---------------------------------------------------------------------------

def _build_no_usable_laps_errors(session: CalibrationSession) -> list[str]:
    """Return a list of human-readable error strings explaining why there are no
    usable calibration laps.  Never raises.
    """
    try:
        total = len(session.laps)
        if total == 0:
            return [
                "No calibration laps were captured in this session.",
                "Drive past the start/finish line at least twice to create lap boundaries.",
                f"Calibration car: {session.calibration_car_id or 'not set'}",
            ]

        qr_list = assess_session_laps(session)
        usable   = sum(1 for r in qr_list if r.quality == CalibrationLapQuality.USABLE)
        rejected = sum(1 for r in qr_list if r.quality == CalibrationLapQuality.REJECTED)
        low_conf = sum(1 for r in qr_list if r.quality == CalibrationLapQuality.LOW_CONFIDENCE)
        # DEF-17U-UAT-007: partial start/stop boundary laps are a distinct category
        # (not rejected, not pit-in) and must be reported so the counts reconcile
        # with the total captured.
        partial = sum(
            1 for r in qr_list
            if r.quality in (CalibrationLapQuality.PARTIAL_START,
                             CalibrationLapQuality.PARTIAL_STOP)
        )

        partial_note = f" / {partial} partial" if partial else ""
        errors: list[str] = [
            f"No usable calibration laps for segment detection: "
            f"{usable} usable / {rejected} rejected / {low_conf} low-confidence"
            f"{partial_note} of {total} captured."
        ]

        for lap, qr in zip(session.laps, qr_list):
            if qr.quality != CalibrationLapQuality.USABLE and qr.reasons:
                errors.append(
                    f"  Lap {lap.lap_number} [{qr.quality.value}]: "
                    + " | ".join(qr.reasons)
                )

        # Recommended action based on most common issue
        all_reasons = " ".join(
            r for qr in qr_list for r in qr.reasons
        ).lower()
        if "too few telemetry samples" in all_reasons:
            errors.append(
                "Recommended: Confirm GT7 Custom UDP Output is enabled "
                "(Settings → Application). Each lap needs 50+ telemetry frames."
            )
        elif "zero/missing x/y/z" in all_reasons or "coordinate" in all_reasons:
            errors.append(
                "Recommended: Ensure the car is on-track and moving when the "
                "session starts. GPS/position data is only sent while driving."
            )
        elif "off-track" in all_reasons:
            errors.append(
                "Recommended: Keep the car on the racing surface. "
                "Laps exceeding 30% off-track samples are rejected."
            )
        elif "outlier" in all_reasons or "duration" in all_reasons:
            errors.append(
                "Recommended: Drive consistent laps at race pace. "
                "Outlier laps (e.g. very long slow laps) cause others to be rejected."
            )
        else:
            errors.append(
                "Recommended: Run calibration again with 2 complete clean laps "
                "at race pace."
            )
        errors.append(f"Calibration car: {session.calibration_car_id or 'not set'}")
        return errors
    except Exception as exc:
        return [
            f"No usable calibration laps in session.",
            f"Diagnostic error: {type(exc).__name__}: {exc}",
        ]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def detect_track_segments(
    session: CalibrationSession,
    reference_path: Optional[ReferencePath] = None,
    layout_seed: Optional[TrackLayoutSeed] = None,
    config: Optional[SegmentDetectionConfig] = None,
    corrected_lap_m: Optional[float] = None,
    station_map=None,   # Optional[TrackStationMap] — not imported here to avoid circular dep
) -> SegmentDetectionResult:
    """Detect track segments from calibration laps.

    Uses USABLE calibration laps from the session.  Segments confirmed across
    multiple laps receive higher confidence.  The reference_path is used for
    metadata only (confidence, source_lap_count) in this implementation.
    layout_seed.corners_expected is used to generate a count-mismatch warning
    but never to invent corners.

    corrected_lap_m: when provided, per-sample lap_progress values are computed
    as cumulative_distance / corrected_lap_m rather than normalising each lap to
    its own path length.  This ensures segment lap_progress values agree with
    the reference path's closure-corrected lap length.  If None and reference_path
    is provided, corrected_lap_m is derived from
    reference_path.points[-1].distance_along_lap_m automatically.

    Car-specific segments (braking, traction, gear, limiter, fuel-save) are
    tagged with calibration_car_id.  Track-geometry segments (apex, straight)
    are not car-tagged but still require user review.
    """
    if config is None:
        config = SegmentDetectionConfig()

    track_loc = session.track_location_id
    layout    = session.layout_id
    car_id    = session.calibration_car_id

    expected_corner_count: Optional[int] = (
        layout_seed.corners_expected if layout_seed else None
    )

    # ── Resolve corrected lap length ────────────────────────────────────────
    if corrected_lap_m is None and reference_path is not None:
        pts = getattr(reference_path, "points", None)
        if pts:
            corrected_lap_m = pts[-1].distance_along_lap_m

    # ── Extract usable laps ─────────────────────────────────────────────────
    usable_laps = [
        lap for lap in session.laps
        if lap.quality == CalibrationLapQuality.USABLE and not lap.is_pit_lap
    ]

    if not usable_laps:
        # Build a diagnostic error message that explains WHY there are no usable laps.
        errors = _build_no_usable_laps_errors(session)
        return SegmentDetectionResult(
            success            = False,
            track_location_id  = track_loc,
            layout_id          = layout,
            errors             = errors,
            calibration_car_id = car_id,
        )

    # ── Check position variation ────────────────────────────────────────────
    has_pos_var = any(_has_position_variation(lap.samples) for lap in usable_laps)

    # ── Per-lap corner detection ────────────────────────────────────────────
    per_lap_corners: list[list[dict]] = []
    for lap in usable_laps:
        if len(lap.samples) < config.min_segment_samples:
            continue
        if corrected_lap_m and corrected_lap_m > 0:
            cum = cumulative_distances(lap.samples)
            progress = [d / corrected_lap_m for d in cum]
        else:
            progress = normalize_to_lap_progress(lap.samples)
        if not progress or max(progress) < 0.001:
            continue
        smoothed_speed = _smooth([s.speed_kph for s in lap.samples], config.smooth_window)
        corners = _detect_corner_apex_candidates(lap.samples, progress, smoothed_speed, config)
        per_lap_corners.append(corners)

    # ── Multi-lap cluster ───────────────────────────────────────────────────
    clusters = _cluster_apex_progress(per_lap_corners, config.apex_merge_radius)
    confirmed_count = sum(1 for cl in clusters if len(cl) >= 2)

    # ── Build primary segments ──────────────────────────────────────────────
    segments, build_warnings = _build_segments_from_clusters(
        clusters, session, config, has_pos_var
    )

    # ── Auxiliary: gear zones ───────────────────────────────────────────────
    # Detect gear zones from the first usable lap as representative
    first_lap = usable_laps[0]
    if corrected_lap_m and corrected_lap_m > 0:
        _cum = cumulative_distances(first_lap.samples)
        first_progress = [d / corrected_lap_m for d in _cum]
    else:
        first_progress = normalize_to_lap_progress(first_lap.samples)
    first_corners = per_lap_corners[0] if per_lap_corners else []

    if first_corners and first_progress:
        gear_segs = _detect_gear_zones_from_lap(
            first_lap.samples, first_progress, first_corners,
            track_loc, layout, car_id,
        )
        segments.extend(gear_segs)

    # ── Auxiliary: limiter zones ────────────────────────────────────────────
    if first_progress:
        limiter_segs = _detect_limiter_zones_from_lap(
            first_lap.samples, first_progress, track_loc, layout, car_id, config
        )
        segments.extend(limiter_segs)

    # ── Auxiliary: kerb candidates (multi-lap) ──────────────────────────────
    kerb_segs = _detect_kerb_candidates_multi_lap(
        usable_laps, track_loc, layout, car_id, config
    )
    segments.extend(kerb_segs)

    # ── Assign corner numbers ───────────────────────────────────────────────
    segments.sort(key=lambda s: s.lap_progress_start)
    segments = assign_corner_numbers(segments, expected_corner_count)

    # ── Inject PIT_LANE segment from station_map if available ───────────────
    if station_map is not None:
        pit_lane = getattr(station_map, "pit_lane", None)
        if pit_lane is not None:
            pit_seg = DetectedTrackSegment(
                segment_id         = "pit_lane",
                segment_type       = TrackSegmentType.PIT_LANE,
                display_name       = "Pit Lane",
                lap_progress_start = pit_lane.entry_progress,
                lap_progress_end   = pit_lane.exit_progress,
                lap_progress_mid   = (pit_lane.entry_progress + pit_lane.exit_progress) / 2.0,
                confidence         = TrackSegmentDetectionConfidence.MEDIUM,
                evidence           = [
                    f"Entry station {pit_lane.entry_station_m:.0f} m, "
                    f"exit station {pit_lane.exit_station_m:.0f} m — detected from pit-in laps"
                ],
                source_lap_count   = 0,
                track_location_id  = track_loc,
                layout_id          = layout,
            )
            segments.append(pit_seg)
            segments.sort(key=lambda s: s.lap_progress_start)

    # ── Count-mismatch check ────────────────────────────────────────────────
    detected_corner_count = sum(
        1 for s in segments if s.segment_type == TrackSegmentType.APEX_ZONE
    )

    corner_count_matches: Optional[bool] = None
    result_warnings = list(build_warnings)

    if expected_corner_count is not None:
        diff = abs(detected_corner_count - expected_corner_count)
        corner_count_matches = diff <= 2
        if not corner_count_matches:
            result_warnings.append(
                f"Corner count mismatch: detected {detected_corner_count}, "
                f"expected {expected_corner_count} (diff {diff}). "
                "Record more calibration laps or adjust speed-drop threshold."
            )

    if not has_pos_var:
        result_warnings.append(
            "No X/Z position variation — heading/curvature unavailable. "
            "Segment confidence is limited; corner direction is UNKNOWN."
        )

    # ── Overall confidence ──────────────────────────────────────────────────
    n_laps = len(usable_laps)
    if n_laps >= 3 and has_pos_var and confirmed_count > 0:
        overall_conf = TrackSegmentDetectionConfidence.HIGH
    elif n_laps >= 2 and confirmed_count > 0:
        overall_conf = TrackSegmentDetectionConfidence.MEDIUM
    elif n_laps >= 1:
        overall_conf = TrackSegmentDetectionConfidence.LOW
    else:
        overall_conf = TrackSegmentDetectionConfidence.INSUFFICIENT

    return SegmentDetectionResult(
        success                     = True,
        track_location_id           = track_loc,
        layout_id                   = layout,
        segments                    = segments,
        detected_corner_count       = detected_corner_count,
        expected_corner_count       = expected_corner_count,
        corner_count_matches_expected = corner_count_matches,
        source_lap_count            = n_laps,
        confidence                  = overall_conf,
        warnings                    = result_warnings,
        calibration_car_id          = car_id,
    )


# ---------------------------------------------------------------------------
# JSON export / import
# ---------------------------------------------------------------------------

def export_segment_detection_json(
    result: SegmentDetectionResult,
    output_dir: Optional[Path] = None,
    session_id: str = "",
) -> Path:
    """Write a SegmentDetectionResult to JSON.

    Filename pattern:
      <track_location_id>__<layout_id>__segments__<session_id>.json

    Stored under output_dir (defaults to SEGMENT_MODELS_DIR).
    """
    if output_dir is None:
        output_dir = SEGMENT_MODELS_DIR
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    sid = session_id or result.detected_at.replace(":", "-").replace(".", "-")
    fname = (
        f"{result.track_location_id}__{result.layout_id}"
        f"__segments__{sid}.json"
    )
    path = output_dir / fname

    def _to_json_safe(obj):
        if isinstance(obj, Enum):
            return obj.value
        if isinstance(obj, Path):
            return str(obj)
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    payload = {
        "schema": "segment_detection_result_v1",
        "success"                     : result.success,
        "track_location_id"           : result.track_location_id,
        "layout_id"                   : result.layout_id,
        "detected_corner_count"       : result.detected_corner_count,
        "expected_corner_count"       : result.expected_corner_count,
        "corner_count_matches_expected": result.corner_count_matches_expected,
        "source_lap_count"            : result.source_lap_count,
        "confidence"                  : result.confidence.value,
        "errors"                      : result.errors,
        "warnings"                    : result.warnings,
        "detected_at"                 : result.detected_at,
        "calibration_car_id"          : result.calibration_car_id,
        "segments": [
            {
                "segment_id"         : s.segment_id,
                "segment_type"       : s.segment_type.value,
                "display_name"       : s.display_name,
                "lap_progress_start" : s.lap_progress_start,
                "lap_progress_end"   : s.lap_progress_end,
                "lap_progress_mid"   : s.lap_progress_mid,
                "confidence"         : s.confidence.value,
                "evidence"           : s.evidence,
                "warnings"           : s.warnings,
                "source_lap_count"   : s.source_lap_count,
                "turn_number"        : s.turn_number,
                "track_location_id"  : s.track_location_id,
                "layout_id"          : s.layout_id,
                "distance_start_m"   : s.distance_start_m,
                "distance_end_m"     : s.distance_end_m,
                "direction"          : s.direction.value if s.direction else None,
                "calibration_car_id" : s.calibration_car_id,
            }
            for s in result.segments
        ],
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=_to_json_safe)

    return path


def import_segment_detection_json(json_path: Path) -> SegmentDetectionResult:
    """Load a SegmentDetectionResult from JSON.

    Raises FileNotFoundError if the file does not exist.
    Raises ValueError if the file is not a valid segment detection JSON.
    """
    json_path = Path(json_path)
    if not json_path.exists():
        raise FileNotFoundError(f"Segment detection file not found: {json_path}")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if data.get("schema") != "segment_detection_result_v1":
        raise ValueError(f"Unrecognised schema: {data.get('schema')}")

    def _parse_direction(v) -> Optional[TrackSegmentDirection]:
        if v is None:
            return None
        try:
            return TrackSegmentDirection(v)
        except ValueError:
            return None

    segments = [
        DetectedTrackSegment(
            segment_id         = s["segment_id"],
            segment_type       = TrackSegmentType(s["segment_type"]),
            display_name       = s["display_name"],
            lap_progress_start = s["lap_progress_start"],
            lap_progress_end   = s["lap_progress_end"],
            lap_progress_mid   = s["lap_progress_mid"],
            confidence         = TrackSegmentDetectionConfidence(s["confidence"]),
            evidence           = s.get("evidence", []),
            warnings           = s.get("warnings", []),
            source_lap_count   = s.get("source_lap_count", 0),
            turn_number        = s.get("turn_number"),
            track_location_id  = s.get("track_location_id"),
            layout_id          = s.get("layout_id"),
            distance_start_m   = s.get("distance_start_m"),
            distance_end_m     = s.get("distance_end_m"),
            direction          = _parse_direction(s.get("direction")),
            calibration_car_id = s.get("calibration_car_id"),
        )
        for s in data.get("segments", [])
    ]

    return SegmentDetectionResult(
        success                       = data["success"],
        track_location_id             = data["track_location_id"],
        layout_id                     = data["layout_id"],
        segments                      = segments,
        detected_corner_count         = data.get("detected_corner_count", 0),
        expected_corner_count         = data.get("expected_corner_count"),
        corner_count_matches_expected = data.get("corner_count_matches_expected"),
        source_lap_count              = data.get("source_lap_count", 0),
        confidence                    = TrackSegmentDetectionConfidence(data.get("confidence", "insufficient")),
        errors                        = data.get("errors", []),
        warnings                      = data.get("warnings", []),
        detected_at                   = data.get("detected_at", ""),
        calibration_car_id            = data.get("calibration_car_id"),
    )
