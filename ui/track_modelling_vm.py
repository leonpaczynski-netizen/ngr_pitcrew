"""Track Modelling view model — pure Python helpers, no PyQt6 dependency.

Provides formatted data tuples for the Track Modelling UI tab and for
tests that verify display logic without needing a running Qt application.
"""
from __future__ import annotations
from typing import Optional

from data.track_intelligence import (
    TrackLocationSeed,
    TrackLayoutSeed,
    CalibrationCarProfile,
    TrackModellingStatus,
    TrackSeedLoadResult,
    build_seed_track_context_for_prompt,
    load_track_seed,
    get_track_locations,
)

# Sentinel text for fields that have no seed data yet
UNKNOWN_VALUE = "Unknown / needs calibration"

# Modelling status values that mean "no telemetry yet"
_SEED_ONLY_STATUSES = {
    TrackModellingStatus.NOT_MODELLED,
    TrackModellingStatus.SEED_ONLY,
}

# Boundary note shown beneath the calibration car panel
CALIBRATION_CAR_BOUNDARY_NOTE = (
    "The Porsche 911 RSR (991) '17 is used for consistent tarmac modelling. "
    "Track geometry remains car-independent. "
    "Braking points, gear usage, throttle behaviour, and tyre stress are "
    "Porsche RSR calibration behaviour — not universal track truth."
)

SEED_WARNING_TEXT = (
    "SEED DATA ONLY — This layout has not been telemetry-calibrated.\n"
    "Corner/segment/camber/kerb/elevation details are NOT validated.\n"
    "Public data is a starting point only. "
    "Do not treat seed facts as engineering truth."
)


def _fmt_bool(val: Optional[bool]) -> str:
    if val is None:
        return UNKNOWN_VALUE
    return "Yes" if val else "No"


def _fmt_float(val: Optional[float], suffix: str = "") -> str:
    if val is None:
        return UNKNOWN_VALUE
    return f"{val}{suffix}"


def _fmt_int(val: Optional[int], suffix: str = "") -> str:
    if val is None:
        return UNKNOWN_VALUE
    return f"{val}{suffix}"


def _fmt_str(val: Optional[str]) -> str:
    if val is None or val == "":
        return UNKNOWN_VALUE
    return val


def format_layout_facts(
    layout: TrackLayoutSeed,
    loc: TrackLocationSeed,
) -> list[tuple[str, str]]:
    """Return (label, value) pairs for the layout facts panel.

    All fields are always included. Unknown values are shown as UNKNOWN_VALUE
    so the user can see what has not yet been calibrated.
    """
    aliases = ", ".join(loc.aliases) if loc.aliases else UNKNOWN_VALUE
    return [
        # ── Location ──────────────────────────────────────────────────────
        ("Track Location",      loc.display_name),
        ("Location ID",         loc.track_location_id),
        ("Aliases",             aliases),
        ("Country",             _fmt_str(loc.country)),
        ("Region",              _fmt_str(loc.region)),
        ("Classification",      _fmt_str(loc.real_or_fictional)),
        ("Surface",             _fmt_str(loc.surface)),
        ("Track Type",          _fmt_str(loc.track_type)),
        # ── Layout ────────────────────────────────────────────────────────
        ("Layout",              layout.display_name),
        ("Layout ID",           layout.layout_id),
        ("Direction",           _fmt_str(layout.direction)),
        ("Length",              _fmt_float(layout.length_m, " m")),
        ("Corners",             _fmt_int(layout.corners_expected)),
        ("Sectors",             _fmt_int(layout.sectors)),
        ("Longest Straight",    _fmt_float(layout.longest_straight_m, " m")),
        ("Elevation Change",    _fmt_float(layout.elevation_change_m, " m")),
        ("Avg Gradient",        _fmt_float(layout.average_gradient_percent, " %")),
        ("Pit Delta",           _fmt_int(layout.pit_delta_seconds, " s")),
        ("Reversible",          _fmt_bool(layout.reversible)),
        ("Rain Supported",      _fmt_bool(layout.rain_supported)),
        ("Night Supported",     _fmt_bool(layout.night_supported)),
        ("24h Supported",       _fmt_bool(layout.full_24h_supported)),
        # ── Modelling / source ────────────────────────────────────────────
        ("Modelling Status",    layout.modelling_status.value),
        ("Validation Status",   _fmt_str(layout.validation_status)),
        ("Source Confidence",   _fmt_str(layout.source_confidence)),
        ("Source URL",          _fmt_str(layout.source_url)),
        ("Notes",               _fmt_str(layout.notes)),
    ]


def format_readiness(layout: TrackLayoutSeed) -> list[tuple[str, str]]:
    """Return (label, value) pairs for the calibration readiness panel."""
    status = layout.modelling_status
    is_seed = status in _SEED_ONLY_STATUSES
    ready_cal = status.is_ready_for_calibration()
    ready_ai = status.is_ready_for_ai()
    missing = status.missing_calibration_requirements()

    rows: list[tuple[str, str]] = [
        ("Modelling Status",        status.value),
        ("Seed Data Only",          "Yes" if is_seed else "No"),
        ("Ready for Calibration",   "Yes" if ready_cal else "No — telemetry laps needed"),
        ("Ready for AI Use",        "Yes" if ready_ai else "No — segments not yet detected"),
        ("Missing Steps",           f"{len(missing)} remaining" if missing else "None — engineer grade"),
    ]
    for i, step in enumerate(missing, 1):
        rows.append((f"  Step {i}", step))
    return rows


def format_calibration_car(car: CalibrationCarProfile) -> list[tuple[str, str]]:
    """Return (label, value) pairs for the calibration car panel."""
    rows: list[tuple[str, str]] = [
        ("Car",         car.display_name),
        ("Class",       car.car_class),
        ("Drivetrain",  car.drivetrain),
        ("Power",       f"{car.stock_power_bhp} BHP"),
        ("Weight",      f"{car.stock_weight_kg} kg"),
        ("Tyres",       car.stock_tyres),
        ("Purpose",     car.purpose),
    ]
    if car.stock_pp:
        rows.append(("PP (stock)", str(car.stock_pp)))
    return rows


def get_seed_warning_text(layout: Optional[TrackLayoutSeed]) -> str:
    """Return the appropriate warning text for the selected layout (or a generic warning)."""
    if layout is None:
        return "No layout selected."
    if layout.modelling_status in _SEED_ONLY_STATUSES:
        return SEED_WARNING_TEXT
    if not layout.modelling_status.is_ready_for_ai():
        return (
            "PARTIAL TELEMETRY — Telemetry has been recorded but segment detection "
            "is not complete. Corner phase data may be missing or incomplete."
        )
    return ""


def is_seed_only(layout: Optional[TrackLayoutSeed]) -> bool:
    """True if the layout has not yet had any telemetry recorded."""
    if layout is None:
        return True
    return layout.modelling_status in _SEED_ONLY_STATUSES


def build_location_display_items(
    seed_result: TrackSeedLoadResult,
) -> list[tuple[str, str]]:
    """Return (display_text, track_location_id) pairs for populating a combo box.

    Sorted alphabetically by display name.
    """
    if not seed_result.success:
        return []
    items = [
        (loc.display_name, loc.track_location_id)
        for loc in seed_result.track_locations
    ]
    return sorted(items, key=lambda t: t[0])


def build_layout_display_items(
    seed_result: TrackSeedLoadResult,
    track_location_id: str,
) -> list[tuple[str, str]]:
    """Return (display_text, layout_id) pairs for the layouts of one location.

    Preserves seed order (forward layouts first, then reverses).
    """
    if not seed_result.success:
        return []
    for loc in seed_result.track_locations:
        if loc.track_location_id == track_location_id:
            return [(lay.display_name, lay.layout_id) for lay in loc.layouts]
    return []


def get_selected_location(
    seed_result: TrackSeedLoadResult,
    track_location_id: str,
) -> Optional[TrackLocationSeed]:
    """Resolve a track_location_id to its TrackLocationSeed, or None."""
    for loc in seed_result.track_locations:
        if loc.track_location_id == track_location_id:
            return loc
    return None


def get_selected_layout(
    seed_result: TrackSeedLoadResult,
    track_location_id: str,
    layout_id: str,
) -> Optional[TrackLayoutSeed]:
    """Resolve location + layout IDs to a TrackLayoutSeed, or None."""
    loc = get_selected_location(seed_result, track_location_id)
    if loc is None:
        return None
    for lay in loc.layouts:
        if lay.layout_id == layout_id:
            return lay
    return None


def build_prompt_preview(
    seed_result: TrackSeedLoadResult,
    track_location_id: str,
    layout_id: str,
) -> str:
    """Build the seed-only AI prompt preview text for a layout."""
    if not seed_result.success:
        errors = "; ".join(seed_result.errors)
        return f"[Seed load failed]\n{errors}"
    if not track_location_id or not layout_id:
        return "Select a track location and layout to preview the AI prompt context."
    return build_seed_track_context_for_prompt(track_location_id, layout_id)


def describe_seed_load_status(seed_result: TrackSeedLoadResult) -> str:
    """Return a one-line status string describing the seed load result."""
    if not seed_result.success:
        return f"Seed load FAILED: {'; '.join(seed_result.errors)}"
    meta = seed_result.metadata
    n_loc = len(seed_result.track_locations)
    n_lay = sum(len(loc.layouts) for loc in seed_result.track_locations)
    version = meta.schema_version if meta else "?"
    warns = len(seed_result.warnings)
    warn_str = f" | {warns} warning(s)" if warns else ""
    return f"Seed v{version} — {n_loc} locations, {n_lay} layouts loaded{warn_str}"


# ---------------------------------------------------------------------------
# Group 17F — Segment Review view-model helpers
# ---------------------------------------------------------------------------

# These helpers import from data.track_segment_review lazily (inside functions)
# so that the view model module stays importable in tests without PyQt6.

_REVIEW_STATUS_LABELS: dict[str, str] = {
    "unreviewed":         "— Unreviewed",
    "confirmed":          "✓ Confirmed",
    "renamed":            "✎ Renamed",
    "rejected":           "✕ Rejected",
    "needs_more_laps":    "⚠ More laps",
    "split_required":     "⟂ Split required",
    "merge_required":     "⇔ Merge required",
    "engineer_validated": "★ Validated",
}


def format_segment_row(seg: object) -> dict[str, str]:
    """Return display values for one row in the segment review table.

    ``seg`` is a ReviewedTrackSegment instance (typed as object to avoid a
    mandatory import at module level).
    """
    status_key = getattr(seg, "review_status", None)
    status_val = status_key.value if hasattr(status_key, "value") else str(status_key)
    status_display = _REVIEW_STATUS_LABELS.get(status_val, status_val)

    turn = seg.turn_number  # type: ignore[attr-defined]
    turn_str = f"T{turn}" if turn is not None else ""

    warnings: list[str] = list(getattr(seg, "warnings", []))
    warnings_str = " | ".join(warnings) if warnings else ""

    seg_type = getattr(seg, "segment_type", None)
    type_val = seg_type.value if hasattr(seg_type, "value") else str(seg_type)

    conf = getattr(seg, "confidence", None)
    conf_val = conf.value if hasattr(conf, "value") else str(conf)

    _VERIFICATION_SOURCE_LABELS: dict[str, str] = {
        "greedy":             "Curvature-detected",
        "ai_verified":        "AI-verified",
        "engineer_validated": "Engineer-validated",
    }
    raw_vs = getattr(seg, "verification_source", "greedy") or "greedy"
    verification_source_display = _VERIFICATION_SOURCE_LABELS.get(raw_vs, raw_vs)

    return {
        "name":                seg.display_name,  # type: ignore[attr-defined]
        "turn":                turn_str,
        "type":                type_val,
        "progress":            f"{seg.lap_progress_start:.1%}–{seg.lap_progress_end:.1%}",  # type: ignore[attr-defined]
        "confidence":          conf_val,
        "laps":                str(getattr(seg, "source_lap_count", 0)),
        "status":              status_display,
        "warnings":            warnings_str,
        "verification_source": verification_source_display,
    }


def format_review_summary(review: Optional[object]) -> dict[str, str]:
    """Return display values for the review approval panel.

    ``review`` is a TrackModelReviewResult or None.  Returns all "—" when None.
    """
    if review is None:
        return {
            "detected":       "—",
            "reviewed":       "—",
            "confirmed":      "—",
            "rejected":       "—",
            "needs_more_laps": "—",
            "completion_pct": "—",
            "ai_ready":       "—",
            "blockers":       "",
        }

    from data.track_segment_review import (
        SegmentReviewStatus,
        review_completion_pct,
        is_ai_ready,
    )

    segs = list(getattr(review, "segments", []))
    total = len(segs)

    _confirmed_statuses = {
        SegmentReviewStatus.CONFIRMED,
        SegmentReviewStatus.RENAMED,
        SegmentReviewStatus.ENGINEER_VALIDATED,
    }

    reviewed_count   = sum(1 for s in segs if getattr(s, "is_reviewed", False))
    confirmed_count  = sum(1 for s in segs if s.review_status in _confirmed_statuses)
    rejected_count   = sum(1 for s in segs
                           if s.review_status == SegmentReviewStatus.REJECTED)
    needs_laps_count = sum(1 for s in segs
                           if s.review_status == SegmentReviewStatus.NEEDS_MORE_LAPS)
    pct  = review_completion_pct(review)  # type: ignore[arg-type]
    ready, blockers = is_ai_ready(review)  # type: ignore[arg-type]

    return {
        "detected":       str(total),
        "reviewed":       str(reviewed_count),
        "confirmed":      str(confirmed_count),
        "rejected":       str(rejected_count),
        "needs_more_laps": str(needs_laps_count),
        "completion_pct": f"{pct:.0f}%",
        "ai_ready":       "Yes" if ready else "No",
        "blockers":       "\n".join(blockers) if blockers else "",
    }


def format_resolver_summary(resolver_result: Optional[object]) -> dict[str, str]:
    """Return display values for the resolver status panel.

    Keys: source_type, modelling_status, ai_ready, blockers, model_path,
          warnings, resolution_status, candidate_count.

    All values are human-readable strings.  Returns all "—" when resolver_result
    is None.  Imports from data.track_model_resolver lazily.
    """
    _empty = {
        "source_type":       "—",
        "modelling_status":  "—",
        "ai_ready":          "—",
        "blockers":          "",
        "model_path":        "—",
        "warnings":          "",
        "resolution_status": "—",
        "candidate_count":   "—",
    }
    if resolver_result is None:
        return _empty

    res_status = getattr(resolver_result, "resolution_status", None)
    res_status_str = res_status.value if hasattr(res_status, "value") else str(res_status)

    candidates = list(getattr(resolver_result, "all_candidate_paths", []))
    resolved = getattr(resolver_result, "resolved_model", None)

    if resolved is None:
        return {**_empty, "resolution_status": res_status_str,
                "candidate_count": str(len(candidates))}

    source_type = getattr(resolved, "source_type", None)
    source_str  = source_type.value if hasattr(source_type, "value") else str(source_type)

    source_labels = {
        "seed_only":                "Seed only (no reviewed model)",
        "detected_unreviewed":      "Detected (not reviewed)",
        "reviewed_model":           "Reviewed — not AI-ready",
        "ai_ready_reviewed_model":  "Reviewed — AI-ready",
        "engineer_validated_model": "Engineer-validated",
        "missing":                  "Missing",
    }
    source_display = source_labels.get(source_str, source_str)

    blockers   = list(getattr(resolved, "blockers", []))
    warn_list  = list(getattr(resolved, "warnings", []))
    src_path   = getattr(resolved, "source_path", None)
    path_str   = src_path.name if src_path is not None else "—"

    return {
        "source_type":       source_display,
        "modelling_status":  str(getattr(resolved, "modelling_status", "—") or "—"),
        "ai_ready":          "Yes" if getattr(resolved, "ai_ready", False) else "No",
        "blockers":          "\n".join(blockers) if blockers else "",
        "model_path":        path_str,
        "warnings":          "\n".join(warn_list[:3]) if warn_list else "",
        "resolution_status": res_status_str,
        "candidate_count":   str(len(candidates)),
    }


def get_review_button_states(
    review: Optional[object],
    selected_segment_id: Optional[str],
) -> dict[str, bool]:
    """Return enabled/disabled state for each review action button.

    Keys: confirm, rename, reject, needs_more_laps, split_required,
          merge_required, save.
    """
    if review is None:
        return {k: False for k in (
            "confirm", "rename", "reject",
            "needs_more_laps", "split_required", "merge_required", "save",
        )}

    segs = list(getattr(review, "segments", []))
    has_selection = selected_segment_id is not None
    has_reviewed  = any(getattr(s, "is_reviewed", False) for s in segs)

    return {
        "confirm":        has_selection,
        "rename":         has_selection,
        "reject":         has_selection,
        "needs_more_laps": has_selection,
        "split_required": has_selection,
        "merge_required": has_selection,
        "save":           has_reviewed,
    }


# ---------------------------------------------------------------------------
# Group 17M — Runtime UAT and Calibration Workflow Hardening
# ---------------------------------------------------------------------------

_WORKFLOW_ERROR_MESSAGES: dict[str, str] = {
    "no_gt7_telemetry":
        "No GT7 telemetry packets received. Check GT7 Settings → Network → Remote Play IP.",
    "no_track_selected":
        "No track/layout selected. Choose a location and layout before starting calibration.",
    "seed_file_missing":
        "Seed data file not found. Check data/tracks_seed.yaml exists and is readable.",
    "no_usable_laps":
        "No usable laps captured. Check for insufficient samples, high off-track fraction, "
        "or coordinate jumps. Run more complete laps.",
    "build_failed":
        "Reference path build failed. At least 2 usable calibration laps are required.",
    "segment_detection_failed":
        "Segment detection failed. Ensure the reference path is built and saved first.",
    "no_reviewed_model":
        "No reviewed track model found. Complete calibration, detect segments, and save a "
        "reviewed model before live segment resolution is available.",
    "malformed_review_file":
        "Reviewed model file is malformed or unreadable. Re-run segment detection and re-save.",
    "missing_track_length":
        "Track length not available for offset mapping. Check seed data or build/save a "
        "reference path first.",
    "road_distance_unavailable":
        "GT7 road_distance field is not present in the current packet. Check telemetry "
        "connection and confirm the car is on track.",
    "live_segment_unresolved":
        "Live segment resolution failed. Ensure a reviewed model exists, the car is on track, "
        "and the selected track/layout matches the active GT7 session.",
}


def get_workflow_error_message(error_key: str) -> str:
    """Return a safe, user-readable error message for a workflow failure state."""
    return _WORKFLOW_ERROR_MESSAGES.get(error_key, f"Unknown error state: {error_key}")


def get_calibration_button_states(
    ctrl_state: str,
    has_track: bool,
    has_completed_laps: bool,
    has_ref_path: bool,
    has_review_model: bool,
    selected_segment_id: Optional[str] = None,
    has_track_length: bool = False,
) -> dict[str, bool]:
    """Return enabled/disabled state for all Track Modelling workflow buttons.

    Pure Python — no PyQt6 dependency.  Uses CalibrationCaptureState string values.

    Args:
        ctrl_state:          CalibrationCaptureState.value
                             ("inactive"/"recording"/"stopped"/"built"/"error")
        has_track:           True when both loc_id and lay_id are non-empty
        has_completed_laps:  True when enough laps are captured to attempt a build
        has_ref_path:        True when a reference path is built (ctrl.can_save)
        has_review_model:    True when a segment review result exists
        selected_segment_id: Segment ID selected in review table, or None
        has_track_length:    True when track_length_m is available for offset actions
    """
    recording        = ctrl_state == "recording"
    stopped_or_built = ctrl_state in ("stopped", "built")
    has_sel          = selected_segment_id is not None

    return {
        # Calibration session lifecycle
        "start":              has_track and not recording,
        "stop":               recording,
        "build":              stopped_or_built and has_completed_laps,
        "save_path":          has_ref_path,
        "detect_segments":    has_ref_path,
        # Segment review
        "confirm":            has_review_model and has_sel,
        "rename":             has_review_model and has_sel,
        "reject":             has_review_model and has_sel,
        "needs_more_laps":    has_review_model and has_sel,
        "split_required":     has_review_model and has_sel,
        "merge_required":     has_review_model and has_sel,
        "save_review":        has_review_model,
        # Lap offset calibration
        "create_zero_offset": has_track and has_track_length,
        "load_offset":        has_track,
        "save_offset":        has_track_length,
    }


def format_calibration_status_extended(
    status_summary: dict,
    last_packet_age_s: Optional[float] = None,
) -> dict[str, str]:
    """Return enhanced status label strings for the calibration panel.

    Args:
        status_summary:    Dict from TrackCalibrationCaptureController.get_status_summary()
        last_packet_age_s: Seconds since last calibration packet received, or None

    Returns dict with keys: state_text, recording_indicator, packet_age,
        sample_count, lap_count, path_info, saved_path
    """
    state         = status_summary.get("state", "inactive")
    lap_num       = status_summary.get("current_lap_number")
    total_samples = status_summary.get("total_samples", 0)
    in_progress   = status_summary.get("in_progress_samples", 0)
    lap_count     = status_summary.get("lap_count", 0)
    usable        = status_summary.get("usable_laps", 0)
    rejected      = status_summary.get("rejected_laps", 0)
    low_conf      = status_summary.get("low_confidence_laps", 0)
    pts           = status_summary.get("reference_path_points", 0)
    conf          = status_summary.get("confidence", 0.0)
    saved         = status_summary.get("saved_path", "")
    error         = status_summary.get("error", "")

    if state == "recording":
        state_text          = f"Recording — lap {lap_num or '?'}"
        recording_indicator = "● RECORDING"
    elif state == "stopped":
        state_text          = f"Stopped — {lap_count} lap{'s' if lap_count != 1 else ''} captured"
        recording_indicator = ""
    elif state == "built":
        state_text          = "Path built — ready to save"
        recording_indicator = ""
    elif state == "error":
        state_text          = f"Error: {error}" if error else "Session error"
        recording_indicator = ""
    else:
        state_text          = "No calibration session active"
        recording_indicator = ""

    if last_packet_age_s is None:
        packet_age = "No packets received" if state in ("inactive", "error") else "Packet age: unknown"
    elif last_packet_age_s < 1.0:
        packet_age = f"Last packet: {last_packet_age_s * 1000:.0f} ms ago"
    elif last_packet_age_s < 10.0:
        packet_age = f"Last packet: {last_packet_age_s:.1f} s ago"
    else:
        packet_age = f"Last packet: {last_packet_age_s:.0f} s ago — check connection"

    sample_str = (
        f"{total_samples:,} samples"
        + (f"  ({in_progress} in progress)" if state == "recording" else "")
        if total_samples > 0 else "No samples captured"
    )

    if state in ("stopped", "built"):
        lap_str = (
            f"{lap_count} lap{'s' if lap_count != 1 else ''}"
            f"  |  Usable: {usable}  |  Rejected: {rejected}"
            + (f"  |  Low-conf: {low_conf}" if low_conf else "")
        )
    elif state == "recording":
        lap_str = f"{lap_count} completed  |  Lap {lap_num or '?'} in progress"
    else:
        lap_str = "—"

    return {
        "state_text":          state_text,
        "recording_indicator": recording_indicator,
        "packet_age":          packet_age,
        "sample_count":        sample_str,
        "lap_count":           lap_str,
        "path_info":           f"{pts} pts  |  Confidence: {conf:.2f}" if pts else "—",
        "saved_path":          saved,
    }


def format_lap_offset_status(
    offset_calibration=None,
    track_length_m: Optional[float] = None,
) -> dict[str, str]:
    """Return display fields for the lap offset calibration status panel.

    Args:
        offset_calibration: LapStartOffsetCalibration or None
        track_length_m:     Track length in metres from seed or reference path, or None

    Returns dict with keys: status, offset_m, confidence, track_length,
        source, warnings, provisional_note
    """
    track_length_str = (
        f"{track_length_m:.0f} m" if track_length_m is not None
        else "Unknown — check seed data or build reference path"
    )

    if offset_calibration is None:
        return {
            "status":           "No offset calibration",
            "offset_m":         "—",
            "confidence":       "—",
            "track_length":     track_length_str,
            "source":           "—",
            "warnings":         "",
            "provisional_note": (
                "Create a zero-offset calibration to enable road_distance → "
                "distance_along_lap_m mapping."
            ),
        }

    conf     = getattr(offset_calibration, "confidence", None)
    conf_val = conf.value if hasattr(conf, "value") else str(conf or "unknown")
    offset_m = getattr(offset_calibration, "offset_m", None)
    source   = str(getattr(offset_calibration, "calibration_source", None) or "unknown")
    warns    = list(getattr(offset_calibration, "warnings", []))
    cal_len  = getattr(offset_calibration, "track_length_m", None)

    is_zero  = source == "zero_offset"
    is_provis = conf_val in ("low", "unknown") or is_zero

    status = (
        "Zero offset — provisional (validate at S/F line)"
        if is_zero else
        f"Calibrated — confidence: {conf_val}"
    )

    return {
        "status":     status,
        "offset_m":   f"{offset_m:.2f} m" if offset_m is not None else "—",
        "confidence": conf_val,
        "track_length": (
            f"{cal_len:.0f} m" if cal_len is not None else track_length_str
        ),
        "source":     source,
        "warnings":   " | ".join(warns[:3]) if warns else "",
        "provisional_note": (
            "PROVISIONAL — offset is 0 m. Distance mapping may be inaccurate if the "
            "car was not at the start/finish line when this calibration was created."
            if is_provis else ""
        ),
    }


def format_live_resolver_status_summary(
    loc_id: str,
    lay_id: str,
    resolver_result=None,
    offset_calibration=None,
    live_position=None,
    live_segment_result=None,
) -> str:
    """Return a compact multi-line status summary for the live runtime check panel.

    Pure Python — safe to call from tests without PyQt6.
    Returns a newline-separated string for display in a QLabel or text area.
    """
    lines: list[str] = []

    if not loc_id or not lay_id:
        lines.append("Track: not selected")
        lines.append("Select a track location and layout to enable runtime checks.")
        return "\n".join(lines)

    lines.append(f"Track: {loc_id} / {lay_id}")

    # Resolver
    if resolver_result is None:
        lines.append("Resolver: not checked")
    else:
        resolved = getattr(resolver_result, "resolved_model", None)
        if resolved is None:
            lines.append("Resolver: no model found")
        else:
            source   = getattr(resolved, "source_type", None)
            src_val  = source.value if hasattr(source, "value") else str(source or "")
            ai_ready = getattr(resolved, "ai_ready", False)
            lines.append(
                f"Resolver: {src_val}  |  AI-ready: {'Yes' if ai_ready else 'No'}"
            )

    # Offset
    if offset_calibration is None:
        lines.append("Offset calibration: none — road_distance mapping unavailable")
    else:
        conf     = getattr(offset_calibration, "confidence", None)
        conf_val = conf.value if hasattr(conf, "value") else str(conf or "")
        offset_m = getattr(offset_calibration, "offset_m", 0.0)
        lines.append(f"Offset: {offset_m:.1f} m  |  confidence: {conf_val}")

    # Live position
    if live_position is None:
        lines.append("Live position: no data")
    else:
        rd    = getattr(live_position, "road_distance_m", None)
        speed = getattr(live_position, "speed_kph", None)
        parts: list[str] = []
        if rd is not None:
            parts.append(f"road_dist={rd:.1f} m")
        if speed is not None:
            parts.append(f"speed={speed:.0f} kph")
        lines.append(f"Live position: {', '.join(parts) if parts else 'on track'}")

    # Live segment
    if live_segment_result is None:
        lines.append("Live segment: not resolved")
    else:
        res_status = getattr(live_segment_result, "resolution_status", None)
        status_val = res_status.value if hasattr(res_status, "value") else str(res_status or "")
        match      = getattr(live_segment_result, "match", None)
        if match is not None:
            name = getattr(match, "display_name", None) or getattr(match, "segment_id", "")
            lines.append(f"Segment: {name}  ({status_val})")
        else:
            lines.append(f"Segment: unresolved  ({status_val})")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Group 17M UAT defect remediation helpers
# ---------------------------------------------------------------------------

def format_lap_count_info(status_summary: dict) -> dict[str, str]:
    """Return human-readable lap count strings for the calibration status panel.

    Distinguishes between raw captured lap segments (all boundary crossings,
    including partial fragments at session start/end) and quality-assessed laps
    (usable/rejected/low-confidence, only available after Build Reference Path).

    Pure Python — no PyQt6 dependency.
    """
    lap_count      = status_summary.get("lap_count", 0)
    usable         = status_summary.get("usable_laps", 0)
    rejected       = status_summary.get("rejected_laps", 0)
    low_conf       = status_summary.get("low_confidence_laps", 0)
    state          = status_summary.get("state", "inactive")
    cur_lap        = status_summary.get("current_lap_number")
    in_progress    = status_summary.get("in_progress_samples", 0)

    assessed_total = usable + rejected + low_conf

    # "captured" label —— always show raw count
    if lap_count == 0:
        captured_text = "No lap boundaries crossed yet"
    elif state == "recording":
        cur_str = f" (lap {cur_lap} in progress, {in_progress} samples)" if cur_lap else ""
        captured_text = f"{lap_count} lap{'s' if lap_count != 1 else ''} recorded{cur_str}"
    else:
        captured_text = f"{lap_count} lap segment{'s' if lap_count != 1 else ''} captured"

    # "quality" label —— only non-trivial after Build
    if assessed_total == 0:
        if state in ("stopped", "built", "error") and lap_count > 0:
            quality_text = "Run Build Reference Path to assess lap quality"
        else:
            quality_text = ""
    else:
        quality_text = f"{usable} usable  /  {rejected} rejected  /  {low_conf} low-confidence"

    # "explanation" label —— only when gap exists between captured and assessed
    if assessed_total > 0 and lap_count > assessed_total:
        extra = lap_count - assessed_total
        explanation = (
            f"Note: {extra} short/partial segment(s) from session start or stop "
            f"were not counted in quality assessment. This is normal."
        )
    else:
        explanation = ""

    return {
        "captured_text": captured_text,
        "quality_text":  quality_text,
        "explanation":   explanation,
    }


def format_file_audit_status(audit) -> dict[str, str]:
    """Return UI-friendly strings from a TrackModelFileAudit (duck-typed).

    Pure Python — no PyQt6 dependency.
    """
    exists   = bool(getattr(audit, "ref_path_exists", False))
    load_ok  = bool(getattr(audit, "ref_path_load_ok", False))
    load_err = str(getattr(audit, "ref_path_load_error", "") or "")
    modified = str(getattr(audit, "ref_path_modified", "") or "")
    pts      = int(getattr(audit, "ref_path_point_count", 0))
    conf     = float(getattr(audit, "ref_path_confidence", 0.0))
    laps     = int(getattr(audit, "ref_path_source_laps", 0))
    f_path   = str(getattr(audit, "ref_path_file", "") or "")

    rev_exists     = bool(getattr(audit, "reviewed_exists", False))
    off_exists     = bool(getattr(audit, "offset_exists", False))
    cal_laps_count = int(getattr(audit, "calibration_laps_usable_count", 0))
    cal_laps_ok    = bool(getattr(audit, "calibration_laps_exists", False)) and cal_laps_count > 0
    # is_legacy_ref_path_only is a property on TrackModelFileAudit; use getattr for duck-typing
    _is_legacy_prop = getattr(type(audit), "is_legacy_ref_path_only", None)
    is_legacy       = bool(_is_legacy_prop.fget(audit)) if _is_legacy_prop else (
        exists and load_ok and not getattr(audit, "calibration_laps_exists", False)
    )

    if not exists:
        saved_text  = "No saved reference path for this track/layout"
        detail_text = ""
        load_status = ""
    elif load_ok:
        mod_str     = f"  (saved {modified})" if modified else ""
        saved_text  = f"Saved: {f_path}{mod_str}"
        if cal_laps_ok:
            detail_text = (
                f"{pts} pts  |  conf {conf:.2f}  |  {laps} laps  |  "
                f"{cal_laps_count} laps persisted"
            )
            load_status = "Detect Segments ready — lap data available from disk"
        elif is_legacy:
            detail_text = f"{pts} pts  |  conf {conf:.2f}  |  {laps} laps  |  no lap data saved"
            load_status = (
                "Pre-17N format — re-run calibration once to enable "
                "Detect Segments after restart"
            )
        else:
            detail_text = f"{pts} pts  |  conf {conf:.2f}  |  {laps} laps"
            load_status = "Loaded OK"
    else:
        saved_text  = f"Saved file found but could not load: {load_err}"
        detail_text = f"File: {f_path}"
        load_status = "File unreadable — re-run calibration or check file"

    extra_files: list[str] = []
    if rev_exists:
        extra_files.append("Reviewed model found")
    if off_exists:
        extra_files.append("Offset calibration found")
    extras_text = "  |  ".join(extra_files)

    return {
        "saved_text":  saved_text,
        "detail_text": detail_text,
        "load_status": load_status,
        "extras_text": extras_text,
    }


def format_build_failure_diagnostics(result, session=None) -> str:
    """Format a human-readable diagnostic string from a failed CalibrationBuildResult.

    Parameters
    ----------
    result : CalibrationBuildResult
        The result of a failed build_reference_path() call.
    session : CalibrationSession | None
        Optional session object.  When provided, used to fill in car ID and
        to detect the "zero laps captured" case.

    Returns
    -------
    str
        Multi-line message suitable for QMessageBox.warning().
    """
    lines: list[str] = []

    # Primary error line(s)
    for err in (getattr(result, "errors", None) or []):
        lines.append(err)

    usable  = int(getattr(result, "usable_lap_count",         0))
    rejected = int(getattr(result, "rejected_lap_count",       0))
    low_conf = int(getattr(result, "low_confidence_lap_count", 0))
    total    = usable + rejected + low_conf

    # Lap quality breakdown
    lines.append("")
    if total > 0:
        lines.append(
            f"Lap quality:  {usable} usable  /  {rejected} rejected  /  "
            f"{low_conf} low-confidence  ({total} total captured)"
        )
    elif session is not None and not getattr(session, "laps", None):
        lines.append("No lap segments were captured in this session.")
        lines.append(
            "Drive past the start/finish line at least twice "
            "to create complete lap boundaries."
        )
    else:
        lines.append("No laps assessed (session data unavailable).")

    # Per-lap rejection details from build warnings
    warnings = list(getattr(result, "warnings", None) or [])
    if warnings:
        lines.append("")
        lines.append("Rejection details:")
        for w in warnings:
            lines.append(f"  • {w}")

    # Car ID
    car_id = ""
    if session is not None:
        car_id = str(getattr(session, "calibration_car_id", "") or "")
    if car_id:
        lines.append("")
        lines.append(f"Calibration car: {car_id}")

    # Recommended action based on patterns in warnings
    lines.append("")
    combined_warnings = " ".join(warnings).lower()
    if total == 0:
        lines.append(
            "Recommended: Start recording, then drive 2 complete clean laps "
            "(cross the start/finish line twice)."
        )
    elif usable == 0 and "too few telemetry samples" in combined_warnings:
        lines.append(
            "Recommended: Ensure GT7 Custom UDP telemetry is enabled "
            "(Settings → Application → Custom UDP Output)."
        )
        lines.append(
            "Each calibration lap must contain at least "
            f"{_min_samples()} telemetry samples (~5 seconds of driving)."
        )
    elif usable == 0 and (
        "zero/missing x/y/z" in combined_warnings or "coordinate" in combined_warnings
    ):
        lines.append(
            "Recommended: Ensure the car is moving before starting the session. "
            "The GT7 packet sends position (x/y/z) only while on-track."
        )
    elif usable == 0 and "off-track" in combined_warnings:
        lines.append(
            "Recommended: Keep the car fully on track. "
            "Laps with more than 30% off-track samples are rejected."
        )
    elif usable == 0 and "outlier" in combined_warnings:
        lines.append(
            "Recommended: Drive consistent laps at race pace. "
            "One very long or very short lap causes the others to be rejected as outliers."
        )
        lines.append(
            "Avoid pit stops or pauses mid-lap during calibration."
        )
    elif usable == 1:
        lines.append(
            "Recommended: Drive 1 more clean lap. Minimum 2 usable laps are required."
        )
    elif usable > 0:
        lines.append(
            f"Recommended: Drive {max(0, 2 - usable)} more clean lap(s) "
            "to reach the minimum of 2 usable laps."
        )
    else:
        lines.append(
            "Recommended: Drive 2 complete clean laps at race pace, "
            "then click Build Reference Path."
        )

    return "\n".join(lines)


def _min_samples() -> int:
    """Return MIN_CALIBRATION_SAMPLES without a hard import dependency."""
    try:
        from data.track_calibration import MIN_CALIBRATION_SAMPLES
        return MIN_CALIBRATION_SAMPLES
    except Exception:
        return 50


# ---------------------------------------------------------------------------
# Group 18A — Track Truth Foundation view-model helper
# ---------------------------------------------------------------------------

_TRUTH_STATUS_MAP: dict[str, tuple[str, str]] = {
    "METADATA_ONLY":         ("Metadata only — no coordinate geometry",           "#888888"),
    "CURVATURE_PROVISIONAL": ("Curvature-provisional — corner mapping unverified", "#F5A623"),
    "ACCEPTED_SEED_MAP":     ("Track Truth accepted — Map Alignment ready",        "#4caf50"),
    "ACCEPTED_LIVE_MAPPING": ("Track Truth accepted — Live Mapping Ready",         "#88EE88"),
}

_GREEN  = "#4caf50"
_AMBER  = "#F5A623"
_GREY   = "#888888"
_PLACEHOLDER = "—"


def format_track_truth_status(
    model,
    validation,
    track_id: Optional[str] = None,
    layout_id: Optional[str] = None,
) -> dict[str, str]:
    """Return display dict for the Track Truth status panel.

    ``model`` is a TrackTruthModel or None.
    ``validation`` is a TrackTruthValidationResult or None.

    All keys are always present in the returned dict.
    When model is None every value is "—" and every color is "#888888".

    Keys returned
    -------------
    track_id, layout_id,
    library_availability, library_availability_color,
    seed_geometry, seed_geometry_color,
    corner_metadata, corner_metadata_color,
    complex_metadata, complex_metadata_color,
    geometry_acceptance, geometry_acceptance_color,
    live_mapping_ready, live_mapping_ready_color,
    ai_context_ready, ai_context_ready_color,
    blockers,
    warnings,
    status_label, status_color
    """
    _ph = {
        "track_id":                    _PLACEHOLDER,
        "layout_id":                   _PLACEHOLDER,
        "library_availability":        _PLACEHOLDER,
        "library_availability_color":  _GREY,
        "seed_geometry":               _PLACEHOLDER,
        "seed_geometry_color":         _GREY,
        "corner_metadata":             _PLACEHOLDER,
        "corner_metadata_color":       _GREY,
        "complex_metadata":            _PLACEHOLDER,
        "complex_metadata_color":      _GREY,
        "geometry_acceptance":         _PLACEHOLDER,
        "geometry_acceptance_color":   _GREY,
        "live_mapping_ready":          _PLACEHOLDER,
        "live_mapping_ready_color":    _GREY,
        "ai_context_ready":            _PLACEHOLDER,
        "ai_context_ready_color":      _GREY,
        "blockers":                    _PLACEHOLDER,
        "warnings":                    _PLACEHOLDER,
        "status_label":                _PLACEHOLDER,
        "status_color":                _GREY,
    }

    if model is None:
        return _ph

    # ── IDs ──────────────────────────────────────────────────────────────────
    try:
        m = model.manifest
        tid = track_id  if track_id  else getattr(m, "track_id",  "")
        lid = layout_id if layout_id else getattr(m, "layout_id", "")
    except Exception:
        tid = track_id  or _PLACEHOLDER
        lid = layout_id or _PLACEHOLDER

    # ── seed_geometry_available ───────────────────────────────────────────────
    try:
        geo_avail = bool(getattr(model.manifest, "seed_geometry_available", False))
    except Exception:
        geo_avail = False

    seed_geo_val   = "Available"     if geo_avail else "Not available"
    seed_geo_color = _GREEN          if geo_avail else _GREY

    # ── corner_windows ────────────────────────────────────────────────────────
    try:
        n_corners = len(list(model.corner_windows))
    except Exception:
        n_corners = 0

    if n_corners > 0:
        corner_val   = f"Yes ({n_corners} corners)"
        corner_color = _GREEN
    else:
        corner_val   = "None"
        corner_color = _GREY

    # ── corner_complexes ──────────────────────────────────────────────────────
    try:
        n_complexes = len(list(model.corner_complexes))
    except Exception:
        n_complexes = 0

    if n_complexes > 0:
        complex_val   = f"Yes ({n_complexes} complexes)"
        complex_color = _GREEN
    else:
        complex_val   = "None"
        complex_color = _GREY

    # ── validation-derived fields ─────────────────────────────────────────────
    if validation is None:
        # Model present but validation not run — treat as metadata-only / unknown
        geo_accept_val   = "Unknown"
        geo_accept_color = _GREY
        live_val         = "Not ready"
        live_color       = _GREY
        ai_val           = "Blocked"
        ai_color         = _GREY
        blockers_str     = "—"
        warnings_str     = "—"
        status_label     = "Metadata only — no coordinate geometry"
        status_color     = _GREY
    else:
        try:
            is_accepted = bool(validation.is_accepted)
        except Exception:
            is_accepted = False

        # geometry_acceptance
        if is_accepted:
            geo_accept_val   = "Accepted"
            geo_accept_color = _GREEN
        else:
            # Amber if some metadata present (corners or complexes), grey otherwise
            geo_accept_color = _AMBER if (n_corners > 0 or n_complexes > 0) else _GREY
            geo_accept_val   = "Blocked"

        # live_mapping_ready
        try:
            live_ready = bool(validation.is_usable_for_live_mapping)
        except Exception:
            live_ready = False

        live_val   = "Ready"     if live_ready else "Not ready"
        live_color = _GREEN      if live_ready else _GREY

        # ai_context_ready
        try:
            ai_ready = bool(validation.is_usable_for_ai_corner_context)
        except Exception:
            ai_ready = False

        if ai_ready:
            ai_val   = "Ready"
            ai_color = _GREEN
        else:
            ai_val   = "Blocked"
            ai_color = _AMBER if is_accepted else _GREY

        # blockers / warnings
        try:
            raw_blockers = list(validation.blockers) if validation.blockers else []
        except Exception:
            raw_blockers = []
        blockers_str = "\n".join(raw_blockers) if raw_blockers else "None"

        try:
            raw_warnings = list(validation.warnings) if validation.warnings else []
        except Exception:
            raw_warnings = []
        warnings_str = "\n".join(raw_warnings) if raw_warnings else "None"

        # status_label / status_color
        try:
            status_val = str(validation.status.value)
        except Exception:
            status_val = ""

        if status_val in _TRUTH_STATUS_MAP:
            status_label, status_color = _TRUTH_STATUS_MAP[status_val]
        else:
            status_label = "No track truth data"
            status_color = _GREY

    return {
        "track_id":                    str(tid),
        "layout_id":                   str(lid),
        "library_availability":        "Available",
        "library_availability_color":  _GREEN,
        "seed_geometry":               seed_geo_val,
        "seed_geometry_color":         seed_geo_color,
        "corner_metadata":             corner_val,
        "corner_metadata_color":       corner_color,
        "complex_metadata":            complex_val,
        "complex_metadata_color":      complex_color,
        "geometry_acceptance":         geo_accept_val,
        "geometry_acceptance_color":   geo_accept_color,
        "live_mapping_ready":          live_val,
        "live_mapping_ready_color":    live_color,
        "ai_context_ready":            ai_val,
        "ai_context_ready_color":      ai_color,
        "blockers":                    blockers_str,
        "warnings":                    warnings_str,
        "status_label":                status_label,
        "status_color":                status_color,
    }
