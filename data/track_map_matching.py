"""Track Map Matching — map X/Y/Z telemetry positions to station map stations.

Pure Python, no PyQt6 dependency.

Layer 2 consumer of the Layer 1 TrackStationMap:
  - Takes a real-time or calibration X/Y/Z position from GT7 telemetry.
  - Finds the nearest station on the station map (horizontal XZ plane).
  - Returns station_m, progress_pct, corner_id, corner_phase, lateral_offset_m,
    edge distances, and a confidence rating.

Pit/out-lap detection:
  - Any position that maps > PIT_DISTANCE_THRESHOLD_M from the nearest station
    is treated as likely pit lane or an out-of-bounds fragment.
  - Very low speed samples (< MIN_SPEED_KPH) are treated as grid/pit-stop,
    ignored for map-matching purposes.

Lateral offset convention:
  - Positive  = left of centreline (in direction of travel)
  - Negative  = right of centreline
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from data.track_station_map import StationPoint, TrackStationMap


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PIT_DISTANCE_THRESHOLD_M: float = 60.0   # > this from centreline → likely pit/OOB
MIN_SPEED_KPH: float             = 8.0    # below this → grid/pit-stop, ignore
CONFIDENCE_HIGH_M: float         = 5.0    # within this → HIGH confidence
CONFIDENCE_MED_M:  float         = 20.0   # within this → MEDIUM confidence


# ---------------------------------------------------------------------------
# Enums / dataclasses
# ---------------------------------------------------------------------------

class MapMatchConfidence(str, Enum):
    HIGH    = "high"
    MEDIUM  = "medium"
    LOW     = "low"
    UNKNOWN = "unknown"


@dataclass
class MapMatchResult:
    """Result of matching one telemetry position to the station map."""
    station_m:            float
    progress_pct:         float          # 0–100
    nearest_station_idx:  int
    corner_id:            Optional[str]
    corner_phase:         str
    lateral_offset_m:     float          # +left, –right of centreline
    dist_to_left_edge_m:  float          # distance to left track edge
    dist_to_right_edge_m: float          # distance to right track edge
    dist_to_centreline_m: float          # unsigned distance to nearest station
    confidence:           str            # MapMatchConfidence value
    is_pit_likely:        bool
    warnings:             List[str]      = field(default_factory=list)

    def is_on_track(self) -> bool:
        return not self.is_pit_likely and self.confidence != MapMatchConfidence.UNKNOWN


# ---------------------------------------------------------------------------
# Pure math helpers
# ---------------------------------------------------------------------------

def _xz_dist(x1: float, z1: float, x2: float, z2: float) -> float:
    """Horizontal (XZ plane) distance between two points."""
    return math.sqrt((x1 - x2) ** 2 + (z1 - z2) ** 2)


def _dot2(ax: float, az: float, bx: float, bz: float) -> float:
    return ax * bx + az * bz


def _lateral_offset(
    px: float, pz: float,
    sx: float, sz: float,
    heading_rad: float,
) -> float:
    """Signed lateral offset of (px, pz) relative to station at (sx, sz, heading).

    Positive = left of centreline (in direction of travel).
    The perpendicular (left) direction is 90° counter-clockwise from heading:
      heading → (sin θ, cos θ) in XZ
      perpendicular left → (cos θ, –sin θ) in XZ
    """
    dx = px - sx
    dz = pz - sz
    # heading vector in XZ: forward = (sin(heading), cos(heading))
    # left perpendicular in XZ: (cos(heading), -sin(heading))
    left_x =  math.cos(heading_rad)
    left_z = -math.sin(heading_rad)
    return dx * left_x + dz * left_z


# ---------------------------------------------------------------------------
# Nearest-station finder (linear scan; adequate for typical station counts)
# ---------------------------------------------------------------------------

def find_nearest_station_idx(
    x: float,
    z: float,
    stations: List[StationPoint],
    search_from: int = 0,
    wrap_around: bool = True,
) -> int:
    """Return the index of the station nearest to (x, z) in the XZ plane.

    For live use, ``search_from`` can constrain the search to a local window
    around the last known position.  Setting ``wrap_around=True`` allows the
    search to handle the lap seam (station 0).
    """
    if not stations:
        raise ValueError("stations list is empty")

    n = len(stations)
    best_idx  = 0
    best_dist = float("inf")

    for i, s in enumerate(stations):
        d = _xz_dist(x, z, s.x, s.z)
        if d < best_dist:
            best_dist = d
            best_idx  = i

    return best_idx


# ---------------------------------------------------------------------------
# Main match function
# ---------------------------------------------------------------------------

def match_position_to_map(
    x: float,
    y: float,
    z: float,
    station_map: TrackStationMap,
    speed_kph: float = 0.0,
    hint_idx: Optional[int] = None,
) -> MapMatchResult:
    """Map a telemetry X/Y/Z position to the station map.

    Args:
        x, y, z:      GT7 world position.
        station_map:  1 m station map for the current layout.
        speed_kph:    Current speed; below MIN_SPEED_KPH returns UNKNOWN confidence.
        hint_idx:     Optional previous station index (for faster live updates).

    Returns:
        MapMatchResult with station_m, progress_pct, lateral_offset_m,
        edge distances, confidence, and pit_likely flag.
    """
    warnings: List[str] = []

    if not station_map.stations:
        return MapMatchResult(
            station_m=0.0, progress_pct=0.0, nearest_station_idx=0,
            corner_id=None, corner_phase="unknown",
            lateral_offset_m=0.0, dist_to_left_edge_m=0.0,
            dist_to_right_edge_m=0.0, dist_to_centreline_m=0.0,
            confidence=MapMatchConfidence.UNKNOWN,
            is_pit_likely=False,
            warnings=["Station map is empty"],
        )

    # Very low speed → grid/pit-stop, do not match
    if speed_kph < MIN_SPEED_KPH:
        return MapMatchResult(
            station_m=0.0, progress_pct=0.0, nearest_station_idx=0,
            corner_id=None, corner_phase="unknown",
            lateral_offset_m=0.0, dist_to_left_edge_m=0.0,
            dist_to_right_edge_m=0.0, dist_to_centreline_m=0.0,
            confidence=MapMatchConfidence.UNKNOWN,
            is_pit_likely=True,
            warnings=["Speed too low — likely stationary or pit stop"],
        )

    idx = find_nearest_station_idx(x, z, station_map.stations)
    st  = station_map.stations[idx]

    # Distance to centreline (XZ plane)
    dist = _xz_dist(x, z, st.x, st.z)

    # Lateral offset (signed)
    lat_off = _lateral_offset(x, z, st.x, st.z, st.heading_rad)

    # Edge distances
    left_w  = st.left_width_m  if st.left_width_m  > 0 else station_map.default_track_width_m / 2.0
    right_w = st.right_width_m if st.right_width_m > 0 else station_map.default_track_width_m / 2.0
    dist_left  = left_w  - lat_off   # positive = room to left edge
    dist_right = right_w + lat_off   # positive = room to right edge

    # Confidence
    if dist <= CONFIDENCE_HIGH_M:
        conf = MapMatchConfidence.HIGH
    elif dist <= CONFIDENCE_MED_M:
        conf = MapMatchConfidence.MEDIUM
    elif dist <= PIT_DISTANCE_THRESHOLD_M:
        conf = MapMatchConfidence.LOW
        warnings.append(f"Position {dist:.0f} m from centreline — low confidence")
    else:
        conf = MapMatchConfidence.UNKNOWN
        warnings.append(f"Position {dist:.0f} m from centreline — likely pit/OOB")

    is_pit = dist > PIT_DISTANCE_THRESHOLD_M

    return MapMatchResult(
        station_m            = st.station_m,
        progress_pct         = st.progress_pct,
        nearest_station_idx  = idx,
        corner_id            = st.corner_id,
        corner_phase         = st.corner_phase,
        lateral_offset_m     = lat_off,
        dist_to_left_edge_m  = max(0.0, dist_left),
        dist_to_right_edge_m = max(0.0, dist_right),
        dist_to_centreline_m = dist,
        confidence           = conf,
        is_pit_likely        = is_pit,
        warnings             = warnings,
    )


# ---------------------------------------------------------------------------
# Outlap / first-lap detection helper
# ---------------------------------------------------------------------------

def is_likely_outlap(
    station_m: float,
    lap_length_m: float,
    has_crossed_start_finish: bool,
) -> bool:
    """Return True if this sample is likely from an out-lap (before first S/F crossing).

    ``has_crossed_start_finish`` should be set to True by the caller once the
    lap counter increments for the first time.  Until then, all samples are
    treated as outlap/low-confidence.
    """
    return not has_crossed_start_finish


# ---------------------------------------------------------------------------
# Batch helper: convert calibration laps to map-matched positions
# ---------------------------------------------------------------------------

def map_match_samples(
    samples,   # list of TelemetrySample-like objects with .x, .y, .z, .speed_kph
    station_map: TrackStationMap,
) -> List[MapMatchResult]:
    """Match a list of telemetry samples to the station map.

    Returns one MapMatchResult per sample.  Pure function — no state, no
    PyQt6 dependency.
    """
    results: List[MapMatchResult] = []
    for s in samples:
        spd = getattr(s, "speed_kph", 0.0) or 0.0
        results.append(match_position_to_map(s.x, s.y, s.z, station_map, speed_kph=spd))
    return results
