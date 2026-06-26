"""Track Issue Enrichment — map telemetry issues to reviewed track segments (Group 17I).

Pure Python, no PyQt6.

Architecture boundary:
  - Reads: data.track_model_resolver (resolved model + segment data)
  - Reads: data.track_calibration (reference path for XYZ→lap_progress lookup)
  - Reads: data.track_segment_review (segment review status/names)
  - Adapts: telemetry.recorder.LapStats and data.corner_learning.CornerIssue
  - Does NOT write any files
  - Does NOT re-detect telemetry issues — enriches existing issues only

Design rules:
  - Never invent corner names for unresolved issues
  - If no reviewed model → confidence is UNRESOLVED
  - If model exists but segment REJECTED → match is UNRESOLVED
  - If segment NEEDS_MORE_LAPS → confidence is LOW
  - Matching priority: segment_id exact > lap_progress range > distance → progress > XYZ nearest > lap_progress nearest > unresolved
  - All resolver exceptions are caught internally — never propagate to callers
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

class TrackIssueType(str, Enum):
    """Telemetry issue category."""
    BRAKE_LOCK              = "brake_lock"
    WHEELSPIN               = "wheelspin"
    OVERSTEER               = "oversteer"
    UNDERSTEER              = "understeer"
    LIMITER_HIT             = "limiter_hit"
    POOR_EXIT_DRIVE         = "poor_exit_drive"
    WRONG_GEAR              = "wrong_gear"
    FUEL_SAVING_OPPORTUNITY = "fuel_saving_opportunity"
    TYRE_WEAR_HOTSPOT       = "tyre_wear_hotspot"
    UNKNOWN                 = "unknown"


class TrackIssuePhase(str, Enum):
    """Track phase where the issue occurred."""
    BRAKING  = "braking"
    ENTRY    = "entry"
    APEX     = "apex"
    EXIT     = "exit"
    TRACTION = "traction"
    STRAIGHT = "straight"
    UNKNOWN  = "unknown"


class TrackIssueEnrichmentConfidence(str, Enum):
    """Confidence level of the segment match."""
    HIGH       = "high"
    MEDIUM     = "medium"
    LOW        = "low"
    UNRESOLVED = "unresolved"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class RawTelemetryIssue:
    """A single telemetry issue with optional location evidence."""
    issue_type: TrackIssueType
    phase: TrackIssuePhase
    lap_num: int
    lap_progress: Optional[float] = None   # 0.0–1.0; None if unknown
    pos_x: Optional[float] = None
    pos_y: Optional[float] = None
    pos_z: Optional[float] = None
    distance_along_lap_m: Optional[float] = None
    segment_id: Optional[str] = None       # direct match if known
    evidence: str = ""


@dataclass
class EnrichedTelemetryIssue:
    """A telemetry issue enriched with reviewed segment context."""
    raw: RawTelemetryIssue
    matched_segment_id: Optional[str] = None
    matched_segment_type: Optional[str] = None   # TrackSegmentType.value
    matched_segment_display_name: str = ""
    matched_segment_lap_progress_mid: Optional[float] = None
    match_method: str = ""  # "segment_id"|"lap_progress"|"distance"|"nearest"|"unresolved"
    confidence: TrackIssueEnrichmentConfidence = TrackIssueEnrichmentConfidence.UNRESOLVED
    setup_implications: list[str] = field(default_factory=list)
    driver_implications: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class TrackIssueEnrichmentResult:
    """Output of enrich_telemetry_issues()."""
    track_location_id: str
    layout_id: str
    enriched_issues: list[EnrichedTelemetryIssue] = field(default_factory=list)
    unresolved_count: int = 0
    model_source: str = "missing"   # "reviewed"|"ai_ready"|"engineer_validated"|"seed_only"|"missing"
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Implication mapping
# ---------------------------------------------------------------------------

_SETUP_IMPLICATIONS: dict[tuple[str, Optional[str]], list[str]] = {
    # (issue_type.value, segment_type.value or None for any)
    ("brake_lock",       "braking_zone"):     ["brake_bias (toward rear)", "LSD braking sensitivity",
                                               "front compression damping", "front ride height"],
    ("brake_lock",       "corner_entry"):     ["brake_bias (toward rear)", "front damping",
                                               "front ride height"],
    ("brake_lock",       None):              ["brake_bias (toward rear)", "front damping"],
    ("wheelspin",        "corner_exit"):     ["LSD acceleration sensitivity", "rear compression damping",
                                              "rear ARB", "rear downforce (if available)", "exit gear ratio"],
    ("wheelspin",        "traction_zone"):   ["LSD acceleration sensitivity", "rear compression damping",
                                              "rear ARB", "rear traction balance"],
    ("wheelspin",        None):              ["LSD acceleration sensitivity", "rear compression damping"],
    ("oversteer",        "corner_exit"):     ["rear downforce (if available)", "rear ARB (soften)",
                                              "rear toe-in", "LSD acceleration sensitivity"],
    ("oversteer",        "apex_zone"):       ["rear ARB (soften)", "rear toe-in",
                                              "LSD acceleration sensitivity"],
    ("oversteer",        None):              ["rear ARB (soften)", "rear toe-in"],
    ("understeer",       "corner_entry"):    ["front springs/ARB (soften)", "front downforce",
                                              "front ride height", "front camber/toe"],
    ("understeer",       "apex_zone"):       ["front springs/ARB (soften)", "front downforce",
                                              "front camber/toe"],
    ("understeer",       None):              ["front springs/ARB (soften)", "front downforce"],
    ("limiter_hit",      "straight"):        ["top gear ratio (lengthen)", "final drive (lengthen)",
                                              "aero drag reduction"],
    ("limiter_hit",      "gear_zone"):       ["top gear ratio (lengthen)", "final drive (lengthen)"],
    ("limiter_hit",      "limiter_zone"):    ["top gear ratio (lengthen)", "final drive (lengthen)"],
    ("limiter_hit",      None):              ["top gear ratio (lengthen)", "final drive (lengthen)"],
    ("poor_exit_drive",  "corner_exit"):     ["LSD acceleration sensitivity", "exit gear selection",
                                              "rear grip balance", "rotation balance"],
    ("poor_exit_drive",  "traction_zone"):   ["LSD acceleration sensitivity", "rear grip balance"],
    ("poor_exit_drive",  None):              ["LSD acceleration sensitivity", "exit gear selection"],
    ("wrong_gear",       "apex_zone"):       ["gearbox spacing (this gear range)"],
    ("wrong_gear",       "corner_exit"):     ["gearbox spacing (exit range)"],
    ("wrong_gear",       None):              ["gearbox spacing"],
    ("fuel_saving_opportunity", "straight"): ["exit gear (one higher)", "throttle map"],
    ("fuel_saving_opportunity", None):       ["throttle map", "exit gear (one higher)"],
    ("tyre_wear_hotspot", None):             ["tyre pressure", "camber (contact patch)", "compound selection"],
    ("unknown",          None):              [],
}

_DRIVER_IMPLICATIONS: dict[tuple[str, Optional[str]], list[str]] = {
    ("brake_lock",       "braking_zone"):    ["brake release technique (progressive)",
                                              "trail braking pressure", "steering while braking"],
    ("brake_lock",       "corner_entry"):    ["brake release technique", "trail braking balance"],
    ("brake_lock",       None):             ["brake release technique"],
    ("wheelspin",        "corner_exit"):    ["throttle pickup timing", "short shift technique",
                                             "steering unwind on exit"],
    ("wheelspin",        "traction_zone"):  ["throttle pickup timing", "smooth progressive application"],
    ("wheelspin",        None):            ["throttle pickup timing"],
    ("oversteer",        "corner_exit"):   ["earlier smoother throttle application",
                                            "trail braking balance"],
    ("oversteer",        "apex_zone"):     ["trail braking balance", "apex commitment"],
    ("oversteer",        None):            ["earlier smoother throttle"],
    ("understeer",       "corner_entry"):  ["corner entry speed (reduce)", "brake trail balance"],
    ("understeer",       "apex_zone"):     ["apex speed and line choice"],
    ("understeer",       None):            ["corner entry speed (reduce)"],
    ("limiter_hit",      "straight"):      ["upshift timing", "fuel map (if applicable)"],
    ("limiter_hit",      None):            ["upshift timing"],
    ("poor_exit_drive",  "corner_exit"):   ["apex speed choice", "throttle timing", "gear choice on exit"],
    ("poor_exit_drive",  None):            ["apex speed and gear choice"],
    ("wrong_gear",       "apex_zone"):     ["gear selection at apex", "drive-out technique"],
    ("wrong_gear",       "corner_exit"):   ["gear selection on exit"],
    ("wrong_gear",       None):            ["gear selection"],
    ("fuel_saving_opportunity", "straight"):["lift-and-coast timing", "throttle modulation"],
    ("fuel_saving_opportunity", None):     ["lift-and-coast technique"],
    ("tyre_wear_hotspot", None):           ["smooth input style at this location", "reduce kerb use"],
    ("unknown",          None):            [],
}


def _get_implications(
    issue_type: TrackIssueType,
    segment_type_value: Optional[str],
) -> tuple[list[str], list[str]]:
    """Return (setup_implications, driver_implications) for an issue+segment combination."""
    key_specific = (issue_type.value, segment_type_value)
    key_generic  = (issue_type.value, None)
    setup  = _SETUP_IMPLICATIONS.get(key_specific, _SETUP_IMPLICATIONS.get(key_generic, []))
    driver = _DRIVER_IMPLICATIONS.get(key_specific, _DRIVER_IMPLICATIONS.get(key_generic, []))
    return list(setup), list(driver)


# ---------------------------------------------------------------------------
# Confidence helpers
# ---------------------------------------------------------------------------

_CONFIDENCE_ORDER = [
    TrackIssueEnrichmentConfidence.UNRESOLVED,
    TrackIssueEnrichmentConfidence.LOW,
    TrackIssueEnrichmentConfidence.MEDIUM,
    TrackIssueEnrichmentConfidence.HIGH,
]


def _downgrade(conf: TrackIssueEnrichmentConfidence, levels: int = 1) -> TrackIssueEnrichmentConfidence:
    idx = _CONFIDENCE_ORDER.index(conf)
    return _CONFIDENCE_ORDER[max(0, idx - levels)]


def _base_confidence_from_source(model_source: str) -> TrackIssueEnrichmentConfidence:
    """Return base confidence from the model source label."""
    if model_source in ("engineer_validated", "ai_ready"):
        return TrackIssueEnrichmentConfidence.HIGH
    if model_source == "reviewed":
        return TrackIssueEnrichmentConfidence.MEDIUM
    if model_source == "seed_only":
        return TrackIssueEnrichmentConfidence.LOW
    return TrackIssueEnrichmentConfidence.UNRESOLVED


# ---------------------------------------------------------------------------
# Reference path helpers (XYZ → lap_progress)
# ---------------------------------------------------------------------------

def _load_reference_path(
    track_location_id: str,
    layout_id: str,
    base_dir: Optional[Path] = None,
):
    """Load the reference path for this track/layout; return None on any error."""
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


def _xyz_to_lap_progress(
    x: float, y: float, z: float,
    ref_path,
) -> Optional[float]:
    """Find the nearest reference path point to (x, y, z) and return its lap_progress.

    Uses XZ distance (ignores Y/elevation) for robustness.
    Returns None if reference path has no points.
    """
    if ref_path is None or not ref_path.points:
        return None
    best_dist = float("inf")
    best_progress = None
    for pt in ref_path.points:
        dx = pt.x - x
        dz = pt.z - z
        d = math.sqrt(dx * dx + dz * dz)
        if d < best_dist:
            best_dist = d
            best_progress = pt.lap_progress
    return best_progress


def _distance_to_lap_progress(
    distance_m: float,
    ref_path,
) -> Optional[float]:
    """Convert a distance_along_lap_m to lap_progress via the reference path."""
    if ref_path is None or not ref_path.points:
        return None
    # Find closest point by distance_along_lap_m
    best_diff = float("inf")
    best_progress = None
    for pt in ref_path.points:
        diff = abs(pt.distance_along_lap_m - distance_m)
        if diff < best_diff:
            best_diff = diff
            best_progress = pt.lap_progress
    return best_progress


# ---------------------------------------------------------------------------
# Segment matching
# ---------------------------------------------------------------------------

def _find_segment_by_id(segment_id: str, segments: list) -> Optional[object]:
    for seg in segments:
        if seg.segment_id == segment_id:
            return seg
    return None


def _find_segment_by_progress(progress: float, segments: list) -> Optional[object]:
    """Return the segment whose [start, end] range contains progress."""
    for seg in segments:
        if seg.lap_progress_start <= progress <= seg.lap_progress_end:
            return seg
    return None


def _find_nearest_segment_by_progress(progress: float, segments: list) -> Optional[object]:
    """Return the segment whose midpoint is nearest to progress."""
    if not segments:
        return None
    return min(segments, key=lambda s: abs(s.lap_progress_mid - progress))


def _segment_review_confidence_ok(seg) -> tuple[bool, Optional[TrackIssueEnrichmentConfidence], str]:
    """Check segment review status; return (is_ok, override_confidence, warning).

    If REJECTED → not OK (UNRESOLVED).
    If NEEDS_MORE_LAPS → LOW.
    If UNREVIEWED → MEDIUM (lower than base).
    Otherwise → keep base confidence.
    """
    try:
        from data.track_segment_review import SegmentReviewStatus
        status = seg.review_status
        if status == SegmentReviewStatus.REJECTED:
            return False, TrackIssueEnrichmentConfidence.UNRESOLVED, "Segment is REJECTED — match invalidated"
        if status == SegmentReviewStatus.NEEDS_MORE_LAPS:
            return True, TrackIssueEnrichmentConfidence.LOW, "Segment needs more calibration laps — confidence reduced"
        if status == SegmentReviewStatus.UNREVIEWED:
            return True, TrackIssueEnrichmentConfidence.MEDIUM, "Segment is unreviewed — confidence capped at MEDIUM"
    except Exception:
        pass
    return True, None, ""


def _match_issue_to_segment(
    issue: RawTelemetryIssue,
    segments: list,
    ref_path,
    model_source: str,
) -> tuple[Optional[object], str, TrackIssueEnrichmentConfidence]:
    """Attempt to match a raw issue to a reviewed segment.

    Returns (matched_segment, match_method, confidence).
    match_method is one of: "segment_id", "lap_progress", "distance", "nearest", "unresolved"
    """
    base_conf = _base_confidence_from_source(model_source)

    if base_conf == TrackIssueEnrichmentConfidence.UNRESOLVED or not segments:
        return None, "unresolved", TrackIssueEnrichmentConfidence.UNRESOLVED

    # Priority 1: exact segment_id match
    if issue.segment_id:
        seg = _find_segment_by_id(issue.segment_id, segments)
        if seg is not None:
            ok, override, warn = _segment_review_confidence_ok(seg)
            if not ok:
                return seg, "segment_id", TrackIssueEnrichmentConfidence.UNRESOLVED
            conf = override if override is not None else base_conf
            return seg, "segment_id", conf

    # Resolve lap_progress from various sources
    resolved_progress: Optional[float] = issue.lap_progress

    # Priority 2a: lap_progress provided directly → match by range
    if resolved_progress is not None:
        seg = _find_segment_by_progress(resolved_progress, segments)
        if seg is not None:
            ok, override, warn = _segment_review_confidence_ok(seg)
            if not ok:
                return seg, "unresolved", TrackIssueEnrichmentConfidence.UNRESOLVED
            conf = override if override is not None else base_conf
            return seg, "lap_progress", conf

    # Priority 2b: distance_along_lap_m → convert via reference path → match by range
    if issue.distance_along_lap_m is not None and ref_path is not None:
        p = _distance_to_lap_progress(issue.distance_along_lap_m, ref_path)
        if p is not None:
            seg = _find_segment_by_progress(p, segments)
            if seg is not None:
                ok, override, warn = _segment_review_confidence_ok(seg)
                if not ok:
                    return seg, "unresolved", TrackIssueEnrichmentConfidence.UNRESOLVED
                conf = override if override is not None else _downgrade(base_conf)
                return seg, "distance", conf

    # Priority 3: XYZ → nearest reference path point → lap_progress → match by range
    if issue.pos_x is not None and issue.pos_z is not None and ref_path is not None:
        p = _xyz_to_lap_progress(
            issue.pos_x, issue.pos_y or 0.0, issue.pos_z, ref_path
        )
        if p is not None:
            resolved_progress = p
            seg = _find_segment_by_progress(p, segments)
            if seg is not None:
                ok, override, warn = _segment_review_confidence_ok(seg)
                if not ok:
                    return seg, "unresolved", TrackIssueEnrichmentConfidence.UNRESOLVED
                conf = override if override is not None else _downgrade(base_conf)
                return seg, "nearest", conf

    # Priority 4: if we have any resolved_progress, find nearest segment by midpoint
    if resolved_progress is not None:
        seg = _find_nearest_segment_by_progress(resolved_progress, segments)
        if seg is not None:
            ok, override, warn = _segment_review_confidence_ok(seg)
            if not ok:
                return seg, "unresolved", TrackIssueEnrichmentConfidence.UNRESOLVED
            # Nearest fallback → always downgrade
            conf = override if override is not None else _downgrade(base_conf)
            return seg, "nearest", conf

    return None, "unresolved", TrackIssueEnrichmentConfidence.UNRESOLVED


# ---------------------------------------------------------------------------
# Main enrichment function
# ---------------------------------------------------------------------------

def enrich_telemetry_issues(
    raw_issues: list[RawTelemetryIssue],
    track_location_id: str,
    layout_id: str,
    base_dir: Optional[Path] = None,
) -> TrackIssueEnrichmentResult:
    """Enrich a list of raw telemetry issues with reviewed segment context.

    Resolves the best available track model for the given track/layout.
    Never raises — all errors are captured in result.warnings.
    """
    result_warnings: list[str] = []
    enriched: list[EnrichedTelemetryIssue] = []
    model_source = "missing"
    segments: list = []

    # Resolve model
    resolved_model = None
    try:
        from data.track_model_resolver import resolve_best_track_model, TrackModelSourceType
        resolver_result = resolve_best_track_model(track_location_id, layout_id, base_dir)
        rm = resolver_result.resolved_model
        if rm is not None:
            source = rm.source_type
            if source == TrackModelSourceType.ENGINEER_VALIDATED_MODEL:
                model_source = "engineer_validated"
            elif source == TrackModelSourceType.AI_READY_REVIEWED_MODEL:
                model_source = "ai_ready"
            elif source == TrackModelSourceType.REVIEWED_MODEL:
                model_source = "reviewed"
            elif source == TrackModelSourceType.SEED_ONLY:
                model_source = "seed_only"
            else:
                model_source = "missing"
            resolved_model = rm
            if rm.reviewed_model is not None:
                segments = list(rm.reviewed_model.segments)
        if resolver_result.warnings:
            result_warnings.extend(resolver_result.warnings)
    except Exception as exc:
        result_warnings.append(f"Resolver error: {exc}")

    # Load reference path (for XYZ→lap_progress)
    ref_path = None
    if track_location_id and layout_id:
        ref_path = _load_reference_path(track_location_id, layout_id, base_dir)

    if not segments:
        if model_source in ("seed_only", "missing"):
            result_warnings.append(
                "No reviewed segments available — all issues are UNRESOLVED. "
                "Enrich after completing segment detection and review."
            )
        else:
            result_warnings.append("Reviewed model has no segments — cannot match issues.")

    unresolved_count = 0

    for raw in raw_issues:
        matched_seg, match_method, confidence = _match_issue_to_segment(
            raw, segments, ref_path, model_source
        )

        warn: list[str] = []
        setup_impl: list[str] = []
        driver_impl: list[str] = []
        seg_id: Optional[str] = None
        seg_type: Optional[str] = None
        seg_name: str = ""
        seg_mid: Optional[float] = None

        if matched_seg is not None and match_method != "unresolved":
            seg_id   = matched_seg.segment_id
            seg_type = matched_seg.segment_type.value if hasattr(matched_seg.segment_type, "value") else str(matched_seg.segment_type)
            seg_name = matched_seg.display_name if hasattr(matched_seg, "display_name") else matched_seg.segment_id
            seg_mid  = matched_seg.lap_progress_mid

            # Segment status warnings
            _, _, seg_warn = _segment_review_confidence_ok(matched_seg)
            if seg_warn:
                warn.append(seg_warn)

            # Build implications
            setup_impl, driver_impl = _get_implications(raw.issue_type, seg_type)
        else:
            unresolved_count += 1
            warn.append(
                "No reviewed segment matched — do not invent a corner name. "
                "Use raw evidence only."
            )
            if model_source in ("seed_only", "missing"):
                warn.append(
                    f"Model source is {model_source} — segment matching requires a reviewed model."
                )

        enriched.append(EnrichedTelemetryIssue(
            raw=raw,
            matched_segment_id=seg_id,
            matched_segment_type=seg_type,
            matched_segment_display_name=seg_name,
            matched_segment_lap_progress_mid=seg_mid,
            match_method=match_method,
            confidence=confidence,
            setup_implications=setup_impl,
            driver_implications=driver_impl,
            warnings=warn,
        ))

    return TrackIssueEnrichmentResult(
        track_location_id=track_location_id,
        layout_id=layout_id,
        enriched_issues=enriched,
        unresolved_count=unresolved_count,
        model_source=model_source,
        warnings=result_warnings,
    )


# ---------------------------------------------------------------------------
# Repeat issue grouping and prompt summary
# ---------------------------------------------------------------------------

def summarise_enriched_issues_for_prompt(
    enriched_issues: list[EnrichedTelemetryIssue],
) -> str:
    """Produce a compact AI-ready summary of enriched issues grouped by segment and type.

    - Groups by (segment_display_name, issue_type)
    - Counts unique lap numbers
    - Never invents corner names for unresolved issues
    - Returns empty string if no issues
    """
    if not enriched_issues:
        return ""

    # Group resolved issues
    resolved_groups: dict[tuple[str, str], list[EnrichedTelemetryIssue]] = {}
    unresolved_by_type: dict[str, list[EnrichedTelemetryIssue]] = {}

    for ei in enriched_issues:
        if ei.confidence == TrackIssueEnrichmentConfidence.UNRESOLVED or not ei.matched_segment_id:
            key = ei.raw.issue_type.value
            unresolved_by_type.setdefault(key, []).append(ei)
        else:
            key = (ei.matched_segment_display_name, ei.raw.issue_type.value)
            resolved_groups.setdefault(key, []).append(ei)

    lines: list[str] = ["## Track-Located Telemetry Issues"]

    if not resolved_groups and not unresolved_by_type:
        return ""

    for (seg_name, issue_type), group in sorted(
        resolved_groups.items(), key=lambda kv: (kv[0][0], kv[0][1])
    ):
        laps = sorted({ei.raw.lap_num for ei in group})
        conf = _best_confidence(group)
        lap_str = ", ".join(f"L{n}" for n in laps[:8])
        if len(laps) > 8:
            lap_str += f" … ({len(laps)} total)"
        lines.append(
            f"{seg_name} — {issue_type}: {len(laps)} lap(s) ({lap_str}) [confidence: {conf}]"
        )
        # Setup implications (first group member)
        setup = group[0].setup_implications
        driver = group[0].driver_implications
        if setup:
            lines.append(f"  Setup areas: {', '.join(setup[:4])}")
        if driver:
            lines.append(f"  Driver focus: {', '.join(driver[:3])}")

    if unresolved_by_type:
        lines.append("")
        lines.append("Unresolved (no segment match — do not invent corner names):")
        for issue_type, group in sorted(unresolved_by_type.items()):
            laps = sorted({ei.raw.lap_num for ei in group})
            lap_str = ", ".join(f"L{n}" for n in laps[:6])
            lines.append(f"  {issue_type}: {len(group)} event(s), lap(s): {lap_str}")

    return "\n".join(lines)


def _best_confidence(group: list[EnrichedTelemetryIssue]) -> str:
    """Return the best confidence across a group of enriched issues."""
    order = [c.value for c in _CONFIDENCE_ORDER]
    best = "unresolved"
    for ei in group:
        v = ei.confidence.value
        if order.index(v) > order.index(best):
            best = v
    return best


# ---------------------------------------------------------------------------
# Adapters: LapStats → RawTelemetryIssue
# ---------------------------------------------------------------------------

def issues_from_lap_stats(
    laps: list,
    include_single_events: bool = True,
) -> list[RawTelemetryIssue]:
    """Convert a list of LapStats objects to RawTelemetryIssue instances.

    Extracts position-tagged events: lock_up, wheelspin, oversteer,
    snap_throttle (→ wheelspin/traction), over_braking (→ brake_lock).

    include_single_events: if False, only includes events that appear
    in 2+ laps (reduces noise).  Default True for compatibility.
    """
    issues: list[RawTelemetryIssue] = []
    for lap in laps:
        lap_num = getattr(lap, "lap_num", 0)

        for xyz in getattr(lap, "lock_up_positions", []):
            if len(xyz) >= 3:
                issues.append(RawTelemetryIssue(
                    issue_type=TrackIssueType.BRAKE_LOCK,
                    phase=TrackIssuePhase.BRAKING,
                    lap_num=lap_num,
                    pos_x=float(xyz[0]), pos_y=float(xyz[1]), pos_z=float(xyz[2]),
                    evidence=f"lock_up at lap {lap_num}",
                ))

        for xyz in getattr(lap, "wheelspin_positions", []):
            if len(xyz) >= 3:
                issues.append(RawTelemetryIssue(
                    issue_type=TrackIssueType.WHEELSPIN,
                    phase=TrackIssuePhase.TRACTION,
                    lap_num=lap_num,
                    pos_x=float(xyz[0]), pos_y=float(xyz[1]), pos_z=float(xyz[2]),
                    evidence=f"wheelspin at lap {lap_num}",
                ))

        for xyz in getattr(lap, "oversteer_positions", []):
            if len(xyz) >= 3:
                issues.append(RawTelemetryIssue(
                    issue_type=TrackIssueType.OVERSTEER,
                    phase=TrackIssuePhase.EXIT,
                    lap_num=lap_num,
                    pos_x=float(xyz[0]), pos_y=float(xyz[1]), pos_z=float(xyz[2]),
                    evidence=f"oversteer at lap {lap_num}",
                ))

        for xyz in getattr(lap, "snap_throttle_positions", []):
            if len(xyz) >= 3:
                issues.append(RawTelemetryIssue(
                    issue_type=TrackIssueType.WHEELSPIN,
                    phase=TrackIssuePhase.TRACTION,
                    lap_num=lap_num,
                    pos_x=float(xyz[0]), pos_y=float(xyz[1]), pos_z=float(xyz[2]),
                    evidence=f"snap_throttle at lap {lap_num}",
                ))

        for xyz in getattr(lap, "over_braking_positions", []):
            if len(xyz) >= 3:
                issues.append(RawTelemetryIssue(
                    issue_type=TrackIssueType.BRAKE_LOCK,
                    phase=TrackIssuePhase.BRAKING,
                    lap_num=lap_num,
                    pos_x=float(xyz[0]), pos_y=float(xyz[1]), pos_z=float(xyz[2]),
                    evidence=f"over_braking at lap {lap_num}",
                ))

    return issues


# ---------------------------------------------------------------------------
# Adapters: CornerIssue → RawTelemetryIssue
# ---------------------------------------------------------------------------

_CORNER_ISSUE_TYPE_MAP: dict[str, TrackIssueType] = {
    "brake_lock":                  TrackIssueType.BRAKE_LOCK,
    "rear_wheelspin":              TrackIssueType.WHEELSPIN,
    "traction_loss":               TrackIssueType.WHEELSPIN,
    "rear_oversteer":              TrackIssueType.OVERSTEER,
    "exit_instability":            TrackIssueType.OVERSTEER,
    "front_understeer":            TrackIssueType.UNDERSTEER,
    "poor_drive_out":              TrackIssueType.POOR_EXIT_DRIVE,
    "exit_gear_too_low":           TrackIssueType.WRONG_GEAR,
    "exit_gear_too_high":          TrackIssueType.WRONG_GEAR,
    "early_limiter_on_straight":   TrackIssueType.LIMITER_HIT,
    "late_upshift":                TrackIssueType.LIMITER_HIT,
    "early_upshift":               TrackIssueType.LIMITER_HIT,
    "fuel_inefficient_gear_choice":TrackIssueType.FUEL_SAVING_OPPORTUNITY,
    "tyre_overheat":               TrackIssueType.TYRE_WEAR_HOTSPOT,
    "fuel_loss":                   TrackIssueType.FUEL_SAVING_OPPORTUNITY,
    "unstable_downshift":          TrackIssueType.WRONG_GEAR,
}

_CORNER_PHASE_MAP: dict[str, TrackIssuePhase] = {
    "braking":           TrackIssuePhase.BRAKING,
    "entry":             TrackIssuePhase.ENTRY,
    "apex":              TrackIssuePhase.APEX,
    "exit":              TrackIssuePhase.EXIT,
    "mid_corner":        TrackIssuePhase.APEX,
    "following_straight":TrackIssuePhase.STRAIGHT,
}


def _decode_corner_id(corner_id: str) -> tuple[Optional[float], Optional[float]]:
    """Decode a corner_id like 'P500_-200' to (x, z) world coordinates.

    Returns (None, None) if format is not recognised.
    """
    try:
        if not corner_id.startswith("P"):
            return None, None
        rest = corner_id[1:]
        parts = rest.rsplit("_", 1)
        if len(parts) != 2:
            return None, None
        x = float(parts[0])
        z = float(parts[1])
        return x, z
    except (ValueError, IndexError):
        return None, None


def issues_from_corner_issues(
    corner_issues: list,
) -> list[RawTelemetryIssue]:
    """Convert CornerIssue objects (from data.corner_learning) to RawTelemetryIssue.

    Decodes the corner_id (XZ grid bucket) to approximate world position.
    """
    issues: list[RawTelemetryIssue] = []
    for ci in corner_issues:
        issue_type = _CORNER_ISSUE_TYPE_MAP.get(
            getattr(ci, "issue_type", ""), TrackIssueType.UNKNOWN
        )
        phase = _CORNER_PHASE_MAP.get(
            getattr(ci, "phase", ""), TrackIssuePhase.UNKNOWN
        )
        x, z = _decode_corner_id(getattr(ci, "corner_id", ""))
        issues.append(RawTelemetryIssue(
            issue_type=issue_type,
            phase=phase,
            lap_num=0,  # CornerIssue aggregates across laps; use 0 as sentinel
            pos_x=x,
            pos_y=None,
            pos_z=z,
            evidence=getattr(ci, "evidence", ""),
        ))
    return issues
