"""Track Width Model — learn and represent track width from telemetry lateral offsets.

Pure Python, no PyQt6 dependency.

Width represents the usable ribbon of track at each station.  There are two
sources of information:
  1. Seed defaults — a fixed nominal width (e.g. 12 m) applied to all stations
     when no telemetry data is available.
  2. Telemetry-observed — min/max lateral offsets measured from clean laps.
     This represents the DRIVEN envelope, NOT the legal track boundary.

Design rules:
  - Never assume telemetry proves the full legal track width.
  - Treat telemetry-observed width as "observed usable envelope".
  - If observed min/max lateral range is smaller than seed width, the seed
    width is preserved as the conservative estimate.
  - Stations with fewer than MIN_OBS_LAPS lateral observations retain SEED_DEFAULT
    width.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from data.track_station_map import StationPoint, TrackStationMap, WidthSource
from data.track_map_matching import match_position_to_map, MapMatchConfidence


MIN_OBS_LAPS: int          = 2     # require at least this many laps before updating width
NEAR_EDGE_THRESHOLD_M: float = 0.5  # < this dist to edge → near-edge flag


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class WidthObservation:
    """Lateral offsets recorded at one station across multiple laps."""
    station_idx:  int
    station_m:    float
    offsets:      List[float] = field(default_factory=list)   # +left, –right

    def sample_count(self) -> int:
        return len(self.offsets)

    def min_offset(self) -> float:
        return min(self.offsets) if self.offsets else 0.0

    def max_offset(self) -> float:
        return max(self.offsets) if self.offsets else 0.0

    def observed_left_m(self) -> float:
        """Maximum leftward offset (positive)."""
        return max(0.0, self.max_offset())

    def observed_right_m(self) -> float:
        """Maximum rightward offset magnitude (from centreline to right)."""
        return max(0.0, -self.min_offset())


@dataclass
class WidthEstimate:
    """Best current width estimate for one station."""
    station_idx:    int
    station_m:      float
    left_width_m:   float
    right_width_m:  float
    source:         str       # WidthSource value
    obs_lap_count:  int = 0   # how many laps contributed
    confidence:     float = 0.0


# ---------------------------------------------------------------------------
# Width learning from calibration laps
# ---------------------------------------------------------------------------

def collect_lateral_offsets(
    session,              # CalibrationSession duck-type
    station_map: TrackStationMap,
    quality_filter: bool = True,
) -> Dict[int, WidthObservation]:
    """Accumulate lateral offsets per station from all usable calibration laps.

    Args:
        session:        CalibrationSession with .laps (list of CalibrationLap).
        station_map:    Station map to match positions against.
        quality_filter: If True, only use laps whose .quality == USABLE.

    Returns:
        Dict mapping station_idx → WidthObservation.
    """
    observations: Dict[int, WidthObservation] = {}

    try:
        from data.track_calibration import CalibrationLapQuality
        required_quality = CalibrationLapQuality.USABLE
    except ImportError:
        required_quality = None

    for lap in session.laps:
        if quality_filter and required_quality is not None:
            if getattr(lap, "quality", None) != required_quality:
                continue

        for sample in lap.samples:
            spd = getattr(sample, "speed_kph", 0.0) or 0.0
            result = match_position_to_map(
                sample.x, sample.y, sample.z, station_map, speed_kph=spd
            )
            if result.confidence == MapMatchConfidence.UNKNOWN:
                continue   # skip pit/OOB samples

            idx = result.nearest_station_idx
            if idx not in observations:
                observations[idx] = WidthObservation(
                    station_idx = idx,
                    station_m   = result.station_m,
                )
            observations[idx].offsets.append(result.lateral_offset_m)

    return observations


def build_width_estimates(
    observations: Dict[int, WidthObservation],
    station_map: TrackStationMap,
) -> Dict[int, WidthEstimate]:
    """Convert lateral offset observations to WidthEstimate per station.

    Only stations with >= MIN_OBS_LAPS distinct lap observations get
    TELEMETRY_OBSERVED status; others retain SEED_DEFAULT.
    """
    estimates: Dict[int, WidthEstimate] = {}

    for idx, obs in observations.items():
        if obs.sample_count() < MIN_OBS_LAPS:
            continue   # insufficient data

        seed_left  = station_map.default_track_width_m / 2.0
        seed_right = station_map.default_track_width_m / 2.0

        if idx < len(station_map.stations):
            s = station_map.stations[idx]
            if s.left_width_m  > 0:
                seed_left  = s.left_width_m
            if s.right_width_m > 0:
                seed_right = s.right_width_m

        # Observed envelope is always within seed bounds
        obs_left  = min(obs.observed_left_m(),  seed_left)
        obs_right = min(obs.observed_right_m(), seed_right)

        confidence = min(1.0, obs.sample_count() / 50.0)

        estimates[idx] = WidthEstimate(
            station_idx   = idx,
            station_m     = obs.station_m,
            left_width_m  = max(seed_left,  obs_left),
            right_width_m = max(seed_right, obs_right),
            source        = WidthSource.TELEMETRY_OBSERVED,
            obs_lap_count = obs.sample_count(),
            confidence    = confidence,
        )

    return estimates


def apply_width_estimates_to_map(
    station_map: TrackStationMap,
    estimates: Dict[int, WidthEstimate],
) -> None:
    """Update station map stations in-place with telemetry-learned widths."""
    for idx, est in estimates.items():
        if idx < len(station_map.stations):
            s = station_map.stations[idx]
            s.left_width_m  = est.left_width_m
            s.right_width_m = est.right_width_m
            s.width_source  = est.source


# ---------------------------------------------------------------------------
# Near-edge detection helpers
# ---------------------------------------------------------------------------

def is_near_left_edge(match_result, threshold_m: float = NEAR_EDGE_THRESHOLD_M) -> bool:
    """True if the car is within threshold_m of the left track edge."""
    return match_result.dist_to_left_edge_m <= threshold_m


def is_near_right_edge(match_result, threshold_m: float = NEAR_EDGE_THRESHOLD_M) -> bool:
    """True if the car is within threshold_m of the right track edge."""
    return match_result.dist_to_right_edge_m <= threshold_m


def unused_track_width_pct(match_result) -> float:
    """Fraction of track width NOT driven (0 = used all, 1 = used none).

    Returns 0.0 if width information is unknown.
    """
    total = match_result.dist_to_left_edge_m + match_result.dist_to_right_edge_m
    if total <= 0:
        return 0.0
    driven = total - abs(match_result.lateral_offset_m)
    return max(0.0, min(1.0, 1.0 - driven / total))
