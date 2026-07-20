"""Knowledge Transfer — is established engineering KNOWLEDGE reusable in another context? (Ph 23).

A deterministic, ADVISORY-ONLY evaluation of whether a domain of engineering knowledge proven in
a SOURCE context is likely to be reusable in a TARGET context. It transfers NO setup values - it
reasons about knowledge (mechanisms, handling behaviour), gated by the visible transfer rules
(``transfer_rules``) and the domain's transferability class.

Every field carries a **reason / source / calculation**; the transfer level is decided ONLY by
the deterministic rules. Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no
wall-clock; no ML / optimisation; deterministic; never raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Mapping, Optional, Tuple

from strategy.transfer_rules import (
    TRANSFER_RULES_VERSION, car_attributes, evaluate_rules, domain_transfer_class,
    DOMAIN_CLASS_REASON,
)

KNOWLEDGE_TRANSFER_VERSION = "knowledge_transfer_v1"

# Source maturity (Phase 22) must reach at least this to be worth transferring.
_ESTABLISHED = ("established", "mature", "complete")
_STRONG_SOURCE = ("mature", "complete")


class TransferLevel(str, Enum):
    NOT_TRANSFERABLE = "not_transferable"
    VERY_LOW = "very_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    SUPPORTED = "supported"


@dataclass(frozen=True)
class KnowledgeTransferCandidate:
    source_context: dict
    target_context: dict
    engineering_domain: str
    knowledge_area: str
    transfer_level: str
    reason: str
    supporting_evidence: dict
    supporting_campaigns: Tuple[str, ...]
    supporting_mechanisms: Tuple[str, ...]
    confidence: dict
    limitations: Tuple[str, ...]
    rules_satisfied: Tuple[str, ...]
    eval_version: str = KNOWLEDGE_TRANSFER_VERSION

    def to_dict(self) -> dict:
        return {"source_context": dict(self.source_context),
                "target_context": dict(self.target_context),
                "engineering_domain": self.engineering_domain,
                "knowledge_area": self.knowledge_area, "transfer_level": self.transfer_level,
                "reason": self.reason, "supporting_evidence": dict(self.supporting_evidence),
                "supporting_campaigns": list(self.supporting_campaigns),
                "supporting_mechanisms": list(self.supporting_mechanisms),
                "confidence": dict(self.confidence), "limitations": list(self.limitations),
                "rules_satisfied": list(self.rules_satisfied),
                "eval_version": self.eval_version}


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


def evaluate_transfer(source_domain: Mapping, source_ctx: Mapping,
                      target_ctx: Mapping) -> KnowledgeTransferCandidate:
    """Evaluate the transfer of ONE established source domain of knowledge to ONE target context.
    Deterministic; the level is decided only by the visible rules + domain class. Never raises."""
    sd = source_domain if isinstance(source_domain, Mapping) else {}
    sc = dict(source_ctx or {})
    tc = dict(target_ctx or {})

    domain = _lc(sd.get("domain"))
    maturity = _lc((sd.get("maturity") or {}).get("value"))
    confidence_level = _lc((sd.get("confidence") or {}).get("value"))
    mechanisms = tuple(_lc(m) for m in (sd.get("supporting_mechanisms") or []) if _lc(m))
    campaigns = tuple(str(c) for c in (sd.get("supporting_campaigns") or []) if str(c))
    dom_class = domain_transfer_class(domain)

    src_attrs = car_attributes(sc.get("car"))
    tgt_attrs = car_attributes(tc.get("car"))
    rules = evaluate_rules(src_attrs, tgt_attrs, sc, tc)
    satisfied = tuple(rid for rid, ok in rules.items() if ok)

    level, reason, limitations = _decide(dom_class, domain, maturity, confidence_level,
                                         bool(mechanisms), rules, src_attrs, tgt_attrs, sc, tc)

    return KnowledgeTransferCandidate(
        source_context=_ctx_summary(sc, src_attrs), target_context=_ctx_summary(tc, tgt_attrs),
        engineering_domain=domain,
        knowledge_area=str((sd.get("knowledge_state") or {}).get("value") or domain),
        transfer_level=level.value, reason=reason,
        supporting_evidence={"source_maturity": maturity,
                             "source_confidence": confidence_level,
                             "domain_transfer_class": dom_class,
                             "rules_satisfied_count": len(satisfied),
                             "source": "Phase 22 knowledge graph + Phase 23 transfer rules"},
        supporting_campaigns=campaigns, supporting_mechanisms=mechanisms,
        confidence={"value": confidence_level,
                    "reason": "confidence of the source knowledge being transferred",
                    "source": "Phase 20 knowledge confidence (via Phase 22)",
                    "calculation": "reused verbatim from the source domain confidence"},
        limitations=tuple(limitations), rules_satisfied=satisfied)


def _decide(dom_class, domain, maturity, confidence, has_mech, rules, s_attrs, t_attrs,
            sc, tc):
    limitations: List[str] = []

    # 0. nothing established to transfer.
    if maturity not in _ESTABLISHED:
        return (TransferLevel.NOT_TRANSFERABLE,
                f"the source knowledge in '{domain}' is only {maturity or 'unknown'} - there is "
                "no established knowledge to transfer yet.",
                ["source knowledge not yet established (needs to reach at least ESTABLISHED)"])

    # 1. context-bound / driver-specific / car-track-specific domains.
    if dom_class == "context_bound":
        return (TransferLevel.NOT_TRANSFERABLE, DOMAIN_CLASS_REASON["context_bound"] + ".",
                ["track / event specific - not a cross-car property"])
    if dom_class == "driver_specific":
        if rules.get("same_driver"):
            lvl = _arch_level(dom_class, maturity, has_mech, rules)
            return (lvl, "driver-technique knowledge, transferring to the SAME driver: "
                    + _match_summary(rules), _arch_limits(rules, limitations))
        return (TransferLevel.NOT_TRANSFERABLE, DOMAIN_CLASS_REASON["driver_specific"] + ".",
                ["different driver - technique knowledge does not transfer"])
    if dom_class == "car_track_specific":
        # gearbox: only transfers when explicitly supported (shared mechanism + strong match).
        if has_mech and maturity in _STRONG_SOURCE and rules.get("same_manufacturer") \
                and rules.get("same_drivetrain") and rules.get("compatible_gt7_version"):
            return (TransferLevel.LOW,
                    "gearing knowledge is normally car/track specific, but a shared mechanism on "
                    "an architecturally identical car gives limited, explicitly-supported reuse: "
                    + _match_summary(rules),
                    ["gearing is car/track specific - reuse is limited even when supported"])
        return (TransferLevel.NOT_TRANSFERABLE, DOMAIN_CLASS_REASON["car_track_specific"] + ".",
                ["gearing / final-drive is car & track specific - not transferable without "
                 "explicit shared evidence"])

    # 2. version incompatibility caps everything low.
    if not rules.get("compatible_gt7_version"):
        limitations.append("different GT7 major version - physics / BOP may differ")
        if rules.get("same_manufacturer") or rules.get("same_drivetrain"):
            return (TransferLevel.VERY_LOW,
                    "some architectural similarity but a different GT7 major version undermines "
                    "transfer: " + _match_summary(rules), limitations)
        return (TransferLevel.NOT_TRANSFERABLE,
                "different GT7 major version and little architectural similarity: "
                + _match_summary(rules), limitations)

    # 3. architecture-dependent / handling-drivetrain domains.
    level = _arch_level(dom_class, maturity, has_mech, rules)
    limitations = _arch_limits(rules, limitations)
    return (level, f"{DOMAIN_CLASS_REASON[dom_class]}; " + _match_summary(rules), limitations)


def _arch_level(dom_class, maturity, has_mech, rules) -> TransferLevel:
    """Deterministic level from the satisfied architectural rules + source strength."""
    mfr = rules.get("same_manufacturer")
    dt = rules.get("same_drivetrain")
    layout = rules.get("same_layout")
    cat = rules.get("same_race_category")
    susp = rules.get("same_suspension_architecture")

    if dom_class == "handling_drivetrain":
        strong = dt and layout
        if strong and mfr and has_mech and maturity in _STRONG_SOURCE:
            return TransferLevel.SUPPORTED
        if strong:
            return TransferLevel.HIGH
        if dt or layout:
            return TransferLevel.MEDIUM
        return TransferLevel.VERY_LOW

    # architecture_dependent
    strong = mfr and dt and cat            # architecturally the same car family
    if strong and susp and has_mech and maturity in _STRONG_SOURCE:
        return TransferLevel.SUPPORTED
    if strong:
        return TransferLevel.HIGH
    two = sum(bool(x) for x in (mfr, dt, cat)) >= 2
    if two:
        return TransferLevel.MEDIUM
    if mfr or dt or cat:
        return TransferLevel.LOW
    return TransferLevel.NOT_TRANSFERABLE


def _arch_limits(rules, limitations: List[str]) -> List[str]:
    if not rules.get("same_manufacturer"):
        limitations.append("different manufacturer - component families may differ")
    if not rules.get("same_drivetrain"):
        limitations.append("different drivetrain - load transfer differs")
    if not rules.get("same_race_category"):
        limitations.append("different race category - aero / tyre envelope differs")
    return limitations


def _match_summary(rules) -> str:
    ok = [rid.replace("_", " ") for rid, v in rules.items() if v]
    return ("shared: " + ", ".join(ok)) if ok else "no architectural rule satisfied"


def _ctx_summary(ctx: Mapping, attrs: Mapping) -> dict:
    return {"car": str(ctx.get("car", "") or ""), "discipline": str(ctx.get("discipline", "") or ""),
            "gt7_version": str(ctx.get("gt7_version", "") or ""),
            "driver": str(ctx.get("driver", "") or ""),
            "manufacturer": attrs.get("manufacturer"), "drivetrain": attrs.get("drivetrain"),
            "layout": attrs.get("layout"), "category": attrs.get("category")}


def transfer_versions() -> dict:
    return {"knowledge_transfer": KNOWLEDGE_TRANSFER_VERSION,
            "transfer_rules": TRANSFER_RULES_VERSION}
