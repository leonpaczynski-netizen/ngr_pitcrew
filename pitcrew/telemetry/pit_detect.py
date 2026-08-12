"""Finding a pit stop in the telemetry, because GT7 does not report one.

There is no pit flag, no pit-limiter bit and no pit-lane state in any packet
format. A stop has to be recognised from what the car is doing, and the three
signals available are, in descending reliability:

1. **Fuel rising.** Fuel only goes up in the pit box. This is the strongest
   signal the stream carries and it is never ambiguous.
2. **Stationary on track.** Speed at or near zero while the game reports the
   car on track and not paused.
3. **Tyre temperatures collapsing.** A tyre change swaps hot rubber for cold,
   so all four fall together and stay down. Slower and noisier than the other
   two, and the only evidence available for a **tyres-only stop** — which is
   the case that matters, because it is the one the app currently cannot see
   at all (gap register D3).

The confidence a stop carries is set by which of those fired, and it is
reported rather than averaged away. A stop seen only by the speed trace is a
weaker claim than one seen by the fuel gauge, and a measurement built on the
first should not be presented as if it rested on the second.

**This is the detector the live path needs too** (target design §8.5, and the
missing half of UAT defect D1: "box this lap" is an instruction whose execution
nothing currently confirms). It is deliberately pure — a function over a
sequence of samples — so the same code can run over a recorded capture offline
and over a live packet stream, and be tested against synthetic traces either
way.

It supersedes `telemetry/pit_state.py`, which despite its name detects nothing:
that module counts pit events it is handed, references a `RaceStateTracker`
this codebase replaced, and has no importer.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Stationary, in the units the packet reports. Not zero: the box release and
# the roll-in both pass through single-digit speeds, and a hard zero would
# clip the ends off the stop and shorten every duration measured here.
STOPPED_KPH = 2.0

# Fuel is a 32-bit float off the wire, so it dithers in the last digit even
# when nothing is happening. A rise has to clear that to count.
FUEL_RISE_L = 0.10

# All four tyres falling by this much across the stop reads as a change.
# A stationary car cools a little anyway, so this is set above idle cooling
# rather than at it.
TEMP_DROP_C = 12.0

# A stop shorter than this is the car being slow, not the car being serviced.
MIN_STOP_S = 2.0

# Above this, consecutive samples are not consecutive: the stream dropped.
# 60 Hz is one sample every ~16.7 ms, so a fifth of a second is a dozen
# missing packets and not a jitter.
MAX_SAMPLE_GAP_S = 0.20

FUEL = "fuel"           # fuel rose: certain
TEMPS = "temps"         # tyre temperatures collapsed: strong
SPEED = "speed"         # stationary only: weak


@dataclass(frozen=True)
class Sample:
    """One packet, reduced to what stop detection needs.

    A named subset rather than the packet itself, so the detector can be
    driven from a synthetic trace in a test without constructing 368 bytes of
    GT7 wire format for every frame.
    """
    t_s: float
    speed_kph: float
    fuel_l: float
    on_track: bool
    lap: int
    temps: tuple[float, float, float, float] | None = None
    road_distance_m: float | None = None
    position: int | None = None


@dataclass(frozen=True)
class Stop:
    """One detected pit stop, and what was seen."""
    start_s: float
    end_s: float
    lap: int
    fuel_before_l: float
    fuel_after_l: float
    temp_before_c: float | None
    temp_after_c: float | None
    signals: tuple[str, ...]
    samples: int
    # True when the stream had a hole inside the stop. Every duration taken
    # from this stop is then a lower bound rather than a measurement, and the
    # analysis must refuse it rather than quote it.
    gapped: bool = False
    gap_s: float = 0.0

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s

    @property
    def fuel_added_l(self) -> float:
        return max(0.0, self.fuel_after_l - self.fuel_before_l)

    @property
    def took_fuel(self) -> bool:
        return FUEL in self.signals

    @property
    def changed_tyres(self) -> bool:
        """Whether the tyres came off.

        Temperature is the only evidence GT7 gives, so a stop too short to cool
        the rubber measurably reads as no change. That is a floor on what is
        knowable, not a bug, and it is why `confidence` degrades with it.
        """
        return TEMPS in self.signals

    @property
    def confidence(self) -> str:
        if FUEL in self.signals and TEMPS in self.signals:
            return "high"
        if FUEL in self.signals or TEMPS in self.signals:
            return "medium"
        return "low"

    def describe(self) -> str:
        what = []
        if self.took_fuel:
            what.append(f"+{self.fuel_added_l:.1f} L")
        if self.changed_tyres:
            what.append("tyres")
        return (f"lap {self.lap}: {self.duration_s:.1f} s stationary"
                f"{' (' + ', '.join(what) + ')' if what else ''}"
                f", {self.confidence} confidence")


@dataclass
class _Window:
    start_s: float
    end_s: float
    lap: int
    fuel: list = field(default_factory=list)
    temps: list = field(default_factory=list)
    samples: int = 0
    gap_s: float = 0.0


def find_stops(samples, *, stopped_kph: float = STOPPED_KPH,
               min_stop_s: float = MIN_STOP_S) -> list[Stop]:
    """Every stationary period that looks like a stop, in order.

    Off-track samples end a window rather than extending it: the car being
    stationary in a gravel trap is not a pit stop, and treating it as one would
    put a fabricated constant into a file whose entire purpose is to hold
    measured ones.
    """
    windows: list[_Window] = []
    current: _Window | None = None
    previous: Sample | None = None

    for sample in samples:
        stationary = sample.speed_kph <= stopped_kph and sample.on_track
        if stationary:
            if current is None:
                current = _Window(start_s=sample.t_s, end_s=sample.t_s,
                                  lap=sample.lap)
            elif previous is not None:
                step = sample.t_s - previous.t_s
                if step > MAX_SAMPLE_GAP_S:
                    current.gap_s = max(current.gap_s, step)
            current.end_s = sample.t_s
            current.samples += 1
            current.fuel.append(sample.fuel_l)
            if sample.temps:
                current.temps.append(sum(sample.temps) / len(sample.temps))
        elif current is not None:
            windows.append(current)
            current = None
        previous = sample

    if current is not None:
        windows.append(current)

    return [stop for stop in (_classify(w, min_stop_s) for w in windows)
            if stop is not None]


def _classify(window: _Window, min_stop_s: float) -> Stop | None:
    if window.end_s - window.start_s < min_stop_s or not window.fuel:
        return None

    fuel_before, fuel_after = window.fuel[0], window.fuel[-1]
    temp_before = window.temps[0] if window.temps else None
    temp_after = window.temps[-1] if window.temps else None

    signals: list[str] = [SPEED]
    if fuel_after - fuel_before >= FUEL_RISE_L:
        signals.append(FUEL)
    if (temp_before is not None and temp_after is not None
            and temp_before - temp_after >= TEMP_DROP_C):
        signals.append(TEMPS)

    return Stop(
        start_s=window.start_s, end_s=window.end_s, lap=window.lap,
        fuel_before_l=fuel_before, fuel_after_l=fuel_after,
        temp_before_c=temp_before, temp_after_c=temp_after,
        signals=tuple(signals), samples=window.samples,
        gapped=window.gap_s > 0.0, gap_s=window.gap_s,
    )


def refuel_span(samples, stop: Stop) -> list[Sample]:
    """The samples inside a stop where fuel was actually going in.

    The refuel rate is the slope of *that* span, not of the whole stop. A stop
    is dead time, then fuelling, then more dead time, and dividing the litres
    by the full stationary duration would report a rate that is wrong by
    whatever the dead time was — which is exactly the quantity §3.4 wants
    measured separately.
    """
    inside = [s for s in samples if stop.start_s <= s.t_s <= stop.end_s]
    rising = [i for i in range(1, len(inside))
              if inside[i].fuel_l - inside[i - 1].fuel_l > 0.0]
    if not rising:
        return []
    return inside[rising[0] - 1:rising[-1] + 1]


def stream_gaps(samples, *, max_gap_s: float = MAX_SAMPLE_GAP_S) -> list[tuple]:
    """Holes in the timeline, as (from_s, to_s) pairs.

    Missing input has to read as missing. A capture with a two-second hole
    across a pit stop can still be measured, arithmetically, and the answer
    would be confidently wrong.
    """
    gaps = []
    previous = None
    for sample in samples:
        if previous is not None and sample.t_s - previous.t_s > max_gap_s:
            gaps.append((previous.t_s, sample.t_s))
        previous = sample
    return gaps
