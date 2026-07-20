"""Knowledge Readiness — per-domain synthesis of whether knowledge is ready to rely on (Phase 28).

Synthesises the Phase-22 maturity, Phase-25 convergence, Phase-26 re-validation and Phase-27
coverage / blind-spot signals into ONE per-domain readiness status: is this engineering knowledge
ready to rely on for a decision, ready only within limits, still provisional, or not yet ready (and
why). It decides nothing about the car and produces no readiness for knowledge the evidence does not
support — "ready" always means "the evidence supports relying on it", never "apply this setup".

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Tuple

KNOWLEDGE_READINESS_VERSION = "knowledge_readiness_v1"


class KnowledgeReadinessStatus(str, Enum):
    READY = "ready"
    READY_WITH_LIMITATIONS = "ready_with_limitations"
    CONTEXT_BOUND_ONLY = "context_bound_only"
    PROVISIONAL = "provisional"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"
    NEEDS_REVALIDATION = "needs_revalidation"
    CONFLICTED = "conflicted"
    REGRESSED = "regressed"
    SUPERSEDED = "superseded"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    UNKNOWN = "unknown"


# Display / ordering priority (lower = shown first) — not-ready first, ready last. VISIBLE constant.
READINESS_PRIORITY = {
    "conflicted": 0, "regressed": 1, "superseded": 2, "needs_revalidation": 3,
    "needs_more_evidence": 4, "insufficient_evidence": 5, "provisional": 6,
    "context_bound_only": 7, "ready_with_limitations": 8, "ready": 9, "unknown": 10,
}

# Statuses that count as "usable to rely on" (fully or within limits) for the programme grade.
RELYABLE_STATUSES = frozenset({"ready", "ready_with_limitations", "context_bound_only"})
# Statuses that actively block readiness (a problem is recorded, not merely missing evidence).
BLOCKING_STATUSES = frozenset({"conflicted", "regressed"})

_NO_ACTION = ("Readiness status only - it states whether the evidence supports relying on this "
              "knowledge, never 'apply this setup'. No test, experiment, campaign, schedule or "
              "setup action is created or applied.")


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


@dataclass(frozen=True)
class KnowledgeReadinessItem:
    domain: str
    readiness_status: str
    convergence_status: str
    freshness_status: str
    confirmed_good: bool
    current_maturity: str
    current_confidence: str
    coverage_gap_count: int
    blind_spot_severity: str
    limiting_factors: Tuple[str, ...]
    what_would_raise_readiness: str
    usable_as: str                # "decision" / "decision within its context" / "hypothesis" / "not yet"
    no_action_statement: str
    eval_version: str = KNOWLEDGE_READINESS_VERSION

    def to_dict(self) -> dict:
        return {"domain": self.domain, "readiness_status": self.readiness_status,
                "convergence_status": self.convergence_status,
                "freshness_status": self.freshness_status, "confirmed_good": self.confirmed_good,
                "current_maturity": self.current_maturity,
                "current_confidence": self.current_confidence,
                "coverage_gap_count": self.coverage_gap_count,
                "blind_spot_severity": self.blind_spot_severity,
                "limiting_factors": list(self.limiting_factors),
                "what_would_raise_readiness": self.what_would_raise_readiness,
                "usable_as": self.usable_as, "no_action_statement": self.no_action_statement,
                "eval_version": self.eval_version}


def classify_readiness(convergence: Mapping, revalidation_item: Mapping,
                       coverage_item: Mapping) -> KnowledgeReadinessItem:
    """Classify ONE domain's readiness from the convergence + re-validation + coverage authorities.
    Deterministic ladder; every status explained by limiting factors; never raises."""
    try:
        return _classify(convergence or {}, revalidation_item or {}, coverage_item or {})
    except Exception:
        return KnowledgeReadinessItem(
            domain=_lc((convergence or {}).get("domain")),
            readiness_status=KnowledgeReadinessStatus.UNKNOWN.value, convergence_status="unknown",
            freshness_status="unknown", confirmed_good=False, current_maturity="unknown",
            current_confidence="unknown", coverage_gap_count=0, blind_spot_severity="unknown",
            limiting_factors=(), what_would_raise_readiness="", usable_as="not yet",
            no_action_statement=_NO_ACTION)


def _classify(conv: Mapping, reval: Mapping, cov: Mapping) -> KnowledgeReadinessItem:
    domain = _lc(conv.get("domain"))
    conv_status = _lc(conv.get("convergence_status"))
    freshness = _lc(reval.get("freshness_status"))
    confirmed_good = bool(conv.get("confirmed_good"))
    maturity = _lc(conv.get("current_maturity"))
    confidence = _lc(conv.get("current_confidence"))
    gap_count = int(cov.get("gap_count") or 0)
    blind = _lc(cov.get("blind_spot_severity"))

    factors = []

    def note(msg):
        factors.append(msg)

    # deterministic ladder — problems first, then missing evidence, then positive states.
    if conv_status == "superseded" or freshness in ("superseded", "retired"):
        status = KnowledgeReadinessStatus.SUPERSEDED
        note("the conclusion was superseded or retired")
        usable = "not yet"
    elif conv_status == "conflicting" or freshness == "weakened_by_conflict":
        status = KnowledgeReadinessStatus.CONFLICTED
        note("an unresolved conflict remains in the evidence")
        usable = "not yet"
    elif conv_status == "regressed" or freshness == "weakened_by_regression":
        status = KnowledgeReadinessStatus.REGRESSED
        note("a regression weakened the tested direction")
        usable = "not yet"
    elif freshness in ("revalidation_required", "invalidated_by_version_change"):
        status = KnowledgeReadinessStatus.NEEDS_REVALIDATION
        note("context or version changed - re-validation is required before relying on it")
        usable = "hypothesis"
    elif freshness in ("insufficient_date_evidence", "insufficient_context_evidence") \
            or conv_status == "insufficient_evidence":
        status = KnowledgeReadinessStatus.INSUFFICIENT_EVIDENCE
        note("there is too little evidence to assess readiness")
        usable = "not yet"
    elif blind == "critical":
        status = KnowledgeReadinessStatus.NEEDS_MORE_EVIDENCE
        note("a critical coverage blind spot (a strong claim on thin evidence)")
        usable = "hypothesis"
    elif conv_status in ("strongly_converged", "stable_confirmed_good") \
            and freshness in ("current", "") and blind not in ("critical", "material"):
        if gap_count == 0:
            status = KnowledgeReadinessStatus.READY
            note("strong convergence, current, well covered")
            usable = "decision"
        else:
            status = KnowledgeReadinessStatus.READY_WITH_LIMITATIONS
            note("strong and current, with minor coverage gaps")
            usable = "decision"
    elif conv_status == "stable_but_context_bound" or freshness == "current_but_context_bound":
        status = KnowledgeReadinessStatus.CONTEXT_BOUND_ONLY
        note("stable only within its observed context")
        usable = "decision within its context"
    elif blind == "material" and confirmed_good:
        status = KnowledgeReadinessStatus.READY_WITH_LIMITATIONS
        note("confirmed-good but resting on limited evidence")
        usable = "decision"
    elif conv_status in ("converging", "mixed"):
        status = KnowledgeReadinessStatus.PROVISIONAL
        note("evidence is still converging")
        usable = "hypothesis"
    elif blind in ("material", "moderate") or gap_count > 0:
        status = KnowledgeReadinessStatus.NEEDS_MORE_EVIDENCE
        note("coverage gaps remain")
        usable = "hypothesis"
    else:
        status = KnowledgeReadinessStatus.UNKNOWN
        note("readiness could not be determined from the current evidence")
        usable = "not yet"

    if gap_count > 0 and status not in (KnowledgeReadinessStatus.READY,):
        note(f"{gap_count} coverage dimension(s) with gaps")
    raise_hint = _raise_hint(status)

    return KnowledgeReadinessItem(
        domain=domain, readiness_status=status.value, convergence_status=conv_status,
        freshness_status=freshness, confirmed_good=confirmed_good, current_maturity=maturity,
        current_confidence=confidence, coverage_gap_count=gap_count, blind_spot_severity=blind,
        limiting_factors=tuple(factors), what_would_raise_readiness=raise_hint, usable_as=usable,
        no_action_statement=_NO_ACTION)


def _raise_hint(status: KnowledgeReadinessStatus) -> str:
    return {
        KnowledgeReadinessStatus.READY: "",
        KnowledgeReadinessStatus.READY_WITH_LIMITATIONS: "closing the remaining coverage gaps",
        KnowledgeReadinessStatus.CONTEXT_BOUND_ONLY: "an independent observation in another context",
        KnowledgeReadinessStatus.PROVISIONAL: "further independent evidence to reach convergence",
        KnowledgeReadinessStatus.NEEDS_MORE_EVIDENCE: "an independent, broader observation",
        KnowledgeReadinessStatus.NEEDS_REVALIDATION: "a current-context / current-version confirmation",
        KnowledgeReadinessStatus.CONFLICTED: "a discriminating observation to resolve the conflict",
        KnowledgeReadinessStatus.REGRESSED: "an independent re-observation of the affected direction",
        KnowledgeReadinessStatus.SUPERSEDED: "new stronger compatible evidence",
        KnowledgeReadinessStatus.INSUFFICIENT_EVIDENCE: "any dated, context-tagged observation",
        KnowledgeReadinessStatus.UNKNOWN: "clearer evidence",
    }.get(status, "")


def knowledge_readiness_versions() -> dict:
    return {"knowledge_readiness": KNOWLEDGE_READINESS_VERSION}
