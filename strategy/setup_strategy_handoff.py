"""Setup → Strategy handoff (pure, Qt-free) — Engineering-Brain Phase 6.

The boundary the plan insists on:
  * The Setup Brain ENGINEERS THE CAR for the discipline. For a race setup it targets
    tyre preservation, traction stability, fuel/drag efficiency and consistency.
  * The Strategy Brain WINS THE RACE. It owns tyre-degradation curves, the crossover
    lap, fuel-per-lap, refuel time, pit loss, legal candidates and total-race-time
    ranking — from MEASURED practice data.

This module is the clean handoff between them: it packages the race setup's
strategy-relevant CHARACTERISTICS (as evidence, derived from the target handling model
and the synthesized setup) for the Strategy Brain to consume — and it explicitly authors
NO strategy: no pit call, no compound choice, no stint plan, no total-race-time number.
It never crosses into strategy authority.
"""
from __future__ import annotations

from dataclasses import dataclass, field as _dc_field
from typing import Optional


# The strategy-relevant characteristics a race setup can be described by (evidence only).
@dataclass(frozen=True)
class SetupStrategyHandoff:
    objective: str
    # Setup characteristics (each -1..+1: higher = the setup favours this).
    tyre_preservation: float
    traction_stability: float
    fuel_drag_efficiency: float
    consistency: float
    # Human-readable notes the Strategy Brain can show alongside its own analysis.
    strengths: list
    weaknesses: list
    # The evidence the Strategy Brain still needs to MEASURE (setup cannot supply it).
    strategy_owns: tuple
    # Hard boundary marker — this object authors no strategy.
    authority: str = "setup_provides_evidence_only"

    def as_json(self) -> dict:
        return {
            "objective": self.objective,
            "characteristics": {
                "tyre_preservation": round(self.tyre_preservation, 2),
                "traction_stability": round(self.traction_stability, 2),
                "fuel_drag_efficiency": round(self.fuel_drag_efficiency, 2),
                "consistency": round(self.consistency, 2),
            },
            "strengths": list(self.strengths),
            "weaknesses": list(self.weaknesses),
            "strategy_owns": list(self.strategy_owns),
            "authority": self.authority,
        }


# What the Strategy Brain owns and the Setup Brain must NOT author (boundary guard).
STRATEGY_OWNED = (
    "tyre degradation curve",
    "tyre crossover lap (when fresh beats worn)",
    "fuel use per lap + fuel-saving cost",
    "refuel time + pit loss",
    "legal strategy candidates",
    "compound selection + pit-stop timing",
    "total-race-time ranking",
)

# Setup keys that would indicate strategy authority leaking in — must never appear.
_FORBIDDEN_STRATEGY_KEYS = frozenset({
    "pit_lap", "pit_window", "compound", "stint", "stops", "fuel_map",
    "total_race_time", "crossover_lap", "strategy",
})


def _num(v) -> float:
    try:
        f = float(v)
        return f if f == f and f not in (float("inf"), float("-inf")) else 0.0
    except (TypeError, ValueError):
        return 0.0


def build_setup_strategy_handoff(context, synthesis=None) -> Optional[SetupStrategyHandoff]:
    """Package the setup's strategy-relevant characteristics as EVIDENCE for the Strategy
    Brain. Only meaningful for a race setup (base/quali return None). Derives the
    characteristics from the target handling model (and the synthesized setup when given).
    Authors no strategy."""
    obj = str(getattr(context, "objective", "base")).lower()
    if obj != "race":
        return None

    # Build the target model to read the race-relevant handling targets.
    try:
        from strategy.setup_synthesis import build_target_handling_model
        target = build_target_handling_model(context)
        t = target.targets
    except Exception:
        t = {}

    tyre = _num(t.get("tyre_preservation"))
    traction = 0.5 * (_num(t.get("exit_traction")) + _num(t.get("power_oversteer_resistance")))
    fuel = _num(t.get("fuel_efficiency"))
    consistency = _num(t.get("consistency"))

    strengths: list = []
    weaknesses: list = []
    if tyre >= 0.3:
        strengths.append("engineered to protect the tyre over a stint (supports longer stints)")
    elif tyre <= -0.1:
        weaknesses.append("aggressive trim — expect higher tyre wear (favours shorter stints)")
    if traction >= 0.3:
        strengths.append("stable traction on power (reduces wheelspin loss and lap-time variance)")
    if fuel >= 0.2:
        strengths.append("lower drag / fuel burn (helps a fuel-saving strategy)")
    elif fuel <= -0.1:
        weaknesses.append("higher downforce/drag — more fuel burn (weigh vs a fuel-save plan)")
    if consistency >= 0.3:
        strengths.append("low lap-time variance (predictable stint pace for the plan)")

    return SetupStrategyHandoff(
        objective=obj, tyre_preservation=tyre, traction_stability=traction,
        fuel_drag_efficiency=fuel, consistency=consistency,
        strengths=strengths, weaknesses=weaknesses, strategy_owns=STRATEGY_OWNED,
    )


def handoff_respects_boundary(handoff_json: dict) -> bool:
    """True if the handoff surface authors NO strategy (no forbidden strategy keys, and
    the authority marker is intact). A guard the tests + callers can assert."""
    if not isinstance(handoff_json, dict):
        return True
    if handoff_json.get("authority") != "setup_provides_evidence_only":
        return False
    keys = set(handoff_json.keys()) | set(handoff_json.get("characteristics", {}).keys())
    return not (keys & _FORBIDDEN_STRATEGY_KEYS)
