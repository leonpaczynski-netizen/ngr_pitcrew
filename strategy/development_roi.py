"""Development ROI — engineering-knowledge return on a further test session (Program 2, Phase 20).

A deterministic, ADVISORY-ONLY estimate that answers, for ONE campaign: *if we spend another
test session here, how much engineering KNOWLEDGE could realistically be gained, at what cost,
and what risk remains?* It is about engineering knowledge — NOT lap time, NOT performance.

It REUSES existing measures verbatim: information gain from Phase 19 saturation, cost from the
Phase 19 cost model (already on each efficiency campaign), confidence from Phase 20's
knowledge-confidence layer, and prediction accuracy / contradictions from Phase 11 calibration
and Phase 18 progress. It recomputes none of them.

Critically this is **not an optimiser**: it computes per-campaign facts and ranks / prioritises
/ sorts NOTHING. It emits an `engineering_priority_reason` string (an explanation, not a
score-ordering). Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no
wall-clock; deterministic; never raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Mapping, Optional, Tuple

DEVELOPMENT_ROI_VERSION = "development_roi_v1"

# Visible mapping of the (already-computed) qualitative information-gain to a 0..1 magnitude.
INFO_GAIN_SCALE = {"high": 1.0, "moderate": 0.66, "low": 0.33, "none": 0.0}
# A campaign with no still-testable experiment cannot yield a further session's knowledge.
NO_TESTABLE_SESSION_VALUE = 0.0


@dataclass(frozen=True)
class DevelopmentROI:
    campaign_id: str
    objective: str
    expected_information_gain: float      # 0..1 (from Phase 19 saturation; not recomputed)
    expected_confidence_gain: float       # 0..1 (headroom bounded by testability)
    knowledge_gap: float                  # 0..1 (1 - overall confidence)
    estimated_session_value: float        # 0..1 (info gain gated by testability)
    cost_to_close_gap: dict               # laps / tyres / minutes (from Phase 19 cost model)
    remaining_risk: str                   # none / low / moderate / high (explained)
    testable: bool
    engineering_priority_reason: str      # explanation only — NOT a ranking
    inputs: dict                          # every raw input, visible
    eval_version: str = DEVELOPMENT_ROI_VERSION

    def to_dict(self) -> dict:
        return {"campaign_id": self.campaign_id, "objective": self.objective,
                "expected_information_gain": self.expected_information_gain,
                "expected_confidence_gain": self.expected_confidence_gain,
                "knowledge_gap": self.knowledge_gap,
                "estimated_session_value": self.estimated_session_value,
                "cost_to_close_gap": dict(self.cost_to_close_gap),
                "remaining_risk": self.remaining_risk, "testable": self.testable,
                "engineering_priority_reason": self.engineering_priority_reason,
                "inputs": dict(self.inputs), "eval_version": self.eval_version}


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


def _round(v) -> float:
    return round(float(v), 4)


def estimate_campaign_roi(campaign_efficiency: Mapping,
                          confidence: Mapping,
                          calibration: Optional[Mapping] = None) -> DevelopmentROI:
    """Deterministic ROI estimate for ONE Phase-19 efficiency campaign, given its Phase-20
    confidence assessment (+ context calibration). Reuses existing measures; recomputes none.
    Advisory only; ranks nothing; never raises."""
    campaign_efficiency = campaign_efficiency if isinstance(campaign_efficiency, Mapping) else {}
    confidence = confidence if isinstance(confidence, Mapping) else {}
    calibration = calibration if isinstance(calibration, Mapping) else {}

    cid = str(campaign_efficiency.get("campaign_id") or "")
    objective = str(campaign_efficiency.get("objective") or "")
    sat = campaign_efficiency.get("saturation") or {}
    sig = (sat.get("signals") or {}) if isinstance(sat, Mapping) else {}

    ig_label = str(campaign_efficiency.get("remaining_information_gain")
                   or (sat.get("information_gain_remaining") if isinstance(sat, Mapping) else "")
                   or "")
    expected_information_gain = _round(INFO_GAIN_SCALE.get(ig_label, 0.0))

    # still-testable? reuse the Phase-19 signals (never re-derive).
    remaining_untested = _int(sig.get("remaining_untested_experiments"))
    remaining_discriminating = _int(sig.get("remaining_discriminating_experiments"))
    testable = remaining_untested > 0

    # knowledge gap = 1 - overall confidence (unknown confidence -> full gap).
    overall_score = confidence.get("overall_score")
    conf_score = _num(overall_score, 0.0) if overall_score is not None else 0.0
    knowledge_gap = _round(max(0.0, 1.0 - conf_score))

    # expected confidence gain = the gap we could realistically close THIS session, bounded by
    # whether a legal experiment remains (no experiment -> no gain). Discriminating tests close
    # more of the gap than a plain validation re-run.
    if not testable:
        expected_confidence_gain = 0.0
    elif remaining_discriminating > 0:
        expected_confidence_gain = knowledge_gap
    else:
        expected_confidence_gain = _round(knowledge_gap * 0.5)

    # estimated session value = the information a further session could yield, gated by
    # testability. NOT lap time; NOT a ranking — a per-campaign 0..1 magnitude.
    estimated_session_value = (_round(expected_information_gain) if testable
                               else NO_TESTABLE_SESSION_VALUE)

    cost_to_close_gap = _cost_of_remaining(campaign_efficiency)
    remaining_risk, risk_reason = _remaining_risk(sig, calibration)

    reason = _priority_reason(testable, expected_information_gain, knowledge_gap,
                              remaining_discriminating, remaining_risk, risk_reason,
                              str(confidence.get("overall_level") or "unknown"))

    inputs = {
        "information_gain_remaining": ig_label or "unknown",
        "overall_confidence_level": str(confidence.get("overall_level") or "unknown"),
        "overall_confidence_score": overall_score,
        "remaining_untested_experiments": remaining_untested,
        "remaining_discriminating_experiments": remaining_discriminating,
        "regressions": _int(sig.get("regressions")),
        "conflicting_evidence": bool(sig.get("conflicting_evidence")),
        "unresolved_mechanisms": _int(sig.get("unresolved_mechanisms")),
        "elevated_risk_regressions": _int(calibration.get("elevated_risk_regressions")),
    }

    return DevelopmentROI(
        campaign_id=cid, objective=objective,
        expected_information_gain=expected_information_gain,
        expected_confidence_gain=_round(expected_confidence_gain),
        knowledge_gap=knowledge_gap, estimated_session_value=estimated_session_value,
        cost_to_close_gap=cost_to_close_gap, remaining_risk=remaining_risk, testable=testable,
        engineering_priority_reason=reason, inputs=inputs)


def _cost_of_remaining(campaign_efficiency: Mapping) -> dict:
    """Reuse the Phase-19 per-campaign remaining-cost totals verbatim (no recompute)."""
    return {
        "laps": _int(campaign_efficiency.get("estimated_remaining_laps")),
        "tyre_sets": _round(_num(campaign_efficiency.get("estimated_remaining_tyre_sets"))),
        "time_minutes": _round(_num(campaign_efficiency.get("estimated_remaining_time_minutes"))),
        "source": "Phase 19 engineering cost model",
    }


def _remaining_risk(sig: Mapping, calibration: Mapping) -> Tuple[str, str]:
    regressions = _int(sig.get("regressions"))
    conflicting = bool(sig.get("conflicting_evidence"))
    unresolved = _int(sig.get("unresolved_mechanisms"))
    elevated = _int(calibration.get("elevated_risk_regressions"))
    if conflicting or elevated > 0:
        return "high", ("unresolved conflicting evidence" if conflicting
                        else f"{elevated} elevated-risk regression(s) in calibration history")
    if regressions > 0:
        return "moderate", f"{regressions} recorded regression(s)"
    if unresolved > 0:
        return "low", f"{unresolved} unresolved mechanism(s)"
    return "none", "no recorded regression / conflict / unresolved mechanism"


def _priority_reason(testable, info_gain, gap, discriminating, risk, risk_reason,
                     conf_level) -> str:
    if not testable:
        return ("No still-testable experiment remains; a further session cannot add "
                "engineering knowledge here (not a ranking - a statement of testability).")
    parts = [f"confidence is {conf_level} (knowledge gap {gap})",
             f"remaining information gain {info_gain}"]
    if discriminating > 0:
        parts.append(f"{discriminating} discriminating test(s) available to resolve it")
    if risk != "none":
        parts.append(f"remaining risk {risk} ({risk_reason})")
    return ("A further session could close part of the gap: " + "; ".join(parts)
            + ". Advisory only - this ranks nothing and prioritises nothing automatically.")


def roi_versions() -> dict:
    return {"development_roi": DEVELOPMENT_ROI_VERSION}
