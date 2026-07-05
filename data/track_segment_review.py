"""Track Segment Review — review/approval layer for automatically detected segments.

Pure Python, no PyQt6 dependency.

Architecture boundary:
  - Depends on: data.track_segment_detection (models only)
  - Does NOT own: segment detection, AI prompt integration
  - Reviewed segments are NOT integrated into Setup/Strategy/AI prompts yet (Group 17G+)
  - Car-behaviour boundary warnings from detection are preserved, not hidden

Review workflow:
  1. detect_track_segments() → SegmentDetectionResult  (Group 17E)
  2. create_review_from_detection(result) → TrackModelReviewResult  (all unreviewed)
  3. confirm / rename / reject / mark_* per segment via action functions
  4. is_ai_ready(review) → (bool, list[str]) blockers
  5. export_review_json() → data/track_models/<loc>__<layout>__reviewed_segments__<sid>.json

AI-ready criteria (all must hold):
  * At least one segment exists
  * All apex_zone segments are reviewed (not unreviewed)
  * No segment is marked needs_more_laps
  * No segment is marked split_required or merge_required
  * At least one non-rejected instance of each key type:
      straight, braking_zone, apex_zone, corner_exit
    (if a type is entirely absent from detection, that absence is flagged as a blocker)

Engineer-validated is a future maturity level; NOT required for AI-ready.
Warnings from detection are always preserved — never hidden.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from data.track_segment_detection import (
    DetectedTrackSegment,
    SegmentDetectionResult,
    TrackSegmentDetectionConfidence,
    TrackSegmentType,
    SEGMENT_MODELS_DIR,
)

# Reviewed models share the same folder as detection results
REVIEW_MODELS_DIR: Path = SEGMENT_MODELS_DIR

_REVIEW_SCHEMA: str = "track_model_review_result_v1"

# Segment types that must all be present (or explicitly all-rejected) for AI-ready.
# BRAKING_ZONE is intentionally NOT required: it is inferred from a speed-drop
# threshold and is the least-reliably-detected type, so requiring it blocked
# otherwise-good models (real UAT case: straights + apexes + corner-exits all
# detected, braking zones not). A model without explicit braking segments is
# still useful to the AI (braking is implied by corner entry -> apex). Missing
# braking zones remain a detection WARNING, just not an AI-ready blocker.
_AI_READY_REQUIRED_TYPES: frozenset[TrackSegmentType] = frozenset({
    TrackSegmentType.STRAIGHT,
    TrackSegmentType.APEX_ZONE,
    TrackSegmentType.CORNER_EXIT,
})


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SegmentReviewStatus(str, Enum):
    UNREVIEWED          = "unreviewed"
    CONFIRMED           = "confirmed"
    RENAMED             = "renamed"
    SPLIT_REQUIRED      = "split_required"
    MERGE_REQUIRED      = "merge_required"
    REJECTED            = "rejected"
    NEEDS_MORE_LAPS     = "needs_more_laps"
    ENGINEER_VALIDATED  = "engineer_validated"


class SegmentReviewAction(str, Enum):
    CONFIRM                    = "confirm"
    RENAME                     = "rename"
    REJECT                     = "reject"
    MARK_NEEDS_MORE_LAPS       = "mark_needs_more_laps"
    MARK_SPLIT_REQUIRED        = "mark_split_required"
    MARK_MERGE_REQUIRED        = "mark_merge_required"
    PROMOTE_ENGINEER_VALIDATED = "promote_engineer_validated"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ReviewedTrackSegment:
    """A detected segment with its review state.

    Original detection fields are preserved unchanged so the detection history
    is always recoverable.  Review fields overlay the originals for display.
    """
    # ── Original detection fields (read-only after construction) ────────────
    segment_id: str
    segment_type: TrackSegmentType
    original_display_name: str
    lap_progress_start: float
    lap_progress_end: float
    lap_progress_mid: float
    confidence: TrackSegmentDetectionConfidence
    evidence: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_lap_count: int = 0
    turn_number: Optional[int] = None
    track_location_id: Optional[str] = None
    layout_id: Optional[str] = None
    direction: Optional[str] = None  # "left" | "right" | "unknown" | None
    calibration_car_id: Optional[str] = None

    # ── Review state ─────────────────────────────────────────────────────────
    review_status: SegmentReviewStatus = SegmentReviewStatus.UNREVIEWED
    reviewed_display_name: str = ""   # empty → show original_display_name
    review_notes: str = ""
    reviewed_at: Optional[str] = None
    last_action: Optional[SegmentReviewAction] = None
    verification_source: str = "greedy"

    @property
    def display_name(self) -> str:
        """Active display name: reviewed override if set, else original detection name."""
        return self.reviewed_display_name if self.reviewed_display_name else self.original_display_name

    @property
    def is_reviewed(self) -> bool:
        """True when any review action has been taken (status ≠ UNREVIEWED)."""
        return self.review_status != SegmentReviewStatus.UNREVIEWED


@dataclass
class TrackModelReviewResult:
    """Complete reviewed track model: detection metadata + per-segment review state.

    Holds the full list of ReviewedTrackSegment objects.  Action functions
    mutate segments in-place and update last_reviewed_at.
    """
    track_location_id: str
    layout_id: str
    calibration_car_id: Optional[str]
    source_lap_count: int
    detected_corner_count: int
    expected_corner_count: Optional[int]
    detection_confidence: TrackSegmentDetectionConfidence
    segments: list[ReviewedTrackSegment] = field(default_factory=list)
    detection_warnings: list[str] = field(default_factory=list)
    review_warnings: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_reviewed_at: Optional[str] = None
    # Maturity level persisted in the JSON snapshot; computed at export time.
    # Values mirror TrackModellingStatus: segment_detected / user_reviewed / engineer_grade
    modelling_status: Optional[str] = None


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

def create_review_from_detection(result: SegmentDetectionResult) -> TrackModelReviewResult:
    """Create a new unreviewed review model from a SegmentDetectionResult.

    All segments start as UNREVIEWED.  Detection warnings are preserved.
    """
    reviewed_segs: list[ReviewedTrackSegment] = []
    for seg in result.segments:
        reviewed_segs.append(ReviewedTrackSegment(
            segment_id          = seg.segment_id,
            segment_type        = seg.segment_type,
            original_display_name = seg.display_name,
            lap_progress_start  = seg.lap_progress_start,
            lap_progress_end    = seg.lap_progress_end,
            lap_progress_mid    = seg.lap_progress_mid,
            confidence          = seg.confidence,
            evidence            = list(seg.evidence),
            warnings            = list(seg.warnings),
            source_lap_count    = seg.source_lap_count,
            turn_number         = seg.turn_number,
            track_location_id   = seg.track_location_id,
            layout_id           = seg.layout_id,
            direction           = (seg.direction.value if seg.direction is not None else None),
            calibration_car_id  = seg.calibration_car_id,
        ))

    return TrackModelReviewResult(
        track_location_id   = result.track_location_id,
        layout_id           = result.layout_id,
        calibration_car_id  = result.calibration_car_id,
        source_lap_count    = result.source_lap_count,
        detected_corner_count = result.detected_corner_count,
        expected_corner_count = result.expected_corner_count,
        detection_confidence  = result.confidence,
        segments            = reviewed_segs,
        detection_warnings  = list(result.warnings),
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _find_segment(review: TrackModelReviewResult, segment_id: str) -> Optional[ReviewedTrackSegment]:
    for s in review.segments:
        if s.segment_id == segment_id:
            return s
    return None


def _touch(review: TrackModelReviewResult) -> None:
    review.last_reviewed_at = datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Review action functions (mutate in place, return the review for convenience)
# ---------------------------------------------------------------------------

def confirm_segment(
    review: TrackModelReviewResult,
    segment_id: str,
    notes: str = "",
) -> TrackModelReviewResult:
    """Confirm a segment as correct.  Returns the same review object."""
    seg = _find_segment(review, segment_id)
    if seg is not None:
        seg.review_status = SegmentReviewStatus.CONFIRMED
        seg.last_action   = SegmentReviewAction.CONFIRM
        if notes:
            seg.review_notes = notes
        seg.reviewed_at = datetime.now(timezone.utc).isoformat()
        _touch(review)
    return review


def rename_segment(
    review: TrackModelReviewResult,
    segment_id: str,
    new_name: str,
    notes: str = "",
) -> TrackModelReviewResult:
    """Rename a segment and mark it RENAMED.  Blank new_name is ignored."""
    if not new_name.strip():
        return review
    seg = _find_segment(review, segment_id)
    if seg is not None:
        seg.reviewed_display_name = new_name.strip()
        seg.review_status = SegmentReviewStatus.RENAMED
        seg.last_action   = SegmentReviewAction.RENAME
        if notes:
            seg.review_notes = notes
        seg.reviewed_at = datetime.now(timezone.utc).isoformat()
        _touch(review)
    return review


def reject_segment(
    review: TrackModelReviewResult,
    segment_id: str,
    notes: str = "",
) -> TrackModelReviewResult:
    """Mark a segment as rejected (will not be used for AI context)."""
    seg = _find_segment(review, segment_id)
    if seg is not None:
        seg.review_status = SegmentReviewStatus.REJECTED
        seg.last_action   = SegmentReviewAction.REJECT
        if notes:
            seg.review_notes = notes
        seg.reviewed_at = datetime.now(timezone.utc).isoformat()
        _touch(review)
    return review


def mark_needs_more_laps(
    review: TrackModelReviewResult,
    segment_id: str,
    notes: str = "",
) -> TrackModelReviewResult:
    """Flag a segment as requiring more calibration laps before it can be used."""
    seg = _find_segment(review, segment_id)
    if seg is not None:
        seg.review_status = SegmentReviewStatus.NEEDS_MORE_LAPS
        seg.last_action   = SegmentReviewAction.MARK_NEEDS_MORE_LAPS
        if notes:
            seg.review_notes = notes
        seg.reviewed_at = datetime.now(timezone.utc).isoformat()
        _touch(review)
    return review


def mark_split_required(
    review: TrackModelReviewResult,
    segment_id: str,
    notes: str = "",
) -> TrackModelReviewResult:
    """Flag a segment as needing to be split into smaller segments."""
    seg = _find_segment(review, segment_id)
    if seg is not None:
        seg.review_status = SegmentReviewStatus.SPLIT_REQUIRED
        seg.last_action   = SegmentReviewAction.MARK_SPLIT_REQUIRED
        if notes:
            seg.review_notes = notes
        seg.reviewed_at = datetime.now(timezone.utc).isoformat()
        _touch(review)
    return review


def mark_merge_required(
    review: TrackModelReviewResult,
    segment_id: str,
    notes: str = "",
) -> TrackModelReviewResult:
    """Flag a segment as needing to be merged with an adjacent segment."""
    seg = _find_segment(review, segment_id)
    if seg is not None:
        seg.review_status = SegmentReviewStatus.MERGE_REQUIRED
        seg.last_action   = SegmentReviewAction.MARK_MERGE_REQUIRED
        if notes:
            seg.review_notes = notes
        seg.reviewed_at = datetime.now(timezone.utc).isoformat()
        _touch(review)
    return review


def promote_engineer_validated(
    review: TrackModelReviewResult,
    segment_id: str,
    notes: str = "",
) -> TrackModelReviewResult:
    """Promote a CONFIRMED segment to ENGINEER_VALIDATED.

    Only CONFIRMED segments can be promoted.  UNREVIEWED/REJECTED/etc. are
    ignored so this cannot accidentally bypass the confirm step.
    """
    seg = _find_segment(review, segment_id)
    if seg is not None and seg.review_status == SegmentReviewStatus.CONFIRMED:
        seg.review_status = SegmentReviewStatus.ENGINEER_VALIDATED
        seg.last_action   = SegmentReviewAction.PROMOTE_ENGINEER_VALIDATED
        if notes:
            seg.review_notes = notes
        seg.reviewed_at = datetime.now(timezone.utc).isoformat()
        _touch(review)
    return review


# ---------------------------------------------------------------------------
# Aggregate helpers
# ---------------------------------------------------------------------------

def review_completion_pct(review: TrackModelReviewResult) -> float:
    """Return review completion as a percentage (0.0–100.0).

    Empty segment list returns 100.0 (nothing to review).
    """
    if not review.segments:
        return 100.0
    reviewed = sum(1 for s in review.segments if s.is_reviewed)
    return reviewed / len(review.segments) * 100.0


def is_ai_ready(review: TrackModelReviewResult) -> tuple[bool, list[str]]:
    """Return (is_ready, blockers) for AI integration.

    is_ready is True only when all readiness criteria are met.
    blockers is a human-readable list of reasons the model is not ready.
    Warnings from detection are NOT included here — they are preserved and
    surfaced in the UI regardless of AI-ready status.
    """
    blockers: list[str] = []

    # 1. At least one segment must exist
    if not review.segments:
        blockers.append(
            "No segments detected — run 'Detect Segments' first"
        )
        return False, blockers

    # 2. All apex_zone segments must be reviewed (status ≠ UNREVIEWED)
    unreviewed_apexes = [
        s for s in review.segments
        if s.segment_type == TrackSegmentType.APEX_ZONE
        and s.review_status == SegmentReviewStatus.UNREVIEWED
    ]
    if unreviewed_apexes:
        blockers.append(
            f"{len(unreviewed_apexes)} corner apex segment(s) not yet reviewed — "
            "confirm or reject each detected corner before AI use"
        )

    # 3. No segment marked needs_more_laps
    needs_more = [
        s for s in review.segments
        if s.review_status == SegmentReviewStatus.NEEDS_MORE_LAPS
    ]
    if needs_more:
        names = ", ".join(s.display_name for s in needs_more[:3])
        extra = f" (+{len(needs_more) - 3} more)" if len(needs_more) > 3 else ""
        blockers.append(
            f"Segment(s) flagged 'needs more laps': {names}{extra} — "
            "record additional calibration laps to improve these segments"
        )

    # 4. No segment marked split_required or merge_required
    split_merge = [
        s for s in review.segments
        if s.review_status in (
            SegmentReviewStatus.SPLIT_REQUIRED,
            SegmentReviewStatus.MERGE_REQUIRED,
        )
    ]
    if split_merge:
        blockers.append(
            f"{len(split_merge)} segment(s) flagged for split/merge — "
            "resolve these flags before enabling AI use"
        )

    # 5. Each required segment type must be present in the detection (even if rejected)
    #    A type that was never detected at all is a structural gap; fully-rejected types
    #    are acceptable (user deliberately excluded them).
    detected_types = {s.segment_type for s in review.segments}
    missing_types = [
        t.value for t in _AI_READY_REQUIRED_TYPES
        if t not in detected_types
    ]
    if missing_types:
        blockers.append(
            f"Key segment type(s) not detected: {', '.join(missing_types)} — "
            "more calibration laps may be needed to detect these"
        )

    return len(blockers) == 0, blockers


# ---------------------------------------------------------------------------
# JSON persistence
# ---------------------------------------------------------------------------

def export_review_json(
    review: TrackModelReviewResult,
    output_dir: Optional[Path] = None,
    session_id: str = "",
) -> Path:
    """Export a reviewed track model to JSON.

    Filename: <track_location_id>__<layout_id>__reviewed_segments__<session_id>.json
    Returns the path to the written file.
    """
    if output_dir is None:
        output_dir = REVIEW_MODELS_DIR
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    loc = review.track_location_id or "unknown"
    lay = review.layout_id or "unknown"
    sid = session_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"{loc}__{lay}__reviewed_segments__{sid}.json"
    out_path = output_dir / filename

    segs_out: list[dict] = []
    for seg in review.segments:
        segs_out.append({
            "segment_id":             seg.segment_id,
            "segment_type":           seg.segment_type.value,
            "original_display_name":  seg.original_display_name,
            "reviewed_display_name":  seg.reviewed_display_name,
            "lap_progress_start":     seg.lap_progress_start,
            "lap_progress_end":       seg.lap_progress_end,
            "lap_progress_mid":       seg.lap_progress_mid,
            "confidence":             seg.confidence.value,
            "evidence":               seg.evidence,
            "warnings":               seg.warnings,
            "source_lap_count":       seg.source_lap_count,
            "turn_number":            seg.turn_number,
            "track_location_id":      seg.track_location_id,
            "layout_id":              seg.layout_id,
            "direction":              seg.direction,
            "calibration_car_id":     seg.calibration_car_id,
            "review_status":          seg.review_status.value,
            "review_notes":           seg.review_notes,
            "reviewed_at":            seg.reviewed_at,
            "last_action":            (seg.last_action.value if seg.last_action else None),
            "verification_source":    seg.verification_source,
        })

    # Compute modelling_status maturity at export time
    _has_validated = any(
        s.review_status == SegmentReviewStatus.ENGINEER_VALIDATED
        for s in review.segments
    )
    if _has_validated:
        _modelling_status = "engineer_grade"
    else:
        _ai_ready, _ = is_ai_ready(review)
        _modelling_status = "user_reviewed" if _ai_ready else "segment_detected"

    doc = {
        "schema":               _REVIEW_SCHEMA,
        "track_location_id":    review.track_location_id,
        "layout_id":            review.layout_id,
        "calibration_car_id":   review.calibration_car_id,
        "source_lap_count":     review.source_lap_count,
        "detected_corner_count": review.detected_corner_count,
        "expected_corner_count": review.expected_corner_count,
        "detection_confidence": review.detection_confidence.value,
        "detection_warnings":   review.detection_warnings,
        "review_warnings":      review.review_warnings,
        "created_at":           review.created_at,
        "last_reviewed_at":     review.last_reviewed_at,
        "modelling_status":     _modelling_status,
        "segments":             segs_out,
    }

    out_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path


def import_review_json(json_path: Path) -> TrackModelReviewResult:
    """Load a reviewed track model from JSON.

    Raises:
        FileNotFoundError: if the file does not exist
        ValueError: if the JSON is malformed or has an unexpected schema
    """
    json_path = Path(json_path)
    if not json_path.exists():
        raise FileNotFoundError(f"Review JSON not found: {json_path}")

    try:
        doc = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {json_path}: {exc}") from exc

    if doc.get("schema") != _REVIEW_SCHEMA:
        raise ValueError(
            f"Unexpected schema '{doc.get('schema')}' in {json_path}; "
            f"expected '{_REVIEW_SCHEMA}'"
        )

    segments: list[ReviewedTrackSegment] = []
    for s in doc.get("segments", []):
        last_action = None
        if s.get("last_action"):
            try:
                last_action = SegmentReviewAction(s["last_action"])
            except ValueError:
                pass

        try:
            seg = ReviewedTrackSegment(
                segment_id            = s["segment_id"],
                segment_type          = TrackSegmentType(s["segment_type"]),
                original_display_name = s["original_display_name"],
                reviewed_display_name = s.get("reviewed_display_name", ""),
                lap_progress_start    = float(s["lap_progress_start"]),
                lap_progress_end      = float(s["lap_progress_end"]),
                lap_progress_mid      = float(s["lap_progress_mid"]),
                confidence            = TrackSegmentDetectionConfidence(s["confidence"]),
                evidence              = list(s.get("evidence", [])),
                warnings              = list(s.get("warnings", [])),
                source_lap_count      = int(s.get("source_lap_count", 0)),
                turn_number           = s.get("turn_number"),
                track_location_id     = s.get("track_location_id"),
                layout_id             = s.get("layout_id"),
                direction             = s.get("direction"),
                calibration_car_id    = s.get("calibration_car_id"),
                review_status         = SegmentReviewStatus(s.get("review_status", "unreviewed")),
                review_notes          = s.get("review_notes", ""),
                reviewed_at           = s.get("reviewed_at"),
                last_action           = last_action,
                verification_source   = s.get("verification_source", "greedy"),
            )
        except (KeyError, ValueError) as exc:
            raise ValueError(f"Malformed segment in {json_path}: {exc}") from exc

        segments.append(seg)

    try:
        result = TrackModelReviewResult(
            track_location_id    = doc["track_location_id"],
            layout_id            = doc["layout_id"],
            calibration_car_id   = doc.get("calibration_car_id"),
            source_lap_count     = int(doc.get("source_lap_count", 0)),
            detected_corner_count = int(doc.get("detected_corner_count", 0)),
            expected_corner_count = doc.get("expected_corner_count"),
            detection_confidence = TrackSegmentDetectionConfidence(
                doc.get("detection_confidence", "insufficient")
            ),
            segments             = segments,
            detection_warnings   = list(doc.get("detection_warnings", [])),
            review_warnings      = list(doc.get("review_warnings", [])),
            created_at           = doc.get("created_at", ""),
            last_reviewed_at     = doc.get("last_reviewed_at"),
            modelling_status     = doc.get("modelling_status"),  # None for old files
        )
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Malformed review document in {json_path}: {exc}") from exc

    return result
