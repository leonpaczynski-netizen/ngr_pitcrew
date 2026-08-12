"""M0 — measuring the four constants the strategy model currently guesses.

Target design §11 items 1, 2 and 4, plus the pit-loss decomposition of §3.4.
None of these is published anywhere and all four are currently either typed in
by hand or hardcoded. A strategy built on them is arithmetic performed on
folklore, so this reads one recorded race and produces them with intervals and
provenance attached.

The run is three stops, in a fixed order, and the order is the method:

    A  tyres only          → the dead time and the tyre change, together
    B  fuel only, big fill → the refuel rate, and dead time separately
    C  tyres and a big fill → serial or parallel

**The algebra, because it is the whole design.** Write `D` for the fixed dead
time before anything happens, `T` for the tyre change, and `F(V) = V / r` for
fuelling `V` litres at rate `r`:

    t_A = D + T
    t_B = D + F(V_B)                    → D = t_B - F(V_B), and then T = t_A - D
    t_C = D + T + F(V_C)                if serial
    t_C = D + max(T, F(V_C))            if parallel

So both predictions are computable from A and B, and they differ by exactly

    separation = min(T, F(V_C))

That number is the entire experiment. **If the fill at C is small, `F(V_C)` is
small, the two models predict nearly the same duration, and the run cannot
answer the question it was run to answer.** Because GT7's tank is 100 L and the
MFD reads percent, the fill available at C is capped by how empty the car
arrives — which is why the run card states an arrival percentage per stop, and
why this module checks it and voids the run rather than picking a winner from
noise.

Nothing here is written into the strategy path. It emits a file; wiring it in
is Stage 1 and wants its own review.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from pitcrew.telemetry.pit_detect import (
    Sample,
    Stop,
    find_stops,
    refuel_span,
    stream_gaps,
)

# GT7's tank is 100 L for every car but karts (5 L) and EVs (0 L), so the MFD
# percentage and the telemetry litre figure are the same number. Anything else
# is a kart, an EV, or a bad parse - all three worth hearing about, none worth
# silently absorbing. This is the expected value, never a substitute for the
# one on the wire.
EXPECTED_CAPACITY_L = 100.0

# Two sample periods at 60 Hz, each end of a duration. The floor on how well
# any stationary time can be known from this stream.
TIMING_RESOLUTION_S = 2.0 / 60.0

# A fill has to buy more fuelling time than the timing noise, or the stop tells
# us nothing about which model is right. Deliberately generous: the cost of
# calling a run inconclusive is repeating it, and the cost of not doing so is a
# guess laundered into a measured constant.
MIN_SEPARATION_S = 1.5

SERIAL = "serial"
PARALLEL = "parallel"
INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class Measurement:
    """One constant, its interval, and where it came from.

    `value is None` means **absent** - no stop in this capture supports it.
    That is not the same as zero and must never be defaulted downstream, which
    is why the export writes null and says which stop was missing.
    """
    name: str
    value: float | None
    unit: str
    low: float | None = None
    high: float | None = None
    source: str = ""
    samples: int = 0
    conclusive: bool = False
    note: str = ""

    def as_dict(self) -> dict:
        return {
            "value": None if self.value is None else round(self.value, 4),
            "unit": self.unit,
            "interval": (None if self.low is None
                         else [round(self.low, 4), round(self.high, 4)]),
            "source": self.source or None,
            "samples": self.samples,
            "conclusive": self.conclusive,
            "note": self.note,
        }


@dataclass
class M0Result:
    measurements: dict[str, Measurement] = field(default_factory=dict)
    stops: list[Stop] = field(default_factory=list)
    verdict: str = INCONCLUSIVE
    verdict_note: str = ""
    warnings: list[str] = field(default_factory=list)
    void: bool = False
    void_reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "schema": "pitcrew.m0/1",
            "void": self.void,
            "voidReasons": list(self.void_reasons),
            "serialOrParallel": {
                "verdict": self.verdict,
                "note": self.verdict_note,
            },
            "constants": {name: m.as_dict()
                          for name, m in sorted(self.measurements.items())},
            "stops": [
                {"lap": s.lap, "durationS": round(s.duration_s, 3),
                 # What the car arrived on. The run card sets an arrival
                 # threshold per stop, because the fill available is capped by
                 # how empty you turn up - and the tank is 100 L, so this
                 # figure is both litres and percent.
                 "arrivedOnL": round(s.fuel_before_l, 2),
                 "fuelAddedL": round(s.fuel_added_l, 2),
                 "tookFuel": s.took_fuel, "changedTyres": s.changed_tyres,
                 "confidence": s.confidence, "signals": list(s.signals),
                 "gapped": s.gapped}
                for s in self.stops
            ],
            "warnings": list(self.warnings),
        }

    def summary(self) -> str:
        lines = ["M0 measurement run", "=" * 60]
        if self.void:
            lines.append("RUN VOID - do not use these numbers:")
            lines += [f"  - {r}" for r in self.void_reasons]
            lines.append("")
        lines.append(f"Stops detected: {len(self.stops)}")
        for stop in self.stops:
            lines.append(f"  {stop.describe()}")
        lines.append("")
        for name, m in sorted(self.measurements.items()):
            if m.value is None:
                lines.append(f"  {name:22s} ABSENT   {m.note}")
                continue
            span = ("" if m.low is None
                    else f"  [{m.low:.3f} - {m.high:.3f}]")
            flag = "" if m.conclusive else "   (not conclusive)"
            lines.append(f"  {name:22s} {m.value:8.3f} {m.unit}{span}{flag}")
            if m.note:
                lines.append(f"  {'':22s}   {m.note}")
        lines += ["", f"Serial or parallel: {self.verdict.upper()}",
                  f"  {self.verdict_note}"]
        if self.warnings:
            lines += ["", "Warnings:"] + [f"  - {w}" for w in self.warnings]
        return "\n".join(lines)


# ------------------------------------------------------------------ the fit

def _slope(points: list[tuple[float, float]]) -> tuple[float, float] | None:
    """Least-squares slope and the standard error of that slope.

    The error is the scatter of the data about the line, which is what an
    interval on a measured rate should mean. Returns None below three points,
    where a standard error is not defined and quoting one would be invention.
    """
    n = len(points)
    if n < 3:
        return None
    mean_x = sum(x for x, _ in points) / n
    mean_y = sum(y for _, y in points) / n
    sxx = sum((x - mean_x) ** 2 for x, _ in points)
    if sxx <= 0:
        return None
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in points)
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    residuals = sum((y - (slope * x + intercept)) ** 2 for x, y in points)
    if n <= 2:
        return slope, 0.0
    stderr = ((residuals / (n - 2)) / sxx) ** 0.5
    return slope, stderr


# ------------------------------------------------------------- measurements

def _refuel_rate(samples: list[Sample], stop: Stop) -> Measurement:
    name = "refuelRateLps"
    if not stop.took_fuel:
        return Measurement(name, None, "L/s",
                           note="no fuel-only stop in this capture")
    if stop.gapped:
        return Measurement(
            name, None, "L/s", source=f"lap {stop.lap}",
            note=f"insufficient data - the stream dropped for "
                 f"{stop.gap_s:.2f} s inside this stop")

    span = refuel_span(samples, stop)
    fit = _slope([(s.t_s, s.fuel_l) for s in span])
    if fit is None:
        return Measurement(name, None, "L/s", source=f"lap {stop.lap}",
                           samples=len(span),
                           note="too few samples while fuel was flowing")
    slope, stderr = fit
    flow_s = span[-1].t_s - span[0].t_s

    # Floor the interval at what the instrument can resolve. A perfectly
    # linear fill - which a well-behaved stop very nearly is - drives the
    # standard error to zero, and an interval of zero width claims the rate is
    # known exactly. It is not: the ends of the flow are located to one sample
    # each at 60 Hz, so the rate cannot be known better than that.
    half = max(2 * stderr, abs(slope) * TIMING_RESOLUTION_S / flow_s
               if flow_s > 0 else 0.0)
    return Measurement(
        name, slope, "L/s", low=slope - half, high=slope + half,
        source=f"lap {stop.lap}, fuel-only stop", samples=len(span),
        conclusive=True,
        note=f"{stop.fuel_added_l:.1f} L over {flow_s:.1f} s of flow; interval "
             f"is 2 standard errors of the fitted slope, floored at the 60 Hz "
             f"timing resolution")


def _stationary(stop: Stop | None, name: str, description: str) -> Measurement:
    if stop is None:
        return Measurement(name, None, "s",
                           note=f"no {description} in this capture")
    if stop.gapped:
        return Measurement(
            name, None, "s", source=f"lap {stop.lap}",
            note=f"insufficient data - the stream dropped for "
                 f"{stop.gap_s:.2f} s inside this stop")
    return Measurement(
        name, stop.duration_s, "s",
        low=stop.duration_s - TIMING_RESOLUTION_S,
        high=stop.duration_s + TIMING_RESOLUTION_S,
        source=f"lap {stop.lap}, {description}", samples=stop.samples,
        conclusive=True,
        note="stationary time; interval is the 60 Hz sampling resolution")


def _pit_loss(samples: list[Sample], stop: Stop,
              green_lap_s: float | None) -> Measurement:
    """The lap-time cost of the stop, over and above standing still.

    **This is not the entry-line-to-exit-line measure the brief asked for, and
    the deviation is deliberate.** GT7 exposes no pit-lane state and no pit
    geometry, and locating the two lines from world coordinates needs a
    per-track pit model the app does not have. What it does have is lap
    boundaries, so this measures the lap containing the stop plus the one after
    it, against green pace, minus the stationary time.

    That makes it `dLane + dIn + dOut` from §3.4 rather than `dLane` alone -
    which is the quantity the optimiser actually wants, since the in-lap
    slow-down and out-lap warm-up are costs of stopping however they are
    labelled. It is also the one the model is missing entirely today (gap
    register A2).
    """
    name = "pitLaneDeltaS"
    if green_lap_s is None:
        return Measurement(name, None, "s",
                           note="no green laps to compare against")

    laps: dict[int, list[float]] = {}
    for s in samples:
        laps.setdefault(s.lap, []).append(s.t_s)
    in_lap, out_lap = stop.lap, stop.lap + 1
    if in_lap not in laps or out_lap not in laps:
        return Measurement(name, None, "s", source=f"lap {stop.lap}",
                           note="the out-lap is not in the capture")

    spent = ((laps[in_lap][-1] - laps[in_lap][0])
             + (laps[out_lap][-1] - laps[out_lap][0]))
    delta = spent - 2 * green_lap_s - stop.duration_s
    return Measurement(
        name, delta, "s",
        low=delta - 2 * TIMING_RESOLUTION_S, high=delta + 2 * TIMING_RESOLUTION_S,
        source=f"laps {in_lap}-{out_lap} against a {green_lap_s:.1f} s green lap",
        samples=len(laps[in_lap]) + len(laps[out_lap]), conclusive=True,
        note="transit plus in-lap and out-lap cost, stationary time removed; "
             "NOT entry-line to exit-line - GT7 exposes no pit geometry")


def _green_lap_s(samples: list[Sample], stops: list[Stop]) -> float | None:
    """Median duration of the laps that had no stop in them or after them."""
    touched = set()
    for stop in stops:
        touched.update((stop.lap, stop.lap + 1))
    laps: dict[int, list[float]] = {}
    for s in samples:
        laps.setdefault(s.lap, []).append(s.t_s)
    clean = sorted(times[-1] - times[0]
                   for lap, times in laps.items()
                   if lap not in touched and len(times) > 1)
    # Drop the first and last: the capture starts and ends mid-lap, so their
    # durations are artefacts of when the recorder was switched on.
    interior = clean[1:-1] if len(clean) > 3 else clean
    if not interior:
        return None
    return interior[len(interior) // 2]


# --------------------------------------------------------------- the verdict

def _verdict(result: M0Result, tyres_only: Stop | None, fuel_only: Stop | None,
             both: Stop | None) -> None:
    if tyres_only is None or fuel_only is None or both is None:
        missing = [n for n, s in (("tyres-only", tyres_only),
                                  ("fuel-only", fuel_only),
                                  ("tyres-and-fuel", both)) if s is None]
        result.verdict = INCONCLUSIVE
        result.verdict_note = (
            f"the run needs all three stops; missing: {', '.join(missing)}")
        return

    rate = result.measurements["refuelRateLps"]
    if rate.value is None or rate.value <= 0:
        result.verdict = INCONCLUSIVE
        result.verdict_note = ("no refuel rate, so neither model can be "
                               "evaluated")
        return

    t_a, t_b, t_c = (tyres_only.duration_s, fuel_only.duration_s,
                     both.duration_s)
    f_b = fuel_only.fuel_added_l / rate.value
    f_c = both.fuel_added_l / rate.value
    dead = t_b - f_b
    tyres = t_a - dead

    serial_pred = dead + tyres + f_c
    parallel_pred = dead + max(tyres, f_c)
    separation = min(tyres, f_c)

    result.measurements["pitDeadTimeS"] = Measurement(
        "pitDeadTimeS", dead, "s",
        low=dead - 2 * TIMING_RESOLUTION_S, high=dead + 2 * TIMING_RESOLUTION_S,
        source=f"lap {fuel_only.lap} stationary time minus fuelling time",
        samples=fuel_only.samples, conclusive=dead > 0,
        note="derived: t_B - V_B/r" if dead > 0 else
             "negative, so the rate or the stop boundaries are wrong")
    result.measurements["tyreChangeS"] = Measurement(
        "tyreChangeS", tyres, "s",
        low=tyres - 2 * TIMING_RESOLUTION_S,
        high=tyres + 2 * TIMING_RESOLUTION_S,
        source=f"lap {tyres_only.lap} stationary time minus the dead time",
        samples=tyres_only.samples, conclusive=tyres > 0,
        note="derived: t_A - D")

    if separation < MIN_SEPARATION_S:
        result.verdict = INCONCLUSIVE
        result.verdict_note = (
            f"the two models are only {separation:.2f} s apart, under the "
            f"{MIN_SEPARATION_S:.1f} s this run can resolve. "
            f"Tyre change {tyres:.1f} s, fuelling at C {f_c:.1f} s "
            f"({both.fuel_added_l:.0f} L at {rate.value:.2f} L/s). "
            f"**Repeat with a larger fill at stop C** - arrive emptier so "
            f"there is room for it.")
        return

    serial_err = abs(t_c - serial_pred)
    parallel_err = abs(t_c - parallel_pred)
    winner = SERIAL if serial_err < parallel_err else PARALLEL
    margin = abs(serial_err - parallel_err)

    if min(serial_err, parallel_err) > separation:
        result.verdict = INCONCLUSIVE
        result.verdict_note = (
            f"neither model fits: C took {t_c:.1f} s against {serial_pred:.1f} s "
            f"serial and {parallel_pred:.1f} s parallel, and the closer of "
            f"those is out by {min(serial_err, parallel_err):.1f} s - more "
            f"than the {separation:.1f} s that separates the models. Something "
            f"other than tyres and fuel is in this stop.")
        return

    result.verdict = winner
    result.verdict_note = (
        f"C took {t_c:.2f} s. Serial predicts {serial_pred:.2f} s "
        f"(out by {serial_err:.2f}), parallel {parallel_pred:.2f} s "
        f"(out by {parallel_err:.2f}). The models are {separation:.2f} s apart "
        f"and the winner is ahead by {margin:.2f} s.")


# ------------------------------------------------------------------ preconditions

def _check_run(result: M0Result, samples: list[Sample], stops: list[Stop],
               capacity_l: float | None) -> None:
    if capacity_l is None:
        result.warnings.append("no fuel capacity in the capture")
    elif abs(capacity_l - EXPECTED_CAPACITY_L) > 0.5:
        result.warnings.append(
            f"tank capacity is {capacity_l:.1f} L, not the {EXPECTED_CAPACITY_L:.0f} L "
            f"GT7 reports for every car but karts (5 L) and EVs (0 L). That is a "
            f"kart, an EV, or a bad parse - check before trusting anything here")

    gaps = stream_gaps(samples)
    if gaps:
        worst = max(b - a for a, b in gaps)
        result.warnings.append(
            f"{len(gaps)} holes in the stream, worst {worst:.2f} s")

    if len(stops) < 3:
        result.void = True
        result.void_reasons.append(
            f"the protocol is three stops and this capture has {len(stops)}")
    for stop in stops:
        if stop.gapped:
            result.void = True
            result.void_reasons.append(
                f"the stream dropped for {stop.gap_s:.2f} s inside the stop on "
                f"lap {stop.lap}, so its duration is a lower bound, not a "
                f"measurement")


# ------------------------------------------------------------------ position

def _position(result: M0Result, samples: list[Sample]) -> None:
    """G17 - what the pre-race position field does once the race starts.

    The target design (§1.2) says the i16 at 0x84 is the grid slot and goes to
    -1 at lights-out, and warns that at least one public library labels it
    `race_position`. `packet.py:449` makes that exact claim in a docstring. One
    capture settles it from our own evidence.
    """
    values = [s.position for s in samples if s.position is not None]
    if not values:
        result.measurements["positionFieldLive"] = Measurement(
            "positionFieldLive", None, "", note="no position field captured")
        return
    racing = [s.position for s in samples
              if s.position is not None and s.lap > 0]
    distinct = sorted(set(racing))
    live = len(distinct) > 1
    result.measurements["positionFieldLive"] = Measurement(
        "positionFieldLive", float(len(distinct)), "distinct values",
        source="whole capture, laps 1+", samples=len(racing), conclusive=True,
        note=("the field CHANGES during the race, so it may be a live "
              "classification after all - re-check packet.py:449"
              if live else
              f"constant at {distinct[0] if distinct else 'nothing'} once "
              f"racing, so it carries no live classification - as designed"))


# ----------------------------------------------------------------------- run

def analyse(samples: list[Sample], *, capacity_l: float | None = None) -> M0Result:
    """Measure what the capture supports, and refuse what it does not."""
    result = M0Result()
    samples = sorted(samples, key=lambda s: s.t_s)
    stops = find_stops(samples)
    result.stops = stops

    _check_run(result, samples, stops, capacity_l)
    _position(result, samples)

    fuel_only = next((s for s in stops if s.took_fuel and not s.changed_tyres),
                     None)
    tyres_only = next((s for s in stops if s.changed_tyres and not s.took_fuel),
                      None)
    both = next((s for s in stops if s.took_fuel and s.changed_tyres), None)

    result.measurements["refuelRateLps"] = (
        _refuel_rate(samples, fuel_only) if fuel_only
        else Measurement("refuelRateLps", None, "L/s",
                         note="no fuel-only stop in this capture"))
    result.measurements["tyresOnlyStopS"] = _stationary(
        tyres_only, "tyresOnlyStopS", "tyres-only stop")
    result.measurements["fuelOnlyStopS"] = _stationary(
        fuel_only, "fuelOnlyStopS", "fuel-only stop")
    result.measurements["bothStopS"] = _stationary(
        both, "bothStopS", "tyres-and-fuel stop")

    green = _green_lap_s(samples, stops)
    reference = tyres_only or fuel_only or (stops[0] if stops else None)
    result.measurements["pitLaneDeltaS"] = (
        _pit_loss(samples, reference, green) if reference
        else Measurement("pitLaneDeltaS", None, "s", note="no stop to measure"))

    _verdict(result, tyres_only, fuel_only, both)
    return result


def write_constants(result: M0Result, path: str | Path) -> Path:
    """The provenance-tagged constants file. Not wired into strategy."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result.as_dict(), indent=2) + "\n",
                      encoding="utf-8")
    return target
