"""Live Current Segment Resolver — map a real-time telemetry position to a reviewed track segment.

Pure Python, no PyQt6.

Architecture boundary:
  - Reads: data.track_model_resolver (resolve_best_track_model)
  - Reads: data.track_calibration (reference path for XYZ→lap_progress)
  - Reads: data.track_segment_review (ReviewedTrackSegment, SegmentReviewStatus)
  - Does NOT write files
  - Does NOT re-detect segments
  - Does NOT invent corner names when unresolved
  - Does NOT invent lap_progress when only XYZ is present and no reference path is loaded

Design rules:
  - Matching priority: segment_id exact → lap_progress range → distance_along_lap_m range
    → XYZ nearest via reference path → nearest segment by midpoint → unresolved
  - Rejected segments are excluded from matching
  - NEEDS_MORE_LAPS and UNREVIEWED segments are included with confidence degradation
  - Reviewed-but-not-AI-ready models are allowed but flagged in warnings
  - All exceptions caught internally — never propagate to callers
  - Seed-only context → status = no_reviewed_model (no invented segment data)

GT7 packet limitations (documented, not worked around):
  - No native lap_progress field in the packet
  - road_distance is absolute track offset, not lap-relative — cannot be used
    as distance_along_lap_m without knowing the lap start offset; conversion deferred
  - XYZ matching via reference path is the primary position method
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class LiveSegmentResolutionConfidence(str, Enum):
    HIGH    = "high"
    MEDIUM  = "medium"
    LOW     = "low"
    UNKNOWN = "unknown"


class LiveSegmentResolutionStatus(str, Enum):
    MATCHED         = "matched"           # reliable segment match
    MATCHED_NEAREST = "matched_nearest"   # fallback to nearest midpoint
    NO_REVIEWED_MODEL  = "no_reviewed_model"   # seed-only or missing → no match possible
    NO_POSITION_DATA   = "no_position_data"    # no lap_progress, no XYZ, no segment_id
    NO_SEGMENT_BOUNDS  = "no_segment_bounds"   # model loaded but zero usable segments
    ERROR              = "error"               # unexpected exception


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class LivePosition:
    """Lightweight position snapshot from a telemetry packet or other source.

    Callers should populate whichever fields are available.  The resolver
    attempts each field in priority order:
      1. segment_id (if already known)
      2. lap_progress (0.0–1.0 if caller has computed it)
      3. distance_along_lap_m (if caller has a lap-relative metre offset)
      4. pos_x / pos_y / pos_z (world coordinates; XYZ matching via reference path)

    Note on road_distance from GT7 packets:
      GT7 ``road_distance`` resets to ~0.0 at the start/finish line each lap and
      increases monotonically along the track surface.  It is stored in
      ``road_distance_m`` but cannot be used as ``distance_along_lap_m`` without a
      ``LapStartOffsetCalibration`` (Group 17L).  With a calibration, callers can
      call ``enrich_position_with_road_distance()`` or pass ``offset_calibration``
      to ``resolve_live_segment()`` to convert road_distance_m automatically.
    """
    lap_progress: Optional[float] = None          # 0.0–1.0 if available
    pos_x: Optional[float] = None
    pos_y: Optional[float] = None
    pos_z: Optional[float] = None
    distance_along_lap_m: Optional[float] = None  # caller-computed, lap-relative
    segment_id: Optional[str] = None              # direct hint if known
    speed_kph: Optional[float] = None             # informational only
    road_distance_m: Optional[float] = None       # raw GT7 road_distance field (Group 17L)


@dataclass
class LiveSegmentResolverConfig:
    """Tuneable parameters for resolve_live_segment()."""
    include_needs_more_laps: bool = True   # include NEEDS_MORE_LAPS with warning
    include_unreviewed: bool = False       # exclude UNREVIEWED by default
    allow_not_ai_ready: bool = True        # match against not-AI-ready models with warning
    max_xyz_match_distance_m: float = 100.0  # discard XYZ match if nearest point > this far


@dataclass
class LiveSegmentMatch:
    """Result of a successful (or partially successful) segment match."""
    track_location_id: str
    layout_id: str
    segment_id: str
    display_name: str
    segment_type: str           # TrackSegmentType.value
    lap_progress: Optional[float]            # position used for the match
    lap_progress_start: float               # segment start
    lap_progress_end: float                 # segment end
    lap_progress_mid: float                 # segment midpoint
    distance_along_lap_m: Optional[float]   # from position if distance-matched
    confidence: LiveSegmentResolutionConfidence
    source: str   # "segment_id" | "lap_progress" | "distance" | "xyz_nearest" | "nearest_midpoint"
    turn_number: Optional[int] = None
    warnings: list[str] = field(default_factory=list)
    previous_segment_id: Optional[str] = None
    previous_segment_display_name: str = ""
    next_segment_id: Optional[str] = None
    next_segment_display_name: str = ""


@dataclass
class LiveSegmentResolverResult:
    """Full output from resolve_live_segment()."""
    track_location_id: str
    layout_id: str
    status: LiveSegmentResolutionStatus
    match: Optional[LiveSegmentMatch] = None
    model_source: str = "missing"      # reflects TrackModelSourceType.value
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Reference path loader
# ---------------------------------------------------------------------------

def _load_reference_path(
    track_location_id: str,
    layout_id: str,
    base_dir: Optional[Path] = None,
):
    """Load reference path for the given track/layout. Returns None on any error."""
    try:
        from data.track_calibration import import_reference_path_json
        from data.track_segment_detection import SEGMENT_MODELS_DIR
        base = base_dir or SEGMENT_MODELS_DIR
        filename = f"{track_location_id}__{layout_id}.reference_path.json"
        path = Path(base) / filename
        if not path.exists():
            return None
        return import_reference_path_json(path)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Position helpers
# ---------------------------------------------------------------------------

def _xyz_to_lap_progress(
    x: float, y: float, z: float,
    ref_path,
    max_match_dist_m: float = 100.0,
) -> tuple[Optional[float], float]:
    """Find the nearest reference path point to (x, y, z) using XZ distance.

    Returns (lap_progress, nearest_distance_m).
    Returns (None, float('inf')) if ref_path is None or has no points.
    Uses XZ distance only (ignores Y / elevation) for robustness against
    elevation differences between the car and the reference path average.
    """
    if ref_path is None or not ref_path.points:
        return None, float("inf")
    best_dist = float("inf")
    best_progress = None
    for pt in ref_path.points:
        dx = pt.x - x
        dz = pt.z - z
        d = math.sqrt(dx * dx + dz * dz)
        if d < best_dist:
            best_dist = d
            best_progress = pt.lap_progress
    if best_dist > max_match_dist_m:
        return None, best_dist
    return best_progress, best_dist


def _distance_to_lap_progress(
    distance_m: float,
    ref_path,
) -> Optional[float]:
    """Convert a lap-relative distance (metres) to lap_progress via reference path."""
    if ref_path is None or not ref_path.points:
        return None
    best_diff = float("inf")
    best_progress = None
    for pt in ref_path.points:
        diff = abs(pt.distance_along_lap_m - distance_m)
        if diff < best_diff:
            best_diff = diff
            best_progress = pt.lap_progress
    return best_progress


# ---------------------------------------------------------------------------
# Segment filtering and sorting
# ---------------------------------------------------------------------------

def _usable_segments(segments: list, config: LiveSegmentResolverConfig) -> list:
    """Return segments suitable for live matching, ordered by lap_progress_mid ascending."""
    try:
        from data.track_segment_review import SegmentReviewStatus
        result = []
        for seg in segments:
            status = seg.review_status
            if status == SegmentReviewStatus.REJECTED:
                continue
            if status == SegmentReviewStatus.UNREVIEWED and not config.include_unreviewed:
                continue
            result.append(seg)
        result.sort(key=lambda s: s.lap_progress_mid)
        return result
    except Exception:
        # If SegmentReviewStatus import fails, return all segments sorted
        try:
            return sorted(segments, key=lambda s: s.lap_progress_mid)
        except Exception:
            return list(segments)


def _find_segment_by_id(segment_id: str, segments: list) -> Optional[object]:
    for seg in segments:
        if seg.segment_id == segment_id:
            return seg
    return None


def _find_segment_by_progress(progress: float, segments: list) -> Optional[object]:
    """Return the first segment whose [start, end] range contains progress."""
    for seg in segments:
        if seg.lap_progress_start <= progress <= seg.lap_progress_end:
            return seg
    return None


def _find_segment_by_distance(distance_m: float, segments: list) -> Optional[object]:
    """Match segment by distance bounds if segments have distance fields (future).

    ReviewedTrackSegment currently stores only lap_progress bounds, not distance
    bounds.  This function is reserved for future use and returns None.
    """
    return None


def _find_nearest_segment(progress: float, segments: list) -> Optional[object]:
    """Return the segment whose midpoint is closest to the given progress."""
    if not segments:
        return None
    return min(segments, key=lambda s: abs(s.lap_progress_mid - progress))


def _prev_next_segments(
    matched_index: int,
    segments: list,
) -> tuple[Optional[object], Optional[object]]:
    """Return (previous_segment, next_segment) with start/finish wraparound.

    segments is assumed sorted by lap_progress_mid ascending.
    """
    n = len(segments)
    if n == 0:
        return None, None
    if n == 1:
        return None, None
    prev_seg = segments[(matched_index - 1) % n]
    next_seg = segments[(matched_index + 1) % n]
    return prev_seg, next_seg


# ---------------------------------------------------------------------------
# Confidence helpers
# ---------------------------------------------------------------------------

def _base_confidence(model_source: str) -> LiveSegmentResolutionConfidence:
    if model_source in ("engineer_validated", "ai_ready"):
        return LiveSegmentResolutionConfidence.HIGH
    if model_source == "reviewed":
        return LiveSegmentResolutionConfidence.MEDIUM
    if model_source == "seed_only":
        return LiveSegmentResolutionConfidence.LOW
    return LiveSegmentResolutionConfidence.UNKNOWN


_CONFIDENCE_ORDER = [
    LiveSegmentResolutionConfidence.UNKNOWN,
    LiveSegmentResolutionConfidence.LOW,
    LiveSegmentResolutionConfidence.MEDIUM,
    LiveSegmentResolutionConfidence.HIGH,
]


def _downgrade_confidence(
    conf: LiveSegmentResolutionConfidence,
    levels: int = 1,
) -> LiveSegmentResolutionConfidence:
    idx = _CONFIDENCE_ORDER.index(conf)
    return _CONFIDENCE_ORDER[max(0, idx - levels)]


def _segment_confidence_adjustment(
    seg,
    base: LiveSegmentResolutionConfidence,
) -> tuple[LiveSegmentResolutionConfidence, list[str]]:
    """Return adjusted confidence and any warnings from segment review status."""
    warnings: list[str] = []
    try:
        from data.track_segment_review import SegmentReviewStatus
        status = seg.review_status
        if status == SegmentReviewStatus.NEEDS_MORE_LAPS:
            base = _downgrade_confidence(base)
            warnings.append(
                f"Segment '{seg.display_name}' needs more calibration laps — confidence reduced."
            )
        elif status == SegmentReviewStatus.UNREVIEWED:
            base = _downgrade_confidence(base, 2)
            warnings.append(
                f"Segment '{seg.display_name}' is unreviewed — confidence significantly reduced."
            )
    except Exception:
        pass
    return base, warnings


# ---------------------------------------------------------------------------
# Model source label
# ---------------------------------------------------------------------------

def _model_source_label(resolver_result) -> str:
    """Extract a short model source label from TrackModelResolverResult."""
    try:
        from data.track_model_resolver import TrackModelSourceType
        rm = resolver_result.resolved_model
        if rm is None:
            return "missing"
        source = rm.source_type
        if source == TrackModelSourceType.ENGINEER_VALIDATED_MODEL:
            return "engineer_validated"
        if source == TrackModelSourceType.AI_READY_REVIEWED_MODEL:
            return "ai_ready"
        if source == TrackModelSourceType.REVIEWED_MODEL:
            return "reviewed"
        if source == TrackModelSourceType.SEED_ONLY:
            return "seed_only"
        return "missing"
    except Exception:
        return "missing"


# ---------------------------------------------------------------------------
# Main resolver
# ---------------------------------------------------------------------------

def resolve_live_segment(
    track_location_id: str,
    layout_id: str,
    position: Optional[LivePosition] = None,
    base_dir: Optional[Path] = None,
    config: Optional[LiveSegmentResolverConfig] = None,
    offset_calibration=None,  # Optional[LapStartOffsetCalibration] — Group 17L
) -> LiveSegmentResolverResult:
    """Resolve the current live position to the best matching reviewed track segment.

    Never raises.  All errors are captured in result.errors / result.warnings.
    Returns LiveSegmentResolverResult with status indicating why matching
    succeeded or failed.

    Matching priority:
      1. position.segment_id exact match (if supplied and exists in model)
      2. position.lap_progress within segment [start, end]
      3. position.road_distance_m + offset_calibration → distance_along_lap_m (Group 17L)
      4. position.distance_along_lap_m (caller-supplied, lap-relative)
      5. XYZ (pos_x/y/z) nearest reference path point → lap_progress → segment range
      6. Nearest segment by lap_progress_mid (fallback)
      7. Unresolved

    offset_calibration (LapStartOffsetCalibration): if provided, road_distance_m from
      the position is converted to distance_along_lap_m and used for Priority 3 matching.
      When absent, road_distance_m is ignored (no mapping attempted).
    """
    if config is None:
        config = LiveSegmentResolverConfig()

    result_warnings: list[str] = []
    result_errors: list[str] = []
    model_source = "missing"
    segments: list = []
    not_ai_ready = False

    # ── Step 1: Resolve model ──────────────────────────────────────────────
    try:
        from data.track_model_resolver import (
            resolve_best_track_model,
            TrackModelSourceType,
            TrackModelResolutionStatus,
        )
        resolver_result = resolve_best_track_model(track_location_id, layout_id, base_dir)
        model_source = _model_source_label(resolver_result)
        rm = resolver_result.resolved_model

        if model_source in ("missing", "seed_only") or rm is None:
            return LiveSegmentResolverResult(
                track_location_id=track_location_id,
                layout_id=layout_id,
                status=LiveSegmentResolutionStatus.NO_REVIEWED_MODEL,
                model_source=model_source,
                warnings=["No reviewed track model available — cannot resolve live segment."],
            )

        if model_source == "reviewed" and not config.allow_not_ai_ready:
            return LiveSegmentResolverResult(
                track_location_id=track_location_id,
                layout_id=layout_id,
                status=LiveSegmentResolutionStatus.NO_REVIEWED_MODEL,
                model_source=model_source,
                warnings=["Reviewed model is not AI-ready and allow_not_ai_ready is False."],
            )

        if model_source == "reviewed":
            not_ai_ready = True
            result_warnings.append(
                "Reviewed model exists but is not AI-ready — segment bounds may be incomplete. "
                "Review and approve all segments for higher confidence."
            )

        if rm.reviewed_model is not None:
            segments = list(rm.reviewed_model.segments)
        if resolver_result.warnings:
            result_warnings.extend(resolver_result.warnings)
    except Exception as exc:
        return LiveSegmentResolverResult(
            track_location_id=track_location_id,
            layout_id=layout_id,
            status=LiveSegmentResolutionStatus.ERROR,
            model_source=model_source,
            errors=[f"Resolver error: {exc}"],
        )

    # ── Step 2: Filter to usable segments ────────────────────────────────
    usable = _usable_segments(segments, config)
    if not usable:
        return LiveSegmentResolverResult(
            track_location_id=track_location_id,
            layout_id=layout_id,
            status=LiveSegmentResolutionStatus.NO_SEGMENT_BOUNDS,
            model_source=model_source,
            warnings=result_warnings + [
                "Track model loaded but no usable reviewed segments found."
            ],
        )

    # ── Step 3: Require position evidence ────────────────────────────────
    if position is None:
        return LiveSegmentResolverResult(
            track_location_id=track_location_id,
            layout_id=layout_id,
            status=LiveSegmentResolutionStatus.NO_POSITION_DATA,
            model_source=model_source,
            warnings=result_warnings + ["No position data provided — cannot resolve segment."],
        )

    has_xyz = (
        position.pos_x is not None and position.pos_z is not None
    )
    has_progress = position.lap_progress is not None
    has_distance = position.distance_along_lap_m is not None
    has_segment_id = position.segment_id is not None
    has_road_distance = (
        position.road_distance_m is not None and offset_calibration is not None
    )

    if not has_xyz and not has_progress and not has_distance and not has_segment_id and not has_road_distance:
        return LiveSegmentResolverResult(
            track_location_id=track_location_id,
            layout_id=layout_id,
            status=LiveSegmentResolutionStatus.NO_POSITION_DATA,
            model_source=model_source,
            warnings=result_warnings + [
                "No usable position evidence (no lap_progress, no XYZ, no segment_id)."
            ],
        )

    # ── Step 3b: Convert road_distance_m to distance_along_lap_m via offset ─
    # (Group 17L) Only attempted when no direct distance_along_lap_m is available.
    effective_distance_m: Optional[float] = position.distance_along_lap_m
    road_distance_match_source: Optional[str] = None

    if not has_distance and has_road_distance:
        try:
            from data.lap_distance_mapper import (
                map_road_distance_to_lap_distance,
                LapDistanceMappingStatus,
            )
            rdm = map_road_distance_to_lap_distance(
                position.road_distance_m,
                offset_calibration.offset_m,
                offset_calibration.track_length_m,
            )
            if rdm.status in (
                LapDistanceMappingStatus.MAPPED,
                LapDistanceMappingStatus.MAPPED_WITH_WRAP,
            ):
                effective_distance_m = rdm.distance_along_lap_m
                road_distance_match_source = "road_distance"
                result_warnings.extend(rdm.warnings)
        except Exception:
            pass

    has_effective_distance = effective_distance_m is not None

    # ── Step 4: Load reference path (needed for XYZ and distance matching) ──
    ref_path = None
    if has_xyz or has_effective_distance:
        ref_path = _load_reference_path(track_location_id, layout_id, base_dir)
        if (
            ref_path is None
            and has_xyz
            and not has_progress
            and not has_effective_distance
            and not has_segment_id
        ):
            return LiveSegmentResolverResult(
                track_location_id=track_location_id,
                layout_id=layout_id,
                status=LiveSegmentResolutionStatus.NO_POSITION_DATA,
                model_source=model_source,
                warnings=result_warnings + [
                    "XYZ position available but no reference path found — "
                    "cannot convert to lap_progress. "
                    "Build and save a reference path first."
                ],
            )

    # ── Step 5: Attempt matching in priority order ────────────────────────
    base_conf = _base_confidence(model_source)
    matched_seg = None
    match_source = "unresolved"
    resolved_progress: Optional[float] = None

    # Priority 1: exact segment_id
    if has_segment_id:
        seg = _find_segment_by_id(position.segment_id, usable)
        if seg is not None:
            matched_seg = seg
            match_source = "segment_id"
            resolved_progress = position.lap_progress or seg.lap_progress_mid

    # Priority 2: lap_progress within segment range
    if matched_seg is None and has_progress:
        resolved_progress = position.lap_progress
        seg = _find_segment_by_progress(resolved_progress, usable)
        if seg is not None:
            matched_seg = seg
            match_source = "lap_progress"

    # Priority 3: distance_along_lap_m (from road_distance offset or caller-supplied)
    if matched_seg is None and has_effective_distance and ref_path is not None:
        p = _distance_to_lap_progress(effective_distance_m, ref_path)
        if p is not None:
            resolved_progress = p
            seg = _find_segment_by_progress(p, usable)
            if seg is not None:
                matched_seg = seg
                match_source = road_distance_match_source or "distance"

    # Priority 4: XYZ → nearest reference path point → lap_progress → segment range
    if matched_seg is None and has_xyz and ref_path is not None:
        p, dist_m = _xyz_to_lap_progress(
            position.pos_x, position.pos_y or 0.0, position.pos_z,
            ref_path, config.max_xyz_match_distance_m,
        )
        if p is not None:
            resolved_progress = p
            seg = _find_segment_by_progress(p, usable)
            if seg is not None:
                matched_seg = seg
                match_source = "xyz_nearest"
                if dist_m > 20.0:
                    result_warnings.append(
                        f"XYZ-to-reference-path match distance was {dist_m:.1f} m — "
                        "positional accuracy may be reduced."
                    )

    # Priority 5: nearest segment by midpoint (if we have any progress estimate)
    if matched_seg is None and resolved_progress is not None:
        seg = _find_nearest_segment(resolved_progress, usable)
        if seg is not None:
            matched_seg = seg
            match_source = "nearest_midpoint"

    # ── Step 6: Handle unresolved ──────────────────────────────────────────
    if matched_seg is None:
        return LiveSegmentResolverResult(
            track_location_id=track_location_id,
            layout_id=layout_id,
            status=LiveSegmentResolutionStatus.NO_POSITION_DATA,
            model_source=model_source,
            warnings=result_warnings + [
                "Could not match position to any reviewed segment. "
                "Segment unknown — do not invent a corner name."
            ],
        )

    # ── Step 7: Compute confidence ─────────────────────────────────────────
    confidence = base_conf
    seg_warnings: list[str] = []

    if match_source == "nearest_midpoint":
        confidence = _downgrade_confidence(confidence)
        seg_warnings.append(
            f"Segment matched by nearest midpoint fallback (match source: nearest_midpoint). "
            "Exact position is uncertain."
        )
    elif match_source == "xyz_nearest":
        confidence = _downgrade_confidence(confidence)
    elif match_source == "road_distance" and offset_calibration is not None:
        # Road-distance offset calibration is reliable when confidence is HIGH/MEDIUM;
        # downgrade only when calibration confidence is LOW or UNKNOWN.
        if offset_calibration.confidence.value in ("low", "unknown"):
            confidence = _downgrade_confidence(confidence)
            seg_warnings.append(
                "Road-distance offset calibration confidence is "
                f"{offset_calibration.confidence.value} — segment match accuracy reduced."
            )

    seg_confidence, status_warnings = _segment_confidence_adjustment(matched_seg, confidence)
    seg_warnings.extend(status_warnings)

    # ── Step 8: Previous / next segment ──────────────────────────────────
    try:
        matched_index = usable.index(matched_seg)
    except ValueError:
        matched_index = 0

    prev_seg, next_seg = _prev_next_segments(matched_index, usable)

    prev_id = prev_seg.segment_id if prev_seg else None
    prev_name = prev_seg.display_name if prev_seg else ""
    next_id = next_seg.segment_id if next_seg else None
    next_name = next_seg.display_name if next_seg else ""

    # ── Step 9: Build result ──────────────────────────────────────────────
    seg_type = (
        matched_seg.segment_type.value
        if hasattr(matched_seg.segment_type, "value")
        else str(matched_seg.segment_type)
    )

    match = LiveSegmentMatch(
        track_location_id=track_location_id,
        layout_id=layout_id,
        segment_id=matched_seg.segment_id,
        display_name=matched_seg.display_name,
        segment_type=seg_type,
        lap_progress=resolved_progress,
        lap_progress_start=matched_seg.lap_progress_start,
        lap_progress_end=matched_seg.lap_progress_end,
        lap_progress_mid=matched_seg.lap_progress_mid,
        distance_along_lap_m=effective_distance_m if has_effective_distance else None,
        confidence=seg_confidence,
        source=match_source,
        turn_number=matched_seg.turn_number if hasattr(matched_seg, "turn_number") else None,
        warnings=seg_warnings + result_warnings,
        previous_segment_id=prev_id,
        previous_segment_display_name=prev_name,
        next_segment_id=next_id,
        next_segment_display_name=next_name,
    )

    status = (
        LiveSegmentResolutionStatus.MATCHED_NEAREST
        if match_source == "nearest_midpoint"
        else LiveSegmentResolutionStatus.MATCHED
    )

    return LiveSegmentResolverResult(
        track_location_id=track_location_id,
        layout_id=layout_id,
        status=status,
        match=match,
        model_source=model_source,
        warnings=result_warnings,
    )


# ---------------------------------------------------------------------------
# Packet adapter
# ---------------------------------------------------------------------------

def packet_to_live_position(packet) -> Optional[LivePosition]:
    """Extract a LivePosition from a GT7-compatible telemetry packet.

    Accepts any duck-typed object with pos_x/pos_y/pos_z attributes.
    Returns None if the packet is clearly invalid (off-track, paused, loading).

    GT7 limitations:
      - No native lap_progress field — lap_progress is NOT populated here.
      - road_distance is stored in road_distance_m but is NOT converted to
        distance_along_lap_m here.  Use enrich_position_with_road_distance()
        or pass offset_calibration to resolve_live_segment() to convert it.
      - XYZ matching via reference path is performed inside resolve_live_segment().
    """
    try:
        # Validate packet state
        car_on_track = getattr(packet, "car_on_track", None)
        paused = getattr(packet, "paused", False)
        loading = getattr(packet, "loading", False)
        if paused or loading:
            return None
        if car_on_track is not None and not car_on_track:
            return None

        x = getattr(packet, "pos_x", None)
        y = getattr(packet, "pos_y", None)
        z = getattr(packet, "pos_z", None)
        speed = getattr(packet, "speed_kmh", None)
        road_dist = getattr(packet, "road_distance", None)

        # If all XYZ are exactly 0.0, the packet is likely uninitialised
        if x == 0.0 and y == 0.0 and z == 0.0:
            return None

        return LivePosition(
            lap_progress=None,          # not available from GT7 packet directly
            pos_x=float(x) if x is not None else None,
            pos_y=float(y) if y is not None else None,
            pos_z=float(z) if z is not None else None,
            distance_along_lap_m=None,  # requires offset calibration — not set here
            segment_id=None,
            speed_kph=float(speed) if speed is not None else None,
            road_distance_m=float(road_dist) if road_dist is not None else None,
        )
    except Exception:
        return None


def enrich_position_with_road_distance(
    position: LivePosition,
    offset_calibration,  # Optional[LapStartOffsetCalibration]
) -> LivePosition:
    """Return a LivePosition with distance_along_lap_m computed from road_distance_m.

    No-op (returns original position) if:
      - position.distance_along_lap_m is already set
      - position.road_distance_m is None
      - offset_calibration is None
      - mapping fails (bad track_length, invalid offset, etc.)

    On success, returns a new LivePosition dataclass instance with
    distance_along_lap_m populated.  The original position is not mutated.
    Uses map_road_distance_to_lap_distance() from data.lap_distance_mapper.
    """
    try:
        if position.distance_along_lap_m is not None:
            return position
        if position.road_distance_m is None or offset_calibration is None:
            return position

        from dataclasses import replace
        from data.lap_distance_mapper import (
            map_road_distance_to_lap_distance,
            LapDistanceMappingStatus,
        )

        mapping = map_road_distance_to_lap_distance(
            position.road_distance_m,
            offset_calibration.offset_m,
            offset_calibration.track_length_m,
        )

        if mapping.status not in (
            LapDistanceMappingStatus.MAPPED,
            LapDistanceMappingStatus.MAPPED_WITH_WRAP,
        ):
            return position

        return replace(position, distance_along_lap_m=mapping.distance_along_lap_m)
    except Exception:
        return position


# ---------------------------------------------------------------------------
# Live engineer wording helper
# ---------------------------------------------------------------------------

def format_live_segment_for_engineer(result: LiveSegmentResolverResult) -> str:
    """Return a compact one-line engineer wording for the live segment resolution.

    Examples:
      "Current segment: T1 Braking Zone (confidence: high). Next: T1 Entry."
      "Track segment unavailable: no reviewed model for selected layout."
      "Current segment unresolved: no lap progress or position data."
      "Current segment: Sector 3 Exit [nearest fallback] (confidence: low). Prev: Sector 3 Apex."

    Rules:
      - No invented corner names when unresolved.
      - No hype commentary.
      - Keep under ~120 characters where possible.
    """
    status = result.status
    m = result.match

    if status == LiveSegmentResolutionStatus.NO_REVIEWED_MODEL:
        return "Track segment unavailable: no reviewed model for selected layout."

    if status == LiveSegmentResolutionStatus.NO_SEGMENT_BOUNDS:
        return "Track segment unavailable: reviewed model has no usable segments."

    if status == LiveSegmentResolutionStatus.NO_POSITION_DATA:
        return "Current segment unresolved: no lap progress or position data."

    if status == LiveSegmentResolutionStatus.ERROR:
        return "Track segment unavailable: resolver error."

    if m is None:
        return "Current segment unresolved."

    name = m.display_name or "Unknown segment"
    conf = m.confidence.value
    fallback_note = " [nearest fallback]" if status == LiveSegmentResolutionStatus.MATCHED_NEAREST else ""

    parts = [f"Current segment: {name}{fallback_note} (confidence: {conf})."]
    if m.next_segment_display_name:
        parts.append(f"Next: {m.next_segment_display_name}.")
    elif m.previous_segment_display_name:
        parts.append(f"Prev: {m.previous_segment_display_name}.")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Prompt context helper
# ---------------------------------------------------------------------------

def get_live_segment_context_for_prompt(
    track_location_id: str,
    layout_id: str,
    position: Optional[LivePosition] = None,
    base_dir: Optional[Path] = None,
) -> str:
    """Resolve live position and return a compact AI-ready prompt block.

    Returns "" if no reviewed model or no position data — never raises.

    Prompt block format (when matched):
      ## Live Track Position
      Current segment: T1 Braking Zone (confidence: high)
      Segment type: braking_zone | Progress: 5.2%
      Next: T1 Entry | Prev: Start/Finish

    Format (when unresolved):
      ## Live Track Position
      [Warning]: Track segment unresolved — no lap progress or reviewed model available.
      Do not invent a corner name.
    """
    try:
        result = resolve_live_segment(track_location_id, layout_id, position, base_dir)
        lines = ["## Live Track Position"]

        if result.status == LiveSegmentResolutionStatus.MATCHED:
            m = result.match
            lines.append(f"Current segment: {m.display_name} (confidence: {m.confidence.value})")
            pct = f"{m.lap_progress * 100:.1f}%" if m.lap_progress is not None else "unknown"
            lines.append(f"Segment type: {m.segment_type} | Progress: {pct}")
            nav_parts = []
            if m.previous_segment_display_name:
                nav_parts.append(f"Prev: {m.previous_segment_display_name}")
            if m.next_segment_display_name:
                nav_parts.append(f"Next: {m.next_segment_display_name}")
            if nav_parts:
                lines.append(" | ".join(nav_parts))
            for warn in m.warnings:
                lines.append(f"[Warning]: {warn}")
            return "\n".join(lines)

        if result.status == LiveSegmentResolutionStatus.MATCHED_NEAREST:
            m = result.match
            lines.append(
                f"Current segment (nearest fallback): {m.display_name} "
                f"(confidence: {m.confidence.value})"
            )
            lines.append(f"Segment type: {m.segment_type}")
            nav_parts = []
            if m.previous_segment_display_name:
                nav_parts.append(f"Prev: {m.previous_segment_display_name}")
            if m.next_segment_display_name:
                nav_parts.append(f"Next: {m.next_segment_display_name}")
            if nav_parts:
                lines.append(" | ".join(nav_parts))
            lines.append("[Warning]: Segment match used nearest-midpoint fallback — positional accuracy reduced.")
            return "\n".join(lines)

        # Any other status: short warning, no invented segment name
        if result.status == LiveSegmentResolutionStatus.NO_REVIEWED_MODEL:
            return ""  # silently omit rather than add a confusing warning block
        lines.append(
            "[Warning]: Track segment unresolved — no lap progress or reviewed model available. "
            "Do not invent a corner name."
        )
        return "\n".join(lines)
    except Exception:
        return ""
