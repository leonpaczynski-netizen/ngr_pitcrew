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
    "fuel is not separated - a lighter car reads higher, so any decline here "
    "is a LOWER BOUND on the grip decline",
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
STAGE2_MIN_TOTAL_PUSH_LAPS = 24
STAGE2_MIN_ABS_T = 2.5
# Stage 1's: a warm-up is one observation per stint, not one per lap.
STAGE1_MIN_WARMUPS = 3
STAGE1_MIN_LAPS_PER_WARMUP = 4
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
        return cls(scope=scope_of(rows[0]), rows=counted, stints=dict(stints))

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
        """
        return {key: laps for key, laps in self.stints.items()
                if len(laps) >= STAGE2_MIN_PUSH_LAPS_PER_STINT}

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
    def warmups(self) -> list[list[dict]]:
        """Stints that began on a set whose age is actually known to be zero."""
        out = []
        for laps in self.stints.values():
            if not laps or laps[0].get("laps_on_set") != 0:
                continue
            if len(laps) >= STAGE1_MIN_LAPS_PER_WARMUP:
                out.append(laps)
        return out

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
    per_stint = {}
    for key, laps in evidence.stints.items():
        fit = ols([float(r["lap_in_stint"] or 0) for r in laps],
                  [r["grip_g"] for r in laps])
        per_stint[key] = {"slope_g_per_lap": fit.slope, "se": fit.se,
                          "t": fit.t, "laps": fit.n}

    xs: list[float] = []
    ys: list[float] = []
    for laps in evidence.stints.values():
        if len(laps) < 2:
            continue
        mean_x = sum(float(r["lap_in_stint"] or 0) for r in laps) / len(laps)
        mean_y = sum(r["grip_g"] for r in laps) / len(laps)
        for row in laps:
            xs.append(float(row["lap_in_stint"] or 0) - mean_x)
            ys.append(row["grip_g"] - mean_y)
    usable_stints = sum(1 for laps in evidence.stints.values() if len(laps) >= 2)
    pooled = ols(xs, ys, dof_penalty=usable_stints + 1)

    return {
        "grip_g_per_lap": pooled.slope,
        "se": pooled.se,
        "t": pooled.t,
        "intercept_g": fit_baseline(evidence)["mean_grip_g"],
        "pooled_over_stints": usable_stints,
        "per_stint": per_stint,
        "method": ("OLS of comb_p95 on lap-in-stint, demeaned within stint; "
                   "degrees of freedom charged for every stint mean"),
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
            "caveat": ("compound is confounded with session: no session in the "
                       "archive ran two compounds. Protocol P1 is what makes "
                       "this controlled."),
        })
    return out


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

    def as_dict(self) -> dict:
        return {"stage": self.stage, "name": self.name, "met": self.met,
                "requirements": self.requirements,
                "failures": list(self.failures), "says": self.says,
                "scope": self.scope.as_dict() if self.scope else None}


# Stage 0 is not a gate. It is what every scope that has met nothing else says,
# and it has to be said out loud rather than left as silence.
STAGE0_LINE = ("I can't see tyre wear. No wear channel exists in any GT7 "
               "packet, there's no gauge reading this stint, and lap time "
               "can't resolve it at your spread.")


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
    requirements = {
        "warmup_sequences": {"required": STAGE1_MIN_WARMUPS,
                             "observed": len(warmups)},
        "laps_per_sequence": {"required": STAGE1_MIN_LAPS_PER_WARMUP,
                              "observed": [len(w) for w in warmups]},
    }
    failures = []
    if len(warmups) < STAGE1_MIN_WARMUPS:
        failures.append(
            f"{len(warmups)} warm-up sequence(s) on a set of known age; "
            f"{STAGE1_MIN_WARMUPS} needed. A warm-up is one observation per "
            f"stint, not one per lap - protocol P3 supplies three in an evening.")
    met = not failures
    return GateVerdict(
        stage=1, name="warm-up plateau", met=met, scope=evidence.scope,
        requirements=requirements, failures=tuple(failures),
        says=("Tyres are up to temperature." if met else
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
    t = fit.get("t")
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
        "abs_t": {"required": STAGE2_MIN_ABS_T,
                  "observed": abs(t) if t is not None else None},
        "single_yaw_source": {"required": True,
                              "observed": evidence.scope.yaw_source},
    }
    failures = []
    if len(contributing) < STAGE2_MIN_STINTS:
        failures.append(
            f"{len(contributing)} contributing stint(s) of at least "
            f"{STAGE2_MIN_PUSH_LAPS_PER_STINT} push laps; "
            f"{STAGE2_MIN_STINTS} needed (this scope holds "
            f"{evidence.stint_count} stint(s) in total, "
            f"{evidence.samples} push laps)")
    if evidence.contributing_laps < STAGE2_MIN_TOTAL_PUSH_LAPS:
        failures.append(
            f"{evidence.contributing_laps} push lap(s) across the contributing "
            f"stints; {STAGE2_MIN_TOTAL_PUSH_LAPS} needed")
    if t is None:
        failures.append("the trend has no testable slope on this population")
    elif abs(t) < STAGE2_MIN_ABS_T:
        failures.append(f"trend |t| = {abs(t):.2f}, {STAGE2_MIN_ABS_T} needed")
    met = not failures
    slope = fit.get("grip_g_per_lap")
    intercept = fit.get("intercept_g")
    if met and slope is not None and intercept:
        # **The horizon is a stint he actually drives, not a gate constant.**
        # This line used to quote the decline over `STAGE2_MIN_PUSH_LAPS_PER_
        # STINT` laps, which silently rescaled the number the day that
        # threshold moved from 8 to 5. The median contributing stint is a fact
        # about his running; the gate's floor is a fact about the gate.
        lengths = sorted(len(laps) for laps in contributing.values())
        horizon = lengths[len(lengths) // 2]
        over = abs(slope) * horizon / intercept * 100.0
        says = (f"Grip's down about {over:.0f} per cent over a {horizon}-lap "
                f"stint on this set. That's measured off your own laps, not "
                f"off the stopwatch.")
    else:
        says = ("Not yet: I can see your grip trend but I can't stand behind "
                "it. " + (failures[0] if failures else ""))
    return GateVerdict(stage=2, name="degradation", met=met,
                       scope=evidence.scope, requirements=requirements,
                       failures=tuple(failures), says=says)


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
    t = fit.get("t")
    if not met:
        return "low" if t is not None and abs(t) >= 2.0 else "none"
    if t is not None and abs(t) >= 4.0 and evidence.stint_count >= 4:
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

    by_circuit: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row["unit_kind"] == "LAP":
            by_circuit[row["circuit_key"]].append(row)

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
        out.append({
            "id": prior.id,
            "claim": prior.claim,
            "status": prior.status,
            "source": prior.source,
            "n": prior.n,
            "speakable_here": prior.speakable_at(key),
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
                "samples": model["samples"], "stints": model["stints"],
                "sessions": model["sessions"],
                "confidence": model["confidence"],
                "unknowns": model["unknowns"],
                "why": gate.get("failures", [])}
    return {"may_speak": False, "stage": stage, "say": STAGE0_LINE,
            "why": [f"no {kind} model fitted for this scope"]}
