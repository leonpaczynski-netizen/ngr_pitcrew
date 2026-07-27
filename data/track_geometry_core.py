"""Deterministic centreline geometry — the single source of truth for track shape.

One heading + signed-curvature estimator, consumed by BOTH the station map (Layer 1,
``track_station_map``) and corner detection (``track_segment_detection``). Previously
each computed its own heading/curvature with different conventions and a
``max(|xz_curvature|, |yaw_curvature|)`` blend that rectified noise into false peaks;
the two disagreed on corner count, position and direction. This module removes that
divergence.

Design rules (unchanged from the track-model architecture):
  * Geometry comes from X/Z position ONLY. Speed/brake/throttle/yaw never DEFINE shape.
    Yaw rate is available as an optional cross-check (``yaw_curvature_discrepancy``),
    never folded into the geometric magnitude.
  * Signed curvature convention matches ``StationPoint.curvature``: computed as the rate
    of change of heading ``atan2(dx, dz)`` with arc length, so ``+`` and ``−`` keep the
    same left/right meaning the station map already used.
  * Phase-preserving: curvature is a centred, arc-length-baselined difference of the
    heading (a smoothed derivative), so a corner's apex stays at the curvature peak
    instead of being smeared by a trailing box-car.

Pure, deterministic, no Qt, no I/O.
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

#: Arc-length baseline (metres) over which curvature is differenced. Wide enough to
#: reject 1 m position jitter, short enough to resolve a hairpin. This replaces the old
#: 15-station box-car smoothing of an already-noisy 1 m forward difference.
DEFAULT_CURVATURE_BASELINE_M: float = 8.0

#: Minimum car speed (m/s) for a yaw-rate sample to be a usable curvature cross-check.
_MIN_YAW_SPEED_MS: float = 2.78   # 10 km/h


def _angular_diff(a: float, b: float) -> float:
    """Signed smallest angle a−b, normalised to [−π, π]."""
    d = a - b
    while d > math.pi:
        d -= 2 * math.pi
    while d < -math.pi:
        d += 2 * math.pi
    return d


def _cumulative_arc_length(xz: Sequence[Tuple[float, float]]) -> List[float]:
    """Cumulative XZ arc length at each point (first = 0)."""
    cum = [0.0]
    for i in range(1, len(xz)):
        dx = xz[i][0] - xz[i - 1][0]
        dz = xz[i][1] - xz[i - 1][1]
        cum.append(cum[-1] + math.hypot(dx, dz))
    return cum


def compute_headings(xz: Sequence[Tuple[float, float]]) -> List[float]:
    """Per-point heading (rad) via a CENTRED position difference: ``atan2(dx, dz)``.

    Centred (not forward) differencing keeps the heading — and therefore the curvature
    peak — aligned with the geometry. Endpoints fall back to a one-sided difference.
    """
    n = len(xz)
    if n == 0:
        return []
    if n == 1:
        return [0.0]
    headings: List[float] = []
    for i in range(n):
        if i == 0:
            dx = xz[1][0] - xz[0][0]
            dz = xz[1][1] - xz[0][1]
        elif i == n - 1:
            dx = xz[-1][0] - xz[-2][0]
            dz = xz[-1][1] - xz[-2][1]
        else:
            dx = xz[i + 1][0] - xz[i - 1][0]
            dz = xz[i + 1][1] - xz[i - 1][1]
        headings.append(math.atan2(dx, dz))
    return headings


def compute_signed_curvature(
    xz: Sequence[Tuple[float, float]],
    *,
    arc_length: Optional[Sequence[float]] = None,
    baseline_m: float = DEFAULT_CURVATURE_BASELINE_M,
) -> List[float]:
    """Signed curvature (rad/m) at each point: the arc-length rate of heading change.

    For each point we difference the heading between the two path points roughly
    ``baseline_m`` apart, straddling it — a centred, arc-length-normalised derivative
    that is robust to metre-scale jitter yet keeps the peak at the apex. Sign follows
    the heading turn direction (``+`` left / ``−`` right in the GT7 XZ plane), matching
    ``StationPoint.curvature``.
    """
    n = len(xz)
    if n < 3:
        return [0.0] * n
    headings = compute_headings(xz)
    cum = list(arc_length) if arc_length is not None else _cumulative_arc_length(xz)
    half = max(baseline_m / 2.0, 1e-6)

    curv: List[float] = []
    for i in range(n):
        # Walk outward to points ~half the baseline behind and ahead (arc length).
        lo = i
        while lo > 0 and (cum[i] - cum[lo]) < half:
            lo -= 1
        hi = i
        while hi < n - 1 and (cum[hi] - cum[i]) < half:
            hi += 1
        ds = cum[hi] - cum[lo]
        if ds <= 1e-9 or lo == hi:
            curv.append(0.0)
            continue
        dtheta = _angular_diff(headings[hi], headings[lo])
        curv.append(dtheta / ds)
    return curv


def compute_geometry(
    xz: Sequence[Tuple[float, float]],
    *,
    arc_length: Optional[Sequence[float]] = None,
    baseline_m: float = DEFAULT_CURVATURE_BASELINE_M,
) -> Tuple[List[float], List[float]]:
    """(headings, signed_curvatures) for a centreline — the one call both layers use."""
    headings = compute_headings(xz)
    curvature = compute_signed_curvature(xz, arc_length=arc_length, baseline_m=baseline_m)
    return headings, curvature


def yaw_curvature_discrepancy(
    geometric_curvature: Sequence[float],
    yaw_rates: Sequence[Optional[float]],
    speeds_ms: Sequence[Optional[float]],
) -> Optional[float]:
    """Mean |geometric − yaw-implied| curvature, as a CROSS-CHECK only (never blended).

    Yaw-implied curvature is ``yaw_rate / speed``. Returns the mean absolute difference
    over points with a usable yaw sample, or ``None`` when there is no usable yaw data.
    A large value flags telemetry/geometry disagreement for diagnostics; it never alters
    the geometric curvature that defines the track.
    """
    diffs: List[float] = []
    # Iterate the three sequences together defensively (lengths may differ).
    m = min(len(geometric_curvature), len(yaw_rates), len(speeds_ms))
    for i in range(m):
        yaw = yaw_rates[i]
        spd = speeds_ms[i]
        if yaw is None or spd is None or spd < _MIN_YAW_SPEED_MS:
            continue
        yaw_curv = yaw / spd
        diffs.append(abs(geometric_curvature[i] - yaw_curv))
    if not diffs:
        return None
    return sum(diffs) / len(diffs)
