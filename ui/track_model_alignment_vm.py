"""Track Model Alignment View Model.

Pure Python — no PyQt6 dependency.  Converts TrackModelAlignmentResult into
display strings and button-state decisions for the dashboard.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from data.track_model_alignment import (
    TrackModelAlignmentResult,
    TrackModelMatchStatus,
)


# ---------------------------------------------------------------------------
# Match-status display
# ---------------------------------------------------------------------------

_STATUS_DISPLAY = {
    TrackModelMatchStatus.NOT_READY:        ("Not built",              "#888888"),
    TrackModelMatchStatus.FAILED_MATCH:     ("Failed — cannot accept", "#EE4444"),
    TrackModelMatchStatus.PARTIAL_MATCH:    ("Partial match",          "#F5A623"),
    TrackModelMatchStatus.GOOD_MATCH:       ("Good match",             "#ffa500"),
    TrackModelMatchStatus.ACCEPTABLE_MATCH: ("Acceptable — can accept","#4caf50"),
}

_WORKFLOW_STATE_DISPLAY = {
    "not_built":          ("Not built",                "#888888"),
    "built_not_aligned":  ("Built — alignment pending", "#F5A623"),
    "aligned_rejected":   ("Aligned — not accepted",    "#F5A623"),
    "aligned_accepted":   ("Accepted and saved",        "#88EE88"),
}


def format_geometry_alignment_summary(geo_result) -> str:
    """Return a single-line display string for the geometry alignment result."""
    if geo_result is None:
        return "—"
    if not getattr(geo_result, "seed_coordinate_map_available", False):
        if getattr(geo_result, "lap_length_delta_pct", 0.0) > 0:
            delta = geo_result.lap_length_delta_pct
            color_tag = "warn" if delta > 5.0 else "ok"
            return f"Length only — seed map unavailable ({delta:.1f}% delta)"
        return "Seed coordinate map unavailable"
    mean_err = getattr(geo_result, "mean_coord_error_m", None)
    max_err  = getattr(geo_result, "max_coord_error_m",  None)
    delta    = getattr(geo_result, "lap_length_delta_pct", 0.0)
    parts: List[str] = []
    if mean_err is not None:
        parts.append(f"mean err {mean_err:.1f} m")
    if max_err is not None:
        parts.append(f"max {max_err:.1f} m")
    if delta > 0:
        parts.append(f"length delta {delta:.1f}%")
    n_missing = len(getattr(geo_result, "missing_section_ranges", []))
    if n_missing:
        parts.append(f"{n_missing} missing section(s)")
    return ", ".join(parts) if parts else "Match computed"


def format_seed_audit_summary(audit) -> str:
    """Return a single-line seed audit summary string for display."""
    if audit is None:
        return "—"
    parts: List[str] = []
    if audit.has_lap_length:
        parts.append("lap length")
    if audit.has_sector_definitions:
        parts.append(f"{audit.sector_count} sectors")
    if audit.has_corner_windows:
        parts.append(f"{audit.corner_count} corner windows")
    if audit.has_corner_complexes:
        parts.append(f"{audit.complex_count} complexes")
    if audit.has_seed_centreline:
        parts.append("centreline")
    else:
        parts.append("no centreline")
    return ", ".join(parts) if parts else "metadata only"


def format_alignment_summary(
    result: Optional[TrackModelAlignmentResult],
    layout_seed=None,
    geo_result=None,    # Optional TrackMapGeometryAlignmentResult (Group 17T)
) -> Dict[str, str]:
    """Return a dict of label → value strings for the alignment panel.

    layout_seed (optional TrackLayoutSeed) — used to compute seed audit display.
    geo_result  (optional TrackMapGeometryAlignmentResult) — coordinate geometry match.
    """
    if result is None:
        return {
            "match_status":         "—",
            "match_color":          "#888888",
            "seed_corners":         "—",
            "model_corners":        "—",
            "extra_peaks":          "—",
            "placeholders":         "—",
            "seed_truth_source":    "—",
            "seed_position_status": "—",
            "corners_matched":      "—",
            "corner_position_match":"—",
            "corner_position_color":"#888888",
            "lap_model":            "—",
            "lap_seed":             "—",
            "lap_delta":            "—",
            "lap_delta_color":      "#888888",
            "stations":             "—",
            "confidence":           "—",
            "sector":               "—",
            "blockers":             "",
            "warnings":             "",
            "accepted_at":          "—",
            "workflow_state":       "Not built",
            "workflow_color":       "#888888",
            "seed_audit":           "—",
            "geometry_match":       "—",
            "seed_source":          "—",
        }

    status_text, status_color = _STATUS_DISPLAY.get(
        result.match_status, ("Unknown", "#888888")
    )

    lap_delta_str = (
        f"{result.lap_length_delta_pct:.1f}%"
        if result.lap_length_m_seed > 0
        else "N/A (no seed length)"
    )
    lap_delta_color = (
        "#88EE88" if result.lap_length_delta_pct <= 2.0
        else "#F5A623" if result.lap_length_delta_pct <= 5.0
        else "#EE4444"
    )

    if result.accepted:
        workflow_state, workflow_color = _WORKFLOW_STATE_DISPLAY["aligned_accepted"]
    elif result.match_status in (
        TrackModelMatchStatus.GOOD_MATCH, TrackModelMatchStatus.ACCEPTABLE_MATCH
    ):
        workflow_state, workflow_color = _WORKFLOW_STATE_DISPLAY["aligned_rejected"]
    elif result.match_status == TrackModelMatchStatus.NOT_READY:
        workflow_state, workflow_color = _WORKFLOW_STATE_DISPLAY["not_built"]
    else:
        workflow_state, workflow_color = _WORKFLOW_STATE_DISPLAY["built_not_aligned"]

    # ── Seed corner position status (Group 17Q/17R) ───────────────────────
    if result.seed_corner_positions_available:
        n_matched = result.corners_matched
        n_total   = result.seed_corners_expected
        seed_pos_status  = f"Available ({n_matched}/{n_total} matched)"
        seed_truth_source = f"Seed corner windows ({n_total} defs)"
    else:
        seed_pos_status   = (
            "Unavailable — corner labels are curvature peaks, not verified positions"
        )
        seed_truth_source = "Metadata only — no coordinate or window data"

    corners_matched_str = (
        f"{result.corners_matched} / {result.seed_corners_expected}"
        if result.seed_corner_positions_available
        else "N/A (no seed positions)"
    )

    _POS_MATCH_DISPLAY = {
        "PASS":         ("Pass",        "#88EE88"),
        "PARTIAL":      ("Partial",     "#F5A623"),
        "FAIL":         ("Fail",        "#EE4444"),
        "NOT_AVAILABLE":("Not available","#888888"),
    }
    pos_match_text, pos_match_color = _POS_MATCH_DISPLAY.get(
        result.corner_position_match, ("Unknown", "#888888")
    )

    # ── Seed audit (Group 17S / 17T / 17U) ───────────────────────────────
    from data.track_intelligence import audit_layout_seed as _audit_fn
    _audit = _audit_fn(layout_seed)
    seed_audit_str = format_seed_audit_summary(_audit)

    _seed_source_raw = getattr(_audit, "seed_source", "none")
    _seed_source_display = {
        "track_library":   "Track library",
        "legacy_fallback": "Legacy fallback",
        "none":            "Unavailable",
    }.get(_seed_source_raw, "—")

    # ── Geometry alignment (Group 17T) ────────────────────────────────────
    geo_match_str = format_geometry_alignment_summary(geo_result)

    return {
        "match_status":          status_text,
        "match_color":           status_color,
        "seed_corners":          str(result.seed_corners_expected) if result.seed_corners_expected else "N/A",
        "model_corners":         str(result.model_corners_found),
        "extra_peaks":           str(result.extra_peaks_suppressed),
        "placeholders":          str(result.placeholder_count),
        "seed_truth_source":     seed_truth_source,
        "seed_position_status":  seed_pos_status,
        "corners_matched":       corners_matched_str,
        "corner_position_match": pos_match_text,
        "corner_position_color": pos_match_color,
        "lap_model":             f"{result.lap_length_m_model:.0f} m",
        "lap_seed":              f"{result.lap_length_m_seed:.0f} m" if result.lap_length_m_seed else "N/A",
        "lap_delta":             lap_delta_str,
        "lap_delta_color":       lap_delta_color,
        "stations":              str(result.station_count),
        "confidence":            f"{result.confidence:.2f}",
        "sector":                result.sector_alignment.note,
        "blockers":              "\n".join(result.blockers) if result.blockers else "",
        "warnings":              "\n".join(result.warnings) if result.warnings else "",
        "accepted_at":           result.accepted_at or "—",
        "workflow_state":        workflow_state,
        "workflow_color":        workflow_color,
        "seed_audit":            seed_audit_str,
        "geometry_match":        geo_match_str,
        "seed_source":           _seed_source_display,
    }


# ---------------------------------------------------------------------------
# Button state decisions
# ---------------------------------------------------------------------------

def get_acceptance_button_states(
    result: Optional[TrackModelAlignmentResult],
    has_station_map: bool,
) -> Dict[str, bool]:
    """Return enabled/disabled flags for the acceptance workflow buttons.

    Keys:
      "accept"   — Accept Track Model button
      "rebuild"  — Rebuild / Recalibrate button
    """
    if not has_station_map:
        return {"accept": False, "rebuild": False}

    if result is None:
        return {"accept": False, "rebuild": True}

    accept_enabled = (
        result.match_status in (TrackModelMatchStatus.ACCEPTABLE_MATCH, TrackModelMatchStatus.GOOD_MATCH)
        and not result.blockers
        and not result.accepted  # disable once already accepted
    )
    rebuild_enabled = True  # always available if station map exists

    return {
        "accept":  accept_enabled,
        "rebuild": rebuild_enabled,
    }


# ---------------------------------------------------------------------------
# Mismatch reason formatting
# ---------------------------------------------------------------------------

def format_mismatch_reasons(result: Optional[TrackModelAlignmentResult]) -> List[str]:
    """Return a list of human-readable mismatch/warning strings."""
    if result is None:
        return []
    lines: List[str] = []
    for b in result.blockers:
        lines.append(f"BLOCKER: {b}")
    for w in result.warnings:
        lines.append(f"Warning: {w}")
    return lines


# ---------------------------------------------------------------------------
# Manual segment approval guard — DEF-17P-UAT-012
# ---------------------------------------------------------------------------

def manual_approval_buttons_enabled(in_alignment_workflow: bool = True) -> bool:
    """Return False — per-segment approval buttons are not part of the normal workflow."""
    return not in_alignment_workflow


# ---------------------------------------------------------------------------
# Group 17V — Seed Geometry button states and diagnostics
# ---------------------------------------------------------------------------

def get_geometry_button_states(
    build_result,
    save_result,
    seed_available: bool,
    session_active: bool,
) -> Dict[str, tuple]:
    """Return {button_name: (enabled, reason)} for 'generate', 'save', 'reload'.

    State machine:
    - generate: enabled when session_active=True and (build_result is None or
                not seed_available)
    - save: enabled when build_result is not None and build_result.can_generate
            and save_result is None
    - reload: enabled when seed_available=True
    """
    generate_enabled = session_active and (build_result is None or not seed_available)
    generate_reason  = (
        "" if generate_enabled
        else ("No active calibration session" if not session_active
              else "Seed geometry already available — reload or re-run to replace")
    )

    save_enabled = (
        build_result is not None
        and build_result.can_generate
        and save_result is None
    )
    save_reason = (
        "" if save_enabled
        else ("No geometry built yet" if build_result is None
              else ("Cannot generate — no accepted laps" if not build_result.can_generate
                    else "Already saved"))
    )

    reload_enabled = seed_available
    reload_reason  = "" if reload_enabled else "No seed geometry in library for this layout"

    return {
        "generate": (generate_enabled, generate_reason),
        "save":     (save_enabled,     save_reason),
        "reload":   (reload_enabled,   reload_reason),
    }


def format_candidate_diagnostics(filter_results) -> str:
    """Format per-lap results as a multi-line string for display in the status label.

    Example: 'Lap 1: accepted (delta 1.2%)\nLap 2: rejected — incomplete lap (delta 5.9%)'
    Returns empty string if filter_results is None.
    """
    if filter_results is None:
        return ""
    lines: List[str] = []
    for fr in sorted(filter_results, key=lambda r: r.lap_index):
        lap_num = fr.lap_index + 1
        if fr.status == "accepted":
            delta_str = f"delta {fr.delta_pct:.1f}%" if fr.delta_pct > 0 else "exact match"
            lines.append(f"Lap {lap_num}: accepted ({delta_str})")
        else:
            lines.append(f"Lap {lap_num}: rejected — {fr.reason} (delta {fr.delta_pct:.1f}%)")
    return "\n".join(lines)
