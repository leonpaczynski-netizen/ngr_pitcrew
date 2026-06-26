"""Track Geometry Builder — builds seed coordinate maps from calibration sessions.

Group 17V — Professional Track Geometry Builder.

Pure Python, no PyQt6 dependency.  All functions are unit-testable without a Qt application.

Architecture boundary:
  - Owns: lap-length filtering, multi-lap averaging, SeedCoordinateMap construction,
           library persistence for geometry.seed_map.json.
  - Does NOT own: corner detection, segment classification, UI.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from data.track_calibration import (
    CalibrationSession,
    CalibrationLap,
    CalibrationLapQuality,
    evaluate_lap_quality,
    estimate_path_length,
)
from data.track_station_map import resample_path_to_uniform_spacing
from data.track_seed_coordinate_map import (
    SeedCoordinateMap,
    SeedMapStation,
    export_seed_coordinate_map_json,
)
from data.track_library import _layout_dir, update_manifest_availability


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------

@dataclass
class LapGeometryFilterResult:
    lap_index:  int
    status:     str    # "accepted" | "rejected"
    reason:     str    # "" if accepted, classification if rejected
    delta_pct:  float
    note:       str    # racing-line note if 0 < delta_pct < 5


@dataclass
class GeometryBuildResult:
    accepted_lap_indices: List[int]
    rejected_laps:        List[LapGeometryFilterResult]
    can_generate:         bool
    seed_map:             Optional[SeedCoordinateMap]
    confidence:           str    # "low" | "medium" | "high"
    station_count:        int


@dataclass
class GeometrySaveResult:
    saved_path:       Optional[Path]
    manifest_updated: bool
    error:            str   # "" on success


# ---------------------------------------------------------------------------
# Delta classification
# ---------------------------------------------------------------------------

def classify_lap_delta(delta_pct: float, consistent_short_count: int) -> str:
    """Classify a lap length delta into a rejection reason string.

    Rules:
      delta_pct < 5.0 → "racing-line variance"
      5.0 ≤ delta_pct ≤ 20.0 AND consistent_short_count < 3  → "incomplete lap"
      5.0 ≤ delta_pct ≤ 20.0 AND consistent_short_count >= 3 → "scale discrepancy"
      delta_pct > 20.0 → "critical / wrong layout"
    """
    if delta_pct < 5.0:
        return "racing-line variance"
    elif delta_pct <= 20.0:
        if consistent_short_count < 3:
            return "incomplete lap"
        else:
            return "scale discrepancy"
    else:
        return "critical / wrong layout"


# ---------------------------------------------------------------------------
# Lap filtering
# ---------------------------------------------------------------------------

def filter_full_laps(
    session: CalibrationSession,
    manifest_lap_length_m: float,
) -> List[LapGeometryFilterResult]:
    """Filter laps by existing quality gates and full-lap threshold.

    A lap must pass the existing quality gates (evaluate_lap_quality with
    session-level medians) AND have a measured path length >= 95% of
    manifest_lap_length_m to be accepted.

    Returns one LapGeometryFilterResult per lap in session.laps order.
    """
    import statistics as _stats

    # Compute session-level medians for the existing quality evaluator
    path_lengths = [estimate_path_length(lap.samples) for lap in session.laps]
    durations    = [lap.lap_time_ms for lap in session.laps]
    median_path  = _stats.median(path_lengths) if path_lengths else None
    median_dur   = _stats.median(durations)    if durations    else None

    # Pre-compute consistent_short_count: laps where 5 <= delta_pct <= 20
    # (all on the short side relative to manifest)
    consistent_short_count = 0
    for path_len in path_lengths:
        if manifest_lap_length_m > 0:
            delta = abs(manifest_lap_length_m - path_len) / manifest_lap_length_m * 100.0
            if 5.0 <= delta <= 20.0 and path_len < manifest_lap_length_m:
                consistent_short_count += 1

    results: List[LapGeometryFilterResult] = []

    for idx, lap in enumerate(session.laps):
        path_len = path_lengths[idx]

        # --- Step 1: existing quality gates ---
        qr = evaluate_lap_quality(
            lap,
            session_median_duration_ms=median_dur,
            session_median_path_m=median_path,
        )

        if qr.quality == CalibrationLapQuality.REJECTED:
            reason = "; ".join(qr.reasons) if qr.reasons else "quality check failed"
            results.append(LapGeometryFilterResult(
                lap_index=idx,
                status="rejected",
                reason=reason,
                delta_pct=0.0,
                note="",
            ))
            continue

        # --- Step 2: full-lap threshold (95% of manifest length) ---
        if manifest_lap_length_m > 0:
            delta_pct = abs(manifest_lap_length_m - path_len) / manifest_lap_length_m * 100.0
        else:
            delta_pct = 0.0

        threshold_m = manifest_lap_length_m * 0.95
        if path_len < threshold_m:
            classification = classify_lap_delta(delta_pct, consistent_short_count)
            results.append(LapGeometryFilterResult(
                lap_index=idx,
                status="rejected",
                reason=classification,
                delta_pct=delta_pct,
                note="",
            ))
            continue

        # Accepted — add racing-line note if delta is between 0 and 5%
        note = ""
        if 0.0 < delta_pct < 5.0:
            note = "racing-line variance: lap length within 5% of manifest"

        results.append(LapGeometryFilterResult(
            lap_index=idx,
            status="accepted",
            reason="",
            delta_pct=delta_pct,
            note=note,
        ))

    return results


# ---------------------------------------------------------------------------
# Geometry builder
# ---------------------------------------------------------------------------

def build_seed_geometry(
    session: CalibrationSession,
    manifest_lap_length_m: float,
    track_location_id: str,
    layout_id: str,
) -> GeometryBuildResult:
    """Build a SeedCoordinateMap from accepted laps in the session.

    Steps:
    1.  Filter laps via filter_full_laps().
    2.  Resample each accepted lap to 1 m stations.
    3.  Truncate all to minimum station count, then element-wise average.
    4.  Build and return a SeedCoordinateMap.

    Returns can_generate=False with seed_map=None if no laps pass filtering.
    """
    filter_results = filter_full_laps(session, manifest_lap_length_m)

    accepted_indices: List[int] = []
    rejected_laps: List[LapGeometryFilterResult] = []

    for fr in filter_results:
        if fr.status == "accepted":
            accepted_indices.append(fr.lap_index)
        else:
            rejected_laps.append(fr)

    if not accepted_indices:
        return GeometryBuildResult(
            accepted_lap_indices=[],
            rejected_laps=rejected_laps,
            can_generate=False,
            seed_map=None,
            confidence="low",
            station_count=0,
        )

    # Resample each accepted lap to 1 m uniform stations
    resampled_laps: List[List[tuple]] = []
    for idx in accepted_indices:
        lap = session.laps[idx]
        xyz = [(s.x, s.y, s.z) for s in lap.samples]
        resampled = resample_path_to_uniform_spacing(xyz, spacing_m=1.0)
        resampled_laps.append(resampled)

    # Truncate to minimum station count across laps
    min_count = min(len(r) for r in resampled_laps)
    truncated = [r[:min_count] for r in resampled_laps]

    # Element-wise average
    n_laps = len(truncated)
    averaged: List[tuple] = []
    for i in range(min_count):
        avg_x = sum(r[i][0] for r in truncated) / n_laps
        avg_y = sum(r[i][1] for r in truncated) / n_laps
        avg_z = sum(r[i][2] for r in truncated) / n_laps
        averaged.append((avg_x, avg_y, avg_z))

    # Confidence tier
    n_accepted = len(accepted_indices)
    if n_accepted >= 4:
        confidence = "high"
    elif n_accepted >= 2:
        confidence = "medium"
    else:
        confidence = "low"

    # Build SeedMapStation list
    stations: List[SeedMapStation] = []
    for i, (x, y, z) in enumerate(averaged):
        station_m = float(i)   # 1 m per step after resampling
        progress_pct = (station_m / manifest_lap_length_m * 100.0) if manifest_lap_length_m > 0 else 0.0
        stations.append(SeedMapStation(
            station_m=station_m,
            progress_pct=progress_pct,
            x=x,
            y=y,
            z=z,
        ))

    seed_map = SeedCoordinateMap(
        track_location_id=track_location_id,
        layout_id=layout_id,
        source="telemetry_capture",
        confidence=confidence,
        lap_length_m=manifest_lap_length_m,
        start_finish_station_m=0.0,
        stations=stations,
        has_z_coordinates=True,
        has_corner_markers=False,
        has_sector_markers=False,
        has_width_corridor=False,
    )

    return GeometryBuildResult(
        accepted_lap_indices=accepted_indices,
        rejected_laps=rejected_laps,
        can_generate=True,
        seed_map=seed_map,
        confidence=confidence,
        station_count=len(stations),
    )


# ---------------------------------------------------------------------------
# Save to library
# ---------------------------------------------------------------------------

def save_seed_geometry_to_library(
    seed_map: SeedCoordinateMap,
    track_id: str,
    layout_id: str,
    base_dir: Optional[Path] = None,
) -> GeometrySaveResult:
    """Write geometry.seed_map.json to the track library and update the manifest.

    Save path: data/track_library/tracks/<track_id>/layouts/<layout_id>/geometry.seed_map.json
    Uses the same _layout_dir() resolution as track_library.py.

    Returns GeometrySaveResult with saved_path and manifest_updated populated.
    Never raises.
    """
    try:
        layout_path = _layout_dir(track_id, layout_id, base_dir)
        layout_path.mkdir(parents=True, exist_ok=True)

        # Write via export_seed_coordinate_map_json (it writes to output_dir/<filename>)
        # But the brief requires the file to be named "geometry.seed_map.json", not the
        # default <track_id>__<layout_id>.seed_map.json.  Write directly.
        dest = layout_path / "geometry.seed_map.json"

        import json as _json
        station_list = []
        for s in seed_map.stations:
            entry: dict = {
                "station_m":    s.station_m,
                "progress_pct": s.progress_pct,
                "x":            s.x,
                "y":            s.y,
                "z":            s.z,
            }
            if s.width_left_m  is not None: entry["width_left_m"]  = s.width_left_m
            if s.width_right_m is not None: entry["width_right_m"] = s.width_right_m
            if s.corner_id:                 entry["corner_id"]      = s.corner_id
            if s.sector_id:                 entry["sector_id"]      = s.sector_id
            station_list.append(entry)

        payload = {
            "schema":                 "seed_coordinate_map_v1",
            "track_location_id":      seed_map.track_location_id,
            "layout_id":              seed_map.layout_id,
            "source":                 seed_map.source,
            "confidence":             seed_map.confidence,
            "lap_length_m":           seed_map.lap_length_m,
            "start_finish_station_m": seed_map.start_finish_station_m,
            "has_z_coordinates":      seed_map.has_z_coordinates,
            "has_corner_markers":     seed_map.has_corner_markers,
            "has_sector_markers":     seed_map.has_sector_markers,
            "has_width_corridor":     seed_map.has_width_corridor,
            "notes":                  seed_map.notes,
            "stations":               station_list,
        }

        tmp = dest.with_suffix(".tmp")
        tmp.write_text(_json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(dest)

    except Exception as exc:
        return GeometrySaveResult(
            saved_path=None,
            manifest_updated=False,
            error=str(exc),
        )

    # Update manifest availability
    manifest_updated = update_manifest_availability(
        track_id, layout_id, base_dir, seed_geometry=True
    )

    return GeometrySaveResult(
        saved_path=dest,
        manifest_updated=manifest_updated,
        error="",
    )
