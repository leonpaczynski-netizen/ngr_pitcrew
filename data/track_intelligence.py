"""Track Intelligence — seed loader and track modelling foundation for NGR Pit Crew."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import yaml

SEED_YAML_PATH = (
    Path(__file__).parent.parent
    / "docs"
    / "track_modelling_seed"
    / "track_modelling_seed.yaml"
)

_MATURITY_ORDER = [
    "not_modelled",
    "seed_only",
    "telemetry_sampled",
    "reference_path_built",
    "segment_detected",
    "user_reviewed",
    "practice_refined",
    "race_validated",
    "engineer_grade",
]


class TrackModellingStatus(str, Enum):
    NOT_MODELLED = "not_modelled"
    SEED_ONLY = "seed_only"
    TELEMETRY_SAMPLED = "telemetry_sampled"
    REFERENCE_PATH_BUILT = "reference_path_built"
    SEGMENT_DETECTED = "segment_detected"
    USER_REVIEWED = "user_reviewed"
    PRACTICE_REFINED = "practice_refined"
    RACE_VALIDATED = "race_validated"
    ENGINEER_GRADE = "engineer_grade"

    def _maturity(self) -> int:
        try:
            return _MATURITY_ORDER.index(self.value)
        except ValueError:
            return -1

    def is_ready_for_calibration(self) -> bool:
        """True once at least one telemetry lap has been captured."""
        return self._maturity() >= _MATURITY_ORDER.index("telemetry_sampled")

    def is_ready_for_ai(self) -> bool:
        """True once segments are detected and the AI can reference corner phases."""
        return self._maturity() >= _MATURITY_ORDER.index("segment_detected")

    def missing_calibration_requirements(self) -> list[str]:
        """Human-readable list of steps still needed to reach engineer_grade."""
        maturity = self._maturity()
        steps = []
        if maturity < _MATURITY_ORDER.index("telemetry_sampled"):
            steps.append("Record calibration laps (Porsche 911 RSR)")
        if maturity < _MATURITY_ORDER.index("reference_path_built"):
            steps.append("Build reference path from telemetry")
        if maturity < _MATURITY_ORDER.index("segment_detected"):
            steps.append("Auto-detect corner/braking/straight segments")
        if maturity < _MATURITY_ORDER.index("user_reviewed"):
            steps.append("User review of segment boundaries")
        if maturity < _MATURITY_ORDER.index("practice_refined"):
            steps.append("Refine model from practice laps")
        if maturity < _MATURITY_ORDER.index("race_validated"):
            steps.append("Validate model against race data")
        if maturity < _MATURITY_ORDER.index("engineer_grade"):
            steps.append("Engineer sign-off")
        return steps


@dataclass
class TrackSeedMetadata:
    schema_name: str
    schema_version: str
    generated_utc: str
    purpose: str
    track_count: int
    layout_count_in_seed: int


@dataclass
class CalibrationCarProfile:
    profile_id: str
    display_name: str
    manufacturer: str
    year: int
    car_class: str
    drivetrain: str
    stock_power_bhp: int
    stock_weight_kg: int
    stock_tyres: str
    purpose: str
    country: Optional[str] = None
    engine_type: Optional[str] = None
    aspiration: Optional[str] = None
    stock_power_rpm: Optional[int] = None
    stock_torque_kgfm: Optional[float] = None
    stock_torque_rpm: Optional[int] = None
    stock_pp: Optional[float] = None
    data_rule: Optional[str] = None
    source: Optional[str] = None


@dataclass
class SeedCornerDefinition:
    """Per-corner progress window from seed data (Group 17Q extension).

    When present in TrackLayoutSeed.corner_definitions the alignment engine can
    verify each telemetry-detected corner lands inside its expected progress
    range, not merely that the total count matches.  All progress values are
    0–100 (percent of lap).  Existing seeds without this data still load fine.
    """
    corner_id:          str
    display_name:       str   = ""
    apex_progress_pct:  float = 0.0   # expected apex centre (0–100)
    start_progress_pct: float = 0.0   # window entry (0–100)
    end_progress_pct:   float = 0.0   # window exit (0–100)
    direction:          Optional[str] = None   # "left" / "right"
    sector_id:          Optional[int] = None
    source:             str   = "seed"
    confidence:         str   = "medium"


@dataclass
class SeedSectorDefinition:
    """Named sector with progress range for a layout (Group 17S)."""
    sector_id:          str
    display_name:       str   = ""
    start_progress_pct: float = 0.0
    end_progress_pct:   float = 100.0
    source:             str   = "estimated"
    confidence:         str   = "low"


@dataclass
class CornerComplexDefinition:
    """Named driving complex grouping multiple official corners (Group 17S)."""
    complex_id:         str
    display_name:       str
    member_corner_ids:  list = field(default_factory=list)
    start_progress_pct: float = 0.0
    end_progress_pct:   float = 0.0
    sector_id:          Optional[str] = None
    coaching_name:      str   = ""
    notes:              str   = ""
    source:             str   = "estimated"
    confidence:         str   = "low"


@dataclass
class SeedAuditResult:
    """Summary of what seed data is available for a layout (Group 17S/17U)."""
    has_metadata:            bool = True
    has_lap_length:          bool = False
    has_sector_definitions:  bool = False
    has_corner_windows:      bool = False
    has_corner_complexes:    bool = False
    has_seed_centreline:     bool = False
    corner_count:            int  = 0
    sector_count:            int  = 0
    complex_count:           int  = 0
    centreline_point_count:  int  = 0
    max_match_status:        str  = "GOOD_MATCH"
    missing_for_full_accept: list = field(default_factory=list)
    # Group 17U — track library integration
    seed_source:             str  = "none"   # "track_library" / "legacy_fallback" / "none"
    library_manifest_loaded: bool = False
    validation_rules_loaded: bool = False


@dataclass
class TrackLayoutSeed:
    layout_id: str
    display_name: str
    track_location_id: str
    direction: Optional[str] = None
    length_m: Optional[float] = None
    longest_straight_m: Optional[float] = None
    elevation_change_m: Optional[float] = None
    average_gradient_percent: Optional[float] = None
    pit_delta_seconds: Optional[int] = None
    corners_expected: Optional[int] = None
    sectors: Optional[int] = None
    bop_applied: Optional[str] = None
    oval: Optional[bool] = None
    reversible: Optional[bool] = None
    rain_supported: Optional[bool] = None
    night_supported: Optional[bool] = None
    full_24h_supported: Optional[bool] = None
    update_version: Optional[str] = None
    source_url: Optional[str] = None
    source_confidence: Optional[str] = None
    validation_status: Optional[str] = None
    modelling_status: TrackModellingStatus = TrackModellingStatus.NOT_MODELLED
    needs_telemetry_reference_path: bool = True
    needs_segment_detection: bool = True
    notes: Optional[str] = None
    corner_definitions: list[SeedCornerDefinition] = field(default_factory=list)
    sector_definitions: list[SeedSectorDefinition] = field(default_factory=list)
    corner_complexes: list[CornerComplexDefinition] = field(default_factory=list)


@dataclass
class TrackLocationSeed:
    track_location_id: str
    display_name: str
    aliases: list[str] = field(default_factory=list)
    region: Optional[str] = None
    country: Optional[str] = None
    real_or_fictional: Optional[str] = None
    surface: Optional[str] = None
    track_type: Optional[str] = None
    opened_year: Optional[int] = None
    altitude_m: Optional[float] = None
    gtplus_layout_count: Optional[int] = None
    dg_edge_variant_count: Optional[int] = None
    gt_engine_layout_count_in_seed: Optional[int] = None
    source_count_conflict: bool = False
    rain_supported_track_level: Optional[bool] = None
    night_supported_track_level: Optional[bool] = None
    full_24h_supported_track_level: Optional[bool] = None
    reversible_supported_track_level: Optional[bool] = None
    update_version: Optional[str] = None
    official_url: Optional[str] = None
    source_confidence: Optional[str] = None
    validation_status: Optional[str] = None
    layouts: list[TrackLayoutSeed] = field(default_factory=list)


@dataclass
class TrackSeedLoadResult:
    success: bool
    metadata: Optional[TrackSeedMetadata] = None
    calibration_cars: list[CalibrationCarProfile] = field(default_factory=list)
    track_locations: list[TrackLocationSeed] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    duplicate_layout_ids: list[str] = field(default_factory=list)
    unknown_modelling_statuses: list[str] = field(default_factory=list)


_CACHE: Optional[TrackSeedLoadResult] = None


def _parse_modelling_status(raw: object) -> tuple[TrackModellingStatus, Optional[str]]:
    """Return (status, unknown_value_or_None). Preserves unknown values."""
    val = str(raw) if raw is not None else "not_modelled"
    try:
        return TrackModellingStatus(val), None
    except ValueError:
        return TrackModellingStatus.NOT_MODELLED, val


def _parse_calibration_car(raw: dict) -> CalibrationCarProfile:
    return CalibrationCarProfile(
        profile_id=raw.get("profile_id", ""),
        display_name=raw.get("display_name", ""),
        manufacturer=raw.get("manufacturer", ""),
        year=int(raw.get("year", 0)),
        car_class=raw.get("class", ""),
        drivetrain=raw.get("drivetrain", ""),
        stock_power_bhp=int(raw.get("stock_power_bhp", 0)),
        stock_weight_kg=int(raw.get("stock_weight_kg", 0)),
        stock_tyres=raw.get("stock_tyres", ""),
        purpose=raw.get("purpose", ""),
        country=raw.get("country"),
        engine_type=raw.get("engine_type"),
        aspiration=raw.get("aspiration"),
        stock_power_rpm=raw.get("stock_power_rpm"),
        stock_torque_kgfm=raw.get("stock_torque_kgfm"),
        stock_torque_rpm=raw.get("stock_torque_rpm"),
        stock_pp=raw.get("stock_pp"),
        data_rule=raw.get("data_rule"),
        source=raw.get("source"),
    )


def _parse_corner_def(raw: dict) -> SeedCornerDefinition:
    return SeedCornerDefinition(
        corner_id          = str(raw.get("corner_id", "")),
        display_name       = str(raw.get("display_name", raw.get("corner_id", ""))),
        apex_progress_pct  = float(raw.get("apex_progress_pct", 0.0)),
        start_progress_pct = float(raw.get("start_progress_pct", 0.0)),
        end_progress_pct   = float(raw.get("end_progress_pct", 0.0)),
        direction          = raw.get("direction"),
        sector_id          = raw.get("sector_id"),
        source             = str(raw.get("source", "seed")),
        confidence         = str(raw.get("confidence", "medium")),
    )


def _parse_sector_def(raw: dict) -> SeedSectorDefinition:
    return SeedSectorDefinition(
        sector_id          = str(raw.get("sector_id", "")),
        display_name       = str(raw.get("display_name", raw.get("sector_id", ""))),
        start_progress_pct = float(raw.get("start_progress_pct", 0.0)),
        end_progress_pct   = float(raw.get("end_progress_pct", 100.0)),
        source             = str(raw.get("source", "estimated")),
        confidence         = str(raw.get("confidence", "low")),
    )


def _parse_complex_def(raw: dict) -> CornerComplexDefinition:
    return CornerComplexDefinition(
        complex_id         = str(raw.get("complex_id", "")),
        display_name       = str(raw.get("display_name", "")),
        member_corner_ids  = list(raw.get("member_corner_ids", [])),
        start_progress_pct = float(raw.get("start_progress_pct", 0.0)),
        end_progress_pct   = float(raw.get("end_progress_pct", 0.0)),
        sector_id          = raw.get("sector_id"),
        coaching_name      = str(raw.get("coaching_name", "")),
        notes              = str(raw.get("notes", "")),
        source             = str(raw.get("source", "estimated")),
        confidence         = str(raw.get("confidence", "low")),
    )


def _parse_layout(raw: dict, track_location_id: str) -> tuple[TrackLayoutSeed, Optional[str]]:
    status, unknown = _parse_modelling_status(raw.get("modelling_status"))
    corner_definitions = [_parse_corner_def(c) for c in raw.get("corners", [])]
    sector_definitions = [_parse_sector_def(s) for s in raw.get("sector_definitions", [])]
    corner_complexes   = [_parse_complex_def(c) for c in raw.get("corner_complexes", [])]
    return TrackLayoutSeed(
        layout_id=raw.get("layout_id", ""),
        display_name=raw.get("display_name", ""),
        track_location_id=track_location_id,
        direction=raw.get("direction"),
        length_m=raw.get("length_m"),
        longest_straight_m=raw.get("longest_straight_m"),
        elevation_change_m=raw.get("elevation_change_m"),
        average_gradient_percent=raw.get("average_gradient_percent"),
        pit_delta_seconds=raw.get("pit_delta_seconds"),
        corners_expected=raw.get("corners_expected"),
        sectors=raw.get("sectors"),
        bop_applied=raw.get("bop_applied"),
        oval=raw.get("oval"),
        reversible=raw.get("reversible"),
        rain_supported=raw.get("rain_supported"),
        night_supported=raw.get("night_supported"),
        full_24h_supported=raw.get("full_24h_supported"),
        update_version=str(raw["update_version"]) if raw.get("update_version") is not None else None,
        source_url=raw.get("source_url"),
        source_confidence=raw.get("source_confidence"),
        validation_status=raw.get("validation_status"),
        modelling_status=status,
        needs_telemetry_reference_path=bool(raw.get("needs_telemetry_reference_path", True)),
        needs_segment_detection=bool(raw.get("needs_segment_detection", True)),
        notes=raw.get("notes"),
        corner_definitions=corner_definitions,
        sector_definitions=sector_definitions,
        corner_complexes=corner_complexes,
    ), unknown


def _parse_track_location(
    raw: dict,
    seen_layout_ids: set[str],
    duplicate_layout_ids: list[str],
    all_location_ids: set[str],
) -> tuple[TrackLocationSeed, list[str], list[str]]:
    loc_id = raw.get("track_location_id", "")
    warnings: list[str] = []
    unknown_statuses: list[str] = []

    layouts: list[TrackLayoutSeed] = []
    for raw_layout in raw.get("layouts", []):
        layout, unknown = _parse_layout(raw_layout, loc_id)

        if unknown is not None:
            unknown_statuses.append(unknown)

        lid = layout.layout_id
        if lid in seen_layout_ids:
            duplicate_layout_ids.append(lid)
        else:
            seen_layout_ids.add(lid)

        # Warn if layout_id doesn't start with location_id
        if lid and not lid.startswith(loc_id):
            warnings.append(f"Layout ID '{lid}' does not start with location ID '{loc_id}'")

        layouts.append(layout)

    # Alias safety: aliases must not clash with other location IDs
    aliases = raw.get("aliases") or []
    for alias in aliases:
        alias_lower = alias.lower()
        for other_id in all_location_ids:
            if other_id != loc_id and alias_lower == other_id.lower():
                warnings.append(
                    f"Alias '{alias}' on '{loc_id}' clashes with location ID '{other_id}'"
                )

    loc = TrackLocationSeed(
        track_location_id=loc_id,
        display_name=raw.get("display_name", ""),
        aliases=aliases if isinstance(aliases, list) else [],
        region=raw.get("region"),
        country=raw.get("country"),
        real_or_fictional=raw.get("real_or_fictional"),
        surface=raw.get("surface"),
        track_type=raw.get("track_type"),
        opened_year=raw.get("opened_year"),
        altitude_m=raw.get("altitude_m"),
        gtplus_layout_count=raw.get("gtplus_layout_count"),
        dg_edge_variant_count=raw.get("dg_edge_variant_count"),
        gt_engine_layout_count_in_seed=raw.get("gt_engine_layout_count_in_seed"),
        source_count_conflict=bool(raw.get("source_count_conflict", False)),
        rain_supported_track_level=raw.get("rain_supported_track_level"),
        night_supported_track_level=raw.get("night_supported_track_level"),
        full_24h_supported_track_level=raw.get("full_24h_supported_track_level"),
        reversible_supported_track_level=raw.get("reversible_supported_track_level"),
        update_version=str(raw["update_version"]) if raw.get("update_version") is not None else None,
        official_url=raw.get("official_url"),
        source_confidence=raw.get("source_confidence"),
        validation_status=raw.get("validation_status"),
        layouts=layouts,
    )
    return loc, warnings, unknown_statuses


def load_track_seed(
    yaml_path: Optional[Path] = None,
    force_reload: bool = False,
) -> TrackSeedLoadResult:
    """Load and validate the track modelling seed YAML. Results are cached after first load."""
    global _CACHE
    if _CACHE is not None and not force_reload and yaml_path is None:
        return _CACHE

    path = yaml_path or SEED_YAML_PATH
    errors: list[str] = []
    warnings: list[str] = []

    if not Path(path).exists():
        return TrackSeedLoadResult(success=False, errors=[f"Seed file not found: {path}"])

    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as exc:
        return TrackSeedLoadResult(success=False, errors=[f"YAML parse error: {exc}"])

    if not isinstance(data, dict):
        return TrackSeedLoadResult(success=False, errors=["Seed YAML root is not a mapping"])

    # Metadata validation
    required_meta = ["schema_name", "schema_version", "generated_utc"]
    missing_meta = [k for k in required_meta if k not in data]
    metadata: Optional[TrackSeedMetadata] = None
    if missing_meta:
        errors.append(f"Missing metadata fields: {missing_meta}")
    else:
        metadata = TrackSeedMetadata(
            schema_name=data["schema_name"],
            schema_version=data["schema_version"],
            generated_utc=data["generated_utc"],
            purpose=data.get("purpose", ""),
            track_count=int(data.get("track_count", 0)),
            layout_count_in_seed=int(data.get("layout_count_in_seed", 0)),
        )

    # Calibration car validation
    raw_cars = data.get("calibration_car_profiles", []) or []
    calibration_cars: list[CalibrationCarProfile] = []
    if not raw_cars:
        errors.append("No calibration_car_profiles found in seed")
    else:
        for raw_car in raw_cars:
            calibration_cars.append(_parse_calibration_car(raw_car))

    # Track locations
    raw_tracks = data.get("tracks", []) or []
    if not raw_tracks:
        errors.append("No tracks found in seed")

    track_locations: list[TrackLocationSeed] = []
    duplicate_layout_ids: list[str] = []
    unknown_statuses: list[str] = []
    seen_layout_ids: set[str] = set()
    all_location_ids = {
        t.get("track_location_id", "") for t in raw_tracks if isinstance(t, dict)
    }

    for raw_track in raw_tracks:
        if not isinstance(raw_track, dict):
            warnings.append(f"Non-dict track entry skipped: {raw_track!r}")
            continue
        loc, loc_warnings, loc_unknown = _parse_track_location(
            raw_track, seen_layout_ids, duplicate_layout_ids, all_location_ids
        )
        track_locations.append(loc)
        warnings.extend(loc_warnings)
        unknown_statuses.extend(loc_unknown)

    if duplicate_layout_ids:
        warnings.append(f"Duplicate layout IDs detected: {duplicate_layout_ids}")

    success = len(errors) == 0
    result = TrackSeedLoadResult(
        success=success,
        metadata=metadata,
        calibration_cars=calibration_cars,
        track_locations=track_locations,
        errors=errors,
        warnings=warnings,
        duplicate_layout_ids=duplicate_layout_ids,
        unknown_modelling_statuses=list(dict.fromkeys(unknown_statuses)),
    )

    if success and yaml_path is None:
        _CACHE = result
    return result


def get_track_locations(yaml_path: Optional[Path] = None) -> list[TrackLocationSeed]:
    """Return all track locations from the seed."""
    return load_track_seed(yaml_path).track_locations


def get_track_layouts(yaml_path: Optional[Path] = None) -> list[TrackLayoutSeed]:
    """Return a flat list of all layouts from all locations."""
    return [
        layout
        for loc in load_track_seed(yaml_path).track_locations
        for layout in loc.layouts
    ]


def resolve_track_layout(
    track_location_id: str,
    layout_id: str,
    yaml_path: Optional[Path] = None,
) -> Optional[TrackLayoutSeed]:
    """Return a specific layout by location + layout ID, or None if not found."""
    for loc in load_track_seed(yaml_path).track_locations:
        if loc.track_location_id == track_location_id:
            for layout in loc.layouts:
                if layout.layout_id == layout_id:
                    return layout
    return None


def search_track_layouts(
    query: str,
    yaml_path: Optional[Path] = None,
) -> list[TrackLayoutSeed]:
    """
    Search layouts by display name, location ID, alias, or layout ID.
    Case-insensitive substring match. Returns matching layouts.
    """
    q = query.lower().strip()
    if not q:
        return []
    results: list[TrackLayoutSeed] = []
    for loc in load_track_seed(yaml_path).track_locations:
        loc_match = (
            q in loc.display_name.lower()
            or q in loc.track_location_id.lower()
            or any(q in alias.lower() for alias in loc.aliases)
        )
        for layout in loc.layouts:
            if loc_match or q in layout.display_name.lower() or q in layout.layout_id.lower():
                results.append(layout)
    return results


def audit_layout_seed(
    layout_seed,
    track_location_id: Optional[str] = None,
    layout_id_str: Optional[str] = None,
) -> SeedAuditResult:
    """Return a SeedAuditResult describing what seed data is available.

    Accepts a TrackLayoutSeed (duck-typed) or None.  Always backward-compatible
    — seeds without sector_definitions or corner_complexes return empty lists.

    When track_location_id and layout_id_str are provided, also checks whether a
    seed coordinate map file exists at data/track_seed_maps/<id>__<id>.seed_map.json
    and reports has_seed_centreline accordingly.
    """
    if layout_seed is None:
        return SeedAuditResult(
            has_metadata=False,
            missing_for_full_accept=["No seed data found for this layout"],
        )

    has_length    = bool(getattr(layout_seed, "length_m", None))
    corner_defs   = getattr(layout_seed, "corner_definitions", []) or []
    sector_defs   = getattr(layout_seed, "sector_definitions", []) or []
    complexes     = getattr(layout_seed, "corner_complexes", []) or []
    has_corners   = len(corner_defs) > 0
    has_sectors   = len(sector_defs) > 0
    has_complexes = len(complexes) > 0

    # Check for seed coordinate map — track library first, legacy fallback (Group 17T/17U)
    has_centreline      = False
    centreline_pts      = 0
    _seed_source        = "none"
    _lib_manifest_ok    = False
    _lib_rules_ok       = False
    if track_location_id and layout_id_str:
        try:
            from data.track_library import (
                audit_track_library_layout as _lib_audit,
                resolve_seed_coordinate_map as _resolve_map,
                load_validation_rules as _load_vr,
            )
            _lib_audit_result = _lib_audit(track_location_id, layout_id_str)
            _lib_manifest_ok  = _lib_audit_result.manifest_loaded
            _lib_rules_ok     = _lib_audit_result.validation_rules_loaded
            _smap, _seed_source = _resolve_map(track_location_id, layout_id_str)
            if _smap is not None:
                has_centreline = True
                centreline_pts = _smap.station_count()
        except Exception:
            # Fallback: legacy path only (Group 17T behaviour)
            try:
                from data.track_seed_coordinate_map import (
                    load_seed_coordinate_map as _load_legacy,
                )
                _smap = _load_legacy(track_location_id, layout_id_str)
                if _smap is not None:
                    has_centreline = True
                    centreline_pts = _smap.station_count()
                    _seed_source   = "legacy_fallback"
            except Exception:
                pass

    missing: list[str] = []
    if not has_length:
        missing.append("Seed lap length missing")
    if not has_corners:
        missing.append("Seed corner windows missing — add corners: to YAML")
    if not has_centreline:
        missing.append(
            "Seed coordinate map unavailable — add geometry.seed_map.json to the track library "
            f"(data/track_library/tracks/{track_location_id or '<track_id>'}/layouts/"
            f"{layout_id_str or '<layout_id>'}/geometry.seed_map.json) "
            "for full geometry overlay"
        )

    max_status = "ACCEPTABLE_MATCH" if has_corners else "GOOD_MATCH"

    return SeedAuditResult(
        has_metadata            = True,
        has_lap_length          = has_length,
        has_sector_definitions  = has_sectors,
        has_corner_windows      = has_corners,
        has_corner_complexes    = has_complexes,
        has_seed_centreline     = has_centreline,
        corner_count            = len(corner_defs),
        sector_count            = len(sector_defs),
        complex_count           = len(complexes),
        centreline_point_count  = centreline_pts,
        max_match_status        = max_status,
        missing_for_full_accept = missing,
        seed_source             = _seed_source,
        library_manifest_loaded = _lib_manifest_ok,
        validation_rules_loaded = _lib_rules_ok,
    )


def build_seed_track_context_for_prompt(
    track_location_id: str,
    layout_id: str,
    yaml_path: Optional[Path] = None,
) -> str:
    """
    Build an AI prompt context block for a specific track layout.
    Includes seed facts, modelling status, data confidence caveats,
    and calibration car boundary note.
    """
    result = load_track_seed(yaml_path)
    if not result.success:
        return f"[Track Intelligence] Seed load failed: {'; '.join(result.errors)}"

    loc = next(
        (l for l in result.track_locations if l.track_location_id == track_location_id),
        None,
    )
    if loc is None:
        return f"[Track Intelligence] Location '{track_location_id}' not found in seed."

    layout = next((l for l in loc.layouts if l.layout_id == layout_id), None)
    if layout is None:
        return f"[Track Intelligence] Layout '{layout_id}' not found for '{loc.display_name}'."

    lines: list[str] = [
        f"## Track Seed Context: {loc.display_name} — {layout.display_name}",
        f"Track: {loc.display_name} | Country: {loc.country} | Region: {loc.region}",
        f"Surface: {loc.surface or 'unknown'} | Type: {loc.track_type or 'unknown'} | "
        f"Classification: {loc.real_or_fictional or 'unknown'}",
    ]
    if loc.altitude_m is not None:
        lines.append(f"Altitude: {loc.altitude_m}m ASL")

    lines.append("")
    lines.append(f"Layout: {layout.display_name}")
    lines.append(f"Direction: {layout.direction or 'unknown'}")

    if layout.length_m is not None:
        lines.append(f"Length: {layout.length_m}m")
    if layout.longest_straight_m is not None:
        lines.append(f"Longest straight: {layout.longest_straight_m}m")
    if layout.corners_expected is not None:
        lines.append(f"Corners: {layout.corners_expected}")
    if layout.sectors is not None:
        lines.append(f"Sectors: {layout.sectors}")
    if layout.elevation_change_m is not None:
        lines.append(f"Elevation change: {layout.elevation_change_m}m")
    if layout.average_gradient_percent is not None:
        lines.append(f"Average gradient: {layout.average_gradient_percent}%")
    if layout.pit_delta_seconds is not None:
        lines.append(f"Pit delta: {layout.pit_delta_seconds}s")
    if layout.rain_supported is not None:
        lines.append(f"Rain: {'Yes' if layout.rain_supported else 'No'}")
    if layout.night_supported is not None:
        lines.append(f"Night: {'Yes' if layout.night_supported else 'No'}")
    if layout.full_24h_supported is not None:
        lines.append(f"24h: {'Yes' if layout.full_24h_supported else 'No'}")
    if layout.oval:
        lines.append("Oval: Yes")
    if layout.bop_applied:
        lines.append(f"BoP: {layout.bop_applied}")
    if layout.notes:
        lines.append(f"Notes: {layout.notes}")

    lines.append("")
    lines.append(f"Modelling status: {layout.modelling_status.value}")

    seed_only_states = {TrackModellingStatus.NOT_MODELLED, TrackModellingStatus.SEED_ONLY}
    if layout.modelling_status in seed_only_states:
        lines += [
            "DATA CAVEAT: Track geometry is public seed data only. Exact x/y/z coordinates,",
            "corner phases, braking zones and apex positions are NOT available.",
            "Do NOT state specific corner geometry as fact. Use hedged language such as",
            "'typically', 'based on seed data', or 'may vary in-game'.",
        ]
    elif not layout.modelling_status.is_ready_for_ai():
        lines.append(
            "DATA CAVEAT: Telemetry data is available but segment detection is not complete. "
            "Corner phase data may be incomplete."
        )

    if result.calibration_cars:
        car = result.calibration_cars[0]
        lines += [
            "",
            f"Calibration car: {car.display_name} "
            f"({car.car_class}, {car.drivetrain}, {car.stock_power_bhp}bhp, "
            f"{car.stock_weight_kg}kg, {car.stock_tyres} tyres)",
            "BOUNDARY: Braking points, gear usage, throttle behaviour, and tyre stress data",
            "from this car are Porsche RSR-specific. Do not present them as universal track truth.",
        ]

    return "\n".join(lines)
