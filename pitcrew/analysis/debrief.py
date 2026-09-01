"""The practice debrief — what the session actually showed, and what it did not.

**Why this exists.** Every live call in the app comes from `RaceCoordinator`,
which is built in exactly one place: `start_race()`. George owns the race and
nothing owns practice, so the driver ran three Daytona sessions on 1 Sep 2026
and the engineer said nothing at all. The numbers were all computed and none of
them were ever spoken.

This module is the answer to the half of that gap that can be answered honestly
today: **the debrief between runs.** It is deliberately not a live coach. A
corner is 3-4x noisier than a whole lap in relative terms (22 Aug, 307 clean
laps), so there is nothing truthful to say about a corner while the driver is
still in it. Between runs there is, because between runs there is a sample.

### What it is allowed to say, and why each one survives

* **Consistency** — the lap-to-lap spread of minimum speed at a corner. The
  noise floor is not an obstacle here, it *is* the measurement: where the
  spread is wide, that is where the repeatability is missing. Needs no
  reference lap, no comparison driver and no correlation.
* **Gear** — the one channel that beats the noise floor outright, because it is
  an integer. There is no measurement error in "second or third". Where the
  driver's gear at a corner varied across laps he has run an A/B without
  setting one up, and it can be read back to him.
* **Correlation** of a corner's minimum speed against lap time — pooled across
  laps, which is the shape `docs/RACE-ENGINEER-CHARTER_2026-08-23.md` §2 leaves
  standing. Reported ONLY when it clears significance; otherwise the corner
  goes in `silences`.
* **Pace and burn** — whole-lap figures, which sit below the noise floor.

### What it is NOT allowed to say

Per-lap, per-corner input coaching in any channel. Brake point and throttle
position are refuted by the driver's own data and no amount of aggregation in
here brings them back.

### Two filters, and they are not the same one

`counted` (see `analysis/session.py`) is the pace-and-fuel set: it drops
out-laps, in-laps, hand strikes and incidents. **This module drops more.** An
excursion does not have to reach the 2.5 s `incidents.OFF_TRACK_MIN_S` to
destroy a corner reading, and on the Daytona set two laps with longest runs of
1.22 s and 1.43 s - neither an incident, both correctly counted for pace -
carried an entire finding on their own:

    r(T1 min speed, lap time)   all 13 laps  -0.86   T1 scatter 12.8 km/h
                                11 clean     -0.30   T1 scatter  2.8 km/h

The headline said T1 was worth 1.8 s a lap and was his least repeatable corner.
Both reversed. It had already survived a check for a tyre-age confound, which
is exactly why it was convincing - **a confound check that passes is not the
same as a clean sample.** So `CLEAN_OFF_TRACK_S` is cumulative time off the
road, it is stricter than the incident threshold, and the count it drops is
reported rather than absorbed.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from pitcrew.analysis import distance
from pitcrew.analysis.corner_model import Corner, CornerModel
from pitcrew.analysis.corners import CountedLap, _slice, length_gate

# **Cumulative seconds off the racing surface that put a lap out of the corner
# analysis.** Deliberately below `incidents.OFF_TRACK_MIN_S` (2.5 s), which
# measures the longest CONTIGUOUS run and exists to answer a different
# question - "was this lap an incident" rather than "is this lap's corner data
# usable". Ordinary kerb-clipping laps on the Daytona set sit at 0.0-0.4 s; the
# two that carried the false T1 finding sat at 1.22 and 1.43.
CLEAN_OFF_TRACK_S = 1.0

# Below this many clean laps a correlation is not reported at all. At eleven
# laps the strongest thing on the Daytona set was r = -0.56, about p = 0.07 -
# close enough to look like a finding and not close enough to be one.
MIN_LAPS_FOR_CORRELATION = 10

# Two-tailed. Nothing here is a screening exercise where a looser bar would be
# defensible; every one of these is said out loud to a driver.
ALPHA = 0.05

# Laps needed in EACH arm before a gear difference is called a comparison. Below
# it the split is still reported - it is how the Spa Bus Stop hypothesis was
# found - but flagged as unbalanced, and the wording has to change with it.
MIN_GEAR_ARM = 3


# --------------------------------------------------------------- statistics

def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta. Numerical Recipes 6.4."""
    tiny, eps, itmax = 1e-30, 3e-7, 200
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, itmax + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        c = 1.0 + aa / c
        if abs(d) < tiny:
            d = tiny
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        c = 1.0 + aa / c
        if abs(d) < tiny:
            d = tiny
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def _betai(a: float, b: float, x: float) -> float:
    """Regularised incomplete beta I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                     + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def correlation_p(r: float, n: int) -> float | None:
    """Two-tailed p for a Pearson r on n pairs, or None if undefined.

    **No SciPy in this codebase**, so the t-distribution is done here. Tested
    against published critical values rather than against itself.
    """
    if n < 3:
        return None
    if abs(r) >= 1.0:
        return 0.0
    df = n - 2
    t = abs(r) * math.sqrt(df / (1.0 - r * r))
    return _betai(df / 2.0, 0.5, df / (df + t * t))


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    sxx = sum((a - mx) ** 2 for a in xs)
    syy = sum((b - my) ** 2 for b in ys)
    if sxx <= 0.0 or syy <= 0.0:
        return None
    return sxy / math.sqrt(sxx * syy)


def _mean(values) -> float | None:
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def _sd(values) -> float | None:
    """Population sd. Returns None below two samples — never 0.0, which would
    read as "perfectly repeatable" for a corner seen once (CLAUDE.md rule 3)."""
    values = [v for v in values if v is not None]
    if len(values) < 2:
        return None
    m = sum(values) / len(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / len(values))


# ------------------------------------------------------------------ results

@dataclass(frozen=True)
class Census:
    """Where every lap went. The arithmetic has to close."""
    recorded: int
    out_laps: int
    in_laps: int
    excluded: int
    excursions: int          # dropped by CLEAN_OFF_TRACK_S, not by `counted`
    analysed: int

    def describe(self) -> str:
        parts = [f"{self.analysed} of {self.recorded} laps analysed"]
        dropped = []
        if self.out_laps:
            dropped.append(f"{self.out_laps} out")
        if self.in_laps:
            dropped.append(f"{self.in_laps} in")
        if self.excluded:
            dropped.append(f"{self.excluded} struck")
        if self.excursions:
            dropped.append(f"{self.excursions} with an excursion")
        if dropped:
            parts.append(" — " + ", ".join(dropped))
        return "".join(parts)


@dataclass(frozen=True)
class Pace:
    n: int
    median_ms: int | None
    best_ms: int | None
    sd_ms: float | None


@dataclass(frozen=True)
class Burn:
    n: int
    median_l: float | None
    sd_l: float | None


@dataclass(frozen=True)
class CornerScatter:
    """How repeatable the driver is at one corner. The headline of the whole
    debrief, because it needs no reference of any kind."""
    corner_id: str
    corner_name: str
    n: int
    mean_kph: float | None
    sd_kph: float | None
    carry_m: float

    @property
    def cov_pct(self) -> float | None:
        if self.sd_kph is None or not self.mean_kph:
            return None
        return 100.0 * self.sd_kph / self.mean_kph


@dataclass(frozen=True)
class GearArm:
    gear: int
    n: int
    mean_min_kph: float | None
    mean_lap_ms: float | None


@dataclass(frozen=True)
class GearSplit:
    """A corner the driver took in more than one gear — an A/B he ran without
    setting one up."""
    corner_id: str
    corner_name: str
    arms: tuple[GearArm, ...]

    @property
    def balanced(self) -> bool:
        return all(arm.n >= MIN_GEAR_ARM for arm in self.arms)

    @property
    def quickest(self) -> GearArm | None:
        rated = [a for a in self.arms if a.mean_lap_ms is not None]
        return min(rated, key=lambda a: a.mean_lap_ms) if rated else None


@dataclass(frozen=True)
class Correlation:
    corner_id: str
    corner_name: str
    n: int
    r: float
    p: float

    @property
    def speak(self) -> bool:
        return self.n >= MIN_LAPS_FOR_CORRELATION and self.p <= ALPHA


@dataclass(frozen=True)
class VideoCue:
    """Where to look, in seconds into the capture."""
    lap_num: int
    corner_id: str
    path: str
    second: float


@dataclass(frozen=True)
class Debrief:
    census: Census
    pace: Pace
    burn: Burn
    scatter: tuple[CornerScatter, ...]
    gears: tuple[GearSplit, ...]
    correlations: tuple[Correlation, ...]
    video: tuple[VideoCue, ...] = ()
    # **Everything the debrief could not see, and why.** The standing rule from
    # the degradation work: silence means "I cannot see it", never "nothing is
    # happening". A corner that fails significance leaves a line here rather
    # than simply not appearing.
    silences: tuple[str, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def least_repeatable(self) -> CornerScatter | None:
        rated = [s for s in self.scatter if s.cov_pct is not None]
        return max(rated, key=lambda s: s.cov_pct) if rated else None

    @property
    def spoken(self) -> list[Correlation]:
        return [c for c in self.correlations if c.speak]


# ------------------------------------------------------------------ analysis

def is_clean(off_track_s: float | None) -> bool:
    """Usable for corner analysis. `None` means the surface channel was absent
    for that lap, which is not evidence of a clean one — it is refused."""
    return off_track_s is not None and off_track_s < CLEAN_OFF_TRACK_S


def _carry_m(model: CornerModel, index: int) -> float:
    corners = model.corners
    here = corners[index]
    nxt = corners[(index + 1) % len(corners)]
    if index + 1 < len(corners):
        return nxt.start_m - here.end_m
    return nxt.start_m + model.lap_length_m - here.end_m


def _window(lap: CountedLap, corner: Corner) -> tuple[list[float], list[int]]:
    frames = _slice(lap.frames, corner)
    speeds, gears = [], []
    for frame in frames:
        speed, gear = frame.get("speed_kph"), frame.get("gear")
        if speed is None:
            continue
        speeds.append(speed)
        gears.append(gear)
    return speeds, gears


def analyse(model: CornerModel, laps: list[tuple[CountedLap, int]],
            *, census: Census, pace: Pace, burn: Burn) -> Debrief:
    """The pure core. `laps` is (lap, lap_time_ms), already filtered clean."""
    laps = [(lap, ms) for lap, ms in laps]
    kept = {id(lap) for lap in length_gate([lap for lap, _ in laps]).kept}
    laps = [(lap, ms) for lap, ms in laps if id(lap) in kept]

    scatter, gears, correlations, silences = [], [], [], []
    times = [float(ms) for _, ms in laps]

    for index, corner in enumerate(model.corners):
        mins, apex_gears, paired_times = [], [], []
        for (lap, ms) in laps:
            speeds, lap_gears = _window(lap, corner)
            if len(speeds) < 3:
                continue
            at = speeds.index(min(speeds))
            mins.append(speeds[at])
            apex_gears.append(lap_gears[at] if at < len(lap_gears) else None)
            paired_times.append(float(ms))

        if len(mins) < 2:
            silences.append(
                f"{corner.name}: only {len(mins)} lap(s) reached it — "
                "nothing can be said about a corner seen once")
            continue

        scatter.append(CornerScatter(
            corner_id=corner.id, corner_name=corner.name, n=len(mins),
            mean_kph=_mean(mins), sd_kph=_sd(mins),
            carry_m=_carry_m(model, index)))

        # **Gear, and it is the strongest channel here.** An integer carries no
        # measurement noise, so a difference between gears is a real difference
        # and not a threshold argument. What it does NOT carry is causation:
        # apex gear is partly an EFFECT of entry speed, since arriving slowly
        # puts the car a gear lower on its own. Observation cannot separate
        # those - only a deliberate run can, which is why this is reported as
        # something to test rather than something to do.
        by_gear: dict[int, list[tuple[float, float]]] = {}
        for gear, low, ms in zip(apex_gears, mins, paired_times):
            if gear is None or gear <= 0:
                continue
            by_gear.setdefault(gear, []).append((low, ms))
        if len(by_gear) > 1:
            gears.append(GearSplit(
                corner_id=corner.id, corner_name=corner.name,
                arms=tuple(sorted(
                    (GearArm(gear=g, n=len(rows),
                             mean_min_kph=_mean([r[0] for r in rows]),
                             mean_lap_ms=_mean([r[1] for r in rows]))
                     for g, rows in by_gear.items()),
                    key=lambda a: a.gear))))

        r = _pearson(mins, paired_times)
        if r is None:
            silences.append(f"{corner.name}: minimum speed did not vary enough "
                            "to correlate against lap time")
            continue
        p = correlation_p(r, len(mins))
        found = Correlation(corner_id=corner.id, corner_name=corner.name,
                            n=len(mins), r=r, p=p if p is not None else 1.0)
        correlations.append(found)
        if not found.speak:
            if found.n < MIN_LAPS_FOR_CORRELATION:
                silences.append(
                    f"{corner.name}: {found.n} clean laps, below the "
                    f"{MIN_LAPS_FOR_CORRELATION} this needs — not that nothing "
                    "is happening, that I cannot see it")
            else:
                silences.append(
                    f"{corner.name}: r={found.r:+.2f} at p={found.p:.2f}, "
                    "which does not clear the bar")

    return Debrief(
        census=census, pace=pace, burn=burn,
        scatter=tuple(sorted(scatter,
                             key=lambda s: -(s.cov_pct or 0.0))),
        gears=tuple(gears),
        correlations=tuple(sorted(correlations, key=lambda c: c.p)),
        silences=tuple(silences),
        notes=(f"Corner analysis drops any lap with {CLEAN_OFF_TRACK_S:.1f} s "
               "or more off the racing surface, which is stricter than the "
               "incident threshold and is why the counts differ from pace.",))


# ------------------------------------------------------------- store binding

def from_store(store, event_id: int, *, session_ids=None) -> Debrief | None:
    """Build the debrief for an event's practice running.

    Returns None where there is no corner model for the circuit — which is
    honest, and is what happened at Daytona until one was built on 1 Sep. The
    pace and fuel halves would still compute, but a debrief whose corner half
    is silently absent reads as "nothing to say about your driving".
    """
    from pitcrew.analysis.resolve import circuit_key
    from pitcrew.analysis.runs import (
        REASON_IN_LAP,
        REASON_OUT_LAP,
        classify_exclusions,
    )
    from pitcrew.analysis.session import counted_laps
    from pitcrew.export.build import event_lap_inputs

    event = store.get_event(event_id)
    if event is None:
        return None
    model = store.get_corner_model(circuit_key(event["track"], event["layout"]))
    if model is None:
        return None

    laps = event_lap_inputs(store, event_id, "practice")
    if session_ids is not None:
        laps = [lap for lap in laps if lap.session_id in set(session_ids)]
    if not laps:
        return None

    # **The same rule the rack and the export use, imported not restated.**
    # `classify_exclusions` applies the out-lap and the fuel-implausible lap;
    # the stored `is_out_lap` column is zero on every lap ever recorded, so
    # reading the flag instead would count every out-lap in the pace.
    capacity = next((lap.fuel_start for lap in laps
                     if lap.fuel_start and lap.fuel_start > 50), None)
    laps = classify_exclusions(laps, capacity)
    counted = counted_laps(laps)

    times = sorted(lap.lap_time_ms for lap in counted if lap.lap_time_ms)
    burns = sorted(lap.fuel_start - lap.fuel_end for lap in counted
                   if lap.fuel_start and lap.fuel_end
                   and lap.fuel_start > lap.fuel_end)
    pace = Pace(n=len(times),
                median_ms=times[len(times) // 2] if times else None,
                best_ms=times[0] if times else None,
                sd_ms=_sd([float(t) for t in times]))
    burn = Burn(n=len(burns),
                median_l=burns[len(burns) // 2] if burns else None,
                sd_l=_sd(burns))

    # **Two filters, and the second one was invisible until 1 Sep.** An
    # excursion makes a corner reading wrong; a TELEPORT makes the distance
    # axis itself wrong, and 7% of stored laps contain one. A teleport that
    # leaves the total length plausible sails through `length_gate`, and every
    # corner window after it is indexed against an axis that jumped. See
    # `analysis.distance`.
    clean, teleported = [], []
    for lap in counted:
        if not (is_clean(lap.off_track_s) and lap.frames):
            continue
        if not distance.teleports(lap.frames).happened:
            clean.append(lap)
        else:
            teleported.append(lap)
    # **Counted by the reason `classify_exclusions` assigned, not by the stored
    # flags.** That function names an out-lap by the rule rather than by
    # `is_out_lap`, which is zero on every lap ever recorded - so counting the
    # flag put three Daytona out-laps under "struck by hand" on the first run
    # of this, which reads as the driver having thrown laps away.
    def _with_reason(name: str) -> int:
        return sum(1 for lap in laps if lap.exclusion_reason == name)

    census = Census(
        recorded=len(laps),
        out_laps=_with_reason(REASON_OUT_LAP),
        in_laps=_with_reason(REASON_IN_LAP),
        excluded=sum(1 for lap in laps
                     if lap.exclusion_reason not in
                     (None, REASON_OUT_LAP, REASON_IN_LAP)),
        excursions=len(counted) - len(clean),
        analysed=len(clean))

    pairs = [(CountedLap(lap=lap.lap_num, frames=lap.frames,
                         setup_sheet_id=lap.setup_sheet_id,
                         sample_hz=_sample_hz(lap)), lap.lap_time_ms)
             for lap in clean]
    if not pairs:
        return Debrief(census=census, pace=pace, burn=burn,
                       scatter=(), gears=(), correlations=(),
                       silences=("No lap survived the excursion filter, so "
                                 "there is nothing to say about any corner.",))

    debrief = analyse(model, pairs, census=census, pace=pace, burn=burn)
    if teleported:
        debrief = Debrief(
            census=debrief.census, pace=debrief.pace, burn=debrief.burn,
            scatter=debrief.scatter, gears=debrief.gears,
            correlations=debrief.correlations, video=debrief.video,
            silences=debrief.silences + (
                f"{len(teleported)} lap(s) left out: the car jumped position "
                "mid-lap, so their corners are indexed against an axis that "
                "moved. A reset or a garage return.",),
            notes=debrief.notes)
    return _with_video(store, debrief, model, clean)


def _sample_hz(lap) -> float | None:
    frames = lap.frames or []
    if len(frames) < 2:
        return None
    span = frames[-1].get("t_ms", 0) - frames[0].get("t_ms", 0)
    return (len(frames) - 1) * 1000.0 / span if span else None


def _with_video(store, debrief: Debrief, model: CornerModel, clean) -> Debrief:
    """Timecodes for the corner worth looking at, where a capture exists.

    Uses `race.video_index`, which knows the zero exactly because the app
    started the recording — no offset to type.

    **The old caveat here was wrong and is corrected.** It said the seek rests
    on a distance axis "unreliable on 8-12% of laps". Re-measured against the
    position channel on 672 stored laps, the two axes place a corner within
    half a metre of each other and disagree materially on 1.6% — and every lap
    reaching this point has already passed the teleport check. What the 8-12%
    figure actually counted was laps of a different piece of road, which are
    filtered long before here. The seek is good to about a metre; the residual
    is the driver apexing in a slightly different place, which is a real
    difference and the thing worth watching.
    """
    from pitcrew.race import video_index

    target = debrief.least_repeatable
    if target is None:
        return debrief
    corner = next((c for c in model.corners if c.id == target.corner_id), None)
    if corner is None:
        return debrief

    # **The stored lap number has to be recovered.** `event_lap_inputs`
    # renumbers laps continuously across the event so that two laps are never
    # both called "lap 1", and `video_index` keys its crossings on the stored
    # per-session number. Nothing on `LapInput` carries the original, so it is
    # matched back by (session, lap time) - unique within a session at
    # millisecond precision, and skipped rather than guessed where it is not.
    cues, indexes, numbers = [], {}, {}
    for lap in clean:
        if lap.session_id not in indexes:
            indexes[lap.session_id] = video_index.for_session(store, lap.session_id)
            seen: dict[int, int | None] = {}
            for row in store.list_laps(lap.session_id):
                key = row["lap_time_ms"]
                seen[key] = None if key in seen else row["lap_num"]
            numbers[lap.session_id] = seen
        index = indexes[lap.session_id]
        if not index.usable or not index.path:
            continue
        stored_num = numbers[lap.session_id].get(lap.lap_time_ms)
        if stored_num is None:
            continue
        at_lap = index.at_lap(stored_num)
        into = video_index.seconds_into_lap(lap.frames, corner.apex_m)
        if at_lap is None or into is None:
            continue
        # `at_lap` is the CROSSING - the end of the lap - so the corner sits
        # that lap's own duration before it, plus however far into the lap it
        # is. Subtracting is what puts it in the right lap rather than the next.
        cues.append(VideoCue(
            lap_num=lap.lap_num, corner_id=corner.id, path=index.path,
            second=at_lap - (lap.lap_time_ms / 1000.0) + into))
    if not cues:
        return debrief
    return Debrief(
        census=debrief.census, pace=debrief.pace, burn=debrief.burn,
        scatter=debrief.scatter, gears=debrief.gears,
        correlations=debrief.correlations, video=tuple(cues),
        silences=debrief.silences, notes=debrief.notes)


# --------------------------------------------------------------- the radio

# **A debrief is not a live call and the register is different.** CLAUDE.md
# §5.5 governs what is said at racing speed: one thing, instruction first,
# reason second. This is said with the car stopped, so it may carry more than
# one thing - but not many more. Six lines is about twenty seconds of speech
# and it is where a spoken summary stops being listened to.
MAX_SPOKEN_LINES = 6


def _say_seconds(ms) -> str | None:
    """A lap time as the radio should say it.

    One decimal, not three. `format_lap_time` is right on a screen he can
    re-read; spoken, "one oh six point oh four two" is a number nobody holds.
    """
    return None if ms is None else f"{ms / 1000.0:.1f}"


def spoken_lines(debrief: Debrief) -> list[str]:
    """What the engineer says when the session closes, in order.

    Ordered the way an engineer talks rather than the way the data is
    computed: what happened, then the one thing worth doing about it, then
    what could not be seen. **Numbers are kept to two per clause** — the voice
    pack is per-phrase clips and a clause carrying three numbers needs a clip
    per combination, which is tens of thousands of files, so it falls through
    to live synthesis every time (measured on the qualifying out-lap call).
    """
    lines: list[str] = []
    census, pace = debrief.census, debrief.pace

    if census.analysed == 0:
        return ["Session done. No lap survived clean enough to read. "
                "I have nothing for you."]

    lines.append(f"Session done. {census.analysed} laps analysed "
                 f"of {census.recorded}.")
    if pace.median_ms is not None and pace.best_ms is not None:
        lines.append(f"Median {_say_seconds(pace.median_ms)}. "
                     f"Best {_say_seconds(pace.best_ms)}.")

    # **The actionable thing goes before the descriptive one.** A gear split
    # with laps on both sides is the only item here he can act on directly;
    # everything else is a place to look.
    balanced = [g for g in debrief.gears if g.balanced and g.quickest]
    if balanced:
        # **Ranked by the SIZE OF THE DIFFERENCE, not by which arm posted the
        # quickest absolute lap.** Selecting on absolute time picks whichever
        # corner happened to be taken in one gear during the driver's quickest
        # run, which is a statement about the run and not about the gear. The
        # claim being made is "this gear was worth something", so the ranking
        # has to be that quantity - CLAUDE.md rule 12, report the constraint
        # that actually produced the answer.
        best_split = max(balanced, key=_gear_gap_ms)
        quickest = best_split.quickest
        others = [a for a in best_split.arms if a.gear != quickest.gear
                  and a.mean_lap_ms is not None]
        against = min(others, key=lambda a: a.mean_lap_ms) if others else None
        if against is not None:
            lines.append(
                f"At {best_split.corner_name}, {_ordinal(quickest.gear)} gear "
                f"was quicker than {_ordinal(against.gear)}. "
                f"{quickest.n} laps against {against.n}. Worth a proper test.")

    worst = debrief.least_repeatable
    if worst is not None and worst.sd_kph is not None:
        lines.append(f"{worst.corner_name} is your least repeatable corner. "
                     f"{worst.sd_kph:.1f} kilometres an hour of spread.")

    for found in debrief.spoken[:1]:
        way = "faster" if found.r < 0 else "slower"
        lines.append(f"Your quick laps are the ones you are {way} "
                     f"through {found.corner_name}.")

    # **Silence is reported, never left as absence.** The standing rule from
    # the degradation work: a corner nobody mentions reads as a corner where
    # nothing is happening, and that is not what it means.
    if debrief.silences and not debrief.spoken:
        lines.append("Nothing else cleared the bar. That is me not seeing it, "
                     "not nothing happening.")

    return lines[:MAX_SPOKEN_LINES]


def _gear_gap_ms(split: GearSplit) -> float:
    """Lap time between the quickest arm and the next. Zero if unrateable."""
    rated = sorted(a.mean_lap_ms for a in split.arms if a.mean_lap_ms is not None)
    return (rated[1] - rated[0]) if len(rated) > 1 else 0.0


_ORDINALS = {1: "first", 2: "second", 3: "third", 4: "fourth",
             5: "fifth", 6: "sixth", 7: "seventh", 8: "eighth"}


def _ordinal(gear: int) -> str:
    """Gears are spoken, not printed. "G2" is a column heading, not a word."""
    return _ORDINALS.get(gear, f"gear {gear}")
