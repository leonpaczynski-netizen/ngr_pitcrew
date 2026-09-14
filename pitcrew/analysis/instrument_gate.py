"""The gate every new instrument passes before it is quoted - plan row 5.0.

**Every instrument this project has discarded was discarded after being quoted**
(`reference_instrument_noise_floors_2026_09_04`). The front-lock percentage
halved on a toe change and the change sat inside its own same-setup floor; the
yaw-per-lock index moved 2.1x its floor in the predicted direction while it was
measuring the rear sliding; the front slip gap could not move at all with ABS
holding the axle at its working point. Three different failures, so three
checks, and a fourth the 4 Sep method did not have:

(a) **Same-setup floor.** One unchanged session's clean laps split into two
    halves every possible way; the spread of |mean A - mean B| is what an
    effect has to beat. Median and p90, both reported.
(b) **Between-run floor.** The same split over *runs* rather than laps, because
    a session mean and a before/after across runs carry fuel, tyre, day and
    wind that consecutive laps do not. Plan row 5.3 needs this one.
(c) **Known answer.** On a change whose direction is already known right - his
    report plus an outcome - the instrument moves that way by more than its
    floor, or it is recorded as blind.
(d) **Can it move.** A channel pinned in a narrow band (ABS working point) is
    measuring the controller, not the car.

None of these returns a number where it cannot: too few laps is `None` with a
reason (rule 3), never a floor of zero (rule 9).
"""
from __future__ import annotations

import itertools
import math
import random
import statistics
from dataclasses import dataclass

# Fewer laps than this and there is no split worth the name: two laps split one
# each is a single difference, not a distribution.
MIN_LAPS = 4
# Above this many distinct splits, a fixed-seed sample of them - the answer
# converges long before C(20, 10) = 184,756 and the seed keeps it repeatable.
MAX_SPLITS = 5000
SAMPLE_SEED = 20260904


@dataclass(frozen=True)
class Floor:
    """What an effect on this instrument has to beat."""
    median: float | None
    p90: float | None
    n: int
    n_basis: str
    splits: int
    method: str
    why_none: str | None = None

    @property
    def established(self) -> bool:
        return self.median is not None and self.median > 0.0


def _split_diffs(values: list[float]) -> list[float]:
    n = len(values)
    half = n // 2
    indices = range(n)
    combos = itertools.combinations(indices, half)
    total = math.comb(n, half)
    if total > MAX_SPLITS:
        rng = random.Random(SAMPLE_SEED)
        chosen = set()
        while len(chosen) < MAX_SPLITS:
            chosen.add(tuple(sorted(rng.sample(list(indices), half))))
        combos = iter(sorted(chosen))
    diffs = []
    seen = set()
    for a in combos:
        b = tuple(i for i in indices if i not in a)
        # An even n reaches every split twice (A|B and B|A); count it once.
        key = min(a, b)
        if key in seen:
            continue
        seen.add(key)
        mean_a = statistics.fmean(values[i] for i in a)
        mean_b = statistics.fmean(values[i] for i in b)
        diffs.append(abs(mean_a - mean_b))
    return diffs


def _p90(diffs: list[float]) -> float:
    ordered = sorted(diffs)
    return ordered[min(len(ordered) - 1, int(math.ceil(0.9 * len(ordered))) - 1)]


def same_setup_floor(values, *, n_basis: str = "clean laps") -> Floor:
    """(a): every split of one unchanged session's laps into two halves."""
    clean = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    method = "split-halves, every split of one unchanged session (4 Sep 2026 method)"
    if len(clean) < MIN_LAPS:
        return Floor(None, None, len(clean), n_basis, 0, method,
                     why_none=f"{len(clean)} {n_basis}; a floor needs {MIN_LAPS}")
    diffs = _split_diffs(clean)
    return Floor(statistics.median(diffs), _p90(diffs), len(clean), n_basis,
                 len(diffs), method)


def between_run_floor(runs, *, n_basis: str = "runs") -> Floor:
    """(b): how far one run's mean lands from another's on one unchanged setup.

    **The scale is run against run**, because that is the comparison it guards:
    a before/after is one run on each side. Every pair of runs is compared, and
    the median and p90 of |mean A - mean B| are the floor. (A first version
    split the run means into two halves, which answers "half the runs against
    the other half" - a floor that shrinks as runs are added and says nothing
    about a single run. The dry run on 23 Daytona sessions showed it: a
    between-run floor below every within-session one.)

    **Only runs on ONE setup belong in `runs`.** Sessions with a change between
    them make the floor wider by the change's effect - the caller has to know
    which runs share a setup (plan row 5.4a), and this function cannot."""
    means = []
    for run in runs:
        clean = [float(v) for v in run if v is not None and math.isfinite(float(v))]
        if clean:
            means.append(statistics.fmean(clean))
    method = "every pair of runs on one unchanged setup, |run mean A - run mean B|"
    if len(means) < 3:
        return Floor(None, None, len(means), n_basis, 0, method,
                     why_none=f"{len(means)} runs; a between-run floor needs 3")
    diffs = [abs(x - y) for x, y in itertools.combinations(means, 2)]
    return Floor(statistics.median(diffs), _p90(diffs), len(means), n_basis,
                 len(diffs), method)


@dataclass(frozen=True)
class KnownAnswer:
    """(c): did the instrument see a change whose direction is already known?"""
    moved: float | None
    expected: str           # "up" | "down"
    floor: float | None
    verdict: str            # "sees it" | "blind" | "wrong way" | "cannot tell"
    why: str


def known_answer(before, after, *, expected: str, floor: Floor) -> KnownAnswer:
    """Compare means of `before` and `after` laps against the floor.

    `expected` comes from his report plus an outcome measure - never from the
    instrument being checked, or the check is circular."""
    if expected not in ("up", "down"):
        raise ValueError("expected is 'up' or 'down'")
    b = [float(v) for v in before if v is not None]
    a = [float(v) for v in after if v is not None]
    if not b or not a:
        return KnownAnswer(None, expected, floor.median, "cannot tell",
                           "no values on one side")
    if not floor.established:
        return KnownAnswer(statistics.fmean(a) - statistics.fmean(b), expected,
                           None, "cannot tell",
                           f"no floor: {floor.why_none or 'not established'}")
    moved = statistics.fmean(a) - statistics.fmean(b)
    if abs(moved) <= floor.p90:
        return KnownAnswer(moved, expected, floor.p90, "blind",
                           f"moved {moved:+.4g} inside the p90 floor {floor.p90:.4g}")
    right_way = (moved > 0) == (expected == "up")
    if right_way:
        return KnownAnswer(moved, expected, floor.p90, "sees it",
                           f"moved {moved:+.4g}, beyond the p90 floor {floor.p90:.4g}, "
                           f"the known way")
    return KnownAnswer(moved, expected, floor.p90, "wrong way",
                       f"moved {moved:+.4g} against the known direction")


@dataclass(frozen=True)
class Movable:
    """(d): can the channel move, or is something holding it?"""
    pinned_fraction: float | None
    band: tuple[float, float] | None
    movable: bool | None
    why: str


def can_it_move(values, *, band_width: float, pinned_above: float = 0.40) -> Movable:
    """The largest share of values inside any window `band_width` wide.

    ABS held 43-47% of heavy-braking front slip inside 0.86-0.92 (5 Sep 2026);
    a channel living in a band that narrow is reporting the controller. None
    where there are too few values to say (rule 3)."""
    clean = sorted(float(v) for v in values if v is not None and math.isfinite(float(v)))
    if len(clean) < 20:
        return Movable(None, None, None, f"{len(clean)} values; need 20 to judge a pin")
    best, lo_best = 0, 0
    j = 0
    for i in range(len(clean)):
        while clean[i] - clean[j] > band_width:
            j += 1
        if i - j + 1 > best:
            best, lo_best = i - j + 1, j
    fraction = best / len(clean)
    band = (clean[lo_best], clean[lo_best] + band_width)
    if fraction > pinned_above:
        return Movable(fraction, band, False,
                       f"{fraction:.0%} of values sit inside {band[0]:.4g}-{band[1]:.4g}: "
                       f"pinned, likely by a controller")
    return Movable(fraction, band, True,
                   f"at most {fraction:.0%} inside any {band_width:g}-wide band")


@dataclass(frozen=True)
class GateResult:
    usable: bool
    reasons: tuple[str, ...]


def gate(floor: Floor, *, known: KnownAnswer | None = None,
         movable: Movable | None = None, between: Floor | None = None,
         needs_between_run: bool = False) -> GateResult:
    """All four checks, and a plain yes or no with every reason.

    A check that was not run is a reason, not a pass: an instrument is usable
    only when its floor is established, it moved its known answer the right
    way, it is not pinned, and - where the use compares runs - the between-run
    floor exists."""
    reasons = []
    ok = True
    if not floor.established:
        ok = False
        reasons.append(f"no same-setup floor ({floor.why_none or 'zero spread'})")
    if known is None:
        ok = False
        reasons.append("no known-answer check run")
    elif known.verdict != "sees it":
        ok = False
        reasons.append(f"known answer: {known.verdict} - {known.why}")
    if movable is None:
        ok = False
        reasons.append("not checked for a pinned channel")
    elif movable.movable is not True:
        ok = False
        reasons.append(f"pin check: {movable.why}")
    if needs_between_run:
        if between is None or not between.established:
            ok = False
            reasons.append("the use compares runs and no between-run floor exists"
                           + (f" ({between.why_none})" if between and between.why_none else ""))
    if ok:
        reasons.append("floor established, known answer seen, channel free to move")
    return GateResult(ok, tuple(reasons))
