"""Knowledge Convergence — has a domain's evidence genuinely converged? (Program 2, Phase 25).

A deterministic, READ-ONLY assessment of whether a domain's knowledge has genuinely converged
through INDEPENDENT repeated evidence, remains unresolved, or only looks repeated because it
derives from the same session / campaign / source / inherited conclusion. Strong convergence is
evidence-gated and lineage-aware: repeated dependent evidence never produces strong convergence,
and a conclusion re-stated through Phases 22/23/24 is ONE lineage, not three confirmations.

It reuses the Phase-24 confirmed-good semantics and Phase-22 maturity/confidence definitions (via
the playbook authority) rather than inventing replacements, and keeps Phase-23 transfer limits
adjacent to any claimed stability. Conflict reduces certainty (never averaged into false
stability); regressions remain negative learning; retired directions stay retired.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Mapping, Sequence, Tuple

KNOWLEDGE_CONVERGENCE_VERSION = "knowledge_convergence_v1"

# Visible thresholds (no hidden numbers).
STRONG_MIN_INDEPENDENT_GROUPS = 2      # >=2 genuinely independent lines for strong convergence
CONVERGING_MIN_SUPPORT = 1             # >=1 support line to be "converging"
_ESTABLISHED = ("established", "mature", "complete")
_CONTEXT_BOUND_CLASSES = ("context_bound", "car_track_specific", "driver_specific")

# Convergence-status display / ordering priority (lower = shown first). VISIBLE constant.
CONVERGENCE_PRIORITY = {
    "conflicting": 0, "regressed": 1, "superseded": 2, "strongly_converged": 3,
    "stable_confirmed_good": 4, "converging": 5, "stable_but_context_bound": 6, "mixed": 7,
    "insufficient_evidence": 8, "unknown": 9,
}


class ConvergenceStatus(str, Enum):
    STRONGLY_CONVERGED = "strongly_converged"
    CONVERGING = "converging"
    STABLE_BUT_CONTEXT_BOUND = "stable_but_context_bound"
    STABLE_CONFIRMED_GOOD = "stable_confirmed_good"
    MIXED = "mixed"
    CONFLICTING = "conflicting"
    REGRESSED = "regressed"
    SUPERSEDED = "superseded"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    UNKNOWN = "unknown"


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


def _int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


@dataclass(frozen=True)
class KnowledgeConvergence:
    domain: str
    convergence_status: str
    independent_support_count: int
    dependent_support_count: int
    regression_count: int
    conflict_count: int
    confirmation_count: int
    compatible_contexts: int
    context_limited_observations: int
    current_maturity: str
    current_confidence: str
    confirmed_good: bool
    retired_directions: Tuple[str, ...]
    unresolved_boundaries: Tuple[str, ...]
    transfer_limitations: Tuple[str, ...]
    evidence_lineage_summary: str
    suitable_only_as_investigation_aid: bool
    rationale: str
    eval_version: str = KNOWLEDGE_CONVERGENCE_VERSION

    def to_dict(self) -> dict:
        return {"domain": self.domain, "convergence_status": self.convergence_status,
                "independent_support_count": self.independent_support_count,
                "dependent_support_count": self.dependent_support_count,
                "regression_count": self.regression_count, "conflict_count": self.conflict_count,
                "confirmation_count": self.confirmation_count,
                "compatible_contexts": self.compatible_contexts,
                "context_limited_observations": self.context_limited_observations,
                "current_maturity": self.current_maturity,
                "current_confidence": self.current_confidence, "confirmed_good": self.confirmed_good,
                "retired_directions": list(self.retired_directions),
                "unresolved_boundaries": list(self.unresolved_boundaries),
                "transfer_limitations": list(self.transfer_limitations),
                "evidence_lineage_summary": self.evidence_lineage_summary,
                "suitable_only_as_investigation_aid": self.suitable_only_as_investigation_aid,
                "rationale": self.rationale, "eval_version": self.eval_version}


def _superseded(points: Sequence[Mapping]) -> bool:
    """A retired direction later replaced by a stronger independent confirmation = superseded
    (history retained). Requires explicit stronger evidence, not merely a later date."""
    retired_seq = None
    retired_conf_rank = 0
    rank = {"unknown": 0, "low": 1, "medium": 2, "high": 3}
    for p in points:
        tt = _lc(p.get("transition_type"))
        seq = _int(p.get("sequence_key"))
        if tt == "direction_retired":
            retired_seq = seq
            retired_conf_rank = rank.get(_lc(p.get("confidence_after")), 0)
        elif retired_seq is not None and seq >= retired_seq and tt in (
                "independent_confirmation", "confirmed_good_established"):
            if rank.get(_lc(p.get("confidence_after")), 0) >= retired_conf_rank:
                return True
    return False


def assess_convergence(domain: str, points: Sequence[Mapping], independence_summary: Mapping,
                       authority: Mapping) -> KnowledgeConvergence:
    """Assess ONE domain's convergence from its timeline points + independence summary + the
    Phase-24 playbook authority (maturity/confidence/confirmed_good/regressions/conflicting/
    transfer). Deterministic; never raises."""
    domain = _lc(domain)
    pts = [p for p in (points or []) if isinstance(p, Mapping)]
    ind = independence_summary if isinstance(independence_summary, Mapping) else {}
    auth = authority if isinstance(authority, Mapping) else {}

    independent = _int(ind.get("independent_groups"))
    partial = _int(ind.get("partially_independent"))
    dependent = _int(ind.get("same_session")) + _int(ind.get("same_source_record")) + partial
    regressions = _int(auth.get("regressions"))
    confirmations = _int(auth.get("confirmations"))
    conflicting = bool(auth.get("conflicting"))
    maturity = _lc(auth.get("maturity"))
    confidence = _lc(auth.get("confidence"))
    confirmed_good = bool(auth.get("confirmed_good"))
    transfer_class = _lc(auth.get("transfer_class"))
    transfer_limits = tuple(str(x) for x in (auth.get("transfer_limitations") or ()))
    retired = tuple(str(x) for x in (auth.get("retired_directions") or ()))
    boundaries = tuple(str(x) for x in (auth.get("unresolved_boundaries") or ()))
    compatible = _int(auth.get("compatible_contexts"))
    context_limited = _int(auth.get("context_limited_observations"))
    conflict_count = sum(1 for p in pts if _lc(p.get("transition_type")) == "conflict_introduced")
    conflict_resolved = any(_lc(p.get("transition_type")) == "conflict_resolved" for p in pts)
    established = maturity in _ESTABLISHED
    superseded = _superseded(pts)

    lineage = (f"{independent} independent line(s), {partial} partially-independent (same-scope) "
               f"repeat(s), {_int(ind.get('same_session'))} same-session and "
               f"{_int(ind.get('same_source_record'))} same-record repeat(s). Phase-22/23/24 "
               "re-statements of this conclusion are one lineage, not extra confirmations.")

    # deterministic ladder.
    if superseded:
        status = ConvergenceStatus.SUPERSEDED
        why = ("an earlier conclusion was superseded by later stronger independent evidence; the "
               "historical conclusion is retained in the timeline.")
    elif conflicting and not conflict_resolved:
        status = ConvergenceStatus.CONFLICTING
        why = ("evidence conflicts (both confirmed and regressed) and is not resolved - certainty "
               "is reduced, not averaged into stability.")
    elif regressions > 0 and confirmations == 0:
        status = ConvergenceStatus.REGRESSED
        why = "regression(s) with no offsetting confirmation - negative learning, not convergence."
    elif confirmed_good and regressions == 0:
        status = ConvergenceStatus.STABLE_CONFIRMED_GOOD
        why = "a confirmed-good behaviour preserved through later evidence (protect it)."
    elif established and transfer_class in _CONTEXT_BOUND_CLASSES:
        # a context-bound domain (car/track/driver specific) is stable HERE, not universally -
        # it is never labelled strongly converged (which would imply broad reusability).
        status = ConvergenceStatus.STABLE_BUT_CONTEXT_BOUND
        why = ("established but context-bound (track / car / driver specific) - stable here, not "
               "universally; convergence does not extend to other contexts.")
    elif (independent >= STRONG_MIN_INDEPENDENT_GROUPS and established and regressions == 0
          and not conflicting):
        status = ConvergenceStatus.STRONGLY_CONVERGED
        why = (f"{independent} genuinely independent supporting line(s), {maturity} maturity, no "
               "unresolved regression or conflict.")
    elif (independent >= CONVERGING_MIN_SUPPORT or partial >= 1) and confirmations >= 1 \
            and regressions == 0:
        status = ConvergenceStatus.CONVERGING
        why = ("evidence is building but below the independent-confirmation threshold for strong "
               "convergence.")
    elif confirmations >= 1 and regressions >= 1:
        status = ConvergenceStatus.MIXED
        why = "both supporting and negative evidence present - not a stable trend."
    elif confirmations == 0 and regressions == 0:
        status = ConvergenceStatus.INSUFFICIENT_EVIDENCE
        why = "no executed supporting or negative evidence for this domain yet."
    else:
        status = ConvergenceStatus.UNKNOWN
        why = "convergence could not be classified from the available evidence."

    investigation_only = bool(transfer_limits) or status.value not in (
        ConvergenceStatus.STRONGLY_CONVERGED.value, ConvergenceStatus.STABLE_CONFIRMED_GOOD.value)

    return KnowledgeConvergence(
        domain=domain, convergence_status=status.value, independent_support_count=independent,
        dependent_support_count=dependent, regression_count=regressions,
        conflict_count=conflict_count, confirmation_count=confirmations,
        compatible_contexts=compatible, context_limited_observations=context_limited,
        current_maturity=maturity, current_confidence=confidence, confirmed_good=confirmed_good,
        retired_directions=retired, unresolved_boundaries=boundaries,
        transfer_limitations=transfer_limits, evidence_lineage_summary=lineage,
        suitable_only_as_investigation_aid=investigation_only, rationale=why)


def convergence_versions() -> dict:
    return {"knowledge_convergence": KNOWLEDGE_CONVERGENCE_VERSION}
