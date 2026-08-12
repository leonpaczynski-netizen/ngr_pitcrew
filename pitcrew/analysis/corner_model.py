"""Corner identity — where the corners are, and what they are called.

GT7 sends no track ID and no corner definition, so corner identity comes from
the app. That makes it something the export has to declare
(`meta.cornerModel`), because a corner aggregate is worthless if `T3` means a
different corner next week.

The approach here is **auto-segment anchored to lap distance**: corners are
found from speed minima on a reference lap, numbered around the lap, and then
stored as lap-distance windows keyed by circuit. Later sessions at the same
circuit reuse the stored model rather than re-detecting, which is what makes
the IDs stable across sessions. Re-detecting on every session would renumber
the corners the first time the driver took a different line.

A model is only rebuilt when the circuit changes or the lap length moves by
more than a tolerance — i.e. when it is a different layout.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

from pitcrew.analysis import thresholds

SOURCE_AUTO_SEGMENT = "auto-segment"
SOURCE_TRACK_MAP = "track-map"

# Lap lengths differing by more than this are different layouts, so the stored
# windows do not apply.
LAP_LENGTH_TOLERANCE_M = 50.0


@dataclass(frozen=True)
class Corner:
    """One corner as a window of lap distance."""
    id: str          # "T1"
    name: str        # "Turn 1"
    start_m: float
    apex_m: float
    end_m: float

    def contains(self, distance_m: float) -> bool:
        return self.start_m <= distance_m <= self.end_m


@dataclass(frozen=True)
class CornerModel:
    model_id: str
    version: int
    source: str
    lap_length_m: float
    corners: tuple[Corner, ...]

    def as_meta(self) -> dict:
        """The `meta.cornerModel` object."""
        return {
            "source": self.source,
            "id": self.model_id,
            "version": self.version,
        }

    def applies_to(self, lap_length_m: float) -> bool:
        return abs(self.lap_length_m - lap_length_m) <= LAP_LENGTH_TOLERANCE_M

    def as_dict(self) -> dict:
        return {
            "model_id": self.model_id,
            "version": self.version,
            "source": self.source,
            "lap_length_m": self.lap_length_m,
            "corners": [
                {"id": c.id, "name": c.name, "start_m": c.start_m,
                 "apex_m": c.apex_m, "end_m": c.end_m}
                for c in self.corners
            ],
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "CornerModel":
        return cls(
            model_id=payload["model_id"],
            version=int(payload["version"]),
            source=payload["source"],
            lap_length_m=float(payload["lap_length_m"]),
            corners=tuple(
                Corner(c["id"], c["name"], float(c["start_m"]),
                       float(c["apex_m"]), float(c["end_m"]))
                for c in payload["corners"]
            ),
        )


def model_id_for(track: str, layout: str | None = None) -> str:
    parts = [track or "unknown"]
    if layout:
        parts.append(layout)
    joined = "-".join(parts).lower()
    return "".join(ch if ch.isalnum() else "-" for ch in joined).strip("-")


def _smooth(values: list[float], window: int) -> list[float]:
    if window <= 1 or len(values) <= window:
        return list(values)
    half = window // 2
    out = []
    for i in range(len(values)):
        lo = max(0, i - half)
        hi = min(len(values), i + half + 1)
        out.append(mean(values[lo:hi]))
    return out


def _sample_interval_ms(frames: list[dict]) -> float:
    if len(frames) < 2:
        return 16.67
    span = frames[-1]["t_ms"] - frames[0]["t_ms"]
    if span <= 0:
        return 16.67
    return span / (len(frames) - 1)


def detect_corners(frames: list[dict], model_id: str, *,
                   version: int = 1) -> CornerModel | None:
    """Segment one clean lap into corners.

    Returns None when the lap cannot be segmented — too few frames, no
    distance channel, or a speed trace flat enough that nothing qualifies as a
    corner. None means "no corner model", which the export handles by omitting
    the `corners` section, rather than by inventing one.
    """
    usable = [f for f in frames
              if f.get("lap_distance_m") is not None
              and f.get("speed_kph") is not None]
    if len(usable) < 60:
        return None

    usable.sort(key=lambda f: f["lap_distance_m"])
    distances = [f["lap_distance_m"] for f in usable]
    speeds = [f["speed_kph"] for f in usable]
    lap_length_m = distances[-1]
    if lap_length_m <= 0:
        return None

    interval_ms = _sample_interval_ms(frames)
    window = max(3, int(thresholds.SPEED_SMOOTHING_MS / interval_ms))
    smoothed = _smooth(speeds, window)

    apex_indices = _find_apexes(distances, smoothed)
    if not apex_indices:
        return None

    corners = []
    for number, index in enumerate(apex_indices, start=1):
        start_i, end_i = _corner_bounds(smoothed, index, apex_indices)
        corners.append(Corner(
            id=f"T{number}",
            name=f"Turn {number}",
            start_m=round(distances[start_i], 1),
            apex_m=round(distances[index], 1),
            end_m=round(distances[end_i], 1),
        ))

    return CornerModel(
        model_id=model_id,
        version=version,
        source=SOURCE_AUTO_SEGMENT,
        lap_length_m=round(lap_length_m, 1),
        corners=tuple(corners),
    )


def _find_apexes(distances: list[float], speeds: list[float]) -> list[int]:
    """Indices of speed minima that are prominent enough to be corners."""
    candidates: list[int] = []
    for i in range(1, len(speeds) - 1):
        if speeds[i] <= speeds[i - 1] and speeds[i] < speeds[i + 1]:
            candidates.append(i)
    if not candidates:
        return []

    # Collapse minima that are the same corner sampled twice, keeping the
    # slowest point of each cluster.
    clustered: list[int] = []
    for index in candidates:
        if clustered and (distances[index] - distances[clustered[-1]]
                          < thresholds.CORNER_MIN_SEPARATION_M):
            if speeds[index] < speeds[clustered[-1]]:
                clustered[-1] = index
            continue
        clustered.append(index)

    # A minimum is a corner only if the car accelerates away from it on both
    # sides. This is what separates a corner from a lift or a bumpy straight.
    prominent = []
    for index in clustered:
        floor = speeds[index] + thresholds.CORNER_PROMINENCE_KPH
        if _rises_to(speeds, index, floor, step=-1) and \
           _rises_to(speeds, index, floor, step=1):
            prominent.append(index)
    return prominent


def _rises_to(speeds: list[float], start: int, floor: float, step: int) -> bool:
    i = start
    while 0 <= i < len(speeds):
        if speeds[i] >= floor:
            return True
        i += step
    return False


def _corner_bounds(speeds: list[float], apex: int,
                   apexes: list[int]) -> tuple[int, int]:
    """Widen from the apex to where the car has recovered its speed.

    The window closes once speed is back up by the same margin that made this a
    corner in the first place, so entry and exit speeds mean something rather
    than being sampled from the middle of a straight.

    Bounded by the fastest point between this apex and each neighbour. That
    divider belongs to whichever corner reaches it first and to neither
    otherwise, so two windows can never overlap.
    """
    position = apexes.index(apex)
    left_limit = (_fastest_between(speeds, apexes[position - 1], apex)
                  if position > 0 else 0)
    right_limit = (_fastest_between(speeds, apex, apexes[position + 1])
                   if position + 1 < len(apexes) else len(speeds) - 1)

    recovered = speeds[apex] + thresholds.CORNER_PROMINENCE_KPH

    start = apex
    while start > left_limit and speeds[start] < recovered:
        start -= 1
    end = apex
    while end < right_limit and speeds[end] < recovered:
        end += 1
    return start, end


def _fastest_between(speeds: list[float], left: int, right: int) -> int:
    """Index of the highest speed strictly between two apexes."""
    if right - left < 2:
        return left
    span = range(left + 1, right)
    return max(span, key=lambda i: speeds[i])
