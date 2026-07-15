"""Group 48 — Race Strategy Brain Phase 2: deterministic candidate generator.

WHY IT EXISTS
  Given a :class:`~strategy.race_strategy_evidence.RaceStrategyEvidence` snapshot,
  enumerate the *legal* strategy candidates for the event — no-stop, one-stop,
  two-stop, plus fuel-save / push / compound-switch variants — each with its
  structural plan and the deterministic fuel + pit-time maths that does NOT
  depend on pace.  Pace-based total race time is left to
  :mod:`strategy.race_strategy_scorer` so the two concerns stay separable.

WHAT THIS MODULE IS NOT
  • It invents no telemetry.  Fuel need is derived only from measured fuel use;
    when fuel data is absent a candidate is still enumerated but flagged and its
    fuel fields stay 0.0 (never guessed).
  • It touches no setup dict, the Apply gate, or any setup recommendation.
  • Pure: no PyQt6, no DB, no I/O, no AI, never raises.

LEGALITY
  A candidate is ILLEGAL (and excluded from any recommendation) when it violates
  a hard event rule: fewer stops than ``mandatory_pit_stops``, a stint that needs
  more than a full tank of fuel, or a compound plan that fails to include every
  ``required_compounds`` entry.  Illegal candidates are still RETURNED (so the UI
  can explain *why* they were rejected) but carry ``Legality.ILLEGAL``.

MODEL CONSTANTS (engineering assumptions, not invented telemetry)
  A chosen fuel MAP trades pace for consumption.  ``FUEL_SAVE_CONSUMPTION_FACTOR``
  and ``PUSH_CONSUMPTION_FACTOR`` scale *fuel need*; the matching per-lap time
  cost lives in the scorer.  These are documented model choices (mirroring the
  ``WET_PACE_PENALTY`` style constant in strategy/engine.py), surfaced to the
  driver as assumptions — never presented as measured car data.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from strategy.race_strategy_evidence import (
    GT7_TANK_CAPACITY_L,
    RaceStrategyEvidence,
    StrategyConfidence,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Legality(str, Enum):
    LEGAL = "LEGAL"
    ILLEGAL = "ILLEGAL"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


# Fuel map identifiers for a stint.
FUEL_MAP_NORMAL = "normal"
FUEL_MAP_SAVE = "save"
FUEL_MAP_PUSH = "push"

# Fuel-consumption scaling per fuel map (engineering model, documented above).
FUEL_SAVE_CONSUMPTION_FACTOR: float = 0.90   # lift-and-coast / lean map saves ~10 % fuel
PUSH_CONSUMPTION_FACTOR: float = 1.05        # rich map / attack burns ~5 % more

# Bound on the number of pit stops we bother to enumerate.
MAX_ENUMERATED_STOPS: int = 3


# ---------------------------------------------------------------------------
# Candidate model
# ---------------------------------------------------------------------------

@dataclass
class StrategyCandidate:
    """One legal-or-illegal race strategy candidate.

    ``estimated_total_race_time`` is populated by the scorer (it needs pace); the
    generator leaves it at 0.0.  All fuel / pit fields ARE computed here because
    they need no pace reference — only measured fuel use and the event pit loss.
    """

    candidate_id: str
    pit_count: int
    stints: list[dict]                       # [{compound, laps, fuel_map}, ...]
    compound_plan: list[str]
    fuel_map_plan: list[str]
    estimated_laps_per_stint: list[int]
    estimated_fuel_needed: float             # total litres over the race (0.0 == unknown)
    estimated_refuel_time: float             # total seconds (0.0 == unknown/not-refuelling)
    estimated_pit_time: float                # pit-lane loss + refuel (0.0 == no stops)
    estimated_total_race_time: float = 0.0   # filled by the scorer
    risk_level: RiskLevel = RiskLevel.MEDIUM
    confidence: StrategyConfidence = StrategyConfidence.INSUFFICIENT_EVIDENCE
    legality_status: Legality = Legality.LEGAL
    explanation: str = ""

    @property
    def is_legal(self) -> bool:
        return self.legality_status == Legality.LEGAL


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_candidates(evidence: RaceStrategyEvidence) -> list[StrategyCandidate]:
    """Enumerate strategy candidates for the given evidence, deterministically.

    Returns candidates in a stable order.  Legal AND illegal candidates are
    returned; callers must filter on ``is_legal`` for a recommendation.  Returns
    an empty list only when the race length cannot be established at all.
    """
    try:
        race_laps = _resolve_race_laps(evidence)
        if race_laps <= 0:
            return []

        fuel_per_lap = evidence.mean_fuel_per_lap()          # 0.0 when unknown
        fastest = _fastest_compound(evidence)
        second = _second_compound(evidence, fastest)

        candidates: list[StrategyCandidate] = []
        max_stops = min(max(race_laps - 1, 0), MAX_ENUMERATED_STOPS)

        # --- base stop-count candidates ---------------------------------
        for n in range(0, max_stops + 1):
            cand = _build_candidate(
                candidate_id=_base_id(n),
                pit_count=n,
                race_laps=race_laps,
                evidence=evidence,
                compound=fastest,
                fuel_per_lap=fuel_per_lap,
                fuel_map=FUEL_MAP_NORMAL,
                risk=_base_risk(n),
            )
            candidates.append(cand)

        # --- fuel-save one-stop (converts a would-be two-stop) ----------
        if max_stops >= 1:
            candidates.append(_build_candidate(
                candidate_id="1stop_fuelsave",
                pit_count=1,
                race_laps=race_laps,
                evidence=evidence,
                compound=fastest,
                fuel_per_lap=fuel_per_lap,
                fuel_map=FUEL_MAP_SAVE,
                risk=RiskLevel.MEDIUM,
            ))

        # --- push two-stop ---------------------------------------------
        if max_stops >= 2:
            candidates.append(_build_candidate(
                candidate_id="2stop_push",
                pit_count=2,
                race_laps=race_laps,
                evidence=evidence,
                compound=fastest,
                fuel_per_lap=fuel_per_lap,
                fuel_map=FUEL_MAP_PUSH,
                risk=RiskLevel.HIGH,
            ))

        # --- compound-switch one-stop (two distinct compounds) ----------
        if second is not None and max_stops >= 1:
            candidates.append(_build_candidate(
                candidate_id="1stop_compound_switch",
                pit_count=1,
                race_laps=race_laps,
                evidence=evidence,
                compound=fastest,
                fuel_per_lap=fuel_per_lap,
                fuel_map=FUEL_MAP_NORMAL,
                risk=RiskLevel.MEDIUM,
                compound_sequence=[fastest, second],
            ))

        return candidates
    except Exception:
        return []


def legal_candidates(candidates: list[StrategyCandidate]) -> list[StrategyCandidate]:
    """Filter to legal candidates only (recommendation input)."""
    return [c for c in candidates if c.is_legal]


# ---------------------------------------------------------------------------
# Candidate construction
# ---------------------------------------------------------------------------

def _build_candidate(
    *,
    candidate_id: str,
    pit_count: int,
    race_laps: int,
    evidence: RaceStrategyEvidence,
    compound: str,
    fuel_per_lap: float,
    fuel_map: str,
    risk: RiskLevel,
    compound_sequence: Optional[list[str]] = None,
) -> StrategyCandidate:
    """Assemble one candidate with its deterministic fuel + pit maths."""
    n_stints = pit_count + 1
    laps_per_stint = _distribute_laps(race_laps, n_stints)

    # Compound plan: an explicit sequence (compound-switch) or a single compound
    # repeated.  When an event mandates compounds, weave them across the stints.
    if compound_sequence is not None:
        compound_plan = _fit_sequence(compound_sequence, n_stints)
    else:
        compound_plan = _apply_required_compounds(
            [compound] * n_stints, list(evidence.required_compounds)
        )

    fuel_map_plan = [fuel_map] * n_stints
    consumption_factor = _consumption_factor(fuel_map)

    stints = [
        {"compound": compound_plan[i], "laps": laps_per_stint[i], "fuel_map": fuel_map}
        for i in range(n_stints)
    ]

    # --- fuel + refuel maths (only when fuel use is known) ---
    total_fuel = 0.0
    refuel_total = 0.0
    fuel_known = fuel_per_lap > 0.0
    refuel_known = evidence.refuel_rate_lps > 0.0
    fuel_infeasible = False

    if fuel_known:
        for i, laps in enumerate(laps_per_stint):
            stint_fuel = fuel_per_lap * laps * consumption_factor
            total_fuel += stint_fuel
            if stint_fuel > GT7_TANK_CAPACITY_L + 1e-6:
                fuel_infeasible = True
            # Refuel happens for every stint after the first (i.e. at each stop).
            if i > 0 and refuel_known:
                refuel_total += math.ceil(
                    min(stint_fuel, GT7_TANK_CAPACITY_L) / evidence.refuel_rate_lps
                )

    pit_loss = evidence.pit_loss_seconds if evidence.pit_loss_seconds > 0 else 0.0
    pit_time = pit_count * pit_loss + refuel_total

    # --- legality ---
    legality, reason = _legality(
        pit_count=pit_count,
        compound_plan=compound_plan,
        evidence=evidence,
        fuel_infeasible=fuel_infeasible,
        fuel_known=fuel_known,
    )

    # --- confidence: evidence quality, dropped when this plan leans on gaps ---
    confidence = evidence.evidence_confidence
    if fuel_map == FUEL_MAP_SAVE and not evidence.has_long_run_data():
        confidence = StrategyConfidence.worst(confidence, StrategyConfidence.LOW)

    explanation = _candidate_explanation(
        candidate_id, pit_count, laps_per_stint, compound_plan, fuel_map,
        legality, reason, fuel_known, refuel_known,
    )

    return StrategyCandidate(
        candidate_id=candidate_id,
        pit_count=pit_count,
        stints=stints,
        compound_plan=compound_plan,
        fuel_map_plan=fuel_map_plan,
        estimated_laps_per_stint=laps_per_stint,
        estimated_fuel_needed=round(total_fuel, 2) if fuel_known else 0.0,
        estimated_refuel_time=refuel_total,
        estimated_pit_time=pit_time,
        estimated_total_race_time=0.0,
        risk_level=risk,
        confidence=confidence,
        legality_status=legality,
        explanation=explanation,
    )


# ---------------------------------------------------------------------------
# Legality
# ---------------------------------------------------------------------------

def _legality(
    *,
    pit_count: int,
    compound_plan: list[str],
    evidence: RaceStrategyEvidence,
    fuel_infeasible: bool,
    fuel_known: bool,
) -> tuple[Legality, str]:
    """Return (Legality, human reason).  Any single violation → ILLEGAL."""
    # Mandatory pit stops.
    if pit_count < evidence.mandatory_pit_stops:
        return (
            Legality.ILLEGAL,
            f"race rules require at least {evidence.mandatory_pit_stops} pit stop(s); "
            f"this plan makes {pit_count}",
        )

    # Fuel feasibility (only enforceable when fuel use is known).
    if fuel_known and fuel_infeasible:
        return (
            Legality.ILLEGAL,
            "a stint needs more than a full 100 L tank of fuel — more stops required",
        )

    # Required compounds must all appear.
    required = [c for c in evidence.required_compounds if c]
    if required:
        used = set(compound_plan)
        missing = [c for c in required if c not in used]
        if missing:
            return (
                Legality.ILLEGAL,
                f"event mandates compound(s) {', '.join(missing)} that this plan never fits",
            )

    return (Legality.LEGAL, "")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_race_laps(evidence: RaceStrategyEvidence) -> int:
    """Race laps: authoritative for lap races, estimated for timed races.

    Timed estimate uses the representative (median) race-pace lap, matching the
    Group 48 race-result focus rather than a flying-lap estimate.  Returns 0 when
    no length can be established.
    """
    if evidence.race_laps > 0:
        return int(evidence.race_laps)
    if evidence.race_duration_minutes > 0:
        rep = evidence.representative_lap_s()
        if rep > 0:
            return math.ceil((evidence.race_duration_minutes * 60.0) / rep)
    return 0


def _distribute_laps(race_laps: int, n_stints: int) -> list[int]:
    """Split race_laps across n_stints as evenly as possible (earlier stints +1)."""
    n_stints = max(1, n_stints)
    base = race_laps // n_stints
    rem = race_laps % n_stints
    return [base + (1 if i < rem else 0) for i in range(n_stints)]


def _consumption_factor(fuel_map: str) -> float:
    if fuel_map == FUEL_MAP_SAVE:
        return FUEL_SAVE_CONSUMPTION_FACTOR
    if fuel_map == FUEL_MAP_PUSH:
        return PUSH_CONSUMPTION_FACTOR
    return 1.0


def _fastest_compound(evidence: RaceStrategyEvidence) -> str:
    """Pick the fastest available compound by measured median pace.

    Falls back to the first available compound (or "unknown") when there is no
    per-compound pace data — never invents a pace.
    """
    avail = list(evidence.available_compounds)
    if evidence.compound_samples:
        paced = [(c, evidence.compound_pace_s(c)) for c in (avail or evidence.compound_samples.keys())]
        paced = [(c, p) for c, p in paced if p > 0]
        if paced:
            return min(paced, key=lambda cp: cp[1])[0]
    if avail:
        return avail[0]
    return "unknown"


def _second_compound(evidence: RaceStrategyEvidence, fastest: str) -> Optional[str]:
    """A distinct, MEASURED second compound for a compound-switch plan, or None.

    Untested compounds (no measured pace) must never enter a recommended
    strategy — they may only appear as unvalidated alternatives. So a
    compound-switch candidate is built only from a compound that has real pace
    data; when none exists, return None and no switch candidate is generated.
    """
    tested = [c for c in evidence.available_compounds
              if c != fastest and evidence.compound_pace_s(c) > 0]
    if tested:
        return min(tested, key=lambda c: evidence.compound_pace_s(c))
    return None


def _fit_sequence(sequence: list[str], n_stints: int) -> list[str]:
    """Fit a compound sequence to n stints, cycling if shorter, truncating if longer."""
    if not sequence:
        return ["unknown"] * n_stints
    return [sequence[i % len(sequence)] for i in range(n_stints)]


def _apply_required_compounds(plan: list[str], required: list[str]) -> list[str]:
    """Weave mandatory compounds into a single-compound plan where stints allow.

    Assigns each still-unsatisfied required compound to the latest stints so the
    fastest compound runs first.  If there are fewer stints than distinct
    required compounds the plan simply cannot satisfy them — legality catches it.
    """
    required = [c for c in required if c]
    if not required:
        return list(plan)
    plan = list(plan)
    missing = [c for c in required if c not in set(plan)]
    # Fill from the last stint backwards.
    idx = len(plan) - 1
    for comp in missing:
        if idx < 0:
            break
        plan[idx] = comp
        idx -= 1
    return plan


def _base_id(n: int) -> str:
    return {0: "nostop", 1: "1stop", 2: "2stop", 3: "3stop"}.get(n, f"{n}stop")


def _base_risk(n: int) -> RiskLevel:
    # A no-stop leans hardest on fuel + tyre life → higher risk.
    if n == 0:
        return RiskLevel.HIGH
    if n == 1:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def _candidate_explanation(
    candidate_id: str,
    pit_count: int,
    laps_per_stint: list[int],
    compound_plan: list[str],
    fuel_map: str,
    legality: Legality,
    reason: str,
    fuel_known: bool,
    refuel_known: bool,
) -> str:
    stint_desc = ", ".join(
        f"{laps_per_stint[i]} laps on {compound_plan[i]}" for i in range(len(laps_per_stint))
    )
    parts = [f"{pit_count}-stop plan: {stint_desc}."]
    if fuel_map == FUEL_MAP_SAVE:
        parts.append("Runs a fuel-saving map to stretch the stints (costs a little lap time).")
    elif fuel_map == FUEL_MAP_PUSH:
        parts.append("Runs an attacking fuel map (higher consumption, higher risk).")
    if not fuel_known:
        parts.append("Fuel use is unknown, so fuel and refuel time could not be calculated.")
    elif pit_count > 0 and not refuel_known:
        parts.append("Refuel rate is unknown, so refuel time is not included.")
    if legality == Legality.ILLEGAL:
        parts.append(f"ILLEGAL — {reason}.")
    return " ".join(parts)
