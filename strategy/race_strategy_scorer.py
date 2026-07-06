"""Group 48 — Race Strategy Brain Phase 2: total-race-time scoring engine.

WHY IT EXISTS
  Ranks strategy candidates by *estimated total race time*, not by fastest lap.
  A slightly slower plan that avoids a pit stop can win; a faster plan can be
  demoted when its fuel evidence is weak or when it risks a fragile rear.  All of
  that is expressed as deterministic, itemised time costs so the driver can see
  exactly where the seconds go.

MODEL (deterministic, evidence-gated)
  total_time = green_base + degradation_cost + pit_time + fuel_saving_cost + compound_cost

    green_base       race_laps × representative (median) race-pace lap
    degradation_cost per-stint tyre-life penalty, from MEASURED tyre-wear samples
                     only — zero (with a note) when no wear data exists
    pit_time         candidate's pit-lane loss + refuel time (already computed
                     from measured fuel use + event pit loss / refuel rate)
    fuel_saving_cost per-lap time price of a lean fuel map, applied ONLY to a
                     fuel-save candidate (documented model constant)
    compound_cost    measured per-compound pace delta × laps, applied ONLY where
                     per-compound pace evidence exists — never invented

  Consistency / traffic do NOT move the point estimate (they would shift every
  candidate equally); they surface as risk flags instead, honouring "penalty only
  if existing evidence supports it".

SAFETY
  Pure: no PyQt6, no DB, no I/O, no AI, never raises.  Authors no setup values,
  cannot touch the Apply gate or any setup recommendation.  When required
  evidence is missing the confidence drops or the recommendation returns
  INSUFFICIENT_EVIDENCE — it never invents certainty.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean
from typing import Optional

from strategy.race_strategy_candidates import (
    FUEL_MAP_PUSH,
    FUEL_MAP_SAVE,
    Legality,
    RiskLevel,
    StrategyCandidate,
    generate_candidates,
    legal_candidates,
)
from strategy.race_strategy_evidence import (
    RaceStrategyEvidence,
    StrategyConfidence,
)


# ---------------------------------------------------------------------------
# Model constants (documented engineering assumptions)
# ---------------------------------------------------------------------------

# Per-lap lap-time price of running a fuel-saving (lean / lift-and-coast) map.
# Pairs with FUEL_SAVE_CONSUMPTION_FACTOR in race_strategy_candidates.py.
FUEL_SAVE_TIME_PENALTY_S_PER_LAP: float = 0.40

# Two candidates whose total times are within this margin are treated as a tie;
# the safer (lower-risk) plan is then preferred.  Encodes "safety of the plan".
SAFETY_TIE_TOLERANCE_S: float = 5.0


# ---------------------------------------------------------------------------
# Score model
# ---------------------------------------------------------------------------

@dataclass
class StrategyScore:
    """Deterministic scored outcome for a single candidate."""

    rank: int
    candidate_id: str
    estimated_total_time_seconds: float
    estimated_gap_to_best_seconds: float
    estimated_average_lap_time: float
    pit_time_total_seconds: float
    refuel_time_total_seconds: float
    degradation_cost_seconds: float
    fuel_saving_cost_seconds: float
    compound_cost_seconds: float
    confidence: StrategyConfidence
    risk_flags: list[str] = field(default_factory=list)
    reasoning_summary: str = ""


@dataclass
class StrategyRecommendation:
    """The recommended strategy plus the full ranked field and honest context."""

    recommended: Optional[StrategyScore]
    ranked: list[StrategyScore]
    candidates: list[StrategyCandidate]
    confidence: StrategyConfidence
    missing_evidence: list[str]
    reason: str = ""

    @property
    def has_recommendation(self) -> bool:
        return self.recommended is not None


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_candidate(
    candidate: StrategyCandidate,
    evidence: RaceStrategyEvidence,
    *,
    rear_traction_fragile: bool = False,
) -> Optional[StrategyScore]:
    """Score one candidate deterministically, or None when pace is unknown.

    ``rear_traction_fragile`` (typically derived from the structured driver
    profile) adds a risk flag and, for aggressive fuel maps, is what lets the
    recommender demote a snap-happy push plan in favour of a stable one.
    """
    base_lap_s = evidence.representative_lap_s()
    if base_lap_s <= 0:
        return None  # cannot estimate total race time without a pace reference

    race_laps = sum(candidate.estimated_laps_per_stint)
    if race_laps <= 0:
        return None

    green_base = base_lap_s * race_laps

    # --- degradation cost (measured tyre-wear samples only) ---
    deg_rate = _degradation_rate_s_per_lap(evidence)
    degradation_cost = 0.0
    for laps in candidate.estimated_laps_per_stint:
        # Linear accumulation within each stint: lap i (0-indexed) loses i*rate.
        degradation_cost += deg_rate * (laps * (laps - 1) / 2.0)

    # --- fuel-saving cost (only for a fuel-save map) ---
    fuel_saving_cost = 0.0
    if FUEL_MAP_SAVE in candidate.fuel_map_plan:
        fuel_saving_cost = FUEL_SAVE_TIME_PENALTY_S_PER_LAP * race_laps

    # --- compound cost (only where per-compound pace evidence exists) ---
    compound_cost = _compound_cost(candidate, evidence, base_lap_s)

    pit_time = candidate.estimated_pit_time
    total = green_base + degradation_cost + pit_time + fuel_saving_cost + compound_cost

    on_track_time = green_base + degradation_cost + fuel_saving_cost + compound_cost
    avg_lap = on_track_time / race_laps if race_laps else 0.0

    confidence = StrategyConfidence.worst(evidence.evidence_confidence, candidate.confidence)

    risk_flags = _risk_flags(candidate, evidence, deg_rate, rear_traction_fragile)
    reasoning = _score_reasoning(candidate, degradation_cost, pit_time, fuel_saving_cost, compound_cost)

    return StrategyScore(
        rank=0,  # assigned by score_candidates()
        candidate_id=candidate.candidate_id,
        estimated_total_time_seconds=round(total, 2),
        estimated_gap_to_best_seconds=0.0,  # assigned by score_candidates()
        estimated_average_lap_time=round(avg_lap, 3),
        pit_time_total_seconds=round(pit_time, 2),
        refuel_time_total_seconds=round(candidate.estimated_refuel_time, 2),
        degradation_cost_seconds=round(degradation_cost, 2),
        fuel_saving_cost_seconds=round(fuel_saving_cost, 2),
        compound_cost_seconds=round(compound_cost, 2),
        confidence=confidence,
        risk_flags=risk_flags,
        reasoning_summary=reasoning,
    )


def score_candidates(
    candidates: list[StrategyCandidate],
    evidence: RaceStrategyEvidence,
    *,
    rear_traction_fragile: bool = False,
    legal_only: bool = True,
) -> list[StrategyScore]:
    """Score and rank candidates by estimated total race time (ascending).

    Illegal candidates are dropped when ``legal_only`` (the default) — a legality
    violation is never merely a time penalty.  Ranks are 1-based; ties are broken
    by input order for determinism.
    """
    pool = [c for c in candidates if (c.is_legal or not legal_only)]
    scored = [
        s for s in (
            score_candidate(c, evidence, rear_traction_fragile=rear_traction_fragile)
            for c in pool
        )
        if s is not None
    ]
    if not scored:
        return []

    # Rank by total time (ascending); stable by original order for ties.
    order = sorted(range(len(scored)), key=lambda i: (scored[i].estimated_total_time_seconds, i))
    best_time = scored[order[0]].estimated_total_time_seconds
    for rank_1based, idx in enumerate(order, start=1):
        scored[idx].rank = rank_1based
        scored[idx].estimated_gap_to_best_seconds = round(
            scored[idx].estimated_total_time_seconds - best_time, 2
        )
    scored.sort(key=lambda s: s.rank)
    return scored


# ---------------------------------------------------------------------------
# Recommendation (generator + scorer + safety tie-break)
# ---------------------------------------------------------------------------

def recommend_strategy(
    evidence: RaceStrategyEvidence,
    *,
    rear_traction_fragile: bool = False,
) -> StrategyRecommendation:
    """End-to-end: generate legal candidates, score them, pick the best.

    Honesty gates:
      • INSUFFICIENT_EVIDENCE evidence, or no scorable/legal candidate, yields a
        recommendation with ``recommended=None`` and an explanatory reason.
      • Among candidates within :data:`SAFETY_TIE_TOLERANCE_S` of the fastest,
        the lowest-risk plan is chosen (safety-first), so a marginally quicker
        but fragile push loses to a stable plan.
    """
    missing = list(evidence.missing_evidence_text())

    if evidence.evidence_confidence == StrategyConfidence.INSUFFICIENT_EVIDENCE:
        return StrategyRecommendation(
            recommended=None,
            ranked=[],
            candidates=[],
            confidence=StrategyConfidence.INSUFFICIENT_EVIDENCE,
            missing_evidence=missing,
            reason=(
                "Not enough race evidence to model a strategy — "
                "need at least clean lap times and fuel-use data."
            ),
        )

    candidates = generate_candidates(evidence)
    legal = legal_candidates(candidates)
    scored = score_candidates(
        candidates, evidence, rear_traction_fragile=rear_traction_fragile, legal_only=True
    )

    if not scored:
        return StrategyRecommendation(
            recommended=None,
            ranked=[],
            candidates=candidates,
            confidence=StrategyConfidence.worst(evidence.evidence_confidence),
            missing_evidence=missing,
            reason=(
                "No legal strategy could be scored — either the race length or the "
                "pace reference is missing, or every candidate violates an event rule."
            ),
        )

    recommended = _safety_aware_pick(scored)

    return StrategyRecommendation(
        recommended=recommended,
        ranked=scored,
        candidates=candidates,
        confidence=recommended.confidence,
        missing_evidence=missing,
        reason=recommended.reasoning_summary,
    )


def _safety_aware_pick(scored: list[StrategyScore]) -> StrategyScore:
    """Pick the fastest plan, but prefer a safer one inside the tie tolerance."""
    best = scored[0]
    contenders = [
        s for s in scored
        if s.estimated_gap_to_best_seconds <= SAFETY_TIE_TOLERANCE_S
    ]
    # Lower risk wins the tie; total time breaks a risk tie (stable).
    return min(contenders, key=lambda s: (_risk_ordinal(s), s.estimated_total_time_seconds))


# ---------------------------------------------------------------------------
# Cost helpers
# ---------------------------------------------------------------------------

def _degradation_rate_s_per_lap(evidence: RaceStrategyEvidence) -> float:
    """Measured per-lap degradation rate in seconds, or 0.0 when unknown.

    ``tyre_wear_samples`` are interpreted as the per-lap pace-loss increment
    already measured at THIS event's tyre-wear multiplier, so the multiplier is
    not re-applied (that would double-count).  No samples → 0.0 (no invention).
    """
    if not evidence.tyre_wear_samples:
        return 0.0
    rate = mean(evidence.tyre_wear_samples)
    return rate if rate > 0 else 0.0


def _compound_cost(
    candidate: StrategyCandidate,
    evidence: RaceStrategyEvidence,
    base_lap_s: float,
) -> float:
    """Sum measured per-compound pace deltas over the plan (evidence-gated).

    A stint on a compound whose MEASURED median pace is slower than the
    reference costs (delta × laps).  Compounds with no per-compound samples
    contribute nothing — the cost is never invented.
    """
    if not evidence.compound_samples:
        return 0.0
    cost = 0.0
    for i, compound in enumerate(candidate.compound_plan):
        pace = evidence.compound_pace_s(compound)
        if pace <= 0:
            continue
        laps = candidate.estimated_laps_per_stint[i] if i < len(candidate.estimated_laps_per_stint) else 0
        delta = pace - base_lap_s
        if delta > 0:
            cost += delta * laps
    return cost


# ---------------------------------------------------------------------------
# Risk / reasoning
# ---------------------------------------------------------------------------

_RISK_ORDER: dict[RiskLevel, int] = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
}


def _risk_ordinal(score: StrategyScore) -> int:
    """Ordinal risk for tie-breaking: more risk flags → higher (worse)."""
    return len(score.risk_flags)


def _risk_flags(
    candidate: StrategyCandidate,
    evidence: RaceStrategyEvidence,
    deg_rate: float,
    rear_traction_fragile: bool,
) -> list[str]:
    flags: list[str] = []

    if candidate.risk_level == RiskLevel.HIGH:
        flags.append("high-risk plan")

    if candidate.pit_count == 0 and evidence.fuel_use_samples:
        # A no-stop is fuel-critical.
        flags.append("no-stop: no margin for a fuel or tyre problem")

    if FUEL_MAP_PUSH in candidate.fuel_map_plan:
        if rear_traction_fragile:
            flags.append("rear traction fragile — an attacking map risks snap oversteer")
        else:
            flags.append("attacking fuel map — higher tyre and fuel risk")

    if FUEL_MAP_SAVE in candidate.fuel_map_plan and not evidence.has_long_run_data():
        flags.append("fuel-save plan relies on unproven long-run pace")

    if deg_rate <= 0 and candidate.pit_count == 0:
        flags.append("no tyre-degradation data — a no-stop cannot be verified")

    if evidence.weather_context in ("random", "unstable", "wet"):
        flags.append("weather unstable — plan may need to change")

    if evidence.driver_consistency and evidence.driver_consistency > 0.015:
        flags.append("lap-time consistency is poor — real spread will be wider")

    return flags


def _score_reasoning(
    candidate: StrategyCandidate,
    degradation_cost: float,
    pit_time: float,
    fuel_saving_cost: float,
    compound_cost: float,
) -> str:
    bits = [f"{candidate.pit_count}-stop"]
    if pit_time > 0:
        bits.append(f"{pit_time:.0f}s in the pits")
    if degradation_cost > 0:
        bits.append(f"{degradation_cost:.0f}s tyre degradation")
    if fuel_saving_cost > 0:
        bits.append(f"{fuel_saving_cost:.0f}s lost to fuel saving")
    if compound_cost > 0:
        bits.append(f"{compound_cost:.0f}s compound pace delta")
    return ", ".join(bits) + "."


# ---------------------------------------------------------------------------
# Fuel-saving worth-it helper (explicit maths for the explanation surface)
# ---------------------------------------------------------------------------

def fuel_save_worth_it(fuel_save_total_s: float, extra_stop_total_s: float) -> bool:
    """True when a fuel-save plan's total time beats the extra-stop alternative.

    Encodes the rule "recommend fuel saving only if the time lost is less than
    the pit/refuel time saved" as a direct total-time comparison.
    """
    return fuel_save_total_s < extra_stop_total_s
