"""Per-corner reference-point extraction from a lap's telemetry frames (pure).

Holistic brain, Phase 1 — the orchestration the codebase was missing: run a
completed lap's frames through a segment resolver, group them by CORNER (not raw
phase-segment), and extract the driving reference points a coach needs:

  * braking point   — road_distance where the driver first hits the brakes
  * apex/min speed  — slowest speed through the corner
  * entry / exit gear
  * throttle-on point — road_distance where the driver first gets back on power
                         (at/after the apex)
  * entry / exit speed

No Qt, no DB, no I/O. The caller supplies the frames (dicts from the batch
telemetry reader OR in-memory ``TelemetryFrame`` objects — both duck-typed), a
``frame_resolver(frame) -> (segment_id, phase)`` (build one from
``strategy.practice_capture.build_xyz_segment_resolver``), and a
``segment_corner_map`` mapping segment_id -> (turn_number, corner_name).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple


def _g(frame, key, default=0.0):
    if isinstance(frame, dict):
        v = frame.get(key, default)
    else:
        v = getattr(frame, key, default)
    return default if v is None else v


@dataclass(frozen=True)
class CornerReferencePoints:
    turn_number: Optional[int]
    corner_name: str
    segment_ids: Tuple[str, ...]
    frame_count: int
    braking_point_m: Optional[float]     # road_distance of first braking
    min_speed_kmh: float                 # apex speed
    entry_speed_kmh: float
    exit_speed_kmh: float
    entry_gear: int
    exit_gear: int
    apex_gear: int
    throttle_on_m: Optional[float]       # road_distance of throttle re-application
    max_brake: float
    max_throttle: float

    def coaching_line(self) -> str:
        loc = self.corner_name or (f"Turn {self.turn_number}" if self.turn_number else "corner")
        parts = [loc + ":"]
        if self.braking_point_m is not None:
            parts.append(f"brake ~{self.braking_point_m:.0f} m")
        parts.append(f"{self.entry_gear}→{self.exit_gear} gear")
        parts.append(f"apex {self.min_speed_kmh:.0f} km/h")
        if self.throttle_on_m is not None:
            parts.append(f"throttle ~{self.throttle_on_m:.0f} m")
        return " · ".join(parts)


def extract_lap_corner_metrics(
    frames: Sequence,
    frame_resolver: Callable[[object], Tuple[str, str]],
    segment_corner_map: Mapping[str, Tuple[Optional[int], str]],
    *,
    brake_threshold: float = 0.2,
    throttle_threshold: float = 0.5,
) -> List[CornerReferencePoints]:
    """Extract per-corner reference points for one lap.

    Frames are grouped by corner (via segment_corner_map); a corner spans its
    braking/entry/apex/exit phase-segments. Returns one record per corner the
    lap actually visited, in visit order.
    """
    if not frames:
        return []

    # Bucket frame indices by corner key, preserving first-seen order.
    order: List[Tuple[Optional[int], str]] = []
    buckets: Dict[Tuple[Optional[int], str], List[int]] = {}
    seg_ids: Dict[Tuple[Optional[int], str], List[str]] = {}
    for i, fr in enumerate(frames):
        try:
            seg_id, _phase = frame_resolver(fr)
        except Exception:
            seg_id, _phase = "", ""
        if not seg_id:
            continue
        corner = segment_corner_map.get(seg_id)
        if corner is None:
            continue
        key = (corner[0], corner[1])
        if key not in buckets:
            buckets[key] = []
            seg_ids[key] = []
            order.append(key)
        buckets[key].append(i)
        if seg_id not in seg_ids[key]:
            seg_ids[key].append(seg_id)

    out: List[CornerReferencePoints] = []
    for key in order:
        idxs = buckets[key]
        if not idxs:
            continue
        fr_list = [frames[i] for i in idxs]
        speeds = [float(_g(f, "speed_kmh", 0.0)) for f in fr_list]
        brakes = [float(_g(f, "brake", 0.0)) for f in fr_list]
        throttles = [float(_g(f, "throttle", 0.0)) for f in fr_list]
        gears = [int(_g(f, "gear", 0)) for f in fr_list]
        rds = [float(_g(f, "road_distance", 0.0)) for f in fr_list]

        # Braking point: first frame where brake crosses the threshold.
        braking_m: Optional[float] = None
        for j, b in enumerate(brakes):
            if b >= brake_threshold:
                braking_m = rds[j]
                break

        # Apex = min-speed frame.
        apex_j = min(range(len(speeds)), key=lambda k: speeds[k]) if speeds else 0

        # Throttle-on: first frame at/after the apex where throttle crosses back.
        throttle_on_m: Optional[float] = None
        for j in range(apex_j, len(throttles)):
            if throttles[j] >= throttle_threshold:
                throttle_on_m = rds[j]
                break

        out.append(CornerReferencePoints(
            turn_number=key[0],
            corner_name=key[1],
            segment_ids=tuple(seg_ids[key]),
            frame_count=len(idxs),
            braking_point_m=braking_m,
            min_speed_kmh=round(min(speeds), 1) if speeds else 0.0,
            entry_speed_kmh=round(speeds[0], 1) if speeds else 0.0,
            exit_speed_kmh=round(speeds[-1], 1) if speeds else 0.0,
            entry_gear=gears[0] if gears else 0,
            exit_gear=gears[-1] if gears else 0,
            apex_gear=gears[apex_j] if gears else 0,
            throttle_on_m=throttle_on_m,
            max_brake=round(max(brakes), 3) if brakes else 0.0,
            max_throttle=round(max(throttles), 3) if throttles else 0.0,
        ))
    return out


def build_segment_corner_map(segments: Sequence) -> Dict[str, Tuple[Optional[int], str]]:
    """From reviewed segments -> {segment_id: (turn_number, corner_name)}.

    Segments sharing a turn number collapse into one corner; when a turn number
    is absent, the display name is the corner key so phase-segments of the same
    named corner still group together.
    """
    out: Dict[str, Tuple[Optional[int], str]] = {}
    for s in (segments or []):
        sid = str(getattr(s, "segment_id", "") or "")
        if not sid:
            continue
        turn = getattr(s, "turn_number", None)
        name = getattr(s, "display_name", "") or getattr(s, "original_display_name", "")
        if not name and turn:
            name = f"Turn {turn}"
        out[sid] = (turn, str(name or sid))
    return out
