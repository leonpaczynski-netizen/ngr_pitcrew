"""Lap Distance Mapper — Group 17L.

Converts GT7 road_distance (absolute track surface distance, resets per lap at
the start/finish line) to model distance_along_lap_m and lap_progress via a
configurable lap-start offset calibration.

GT7 road_distance field (telemetry/packet.py, offset 0xA0=160, type float):
  - Resets to ~0.0 when the car crosses the start/finish line each lap.
  - Increases monotonically along the track surface within each lap.
  - May differ from the reference path's distance_along_lap_m if the calibration
    lap started from a position other than the start/finish line (e.g. pit exit).
  - The lap-start offset bridges the two coordinate systems.

Architecture boundary:
  - Pure Python, no PyQt6.
  - May import: data.track_calibration (ReferencePath, TRACK_MODELS_DIR).
  - Does NOT write telemetry to DB.
  - Does NOT call AI functions.
  - Does NOT invent lap_progress when data is insufficient.
  - Does NOT treat seed-only data as trusted live coaching truth.
  - Does NOT build track auto-detection.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class LapDistanceMappingStatus(str, Enum):
    MAPPED            = "mapped"             # successful conversion, no wrap
    MAPPED_WITH_WRAP  = "mapped_with_wrap"   # successful but modulo wrap occurred
    NO_DISTANCE_DATA  = "no_distance_data"   # road_distance_m is None
    NO_TRACK_LENGTH   = "no_track_length"    # track_length_m is missing or below minimum
    INVALID_OFFSET    = "invalid_offset"     # offset_m is outside [0, track_length_m)
    ERROR             = "error"              # unexpected exception


class LapDistanceMappingConfidence(str, Enum):
    HIGH    = "high"    # engine-validated or ai_ready model + clean calibration lap
    MEDIUM  = "medium"  # reviewed model or reference path length only
    LOW     = "low"     # seed-only track length estimate
    UNKNOWN = "unknown" # no confidence evidence available


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class LapStartOffsetCalibration:
    """Relationship between GT7 road_distance and model distance_along_lap_m.

    Conversion formula:
        model_distance = normalise_distance(road_distance - offset_m, track_length_m)

    offset_m is precomputed as:
        normalise_distance(gt7_start_distance_m - model_start_distance_m, track_length_m)

    When calibration starts at the start/finish line and the reference path also
    starts at the start/finish, both gt7_start_distance_m and model_start_distance_m
    are 0.0, giving offset_m = 0.0 (no correction needed).
    """
    track_location_id: str
    layout_id: str
    calibration_source: str          # "reference_path" | "seed_length" | "manual" | "calibration_lap"
    track_length_m: float            # track circumference used for modulo wrap-around
    gt7_start_distance_m: float      # GT7 road_distance at the point where model_distance = 0
    model_start_distance_m: float    # distance_along_lap_m at the calibration start (usually 0.0)
    offset_m: float                  # precomputed: normalise(gt7_start - model_start, track_length)
    confidence: LapDistanceMappingConfidence
    sample_count: int = 0
    source_session_id: str = ""
    created_at: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class LapDistanceMappingResult:
    """Result of a road_distance → model distance conversion."""
    status: LapDistanceMappingStatus
    distance_along_lap_m: Optional[float]  # converted lap-relative distance (metres)
    lap_progress: Optional[float]          # 0.0–1.0 (distance / track_length)
    wrapped: bool = False                  # True if modulo wrap-around occurred
    confidence: LapDistanceMappingConfidence = LapDistanceMappingConfidence.UNKNOWN
    warnings: list[str] = field(default_factory=list)
    offset_m: float = 0.0
    track_length_m: float = 0.0


@dataclass
class LapDistanceMapperConfig:
    """Tuneable parameters for the lap distance mapper."""
    min_track_length_m: float = 100.0   # below this track_length_m is rejected
    clamp_progress: bool = True          # clamp lap_progress to [0.0, 1.0]


# ---------------------------------------------------------------------------
# Core calculation functions
# ---------------------------------------------------------------------------

def normalise_distance(distance_m: float, track_length_m: float) -> float:
    """Wrap distance_m to [0, track_length_m) using modulo arithmetic.

    Python's modulo always returns non-negative when the divisor is positive,
    so negative distances are handled correctly:
        normalise_distance(-100, 5800) → 5700.0

    Raises ValueError if track_length_m <= 0.
    """
    if track_length_m <= 0.0:
        raise ValueError(f"track_length_m must be > 0, got {track_length_m}")
    return distance_m % track_length_m


def calculate_lap_start_offset(
    gt7_start_distance_m: float,
    model_start_distance_m: float,
    track_length_m: float,
) -> float:
    """Compute the normalised lap-start offset used to convert GT7 road_distance.

    offset_m = normalise_distance(gt7_start_distance_m - model_start_distance_m,
                                  track_length_m)

    The offset represents the GT7 road_distance value at the point where the
    reference path's distance_along_lap_m equals model_start_distance_m (usually 0.0).

    Raises ValueError if track_length_m <= 0.
    """
    if track_length_m <= 0.0:
        raise ValueError(f"track_length_m must be > 0, got {track_length_m}")
    return normalise_distance(gt7_start_distance_m - model_start_distance_m, track_length_m)


def map_road_distance_to_lap_distance(
    road_distance_m: Optional[float],
    offset_m: float,
    track_length_m: float,
    config: Optional[LapDistanceMapperConfig] = None,
) -> LapDistanceMappingResult:
    """Convert GT7 road_distance to model distance_along_lap_m.

    Formula: model_distance = normalise_distance(road_distance - offset_m, track_length_m)

    Returns:
      MAPPED              — success, no wrap-around
      MAPPED_WITH_WRAP    — success, but modulo wrap-around occurred
      NO_DISTANCE_DATA    — road_distance_m is None
      NO_TRACK_LENGTH     — track_length_m <= 0 or below min_track_length_m
      INVALID_OFFSET      — offset_m not in [0, track_length_m)
      ERROR               — unexpected exception

    Note: lap_progress is NOT set in the returned result; call
    map_road_distance_to_lap_progress() for a result that includes lap_progress.
    """
    if config is None:
        config = LapDistanceMapperConfig()

    if road_distance_m is None:
        return LapDistanceMappingResult(
            status=LapDistanceMappingStatus.NO_DISTANCE_DATA,
            distance_along_lap_m=None,
            lap_progress=None,
            offset_m=offset_m,
            track_length_m=track_length_m,
        )

    if track_length_m <= 0.0 or track_length_m < config.min_track_length_m:
        return LapDistanceMappingResult(
            status=LapDistanceMappingStatus.NO_TRACK_LENGTH,
            distance_along_lap_m=None,
            lap_progress=None,
            offset_m=offset_m,
            track_length_m=track_length_m,
        )

    if offset_m < 0.0 or offset_m >= track_length_m:
        return LapDistanceMappingResult(
            status=LapDistanceMappingStatus.INVALID_OFFSET,
            distance_along_lap_m=None,
            lap_progress=None,
            offset_m=offset_m,
            track_length_m=track_length_m,
            warnings=[
                f"offset_m {offset_m:.2f} is outside [0, {track_length_m:.2f}) — "
                "use calculate_lap_start_offset() to produce a normalised offset."
            ],
        )

    try:
        raw = road_distance_m - offset_m
        wrapped = (raw < 0.0) or (raw >= track_length_m)
        lap_distance = normalise_distance(raw, track_length_m)

        result_warnings: list[str] = []
        if wrapped:
            result_warnings.append(
                f"Modulo wrap-around: road_distance {road_distance_m:.1f} m − "
                f"offset {offset_m:.1f} m = {raw:.1f} m; "
                f"mapped to {lap_distance:.1f} m on {track_length_m:.1f} m track."
            )

        status = (
            LapDistanceMappingStatus.MAPPED_WITH_WRAP
            if wrapped
            else LapDistanceMappingStatus.MAPPED
        )

        return LapDistanceMappingResult(
            status=status,
            distance_along_lap_m=lap_distance,
            lap_progress=None,
            wrapped=wrapped,
            warnings=result_warnings,
            offset_m=offset_m,
            track_length_m=track_length_m,
        )
    except Exception as exc:  # pragma: no cover
        return LapDistanceMappingResult(
            status=LapDistanceMappingStatus.ERROR,
            distance_along_lap_m=None,
            lap_progress=None,
            warnings=[f"Unexpected error mapping road distance: {exc}"],
            offset_m=offset_m,
            track_length_m=track_length_m,
        )


def map_road_distance_to_lap_progress(
    road_distance_m: Optional[float],
    offset_m: float,
    track_length_m: float,
    config: Optional[LapDistanceMapperConfig] = None,
) -> LapDistanceMappingResult:
    """Convert GT7 road_distance to lap_progress (0.0–1.0).

    Calls map_road_distance_to_lap_distance() then divides by track_length_m.
    lap_progress is clamped to [0.0, 1.0] when config.clamp_progress is True.

    Returns the same failure statuses as map_road_distance_to_lap_distance().
    """
    if config is None:
        config = LapDistanceMapperConfig()

    result = map_road_distance_to_lap_distance(
        road_distance_m, offset_m, track_length_m, config
    )

    if result.status not in (
        LapDistanceMappingStatus.MAPPED,
        LapDistanceMappingStatus.MAPPED_WITH_WRAP,
    ):
        return result

    lap_progress = result.distance_along_lap_m / track_length_m
    if config.clamp_progress:
        lap_progress = max(0.0, min(1.0, lap_progress))

    return LapDistanceMappingResult(
        status=result.status,
        distance_along_lap_m=result.distance_along_lap_m,
        lap_progress=lap_progress,
        wrapped=result.wrapped,
        confidence=result.confidence,
        warnings=result.warnings,
        offset_m=offset_m,
        track_length_m=track_length_m,
    )


# ---------------------------------------------------------------------------
# Calibration creation helpers
# ---------------------------------------------------------------------------

def create_offset_zero(
    track_location_id: str,
    layout_id: str,
    track_length_m: float,
    confidence: LapDistanceMappingConfidence = LapDistanceMappingConfidence.LOW,
    source: str = "zero_offset",
) -> LapStartOffsetCalibration:
    """Create a zero-offset calibration (road_distance aligns with model distance).

    Use when calibration started at the start/finish line, or when no offset
    information is available and zero is the safest default.
    Raises ValueError if track_length_m is not a positive finite number.
    """
    if not track_length_m or track_length_m <= 0:
        raise ValueError(
            f"track_length_m must be positive, got {track_length_m!r}"
        )
    return LapStartOffsetCalibration(
        track_location_id=track_location_id,
        layout_id=layout_id,
        calibration_source=source,
        track_length_m=track_length_m,
        gt7_start_distance_m=0.0,
        model_start_distance_m=0.0,
        offset_m=0.0,
        confidence=confidence,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def create_offset_from_reference_path(
    ref_path,
    gt7_start_distance_m: float = 0.0,
    model_start_distance_m: float = 0.0,
    confidence: LapDistanceMappingConfidence = LapDistanceMappingConfidence.MEDIUM,
    source: str = "reference_path",
    source_session_id: str = "",
) -> Optional[LapStartOffsetCalibration]:
    """Build a LapStartOffsetCalibration from a ReferencePath object.

    track_length_m is inferred from the last point's distance_along_lap_m.
    Returns None if the reference path is None, empty, or has zero length.

    gt7_start_distance_m: GT7 road_distance at the start of the reference path.
      Defaults to 0.0 (assumes calibration started at the start/finish line).
    model_start_distance_m: the reference path's distance_along_lap_m at its
      first sample.  Defaults to 0.0 (the usual case).
    """
    try:
        if ref_path is None or not ref_path.points:
            return None
        track_length_m = ref_path.points[-1].distance_along_lap_m
        if track_length_m <= 0.0:
            return None
        offset_m = calculate_lap_start_offset(
            gt7_start_distance_m, model_start_distance_m, track_length_m
        )
        cal_warnings: list[str] = []
        if gt7_start_distance_m != 0.0:
            cal_warnings.append(
                f"Non-zero gt7_start_distance_m ({gt7_start_distance_m:.1f} m) used — "
                "offset may be imprecise if the road_distance start was estimated."
            )
        return LapStartOffsetCalibration(
            track_location_id=ref_path.track_location_id,
            layout_id=ref_path.layout_id,
            calibration_source=source,
            track_length_m=track_length_m,
            gt7_start_distance_m=gt7_start_distance_m,
            model_start_distance_m=model_start_distance_m,
            offset_m=offset_m,
            confidence=confidence,
            source_session_id=source_session_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            warnings=cal_warnings,
        )
    except Exception:
        return None


# ---------------------------------------------------------------------------
# JSON persistence
# ---------------------------------------------------------------------------

def export_offset_calibration_json(
    calibration: LapStartOffsetCalibration,
    output_dir: Optional[Path] = None,
) -> Path:
    """Write a LapStartOffsetCalibration to a JSON file.

    Filename: <track_location_id>__<layout_id>__lap_offset.json
    Stored in output_dir (defaults to data/track_models/).
    Returns the path to the written file.
    """
    from data.track_calibration import TRACK_MODELS_DIR
    out = Path(output_dir) if output_dir is not None else TRACK_MODELS_DIR
    out.mkdir(parents=True, exist_ok=True)
    filename = f"{calibration.track_location_id}__{calibration.layout_id}__lap_offset.json"
    dest = out / filename
    conf_val = (
        calibration.confidence.value
        if hasattr(calibration.confidence, "value")
        else str(calibration.confidence)
    )
    data = {
        "track_location_id": calibration.track_location_id,
        "layout_id": calibration.layout_id,
        "calibration_source": calibration.calibration_source,
        "track_length_m": calibration.track_length_m,
        "gt7_start_distance_m": calibration.gt7_start_distance_m,
        "model_start_distance_m": calibration.model_start_distance_m,
        "offset_m": calibration.offset_m,
        "confidence": conf_val,
        "sample_count": calibration.sample_count,
        "source_session_id": calibration.source_session_id,
        "created_at": calibration.created_at,
        "warnings": list(calibration.warnings),
    }
    dest.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return dest


def import_offset_calibration_json(json_path: Path) -> LapStartOffsetCalibration:
    """Load a LapStartOffsetCalibration from a previously exported JSON file.

    Raises FileNotFoundError if the file does not exist.
    Raises json.JSONDecodeError on malformed JSON.
    Raises KeyError if required fields are missing.
    """
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    return LapStartOffsetCalibration(
        track_location_id=data["track_location_id"],
        layout_id=data["layout_id"],
        calibration_source=data.get("calibration_source", "unknown"),
        track_length_m=float(data["track_length_m"]),
        gt7_start_distance_m=float(data.get("gt7_start_distance_m", 0.0)),
        model_start_distance_m=float(data.get("model_start_distance_m", 0.0)),
        offset_m=float(data["offset_m"]),
        confidence=LapDistanceMappingConfidence(data.get("confidence", "unknown")),
        sample_count=int(data.get("sample_count", 0)),
        source_session_id=data.get("source_session_id", ""),
        created_at=data.get("created_at", ""),
        warnings=list(data.get("warnings", [])),
    )


def load_offset_calibration_for_track(
    track_location_id: str,
    layout_id: str,
    base_dir: Optional[Path] = None,
) -> Optional[LapStartOffsetCalibration]:
    """Load the offset calibration for a track/layout, or None if not found.

    Filename: <track_location_id>__<layout_id>__lap_offset.json
    Looked up in base_dir (defaults to data/track_models/).
    Never raises — all errors return None.
    """
    try:
        from data.track_calibration import TRACK_MODELS_DIR
        base = Path(base_dir) if base_dir is not None else TRACK_MODELS_DIR
        filename = f"{track_location_id}__{layout_id}__lap_offset.json"
        path = base / filename
        if not path.exists():
            return None
        return import_offset_calibration_json(path)
    except Exception:
        return None
