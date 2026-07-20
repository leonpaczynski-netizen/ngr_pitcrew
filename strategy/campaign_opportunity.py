"""Campaign Opportunity — is further work on this campaign worthwhile? (Program 2, Phase 20).

A deterministic, ADVISORY-ONLY classification that answers, for ONE campaign: *how worthwhile
is more work here?* It ORCHESTRATES existing authorities and adds no new logic of its own:
campaign completion status = Phase 18; evidence saturation = Phase 19; confidence = Phase 20
knowledge-confidence; cost = Phase 19 cost model. Every outcome carries a visible rationale.

It classifies; it decides nothing. It never completes / freezes / abandons a campaign, creates
an experiment, re-ranks, or applies a setup. The Phase-18 completion authority and the frozen
Apply gate remain untouched. Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no
random, no wall-clock; deterministic; never raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Optional, Tuple

CAMPAIGN_OPPORTUNITY_VERSION = "campaign_opportunity_v1"


class CampaignOpportunity(str, Enum):
    COMPLETE = "complete"
    NEARLY_COMPLETE = "nearly_complete"
    WORTH_ANOTHER_CONFIRMATION = "worth_another_confirmation"
    WORTH_CONTRADICTION_TESTING = "worth_contradiction_testing"
    WORTH_MECHANISM_ISOLATION = "worth_mechanism_isolation"
    NOT_WORTH_FURTHER_WORK = "not_worth_further_work"
    EVIDENCE_EXHAUSTED = "evidence_exhausted"
    KNOWLEDGE_PLATEAU = "knowledge_plateau"
    UNKNOWN = "unknown"


# Statuses owned by Phase 18 that this layer only READS (never sets).
_STATUS_COMPLETED = "completed"
_STATUS_READY_TO_FREEZE = "ready_to_freeze"
_STATUS_ABANDONED = "abandoned"
_STATUS_STALE = "stale"

# Confidence levels (Phase 20) considered "confident enough that more confirmation adds little".
_CONFIDENT_LEVELS = ("high", "very_high")


@dataclass(frozen=True)
class CampaignOpportunityResult:
    campaign_id: str
    objective: str
    opportunity: str
    worthwhile: bool
    reason: str
    factors: dict
    recommended_focus: str      # advisory description of WHAT kind of test — not an instruction
    eval_version: str = CAMPAIGN_OPPORTUNITY_VERSION

    def to_dict(self) -> dict:
        return {"campaign_id": self.campaign_id, "objective": self.objective,
                "opportunity": self.opportunity, "worthwhile": self.worthwhile,
                "reason": self.reason, "factors": dict(self.factors),
                "recommended_focus": self.recommended_focus, "eval_version": self.eval_version}


def _int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def classify_campaign_opportunity(campaign_efficiency: Mapping,
                                  confidence: Mapping,
                                  roi: Optional[Mapping] = None) -> CampaignOpportunityResult:
    """Deterministic opportunity classification for ONE campaign from existing measures:
    Phase-18 status + Phase-19 saturation + Phase-20 confidence (+ Phase-20 ROI). Every branch
    is explained. Advisory only; never raises."""
    campaign_efficiency = campaign_efficiency if isinstance(campaign_efficiency, Mapping) else {}
    confidence = confidence if isinstance(confidence, Mapping) else {}
    roi = roi if isinstance(roi, Mapping) else {}

    cid = str(campaign_efficiency.get("campaign_id") or "")
    objective = str(campaign_efficiency.get("objective") or "")
    status = str(campaign_efficiency.get("status") or "").strip().lower()
    sat = campaign_efficiency.get("saturation") or {}
    sat = sat if isinstance(sat, Mapping) else {}
    sig = sat.get("signals") or {}
    sig = sig if isinstance(sig, Mapping) else {}
    sat_status = str(sat.get("status") or "").strip().lower()
    conf_level = str(confidence.get("overall_level") or "unknown").strip().lower()

    executed = _int(sig.get("executed"))
    remaining_untested = _int(sig.get("remaining_untested_experiments"))
    remaining_discriminating = _int(sig.get("remaining_discriminating_experiments"))
    unresolved_mechanisms = _int(sig.get("unresolved_mechanisms"))
    conflicting = bool(sig.get("conflicting_evidence"))
    confirmations = _int(sig.get("confirmations"))
    nothing_left = remaining_untested == 0

    factors = {
        "campaign_status": status, "saturation_status": sat_status,
        "confidence_level": conf_level, "executed": executed,
        "remaining_untested_experiments": remaining_untested,
        "remaining_discriminating_experiments": remaining_discriminating,
        "unresolved_mechanisms": unresolved_mechanisms, "conflicting_evidence": conflicting,
        "confirmations": confirmations,
    }

    # --- deterministic ladder (Phase-18 completion authority is read, never overridden) ---
    if status == _STATUS_COMPLETED:
        return _r(cid, objective, CampaignOpportunity.COMPLETE, False,
                  "Phase 18 marks this campaign COMPLETED (confirmed across sessions); no "
                  "further work is required.", factors, "none")
    if status == _STATUS_READY_TO_FREEZE:
        return _r(cid, objective, CampaignOpportunity.NEARLY_COMPLETE, False,
                  "Phase 18 marks this READY_TO_FREEZE; the objective is met and awaits the "
                  "existing freeze authority - no further testing is needed.", factors,
                  "freeze via the existing authority")
    if executed == 0 and remaining_untested == 0:
        return _r(cid, objective, CampaignOpportunity.UNKNOWN, False,
                  "No experiment has run and none remains - opportunity cannot be assessed.",
                  factors, "none")

    # conflicting evidence with a discriminating test still available -> resolve it first.
    if conflicting and remaining_discriminating > 0:
        return _r(cid, objective, CampaignOpportunity.WORTH_CONTRADICTION_TESTING, True,
                  "Evidence conflicts (both confirmed and regressed) and a discriminating test "
                  "remains - a session to resolve the contradiction is worthwhile.", factors,
                  "contradiction / discriminating test")

    # over-tested: kept testing, learned nothing new, nothing left to discriminate.
    if sat_status == "overtested":
        return _r(cid, objective, CampaignOpportunity.EVIDENCE_EXHAUSTED, False,
                  "Phase 19 reports the evidence is OVER-TESTED - repeated tests are no longer "
                  "adding information; further work is not worthwhile.", factors, "none")

    # unresolved mechanism with a legal experiment left -> isolate the mechanism.
    if unresolved_mechanisms > 0 and remaining_untested > 0:
        return _r(cid, objective, CampaignOpportunity.WORTH_MECHANISM_ISOLATION, True,
                  f"{unresolved_mechanisms} mechanism(s) remain unresolved and a legal "
                  "experiment is available - a mechanism-isolation session is worthwhile.",
                  factors, "mechanism isolation")

    # a direction confirmed but confidence is not yet HIGH, and a test remains -> confirm again.
    if (confirmations >= 1 and conf_level not in _CONFIDENT_LEVELS
            and remaining_untested > 0):
        return _r(cid, objective, CampaignOpportunity.WORTH_ANOTHER_CONFIRMATION, True,
                  f"A direction is confirmed but confidence is only {conf_level}; a further "
                  "confirmation would strengthen it.", factors, "confirmation / validation test")

    # nothing left to test.
    if nothing_left:
        if conf_level in _CONFIDENT_LEVELS or sat_status == "saturated":
            return _r(cid, objective, CampaignOpportunity.NOT_WORTH_FURTHER_WORK, False,
                      f"No legal experiment remains and evidence is saturated (confidence "
                      f"{conf_level}) - further work is not worthwhile.", factors, "none")
        return _r(cid, objective, CampaignOpportunity.KNOWLEDGE_PLATEAU, False,
                  f"No legal experiment remains yet the objective is unresolved (confidence "
                  f"{conf_level}) - knowledge has plateaued; a new idea/experiment is needed "
                  "before more testing helps.", factors, "new hypothesis required")

    # experiments remain but none of the specific triggers fired -> generic worthwhile confirm.
    if remaining_untested > 0:
        return _r(cid, objective, CampaignOpportunity.WORTH_ANOTHER_CONFIRMATION, True,
                  f"Legal experiment(s) remain and confidence is {conf_level}; further testing "
                  "can still add knowledge.", factors, "confirmation / validation test")

    return _r(cid, objective, CampaignOpportunity.UNKNOWN, False,
              "Opportunity could not be classified from the available signals.", factors,
              "none")


def _r(cid, objective, opp: CampaignOpportunity, worthwhile, reason, factors,
       focus) -> CampaignOpportunityResult:
    return CampaignOpportunityResult(
        campaign_id=cid, objective=objective, opportunity=opp.value, worthwhile=worthwhile,
        reason=reason, factors=factors, recommended_focus=focus)


def opportunity_versions() -> dict:
    return {"campaign_opportunity": CAMPAIGN_OPPORTUNITY_VERSION}
