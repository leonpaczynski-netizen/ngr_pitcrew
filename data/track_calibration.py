"""Track Calibration — lap capture data model, quality evaluator, and reference path builder.

Pure Python, no PyQt6 dependency.  All functions are unit-testable without a Qt application.

Architecture boundary:
  - Owns: calibration lap data, quality assessment, reference path geometry.
  - Does NOT own: corner detection, segment classification, AI prompt integration.
  - Calibration car is always Porsche 911 RSR (991) '17 by default.
  - Track geometry is car-independent.  Braking/gear/throttle behaviour are stored
    as Porsche RSR calibration data, NOT as universal track truth.
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

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Minimum number of TelemetrySample objects for a lap to be considered usable.
MIN_CALIBRATION_SAMPLES: int = 50

#: Distance jump (metres) between consecutive samples that flags a teleport/reset.
MAX_JUMP_THRESHOLD_M: float = 100.0

#: Maximum fraction of samples in pit lane before a lap is rejected.
MAX_PIT_FRACTION: float = 0.10

#: Maximum fraction of off-track samples before a lap is rejected.
MAX_OFF_TRACK_FRACTION: float = 0.30

#: Factor by which a lap duration may exceed the session median before rejection.
LAP_DURATION_OUTLIER_FACTOR: float = 2.0

#: Factor by which a lap path length may exceed the session median before rejection.
LAP_PATH_OUTLIER_FACTOR: float = 2.0

#: Number of progress buckets used for the reference path.
N_PROGRESS_BUCKETS: int = 200

#: Minimum usable laps needed to build a reference path.
MIN_USABLE_LAPS_FOR_PATH: int = 2

#: Road-normal Y threshold below which a sample is considered off-track.
OFF_TRACK_ROAD_PLANE_Y_THRESHOLD: float = 0.5

#: Profile ID of the primary calibration car (Porsche 911 RSR (991) '17).
PRIMARY_CALIBRATION_CAR_ID: str = "porsche_911_rsr_991_2017"

#: Folder where reference path JSON files are stored (relative to project root).
TRACK_MODELS_DIR: Path = Path(__file__).parent.parent / "data" / "track_models"


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class CalibrationLapQuality(str, Enum):
    """Quality rating assigned to a recorded calibration lap."""
    USABLE         = "usable"
    LOW_CONFIDENCE = "low_confidence"
    REJECTED       = "rejected"


class CalibrationSource(str, Enum):
    """How the calibration data was captured."""
    GT7_TELEMETRY_LIVE = "gt7_telemetry_live"
    IMPORTED_JSON      = "imported_json"
    SYNTHETIC_TEST     = "synthetic_test"


# ---------------------------------------------------------------------------
# Core data models
# ---------------------------------------------------------------------------

@dataclass
class TelemetrySample:
    """One telemetry snapshot captured during a calibration lap.

    Fields match the GT7Packet / TelemetryFrame channels that are actually
    available.  Optional fields are None when the channel is not available or
    not reliable for the capture source.
    """
    timestamp_ms: int           # elapsed ms within the lap
    lap_number: int
    x: float                    # GT7 world-space X (m)
    y: float                    # GT7 world-space Y (m)
    z: float                    # GT7 world-space Z (m)
    speed_kph: float
    gear: int
    rpm: float
    throttle: float             # 0.0 – 1.0
    brake: float                # 0.0 – 1.0
    road_distance: float = 0.0  # metres along track surface
    # Channels not always available
    steering: Optional[float] = None     # GT7 does not expose steering angle
    yaw_rate: Optional[float] = None     # angvel_z rad/s if captured
    road_plane_y: Optional[float] = None # road normal Y; 1.0 = flat tarmac
    is_off_track: Optional[bool] = None
    is_in_pit_lane: Optional[bool] = None
    surface_type: str = "road"

    # ------------------------------------------------------------------ factory

    @classmethod
    def from_frame(cls, frame, lap_number: int) -> "TelemetrySample":
        """Build from a TelemetryFrame (from telemetry/recorder.py).

        Accepts the frame type via duck-typing so this module has no import
        dependency on telemetry.recorder.
        """
        road_plane_y = getattr(frame, "road_plane_y", None)
        off_track: Optional[bool] = None
        if road_plane_y is not None:
            off_track = road_plane_y < OFF_TRACK_ROAD_PLANE_Y_THRESHOLD and frame.speed_kmh > 20.0

        road_y = road_plane_y
        if road_y is None:
            surface_type = "road"
        elif road_y >= 0.85:
            surface_type = "road"
        elif road_y >= 0.50:
            surface_type = "kerb"
        else:
            surface_type = "grass"

        return cls(
            timestamp_ms  = getattr(frame, "elapsed_ms", 0),
            lap_number    = lap_number,
            x             = getattr(frame, "pos_x", 0.0),
            y             = getattr(frame, "pos_y", 0.0),
            z             = getattr(frame, "pos_z", 0.0),
            speed_kph     = getattr(frame, "speed_kmh", 0.0),
            gear          = getattr(frame, "gear", 0),
            rpm           = getattr(frame, "rpm", 0.0),
            throttle      = getattr(frame, "throttle", 0.0),
            brake         = getattr(frame, "brake", 0.0),
            road_distance = getattr(frame, "road_distance", 0.0),
            steering      = None,            # not in GT7 packet
            yaw_rate      = getattr(frame, "angvel_z", None),
            road_plane_y  = road_plane_y,
            is_off_track  = off_track,
            is_in_pit_lane= None,            # no per-sample pit lane flag in GT7
            surface_type  = surface_type,
        )

    # ------------------------------------------------------------------ helpers

    def has_valid_xyz(self) -> bool:
        """True if x/y/z coordinates are present and non-zero."""
        return not (self.x == 0.0 and self.y == 0.0 and self.z == 0.0)


@dataclass
class LapQualityResult:
    """Output of the lap quality evaluator."""
    quality: CalibrationLapQuality
    reasons: list[str] = field(default_factory=list)
    sample_count: int = 0
    path_length_m: float = 0.0
    duration_ms: int = 0

    @property
    def is_usable(self) -> bool:
        return self.quality == CalibrationLapQuality.USABLE


@dataclass
class CalibrationLap:
    """A single recorded calibration lap with quality rating."""
    lap_number: int
    lap_time_ms: int
    samples: list[TelemetrySample] = field(default_factory=list)
    quality: CalibrationLapQuality = CalibrationLapQuality.REJECTED
    quality_reasons: list[str] = field(default_factory=list)
    path_length_m: float = 0.0
    is_pit_lap: bool = False


@dataclass
class CalibrationSession:
    """All calibration laps recorded for one track layout."""
    session_id: str
    track_location_id: str
    layout_id: str
    calibration_car_id: str = PRIMARY_CALIBRATION_CAR_ID
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = CalibrationSource.GT7_TELEMETRY_LIVE
    laps: list[CalibrationLap] = field(default_factory=list)
    notes: Optional[str] = None
    modelling_status: str = "not_modelled"


@dataclass
class ReferencePathPoint:
    """One averaged point along the reference path."""
    lap_progress: float              # 0.0 – 1.0
    distance_along_lap_m: float      # metres from lap start
    x: float
    y: float
    z: float
    speed_kph_avg: float
    source_lap_count: int
    yaw_rate_avg: Optional[float] = None   # rad/s average from angvel_z samples


@dataclass
class ReferencePath:
    """Reference path built from multiple aligned calibration laps."""
    track_location_id: str
    layout_id: str
    calibration_car_id: str
    source_lap_count: int
    points: list[ReferencePathPoint] = field(default_factory=list)
    confidence: float = 0.0          # 0.0 – 1.0
    built_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    warnings: list[str] = field(default_factory=list)


@dataclass
class CalibrationBuildResult:
    """Result of build_reference_path()."""
    success: bool
    reference_path: Optional[ReferencePath] = None
    usable_lap_count: int = 0
    rejected_lap_count: int = 0
    low_confidence_lap_count: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Distance and progress helpers
# ---------------------------------------------------------------------------

def point_distance_3d(x1: float, y1: float, z1: float,
                       x2: float, y2: float, z2: float) -> float:
    """Euclidean distance between two 3D points (metres)."""
    dx = x2 - x1
    dy = y2 - y1
    dz = z2 - z1
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def estimate_path_length(samples: list[TelemetrySample]) -> float:
    """Sum of 3D Euclidean distances between consecutive sample positions."""
    if len(samples) < 2:
        return 0.0
    total = 0.0
    for i in range(1, len(samples)):
        total += point_distance_3d(
            samples[i - 1].x, samples[i - 1].y, samples[i - 1].z,
            samples[i].x,     samples[i].y,     samples[i].z,
        )
    return total


def detect_coordinate_jumps(
    samples: list[TelemetrySample],
    threshold_m: float = MAX_JUMP_THRESHOLD_M,
) -> list[int]:
    """Return indices where the 3D distance to the previous sample exceeds threshold_m.

    Index i means the jump occurred between samples[i-1] and samples[i].
    """
    jump_indices: list[int] = []
    for i in range(1, len(samples)):
        d = point_distance_3d(
            samples[i - 1].x, samples[i - 1].y, samples[i - 1].z,
            samples[i].x,     samples[i].y,     samples[i].z,
        )
        if d > threshold_m:
            jump_indices.append(i)
    return jump_indices


def cumulative_distances(samples: list[TelemetrySample]) -> list[float]:
    """Return cumulative 3D path distance at each sample (metres).

    First element is always 0.0.  Length equals len(samples).
    """
    if not samples:
        return []
    result = [0.0]
    for i in range(1, len(samples)):
        d = point_distance_3d(
            samples[i - 1].x, samples[i - 1].y, samples[i - 1].z,
            samples[i].x,     samples[i].y,     samples[i].z,
        )
        result.append(result[-1] + d)
    return result


def normalize_to_lap_progress(samples: list[TelemetrySample]) -> list[float]:
    """Return per-sample lap progress values in [0.0, 1.0].

    Progress is derived from cumulative 3D path distance.  Returns [] if
    path length is zero or samples is empty.
    """
    if not samples:
        return []
    dists = cumulative_distances(samples)
    total = dists[-1]
    if total <= 0.0:
        return [0.0] * len(samples)
    return [d / total for d in dists]


def resample_to_buckets(
    samples: list[TelemetrySample],
    n_buckets: int = N_PROGRESS_BUCKETS,
) -> list[list[TelemetrySample]]:
    """Partition samples into n_buckets evenly-spaced lap-progress buckets.

    Returns a list of n_buckets sub-lists.  Some may be empty if no samples
    fall in that progress range.  Buckets are [0/n, 1/n), [1/n, 2/n), …, [N-1/n, 1.0].
    """
    if not samples or n_buckets < 1:
        return [[] for _ in range(n_buckets)]

    progress = normalize_to_lap_progress(samples)
    buckets: list[list[TelemetrySample]] = [[] for _ in range(n_buckets)]

    for s, p in zip(samples, progress):
        bucket_idx = min(int(p * n_buckets), n_buckets - 1)
        buckets[bucket_idx].append(s)

    return buckets


# ---------------------------------------------------------------------------
# Lap quality evaluator
# ---------------------------------------------------------------------------

def evaluate_lap_quality(
    lap: CalibrationLap,
    session_median_duration_ms: Optional[float] = None,
    session_median_path_m: Optional[float] = None,
) -> LapQualityResult:
    """Assess the quality of a calibration lap.

    Parameters
    ----------
    lap : CalibrationLap
        The lap to assess (samples must already be populated; quality/path_length_m
        will be computed here and reflected in the returned result but the lap object
        is NOT mutated by this function).
    session_median_duration_ms : float | None
        Median lap duration for the session (ms).  Used to detect duration outliers.
    session_median_path_m : float | None
        Median path length for the session (m).  Used to detect path outliers.

    Returns
    -------
    LapQualityResult
        quality, reasons, sample_count, path_length_m, duration_ms.
    """
    samples = lap.samples
    n = len(samples)
    path_length = estimate_path_length(samples)
    duration_ms = lap.lap_time_ms

    reasons: list[str] = []
    low_confidence_reasons: list[str] = []
    quality = CalibrationLapQuality.USABLE

    # ── Hard reject: too few samples ────────────────────────────────────────
    if n < MIN_CALIBRATION_SAMPLES:
        reasons.append(
            f"Too few telemetry samples ({n} < {MIN_CALIBRATION_SAMPLES})"
        )

    # ── Hard reject: missing/all-zero xyz ────────────────────────────────────
    invalid_xyz = sum(1 for s in samples if not s.has_valid_xyz())
    if invalid_xyz == n and n > 0:
        reasons.append("All samples have zero/missing x/y/z coordinates")
    elif invalid_xyz > 0:
        low_confidence_reasons.append(
            f"{invalid_xyz}/{n} samples have zero/missing x/y/z coordinates"
        )

    # ── Hard reject: coordinate teleport/jump ───────────────────────────────
    jump_indices = detect_coordinate_jumps(samples)
    if jump_indices:
        reasons.append(
            f"Coordinate jump(s) detected at {len(jump_indices)} location(s) "
            f"(threshold {MAX_JUMP_THRESHOLD_M} m) — likely reset or teleport"
        )

    # ── Hard reject: excessive pit lane samples ──────────────────────────────
    pit_count = sum(1 for s in samples if s.is_in_pit_lane is True)
    if n > 0 and pit_count / n > MAX_PIT_FRACTION:
        reasons.append(
            f"Pit lane samples exceed limit ({pit_count}/{n} = "
            f"{pit_count / n:.0%} > {MAX_PIT_FRACTION:.0%})"
        )

    # ── Hard reject: excessive off-track samples ─────────────────────────────
    off_track_count = sum(1 for s in samples if s.is_off_track is True)
    if n > 0 and off_track_count / n > MAX_OFF_TRACK_FRACTION:
        reasons.append(
            f"Off-track samples exceed limit ({off_track_count}/{n} = "
            f"{off_track_count / n:.0%} > {MAX_OFF_TRACK_FRACTION:.0%})"
        )

    # ── Hard reject: duration outlier ────────────────────────────────────────
    if session_median_duration_ms and session_median_duration_ms > 0 and duration_ms > 0:
        ratio = duration_ms / session_median_duration_ms
        if ratio > LAP_DURATION_OUTLIER_FACTOR or ratio < (1.0 / LAP_DURATION_OUTLIER_FACTOR):
            reasons.append(
                f"Lap duration {duration_ms / 1000:.1f}s is a major outlier "
                f"vs session median {session_median_duration_ms / 1000:.1f}s "
                f"(ratio {ratio:.2f})"
            )

    # ── Hard reject: path length outlier ─────────────────────────────────────
    if session_median_path_m and session_median_path_m > 0 and path_length > 0:
        ratio = path_length / session_median_path_m
        if ratio > LAP_PATH_OUTLIER_FACTOR or ratio < (1.0 / LAP_PATH_OUTLIER_FACTOR):
            reasons.append(
                f"Path length {path_length:.0f} m is a major outlier "
                f"vs session median {session_median_path_m:.0f} m "
                f"(ratio {ratio:.2f})"
            )

    # ── Determine quality ────────────────────────────────────────────────────
    if reasons:
        quality = CalibrationLapQuality.REJECTED
    elif low_confidence_reasons:
        quality = CalibrationLapQuality.LOW_CONFIDENCE
        reasons.extend(low_confidence_reasons)
    else:
        quality = CalibrationLapQuality.USABLE

    return LapQualityResult(
        quality=quality,
        reasons=reasons,
        sample_count=n,
        path_length_m=path_length,
        duration_ms=duration_ms,
    )


def assess_session_laps(session: CalibrationSession) -> list[LapQualityResult]:
    """Evaluate all laps in a session, computing session-level medians first.

    Returns one LapQualityResult per lap (same order as session.laps).
    """
    if not session.laps:
        return []

    # First pass: compute path lengths and durations for median calculation
    path_lengths: list[float] = []
    durations: list[int] = []
    for lap in session.laps:
        path_lengths.append(estimate_path_length(lap.samples))
        durations.append(lap.lap_time_ms)

    median_path = statistics.median(path_lengths) if path_lengths else None
    median_dur  = statistics.median(durations)  if durations  else None

    # Second pass: full quality evaluation with session context
    results: list[LapQualityResult] = []
    for lap in session.laps:
        result = evaluate_lap_quality(
            lap,
            session_median_duration_ms=median_dur,
            session_median_path_m=median_path,
        )
        results.append(result)
    return results


def diagnose_calibration_session(session: "CalibrationSession") -> dict:
    """Return a structured diagnostic snapshot of a calibration session.

    Runs assess_session_laps() and packages results into a diagnostic dict.
    Suitable for UI display without raising.  Never mutates the session.

    Returns
    -------
    dict with keys:
        total_laps, usable_count, rejected_count, low_confidence_count,
        total_samples, per_lap (list of per-lap dicts), all_reasons (list[str]),
        most_common_reason (str | None), car_id (str), has_any_laps (bool)
    """
    from collections import Counter

    _empty = {
        "total_laps": 0,
        "usable_count": 0,
        "rejected_count": 0,
        "low_confidence_count": 0,
        "total_samples": 0,
        "per_lap": [],
        "all_reasons": [],
        "most_common_reason": None,
        "car_id": getattr(session, "calibration_car_id", ""),
        "has_any_laps": False,
    }

    try:
        if not session.laps:
            return _empty

        quality_results = assess_session_laps(session)
        usable = rejected = low_conf = total_samples = 0
        per_lap: list[dict] = []
        all_reasons: list[str] = []

        for lap, qr in zip(session.laps, quality_results):
            total_samples += qr.sample_count
            per_lap.append({
                "lap_number":   lap.lap_number,
                "quality":      qr.quality.value,
                "reasons":      list(qr.reasons),
                "sample_count": qr.sample_count,
                "path_length_m": round(qr.path_length_m, 1),
                "duration_s":    round(qr.duration_ms / 1000, 1) if qr.duration_ms else 0.0,
            })
            if qr.quality == CalibrationLapQuality.USABLE:
                usable += 1
            elif qr.quality == CalibrationLapQuality.LOW_CONFIDENCE:
                low_conf += 1
                all_reasons.extend(qr.reasons)
            else:
                rejected += 1
                all_reasons.extend(qr.reasons)

        most_common: Optional[str] = None
        if all_reasons:
            # Use first 5 words of each reason as the "type" key
            prefixes = [" ".join(r.split()[:5]) for r in all_reasons]
            most_common = Counter(prefixes).most_common(1)[0][0]

        return {
            "total_laps":           len(session.laps),
            "usable_count":         usable,
            "rejected_count":       rejected,
            "low_confidence_count": low_conf,
            "total_samples":        total_samples,
            "per_lap":              per_lap,
            "all_reasons":          all_reasons,
            "most_common_reason":   most_common,
            "car_id":               getattr(session, "calibration_car_id", ""),
            "has_any_laps":         True,
        }
    except Exception:
        return _empty


# ---------------------------------------------------------------------------
# Pit-lap detection (Group 21B)
# ---------------------------------------------------------------------------

#: XZ distance from centroid (metres) used to identify pit-lane excursions.
#: Kept locally to avoid circular import with data.track_map_matching.
_PIT_DISTANCE_THRESHOLD_M: float = 60.0


def detect_pit_lap_raw(
    samples: list,
    threshold_seconds: float = 10.0,
) -> bool:
    """Detect a pit-in lap without needing a centreline.

    Computes XZ centroid of all samples. Any contiguous run of samples where
    the XZ distance from centroid exceeds _PIT_DISTANCE_THRESHOLD_M (60 m)
    lasting > threshold_seconds is treated as pit activity.

    Timestamps come from TelemetrySample.timestamp_ms (elapsed ms within the
    lap). At 60 Hz a 10-second run equals 600 samples; timestamp_ms is used
    directly when available.
    """
    if not samples:
        return False

    # Compute XZ centroid
    n = len(samples)
    cx = sum(s.x for s in samples) / n
    cz = sum(s.z for s in samples) / n

    threshold_ms = threshold_seconds * 1000.0

    run_start_ms: Optional[float] = None  # timestamp_ms when the current run began

    for s in samples:
        dist_xz = math.sqrt((s.x - cx) ** 2 + (s.z - cz) ** 2)
        ts = s.timestamp_ms

        if dist_xz > _PIT_DISTANCE_THRESHOLD_M:
            if run_start_ms is None:
                run_start_ms = ts
            else:
                # Check if this run has lasted long enough
                if (ts - run_start_ms) > threshold_ms:
                    return True
        else:
            run_start_ms = None

    return False


# ---------------------------------------------------------------------------
# Reference path builder
# ---------------------------------------------------------------------------

def _average_bucket(
    bucket: list[TelemetrySample],
) -> tuple[float, float, float, float, Optional[float]]:
    """Return (avg_x, avg_y, avg_z, avg_speed, avg_yaw_rate) for a non-empty bucket.

    avg_yaw_rate is None when no samples in the bucket have a valid yaw_rate value.
    """
    n = len(bucket)
    avg_x = sum(s.x for s in bucket) / n
    avg_y = sum(s.y for s in bucket) / n
    avg_z = sum(s.z for s in bucket) / n
    avg_spd = sum(s.speed_kph for s in bucket) / n
    yaw_vals = [s.yaw_rate for s in bucket if s.yaw_rate is not None]
    avg_yaw: Optional[float] = (sum(yaw_vals) / len(yaw_vals)) if yaw_vals else None
    return avg_x, avg_y, avg_z, avg_spd, avg_yaw


def compute_corrected_lap_length(points: list) -> float:
    """Find lap closure: min 3D distance from last 20% of points back to points[0].

    Returns distance_along_lap_m of the closest point found.
    Falls back to last point if fewer than 10 points or no closure found.
    """
    if len(points) < 10:
        return points[-1].distance_along_lap_m if points else 0.0
    start_x, start_y, start_z = points[0].x, points[0].y, points[0].z
    cutoff = int(len(points) * 0.80)
    search_region = points[cutoff:]

    def dist3d(p):
        return ((p.x - start_x)**2 + (p.y - start_y)**2 + (p.z - start_z)**2) ** 0.5

    closest = min(search_region, key=dist3d)
    return closest.distance_along_lap_m


def build_reference_path(session: CalibrationSession) -> CalibrationBuildResult:
    """Build a reference path from usable calibration laps in a session.

    Algorithm:
    1.  Evaluate quality of every lap (session-aware medians).
    2.  Select only USABLE laps.
    3.  Normalise each usable lap to [0.0, 1.0] lap progress.
    4.  Divide each lap into N_PROGRESS_BUCKETS buckets.
    5.  Average x/y/z/speed across all laps per bucket.
    6.  Assign distance_along_lap_m from cumulative averaged distances.
    7.  Compute confidence from source_lap_count and bucket fill rate.

    Raises no exceptions — all failure modes return success=False.
    """
    if not session.track_location_id or not session.layout_id:
        return CalibrationBuildResult(
            success=False,
            errors=["CalibrationSession is missing track_location_id or layout_id"],
        )

    quality_results = assess_session_laps(session)

    # Persist quality assessment back to CalibrationLap objects so consumers
    # such as detect_track_segments() can filter by quality without re-assessing.
    for lap, qr in zip(session.laps, quality_results):
        lap.quality         = qr.quality
        lap.quality_reasons = list(qr.reasons)

    usable_laps: list[CalibrationLap] = []
    rejected_count = 0
    low_conf_count = 0
    all_warnings: list[str] = []
    pit_lap_count = 0

    for lap, qr in zip(session.laps, quality_results):
        if qr.quality == CalibrationLapQuality.USABLE:
            if detect_pit_lap_raw(lap.samples):
                lap.is_pit_lap = True
                pit_lap_count += 1
                all_warnings.append(
                    f"Lap {lap.lap_number} detected as a pit-in lap and excluded from reference path"
                )
            else:
                usable_laps.append(lap)
        elif qr.quality == CalibrationLapQuality.LOW_CONFIDENCE:
            low_conf_count += 1
            all_warnings.append(
                f"Lap {lap.lap_number} low confidence: {'; '.join(qr.reasons)}"
            )
        else:
            rejected_count += 1
            all_warnings.append(
                f"Lap {lap.lap_number} rejected: {'; '.join(qr.reasons)}"
            )

    if len(usable_laps) < MIN_USABLE_LAPS_FOR_PATH:
        errors_list = [
            f"Not enough usable laps to build reference path "
            f"({len(usable_laps)} usable, need {MIN_USABLE_LAPS_FOR_PATH})"
        ]
        if pit_lap_count > 0 and len(usable_laps) == 0:
            all_warnings.append(
                "All calibration laps appear to be pit-in laps. "
                "No reference path built. Drive a clean lap first."
            )
        return CalibrationBuildResult(
            success=False,
            usable_lap_count=len(usable_laps),
            rejected_lap_count=rejected_count,
            low_confidence_lap_count=low_conf_count,
            warnings=all_warnings,
            errors=errors_list,
        )

    # ── Per-lap bucketing ────────────────────────────────────────────────────
    # Shape: [lap_index][bucket_index] = list[TelemetrySample]
    all_buckets: list[list[list[TelemetrySample]]] = []
    for lap in usable_laps:
        all_buckets.append(resample_to_buckets(lap.samples, N_PROGRESS_BUCKETS))

    # ── Merge buckets across laps ────────────────────────────────────────────
    merged: list[list[TelemetrySample]] = []
    for b_idx in range(N_PROGRESS_BUCKETS):
        combined: list[TelemetrySample] = []
        for lap_buckets in all_buckets:
            combined.extend(lap_buckets[b_idx])
        merged.append(combined)

    # ── Build reference path points ──────────────────────────────────────────
    points: list[ReferencePathPoint] = []
    filled_buckets = 0
    cumulative_dist = 0.0
    prev_point: Optional[tuple[float, float, float]] = None

    for b_idx, bucket in enumerate(merged):
        if not bucket:
            continue
        filled_buckets += 1
        avg_x, avg_y, avg_z, avg_spd, avg_yaw = _average_bucket(bucket)

        if prev_point is not None:
            step_dist = point_distance_3d(
                prev_point[0], prev_point[1], prev_point[2],
                avg_x, avg_y, avg_z,
            )
            cumulative_dist += step_dist
        prev_point = (avg_x, avg_y, avg_z)

        points.append(ReferencePathPoint(
            lap_progress         = b_idx / (N_PROGRESS_BUCKETS - 1) if N_PROGRESS_BUCKETS > 1 else 0.0,
            distance_along_lap_m = cumulative_dist,
            x                    = avg_x,
            y                    = avg_y,
            z                    = avg_z,
            speed_kph_avg        = avg_spd,
            source_lap_count     = len(bucket),
            yaw_rate_avg         = avg_yaw,
        ))

    if not points:
        return CalibrationBuildResult(
            success=False,
            usable_lap_count=len(usable_laps),
            rejected_lap_count=rejected_count,
            low_confidence_lap_count=low_conf_count,
            warnings=all_warnings,
            errors=["No reference path points could be computed from usable laps"],
        )

    # ── Lap closure correction ────────────────────────────────────────────────
    corrected_length = compute_corrected_lap_length(points)
    points[-1].distance_along_lap_m = corrected_length

    # ── Renormalise lap_progress to corrected lap length ──────────────────────
    corrected_m = points[-1].distance_along_lap_m
    if corrected_m > 0:
        for pt in points:
            pt.lap_progress = pt.distance_along_lap_m / corrected_m

    # ── Confidence score ─────────────────────────────────────────────────────
    fill_rate = filled_buckets / N_PROGRESS_BUCKETS
    lap_confidence = min(1.0, len(usable_laps) / 5.0)  # saturates at 5 laps
    confidence = round(fill_rate * lap_confidence, 3)

    if fill_rate < 0.8:
        all_warnings.append(
            f"Reference path has sparse coverage: only {fill_rate:.0%} of buckets filled"
        )
    if len(usable_laps) < 3:
        all_warnings.append(
            f"Reference path built from only {len(usable_laps)} lap(s); "
            "3 or more are recommended for reliability"
        )

    ref_path = ReferencePath(
        track_location_id  = session.track_location_id,
        layout_id          = session.layout_id,
        calibration_car_id = session.calibration_car_id,
        source_lap_count   = len(usable_laps),
        points             = points,
        confidence         = confidence,
        warnings           = list(all_warnings),
    )

    return CalibrationBuildResult(
        success                 = True,
        reference_path          = ref_path,
        usable_lap_count        = len(usable_laps),
        rejected_lap_count      = rejected_count,
        low_confidence_lap_count= low_conf_count,
        warnings                = list(all_warnings),
    )


# ---------------------------------------------------------------------------
# File export / import helpers
# ---------------------------------------------------------------------------

def export_reference_path_json(
    path: ReferencePath,
    output_dir: Optional[Path] = None,
) -> Path:
    """Serialise a ReferencePath to a JSON file under output_dir.

    The filename is ``<track_location_id>__<layout_id>.reference_path.json``.
    Creates output_dir if it does not exist.

    Returns the Path to the written file.
    """
    out = output_dir or TRACK_MODELS_DIR
    out.mkdir(parents=True, exist_ok=True)

    filename = f"{path.track_location_id}__{path.layout_id}.reference_path.json"
    dest = out / filename

    payload = {
        "track_location_id":  path.track_location_id,
        "layout_id":          path.layout_id,
        "calibration_car_id": path.calibration_car_id,
        "source_lap_count":   path.source_lap_count,
        "confidence":         path.confidence,
        "built_at":           path.built_at,
        "warnings":           path.warnings,
        "points": [
            {
                "lap_progress":         pt.lap_progress,
                "distance_along_lap_m": pt.distance_along_lap_m,
                "x":                    pt.x,
                "y":                    pt.y,
                "z":                    pt.z,
                "speed_kph_avg":        pt.speed_kph_avg,
                "source_lap_count":     pt.source_lap_count,
                "yaw_rate_avg":         pt.yaw_rate_avg,
            }
            for pt in path.points
        ],
    }

    dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return dest


def import_reference_path_json(json_path: Path) -> ReferencePath:
    """Load a ReferencePath from a previously exported JSON file.

    Raises FileNotFoundError, json.JSONDecodeError, KeyError on bad files.
    """
    raw = json.loads(json_path.read_text(encoding="utf-8"))
    points = [
        ReferencePathPoint(
            lap_progress         = pt["lap_progress"],
            distance_along_lap_m = pt["distance_along_lap_m"],
            x                    = pt["x"],
            y                    = pt["y"],
            z                    = pt["z"],
            speed_kph_avg        = pt["speed_kph_avg"],
            source_lap_count     = pt["source_lap_count"],
            yaw_rate_avg         = pt.get("yaw_rate_avg"),
        )
        for pt in raw.get("points", [])
    ]
    return ReferencePath(
        track_location_id  = raw["track_location_id"],
        layout_id          = raw["layout_id"],
        calibration_car_id = raw.get("calibration_car_id", PRIMARY_CALIBRATION_CAR_ID),
        source_lap_count   = raw.get("source_lap_count", len(points)),
        points             = points,
        confidence         = raw.get("confidence", 0.0),
        built_at           = raw.get("built_at", ""),
        warnings           = raw.get("warnings", []),
    )


# ---------------------------------------------------------------------------
# Persistence audit helper (Group 17M UAT defect remediation)
# ---------------------------------------------------------------------------

def reference_path_filename(loc_id: str, lay_id: str) -> str:
    """Return the expected filename for a reference path JSON."""
    return f"{loc_id}__{lay_id}.reference_path.json"


# ---------------------------------------------------------------------------
# Calibration laps serialisation (Group 17N UAT defect remediation)
# ---------------------------------------------------------------------------

def calibration_laps_filename(loc_id: str, lay_id: str) -> str:
    """Return the expected filename for a calibration laps JSON."""
    return f"{loc_id}__{lay_id}.calibration_laps.json"


def export_calibration_laps_json(
    laps: list["CalibrationLap"],
    loc_id: str,
    lay_id: str,
    car_id: str = PRIMARY_CALIBRATION_CAR_ID,
    output_dir: Optional[Path] = None,
) -> Path:
    """Serialise USABLE CalibrationLap objects (with raw TelemetrySample data) to JSON.

    Only USABLE laps are written; rejected / low-confidence laps are not persisted
    because segment detection requires usable laps exclusively.

    The filename is ``<loc_id>__<lay_id>.calibration_laps.json``.
    Creates output_dir if it does not exist.  Returns the Path to the written file.
    """
    usable = [lap for lap in laps if lap.quality == CalibrationLapQuality.USABLE]

    out = output_dir or TRACK_MODELS_DIR
    out.mkdir(parents=True, exist_ok=True)

    dest = out / calibration_laps_filename(loc_id, lay_id)

    def _sample_dict(s: TelemetrySample) -> dict:
        return {
            "timestamp_ms":   s.timestamp_ms,
            "lap_number":     s.lap_number,
            "x": s.x, "y": s.y, "z": s.z,
            "speed_kph":      s.speed_kph,
            "gear":           s.gear,
            "rpm":            s.rpm,
            "throttle":       s.throttle,
            "brake":          s.brake,
            "road_distance":  s.road_distance,
            "yaw_rate":       s.yaw_rate,
            "road_plane_y":   s.road_plane_y,
            "is_off_track":   s.is_off_track,
            "surface_type":   s.surface_type,
        }

    payload = {
        "format_version":    1,
        "track_location_id": loc_id,
        "layout_id":         lay_id,
        "calibration_car_id": car_id,
        "saved_at":          datetime.now(timezone.utc).isoformat(),
        "usable_lap_count":  len(usable),
        "laps": [
            {
                "lap_number":      lap.lap_number,
                "lap_time_ms":     lap.lap_time_ms,
                "quality":         lap.quality.value,
                "quality_reasons": lap.quality_reasons,
                "path_length_m":   lap.path_length_m,
                "samples":         [_sample_dict(s) for s in lap.samples],
            }
            for lap in usable
        ],
    }

    dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return dest


def import_calibration_laps_json(json_path: Path) -> "CalibrationSession":
    """Load saved USABLE CalibrationLap objects and return a CalibrationSession.

    The returned session has only USABLE laps, no in-progress samples, and
    state suitable for passing to detect_track_segments().

    Raises FileNotFoundError, json.JSONDecodeError, KeyError on bad files.
    """
    raw = json.loads(json_path.read_text(encoding="utf-8"))

    loc_id  = raw["track_location_id"]
    lay_id  = raw["layout_id"]
    car_id  = raw.get("calibration_car_id", PRIMARY_CALIBRATION_CAR_ID)
    saved_at = raw.get("saved_at", "")

    laps: list[CalibrationLap] = []
    for ld in raw.get("laps", []):
        samples: list[TelemetrySample] = [
            TelemetrySample(
                timestamp_ms  = s["timestamp_ms"],
                lap_number    = s["lap_number"],
                x             = s["x"],
                y             = s["y"],
                z             = s["z"],
                speed_kph     = s["speed_kph"],
                gear          = s["gear"],
                rpm           = s["rpm"],
                throttle      = s["throttle"],
                brake         = s["brake"],
                road_distance = s.get("road_distance", 0.0),
                yaw_rate      = s.get("yaw_rate"),
                road_plane_y  = s.get("road_plane_y"),
                is_off_track  = s.get("is_off_track"),
                surface_type  = s.get("surface_type", "road"),
            )
            for s in ld.get("samples", [])
        ]
        lap = CalibrationLap(
            lap_number     = ld["lap_number"],
            lap_time_ms    = ld["lap_time_ms"],
            samples        = samples,
            quality        = CalibrationLapQuality(ld.get("quality", "usable")),
            quality_reasons= ld.get("quality_reasons", []),
            path_length_m  = ld.get("path_length_m", 0.0),
        )
        laps.append(lap)

    session = CalibrationSession(
        session_id         = f"loaded__{loc_id}__{lay_id}__from_disk",
        track_location_id  = loc_id,
        layout_id          = lay_id,
        calibration_car_id = car_id,
        started_at         = saved_at,
        laps               = laps,
    )
    return session


@dataclass
class TrackModelFileAudit:
    """Snapshot of what track model files exist on disk for a given track/layout.

    All fields are safe to read without checking status first.
    Never contains references to live session state.
    """
    loc_id: str = ""
    lay_id: str = ""

    ref_path_file: str = ""          # absolute path string, or ""
    ref_path_exists: bool = False
    ref_path_load_ok: bool = False
    ref_path_load_error: str = ""
    ref_path_modified: str = ""      # ISO-8601 mtime, or ""
    ref_path_point_count: int = 0
    ref_path_confidence: float = 0.0
    ref_path_source_laps: int = 0

    # DEF-17N-UAT-004: calibration laps file (raw usable lap data for detect_segments)
    calibration_laps_file: str = ""
    calibration_laps_exists: bool = False
    calibration_laps_usable_count: int = 0
    calibration_laps_load_error: str = ""

    reviewed_file: str = ""
    reviewed_exists: bool = False

    offset_file: str = ""
    offset_exists: bool = False

    def summary_line(self) -> str:
        """Return a compact one-line summary for UI display."""
        if not self.loc_id or not self.lay_id:
            return "No track selected"
        parts: list[str] = []
        if self.ref_path_exists:
            if self.ref_path_load_ok:
                laps_note = (
                    f", {self.calibration_laps_usable_count} laps persisted"
                    if self.calibration_laps_exists and self.calibration_laps_usable_count > 0
                    else ""
                )
                parts.append(
                    f"Reference path: {self.ref_path_point_count} pts "
                    f"(conf {self.ref_path_confidence:.2f}, "
                    f"{self.ref_path_source_laps} laps{laps_note})"
                )
            else:
                parts.append(
                    f"Reference path: file exists but could not load "
                    f"({self.ref_path_load_error})"
                )
        else:
            parts.append("Reference path: not saved")
        if self.reviewed_exists:
            parts.append("Reviewed model: found")
        if self.offset_exists:
            parts.append("Offset calibration: found")
        return "  |  ".join(parts)

    def ref_path_status_text(self) -> str:
        """Short text for the 'saved path' label in the UI."""
        if not self.ref_path_exists:
            return ""
        if self.ref_path_load_ok:
            mod = f"  (saved {self.ref_path_modified})" if self.ref_path_modified else ""
            return f"Saved: {self.ref_path_file}{mod}"
        return f"Saved file found but unreadable: {self.ref_path_load_error}"

    @property
    def can_detect_segments(self) -> bool:
        """True if Detect Segments can run from persisted data (no live session needed)."""
        return (
            self.ref_path_exists
            and self.ref_path_load_ok
            and self.calibration_laps_exists
            and self.calibration_laps_usable_count > 0
        )

    @property
    def is_legacy_ref_path_only(self) -> bool:
        """True if a ref path exists but no raw calibration laps were saved.

        This is the pre-Group-17N state: user must re-run one calibration session
        to persist the lap data needed by Detect Segments.
        """
        return self.ref_path_exists and self.ref_path_load_ok and not self.calibration_laps_exists


def audit_track_model_files(
    loc_id: str,
    lay_id: str,
    search_dir: Optional[Path] = None,
) -> TrackModelFileAudit:
    """Return an audit of what track model files exist for this loc/layout pair.

    Never raises.  All attribute errors are captured into the audit fields.
    """
    audit = TrackModelFileAudit(loc_id=loc_id, lay_id=lay_id)
    try:
        d = search_dir or TRACK_MODELS_DIR

        # ── Reference path ────────────────────────────────────────────────────
        ref_name = reference_path_filename(loc_id, lay_id)
        ref_path = d / ref_name
        audit.ref_path_file = str(ref_path)
        audit.ref_path_exists = ref_path.exists()
        if audit.ref_path_exists:
            try:
                import datetime as _dt
                mtime = ref_path.stat().st_mtime
                audit.ref_path_modified = (
                    _dt.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
                )
                rp = import_reference_path_json(ref_path)
                audit.ref_path_load_ok     = True
                audit.ref_path_point_count = len(rp.points)
                audit.ref_path_confidence  = rp.confidence
                audit.ref_path_source_laps = rp.source_lap_count
            except Exception as exc:  # noqa: BLE001
                audit.ref_path_load_error = f"{type(exc).__name__}: {exc}"

        # ── Calibration laps file (DEF-17N-UAT-004) ───────────────────────────
        laps_name = calibration_laps_filename(loc_id, lay_id)
        laps_path = d / laps_name
        audit.calibration_laps_file   = str(laps_path)
        audit.calibration_laps_exists = laps_path.exists()
        if audit.calibration_laps_exists:
            try:
                import json as _json
                raw = _json.loads(laps_path.read_text(encoding="utf-8"))
                audit.calibration_laps_usable_count = int(
                    raw.get("usable_lap_count", len(raw.get("laps", [])))
                )
            except Exception as exc:  # noqa: BLE001
                audit.calibration_laps_load_error = f"{type(exc).__name__}: {exc}"
                audit.calibration_laps_exists = False  # treat as missing if corrupt

        # ── Reviewed segment file ─────────────────────────────────────────────
        reviewed_name = f"{loc_id}__{lay_id}.reviewed_segments.json"
        reviewed_path = d / reviewed_name
        audit.reviewed_file   = str(reviewed_path)
        audit.reviewed_exists = reviewed_path.exists()

        # ── Lap offset calibration file ───────────────────────────────────────
        offset_name = f"{loc_id}__{lay_id}__lap_offset.json"
        offset_path = d / offset_name
        audit.offset_file   = str(offset_path)
        audit.offset_exists = offset_path.exists()

    except Exception as exc:  # noqa: BLE001
        audit.ref_path_load_error = f"Audit failed: {exc}"

    return audit
