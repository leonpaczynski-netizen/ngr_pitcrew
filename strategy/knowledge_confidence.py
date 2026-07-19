"""Confidence-Weighted Knowledge Quality (Program 2, Phase 20).

A deterministic, ADVISORY-ONLY assessment of *how trustworthy* a campaign's engineering
conclusions actually are. Phase 18 says "3 improved, 2 failed"; Phase 19 says "how saturated";
this layer says "how much confidence do we really have, and how much uncertainty remains?".

Every component score carries a **reason**, a **source** (which existing authority it came
from) and a **calculation** (the exact visible formula / threshold used). Every threshold is a
named constant — no hidden maths, no weighting black box (the overall score is the equal-
weighted mean of the *included* components, and the weight [1.0 each] is stated).

It measures; it decides nothing. It never completes/freezes a campaign, re-ranks, applies a
setup, mutates evidence, or invents data. Purity: Qt-free, DB-free, UI-free, network-free,
AI-free; no random, no wall-clock; deterministic; never raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Mapping, Optional, Tuple

KNOWLEDGE_CONFIDENCE_VERSION = "knowledge_confidence_v1"

# --------------------------------------------------------------------------- #
# Visible thresholds — every decision number is a named constant.
# --------------------------------------------------------------------------- #
MIN_CONFIRMATIONS_MEDIUM = 1        # >=1 confirmation -> some positive evidence
MIN_CONFIRMATIONS_HIGH = 2          # >=2 confirmations -> strong positive evidence
MIN_REPEATABILITY = 2               # the same direction confirmed >=2 times = repeatable
MAX_ALLOWED_CONTRADICTIONS = 0      # >0 contradictions blocks the top confidence band
CONTRADICTION_FULL_PENALTY = 2      # this many regressions drives the contradiction score to 0
MECHANISM_FULL_PENALTY = 2          # this many unresolved mechanisms drives support to 0
MIN_PREDICTION_ACCURACY_HIGH = 0.70  # calibration accuracy considered trustworthy
CONF_BAND_VERY_HIGH = 0.85
CONF_BAND_HIGH = 0.70
CONF_BAND_MEDIUM = 0.50
CONF_BAND_LOW = 0.30

_THRESHOLDS = {
    "min_confirmations_medium": MIN_CONFIRMATIONS_MEDIUM,
    "min_confirmations_high": MIN_CONFIRMATIONS_HIGH,
    "min_repeatability": MIN_REPEATABILITY,
    "max_allowed_contradictions": MAX_ALLOWED_CONTRADICTIONS,
    "contradiction_full_penalty": CONTRADICTION_FULL_PENALTY,
    "mechanism_full_penalty": MECHANISM_FULL_PENALTY,
    "min_prediction_accuracy_high": MIN_PREDICTION_ACCURACY_HIGH,
    "band_very_high": CONF_BAND_VERY_HIGH, "band_high": CONF_BAND_HIGH,
    "band_medium": CONF_BAND_MEDIUM, "band_low": CONF_BAND_LOW,
}


class ConfidenceLevel(str, Enum):
    UNKNOWN = "unknown"
    VERY_LOW = "very_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


# Ordered weakest -> strongest for deterministic capping (min of band vs cap).
_ORDER = [ConfidenceLevel.UNKNOWN, ConfidenceLevel.VERY_LOW, ConfidenceLevel.LOW,
          ConfidenceLevel.MEDIUM, ConfidenceLevel.HIGH, ConfidenceLevel.VERY_HIGH]


def _min_level(a: ConfidenceLevel, b: ConfidenceLevel) -> ConfidenceLevel:
    return a if _ORDER.index(a) <= _ORDER.index(b) else b


@dataclass(frozen=True)
class ConfidenceComponent:
    name: str
    score: Optional[float]              # 0..1, or None when genuinely unknown
    label: str
    included_in_overall: bool
    reason: str
    source: str
    calculation: str

    def to_dict(self) -> dict:
        return {"name": self.name, "score": self.score, "label": self.label,
                "included_in_overall": self.included_in_overall, "reason": self.reason,
                "source": self.source, "calculation": self.calculation}


@dataclass(frozen=True)
class KnowledgeConfidence:
    campaign_id: str
    overall_level: str
    overall_score: Optional[float]
    components: Tuple[ConfidenceComponent, ...]
    caps_applied: Tuple[str, ...]
    reasons: Tuple[str, ...]
    thresholds: dict
    eval_version: str = KNOWLEDGE_CONFIDENCE_VERSION

    def to_dict(self) -> dict:
        return {"campaign_id": self.campaign_id, "overall_level": self.overall_level,
                "overall_score": self.overall_score,
                "components": [c.to_dict() for c in self.components],
                "caps_applied": list(self.caps_applied), "reasons": list(self.reasons),
                "thresholds": dict(self.thresholds), "eval_version": self.eval_version}

    def component(self, name: str) -> Optional[ConfidenceComponent]:
        return next((c for c in self.components if c.name == name), None)


def _num(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _clamp01(v: float) -> float:
    return round(max(0.0, min(1.0, v)), 4)


def _signals(campaign_efficiency: Mapping) -> dict:
    """Read the per-campaign evidence signals produced by Phase 19 (saturation.signals),
    which are themselves a projection of the Phase-18 campaign progress. Never re-derives."""
    sat = campaign_efficiency.get("saturation")
    sat = sat if isinstance(sat, Mapping) else {}
    sig = sat.get("signals")
    sig = sig if isinstance(sig, Mapping) else {}
    return {
        "confirmations": _int(sig.get("confirmations")),
        "partial": _int(sig.get("partial_improvements")),
        "regressions": _int(sig.get("regressions")),
        "no_change": _int(sig.get("no_change")),
        "executed": _int(sig.get("executed")),
        "conflicting": bool(sig.get("conflicting_evidence")),
        "unresolved_mechanisms": _int(sig.get("unresolved_mechanisms")),
        "remaining_untested": _int(sig.get("remaining_untested_experiments")),
        "remaining_discriminating": _int(sig.get("remaining_discriminating_experiments")),
        "saturation_status": str(sat.get("status") or ""),
        "information_gain_remaining": str(
            campaign_efficiency.get("remaining_information_gain")
            or sat.get("information_gain_remaining") or ""),
    }


def assess_campaign_confidence(campaign_efficiency: Mapping,
                               calibration: Optional[Mapping] = None) -> KnowledgeConfidence:
    """Deterministic confidence assessment for ONE Phase-19 efficiency campaign (+ the
    context-level Phase-11 prediction calibration). Every component is explained; the overall
    score is the equal-weighted mean of the included components. Advisory only; never raises."""
    campaign_efficiency = campaign_efficiency if isinstance(campaign_efficiency, Mapping) else {}
    calibration = calibration if isinstance(calibration, Mapping) else {}
    cid = str(campaign_efficiency.get("campaign_id") or "")
    s = _signals(campaign_efficiency)
    components: List[ConfidenceComponent] = []

    # 1. confirmation_strength — magnitude of positive evidence.
    cs = _clamp01(s["confirmations"] / MIN_CONFIRMATIONS_HIGH) if MIN_CONFIRMATIONS_HIGH else 0.0
    components.append(ConfidenceComponent(
        name="confirmation_strength", score=cs,
        label=("strong" if s["confirmations"] >= MIN_CONFIRMATIONS_HIGH else
               "some" if s["confirmations"] >= MIN_CONFIRMATIONS_MEDIUM else "none"),
        included_in_overall=True,
        reason=f"{s['confirmations']} confirmed improvement(s) recorded",
        source="Phase 18 campaign progress (via Phase 19 signals)",
        calculation=f"min(confirmations {s['confirmations']} / MIN_CONFIRMATIONS_HIGH "
                    f"{MIN_CONFIRMATIONS_HIGH}, 1.0)"))

    # 2. repeatability — was the SAME direction confirmed >= MIN_REPEATABILITY times?
    rep = _clamp01(s["confirmations"] / MIN_REPEATABILITY) if MIN_REPEATABILITY else 0.0
    components.append(ConfidenceComponent(
        name="repeatability", score=rep,
        label="repeatable" if s["confirmations"] >= MIN_REPEATABILITY else "not_yet_repeated",
        included_in_overall=True,
        reason=(f"direction confirmed {s['confirmations']} time(s); "
                f"{'meets' if s['confirmations'] >= MIN_REPEATABILITY else 'below'} the "
                f"repeatability threshold"),
        source="Phase 18 campaign progress (via Phase 19 signals)",
        calculation=f"min(confirmations {s['confirmations']} / MIN_REPEATABILITY "
                    f"{MIN_REPEATABILITY}, 1.0)"))

    # 3. contradiction_level — contribution FALLS as contradictions rise.
    contra_score = _clamp01(1.0 - s["regressions"] / CONTRADICTION_FULL_PENALTY) \
        if CONTRADICTION_FULL_PENALTY else (0.0 if s["regressions"] else 1.0)
    if s["conflicting"]:
        contra_score = min(contra_score, 0.5)
    components.append(ConfidenceComponent(
        name="contradiction_level", score=contra_score,
        label=("clean" if s["regressions"] == 0 and not s["conflicting"] else
               "conflicting" if s["conflicting"] else "some_contradiction"),
        included_in_overall=True,
        reason=(f"{s['regressions']} regression(s)"
                + ("; both confirmed and regressed (unresolved conflict)"
                   if s["conflicting"] else "")),
        source="Phase 18 campaign progress (via Phase 19 signals)",
        calculation=(f"max(0, 1 - regressions {s['regressions']} / CONTRADICTION_FULL_PENALTY "
                     f"{CONTRADICTION_FULL_PENALTY})"
                     + (" then capped at 0.5 (conflicting)" if s["conflicting"] else ""))))

    # 4. mechanism_support — unresolved mechanisms weaken the causal story.
    mech_score = _clamp01(1.0 - s["unresolved_mechanisms"] / MECHANISM_FULL_PENALTY) \
        if MECHANISM_FULL_PENALTY else (0.0 if s["unresolved_mechanisms"] else 1.0)
    components.append(ConfidenceComponent(
        name="mechanism_support", score=mech_score,
        label="explained" if s["unresolved_mechanisms"] == 0 else "partially_explained",
        included_in_overall=True,
        reason=f"{s['unresolved_mechanisms']} mechanism(s) still unresolved",
        source="Phase 13 mechanism annotation (via Phase 18 progress)",
        calculation=f"max(0, 1 - unresolved_mechanisms {s['unresolved_mechanisms']} / "
                    f"MECHANISM_FULL_PENALTY {MECHANISM_FULL_PENALTY})"))

    # 5. outcome_consistency — fraction of executed tests that pointed the same (positive) way.
    if s["executed"] > 0:
        oc = _clamp01((s["confirmations"] + 0.5 * s["partial"]) / s["executed"])
        oc_component = ConfidenceComponent(
            name="outcome_consistency", score=oc,
            label=("consistent" if oc >= 0.75 else "mixed" if oc >= 0.4 else "inconsistent"),
            included_in_overall=True,
            reason=f"{s['confirmations']} confirmed + {s['partial']} partial of "
                   f"{s['executed']} executed",
            source="Phase 3 outcome evaluation (via Phase 18 progress)",
            calculation=f"(confirmations {s['confirmations']} + 0.5*partial {s['partial']}) / "
                        f"executed {s['executed']}")
    else:
        oc_component = ConfidenceComponent(
            name="outcome_consistency", score=None, label="no_data",
            included_in_overall=False, reason="no experiment executed for this objective yet",
            source="Phase 3 outcome evaluation", calculation="undefined (executed == 0)")
    components.append(oc_component)

    # 6. prediction_accuracy — CONTEXT-level calibration; excluded when unknown so it neither
    #    inflates nor deflates confidence in the absence of reconciliations.
    recon = _int(calibration.get("reconciliations"))
    if recon > 0:
        pa = _clamp01(_num(calibration.get("overall_accuracy")))
        pa_component = ConfidenceComponent(
            name="prediction_accuracy", score=pa,
            label=("trustworthy" if pa >= MIN_PREDICTION_ACCURACY_HIGH else "developing"),
            included_in_overall=True,
            reason=f"context prediction accuracy {pa} over {recon} reconciliation(s)",
            source="Phase 11 prediction calibration (context-level)",
            calculation=f"mean overall_accuracy {pa} (>= MIN_PREDICTION_ACCURACY_HIGH "
                        f"{MIN_PREDICTION_ACCURACY_HIGH} = trustworthy)")
    else:
        pa_component = ConfidenceComponent(
            name="prediction_accuracy", score=None, label="unknown",
            included_in_overall=False,
            reason="no prediction-vs-outcome reconciliation recorded for this context",
            source="Phase 11 prediction calibration (context-level)",
            calculation="excluded from overall (reconciliations == 0)")
    components.append(pa_component)

    # 7. remaining_uncertainty — reported (feeds ROI); NOT folded into overall confidence,
    #    because uncertainty about *completeness* is not doubt about what is already confirmed.
    ru = _remaining_uncertainty_score(s)
    components.append(ConfidenceComponent(
        name="remaining_uncertainty", score=ru, label=_uncertainty_label(s),
        included_in_overall=False,
        reason=(f"information gain remaining: {s['information_gain_remaining'] or 'unknown'}; "
                f"{s['remaining_untested']} untested experiment(s)"),
        source="Phase 19 evidence saturation",
        calculation="reported for ROI; excluded from overall (completeness != correctness)"))

    # Overall = equal-weighted mean of the INCLUDED components (weight 1.0 each; stated).
    included = [c.score for c in components if c.included_in_overall and c.score is not None]
    reasons: List[str] = []
    caps: List[str] = []
    if not included or s["executed"] == 0:
        overall_score: Optional[float] = None
        level = ConfidenceLevel.UNKNOWN
        reasons.append("no executed evidence yet - confidence is UNKNOWN")
    else:
        overall_score = round(sum(included) / len(included), 4)
        level = _band(overall_score)
        reasons.append(f"equal-weighted mean of {len(included)} included component(s) "
                       f"(weight 1.0 each) = {overall_score}")
        # visible caps
        if s["conflicting"]:
            level = _min_level(level, ConfidenceLevel.LOW)
            caps.append("unresolved conflicting evidence caps confidence at LOW")
        if s["confirmations"] == 0 and s["regressions"] > 0:
            level = _min_level(level, ConfidenceLevel.VERY_LOW)
            caps.append("no confirmation with a recorded regression caps confidence at VERY_LOW")
        if s["confirmations"] < MIN_REPEATABILITY:
            # a single, unrepeated confirmation cannot be HIGH/VERY_HIGH confidence — this
            # mirrors the Phase-18 doctrine that one confirmation is VALIDATION_REQUIRED.
            level = _min_level(level, ConfidenceLevel.MEDIUM)
            caps.append(f"< MIN_REPEATABILITY ({MIN_REPEATABILITY}) confirmations caps "
                        f"confidence at MEDIUM (not yet repeated)")

    return KnowledgeConfidence(
        campaign_id=cid, overall_level=level.value, overall_score=overall_score,
        components=tuple(components), caps_applied=tuple(caps), reasons=tuple(reasons),
        thresholds=dict(_THRESHOLDS))


def _band(score: float) -> ConfidenceLevel:
    if score >= CONF_BAND_VERY_HIGH:
        return ConfidenceLevel.VERY_HIGH
    if score >= CONF_BAND_HIGH:
        return ConfidenceLevel.HIGH
    if score >= CONF_BAND_MEDIUM:
        return ConfidenceLevel.MEDIUM
    if score >= CONF_BAND_LOW:
        return ConfidenceLevel.LOW
    return ConfidenceLevel.VERY_LOW


def _remaining_uncertainty_score(s: Mapping) -> float:
    """A 0..1 measure of how much is still UNKNOWN (1.0 = a lot left to learn, 0.0 = nothing)."""
    ig = str(s.get("information_gain_remaining") or "")
    base = {"high": 1.0, "moderate": 0.66, "low": 0.33, "none": 0.0}.get(ig, 0.5)
    return round(base, 4)


def _uncertainty_label(s: Mapping) -> str:
    ig = str(s.get("information_gain_remaining") or "")
    return {"high": "high", "moderate": "moderate", "low": "low", "none": "resolved"}.get(
        ig, "unknown")


def knowledge_versions() -> dict:
    return {"knowledge_confidence": KNOWLEDGE_CONFIDENCE_VERSION}
