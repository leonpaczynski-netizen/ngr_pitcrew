"""Adaptive Per-Gear Shift Strategy — core domain engine (Phase 1).

Computes per-gear optimal shift RPMs for Qualifying (minimum lap time) and
Race (minimum lap time given a fuel-saving target) from gear ratios, engine
torque-curve shape, and aspiration type.

DOCTRINE
  Deterministic, offline, pure.  No Qt, no DB, no network, no I/O.
  Never raises — every entry point wraps its logic in a try/except and
  returns an honest INSUFFICIENT_EVIDENCE result on failure.

CONFIDENCE CEILING (Phase 1)
  All engine-data in Phase 1 is supplied manually by the driver (peak-power
  RPM, peak-torque RPM, redline).  There is no telemetry-calibrated torque
  curve yet.  Therefore:
  - A manually-seeded result is capped at PROVISIONAL — never HIGH or MEDIUM.
  - Outputs annotated PROVISIONAL are shown with a "unvalidated proxy" badge
    in the UI; the domain tags them but does NOT suppress the numbers.
  - Overall confidence = weakest across all covered gear pairs.

TORQUE CURVE MODEL
  Piecewise-linear with four anchors derived from peak_torque_rpm,
  peak_power_rpm, and redline.  The shape between peak-torque and
  peak-power RPM is derived from the constant-power assumption:
      T(peak_power_rpm) = peak_torque_rpm / peak_power_rpm
  (If power is constant in that band, torque must fall as 1/rpm.)
  Aspiration shape-priors widen or narrow the low-end plateau via named
  constants from shift_strategy_constants.

QUALIFYING OPTIMISER (per gear pair i → i+1)
  Sweep candidate shift RPMs from QUAL_MIN_RPM_FRACTION × peak_power_rpm
  to redline in SWEEP_STEP_RPM increments.  For each candidate:
    elapsed ≈ SPEED_WINDOW / mean_T(cand … redline, gear i)
             + SHIFT_LOSS_S
             + SPEED_WINDOW / mean_T(post_shift_rpm … redline, gear i+1)
  Pick argmin; ties resolve to the LOWER candidate.

RACE OPTIMISER (cross-gear greedy)
  Sweep from qualifying target down to RACE_MIN_RPM_FRACTION × peak_power_rpm.
  Per candidate: time_cost = extra elapsed vs qualifying; fuel_saving_frac via
  FUEL_BURN_RPM_COEFFICIENT (PROVISIONAL proxy).  Remove dominated candidates.
  Greedy select by saving-per-second-lost descending until Σ fuel_saving ≥
  required_fuel_saving_pct / 100.  At target 0.0 race == qualifying.

POST-SHIFT RPM
  post_shift_rpm(i→i+1, shift_rpm) = round(shift_rpm × ratio[i+1] / ratio[i])
  The final drive cancels in this ratio — it is per-pair relative.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

from strategy.shift_strategy_constants import (
    EV_IDLE_TORQUE_FRAC, EV_REDLINE_TORQUE_FRAC,
    FUEL_BURN_RPM_COEFFICIENT,
    IDLE_RPM_ANCHOR,
    MIN_USEFUL_RPM_FRACTION,
    NA_IDLE_TORQUE_FRAC, NA_REDLINE_TORQUE_FRAC,
    QUAL_MIN_RPM_FRACTION, RACE_MIN_RPM_FRACTION,
    SC_IDLE_TORQUE_FRAC, SC_REDLINE_TORQUE_FRAC,
    SHIFT_LOSS_S, SHIFT_STRATEGY_VERSION,
    SPEED_WINDOW, SWEEP_STEP_RPM,
    TC_IDLE_TORQUE_FRAC, TC_REDLINE_TORQUE_FRAC,
)
from strategy.shift_strategy_inputs import ShiftStrategyInputs


# ---------------------------------------------------------------------------
# Confidence enum
# ---------------------------------------------------------------------------

class ShiftConfidence(str, Enum):
    HIGH = "high"                         # telemetry-calibrated (Phase 2+)
    MEDIUM = "medium"                     # model-validated (Phase 2+)
    LOW = "low"                           # model, minimal data
    PROVISIONAL = "provisional"           # manually seeded — cap in Phase 1
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"  # cannot compute
    STALE = "stale"                       # inputs changed since last compute


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PerGearShiftDecision:
    """Optimal shift recommendation for one gear pair (from_gear → to_gear)."""

    from_gear: int                          # gear number shifting FROM (1-indexed)
    to_gear: int                            # gear number shifting INTO
    qualifying_target_rpm: Optional[int]    # optimal shift RPM for qualifying
    race_target_rpm: Optional[int]          # optimal shift RPM for race
    rpm_delta_from_qualifying: Optional[int]  # race - qualifying (negative = short-shift)
    expected_post_shift_rpm: Optional[int]  # RPM in next gear immediately after upshift
    predicted_time_cost: Optional[float]    # extra seconds/lap vs qualifying (race only)
    predicted_fuel_saving: Optional[float]  # fractional fuel saving (race only; PROVISIONAL)
    evidence_source: str                    # e.g. "manual_engine_data", "below_powerband"
    sample_count: int                       # telemetry samples used (0 in Phase 1)
    confidence: ShiftConfidence
    rationale: str
    valid: bool                             # False if post-shift RPM below power band

    def to_dict(self) -> dict:
        return {
            "from_gear": self.from_gear,
            "to_gear": self.to_gear,
            "qualifying_target_rpm": self.qualifying_target_rpm,
            "race_target_rpm": self.race_target_rpm,
            "rpm_delta_from_qualifying": self.rpm_delta_from_qualifying,
            "expected_post_shift_rpm": self.expected_post_shift_rpm,
            "predicted_time_cost": self.predicted_time_cost,
            "predicted_fuel_saving": self.predicted_fuel_saving,
            "evidence_source": self.evidence_source,
            "sample_count": self.sample_count,
            "confidence": self.confidence.value,
            "rationale": self.rationale,
            "valid": self.valid,
        }


@dataclass(frozen=True)
class ShiftProfile:
    """Collection of per-gear decisions for one driving mode."""

    mode: str                               # "qualifying" or "race"
    decisions: Tuple[PerGearShiftDecision, ...]
    overall_confidence: ShiftConfidence

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "decisions": [d.to_dict() for d in self.decisions],
            "overall_confidence": self.overall_confidence.value,
        }


@dataclass(frozen=True)
class ShiftStrategyResult:
    """Top-level result returned by :func:`compute_shift_strategy`."""

    car_id: str
    configuration_fingerprint: str
    qualifying_profile: ShiftProfile
    race_profile: ShiftProfile
    required_fuel_saving_pct: float
    predicted_fuel_saving_pct: float
    predicted_time_cost_per_lap: Optional[float]
    overall_confidence: ShiftConfidence
    evidence_summary: str
    missing_evidence: Tuple[str, ...]       # next-action strings, never blank
    warnings: Tuple[str, ...]
    stale_reason: str
    algorithm_version: str

    # Public engine-data fields — set from inputs even when result is
    # INSUFFICIENT_EVIDENCE, so the VM can read these without private-attr crawl
    # and use them as a structured signal for stepper-stage classification.
    engine_peak_power_rpm: Optional[int] = None
    engine_peak_torque_rpm: Optional[int] = None
    engine_redline: Optional[int] = None
    # Number of gear ratios that were passed in (0 when none, regardless of
    # how many decisions were computed) — used by the VM to distinguish
    # "no ratios entered" (stage 0) from "ratios present but no engine data" (stage 1).
    gear_ratio_count: int = 0

    def to_dict(self) -> dict:
        return {
            "car_id": self.car_id,
            "configuration_fingerprint": self.configuration_fingerprint,
            "qualifying_profile": self.qualifying_profile.to_dict(),
            "race_profile": self.race_profile.to_dict(),
            "required_fuel_saving_pct": self.required_fuel_saving_pct,
            "predicted_fuel_saving_pct": self.predicted_fuel_saving_pct,
            "predicted_time_cost_per_lap": self.predicted_time_cost_per_lap,
            "overall_confidence": self.overall_confidence.value,
            "evidence_summary": self.evidence_summary,
            "missing_evidence": list(self.missing_evidence),
            "warnings": list(self.warnings),
            "stale_reason": self.stale_reason,
            "algorithm_version": self.algorithm_version,
            "engine_peak_power_rpm": self.engine_peak_power_rpm,
            "engine_peak_torque_rpm": self.engine_peak_torque_rpm,
            "engine_redline": self.engine_redline,
            "gear_ratio_count": self.gear_ratio_count,
        }


# ---------------------------------------------------------------------------
# Torque curve model
# ---------------------------------------------------------------------------

def _aspiration_shape(aspiration: str) -> Tuple[float, float]:
    """Return (idle_torque_frac, redline_torque_frac) for the aspiration type."""
    a = str(aspiration or "NA").upper()
    if a == "EV":
        return EV_IDLE_TORQUE_FRAC, EV_REDLINE_TORQUE_FRAC
    if a in ("TC",):
        return TC_IDLE_TORQUE_FRAC, TC_REDLINE_TORQUE_FRAC
    if a in ("SC",):
        return SC_IDLE_TORQUE_FRAC, SC_REDLINE_TORQUE_FRAC
    # NA (default)
    return NA_IDLE_TORQUE_FRAC, NA_REDLINE_TORQUE_FRAC


def _lerp(x: float, x0: float, y0: float, x1: float, y1: float) -> float:
    """Linear interpolation between two anchor points. Clamps to [min,max]."""
    if x1 == x0:
        return y0
    t = (x - x0) / (x1 - x0)
    t = max(0.0, min(1.0, t))
    return y0 + t * (y1 - y0)


def normalised_torque(
    rpm: float,
    *,
    peak_torque_rpm: int,
    peak_power_rpm: int,
    redline: int,
    aspiration: str,
) -> float:
    """Piecewise-linear normalised torque in [0, 1] at the given RPM.

    Anchors
    -------
    1. IDLE_RPM_ANCHOR  → idle_torque_frac   (aspiration-specific)
    2. peak_torque_rpm  → 1.0
    3. peak_power_rpm   → peak_torque_rpm / peak_power_rpm
       (derived from constant-power assumption; T ∝ 1/rpm in that band)
    4. redline          → redline_torque_frac (aspiration-specific)

    Assumptions (exposed for callers / tests)
    ------------------------------------------
    • Power is approximated as constant between peak_torque_rpm and
      peak_power_rpm, giving T(peak_power_rpm) = peak_torque_rpm / peak_power_rpm.
    • Below IDLE_RPM_ANCHOR the torque is clamped to idle_torque_frac.
    • Above redline the torque is clamped to redline_torque_frac.
    • The curve is always non-negative.
    """
    idle_frac, redline_frac = _aspiration_shape(aspiration)

    # torque at peak-power RPM, from the constant-power assumption
    t_at_pp = float(peak_torque_rpm) / float(peak_power_rpm)
    # clamp so it stays in (0, 1]
    t_at_pp = max(0.05, min(1.0, t_at_pp))

    r = float(rpm)

    # Below idle
    if r <= IDLE_RPM_ANCHOR:
        return idle_frac

    # Idle → peak_torque_rpm
    if r <= peak_torque_rpm:
        return _lerp(r, IDLE_RPM_ANCHOR, idle_frac, peak_torque_rpm, 1.0)

    # peak_torque_rpm → peak_power_rpm  (power-band plateau; torque falls as 1/rpm)
    if r <= peak_power_rpm:
        return _lerp(r, peak_torque_rpm, 1.0, peak_power_rpm, t_at_pp)

    # peak_power_rpm → redline  (power falls; torque falls faster)
    if r <= redline:
        return _lerp(r, peak_power_rpm, t_at_pp, redline, redline_frac)

    # Above redline
    return redline_frac


def _mean_torque(
    rpm_lo: float,
    rpm_hi: float,
    *,
    peak_torque_rpm: int,
    peak_power_rpm: int,
    redline: int,
    aspiration: str,
    steps: int = 20,
) -> float:
    """Arithmetic mean of normalised torque over [rpm_lo, rpm_hi].

    Uses ``steps`` uniformly-spaced samples.  Returns a small positive floor
    (0.01) instead of zero to avoid division-by-zero in the time proxy.
    """
    if rpm_hi <= rpm_lo:
        return 0.01
    interval = rpm_hi - rpm_lo
    total = 0.0
    for k in range(steps):
        rpm = rpm_lo + (k + 0.5) * interval / steps
        total += normalised_torque(
            rpm,
            peak_torque_rpm=peak_torque_rpm,
            peak_power_rpm=peak_power_rpm,
            redline=redline,
            aspiration=aspiration,
        )
    mean = total / steps
    return max(0.01, mean)


# ---------------------------------------------------------------------------
# Per-pair helpers
# ---------------------------------------------------------------------------

def _post_shift_rpm(shift_rpm: int, ratio_from: float, ratio_to: float) -> int:
    """RPM in the next gear immediately after the upshift.

    post = shift_rpm × ratio_to / ratio_from

    The final-drive ratio cancels (it appears in both numerator and
    denominator via wheel-speed continuity) so it is not needed here.
    """
    if ratio_from <= 0:
        return 0
    return int(round(shift_rpm * ratio_to / ratio_from))


def _time_proxy(
    shift_rpm: int,
    post_rpm: int,
    ratio_from: float,
    ratio_to: float,
    *,
    peak_torque_rpm: int,
    peak_power_rpm: int,
    redline: int,
    aspiration: str,
) -> float:
    """Proxy for elapsed time through a gear transition.

    = time_in_gear (current gear, shift_rpm → redline)
    + SHIFT_LOSS_S
    + time_in_next_gear (next gear, post_rpm → redline)

    Uses SPEED_WINDOW / mean_torque as a proportional elapsed-time measure.
    """
    mt_cur = _mean_torque(
        shift_rpm, redline,
        peak_torque_rpm=peak_torque_rpm, peak_power_rpm=peak_power_rpm,
        redline=redline, aspiration=aspiration,
    )
    mt_nxt = _mean_torque(
        post_rpm, redline,
        peak_torque_rpm=peak_torque_rpm, peak_power_rpm=peak_power_rpm,
        redline=redline, aspiration=aspiration,
    )
    return SPEED_WINDOW / mt_cur + SHIFT_LOSS_S + SPEED_WINDOW / mt_nxt


# ---------------------------------------------------------------------------
# Qualifying optimiser
# ---------------------------------------------------------------------------

def _qualifying_decision_for_pair(
    pair_index: int,
    ratio_from: float,
    ratio_to: float,
    *,
    peak_torque_rpm: int,
    peak_power_rpm: int,
    redline: int,
    aspiration: str,
) -> PerGearShiftDecision:
    """Find the lowest-time shift RPM for gear pair (pair_index → pair_index+1).

    Returns an invalid decision when the power band is too narrow to evaluate.
    """
    from_gear = pair_index + 1
    to_gear = pair_index + 2

    qual_floor = int(QUAL_MIN_RPM_FRACTION * peak_power_rpm)
    useful_floor = int(MIN_USEFUL_RPM_FRACTION * peak_power_rpm)

    # Build candidate list
    candidates: List[int] = list(range(qual_floor, redline + 1, SWEEP_STEP_RPM))
    if not candidates or candidates[-1] < redline:
        # ensure we always include the top of the sweep range
        if qual_floor <= redline:
            candidates.append(redline)
    # Deduplicate and sort
    candidates = sorted(set(candidates))

    best_rpm: Optional[int] = None
    best_time: float = float("inf")

    for cand in candidates:
        if cand > redline:
            break
        post = _post_shift_rpm(cand, ratio_from, ratio_to)
        t = _time_proxy(
            cand, post, ratio_from, ratio_to,
            peak_torque_rpm=peak_torque_rpm,
            peak_power_rpm=peak_power_rpm,
            redline=redline,
            aspiration=aspiration,
        )
        if t < best_time:
            best_time = t
            best_rpm = cand

    if best_rpm is None:
        return PerGearShiftDecision(
            from_gear=from_gear, to_gear=to_gear,
            qualifying_target_rpm=None, race_target_rpm=None,
            rpm_delta_from_qualifying=None, expected_post_shift_rpm=None,
            predicted_time_cost=None, predicted_fuel_saving=None,
            evidence_source="insufficient_data", sample_count=0,
            confidence=ShiftConfidence.INSUFFICIENT_EVIDENCE,
            rationale=f"Gear {from_gear}→{to_gear}: no valid shift point in sweep range.",
            valid=False,
        )

    post_rpm = _post_shift_rpm(best_rpm, ratio_from, ratio_to)

    # Check post-shift RPM is above the useful floor
    if post_rpm < useful_floor:
        return PerGearShiftDecision(
            from_gear=from_gear, to_gear=to_gear,
            qualifying_target_rpm=best_rpm, race_target_rpm=None,
            rpm_delta_from_qualifying=None, expected_post_shift_rpm=post_rpm,
            predicted_time_cost=None, predicted_fuel_saving=None,
            evidence_source="below_powerband", sample_count=0,
            confidence=ShiftConfidence.INSUFFICIENT_EVIDENCE,
            rationale=(
                f"Gear {from_gear}→{to_gear}: post-shift RPM {post_rpm} rpm is below "
                f"the power-band floor ({useful_floor} rpm). "
                "Check gear ratios or enter more accurate engine data."
            ),
            valid=False,
        )

    return PerGearShiftDecision(
        from_gear=from_gear, to_gear=to_gear,
        qualifying_target_rpm=best_rpm, race_target_rpm=best_rpm,
        rpm_delta_from_qualifying=0, expected_post_shift_rpm=post_rpm,
        predicted_time_cost=0.0, predicted_fuel_saving=0.0,
        evidence_source="manual_engine_data", sample_count=0,
        confidence=ShiftConfidence.PROVISIONAL,
        rationale=(
            f"Gear {from_gear}→{to_gear}: shift at {best_rpm} rpm "
            f"(post-shift {post_rpm} rpm in gear {to_gear}). "
            "Provisional — based on manually entered engine data."
        ),
        valid=True,
    )


# ---------------------------------------------------------------------------
# Race optimiser
# ---------------------------------------------------------------------------

def _race_decisions(
    qual_decisions: List[PerGearShiftDecision],
    ratio_list: List[float],
    *,
    peak_torque_rpm: int,
    peak_power_rpm: int,
    redline: int,
    aspiration: str,
    required_fuel_saving_pct: float,
) -> Tuple[List[PerGearShiftDecision], float, Optional[float]]:
    """Compute race shift targets using a cross-gear greedy optimiser.

    Returns (race_decisions, predicted_fuel_saving_pct, predicted_time_cost_per_lap).

    At required_fuel_saving_pct == 0.0 (or ≤ epsilon) every race target equals
    the qualifying target (no short-shifting).
    """
    _EPS = 1e-9
    target_frac = required_fuel_saving_pct / 100.0

    # Build per-pair candidate tables first
    # candidate: (gear_pair_index, cand_rpm, time_cost, fuel_saving_frac, saving_per_s)
    PairCandidate = Tuple[int, int, float, float, float]  # type alias hint

    if required_fuel_saving_pct <= _EPS:
        # No fuel saving needed — race == qualifying
        decisions = []
        for d in qual_decisions:
            decisions.append(PerGearShiftDecision(
                from_gear=d.from_gear, to_gear=d.to_gear,
                qualifying_target_rpm=d.qualifying_target_rpm,
                race_target_rpm=d.qualifying_target_rpm,
                rpm_delta_from_qualifying=0,
                expected_post_shift_rpm=d.expected_post_shift_rpm,
                predicted_time_cost=0.0,
                predicted_fuel_saving=0.0,
                evidence_source=d.evidence_source,
                sample_count=d.sample_count,
                confidence=d.confidence,
                rationale=d.rationale,
                valid=d.valid,
            ))
        return decisions, 0.0, 0.0

    race_floor = int(RACE_MIN_RPM_FRACTION * peak_power_rpm)

    # Collect all non-dominated candidates across all valid gear pairs
    all_candidates: List[PairCandidate] = []

    for pair_idx, d in enumerate(qual_decisions):
        if not d.valid or d.qualifying_target_rpm is None:
            continue
        qual_rpm = d.qualifying_target_rpm
        ratio_from = ratio_list[pair_idx]
        ratio_to = ratio_list[pair_idx + 1]

        # Compute qualifying elapsed time (baseline for time_cost)
        qual_post = _post_shift_rpm(qual_rpm, ratio_from, ratio_to)
        qual_time = _time_proxy(
            qual_rpm, qual_post, ratio_from, ratio_to,
            peak_torque_rpm=peak_torque_rpm, peak_power_rpm=peak_power_rpm,
            redline=redline, aspiration=aspiration,
        )

        # Build candidates for this pair
        pair_candidates: List[Tuple[int, float, float, float]] = []
        # (cand_rpm, time_cost, fuel_saving_frac, saving_per_s_lost)

        sweep_start = min(qual_rpm - SWEEP_STEP_RPM, qual_rpm)
        sweep_end = max(race_floor, qual_rpm - 1)

        cand = sweep_start
        while cand >= race_floor:
            if cand >= qual_rpm:
                cand -= SWEEP_STEP_RPM
                continue
            post = _post_shift_rpm(cand, ratio_from, ratio_to)
            # Skip if post-shift RPM is below useful floor
            useful_floor = int(MIN_USEFUL_RPM_FRACTION * peak_power_rpm)
            if post < useful_floor:
                cand -= SWEEP_STEP_RPM
                continue

            t = _time_proxy(
                cand, post, ratio_from, ratio_to,
                peak_torque_rpm=peak_torque_rpm, peak_power_rpm=peak_power_rpm,
                redline=redline, aspiration=aspiration,
            )
            time_cost = t - qual_time  # positive = slower
            if time_cost < 0:
                time_cost = 0.0

            fuel_saving_frac = (qual_rpm - cand) / qual_rpm * FUEL_BURN_RPM_COEFFICIENT

            if time_cost > _EPS:
                saving_per_s = fuel_saving_frac / time_cost
            else:
                saving_per_s = fuel_saving_frac * 1e6  # effectively free saving

            pair_candidates.append((cand, time_cost, fuel_saving_frac, saving_per_s))
            cand -= SWEEP_STEP_RPM

        # Remove dominated candidates:
        # A dominates B if A.time_cost <= B.time_cost AND A.fuel_saving >= B.fuel_saving
        # with at least one strict.
        non_dominated: List[Tuple[int, float, float, float]] = []
        for i, (r_i, tc_i, fs_i, sps_i) in enumerate(pair_candidates):
            dominated = False
            for j, (r_j, tc_j, fs_j, sps_j) in enumerate(pair_candidates):
                if i == j:
                    continue
                if tc_j <= tc_i and fs_j >= fs_i and (tc_j < tc_i or fs_j > fs_i):
                    dominated = True
                    break
            if not dominated:
                non_dominated.append((r_i, tc_i, fs_i, sps_i))

        for (cand_rpm, tc, fs, sps) in non_dominated:
            all_candidates.append((pair_idx, cand_rpm, tc, fs, sps))

    # Greedy selection: sort by saving_per_second_lost descending
    all_candidates.sort(key=lambda c: c[4], reverse=True)

    # Track selected race RPM per pair (default = qualifying RPM)
    selected: dict[int, Tuple[int, float, float]] = {}  # pair_idx -> (rpm, tc, fs)

    total_fuel_saving = 0.0
    _OVER_SAVE_EPSILON = 0.001  # don't over-save beyond target + 0.1%

    for pair_idx, cand_rpm, tc, fs, sps in all_candidates:
        if total_fuel_saving >= target_frac + _OVER_SAVE_EPSILON:
            break
        # Don't exceed target unnecessarily — but only skip if we already have
        # a candidate for this pair (we can't split a pair)
        if pair_idx in selected:
            continue
        selected[pair_idx] = (cand_rpm, tc, fs)
        total_fuel_saving += fs

    # Build final decisions
    decisions: List[PerGearShiftDecision] = []
    total_time_cost = 0.0

    for pair_idx, d in enumerate(qual_decisions):
        if not d.valid or d.qualifying_target_rpm is None:
            # carry through invalid decisions unchanged
            decisions.append(PerGearShiftDecision(
                from_gear=d.from_gear, to_gear=d.to_gear,
                qualifying_target_rpm=d.qualifying_target_rpm,
                race_target_rpm=None,
                rpm_delta_from_qualifying=None,
                expected_post_shift_rpm=d.expected_post_shift_rpm,
                predicted_time_cost=None, predicted_fuel_saving=None,
                evidence_source=d.evidence_source, sample_count=d.sample_count,
                confidence=d.confidence, rationale=d.rationale, valid=d.valid,
            ))
            continue

        qual_rpm = d.qualifying_target_rpm
        ratio_from = ratio_list[pair_idx]
        ratio_to = ratio_list[pair_idx + 1]

        if pair_idx in selected:
            race_rpm, tc, fs = selected[pair_idx]
            total_time_cost += tc
            post_rpm = _post_shift_rpm(race_rpm, ratio_from, ratio_to)
            delta = race_rpm - qual_rpm  # negative when short-shifting
            decisions.append(PerGearShiftDecision(
                from_gear=d.from_gear, to_gear=d.to_gear,
                qualifying_target_rpm=qual_rpm,
                race_target_rpm=race_rpm,
                rpm_delta_from_qualifying=delta,
                expected_post_shift_rpm=post_rpm,
                predicted_time_cost=tc,
                predicted_fuel_saving=fs,
                evidence_source="manual_engine_data", sample_count=0,
                confidence=ShiftConfidence.PROVISIONAL,
                rationale=(
                    f"Gear {d.from_gear}→{d.to_gear}: race shifts at {race_rpm} rpm "
                    f"({abs(delta)} rpm earlier than qualifying) — "
                    f"saves ~{fs * 100:.1f}% fuel, costs ~{tc:.3f}s."
                ),
                valid=True,
            ))
        else:
            # No short-shift selected for this pair
            post_rpm = _post_shift_rpm(qual_rpm, ratio_from, ratio_to)
            decisions.append(PerGearShiftDecision(
                from_gear=d.from_gear, to_gear=d.to_gear,
                qualifying_target_rpm=qual_rpm,
                race_target_rpm=qual_rpm,
                rpm_delta_from_qualifying=0,
                expected_post_shift_rpm=post_rpm,
                predicted_time_cost=0.0,
                predicted_fuel_saving=0.0,
                evidence_source="manual_engine_data", sample_count=0,
                confidence=ShiftConfidence.PROVISIONAL,
                rationale=(
                    f"Gear {d.from_gear}→{d.to_gear}: race shifts at qualifying point "
                    f"({qual_rpm} rpm) — no short-shift needed to meet fuel target."
                ),
                valid=True,
            ))

    predicted_fuel_pct = total_fuel_saving * 100.0
    predicted_time_cost = total_time_cost if total_time_cost > 0 else 0.0

    return decisions, predicted_fuel_pct, predicted_time_cost


# ---------------------------------------------------------------------------
# Insufficient-evidence sentinel builder
# ---------------------------------------------------------------------------

def _insufficient_result(
    inputs: ShiftStrategyInputs,
    fingerprint: str,
    missing: Tuple[str, ...],
    warnings: Tuple[str, ...] = (),
) -> "ShiftStrategyResult":
    empty_profile = ShiftProfile(
        mode="qualifying", decisions=(), overall_confidence=ShiftConfidence.INSUFFICIENT_EVIDENCE
    )
    empty_race = ShiftProfile(
        mode="race", decisions=(), overall_confidence=ShiftConfidence.INSUFFICIENT_EVIDENCE
    )
    return ShiftStrategyResult(
        car_id=inputs.car_id,
        configuration_fingerprint=fingerprint,
        qualifying_profile=empty_profile,
        race_profile=empty_race,
        required_fuel_saving_pct=0.0,
        predicted_fuel_saving_pct=0.0,
        predicted_time_cost_per_lap=None,
        overall_confidence=ShiftConfidence.INSUFFICIENT_EVIDENCE,
        evidence_summary="Insufficient evidence — see missing_evidence for next steps.",
        missing_evidence=missing,
        warnings=warnings,
        stale_reason="",
        algorithm_version=SHIFT_STRATEGY_VERSION,
        # Carry the engine fields even on insufficient results so the VM can
        # distinguish "no ratios" (stage 0) from "ratios but no engine data" (stage 1).
        engine_peak_power_rpm=inputs.peak_power_rpm,
        engine_peak_torque_rpm=inputs.peak_torque_rpm,
        engine_redline=inputs.redline,
        gear_ratio_count=len(inputs.gear_ratios),
    )


# ---------------------------------------------------------------------------
# Confidence helpers
# ---------------------------------------------------------------------------

_CONFIDENCE_RANK = {
    ShiftConfidence.HIGH: 6,
    ShiftConfidence.MEDIUM: 5,
    ShiftConfidence.LOW: 4,
    ShiftConfidence.PROVISIONAL: 3,
    ShiftConfidence.STALE: 2,
    ShiftConfidence.INSUFFICIENT_EVIDENCE: 1,
}


def _weakest(confidences) -> ShiftConfidence:
    """Return the weakest (lowest-rank) confidence level."""
    if not confidences:
        return ShiftConfidence.INSUFFICIENT_EVIDENCE
    return min(confidences, key=lambda c: _CONFIDENCE_RANK.get(c, 0))


def _cap_at_provisional(c: ShiftConfidence) -> ShiftConfidence:
    """Phase 1 cap: manual data cannot exceed PROVISIONAL."""
    if _CONFIDENCE_RANK.get(c, 0) > _CONFIDENCE_RANK[ShiftConfidence.PROVISIONAL]:
        return ShiftConfidence.PROVISIONAL
    return c


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_shift_strategy(
    inputs: ShiftStrategyInputs,
    *,
    required_fuel_saving_pct: float = 0.0,
) -> ShiftStrategyResult:
    """Compute per-gear shift targets for qualifying and race.

    Never raises.  Returns an INSUFFICIENT_EVIDENCE result with descriptive
    missing_evidence strings whenever required data is absent.

    Phase-1 confidence ceiling: all outputs capped at PROVISIONAL because
    engine data is supplied manually, not telemetry-calibrated.
    """
    from strategy.shift_strategy_inputs import compute_shift_fingerprint

    try:
        fingerprint = compute_shift_fingerprint(inputs)

        # --- Guard: gear ratios required ---
        if len(inputs.gear_ratios) < 2:
            return _insufficient_result(
                inputs, fingerprint,
                missing=(
                    "Gear ratios: enter at least 2 gear ratios in the Garage "
                    "Transmission sheet (gear 1 through final gear).",
                ),
            )

        # --- Guard: engine data required ---
        missing: List[str] = []
        if inputs.peak_power_rpm is None:
            missing.append(
                "Peak power RPM: enter the RPM at which this car produces peak power "
                "(check the car's Tuning screen or the GT7 car spec page)."
            )
        if inputs.peak_torque_rpm is None:
            missing.append(
                "Peak torque RPM: enter the RPM at which peak torque occurs "
                "(available on the GT7 car spec page)."
            )
        if inputs.redline is None:
            missing.append(
                "Redline / rev limiter RPM: enter the maximum RPM before the "
                "limiter cuts in (visible on the in-game rev counter)."
            )
        if missing:
            return _insufficient_result(inputs, fingerprint, tuple(missing))

        # All engine data present — safe to unwrap
        peak_power_rpm: int = inputs.peak_power_rpm  # type: ignore[assignment]
        peak_torque_rpm: int = inputs.peak_torque_rpm  # type: ignore[assignment]
        redline: int = inputs.redline  # type: ignore[assignment]

        # Sanity check ordering
        warnings: List[str] = []
        if peak_torque_rpm >= peak_power_rpm:
            warnings.append(
                f"Peak torque RPM ({peak_torque_rpm}) ≥ peak power RPM ({peak_power_rpm}). "
                "Check entered values — on most combustion engines torque peaks before power. "
                "The curve model will be less accurate."
            )
        if peak_power_rpm >= redline:
            warnings.append(
                f"Peak power RPM ({peak_power_rpm}) ≥ redline ({redline}). "
                "Check entered values."
            )

        ratio_list = list(inputs.gear_ratios)
        n_pairs = len(ratio_list) - 1  # pairs: gear 1→2, 2→3, …

        # --- Qualifying profile ---
        qual_decisions: List[PerGearShiftDecision] = []
        for i in range(n_pairs):
            d = _qualifying_decision_for_pair(
                i, ratio_list[i], ratio_list[i + 1],
                peak_torque_rpm=peak_torque_rpm,
                peak_power_rpm=peak_power_rpm,
                redline=redline,
                aspiration=inputs.aspiration,
            )
            qual_decisions.append(d)

        # Include ALL decisions (valid and invalid) so one below-powerband pair
        # drags the overall confidence down to INSUFFICIENT_EVIDENCE as the brief
        # requires: "overall confidence = weakest across covered pairs".
        qual_confidences = [d.confidence for d in qual_decisions]
        if not qual_confidences:
            qual_confidences = [ShiftConfidence.INSUFFICIENT_EVIDENCE]

        qual_overall = _cap_at_provisional(_weakest(qual_confidences))

        qualifying_profile = ShiftProfile(
            mode="qualifying",
            decisions=tuple(qual_decisions),
            overall_confidence=qual_overall,
        )

        # --- Race profile ---
        race_decisions_list, predicted_fuel_pct, predicted_time_cost = _race_decisions(
            qual_decisions, ratio_list,
            peak_torque_rpm=peak_torque_rpm,
            peak_power_rpm=peak_power_rpm,
            redline=redline,
            aspiration=inputs.aspiration,
            required_fuel_saving_pct=required_fuel_saving_pct,
        )

        race_confidences = [d.confidence for d in race_decisions_list]
        if not race_confidences:
            race_confidences = [ShiftConfidence.INSUFFICIENT_EVIDENCE]

        race_overall = _cap_at_provisional(_weakest(race_confidences))

        race_profile = ShiftProfile(
            mode="race",
            decisions=tuple(race_decisions_list),
            overall_confidence=race_overall,
        )

        # --- Overall ---
        overall = _cap_at_provisional(
            _weakest([qual_overall, race_overall])
        )

        # Evidence summary
        valid_pairs = sum(1 for d in qual_decisions if d.valid)
        evidence_summary = (
            f"{valid_pairs} of {n_pairs} gear pair(s) computed from manually entered "
            f"engine data (peak power {peak_power_rpm} rpm, "
            f"peak torque {peak_torque_rpm} rpm, redline {redline} rpm). "
            "Confidence capped at PROVISIONAL — Phase 1 uses no telemetry calibration."
        )

        return ShiftStrategyResult(
            car_id=inputs.car_id,
            configuration_fingerprint=fingerprint,
            qualifying_profile=qualifying_profile,
            race_profile=race_profile,
            required_fuel_saving_pct=required_fuel_saving_pct,
            predicted_fuel_saving_pct=predicted_fuel_pct,
            predicted_time_cost_per_lap=predicted_time_cost,
            overall_confidence=overall,
            evidence_summary=evidence_summary,
            missing_evidence=(),
            warnings=tuple(warnings),
            stale_reason="",
            algorithm_version=SHIFT_STRATEGY_VERSION,
            # Public engine-data fields — readable by VM without private attr crawl.
            engine_peak_power_rpm=peak_power_rpm,
            engine_peak_torque_rpm=peak_torque_rpm,
            engine_redline=redline,
            gear_ratio_count=len(inputs.gear_ratios),
        )

    except Exception as exc:  # pragma: no cover - defensive
        from strategy.shift_strategy_inputs import compute_shift_fingerprint as _fp
        try:
            fp = _fp(inputs)
        except Exception:
            fp = "error"
        return _insufficient_result(
            inputs, fp,
            missing=(
                f"Engine error: {exc!r}. "
                "Enter gear ratios and engine data and try again.",
            ),
            warnings=("An unexpected error occurred in the shift strategy engine.",),
        )
