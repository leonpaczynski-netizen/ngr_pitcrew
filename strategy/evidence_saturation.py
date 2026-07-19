"""Evidence Saturation — when is further testing no longer worthwhile? (Program 2, Phase 19).

A deterministic, ADVISORY-ONLY assessment layered on a Phase-18 engineering campaign. It
answers "how much more is there to learn here?" by reading the campaign's existing outcome
tallies and experiment states (from Phase-17/18) and reporting a saturation status with a
FULLY VISIBLE set of signals and thresholds — no hidden numbers.

Saturation is INDEPENDENT of campaign status: a SATURATED campaign may still be ACTIVE,
VALIDATION_REQUIRED, READY_TO_FREEZE, etc. It NEVER completes, freezes, ranks, mutates or
recommends anything — it only measures remaining information value.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock;
deterministic; never raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Tuple

EVIDENCE_SATURATION_VERSION = "evidence_saturation_v1"

# All thresholds are VISIBLE constants (exposed on every result) — no magic numbers.
CONFIRMATIONS_FOR_STRONG = 1        # >=1 confirmed direction -> evidence is strong
CONFIRMATIONS_FOR_SATURATED = 2     # >=2 confirmations -> the direction is proven
OVERTESTED_REPEATS = 3              # >=3 of the same result with nothing left -> over-tested
EXECUTED_FOR_BUILDING = 2           # >=2 executed experiments -> building evidence


class EvidenceSaturation(str, Enum):
    NOT_STARTED = "not_started"
    EARLY = "early"
    BUILDING = "building"
    STRONG = "strong"
    SATURATED = "saturated"
    OVERTESTED = "overtested"


@dataclass(frozen=True)
class SaturationResult:
    status: str
    signals: dict                       # every count, individually visible
    thresholds: dict                    # the visible decision thresholds
    information_gain_remaining: str      # high / moderate / low / none
    reasons: Tuple[str, ...]
    eval_version: str = EVIDENCE_SATURATION_VERSION

    def to_dict(self) -> dict:
        return {"status": self.status, "signals": dict(self.signals),
                "thresholds": dict(self.thresholds),
                "information_gain_remaining": self.information_gain_remaining,
                "reasons": list(self.reasons), "eval_version": self.eval_version}


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


def _int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _signals(campaign: Mapping) -> dict:
    prog = campaign.get("progress")
    prog = prog if isinstance(prog, Mapping) else {}
    exps = [e for e in (campaign.get("experiments") or []) if isinstance(e, Mapping)]
    confirmations = _int(prog.get("confirmed_improvement"))
    partial = _int(prog.get("partial_improvement"))
    regressions = _int(prog.get("regressions"))
    no_change = _int(prog.get("inconclusive"))
    executed = confirmations + partial + regressions + no_change
    remaining_untested = sum(
        1 for e in exps if _lc(e.get("campaign_role")) != "retired"
        and _lc(e.get("outcome_state")) == "not_tested")
    remaining_discriminators = sum(
        1 for e in exps if _lc(e.get("campaign_role")) == "primary_discriminator"
        and _lc(e.get("outcome_state")) == "not_tested")
    remaining_hypotheses = sum(
        1 for e in exps if _lc(e.get("campaign_role")) != "retired"
        and bool(e.get("needs_further_testing")))
    retired = sum(1 for e in exps if _lc(e.get("campaign_role")) == "retired"
                  or e.get("retirement_state"))
    conflicting = confirmations > 0 and regressions > 0
    unresolved_mechanisms = _int(prog.get("unresolved_mechanisms"))
    return {
        "confirmations": confirmations, "partial_improvements": partial,
        "regressions": regressions, "no_change": no_change, "executed": executed,
        "remaining_untested_experiments": remaining_untested,
        "remaining_discriminating_experiments": remaining_discriminators,
        "remaining_hypotheses": remaining_hypotheses, "retired_experiments": retired,
        "conflicting_evidence": conflicting, "unresolved_mechanisms": unresolved_mechanisms,
        "total_experiments": len(exps),
    }


_THRESHOLDS = {
    "confirmations_for_strong": CONFIRMATIONS_FOR_STRONG,
    "confirmations_for_saturated": CONFIRMATIONS_FOR_SATURATED,
    "overtested_repeats": OVERTESTED_REPEATS,
    "executed_for_building": EXECUTED_FOR_BUILDING,
}


def assess_saturation(campaign: Mapping) -> SaturationResult:
    """Deterministic saturation assessment for ONE Phase-18 campaign. Every signal and
    threshold is visible; every status explains why. Advisory only; mutates nothing."""
    campaign = campaign if isinstance(campaign, Mapping) else {}
    s = _signals(campaign)
    reasons = []

    remaining = s["remaining_untested_experiments"] + s["remaining_hypotheses"]
    nothing_left = (s["remaining_untested_experiments"] == 0
                    and s["remaining_hypotheses"] == 0)
    repeats = max(s["confirmations"], s["regressions"], s["no_change"])

    if s["executed"] == 0:
        status = EvidenceSaturation.NOT_STARTED
        reasons.append("no experiment for this objective has been executed yet")
    elif nothing_left and repeats >= OVERTESTED_REPEATS:
        status = EvidenceSaturation.OVERTESTED
        reasons.append(f"{repeats} repeated results of the same kind with no remaining "
                       f"experiment or hypothesis (>= {OVERTESTED_REPEATS}) - further testing "
                       f"adds little")
    elif nothing_left and s["conflicting_evidence"]:
        status = EvidenceSaturation.OVERTESTED
        reasons.append("conflicting evidence remains (both confirmed and regressed) with no "
                       "discriminating experiment left to resolve it")
    elif nothing_left:
        status = EvidenceSaturation.SATURATED
        reasons.append("no remaining legal / discriminating experiment or hypothesis - "
                       "information gain is near zero")
        if s["confirmations"] >= CONFIRMATIONS_FOR_SATURATED:
            reasons.append(f"the direction is confirmed ({s['confirmations']} times)")
    elif s["confirmations"] >= CONFIRMATIONS_FOR_STRONG \
            and s["remaining_discriminating_experiments"] == 0:
        status = EvidenceSaturation.STRONG
        reasons.append(f"a direction is confirmed ({s['confirmations']}) and no discriminating "
                       "test remains; mostly validation is left")
    elif s["executed"] >= EXECUTED_FOR_BUILDING:
        status = EvidenceSaturation.BUILDING
        reasons.append(f"{s['executed']} experiments executed with "
                       f"{remaining} still available - evidence is building")
    else:
        status = EvidenceSaturation.EARLY
        reasons.append("one experiment executed; substantial testing still remains")

    if s["conflicting_evidence"]:
        reasons.append("conflicting evidence present (both confirmed and regressed)")
    if s["unresolved_mechanisms"] > 0:
        reasons.append(f"{s['unresolved_mechanisms']} mechanism(s) still unresolved")

    if nothing_left:
        info = "none"
    elif s["remaining_discriminating_experiments"] >= 1:
        info = "high"
    elif s["remaining_untested_experiments"] >= 1:
        info = "moderate"
    else:
        info = "low"

    return SaturationResult(status=status.value, signals=s, thresholds=dict(_THRESHOLDS),
                            information_gain_remaining=info, reasons=tuple(reasons))
