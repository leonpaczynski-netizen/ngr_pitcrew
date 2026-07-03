"""Track Truth Foundation — Group 18A.

Single source of truth for what the system knows about a track layout:
coordinate geometry, corner windows, sectors, complexes, and pit lane definition.

This module is pure Python — no PyQt6 dependency.

Schema constants
----------------
TRUTH_MODEL_SCHEMA    = "track_truth_model_v1"
TRUTH_MANIFEST_SCHEMA = "track_truth_manifest_v1"

Public API
----------
Enums: TrackTruthStatus, TrackTruthConfidence, TrackTruthSource, TrackTruthValidationIssue
Dataclasses: TrackStation, CornerWindow, CornerComplex, SectorMarker, PitLaneDefinition,
             TrackTruthManifest, TrackTruthModel, TrackTruthValidationResult
JSON round-trip: track_truth_model_to_dict, track_truth_model_from_dict,
                 export_track_truth_model_json, import_track_truth_model_json
Runtime resolver: resolve_track_truth_model
Validation: validate_track_truth_model
AI guard: can_use_track_truth_for_ai_corner_context
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional

# ---------------------------------------------------------------------------
# Schema constants
# ---------------------------------------------------------------------------

TRUTH_MODEL_SCHEMA: str    = "track_truth_model_v1"
TRUTH_MANIFEST_SCHEMA: str = "track_truth_manifest_v1"


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TrackTruthStatus(str, Enum):
    NO_DATA               = "NO_DATA"
    METADATA_ONLY         = "METADATA_ONLY"
    CURVATURE_PROVISIONAL = "CURVATURE_PROVISIONAL"
    ACCEPTED_SEED_MAP     = "ACCEPTED_SEED_MAP"
    ACCEPTED_LIVE_MAPPING = "ACCEPTED_LIVE_MAPPING"


class TrackTruthConfidence(str, Enum):
    NONE   = "NONE"
    LOW    = "LOW"
    MEDIUM = "MEDIUM"
    HIGH   = "HIGH"


class TrackTruthSource(str, Enum):
    ESTIMATED           = "estimated"
    TELEMETRY_CAPTURED  = "telemetry_captured"
    ENGINEER_VALIDATED  = "engineer_validated"


class TrackTruthValidationIssue(str, Enum):
    NON_MONOTONIC_STATIONS      = "NON_MONOTONIC_STATIONS"
    PROGRESS_OUT_OF_RANGE       = "PROGRESS_OUT_OF_RANGE"
    LAP_LENGTH_ZERO_OR_NEG      = "LAP_LENGTH_ZERO_OR_NEG"
    APEX_OUTSIDE_WINDOW         = "APEX_OUTSIDE_WINDOW"
    COMPLEX_MISSING_MEMBER      = "COMPLEX_MISSING_MEMBER"
    SECTOR_PROGRESS_OUT_RANGE   = "SECTOR_PROGRESS_OUT_RANGE"
    CORNERS_EXPECTED_NO_WINDOWS = "CORNERS_EXPECTED_NO_WINDOWS"
    NO_COORDINATE_GEOMETRY      = "NO_COORDINATE_GEOMETRY"
    SINGLE_MEMBER_COMPLEX       = "SINGLE_MEMBER_COMPLEX"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class TrackStation:
    """One station on the track centreline — primary geometry unit."""
    station_id:       str
    station_m:        float
    progress_pct:     float
    x:                float = 0.0
    y:                float = 0.0
    z:                float = 0.0
    heading_rad:      float = 0.0
    curvature:        float = 0.0
    left_width_m:     float = 0.0
    right_width_m:    float = 0.0
    corner_id:        Optional[str] = None
    corner_phase:     Optional[str] = None
    complex_id:       Optional[str] = None
    sector_id:        Optional[str] = None
    pit_context:      Optional[str] = None


@dataclass
class CornerWindow:
    """Progress-window description of one corner."""
    corner_id:          str
    display_name:       str             = ""
    start_progress_pct: float           = 0.0
    apex_progress_pct:  float           = 0.0
    end_progress_pct:   float           = 0.0
    corner_type:        str             = "unknown"
    expected_gear_min:  Optional[int]   = None
    expected_gear_max:  Optional[int]   = None
    direction:          str             = "unknown"
    sector_id:          Optional[str]   = None
    source:             str             = "estimated"
    confidence:         str             = "low"
    notes:              str             = ""


@dataclass
class CornerComplex:
    """A named group of two or more geometrically-linked corners."""
    complex_id:         str
    display_name:       str
    corner_ids:         List[str]       = field(default_factory=list)
    start_progress_pct: float           = 0.0
    end_progress_pct:   float           = 0.0
    coaching_name:      str             = ""
    sector_id:          Optional[str]   = None
    notes:              str             = ""


@dataclass
class SectorMarker:
    """Sector boundary definition by progress percentage."""
    sector_id:          str
    start_progress_pct: float
    end_progress_pct:   float
    display_name:       str = ""
    source:             str = "estimated"
    confidence:         str = "low"


@dataclass
class PitLaneDefinition:
    """Pit lane entry, lane, and exit windows by progress percentage."""
    entry_start_progress_pct: float
    entry_end_progress_pct:   float
    lane_start_progress_pct:  float
    lane_end_progress_pct:    float
    exit_start_progress_pct:  float
    exit_end_progress_pct:    float
    notes:                    str = ""


@dataclass
class TrackTruthManifest:
    """Summary metadata for a Track Truth model — written as nested dict under 'manifest'."""
    schema:                   str   = TRUTH_MANIFEST_SCHEMA
    track_id:                 str   = ""
    layout_id:                str   = ""
    display_name:             str   = ""
    lap_length_m:             float = 0.0
    corners_expected:         int   = 0
    seed_geometry_available:  bool  = False
    corners_are_seed_verified: bool = False   # explicit field per Group 18A correction
    source:                   str   = "estimated"
    confidence:               str   = "low"


@dataclass
class TrackTruthModel:
    """Complete Track Truth model — geometry + semantic features for one layout."""
    manifest:         TrackTruthManifest
    corner_windows:   List[CornerWindow]  = field(default_factory=list)
    corner_complexes: List[CornerComplex] = field(default_factory=list)
    sectors:          List[SectorMarker]  = field(default_factory=list)
    stations:         List[TrackStation]  = field(default_factory=list)
    pit_lane:         Optional[PitLaneDefinition] = None


@dataclass
class TrackTruthValidationResult:
    """Result of validate_track_truth_model()."""
    is_accepted:                   bool
    is_usable_for_live_mapping:    bool
    is_usable_for_ai_corner_context: bool
    status:                        TrackTruthStatus
    blockers:                      List[str]
    warnings:                      List[str]
    summary:                       str
    issues:                        List[str] = field(default_factory=list)
    # issues = list of TrackTruthValidationIssue member values (as strings)


# ---------------------------------------------------------------------------
# JSON round-trip helpers (private)
# ---------------------------------------------------------------------------

def _parse_station(raw: dict) -> TrackStation:
    return TrackStation(
        station_id   = str(raw.get("station_id", "")),
        station_m    = float(raw.get("station_m", 0.0)),
        progress_pct = float(raw.get("progress_pct", 0.0)),
        x            = float(raw.get("x", 0.0)),
        y            = float(raw.get("y", 0.0)),
        z            = float(raw.get("z", 0.0)),
        heading_rad  = float(raw.get("heading_rad", 0.0)),
        curvature    = float(raw.get("curvature", 0.0)),
        left_width_m  = float(raw.get("left_width_m", 0.0)),
        right_width_m = float(raw.get("right_width_m", 0.0)),
        corner_id    = raw.get("corner_id"),
        corner_phase = raw.get("corner_phase"),
        complex_id   = raw.get("complex_id"),
        sector_id    = raw.get("sector_id"),
        pit_context  = raw.get("pit_context"),
    )


def _parse_corner_window(raw: dict) -> CornerWindow:
    return CornerWindow(
        corner_id          = str(raw.get("corner_id", "")),
        display_name       = str(raw.get("display_name", "")),
        start_progress_pct = float(raw.get("start_progress_pct", 0.0)),
        apex_progress_pct  = float(raw.get("apex_progress_pct", 0.0)),
        end_progress_pct   = float(raw.get("end_progress_pct", 0.0)),
        corner_type        = str(raw.get("corner_type", "unknown")),
        expected_gear_min  = raw.get("expected_gear_min"),
        expected_gear_max  = raw.get("expected_gear_max"),
        direction          = str(raw.get("direction", "unknown")),
        sector_id          = raw.get("sector_id"),
        source             = str(raw.get("source", "estimated")),
        confidence         = str(raw.get("confidence", "low")),
        notes              = str(raw.get("notes", "")),
    )


def _parse_corner_complex(raw: dict) -> CornerComplex:
    return CornerComplex(
        complex_id         = str(raw.get("complex_id", "")),
        display_name       = str(raw.get("display_name", "")),
        corner_ids         = list(raw.get("corner_ids", [])),
        start_progress_pct = float(raw.get("start_progress_pct", 0.0)),
        end_progress_pct   = float(raw.get("end_progress_pct", 0.0)),
        coaching_name      = str(raw.get("coaching_name", "")),
        sector_id          = raw.get("sector_id"),
        notes              = str(raw.get("notes", "")),
    )


def _parse_sector(raw: dict) -> SectorMarker:
    return SectorMarker(
        sector_id          = str(raw.get("sector_id", "")),
        start_progress_pct = float(raw.get("start_progress_pct", 0.0)),
        end_progress_pct   = float(raw.get("end_progress_pct", 0.0)),
        display_name       = str(raw.get("display_name", "")),
        source             = str(raw.get("source", "estimated")),
        confidence         = str(raw.get("confidence", "low")),
    )


def _parse_pit_lane(raw: dict) -> PitLaneDefinition:
    return PitLaneDefinition(
        entry_start_progress_pct = float(raw.get("entry_start_progress_pct", 0.0)),
        entry_end_progress_pct   = float(raw.get("entry_end_progress_pct", 0.0)),
        lane_start_progress_pct  = float(raw.get("lane_start_progress_pct", 0.0)),
        lane_end_progress_pct    = float(raw.get("lane_end_progress_pct", 0.0)),
        exit_start_progress_pct  = float(raw.get("exit_start_progress_pct", 0.0)),
        exit_end_progress_pct    = float(raw.get("exit_end_progress_pct", 0.0)),
        notes                    = str(raw.get("notes", "")),
    )


def _parse_manifest(raw: dict) -> TrackTruthManifest:
    return TrackTruthManifest(
        schema                   = str(raw.get("schema", TRUTH_MANIFEST_SCHEMA)),
        track_id                 = str(raw.get("track_id", "")),
        layout_id                = str(raw.get("layout_id", "")),
        display_name             = str(raw.get("display_name", "")),
        lap_length_m             = float(raw.get("lap_length_m", 0.0)),
        corners_expected         = int(raw.get("corners_expected", 0)),
        seed_geometry_available  = bool(raw.get("seed_geometry_available", False)),
        corners_are_seed_verified = bool(raw.get("corners_are_seed_verified", False)),
        source                   = str(raw.get("source", "estimated")),
        confidence               = str(raw.get("confidence", "low")),
    )


# ---------------------------------------------------------------------------
# JSON round-trip (public)
# ---------------------------------------------------------------------------

def track_truth_model_to_dict(model: TrackTruthModel) -> dict:
    """Serialise a TrackTruthModel to a JSON-compatible dict."""
    m = model.manifest
    manifest_dict = {
        "schema":                    m.schema,
        "track_id":                  m.track_id,
        "layout_id":                 m.layout_id,
        "display_name":              m.display_name,
        "lap_length_m":              m.lap_length_m,
        "corners_expected":          m.corners_expected,
        "seed_geometry_available":   m.seed_geometry_available,
        "corners_are_seed_verified": m.corners_are_seed_verified,
        "source":                    m.source,
        "confidence":                m.confidence,
    }

    def _cw_to_dict(cw: CornerWindow) -> dict:
        d: dict = {
            "corner_id":          cw.corner_id,
            "display_name":       cw.display_name,
            "start_progress_pct": cw.start_progress_pct,
            "apex_progress_pct":  cw.apex_progress_pct,
            "end_progress_pct":   cw.end_progress_pct,
            "corner_type":        cw.corner_type,
            "direction":          cw.direction,
            "source":             cw.source,
            "confidence":         cw.confidence,
            "notes":              cw.notes,
        }
        if cw.expected_gear_min is not None:
            d["expected_gear_min"] = cw.expected_gear_min
        if cw.expected_gear_max is not None:
            d["expected_gear_max"] = cw.expected_gear_max
        if cw.sector_id is not None:
            d["sector_id"] = cw.sector_id
        return d

    def _cc_to_dict(cc: CornerComplex) -> dict:
        d: dict = {
            "complex_id":         cc.complex_id,
            "display_name":       cc.display_name,
            "corner_ids":         list(cc.corner_ids),
            "start_progress_pct": cc.start_progress_pct,
            "end_progress_pct":   cc.end_progress_pct,
            "coaching_name":      cc.coaching_name,
            "notes":              cc.notes,
        }
        if cc.sector_id is not None:
            d["sector_id"] = cc.sector_id
        return d

    def _sm_to_dict(sm: SectorMarker) -> dict:
        return {
            "sector_id":          sm.sector_id,
            "start_progress_pct": sm.start_progress_pct,
            "end_progress_pct":   sm.end_progress_pct,
            "display_name":       sm.display_name,
            "source":             sm.source,
            "confidence":         sm.confidence,
        }

    def _st_to_dict(st: TrackStation) -> dict:
        d: dict = {
            "station_id":    st.station_id,
            "station_m":     st.station_m,
            "progress_pct":  st.progress_pct,
            "x":             st.x,
            "y":             st.y,
            "z":             st.z,
            "heading_rad":   st.heading_rad,
            "curvature":     st.curvature,
            "left_width_m":  st.left_width_m,
            "right_width_m": st.right_width_m,
        }
        if st.corner_id is not None:
            d["corner_id"]   = st.corner_id
        if st.corner_phase is not None:
            d["corner_phase"] = st.corner_phase
        if st.complex_id is not None:
            d["complex_id"]  = st.complex_id
        if st.sector_id is not None:
            d["sector_id"]   = st.sector_id
        if st.pit_context is not None:
            d["pit_context"] = st.pit_context
        return d

    def _pl_to_dict(pl: PitLaneDefinition) -> dict:
        return {
            "entry_start_progress_pct": pl.entry_start_progress_pct,
            "entry_end_progress_pct":   pl.entry_end_progress_pct,
            "lane_start_progress_pct":  pl.lane_start_progress_pct,
            "lane_end_progress_pct":    pl.lane_end_progress_pct,
            "exit_start_progress_pct":  pl.exit_start_progress_pct,
            "exit_end_progress_pct":    pl.exit_end_progress_pct,
            "notes":                    pl.notes,
        }

    return {
        "schema":           TRUTH_MODEL_SCHEMA,
        "manifest":         manifest_dict,
        "corner_windows":   [_cw_to_dict(cw) for cw in model.corner_windows],
        "corner_complexes": [_cc_to_dict(cc) for cc in model.corner_complexes],
        "sectors":          [_sm_to_dict(sm) for sm in model.sectors],
        "stations":         [_st_to_dict(st) for st in model.stations],
        "pit_lane":         _pl_to_dict(model.pit_lane) if model.pit_lane else None,
    }


def track_truth_model_from_dict(raw) -> Optional[TrackTruthModel]:
    """Deserialise a TrackTruthModel from a raw dict.

    Returns None if raw is not a dict, schema mismatch, or any parsing error.
    """
    if not isinstance(raw, dict):
        return None
    if raw.get("schema") != TRUTH_MODEL_SCHEMA:
        return None
    try:
        manifest = _parse_manifest(raw.get("manifest", {}))
        corner_windows   = [_parse_corner_window(c) for c in raw.get("corner_windows", [])]
        corner_complexes = [_parse_corner_complex(c) for c in raw.get("corner_complexes", [])]
        sectors          = [_parse_sector(s)         for s in raw.get("sectors", [])]
        stations         = [_parse_station(s)        for s in raw.get("stations", [])]
        pit_raw = raw.get("pit_lane")
        pit_lane = _parse_pit_lane(pit_raw) if isinstance(pit_raw, dict) else None
        return TrackTruthModel(
            manifest         = manifest,
            corner_windows   = corner_windows,
            corner_complexes = corner_complexes,
            sectors          = sectors,
            stations         = stations,
            pit_lane         = pit_lane,
        )
    except Exception:
        return None


def export_track_truth_model_json(model: TrackTruthModel, path) -> None:
    """Write a TrackTruthModel to a JSON file.  Never raises."""
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        raw = track_truth_model_to_dict(model)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        tmp.replace(p)
    except Exception:
        pass


def import_track_truth_model_json(path) -> Optional[TrackTruthModel]:
    """Load a TrackTruthModel from a JSON file.  Returns None on any error."""
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
        return track_truth_model_from_dict(raw)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Runtime resolver
# ---------------------------------------------------------------------------

def resolve_track_truth_model(
    track_id:  str,
    layout_id: str,
    base_dir:  Optional[Path] = None,
) -> Optional[TrackTruthModel]:
    """Build a TrackTruthModel from the track library for the given layout.

    Reads:
    - data/track_library layout manifest (lap_length_m, availability)
    - semantic_model.json (corners, complexes, sectors)
    - geometry.seed_map.json (stations) if available

    Returns None only when the layout manifest fails to load.
    Corrupt seed map → stations=[] (never raises).
    """
    try:
        from data.track_library import (
            resolve_track_layout_manifest,
            load_track_semantic_model,
            resolve_seed_coordinate_map,
        )
    except Exception:
        return None

    # --- Layout manifest (required) ---
    manifest = resolve_track_layout_manifest(track_id, layout_id, base_dir)
    if manifest is None:
        return None

    lap_length_m            = manifest.lap_length_m
    seed_geometry_available = manifest.availability.seed_geometry
    source                  = manifest.source
    confidence              = manifest.confidence
    display_name            = manifest.display_name

    # --- Semantic model (optional — we proceed gracefully if absent) ---
    sem = load_track_semantic_model(track_id, layout_id, base_dir)

    corners_expected = 0
    corner_windows: List[CornerWindow]   = []
    corner_complexes: List[CornerComplex] = []
    sectors: List[SectorMarker]          = []

    if sem is not None:
        corners_expected = len(sem.corners)

        for c in sem.corners:
            corner_windows.append(CornerWindow(
                corner_id          = str(c.get("corner_id", "")),
                display_name       = str(c.get("display_name", "")),
                start_progress_pct = float(c.get("start_progress_pct", 0.0)),
                apex_progress_pct  = float(c.get("apex_progress_pct", 0.0)),
                end_progress_pct   = float(c.get("end_progress_pct", 0.0)),
                corner_type        = str(c.get("corner_type", "unknown")),
                expected_gear_min  = c.get("expected_gear_min"),
                expected_gear_max  = c.get("expected_gear_max"),
                direction          = str(c.get("direction", "unknown")),
                sector_id          = c.get("sector_id"),
                source             = str(c.get("source", "estimated")),
                confidence         = str(c.get("confidence", "low")),
                notes              = str(c.get("notes", "")),
            ))

        for cx in sem.complexes:
            # semantic model uses "member_corner_ids" in JSON
            corner_ids = list(cx.get("member_corner_ids", cx.get("corner_ids", [])))
            corner_complexes.append(CornerComplex(
                complex_id         = str(cx.get("complex_id", "")),
                display_name       = str(cx.get("display_name", "")),
                corner_ids         = corner_ids,
                start_progress_pct = float(cx.get("start_progress_pct", 0.0)),
                end_progress_pct   = float(cx.get("end_progress_pct", 0.0)),
                coaching_name      = str(cx.get("coaching_name", "")),
                sector_id          = cx.get("sector_id"),
                notes              = str(cx.get("notes", "")),
            ))

        for s in sem.sectors:
            # sector_id is always a string e.g. "S1"
            sectors.append(SectorMarker(
                sector_id          = str(s.get("sector_id", "")),
                start_progress_pct = float(s.get("start_progress_pct", 0.0)),
                end_progress_pct   = float(s.get("end_progress_pct", 0.0)),
                display_name       = str(s.get("display_name", "")),
                source             = str(s.get("source", "estimated")),
                confidence         = str(s.get("confidence", "low")),
            ))

    # --- Seed coordinate map → stations (optional) ---
    stations: List[TrackStation] = []
    try:
        seed_map, _source_label = resolve_seed_coordinate_map(track_id, layout_id, base_dir)
        if seed_map is not None and seed_map.stations:
            for i, sms in enumerate(seed_map.stations):
                stations.append(TrackStation(
                    station_id   = f"{layout_id}@{sms.station_m:.1f}",
                    station_m    = sms.station_m,
                    progress_pct = sms.progress_pct,
                    x            = sms.x,
                    y            = sms.y,
                    z            = sms.z,
                    corner_id    = sms.corner_id,
                    sector_id    = str(sms.sector_id) if sms.sector_id is not None else None,
                    left_width_m  = sms.width_left_m  if sms.width_left_m  is not None else 0.0,
                    right_width_m = sms.width_right_m if sms.width_right_m is not None else 0.0,
                ))
    except Exception:
        stations = []

    truth_manifest = TrackTruthManifest(
        schema                   = TRUTH_MANIFEST_SCHEMA,
        track_id                 = track_id,
        layout_id                = layout_id,
        display_name             = display_name,
        lap_length_m             = lap_length_m,
        corners_expected         = corners_expected,
        seed_geometry_available  = seed_geometry_available,
        corners_are_seed_verified = False,   # corners are estimated for Daytona
        source                   = source,
        confidence               = confidence,
    )

    return TrackTruthModel(
        manifest         = truth_manifest,
        corner_windows   = corner_windows,
        corner_complexes = corner_complexes,
        sectors          = sectors,
        stations         = stations,
        pit_lane         = None,
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_track_truth_model(model: TrackTruthModel) -> TrackTruthValidationResult:
    """Validate a TrackTruthModel and return a detailed result.

    BLOCKERS prevent is_accepted.
    WARNINGS are informational only.
    issues[] contains TrackTruthValidationIssue member values as strings
    for each blocker or warning triggered.
    """
    blockers: List[str] = []
    warnings: List[str] = []
    issues:   List[str] = []

    m = model.manifest

    # --- BLOCKER: lap length ---
    if m.lap_length_m <= 0:
        blockers.append("Lap length is zero or negative")
        issues.append(TrackTruthValidationIssue.LAP_LENGTH_ZERO_OR_NEG)

    # --- BLOCKER: station monotonicity ---
    if model.stations:
        prev_m = model.stations[0].station_m
        monotonic = True
        for st in model.stations[1:]:
            if st.station_m <= prev_m:
                monotonic = False
                break
            prev_m = st.station_m
        if not monotonic:
            blockers.append("Station distances are not strictly increasing (non-monotonic)")
            issues.append(TrackTruthValidationIssue.NON_MONOTONIC_STATIONS)

    # --- BLOCKER: station progress out of range ---
    for st in model.stations:
        if not (0.0 <= st.progress_pct <= 100.0):
            blockers.append(
                f"Station '{st.station_id}' progress_pct {st.progress_pct:.2f} is outside [0, 100]"
            )
            issues.append(TrackTruthValidationIssue.PROGRESS_OUT_OF_RANGE)
            break   # one blocker entry per rule

    # --- BLOCKER: apex outside window ---
    for cw in model.corner_windows:
        if not (cw.start_progress_pct <= cw.apex_progress_pct <= cw.end_progress_pct):
            blockers.append(
                f"Corner '{cw.corner_id}' apex {cw.apex_progress_pct:.2f}% is outside "
                f"window [{cw.start_progress_pct:.2f}, {cw.end_progress_pct:.2f}]"
            )
            issues.append(TrackTruthValidationIssue.APEX_OUTSIDE_WINDOW)
            break

    # --- BLOCKER: complex member not in corner windows ---
    known_corner_ids = {cw.corner_id for cw in model.corner_windows}
    for cc in model.corner_complexes:
        for cid in cc.corner_ids:
            if cid not in known_corner_ids:
                blockers.append(
                    f"Complex '{cc.complex_id}' references corner '{cid}' which is not in corner_windows"
                )
                issues.append(TrackTruthValidationIssue.COMPLEX_MISSING_MEMBER)
                break
        else:
            continue
        break

    # --- BLOCKER: sector progress out of range ---
    for sm in model.sectors:
        if not (0.0 <= sm.start_progress_pct <= 100.0) or not (0.0 <= sm.end_progress_pct <= 100.0):
            blockers.append(
                f"Sector '{sm.sector_id}' progress [{sm.start_progress_pct:.2f}, "
                f"{sm.end_progress_pct:.2f}] contains values outside [0, 100]"
            )
            issues.append(TrackTruthValidationIssue.SECTOR_PROGRESS_OUT_RANGE)
            break

    # --- BLOCKER: corners expected but no windows ---
    if m.corners_expected > 0 and len(model.corner_windows) == 0:
        blockers.append(
            f"corners_expected={m.corners_expected} but no corner_windows present"
        )
        issues.append(TrackTruthValidationIssue.CORNERS_EXPECTED_NO_WINDOWS)

    # --- BLOCKER: no coordinate geometry ---
    if len(model.stations) == 0:
        blockers.append(
            "Coordinate geometry unavailable — high-confidence corner mapping is blocked"
        )
        issues.append(TrackTruthValidationIssue.NO_COORDINATE_GEOMETRY)

    # --- WARNING: single-member complex ---
    for cc in model.corner_complexes:
        if len(cc.corner_ids) == 1:
            warnings.append(
                f"Complex '{cc.complex_id}' has only 1 member corner — usually complexes have 2+"
            )
            issues.append(TrackTruthValidationIssue.SINGLE_MEMBER_COMPLEX)

    # --- Derive acceptance flags ---
    is_accepted = len(blockers) == 0

    is_usable_for_live_mapping = (
        is_accepted
        and len(model.stations) > 0
        and m.corners_are_seed_verified
    )

    is_usable_for_ai_corner_context = (
        is_usable_for_live_mapping
        and m.seed_geometry_available
    )

    # --- Derive status ---
    if len(model.stations) == 0:
        status = TrackTruthStatus.METADATA_ONLY
    elif not is_accepted:
        # Has stations but failed validation — not usable in any accepted/provisional sense
        status = TrackTruthStatus.NO_DATA
    elif model.corner_windows and not m.corners_are_seed_verified:
        status = TrackTruthStatus.CURVATURE_PROVISIONAL
    elif not is_usable_for_live_mapping:
        status = TrackTruthStatus.ACCEPTED_SEED_MAP
    elif is_usable_for_live_mapping:
        status = TrackTruthStatus.ACCEPTED_LIVE_MAPPING
    else:
        status = TrackTruthStatus.NO_DATA

    # --- Summary string ---
    if not is_accepted:
        if status == TrackTruthStatus.METADATA_ONLY:
            summary = "Metadata only — coordinate geometry unavailable"
        else:
            summary = f"Validation failed — {len(blockers)} blocker(s) present"
    elif status == TrackTruthStatus.CURVATURE_PROVISIONAL:
        summary = "Curvature-provisional — corner mapping unverified"
    elif status == TrackTruthStatus.ACCEPTED_SEED_MAP:
        summary = "Track Truth accepted — Seed Map Ready"
    elif status == TrackTruthStatus.ACCEPTED_LIVE_MAPPING:
        summary = "Track Truth accepted — Live Mapping Ready"
    elif status == TrackTruthStatus.METADATA_ONLY:
        summary = "Metadata only — coordinate geometry unavailable"
    else:
        summary = "No data available"

    return TrackTruthValidationResult(
        is_accepted                   = is_accepted,
        is_usable_for_live_mapping    = is_usable_for_live_mapping,
        is_usable_for_ai_corner_context = is_usable_for_ai_corner_context,
        status                        = status,
        blockers                      = blockers,
        warnings                      = warnings,
        summary                       = summary,
        issues                        = [i.value for i in issues],
    )


# ---------------------------------------------------------------------------
# AI guard
# ---------------------------------------------------------------------------

def can_use_track_truth_for_ai_corner_context(
    result: Optional[TrackTruthValidationResult],
) -> bool:
    """Return True only when the model is fully accepted and suitable for AI corner context.

    Safe to call with None — always returns False rather than raising.
    """
    if result is None:
        return False
    if not result.is_accepted:
        return False
    if not result.is_usable_for_ai_corner_context:
        return False
    return True
