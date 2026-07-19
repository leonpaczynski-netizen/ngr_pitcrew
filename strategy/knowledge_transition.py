"""Knowledge Transition — how one piece of evidence moved engineering understanding (Phase 25).

A deterministic, READ-ONLY classifier that, given the running evidence state of a domain and one
new evidence record (+ its independence), decides the transition type and the resulting local
evidence-narrative state. It NEVER collapses conflict, regression, supersession and uncertainty
into one generic state.

The "local state" is a timeline NARRATIVE of evidence accumulation (observed / building /
independently_supported / conflicted / regressed / retired) - it is NOT a Phase-22 maturity
claim; the authoritative current maturity/confidence come from the Phase-24 playbook.

Dates are data: this classifier never treats a later record as automatically stronger. A newer
but weaker contradiction yields NO_MATERIAL_CHANGE, preserving the older stronger finding.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Optional, Tuple

KNOWLEDGE_TRANSITION_VERSION = "knowledge_transition_v1"

_CONF_RANK = {"": 0, "unknown": 0, "very_low": 1, "low": 1, "med": 2, "medium": 2, "high": 3,
              "very_high": 3}
_POSITIVE = ("confirmed_improvement", "partial_improvement")
_NEGATIVE = ("regression",)
_INSUFFICIENT = ("insufficient_evidence", "confounded", "")
# independence values that count as a genuinely / partially new evidence line.
_INDEP_NEW = ("independent",)
_INDEP_PARTIAL = ("same_campaign", "partially_independent")


class KnowledgeTransitionType(str, Enum):
    INITIAL_OBSERVATION = "initial_observation"
    REPEATED_SUPPORT = "repeated_support"
    INDEPENDENT_CONFIRMATION = "independent_confirmation"
    CONFIDENCE_INCREASED = "confidence_increased"
    CONFIDENCE_REDUCED = "confidence_reduced"
    MATURITY_ADVANCED = "maturity_advanced"
    MATURITY_REDUCED = "maturity_reduced"
    CONFIRMED_GOOD_ESTABLISHED = "confirmed_good_established"
    CONFIRMED_GOOD_PRESERVED = "confirmed_good_preserved"
    CONFLICT_INTRODUCED = "conflict_introduced"
    CONFLICT_RESOLVED = "conflict_resolved"
    REGRESSION_OBSERVED = "regression_observed"
    DIRECTION_RETIRED = "direction_retired"
    SUPERSEDED = "superseded"
    CONTEXT_NARROWED = "context_narrowed"
    TRANSFER_LIMITED = "transfer_limited"
    NO_MATERIAL_CHANGE = "no_material_change"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


# Fixed enum order for deterministic tie-breaking.
TRANSITION_ORDER = [t.value for t in KnowledgeTransitionType]

_LOCAL_STATES = ("none", "observed", "building", "independently_supported", "conflicted",
                 "regressed", "retired")


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


@dataclass(frozen=True)
class TransitionResult:
    transition_type: str
    prior_state: str
    resulting_state: str
    rationale: str

    def to_dict(self) -> dict:
        return {"transition_type": self.transition_type, "prior_state": self.prior_state,
                "resulting_state": self.resulting_state, "rationale": self.rationale}


def outcome_kind(status: str) -> str:
    s = _lc(status)
    if s in _POSITIVE:
        return "positive"
    if s in _NEGATIVE:
        return "negative"
    if s in _INSUFFICIENT:
        return "insufficient"
    return "neutral"


def classify_transition(state: Mapping, record: Mapping, independence: str) -> TransitionResult:
    """Classify ONE evidence record's transition given the running domain ``state``.

    ``state`` keys (all optional): observed(bool), positive_count(int), independent_lines(int),
    conflicted(bool), retired(bool), confirmed_good(bool), best_conf_rank(int).
    ``record`` keys: outcome_status, confidence_level, is_failed_direction(bool).
    Never raises.
    """
    state = state if isinstance(state, Mapping) else {}
    record = record if isinstance(record, Mapping) else {}
    indep = _lc(independence)
    kind = outcome_kind(record.get("outcome_status"))
    conf_rank = _CONF_RANK.get(_lc(record.get("confidence_level")), 0)
    prior = _lc(state.get("local_state")) or "none"
    observed = bool(state.get("observed"))
    conflicted = bool(state.get("conflicted"))
    retired = bool(state.get("retired"))
    confirmed_good_now = bool(record.get("confirmed_good_now"))
    prior_confirmed_good = bool(state.get("confirmed_good"))
    best_rank = int(state.get("best_conf_rank") or 0)
    failed_direction = bool(record.get("is_failed_direction"))

    def _r(tt: KnowledgeTransitionType, resulting: str, why: str) -> TransitionResult:
        return TransitionResult(transition_type=tt.value, prior_state=prior,
                                resulting_state=resulting, rationale=why)

    # 1. first evidence ever for the domain.
    if not observed:
        if kind == "positive":
            return _r(KnowledgeTransitionType.INITIAL_OBSERVATION, "observed",
                      "first supporting observation for this domain")
        if kind == "negative":
            return _r(KnowledgeTransitionType.INITIAL_OBSERVATION, "regressed",
                      "first observation for this domain is a regression")
        if kind == "insufficient":
            return _r(KnowledgeTransitionType.INSUFFICIENT_EVIDENCE, "observed",
                      "first observation carries insufficient evidence")
        return _r(KnowledgeTransitionType.INITIAL_OBSERVATION, "observed",
                  "first (neutral) observation for this domain")

    # 2. insufficient evidence.
    if kind == "insufficient":
        return _r(KnowledgeTransitionType.INSUFFICIENT_EVIDENCE, prior,
                  "insufficient / confounded evidence - no material change")

    # 3. negative evidence (regression / failed direction).
    if kind == "negative":
        if failed_direction and state.get("positive_count"):
            return _r(KnowledgeTransitionType.DIRECTION_RETIRED, "retired",
                      "a previously supported direction produced a regression and is retired")
        if state.get("positive_count"):
            return _r(KnowledgeTransitionType.CONFLICT_INTRODUCED, "conflicted",
                      "a regression conflicts with earlier supporting evidence - certainty reduced")
        return _r(KnowledgeTransitionType.REGRESSION_OBSERVED, "regressed",
                  "a regression with no offsetting confirmation")

    # 4. neutral evidence.
    if kind == "neutral":
        return _r(KnowledgeTransitionType.NO_MATERIAL_CHANGE, prior,
                  "no meaningful change in this domain's knowledge")

    # 5. positive evidence — depends on independence, confidence and prior state.
    if retired and conf_rank <= best_rank:
        # a later, not-stronger positive does not reopen a retired direction.
        return _r(KnowledgeTransitionType.NO_MATERIAL_CHANGE, "retired",
                  "a positive result that is not stronger than the evidence that retired this "
                  "direction - it does not reopen it (newer is not automatically better)")
    if conflicted:
        # a positive after a conflict resolves it only if it is at least as strong.
        if conf_rank >= best_rank:
            return _r(KnowledgeTransitionType.CONFLICT_RESOLVED, "independently_supported"
                      if indep in _INDEP_NEW else "building",
                      "new supporting evidence at least as strong as the conflicting evidence - "
                      "conflict resolved")
        return _r(KnowledgeTransitionType.NO_MATERIAL_CHANGE, "conflicted",
                  "a weaker positive does not resolve the existing conflict")
    if confirmed_good_now and not prior_confirmed_good:
        return _r(KnowledgeTransitionType.CONFIRMED_GOOD_ESTABLISHED, "independently_supported",
                  "the domain reached confirmed-good status")
    if prior_confirmed_good:
        return _r(KnowledgeTransitionType.CONFIRMED_GOOD_PRESERVED, "independently_supported",
                  "later supporting evidence preserves the confirmed-good behaviour")
    if indep in _INDEP_NEW:
        return _r(KnowledgeTransitionType.INDEPENDENT_CONFIRMATION, "independently_supported",
                  "a genuinely independent evidence line confirms the direction")
    if indep in _INDEP_PARTIAL:
        return _r(KnowledgeTransitionType.REPEATED_SUPPORT, "building",
                  "a partially independent (same-scope, separate session) repeat of support")
    if conf_rank > best_rank:
        return _r(KnowledgeTransitionType.CONFIDENCE_INCREASED, "building",
                  "supporting evidence at higher confidence than before")
    return _r(KnowledgeTransitionType.REPEATED_SUPPORT, "building",
              "dependent (same-session or same-record) repeat of support - not a new confirmation")


def transition_versions() -> dict:
    return {"knowledge_transition": KNOWLEDGE_TRANSITION_VERSION}
