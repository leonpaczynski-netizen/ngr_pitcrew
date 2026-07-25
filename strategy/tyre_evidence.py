"""Tyre evidence: cliff detection, optimal stint length, compound crossover (pure).

WHY IT EXISTS
  ``race_strategy_session_adapter`` derives tyre-wear from lap-time drift.  This
  module elevates that per-lap data to a per-compound tyre-evidence model:

    • Theil-Sen slope — median of all pairwise slopes; robust against outliers.
      Flat data → ~0, never the fabricated positive produced by summing only
      positive increments.
    • Cliff detection — identifies accelerating degradation (last-third slope
      significantly exceeds first-third slope) and the lap within the stint where
      the cliff starts.
    • Known-good laps — the conservative upper bound on the tested-safe stint
      length.  NEVER projects beyond tested evidence without flagging.
    • Optimal stint — the degradation-vs-pit-cost crossover (S* = sqrt(2 × pit /
      slope)), capped hard at the known-good (tested) laps and the fuel limit.
    • Compound crossover — at what stint lap compound B overtakes compound A
      purely from lap-time accumulation; requires measured runs on BOTH compounds.

WHAT THIS IS NOT
  Pure: no DB, no Qt, no AI, no setup writes.  Deterministic.  Never raises.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import median
from typing import Optional, Sequence

# Minimum laps in a stint before we attempt any characterisation.
MIN_LAPS_FOR_PROFILE: int = 3
# Minimum laps before cliff detection is meaningful.
MIN_LAPS_FOR_CLIFF: int = 5
# s/lap below which degradation is treated as "flat" (within measurement noise).
FLAT_SLOPE_THRESHOLD: float = 0.01
# Ratio last-third-slope / first-third-slope that signals an accelerating cliff.
CLIFF_SLOPE_RATIO: float = 1.5


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CompoundTyreProfile:
    """Evidence-based characterisation of one compound from measured stint laps."""

    compound: str
    tested_laps: int                  # lap count actually measured
    slope_s_per_lap: float            # Theil-Sen per-lap pace loss rate (≥ 0)
    is_flat: bool                     # slope below noise floor (FLAT_SLOPE_THRESHOLD)
    cliff_onset_lap: int              # stint lap where cliff starts; 0 = none detected
    convex: bool                      # degradation accelerating (pre/at-cliff signal)
    known_good_laps: int              # conservative upper bound on usable stint
    optimal_stint_laps: int           # deg-cost vs pit-cost crossover (0 = unknown)
    fuel_limit_laps: int              # fuel-imposed max stint laps (0 = unknown)
    confidence: str                   # "high" | "medium" | "low" | "insufficient"
    note: str

    @property
    def is_tested(self) -> bool:
        return self.tested_laps >= MIN_LAPS_FOR_PROFILE

    @property
    def is_long_run(self) -> bool:
        """True when the stint is long enough for high-confidence analysis (≥ 8 laps)."""
        return self.tested_laps >= 8

    @property
    def stint_length_bounded(self) -> bool:
        """True when evidence provides a meaningful upper bound on stint length."""
        return self.optimal_stint_laps > 0 and self.is_tested


@dataclass(frozen=True)
class CompoundCrossover:
    """Where compound B overtakes compound A in accumulated lap-time, per stint lap."""

    compound_a: str                   # the faster-fresh compound
    compound_b: str                   # the slower-fresh but more durable compound
    fresh_pace_delta_s: float         # how much faster A is on lap 1 (> 0 = A faster)
    crossover_lap: int                # stint lap where B overtakes A (0 = unknown/never)
    note: str
    confidence: str                   # "high" | "medium" | "low" | "insufficient"


# ---------------------------------------------------------------------------
# Public builders
# ---------------------------------------------------------------------------

def build_compound_profile(
    compound: str,
    lap_times_s: Sequence[float],
    *,
    pit_loss_s: float = 0.0,
    fuel_limit_laps: int = 0,
) -> CompoundTyreProfile:
    """Build a tyre evidence profile from an ordered lap-time sequence.

    ``lap_times_s`` must be ordered by tyre age within the stint (index 0 = first
    stint lap after tyre fit).  Returns an "insufficient" profile when too few
    laps are provided; never raises.
    """
    try:
        laps = [float(t) for t in (lap_times_s or []) if t and float(t) > 0]
        n = len(laps)

        if n < MIN_LAPS_FOR_PROFILE:
            return CompoundTyreProfile(
                compound=compound, tested_laps=n,
                slope_s_per_lap=0.0, is_flat=True,
                cliff_onset_lap=0, convex=False,
                known_good_laps=n, optimal_stint_laps=0,
                fuel_limit_laps=fuel_limit_laps,
                confidence="insufficient",
                note=(
                    f"{compound}: only {n} laps recorded — too few to characterise "
                    f"stint behaviour; need ≥ {MIN_LAPS_FOR_PROFILE} clean laps"
                ),
            )

        # Theil-Sen slope (robust, clamped ≥ 0)
        pairs = [(i + 1, laps[i]) for i in range(n)]
        slope = max(0.0, _theil_sen_slope(pairs))
        is_flat = slope < FLAT_SLOPE_THRESHOLD

        # Cliff detection
        cliff_lap, convex = _detect_cliff(laps)

        # Conservative known-good: if cliff seen, cut before it; else = tested_laps
        if cliff_lap > 0:
            known_good = max(1, cliff_lap - 1)
        else:
            known_good = n

        # Optimal stint from degradation-vs-pit crossover formula
        optimal = _optimal_stint_laps(slope, pit_loss_s, known_good, fuel_limit_laps)

        # Confidence
        if n >= 8:
            conf = "high"
        elif n >= MIN_LAPS_FOR_PROFILE:
            conf = "medium" if not convex else "low"
        else:
            conf = "insufficient"

        note = _build_note(compound, n, slope, cliff_lap, convex, optimal, fuel_limit_laps)

        return CompoundTyreProfile(
            compound=compound, tested_laps=n,
            slope_s_per_lap=round(slope, 4), is_flat=is_flat,
            cliff_onset_lap=cliff_lap, convex=convex,
            known_good_laps=known_good, optimal_stint_laps=optimal,
            fuel_limit_laps=fuel_limit_laps,
            confidence=conf, note=note,
        )
    except Exception:
        return CompoundTyreProfile(
            compound=str(compound or ""), tested_laps=0,
            slope_s_per_lap=0.0, is_flat=True,
            cliff_onset_lap=0, convex=False,
            known_good_laps=0, optimal_stint_laps=0,
            fuel_limit_laps=fuel_limit_laps,
            confidence="insufficient",
            note=f"{compound}: profile build failed",
        )


def compute_compound_crossover(
    compound_a: str,
    compound_b: str,
    profile_a: CompoundTyreProfile,
    profile_b: CompoundTyreProfile,
    fresh_pace_delta_s: float,
    pit_loss_s: float = 0.0,
) -> CompoundCrossover:
    """Compute where compound B (more durable) overtakes compound A (faster fresh).

    Requires MEASURED runs on BOTH compounds.  When data is missing for either,
    returns crossover_lap=0 and confidence="insufficient".

    Model (per-lap cumulative approach):
      A's cumulative time after N laps = N×base + slope_a × N(N-1)/2
      B's cumulative time after N laps = N×(base + delta) + slope_b × N(N-1)/2

    B is faster from lap N* where:
      (slope_a − slope_b) × (N*−1)/2 = delta
      → N* = 2×delta / (slope_a − slope_b) + 1

    Caps at the shorter compound's tested_laps (extrapolation flagged).
    """
    try:
        if not profile_a.is_tested or not profile_b.is_tested:
            return CompoundCrossover(
                compound_a=compound_a, compound_b=compound_b,
                fresh_pace_delta_s=fresh_pace_delta_s, crossover_lap=0,
                note=(
                    f"crossover requires measured runs on both {compound_a} and "
                    f"{compound_b} — run full stints on each to compute"
                ),
                confidence="insufficient",
            )

        slope_a = profile_a.slope_s_per_lap
        slope_b = profile_b.slope_s_per_lap

        if fresh_pace_delta_s <= 0.0:
            return CompoundCrossover(
                compound_a=compound_a, compound_b=compound_b,
                fresh_pace_delta_s=fresh_pace_delta_s, crossover_lap=0,
                note=f"{compound_b} is already faster on lap 1 — no crossover needed",
                confidence="medium",
            )

        if slope_a <= slope_b:
            return CompoundCrossover(
                compound_a=compound_a, compound_b=compound_b,
                fresh_pace_delta_s=fresh_pace_delta_s, crossover_lap=0,
                note=(
                    f"{compound_a} stays faster throughout — it degrades no faster "
                    f"than {compound_b} so the fresh-lap advantage never erodes"
                ),
                confidence="medium",
            )

        # slope_a > slope_b and fresh_pace_delta_s > 0 → crossover exists
        n_cross = 2.0 * fresh_pace_delta_s / (slope_a - slope_b) + 1.0
        crossover_lap = max(1, int(math.ceil(n_cross)))

        max_tested = min(profile_a.tested_laps, profile_b.tested_laps)
        conf = "high" if max_tested >= 8 else "medium"

        if crossover_lap > max_tested:
            note = (
                f"{compound_b} crossover at stint lap ~{crossover_lap} is BEYOND the "
                f"tested range (~{max_tested} laps) — run longer stints on both "
                f"compounds to confirm whether {compound_b} ever becomes faster"
            )
            conf = "insufficient"
            crossover_lap = 0   # unknown beyond tested range
        else:
            note = (
                f"{compound_b} overtakes {compound_a} at stint lap ~{crossover_lap} "
                f"(tested to {max_tested} laps; slope_a={slope_a:.3f}s/lap, "
                f"slope_b={slope_b:.3f}s/lap, Δfresh={fresh_pace_delta_s:.2f}s)"
            )

        return CompoundCrossover(
            compound_a=compound_a, compound_b=compound_b,
            fresh_pace_delta_s=fresh_pace_delta_s,
            crossover_lap=crossover_lap, note=note, confidence=conf,
        )
    except Exception:
        try:
            _delta = float(fresh_pace_delta_s)
        except (TypeError, ValueError):
            _delta = 0.0
        return CompoundCrossover(
            compound_a=str(compound_a or ""), compound_b=str(compound_b or ""),
            fresh_pace_delta_s=_delta, crossover_lap=0,
            note="crossover computation failed", confidence="insufficient",
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _theil_sen_slope(pairs: list[tuple[int, float]]) -> float:
    """Median of all pairwise (Δtime / Δlap) slopes.

    ``pairs`` is a list of (lap_number, lap_time_s) tuples in lap order.
    Returns 0.0 when fewer than two points are supplied.
    """
    n = len(pairs)
    if n < 2:
        return 0.0
    slopes: list[float] = []
    for i in range(n):
        for j in range(i + 1, n):
            dx = pairs[j][0] - pairs[i][0]
            if dx > 0:
                slopes.append((pairs[j][1] - pairs[i][1]) / dx)
    if not slopes:
        return 0.0
    slopes.sort()
    mid = len(slopes) // 2
    return slopes[mid] if len(slopes) % 2 == 1 else (slopes[mid - 1] + slopes[mid]) / 2.0


def _detect_cliff(laps: list[float]) -> tuple[int, bool]:
    """Return (cliff_onset_lap, is_convex) from an ordered stint lap sequence.

    cliff_onset_lap:
        1-indexed lap number within the stint where cliff begins.  0 = none within
        the tested range.
    is_convex:
        True when the last-third slope exceeds the first-third slope by the
        CLIFF_SLOPE_RATIO — the degradation is accelerating.

    Requires MIN_LAPS_FOR_CLIFF laps; returns (0, False) when too few.
    """
    n = len(laps)
    if n < MIN_LAPS_FOR_CLIFF:
        return 0, False

    f = max(2, n // 3)
    first_pairs = [(i + 1, laps[i]) for i in range(f)]
    last_pairs = [(n - f + i + 1, laps[n - f + i]) for i in range(f)]

    first_slope = _theil_sen_slope(first_pairs)
    last_slope = _theil_sen_slope(last_pairs)

    # Cliff: last third steeper than CLIFF_SLOPE_RATIO × first third, and meaningfully
    # above noise.  A negative first slope (improving pace) should not mask a cliff.
    first_ref = max(first_slope, FLAT_SLOPE_THRESHOLD)
    is_convex = (last_slope > first_ref * CLIFF_SLOPE_RATIO and last_slope > FLAT_SLOPE_THRESHOLD)

    if not is_convex:
        return 0, False

    # Find the specific lap where the per-lap jump exceeds 2× the overall slope.
    overall = max(FLAT_SLOPE_THRESHOLD, _theil_sen_slope([(i + 1, laps[i]) for i in range(n)]))
    threshold = overall * 2.0

    cliff_lap = 0
    for i in range(1, n):
        marginal = laps[i] - laps[i - 1]
        if marginal > threshold:
            cliff_lap = i + 1   # 1-indexed stint lap where cliff observed
            break

    if cliff_lap == 0:
        # Convex but no single-lap spike — onset is where the last third begins.
        cliff_lap = n - f + 1

    return cliff_lap, True


def _optimal_stint_laps(
    slope: float,
    pit_loss_s: float,
    known_good_laps: int,
    fuel_limit_laps: int,
) -> int:
    """Optimal stint length where extending costs more in degradation than it saves.

    Formula: S* = floor(sqrt(2 × pit_loss_s / slope)), then capped:
      • known_good_laps  — the tested evidence boundary; NEVER exceed.
      • fuel_limit_laps  — the fuel tank limits max stint.

    When slope ≈ 0 (flat tyre): S* → ∞ so the fuel and evidence cap dominates.
    Returns 0 when insufficient data to compute a meaningful estimate.
    """
    fuel_cap = fuel_limit_laps if fuel_limit_laps > 0 else 9999
    known_cap = known_good_laps if known_good_laps > 0 else 9999

    if slope > FLAT_SLOPE_THRESHOLD and pit_loss_s > 0:
        s_star = math.floor(math.sqrt(2.0 * pit_loss_s / slope))
        s_star = min(s_star, known_cap, fuel_cap)
        return max(1, s_star)
    elif slope <= FLAT_SLOPE_THRESHOLD:
        # Flat: go as long as evidence + fuel allow.
        combined = min(known_cap, fuel_cap)
        return combined if combined < 9999 else 0
    return 0


def _build_note(
    compound: str,
    n: int,
    slope: float,
    cliff_lap: int,
    convex: bool,
    optimal: int,
    fuel_limit_laps: int,
) -> str:
    parts: list[str] = []
    if n < MIN_LAPS_FOR_PROFILE:
        return f"{compound}: only {n} laps — insufficient for characterisation"
    parts.append(f"{compound}: {n} laps measured, slope {slope:.3f} s/lap")
    if cliff_lap > 0:
        parts.append(f"cliff at stint lap {cliff_lap}")
    elif convex:
        parts.append("degradation accelerating (cliff forming)")
    else:
        parts.append("no cliff within tested range")
    if optimal > 0:
        parts.append(f"optimal stint ~{optimal} laps")
    else:
        parts.append("optimal stint unknown — extend the test run")
    if n < 8:
        parts.append(
            f"⚠ only tested to lap {n} — stint life beyond {n} laps is UNVERIFIED; "
            "run a full race stint to find the cliff"
        )
    if fuel_limit_laps > 0 and optimal >= fuel_limit_laps:
        parts.append(f"fuel-limited at {fuel_limit_laps} laps/stint")
    return "; ".join(parts)
