"""Assumption Impact — how an assumption limits reliance (Program 2, Phase 30).

An assumption can only LIMIT how far a conclusion may be relied upon - it can block reliance, cap
readiness, narrow scope, weaken confidence, or be merely informational. It can NEVER create or raise
readiness: there is no positive impact. The impact ladder is deterministic and visible.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic.
"""
from __future__ import annotations

from enum import Enum

ASSUMPTION_IMPACT_VERSION = "assumption_impact_v1"


class AssumptionImpact(str, Enum):
    BLOCKS_RELIANCE = "blocks_reliance"        # if the assumption is false, the conclusion is unusable
    CAPS_READINESS = "caps_readiness"          # limits how ready the knowledge can be
    NARROWS_SCOPE = "narrows_scope"            # limits where the knowledge applies
    WEAKENS_CONFIDENCE = "weakens_confidence"  # lowers certainty
    INFORMATIONAL = "informational"            # noted; little practical effect
    UNKNOWN = "unknown"


# lower = more limiting. All impacts are non-positive: an assumption never raises readiness.
ASSUMPTION_IMPACT_PRIORITY = {
    "blocks_reliance": 0, "caps_readiness": 1, "narrows_scope": 2, "weakens_confidence": 3,
    "informational": 4, "unknown": 5,
}

# the maximum readiness an assumption of each impact permits (an assumption can only cap, never lift).
IMPACT_READINESS_CAP = {
    "blocks_reliance": "not_ready",
    "caps_readiness": "ready_with_limitations",
    "narrows_scope": "context_bound_only",
    "weakens_confidence": "ready_with_limitations",
    "informational": "ready",
    "unknown": "ready_with_limitations",
}

_IMPACT_TEXT = {
    AssumptionImpact.BLOCKS_RELIANCE: "if this assumption is wrong, the conclusion cannot be relied "
                                      "upon at all",
    AssumptionImpact.CAPS_READINESS: "this caps how ready the knowledge can be until the assumption "
                                     "is verified",
    AssumptionImpact.NARROWS_SCOPE: "this narrows the knowledge to the context where it was actually "
                                    "observed",
    AssumptionImpact.WEAKENS_CONFIDENCE: "this lowers confidence in the conclusion",
    AssumptionImpact.INFORMATIONAL: "this is noted for transparency and has little practical effect",
    AssumptionImpact.UNKNOWN: "the effect of this assumption could not be determined",
}


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


def impact_text(impact) -> str:
    for i in AssumptionImpact:
        if i.value == _lc(impact):
            return _IMPACT_TEXT.get(i, i.value)
    return _lc(impact)


def readiness_cap(impact) -> str:
    return IMPACT_READINESS_CAP.get(_lc(impact), "ready_with_limitations")


def assumption_impact_versions() -> dict:
    return {"assumption_impact": ASSUMPTION_IMPACT_VERSION}
