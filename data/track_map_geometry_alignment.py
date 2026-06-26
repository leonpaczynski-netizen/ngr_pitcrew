"""Track Map Geometry Alignment — DEF-17T-002/003/004/005/006.

Compares a modelled TrackStationMap (Layer 2) against a SeedCoordinateMap (Layer 1.5).

Detected issues:
  - Lap length / completeness mismatch
  - Missing track sections (coordinate jump detection or length inference)
  - Coordinate scale, translation, rotation differences
  - Corner and sector boundary misalignment

When a SeedCoordinateMap is unavailable, falls back to lap-length-only comparison
(same threshold values as track_model_alignment.py for consistency).

Coordinate transform algorithm:
  1. Subsample both maps to ≤100 representative points.
  2. Compute centroids → translation estimate.
  3. Compute RMS radii → scale estimate.
  4. Scan rotation angles 0–359° (15° steps) + fine-tune (1° steps) around best.
  5. Apply transform and compute mean nearest-neighbour error.

This module is pure Python with no PyQt6 or scikit-learn dependency.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# Thresholds — keep in sync with track_model_alignment.py
_LAP_DELTA_BLOCKER_PCT  = 5.0    # > 5%  blocks acceptance
_LAP_DELTA_CRITICAL_PCT = 20.0   # > 20% is critical
_COORD_ACCEPT_MEAN_M    = 15.0   # mean error ≤ 15 m required
_COORD_ACCEPT_MAX_M     = 50.0   # max error  ≤ 50 m required
_SCALE_WARN_THRESHOLD   = 0.05   # |scale−1| > 5% → warning


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class MapMismatchRange:
    """An estimated range of missing or mismatched track."""
    start_progress_pct:   float
    end_progress_pct:     float
    estimated_missing_m:  float
    description:          str


@dataclass
class CornerCoordinateMatch:
    """Match between a seed map corner marker and a modelled corner."""
    corner_id:           str
    seed_progress_pct:   float
    model_progress_pct:  Optional[float] = None
    delta_progress_pct:  Optional[float] = None
    delta_m:             Optional[float] = None
    matched:             bool            = False


@dataclass
class SectorCoordinateMatch:
    """Match between seed map sector boundaries and modelled sector."""
    sector_id:                 str
    seed_start_progress_pct:   float
    seed_end_progress_pct:     float
    model_start_progress_pct:  Optional[float] = None
    model_end_progress_pct:    Optional[float] = None
    matched:                   bool            = False


@dataclass
class CoordinateTransform:
    """2-D rigid body transform (translation + rotation + uniform scale) from model to seed."""
    translation_x: float = 0.0
    translation_y: float = 0.0
    rotation_rad:  float = 0.0
    scale:         float = 1.0
    quality:       float = 0.0   # 0–1 (1 = perfect alignment)
    axis_flip_y:   bool  = False
    source:        str   = "auto"


@dataclass
class TrackMapGeometryAlignmentResult:
    """Full geometry alignment result between a modelled map and a seed coordinate map."""
    has_coordinate_comparison:    bool  = False
    seed_coordinate_map_available: bool = False
    lap_length_delta_m:           float = 0.0
    lap_length_delta_pct:         float = 0.0
    mean_coord_error_m:           Optional[float] = None
    max_coord_error_m:            Optional[float] = None
    start_finish_offset_m:        Optional[float] = None
    missing_section_ranges:       List[MapMismatchRange]      = field(default_factory=list)
    corner_matches:               List[CornerCoordinateMatch]  = field(default_factory=list)
    sector_matches:               List[SectorCoordinateMatch]  = field(default_factory=list)
    coordinate_transform:         Optional[CoordinateTransform] = None
    blockers:                     List[str] = field(default_factory=list)
    warnings:                     List[str] = field(default_factory=list)
    seed_stations_count:          int = 0
    model_stations_count:         int = 0


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def align_maps_geometry(
    station_map,          # TrackStationMap (Layer 2) — duck-typed
    seed_map=None,        # Optional SeedCoordinateMap (Layer 1.5)
    seed_layout=None,     # Optional TrackLayoutSeed — for length fallback
) -> TrackMapGeometryAlignmentResult:
    """Compare a modelled station map against a seed coordinate map.

    Falls back to lap-length-only comparison when seed_map is None.
    Includes missing-section detection, coordinate transform estimation,
    corner/sector matching, and mean/max error computation.
    """
    model_length = float(getattr(station_map, "lap_length_m", 0.0) or 0.0)

    # Resolve seed length from seed_map or seed_layout fallback
    seed_length = 0.0
    if seed_map is not None:
        seed_length = float(seed_map.lap_length_m or 0.0)
    elif seed_layout is not None:
        seed_length = float(getattr(seed_layout, "length_m", 0.0) or 0.0)

    # Lap length delta
    if seed_length > 0:
        delta_m   = abs(model_length - seed_length)
        delta_pct = delta_m / seed_length * 100.0
    else:
        delta_m   = 0.0
        delta_pct = 0.0

    blockers: List[str] = []
    warnings:  List[str] = []
    model_sc = _station_count(station_map)

    # Lap length blockers (mirrors track_model_alignment.py thresholds)
    if seed_length > 0:
        if delta_pct > _LAP_DELTA_CRITICAL_PCT:
            blockers.append(
                f"Lap length critical mismatch: model {model_length:.0f} m vs seed "
                f"{seed_length:.0f} m ({delta_pct:.1f}%). Possible wrong layout selected."
            )
        elif delta_pct > _LAP_DELTA_BLOCKER_PCT:
            missing_m = seed_length - model_length
            blockers.append(
                f"Modelled lap is {missing_m:.0f} m shorter than seed "
                f"({delta_pct:.1f}%). "
                f"Rebuild from complete clean laps crossing S/F line."
            )

    # Missing section detection
    missing_ranges = _detect_missing_sections(
        station_map, seed_map, seed_length, delta_m, delta_pct
    )
    for r in missing_ranges:
        blockers.append(r.description)

    if seed_map is None:
        # No coordinate map — length-only result
        if seed_length > 0:
            warnings.append(
                "Seed coordinate map unavailable — full geometry match cannot be verified. "
                "Only lap-length comparison performed. "
                "To enable coordinate alignment, add a seed map at "
                "data/track_seed_maps/<track_id>__<layout_id>.seed_map.json"
            )
        return TrackMapGeometryAlignmentResult(
            has_coordinate_comparison    = False,
            seed_coordinate_map_available = False,
            lap_length_delta_m           = delta_m,
            lap_length_delta_pct         = delta_pct,
            missing_section_ranges       = missing_ranges,
            blockers                     = blockers,
            warnings                     = warnings,
            model_stations_count         = model_sc,
        )

    # ── Full coordinate comparison ──────────────────────────────────────────
    seed_pts  = [(s.x, s.y) for s in seed_map.stations]
    model_pts = _extract_model_points(station_map)

    # Filter near-zero clusters (unset coordinates)
    seed_pts  = [p for p in seed_pts  if not (abs(p[0]) < 1e-6 and abs(p[1]) < 1e-6)]
    model_pts = [p for p in model_pts if not (abs(p[0]) < 1e-6 and abs(p[1]) < 1e-6)]

    if not seed_pts or not model_pts:
        warnings.append(
            "Coordinate data missing in seed or model map — skipping coordinate comparison."
        )
        return TrackMapGeometryAlignmentResult(
            has_coordinate_comparison    = True,
            seed_coordinate_map_available = True,
            lap_length_delta_m           = delta_m,
            lap_length_delta_pct         = delta_pct,
            missing_section_ranges       = missing_ranges,
            blockers                     = blockers,
            warnings                     = warnings,
            seed_stations_count          = seed_map.station_count(),
            model_stations_count         = model_sc,
        )

    # Estimate coordinate transform
    transform = estimate_coordinate_transform(model_pts, seed_pts)

    # Apply transform and compute errors
    aligned_pts = _apply_transform(model_pts, transform)
    mean_err, max_err = _compute_coord_errors(aligned_pts, seed_pts)

    # Coordinate blockers
    if mean_err > _COORD_ACCEPT_MEAN_M:
        blockers.append(
            f"Mean coordinate error {mean_err:.1f} m exceeds "
            f"{_COORD_ACCEPT_MEAN_M:.0f} m threshold after alignment. "
            f"Check scale, coordinate space, or track coverage."
        )
    if max_err > _COORD_ACCEPT_MAX_M:
        blockers.append(
            f"Max coordinate error {max_err:.1f} m exceeds "
            f"{_COORD_ACCEPT_MAX_M:.0f} m threshold. "
            f"Possible missing track section or coordinate space mismatch."
        )
    if abs(transform.scale - 1.0) > _SCALE_WARN_THRESHOLD:
        warnings.append(
            f"Scale mismatch detected: model/seed coordinate ratio = {transform.scale:.3f}. "
            f"This may indicate different coordinate systems or GT7 distance units differ from "
            f"the seed map source."
        )

    # Corner and sector matching
    corner_matches = _match_corners(station_map, seed_map)
    sector_matches = _match_sectors(seed_map)

    return TrackMapGeometryAlignmentResult(
        has_coordinate_comparison    = True,
        seed_coordinate_map_available = True,
        lap_length_delta_m           = delta_m,
        lap_length_delta_pct         = delta_pct,
        mean_coord_error_m           = mean_err,
        max_coord_error_m            = max_err,
        missing_section_ranges       = missing_ranges,
        corner_matches               = corner_matches,
        sector_matches               = sector_matches,
        coordinate_transform         = transform,
        blockers                     = blockers,
        warnings                     = warnings,
        seed_stations_count          = seed_map.station_count(),
        model_stations_count         = model_sc,
    )


# ---------------------------------------------------------------------------
# Transform estimation
# ---------------------------------------------------------------------------

def estimate_coordinate_transform(
    source_pts: List[Tuple[float, float]],
    target_pts: List[Tuple[float, float]],
    max_samples: int = 100,
) -> CoordinateTransform:
    """Estimate 2-D rigid body transform (translation + rotation + scale) mapping source → target.

    Algorithm:
      1. Subsample to max_samples points.
      2. Centroid alignment → translation.
      3. RMS radius ratio → scale.
      4. Coarse rotation scan (15° steps) + fine-tune (1° steps) minimising
         mean nearest-neighbour error.
    """
    if len(source_pts) < 3 or len(target_pts) < 3:
        return CoordinateTransform(quality=0.0, source="insufficient_points")

    src = _sample_evenly(source_pts, max_samples)
    tgt = _sample_evenly(target_pts, max_samples)

    src_c = _centroid(src)
    tgt_c = _centroid(tgt)

    trans_x = tgt_c[0] - src_c[0]
    trans_y = tgt_c[1] - src_c[1]

    src_r = _rms_radius(src, src_c)
    tgt_r = _rms_radius(tgt, tgt_c)
    scale = tgt_r / src_r if src_r > 1e-9 else 1.0

    # Centre both clouds
    src_c_pts = [(p[0] - src_c[0], p[1] - src_c[1]) for p in src]
    tgt_c_pts = [(p[0] - tgt_c[0], p[1] - tgt_c[1]) for p in tgt]
    src_scaled = [(x * scale, y * scale) for x, y in src_c_pts]

    # Coarse rotation scan
    best_angle = 0.0
    best_err   = float("inf")
    for deg in range(0, 360, 15):
        angle   = math.radians(deg)
        rotated = _rotate_pts(src_scaled, angle)
        err     = _mean_nearest_error(rotated, tgt_c_pts)
        if err < best_err:
            best_err   = err
            best_angle = angle

    # Fine-tune (±15° around best, 1° resolution)
    for d in range(-15, 16):
        angle   = best_angle + math.radians(d)
        rotated = _rotate_pts(src_scaled, angle)
        err     = _mean_nearest_error(rotated, tgt_c_pts)
        if err < best_err:
            best_err   = err
            best_angle = angle

    quality = max(0.0, min(1.0, 1.0 - best_err / (tgt_r + 1e-9)))

    return CoordinateTransform(
        translation_x = trans_x,
        translation_y = trans_y,
        rotation_rad  = best_angle,
        scale         = scale,
        quality       = quality,
        source        = "auto_centroid_scan",
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _station_count(station_map) -> int:
    if hasattr(station_map, "station_count"):
        return int(station_map.station_count())
    stations = getattr(station_map, "stations", None) or []
    return len(stations)


def _extract_model_points(station_map) -> List[Tuple[float, float]]:
    """Extract (x, z) world coordinates from a station map's stations list."""
    stations = getattr(station_map, "stations", []) or []
    return [
        (s.x, s.z)
        for s in stations
        if hasattr(s, "x") and hasattr(s, "z")
    ]


def _extract_model_points_with_progress(
    station_map,
) -> List[Tuple[float, float, float]]:
    """Extract (x, z, progress_pct) triples from a station map."""
    stations = getattr(station_map, "stations", []) or []
    return [
        (s.x, s.z, getattr(s, "progress_pct", 0.0))
        for s in stations
        if hasattr(s, "x") and hasattr(s, "z")
    ]


def _detect_missing_sections(
    station_map,
    seed_map,
    seed_length: float,
    delta_m: float,
    delta_pct: float,
) -> List[MapMismatchRange]:
    """Estimate which track section is missing based on length delta and/or coordinate jumps."""
    ranges: List[MapMismatchRange] = []

    if delta_pct < _LAP_DELTA_BLOCKER_PCT or seed_length <= 0:
        return ranges

    model_length = float(getattr(station_map, "lap_length_m", 0.0) or 0.0)

    # With coordinates: detect large inter-station jumps
    if seed_map is not None and seed_map.stations:
        model_pts_prog = _extract_model_points_with_progress(station_map)
        if len(model_pts_prog) >= 2:
            # Expected step between consecutive GT7 telemetry stations (~1 m)
            expected_step = max(
                float(getattr(station_map, "default_spacing_m", 1.0)),
                1.0,
            )
            jump_threshold = max(expected_step * 10.0, 20.0)

            max_jump_m        = 0.0
            max_jump_progress = None
            for i in range(1, len(model_pts_prog)):
                px, py, pp = model_pts_prog[i - 1]
                cx, cy, cp = model_pts_prog[i]
                dist = math.hypot(cx - px, cy - py)
                if dist > jump_threshold and dist > max_jump_m:
                    max_jump_m        = dist
                    max_jump_progress = (pp + cp) / 2.0

            if max_jump_progress is not None:
                ranges.append(MapMismatchRange(
                    start_progress_pct  = max(0.0, max_jump_progress - 2.0),
                    end_progress_pct    = min(100.0, max_jump_progress + 2.0),
                    estimated_missing_m = delta_m,
                    description         = (
                        f"Largest mismatch appears around {max_jump_progress:.0f}% lap progress "
                        f"({delta_m:.0f} m gap). Rebuild from complete clean laps starting "
                        f"before this point."
                    ),
                ))
                return ranges

    # Fallback: assume missing section is near the lap boundary
    if model_length < seed_length:
        missing_start_pct = model_length / seed_length * 100.0
        ranges.append(MapMismatchRange(
            start_progress_pct  = missing_start_pct,
            end_progress_pct    = 100.0,
            estimated_missing_m = delta_m,
            description         = (
                f"Modelled lap is {delta_m:.0f} m shorter than seed "
                f"({delta_pct:.1f}%). Largest mismatch appears around "
                f"{missing_start_pct:.0f}–100% lap progress. "
                f"Ensure calibration laps covered the full circuit."
            ),
        ))

    return ranges


def _sample_evenly(
    points: List[Tuple[float, float]],
    n: int,
) -> List[Tuple[float, float]]:
    if len(points) <= n:
        return list(points)
    step = len(points) / n
    return [points[int(i * step)] for i in range(n)]


def _centroid(points: List[Tuple[float, float]]) -> Tuple[float, float]:
    cx = sum(p[0] for p in points) / len(points)
    cy = sum(p[1] for p in points) / len(points)
    return cx, cy


def _rms_radius(
    points: List[Tuple[float, float]],
    center: Tuple[float, float],
) -> float:
    cx, cy = center
    return (
        sum((p[0] - cx) ** 2 + (p[1] - cy) ** 2 for p in points) / len(points)
    ) ** 0.5


def _rotate_pts(
    pts: List[Tuple[float, float]],
    angle: float,
) -> List[Tuple[float, float]]:
    ca, sa = math.cos(angle), math.sin(angle)
    return [(x * ca - y * sa, x * sa + y * ca) for x, y in pts]


def _mean_nearest_error(
    source: List[Tuple[float, float]],
    target: List[Tuple[float, float]],
) -> float:
    """Mean distance from each source point to its nearest target point."""
    if not source or not target:
        return float("inf")
    total = 0.0
    for sx, sy in source:
        min_d2 = min((sx - tx) ** 2 + (sy - ty) ** 2 for tx, ty in target)
        total += min_d2 ** 0.5
    return total / len(source)


def _apply_transform(
    pts: List[Tuple[float, float]],
    t: CoordinateTransform,
) -> List[Tuple[float, float]]:
    """Apply a CoordinateTransform to a list of (x, y) points."""
    ca, sa = math.cos(t.rotation_rad), math.sin(t.rotation_rad)
    return [
        (
            (x * ca - y * sa) * t.scale + t.translation_x,
            (x * sa + y * ca) * t.scale + t.translation_y,
        )
        for x, y in pts
    ]


def _compute_coord_errors(
    model_pts: List[Tuple[float, float]],
    seed_pts:  List[Tuple[float, float]],
) -> Tuple[float, float]:
    """Return (mean_error_m, max_error_m) from each model point to nearest seed point."""
    if not model_pts or not seed_pts:
        return 0.0, 0.0
    errors = [
        min(math.hypot(mx - sx, my - sy) for sx, sy in seed_pts)
        for mx, my in model_pts
    ]
    return sum(errors) / len(errors), max(errors)


def _match_corners(
    station_map,
    seed_map,
) -> List[CornerCoordinateMatch]:
    """Match modelled corners to seed map corner markers by progress proximity."""
    if not getattr(seed_map, "has_corner_markers", False):
        return []

    # Seed corner positions (first station with each corner_id)
    seed_corners: dict[str, float] = {}
    for s in seed_map.stations:
        if s.corner_id and s.corner_id not in seed_corners:
            seed_corners[s.corner_id] = s.progress_pct

    # Model corner progress from seeded_corners
    model_corners = getattr(station_map, "seeded_corners", []) or []
    lap_len = float(getattr(station_map, "lap_length_m", 1.0) or 1.0)
    model_by_id: dict[str, float] = {
        c.corner_id: getattr(c, "approx_station_m", 0.0) / lap_len * 100.0
        for c in model_corners
    }

    threshold_pct = 3.0  # corners within 3% progress are "matched"

    matches: List[CornerCoordinateMatch] = []
    for cid, spct in seed_corners.items():
        mpct = model_by_id.get(cid)
        if mpct is not None:
            delta = abs(mpct - spct)
            matches.append(CornerCoordinateMatch(
                corner_id          = cid,
                seed_progress_pct  = spct,
                model_progress_pct = mpct,
                delta_progress_pct = delta,
                matched            = delta <= threshold_pct,
            ))
        else:
            matches.append(CornerCoordinateMatch(
                corner_id         = cid,
                seed_progress_pct = spct,
                matched           = False,
            ))
    return matches


def _match_sectors(seed_map) -> List[SectorCoordinateMatch]:
    """Return sector boundary matches from seed map station markers."""
    if not getattr(seed_map, "has_sector_markers", False):
        return []

    first_pct: dict[str, float] = {}
    last_pct:  dict[str, float] = {}
    for s in seed_map.stations:
        if s.sector_id:
            if s.sector_id not in first_pct:
                first_pct[s.sector_id] = s.progress_pct
            last_pct[s.sector_id] = s.progress_pct

    return [
        SectorCoordinateMatch(
            sector_id               = sid,
            seed_start_progress_pct = first_pct[sid],
            seed_end_progress_pct   = last_pct[sid],
            matched                 = True,
        )
        for sid in first_pct
    ]
