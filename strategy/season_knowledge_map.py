"""Season Knowledge Map — engineering progress per campaign across the programme (Phase 21).

A deterministic, READ-ONLY classification of *how well understood* each campaign's engineering
question is, aggregated from existing measures only: Phase-18 status, Phase-19 saturation and
Phase-20 confidence / opportunity. It is a map, not a plan - it schedules, ranks, prioritises
and decides NOTHING.

Every state carries a visible reason and the authority (source) it came from. Purity: Qt-free,
DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic; never raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Tuple

SEASON_KNOWLEDGE_MAP_VERSION = "season_knowledge_map_v1"

# Confidence levels (Phase 20) treated as "confident".
_CONFIDENT = ("high", "very_high")


class SeasonKnowledgeState(str, Enum):
    ENGINEERING_COMPLETE = "engineering_complete"
    WELL_UNDERSTOOD = "well_understood"
    EMERGING_CONFIDENCE = "emerging_confidence"
    NEEDS_CONFIRMATION = "needs_confirmation"
    CONTRADICTORY = "contradictory"
    LITTLE_EVIDENCE = "little_evidence"
    NO_USEFUL_EXPERIMENTS = "no_useful_experiments"
    KNOWLEDGE_PLATEAU = "knowledge_plateau"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CampaignKnowledgeState:
    campaign_id: str
    objective: str
    state: str
    reason: str
    source: str
    factors: dict
    eval_version: str = SEASON_KNOWLEDGE_MAP_VERSION

    def to_dict(self) -> dict:
        return {"campaign_id": self.campaign_id, "objective": self.objective,
                "state": self.state, "reason": self.reason, "source": self.source,
                "factors": dict(self.factors), "eval_version": self.eval_version}


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


def _int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def classify_campaign_knowledge(record: Mapping) -> CampaignKnowledgeState:
    """Classify ONE normalised season-campaign record into a knowledge state. Deterministic
    ladder over Phase-18/19/20 measures; every branch is explained. Never raises."""
    r = record if isinstance(record, Mapping) else {}
    cid = str(r.get("campaign_id") or "")
    objective = str(r.get("objective") or "")
    opportunity = _lc(r.get("opportunity"))
    confidence = _lc(r.get("confidence_level"))
    conflicting = bool(r.get("conflicting"))
    executed = _int(r.get("executed"))
    confirmations = _int(r.get("confirmations"))
    testable = bool(r.get("testable"))

    factors = {"campaign_status": _lc(r.get("status")), "opportunity": opportunity,
               "confidence_level": confidence, "conflicting_evidence": conflicting,
               "executed": executed, "confirmations": confirmations, "testable": testable}

    def _s(state: SeasonKnowledgeState, reason: str, source: str) -> CampaignKnowledgeState:
        return CampaignKnowledgeState(campaign_id=cid, objective=objective, state=state.value,
                                      reason=reason, source=source, factors=factors)

    if opportunity == "complete":
        return _s(SeasonKnowledgeState.ENGINEERING_COMPLETE,
                  "Phase 18 marks this campaign COMPLETED - the engineering question is answered.",
                  "Phase 18 campaign completion")
    if conflicting or opportunity == "worth_contradiction_testing":
        return _s(SeasonKnowledgeState.CONTRADICTORY,
                  "the evidence conflicts (both confirmed and regressed) - the conclusion is "
                  "not yet trustworthy.", "Phase 19 saturation + Phase 20 opportunity")
    if opportunity == "knowledge_plateau":
        return _s(SeasonKnowledgeState.KNOWLEDGE_PLATEAU,
                  "no legal experiment remains yet the objective is unresolved - knowledge has "
                  "plateaued.", "Phase 20 campaign opportunity")
    if opportunity == "evidence_exhausted":
        return _s(SeasonKnowledgeState.NO_USEFUL_EXPERIMENTS,
                  "the evidence is over-tested - no useful experiment remains here.",
                  "Phase 19 saturation (over-tested)")
    if confidence in _CONFIDENT:
        return _s(SeasonKnowledgeState.WELL_UNDERSTOOD,
                  f"confidence is {confidence} - the direction is confirmed and trustworthy.",
                  "Phase 20 knowledge confidence")
    if not testable and opportunity == "not_worth_further_work":
        return _s(SeasonKnowledgeState.NO_USEFUL_EXPERIMENTS,
                  "no legal experiment remains and the evidence is saturated.",
                  "Phase 19 saturation + Phase 20 opportunity")
    if confidence == "medium":
        if opportunity == "worth_another_confirmation":
            return _s(SeasonKnowledgeState.NEEDS_CONFIRMATION,
                      "a direction is confirmed once but not yet repeated - one more "
                      "confirmation is warranted.", "Phase 20 confidence + opportunity")
        return _s(SeasonKnowledgeState.EMERGING_CONFIDENCE,
                  "confidence is medium and evidence is accumulating.",
                  "Phase 20 knowledge confidence")
    if executed == 0:
        return _s(SeasonKnowledgeState.LITTLE_EVIDENCE,
                  "no experiment has been executed for this objective yet.",
                  "Phase 18 progress (no executed evidence)")
    if confidence in ("unknown", "very_low"):
        return _s(SeasonKnowledgeState.LITTLE_EVIDENCE,
                  f"confidence is {confidence} - too little trustworthy evidence so far.",
                  "Phase 20 knowledge confidence")
    if confidence == "low":
        return _s(SeasonKnowledgeState.NEEDS_CONFIRMATION,
                  "confidence is low - more confirmation is needed before trusting the "
                  "direction.", "Phase 20 knowledge confidence")
    return _s(SeasonKnowledgeState.UNKNOWN,
              "the knowledge state could not be classified from the available measures.",
              "Phase 20 knowledge quality")


def knowledge_versions() -> dict:
    return {"season_knowledge_map": SEASON_KNOWLEDGE_MAP_VERSION}
