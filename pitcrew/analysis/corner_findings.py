"""What a stint says about one corner — and what it is not entitled to say.

**This is the debrief that replaced live corner coaching**, and the reason it
replaced it is a measurement. The plan was to call a corner lap-to-lap: *"you
are braking eight metres late into T4."* Measured 22 Aug 2026 over 307 clean
laps, per-corner metrics turn out to be **relatively noisier than lap time**,
not quieter:

    lap time      2 sd = 1.66 % of a lap
    corner time   2 sd = 4 % (Watkins) to 6 % (Monza) of a corner

and `brake_point_m` carries a 2 sd of 14–37 m at the median corner, 142 m at
the worst. There is no circuit on file where "move your marker back ten metres"
is a sentence this app may say. So nothing here speaks during a lap. It reports
**after** one, over as many laps as it takes, and it says how many that was.

### The three things it will claim, and the test each has to pass

* **`trend`** — the metric moved through the stint. An ordinary least-squares
  slope against lap number, kept only at `|t| >= TREND_T` over at least
  `MIN_TREND_LAPS` laps. This is the degradation shape: a corner giving up
  minimum speed while the brake point holds is a tyre going away, and it is
  the one finding that arrives before the stopwatch does.
* **`inconsistent`** — this corner's lap-to-lap scatter is materially wider
  than his own typical corner's. Not measured against an absolute figure,
  because there isn't one: it is measured against the other corners of the
  same session, which controls for the car, the circuit, the fuel load and the
  day. `analysis/corners.py` has always said why this matters — *"high spread
  with a normal average is the signature of a car the driver cannot trust, and
  it never shows up in a lap time."*

**There is deliberately no "you are N off your best" finding, and the reason is
worth keeping.** The first draft had one: mean against the best value seen,
kept where the gap cleared the noise floor. It fired on eighteen of twenty-four
Monza corner-metrics, which is not a debrief, it is wallpaper. **The maximum of
n samples sits about `sigma * sqrt(2 ln n)` above the mean by construction** -
for 24 laps that is ~2.5 sigma - so "the mean differs from the best by more
than 2 sigma" is very nearly a theorem, not a discovery. It was noise wearing a
finding's clothes.

What replaced it is `opportunity`, and it is **explicitly not a detection**: a
ranked, descriptive ordering of where the gap between his average and his good
laps is widest, so he knows where to spend a session. It makes no claim that
any single entry is significant, and it says so.

### The rules that keep it honest

**The noise floor is measured from this session, never looked up.** A stored
per-corner table would be a claim about a car, a circuit, a tyre and a day that
have all moved on. Every threshold here is derived from his own consecutive-lap
differences in the very laps being reported — `sigma = sd(diff) / sqrt(2)`,
which is `analysis/grip.py`'s construction and is used for the same reason: a
stint's own drift must not be counted as noise.

**A corner that cannot carry a claim is named as silent, with its reason.**
Not omitted. The whole failure this module is built against is an engineer
whose silence is indistinguishable from nothing being wrong, and the lap-time
work already established the doctrine: *the app must say "silence means I
cannot see them".*

**Every finding carries its sample count**, per CLAUDE.md §4.4, and nothing is
reported from fewer laps than the test needs.
"""
from __future__ import annotations

import math
import statistics as st
from dataclasses import dataclass, field

from pitcrew.analysis.corner_model import CornerModel
from pitcrew.analysis.corners import (
    CountedLap,
    _approach,
    _measure,
    _slice,
    length_gate,
)

# The metrics a corner is judged on, with the unit they are spoken in and how
# many decimals mean anything. `brake_point_m` and `throttle_on_pct` are here
# despite being the two the measurement found worst - **because the gate is
# per corner and measured, not global.** Watkins T7 carries a brake-point 2 sd
# of 11.9 m where Yas T5 carries 142; banning the channel outright would throw
# away the corners that can actually support it.
METRICS = (
    ("min_kph", "minimum speed", "km/h", 1),
    ("time_ms", "corner time", "ms", 0),
    ("brake_point_m", "brake point", "m", 1),
    ("throttle_on_pct", "throttle on", "%", 1),
)

# Fewer consecutive-lap differences than this and there is no noise estimate,
# so there is no threshold, so there is no finding. Four is the fewest that can
# disagree with itself.
MIN_DIFFS = 4
# A trend needs a span to be a trend. Six laps is the fewest that can show a
# slope this test would believe, and it is deliberately above the five that
# `analysis/wear.MIN_DEGRADATION_LAPS` asks of a wear fit.
MIN_TREND_LAPS = 6
# The slope's own t-statistic. 2.5 rather than 2.0: with four metrics on a
# dozen corners this runs some fifty tests a session, and at t = 2.0 two or
# three would clear by chance every time.
TREND_T = 2.5
# How much wider than the session's typical corner this corner's scatter has to
# be before it is a finding about the corner rather than about the day.
INCONSISTENT_RATIO = 2.0
# ...and the fewest corners that can establish what "typical" is.
MIN_CORNERS_FOR_TYPICAL = 4


@dataclass(frozen=True)
class Finding:
    """One claim about one corner, with everything needed to weigh it."""

    corner_id: str
    kind: str                    # trend | inconsistent
    metric: str
    label: str                   # the metric in words
    unit: str
    magnitude: float             # the size of the effect, in `unit`
    samples: int                 # laps behind it
    noise_2sd: float             # what the same laps say the floor is
    detail: str

    def as_text(self) -> str:
        return f"{self.corner_id}: {self.detail}"


@dataclass(frozen=True)
class Silent:
    """A corner that could not carry a claim, and why. Never omitted."""

    corner_id: str
    reason: str


@dataclass(frozen=True)
class Opportunity:
    """Where the gap between his average and his good laps is widest.

    **Descriptive, never a detection.** No significance is claimed for any
    single row: the point is the ORDERING, which says where a session is worth
    spending. `gap` is the mean against this corner's own 90th percentile -
    the ninetieth rather than the best, because the best of n laps is an
    extreme order statistic and the gap to it grows with the number of laps
    driven rather than with anything about the driving.
    """

    corner_id: str
    gap_ms: float
    mean_ms: float
    samples: int

    def as_text(self) -> str:
        return (f"{self.corner_id}: {self.gap_ms:.0f} ms between your average "
                f"and your good laps ({self.samples} laps)")


@dataclass(frozen=True)
class Report:
    findings: list[Finding] = field(default_factory=list)
    # Ranked widest-first. Descriptive; see `Opportunity`.
    opportunities: list[Opportunity] = field(default_factory=list)
    silent: list[Silent] = field(default_factory=list)
    laps_used: int = 0
    laps_held_out: int = 0
    # {corner_id: {metric: 2 sd}} — the floor this session actually measured,
    # published because every threshold here is derived from it.
    noise: dict = field(default_factory=dict)

    @property
    def quiet(self) -> bool:
        return not self.findings

    def summary(self) -> str:
        if not self.laps_used:
            return "No laps could be read."
        if self.quiet:
            return (f"No findings across {self.laps_used} laps. That is not "
                    f"the same as nothing being wrong - see the silent "
                    f"corners for what could not be measured, and the "
                    f"opportunities for where the time is.")
        return (f"{len(self.findings)} finding(s) across {self.laps_used} "
                f"laps.")


# --------------------------------------------------------------- statistics

def _noise_2sd(series: dict[int, float]) -> tuple[float | None, int]:
    """Two standard deviations of the lap-to-lap noise, from consecutive laps.

    `sd(diff) / sqrt(2)`, and only over laps that are actually adjacent: two
    laps either side of a gap are not consecutive in any sense this can use.
    """
    laps = sorted(series)
    diffs = [series[b] - series[a] for a, b in zip(laps, laps[1:])
             if b - a == 1 and series[a] is not None and series[b] is not None]
    if len(diffs) < MIN_DIFFS:
        return None, len(diffs)
    return 2.0 * st.stdev(diffs) / math.sqrt(2.0), len(diffs)


def _slope_t(series: dict[int, float]) -> tuple[float, float, int] | None:
    """(slope per lap, t statistic, n) for an ordinary least-squares fit."""
    points = [(lap, value) for lap, value in sorted(series.items())
              if value is not None]
    if len(points) < MIN_TREND_LAPS:
        return None
    n = len(points)
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx <= 0:
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in points) / sxx
    intercept = mean_y - slope * mean_x
    residual = sum((y - (intercept + slope * x)) ** 2 for x, y in points)
    if n <= 2:
        return None
    variance = residual / (n - 2)
    if variance <= 0:
        # A perfect fit. Real telemetry does not do this; a constant does, and
        # a constant has no slope worth reporting.
        return None
    standard_error = math.sqrt(variance / sxx)
    if standard_error <= 0:
        return None
    return slope, slope / standard_error, n


# ----------------------------------------------------------------- the pass

def _series(model: CornerModel,
            laps: list[CountedLap]) -> dict[str, dict[str, dict[int, float]]]:
    """{corner_id: {metric: {lap_num: value}}} over the laps given."""
    out: dict[str, dict[str, dict[int, float]]] = {}
    for corner in model.corners:
        per_metric: dict[str, dict[int, float]] = {
            name: {} for name, _, _, _ in METRICS}
        for lap in laps:
            window = _slice(lap.frames, corner)
            if len(window) < 2:
                continue
            measured = _measure(window, _approach(lap.frames, corner), corner,
                                lap.interval_ms, None, set(), None, None)
            for name, _, _, _ in METRICS:
                value = measured.get(name)
                if value is not None:
                    per_metric[name][lap.lap] = value
        if any(per_metric.values()):
            out[corner.id] = per_metric
    return out


def analyse(model: CornerModel, laps: list[CountedLap]) -> Report:
    """Everything this stint is entitled to say about its corners.

    `laps` must be ONE run. Consecutive means consecutive within a stint, and
    two laps either side of a pit stop are not adjacent in any sense the noise
    estimate can use - the caller separates runs, this does not.
    """
    gate = length_gate(laps)
    kept = gate.kept
    series = _series(model, kept)
    if not series:
        return Report(laps_used=len(kept), laps_held_out=len(gate.dropped))

    noise: dict[str, dict[str, float]] = {}
    for corner_id, per_metric in series.items():
        noise[corner_id] = {}
        for name, _, _, _ in METRICS:
            floor, _count = _noise_2sd(per_metric[name])
            if floor is not None:
                noise[corner_id][name] = floor

    findings: list[Finding] = []
    for corner_id, per_metric in sorted(series.items(), key=lambda kv: str(kv[0])):
        findings.extend(
            _corner_findings(corner_id, per_metric, noise[corner_id]))
    findings.extend(_inconsistency(series, noise))

    # **After every finding, not during.** Computed inside the loop above, a
    # corner could be listed silent and then have an inconsistency finding
    # added underneath it - which is what happened at Watkins T5.
    spoke = {finding.corner_id for finding in findings}
    silent = [Silent(corner_id, _why_silent(series[corner_id],
                                            noise[corner_id]))
              for corner_id in sorted(series, key=str)
              if corner_id not in spoke]
    return Report(findings=findings, opportunities=_opportunities(series),
                  silent=silent, laps_used=len(kept),
                  laps_held_out=len(gate.dropped), noise=noise)


def _corner_findings(corner_id: str, per_metric: dict, floors: dict
                     ) -> list[Finding]:
    out = []
    for name, label, unit, digits in METRICS:
        series = per_metric.get(name) or {}
        floor = floors.get(name)
        if floor is None:
            continue
        fit = _slope_t(series)
        if fit is not None:
            slope, t_value, n = fit
            span = max(series) - min(series)
            change = slope * span
            # **Both tests, not either.** `t` says the slope is real; the
            # comparison against the floor says it is big enough to be worth a
            # sentence. A statistically certain quarter of a km/h is not a
            # finding about driving.
            if abs(t_value) >= TREND_T and abs(change) >= floor:
                direction = "down" if change < 0 else "up"
                out.append(Finding(
                    corner_id=corner_id, kind="trend", metric=name,
                    label=label, unit=unit, magnitude=change, samples=n,
                    noise_2sd=floor,
                    detail=(f"{label} {direction} "
                            f"{abs(change):.{digits}f} {unit} across {n} laps "
                            f"(t {t_value:.1f}, noise {floor:.{digits}f})")))
                continue

    return out


def _opportunities(series: dict) -> list[Opportunity]:
    """Corner time between his average and his good laps, widest first."""
    out = []
    for corner_id, per_metric in series.items():
        times = [v for v in (per_metric.get("time_ms") or {}).values()
                 if v is not None]
        if len(times) < MIN_TREND_LAPS:
            continue
        ordered = sorted(times)                  # smaller is quicker
        # The tenth percentile of corner times IS the ninetieth percentile of
        # performance. Interpolation is not worth it at these sample sizes.
        good = ordered[max(0, int(len(ordered) * 0.1) - 1)]
        gap = st.mean(times) - good
        if gap <= 0:
            continue
        out.append(Opportunity(corner_id=corner_id, gap_ms=gap,
                               mean_ms=st.mean(times), samples=len(times)))
    return sorted(out, key=lambda o: o.gap_ms, reverse=True)


def _why_silent(per_metric: dict, floors: dict) -> str:
    """The honest reason a corner said nothing. Never 'no problem'."""
    laps = max((len(s) for s in per_metric.values()), default=0)
    if laps == 0:
        return "no lap reached this corner"
    if not floors:
        return (f"{laps} lap(s), but fewer than {MIN_DIFFS + 1} of them "
                f"consecutive - nothing measures the noise, so nothing sets "
                f"a threshold")
    if laps < MIN_TREND_LAPS:
        return (f"{laps} lap(s) - fewer than the {MIN_TREND_LAPS} any test "
                f"here needs")
    return (f"{laps} laps, and everything measured sits inside this corner's "
            f"own lap-to-lap noise")


def _inconsistency(series: dict, noise: dict) -> list[Finding]:
    """Corners he cannot repeat, measured against his other corners.

    **Against the session's own corners, not an absolute figure**, because
    there is no absolute figure: the scatter that is normal depends on the car,
    the circuit, the fuel load and the day, and all four are held constant by
    comparing a session against itself.
    """
    scatters = {}
    for corner_id, floors in noise.items():
        corner_time = (series.get(corner_id) or {}).get("time_ms") or {}
        floor = floors.get("time_ms")
        if floor is None or not corner_time:
            continue
        mean = st.mean(v for v in corner_time.values() if v is not None)
        if mean > 0:
            scatters[corner_id] = floor / mean          # scatter as a fraction
    if len(scatters) < MIN_CORNERS_FOR_TYPICAL:
        return []
    typical = st.median(scatters.values())
    if typical <= 0:
        return []
    out = []
    for corner_id, scatter in sorted(scatters.items(), key=lambda kv: str(kv[0])):
        if scatter < typical * INCONSISTENT_RATIO:
            continue
        samples = len((series[corner_id].get("time_ms") or {}))
        out.append(Finding(
            corner_id=corner_id, kind="inconsistent", metric="time_ms",
            label="corner time", unit="%", magnitude=scatter * 100.0,
            samples=samples, noise_2sd=typical * 100.0,
            detail=(f"lap to lap you vary {scatter * 100:.1f}% here against "
                    f"{typical * 100:.1f}% at your typical corner, over "
                    f"{samples} laps - the mean can be fine and this still "
                    f"be a corner you cannot repeat")))
    return out
