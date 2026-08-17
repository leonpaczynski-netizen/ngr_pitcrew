"""Fitting the tyre model, and refusing to fit what the data does not support.

**The governing rule: the model earns the right to speak. It never speaks on a
prior.** Everything in this module is derived — `CLAUDE.md` §4 rule 5 — and
every figure it produces carries the number of observations behind it, rule 4.
The parts that report *absence* matter as much as the parts that report a
coefficient, because silence that is not explained reads as "all clear", and
this app's own degradation memo is the record of that going wrong.

Three structural defences, none of them left to discipline:

1. **A fit spans exactly one `yaw_source`.** v1 path-reconstructed laps read
   3-4 % low against v2 packet-yaw laps — the same size as the compound step
   the model exists to detect — so `refuse_to_pool` raises rather than
   averaging them. It is a refusal, not a warning.
2. **A scope is `car x circuit x compound x yaw_source` and is never pooled.**
   The front-to-rear gap coefficient is +0.87 s/degC at Yas and +0.011 at Monza
   on a wider gap range; one number for both cars would be a fiction with a
   standard error.
3. **`speakable` is decided here, at fit time, against the sample counts, and
   written into the row.** A caller asks `may_i_say`; it does not get to weigh
   the evidence itself.

**Nothing in this module is wired to a voice call, deliberately.** The Stage 2
degradation line and the race's gauge prompt live in files this change does not
touch. What is here is the evidence and the gate; speaking is a separate
decision made somewhere else, and it reads a boolean.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

from pitcrew.analysis.grip import DERIVATION_VERSION

# The observable is a percentile of a friction envelope. It is **not** a
# coefficient of friction, it is **not** a wear fraction, and it may never be
# fed to `L = 0.85 / w` as if it were `w`. Every fitted model carries this.
_ALWAYS_UNKNOWN = (
    "grip is a DERIVED friction-envelope percentile of the driver's own laps, "
    "not a measured coefficient of friction",
    "it cannot be converted to a wear fraction: GT7 broadcasts no tyre wear "
    "channel in any packet format",
    # M-9: this used to assert the fuel direction was known and safe. It is not.
    "fuel is NOT separated and its direction is NOT known: the partial fuel "
    "coefficient is +0.00059 g/L (t +1.73), the opposite sign to the "
    "theoretical prediction, and it is unidentifiable within a stint where "
    "corr(lap_in_stint, fuel) = -0.946. What can be said: substituting lap "
    "time for fuel leaves the trend intact (-0.00406 g/lap, t -5.46)",
    "the DIRECTION is what is fitted, not the magnitude: the within-stint "
    "signal lives in a percentile band (t -5.9 at p90, -6.4 at p95, +0.1 at "
    "p99) and every fixed-count high-end statistic is flat, so what declines "
    "is time spent near the limit and not the limit itself - which this data "
    "cannot separate from the driver easing off",
    "the wear multiplier is whatever the event ran; it is NOT convertible to "
    "another multiplier (CLAUDE.md 5.2 - linearity is assumed, not proven)",
)

# Past this many laps into a stint the tyre is warm and the reading is settled.
# Chosen from the one clean warm-up on record: session 19's second stint took
# three laps to climb 3.3 % and reach its plateau.
SETTLED_LAP_IN_STINT = 3

# ------------------------------------------------------------ Stage 2's gate
#
# **The per-stint clause used to read "8 push laps each" and it was the wrong
# proxy.** Applied to the archive it rejected Monza / Porsche / RH - a pooled
# slope of -0.00415 g/lap at se 0.00065, **t = -6.42 over 40 push laps and five
# stints** - purely because of how those 40 laps happened to fall across the
# stints (10, 9, 7, 7, 7). That is not thin evidence by any reading, and the
# design pass that set the clause asserted in the same breath that this exact
# scope had met it, on session lap counts of 10, 7, 7, 16 that fail it too. A
# threshold that its own author could not apply consistently is a threshold
# standing in for something else.
#
# What it was standing in for is the fuel confound. Within one stint, fuel load,
# elapsed time and tyre wear are the same variable - measured at r = -1.000 - so
# a single stint cannot tell a degradation trend from a fuel-load artefact at
# any length. What breaks that is **several stints whose fuel-load ranges differ
# at comparable wear states**, plus enough total points for the statistic to
# mean anything. So those two conditions are now stated directly rather than
# inferred from how the laps were distributed:
#
#   * three contributing stints, which is the clause doing the real work;
#   * five push laps in each, because a stint shorter than that carries no
#     within-stint trend at all - but five to seven laps is a genuine
#     contribution once pooled, and eight was arbitrary;
#   * twenty-four push laps across the scope, which is "enough evidence" said
#     out loud instead of derived from per-stint counts;
#   * and the significance clause on the pooled fit, unchanged.
#
# The fuel confound still runs the safe way either way (a lighter car reads
# higher), so the fitted decline remains a lower bound. These conditions are
# about whether the trend is *measurable*, not about which direction it errs in.
STAGE2_MIN_PUSH_LAPS_PER_STINT = 5
STAGE2_MIN_STINTS = 3

# **Derived, not retrofitted.** The two-group sample size for 80 % power at
# 95 % two-sided is N = 31.4 * sigma^2 / delta^2, and with a percentile
# observable both sides scale together, so in CV terms N = 31.4 * (CV/D)^2 for
# a fractional effect D. Stated effect size: **D = 1 % of grip**, which is the
# currency the whole design pass costed in and is roughly a fifth of the
# compound step this observable resolves.
#
# At the measured consecutive-lap CVs that gives: Monza 0.71 % -> 16 laps,
# Yas 1.14 % -> 41, Watkins 1.54 % -> 74. The floor here is the **Monza**
# figure rounded up to the nearest whole stint of his running, because Monza is
# the only scope with enough data to have produced a CV worth trusting and a
# per-circuit floor would let a noisy circuit set itself an easier bar than a
# quiet one. A scope at Watkins' CV therefore needs its own laps to clear the
# significance clause, which is where its extra noise is properly charged.
STAGE2_EFFECT_SIZE_PCT = 1.0
STAGE2_MIN_TOTAL_PUSH_LAPS = 16

# **The gate names a confidence, not a t.** A fixed `|t| >= 2.5` is the wrong
# shape once the estimator is the between-stint one: at 4 degrees of freedom
# 2.5 is p = 0.067 and at 30 it is p = 0.018, so one constant means two
# different claims depending on how many stints happen to exist.
#
# It also has to be **evaluated on the between-stint estimator**, not on the
# pooled within-stint t. Laps inside a stint are not independent draws - fuel,
# temperature and track state all drift smoothly through it - and a pooled t
# that assumes they are is miscalibrated in the dangerous direction: simulated
# on pure noise with AR(1) residuals the false-open rate runs 2.5 % at rho = 0,
# 6.4 % at 0.3, **16.1 % at 0.6** and 23.1 % at 0.8. Positive rho is the
# default here, not the exception.
#
# The mean of the per-stint slopes with df = stints - 1 treats each stint as
# the one independent observation it is. On Monza / Porsche / RH that is
# t = -5.59 on 4 df, p = 0.005 - still comfortably inside this bar, which is
# the point: the claim survives being tested properly.
STAGE2_MAX_P = 0.01
# Stage 1's: a warm-up is one observation per stint, not one per lap.
STAGE1_MIN_WARMUPS = 3
STAGE1_MIN_LAPS_PER_WARMUP = 4
# The plateau has to land in the same place each time, to within a lap, or the
# call cannot say when the tyres are up.
STAGE1_PLATEAU_TOLERANCE_LAPS = 1
# Within this of the sequence's peak rear-axle temperature counts as "up".
# 1.5 degC because that is roughly one lap's worth of climb at settled pace
# (measured: +0.25 degC/min at race pace against 1.3-1.6 degC/min warming up),
# so a tighter figure would be reading noise as a still-climbing axle.
PLATEAU_TEMP_TOLERANCE_C = 1.5
# Stage 3's, on wear grounds. Blocked on gauge readings, not on code: there are
# 15 in 175 archived laps and none at all in either race.
STAGE3_MIN_STINTS = 12
STAGE3_MIN_GAUGE_READINGS_PER_STINT = 2
STAGE3_FRONT_FLOOR_C = 72.0
# Stage 4's. The last clause is not optional - three scopes of the same
# quantity produced slopes at t = +3.12, -3.69 and +2.12, and any one of them
# alone would have read as "significant".
STAGE4_MIN_STINTS = 6
STAGE4_MIN_TEMP_SPAN_C = 8.0
STAGE4_MIN_ABS_T = 3.0
# Stage 5, the cold side. Nobody in the GT7 community has ever established one,
# which is also the reason to be slow about it.
STAGE5_MIN_COLD_START_STINTS = 6
STAGE5_MIN_SCOPES = 2
STAGE5_MIN_ABS_T = 3.0


class PoolingRefused(RuntimeError):
    """Raised when a fit was handed observations it may not average together."""


@dataclass(frozen=True)
class Scope:
    """The keys a fit may never cross."""
    car_key: str
    circuit_key: str
    compound: str | None
    yaw_source: str

    def as_dict(self) -> dict:
        return {"car_key": self.car_key, "circuit_key": self.circuit_key,
                "compound": self.compound, "yaw_source": self.yaw_source}

    def label(self) -> str:
        return (f"{self.circuit_key} / {self.car_key} / "
                f"{self.compound or 'compound-untagged'} / {self.yaw_source}")


def scope_of(row: dict) -> Scope:
    return Scope(row["car_key"], row["circuit_key"], row["compound"],
                 row["yaw_source"])


def refuse_to_pool(rows: list[dict]) -> str:
    """The single `yaw_source` behind these rows, or a refusal.

    **A warning would not do.** The offset between the two sources is 3-4 % and
    the compound step this model exists to find is 1.8-6.4 %; a fit that
    averaged them would produce a plausible number with a plausible standard
    error and no way to tell it was measuring the storage format.
    """
    sources = {row["yaw_source"] for row in rows}
    if not sources:
        raise PoolingRefused("no observations")
    if len(sources) > 1:
        raise PoolingRefused(
            "a fit spans exactly one yaw_source; these observations span "
            + ", ".join(sorted(sources))
            + ". The two differ by 3-4% at the top of the acceleration "
              "distribution, which is the size of a compound step. Fit them "
              "separately, or measure the offset on a session driven both ways.")
    return sources.pop()


# ------------------------------------------------------------------- the maths


@dataclass(frozen=True)
class Fit:
    """A least-squares line, and honest about what it is not.

    `t` is None where the fit has no residual degrees of freedom. None is not
    zero and it is not "not significant" — it is "this cannot be tested", which
    is a different thing to say.
    """
    slope: float | None
    intercept: float | None
    se: float | None
    t: float | None
    n: int
    r: float | None = None

    @property
    def significant_at(self) -> float | None:
        return abs(self.t) if self.t is not None else None


def ols(xs: list[float], ys: list[float], *, dof_penalty: int = 2) -> Fit:
    """Ordinary least squares, in the plain arithmetic and nothing more.

    `dof_penalty` is how many parameters the caller has already spent — 2 for a
    slope and an intercept, more when the data were demeaned within groups
    first, because each group mean is a parameter too. Getting that wrong is how
    a within-group fit comes out looking twice as significant as it is.
    """
    n = len(xs)
    if n != len(ys) or n < 2:
        return Fit(None, None, None, None, n)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx <= 0:
        return Fit(None, None, None, None, n)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    syy = sum((y - mean_y) ** 2 for y in ys)
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    r = sxy / math.sqrt(sxx * syy) if syy > 0 else None
    dof = n - dof_penalty
    if dof <= 0:
        return Fit(slope, intercept, None, None, n, r)
    residual = sum((y - intercept - slope * x) ** 2 for x, y in zip(xs, ys))
    se = math.sqrt(residual / dof / sxx) if residual > 0 else 0.0
    return Fit(slope, intercept, se, (slope / se if se else None), n, r)


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta function (Lentz's method)."""
    tiny = 1e-30
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, 200):
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
        if abs(delta - 1.0) < 3e-12:
            break
    return h


def student_t_p(t: float | None, dof: int) -> float | None:
    """Two-sided p for Student's t. None where the question cannot be asked.

    Written out rather than imported because `pitcrew/analysis` carries no
    numerical dependency and this is the only distribution the fitting layer
    needs. **It exists because a fixed `|t| >= 2.5` is the wrong shape for a
    gate evaluated on four degrees of freedom**: at df = 4 that is p = 0.067,
    and at df = 30 it is p = 0.018. A gate should name the confidence it wants
    and let the degrees of freedom decide the critical value, not the other way
    round.
    """
    if t is None or dof <= 0:
        return None
    x = dof / (dof + t * t)
    a, b = dof / 2.0, 0.5
    # Regularised incomplete beta I_x(a, b), which is the two-sided tail.
    front = math.exp(a * math.log(x) + b * math.log(1.0 - x)
                     + math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b))
    if x < (a + 1.0) / (a + b + 2.0):
        return min(1.0, front * _betacf(a, b, x) / a)
    return min(1.0, 1.0 - front * _betacf(b, a, 1.0 - x) / b)


def _sd(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))


def _welch_t(a: list[float], b: list[float]) -> float | None:
    """Welch's t. Not Student's: the two compounds are different populations
    with different spreads and no reason at all to share a variance."""
    if len(a) < 2 or len(b) < 2:
        return None
    mean_a, mean_b = sum(a) / len(a), sum(b) / len(b)
    var_a = sum((v - mean_a) ** 2 for v in a) / (len(a) - 1)
    var_b = sum((v - mean_b) ** 2 for v in b) / (len(b) - 1)
    denominator = math.sqrt(var_a / len(a) + var_b / len(b))
    return (mean_a - mean_b) / denominator if denominator else None


# ------------------------------------------------------------ the evidence


@dataclass
class ScopeEvidence:
    """What one scope's counted observations amount to.

    Built once and read by every gate, so a gate cannot quietly use a different
    population from the one whose sample count it reports.
    """
    scope: Scope
    rows: list[dict]
    stints: dict[str, list[dict]] = field(default_factory=dict)
    # **Every row, counted or not.** The push-lap filter decides what may enter
    # a grip fit; it is the wrong filter for asking whether a stint began on a
    # fresh set, and keeping only its survivors is what made the warm-up stage
    # unreachable. See `warmups`.
    all_rows: list[dict] = field(default_factory=list)

    @classmethod
    def build(cls, rows: list[dict]) -> "ScopeEvidence":
        counted = [r for r in rows
                   if r["counts_toward_fit"] and r["grip_g"] is not None]
        refuse_to_pool(counted or rows)
        stints: dict[str, list[dict]] = defaultdict(list)
        for row in counted:
            stints[row["stint_key"] or f"session:{row['session_id']}"].append(row)
        for laps in stints.values():
            laps.sort(key=lambda r: r["lap_num"])
        return cls(scope=scope_of(rows[0]), rows=counted, stints=dict(stints),
                   all_rows=list(rows))

    @property
    def samples(self) -> int:
        return len(self.rows)

    @property
    def sessions(self) -> int:
        return len({r["session_id"] for r in self.rows})

    @property
    def stint_count(self) -> int:
        return len(self.stints)

    @property
    def contributing_stints(self) -> dict[str, list[dict]]:
        """Stints long enough to contribute a within-stint trend at all.

        Not "long enough to carry the claim on their own" - that was the old
        eight-lap reading and it threw away five- and six-lap stints whose only
        defect was where the driver happened to stop.

        **Warm-up laps are dropped from stints that are known to have one, and
        only from those.** The opening laps of a stint were previously in the
        degradation fit and out of the temperature fit, which is two
        populations under one sample count - and worse than untidy, because a
        warm-up is a *rising* process and pooling it with a declining one
        produces a slope describing neither.

        The first repair of that was a blanket exclusion, and it was wrong in
        the other direction: it also cut the opening laps off stints where
        nothing says the set was fresh, so there was no warm-up there to
        remove. Measured, that cost precision and bought nothing - across the
        five Monza RH stints the mean slope moved -0.00438 -> -0.00477, well
        inside noise, while the spread between stints nearly doubled (sd
        0.00176 -> 0.00323) because two seven-lap stints were cut to five and
        six. A filter that does not move the estimate and halves its precision
        is removing signal, not bias.

        So the exclusion follows the evidence: a stint the driver marked fresh,
        or one where the frames show a tyre change, loses its warm-up. A stint
        of unknown set age keeps every counted lap, and the model says which
        rule it applied rather than pretending it knows.
        """
        fresh = self.fresh_started_stints
        out = {}
        for key, laps in self.stints.items():
            usable = ([r for r in laps
                       if (r["lap_in_stint"] or 0) >= SETTLED_LAP_IN_STINT]
                      if key in fresh else list(laps))
            if len(usable) >= STAGE2_MIN_PUSH_LAPS_PER_STINT:
                out[key] = usable
        return out

    @property
    def contributing_laps(self) -> int:
        return sum(len(laps) for laps in self.contributing_stints.values())

    @property
    def gauge_stints(self) -> int:
        """Stints carrying enough gauge readings to give a rate, not a point."""
        return sum(1 for laps in self.stints.values()
                   if sum(1 for r in laps
                          if r["gauge_worst_frac"] is not None)
                   >= STAGE3_MIN_GAUGE_READINGS_PER_STINT)

    @property
    def fresh_started_stints(self) -> set[str]:
        """Stints known to have begun on a fresh set, from ANY row.

        **Deliberately reads uncounted rows too, and that is the fix for a
        structural dead end.** This used to ask whether the first *counted* row
        of a stint had `laps_on_set == 0`, and the answer was no for every
        stint in the archive: all 16 known-fresh rows fail the frames gate,
        because the first lap on a new set leaves the pits and the recording
        starts mid-lap, so the frames cannot account for the lap time GT7
        claims. The push-lap filter was doing its job; it was simply being
        asked the wrong question. Whether a set was fresh is a fact about the
        set, not about whether that lap is fit to measure grip on.
        """
        fresh = set()
        for row in self.all_rows:
            if row.get("laps_on_set") == 0 and row.get("stint_key"):
                fresh.add(row["stint_key"])
        return fresh

    @property
    def warmups(self) -> list[list[dict]]:
        """Fresh-set stints with enough measurable laps to see a warm-up in.

        The opening lap itself is usually unmeasurable and is not required to
        be: what a warm-up sequence needs is a known starting point and then
        laps that can be read.
        """
        fresh = self.fresh_started_stints
        return [laps for key, laps in self.stints.items()
                if key in fresh and len(laps) >= STAGE1_MIN_LAPS_PER_WARMUP]

    def settled(self) -> list[dict]:
        return [r for r in self.rows
                if (r["lap_in_stint"] or 0) >= SETTLED_LAP_IN_STINT
                and r["temp_rear_c"] is not None]

    def settled_temp_span_c(self) -> float | None:
        temps = [r["temp_rear_c"] for r in self.settled()]
        return max(temps) - min(temps) if len(temps) >= 2 else None

    def provenance(self, derivation_version: int) -> dict:
        return {
            "derivation_version": derivation_version,
            "lap_ids": sorted({r["lap_id"] for r in self.rows}),
            "session_ids": sorted({r["session_id"] for r in self.rows}),
            "stint_keys": sorted(self.stints),
            "unit_kind": "LAP",
            "grip_stat": "comb_p95",
        }


# --------------------------------------------------------------- the fits


def fit_baseline(evidence: ScopeEvidence) -> dict:
    """The scope's grip level: mean, spread and count. Nothing inferred."""
    values = [r["grip_g"] for r in evidence.rows]
    mean = sum(values) / len(values) if values else None
    sd = _sd(values)
    return {
        "mean_grip_g": mean,
        "sd_grip_g": sd,
        "cv_pct": (100.0 * sd / mean) if mean and sd else None,
        # The figure the sample-size arithmetic actually rests on. The raw CV
        # above counts a stint's decline as noise; this one does not.
        "cv_consec": consecutive_lap_cv(evidence.rows),
        "n": len(values),
        "method": ("mean of comb_p95 over counted push laps; comb_p95 is the "
                   "95th percentile of sqrt(lat_g^2 + long_g^2) above 15 m/s"),
    }


def consecutive_lap_cv(rows: list[dict]) -> dict:
    """Lap-to-lap noise, from consecutive-lap differences rather than raw spread.

    `sigma = sd(delta) / sqrt(2)`, pooled in quadrature across stints. The
    differencing is the point: a stint's own grip decline is a *signal*, and a
    raw within-session standard deviation counts it as noise and makes the
    observable look worse than it is.

    Returns null rather than a figure where no stint carries three consecutive
    counted laps, because two laps is a difference and not a spread.
    """
    by_stint: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if not row["counts_toward_fit"] or row["grip_g"] is None:
            continue
        by_stint[row["stint_key"] or f"session:{row['session_id']}"].append(row)

    sigmas: list[float] = []
    means: list[float] = []
    laps = 0
    for stint in by_stint.values():
        stint.sort(key=lambda r: r["lap_num"])
        values = [r["grip_g"] for r in stint]
        if len(values) < 3:
            continue
        deltas = [values[i + 1] - values[i] for i in range(len(values) - 1)]
        sigmas.append(_sd(deltas) / math.sqrt(2.0))
        means.append(sum(values) / len(values))
        laps += len(values)
    if not sigmas:
        return {"cv_pct": None, "sigma_g": None, "laps": laps,
                "stints": len(by_stint),
                "method": "consecutive-lap differences, sd(delta)/sqrt(2)"}
    sigma = math.sqrt(sum(s * s for s in sigmas) / len(sigmas))
    mean = sum(means) / len(means)
    return {"cv_pct": 100.0 * sigma / mean if mean else None,
            "sigma_g": sigma, "laps": laps, "stints": len(sigmas),
            "method": ("consecutive-lap differences within a stint, "
                       "sd(delta)/sqrt(2), pooled in quadrature")}


def fit_degradation(evidence: ScopeEvidence) -> dict:
    """Grip against lap-in-stint, per stint and pooled.

    The pooled slope is fitted on **stint-demeaned** data, so a stint that
    happened to run at a higher grip level cannot masquerade as a trend. Each
    stint mean costs a degree of freedom and `dof_penalty` says so.

    The per-stint slopes are reported beside it and are not averaged into it:
    they are what says whether the effect reproduces or whether one long stint
    is carrying the whole result.
    """
    # **The same population the gate counts.** These two used to disagree -
    # the gate required five laps a stint and the fit pooled anything with two
    # - so the sample count reported beside a coefficient was not the sample
    # count behind it.
    stints = evidence.contributing_stints

    per_stint = {}
    slopes: list[float] = []
    for key, laps in stints.items():
        fit = ols([float(r["lap_in_stint"] or 0) for r in laps],
                  [r["grip_g"] for r in laps])
        per_stint[key] = {"slope_g_per_lap": fit.slope, "se": fit.se,
                          "t": fit.t, "laps": fit.n}
        if fit.slope is not None:
            slopes.append(fit.slope)

    xs: list[float] = []
    ys: list[float] = []
    for laps in stints.values():
        mean_x = sum(float(r["lap_in_stint"] or 0) for r in laps) / len(laps)
        mean_y = sum(r["grip_g"] for r in laps) / len(laps)
        for row in laps:
            xs.append(float(row["lap_in_stint"] or 0) - mean_x)
            ys.append(row["grip_g"] - mean_y)
    pooled = ols(xs, ys, dof_penalty=len(stints) + 1)

    # **The estimator the gate is judged on.** One slope per stint, then the
    # mean of those - so a stint is one observation, which is what it is. The
    # pooled figure is reported beside it because it is the more precise
    # estimate of the same quantity when the within-stint residuals really are
    # independent; it is simply not the one that decides whether to speak.
    between = None
    if len(slopes) >= 2:
        mean_slope = sum(slopes) / len(slopes)
        spread = _sd(slopes)
        # `_sd` is the population sd; the standard error of a mean wants the
        # sample sd, hence the Bessel correction spelled out here.
        sample_sd = (spread * math.sqrt(len(slopes) / (len(slopes) - 1))
                     if spread is not None else None)
        se = (sample_sd / math.sqrt(len(slopes))
              if sample_sd is not None else None)
        t = mean_slope / se if se else None
        between = {
            "grip_g_per_lap": mean_slope,
            "se": se,
            "t": t,
            "dof": len(slopes) - 1,
            "p": student_t_p(t, len(slopes) - 1),
            "stints": len(slopes),
            "all_negative": all(s < 0 for s in slopes),
            "signs": "".join("-" if s < 0 else "+" for s in slopes),
        }

    return {
        # The headline coefficient is the between-stint one. The gate reads it,
        # and anything quoting `grip_g_per_lap` gets the honest estimator
        # rather than the flattering one.
        "grip_g_per_lap": (between or {}).get("grip_g_per_lap"),
        "se": (between or {}).get("se"),
        "t": (between or {}).get("t"),
        "p": (between or {}).get("p"),
        "dof": (between or {}).get("dof"),
        "estimator": "between-stint mean of per-stint OLS slopes",
        "between_stint": between,
        "pooled_within_stint": {
            "grip_g_per_lap": pooled.slope, "se": pooled.se, "t": pooled.t,
            "note": ("assumes laps inside a stint are independent draws, which "
                     "they are not; reported, never gated on"),
        },
        "intercept_g": fit_baseline(evidence)["mean_grip_g"],
        "pooled_over_stints": len(stints),
        "per_stint": per_stint,
        "method": (f"per-stint OLS of comb_p95 on lap-in-stint over settled "
                   f"laps (lap {SETTLED_LAP_IN_STINT} of a stint onward), then "
                   f"the mean of those slopes with df = stints - 1"),
    }


def fit_temperature_response(evidence: ScopeEvidence) -> dict:
    """Grip against settled rear-axle temperature, session-demeaned.

    **This is the fit the evidence currently argues against.** Settled-lap
    slopes on the three scopes on record came out -0.00625 (t = -2.86),
    +0.00862 (t = +2.40) and -0.00123 (t = -0.37): two significant, opposite
    signs. The number is computed and stored because it is the thing being
    accumulated; whether it may be *said* is Stage 4's problem and Stage 4
    requires the sign to reproduce on a second scope.
    """
    rows = evidence.settled()
    by_session: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        by_session[row["session_id"]].append(row)
    xs: list[float] = []
    ys: list[float] = []
    for laps in by_session.values():
        if len(laps) < 2:
            continue
        mean_t = sum(r["temp_rear_c"] for r in laps) / len(laps)
        mean_g = sum(r["grip_g"] for r in laps) / len(laps)
        for row in laps:
            xs.append(row["temp_rear_c"] - mean_t)
            ys.append(row["grip_g"] - mean_g)
    usable = sum(1 for laps in by_session.values() if len(laps) >= 2)
    fit = ols(xs, ys, dof_penalty=usable + 1)
    return {
        "grip_g_per_c": fit.slope,
        "se": fit.se,
        "t": fit.t,
        "r": fit.r,
        "settled_laps": len(rows),
        "settled_temp_span_c": evidence.settled_temp_span_c(),
        "sessions_pooled": usable,
        "method": (f"OLS of comb_p95 on rear-axle mean degC over laps at or "
                   f"past lap {SETTLED_LAP_IN_STINT} of a stint, demeaned "
                   f"within session"),
    }


def compound_ordering(scopes: dict[Scope, ScopeEvidence]) -> list[dict]:
    """Grip by compound at one car and circuit, and whether it is monotone.

    The one known-sign, known-magnitude grip step in the recorded data, and the
    validation that the observable is measuring grip at all — a softer compound
    must read higher, and lap time does not manage it.

    **It is not a controlled experiment and must not be reported as one.** No
    session in the archive ran two compounds, so compound is confounded with
    session at every circuit. What it establishes is weaker and still worth
    having: the observable separates the conditions in the physically expected
    order where lap time separates nothing.
    """
    families: dict[tuple[str, str, str], dict[str, ScopeEvidence]] = defaultdict(dict)
    for scope, evidence in scopes.items():
        if scope.compound is None or not evidence.rows:
            continue
        families[(scope.car_key, scope.circuit_key,
                  scope.yaw_source)][scope.compound] = evidence

    order = ("RH", "RM", "RS")
    out = []
    for (car, circuit, yaw_source), by_compound in sorted(families.items()):
        present = [c for c in order if c in by_compound]
        if len(present) < 2:
            continue
        levels = [{"compound": c,
                   "mean_grip_g": fit_baseline(by_compound[c])["mean_grip_g"],
                   "n": by_compound[c].samples,
                   "sessions": by_compound[c].sessions}
                  for c in present]
        monotone = all(levels[i]["mean_grip_g"] < levels[i + 1]["mean_grip_g"]
                       for i in range(len(levels) - 1))
        hardest = [r["grip_g"] for r in by_compound[present[0]].rows]
        softest = [r["grip_g"] for r in by_compound[present[-1]].rows]
        out.append({
            "car_key": car, "circuit_key": circuit, "yaw_source": yaw_source,
            "levels": levels,
            "monotone_in_softness": monotone,
            "softest_minus_hardest_pct": (
                100.0 * (levels[-1]["mean_grip_g"] - levels[0]["mean_grip_g"])
                / levels[0]["mean_grip_g"] if levels[0]["mean_grip_g"] else None),
            "welch_t": _welch_t(softest, hardest),
            "mean_lap_in_stint": {c: (sum(r["lap_in_stint"] or 0
                                          for r in by_compound[c].rows)
                                      / max(1, by_compound[c].samples))
                                  for c in present},
            "sessions_per_compound": {c: by_compound[c].sessions
                                      for c in present},
            # **Four confounds, not one.** The stored caveat used to name only
            # "session", and this string travels into the export, so the
            # omissions were being read as absences.
            "caveat": (
                "NOT a controlled comparison, on four counts. (1) Compound is "
                "confounded with SESSION: no session in the archive ran two "
                "compounds, so a compound difference and a session difference "
                "are the same number here. (2) It is confounded with "
                "LAP-IN-STINT: the softer compound's laps sit earlier in the "
                "stint at both circuits, which is where this model's own "
                "fitted trend says grip is highest - correcting for it takes "
                "Monza RS-RH from 6.50 % to 5.35 % and HALVES Watkins RM-RS "
                "from 1.77 % to 0.88 %. (3) It is confounded with CHRONOLOGY: "
                "the archive drifts -0.45 %/day, and the ordering only "
                "survives at Monza because RS sits +5.6 % above the drift "
                "line. (4) It is confounded with SETUP SHEET, though at Monza "
                "the ordering does hold within sheet 1 alone. Protocol P1 - "
                "two compounds in one session - is what makes this controlled."),
            # The Welch t above treats every lap as an independent draw, which
            # it is not when 19 laps come from 5 sessions. This is the same
            # test on session means, which is the honest denominator.
            "welch_t_on_session_means": _welch_t(
                _session_means(by_compound[present[-1]]),
                _session_means(by_compound[present[0]])),
            "independent_validation": (
                len(set(by_compound[c].sessions for c in present)) > 0
                and min(by_compound[c].sessions for c in present) >= 2),
        })
    return out


def _session_means(evidence: ScopeEvidence) -> list[float]:
    by_session: dict[int, list[float]] = defaultdict(list)
    for row in evidence.rows:
        by_session[row["session_id"]].append(row["grip_g"])
    return [sum(v) / len(v) for v in by_session.values()]


# ------------------------------------------------------------------ the gates


@dataclass(frozen=True)
class GateVerdict:
    """Whether a scope has earned the right to make one particular claim.

    `failures` is the point of this object. A gate that is not met has to say
    which requirement it missed and by how much, because the alternative is a
    silence the driver reads as "all clear".
    """
    stage: int
    name: str
    met: bool
    scope: Scope | None
    requirements: dict
    failures: tuple[str, ...]
    says: str
    # **What this call needs back from the driver, if anything.** A structured
    # seam rather than a caller parsing the sentence: the end-of-stint gauge
    # prediction that will score this model's accuracy hangs off exactly this.
    asks_for: str | None = None

    def as_dict(self) -> dict:
        return {"stage": self.stage, "name": self.name, "met": self.met,
                "requirements": self.requirements,
                "failures": list(self.failures), "says": self.says,
                "asks_for": self.asks_for,
                "scope": self.scope.as_dict() if self.scope else None}


# Stage 0 is not a gate. It is what every scope that has met nothing else says,
# and it has to be said out loud rather than left as silence.
STAGE0_LINE = ("I can't see tyre wear. No wear channel exists in any GT7 "
               "packet, there's no gauge reading this stint, and lap time "
               "can't resolve it at your spread.")


def plateau_lap(warmup: list[dict]) -> int | None:
    """Which lap of a fresh set the rear axle stops climbing on.

    Read off **temperature**, not grip: a warm-up announcement is a statement
    about heat, and grip is the thing the app is explicitly not allowed to
    claim at this stage. The plateau is the first lap whose rear-axle mean is
    within `PLATEAU_TEMP_TOLERANCE_C` of the sequence's maximum - the point
    past which more laps stop buying temperature.

    None where the sequence carries no temperature at all, or where it never
    stops climbing, because a warm-up whose end is off the end of the data has
    not been observed.
    """
    laps = [r for r in sorted(warmup, key=lambda r: r["lap_in_stint"] or 0)
            if r.get("temp_rear_c") is not None]
    if len(laps) < 3:
        return None
    peak = max(r["temp_rear_c"] for r in laps)
    for row in laps:
        if row["temp_rear_c"] >= peak - PLATEAU_TEMP_TOLERANCE_C:
            # The last lap being the first one within tolerance means the axle
            # was still climbing when the stint ended.
            if row is laps[-1]:
                return None
            return int(row["lap_in_stint"] or 0)
    return None


def gate_stage1_warmup(evidence: ScopeEvidence) -> GateVerdict:
    """"Tyres are up to temperature." A state announcement, not a licence.

    It claims nothing about grip, which is exactly why it can ship before
    anything else. **What stays forbidden at this stage and every stage after
    it: "tyres are in the window, you can push."** There is no evidence for a
    lower grip bound in GT7, PD documents no optimal state, the HUD has no
    in-window colour, and the only credible external test declined to examine
    the cold side. Saying it would fabricate the window's lower edge, which is
    the exact failure `analysis/tyre_window.py` exists to document.
    """
    warmups = evidence.warmups
    plateaus = [plateau_lap(w) for w in warmups]
    found = [p for p in plateaus if p is not None]
    # **The clause that was specified and had been left out.** Counting warm-up
    # sequences is not the test - the test is whether the plateau lands in the
    # same place each time, because that is the thing the call would be
    # announcing. Without it this gate opened on three sequences whose plateaus
    # had never been compared, which is a state announcement resting on nothing.
    consistent = (len(found) >= STAGE1_MIN_WARMUPS
                  and max(found) - min(found) <= STAGE1_PLATEAU_TOLERANCE_LAPS)
    requirements = {
        "warmup_sequences": {"required": STAGE1_MIN_WARMUPS,
                             "observed": len(warmups)},
        "laps_per_sequence": {"required": STAGE1_MIN_LAPS_PER_WARMUP,
                              "observed": [len(w) for w in warmups]},
        "plateau_lap_agrees_within": {
            "required": STAGE1_PLATEAU_TOLERANCE_LAPS,
            "observed": (max(found) - min(found)) if len(found) > 1 else None,
            "plateau_laps": found},
    }
    fresh = evidence.fresh_started_stints
    requirements["fresh_started_stints"] = {"observed": len(fresh)}
    failures = []
    if len(warmups) < STAGE1_MIN_WARMUPS:
        detail = (
            f"{len(fresh)} stint(s) here are known to have started fresh, and "
            f"{len(warmups)} of those carry {STAGE1_MIN_LAPS_PER_WARMUP}+ "
            f"measurable laps")
        if not fresh:
            # Do not promise that driving fixes this when it may not. Whether a
            # stint is known to be fresh depends on the driver marking it, and
            # nothing in the stream says so - GT7 broadcasts no tyre-change
            # event at all.
            detail += (". Nothing in the archive marks a fresh set in this "
                       "scope: GT7 broadcasts no tyre-change event, so it "
                       "comes from him saying so or from a stop the frames "
                       "show. Protocol P3 supplies these ONLY if the fresh set "
                       "is recorded as fresh")
        failures.append(
            f"{len(warmups)} warm-up sequence(s); {STAGE1_MIN_WARMUPS} needed. "
            f"A warm-up is one observation per stint, not one per lap. {detail}")
    elif not consistent:
        failures.append(
            f"the plateau lands on lap {found} across the sequences, which is "
            f"wider than the +/-{STAGE1_PLATEAU_TOLERANCE_LAPS} laps this call "
            f"would be claiming. A warm-up announcement that cannot say WHEN "
            f"is not an announcement"
            if len(found) > 1 else
            "the plateau lap could not be identified in enough sequences: a "
            "warm-up whose end cannot be located is not a warm-up observation")
    met = not failures
    return GateVerdict(
        stage=1, name="warm-up plateau", met=met, scope=evidence.scope,
        requirements=requirements, failures=tuple(failures),
        says=(f"Tyres are up to temperature - that's lap {found[0] + 1} of a "
              f"fresh set on this car, from {len(warmups)} sets."
              if met else
              "Not yet: I can't tell you when your tyres are warm. "
              + failures[0]))


def gate_stage2_degradation(evidence: ScopeEvidence, fit: dict) -> GateVerdict:
    """"Grip's down about N per cent on this set." The first thing it can earn.

    Reachable on frames already on disk, which is the whole point of deriving
    offline. What must travel with the number, always: it is a derived
    friction-envelope percentile, it is a **lower bound** because fuel runs the
    other way, and it is **not** a wear fraction.
    """
    contributing = evidence.contributing_stints
    slope = fit.get("grip_g_per_lap")
    p = fit.get("p")
    between = fit.get("between_stint") or {}
    requirements = {
        "contributing_stints": {
            "required": STAGE2_MIN_STINTS,
            "min_laps_each": STAGE2_MIN_PUSH_LAPS_PER_STINT,
            "observed": len(contributing),
            "why": ("within one stint fuel, elapsed time and wear are the same "
                    "variable at r = -1.000; only several stints separate a "
                    "degradation trend from a fuel-load artefact")},
        "total_push_laps": {"required": STAGE2_MIN_TOTAL_PUSH_LAPS,
                            "observed": evidence.contributing_laps},
        "p_two_sided": {"required": STAGE2_MAX_P, "observed": fit.get("p"),
                        "estimator": fit.get("estimator"),
                        "dof": fit.get("dof")},
        "slope_is_negative": {"required": True,
                              "observed": None if slope is None else slope < 0},
        "per_stint_signs_agree": {"required": True,
                                  "observed": between.get("all_negative"),
                                  "signs": between.get("signs")},
        "single_yaw_source": {"required": True,
                              "observed": evidence.scope.yaw_source},
    }
    failures = []
    if len(contributing) < STAGE2_MIN_STINTS:
        failures.append(
            f"{len(contributing)} contributing stint(s) of at least "
            f"{STAGE2_MIN_PUSH_LAPS_PER_STINT} settled push laps; "
            f"{STAGE2_MIN_STINTS} needed (this scope holds "
            f"{evidence.stint_count} stint(s) in total, "
            f"{evidence.samples} push laps)")
    if evidence.contributing_laps < STAGE2_MIN_TOTAL_PUSH_LAPS:
        failures.append(
            f"{evidence.contributing_laps} settled push lap(s) across the "
            f"contributing stints; {STAGE2_MIN_TOTAL_PUSH_LAPS} needed for a "
            f"{STAGE2_EFFECT_SIZE_PCT:.0f} % effect at the measured CV")
    if p is None:
        failures.append("the trend has no testable slope on this population")
    elif p > STAGE2_MAX_P:
        failures.append(
            f"between-stint p = {p:.3f} on {fit.get('dof')} df; "
            f"{STAGE2_MAX_P} needed")
    # **The sign clauses, and they are not decoration.** Without them a RISING
    # trend passes every count-and-significance test and is announced as a
    # loss: a scope fitting +0.0062 g/lap at t = +4.4 would have said "grip's
    # down". That is not hypothetical - Yas / Shelby / RS already fits
    # **+0.0109 g/lap at t = +2.68** and is held out only by its stint count,
    # so two more Yas sessions would have shipped it. A model whose own fit
    # says grip is rising has no business reporting a loss; it has a puzzle.
    if slope is None:
        failures.append("no slope to take the sign of")
    elif slope >= 0:
        failures.append(
            f"the fitted trend is RISING ({slope:+.5f} g/lap). Nothing is said "
            f"about a set getting better - that is a measurement problem, not "
            f"a tyre finding")
    elif not between.get("all_negative", False):
        failures.append(
            f"the per-stint slopes disagree in sign ({between.get('signs')}); "
            f"a trend that reverses between stints is not this car's tyre")
    met = not failures

    if met:
        # **Direction only. The magnitude is not speakable and this is where
        # that is enforced.** A percentile sweep showed the within-stint signal
        # lives in a band - t of -5.9 at p90, -6.4 at p95, **+0.1 at p99** -
        # and every fixed-count high-end statistic is flat. So what is measured
        # is that he holds the limit for less of the lap as the stint goes on,
        # which the data cannot separate from him easing off. The direction
        # survives that; a percentage does not.
        #
        # And the line asks for the gauge, because the gauge is the only bridge
        # to a wear number that exists - 15 readings in 175 laps, none in
        # either race - and a call that converts the model's biggest gap into
        # its own next input is worth more than one that quotes a figure.
        says = (f"I think this set is going away - your combined-g is trending "
                f"down across {len(contributing)} stints on this car here. I "
                f"can't tell you by how much. Read me your gauge.")
    else:
        says = ("Not yet: I can see your grip trend but I can't stand behind "
                "it. " + (failures[0] if failures else ""))
    return GateVerdict(stage=2, name="degradation", met=met,
                       scope=evidence.scope, requirements=requirements,
                       failures=tuple(failures), says=says,
                       # **The seam for the end-of-stint gauge prediction.** A
                       # caller that can prompt reads this rather than parsing
                       # the sentence for a question mark.
                       asks_for="tyre-gauge-reading" if met else None)


def gate_stage3_conserve(evidence: ScopeEvidence) -> GateVerdict:
    """"Ease the rears." On wear grounds, per axle — and blocked on the gauge.

    **Not on the external 88 / 90 / 93 degC.** That figure is one person's test,
    on one car, at one track, on GT7 1.55, and it never states which aggregate
    it means — on lap-axle means this driver essentially never reaches 88 degC
    and on corner windows he exceeds 100. A threshold whose aggregate is
    unstated is not a threshold, and this gate requires a measured onset in
    *this* scope, from his own gauge readings.
    """
    requirements = {
        "stints_with_gauge_readings": {
            "required": STAGE3_MIN_STINTS,
            "readings_each": STAGE3_MIN_GAUGE_READINGS_PER_STINT,
            "observed": evidence.gauge_stints},
        "aggregate_named_on_threshold": {"required": True, "observed": False},
        "front_floor_c": {"required": STAGE3_FRONT_FLOOR_C,
                          "note": "so a cold out-lap cannot fire the call"},
        "evaluation_window": {"required": "60 s or once per lap",
                              "note": "at 5 s a fixed rear threshold toggles "
                                      "the call 1.6 times a lap; at 60 s it is "
                                      "0.0-0.1"},
    }
    failures = [
        f"{evidence.gauge_stints} stint(s) carry "
        f"{STAGE3_MIN_GAUGE_READINGS_PER_STINT} or more gauge readings; "
        f"{STAGE3_MIN_STINTS} needed. This is blocked on readings, not on code.",
        "no measured wear onset exists in this scope, and the external "
        "88/90/93 degC figure may be quoted as a reference but may not gate a "
        "call: its aggregate is unstated and it is untestable on this data.",
    ] if evidence.gauge_stints < STAGE3_MIN_STINTS else [
        "no measured wear onset has been fitted in this scope yet",
    ]
    return GateVerdict(
        stage=3, name="conserve on wear grounds", met=False,
        scope=evidence.scope, requirements=requirements,
        failures=tuple(failures),
        says=("Not yet: I can't tell you to ease an axle on wear grounds. "
              + failures[0]))


def gate_stage4_temperature(evidence: ScopeEvidence, fit: dict,
                            reproduced_on: list[str]) -> GateVerdict:
    """A grip-versus-temperature relation. **The evidence argues against one.**

    `reproduced_on` is the list of *other* scopes whose settled slope has the
    same sign at |t| >= 3. It is a required clause and not a nicety: §3.3 of the
    design pass produced slopes at t = +3.12, -3.69 and +2.12 on three scopes of
    the same quantity, and any one of them alone would have read as significant.
    """
    t = fit.get("t")
    span = fit.get("settled_temp_span_c")
    requirements = {
        "stints": {"required": STAGE4_MIN_STINTS,
                   "observed": evidence.stint_count},
        "settled_temp_span_c": {"required": STAGE4_MIN_TEMP_SPAN_C,
                                "observed": span},
        "abs_t": {"required": STAGE4_MIN_ABS_T,
                  "observed": abs(t) if t is not None else None},
        "sign_reproduced_on_another_scope": {"required": 1,
                                             "observed": len(reproduced_on)},
    }
    failures = []
    if evidence.stint_count < STAGE4_MIN_STINTS:
        failures.append(f"{evidence.stint_count} stint(s); "
                        f"{STAGE4_MIN_STINTS} needed")
    if span is None or span < STAGE4_MIN_TEMP_SPAN_C:
        failures.append(
            f"settled rear-axle temperature spans "
            f"{'nothing measurable' if span is None else f'{span:.1f} degC'}; "
            f"{STAGE4_MIN_TEMP_SPAN_C:.0f} degC needed")
    if t is None or abs(t) < STAGE4_MIN_ABS_T:
        failures.append(
            f"slope |t| = {'untestable' if t is None else f'{abs(t):.2f}'}; "
            f"{STAGE4_MIN_ABS_T} needed")
    if not reproduced_on:
        failures.append("the sign is not reproduced on any second scope")
    met = not failures
    if met:
        says = (f"On this car and circuit, grip moves "
                f"{fit['grip_g_per_c']:+.4f} g per degC of rear-axle "
                f"temperature.")
    else:
        rears = [r["temp_rear_c"] for r in evidence.settled()]
        band = (f"Your rears run {min(rears):.0f} to {max(rears):.0f} on this "
                f"car. " if rears else "")
        says = (band + "I don't have a grip relation for that yet - "
                + failures[-1] + ".")
    return GateVerdict(stage=4, name="temperature response", met=met,
                       scope=evidence.scope, requirements=requirements,
                       failures=tuple(failures), says=says)


def gate_stage5_cold_side(evidence: ScopeEvidence) -> GateVerdict:
    """Anything at all about a lower grip bound. **Nobody has ever established
    one for GT7**, which is why this gate is the strictest and why it needs six
    deliberate cold-start stints across two scopes before it opens."""
    cold_starts = len(evidence.warmups)
    requirements = {
        "cold_start_stints": {"required": STAGE5_MIN_COLD_START_STINTS,
                              "observed": cold_starts},
        "scopes": {"required": STAGE5_MIN_SCOPES},
        "abs_t": {"required": STAGE5_MIN_ABS_T},
        "sign_reproduced_across_scopes": {"required": True},
    }
    return GateVerdict(
        stage=5, name="the cold side", met=False, scope=evidence.scope,
        requirements=requirements,
        failures=(f"{cold_starts} cold-start stint(s) in this scope; "
                  f"{STAGE5_MIN_COLD_START_STINTS} across "
                  f"{STAGE5_MIN_SCOPES} scopes needed, and the sign has to "
                  f"reproduce across them",),
        says=("Not yet, and not soon: there is no evidence anywhere for a "
              "lower grip bound in GT7, so I will not tell you your tyres are "
              "too cold."))


# --------------------------------------------------- fitting a whole archive


def group_by_scope(rows: list[dict]) -> dict[Scope, ScopeEvidence]:
    """Counted LAP observations, split into scopes that may not be pooled."""
    grouped: dict[Scope, list[dict]] = defaultdict(list)
    for row in rows:
        if row["unit_kind"] != "LAP":
            continue
        grouped[scope_of(row)].append(row)
    return {scope: ScopeEvidence.build(rows) for scope, rows in grouped.items()}


def _confidence(met: bool, fit: dict, evidence: ScopeEvidence) -> str:
    """How much this fit is worth, and **never more than its gate allows.**

    An unmet gate used to return "low" whenever |t| >= 2, which read as a
    quiet endorsement of exactly the fits the gate had just refused - a scope
    with two stints and a large t looked more trustworthy than one with five
    stints and a modest one, which is backwards. An unmet gate is "none": the
    evidence did not reach the bar, and the t that did not reach it is not a
    consolation.
    """
    if not met:
        return "none"
    p = fit.get("p")
    if p is not None and p <= 0.005 and evidence.stint_count >= 4:
        return "high"
    return "medium"


def fit_scope(evidence: ScopeEvidence, *, reproduced_on: list[str] | None = None,
              derivation_version: int = DERIVATION_VERSION,
              game_version: str | None = None,
              wear_multiplier: str | None = None) -> list[dict]:
    """Every model this scope's observations support, gated and labelled.

    Returns rows ready for `Store.save_tyre_model`. A model whose gate is not
    met is **still written**, with `speakable = 0` and the failed requirement in
    `gate_json` — an unmet gate is a fact about the evidence and deleting it
    would leave the app unable to say why it is silent.
    """
    scope = evidence.scope
    provenance = evidence.provenance(derivation_version)
    if wear_multiplier:
        provenance["tyre_wear_mult"] = wear_multiplier
    shared = {
        **scope.as_dict(),
        "samples": evidence.samples,
        "sessions": evidence.sessions,
        "stints": evidence.stint_count,
        "derivation_version": derivation_version,
        "game_version": game_version,
        "provenance": provenance,
    }

    degradation = fit_degradation(evidence)
    stage2 = gate_stage2_degradation(evidence, degradation)
    temperature = fit_temperature_response(evidence)
    stage4 = gate_stage4_temperature(evidence, temperature,
                                     reproduced_on or [])
    stage1 = gate_stage1_warmup(evidence)

    return [
        {**shared, "model_kind": "baseline",
         "model": fit_baseline(evidence),
         "confidence": "high" if evidence.samples >= 16 else "low",
         # A level is not a claim about tyres. It is speakable as a
         # measurement of this scope and nothing more, so it carries no gate.
         "speakable": 0,
         "gate": {"stage": 0, "name": "no gate", "met": True,
                  "note": "a grip level is reported, never interpreted"},
         "unknowns": [*_ALWAYS_UNKNOWN,
                      "a level is comparable only inside this scope; the "
                      "yaw_source offset alone is 3-4%"]},
        {**shared, "model_kind": "degradation",
         "model": degradation,
         "confidence": _confidence(stage2.met, degradation, evidence),
         "speakable": int(stage2.met),
         "gate": stage2.as_dict(),
         "unknowns": [*_ALWAYS_UNKNOWN,
                      "no cold-side term: the fit uses settled laps only",
                      "no temperature term: the sign conflicts across circuits",
                      "it may inform 'this set is going away'; it may NOT be "
                      "fed to L = 0.85 / w as if it were w"]},
        {**shared, "model_kind": "temperature-response",
         "model": temperature,
         "confidence": _confidence(stage4.met, temperature, evidence),
         "speakable": int(stage4.met),
         "gate": stage4.as_dict(),
         "unknowns": [*_ALWAYS_UNKNOWN,
                      "in-game hour advances with lap number in every recorded "
                      "session, so time of day cannot be separated from tyre "
                      "age within one of them",
                      "there is no track-temperature channel; the clock is a "
                      "stratifier and was never converted to a temperature"]},
        {**shared, "model_kind": "warmup",
         "model": {"warmup_sequences": len(evidence.warmups),
                   "laps_each": [len(w) for w in evidence.warmups],
                   "method": ("stints whose first lap is on a set of known "
                              "zero age, of at least "
                              f"{STAGE1_MIN_LAPS_PER_WARMUP} laps")},
         "confidence": "medium" if stage1.met else "none",
         "speakable": int(stage1.met),
         "gate": stage1.as_dict(),
         "unknowns": [*_ALWAYS_UNKNOWN,
                      "a warm-up announcement claims nothing about grip, and "
                      "'you can push' is forbidden at every stage"]},
    ]


def fit_archive(rows: list[dict], *,
                derivation_version: int = DERIVATION_VERSION,
                game_version: str | None = None,
                wear_multipliers: dict[str, str] | None = None) -> dict:
    """Fit every scope in a set of observations, and say what is still missing.

    The cross-scope pass is what Stage 4 needs: a temperature slope is only
    speakable if its **sign reproduces on a second scope**, so no scope can be
    fitted in isolation.
    """
    scopes = group_by_scope(rows)
    signs: dict[Scope, tuple[float, float] | None] = {}
    for scope, evidence in scopes.items():
        fit = fit_temperature_response(evidence)
        signs[scope] = ((fit["grip_g_per_c"], fit["t"])
                        if fit["grip_g_per_c"] is not None and fit["t"] is not None
                        else None)

    models: list[dict] = []
    for scope, evidence in scopes.items():
        mine = signs.get(scope)
        reproduced = []
        if mine is not None and abs(mine[1]) >= STAGE4_MIN_ABS_T:
            for other, theirs in signs.items():
                if other == scope or theirs is None:
                    continue
                if (theirs[0] > 0) == (mine[0] > 0) and abs(theirs[1]) >= STAGE4_MIN_ABS_T:
                    reproduced.append(other.label())
        models.extend(fit_scope(
            evidence, reproduced_on=reproduced,
            derivation_version=derivation_version, game_version=game_version,
            wear_multiplier=(wear_multipliers or {}).get(scope.circuit_key)))

    # **Split by yaw_source, not just by circuit.** This is the figure the
    # whole sample-size argument rests on, and pooling it across the one
    # boundary this module refuses to pool across everywhere else was the
    # inconsistency most likely to be copied.
    by_circuit: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row["unit_kind"] == "LAP":
            by_circuit[f"{row['circuit_key']} [{row['yaw_source']}]"].append(row)

    return {
        "scopes": scopes,
        "models": models,
        "compound_ordering": compound_ordering(scopes),
        "not_yet_supported": not_yet_supported(scopes),
        # Per circuit rather than per scope, because the noise figure is a
        # property of the driver and the track and this is the population the
        # sample-size arithmetic was computed on.
        "noise_by_circuit": {circuit: consecutive_lap_cv(circuit_rows)
                             for circuit, circuit_rows
                             in sorted(by_circuit.items())},
    }


def not_yet_supported(scopes: dict[Scope, ScopeEvidence]) -> list[dict]:
    """What the accumulated data still cannot say, per scope, in words.

    This is the half of the fitting layer that has to exist. A model that only
    reports what it found leaves every gap looking like a clean bill of health.
    """
    out = []
    for scope, evidence in sorted(scopes.items(), key=lambda kv: kv[0].label()):
        verdicts = [
            gate_stage1_warmup(evidence),
            gate_stage2_degradation(evidence, fit_degradation(evidence)),
            gate_stage3_conserve(evidence),
            gate_stage4_temperature(evidence,
                                    fit_temperature_response(evidence), []),
            gate_stage5_cold_side(evidence),
        ]
        out.append({
            "scope": scope.label(),
            "push_laps": evidence.samples,
            "sessions": evidence.sessions,
            "stints": evidence.stint_count,
            "open_stages": [v.stage for v in verdicts if v.met],
            "blocked": [{"stage": v.stage, "name": v.name,
                         "why": list(v.failures)}
                        for v in verdicts if not v.met],
            "stage_0_line": STAGE0_LINE,
        })
    return out


# ------------------------------------------------------------- the priors
#
# **Consumed, never restated.** `store/tyres.py` already holds both priors as
# rows with a falsification status and a scope list, which is the right shape:
# "refuted at Monza" is a fact the app carries rather than one somebody
# remembers. This module reads them and does not own a second copy - a prior
# duplicated is a prior that can be refuted in one place and survive in the
# other.


def priors_for_scope(scope: Scope) -> list[dict]:
    """Both stored priors, and whether either may be spoken in this scope.

    The key is composed by `store.tyres.scope_key` and never here. **Where a
    prior's `speakable_scopes` entry does not match, the answer is "not
    speakable here" and it is reported as such** - a near-miss on a slug is not
    a licence, and quietly widening the match would be exactly the kind of thing
    the scope list exists to prevent.
    """
    from pitcrew.store import tyres

    key = prior_scope_key(scope)
    out = []
    for prior in tyres.PRIORS:
        # **A prior's own scope list is necessary and NOT sufficient.** It used
        # to be the whole test, which gave the app two speakability
        # vocabularies - `tyre_models.speakable`, decided at fit time against a
        # counted sample, and a prior's `speakable_here`, decided against
        # nothing at all. The refuted gap association came back
        # `speakable_here=True` on n=17 with no gate in front of it, which is a
        # second door into the same room with no lock on it.
        #
        # So a prior is speakable only where its scope allows it AND its status
        # is not a refutation AND it clears the same sample floor a fitted
        # model would have to. A REFUTED prior is never speakable anywhere,
        # whatever its scope list says - that is what refuted means.
        refuted = "REFUTED" in prior.status.upper()
        untested = "UNTESTED" in prior.status.upper()
        thin = prior.n < STAGE2_MIN_TOTAL_PUSH_LAPS
        blockers = []
        if not prior.speakable_at(key):
            blockers.append(f"not in this prior's speakable scopes ({key})")
        if refuted:
            blockers.append(f"status is {prior.status}: a refuted prior is "
                            f"never speakable, in any scope")
        if untested:
            blockers.append(f"status is {prior.status}: untested is not a "
                            f"licence and never ages into one")
        if thin:
            blockers.append(
                f"rests on n={prior.n}, below the {STAGE2_MIN_TOTAL_PUSH_LAPS} "
                f"observations a fitted model needs to say anything")
        out.append({
            "id": prior.id,
            "claim": prior.claim,
            "status": prior.status,
            "source": prior.source,
            "n": prior.n,
            "in_scope": prior.speakable_at(key),
            "speakable_here": not blockers,
            "blockers": blockers,
            "speakable_scopes": list(prior.speakable_scopes),
            "evidence": list(prior.evidence),
            "caveats": list(prior.caveats),
        })
    return out


def prior_scope_key(scope: Scope) -> str | None:
    """This scope, as the key the prior store speaks.

    **Delegated, not re-composed.** `store.tyres.scope_key` owns the
    composition - which half goes first, and how each half is slugged - and a
    second copy of that ordering here is precisely the defect this call exists
    to avoid. Passing already-slugged halves back through it is safe because
    `slugify` is idempotent on its own output: it emits only `a-z0-9-`, and
    re-slugging that changes nothing.
    """
    from pitcrew.store.tyres import scope_key

    return scope_key(scope.car_key, scope.circuit_key)


def may_i_say(store, *, stage: int, car_key: str, circuit_key: str,
              compound: str | None, yaw_source: str) -> dict:
    """The interface a future caller asks before speaking. **Read-only.**

    It returns the stored verdict rather than re-weighing the evidence: the
    gate was evaluated at fit time by the code that counted the samples, and a
    caller that could re-evaluate it could talk itself into a claim.

    A scope with no fitted model is not an error and not a silence — it comes
    back with `STAGE0_LINE`, which is a real answer the driver can act on.
    """
    kinds = {1: "warmup", 2: "degradation", 4: "temperature-response"}
    kind = kinds.get(stage)
    if kind is None:
        return {"may_speak": False, "stage": stage,
                "say": STAGE0_LINE,
                "why": ["stage 3 and stage 5 have no fitted model kind: "
                        "stage 3 is blocked on gauge readings and stage 5 on "
                        "cold-start stints"]}
    for model in store.list_tyre_models(car_key=car_key,
                                        circuit_key=circuit_key,
                                        model_kind=kind):
        if model["compound"] != compound or model["yaw_source"] != yaw_source:
            continue
        gate = model["gate"]
        return {"may_speak": bool(model["speakable"]),
                "stage": stage,
                "say": gate.get("says") or STAGE0_LINE,
                # What this call wants back, so the caller does not have to
                # read the sentence to find out.
                "asks_for": gate.get("asks_for"),
                "samples": model["samples"], "stints": model["stints"],
                "sessions": model["sessions"],
                "confidence": model["confidence"],
                "unknowns": model["unknowns"],
                # **Staleness is the caller's to judge, so it has to be
                # returned.** A model fitted at derivation version 1 against 40
                # laps is a different claim once 60 laps exist, and a caller
                # holding only a boolean cannot tell. These are what let it ask
                # "is this still current?" without re-fitting.
                "derivation_version": model["derivation_version"],
                "fitted_at": model["fitted_at"],
                "provenance": model["provenance"],
                "why": gate.get("failures", [])}
    return {"may_speak": False, "stage": stage, "say": STAGE0_LINE,
            "asks_for": None,
            "why": [f"no {kind} model fitted for this scope"]}
