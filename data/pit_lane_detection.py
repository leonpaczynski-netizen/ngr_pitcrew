"""Pit-lane traversal detection from telemetry (pure) — UAT 2026-08-07 D1/D5/D6/D8.

During track modelling the app tells the driver "box this lap — a drive-through is
enough, you don't need to stop". Nothing could act on that. Three separate reasons:

* the only telemetry pit detector (``telemetry.state``) needs either refuelling or a
  3-second stop below 10 km/h **in RACING phase**. Track modelling runs in Time Trial,
  where that phase never occurs, so the instruction it gives is unsatisfiable by the
  detector it has (D8);
* the geometric detector (``track_calibration.detect_pit_lap_raw``) measures each
  sample's distance from the LAP'S OWN CENTROID. On any real circuit the centroid is
  the middle of the track and essentially every sample is more than 60 m from it — a
  perfectly clean circular lap is flagged as a pit lap. It was only ever harmless
  because ``pit_detection_enabled`` defaults False and no production caller opts in
  (D5). Turning that flag on without fixing the geometry would have marked EVERY lap a
  pit lap, and convergence would then have excluded all of them;
* the threshold is 60 m, chosen to match a distance constant rather than a pit lane.
  Real pit lanes run 15-30 m from the racing line, so a correct traversal reads as "no
  pit lane seen" (D6).

What a pit lane actually is, geometrically: a path that DIVERGES from the reference
line, stays diverged for a meaningful distance, and REJOINS it. That is what this
module looks for — distance from the nearest station on the measured centreline, never
from a centroid — and it needs no race phase, no refuelling and no stop, so the
drive-through the app asks for is the thing it detects.

Pure: no Qt, no DB, no network, no AI, no wall-clock, no randomness. Never raises.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

#: How far off the reference line a sample must sit to count as "not on the racing
#: line". A car on-line sits within a few metres of a station; a wide line or a kerb
#: excursion reaches perhaps 5-10 m; a pit lane runs 15-30 m. 12 m separates the last
#: two without needing the lane to be unusually wide. The old 60 m constant was copied
#: from track_map_matching.PIT_DISTANCE_THRESHOLD_M, which answers a different
#: question (is this sample so far off that map-matching should give up?).
DIVERGENCE_THRESHOLD_M: float = 12.0

#: How much continuous diverged running makes it a pit lane rather than an off. A
#: short excursion is a mistake; a pit lane is a road.
MIN_TRAVERSAL_M: float = 120.0

#: A traversal must come back. A car that leaves the line and never returns within the
#: lap went off and stopped — that is not a pit lane.
REJOIN_THRESHOLD_M: float = 15.0


@dataclass(frozen=True)
class PitLaneTraversal:
    """One detected divergence-and-rejoin, in reference-line coordinates."""
    detected: bool = False
    entry_station_m: float = 0.0
    exit_station_m: float = 0.0
    length_m: float = 0.0
    max_offset_m: float = 0.0
    sample_count: int = 0
    reason: str = ""

    def as_json(self) -> dict:
        return {"detected": self.detected, "entry_station_m": self.entry_station_m,
                "exit_station_m": self.exit_station_m, "length_m": self.length_m,
                "max_offset_m": self.max_offset_m, "sample_count": self.sample_count,
                "reason": self.reason}


def _nearest(x: float, z: float, stations: Sequence) -> "tuple[float, float]":
    """(distance, station_m) of the nearest station in the XZ plane."""
    best_d = float("inf")
    best_m = 0.0
    for s in stations:
        dx = x - s.x
        dz = z - s.z
        d = dx * dx + dz * dz          # squared — the sqrt is done once at the end
        if d < best_d:
            best_d = d
            best_m = s.station_m
    return (math.sqrt(best_d) if best_d < float("inf") else float("inf"), best_m)


def detect_pit_lane_traversal(
    samples: Sequence,
    stations: Sequence,
    *,
    divergence_m: float = DIVERGENCE_THRESHOLD_M,
    min_traversal_m: float = MIN_TRAVERSAL_M,
    stride: int = 1,
) -> PitLaneTraversal:
    """Find a divergence-and-rejoin in one lap's samples. Never raises.

    ``stride`` subsamples the input. The full search is O(samples x stations) and a
    90-second lap at 60 Hz against a 5 km centreline is ~27 million distance
    computations; the caller decides how much precision it needs (defect D9).
    """
    try:
        if not samples or not stations:
            return PitLaneTraversal(reason="no samples or no station map")

        step = max(1, int(stride or 1))
        pts = list(samples)[::step]

        run_start_idx: Optional[int] = None
        run_entry_m = 0.0
        best: Optional[PitLaneTraversal] = None
        max_offset = 0.0
        prev_on_line_m = 0.0

        for idx, s in enumerate(pts):
            try:
                dist, station_m = _nearest(float(s.x), float(s.z), stations)
            except (AttributeError, TypeError, ValueError):
                continue

            if dist > divergence_m:
                if run_start_idx is None:
                    run_start_idx = idx
                    run_entry_m = prev_on_line_m or station_m
                    max_offset = dist
                else:
                    max_offset = max(max_offset, dist)
                continue

            # Back on the line — close any open run.
            prev_on_line_m = station_m
            if run_start_idx is None:
                continue
            if dist <= REJOIN_THRESHOLD_M:
                length = abs(station_m - run_entry_m)
                # A traversal that wraps the start/finish line reads as almost a whole
                # lap; take the short way round.
                total = _lap_length(stations)
                if total and length > total / 2.0:
                    length = total - length
                if length >= min_traversal_m:
                    candidate = PitLaneTraversal(
                        detected=True, entry_station_m=run_entry_m,
                        exit_station_m=station_m, length_m=length,
                        max_offset_m=max_offset, sample_count=idx - run_start_idx,
                        reason=(f"diverged up to {max_offset:.0f} m off the line for "
                                f"{length:.0f} m and rejoined"))
                    if best is None or candidate.length_m > best.length_m:
                        best = candidate
            run_start_idx = None
            max_offset = 0.0

        if best is not None:
            return best
        if run_start_idx is not None:
            return PitLaneTraversal(
                reason="the car left the racing line and did not rejoin on this lap")
        return PitLaneTraversal(
            reason=f"no continuous run more than {divergence_m:.0f} m off the racing line")
    except Exception:
        return PitLaneTraversal(reason="pit-lane detection failed")


def _lap_length(stations: Sequence) -> float:
    try:
        return max(float(s.station_m) for s in stations)
    except (ValueError, TypeError, AttributeError):
        return 0.0


def is_pit_lap(samples: Sequence, stations: Sequence, **kwargs) -> bool:
    """True when this lap contains a pit-lane traversal.

    The replacement for ``track_calibration.detect_pit_lap_raw``, which measured
    distance from the lap's own centroid and therefore flagged every clean lap.
    Requires a station map: without a measured reference line there is nothing to
    diverge FROM, and guessing is what produced the centroid version.
    """
    return detect_pit_lane_traversal(samples, stations, **kwargs).detected
