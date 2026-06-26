"""Track Model Alignment — Layer 3 of the track modelling architecture.

Compares the telemetry-derived TrackStationMap (Layer 2) against the seeded
track truth (Layer 1) and produces a TrackModelAlignmentResult that drives the
whole-model Accept Track Model workflow.

Design rules:
  - No AI features.  No auto-detection.  No per-segment approval.
  - Alignment is computed, not decided interactively.
  - The Accept button is enabled only when STRICT criteria pass.
  - Extra curvature peaks (from curvature detection) are NEVER promoted to
    official turns — they are stored separately and reported here.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import List, Optional

from data.track_station_map import TrackStationMap, STATION_MODELS_DIR
from data.seed_corner_matching import CornerMatchStatus, CornerCandidateMatch

ACCEPTED_MODEL_SCHEMA: str   = "accepted_track_model_v1"
_MIN_STATIONS_FOR_ALIGNMENT  = 200
_MAX_LAP_DELTA_STRICT_PCT    = 2.0    # ACCEPTABLE_MATCH threshold
_MAX_LAP_DELTA_GOOD_PCT      = 8.0    # GOOD_MATCH threshold
_MAX_LAP_DELTA_PARTIAL_PCT   = 20.0   # PARTIAL_MATCH threshold
_MIN_CONFIDENCE_STRICT       = 0.60


# ---------------------------------------------------------------------------
# Match-status enum
# ---------------------------------------------------------------------------

class TrackModelMatchStatus(str, Enum):
    NOT_READY        = "NOT_READY"        # no station map or too few stations
    FAILED_MATCH     = "FAILED_MATCH"     # lap length > 20% off, or 0 corners
    PARTIAL_MATCH    = "PARTIAL_MATCH"    # lap length 8-20% off, or placeholders dominate
    GOOD_MATCH       = "GOOD_MATCH"       # lap delta < 8%, all corners accounted for
    ACCEPTABLE_MATCH = "ACCEPTABLE_MATCH" # lap delta < 2%, no blocking issues — Accept enabled


# ---------------------------------------------------------------------------
# Per-corner alignment
# ---------------------------------------------------------------------------

@dataclass
class CornerAlignmentResult:
    corner_id:       str
    approx_progress: float
    is_placeholder:  bool     # True = curvature did not find this corner; was estimated
    confidence:      float


# ---------------------------------------------------------------------------
# Sector alignment
# ---------------------------------------------------------------------------

@dataclass
class SectorAlignmentResult:
    seed_sector_count: int     # 0 = seed has no sector info
    status:            str     # "matched" / "not_available" / "skipped"
    note:              str


# ---------------------------------------------------------------------------
# Whole-model alignment result
# ---------------------------------------------------------------------------

@dataclass
class TrackModelAlignmentResult:
    match_status:           TrackModelMatchStatus
    seed_corners_expected:  int
    model_corners_found:    int     # official corners in station map
    extra_peaks_suppressed: int     # curvature peaks beyond corners_expected (non-official)
    placeholder_count:      int     # placeholders created because detection fell short
    lap_length_m_model:     float
    lap_length_m_seed:      float
    lap_length_delta_pct:   float
    station_count:          int
    confidence:             float
    corner_alignments:      List[CornerAlignmentResult]
    sector_alignment:       SectorAlignmentResult
    blockers:               List[str]
    warnings:               List[str]
    accepted:               bool = False
    accepted_at:            str  = ""
    # Group 17Q — seed corner position matching fields (default-safe for backward compat)
    seed_corner_positions_available: bool = False   # True when seed has per-corner windows
    corner_position_match:  str  = "NOT_AVAILABLE"  # "PASS"/"PARTIAL"/"FAIL"/"NOT_AVAILABLE"
    corners_matched:        int  = 0                # windows with a confirmed telemetry match
    corner_candidate_matches: List[CornerCandidateMatch] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Alignment computation
# ---------------------------------------------------------------------------

def align_track_model(
    station_map: TrackStationMap,
    layout_seed=None,   # Optional TrackLayoutSeed duck-typed
) -> TrackModelAlignmentResult:
    """Compare station_map (Layer 2) against layout_seed (Layer 1).

    Returns a TrackModelAlignmentResult describing how well the telemetry-
    derived model matches the official seeded circuit definition.
    """
    blockers: List[str] = []
    warnings: List[str] = []

    # ── Seed truth ────────────────────────────────────────────────────────
    seed_corners_expected = getattr(layout_seed, "corners_expected", 0) or 0
    seed_length_m         = getattr(layout_seed, "length_m", 0.0) or 0.0
    seed_sectors          = getattr(layout_seed, "sectors", None)

    # ── Station map metrics ────────────────────────────────────────────────
    station_count   = station_map.station_count()
    lap_length_m    = station_map.lap_length_m
    confidence      = station_map.confidence_overall
    model_corners   = len(station_map.seeded_corners)
    extra_peaks     = len(station_map.extra_curvature_peaks)
    placeholder_cnt = sum(1 for c in station_map.seeded_corners if c.is_seeded_placeholder)

    # ── NOT_READY guard ────────────────────────────────────────────────────
    if station_count < _MIN_STATIONS_FOR_ALIGNMENT:
        return TrackModelAlignmentResult(
            match_status           = TrackModelMatchStatus.NOT_READY,
            seed_corners_expected  = seed_corners_expected,
            model_corners_found    = model_corners,
            extra_peaks_suppressed = extra_peaks,
            placeholder_count      = placeholder_cnt,
            lap_length_m_model     = lap_length_m,
            lap_length_m_seed      = seed_length_m,
            lap_length_delta_pct   = 0.0,
            station_count          = station_count,
            confidence             = confidence,
            corner_alignments      = [],
            sector_alignment       = SectorAlignmentResult(
                seed_sector_count=0, status="not_available",
                note="Station map not built yet"),
            blockers = [f"Station map has only {station_count} stations (minimum {_MIN_STATIONS_FOR_ALIGNMENT})"],
            warnings = [],
        )

    # ── Lap length delta ───────────────────────────────────────────────────
    if seed_length_m > 0:
        delta_pct = abs(lap_length_m - seed_length_m) / seed_length_m * 100.0
    else:
        delta_pct = 0.0
        warnings.append("Seed has no lap length — lap length alignment skipped")

    if delta_pct > _MAX_LAP_DELTA_PARTIAL_PCT and seed_length_m > 0:
        blockers.append(
            f"Lap length mismatch critical: {delta_pct:.1f}% delta "
            f"(model {lap_length_m:.0f} m vs seed {seed_length_m:.0f} m) "
            f"exceeds {_MAX_LAP_DELTA_PARTIAL_PCT}% limit. "
            f"Check calibration laps covered the full layout and no pit/out-lap contamination."
        )
    elif delta_pct > _MAX_LAP_DELTA_GOOD_PCT and seed_length_m > 0:
        blockers.append(
            f"Lap length mismatch: {delta_pct:.1f}% exceeds {_MAX_LAP_DELTA_GOOD_PCT}% good-match threshold "
            f"(model {lap_length_m:.0f} m vs seed {seed_length_m:.0f} m). "
            f"Possible causes: incomplete lap coverage, start/finish offset error, or GT7 coordinate "
            f"distance differs from official length. Model acceptance blocked until resolved."
        )

    # ── Corner count ───────────────────────────────────────────────────────
    if seed_corners_expected > 0 and model_corners != seed_corners_expected:
        blockers.append(
            f"Corner count mismatch: model has {model_corners}, seed expects {seed_corners_expected}"
        )
    if placeholder_cnt > 0:
        warnings.append(
            f"{placeholder_cnt} corner(s) estimated by placeholder — curvature did not confirm them"
        )
    if extra_peaks > 0:
        warnings.append(
            f"{extra_peaks} extra curvature peak(s) suppressed — not promoted to official turns"
        )

    # ── Confidence ─────────────────────────────────────────────────────────
    if confidence < _MIN_CONFIDENCE_STRICT:
        warnings.append(f"Reference path confidence {confidence:.2f} is below 0.60")

    # ── Seed corner position matching (Group 17Q — DEF-17Q-001/002) ────────
    corner_defs = getattr(layout_seed, "corner_definitions", []) or []
    seed_corner_positions_available = bool(corner_defs)
    corner_candidate_matches: List[CornerCandidateMatch] = []
    corners_matched   = 0
    corner_position_match = "NOT_AVAILABLE"

    if not corner_defs:
        # Seed has no per-corner windows — honest about position verification limits
        warnings.append(
            "Seed corner location data unavailable — corner count matched, "
            "but corner-position match cannot be fully verified."
        )
        # Mark every official corner as SEED_POSITION_UNAVAILABLE
        for c in station_map.seeded_corners:
            corner_candidate_matches.append(CornerCandidateMatch(
                seed_corner_id             = c.corner_id,
                matched_candidate_id       = c.corner_id if not c.is_seeded_placeholder else None,
                candidate_progress_pct     = c.approx_progress * 100.0,
                expected_apex_progress_pct = None,
                delta_pct                  = None,
                match_status               = CornerMatchStatus.SEED_POSITION_UNAVAILABLE,
                confidence                 = c.confidence,
                notes                      = f"{c.corner_id}: seed has no progress window — position unverified",
            ))
        corners_matched = 0
        corner_position_match = "NOT_AVAILABLE"
    else:
        # Seed has corner windows — check each official corner against its expected range
        def_by_id = {cd.corner_id: cd for cd in corner_defs}
        for c in station_map.seeded_corners:
            cdef = def_by_id.get(c.corner_id)
            if c.is_seeded_placeholder:
                status_cm = CornerMatchStatus.NO_CANDIDATE_IN_WINDOW
                notes_cm  = f"{c.corner_id}: placeholder — no curvature peak found in seed window"
                delta_cm  = None
                cand_pct  = None
                exp_apex  = cdef.apex_progress_pct if cdef else None
            elif cdef is None:
                status_cm = CornerMatchStatus.SEED_POSITION_UNAVAILABLE
                notes_cm  = f"{c.corner_id}: no seed window definition found"
                delta_cm  = None
                cand_pct  = c.approx_progress * 100.0
                exp_apex  = None
            else:
                cand_pct  = c.approx_progress * 100.0
                delta_cm  = abs(cand_pct - cdef.apex_progress_pct)
                status_cm = CornerMatchStatus.MATCHED
                notes_cm  = (
                    f"{c.corner_id}: apex at {cand_pct:.1f}% "
                    f"(expected {cdef.apex_progress_pct:.1f}%, Δ={delta_cm:.1f}%)"
                )
                exp_apex  = cdef.apex_progress_pct
                corners_matched += 1

            corner_candidate_matches.append(CornerCandidateMatch(
                seed_corner_id             = c.corner_id,
                matched_candidate_id       = c.corner_id if not c.is_seeded_placeholder else None,
                candidate_progress_pct     = cand_pct,
                expected_apex_progress_pct = exp_apex,
                delta_pct                  = delta_cm,
                match_status               = status_cm,
                confidence                 = c.confidence,
                notes                      = notes_cm,
            ))

        total_windows = len(corner_defs)
        if corners_matched == total_windows:
            corner_position_match = "PASS"
        elif corners_matched == 0:
            corner_position_match = "FAIL"
            blockers.append(
                "Corner position match failed — no seed window has a confirmed telemetry peak"
            )
        else:
            unmatched = total_windows - corners_matched
            corner_position_match = "PARTIAL"
            blockers.append(
                f"{unmatched} seed corner(s) have no telemetry match in their expected progress range"
            )

    # ── Corner alignments ──────────────────────────────────────────────────
    corner_alignments = [
        CornerAlignmentResult(
            corner_id       = c.corner_id,
            approx_progress = c.approx_progress,
            is_placeholder  = c.is_seeded_placeholder,
            confidence      = c.confidence,
        )
        for c in station_map.seeded_corners
    ]

    # ── Sector alignment ───────────────────────────────────────────────────
    if seed_sectors is not None and seed_sectors > 0:
        sector_alignment = SectorAlignmentResult(
            seed_sector_count = seed_sectors,
            status            = "not_available",
            note              = (
                f"Seed defines {seed_sectors} sector(s). "
                "Sector boundary positions are not available in GT7 seed data — "
                "sector count noted but cannot be verified against the model."
            ),
        )
    else:
        sector_alignment = SectorAlignmentResult(
            seed_sector_count = 0,
            status            = "not_available",
            note              = "Seed has no sector count — sector alignment skipped (non-critical)",
        )

    # ── Determine overall match status ─────────────────────────────────────
    # DEF-17Q-002: ACCEPTABLE_MATCH requires seed corner positions available + no blockers.
    # Without corner definitions, cap at GOOD_MATCH — cannot claim full position verification.
    if blockers:
        if delta_pct > _MAX_LAP_DELTA_PARTIAL_PCT and seed_length_m > 0:
            match_status = TrackModelMatchStatus.FAILED_MATCH
        else:
            match_status = TrackModelMatchStatus.PARTIAL_MATCH
    elif delta_pct > _MAX_LAP_DELTA_GOOD_PCT and seed_length_m > 0:
        match_status = TrackModelMatchStatus.PARTIAL_MATCH
    elif delta_pct <= _MAX_LAP_DELTA_STRICT_PCT and corner_defs:
        # Seed positions available, lap delta tight, no blockers — full acceptance possible
        match_status = TrackModelMatchStatus.ACCEPTABLE_MATCH
    else:
        # No seed position data, or lap delta 2–5% — good but not fully accepted
        match_status = TrackModelMatchStatus.GOOD_MATCH

    return TrackModelAlignmentResult(
        match_status           = match_status,
        seed_corners_expected  = seed_corners_expected,
        model_corners_found    = model_corners,
        extra_peaks_suppressed = extra_peaks,
        placeholder_count      = placeholder_cnt,
        lap_length_m_model     = lap_length_m,
        lap_length_m_seed      = seed_length_m,
        lap_length_delta_pct   = delta_pct,
        station_count          = station_count,
        confidence             = confidence,
        corner_alignments      = corner_alignments,
        sector_alignment       = sector_alignment,
        blockers               = blockers,
        warnings               = warnings,
        seed_corner_positions_available = seed_corner_positions_available,
        corner_position_match  = corner_position_match,
        corners_matched        = corners_matched,
        corner_candidate_matches = corner_candidate_matches,
    )


# ---------------------------------------------------------------------------
# Blockers helper
# ---------------------------------------------------------------------------

def get_alignment_blockers(result: TrackModelAlignmentResult) -> List[str]:
    """Return a list of human-readable blocker strings preventing acceptance."""
    return list(result.blockers)


# ---------------------------------------------------------------------------
# Accepted model persistence
# ---------------------------------------------------------------------------

def accepted_model_filename(track_location_id: str, layout_id: str) -> str:
    return f"{track_location_id}__{layout_id}.accepted_model.json"


def export_accepted_model_json(
    result: TrackModelAlignmentResult,
    track_location_id: str,
    layout_id: str,
    output_dir: Optional[Path] = None,
) -> Path:
    """Persist an accepted alignment result to JSON."""
    out_dir = Path(output_dir) if output_dir else STATION_MODELS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = accepted_model_filename(track_location_id, layout_id)
    path  = out_dir / fname

    payload = {
        "schema":                 ACCEPTED_MODEL_SCHEMA,
        "track_location_id":      track_location_id,
        "layout_id":              layout_id,
        "match_status":           result.match_status,
        "accepted":               result.accepted,
        "accepted_at":            result.accepted_at,
        "seed_corners_expected":  result.seed_corners_expected,
        "model_corners_found":    result.model_corners_found,
        "extra_peaks_suppressed": result.extra_peaks_suppressed,
        "placeholder_count":      result.placeholder_count,
        "lap_length_m_model":     result.lap_length_m_model,
        "lap_length_m_seed":      result.lap_length_m_seed,
        "lap_length_delta_pct":   result.lap_length_delta_pct,
        "station_count":          result.station_count,
        "confidence":             result.confidence,
        "blockers":               result.blockers,
        "warnings":               result.warnings,
        # Group 17Q fields
        "seed_corner_positions_available": result.seed_corner_positions_available,
        "corner_position_match":  result.corner_position_match,
        "corners_matched":        result.corners_matched,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    return path


def find_accepted_model_path(
    track_location_id: str,
    layout_id: str,
    base_dir: Optional[Path] = None,
) -> Optional[Path]:
    """Return the path to an existing accepted model file, or None."""
    d     = Path(base_dir) if base_dir else STATION_MODELS_DIR
    fname = accepted_model_filename(track_location_id, layout_id)
    p     = d / fname
    return p if p.exists() else None


def import_accepted_model_json(json_path: Path) -> Optional[TrackModelAlignmentResult]:
    """Load a previously accepted alignment result. Returns None on any error."""
    try:
        path = Path(json_path)
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if data.get("schema") != ACCEPTED_MODEL_SCHEMA:
            return None
        return TrackModelAlignmentResult(
            match_status           = TrackModelMatchStatus(data.get("match_status", "NOT_READY")),
            seed_corners_expected  = data.get("seed_corners_expected", 0),
            model_corners_found    = data.get("model_corners_found", 0),
            extra_peaks_suppressed = data.get("extra_peaks_suppressed", 0),
            placeholder_count      = data.get("placeholder_count", 0),
            lap_length_m_model     = data.get("lap_length_m_model", 0.0),
            lap_length_m_seed      = data.get("lap_length_m_seed", 0.0),
            lap_length_delta_pct   = data.get("lap_length_delta_pct", 0.0),
            station_count          = data.get("station_count", 0),
            confidence             = data.get("confidence", 0.0),
            corner_alignments      = [],
            sector_alignment       = SectorAlignmentResult(0, "not_available", "Loaded from disk"),
            blockers               = data.get("blockers", []),
            warnings               = data.get("warnings", []),
            accepted               = data.get("accepted", True),
            accepted_at            = data.get("accepted_at", ""),
            # Group 17Q — safe defaults for files saved before this group
            seed_corner_positions_available = bool(data.get("seed_corner_positions_available", False)),
            corner_position_match  = data.get("corner_position_match", "NOT_AVAILABLE"),
            corners_matched        = data.get("corners_matched", 0),
            corner_candidate_matches = [],
        )
    except Exception:  # noqa: BLE001
        return None
