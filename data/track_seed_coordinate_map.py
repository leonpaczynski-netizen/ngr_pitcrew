"""Seed Coordinate Map — Layer 1.5 track geometry data for coordinate-based alignment.

A SeedCoordinateMap is a discretised XY centreline for a specific layout, stored at:
    data/track_seed_maps/<track_location_id>__<layout_id>.seed_map.json

When present it enables:
  - Full coordinate-based station-map alignment (mean/max error, missing sections)
  - Visual seed/model overlay in the track map widget
  - Corner and sector boundary matching by coordinate proximity

When absent the system falls back to:
  - Lap-length delta comparison only (track_model_alignment.py)
  - Progress-window-based corner matching (Group 17Q/17S)
  - No visual seed overlay

Seed maps can be sourced from:
  - A previously accepted GT7 telemetry model (exported from TrackStationMap)
  - An official or estimated centreline authored manually as JSON
  - A future SVG/polyline import pipeline

Coordinate space:
  Prefer GT7 world coordinates (X = left/right, Z = forward/back) so that the
  seed centreline can be overlaid on the modelled station map directly.  If the
  seed map was authored in a different coordinate space, record it in ``notes``
  and supply a CoordinateTransform at alignment time.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

SEED_MAPS_DIR = Path(__file__).parent / "track_seed_maps"
SEED_MAP_SCHEMA = "seed_coordinate_map_v1"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SeedMapStation:
    """One point on the seed coordinate centreline."""
    station_m:      float           # cumulative distance from S/F (m)
    progress_pct:   float           # 0–100 % of lap
    x:              float = 0.0     # GT7 world X (or normalised)
    y:              float = 0.0     # GT7 world Z (used as 2-D Y in top-down view)
    z:              float = 0.0     # GT7 world Y — vertical, optional
    width_left_m:   Optional[float] = None
    width_right_m:  Optional[float] = None
    corner_id:      Optional[str]   = None   # e.g. "T1"
    sector_id:      Optional[str]   = None   # e.g. "S1"


@dataclass
class SeedCoordinateMap:
    """Coordinate-based track centreline for a specific layout."""
    track_location_id:      str
    layout_id:              str
    source:                 str   = "unknown"
    confidence:             str   = "low"
    lap_length_m:           float = 0.0
    start_finish_station_m: float = 0.0
    stations:               List[SeedMapStation] = field(default_factory=list)
    has_z_coordinates:      bool  = False
    has_corner_markers:     bool  = False
    has_sector_markers:     bool  = False
    has_width_corridor:     bool  = False
    notes:                  str   = ""

    def station_count(self) -> int:
        return len(self.stations)

    def corner_marker_ids(self) -> List[str]:
        return sorted({s.corner_id for s in self.stations if s.corner_id})

    def sector_ids(self) -> List[str]:
        seen: List[str] = []
        for s in self.stations:
            if s.sector_id and s.sector_id not in seen:
                seen.append(s.sector_id)
        return seen


# ---------------------------------------------------------------------------
# File name convention
# ---------------------------------------------------------------------------

def seed_coordinate_map_filename(track_location_id: str, layout_id: str) -> str:
    return f"{track_location_id}__{layout_id}.seed_map.json"


# ---------------------------------------------------------------------------
# Discovery / load
# ---------------------------------------------------------------------------

def find_seed_coordinate_map_path(
    track_location_id: str,
    layout_id: str,
    base_dir: Optional[Path] = None,
) -> Optional[Path]:
    """Return path to the seed map JSON if it exists, else None."""
    d = Path(base_dir) if base_dir else SEED_MAPS_DIR
    p = d / seed_coordinate_map_filename(track_location_id, layout_id)
    return p if p.exists() else None


def load_seed_coordinate_map(
    track_location_id: str,
    layout_id: str,
    base_dir: Optional[Path] = None,
) -> Optional[SeedCoordinateMap]:
    """Load and parse the seed coordinate map for a layout, or return None if absent."""
    path = find_seed_coordinate_map_path(track_location_id, layout_id, base_dir)
    if path is None:
        return None
    return import_seed_coordinate_map_json(path)


# ---------------------------------------------------------------------------
# JSON import / export
# ---------------------------------------------------------------------------

def export_seed_coordinate_map_json(
    seed_map: SeedCoordinateMap,
    output_dir: Optional[Path] = None,
) -> Path:
    """Serialise a SeedCoordinateMap to JSON and return the written path."""
    out_dir = Path(output_dir) if output_dir else SEED_MAPS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / seed_coordinate_map_filename(
        seed_map.track_location_id, seed_map.layout_id
    )
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
        "schema":                  SEED_MAP_SCHEMA,
        "track_location_id":       seed_map.track_location_id,
        "layout_id":               seed_map.layout_id,
        "source":                  seed_map.source,
        "confidence":              seed_map.confidence,
        "lap_length_m":            seed_map.lap_length_m,
        "start_finish_station_m":  seed_map.start_finish_station_m,
        "has_z_coordinates":       seed_map.has_z_coordinates,
        "has_corner_markers":      seed_map.has_corner_markers,
        "has_sector_markers":      seed_map.has_sector_markers,
        "has_width_corridor":      seed_map.has_width_corridor,
        "notes":                   seed_map.notes,
        "stations":                station_list,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    return path


def import_seed_coordinate_map_json(path) -> Optional[SeedCoordinateMap]:
    """Parse a seed map JSON file; returns None on any error or schema mismatch."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if data.get("schema") != SEED_MAP_SCHEMA:
            return None
        stations = [
            SeedMapStation(
                station_m     = float(s.get("station_m",    0)),
                progress_pct  = float(s.get("progress_pct", 0)),
                x             = float(s.get("x",            0)),
                y             = float(s.get("y",            0)),
                z             = float(s.get("z",            0)),
                width_left_m  = s.get("width_left_m"),
                width_right_m = s.get("width_right_m"),
                corner_id     = s.get("corner_id"),
                sector_id     = s.get("sector_id"),
            )
            for s in data.get("stations", [])
        ]
        return SeedCoordinateMap(
            track_location_id      = data.get("track_location_id", ""),
            layout_id              = data.get("layout_id",          ""),
            source                 = data.get("source",             "unknown"),
            confidence             = data.get("confidence",         "low"),
            lap_length_m           = float(data.get("lap_length_m",           0)),
            start_finish_station_m = float(data.get("start_finish_station_m", 0)),
            stations               = stations,
            has_z_coordinates      = bool(data.get("has_z_coordinates",  False)),
            has_corner_markers     = bool(data.get("has_corner_markers",  False)),
            has_sector_markers     = bool(data.get("has_sector_markers",  False)),
            has_width_corridor     = bool(data.get("has_width_corridor",  False)),
            notes                  = data.get("notes", ""),
        )
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Resample
# ---------------------------------------------------------------------------

def resample_seed_map(
    seed_map: SeedCoordinateMap,
    spacing_m: float = 1.0,
) -> SeedCoordinateMap:
    """Resample a seed coordinate map to uniform station spacing (linear interpolation).

    Returns the original map unchanged if it has no stations or no lap_length_m.
    """
    if not seed_map.stations or seed_map.lap_length_m <= 0:
        return seed_map

    src = sorted(seed_map.stations, key=lambda s: s.station_m)
    total = seed_map.lap_length_m
    n_stations = max(1, int(total / spacing_m))

    resampled: List[SeedMapStation] = []
    for i in range(n_stations):
        target_m = i * spacing_m
        progress = target_m / total * 100.0

        lo = src[0]
        hi = src[-1]
        for j in range(len(src) - 1):
            if src[j].station_m <= target_m <= src[j + 1].station_m:
                lo = src[j]
                hi = src[j + 1]
                break

        span = hi.station_m - lo.station_m
        t = (target_m - lo.station_m) / span if span > 0 else 0.0
        t = max(0.0, min(1.0, t))

        resampled.append(SeedMapStation(
            station_m    = target_m,
            progress_pct = progress,
            x            = lo.x + t * (hi.x - lo.x),
            y            = lo.y + t * (hi.y - lo.y),
            z            = lo.z + t * (hi.z - lo.z),
            corner_id    = lo.corner_id if t < 0.5 else hi.corner_id,
            sector_id    = lo.sector_id if t < 0.5 else hi.sector_id,
        ))

    return SeedCoordinateMap(
        track_location_id      = seed_map.track_location_id,
        layout_id              = seed_map.layout_id,
        source                 = seed_map.source,
        confidence             = seed_map.confidence,
        lap_length_m           = seed_map.lap_length_m,
        start_finish_station_m = seed_map.start_finish_station_m,
        stations               = resampled,
        has_z_coordinates      = seed_map.has_z_coordinates,
        has_corner_markers     = seed_map.has_corner_markers,
        has_sector_markers     = seed_map.has_sector_markers,
        has_width_corridor     = seed_map.has_width_corridor,
        notes                  = seed_map.notes,
    )
