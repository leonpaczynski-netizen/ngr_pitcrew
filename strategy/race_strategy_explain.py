"""Group 48 — Race Strategy Brain Phase 2: driver-readable explanation surface.

WHY IT EXISTS
  A number without a "why" is not trustworthy.  This module turns a scored
  :class:`~strategy.race_strategy_scorer.StrategyRecommendation` into a compact,
  honest explanation the driver can read at a glance.  Crucially it keeps four
  categories visibly separate so nothing masquerades as fact:

      KNOWN EVIDENCE   — things actually measured this session
      CALCULATED       — deterministic estimates derived from that evidence
      ASSUMPTION       — documented model defaults (fuel-map penalties, event
                         pit-loss default, representative-lap choice)
      MISSING EVIDENCE — what we do NOT know, stated plainly
      RISK             — flags that could break the plan

HONESTY
  Never emits "perfect strategy" / "guaranteed win" language.  When there is no
  recommendation it says so and shows what evidence is missing.  Pure module:
  no PyQt6, no I/O, never raises.  It renders text/HTML only — it authors no
  setup values and cannot touch the Apply gate.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from strategy.race_strategy_candidates import StrategyCandidate
from strategy.race_strategy_evidence import RaceStrategyEvidence, StrategyConfidence
from strategy.race_strategy_scorer import StrategyRecommendation, StrategyScore


@dataclass
class StrategyExplanation:
    """Structured, category-separated explanation of a strategy recommendation."""

    recommended_plan: str                    # e.g. "One-stop race plan"
    why: str                                 # prose comparing to the runner-up
    confidence: str                          # StrategyConfidence value string
    known_evidence: list[str] = field(default_factory=list)
    calculated: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    has_recommendation: bool = True

    # ------------------------------------------------------------------
    def to_text(self) -> str:
        """Render a plain-text block with each category clearly labelled."""
        lines: list[str] = []
        lines.append("Recommended Strategy:")
        lines.append(f"  {self.recommended_plan}")
        lines.append("")
        if self.why:
            lines.append("Why:")
            lines.append(f"  {self.why}")
            lines.append("")
        lines.append(f"Confidence: {self.confidence}")
        lines.append("")
        _section(lines, "Known evidence", self.known_evidence)
        _section(lines, "Calculated estimate", self.calculated)
        _section(lines, "Assumptions / defaults", self.assumptions)
        _section(lines, "Missing evidence", self.missing_evidence)
        _section(lines, "Risk", self.risk_flags)
        return "\n".join(lines).rstrip() + "\n"


def _section(lines: list[str], title: str, items: list[str]) -> None:
    if not items:
        return
    lines.append(f"{title}:")
    for it in items:
        lines.append(f"  - {it}")
    lines.append("")


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

_PLAN_NAMES = {
    "nostop": "No-stop race plan",
    "1stop": "One-stop race plan",
    "2stop": "Two-stop race plan",
    "3stop": "Three-stop race plan",
    "1stop_fuelsave": "Fuel-save one-stop race plan",
    "2stop_push": "Push two-stop race plan",
    "1stop_compound_switch": "Compound-switch one-stop race plan",
}


def plan_name(candidate_id: str) -> str:
    return _PLAN_NAMES.get(candidate_id, candidate_id.replace("_", " ") + " plan")


def build_explanation(
    recommendation: StrategyRecommendation,
    evidence: RaceStrategyEvidence,
) -> StrategyExplanation:
    """Build a :class:`StrategyExplanation` from a scored recommendation.

    Deterministic and honest: only asserts what the evidence supports, labels
    every model default as an assumption, and lists missing evidence verbatim.
    """
    if not recommendation.has_recommendation or recommendation.recommended is None:
        return StrategyExplanation(
            recommended_plan="No recommendation — insufficient evidence",
            why=recommendation.reason or "Not enough race data to model a strategy.",
            confidence=StrategyConfidence.INSUFFICIENT_EVIDENCE.value,
            known_evidence=_known_evidence(evidence),
            calculated=[],
            assumptions=[],
            missing_evidence=list(recommendation.missing_evidence),
            risk_flags=[],
            has_recommendation=False,
        )

    best = recommendation.recommended
    cand = _find_candidate(recommendation, best.candidate_id)

    return StrategyExplanation(
        recommended_plan=plan_name(best.candidate_id),
        why=_why(best, recommendation.ranked),
        confidence=best.confidence.value,
        known_evidence=_known_evidence(evidence),
        calculated=_calculated(best),
        assumptions=_assumptions(cand, evidence),
        missing_evidence=list(recommendation.missing_evidence),
        risk_flags=list(best.risk_flags),
        has_recommendation=True,
    )


# ---------------------------------------------------------------------------
# Category builders
# ---------------------------------------------------------------------------

def _known_evidence(evidence: RaceStrategyEvidence) -> list[str]:
    known: list[str] = []
    if evidence.lap_time_samples:
        known.append(
            f"{len(evidence.lap_time_samples)} clean lap sample(s); "
            f"race pace ~ {evidence.representative_lap_s():.3f}s (median)."
        )
    if evidence.fuel_use_samples:
        known.append(
            f"Fuel use ~ {evidence.mean_fuel_per_lap():.2f} L/lap "
            f"({len(evidence.fuel_use_samples)} sample(s))."
        )
    if evidence.tyre_wear_samples:
        known.append(
            f"{len(evidence.tyre_wear_samples)} tyre-wear sample(s)"
            + (" (long-run)." if evidence.has_long_run_data() else " (short sample).")
        )
    if evidence.refuel_rate_lps > 0:
        known.append(f"Refuel rate {evidence.refuel_rate_lps:.2f} L/s.")
    if evidence.pit_loss_seconds > 0:
        known.append(f"Pit-lane loss {evidence.pit_loss_seconds:.1f}s.")
    if evidence.tyre_multiplier > 0:
        known.append(f"Tyre-wear multiplier {evidence.tyre_multiplier:g}×.")
    if evidence.fuel_multiplier > 0:
        known.append(f"Fuel multiplier {evidence.fuel_multiplier:g}×.")
    return known


def _calculated(best: StrategyScore) -> list[str]:
    calc = [
        f"Estimated total race time {best.estimated_total_time_seconds:.1f}s "
        f"(avg lap {best.estimated_average_lap_time:.3f}s).",
    ]
    if best.pit_time_total_seconds > 0:
        calc.append(
            f"Pit time {best.pit_time_total_seconds:.1f}s "
            f"(incl. {best.refuel_time_total_seconds:.1f}s refuelling)."
        )
    if best.degradation_cost_seconds > 0:
        calc.append(f"Tyre-degradation cost {best.degradation_cost_seconds:.1f}s.")
    if best.fuel_saving_cost_seconds > 0:
        calc.append(f"Fuel-saving time cost {best.fuel_saving_cost_seconds:.1f}s.")
    if best.compound_cost_seconds > 0:
        calc.append(f"Compound pace-delta cost {best.compound_cost_seconds:.1f}s.")
    return calc


def _assumptions(cand: Optional[StrategyCandidate], evidence: RaceStrategyEvidence) -> list[str]:
    a = ["Race pace uses the MEDIAN clean lap (race-repeatable), not a flying lap."]
    if evidence.pit_loss_seconds <= 0:
        a.append("Pit-lane loss unknown — the event default was used.")
    if cand is not None:
        fmp = set(cand.fuel_map_plan)
        if "save" in fmp:
            a.append("Fuel-save map assumed to trade a little lap time for lower consumption.")
        if "push" in fmp:
            a.append("Push map assumed to raise fuel consumption without a pace gain modelled.")
    return a


def _why(best: StrategyScore, ranked: list[StrategyScore]) -> str:
    """Prose comparing the pick to the next-best DIFFERENT plan."""
    runner = next((s for s in ranked if s.candidate_id != best.candidate_id), None)
    if runner is None:
        return best.reasoning_summary
    gap = runner.estimated_total_time_seconds - best.estimated_total_time_seconds
    if gap >= 0:
        return (
            f"{plan_name(best.candidate_id)} is projected {gap:.1f}s faster over the "
            f"race than the {plan_name(runner.candidate_id).lower()} — "
            f"{best.reasoning_summary}"
        )
    # best was chosen despite being marginally slower (safety tie-break)
    return (
        f"{plan_name(best.candidate_id)} is within {abs(gap):.1f}s of the "
        f"{plan_name(runner.candidate_id).lower()} but is the safer plan, so it is "
        f"preferred — {best.reasoning_summary}"
    )


def _find_candidate(
    recommendation: StrategyRecommendation, candidate_id: str
) -> Optional[StrategyCandidate]:
    for c in recommendation.candidates:
        if c.candidate_id == candidate_id:
            return c
    return None
