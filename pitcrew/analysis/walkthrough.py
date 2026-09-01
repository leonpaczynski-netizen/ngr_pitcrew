"""Talking one lap through, corner by corner, against the driver's own others.

**What this is allowed to be.** Per-lap, per-corner *input* coaching is refuted
by the driver's own data (`docs/RACE-ENGINEER-CHARTER_2026-08-23.md` §2, 307
clean laps): brake point scatters 14-37 m lap to lap and throttle-on 11-51
percentage points, so "brake ten metres later at T4" is noise wearing a number.
Nothing here says that.

What it says instead is a **description of one lap**, which is a different
claim and a measured one:

* How long this lap spent in each corner window, against the median of every
  other clean lap. Both numbers are measurements - the single lap's time is
  exact, and a median over a dozen laps is well determined - so the difference
  between them is a fact about this lap.
* Whether that difference is bigger than the driver's own scatter at that
  corner. Inside his scatter it is **not** reported as a finding, because that
  is precisely what cannot be told apart from an ordinary lap.
* What gear he was in, which is an integer and therefore the one channel with
  no measurement noise at all - see `analysis/debrief`.
* Where to look in the capture.

**The remainder is reported, never absorbed.** Corner windows do not cover a
lap: at Daytona five windows span about 600 m of a 5,700 m lap, so the corner
deltas cannot add up to the lap-time delta and must not be presented as though
they do. Whatever is left over is the straights and the transitions, and it is
printed as its own line. A decomposition that silently swallows 85% of the lap
is worse than no decomposition.

**Every lap here has passed the teleport check** (`analysis/distance`), so the
distance axis this is indexed against is good to about a metre.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from pitcrew.analysis import distance
from pitcrew.analysis.corner_model import Corner, CornerModel
from pitcrew.analysis.corners import CountedLap, _slice, length_gate

# A corner delta smaller than this fraction of the driver's own spread there is
# not reported as anything. It is what an ordinary lap looks like.
NOTABLE_SIGMA = 1.0

# Below this many other laps there is no distribution to compare against and
# the walkthrough describes the lap without judging it.
MIN_REFERENCE_LAPS = 4


@dataclass(frozen=True)
class Segment:
    """One corner on the lap being talked through."""
    corner_id: str
    corner_name: str
    apex_m: float
    seconds: float
    median_seconds: float | None
    sd_seconds: float | None
    min_kph: float
    median_min_kph: float | None
    gear: int | None
    usual_gear: int | None
    video_second: float | None = None

    @property
    def delta(self) -> float | None:
        """Seconds this lap spent here against the median. Negative is quicker."""
        if self.median_seconds is None:
            return None
        return self.seconds - self.median_seconds

    @property
    def sigma(self) -> float | None:
        """How many of the driver's own standard deviations that is."""
        if self.delta is None or not self.sd_seconds:
            return None
        return self.delta / self.sd_seconds

    @property
    def notable(self) -> bool:
        """Worth a word. Inside his own scatter, deliberately not."""
        return self.sigma is not None and abs(self.sigma) >= NOTABLE_SIGMA

    @property
    def gear_differs(self) -> bool:
        return (self.gear is not None and self.usual_gear is not None
                and self.gear != self.usual_gear)


@dataclass(frozen=True)
class Walkthrough:
    lap_num: int
    lap_time_ms: int
    reference_ms: int | None
    reference_laps: int
    segments: tuple[Segment, ...]
    video_path: str | None = None
    silences: tuple[str, ...] = ()

    @property
    def delta_ms(self) -> int | None:
        if self.reference_ms is None:
            return None
        return self.lap_time_ms - self.reference_ms

    @property
    def accounted_s(self) -> float:
        return sum(s.delta for s in self.segments if s.delta is not None)

    @property
    def unaccounted_s(self) -> float | None:
        """**The straights, and they are most of the lap.**

        Corner windows span a fraction of the road. Presenting the corner
        deltas as a decomposition of the lap without this line would credit
        the corners with time that was won or lost somewhere nobody looked.
        """
        if self.delta_ms is None:
            return None
        return self.delta_ms / 1000.0 - self.accounted_s

    @property
    def notable(self) -> list[Segment]:
        return [s for s in self.segments if s.notable]


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _sd(values: list[float]) -> float | None:
    """None below two samples, never 0.0 — see CLAUDE.md rule 3."""
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))


def _mode(values: list[int]) -> int | None:
    if not values:
        return None
    return max(set(values), key=values.count)


def _measure(lap: CountedLap, corner: Corner):
    """Seconds in the window, minimum speed, and the gear at the apex."""
    window = _slice(lap.frames, corner)
    speeds, gears = [], []
    for frame in window:
        speed = frame.get("speed_kph")
        if speed is None:
            continue
        speeds.append(speed)
        gears.append(frame.get("gear"))
    if len(speeds) < 3:
        return None
    seconds = (len(window) - 1) * lap.interval_ms / 1000.0
    at = speeds.index(min(speeds))
    return seconds, speeds[at], (gears[at] if at < len(gears) else None)


def walk(model: CornerModel, subject: tuple[CountedLap, int],
         others: list[tuple[CountedLap, int]]) -> Walkthrough:
    """Describe `subject` corner by corner against `others`.

    `others` should not contain the subject: a lap compared against a set it
    belongs to is compared partly against itself, and the effect is largest
    exactly where the sample is smallest.
    """
    lap, lap_time_ms = subject
    kept = {id(l) for l in length_gate([l for l, _ in others]).kept}
    others = [(l, ms) for l, ms in others if id(l) in kept]
    reference_ms = _median([float(ms) for _, ms in others])

    segments, silences = [], []
    for corner in model.corners:
        mine = _measure(lap, corner)
        if mine is None:
            silences.append(f"{corner.name}: this lap has no usable frames "
                            "through it")
            continue
        seconds, low, gear = mine

        times, lows, gears = [], [], []
        for other, _ in others:
            got = _measure(other, corner)
            if got is None:
                continue
            times.append(got[0])
            lows.append(got[1])
            if got[2] is not None:
                gears.append(got[2])

        if len(times) < MIN_REFERENCE_LAPS:
            silences.append(
                f"{corner.name}: {len(times)} other lap(s) to compare against, "
                f"below the {MIN_REFERENCE_LAPS} this needs — described, "
                "not judged")
            segments.append(Segment(
                corner_id=corner.id, corner_name=corner.name,
                apex_m=corner.apex_m, seconds=seconds, median_seconds=None,
                sd_seconds=None, min_kph=low, median_min_kph=None,
                gear=gear, usual_gear=None))
            continue

        segments.append(Segment(
            corner_id=corner.id, corner_name=corner.name, apex_m=corner.apex_m,
            seconds=seconds, median_seconds=_median(times),
            sd_seconds=_sd(times), min_kph=low, median_min_kph=_median(lows),
            gear=gear, usual_gear=_mode(gears)))

    return Walkthrough(
        lap_num=lap.lap, lap_time_ms=lap_time_ms,
        reference_ms=int(reference_ms) if reference_ms is not None else None,
        reference_laps=len(others), segments=tuple(segments),
        silences=tuple(silences))


# ------------------------------------------------------------- store binding

def from_store(store, event_id: int, *, lap_num: int | None = None):
    """Talk through one practice lap, defaulting to the quickest clean one.

    Returns None where there is no corner model for the circuit, or where no
    lap survives the filters — both honest states, and both quiet rather than
    an empty walkthrough that reads as "nothing to say".
    """
    from pitcrew.analysis.debrief import _sample_hz, is_clean
    from pitcrew.analysis.resolve import circuit_key
    from pitcrew.analysis.runs import classify_exclusions
    from pitcrew.analysis.session import counted_laps
    from pitcrew.export.build import event_lap_inputs
    from pitcrew.race import video_index

    event = store.get_event(event_id)
    if event is None:
        return None
    model = store.get_corner_model(circuit_key(event["track"], event["layout"]))
    if model is None:
        return None

    laps = event_lap_inputs(store, event_id, "practice")
    if not laps:
        return None
    capacity = next((lap.fuel_start for lap in laps
                     if lap.fuel_start and lap.fuel_start > 50), None)
    laps = classify_exclusions(laps, capacity)
    clean = [lap for lap in counted_laps(laps)
             if is_clean(lap.off_track_s) and lap.frames
             and not distance.teleports(lap.frames).happened]
    if not clean:
        return None

    chosen = (next((lap for lap in clean if lap.lap_num == lap_num), None)
              if lap_num is not None
              else min(clean, key=lambda lap: lap.lap_time_ms))
    if chosen is None:
        return None

    def counted(lap):
        return CountedLap(lap=lap.lap_num, frames=lap.frames,
                          setup_sheet_id=lap.setup_sheet_id,
                          sample_hz=_sample_hz(lap))

    # **The subject is held out of its own reference.** A lap compared against
    # a set it belongs to is compared partly against itself, and it drags the
    # median toward itself hardest when there are fewest laps - which is
    # exactly when the comparison is being leaned on.
    others = [(counted(lap), lap.lap_time_ms)
              for lap in clean if lap.lap_num != chosen.lap_num]
    result = walk(model, (counted(chosen), chosen.lap_time_ms), others)
    return _with_video(store, result, chosen)


def _with_video(store, result: Walkthrough, lap) -> Walkthrough:
    """Attach a timecode to every corner of the lap being talked through."""
    from pitcrew.race import video_index

    index = video_index.for_session(store, lap.session_id)
    if not index.usable or not index.path:
        return result
    stored_num = None
    seen: dict[int, int | None] = {}
    for row in store.list_laps(lap.session_id):
        key = row["lap_time_ms"]
        seen[key] = None if key in seen else row["lap_num"]
    stored_num = seen.get(lap.lap_time_ms)
    if stored_num is None:
        return result
    at_lap = index.at_lap(stored_num)
    if at_lap is None:
        return result
    start = at_lap - lap.lap_time_ms / 1000.0

    placed = []
    for segment in result.segments:
        into = video_index.seconds_into_lap(lap.frames, segment.apex_m)
        placed.append(Segment(
            **{**segment.__dict__,
               "video_second": (start + into) if into is not None else None}))
    return Walkthrough(
        lap_num=result.lap_num, lap_time_ms=result.lap_time_ms,
        reference_ms=result.reference_ms, reference_laps=result.reference_laps,
        segments=tuple(placed), video_path=index.path,
        silences=result.silences)
