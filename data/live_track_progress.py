"""Group 56 — Live Position → Track Progress Resolver (pure).

WHY IT EXISTS
  Group 55 added track-specific pit-lane corroboration, but it needs a reliable
  normalised live lap-progress (0.0–1.0) that the app did not produce. This module
  converts live GT7 world position (X/Y/Z) into a read-only normalised lap progress
  by matching the car to the nearest station on an approved / reference track path.
  "The pit wall already has the map — this gives it a finger on the map."

WHAT THIS MODULE IS
  A pure, deterministic resolver over a list of ``TrackPathStation`` (built from a
  ReferencePath / TrackStationMap / plain dict). Given a live position it reports the
  nearest station, distance along the lap, normalised progress, a lateral offset
  estimate, and a confidence grade — mirroring the thresholds already used by
  ``data/track_map_matching.py`` (HIGH ≤5 m, MEDIUM ≤20 m, LOW ≤60 m).

WHAT THIS MODULE IS NOT
  • It NEVER creates a pit stop and never counts one — it only produces progress
    evidence that Group 55 may use to corroborate an existing pit event.
  • It writes no files, needs no DB, imports no Qt, and calls no AI.
  • It never raises on missing / malformed / partial data — it returns an honest
    UNKNOWN result. Unknown / low-confidence progress is NEVER treated as safe and
    is NOT allowed to lift pit confidence (the adapter enforces that).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

# Distance thresholds (metres) — mirror data/track_map_matching.py for consistency.
CONF_HIGH_M: float = 5.0    # within this → HIGH confidence
CONF_MED_M: float = 20.0    # within this → MEDIUM confidence
CONF_LOW_M: float = 60.0    # within this → LOW; beyond → UNKNOWN (likely pit/OOB)


class TrackProgressConfidence(str, Enum):
    UNKNOWN = "UNKNOWN"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

    @property
    def is_usable_for_pit(self) -> bool:
        """Only MEDIUM/HIGH progress may corroborate a pit event (Group 55)."""
        return self in (TrackProgressConfidence.MEDIUM, TrackProgressConfidence.HIGH)


@dataclass(frozen=True)
class TrackPathStation:
    """One station on the reference path (horizontal plane = X/Z; Y = elevation)."""
    index: int
    x: float
    y: float
    z: float
    distance_along_lap_m: float
    progress: Optional[float] = None      # 0.0–1.0 if known
    heading_rad: Optional[float] = None   # forward heading in the XZ plane


@dataclass(frozen=True)
class LiveTrackProgressResult:
    """Read-only resolution of a live position to track progress."""
    progress: Optional[float] = None                 # 0.0–1.0, None when unknown
    distance_along_lap_m: Optional[float] = None
    nearest_station_index: Optional[int] = None
    nearest_distance_m: Optional[float] = None        # XZ distance to the station
    lateral_offset_m: Optional[float] = None          # +left / -right of centreline
    confidence: TrackProgressConfidence = TrackProgressConfidence.UNKNOWN
    source: str = "missing"
    message: str = ""
    warnings: Tuple[str, ...] = ()
    track_id: str = ""
    layout_id: str = ""

    @property
    def has_progress(self) -> bool:
        return self.progress is not None and self.confidence is not TrackProgressConfidence.UNKNOWN

    @property
    def usable_for_pit(self) -> bool:
        """MEDIUM/HIGH progress may feed the Group 55 pit-lane resolver."""
        return self.has_progress and self.confidence.is_usable_for_pit


# ---------------------------------------------------------------------------
# Numeric helpers (reject NaN/inf; never raise)
# ---------------------------------------------------------------------------

def _num(v) -> Optional[float]:
    try:
        if v is None:
            return None
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):  # NaN / inf
        return None
    return f


def _coords(position) -> Optional[Tuple[float, float, float]]:
    """Extract (x, y, z) from a tuple/list, an object, or a dict. None if unusable.

    Accepts (x, z) or (x, y, z) tuples; objects with x/y/z or pos_x/pos_y/pos_z
    (e.g. a GT7Packet); dicts with the same keys. Y defaults to 0.0 when absent.
    """
    if position is None:
        return None
    try:
        # Sequence forms.
        if isinstance(position, (tuple, list)):
            if len(position) == 2:
                x, z = _num(position[0]), _num(position[1])
                y = 0.0
            elif len(position) >= 3:
                x, y, z = _num(position[0]), _num(position[1]), _num(position[2])
            else:
                return None
        else:
            def _pick(*names):
                for nm in names:
                    if isinstance(position, dict):
                        if nm in position:
                            return _num(position[nm])
                    elif hasattr(position, nm):
                        return _num(getattr(position, nm))
                return None
            x = _pick("x", "pos_x")
            y = _pick("y", "pos_y")
            z = _pick("z", "pos_z")
            if y is None:
                y = 0.0
        if x is None or z is None:
            return None
        return (x, y if y is not None else 0.0, z)
    except Exception:
        return None


def _xz_dist(x1, z1, x2, z2) -> float:
    return math.sqrt((x1 - x2) ** 2 + (z1 - z2) ** 2)


# ---------------------------------------------------------------------------
# Station building
# ---------------------------------------------------------------------------

def build_track_path_stations(track_context_or_model) -> List[TrackPathStation]:
    """Build ``TrackPathStation`` list from a variety of reference-path sources.

    Accepts (first usable wins), never raises, returns [] when nothing usable:
      • an object with ``.points`` (ReferencePath): x/y/z, distance_along_lap_m,
        lap_progress.
      • an object with ``.stations`` (TrackStationMap): x/y/z, station_m,
        progress_pct, heading_rad.
      • a dict with ``reference_path`` (a dict/obj), ``stations`` or ``points``.
      • a plain list of station-like dicts/objects.
    """
    try:
        src = track_context_or_model
        if src is None:
            return []

        # Unwrap a track-context dict pointing at a path.
        if isinstance(src, dict):
            for key in ("reference_path", "track_path", "stations", "points"):
                if key in src and src[key] is not None:
                    inner = src[key]
                    built = build_track_path_stations(inner)
                    if built:
                        return built
            return []

        # ReferencePath-like (points with distance_along_lap_m + lap_progress).
        pts = getattr(src, "points", None)
        if pts:
            return _stations_from_points(pts)

        # TrackStationMap-like (stations with station_m + progress_pct).
        sts = getattr(src, "stations", None)
        if sts:
            return _stations_from_station_map(sts)

        # A plain list.
        if isinstance(src, (list, tuple)) and src:
            # Heuristic: station_m present → station-map style; else points style.
            first = src[0]
            if _has(first, "station_m") or _has(first, "progress_pct"):
                return _stations_from_station_map(src)
            return _stations_from_points(src)

        return []
    except Exception:
        return []


def _has(obj, key) -> bool:
    if isinstance(obj, dict):
        return key in obj
    return hasattr(obj, key)


def _get(obj, *names, default=None):
    for nm in names:
        if isinstance(obj, dict):
            if nm in obj:
                return obj[nm]
        elif hasattr(obj, nm):
            return getattr(obj, nm)
    return default


def _stations_from_points(pts) -> List[TrackPathStation]:
    out: List[TrackPathStation] = []
    for i, p in enumerate(pts):
        x = _num(_get(p, "x", "pos_x"))
        z = _num(_get(p, "z", "pos_z"))
        if x is None or z is None:
            continue
        y = _num(_get(p, "y", "pos_y")) or 0.0
        dist = _num(_get(p, "distance_along_lap_m", "station_m", default=None))
        prog = _num(_get(p, "progress", "lap_progress", default=None))
        if prog is not None and prog > 1.0 + 1e-9:  # a percentage slipped through
            prog = prog / 100.0
        heading = _num(_get(p, "heading_rad", default=None))
        out.append(TrackPathStation(
            index=len(out), x=x, y=y, z=z,
            distance_along_lap_m=dist if dist is not None else float(len(out)),
            progress=prog, heading_rad=heading,
        ))
    return out


def _stations_from_station_map(sts) -> List[TrackPathStation]:
    out: List[TrackPathStation] = []
    for s in sts:
        x = _num(_get(s, "x", "pos_x"))
        z = _num(_get(s, "z", "pos_z"))
        if x is None or z is None:
            continue
        y = _num(_get(s, "y", "pos_y")) or 0.0
        dist = _num(_get(s, "station_m", "distance_along_lap_m", default=None))
        pct = _num(_get(s, "progress_pct", default=None))
        prog = None
        if pct is not None:
            prog = pct / 100.0
        else:
            p = _num(_get(s, "progress", "lap_progress", default=None))
            prog = p
        heading = _num(_get(s, "heading_rad", default=None))
        out.append(TrackPathStation(
            index=len(out), x=x, y=y, z=z,
            distance_along_lap_m=dist if dist is not None else float(len(out)),
            progress=prog, heading_rad=heading,
        ))
    return out


def _lap_length_from_stations(stations: List[TrackPathStation]) -> Optional[float]:
    """Best-effort lap length = the maximum distance_along_lap_m across stations."""
    dists = [s.distance_along_lap_m for s in stations
             if s.distance_along_lap_m is not None]
    if not dists:
        return None
    lap = max(dists)
    return lap if lap > 0 else None


# ---------------------------------------------------------------------------
# Progress helpers
# ---------------------------------------------------------------------------

def normalise_distance_to_progress(distance_m, lap_length_m) -> Optional[float]:
    """Convert a distance-along-lap to a normalised progress 0.0–1.0 (wraps).

    Returns None on invalid inputs or a zero/negative lap length. Never raises.
    """
    d = _num(distance_m)
    lap = _num(lap_length_m)
    if d is None or lap is None or lap <= 0:
        return None
    p = (d % lap) / lap
    if p < 0.0:
        p += 1.0
    if p >= 1.0:
        p = p % 1.0
    return p


def nearest_station(position, stations) -> Optional[Tuple[int, float]]:
    """Return (nearest_index, xz_distance_m) or None. XZ plane; ignores elevation."""
    coords = _coords(position)
    if coords is None or not stations:
        return None
    px, _py, pz = coords
    best_idx = None
    best_d = float("inf")
    for s in stations:
        if not isinstance(s, TrackPathStation):
            continue
        d = _xz_dist(px, pz, s.x, s.z)
        if d < best_d:
            best_d = d
            best_idx = s.index
    if best_idx is None or best_d == float("inf"):
        return None
    return (best_idx, best_d)


def estimate_lateral_offset(position, station, next_station_or_heading=None) -> Optional[float]:
    """Signed lateral offset (+left / -right) of the position vs the station.

    Uses the station's heading if provided, else derives a heading from the
    next station, else returns None (cannot orient). Never raises.
    """
    coords = _coords(position)
    if coords is None or not isinstance(station, TrackPathStation):
        return None
    px, _py, pz = coords

    heading = station.heading_rad
    if heading is None:
        nx = next_station_or_heading
        if isinstance(nx, (int, float)):
            heading = _num(nx)
        elif isinstance(nx, TrackPathStation):
            dx = nx.x - station.x
            dz = nx.z - station.z
            if abs(dx) > 1e-9 or abs(dz) > 1e-9:
                heading = math.atan2(dx, dz)  # forward = (sin h, cos h) in XZ
    if heading is None:
        return None

    dx = px - station.x
    dz = pz - station.z
    # left perpendicular in XZ = (cos h, -sin h)
    left_x = math.cos(heading)
    left_z = -math.sin(heading)
    return dx * left_x + dz * left_z


# ---------------------------------------------------------------------------
# Main resolver
# ---------------------------------------------------------------------------

def resolve_live_track_progress(
    position,
    stations,
    *,
    track_id: Optional[str] = None,
    layout_id: Optional[str] = None,
    lap_length_m: Optional[float] = None,
    identity_ok: bool = True,
    speed_kph: Optional[float] = None,
    source: str = "track_model",
) -> LiveTrackProgressResult:
    """Resolve a live world position to normalised track progress. Never raises.

    Confidence (distance to the nearest reference station, XZ plane):
      HIGH   ≤ CONF_HIGH_M  and valid lap length/progress and identity matches
      MEDIUM ≤ CONF_MED_M   and valid lap length/progress
      LOW    ≤ CONF_LOW_M   (usable but uncertain — NOT used to lift pit confidence)
      UNKNOWN: no path / no position / invalid numbers / too far / wrong layout
    """
    tid = str(track_id or "")
    lid = str(layout_id or "")

    if not stations:
        return LiveTrackProgressResult(
            confidence=TrackProgressConfidence.UNKNOWN, source="missing",
            message="Approved reference path unavailable for this track/layout.",
            warnings=("approved reference path unavailable",),
            track_id=tid, layout_id=lid,
        )

    coords = _coords(position)
    if coords is None:
        return LiveTrackProgressResult(
            confidence=TrackProgressConfidence.UNKNOWN, source=source,
            message="Live world position unavailable.",
            warnings=("live world position unavailable",),
            track_id=tid, layout_id=lid,
        )

    valid_stations = [s for s in stations if isinstance(s, TrackPathStation)]
    near = nearest_station(coords, valid_stations)
    if near is None:
        return LiveTrackProgressResult(
            confidence=TrackProgressConfidence.UNKNOWN, source=source,
            message="Could not match live position to the reference path.",
            warnings=("live world position unavailable",),
            track_id=tid, layout_id=lid,
        )
    idx, dist = near
    st = valid_stations[idx] if idx < len(valid_stations) else _by_index(valid_stations, idx)

    lap = _num(lap_length_m) or _lap_length_from_stations(valid_stations)
    progress = st.progress if (st and st.progress is not None) else \
        normalise_distance_to_progress(st.distance_along_lap_m if st else None, lap)

    warnings: List[str] = []

    # Grade confidence on nearest distance + data validity + identity.
    if dist > CONF_LOW_M:
        return LiveTrackProgressResult(
            progress=None,
            distance_along_lap_m=(st.distance_along_lap_m if st else None),
            nearest_station_index=idx, nearest_distance_m=dist,
            lateral_offset_m=None,
            confidence=TrackProgressConfidence.UNKNOWN, source=source,
            message=f"Live position is {dist:.0f} m from the reference path — off track / pit / OOB.",
            warnings=("live position is far from the reference path",),
            track_id=tid, layout_id=lid,
        )

    if progress is None:
        warnings.append("reference path has no usable lap length/progress")
        conf = TrackProgressConfidence.LOW
    elif dist <= CONF_HIGH_M:
        conf = TrackProgressConfidence.HIGH
    elif dist <= CONF_MED_M:
        conf = TrackProgressConfidence.MEDIUM
    else:
        conf = TrackProgressConfidence.LOW
        warnings.append("track progress confidence low, not used to lift pit confidence")

    if not identity_ok:
        warnings.append("reference path does not match current track/layout")
        # A mismatched path can never be HIGH/MEDIUM.
        if conf in (TrackProgressConfidence.HIGH, TrackProgressConfidence.MEDIUM):
            conf = TrackProgressConfidence.LOW

    if conf == TrackProgressConfidence.HIGH and dist > CONF_HIGH_M:
        conf = TrackProgressConfidence.MEDIUM  # defensive

    # Lateral offset (best-effort; needs orientation).
    next_st = _by_index(valid_stations, idx + 1)
    lateral = estimate_lateral_offset(coords, st, next_st) if st else None

    pct = f"{progress * 100.0:.1f}%" if progress is not None else "unknown"
    msg = (f"Track progress {pct} (match {conf.value.lower()}, {dist:.1f} m "
           f"from reference path).")

    return LiveTrackProgressResult(
        progress=progress,
        distance_along_lap_m=(st.distance_along_lap_m if st else None),
        nearest_station_index=idx, nearest_distance_m=dist,
        lateral_offset_m=lateral,
        confidence=conf, source=source, message=msg,
        warnings=tuple(warnings), track_id=tid, layout_id=lid,
    )


def _by_index(stations: List[TrackPathStation], idx: int) -> Optional[TrackPathStation]:
    for s in stations:
        if s.index == idx:
            return s
    if 0 <= idx < len(stations):
        return stations[idx]
    return None


# ---------------------------------------------------------------------------
# Rendering (pure, driver-readable, no command wording)
# ---------------------------------------------------------------------------

def format_live_track_progress_evidence(result: LiveTrackProgressResult) -> dict:
    """Return {'found': [...], 'missing': [...], 'warnings': [...]} evidence lines.

    Short, honest, driver-readable. No command wording, no "Pit Now".
    """
    found: List[str] = []
    missing: List[str] = []
    warnings: List[str] = []
    try:
        if result is None:
            return {"found": [], "missing": ["track progress unavailable"], "warnings": []}

        if result.has_progress and result.progress is not None:
            found.append(f"track progress: {result.progress * 100.0:.1f}% lap (track model)")
            if result.distance_along_lap_m is not None:
                found.append(f"distance along lap: {result.distance_along_lap_m:,.0f} m")
            conf = result.confidence.value.lower()
            if result.nearest_distance_m is not None:
                found.append(
                    f"position match: {conf} confidence, "
                    f"{result.nearest_distance_m:.1f} m from reference path")
            else:
                found.append(f"position match: {conf} confidence")
        else:
            if result.confidence is TrackProgressConfidence.UNKNOWN:
                # Distinguish no-path vs no-position vs too-far.
                msg = (result.message or "").lower()
                if "reference path unavailable" in msg:
                    missing.append("approved reference path unavailable")
                elif "world position" in msg:
                    missing.append("live world position unavailable")
                else:
                    missing.append("track progress unavailable, pit-lane corroboration disabled")
            else:
                missing.append("track progress unavailable, pit-lane corroboration disabled")

        for w in result.warnings:
            warnings.append(w)
        return {"found": found, "missing": missing, "warnings": warnings}
    except Exception:
        return {"found": [], "missing": ["track progress unavailable"], "warnings": []}
