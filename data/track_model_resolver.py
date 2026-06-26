"""Track Model Resolver — discover, rank, and resolve the best reviewed track model.

Pure Python, no PyQt6 dependency.

Architecture boundary:
  - Reads: data/track_models/ (reviewed JSON files produced by Group 17F)
  - Imports: data.track_segment_review (read-only; no mutations)
  - Imports: data.track_intelligence (seed context for fallback)
  - Does NOT write any files; export lives in data.track_segment_review
  - Not integrated into Setup Builder / Strategy Builder / Live AI yet (Group 17H+)

Model maturity priority (highest wins when multiple files exist):
  1. engineer_validated_model — at least one segment is ENGINEER_VALIDATED
  2. ai_ready_reviewed_model  — is_ai_ready() returns True
  3. reviewed_model           — reviewed file exists but not AI-ready
  4. seed_only                — no reviewed model on disk; seed data only
  5. missing                  — no seed entry and no reviewed model found

When maturity is equal, prefer the newest file (by `created_at` timestamp from JSON,
with filename as the tie-breaker since filenames embed a UTC timestamp).

Malformed reviewed model files are silently skipped; errors are recorded in
TrackModelResolverResult.errors so callers can surface them without crashing.

Design constraints (preserved from Group 17F spec):
  - Detected segments are NOT engineer-validated until reviewed.
  - Car-behaviour boundary: braking/gear/traction data tagged with calibration_car_id
    are Porsche RSR-specific, NOT universal track truth.
  - Warnings from detection are always preserved — never hidden.
  - AI should not consume a reviewed model unless it is explicitly AI-ready,
    or the prompt includes clear warnings about the model state.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Union

from data.track_segment_review import (
    REVIEW_MODELS_DIR,
    TrackModelReviewResult,
    SegmentReviewStatus,
    import_review_json,
    is_ai_ready,
    review_completion_pct,
)

_PORSCHE_BOUNDARY_NOTE = (
    "Car-behaviour boundary: braking points, gear selection, throttle, and traction "
    "data are Porsche 911 RSR (991) '17 calibration behaviour — not universal track truth."
)

_REVIEWED_SEGMENTS_INFIX = "__reviewed_segments__"


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TrackModelSourceType(str, Enum):
    """How the best available track model was sourced."""
    SEED_ONLY                = "seed_only"
    DETECTED_UNREVIEWED      = "detected_unreviewed"   # future: detection result not yet reviewed
    REVIEWED_MODEL           = "reviewed_model"        # reviewed but not AI-ready
    AI_READY_REVIEWED_MODEL  = "ai_ready_reviewed_model"
    ENGINEER_VALIDATED_MODEL = "engineer_validated_model"
    MISSING                  = "missing"


class TrackModelResolutionStatus(str, Enum):
    """Outcome of a resolution attempt."""
    FOUND               = "found"               # engineer-validated or AI-ready
    FOUND_WITH_WARNINGS = "found_with_warnings" # reviewed but not AI-ready
    SEED_ONLY_FALLBACK  = "seed_only_fallback"  # no reviewed model; fell back to seed
    NOT_AI_READY        = "not_ai_ready"        # reviewed file exists; blockers remain
    MISSING             = "missing"             # no seed entry and no reviewed model
    ERROR               = "error"               # file I/O or parse error


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ResolvedTrackModel:
    """Summary of the best available track model for a given track/layout."""
    track_location_id: str
    layout_id: str
    source_type: TrackModelSourceType
    modelling_status: str          # mirrors TrackModellingStatus values
    ai_ready: bool
    review_completion_pct: float   # 0–100
    segment_count: int
    confirmed_count: int
    rejected_count: int
    needs_more_laps_count: int
    warning_count: int             # total detection + segment-level warnings
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_path: Optional[Path] = None
    reviewed_model: Optional[TrackModelReviewResult] = None
    seed_layout: Optional[object] = None   # TrackLayoutSeed if loaded


@dataclass
class TrackModelResolverResult:
    """Return type from resolve_best_track_model."""
    track_location_id: str
    layout_id: str
    resolution_status: TrackModelResolutionStatus
    resolved_model: Optional[ResolvedTrackModel] = None
    all_candidate_paths: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _source_type_rank(source_type: TrackModelSourceType) -> int:
    """Higher = better candidate. Used to pick the best file."""
    return {
        TrackModelSourceType.MISSING:                  0,
        TrackModelSourceType.SEED_ONLY:                1,
        TrackModelSourceType.DETECTED_UNREVIEWED:      2,
        TrackModelSourceType.REVIEWED_MODEL:           3,
        TrackModelSourceType.AI_READY_REVIEWED_MODEL:  4,
        TrackModelSourceType.ENGINEER_VALIDATED_MODEL: 5,
    }.get(source_type, 0)


def _classify_review(review: TrackModelReviewResult) -> tuple[TrackModelSourceType, str]:
    """Return (source_type, modelling_status) from a loaded review.

    Uses the persisted ``modelling_status`` field when present (Group 17G+),
    otherwise falls back to computing it from segment data.
    """
    # Prefer the persisted status if it was written by a recent export
    persisted = review.modelling_status

    has_validated = any(
        s.review_status == SegmentReviewStatus.ENGINEER_VALIDATED
        for s in review.segments
    )
    if has_validated:
        source = TrackModelSourceType.ENGINEER_VALIDATED_MODEL
        status = persisted if persisted else "engineer_grade"
        return source, status

    ai_ready, _ = is_ai_ready(review)
    if ai_ready:
        source = TrackModelSourceType.AI_READY_REVIEWED_MODEL
        status = persisted if persisted else "user_reviewed"
    else:
        source = TrackModelSourceType.REVIEWED_MODEL
        status = persisted if persisted else "segment_detected"

    return source, status


def _created_at_key(review: TrackModelReviewResult, path: Path) -> str:
    """Stable sort key (descending → invert) for newest-first ordering."""
    # Use the persisted created_at if available; fall back to filename
    ts = review.created_at or ""
    return ts if ts else path.name


def _build_resolved_model(
    review: TrackModelReviewResult,
    path: Path,
    seed_layout: Optional[object] = None,
) -> ResolvedTrackModel:
    """Build a ResolvedTrackModel from a loaded review."""
    source_type, modelling_status = _classify_review(review)

    _confirmed_statuses = {
        SegmentReviewStatus.CONFIRMED,
        SegmentReviewStatus.RENAMED,
        SegmentReviewStatus.ENGINEER_VALIDATED,
    }

    segs = review.segments
    confirmed  = sum(1 for s in segs if s.review_status in _confirmed_statuses)
    rejected   = sum(1 for s in segs if s.review_status == SegmentReviewStatus.REJECTED)
    more_laps  = sum(1 for s in segs if s.review_status == SegmentReviewStatus.NEEDS_MORE_LAPS)

    # Aggregate all warnings: detection-level + per-segment
    all_warnings: list[str] = list(review.detection_warnings)
    for seg in segs:
        all_warnings.extend(seg.warnings)
    all_warnings.extend(review.review_warnings)

    ai_ready, blockers = is_ai_ready(review)
    pct = review_completion_pct(review)

    return ResolvedTrackModel(
        track_location_id   = review.track_location_id,
        layout_id           = review.layout_id,
        source_type         = source_type,
        modelling_status    = modelling_status,
        ai_ready            = ai_ready,
        review_completion_pct = pct,
        segment_count       = len(segs),
        confirmed_count     = confirmed,
        rejected_count      = rejected,
        needs_more_laps_count = more_laps,
        warning_count       = len(all_warnings),
        blockers            = blockers,
        warnings            = all_warnings,
        source_path         = path,
        reviewed_model      = review,
        seed_layout         = seed_layout,
    )


# ---------------------------------------------------------------------------
# Discovery functions
# ---------------------------------------------------------------------------

def list_reviewed_track_models(
    base_dir: Optional[Union[Path, str]] = None,
) -> list[Path]:
    """Return all reviewed model JSON files in base_dir (not filtered by track/layout).

    Files are returned sorted by filename descending (newest UTC timestamp first).
    """
    base = Path(base_dir) if base_dir else REVIEW_MODELS_DIR
    if not base.exists() or not base.is_dir():
        return []
    candidates = [
        p for p in base.iterdir()
        if p.is_file()
        and _REVIEWED_SEGMENTS_INFIX in p.name
        and p.suffix == ".json"
    ]
    return sorted(candidates, key=lambda p: p.name, reverse=True)


def load_reviewed_track_model(path: Union[Path, str]) -> TrackModelReviewResult:
    """Load and return a reviewed track model from a JSON file.

    Raises FileNotFoundError or ValueError on failure (propagated from import_review_json).
    """
    return import_review_json(Path(path))


def find_reviewed_models_for_layout(
    track_location_id: str,
    layout_id: str,
    base_dir: Optional[Union[Path, str]] = None,
) -> list[Path]:
    """Return all reviewed model JSON files for this track_location_id + layout_id.

    Files are returned sorted by filename descending (newest first, since filenames
    embed a UTC timestamp in the session_id segment).
    """
    base = Path(base_dir) if base_dir else REVIEW_MODELS_DIR
    if not base.exists() or not base.is_dir():
        return []
    prefix = f"{track_location_id}__{layout_id}{_REVIEWED_SEGMENTS_INFIX}"
    candidates = [
        p for p in base.iterdir()
        if p.is_file() and p.name.startswith(prefix) and p.suffix == ".json"
    ]
    return sorted(candidates, key=lambda p: p.name, reverse=True)


def resolve_best_track_model(
    track_location_id: str,
    layout_id: str,
    base_dir: Optional[Union[Path, str]] = None,
) -> TrackModelResolverResult:
    """Resolve the best available reviewed track model for a track/layout.

    Priority (highest wins):
      engineer_validated_model → ai_ready_reviewed_model → reviewed_model → seed_only

    When maturity is equal, the newest file wins.
    Malformed files are skipped; errors are recorded without crashing.

    Returns a TrackModelResolverResult that always has a valid resolution_status.
    """
    candidate_paths = find_reviewed_models_for_layout(
        track_location_id, layout_id, base_dir
    )

    errors: list[str] = []
    result_warnings: list[str] = []

    # Try to load each candidate; keep the best one
    best_review: Optional[TrackModelReviewResult] = None
    best_path: Optional[Path] = None
    best_rank: int = -1
    best_created_at: str = ""

    for path in candidate_paths:
        try:
            review = import_review_json(path)
        except (FileNotFoundError, ValueError) as exc:
            errors.append(f"Skipped malformed file '{path.name}': {exc}")
            continue

        source_type, _ = _classify_review(review)
        rank = _source_type_rank(source_type)
        created_at = review.created_at or path.name

        # Accept this candidate if it has higher rank, or same rank but newer
        if rank > best_rank or (rank == best_rank and created_at > best_created_at):
            best_review = review
            best_path = path
            best_rank = rank
            best_created_at = created_at

    if best_review is None:
        # No usable reviewed model — attempt seed fallback
        seed_layout = _get_seed_layout(track_location_id, layout_id)
        if seed_layout is None:
            return TrackModelResolverResult(
                track_location_id  = track_location_id,
                layout_id          = layout_id,
                resolution_status  = TrackModelResolutionStatus.MISSING,
                all_candidate_paths = candidate_paths,
                errors             = errors,
                warnings           = result_warnings,
            )

        # Seed fallback
        resolved = ResolvedTrackModel(
            track_location_id     = track_location_id,
            layout_id             = layout_id,
            source_type           = TrackModelSourceType.SEED_ONLY,
            modelling_status      = _seed_modelling_status(seed_layout),
            ai_ready              = False,
            review_completion_pct = 0.0,
            segment_count         = 0,
            confirmed_count       = 0,
            rejected_count        = 0,
            needs_more_laps_count = 0,
            warning_count         = 0,
            blockers              = [
                "No reviewed track model exists — seed data only. "
                "Run calibration laps and segment detection first."
            ],
            warnings              = [
                "SEED DATA ONLY — corner/segment/camber/kerb/elevation details "
                "are NOT validated. Do not treat seed facts as engineering truth."
            ],
            source_path           = None,
            reviewed_model        = None,
            seed_layout           = seed_layout,
        )
        return TrackModelResolverResult(
            track_location_id  = track_location_id,
            layout_id          = layout_id,
            resolution_status  = TrackModelResolutionStatus.SEED_ONLY_FALLBACK,
            resolved_model     = resolved,
            all_candidate_paths = candidate_paths,
            errors             = errors,
            warnings           = result_warnings,
        )

    # We have a usable reviewed model
    seed_layout = _get_seed_layout(track_location_id, layout_id)
    resolved = _build_resolved_model(best_review, best_path, seed_layout=seed_layout)

    source_type = resolved.source_type
    if source_type == TrackModelSourceType.ENGINEER_VALIDATED_MODEL:
        res_status = TrackModelResolutionStatus.FOUND
    elif source_type == TrackModelSourceType.AI_READY_REVIEWED_MODEL:
        res_status = (
            TrackModelResolutionStatus.FOUND
            if not resolved.warnings
            else TrackModelResolutionStatus.FOUND_WITH_WARNINGS
        )
    else:
        # reviewed_model — not AI-ready
        res_status = TrackModelResolutionStatus.NOT_AI_READY
        result_warnings.append(
            "Reviewed model exists but is not AI-ready. "
            f"Blockers: {'; '.join(resolved.blockers)}"
        )

    if errors:
        result_warnings.append(
            f"{len(errors)} candidate file(s) were skipped due to parse errors."
        )

    return TrackModelResolverResult(
        track_location_id  = track_location_id,
        layout_id          = layout_id,
        resolution_status  = res_status,
        resolved_model     = resolved,
        all_candidate_paths = candidate_paths,
        errors             = errors,
        warnings           = result_warnings,
    )


# ---------------------------------------------------------------------------
# Seed helpers (lazy import to avoid circular dependency)
# ---------------------------------------------------------------------------

def _get_seed_layout(track_location_id: str, layout_id: str) -> Optional[object]:
    """Return TrackLayoutSeed for this track/layout, or None if not found."""
    try:
        from data.track_intelligence import resolve_track_layout
        return resolve_track_layout(track_location_id, layout_id)
    except Exception:
        return None


def _seed_modelling_status(seed_layout: object) -> str:
    """Return the modelling_status string from the seed layout."""
    status = getattr(seed_layout, "modelling_status", None)
    if status is None:
        return "not_modelled"
    if hasattr(status, "value"):
        return status.value
    return str(status)


# ---------------------------------------------------------------------------
# Calibration data loaders (GROUP 19A)
# ---------------------------------------------------------------------------

def _load_calibration_session(track_location_id: str, layout_id: str):
    """Load CalibrationSession from disk. Returns None if not found or invalid."""
    try:
        from data.track_calibration import (
            import_calibration_laps_json,
            calibration_laps_filename,
            TRACK_MODELS_DIR,
        )
        path = TRACK_MODELS_DIR / calibration_laps_filename(track_location_id, layout_id)
        if not path.exists():
            return None
        return import_calibration_laps_json(path)
    except Exception:
        return None


def _load_reference_path(track_location_id: str, layout_id: str):
    """Load ReferencePath from disk. Returns None if not found or invalid."""
    try:
        from data.track_calibration import (
            import_reference_path_json,
            reference_path_filename,
            TRACK_MODELS_DIR,
        )
        path = TRACK_MODELS_DIR / reference_path_filename(track_location_id, layout_id)
        if not path.exists():
            return None
        return import_reference_path_json(path)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# AI prompt context builder
# ---------------------------------------------------------------------------

def build_resolved_track_context_for_prompt(
    track_location_id: str,
    layout_id: str,
    base_dir: Optional[Union[Path, str]] = None,
    active_car_name: str = "",
    rev_limit_threshold_pct: float = 0.90,
) -> str:
    """Build a compact AI prompt context string from the best available track model.

    Resolves the best reviewed model for this track/layout and formats it for
    inclusion in an AI prompt.  Does NOT integrate into any AI caller yet —
    this function is ready for wiring in Group 17H+.

    If only seed data is available, includes the seed warning.
    If a reviewed model exists:
      - states modelling status and AI-ready status clearly
      - lists confirmed segments and key warnings
      - includes the car-behaviour boundary note
      - if not AI-ready, states that clearly with blockers

    Output is compact (no padding, concise labels).
    """
    result = resolve_best_track_model(track_location_id, layout_id, base_dir)
    resolved = result.resolved_model

    lines: list[str] = []

    # --- Seed-only or missing ---------------------------------------------------
    if resolved is None or resolved.source_type == TrackModelSourceType.MISSING:
        lines.append(f"## Track Model Context: {track_location_id} / {layout_id}")
        lines.append("Model status: MISSING — no seed entry and no reviewed model found.")
        return "\n".join(lines)

    if resolved.source_type == TrackModelSourceType.SEED_ONLY:
        # Fall through to seed context builder for seed-level detail
        try:
            from data.track_intelligence import build_seed_track_context_for_prompt
            seed_ctx = build_seed_track_context_for_prompt(track_location_id, layout_id)
        except Exception as exc:
            seed_ctx = f"[Seed context unavailable: {exc}]"
        lines.append(seed_ctx)
        lines.append("")
        lines.append(
            "IMPORTANT: No reviewed track model exists for this layout. "
            "The above is seed data only. Corner geometry, braking zones, and segment "
            "details are NOT validated. Use hedged language."
        )
        return "\n".join(lines)

    # --- Reviewed model (any maturity above seed) --------------------------------
    review = resolved.reviewed_model
    source_label = {
        TrackModelSourceType.REVIEWED_MODEL:           "Reviewed (not AI-ready)",
        TrackModelSourceType.AI_READY_REVIEWED_MODEL:  "Reviewed — AI-ready",
        TrackModelSourceType.ENGINEER_VALIDATED_MODEL: "Engineer-validated",
    }.get(resolved.source_type, resolved.source_type.value)

    lines.append(
        f"## Track Model Context: {track_location_id} / {layout_id}"
    )
    lines.append(f"Model source: {source_label}")
    lines.append(f"Modelling status: {resolved.modelling_status}")
    lines.append(f"AI-ready: {'Yes' if resolved.ai_ready else 'No'}")

    if review is not None:
        lines.append(
            f"Segments: {resolved.segment_count} detected | "
            f"{resolved.confirmed_count} confirmed | "
            f"{resolved.rejected_count} rejected | "
            f"{resolved.needs_more_laps_count} need more laps"
        )
        lines.append(f"Review completion: {resolved.review_completion_pct:.0f}%")
        if review.calibration_car_id:
            lines.append(f"Calibration car: {review.calibration_car_id}")
        lines.append(f"Laps used: {review.source_lap_count}")

    lines.append("")
    lines.append(_PORSCHE_BOUNDARY_NOTE)

    if not resolved.ai_ready and resolved.blockers:
        lines.append("")
        lines.append(
            "NOT AI-READY — the following issues must be resolved before "
            "this model can be used for AI coaching:"
        )
        for blocker in resolved.blockers:
            lines.append(f"  • {blocker}")

    if resolved.warnings:
        lines.append("")
        lines.append("Warnings:")
        for w in resolved.warnings[:5]:   # cap at 5 to keep prompt compact
            lines.append(f"  ⚠ {w}")
        if len(resolved.warnings) > 5:
            lines.append(f"  … and {len(resolved.warnings) - 5} more warning(s)")

    # Confirmed segment list (compact)
    if review is not None:
        _confirmed_statuses = {
            SegmentReviewStatus.CONFIRMED,
            SegmentReviewStatus.RENAMED,
            SegmentReviewStatus.ENGINEER_VALIDATED,
        }
        confirmed_segs = [
            s for s in review.segments
            if s.review_status in _confirmed_statuses
        ]
        if confirmed_segs:
            lines.append("")
            lines.append("Confirmed segments:")
            for seg in confirmed_segs:
                turn = f"T{seg.turn_number} " if seg.turn_number else ""
                lines.append(
                    f"  {turn}{seg.display_name} "
                    f"[{seg.segment_type.value}] "
                    f"{seg.lap_progress_start:.1%}–{seg.lap_progress_end:.1%}"
                )

    if result.errors:
        lines.append("")
        lines.append(
            f"Note: {len(result.errors)} candidate file(s) were skipped "
            "due to parse errors."
        )

    # --- GROUP 19A: Track Intelligence Enrichment ---
    calib_session = _load_calibration_session(track_location_id, layout_id)
    if calib_session is not None:
        from strategy.track_intelligence_enrichment import (
            compute_corner_speed_load,
            compute_sector_fuel,
            compute_overtaking_zones,
            compute_kerb_characterisation,
            format_sector_fuel_block,
            format_corner_speed_load_block,
            format_overtaking_zones_block,
            format_kerb_block,
            format_car_mismatch_warning,
            get_calibration_car_display_name,
        )

        calib_laps = getattr(calib_session, "laps", [])
        reviewed_segs = []
        if resolved and hasattr(resolved, "reviewed_model") and resolved.reviewed_model is not None:
            reviewed_segs = getattr(resolved.reviewed_model, "segments", []) or []

        # Corner speed/load (AC2, AC3)
        corner_data = compute_corner_speed_load(calib_laps, reviewed_segs)
        corner_block = format_corner_speed_load_block(corner_data)
        if corner_block:
            lines.append("")
            lines.append(corner_block)

        # Kerb characterisation (AC9)
        kerb_data = compute_kerb_characterisation(calib_laps, reviewed_segs)
        kerb_block = format_kerb_block(kerb_data)
        if kerb_block:
            lines.append("")
            lines.append(kerb_block)

        # Gear usage by corner (GROUP 22A)
        from strategy.track_intelligence_enrichment import compute_corner_gear_usage, format_corner_gear_usage
        if calib_laps and reviewed_segs:
            gear_usage = compute_corner_gear_usage(
                calib_laps, reviewed_segs, rev_limit_threshold_pct=rev_limit_threshold_pct
            )
            if gear_usage:
                lines.append("\n## Gear Usage by Corner (from calibration telemetry)")
                lines.append(format_corner_gear_usage(gear_usage))

        # Overtaking zones (AC6) — needs reference path
        ref_path = _load_reference_path(track_location_id, layout_id)
        if ref_path is not None:
            zones = compute_overtaking_zones(ref_path, reviewed_segs)
            zones_block = format_overtaking_zones_block(zones)
            if zones_block:
                lines.append("")
                lines.append(zones_block)

        # Sector fuel (AC1) — needs sectors from semantic model
        sectors = []
        if resolved and hasattr(resolved, "reviewed_model") and resolved.reviewed_model is not None:
            sm = getattr(resolved.reviewed_model, "semantic_model", None)
            if sm and hasattr(sm, "sectors"):
                sectors = [
                    {
                        "sector_name": s.name if hasattr(s, "name") else str(s),
                        "start_progress": getattr(s, "start_progress", 0.0),
                        "end_progress": getattr(s, "end_progress", 1.0),
                    }
                    for s in (sm.sectors or [])
                ]

        fuel_multiplier = 1.0  # default; callers may override
        sector_fuel = compute_sector_fuel(calib_laps, sectors)
        fuel_block = format_sector_fuel_block(sector_fuel, fuel_multiplier)
        if fuel_block:
            lines.append("")
            lines.append(fuel_block)

        # Car-mismatch warning (AC4, AC5)
        calib_car_id = getattr(calib_session, "calibration_car_id", "")
        if active_car_name and calib_car_id:
            calib_car_display = get_calibration_car_display_name(calib_car_id)
            active_norm = active_car_name.strip().lower()
            calib_norm = calib_car_display.strip().lower()
            if active_norm != calib_norm:
                warning_block = format_car_mismatch_warning(active_car_name.strip(), calib_car_display)
                lines.append("")
                lines.append(warning_block)

    return "\n".join(lines)
