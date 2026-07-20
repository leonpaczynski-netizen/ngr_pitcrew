"""Tyre, fuel and strategy maturation (Program 2, Phase 49).

Every valid Practice session that produces relevant evidence advances the Race strategy model. This
module rolls the cumulative evidence (tyre model, fuel model, race pace, consistency) plus strategy-
specific readiness flags into deterministic maturity states, and always exposes what evidence is still
missing. It never fabricates certainty: an unknown multiplier or a missing long-run keeps the model
below FINALISATION_READY.

Purity: Qt-free, DB-free, offline, deterministic, no wall-clock, never raises. Authors no pit call and
issues no tyre/fuel command.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Sequence, Tuple

from strategy.preparation_evidence import (
    CumulativePreparationEvidence, EvidenceDomain, ConfidenceLevel, _CONFIDENCE_ORDER,
)

STRATEGY_MATURITY_VERSION = "strategy_maturity_v1"
STRATEGY_MATURITY_SCHEMA = 1


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{STRATEGY_MATURITY_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


class StrategyMaturity(str, Enum):
    NO_EVIDENCE = "no_evidence"
    EARLY_MODEL = "early_model"
    PARTIAL = "partial"
    DEVELOPING = "developing"
    VALIDATION_REQUIRED = "validation_required"
    PROVISIONAL = "provisional"
    FINALISATION_READY = "finalisation_ready"
    FINALISED = "finalised"
    REPLAN_REQUIRED = "replan_required"


class ModelMaturity(str, Enum):
    NONE = "none"
    IMMATURE = "immature"
    DEVELOPING = "developing"
    MATURE = "mature"
    CAPPED = "capped"       # evidence exists but a material unknown caps trust


@dataclass(frozen=True)
class StrategyEvidenceReadiness:
    """Strategy-specific readiness flags, in addition to the cumulative evidence domains."""
    has_representative_race_pace: bool = False
    has_lap_consistency: bool = False
    has_fuel_use: bool = False
    has_tyre_degradation: bool = False
    has_compound_pace: bool = False
    has_pit_loss: bool = False
    refuel_rate_known: bool = False
    race_duration_known: bool = False
    multipliers_known: bool = False
    validated_long_run: bool = False      # a long-run + fuel evidence set that has been validated
    dependency_changed: bool = False      # event revision / race setup reopened since last model
    is_finalised: bool = False

    def as_payload(self) -> dict:
        return {k: bool(getattr(self, k)) for k in (
            "has_representative_race_pace", "has_lap_consistency", "has_fuel_use",
            "has_tyre_degradation", "has_compound_pace", "has_pit_loss", "refuel_rate_known",
            "race_duration_known", "multipliers_known", "validated_long_run", "dependency_changed",
            "is_finalised")}


@dataclass(frozen=True)
class TyreFuelMaturity:
    tyre: ModelMaturity
    fuel: ModelMaturity
    tyre_note: str
    fuel_note: str

    def as_payload(self) -> dict:
        return {"tyre": self.tyre.value, "fuel": self.fuel.value,
                "tyre_note": _norm(self.tyre_note), "fuel_note": _norm(self.fuel_note)}


@dataclass(frozen=True)
class StrategyMaturitySummary:
    maturity: StrategyMaturity
    tyre_fuel: TyreFuelMaturity
    missing_evidence: Tuple[str, ...]
    fingerprint: str = ""

    def as_payload(self) -> dict:
        return {"maturity": self.maturity.value, "tyre_fuel": self.tyre_fuel.as_payload(),
                "missing_evidence": list(self.missing_evidence)}


def _model_maturity(evidence: CumulativePreparationEvidence, domain: EvidenceDomain) -> Tuple[ModelMaturity, str]:
    de = evidence.domain(domain)
    if de is None:
        return ModelMaturity.NONE, "no evidence collected"
    if de.capped:
        return ModelMaturity.CAPPED, "evidence present but a material condition is unknown/partial (capped)"
    rank = _CONFIDENCE_ORDER.index(de.confidence)
    if rank >= _CONFIDENCE_ORDER.index(ConfidenceLevel.MODERATE):
        return ModelMaturity.MATURE, f"{de.exact_samples} exact sample(s)"
    if rank >= _CONFIDENCE_ORDER.index(ConfidenceLevel.DEVELOPING):
        return ModelMaturity.DEVELOPING, f"{de.exact_samples} exact sample(s)"
    return ModelMaturity.IMMATURE, f"{de.exact_samples} exact sample(s)"


def assess_strategy_maturity(readiness: StrategyEvidenceReadiness) -> StrategyMaturity:
    """Deterministic strategy maturity ladder. FINALISATION_READY requires a validated long-run + fuel
    evidence set with the race duration and multipliers known; a changed dependency forces REPLAN."""
    S = StrategyMaturity
    if readiness.is_finalised and not readiness.dependency_changed:
        return S.FINALISED
    if readiness.dependency_changed:
        return S.REPLAN_REQUIRED
    have = sum([readiness.has_representative_race_pace, readiness.has_lap_consistency,
                readiness.has_fuel_use, readiness.has_tyre_degradation, readiness.has_compound_pace,
                readiness.has_pit_loss])
    if have == 0:
        return S.NO_EVIDENCE
    if not readiness.has_representative_race_pace:
        return S.EARLY_MODEL
    if not (readiness.has_lap_consistency and (readiness.has_fuel_use or readiness.has_tyre_degradation)):
        return S.PARTIAL
    # pace + consistency + (fuel or tyre) present
    if not (readiness.has_fuel_use and readiness.has_tyre_degradation):
        return S.DEVELOPING
    if not readiness.validated_long_run:
        return S.VALIDATION_REQUIRED
    if not (readiness.race_duration_known and readiness.multipliers_known):
        return S.PROVISIONAL
    return S.FINALISATION_READY


def _missing_evidence(readiness: StrategyEvidenceReadiness) -> Tuple[str, ...]:
    checks = [
        ("representative race pace", readiness.has_representative_race_pace),
        ("lap-time consistency", readiness.has_lap_consistency),
        ("fuel use", readiness.has_fuel_use),
        ("tyre degradation", readiness.has_tyre_degradation),
        ("compound pace", readiness.has_compound_pace),
        ("pit loss", readiness.has_pit_loss),
        ("refuel rate", readiness.refuel_rate_known),
        ("race duration", readiness.race_duration_known),
        ("tyre/fuel multipliers", readiness.multipliers_known),
        ("validated long run", readiness.validated_long_run),
    ]
    return tuple(name for (name, ok) in checks if not ok)


def build_strategy_maturity(
    evidence: CumulativePreparationEvidence,
    readiness: StrategyEvidenceReadiness,
) -> StrategyMaturitySummary:
    tyre_m, tyre_note = _model_maturity(evidence, EvidenceDomain.TYRE_MODEL)
    fuel_m, fuel_note = _model_maturity(evidence, EvidenceDomain.FUEL_MODEL)
    tf = TyreFuelMaturity(tyre=tyre_m, fuel=fuel_m, tyre_note=tyre_note, fuel_note=fuel_note)
    maturity = assess_strategy_maturity(readiness)
    summary = StrategyMaturitySummary(maturity=maturity, tyre_fuel=tf,
                                      missing_evidence=_missing_evidence(readiness), fingerprint="")
    return StrategyMaturitySummary(maturity=summary.maturity, tyre_fuel=summary.tyre_fuel,
                                   missing_evidence=summary.missing_evidence,
                                   fingerprint=_fp(summary.as_payload()))
