"""Track Library — versioned track knowledge registry for NGR Pit Crew.

Replaces ad hoc file discovery with a structured, schema-versioned registry.

Directory layout
----------------
data/track_library/
    index.json                              TrackLibraryIndex
    tracks/
        <track_id>/
            track.json                      TrackMetadata
            layouts/
                <layout_id>/
                    manifest.json           TrackLayoutManifest
                    semantic_model.json     TrackSemanticModel
                    geometry.seed_map.json  SeedCoordinateMap (optional)
                    width.json              WidthModel (optional)
                    validation_rules.json   ValidationRules
                    source_manifest.json    SourceManifest
                    accepted_models/        accepted station map files
                    calibration_runs/       calibration run references

Resolver priority (for seed coordinate maps)
--------------------------------------------
1. Track library path  → data/track_library/tracks/<id>/layouts/<id>/geometry.seed_map.json
2. Legacy fallback     → data/track_seed_maps/<track_id>__<layout_id>.seed_map.json

All public functions return None (never raise) when files are missing or malformed.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple

TRACK_LIBRARY_BASE = Path(__file__).parent / "track_library"

# ─────────────────────────────────────────────
# Dataclasses
# ─────────────────────────────────────────────

@dataclass
class TrackLibraryIndex:
    schema: str
    library_version: str
    tracks: list = field(default_factory=list)   # list of track_ids
    created_at: str = ""
    updated_at: str = ""


@dataclass
class TrackMetadata:
    schema: str
    track_id: str
    display_name: str
    country: str = ""
    gt7_track_code: str = ""
    layouts: list = field(default_factory=list)  # list of layout_ids


@dataclass
class TrackLibraryAvailability:
    metadata:          bool = True
    sectors:           bool = False
    corner_windows:    bool = False
    corner_complexes:  bool = False
    seed_geometry:     bool = False
    width_model:       bool = False
    accepted_model:    bool = False
    calibration_runs:  bool = False


@dataclass
class TrackLayoutManifest:
    schema:        str
    track_id:      str
    layout_id:     str
    display_name:  str
    lap_length_m:  float
    reverse_layout: bool = False
    assets:        dict  = field(default_factory=dict)
    availability:  TrackLibraryAvailability = field(default_factory=TrackLibraryAvailability)
    source:        str   = "estimated"
    confidence:    str   = "low"
    # Group 55: optional pit-lane mapping block (backward-compatible; {} when absent).
    # Shape: {"available": bool, "source": str, "segments": [ {zone, start_progress,
    #         end_progress, label}, ... ]}. Missing / older manifests → {}.
    pit_lane:      dict  = field(default_factory=dict)


@dataclass
class TrackSemanticModel:
    schema:    str
    track_id:  str
    layout_id: str
    sectors:   list = field(default_factory=list)
    corners:   list = field(default_factory=list)
    complexes: list = field(default_factory=list)
    notes:     str  = ""


@dataclass
class ValidationAcceptance:
    max_lap_delta_pct:          float = 5.0
    max_mean_geometry_error_m:  float = 15.0
    max_corner_apex_delta_pct:  float = 5.0
    require_seed_geometry:      bool  = False
    require_corner_windows:     bool  = False
    require_sectors:            bool  = False


@dataclass
class ValidationWarningThresholds:
    lap_delta_pct:   float = 2.0
    geometry_error_m: float = 5.0


@dataclass
class ValidationRules:
    schema:     str
    track_id:   str
    layout_id:  str
    acceptance: ValidationAcceptance         = field(default_factory=ValidationAcceptance)
    warnings:   ValidationWarningThresholds  = field(default_factory=ValidationWarningThresholds)


@dataclass
class SourceManifest:
    schema:           str
    track_id:         str
    layout_id:        str
    sources:          list = field(default_factory=list)
    fields_estimated: list = field(default_factory=list)
    fields_verified:  list = field(default_factory=list)
    notes:            str  = ""
    last_reviewed_at: str  = ""


@dataclass
class TrackLibraryAuditResult:
    """Audit of what the track library knows about a specific layout."""
    library_available:     bool  = False
    manifest_loaded:       bool  = False
    semantic_model_loaded: bool  = False
    validation_rules_loaded: bool = False
    seed_geometry_in_library: bool = False
    seed_geometry_legacy:     bool = False
    availability:          Optional[TrackLibraryAvailability] = None
    manifest_display_name: str  = ""
    manifest_lap_length_m: float = 0.0
    # "track_library" / "legacy_fallback" / "none"
    seed_coordinate_source: str = "none"
    warnings:              list = field(default_factory=list)


# ─────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────

def _layout_dir(track_id: str, layout_id: str, base_dir: Optional[Path] = None) -> Path:
    base = base_dir if base_dir is not None else TRACK_LIBRARY_BASE
    return base / "tracks" / track_id / "layouts" / layout_id


def _load_json(path: Path) -> Optional[dict]:
    """Load JSON file; return None if absent or malformed."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _parse_availability(raw: dict) -> TrackLibraryAvailability:
    a = raw.get("availability", {}) or {}
    return TrackLibraryAvailability(
        metadata         = bool(a.get("metadata", True)),
        sectors          = bool(a.get("sectors", False)),
        corner_windows   = bool(a.get("corner_windows", False)),
        corner_complexes = bool(a.get("corner_complexes", False)),
        seed_geometry    = bool(a.get("seed_geometry", False)),
        width_model      = bool(a.get("width_model", False)),
        accepted_model   = bool(a.get("accepted_model", False)),
        calibration_runs = bool(a.get("calibration_runs", False)),
    )


def _parse_acceptance(raw: dict) -> ValidationAcceptance:
    a = raw.get("acceptance", {}) or {}
    return ValidationAcceptance(
        max_lap_delta_pct         = float(a.get("max_lap_delta_pct", 5.0)),
        max_mean_geometry_error_m = float(a.get("max_mean_geometry_error_m", 15.0)),
        max_corner_apex_delta_pct = float(a.get("max_corner_apex_delta_pct", 5.0)),
        require_seed_geometry     = bool(a.get("require_seed_geometry", False)),
        require_corner_windows    = bool(a.get("require_corner_windows", False)),
        require_sectors           = bool(a.get("require_sectors", False)),
    )


def _parse_warn_thresholds(raw: dict) -> ValidationWarningThresholds:
    w = raw.get("warnings", {}) or {}
    return ValidationWarningThresholds(
        lap_delta_pct    = float(w.get("lap_delta_pct", 2.0)),
        geometry_error_m = float(w.get("geometry_error_m", 5.0)),
    )


# ─────────────────────────────────────────────
# Public loader functions
# ─────────────────────────────────────────────

def track_library_base_dir() -> Path:
    """Return the base directory for the track library."""
    return TRACK_LIBRARY_BASE


def load_track_library_index(base_dir: Optional[Path] = None) -> Optional[TrackLibraryIndex]:
    """Load data/track_library/index.json; return None if absent or malformed."""
    base = base_dir if base_dir is not None else TRACK_LIBRARY_BASE
    raw = _load_json(base / "index.json")
    if raw is None:
        return None
    if raw.get("schema") != "track_library_index_v1":
        return None
    return TrackLibraryIndex(
        schema          = raw.get("schema", ""),
        library_version = raw.get("library_version", ""),
        tracks          = list(raw.get("tracks", [])),
        created_at      = raw.get("created_at", ""),
        updated_at      = raw.get("updated_at", ""),
    )


def load_track_metadata(track_id: str, base_dir: Optional[Path] = None) -> Optional[TrackMetadata]:
    """Load tracks/<track_id>/track.json; return None if absent or malformed."""
    base = base_dir if base_dir is not None else TRACK_LIBRARY_BASE
    raw = _load_json(base / "tracks" / track_id / "track.json")
    if raw is None:
        return None
    if raw.get("schema") != "track_metadata_v1":
        return None
    return TrackMetadata(
        schema        = raw.get("schema", ""),
        track_id      = raw.get("track_id", ""),
        display_name  = raw.get("display_name", ""),
        country       = raw.get("country", ""),
        gt7_track_code = raw.get("gt7_track_code", ""),
        layouts       = list(raw.get("layouts", [])),
    )


def resolve_track_layout_manifest(
    track_id:  str,
    layout_id: str,
    base_dir:  Optional[Path] = None,
) -> Optional[TrackLayoutManifest]:
    """Load manifest.json for a specific layout; return None if absent or malformed."""
    ldir = _layout_dir(track_id, layout_id, base_dir)
    raw  = _load_json(ldir / "manifest.json")
    if raw is None:
        return None
    if raw.get("schema") != "track_layout_manifest_v1":
        return None
    return TrackLayoutManifest(
        schema        = raw.get("schema", ""),
        track_id      = raw.get("track_id", ""),
        layout_id     = raw.get("layout_id", ""),
        display_name  = raw.get("display_name", ""),
        lap_length_m  = float(raw.get("lap_length_m", 0.0)),
        reverse_layout = bool(raw.get("reverse_layout", False)),
        assets        = dict(raw.get("assets", {})),
        availability  = _parse_availability(raw),
        source        = raw.get("source", "estimated"),
        confidence    = raw.get("confidence", "low"),
        pit_lane      = dict(raw.get("pit_lane", {}) or {}),
    )


def load_track_semantic_model(
    track_id:  str,
    layout_id: str,
    base_dir:  Optional[Path] = None,
) -> Optional[TrackSemanticModel]:
    """Load semantic_model.json for a specific layout; return None if absent or malformed."""
    ldir = _layout_dir(track_id, layout_id, base_dir)
    raw  = _load_json(ldir / "semantic_model.json")
    if raw is None:
        return None
    if raw.get("schema") != "track_semantic_model_v1":
        return None
    return TrackSemanticModel(
        schema    = raw.get("schema", ""),
        track_id  = raw.get("track_id", ""),
        layout_id = raw.get("layout_id", ""),
        sectors   = list(raw.get("sectors", [])),
        corners   = list(raw.get("corners", [])),
        complexes = list(raw.get("complexes", [])),
        notes     = raw.get("notes", ""),
    )


def load_validation_rules(
    track_id:  str,
    layout_id: str,
    base_dir:  Optional[Path] = None,
) -> Optional[ValidationRules]:
    """Load validation_rules.json for a specific layout; return None if absent or malformed."""
    ldir = _layout_dir(track_id, layout_id, base_dir)
    raw  = _load_json(ldir / "validation_rules.json")
    if raw is None:
        return None
    if raw.get("schema") != "validation_rules_v1":
        return None
    return ValidationRules(
        schema     = raw.get("schema", ""),
        track_id   = raw.get("track_id", ""),
        layout_id  = raw.get("layout_id", ""),
        acceptance = _parse_acceptance(raw),
        warnings   = _parse_warn_thresholds(raw),
    )


def load_source_manifest(
    track_id:  str,
    layout_id: str,
    base_dir:  Optional[Path] = None,
) -> Optional[SourceManifest]:
    """Load source_manifest.json for a specific layout; return None if absent or malformed."""
    ldir = _layout_dir(track_id, layout_id, base_dir)
    raw  = _load_json(ldir / "source_manifest.json")
    if raw is None:
        return None
    if raw.get("schema") != "source_manifest_v1":
        return None
    return SourceManifest(
        schema           = raw.get("schema", ""),
        track_id         = raw.get("track_id", ""),
        layout_id        = raw.get("layout_id", ""),
        sources          = list(raw.get("sources", [])),
        fields_estimated = list(raw.get("fields_estimated", [])),
        fields_verified  = list(raw.get("fields_verified", [])),
        notes            = raw.get("notes", ""),
        last_reviewed_at = raw.get("last_reviewed_at", ""),
    )


def load_track_pit_lane(
    track_id:  str,
    layout_id: str,
    base_dir:  Optional[Path] = None,
) -> Optional[dict]:
    """Return the pit-lane mapping block for a layout, or None when absent.

    Group 55 — backward-compatible. Resolution order (first hit wins):
      1. layouts/<id>/pit_lane.json   (a dedicated file, if present)
      2. manifest.json ``pit_lane``   (inline block)
    A track with no pit-lane metadata is valid: returns None (never raises). The
    returned dict is the raw mapping block ({"available", "source", "segments"}).
    """
    try:
        ldir = _layout_dir(track_id, layout_id, base_dir)
        raw = _load_json(ldir / "pit_lane.json")
        if isinstance(raw, dict) and raw.get("segments"):
            block = dict(raw)
            block.setdefault("track_id", track_id)
            block.setdefault("layout_id", layout_id)
            return block
        manifest = resolve_track_layout_manifest(track_id, layout_id, base_dir)
        if manifest is not None and manifest.pit_lane:
            block = dict(manifest.pit_lane)
            block.setdefault("track_id", track_id)
            block.setdefault("layout_id", layout_id)
            return block
        return None
    except Exception:
        return None


def load_seed_coordinate_map_from_library(
    track_id:  str,
    layout_id: str,
    base_dir:  Optional[Path] = None,
) -> Optional[object]:
    """Load geometry.seed_map.json from the track library; return None if absent.

    Returns a SeedCoordinateMap (imported from track_seed_coordinate_map) or None.
    Never raises.
    """
    ldir = _layout_dir(track_id, layout_id, base_dir)
    geo_path = ldir / "geometry.seed_map.json"
    if not geo_path.exists():
        return None
    try:
        from data.track_seed_coordinate_map import import_seed_coordinate_map_json
        return import_seed_coordinate_map_json(geo_path)
    except Exception:
        return None


def resolve_seed_coordinate_map(
    track_id:  str,
    layout_id: str,
    base_dir:  Optional[Path] = None,
) -> Tuple[Optional[object], str]:
    """Return (SeedCoordinateMap_or_None, source_label).

    source_label is one of:
      "track_library"   — loaded from data/track_library/...
      "legacy_fallback" — loaded from data/track_seed_maps/...
      "none"            — not found anywhere
    """
    # 1. Prefer track library
    lib_map = load_seed_coordinate_map_from_library(track_id, layout_id, base_dir)
    if lib_map is not None:
        return lib_map, "track_library"

    # 2. Legacy fallback
    try:
        from data.track_seed_coordinate_map import load_seed_coordinate_map as _legacy
        legacy_map = _legacy(track_id, layout_id)
        if legacy_map is not None:
            return legacy_map, "legacy_fallback"
    except Exception:
        pass

    return None, "none"


def update_manifest_availability(
    track_id: str,
    layout_id: str,
    base_dir: Optional[Path] = None,
    **fields: bool,
) -> bool:
    """Read manifest.json, patch availability keys, write atomically.

    Returns True on success, False on any failure (never raises).
    """
    try:
        ldir = _layout_dir(track_id, layout_id, base_dir)
        manifest_path = ldir / "manifest.json"
        raw = _load_json(manifest_path)
        if raw is None:
            return False
        raw.setdefault("availability", {})
        raw["availability"].update(fields)
        tmp = manifest_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        tmp.replace(manifest_path)
        return True
    except Exception:
        return False


def audit_track_library_layout(
    track_id:  str,
    layout_id: str,
    base_dir:  Optional[Path] = None,
) -> TrackLibraryAuditResult:
    """Return a complete audit of what the track library has for this layout.

    Never raises — all failures produce warnings in the result.
    """
    result = TrackLibraryAuditResult()

    # Index check
    index = load_track_library_index(base_dir)
    if index is not None:
        result.library_available = True
        if track_id not in index.tracks:
            result.warnings.append(f"Track '{track_id}' not listed in library index")

    # Manifest
    manifest = resolve_track_layout_manifest(track_id, layout_id, base_dir)
    if manifest is not None:
        result.manifest_loaded       = True
        result.availability          = manifest.availability
        result.manifest_display_name = manifest.display_name
        result.manifest_lap_length_m = manifest.lap_length_m
    else:
        result.warnings.append(f"Manifest not found for {track_id}/{layout_id}")

    # Semantic model
    sem = load_track_semantic_model(track_id, layout_id, base_dir)
    result.semantic_model_loaded = sem is not None

    # Validation rules
    rules = load_validation_rules(track_id, layout_id, base_dir)
    result.validation_rules_loaded = rules is not None

    # Seed geometry — library first, then legacy
    ldir = _layout_dir(track_id, layout_id, base_dir)
    geo_in_library = (ldir / "geometry.seed_map.json").exists()
    result.seed_geometry_in_library = geo_in_library

    if not geo_in_library:
        # Check legacy path
        try:
            from data.track_seed_coordinate_map import find_seed_coordinate_map_path
            legacy_path = find_seed_coordinate_map_path(track_id, layout_id)
            result.seed_geometry_legacy = (legacy_path is not None and legacy_path.exists())
        except Exception:
            result.seed_geometry_legacy = False

    if geo_in_library:
        result.seed_coordinate_source = "track_library"
    elif result.seed_geometry_legacy:
        result.seed_coordinate_source = "legacy_fallback"
    else:
        result.seed_coordinate_source = "none"

    return result
