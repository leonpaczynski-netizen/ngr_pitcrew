"""Cumulative Practice evidence for one preparation cycle (Program 2, Phase 48 section 8).

MANDATORY INVARIANT: every valid Practice session bound to the Event Preparation Cycle contributes to
the SAME cumulative engineering picture. Sessions for one upcoming round are never treated as
disconnected mini-events, and a new session never RESETS prior evidence.

This module aggregates bound-session evidence into per-domain maturity WITHOUT fabricating certainty.
Three doctrines are enforced structurally:

  * Context safety — only context-*compatible* evidence strengthens an EXACT conclusion. Transferred or
    partial evidence is counted but LABELLED and caps confidence; incompatible or unknown-context
    evidence never silently strengthens exact event confidence. Per-domain compatibility overrides let
    one session be exact for race pace yet unknown for fuel (an unknown fuel multiplier caps fuel
    confidence while pace matures normally).

  * Session purpose — a coaching-only run maps ONLY to driver coaching (never setup working windows); a
    fuel test maps ONLY to the fuel model (never promotes a setup); a qualifying simulation maps to the
    QUALIFYING setup/pace (never the RACE setup). Base / Qualifying / Race setups stay separate.

  * Monotonic membership — adding a valid session can only ADD to evidence membership; an invalid
    session adds nothing and can never raise confidence.

Purity: Qt-free, DB-free, offline, deterministic, no wall-clock, never raises. Authors no setup value.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from strategy.event_preparation_cycle import (
    PreparationActivityType, PreparationProgress, PreparationReadiness, PreparationObjective,
    PreparationPhase, ReadinessLevel,
)

PREPARATION_EVIDENCE_VERSION = "preparation_evidence_v1"
PREPARATION_EVIDENCE_SCHEMA = 1


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{PREPARATION_EVIDENCE_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


class EvidenceCompatibility(str, Enum):
    """How compatible a session's context is with the cycle's exact event context."""
    EXACT = "exact"              # same car/track/layout/discipline/compound/BoP/tuning/restrictions/mults
    PARTIAL = "partial"          # transferable but labelled (some material condition differs/inferred)
    INCOMPATIBLE = "incompatible"  # materially different context; must not strengthen exact confidence
    UNKNOWN = "unknown"          # a material condition (e.g. fuel multiplier) is unknown; caps confidence


class EvidenceDomain(str, Enum):
    SETUP_BASE = "setup_base"
    SETUP_QUALIFYING = "setup_qualifying"
    SETUP_RACE = "setup_race"
    WORKING_WINDOW = "working_window"
    DRIVER_COACHING = "driver_coaching"
    TYRE_MODEL = "tyre_model"
    FUEL_MODEL = "fuel_model"
    RACE_PACE = "race_pace"
    CONSISTENCY = "consistency"
    STRATEGY = "strategy"


# session-purpose map: which engineering domains a VALID session of each activity type contributes to.
# This is the structural guarantee of session-purpose separation.
_TYPE_DOMAINS: Dict[PreparationActivityType, Tuple[EvidenceDomain, ...]] = {
    PreparationActivityType.BASELINE_PRACTICE: (EvidenceDomain.SETUP_BASE, EvidenceDomain.CONSISTENCY,
                                                EvidenceDomain.RACE_PACE),
    PreparationActivityType.SETUP_EXPERIMENT: (EvidenceDomain.SETUP_BASE, EvidenceDomain.WORKING_WINDOW),
    PreparationActivityType.GEARING_TEST: (EvidenceDomain.SETUP_RACE, EvidenceDomain.WORKING_WINDOW),
    # coaching-only: DRIVER_COACHING only. NEVER setup / working window.
    PreparationActivityType.COACHING_RUN: (EvidenceDomain.DRIVER_COACHING,),
    # fuel test: FUEL_MODEL only. NEVER a setup domain (cannot promote a setup).
    PreparationActivityType.FUEL_TEST: (EvidenceDomain.FUEL_MODEL,),
    PreparationActivityType.TYRE_TEST: (EvidenceDomain.TYRE_MODEL,),
    # qualifying sim: QUALIFYING setup + consistency. NEVER SETUP_RACE.
    PreparationActivityType.QUALIFYING_SIMULATION: (EvidenceDomain.SETUP_QUALIFYING,
                                                    EvidenceDomain.CONSISTENCY),
    PreparationActivityType.LONG_RACE_RUN: (EvidenceDomain.SETUP_RACE, EvidenceDomain.RACE_PACE,
                                            EvidenceDomain.TYRE_MODEL, EvidenceDomain.FUEL_MODEL,
                                            EvidenceDomain.CONSISTENCY, EvidenceDomain.STRATEGY),
    PreparationActivityType.STRATEGY_VALIDATION_RUN: (EvidenceDomain.STRATEGY,),
    PreparationActivityType.FINAL_SETUP_CONFIRMATION: (EvidenceDomain.SETUP_RACE,
                                                       EvidenceDomain.CONSISTENCY),
    PreparationActivityType.FREE_PRACTICE: (EvidenceDomain.CONSISTENCY, EvidenceDomain.RACE_PACE),
    PreparationActivityType.OFFICIAL_PRACTICE: (EvidenceDomain.CONSISTENCY, EvidenceDomain.RACE_PACE),
    PreparationActivityType.INSTALLATION_RUN: (),  # readiness check only, no engineering evidence
}


class ConfidenceLevel(str, Enum):
    NONE = "none"
    EMERGING = "emerging"
    DEVELOPING = "developing"
    MODERATE = "moderate"
    STRONG = "strong"


_CONFIDENCE_ORDER = (ConfidenceLevel.NONE, ConfidenceLevel.EMERGING, ConfidenceLevel.DEVELOPING,
                     ConfidenceLevel.MODERATE, ConfidenceLevel.STRONG)


@dataclass(frozen=True)
class PracticeEvidenceSample:
    """One bound telemetry session's contribution, normalised for aggregation. Built from real DB rows
    by the SessionDB orchestration; here it is context-safe data.

    ``is_valid`` gates all contribution — an invalid session (no clean laps / rejected) contributes
    nothing. ``compatibility`` is the default per-domain compatibility; ``domain_overrides`` lets a
    single session be exact for one domain and unknown/partial for another (e.g. exact race pace but
    unknown fuel multiplier)."""
    session_id: str
    activity_id: str
    activity_type: PreparationActivityType
    is_valid: bool = True
    valid_laps: int = 0
    compatibility: EvidenceCompatibility = EvidenceCompatibility.EXACT
    domain_overrides: Mapping[EvidenceDomain, EvidenceCompatibility] = field(default_factory=dict)

    def compat_for(self, domain: EvidenceDomain) -> EvidenceCompatibility:
        return self.domain_overrides.get(domain, self.compatibility)


@dataclass(frozen=True)
class DomainEvidence:
    domain: EvidenceDomain
    confidence: ConfidenceLevel
    exact_samples: int
    partial_samples: int
    session_ids: Tuple[str, ...]          # membership (sorted); monotonic in valid samples
    capped: bool                          # confidence capped by partial/unknown/incompatible context
    labelled_transferred: bool            # any evidence is transferred/partial rather than exact

    def as_payload(self) -> dict:
        return {"domain": self.domain.value, "confidence": self.confidence.value,
                "exact": self.exact_samples, "partial": self.partial_samples,
                "sessions": list(self.session_ids), "capped": self.capped,
                "labelled_transferred": self.labelled_transferred}


@dataclass(frozen=True)
class CumulativePreparationEvidence:
    domains: Tuple[DomainEvidence, ...]
    evidence_membership: Tuple[str, ...]  # every session that contributed to any domain (sorted)
    missing_domains: Tuple[EvidenceDomain, ...]
    fingerprint: str = ""

    def domain(self, d: EvidenceDomain) -> Optional[DomainEvidence]:
        for de in self.domains:
            if de.domain == d:
                return de
        return None

    def confidence(self, d: EvidenceDomain) -> ConfidenceLevel:
        de = self.domain(d)
        return de.confidence if de else ConfidenceLevel.NONE

    def as_payload(self) -> dict:
        return {"schema": PREPARATION_EVIDENCE_SCHEMA,
                "domains": [de.as_payload() for de in self.domains],
                "evidence_membership": list(self.evidence_membership),
                "missing_domains": [d.value for d in self.missing_domains]}


def _confidence_from(exact: int, partial: int, capped: bool) -> ConfidenceLevel:
    """Rule-based confidence. EXACT samples drive the level; a capped domain (any partial/unknown/
    incompatible-derived contribution, or an unknown material condition) can never exceed DEVELOPING.
    A single quick sample never yields STRONG."""
    if exact <= 0 and partial <= 0:
        return ConfidenceLevel.NONE
    if exact <= 0:
        # partial-only evidence is always labelled and capped low
        return ConfidenceLevel.EMERGING
    if exact == 1:
        level = ConfidenceLevel.EMERGING
    elif exact == 2:
        level = ConfidenceLevel.DEVELOPING
    elif exact == 3:
        level = ConfidenceLevel.MODERATE
    else:
        level = ConfidenceLevel.STRONG
    if capped and _CONFIDENCE_ORDER.index(level) > _CONFIDENCE_ORDER.index(ConfidenceLevel.DEVELOPING):
        level = ConfidenceLevel.DEVELOPING
    return level


def build_cumulative_evidence(
    samples: Sequence[PracticeEvidenceSample],
    *,
    required_domains: Sequence[EvidenceDomain] = (),
) -> CumulativePreparationEvidence:
    """Aggregate bound-session samples into per-domain maturity. Deterministic and order-independent.

    Only ``is_valid`` samples contribute. For each domain a session touches (by its activity type):
    EXACT compatibility strengthens the exact conclusion; PARTIAL is counted + labelled and caps the
    domain; INCOMPATIBLE contributes NOTHING (never strengthens exact) ; UNKNOWN counts as partial AND
    caps (an unknown material condition, e.g. fuel multiplier). Membership is the set of contributing
    sessions per domain — monotonic in valid samples."""
    per_domain: Dict[EvidenceDomain, Dict[str, object]] = {}

    def _slot(d: EvidenceDomain):
        return per_domain.setdefault(d, {"exact": 0, "partial": 0, "capped": False,
                                         "labelled": False, "sessions": set()})

    for s in samples:
        if not s.is_valid:
            continue  # invalid sessions contribute nothing to any domain
        for d in _TYPE_DOMAINS.get(s.activity_type, ()):  # session-purpose map
            compat = s.compat_for(d)
            if compat == EvidenceCompatibility.INCOMPATIBLE:
                continue  # never silently strengthens exact event confidence
            slot = _slot(d)
            if compat == EvidenceCompatibility.EXACT:
                slot["exact"] = int(slot["exact"]) + 1
            elif compat == EvidenceCompatibility.PARTIAL:
                slot["partial"] = int(slot["partial"]) + 1
                slot["capped"] = True
                slot["labelled"] = True
            elif compat == EvidenceCompatibility.UNKNOWN:
                slot["partial"] = int(slot["partial"]) + 1
                slot["capped"] = True
                slot["labelled"] = True
            slot["sessions"].add(_norm(s.session_id))

    domains: List[DomainEvidence] = []
    for d in EvidenceDomain:
        if d not in per_domain:
            continue
        slot = per_domain[d]
        exact, partial = int(slot["exact"]), int(slot["partial"])
        capped = bool(slot["capped"])
        conf = _confidence_from(exact, partial, capped)
        domains.append(DomainEvidence(
            domain=d, confidence=conf, exact_samples=exact, partial_samples=partial,
            session_ids=tuple(sorted(sid for sid in slot["sessions"] if sid)),
            capped=capped, labelled_transferred=bool(slot["labelled"])))

    domains.sort(key=lambda de: de.domain.value)
    membership = tuple(sorted({sid for de in domains for sid in de.session_ids}))
    present = {de.domain for de in domains}
    req = list(required_domains) or list(EvidenceDomain)
    missing = tuple(d for d in EvidenceDomain if d in set(req) and d not in present)

    ev = CumulativePreparationEvidence(domains=tuple(domains), evidence_membership=membership,
                                       missing_domains=missing, fingerprint="")
    return CumulativePreparationEvidence(domains=ev.domains, evidence_membership=ev.evidence_membership,
                                         missing_domains=ev.missing_domains, fingerprint=_fp(ev.as_payload()))


# ---------------------------------------------------------------------------
# Projections back onto the cycle view (readiness / progress / objective)
# ---------------------------------------------------------------------------

_DOMAIN_TO_READINESS = {
    EvidenceDomain.SETUP_BASE: "base_setup",
    EvidenceDomain.SETUP_QUALIFYING: "qualifying_setup",
    EvidenceDomain.SETUP_RACE: "race_setup",
    EvidenceDomain.TYRE_MODEL: "tyre_evidence",
    EvidenceDomain.FUEL_MODEL: "fuel_evidence",
    EvidenceDomain.DRIVER_COACHING: "driver_coaching",
    EvidenceDomain.RACE_PACE: "race_pace",
    EvidenceDomain.STRATEGY: "strategy_evidence",
    EvidenceDomain.CONSISTENCY: "consistency",
}

_CONF_TO_READINESS = {
    ConfidenceLevel.NONE: ReadinessLevel.MISSING,
    ConfidenceLevel.EMERGING: ReadinessLevel.DEVELOPING,
    ConfidenceLevel.DEVELOPING: ReadinessLevel.DEVELOPING,
    ConfidenceLevel.MODERATE: ReadinessLevel.ADEQUATE,
    ConfidenceLevel.STRONG: ReadinessLevel.STRONG,
}


def to_readiness(evidence: CumulativePreparationEvidence) -> PreparationReadiness:
    dims: List[Tuple[str, ReadinessLevel, str]] = []
    for domain, name in _DOMAIN_TO_READINESS.items():
        de = evidence.domain(domain)
        if de is None:
            dims.append((name, ReadinessLevel.MISSING, "no evidence collected"))
            continue
        level = _CONF_TO_READINESS.get(de.confidence, ReadinessLevel.DEVELOPING)
        note = f"{de.exact_samples} exact / {de.partial_samples} labelled sample(s)"
        if de.labelled_transferred:
            note += "; includes transferred/partial evidence (capped)"
        dims.append((name, level, note))
    dims.sort(key=lambda t: t[0])
    return PreparationReadiness(dimensions=tuple(dims))


def to_progress(
    evidence: CumulativePreparationEvidence,
    samples: Sequence[PracticeEvidenceSample],
) -> PreparationProgress:
    """Cumulative counts. Only valid samples are tallied. Counts never decrease when a valid session is
    added and never increase from an invalid one."""
    valid = [s for s in samples if s.is_valid]
    laps = sum(int(s.valid_laps) for s in valid)
    sessions = len({_norm(s.session_id) for s in valid if _norm(s.session_id)})
    experiments = sum(1 for s in valid if s.activity_type == PreparationActivityType.SETUP_EXPERIMENT)
    coaching = sum(1 for s in valid if s.activity_type == PreparationActivityType.COACHING_RUN)
    tyre = sum(1 for s in valid if EvidenceDomain.TYRE_MODEL in _TYPE_DOMAINS.get(s.activity_type, ())
               and s.compat_for(EvidenceDomain.TYRE_MODEL) != EvidenceCompatibility.INCOMPATIBLE)
    fuel = sum(1 for s in valid if EvidenceDomain.FUEL_MODEL in _TYPE_DOMAINS.get(s.activity_type, ())
               and s.compat_for(EvidenceDomain.FUEL_MODEL) != EvidenceCompatibility.INCOMPATIBLE)
    race_sims = sum(1 for s in valid if s.activity_type in (
        PreparationActivityType.LONG_RACE_RUN, PreparationActivityType.STRATEGY_VALIDATION_RUN))
    outstanding = tuple(f"collect {d.value} evidence" for d in evidence.missing_domains)
    return PreparationProgress(
        valid_laps=laps, practice_sessions=sessions, setup_experiments_completed=experiments,
        coaching_runs_completed=coaching, tyre_samples=tyre, fuel_samples=fuel,
        race_simulations=race_sims, outstanding_questions=outstanding)


# domain -> the preparation phase whose objective addresses it (for the recommended next objective)
_DOMAIN_TO_PHASE = {
    EvidenceDomain.SETUP_BASE: PreparationPhase.SETUP_DEVELOPMENT,
    EvidenceDomain.WORKING_WINDOW: PreparationPhase.SETUP_DEVELOPMENT,
    EvidenceDomain.DRIVER_COACHING: PreparationPhase.DRIVER_DEVELOPMENT,
    EvidenceDomain.TYRE_MODEL: PreparationPhase.TYRE_AND_FUEL_MODELLING,
    EvidenceDomain.FUEL_MODEL: PreparationPhase.TYRE_AND_FUEL_MODELLING,
    EvidenceDomain.SETUP_QUALIFYING: PreparationPhase.QUALIFYING_DEVELOPMENT,
    EvidenceDomain.SETUP_RACE: PreparationPhase.RACE_SIMULATION,
    EvidenceDomain.RACE_PACE: PreparationPhase.RACE_SIMULATION,
    EvidenceDomain.STRATEGY: PreparationPhase.STRATEGY_FINALISATION,
    EvidenceDomain.CONSISTENCY: PreparationPhase.DRIVER_DEVELOPMENT,
}

# deterministic priority order for recommending the next objective (weakest-required-first)
_OBJECTIVE_PRIORITY = (
    EvidenceDomain.SETUP_BASE, EvidenceDomain.SETUP_RACE, EvidenceDomain.SETUP_QUALIFYING,
    EvidenceDomain.TYRE_MODEL, EvidenceDomain.FUEL_MODEL, EvidenceDomain.RACE_PACE,
    EvidenceDomain.STRATEGY, EvidenceDomain.CONSISTENCY, EvidenceDomain.DRIVER_COACHING,
    EvidenceDomain.WORKING_WINDOW,
)


def to_objective(evidence: CumulativePreparationEvidence) -> PreparationObjective:
    """Recommend the next engineering objective: the highest-priority domain with the weakest evidence.
    Deterministic; never fabricates certainty — a fully-mature picture yields a confirmation objective."""
    ranked = []
    for d in _OBJECTIVE_PRIORITY:
        conf = evidence.confidence(d)
        ranked.append((_CONFIDENCE_ORDER.index(conf), _OBJECTIVE_PRIORITY.index(d), d, conf))
    ranked.sort(key=lambda t: (t[0], t[1]))
    _idx, _pri, weakest, conf = ranked[0]
    if conf in (ConfidenceLevel.MODERATE, ConfidenceLevel.STRONG):
        return PreparationObjective(
            headline="Confirm and protect the current best-known setup",
            rationale="Evidence is maturing across domains; prioritise low-risk confirmation.",
            phase=PreparationPhase.ENGINEERING_CONVERGENCE)
    return PreparationObjective(
        headline=f"Build {weakest.value} evidence",
        rationale=f"{weakest.value} is the weakest domain (confidence: {conf.value}).",
        phase=_DOMAIN_TO_PHASE.get(weakest, PreparationPhase.SETUP_DEVELOPMENT))
