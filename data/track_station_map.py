"""Track Station Map — 1 metre resolution station model for a track/layout.

Pure Python, no PyQt6 dependency.

Layer 1 of the three-layer track modelling architecture:
  Layer 1 — Track Model (this module): stable circuit truth from seed + telemetry
  Layer 2 — Driver Reference Path: car-specific driving line
  Layer 3 — Telemetry Overlay: behaviour events attached to known stations

Design rules:
  - Track geometry is derived from X/Y/Z position ONLY.
  - Brake, throttle, gear, RPM, lock-up and wheelspin data are NOT used to define shape.
  - Corner detection uses horizontal-plane curvature (heading change per metre).
  - If curvature-detected count < corners_expected, seeded placeholders fill the gap
    (LOW confidence) so the map always reflects the expected circuit anatomy.
  - Pit/out-lap fragments are excluded from the station build.

Coordinate system (GT7):
  X = world left/right
  Y = world up (vertical)
  Z = world forward/back
  Curvature is computed in the XZ horizontal plane.
"""
from __future__ import annotations

import json
import math
import statistics
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple

STATION_MODELS_DIR: Path = Path(__file__).parent.parent / "data" / "track_models"
STATION_MAP_SCHEMA: str  = "track_station_map_v1"
DEFAULT_TRACK_WIDTH_M: float = 12.0   # 6 m each side — representative GT car circuit
DEFAULT_SPACING_M: float     = 1.0
_MIN_CURVATURE_THRESHOLD: float = 0.006   # rad/m ≈ 167 m radius — gentle curve
_CORNER_MIN_SEPARATION_M: float = 80.0   # prevent splitting one wide corner into two
_CURVATURE_SMOOTH_WINDOW: int  = 15      # stations over which to smooth curvature


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class CornerPhase(str, Enum):
    STRAIGHT = "straight"
    BRAKING  = "braking"
    TURN_IN  = "turn_in"
    APEX     = "apex"
    EXIT     = "exit"
    UNKNOWN  = "unknown"


class WidthSource(str, Enum):
    SEED_DEFAULT        = "seed_default"
    SEED_SEGMENT        = "seed_segment"
    TELEMETRY_OBSERVED  = "telemetry_observed"
    TELEMETRY_INFERRED  = "telemetry_inferred"
    UNKNOWN             = "unknown"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class StationPoint:
    """One 1-metre station on the track centreline."""
    station_m:     float
    progress_pct:  float          # 0–100
    x:             float
    y:             float
    z:             float
    heading_rad:   float = 0.0
    curvature:     float = 0.0   # rad/m (signed: +left, –right in XZ plane)
    gradient:      float = 0.0   # rise per metre (positive = uphill)
    left_width_m:  float = 0.0   # 0 = unknown
    right_width_m: float = 0.0
    width_source:  str   = WidthSource.UNKNOWN
    segment_id:    Optional[str] = None
    corner_id:     Optional[str] = None
    corner_phase:  str   = CornerPhase.UNKNOWN
    confidence:    float = 0.0   # 0–1
    source:        str   = "reference_path"


@dataclass
class SeededCorner:
    """Known or detected corner on the layout."""
    corner_id:        str     # "T1", "T2", …
    display_name:     str
    approx_station_m: float
    approx_progress:  float   # 0–1
    is_seeded_placeholder: bool = False   # True = inferred, not curvature-detected
    confidence:       float = 1.0
    width_m:          float = 0.0        # optional per-corner width hint
    verification_source: str = "greedy"  # "greedy" | "ai_verified" | "engineer_validated"


@dataclass
class PitLaneBoundary:
    """Describes where the pit lane diverges from and rejoins the racing line.

    entry_station_m / exit_station_m are distances along the centreline where
    the car first crosses the 60 m lateral threshold (entry) and where it
    returns within 60 m (exit).

    Wrap-around: if entry_station_m > exit_station_m the pit lane crosses the
    lap seam (e.g. start/finish is inside the pit complex).  The rendering
    layer handles this case; the values are stored as-is.
    """
    entry_station_m: float
    exit_station_m: float
    entry_progress: float   # 0.0–1.0
    exit_progress: float    # 0.0–1.0


@dataclass
class TrackStationMap:
    """1 metre resolution station map for one track/layout."""
    track_location_id:  str
    layout_id:          str
    lap_length_m:       float
    spacing_m:          float
    stations:           List[StationPoint]
    seeded_corners:     List[SeededCorner]
    start_finish_station: float = 0.0
    default_track_width_m: float = DEFAULT_TRACK_WIDTH_M
    confidence_overall: float   = 0.0
    corners_expected:   int     = 0
    corners_detected:   int     = 0   # from curvature analysis
    extra_curvature_peaks: List[SeededCorner] = field(default_factory=list)  # suppressed peaks beyond corners_expected
    seed_corner_positions_available: bool    = False   # True when corner_definitions were used to select peaks
    source:             str     = "reference_path"
    created_at:         str     = ""
    schema:             str     = STATION_MAP_SCHEMA
    pit_lane:           Optional[PitLaneBoundary] = None

    def station_count(self) -> int:
        return len(self.stations)

    def get_station_at(self, station_m: float) -> Optional[StationPoint]:
        """Return the nearest station to station_m (linear scan, O(n))."""
        if not self.stations:
            return None
        return min(self.stations, key=lambda s: abs(s.station_m - station_m))


# ---------------------------------------------------------------------------
# Path resampling helpers
# ---------------------------------------------------------------------------

def _seg_length(p1: tuple, p2: tuple) -> float:
    """3D Euclidean distance between two (x, y, z) tuples."""
    return math.sqrt(
        (p2[0] - p1[0]) ** 2 +
        (p2[1] - p1[1]) ** 2 +
        (p2[2] - p1[2]) ** 2
    )


def resample_path_to_uniform_spacing(
    xyz_points: List[tuple],
    spacing_m: float = DEFAULT_SPACING_M,
) -> List[tuple]:
    """Resample a list of (x, y, z) path points to uniform arc-length spacing.

    Returns a new list of (x, y, z) tuples spaced approximately ``spacing_m``
    apart along the path.  If the input has fewer than 2 points the input is
    returned unchanged.
    """
    if len(xyz_points) < 2:
        return list(xyz_points)

    # Build cumulative distances along original path
    cum: List[float] = [0.0]
    for i in range(1, len(xyz_points)):
        cum.append(cum[-1] + _seg_length(xyz_points[i - 1], xyz_points[i]))

    total = cum[-1]
    if total <= 0.0:
        return list(xyz_points)

    result: List[tuple] = []
    target = 0.0
    j = 0  # index into original path

    while target <= total + 1e-9:
        # Advance j until cum[j+1] >= target
        while j < len(cum) - 2 and cum[j + 1] < target:
            j += 1
        # Interpolate between xyz_points[j] and xyz_points[j+1]
        seg_len = cum[j + 1] - cum[j] if j + 1 < len(cum) else 0.0
        if seg_len < 1e-9:
            result.append(xyz_points[j])
        else:
            t = (target - cum[j]) / seg_len
            x = xyz_points[j][0] + t * (xyz_points[j + 1][0] - xyz_points[j][0])
            y = xyz_points[j][1] + t * (xyz_points[j + 1][1] - xyz_points[j][1])
            z = xyz_points[j][2] + t * (xyz_points[j + 1][2] - xyz_points[j][2])
            result.append((x, y, z))
        target += spacing_m

    return result


# ---------------------------------------------------------------------------
# Heading and curvature computation
# ---------------------------------------------------------------------------

def _compute_heading(stations: List[StationPoint]) -> None:
    """Set heading_rad on each station (in-place) using forward XZ difference."""
    n = len(stations)
    for i in range(n):
        if i < n - 1:
            dx = stations[i + 1].x - stations[i].x
            dz = stations[i + 1].z - stations[i].z
        else:
            dx = stations[i].x - stations[i - 1].x
            dz = stations[i].z - stations[i - 1].z
        stations[i].heading_rad = math.atan2(dx, dz)


def _compute_gradient(stations: List[StationPoint]) -> None:
    """Set gradient (dy/ds) on each station (in-place)."""
    n = len(stations)
    for i in range(n):
        if i < n - 1:
            dy = stations[i + 1].y - stations[i].y
            ds = stations[i + 1].station_m - stations[i].station_m
        else:
            dy = stations[i].y - stations[i - 1].y
            ds = stations[i].station_m - stations[i - 1].station_m
        stations[i].gradient = (dy / ds) if ds > 1e-9 else 0.0


def _angular_diff(a: float, b: float) -> float:
    """Signed angular difference a–b, normalised to [–π, π]."""
    d = a - b
    while d > math.pi:
        d -= 2 * math.pi
    while d < -math.pi:
        d += 2 * math.pi
    return d


def _compute_curvature(
    stations: List[StationPoint],
    ref_points: Optional[List] = None,
) -> None:
    """Set curvature (rad/m) on each station (in-place), then smooth.

    When ref_points (list of ReferencePathPoint with yaw_rate_avg) is provided,
    the XZ heading-difference curvature is blended with yaw-rate curvature by
    taking the maximum of the two magnitudes (preserving XZ sign).
    """
    n = len(stations)
    raw: List[float] = []
    for i in range(n):
        if i == 0:
            dh = _angular_diff(stations[1].heading_rad, stations[0].heading_rad)
            ds = stations[1].station_m - stations[0].station_m
        elif i == n - 1:
            dh = _angular_diff(stations[-1].heading_rad, stations[-2].heading_rad)
            ds = stations[-1].station_m - stations[-2].station_m
        else:
            dh = _angular_diff(stations[i + 1].heading_rad, stations[i - 1].heading_rad)
            ds = stations[i + 1].station_m - stations[i - 1].station_m
        xz_curv = (dh / ds) if ds > 1e-9 else 0.0

        # Yaw-rate blending when reference path is available
        yaw_curv = 0.0
        if ref_points:
            # Find nearest reference point by progress_pct
            st_prog = stations[i].progress_pct / 100.0
            ref_pt = min(ref_points, key=lambda p: abs(p.lap_progress - st_prog))
            yaw_rate = getattr(ref_pt, "yaw_rate_avg", None)
            speed_kph = getattr(ref_pt, "speed_kph_avg", None) or 0.0
            speed_ms = speed_kph / 3.6
            if yaw_rate is not None and speed_ms >= 2.78:
                yaw_curv = min(abs(yaw_rate / speed_ms), 0.5)

        blended = max(abs(xz_curv), yaw_curv)
        raw.append(blended if xz_curv >= 0 else -blended)

    # Rolling average smoothing
    w = _CURVATURE_SMOOTH_WINDOW
    smoothed: List[float] = []
    for i in range(n):
        lo = max(0, i - w // 2)
        hi = min(n, i + w // 2 + 1)
        smoothed.append(sum(raw[lo:hi]) / (hi - lo))

    for i, s in enumerate(stations):
        s.curvature = smoothed[i]


# ---------------------------------------------------------------------------
# Corner detection from curvature
# ---------------------------------------------------------------------------

def _find_curvature_peaks(
    stations: List[StationPoint],
    min_separation_m: float = _CORNER_MIN_SEPARATION_M,
) -> List[int]:
    """Return indices of local |curvature| maxima (apex candidates).

    Uses iterative suppression: pick the highest remaining peak, then
    suppress all peaks within ``min_separation_m`` of it.
    """
    n = len(stations)
    abs_curv = [abs(s.curvature) for s in stations]

    # Collect raw local maxima (higher than both neighbours)
    candidates: List[tuple] = []  # (abs_curv, idx)
    for i in range(1, n - 1):
        if abs_curv[i] >= abs_curv[i - 1] and abs_curv[i] >= abs_curv[i + 1]:
            candidates.append((abs_curv[i], i))

    # Iterative suppression by minimum separation
    candidates.sort(reverse=True)
    selected: List[int] = []
    used = set()
    for _, idx in candidates:
        if idx in used:
            continue
        selected.append(idx)
        # Suppress neighbouring candidates within min_separation_m
        for _, other_idx in candidates:
            dist = abs(stations[idx].station_m - stations[other_idx].station_m)
            if dist < min_separation_m:
                used.add(other_idx)

    # Sort by station_m order
    selected.sort(key=lambda i: stations[i].station_m)
    return selected


def _detect_corners(
    stations: List[StationPoint],
    corners_expected: int,
    threshold: float = _MIN_CURVATURE_THRESHOLD,
) -> Tuple[List[SeededCorner], List[SeededCorner]]:
    """Detect corners from curvature.

    Returns (official_corners, extra_curvature_peaks):
    - official_corners: exactly corners_expected corners (detected + placeholders)
    - extra_curvature_peaks: real curvature peaks suppressed because corners_expected
      was already satisfied (DEF-17P-UAT-001/005 — never become official turns)
    """
    if not stations:
        return [], []

    peak_indices = _find_curvature_peaks(stations)

    # Apply curvature threshold
    detected_indices = [
        i for i in peak_indices
        if abs(stations[i].curvature) >= threshold
    ]

    extra_indices: List[int] = []

    if corners_expected > 0 and len(detected_indices) > corners_expected:
        # Cap to the N strongest peaks — surplus peaks are non-official extras
        by_mag = sorted(detected_indices, key=lambda i: abs(stations[i].curvature), reverse=True)
        extra_indices    = sorted(by_mag[corners_expected:])
        detected_indices = sorted(by_mag[:corners_expected])
    elif len(detected_indices) < corners_expected and peak_indices:
        # Threshold too strict — relax and take the top N
        by_mag = sorted(peak_indices, key=lambda i: abs(stations[i].curvature), reverse=True)
        detected_indices = sorted(by_mag[:corners_expected])

    total_m = stations[-1].station_m if stations else 0.0

    detected_corners: List[SeededCorner] = []
    for rank, idx in enumerate(detected_indices, start=1):
        s = stations[idx]
        detected_corners.append(SeededCorner(
            corner_id        = f"T{rank}",
            display_name     = f"T{rank}",
            approx_station_m = s.station_m,
            approx_progress  = s.station_m / total_m if total_m > 0 else 0.0,
            is_seeded_placeholder = False,
            confidence       = min(1.0, abs(s.curvature) / 0.05),
        ))

    # Fill missing corners with evenly distributed placeholders
    if corners_expected > 0 and len(detected_corners) < corners_expected:
        needed = corners_expected - len(detected_corners)
        # Place placeholders in the largest gaps between existing corners
        # (and between 0 and the first, and last and total_m)
        existing_stations = [0.0] + [c.approx_station_m for c in detected_corners] + [total_m]
        existing_stations.sort()
        gaps = []
        for i in range(len(existing_stations) - 1):
            gap_size = existing_stations[i + 1] - existing_stations[i]
            gaps.append((gap_size, existing_stations[i], existing_stations[i + 1]))
        gaps.sort(reverse=True)  # largest gaps first

        for _, gap_start, gap_end in gaps[:needed]:
            mid = (gap_start + gap_end) / 2.0
            placeholder = SeededCorner(
                corner_id        = "?",   # numbered below
                display_name     = "?",
                approx_station_m = mid,
                approx_progress  = mid / total_m if total_m > 0 else 0.0,
                is_seeded_placeholder = True,
                confidence       = 0.2,
            )
            detected_corners.append(placeholder)

        # Sort and re-number all corners by station_m
        detected_corners.sort(key=lambda c: c.approx_station_m)
        for rank, c in enumerate(detected_corners, start=1):
            c.corner_id    = f"T{rank}"
            c.display_name = f"T{rank}"

    # Build extra peaks list — real curvature peaks suppressed beyond corners_expected
    extra_peaks: List[SeededCorner] = []
    for rank, idx in enumerate(extra_indices, start=1):
        s = stations[idx]
        extra_peaks.append(SeededCorner(
            corner_id        = f"XP{rank}",
            display_name     = f"XP{rank}",
            approx_station_m = s.station_m,
            approx_progress  = s.station_m / total_m if total_m > 0 else 0.0,
            is_seeded_placeholder = False,
            confidence       = min(1.0, abs(s.curvature) / 0.05),
        ))

    return detected_corners, extra_peaks


# ---------------------------------------------------------------------------
# Corner phase assignment
# ---------------------------------------------------------------------------

_APEX_WINDOW_M: float   = 40.0    # ±40 m around apex → apex region
_EXIT_WINDOW_M: float   = 100.0   # 40–100 m after apex → exit
_BRAKING_WINDOW_M: float = 100.0  # 100 m before corner start → braking


def _assign_corner_phases(stations: List[StationPoint], corners: List[SeededCorner]) -> None:
    """Label corner_id and corner_phase on each station (in-place)."""
    if not corners:
        # Mark everything straight
        for s in stations:
            s.corner_phase = CornerPhase.STRAIGHT
        return

    # First pass: label everything straight
    for s in stations:
        s.corner_phase = CornerPhase.STRAIGHT

    # Second pass: assign corner windows
    for corner in corners:
        apex_m = corner.approx_station_m
        for s in stations:
            dist = s.station_m - apex_m
            if abs(dist) <= _APEX_WINDOW_M:
                s.corner_id   = corner.corner_id
                s.corner_phase = CornerPhase.APEX
            elif -_EXIT_WINDOW_M - _APEX_WINDOW_M <= dist < -_APEX_WINDOW_M:
                if s.corner_id is None:
                    s.corner_id    = corner.corner_id
                    s.corner_phase = CornerPhase.TURN_IN
            elif _APEX_WINDOW_M < dist <= _EXIT_WINDOW_M + _APEX_WINDOW_M:
                if s.corner_id is None:
                    s.corner_id    = corner.corner_id
                    s.corner_phase = CornerPhase.EXIT
            elif -_BRAKING_WINDOW_M - _APEX_WINDOW_M <= dist < -_EXIT_WINDOW_M - _APEX_WINDOW_M:
                if s.corner_id is None:
                    s.corner_id    = corner.corner_id
                    s.corner_phase = CornerPhase.BRAKING


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_track_station_map(
    ref_path,    # ReferencePath duck-typed object with .points list
    layout_seed=None,   # TrackLayoutSeed duck-typed, optional
    spacing_m: float = DEFAULT_SPACING_M,
) -> TrackStationMap:
    """Build a 1 m station map from a ReferencePath.

    Args:
        ref_path:    ReferencePath (from data.track_calibration) with
                     .track_location_id, .layout_id, .calibration_car_id,
                     .confidence, and .points (list of ReferencePathPoint).
        layout_seed: Optional TrackLayoutSeed for corners_expected and
                     default_track_width_m.
        spacing_m:   Target station spacing (default 1 m).

    Returns:
        TrackStationMap with stations, seeded_corners, headings, curvature,
        corner phases, and default width values applied.
    """
    if not ref_path or not ref_path.points:
        raise ValueError("ref_path must have at least one point")

    # Extract XYZ from reference path points
    xyz = [(p.x, p.y, p.z) for p in ref_path.points]
    lap_m = ref_path.points[-1].distance_along_lap_m if ref_path.points else 0.0

    corners_expected = 0
    default_width    = DEFAULT_TRACK_WIDTH_M
    if layout_seed is not None:
        corners_expected = getattr(layout_seed, "corners_expected", 0) or 0
        lm = getattr(layout_seed, "length_m", None)
        if lm and lm > 0 and (lap_m <= 0 or abs(lm - lap_m) / lm < 0.20):
            lap_m = lm

    # Resample to uniform 1 m spacing
    resampled = resample_path_to_uniform_spacing(xyz, spacing_m)
    total_m   = sum(
        _seg_length(resampled[i], resampled[i + 1])
        for i in range(len(resampled) - 1)
    ) if len(resampled) > 1 else 0.0

    if lap_m <= 0:
        lap_m = total_m

    # Build station points
    stations: List[StationPoint] = []
    running_m = 0.0
    for i, (x, y, z) in enumerate(resampled):
        if i > 0:
            running_m += _seg_length(resampled[i - 1], resampled[i])
        prog = (running_m / lap_m * 100.0) if lap_m > 0 else 0.0
        stations.append(StationPoint(
            station_m    = running_m,
            progress_pct = min(100.0, prog),
            x            = x,
            y            = y,
            z            = z,
            left_width_m  = default_width / 2.0,
            right_width_m = default_width / 2.0,
            width_source  = WidthSource.SEED_DEFAULT,
            confidence    = ref_path.confidence if hasattr(ref_path, "confidence") else 0.5,
            source        = "reference_path",
        ))

    # Compute heading, gradient, curvature
    _compute_heading(stations)
    _compute_gradient(stations)
    _compute_curvature(stations, ref_points=ref_path.points)

    # Seed corner definitions (Group 17Q): per-corner progress windows
    corner_defs = getattr(layout_seed, "corner_definitions", []) or [] if layout_seed else []
    seed_corner_positions_available = bool(corner_defs)

    if seed_corner_positions_available:
        # ── Window-based corner selection (DEF-17Q-001) ───────────────────────
        # Use ALL peaks (after min-separation), then match to seed windows.
        from data.seed_corner_matching import match_peaks_to_seed_windows  # lazy import avoids cycle at module level

        peak_station_indices = _find_curvature_peaks(stations)
        total_m_local = ref_path.points[-1].distance_along_lap_m if ref_path.points else (stations[-1].station_m if stations else 1.0)
        if total_m_local <= 0:
            total_m_local = stations[-1].station_m if stations else 1.0

        peak_progresses = [
            stations[i].station_m / total_m_local * 100.0
            for i in peak_station_indices
        ]
        peak_curvatures = [abs(stations[i].curvature) for i in peak_station_indices]

        official_peak_pos, extra_peak_pos, _ = match_peaks_to_seed_windows(
            peak_progresses,
            peak_curvatures,
            [cd.start_progress_pct for cd in corner_defs],
            [cd.apex_progress_pct  for cd in corner_defs],
            [cd.end_progress_pct   for cd in corner_defs],
            [cd.corner_id          for cd in corner_defs],
        )

        # Build official corners from matched peaks or placeholders
        corners: List[SeededCorner] = []
        for j, (idx_in_peaks, cdef) in enumerate(zip(official_peak_pos, corner_defs)):
            if idx_in_peaks >= 0:
                s = stations[peak_station_indices[idx_in_peaks]]
                corners.append(SeededCorner(
                    corner_id        = cdef.corner_id,
                    display_name     = cdef.display_name or cdef.corner_id,
                    approx_station_m = s.station_m,
                    approx_progress  = s.station_m / total_m_local if total_m_local > 0 else 0.0,
                    is_seeded_placeholder = False,
                    confidence       = min(1.0, abs(s.curvature) / 0.05),
                ))
            else:
                # No peak in window — use seed apex position as placeholder
                apex_station = cdef.apex_progress_pct / 100.0 * total_m_local
                corners.append(SeededCorner(
                    corner_id        = cdef.corner_id,
                    display_name     = cdef.display_name or cdef.corner_id,
                    approx_station_m = apex_station,
                    approx_progress  = cdef.apex_progress_pct / 100.0,
                    is_seeded_placeholder = True,
                    confidence       = 0.2,
                ))

        # Extra peaks: all peaks not claimed by any window
        extra_peaks: List[SeededCorner] = []
        for xp_rank, idx_in_peaks in enumerate(extra_peak_pos, start=1):
            s = stations[peak_station_indices[idx_in_peaks]]
            extra_peaks.append(SeededCorner(
                corner_id        = f"XP{xp_rank}",
                display_name     = f"XP{xp_rank}",
                approx_station_m = s.station_m,
                approx_progress  = s.station_m / total_m_local if total_m_local > 0 else 0.0,
                is_seeded_placeholder = False,
                confidence       = min(1.0, abs(s.curvature) / 0.05),
            ))
    else:
        # ── Curvature-cap approach (Group 17P) ───────────────────────────────
        corners, extra_peaks = _detect_corners(stations, corners_expected)
        # Re-compute approx_progress using corrected lap length from ref_path
        _corrected_denom = ref_path.points[-1].distance_along_lap_m if ref_path.points else 0.0
        if _corrected_denom <= 0:
            _corrected_denom = stations[-1].station_m if stations else 1.0
        for _c in corners + extra_peaks:
            _c.approx_progress = _c.approx_station_m / _corrected_denom if _corrected_denom > 0 else 0.0

    # Assign corner phases
    _assign_corner_phases(stations, corners)

    return TrackStationMap(
        track_location_id  = ref_path.track_location_id,
        layout_id          = ref_path.layout_id,
        lap_length_m       = lap_m,
        spacing_m          = spacing_m,
        stations           = stations,
        seeded_corners     = corners,
        extra_curvature_peaks = extra_peaks,
        seed_corner_positions_available = seed_corner_positions_available,
        start_finish_station = 0.0,
        default_track_width_m = default_width,
        confidence_overall = ref_path.confidence if hasattr(ref_path, "confidence") else 0.5,
        corners_expected   = corners_expected,
        corners_detected   = sum(1 for c in corners if not c.is_seeded_placeholder),
        source             = "reference_path",
        created_at         = datetime.now(timezone.utc).isoformat(),
    )


# ---------------------------------------------------------------------------
# Pit lane boundary detection (Group 21B)
# ---------------------------------------------------------------------------

_PIT_LANE_THRESHOLD_M: float = 60.0   # matches track_map_matching.PIT_DISTANCE_THRESHOLD_M


def _xz_dist_to_nearest_station(x: float, z: float, stations: List[StationPoint]) -> Tuple[float, float]:
    """Return (dist_xz, station_m) of the nearest station to (x, z) in XZ plane."""
    best_dist = float("inf")
    best_station_m = 0.0
    for s in stations:
        d = math.sqrt((x - s.x) ** 2 + (z - s.z) ** 2)
        if d < best_dist:
            best_dist = d
            best_station_m = s.station_m
    return best_dist, best_station_m


def detect_pit_lane_from_pit_laps(
    pit_laps: list,
    station_map: "TrackStationMap",
) -> Optional[PitLaneBoundary]:
    """Detect pit lane entry/exit station positions from pit-in laps.

    For each pit lap, finds where the car first diverges > 60 m from the
    centreline (entry) and where it first returns < 60 m (exit).

    Returns a PitLaneBoundary with the median entry/exit station values across
    all pit laps that yield a valid detection, or None if detection fails.

    Wrap-around: if entry_station_m > exit_station_m the pit crosses the lap
    seam.  Values are stored as-is; the rendering layer handles wrap-around.
    """
    if not pit_laps or not station_map.stations:
        return None

    lap_length_m = station_map.lap_length_m
    if lap_length_m <= 0.0:
        lap_length_m = station_map.stations[-1].station_m if station_map.stations else 1.0

    entry_stations: List[float] = []
    exit_stations: List[float] = []

    for lap in pit_laps:
        samples = getattr(lap, "samples", lap) if not isinstance(lap, list) else lap

        in_pit = False
        entry_m: Optional[float] = None
        exit_m: Optional[float] = None

        for s in samples:
            dist, station_m = _xz_dist_to_nearest_station(s.x, s.z, station_map.stations)

            if not in_pit and dist > _PIT_LANE_THRESHOLD_M:
                in_pit = True
                entry_m = station_m
            elif in_pit and dist <= _PIT_LANE_THRESHOLD_M:
                exit_m = station_m
                break   # first return to track is the pit exit

        if entry_m is not None and exit_m is not None:
            entry_stations.append(entry_m)
            exit_stations.append(exit_m)

    if not entry_stations:
        return None

    # Use median values across all pit laps that yielded a detection
    entry_stations.sort()
    exit_stations.sort()
    mid_e = len(entry_stations) // 2
    mid_x = len(exit_stations) // 2
    avg_entry = entry_stations[mid_e]
    avg_exit  = exit_stations[mid_x]

    return PitLaneBoundary(
        entry_station_m = avg_entry,
        exit_station_m  = avg_exit,
        entry_progress  = avg_entry / lap_length_m,
        exit_progress   = avg_exit  / lap_length_m,
    )


# ---------------------------------------------------------------------------
# JSON persistence
# ---------------------------------------------------------------------------

def station_map_filename(track_location_id: str, layout_id: str) -> str:
    return f"{track_location_id}__{layout_id}.station_map.json"


def export_station_map_json(
    station_map: TrackStationMap,
    output_dir: Optional[Path] = None,
) -> Path:
    """Write station map to JSON and return the path."""
    out_dir = Path(output_dir) if output_dir else STATION_MODELS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    fname   = station_map_filename(station_map.track_location_id, station_map.layout_id)
    path    = out_dir / fname

    payload = {
        "schema":             station_map.schema,
        "track_location_id":  station_map.track_location_id,
        "layout_id":          station_map.layout_id,
        "lap_length_m":       station_map.lap_length_m,
        "spacing_m":          station_map.spacing_m,
        "start_finish_station": station_map.start_finish_station,
        "default_track_width_m": station_map.default_track_width_m,
        "confidence_overall": station_map.confidence_overall,
        "corners_expected":   station_map.corners_expected,
        "corners_detected":   station_map.corners_detected,
        "seed_corner_positions_available": station_map.seed_corner_positions_available,
        "source":             station_map.source,
        "created_at":         station_map.created_at,
        "seeded_corners":         [asdict(c) for c in station_map.seeded_corners],
        "extra_curvature_peaks":  [asdict(c) for c in station_map.extra_curvature_peaks],
        "stations":               [asdict(s) for s in station_map.stations],
        "pit_lane": (
            {
                "entry_station_m": station_map.pit_lane.entry_station_m,
                "exit_station_m":  station_map.pit_lane.exit_station_m,
                "entry_progress":  station_map.pit_lane.entry_progress,
                "exit_progress":   station_map.pit_lane.exit_progress,
            }
            if station_map.pit_lane is not None else None
        ),
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    return path


def import_station_map_json(json_path: Path) -> TrackStationMap:
    """Load a station map from JSON.  Raises FileNotFoundError or ValueError."""
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"Station map not found: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if data.get("schema") != STATION_MAP_SCHEMA:
        raise ValueError(
            f"Unsupported station map schema: {data.get('schema')!r}"
        )
    def _load_seeded_corner(c: dict) -> SeededCorner:
        c = dict(c)
        c.setdefault("verification_source", "greedy")
        return SeededCorner(**c)

    corners = [
        _load_seeded_corner(c) for c in data.get("seeded_corners", [])
    ]
    extra_peaks = [
        _load_seeded_corner(c) for c in data.get("extra_curvature_peaks", [])
    ]
    stations = [
        StationPoint(**s) for s in data.get("stations", [])
    ]
    pit_lane_raw = data.get("pit_lane")
    pit_lane_obj: Optional[PitLaneBoundary] = None
    if pit_lane_raw is not None:
        try:
            pit_lane_obj = PitLaneBoundary(
                entry_station_m = float(pit_lane_raw["entry_station_m"]),
                exit_station_m  = float(pit_lane_raw["exit_station_m"]),
                entry_progress  = float(pit_lane_raw["entry_progress"]),
                exit_progress   = float(pit_lane_raw["exit_progress"]),
            )
        except (KeyError, TypeError, ValueError):
            pit_lane_obj = None

    return TrackStationMap(
        track_location_id     = data["track_location_id"],
        layout_id             = data["layout_id"],
        lap_length_m          = data["lap_length_m"],
        spacing_m             = data.get("spacing_m", DEFAULT_SPACING_M),
        stations              = stations,
        seeded_corners        = corners,
        extra_curvature_peaks = extra_peaks,
        start_finish_station  = data.get("start_finish_station", 0.0),
        default_track_width_m = data.get("default_track_width_m", DEFAULT_TRACK_WIDTH_M),
        confidence_overall    = data.get("confidence_overall", 0.0),
        corners_expected      = data.get("corners_expected", 0),
        corners_detected      = data.get("corners_detected", 0),
        seed_corner_positions_available = bool(data.get("seed_corner_positions_available", False)),
        source                = data.get("source", "reference_path"),
        created_at            = data.get("created_at", ""),
        schema                = data.get("schema", STATION_MAP_SCHEMA),
        pit_lane              = pit_lane_obj,
    )


def find_station_map_path(
    track_location_id: str,
    layout_id: str,
    base_dir: Optional[Path] = None,
) -> Optional[Path]:
    """Return the path to an existing station map file, or None."""
    d    = Path(base_dir) if base_dir else STATION_MODELS_DIR
    fname = station_map_filename(track_location_id, layout_id)
    p    = d / fname
    return p if p.exists() else None
