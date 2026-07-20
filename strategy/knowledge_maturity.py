"""Knowledge Maturity — deterministic maturity of an engineering knowledge domain (Phase 22).

A deterministic, ADVISORY-ONLY classification of *how mature* the Engineering Brain's knowledge
of one domain is. It is determined ONLY from existing authorities (Phase-19 saturation, Phase-20
confidence, Phase-21 knowledge state) aggregated over the domain's contributing campaigns — it
invents no weighting and decides nothing.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; no graph or
network libraries; deterministic; never raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Tuple

KNOWLEDGE_MATURITY_VERSION = "knowledge_maturity_v1"

# Confidence levels (Phase 20) in ascending strength — used to pick the best-known confidence.
_CONF_ORDER = ("unknown", "very_low", "low", "medium", "high", "very_high")
_CONFIDENT = ("high", "very_high")

# Phase-21 knowledge states treated as terminal-understood / stuck.
_COMPLETE_STATES = ("engineering_complete",)
_PLATEAU_STATES = ("knowledge_plateau", "no_useful_experiments")


class KnowledgeMaturity(str, Enum):
    UNKNOWN = "unknown"
    EMERGING = "emerging"
    DEVELOPING = "developing"
    ESTABLISHED = "established"
    MATURE = "mature"
    COMPLETE = "complete"
    PLATEAUED = "plateaued"


@dataclass(frozen=True)
class MaturityResult:
    maturity: str
    reason: str
    source: str
    factors: dict
    eval_version: str = KNOWLEDGE_MATURITY_VERSION

    def to_dict(self) -> dict:
        return {"maturity": self.maturity, "reason": self.reason, "source": self.source,
                "factors": dict(self.factors), "eval_version": self.eval_version}


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


def _int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def best_confidence(levels) -> str:
    """The strongest confidence level present (best-known); 'unknown' if none."""
    best = "unknown"
    for lv in levels or []:
        lv = _lc(lv)
        if lv in _CONF_ORDER and _CONF_ORDER.index(lv) > _CONF_ORDER.index(best):
            best = lv
    return best


def classify_maturity(signals: Mapping) -> MaturityResult:
    """Classify ONE domain's aggregated evidence into a maturity level. Deterministic ladder
    over Phase-19/20/21 measures; every branch is explained. Never raises.

    Expected ``signals`` keys (all optional / defaulted):
      contributing_campaigns, executed_total, confirmations_total, regressions_total,
      conflicting_any, unresolved_total, testable_any, confidence_levels[list],
      knowledge_states[list].
    """
    s = signals if isinstance(signals, Mapping) else {}
    campaigns = _int(s.get("contributing_campaigns"))
    executed = _int(s.get("executed_total"))
    confirmations = _int(s.get("confirmations_total"))
    conflicting = bool(s.get("conflicting_any"))
    unresolved = _int(s.get("unresolved_total"))
    testable = bool(s.get("testable_any"))
    levels = list(s.get("confidence_levels") or [])
    states = [_lc(x) for x in (s.get("knowledge_states") or [])]
    best = best_confidence(levels)

    factors = {"contributing_campaigns": campaigns, "executed_total": executed,
               "confirmations_total": confirmations, "regressions_total":
               _int(s.get("regressions_total")), "conflicting_any": conflicting,
               "unresolved_total": unresolved, "testable_any": testable,
               "best_confidence": best, "knowledge_states": states}

    def _r(m: KnowledgeMaturity, reason: str) -> MaturityResult:
        return MaturityResult(maturity=m.value, reason=reason,
                              source="Phase 19 saturation + Phase 20 confidence + Phase 21 state",
                              factors=factors)

    if campaigns == 0 or executed == 0:
        return _r(KnowledgeMaturity.UNKNOWN,
                  "no campaign has produced executed evidence in this domain yet")

    if any(st in _COMPLETE_STATES for st in states) or (
            best == "very_high" and not testable and not conflicting):
        return _r(KnowledgeMaturity.COMPLETE,
                  "a confirmed, trustworthy conclusion with no useful experiment remaining")

    if any(st in _PLATEAU_STATES for st in states) and not testable:
        return _r(KnowledgeMaturity.PLATEAUED,
                  "no legal experiment remains yet the domain is unresolved - knowledge has "
                  "plateaued")

    if best in _CONFIDENT:
        return _r(KnowledgeMaturity.MATURE,
                  f"best confidence is {best}; the domain is well understood with refinement "
                  "remaining")

    if best == "medium" and confirmations >= 1:
        return _r(KnowledgeMaturity.ESTABLISHED,
                  "a direction is confirmed and confidence is building toward trustworthy")

    if executed >= 2:
        return _r(KnowledgeMaturity.DEVELOPING,
                  f"{executed} experiments executed but confidence is still {best}")

    if executed == 1:
        return _r(KnowledgeMaturity.EMERGING,
                  "a single experiment has been executed - knowledge is only emerging")

    return _r(KnowledgeMaturity.UNKNOWN,
              "maturity could not be classified from the available measures")


def maturity_versions() -> dict:
    return {"knowledge_maturity": KNOWLEDGE_MATURITY_VERSION}
