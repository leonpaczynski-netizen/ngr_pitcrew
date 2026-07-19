"""Re-validation Status — deterministic freshness classification per domain (Program 2, Phase 26).

Classifies each knowledge domain's freshness / re-validation status from its Phase-26 decay
signals + the Phase-25 convergence authority. It reports status only - it schedules nothing,
creates no reminders or future dates, and generates no test plan or setup action.

Confirmed-good behaviour stays protected unless evidence explicitly invalidates it; a retired
direction stays retired; a version change re-validates only version-sensitive knowledge; unknown
date/version produces an insufficient / uncertain status, never automatic invalidation.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Tuple

from strategy.revalidation_reason import reasons_from_signals

REVALIDATION_STATUS_VERSION = "revalidation_status_v1"


class KnowledgeFreshnessStatus(str, Enum):
    CURRENT = "current"
    CURRENT_BUT_CONTEXT_BOUND = "current_but_context_bound"
    REVALIDATION_ADVISED = "revalidation_advised"
    REVALIDATION_REQUIRED = "revalidation_required"
    INVALIDATED_BY_VERSION_CHANGE = "invalidated_by_version_change"
    WEAKENED_BY_CONFLICT = "weakened_by_conflict"
    WEAKENED_BY_REGRESSION = "weakened_by_regression"
    SUPERSEDED = "superseded"
    RETIRED = "retired"
    INSUFFICIENT_DATE_EVIDENCE = "insufficient_date_evidence"
    INSUFFICIENT_CONTEXT_EVIDENCE = "insufficient_context_evidence"
    UNKNOWN = "unknown"


# Display / ordering priority (lower = shown first). VISIBLE constant.
FRESHNESS_PRIORITY = {
    "invalidated_by_version_change": 0, "weakened_by_conflict": 1, "weakened_by_regression": 2,
    "superseded": 3, "retired": 4, "revalidation_required": 5, "revalidation_advised": 6,
    "insufficient_date_evidence": 7, "insufficient_context_evidence": 8,
    "current_but_context_bound": 9, "current": 10, "unknown": 11,
}


@dataclass(frozen=True)
class KnowledgeRevalidationStatus:
    domain: str
    freshness_status: str
    convergence_status: str
    confirmed_good: bool
    current_maturity: str
    current_confidence: str
    last_evidence_date: str
    latest_compatible_evidence_date: str
    latest_incompatible_evidence_date: str
    gt7_version_evidence: str
    context_comparison: dict
    reasons: Tuple[dict, ...]
    evidence_lineage: str
    knowledge_still_usable: bool
    investigation_aid_only: bool
    missing_evidence: str
    no_action_statement: str
    eval_version: str = REVALIDATION_STATUS_VERSION

    def to_dict(self) -> dict:
        return {"domain": self.domain, "freshness_status": self.freshness_status,
                "convergence_status": self.convergence_status, "confirmed_good": self.confirmed_good,
                "current_maturity": self.current_maturity,
                "current_confidence": self.current_confidence,
                "last_evidence_date": self.last_evidence_date,
                "latest_compatible_evidence_date": self.latest_compatible_evidence_date,
                "latest_incompatible_evidence_date": self.latest_incompatible_evidence_date,
                "gt7_version_evidence": self.gt7_version_evidence,
                "context_comparison": dict(self.context_comparison),
                "reasons": [dict(r) for r in self.reasons],
                "evidence_lineage": self.evidence_lineage,
                "knowledge_still_usable": self.knowledge_still_usable,
                "investigation_aid_only": self.investigation_aid_only,
                "missing_evidence": self.missing_evidence,
                "no_action_statement": self.no_action_statement, "eval_version": self.eval_version}


_NO_ACTION = ("Re-validation status only - no test, experiment, campaign, schedule, reminder or "
              "setup action is created or applied. Existing knowledge remains as recorded.")


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


def classify_revalidation(signals: Mapping, source_programme: Mapping) -> KnowledgeRevalidationStatus:
    """Classify ONE domain's re-validation status from its decay signals. Deterministic ladder;
    every status explained by reasons; never raises."""
    s = signals if isinstance(signals, Mapping) else {}
    src = source_programme if isinstance(source_programme, Mapping) else {}
    domain = _lc(s.get("domain"))
    reasons = reasons_from_signals(s)

    superseded = bool(s.get("is_superseded"))
    retired = bool(s.get("retired_directions"))
    has_conflict = bool(s.get("has_conflict"))
    has_regression = bool(s.get("has_regression"))
    confirmed_good = bool(s.get("is_confirmed_good"))
    version_sensitive = bool(s.get("version_sensitive"))
    version_changed = bool(s.get("version_changed"))
    dependent_heavy = bool(s.get("dependent_heavy"))
    all_dates_unknown = bool(s.get("all_dates_unknown"))
    context_unknown = bool(s.get("context_unknown"))
    context_bound = bool(s.get("is_context_bound"))
    conv = _lc(s.get("convergence_status"))

    # deterministic ladder.
    if superseded:
        status = KnowledgeFreshnessStatus.SUPERSEDED
        usable, aid = False, False
        missing = "new stronger compatible evidence to reinstate this conclusion"
    elif retired and not confirmed_good and conv in ("regressed", "conflicting", "mixed", "unknown"):
        status = KnowledgeFreshnessStatus.RETIRED
        usable, aid = False, False
        missing = "new explicit evidence that reopens the retired direction"
    elif has_conflict:
        status = KnowledgeFreshnessStatus.WEAKENED_BY_CONFLICT
        usable, aid = True, True
        missing = "an independent discriminating observation to resolve the conflict"
    elif has_regression and not confirmed_good:
        status = KnowledgeFreshnessStatus.WEAKENED_BY_REGRESSION
        usable, aid = True, True
        missing = "an independent re-observation of the affected direction"
    elif version_sensitive and version_changed:
        # version change re-validates only version-sensitive knowledge (never version-insensitive).
        status = KnowledgeFreshnessStatus.INVALIDATED_BY_VERSION_CHANGE
        usable, aid = True, True
        missing = "a compatible confirmation at the current GT7 version"
    elif all_dates_unknown:
        status = KnowledgeFreshnessStatus.INSUFFICIENT_DATE_EVIDENCE
        usable, aid = True, True
        missing = "a dated observation to place this knowledge in the evidence sequence"
    elif context_unknown:
        status = KnowledgeFreshnessStatus.INSUFFICIENT_CONTEXT_EVIDENCE
        usable, aid = True, True
        missing = "a context-tagged observation to establish where this knowledge applies"
    elif confirmed_good:
        # confirmed-good stays protected unless explicitly invalidated (handled above).
        status = (KnowledgeFreshnessStatus.CURRENT_BUT_CONTEXT_BOUND if context_bound
                  else KnowledgeFreshnessStatus.CURRENT)
        usable, aid = True, context_bound
        missing = "" if not context_bound else "an independent observation in the target context"
    elif conv == "strongly_converged":
        status = KnowledgeFreshnessStatus.CURRENT
        usable, aid = True, False
        missing = ""
    elif conv == "stable_but_context_bound" or context_bound:
        status = KnowledgeFreshnessStatus.CURRENT_BUT_CONTEXT_BOUND
        usable, aid = True, True
        missing = "an independent observation in the target context to broaden it"
    elif dependent_heavy:
        status = KnowledgeFreshnessStatus.REVALIDATION_ADVISED
        usable, aid = True, True
        missing = "a genuinely independent confirmation (current evidence is dependent)"
    elif conv in ("converging", "mixed"):
        status = KnowledgeFreshnessStatus.REVALIDATION_ADVISED
        usable, aid = True, True
        missing = "further independent evidence to reach stable convergence"
    elif conv == "insufficient_evidence":
        status = KnowledgeFreshnessStatus.INSUFFICIENT_CONTEXT_EVIDENCE
        usable, aid = True, True
        missing = "executed evidence for this domain"
    else:
        status = KnowledgeFreshnessStatus.UNKNOWN
        usable, aid = True, True
        missing = "clearer evidence to assess freshness"

    lineage = (f"{s.get('independent_count')} independent line(s), "
               f"{s.get('dependent_count')} dependent; last known evidence "
               f"{s.get('last_known_date') or 'unknown'}. Re-statements through Phases 22-25 are "
               "one lineage, not new confirmations.")
    ctx_cmp = {"gt7_version": str(src.get("gt7_version", "") or ""),
               "context_changed_fields": list(s.get("context_changed_fields") or []),
               "version_changed": version_changed, "version_sensitive": version_sensitive}

    return KnowledgeRevalidationStatus(
        domain=domain, freshness_status=status.value, convergence_status=conv,
        confirmed_good=confirmed_good, current_maturity=_lc(s.get("maturity")),
        current_confidence=_lc(s.get("confidence")),
        last_evidence_date=str(s.get("last_known_date") or ""),
        latest_compatible_evidence_date=str(s.get("last_known_date") or ""),
        latest_incompatible_evidence_date="",
        gt7_version_evidence=str(src.get("gt7_version", "") or ""), context_comparison=ctx_cmp,
        reasons=reasons, evidence_lineage=lineage, knowledge_still_usable=usable,
        investigation_aid_only=aid, missing_evidence=missing, no_action_statement=_NO_ACTION)


def status_versions() -> dict:
    return {"revalidation_status": REVALIDATION_STATUS_VERSION}
