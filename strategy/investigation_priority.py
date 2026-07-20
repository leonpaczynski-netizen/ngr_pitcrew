"""Investigation Priority — what to investigate first in a programme (Program 2, Phase 24).

A deterministic, READ-ONLY classification of what an engineer should investigate first when
beginning or continuing a programme. It is NOT an experiment scheduler and contains NO setup
values or executable actions - it classifies knowledge areas.

Every dimension, weight, cap and rationale is a VISIBLE CONSTANT. The category is decided by a
deterministic ladder (fully explainable); the engineering score is a transparent weighted mean
of the visible dimensions and is used only for stable ordering within a category.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; no ML /
optimisation; deterministic; never raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Mapping, Sequence, Tuple

INVESTIGATION_PRIORITY_VERSION = "investigation_priority_v1"


class InvestigationCategory(str, Enum):
    PROTECT_FIRST = "protect_first"
    RECOLLECT_EVIDENCE = "recollect_evidence"
    DO_NOT_REUSE = "do_not_reuse"
    VALIDATE_EARLY = "validate_early"
    CONTEXT_SPECIFIC = "context_specific"
    INVESTIGATE = "investigate"


# Category display / ordering priority (lower = shown first). VISIBLE constant.
CATEGORY_PRIORITY = {
    InvestigationCategory.PROTECT_FIRST.value: 0,
    InvestigationCategory.DO_NOT_REUSE.value: 1,
    InvestigationCategory.RECOLLECT_EVIDENCE.value: 2,
    InvestigationCategory.VALIDATE_EARLY.value: 3,
    InvestigationCategory.CONTEXT_SPECIFIC.value: 4,
    InvestigationCategory.INVESTIGATE.value: 5,
}

# VISIBLE dimension weights (all exposed on every result; equal-ish, no hidden black box).
DIMENSION_WEIGHTS = {
    "recurrence_across_programmes": 1.0,
    "maturity_of_supporting_knowledge": 1.0,
    "transfer_eligibility": 1.0,
    "remaining_uncertainty": 1.0,
    "masking_risk_of_confirmed_good": 1.5,      # elevated — protecting good behaviour matters most
    "known_negative_outcomes": 1.25,
    "context_similarity": 1.0,
    "importance_to_active_programme": 1.0,
    "evidence_gaps": 1.0,
    "version_compatibility": 1.0,
    "driver_relevance": 0.5,
}

_MATURITY_RANK = {"unknown": 0, "emerging": 1, "developing": 2, "established": 3, "mature": 4,
                  "complete": 5, "plateaued": 3}
_CONFIDENCE_RANK = {"unknown": 0, "very_low": 1, "low": 2, "medium": 3, "high": 4, "very_high": 5}
_TRANSFER_RANK = {"not_transferable": 0, "very_low": 1, "low": 2, "medium": 3, "high": 4,
                  "supported": 5}
_UNCERTAINTY_VALUE = {"high": 1.0, "moderate": 0.66, "low": 0.33, "none": 0.0}
_REUSABLE = ("high", "supported")


@dataclass(frozen=True)
class InvestigationPriority:
    domain: str
    category: str
    engineering_score: float
    dimensions: dict
    weights: dict
    caps_applied: Tuple[str, ...]
    rationale: str
    confirmed_good_at_risk: Tuple[dict, ...]
    masking_conflict: bool
    source_authorities: Tuple[str, ...]
    eval_version: str = INVESTIGATION_PRIORITY_VERSION

    def to_dict(self) -> dict:
        return {"domain": self.domain, "category": self.category,
                "engineering_score": self.engineering_score, "dimensions": dict(self.dimensions),
                "weights": dict(self.weights), "caps_applied": list(self.caps_applied),
                "rationale": self.rationale,
                "confirmed_good_at_risk": [dict(p) for p in self.confirmed_good_at_risk],
                "masking_conflict": self.masking_conflict,
                "source_authorities": list(self.source_authorities),
                "eval_version": self.eval_version}


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


def _int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _round(v) -> float:
    return round(float(v), 4)


def classify_priorities(domain_records: Sequence[Mapping]) -> Tuple[dict, ...]:
    """Classify each domain record's investigation priority. Deterministic ladder + visible
    weighted score. Never raises."""
    try:
        return tuple(_classify(r).to_dict()
                     for r in (domain_records or []) if isinstance(r, Mapping))
    except Exception:   # never raise into the caller
        return ()


def _dimensions(r: Mapping) -> dict:
    transfers = [t for t in (r.get("transfers") or []) if isinstance(t, Mapping)]
    levels = [_lc(t.get("transfer_level")) for t in transfers]
    reusable = sum(1 for lv in levels if lv in _REUSABLE)
    total_t = max(len(transfers), 1)
    best_rank = max((_TRANSFER_RANK.get(lv, 0) for lv in levels), default=0)
    rules_sat = [set(_lc(x) for x in (t.get("rules_satisfied") or [])) for t in transfers]
    version_ok = (sum(1 for s in rules_sat if "compatible_gt7_version" in s) / total_t
                  if rules_sat else 0.0)
    driver_ok = (sum(1 for s in rules_sat if "same_driver" in s) / total_t) if rules_sat else 0.0
    ctx_sim = (sum(len(s) for s in rules_sat) / (total_t * 7)) if rules_sat else 0.0
    confirmations = _int(r.get("confirmations"))
    return {
        "recurrence_across_programmes": _round(reusable / total_t),
        "maturity_of_supporting_knowledge": _round(_MATURITY_RANK.get(_lc(r.get("maturity")), 0) / 5),
        "transfer_eligibility": _round(best_rank / 5),
        "remaining_uncertainty": _round(_UNCERTAINTY_VALUE.get(
            _lc(r.get("remaining_uncertainty")), 0.5)),
        "masking_risk_of_confirmed_good": 1.0 if r.get("confirmed_good") else 0.0,
        "known_negative_outcomes": 1.0 if (_int(r.get("regressions")) > 0
                                           or r.get("conflicting")) else 0.0,
        "context_similarity": _round(ctx_sim),
        "importance_to_active_programme": 1.0 if r.get("established") else 0.5,
        "evidence_gaps": _round(1.0 - min(confirmations / 2.0, 1.0)),
        "version_compatibility": _round(version_ok),
        "driver_relevance": _round(driver_ok),
    }


def _classify(r: Mapping) -> InvestigationPriority:
    dims = _dimensions(r)
    score = _round(sum(dims[k] * DIMENSION_WEIGHTS[k] for k in dims)
                   / sum(DIMENSION_WEIGHTS.values()))
    domain = _lc(r.get("domain"))
    dcls = _lc(r.get("domain_transfer_class"))
    established = bool(r.get("established"))
    confirmed_good = bool(r.get("confirmed_good"))
    regressions = _int(r.get("regressions"))
    confirmations = _int(r.get("confirmations"))
    conflicting = bool(r.get("conflicting"))
    transfers = [t for t in (r.get("transfers") or []) if isinstance(t, Mapping)]
    has_reusable = any(_lc(t.get("transfer_level")) in _REUSABLE for t in transfers)
    version_capped = (transfers and all("compatible_gt7_version"
                                        not in set(_lc(x) for x in (t.get("rules_satisfied") or []))
                                        for t in transfers))

    caps: List[str] = []
    at_risk: Tuple[dict, ...] = ()
    masking = False

    # deterministic ladder (each branch is explained).
    if confirmed_good:
        cat = InvestigationCategory.PROTECT_FIRST
        at_risk = ({"behaviour": f"confirmed '{domain}' behaviour", "confidence": _lc(r.get("confidence")),
                    "supporting_campaigns": list(r.get("supporting_campaigns") or []),
                    "source": "Phase 22 knowledge graph"},)
        if regressions > 0:
            masking = True
            caps.append("a harmful direction exists in this confirmed-good domain - protect the "
                        "good behaviour and mark the damaging direction explicitly")
        rationale = ("confirmed-good behaviour - protect it first; any related investigation must "
                     "preserve it.")
    elif regressions > 0 and confirmations == 0:
        cat = InvestigationCategory.DO_NOT_REUSE
        rationale = ("a historically harmful direction with no offsetting confirmation - do not "
                     "reuse or repeat it.")
    elif conflicting:
        cat = InvestigationCategory.RECOLLECT_EVIDENCE
        rationale = ("contradictory evidence - certainty is reduced; the evidence must be "
                     "re-collected rather than reused.")
    elif not established:
        cat = InvestigationCategory.INVESTIGATE
        rationale = ("knowledge here is not yet established - investigate to build evidence "
                     "(nothing to reuse yet).")
    elif established and has_reusable:
        cat = InvestigationCategory.VALIDATE_EARLY
        rationale = ("established and transfer-eligible - validate it early in the target before "
                     "relying on it (it is a hypothesis, not a setup to copy).")
    elif established and dcls in ("context_bound", "car_track_specific", "driver_specific"):
        cat = InvestigationCategory.CONTEXT_SPECIFIC
        rationale = (f"established but {dcls.replace('_', ' ')} - it does not transfer; treat as "
                     "context-specific knowledge.")
    elif established and version_capped:
        cat = InvestigationCategory.RECOLLECT_EVIDENCE
        caps.append("transfer capped by GT7 version difference - recollect evidence in the "
                    "target version")
        rationale = "established but only a different-version target exists - recollect evidence."
    else:
        cat = InvestigationCategory.INVESTIGATE
        rationale = "established knowledge with no compatible reuse target - continue investigating."

    return InvestigationPriority(
        domain=domain, category=cat.value, engineering_score=score, dimensions=dims,
        weights=dict(DIMENSION_WEIGHTS), caps_applied=tuple(caps), rationale=rationale,
        confirmed_good_at_risk=at_risk, masking_conflict=masking,
        source_authorities=("Phase 22 knowledge graph", "Phase 23 transfer eligibility"))


def priority_versions() -> dict:
    return {"investigation_priority": INVESTIGATION_PRIORITY_VERSION}
