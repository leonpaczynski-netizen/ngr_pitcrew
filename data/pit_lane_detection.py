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


#: Side length of a spatial-index cell, in metres. Chosen so a query has to examine
#: only the 3x3 block around a point: any station nearer than the cell size is
#: guaranteed to be in that block. 50 m keeps the block small on a 5 km circuit while
#: comfortably exceeding the divergence distances this module cares about.
_GRID_M: float = 50.0


class _StationIndex:
    """Uniform grid over the station XZ positions.

    The nearest-station search is the whole cost of this module: a 90-second lap at
    60 Hz against a 5 km centreline is 27 million distance computations, which measured
    at ~1.7 seconds per detection and used to run on the Qt thread (defect D9). Bucketing
    the stations makes each query examine a few dozen candidates instead of five
    thousand, and the answer is identical — this is an index, not an approximation.

    Built once per detection call and thrown away; the cost is one pass over the
    stations, which is negligible beside the query loop it replaces.
    """

    __slots__ = ("_cells", "_pts", "_max_ring")

    def __init__(self, stations: Sequence) -> None:
        self._cells: dict = {}
        self._pts: list = []
        for s in stations:
            try:
                x, z, m = float(s.x), float(s.z), float(s.station_m)
            except (AttributeError, TypeError, ValueError):
                continue
            idx = len(self._pts)
            self._pts.append((x, z, m))
            self._cells.setdefault(
                (int(x // _GRID_M), int(z // _GRID_M)), []).append(idx)
        # The widest ring that could still reach an unexamined cell, measured from the
        # index's own extent. A fixed cap here would be a CORRECTNESS bug rather than a
        # slow path: a query far outside the track would stop expanding before reaching
        # any station and report "no station anywhere", which is a different answer from
        # the linear search rather than a slower route to the same one.
        if self._cells:
            gxs = [c[0] for c in self._cells]
            gzs = [c[1] for c in self._cells]
            self._max_ring = max(max(gxs) - min(gxs), max(gzs) - min(gzs)) + 1
        else:
            self._max_ring = 0

    def __bool__(self) -> bool:
        return bool(self._pts)

    def nearest(self, x: float, z: float) -> "tuple[float, float]":
        """(distance, station_m) of the nearest station, or (inf, 0.0)."""
        cells = self._cells
        if not cells:
            return (float("inf"), 0.0)
        cx, cz = int(x // _GRID_M), int(z // _GRID_M)
        best_d = float("inf")
        best_m = 0.0
        pts = self._pts
        # Distance from the query cell to the furthest occupied cell, so the loop is
        # guaranteed to terminate having examined every station rather than at an
        # arbitrary cap.
        gxs = [c[0] for c in cells]
        gzs = [c[1] for c in cells]
        limit = max(max(abs(cx - min(gxs)), abs(cx - max(gxs))),
                    max(abs(cz - min(gzs)), abs(cz - max(gzs)))) + 1
        ring = 1
        while ring <= limit:
            for gx in range(cx - ring, cx + ring + 1):
                for gz in range(cz - ring, cz + ring + 1):
                    for i in cells.get((gx, gz), ()):
                        px, pz, pm = pts[i]
                        dx = x - px
                        dz = z - pz
                        d = dx * dx + dz * dz   # squared; sqrt once at the end
                        if d < best_d:
                            best_d = d
                            best_m = pm
            # A hit inside the searched block is only provably nearest once the block
            # extends at least as far as the hit itself. Widen until that holds.
            if best_d <= (ring * _GRID_M) ** 2:
                break
            ring += 1
        return (math.sqrt(best_d) if best_d < float("inf") else float("inf"), best_m)


def _nearest(x: float, z: float, stations: Sequence) -> "tuple[float, float]":
    """(distance, station_m) of the nearest station in the XZ plane.

    Linear reference implementation. Kept because it is the thing ``_StationIndex`` is
    tested against — an index that silently disagrees with the obvious answer is worse
    than the slow loop it replaced.
    """
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
        index = _StationIndex(stations)
        if not index:
            return PitLaneTraversal(reason="no samples or no station map")

        run_start_idx: Optional[int] = None
        run_entry_m = 0.0
        best: Optional[PitLaneTraversal] = None
        max_offset = 0.0
        prev_on_line_m = 0.0

        for idx, s in enumerate(pts):
            try:
                dist, station_m = index.nearest(float(s.x), float(s.z))
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
