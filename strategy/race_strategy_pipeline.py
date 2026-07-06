"""Group 49 — Race Strategy Brain Phase 3: session-aware recommendation pipeline.

Turns a SessionDB session id + event settings into a full, deterministic race
strategy recommendation, end to end:

    SessionDB samples -> RaceStrategyEvidence -> legal candidates -> total-time
    scoring -> best legal recommendation -> driver-readable, source-aware explanation

The only impure step (reading SessionDB) is isolated in the adapter/from-session
layer; everything here is orchestration over pure Group 48 functions. Never
raises, deterministic, evidence-gated. Authors no setup values, writes nothing,
and has no apply/approve capability.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from strategy.race_strategy_candidates import (
    StrategyCandidate,
    generate_candidates,
    legal_candidates,
)
from strategy.race_strategy_evidence import RaceStrategyEvidence, StrategyConfidence
from strategy.race_strategy_explain import StrategyExplanation
from strategy.race_strategy_from_session import (
    SessionEvidenceResult,
    build_strategy_evidence_from_event_context,
    build_strategy_evidence_from_session,
)
from strategy.race_strategy_scorer import (
    StrategyRecommendation,
    StrategyScore,
    recommend_strategy,
    score_candidates,
)
from strategy.race_strategy_session_adapter import SessionStrategySamples
from strategy.race_strategy_session_explain import build_session_explanation


@dataclass(frozen=True)
class SessionStrategyResult:
    """Full structured result of a session-backed strategy recommendation."""

    session_id: int
    car_id: int
    track: str
    layout_id: str
    evidence: RaceStrategyEvidence
    samples: SessionStrategySamples
    candidates: tuple[StrategyCandidate, ...]
    scored_candidates: tuple[StrategyScore, ...]
    recommendation: StrategyRecommendation
    explanation: StrategyExplanation
    confidence: StrategyConfidence
    missing_evidence: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    safety_notes: tuple[str, ...] = ()
    source_summary: dict = field(default_factory=dict)

    @property
    def has_recommendation(self) -> bool:
        return self.recommendation.has_recommendation


# Standing safety notes surfaced on every result — this pipeline is strategy-only.
_SAFETY_NOTES = (
    "Strategy analysis only — this authors no setup values and cannot apply or "
    "approve any setup change.",
    "SessionDB access is read-only; nothing is written to setup history or "
    "runtime files.",
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def recommend_strategy_from_session(
    db,
    *,
    session_id: int,
    car_id: int = 0,
    track: str = "",
    layout_id: str = "",
    race_duration_minutes: float = 0.0,
    race_laps: int = 0,
    fuel_multiplier: float = 0.0,
    tyre_multiplier: float = 0.0,
    refuel_rate_lps: float = 0.0,
    pit_loss_seconds: float = 0.0,
    starting_fuel_pct: float = 100.0,
    available_compounds: Sequence[str] = (),
    required_compounds: Sequence[str] = (),
    mandatory_pit_stops: int = 0,
    weather_context: Optional[str] = None,
    rear_traction_fragile: bool = False,
    derive_tyre_wear: bool = True,
) -> SessionStrategyResult:
    """Recommend a race strategy from stored SessionDB data + event settings.

    Deterministic and honest: missing session evidence lowers confidence or
    yields INSUFFICIENT_EVIDENCE (no recommendation) rather than fabricated
    numbers. ``rear_traction_fragile`` (typically from the structured driver
    profile) drives the Group 48 safety-aware tie-break so an aggressive push is
    demoted when the rear is fragile. Never raises.
    """
    ev_result = build_strategy_evidence_from_session(
        db,
        session_id=session_id,
        car_id=car_id,
        track=track,
        layout_id=layout_id,
        race_duration_minutes=race_duration_minutes,
        race_laps=race_laps,
        fuel_multiplier=fuel_multiplier,
        tyre_multiplier=tyre_multiplier,
        refuel_rate_lps=refuel_rate_lps,
        pit_loss_seconds=pit_loss_seconds,
        starting_fuel_pct=starting_fuel_pct,
        available_compounds=available_compounds,
        required_compounds=required_compounds,
        mandatory_pit_stops=mandatory_pit_stops,
        weather_context=weather_context,
        derive_tyre_wear=derive_tyre_wear,
    )
    return _assemble(ev_result, rear_traction_fragile=rear_traction_fragile)


def recommend_strategy_from_event_context(
    db,
    *,
    session_id: int,
    event_context,
    pit_loss_seconds: float = 0.0,
    starting_fuel_pct: float = 100.0,
    weather_context: Optional[str] = None,
    rear_traction_fragile: bool = False,
    derive_tyre_wear: bool = True,
) -> SessionStrategyResult:
    """As :func:`recommend_strategy_from_session`, sourcing event settings from the
    canonical :class:`EventContext`. Never raises."""
    ev_result = build_strategy_evidence_from_event_context(
        db,
        session_id=session_id,
        event_context=event_context,
        pit_loss_seconds=pit_loss_seconds,
        starting_fuel_pct=starting_fuel_pct,
        weather_context=weather_context,
        derive_tyre_wear=derive_tyre_wear,
    )
    return _assemble(ev_result, rear_traction_fragile=rear_traction_fragile)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _assemble(
    ev_result: SessionEvidenceResult,
    *,
    rear_traction_fragile: bool,
) -> SessionStrategyResult:
    """Run the pure Group 48 stack over session-built evidence and package it."""
    try:
        evidence = ev_result.evidence
        samples = ev_result.samples

        candidates = generate_candidates(evidence)
        scored = score_candidates(
            candidates, evidence,
            rear_traction_fragile=rear_traction_fragile, legal_only=True,
        )
        recommendation = recommend_strategy(
            evidence, rear_traction_fragile=rear_traction_fragile
        )
        explanation = build_session_explanation(
            recommendation, evidence, ev_result.source_summary
        )

        return SessionStrategyResult(
            session_id=samples.session_id,
            car_id=samples.car_id,
            track=samples.track,
            layout_id=samples.layout_id,
            evidence=evidence,
            samples=samples,
            candidates=tuple(candidates),
            scored_candidates=tuple(scored),
            recommendation=recommendation,
            explanation=explanation,
            confidence=recommendation.confidence,
            missing_evidence=tuple(recommendation.missing_evidence),
            warnings=tuple(ev_result.warnings),
            safety_notes=_SAFETY_NOTES,
            source_summary=ev_result.source_summary,
        )
    except Exception:
        # Absolute fallback — never raise out of the pipeline.
        evidence = ev_result.evidence
        recommendation = recommend_strategy(evidence, rear_traction_fragile=rear_traction_fragile)
        explanation = build_session_explanation(recommendation, evidence, ev_result.source_summary)
        return SessionStrategyResult(
            session_id=ev_result.samples.session_id,
            car_id=ev_result.samples.car_id,
            track=ev_result.samples.track,
            layout_id=ev_result.samples.layout_id,
            evidence=evidence,
            samples=ev_result.samples,
            candidates=(),
            scored_candidates=(),
            recommendation=recommendation,
            explanation=explanation,
            confidence=recommendation.confidence,
            missing_evidence=tuple(recommendation.missing_evidence),
            warnings=tuple(ev_result.warnings) + ("pipeline fallback engaged",),
            safety_notes=_SAFETY_NOTES,
            source_summary=ev_result.source_summary,
        )
