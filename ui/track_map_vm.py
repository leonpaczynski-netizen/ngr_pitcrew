"""Track Map View Model — screen-independent drawing primitives.

Pure Python, NO PyQt6 dependency.  All geometry is computed here; the
dashboard.py QPainter code only consumes the resulting primitive lists.

This module converts TrackStationMap + MapMatchResult into a
TrackMapDrawData object that can be:
  - Rendered by a QPainter widget in dashboard.py
  - Inspected in unit tests without a QApplication

Coordinate projection:
  GT7 world space uses X (left/right) and Z (forward/back) as the horizontal
  plane.  For 2D screen display we map:
      screen_x ← world_x (possibly reflected)
      screen_y ← world_z (Y-up in GT7, which is Z in standard top-view)
  No scaling or reflection is assumed here — project_to_screen() handles that.
"""
from __future__ import annotations

import math
from collections import OrderedDict, namedtuple
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from data.track_station_map import TrackStationMap, SeededCorner, StationPoint
from data.track_map_matching import MapMatchResult, MapMatchConfidence


# ---------------------------------------------------------------------------
# Drawing primitive dataclasses (all coordinates in world or screen space)
# ---------------------------------------------------------------------------

@dataclass
class MapPoint:
    """A 2-D point in map space (world X and Z) or screen space (pixel x, y)."""
    x: float
    y: float   # = world Z in map space; pixel y in screen space


@dataclass
class CornerLabel:
    """A corner label to render at a given map position."""
    text:   str
    x:      float
    y:      float
    is_placeholder: bool = False   # grey-out if True (seeded placeholder)


@dataclass
class CarDot:
    """Live car position dot."""
    x:          float
    y:          float
    confidence: str   # MapMatchConfidence value
    is_valid:   bool = True


@dataclass
class TrackMapDrawData:
    """Complete drawing data for one frame.  Passed to the QPainter widget."""
    # Track shape
    centreline:   List[MapPoint]
    width_left:   List[MapPoint]    # left edge polyline
    width_right:  List[MapPoint]    # right edge polyline
    # Markers
    start_finish: Optional[MapPoint]
    # Annotations
    corner_labels:    List[CornerLabel]
    # Live overlay
    car_dot:      Optional[CarDot]
    telemetry_trace: List[MapPoint]    # historical positions from this session
    # Meta
    bounds:       Tuple[float, float, float, float]   # min_x, min_y, max_x, max_y
    status_text:  str    # shown in a status bar on the widget
    confidence_color: str  # "#2EA043" / "#F5A623" / "#E53E3E" / "#888"
    # Optional / defaulted fields
    has_map:          bool          = False
    seed_overlay_note: str          = ""   # shown when seed centreline unavailable
    seed_centreline:  List[MapPoint] = field(default_factory=list)  # Group 17T overlay
    # Group 20A — segment highlight band (progress 0.0–1.0, normalised)
    highlight_start_progress: Optional[float] = None
    highlight_end_progress:   Optional[float] = None
    # Group 21B — pit lane overlay polyline (world or screen coords)
    pit_lane_polyline: list = field(default_factory=list)  # list of (x, y) screen coords


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def _bounds_of(points: List[MapPoint]) -> Tuple[float, float, float, float]:
    if not points:
        return (0.0, 0.0, 1.0, 1.0)
    xs = [p.x for p in points]
    ys = [p.y for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _expand_bounds(
    b1: Tuple[float, float, float, float],
    b2: Tuple[float, float, float, float],
) -> Tuple[float, float, float, float]:
    return (
        min(b1[0], b2[0]),
        min(b1[1], b2[1]),
        max(b1[2], b2[2]),
        max(b1[3], b2[3]),
    )


def _confidence_color(conf: str) -> str:
    return {
        MapMatchConfidence.HIGH:    "#2EA043",
        MapMatchConfidence.MEDIUM:  "#F5A623",
        MapMatchConfidence.LOW:     "#E53E3E",
        MapMatchConfidence.UNKNOWN: "#888888",
    }.get(conf, "#888888")


def build_track_map_draw_data(
    station_map:   Optional[TrackStationMap],
    match_result:  Optional[MapMatchResult]  = None,
    telemetry_trace: Optional[List[Tuple[float, float, float]]] = None,
    seed_coordinate_map=None,   # Optional SeedCoordinateMap (Group 17T)
) -> TrackMapDrawData:
    """Convert a TrackStationMap (+ optional live match) into drawing primitives.

    Args:
        station_map:          The 1 m station map.  If None, returns an empty frame.
        match_result:         Live car position (optional).
        telemetry_trace:      List of (x, y, z) world positions to draw as a lap
                              trace overlay (optional).
        seed_coordinate_map:  SeedCoordinateMap for seed overlay layer (optional).

    Returns:
        TrackMapDrawData with world-space coordinates.  Call project_to_screen()
        to convert to pixel coordinates before handing to QPainter.
    """
    empty = TrackMapDrawData(
        centreline=[], width_left=[], width_right=[],
        start_finish=None, corner_labels=[], car_dot=None,
        telemetry_trace=[], bounds=(0.0, 0.0, 1.0, 1.0),
        status_text="No track map loaded",
        confidence_color="#888888",
        has_map=False,
    )

    if station_map is None or not station_map.stations:
        return empty

    # Centreline polyline (using X, Z) — close the loop so the circuit joins
    centreline: List[MapPoint] = [
        MapPoint(s.x, s.z) for s in station_map.stations
    ]
    if len(centreline) > 1:
        centreline.append(centreline[0])

    # Width corridor edges
    width_left:  List[MapPoint] = []
    width_right: List[MapPoint] = []
    for s in station_map.stations:
        # Left edge: offset from centreline in perpendicular (left) direction
        # left direction = (cos(heading), –sin(heading)) in XZ
        lw = s.left_width_m  if s.left_width_m  > 0 else station_map.default_track_width_m / 2.0
        rw = s.right_width_m if s.right_width_m > 0 else station_map.default_track_width_m / 2.0
        left_x  =  s.x + math.cos(s.heading_rad) * lw
        left_z  =  s.z - math.sin(s.heading_rad) * lw
        right_x =  s.x - math.cos(s.heading_rad) * rw
        right_z =  s.z + math.sin(s.heading_rad) * rw
        width_left.append(MapPoint(left_x, left_z))
        width_right.append(MapPoint(right_x, right_z))

    # Start/finish marker (station 0)
    sf_pt: Optional[MapPoint] = None
    if station_map.stations:
        s0 = station_map.stations[0]
        sf_pt = MapPoint(s0.x, s0.z)

    # Corner labels
    labels: List[CornerLabel] = [
        CornerLabel(
            text            = c.corner_id,
            x               = _station_x(c.approx_station_m, station_map),
            y               = _station_z(c.approx_station_m, station_map),
            is_placeholder  = c.is_seeded_placeholder,
        )
        for c in station_map.seeded_corners
    ]

    # Car dot
    car_dot: Optional[CarDot] = None
    if match_result is not None and not match_result.is_pit_likely:
        idx = match_result.nearest_station_idx
        if idx < len(station_map.stations):
            st = station_map.stations[idx]
            car_dot = CarDot(
                x          = st.x + match_result.lateral_offset_m * math.cos(st.heading_rad),
                y          = st.z - match_result.lateral_offset_m * math.sin(st.heading_rad),
                confidence = match_result.confidence,
                is_valid   = match_result.confidence != MapMatchConfidence.UNKNOWN,
            )

    # Telemetry trace
    trace: List[MapPoint] = []
    if telemetry_trace:
        trace = [MapPoint(x, z) for (x, _y, z) in telemetry_trace]

    # Bounds (include all geometry)
    bounds = _bounds_of(centreline)
    if trace:
        bounds = _expand_bounds(bounds, _bounds_of(trace))
    if car_dot:
        dot_b = (car_dot.x - 5, car_dot.y - 5, car_dot.x + 5, car_dot.y + 5)
        bounds = _expand_bounds(bounds, dot_b)

    # Status and confidence colour
    conf_color = "#888888"
    if match_result is not None:
        conf_color = _confidence_color(match_result.confidence)

    # Status text
    loc  = station_map.track_location_id.replace("_", " ").title()
    lay  = station_map.layout_id.split("__")[-1].replace("_", " ").title()
    stat = f"{loc} — {lay} | {len(station_map.stations)} stations"
    if station_map.seeded_corners:
        n_ph = sum(1 for c in station_map.seeded_corners if c.is_seeded_placeholder)
        nc   = len(station_map.seeded_corners)
        stat += f" | {nc} corners"
        if n_ph:
            stat += f" ({n_ph} estimated)"
    if match_result and not match_result.is_pit_likely:
        stat += (
            f" | {match_result.station_m:.0f} m"
            f" | {match_result.corner_id or '—'}"
            f" | {match_result.confidence}"
        )

    # Seed coordinate map overlay (Group 17T)
    seed_cl: List[MapPoint] = []
    if seed_coordinate_map is not None:
        seed_cl = [MapPoint(s.x, s.y) for s in seed_coordinate_map.stations]
        if seed_cl:
            bounds = _expand_bounds(bounds, _bounds_of(seed_cl))

    # DEF-17R-002/003: note when seed centreline/positions are unavailable
    seed_pos_ok = getattr(station_map, "seed_corner_positions_available", False)
    if seed_cl:
        seed_overlay_note = ""  # seed map present — no note needed
    elif seed_pos_ok:
        seed_overlay_note = ""
    else:
        seed_overlay_note = (
            "Seed coordinate map unavailable — showing telemetry-derived model only. "
            "Corner labels are curvature peaks, not verified positions."
        )

    # Group 21B — pit lane polyline
    from data.track_station_map import PitLaneBoundary as _PitLaneBoundary
    pit_lane_polyline: List[MapPoint] = []
    if isinstance(station_map.pit_lane, _PitLaneBoundary):
        pl = station_map.pit_lane
        entry_m = pl.entry_station_m
        exit_m  = pl.exit_station_m
        wrap    = entry_m > exit_m  # pit lane crosses the lap seam
        for s in station_map.stations:
            sm_val = s.station_m
            if wrap:
                in_pit = sm_val >= entry_m or sm_val <= exit_m
            else:
                in_pit = entry_m <= sm_val <= exit_m
            if in_pit:
                pit_lane_polyline.append(MapPoint(s.x, s.z))

    return TrackMapDrawData(
        centreline       = centreline,
        width_left       = width_left,
        width_right      = width_right,
        seed_centreline  = seed_cl,
        start_finish     = sf_pt,
        corner_labels    = labels,
        car_dot          = car_dot,
        telemetry_trace  = trace,
        bounds           = bounds,
        status_text      = stat,
        confidence_color = conf_color,
        has_map          = True,
        seed_overlay_note= seed_overlay_note,
        pit_lane_polyline= pit_lane_polyline,
    )


def _station_x(station_m: float, sm: TrackStationMap) -> float:
    """Return world X of the station nearest to station_m."""
    s = sm.get_station_at(station_m)
    return s.x if s else 0.0


def _station_z(station_m: float, sm: TrackStationMap) -> float:
    """Return world Z of the station nearest to station_m."""
    s = sm.get_station_at(station_m)
    return s.z if s else 0.0


# ---------------------------------------------------------------------------
# Screen projection
# ---------------------------------------------------------------------------

# Projection cache.  project_to_screen() reallocates every polyline point on
# every repaint (many times a second during a race).  The heavy geometry only
# changes when a *new* TrackMapDrawData object is built; within one object's
# lifetime the live path mutates just car_dot (and the highlight scalars) in
# place.  So we cache the projected result keyed on the source object's identity
# + canvas size and, on a hit, reproject only the single car-dot point.
#
# All callers run on the Qt GUI thread (telemetry arrives via a queued signal),
# so no lock is needed.  A strong ref to the source object is held in the entry
# so its id() cannot be reused while cached; the `source is draw_data` check
# defends against reuse after eviction anyway.
_PROJ_CACHE_MAX = 8
_PROJ_CACHE: "OrderedDict[tuple, _ProjEntry]" = OrderedDict()
_ProjEntry = namedtuple("_ProjEntry", "source params result")


def _project_point(x: float, y: float, params: tuple) -> MapPoint:
    off_x, off_y, scale, min_x, max_y = params
    return MapPoint(off_x + (x - min_x) * scale, off_y + (max_y - y) * scale)


def _project_car_dot(cd, params: tuple):
    if cd is None:
        return None
    pp = _project_point(cd.x, cd.y, params)
    return CarDot(x=pp.x, y=pp.y, confidence=cd.confidence, is_valid=cd.is_valid)


def project_to_screen(
    draw_data:  TrackMapDrawData,
    canvas_w:   int,
    canvas_h:   int,
    margin:     int = 20,
) -> TrackMapDrawData:
    """Return a new TrackMapDrawData with all coordinates converted to pixels.

    The map is scaled uniformly to fit within the canvas (preserving aspect
    ratio) and centred.  The Y axis may be reflected so that increasing Z
    appears at the top of the screen (as is conventional for top-down maps).
    """
    min_x, min_y, max_x, max_y = draw_data.bounds
    span_x = max_x - min_x
    span_y = max_y - min_y

    if span_x < 1e-3 or span_y < 1e-3:
        return draw_data   # degenerate — return as-is

    cache_key = (id(draw_data), canvas_w, canvas_h, margin)
    cached = _PROJ_CACHE.get(cache_key)
    if cached is not None and cached.source is draw_data:
        # Geometry unchanged for this object; only the live car dot (mutated in
        # place each packet) and the highlight scalars can differ frame-to-frame.
        result = cached.result
        result.car_dot = _project_car_dot(draw_data.car_dot, cached.params)
        result.highlight_start_progress = draw_data.highlight_start_progress
        result.highlight_end_progress   = draw_data.highlight_end_progress
        _PROJ_CACHE.move_to_end(cache_key)
        return result

    avail_w = canvas_w - 2 * margin
    avail_h = canvas_h - 2 * margin
    scale   = min(avail_w / span_x, avail_h / span_y)

    # Centre offset
    off_x = margin + (avail_w - span_x * scale) / 2.0
    off_y = margin + (avail_h - span_y * scale) / 2.0

    def proj(p: MapPoint) -> MapPoint:
        # Reflect Y so higher Z appears higher on screen
        return MapPoint(
            x = off_x + (p.x - min_x) * scale,
            y = off_y + (max_y - p.y) * scale,
        )

    def proj_list(pts: List[MapPoint]) -> List[MapPoint]:
        return [proj(p) for p in pts]

    car_dot = None
    if draw_data.car_dot:
        pp = proj(MapPoint(draw_data.car_dot.x, draw_data.car_dot.y))
        car_dot = CarDot(
            x          = pp.x,
            y          = pp.y,
            confidence = draw_data.car_dot.confidence,
            is_valid   = draw_data.car_dot.is_valid,
        )

    sf = None
    if draw_data.start_finish:
        sf = proj(draw_data.start_finish)

    labels: List[CornerLabel] = []
    for lbl in draw_data.corner_labels:
        pp = proj(MapPoint(lbl.x, lbl.y))
        labels.append(CornerLabel(
            text           = lbl.text,
            x              = pp.x,
            y              = pp.y,
            is_placeholder = lbl.is_placeholder,
        ))

    result = TrackMapDrawData(
        centreline       = proj_list(draw_data.centreline),
        width_left       = proj_list(draw_data.width_left),
        width_right      = proj_list(draw_data.width_right),
        seed_centreline  = proj_list(draw_data.seed_centreline),
        start_finish     = sf,
        corner_labels    = labels,
        car_dot          = car_dot,
        telemetry_trace  = proj_list(draw_data.telemetry_trace),
        bounds           = (0.0, 0.0, float(canvas_w), float(canvas_h)),
        status_text      = draw_data.status_text,
        confidence_color = draw_data.confidence_color,
        has_map          = draw_data.has_map,
        seed_overlay_note              = draw_data.seed_overlay_note,
        highlight_start_progress       = draw_data.highlight_start_progress,
        highlight_end_progress         = draw_data.highlight_end_progress,
        pit_lane_polyline              = proj_list(draw_data.pit_lane_polyline),
    )

    _PROJ_CACHE[cache_key] = _ProjEntry(
        source=draw_data,
        params=(off_x, off_y, scale, min_x, max_y),
        result=result,
    )
    while len(_PROJ_CACHE) > _PROJ_CACHE_MAX:
        _PROJ_CACHE.popitem(last=False)   # evict least-recently-used
    return result
