"""Engineering Knowledge Quality assembly (Program 2, Phase 20).

Composes the three Phase-20 layers — knowledge confidence, development ROI and campaign
opportunity — over a Phase-19 Engineering Efficiency view (+ Phase-11 prediction calibration)
into one read-only advisory. It reuses every underlying measure verbatim and adds no new
scoring of its own.

It preserves the campaign ORDER supplied by Phase 19; it ranks / sorts / prioritises NOTHING
(not an optimiser). It applies nothing, completes nothing, mutates nothing. Purity: Qt-free,
DB-free, UI-free, network-free, AI-free; no random, no wall-clock (dates are data);
deterministic; never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import List, Mapping, Optional, Sequence, Tuple

from strategy.knowledge_confidence import (
    KNOWLEDGE_CONFIDENCE_VERSION, assess_campaign_confidence,
)
from strategy.development_roi import DEVELOPMENT_ROI_VERSION, estimate_campaign_roi
from strategy.campaign_opportunity import (
    CAMPAIGN_OPPORTUNITY_VERSION, classify_campaign_opportunity,
)

KNOWLEDGE_QUALITY_VERSION = "knowledge_quality_v1"
KNOWLEDGE_QUALITY_SCHEMA = 1

_SAFETY = ("Read-only engineering knowledge-quality view. Confidence, development ROI and "
           "campaign opportunity are ADVISORY only - they measure trust and remaining "
           "engineering return; they rank, prioritise, complete, freeze, apply, create and "
           "execute NOTHING. Completion stays governed by Phase 18 and the frozen Apply gate "
           "remains the sole route to the car.")


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


@dataclass(frozen=True)
class EngineeringKnowledgeQuality:
    context_summary: dict
    campaigns: Tuple[dict, ...]         # one entry per campaign: confidence + roi + opportunity
    totals: dict
    safety_statement: str
    content_fingerprint: str
    knowledge_versions: dict
    schema_version: int = KNOWLEDGE_QUALITY_SCHEMA
    eval_version: str = KNOWLEDGE_QUALITY_VERSION

    def to_dict(self) -> dict:
        return {"context_summary": dict(self.context_summary),
                "campaigns": [dict(c) for c in self.campaigns], "totals": dict(self.totals),
                "safety_statement": self.safety_statement,
                "content_fingerprint": self.content_fingerprint,
                "knowledge_versions": dict(self.knowledge_versions),
                "schema_version": self.schema_version, "eval_version": self.eval_version}


def build_knowledge_quality(efficiency: Optional[Mapping], *,
                            calibration: Optional[Mapping] = None) -> EngineeringKnowledgeQuality:
    """Compose confidence + ROI + opportunity over the Phase-19 efficiency campaigns.
    Deterministic; preserves the incoming campaign order; ranks nothing; never raises."""
    try:
        return _build(efficiency or {}, (calibration or {}))
    except Exception as exc:   # never raise into the caller
        kv = knowledge_versions()
        return EngineeringKnowledgeQuality(
            context_summary={}, campaigns=(), totals={}, safety_statement=_SAFETY,
            content_fingerprint=_fp({"error": type(exc).__name__, "kv": kv}),
            knowledge_versions=kv)


def _build(efficiency: Mapping, calibration: Mapping) -> EngineeringKnowledgeQuality:
    cal = calibration.get("calibration") if isinstance(calibration, Mapping) else None
    cal = cal if isinstance(cal, Mapping) else (calibration if isinstance(calibration, Mapping)
                                                else {})
    eff_campaigns = list(efficiency.get("campaigns") or [])

    out: List[dict] = []
    level_counts: dict = {}
    worthwhile = 0
    opp_counts: dict = {}
    for ce in eff_campaigns:
        ce = ce if isinstance(ce, Mapping) else {}
        confidence = assess_campaign_confidence(ce, cal).to_dict()
        roi = estimate_campaign_roi(ce, confidence, cal).to_dict()
        opportunity = classify_campaign_opportunity(ce, confidence, roi).to_dict()
        lvl = confidence.get("overall_level") or "unknown"
        level_counts[lvl] = level_counts.get(lvl, 0) + 1
        opp = opportunity.get("opportunity") or "unknown"
        opp_counts[opp] = opp_counts.get(opp, 0) + 1
        if opportunity.get("worthwhile"):
            worthwhile += 1
        out.append({
            "campaign_id": _norm(ce.get("campaign_id")),
            "objective": _norm(ce.get("objective")),
            "status": _norm(ce.get("status")),
            "confidence": confidence, "roi": roi, "opportunity": opportunity,
        })

    totals = {
        "campaigns": len(out),
        "confidence_level_counts": level_counts,
        "opportunity_counts": opp_counts,
        "worthwhile_campaigns": worthwhile,
        "context_prediction_accuracy": (cal.get("overall_accuracy")
                                        if cal.get("reconciliations") else None),
    }
    kv = knowledge_versions()
    fp = _fp({"prog": _norm(efficiency.get("content_fingerprint")),
              "camps": [(c["campaign_id"], c["confidence"]["overall_level"],
                         c["confidence"]["overall_score"],
                         c["opportunity"]["opportunity"]) for c in out],
              "cal": [cal.get("reconciliations"), cal.get("overall_accuracy")], "kv": kv})
    return EngineeringKnowledgeQuality(
        context_summary=dict(efficiency.get("context_summary") or {}),
        campaigns=tuple(out), totals=totals, safety_statement=_SAFETY,
        content_fingerprint=fp, knowledge_versions=kv)


def knowledge_versions() -> dict:
    return {"knowledge_quality": KNOWLEDGE_QUALITY_VERSION,
            "knowledge_confidence": KNOWLEDGE_CONFIDENCE_VERSION,
            "development_roi": DEVELOPMENT_ROI_VERSION,
            "campaign_opportunity": CAMPAIGN_OPPORTUNITY_VERSION,
            "schema": KNOWLEDGE_QUALITY_SCHEMA}


def _fp(payload: dict) -> str:
    return (f"{KNOWLEDGE_QUALITY_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        default=str).encode()).hexdigest()[:24])
