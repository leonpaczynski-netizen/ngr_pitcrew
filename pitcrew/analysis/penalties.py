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

### What this shape is NOT, and what is done about each (critic pass 6)

The shape above is a *hard brake at speed where the model says nothing is
braked for*. Three other things make that shape, and none of them is a
penalty. Left alone, each one reached the driver as **"Penalty served. About
0.3 seconds."** - a flat assertion, at medium confidence, under a helmet.

1. **An avoidance stab** - lifting hard behind a spinning car on a straight.
   Nothing in the feed distinguishes it, and nothing here pretends to: the
   call goes out LOW and `Call.spoken()` ends it "Unconfirmed." Every caller
   that speaks it must keep it that way. The *lap* still leaves the pace and
   burn populations, and that half needs no hedge - whatever caused it, a lap
   with a full-brake-to-a-crawl in it is not evidence of pace.
2. **A wet brake taken early** for a corner the model does contain, beginning
   further back than `APPROACH_M`. Every frame this detector was calibrated
   against is dry, and the app cannot read that it is raining - the
   hygrometer reader was struck for exactly that reason. So the controller
   does not run the detector at all where the event's own record says the
   session may be wet, and the lap's `penalties_served` stays `None` rather
   than `0`.
3. **A corner missing from the model.** Every corner model on file is
   `auto-segment`, so this is the one that would repeat: the same brake, at
   the same place, on every lap of the race. It has a signature a served
   penalty does not - a penalty is served on a lap, a corner is there on all
   of them - and `RoadNotPenalty` below is that test. Refusing every
   auto-segment model instead, which is the obvious guard, would refuse every
   circuit this app has ever seen and delete the feature; refusing every
   repeat would refuse the second of two real ones (Daytona, 4 Sep: sessions
   121, 124 and 125 each carry two, on laps 3 and 6, 2 and 6, and 6 and 8 -
   never consecutive). Two CONSECUTIVE laps at one place is the road.
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
# Two flags this far apart round the lap are the same stretch of road. The
# eight on file at Daytona - the six the driver named in the 4 Sep A/B runs
# plus two more in that evening's stint, all the same signature at the same
# place - span 5,194-5,218 m, 24 m, because the brake is picked up wherever
# the car happens to be. 150 m holds that and is still far narrower than the
# distance between any two corners in any model on file.
SAME_PLACE_M = 150.0


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


class RoadNotPenalty:
    """Which flagged places are a corner the model is missing. One session.

    Item 3 of the module docstring. A served penalty happens on a lap; a
    corner is there on every lap, so a place flagged on two CONSECUTIVE laps
    is the road. When that happens the place is retired for the rest of the
    session and the earlier lap is handed back - it was struck on a reading
    this has just withdrawn, which is CLAUDE.md rule 10 the right way round:
    the guard can retire its own reference.

    **What it costs, stated.** The first lap of a missing corner is still
    flagged and still spoken, once, at LOW with "Unconfirmed." on the end.
    There is no way to recognise the shape from one lap, and refusing every
    first sighting would refuse every real penalty as well - they arrive
    exactly once too. One hedged sentence a race is the price of not being
    silent about the eight that were real.

    **CLAUDE.md rule 11.** One instance per session; the controller keys it
    on the session id beside `_corner_windows_cache` for the same reason.
    """

    def __init__(self, same_place_m: float = SAME_PLACE_M) -> None:
        self._same_place_m = float(same_place_m)
        # place (metres round the lap) -> the last lap it was flagged on
        self._seen: dict[float, int] = {}
        # places the road explains: nothing here is a penalty again
        self._retired: list[float] = []

    def _near(self, places, at_m: float):
        for place in places:
            if abs(place - at_m) <= self._same_place_m:
                return place
        return None

    def retired(self) -> tuple[float, ...]:
        """The places this session has decided are corners, for the log."""
        return tuple(self._retired)

    def filter(self, lap_num: int, found) -> tuple[list, list[int]]:
        """`(the ones that are still penalties, the laps to hand back)`.

        `found` is one lap's `Penalty` list. The returned laps are ones a
        previous call kept and this one withdraws - pass each to
        `RaceCoordinator.forget_penalty`.
        """
        kept, give_back = [], []
        for penalty in found or ():
            at_m = float(penalty.at_m)
            if self._near(self._retired, at_m) is not None:
                continue                # this place is a corner, not a penalty
            place = self._near(self._seen, at_m)
            if place is not None and self._seen[place] == int(lap_num) - 1:
                # Two laps running at one place: the road. Retire it, and
                # withdraw the lap it was first seen on.
                self._retired.append(place)
                give_back.append(int(lap_num) - 1)
                self._seen.pop(place, None)
                continue
            if place is None:
                place = at_m
            self._seen[place] = int(lap_num)
            kept.append(penalty)
        return kept, give_back
