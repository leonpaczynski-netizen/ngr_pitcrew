"""Where a circuit's straights are, derived from the laps he has driven there.

**Why this exists.** At Bathurst on 14 Sep 2026 George's lines ran into the
Hell Corner braking. The live detector (`race/straight.py`) knows only that the
car has been straight and flat for a while - not how much straight is left - so
without a circuit model the voice waits for 4 s of held straight and caps a
data line at 2.8 s. Measured over that race, that finishes inside the straight
63% of the time, and half of Bathurst's straights had 1.5 s or less left at the
detector's edge. What closes the gap is knowing where the straight ENDS.

**GT7 gives no track ID and no lap distance** (CLAUDE.md 3.3.2), so this is a
`track-map` in the app's own sense: stable windows of lap distance, keyed by the
driver-selected circuit, derived from his own stored laps and labelled
`[DERIVED]` with the lap count and sessions behind every window (rules 4, 5).

### The axis - the one the live ruler produces

`lap_distance_m` in `lap_frames` is speed integrated from the line at 60 Hz by
`telemetry/recorder.py`; `race/lap_ruler.py` is the same integration live. Both
come out a smooth 0.2-0.9% short of the catalogue length (`analysis/distance`),
so each lap is put on a common axis by its OWN length - the same correction
`lap_sectors.read` makes with fractions - and the model's `lap_length_m` is the
median integrated length of the laps it was built from. Live, the ruler's last
closed lap supplies the same per-lap scale (`race/straight.StraightsModel`).

Refused before pooling, each for a stated reason:

* **a teleport** - one frame in which the car moved more than 25 m
  (`distance.teleports`): every distance after it is on a different axis;
* **a length off the pooled median by more than 2%** - a swallowed crossing,
  a fragment, a pit-lane lap;
* **slower than 107% of the median lap** - not race pace, so its seconds do
  not describe the straight George will be timing;
* **no distance channel** at all.

### What a straight is

The live detector's rule - throttle at least 90%, lateral load at most 0.3 g -
plus **no brake**, held at least 2 s. Two differences, both deliberate:

* **Upshift dips up to 0.5 s are bridged.** A Gr.3 upshift drops the throttle
  to zero for six frames (0.1 s) and splits every Bathurst straight at every
  gear - Mountain Straight at 4th, 5th and 6th; the road did not change and
  neither did how long the driver can listen. **Only the throttle may dip:**
  a gap in which the lateral load or the brake went over the gate is a kink
  or a corner exit and is never bridged, however short.
* **Pooled on a circular axis.** Bathurst's pit straight runs across the line,
  so a window may end past `lap_length_m` and the live lookup wraps.

A window is pooled where **more than half** of the laps are on a straight
(coverage on a 5 m grid). Its start is the median of the contributing runs'
starts; **its end is their lower quartile** - on three laps in four the
straight lasts at least that far - which is the conservative side for a voice
that must finish before it.

### Gates - what is stored, and what is only reported

A pooled window is stored only if it passes `gate`: at least `MIN_LAPS` laps
contribute, and its end is a place - the interquartile range of where the
straight ended is at most `MAX_END_SPREAD_M`. A model needs `MIN_LAPS` clean
laps. The numbers, and what they were measured against, are beside the
constants. A window that fails is left out and listed in `Derived.dropped`
with its reason and lap count.

**Leaving a window out is not neutral live.** Where a model exists and the
ruler is trusted, `race/straight.StraightsModel.remaining_s` reads a place
with no stored window as 0.0 - no room - not as unknown. A dropped straight is
therefore one nothing is volunteered on, which is the conservative side, and
the report says which.

**Yas Marina, the case that set the spread gate** (15 Sep 2026, 25 laps,
sessions 11-44, one car). The back straight (1619-2214 m, 12 s) ended
anywhere from 1924 to 2416 m - IQR 189 m, 2.6 s at 260 km/h. Twelve laps ran
to the braking at 2369-2416 m; thirteen ended earlier, each at the first frame
where the derived lateral load crossed 0.3 g (peaks 0.31-0.40) along the
flat-out curve. **Not two lines:** at 1700-2300 m the early-ending laps sit
within about 1 m of the others' line (median offset -1.2 to +0.6 m, ranges
overlapping), in the same sessions (41, 43, 44 carry both), so there is no
variant to split off. **Not a corner cut** for the same reason. **Not kept:**
its end is not a place on the road but where a 0.3 g reading first happened,
and its spread is five times the live fit margin. Dropped, with the second
straight (IQR 52 m: its ends fall in two clusters, 3221-3277 m and 3300-3369
m, both at a lateral-load crossing); the third is stored.

### Braking zones

Heavy braking - brake at least 50% for 0.2 s - pooled the same way, entry at
the lower quartile of the contributing laps' starts. A window's usable end is
the earlier of its own end and the next braking entry, so nothing is started
that would overrun into one.
"""
from __future__ import annotations

import bisect
import statistics
from dataclasses import dataclass, field

from pitcrew.analysis.distance import teleports

SAMPLE_HZ = 60.0

# The live detector's thresholds (`race/straight.py`), restated rather than
# imported so this module stays importable without the race layer - and
# checked equal by a test, so the two cannot drift.
THROTTLE_PCT = 90.0
MAX_LATERAL_G = 0.3
MIN_HELD_S = 2.0
# "No braking": the pedal is not being pressed. Above the load-cell's
# resting noise, below any real application.
MAX_BRAKE_PCT = 5.0
# An upshift, not a corner. See the module docstring.
BRIDGE_S = 0.5

# Heavy braking, and how long it has to last to be a braking zone rather than
# a dab.
HEAVY_BRAKE_PCT = 50.0
MIN_BRAKE_S = 0.2

# Pooling.
GRID_M = 5.0
PRESENCE = 0.5          # strictly more than this fraction of laps
END_QUANTILE = 0.25

# **The gates** (15 Sep 2026). A window that fails one is reported and left
# out of the model, never stored; see the module docstring's "Gates".
#
# Clean laps a model is pooled from, and laps a stored window has to be on.
# Measured by deriving gated models from n laps drawn at random from six
# circuits' full pools (Monza 158, Daytona 138, Sardegna 109, Spa 60, Watkins
# 61, Red Bull Ring 49 laps; 20 draws each) and comparing every window stored
# against the model the full pool stores:
#
#   n    stored  claims past the full pool's end by > 0.5 s  phantom windows
#   5      352     3                                            8.2%
#   8      459     1                                            7.6%
#   10     471     0                                            5.3%
#   15     478     0                                            3.1%
#   20-25  989     0                                            3.6%
#
# 0.5 s is the live gate's `FIT_MARGIN_S`: an end placed further out than
# that is a clip the margin no longer protects. From 10 laps no draw stored
# one; below it they appear. Phantoms (a window the full pool does not hold)
# settle at the 3-4% of windows that sit near half presence. 10 is one
# practice session, and every circuit on file clears it (Suzuka, the
# fewest, has 16).
MIN_LAPS = 10
# How far a window's end may wander lap to lap - the interquartile range of
# where its straight ended - and still be a place on the road. Measured on the
# twelve circuits on file (15 Sep 2026), pooled two ways: every clean lap (57
# windows) and the most recent 80, as `straight_refresh` pools them (56). The
# windows whose runs end at one landmark - a braking point, or one corner's
# lateral load - on at least three laps in four spread 4-34 m. The ten that
# spread 48-412 m each end in TWO places on a quarter of the laps or more: a
# lateral load crossing the 0.3 g rule along a flat-out curve or a kink on
# some laps, the braking point or the corner itself on the rest (Yas Marina's
# back straight, Road Atlanta's, Watkins Glen's last, the Bathurst pit
# straight, Daytona's first on the recent laps). Their lower-quartile end is
# not a landmark but wherever that mix put it. Nothing on file falls between
# 34 and 48 m; 40 m is 0.72 s at 200 km/h.
MAX_END_SPREAD_M = 40.0
LAP_LENGTH_TOLERANCE = 0.02
PACE_RATIO = 1.07
PROFILE_POINTS = 11

SOURCE = "derived-laps"
TAG = "[DERIVED]"


@dataclass
class LapInput:
    """One stored lap, decoded."""
    session_id: int
    lap_num: int
    lap_time_ms: int
    frames: list
    sample_hz: float = SAMPLE_HZ
    car_name: str | None = None
    # Whether the car jumped, when the loader already knows - it read the
    # position channels and dropped them to keep 80 laps in memory. None:
    # `select` looks for itself.
    teleported: bool | None = None


@dataclass
class _Lap:
    source: LapInput
    distance: list[float]       # on the model axis, per frame
    length_m: float
    hz: float
    unwrapped: tuple | None = None


@dataclass
class Derived:
    """The model and the account of how it was reached."""
    circuit_key: str
    model: dict | None
    laps_used: int
    refused: dict[str, int] = field(default_factory=dict)
    reason: str | None = None
    # Windows present on most laps that failed `gate`: reported, never stored.
    dropped: list[dict] = field(default_factory=list)


# ----------------------------------------------------------- per-lap runs

def _bridged(flags: list[bool], bridge: int,
             allowed: list[bool] | None = None) -> list[bool]:
    """Close gaps of up to `bridge` frames between two True runs - only where
    every frame of the gap is `allowed`, when that is given."""
    out = list(flags)
    n = len(flags)
    i = 0
    while i < n:
        if out[i]:
            i += 1
            continue
        j = i
        while j < n and not flags[j]:
            j += 1
        if (0 < i and j < n and j - i <= bridge
                and (allowed is None or all(allowed[i:j]))):
            for k in range(i, j):
                out[k] = True
        i = j
    return out


def _only_the_throttle_dipped(frame: dict) -> bool:
    """An upshift, and nothing else: the car is still straight and unbraked.

    A gap where the lateral load went over the gate is a kink or a corner
    exit - 1.25 g for a quarter second at Bathurst's Forrest's Elbow exit -
    and is never bridged, however short.
    """
    g = frame.get("lat_g")
    brake = frame.get("brake_pct")
    return (g is not None and abs(g) <= MAX_LATERAL_G
            and (brake is None or brake <= MAX_BRAKE_PCT))


def bridged_listenable(frames: list[dict], hz: float = SAMPLE_HZ) -> list[bool]:
    """Per frame: on a straight, with upshift dips of up to `BRIDGE_S` closed."""
    return _bridged([listenable(f) for f in frames], int(BRIDGE_S * hz),
                    [_only_the_throttle_dipped(f) for f in frames])


def _runs(flags: list[bool]) -> list[tuple[int, int]]:
    out, start = [], None
    for index, flag in enumerate(flags):
        if flag and start is None:
            start = index
        elif not flag and start is not None:
            out.append((start, index))
            start = None
    if start is not None:
        out.append((start, len(flags)))
    return out


def listenable(frame: dict) -> bool:
    """The live detector's test on one stored frame, plus no brake."""
    throttle = frame.get("throttle_pct")
    g = frame.get("lat_g")
    brake = frame.get("brake_pct")
    return (throttle is not None and throttle >= THROTTLE_PCT
            and g is not None and abs(g) <= MAX_LATERAL_G
            and (brake is None or brake <= MAX_BRAKE_PCT))


def straight_runs(frames: list[dict], hz: float = SAMPLE_HZ,
                  ) -> list[tuple[int, int]]:
    """Every straight in one lap as frame ranges `(start, end)`, end exclusive.

    A run that reaches the end of the lap and one that begins it are the same
    stretch of road either side of the line, so they are joined into a single
    wrapped run whose end index is `len(frames) + k` and judged on their
    combined length.
    """
    n = len(frames)
    if not n:
        return []
    runs = _runs(bridged_listenable(frames, hz))
    if (len(runs) >= 2 and runs[0][0] == 0 and runs[-1][1] == n):
        head = runs.pop(0)
        tail = runs.pop()
        runs.append((tail[0], n + head[1]))
    minimum = MIN_HELD_S * hz
    return [(a, b) for a, b in runs if b - a >= minimum]


def braking_runs(frames: list[dict], hz: float = SAMPLE_HZ,
                 ) -> list[tuple[int, int]]:
    flags = [(f.get("brake_pct") or 0.0) >= HEAVY_BRAKE_PCT for f in frames]
    flags = _bridged(flags, int(MIN_BRAKE_S * hz))
    minimum = MIN_BRAKE_S * hz
    return [(a, b) for a, b in _runs(flags) if b - a >= minimum]


# ------------------------------------------------------------ selection

def _length(frames: list[dict]) -> float | None:
    values = [f.get("lap_distance_m") for f in frames
              if f.get("lap_distance_m") is not None]
    return max(values) if values else None


def select(laps: list[LapInput], *, max_laps: int | None = None,
           reference_length_m: float | None = None,
           ) -> tuple[list[_Lap], dict[str, int], float | None]:
    """The laps fit to pool, on one axis, and a count of the rest by reason.

    `laps` is in the order driven. `max_laps` keeps the most recent of the
    laps that pass - after the medians are taken over all of them. With
    `reference_length_m` the 2% length test is against that length instead
    of the pooled median: after a lap-distance axis change the older laps can
    outnumber the new ones, and their median would keep the old axis.
    """
    refused: dict[str, int] = {}

    def refuse(reason: str) -> None:
        refused[reason] = refused.get(reason, 0) + 1

    candidates = []
    for lap in laps:
        if not lap.frames:
            refuse("no frames")
            continue
        length = _length(lap.frames)
        if length is None or length <= 0:
            refuse("no distance channel")
            continue
        if any(f.get("lap_distance_m") is None for f in lap.frames):
            refuse("no distance channel")
            continue
        if (lap.teleported if lap.teleported is not None
                else teleports(lap.frames).happened):
            refuse("teleport")
            continue
        if not lap.lap_time_ms or lap.lap_time_ms <= 0:
            refuse("no lap time")
            continue
        candidates.append((lap, length))
    if not candidates:
        return [], refused, None

    median_length = (reference_length_m if reference_length_m
                     else statistics.median(length for _, length in candidates))
    on_axis = [(lap, length) for lap, length in candidates
               if abs(length - median_length)
               <= LAP_LENGTH_TOLERANCE * median_length]
    for _ in range(len(candidates) - len(on_axis)):
        refuse("length off the median by more than 2%")
    if not on_axis:
        return [], refused, None
    # Pace against the laps on the axis only: after a layout or axis change
    # the old laps' times would call every new lap slow.
    median_time = statistics.median(lap.lap_time_ms for lap, _ in on_axis)
    kept = []
    for lap, length in on_axis:
        if lap.lap_time_ms > PACE_RATIO * median_time:
            refuse("slower than 107% of the median lap")
            continue
        kept.append((lap, length))
    if not kept:
        return [], refused, None
    if max_laps is not None and len(kept) > max_laps:
        refused[f"older than the most recent {max_laps}"] = len(kept) - max_laps
        kept = kept[-max_laps:]
    axis = statistics.median(length for _, length in kept)
    out = []
    for lap, length in kept:
        scale = axis / length
        out.append(_Lap(lap, [f["lap_distance_m"] * scale for f in lap.frames],
                        length, lap.sample_hz or SAMPLE_HZ))
    return out, refused, axis


# -------------------------------------------------------------- pooling

def _quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = q * (len(ordered) - 1)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _unwrapped(lap: _Lap) -> tuple[list[float], list[float]]:
    """Distance and time for a lap run twice round, so a wrapped run indexes.

    Indices past the end of the lap are the start of the same lap again, one
    lap length further on - the same road, which is all a window needs.
    Cached on the lap: the profile asks for it once per point per window.
    """
    if lap.unwrapped is None:
        n = len(lap.distance)
        length = lap.distance[-1]
        distance = lap.distance + [d + length for d in lap.distance]
        dt = 1.0 / lap.hz
        lap.unwrapped = (distance, [i * dt for i in range(2 * n)])
    return lap.unwrapped


def _segments(coverage: list[float], threshold: float) -> list[tuple[int, int]]:
    """Contiguous grid bins above `threshold`, circular: `(first, last+1)`,
    where a segment crossing the line has `last+1 > len(coverage)`."""
    n = len(coverage)
    flags = [c > threshold for c in coverage]
    if all(flags):
        return [(0, n)]
    runs = _runs(flags)
    if len(runs) >= 2 and runs[0][0] == 0 and runs[-1][1] == n:
        head = runs.pop(0)
        tail = runs.pop()
        runs.append((tail[0], n + head[1]))
    return runs


def _coverage(laps: list[_Lap], axis: float, runs_of) -> tuple[list[float], list]:
    bins = max(1, int(axis // GRID_M) + 1)
    counts = [0] * bins
    per_lap = []
    for lap in laps:
        distance, _ = _unwrapped(lap)
        spans = []
        covered = set()
        for a, b in runs_of(lap):
            start_m, end_m = distance[a], distance[b - 1]
            spans.append((a, b, start_m, end_m))
            first = int(start_m // GRID_M)
            last = int(end_m // GRID_M)
            for k in range(first, last + 1):
                covered.add(k % bins)
        for k in covered:
            counts[k] += 1
        per_lap.append(spans)
    return [c / len(laps) for c in counts], per_lap


def _overlap(a0: float, a1: float, b0: float, b1: float, axis: float) -> float:
    best = 0.0
    for shift in (-axis, 0.0, axis):
        best = max(best, min(a1, b1 + shift) - max(a0, b0 + shift))
    return best


def _time_at(distance: list[float], time: list[float],
             target: float) -> float | None:
    """When the lap reached `target` metres, interpolated. Distance is
    integrated from a speed that is never negative, so it is sorted."""
    i = bisect.bisect_left(distance, target)
    if i <= 0 or i >= len(distance):
        return None
    d0, d1 = distance[i - 1], distance[i]
    t0, t1 = time[i - 1], time[i]
    if d1 == d0:
        return t1
    return t0 + (t1 - t0) * (target - d0) / (d1 - d0)


def _pool_straights(laps: list[_Lap], axis: float) -> list[dict]:
    """Every window present on most laps, gated or not - `gate` decides."""
    coverage, per_lap = _coverage(
        laps, axis, lambda lap: straight_runs(lap.source.frames, lap.hz))
    windows = []
    for first, last in _segments(coverage, PRESENCE):
        seg0, seg1 = first * GRID_M, last * GRID_M
        members = []
        for lap, spans in zip(laps, per_lap):
            best, pick = 0.0, None
            for a, b, s0, s1 in spans:
                o = _overlap(seg0, seg1, s0, s1, axis)
                if o > best:
                    best, pick = o, (a, b, s0, s1)
            if pick is not None:
                members.append((lap, pick))
        if not members or len(members) <= PRESENCE * len(laps):
            continue
        # Starts and ends on one unwrapped axis anchored at the segment.
        starts, ends, durations, end_kph = [], [], [], []
        for lap, (a, b, s0, s1) in members:
            while s0 < seg0 - axis / 2:
                s0, s1 = s0 + axis, s1 + axis
            while s0 > seg0 + axis / 2:
                s0, s1 = s0 - axis, s1 - axis
            starts.append(s0)
            ends.append(s1)
            durations.append((b - a) / lap.hz)
            frames = lap.source.frames
            speed = frames[(b - 1) % len(frames)].get("speed_kph")
            if speed is not None:
                end_kph.append(speed)
        start_m = statistics.median(starts)
        end_m = _quantile(ends, END_QUANTILE)
        if end_m - start_m <= 0:
            windows.append({
                "start_m": round(start_m % axis, 1),
                "end_m": round(start_m % axis + (end_m - start_m), 1),
                "laps": len(members), "laps_pooled": len(laps),
                "end_spread_m": round(_quantile(ends, 0.75)
                                      - _quantile(ends, 0.25), 1),
                "empty": True})
            continue
        # How long is left from each point to `end_m`, lap by lap.
        profile = []
        for k in range(PROFILE_POINTS):
            at = start_m + (end_m - start_m) * k / (PROFILE_POINTS - 1)
            left = []
            for lap, (a, b, _s0, _s1) in members:
                distance, time = _unwrapped(lap)
                shift = 0.0
                while at + shift < distance[0]:
                    shift += axis
                t_at = _time_at(distance, time, at + shift)
                t_end = _time_at(distance, time, end_m + shift)
                if t_at is not None and t_end is not None and t_end >= t_at:
                    left.append(t_end - t_at)
            profile.append(round(statistics.median(left), 3) if left else None)
        if any(value is None for value in profile):
            profile = []
        start_norm = start_m % axis
        windows.append({
            "start_m": round(start_norm, 1),
            "end_m": round(start_norm + (end_m - start_m), 1),
            "laps": len(members),
            "laps_pooled": len(laps),
            "median_s": round(statistics.median(durations), 2),
            "p25_s": round(_quantile(durations, 0.25), 2),
            "p75_s": round(_quantile(durations, 0.75), 2),
            "spread_s": round(_quantile(durations, 0.75)
                              - _quantile(durations, 0.25), 2),
            "end_spread_m": round(_quantile(ends, 0.75)
                                  - _quantile(ends, 0.25), 1),
            "end_kph": (round(statistics.median(end_kph), 1)
                        if end_kph else None),
            "t_left_s": profile,
        })
    windows.sort(key=lambda w: w["start_m"])
    return windows


def _pool_braking(laps: list[_Lap], axis: float) -> list[dict]:
    coverage, per_lap = _coverage(
        laps, axis, lambda lap: braking_runs(lap.source.frames, lap.hz))
    zones = []
    for first, last in _segments(coverage, PRESENCE):
        seg0, seg1 = first * GRID_M, last * GRID_M
        starts, ends, peaks = [], [], []
        for lap, spans in zip(laps, per_lap):
            best, pick = 0.0, None
            for a, b, s0, s1 in spans:
                o = _overlap(seg0, seg1, s0, s1, axis) + 1e-9
                if o > best:
                    best, pick = o, (a, b, s0, s1)
            if pick is None:
                continue
            a, b, s0, s1 = pick
            while s0 < seg0 - axis / 2:
                s0, s1 = s0 + axis, s1 + axis
            while s0 > seg0 + axis / 2:
                s0, s1 = s0 - axis, s1 - axis
            starts.append(s0)
            ends.append(s1)
            frames = lap.source.frames
            peaks.append(max((frames[i % len(frames)].get("brake_pct") or 0.0)
                             for i in range(a, b)))
        if len(starts) < MIN_LAPS or len(starts) <= PRESENCE * len(laps):
            continue
        entry = _quantile(starts, END_QUANTILE)
        zones.append({
            "start_m": round(entry % axis, 1),
            "end_m": round(entry % axis + (statistics.median(ends) - entry), 1),
            "laps": len(starts),
            "peak_brake_pct": round(statistics.median(peaks), 1),
        })
    zones.sort(key=lambda z: z["start_m"])
    return zones


def _next_braking(window: dict, zones: list[dict], axis: float) -> float | None:
    """The first braking entry at or after the window's start, on its axis."""
    best = None
    for zone in zones:
        for shift in (0.0, axis):
            entry = zone["start_m"] + shift
            if entry > window["start_m"] and (best is None or entry < best):
                best = entry
    return round(best, 1) if best is not None else None


def gate(window: dict) -> str | None:
    """Why a pooled window may not be stored, or None if it may.

    See `MIN_LAPS` and `MAX_END_SPREAD_M` for the numbers and what they were
    measured against.
    """
    if window.get("empty"):
        return "its lower-quartile end comes before its start"
    if window["laps"] < MIN_LAPS:
        return f"on {window['laps']} laps, fewer than {MIN_LAPS}"
    if window["end_spread_m"] > MAX_END_SPREAD_M:
        return (f"its end wanders {window['end_spread_m']:.0f} m lap to lap "
                f"(interquartile), more than {MAX_END_SPREAD_M:.0f} m")
    return None


def describe_dropped(window: dict) -> str:
    return (f"{window['start_m']:.0f}-{window['end_m']:.0f} m on "
            f"{window['laps']}/{window['laps_pooled']} laps: {window['reason']}")


def derive(circuit_key: str, laps: list[LapInput], *,
           derived_on: str | None = None,
           max_laps: int | None = None,
           reference_length_m: float | None = None) -> Derived:
    """The straights model for one circuit, or None with the reason.

    `max_laps` keeps only the most recent laps that survived selection (the
    input is in the order driven), so a pool capped for memory is capped at
    the same count every time rather than at however many a capped load
    happened to leave. `reference_length_m` pools only laps on that axis -
    see `select`.
    """
    kept, refused, axis = select(laps, max_laps=max_laps,
                                 reference_length_m=reference_length_m)
    if not kept or axis is None:
        return Derived(circuit_key, None, 0, refused,
                       "no lap survived selection")
    if len(kept) < MIN_LAPS:
        return Derived(circuit_key, None, len(kept), refused,
                       f"{len(kept)} clean laps, fewer than {MIN_LAPS}")
    pooled = _pool_straights(kept, axis)
    dropped = []
    windows = []
    for window in pooled:
        reason = gate(window)
        if reason is None:
            windows.append(window)
        else:
            dropped.append({key: window[key] for key in (
                "start_m", "end_m", "laps", "laps_pooled", "end_spread_m")}
                | {"reason": reason})
    zones = _pool_braking(kept, axis)
    for index, window in enumerate(windows, start=1):
        window["id"] = f"S{index}"
        window["brake_m"] = _next_braking(window, zones, axis)
    for index, zone in enumerate(zones, start=1):
        zone["id"] = f"B{index}"
    sessions = sorted({lap.source.session_id for lap in kept})
    cars = sorted({lap.source.car_name for lap in kept if lap.source.car_name})
    model = {
        "model_id": circuit_key,
        "circuit_key": circuit_key,
        "version": 1,
        "source": SOURCE,
        "tag": TAG,
        "lap_length_m": round(axis, 1),
        "laps": len(kept),
        "session_ids": sessions,
        "cars": cars,
        "derived_on": derived_on,
        "rule": {
            "throttle_pct": THROTTLE_PCT, "max_lateral_g": MAX_LATERAL_G,
            "max_brake_pct": MAX_BRAKE_PCT, "min_held_s": MIN_HELD_S,
            "bridge_s": BRIDGE_S, "presence": PRESENCE,
            "end_quantile": END_QUANTILE, "heavy_brake_pct": HEAVY_BRAKE_PCT,
            "min_brake_s": MIN_BRAKE_S,
            "min_laps": MIN_LAPS, "max_end_spread_m": MAX_END_SPREAD_M,
        },
        "windows": [{"id": w["id"], **{k: v for k, v in w.items()
                                        if k != "id"}} for w in windows],
        "braking": [{"id": z["id"], **{k: v for k, v in z.items()
                                        if k != "id"}} for z in zones],
    }
    if not windows:
        return Derived(circuit_key, None, len(kept), refused,
                       "every window failed the gates" if dropped
                       else "no straight present on most laps",
                       dropped=dropped)
    return Derived(circuit_key, model, len(kept), refused, dropped=dropped)
