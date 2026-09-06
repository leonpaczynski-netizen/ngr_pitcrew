"""Track-limit penalties served, read off the frames.

GT7 serves a time penalty by making the driver slow to a crawl inside a
marked zone - so a served penalty is a hard brake at speed on a stretch of
road where nothing is braked for. Six laps of the Daytona A/B runs of 4 Sep
2026 carry one at about 5,200 m on the banking - full brake from 270 km/h to
about 190, lateral g near zero, no pit lane - and the app flagged none of
them, so those laps went into the pace population as driven, and the next
lap's front stretch with them.

### What is read, and what is not

* **Read:** a brake run - `BRAKE_PCT` or more, for `MIN_BRAKE_S` or longer -
  that starts above `MIN_SPEED_KPH` with the car going straight
  (`MAX_LAT_G`), and starts outside every corner's braking approach in the
  circuit's corner model. The Bus Stop brake at 3,700 m on the same laps
  starts 80-120 m before T5's `start_m` and is excluded by `APPROACH_M`.
* **Not read:** the penalty indicator on the HUD. No captured frame of one
  exists to calibrate a reader against, and a reader with no calibration
  frame is the fabricated-zero defect in a new shape (plan §9a).
* **Derived:** `lost_s`, the time given away from the brake until the car
  is back to the speed it braked from - `sum(dt * (v_entry - v) / v_entry)`
  - is a model of the penalty's cost, not a reading, and is exported under
  that heading.

A lap with no frames on file gets `None`, never zero (CLAUDE.md rule 3).
"""
from __future__ import annotations

from dataclasses import dataclass

BRAKE_PCT = 80.0
MIN_SPEED_KPH = 180.0
# Daytona's banking loads the car to about 0.3 g laterally while it is going
# straight (memory: the banking is vertical load, 1.92 g sustained, with
# lateral g near 0.05-0.3); the 4 Sep session 121 lap-3 penalty peaked at
# 0.312 and was missed at 0.30. Half a g is still well inside "not
# cornering" - the Bus Stop brake, in a straight line, peaks at 0.25, and it
# is the corner window that excludes it, not this.
MAX_LAT_G = 0.50
MIN_BRAKE_S = 0.5
# How far before a corner's `start_m` its braking zone may begin.
APPROACH_M = 250.0
# Recovery is judged over at most this long after the brake began.
MAX_RECOVERY_S = 25.0
SAMPLE_HZ = 60.0


@dataclass(frozen=True)
class Penalty:
    """One served penalty, where and what it cost."""
    at_m: float
    brake_s: float
    speed_from_kph: float
    speed_to_kph: float
    lost_s: float           # derived - see the module docstring


def _windows(corners) -> list[tuple[float, float]]:
    out = []
    for corner in corners or ():
        start = corner.get("start_m") if isinstance(corner, dict) else \
            getattr(corner, "start_m", None)
        end = corner.get("end_m") if isinstance(corner, dict) else \
            getattr(corner, "end_m", None)
        if start is None or end is None:
            continue
        out.append((float(start) - APPROACH_M, float(end)))
    return out


def _in_a_corner(at_m: float, windows) -> bool:
    return any(lo <= at_m <= hi for lo, hi in windows)


def read_columns(rows, field_names, corners, *,
                 sample_hz: float = SAMPLE_HZ) -> list[Penalty] | None:
    """From the recorder's column-array rows, while they are still in hand."""
    index = {name: position for position, name in enumerate(field_names)}
    wanted = ("lap_distance_m", "speed_kph", "brake_pct", "lat_g")
    if any(name not in index for name in wanted):
        return None
    frames = [{name: row[index[name]] for name in wanted} for row in rows]
    return read_rows(frames, corners, sample_hz=sample_hz)


def read_rows(frames, corners, *, sample_hz: float = SAMPLE_HZ
              ) -> list[Penalty] | None:
    """Every penalty served on one lap's frames, or None without frames.

    `frames` are dicts with `lap_distance_m`, `speed_kph`, `brake_pct` and
    `lat_g`; `corners` are the corner model's entries (`start_m`, `end_m`).
    An empty list is a lap with frames and no penalty; `None` is a lap the
    detector could not look at.
    """
    rows = [f for f in (frames or ())
            if f.get("lap_distance_m") is not None
            and f.get("speed_kph") is not None]
    if not rows:
        return None
    windows = _windows(corners)
    dt = 1.0 / sample_hz
    out: list[Penalty] = []
    i, n = 0, len(rows)
    while i < n:
        f = rows[i]
        if (f.get("brake_pct") or 0.0) < BRAKE_PCT:
            i += 1
            continue
        j = i
        while j < n and (rows[j].get("brake_pct") or 0.0) >= BRAKE_PCT:
            j += 1
        run = rows[i:j]
        entry = run[0]
        brake_s = len(run) * dt
        straight = all(abs(r.get("lat_g") or 0.0) <= MAX_LAT_G for r in run)
        if (brake_s >= MIN_BRAKE_S and entry["speed_kph"] >= MIN_SPEED_KPH
                and straight
                and not _in_a_corner(float(entry["lap_distance_m"]), windows)):
            v_entry = float(entry["speed_kph"])
            lost = 0.0
            k = i
            limit = i + int(MAX_RECOVERY_S * sample_hz)
            while k < n and k < limit:
                v = float(rows[k]["speed_kph"])
                if k > j and v >= v_entry:
                    break
                lost += dt * max(0.0, v_entry - v) / v_entry
                k += 1
            out.append(Penalty(at_m=float(entry["lap_distance_m"]),
                               brake_s=brake_s, speed_from_kph=v_entry,
                               speed_to_kph=float(run[-1]["speed_kph"]),
                               lost_s=lost))
        i = j
    return out
