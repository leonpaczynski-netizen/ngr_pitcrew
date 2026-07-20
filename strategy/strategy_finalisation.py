"""Strategy finalisation & deadline-aware risk (Program 2, Phase 49).

An explicit, user-controlled strategy meeting: it presents the primary and alternative plans built from
the accumulated Practice evidence, states the assumptions and what evidence is still missing, and is
FINALISED only on explicit driver confirmation. Finalisation cannot occur without the required evidence
UNLESS the driver explicitly accepts a low-confidence plan (which stays visibly labelled). Strategy is
never auto-finalised and no pit/tyre/fuel command is issued.

Deadline-aware risk: as the official race approaches the system becomes more conservative. When little
preparation time remains it prefers protecting the current best-known setup and low-risk confirmation,
and it does not begin a risky coupled setup experiment shortly before the race unless the driver
explicitly overrides with a visible warning.

Purity: Qt-free, DB-free, offline, deterministic, no wall-clock, never raises. The risk posture is
advisory runtime output (it may consult the injected countdown); it is not part of the cycle identity
fingerprint.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Sequence, Tuple

from strategy.strategy_maturity import StrategyMaturity

STRATEGY_FINALISATION_VERSION = "strategy_finalisation_v1"
STRATEGY_FINALISATION_SCHEMA = 1


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{STRATEGY_FINALISATION_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


@dataclass(frozen=True)
class StrategyPlan:
    """One presented plan (primary or alternative). Values are labels/estimates, never fabricated."""
    label: str
    total_race_time_estimate: str = ""
    fuel_required: str = ""
    tyre_life: str = ""
    stint_lengths: Tuple[str, ...] = field(default_factory=tuple)
    pit_windows: Tuple[str, ...] = field(default_factory=tuple)
    refuelling_time: str = ""
    pit_loss: str = ""
    confidence: str = ""
    assumptions: Tuple[str, ...] = field(default_factory=tuple)
    trigger_conditions: Tuple[str, ...] = field(default_factory=tuple)
    weather_contingency: str = ""

    def as_payload(self) -> dict:
        return {"label": _norm(self.label), "total_race_time_estimate": _norm(self.total_race_time_estimate),
                "fuel_required": _norm(self.fuel_required), "tyre_life": _norm(self.tyre_life),
                "stint_lengths": [_norm(s) for s in self.stint_lengths],
                "pit_windows": [_norm(s) for s in self.pit_windows],
                "refuelling_time": _norm(self.refuelling_time), "pit_loss": _norm(self.pit_loss),
                "confidence": _norm(self.confidence),
                "assumptions": sorted(_norm(s) for s in self.assumptions if _norm(s)),
                "trigger_conditions": sorted(_norm(s) for s in self.trigger_conditions if _norm(s)),
                "weather_contingency": _norm(self.weather_contingency)}


@dataclass(frozen=True)
class StrategyFinalisationDecision:
    finalised: bool
    primary: Optional[StrategyPlan]
    alternative: Optional[StrategyPlan]
    race_setup_dependency: str
    evidence_still_missing: Tuple[str, ...]
    low_confidence_accepted: bool
    reason: str
    fingerprint: str = ""

    def as_payload(self) -> dict:
        return {"finalised": bool(self.finalised),
                "primary": self.primary.as_payload() if self.primary else None,
                "alternative": self.alternative.as_payload() if self.alternative else None,
                "race_setup_dependency": _norm(self.race_setup_dependency),
                "evidence_still_missing": list(self.evidence_still_missing),
                "low_confidence_accepted": bool(self.low_confidence_accepted),
                "reason": _norm(self.reason)}


def build_strategy_finalisation(
    maturity: StrategyMaturity,
    *,
    confirmed: bool,
    primary: Optional[StrategyPlan] = None,
    alternative: Optional[StrategyPlan] = None,
    race_setup_dependency: str = "",
    evidence_still_missing: Sequence[str] = (),
    low_confidence_accepted: bool = False,
) -> StrategyFinalisationDecision:
    """Finalise ONLY on explicit confirmation. If the strategy is not FINALISATION_READY, finalisation
    requires the driver to explicitly accept a low-confidence plan; otherwise it stays un-finalised and
    states the missing evidence. Never auto-finalises."""
    ready = maturity == StrategyMaturity.FINALISATION_READY
    missing = tuple(_norm(m) for m in evidence_still_missing if _norm(m))

    if not confirmed:
        finalised = False
        reason = "explicit strategy acknowledgement required to finalise"
    elif ready:
        finalised = True
        reason = "finalised by explicit driver decision (evidence sufficient)"
    elif low_confidence_accepted:
        finalised = True
        reason = "finalised on explicit low-confidence acceptance; assumptions remain visible"
    else:
        finalised = False
        reason = (f"cannot finalise from maturity '{maturity.value}' without required evidence "
                  "or explicit low-confidence acceptance")

    dec = StrategyFinalisationDecision(
        finalised=finalised, primary=primary, alternative=alternative,
        race_setup_dependency=_norm(race_setup_dependency), evidence_still_missing=missing,
        low_confidence_accepted=bool(low_confidence_accepted), reason=reason, fingerprint="")
    return StrategyFinalisationDecision(
        finalised=dec.finalised, primary=dec.primary, alternative=dec.alternative,
        race_setup_dependency=dec.race_setup_dependency, evidence_still_missing=dec.evidence_still_missing,
        low_confidence_accepted=dec.low_confidence_accepted, reason=dec.reason, fingerprint=_fp(dec.as_payload()))


# ---------------------------------------------------------------------------
# Deadline-aware risk
# ---------------------------------------------------------------------------

class RiskPosture(str, Enum):
    EXPLORATORY_OK = "exploratory_ok"
    PREFER_CONFIRMATION = "prefer_confirmation"
    PROTECT_BEST_KNOWN = "protect_best_known"
    BLOCK_UNLESS_OVERRIDDEN = "block_unless_overridden"


# days-until-race thresholds; conservative as the race approaches
_NEAR_RACE_DAYS = 3
_RACE_WEEK_DAYS = 7


@dataclass(frozen=True)
class DeadlineRiskAssessment:
    posture: RiskPosture
    warning: str
    allow_experiment: bool


def assess_deadline_risk(
    days_until_race: Optional[int],
    *,
    high_interaction_experiment: bool,
    reversible: bool = True,
    explicitly_overridden: bool = False,
) -> DeadlineRiskAssessment:
    """Deterministic deadline-aware risk posture. A high-interaction (coupled) setup experiment close to
    the race is blocked unless the driver explicitly overrides with a visible warning; otherwise the
    system prefers protecting the best-known setup and low-risk confirmation. ``days_until_race`` is the
    injected countdown (display-derived); this output is advisory, never persisted cycle identity."""
    near = days_until_race is not None and days_until_race <= _NEAR_RACE_DAYS
    race_week = days_until_race is not None and days_until_race <= _RACE_WEEK_DAYS

    if high_interaction_experiment and near:
        if explicitly_overridden:
            return DeadlineRiskAssessment(
                RiskPosture.PROTECT_BEST_KNOWN,
                "High-interaction experiment run close to the race by explicit override — proceed with "
                "caution; protect the rollback setup.", allow_experiment=True)
        return DeadlineRiskAssessment(
            RiskPosture.BLOCK_UNLESS_OVERRIDDEN,
            "A high-interaction coupled experiment is risky this close to the race. Protect the current "
            "best-known setup; override explicitly if you accept the risk.", allow_experiment=False)

    if near:
        return DeadlineRiskAssessment(
            RiskPosture.PROTECT_BEST_KNOWN,
            "Little time remains — prefer confirmation, blocker resolution and consistency over new "
            "experiments.", allow_experiment=not high_interaction_experiment)

    if race_week:
        return DeadlineRiskAssessment(
            RiskPosture.PREFER_CONFIRMATION,
            "Race week — favour low-risk confirmation and strategy validation.",
            allow_experiment=not high_interaction_experiment or explicitly_overridden)

    return DeadlineRiskAssessment(RiskPosture.EXPLORATORY_OK, "", allow_experiment=True)
