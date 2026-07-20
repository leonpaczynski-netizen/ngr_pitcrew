"""Engineering Cost of Knowledge (Program 2, Phase 19).

A deterministic, ADVISORY-ONLY estimator of the engineering EFFORT a controlled experiment
costs and the value it returns per unit of that effort. The engineering VALUE is reused
verbatim from Phase 17 (``ExperimentValuation.engineering_value``) — this module NEVER
re-ranks or recomputes value; it only divides the existing value by visible cost estimates.

It also provides a deterministic ``EngineeringBudget`` planner: given a session budget (time,
tyres, fuel), it advises which of a campaign's still-testable experiments fit — in the
existing Phase-17 rank order, a greedy deterministic fit, NOT an optimiser or scheduler.

All cost constants are VISIBLE (exposed on every estimate). Purity: Qt-free, DB-free,
UI-free, network-free, AI-free; no random, no wall-clock; deterministic; never raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Mapping, Optional, Sequence, Tuple

ENGINEERING_COST_VERSION = "engineering_cost_v1"

# VISIBLE cost estimation constants (exposed on every estimate; no hidden numbers).
MIN_CLEAN_LAPS = 4            # bounded-experiment default clean-lap requirement (Phase 15)
WARMUP_LAPS = 1              # one out/warm-up lap excluded from measurement
AB_A_REVERT_LAPS = 4        # A/B/A: a revert-check window equal to the clean-lap requirement
TYRE_LAPS_PER_SET = 12      # conservative practice-run laps per tyre set (estimate)
MINUTES_PER_LAP_DEFAULT = 2.0   # generic lap-time estimate (override via lap_time_seconds)
FUEL_LAPS_PER_LAP = 1.0     # one lap of fuel consumed per lap driven (estimate)
DISCRIMINATOR_CONFIDENCE = 1.0  # a discriminating test returns its full engineering value
OTHER_CONFIDENCE = 0.6      # a validation / secondary test returns a reduced share

COST_CONSTANTS = {
    "min_clean_laps": MIN_CLEAN_LAPS, "warmup_laps": WARMUP_LAPS,
    "ab_a_revert_laps": AB_A_REVERT_LAPS, "tyre_laps_per_set": TYRE_LAPS_PER_SET,
    "minutes_per_lap_default": MINUTES_PER_LAP_DEFAULT,
    "fuel_laps_per_lap": FUEL_LAPS_PER_LAP,
    "discriminator_confidence_share": DISCRIMINATOR_CONFIDENCE,
    "other_confidence_share": OTHER_CONFIDENCE,
}


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


def _round(v, n=3) -> float:
    try:
        return round(float(v), n)
    except (TypeError, ValueError):
        return 0.0


@dataclass(frozen=True)
class ExperimentCostEstimate:
    candidate_id: str
    field: str
    laps: int
    warmup_laps: int
    baseline_laps: int
    test_laps: int
    revert_laps: int
    time_minutes: float
    fuel_laps: float
    tyre_sets: float
    engineering_value: float            # reused from Phase 17 — never recomputed
    estimated_confidence_gain: float
    value_per_lap: float
    value_per_minute: float
    info_gain_per_tyre_set: float
    ab_structure: str
    testable: bool
    cost_constants: dict
    rationale: str

    def to_dict(self) -> dict:
        return {"candidate_id": self.candidate_id, "field": self.field, "laps": self.laps,
                "warmup_laps": self.warmup_laps, "baseline_laps": self.baseline_laps,
                "test_laps": self.test_laps, "revert_laps": self.revert_laps,
                "time_minutes": self.time_minutes, "fuel_laps": self.fuel_laps,
                "tyre_sets": self.tyre_sets, "engineering_value": self.engineering_value,
                "estimated_confidence_gain": self.estimated_confidence_gain,
                "value_per_lap": self.value_per_lap, "value_per_minute": self.value_per_minute,
                "info_gain_per_tyre_set": self.info_gain_per_tyre_set,
                "ab_structure": self.ab_structure, "testable": self.testable,
                "cost_constants": dict(self.cost_constants), "rationale": self.rationale}


def estimate_experiment_cost(experiment: Mapping, *,
                             minutes_per_lap: Optional[float] = None) -> ExperimentCostEstimate:
    """Estimate the effort of ONE Phase-18 campaign experiment. The engineering value comes
    from Phase 17 (never recomputed). Deterministic; never raises."""
    experiment = experiment if isinstance(experiment, Mapping) else {}
    role = _lc(experiment.get("campaign_role"))
    coupled = _lc(experiment.get("attribution_scope")) == "coupled_pair"
    # A/B/A: warm-up + baseline window + test window + revert-check window.
    warmup = WARMUP_LAPS
    baseline = MIN_CLEAN_LAPS
    test = MIN_CLEAN_LAPS + (MIN_CLEAN_LAPS if coupled else 0)
    revert = AB_A_REVERT_LAPS
    laps = warmup + baseline + test + revert
    mpl = float(minutes_per_lap) if minutes_per_lap else MINUTES_PER_LAP_DEFAULT
    time_minutes = _round(laps * mpl, 2)
    fuel_laps = _round(laps * FUEL_LAPS_PER_LAP, 2)
    tyre_sets = _round(laps / TYRE_LAPS_PER_SET, 3)
    value = _round(experiment.get("engineering_value") or 0.0, 6)
    share = DISCRIMINATOR_CONFIDENCE if role == "primary_discriminator" else OTHER_CONFIDENCE
    confidence_gain = _round(value * share, 6)
    testable = role != "retired" and _lc(experiment.get("outcome_state")) == "not_tested"
    return ExperimentCostEstimate(
        candidate_id=str(experiment.get("candidate_id") or ""),
        field=_lc(experiment.get("field")), laps=laps, warmup_laps=warmup,
        baseline_laps=baseline, test_laps=test, revert_laps=revert, time_minutes=time_minutes,
        fuel_laps=fuel_laps, tyre_sets=tyre_sets, engineering_value=value,
        estimated_confidence_gain=confidence_gain,
        value_per_lap=_round(value / laps, 6) if laps else 0.0,
        value_per_minute=_round(value / time_minutes, 6) if time_minutes else 0.0,
        info_gain_per_tyre_set=_round(value / tyre_sets, 6) if tyre_sets else 0.0,
        ab_structure="A/B/A", testable=testable, cost_constants=dict(COST_CONSTANTS),
        rationale=(f"laps = warmup({warmup}) + baseline({baseline}) + test({test}) + "
                   f"revert({revert}); value from Phase-17 rank (not recomputed)"))


@dataclass(frozen=True)
class EngineeringBudget:
    session_time_minutes: Optional[float]
    tyre_sets_available: Optional[float]
    fuel_laps_available: Optional[float]
    estimated_laps_remaining: int
    recommended: Tuple[dict, ...]        # experiments that fit, in Phase-17 rank order
    deferred: Tuple[dict, ...]           # experiments that do not fit this budget
    used_minutes: float
    used_tyre_sets: float
    used_laps: int
    time_utilisation: Optional[float]
    tyre_utilisation: Optional[float]
    estimated_confidence_increase: float
    budget_known: bool
    rationale: str
    eval_version: str = ENGINEERING_COST_VERSION

    def to_dict(self) -> dict:
        return {"session_time_minutes": self.session_time_minutes,
                "tyre_sets_available": self.tyre_sets_available,
                "fuel_laps_available": self.fuel_laps_available,
                "estimated_laps_remaining": self.estimated_laps_remaining,
                "recommended": [dict(r) for r in self.recommended],
                "deferred": [dict(d) for d in self.deferred],
                "used_minutes": self.used_minutes, "used_tyre_sets": self.used_tyre_sets,
                "used_laps": self.used_laps, "time_utilisation": self.time_utilisation,
                "tyre_utilisation": self.tyre_utilisation,
                "estimated_confidence_increase": self.estimated_confidence_increase,
                "budget_known": self.budget_known, "rationale": self.rationale,
                "eval_version": self.eval_version}


def plan_budget(estimates: Sequence[ExperimentCostEstimate], *,
                session_budget: Optional[Mapping] = None) -> EngineeringBudget:
    """Deterministic greedy budget fit over still-testable experiments, in the EXISTING
    Phase-17 rank order (``estimates`` must already be rank-ordered). NOT an optimiser or
    scheduler — it advises which experiments fit; it selects/mutates/executes nothing."""
    sb = session_budget or {}
    minutes = _num(sb.get("session_minutes_remaining"))
    tyres = _num(sb.get("tyre_sets_available"))
    fuel_laps = _num(sb.get("fuel_laps_available"))
    mpl = _num(sb.get("lap_time_seconds"))
    mpl = (mpl / 60.0) if mpl else None

    testable = [e for e in estimates if e.testable]
    known = minutes is not None or tyres is not None
    used_min = used_tyre = 0.0
    used_laps = 0
    conf = 0.0
    recommended: List[dict] = []
    deferred: List[dict] = []
    for e in testable:
        e_minutes = (e.laps * mpl) if mpl else e.time_minutes
        fits = True
        if minutes is not None and used_min + e_minutes > minutes + 1e-9:
            fits = False
        if tyres is not None and used_tyre + e.tyre_sets > tyres + 1e-9:
            fits = False
        if fuel_laps is not None and (used_laps + e.laps) > fuel_laps + 1e-9:
            fits = False
        if fits and known:
            used_min += e_minutes
            used_tyre += e.tyre_sets
            used_laps += e.laps
            conf += e.estimated_confidence_gain
            recommended.append(e.to_dict())
        else:
            deferred.append(e.to_dict())

    est_laps_remaining = int(round(minutes / mpl)) if (minutes is not None and mpl) else (
        int(round(minutes / MINUTES_PER_LAP_DEFAULT)) if minutes is not None else
        int(round(fuel_laps)) if fuel_laps is not None else 0)
    rationale = ("greedy fit in Phase-17 rank order (no optimisation, no scheduling)"
                 if known else "session budget unknown - no budget fit; all experiments "
                 "deferred until session context is supplied")
    return EngineeringBudget(
        session_time_minutes=minutes, tyre_sets_available=tyres,
        fuel_laps_available=fuel_laps, estimated_laps_remaining=est_laps_remaining,
        recommended=tuple(recommended), deferred=tuple(deferred),
        used_minutes=_round(used_min, 2), used_tyre_sets=_round(used_tyre, 3),
        used_laps=used_laps,
        time_utilisation=(_round(used_min / minutes, 3) if minutes else None),
        tyre_utilisation=(_round(used_tyre / tyres, 3) if tyres else None),
        estimated_confidence_increase=_round(conf, 6), budget_known=known,
        rationale=rationale)


def _num(v):
    try:
        if v is None or (isinstance(v, str) and not v.strip()) or isinstance(v, bool):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def cost_versions() -> dict:
    return {"engineering_cost": ENGINEERING_COST_VERSION}
