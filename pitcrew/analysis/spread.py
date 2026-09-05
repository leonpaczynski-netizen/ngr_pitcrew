"""Inconsistency as a finding, not as a bar the finding has to clear.

**The driver's point, 5 Sep 2026, and it corrects the doctrine that was here.**
Scatter was treated as a state to be tolerated and used only as a refusal
threshold — a delta inside the spread claims nothing. That is right as far as
it goes and it stops one lap short:

> *"Why is the car not set up for a certain part of the track? If two sectors
> are close each lap and one sector has spread, what is in that sector causing
> it? Like the Bus Stop at Daytona and T1. T1 needed lsd_b, the Bus Stop needed
> front compression lowered. That could have been identified earlier if laps
> weren't thrown away as noise but actually analysed as to why there is noise."*

He is right, and both of those were found late. **A corner the driver cannot
repeat is a corner where the car is not repeatable**, and that is a setup
finding with a location attached — which is exactly what the mean of a sector
cannot give you, because a mean over an unrepeatable corner is a confident
number describing nothing that happened.

So spread gets read in its own right: which part of the lap carries it, and
whether that is distinguishable from the parts that do not.

### Two things that inflate spread and are not the car

**Learning.** Measured on this driver, improvement across a run is ~0.3 s/run
and beats every setup effect on file. A sector that is getting quicker every
lap has a large raw spread and a small residual one, and only the residual is
about the car. Everything here is detrended against lap order first.

**Excursions.** Already excluded upstream — an off is not a slow lap, it is a
different lap. Daytona T1 read r=-0.86 against lap time until two off-track
laps came out, then -0.30.

### What eight laps can actually distinguish

Very little, and the honest answer is usually "not yet". The sampling
distribution of a variance is wide: comparing two sectors of nine laps each,
one needs about **3.2x** the variance of the other before 95% confidence, and
at six laps each it is about **5.1x**. Those are not conservatism, they are
the F distribution, and `ratio_p` computes it rather than asserting it.

That bar is why this reports the ratio and the p together and refuses to rank
anything it cannot separate. A sector 1.4x another is not the answer to
anything.
"""
from __future__ import annotations

import math
import statistics as st
from dataclasses import dataclass

# Below this many laps a spread is not worth computing at all.
MIN_LAPS = 5
# The bar a ratio must clear to be called a difference.
ALPHA = 0.05
# **Above this, the spread has to be RESOLVED before it is read either way.**
#
# The first version of this said "suspect the measurement" and the driver
# corrected it: *don't dismiss as data error - Ludo should ask, not dismiss.
# The variability of data is data to investigate.* He is right, and the
# distinction matters more here than almost anywhere, because this is the
# threshold that decides whether a large signal gets looked at or waved away.
#
# Ten percent of a sector is seconds, which is larger than a driver is
# normally inconsistent by - so it is genuinely ambiguous, and both branches
# are worth having. It can be an instrument fault: 7% of laps in this archive
# TELEPORT and speed integration cannot see it, a sector model can straddle a
# pit entry, an out-lap can slip the filter. **Or it can be the most important
# finding on the screen** - a corner the car simply cannot be driven through
# the same way twice.
#
# So this flags "resolve me", never "ignore me", and the resolution is a
# measurement rather than a judgement: `analysis.distance.teleports(frames)`
# answers the instrument half directly.
RESOLVE_ABOVE_RELATIVE = 0.10
# Kept for callers written against the old name, which said the wrong thing.
IMPLAUSIBLE_RELATIVE = RESOLVE_ABOVE_RELATIVE


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta, Lentz's method."""
    tiny = 1e-30
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, 200):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-16:
            break
    return h


def _betai(a: float, b: float, x: float) -> float:
    """Regularised incomplete beta `I_x(a, b)`.

    Written out rather than imported: scipy is not a dependency of this app
    and adding one for a single distribution would be a poor trade. Verified
    against published F tables in `tests/test_spread.py`.
    """
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                     + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def ratio_p(var_high: float, n_high: int, var_low: float, n_low: int):
    """One-sided p that `var_high` exceeds `var_low`, or None.

    `None` where either side is too short to say anything, or where the
    smaller variance is zero - a division nobody can interpret rather than an
    infinite ratio dressed as certainty.
    """
    if n_high < MIN_LAPS or n_low < MIN_LAPS or var_low <= 0 or var_high <= 0:
        return None
    d1, d2 = n_high - 1, n_low - 1
    f = var_high / var_low
    x = d1 * f / (d1 * f + d2)
    return 1.0 - _betai(d1 / 2.0, d2 / 2.0, x)


def detrended_sd(values) -> float | None:
    """Standard deviation after a linear trend against lap order is removed.

    **Learning is not instability.** A sector getting quicker every lap has a
    large raw spread and a small residual one, and only the residual is about
    the car. `None` below `MIN_LAPS`, because a spread over four laps is not
    a spread.
    """
    series = [float(v) for v in values if v is not None]
    n = len(series)
    if n < MIN_LAPS:
        return None
    mean_x = (n - 1) / 2.0
    mean_y = sum(series) / n
    spread_x = sum((i - mean_x) ** 2 for i in range(n))
    slope = 0.0
    if spread_x > 0:
        slope = sum((i - mean_x) * (y - mean_y)
                    for i, y in enumerate(series)) / spread_x
    residual = [y - (mean_y + slope * (i - mean_x))
                for i, y in enumerate(series)]
    # One degree of freedom already spent on the trend.
    if n - 2 <= 0:
        return None
    return math.sqrt(sum(r * r for r in residual) / (n - 2))


def needs_resolving(spread) -> bool:
    """Is this spread large enough that it must be explained before it is used?

    **Not a verdict, and never a dismissal.** It is larger than a driver is
    normally inconsistent by, which makes it ambiguous rather than wrong: it
    is either an instrument fault or the most important finding on the screen,
    and those two demand opposite responses. `analysis.distance.teleports`
    settles the instrument half. See `RESOLVE_ABOVE_RELATIVE`.
    """
    return bool(spread is not None and spread.relative is not None
                and spread.relative > RESOLVE_ABOVE_RELATIVE)


# The old name presumed the answer. Kept so nothing breaks, deprecated in
# meaning: what it returns is a question, not a fault.
looks_like_a_fault = needs_resolving


@dataclass(frozen=True)
class Spread:
    """One part of the lap, and how repeatable the car is in it."""
    label: str
    laps: int
    mean: float
    raw_sd: float
    sd: float                       # detrended
    @property
    def relative(self) -> float | None:
        """Spread as a fraction of the part's own duration.

        Sectors are not the same length, so absolute spread ranks the long one
        first by construction. This is what makes them comparable at all.
        """
        return self.sd / self.mean if self.mean else None


def measure(label: str, values) -> Spread | None:
    series = [float(v) for v in values if v is not None]
    if len(series) < MIN_LAPS:
        return None
    sd = detrended_sd(series)
    if sd is None:
        return None
    return Spread(label=label, laps=len(series), mean=st.fmean(series),
                  raw_sd=st.pstdev(series), sd=sd)


def least_repeatable(spreads):
    """`(worst, steadiest, ratio, p)` or `None` where nothing can be said.

    **It compares the worst against the steadiest and nothing else.** Ranking
    three sectors from a sample this size invites reading an order into noise;
    the only question eight laps can answer is whether the extremes differ.
    """
    usable = [s for s in spreads if s is not None and s.relative is not None]
    if len(usable) < 2:
        return None
    order = sorted(usable, key=lambda s: s.relative or 0.0)
    steadiest, worst = order[0], order[-1]
    if steadiest is worst or not steadiest.sd:
        return None
    ratio = (worst.sd / worst.mean) / (steadiest.sd / steadiest.mean)
    # The F test is on variances of the raw times; the ratio reported is on
    # the relative spreads, which is what makes unequal-length parts
    # comparable. Both are stated so neither has to be inferred.
    p = ratio_p(worst.sd ** 2, worst.laps, steadiest.sd ** 2, steadiest.laps)
    return worst, steadiest, ratio, p
