"""Engineering Knowledge Graph — knowledge organised by engineering domain (Phase 22).

A deterministic, READ-ONLY map of what the Engineering Brain currently knows, organised by
ENGINEERING DOMAIN (Differential, Springs, Anti-roll Bars, ...) rather than by campaign. Each
domain aggregates the campaigns whose setup fields / issue family / mechanisms map to it (via
FULLY VISIBLE maps — no inference: an unmapped attribute contributes to no domain), and reports
its knowledge state, confidence, supporting evidence, remaining uncertainty, known limitations
and maturity (Phase-22 knowledge_maturity).

This is NOT an AI graph, NOT graph theory, NOT ML, NOT optimisation - it is deterministic
aggregation of existing authorities. It ranks, schedules, completes and decides NOTHING.
Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; no graph /
network libraries; deterministic; never raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Mapping, Sequence, Tuple

from strategy.knowledge_maturity import (
    KNOWLEDGE_MATURITY_VERSION, best_confidence, classify_maturity,
)

ENGINEERING_KNOWLEDGE_GRAPH_VERSION = "engineering_knowledge_graph_v1"

_CONFIDENT = ("high", "very_high")
# Phase-21 knowledge states ordered most-understood -> least (for the domain's dominant state).
_STATE_ORDER = ("engineering_complete", "well_understood", "emerging_confidence",
                "needs_confirmation", "contradictory", "knowledge_plateau",
                "no_useful_experiments", "little_evidence", "unknown")


class KnowledgeDomain(str, Enum):
    DIFFERENTIAL = "differential"
    SUSPENSION = "suspension"
    RIDE_HEIGHT = "ride_height"
    SPRINGS = "springs"
    ANTI_ROLL_BARS = "anti_roll_bars"
    DAMPERS = "dampers"
    ALIGNMENT = "alignment"
    BRAKE_BALANCE = "brake_balance"
    AERODYNAMICS = "aerodynamics"
    TYRES = "tyres"
    FUEL = "fuel"
    GEARBOX = "gearbox"
    TRACK_SURFACE = "track_surface"
    TRACK_SEGMENTS = "track_segments"
    VEHICLE_BALANCE = "vehicle_balance"
    WEIGHT_TRANSFER = "weight_transfer"
    DRIVER_TECHNIQUE = "driver_technique"


# Fixed domain order for deterministic output.
_DOMAIN_ORDER = [d for d in KnowledgeDomain]

# VISIBLE mapping keywords (substring match, lowercased). Unmapped -> no contribution.
FIELD_DOMAIN_KEYWORDS = {
    KnowledgeDomain.DIFFERENTIAL: ("lsd", "diff"),
    KnowledgeDomain.ANTI_ROLL_BARS: ("arb", "anti_roll", "antiroll", "roll_bar"),
    KnowledgeDomain.SPRINGS: ("spring",),
    KnowledgeDomain.RIDE_HEIGHT: ("ride_height", "rideheight", "rh_"),
    KnowledgeDomain.DAMPERS: ("damper",),
    KnowledgeDomain.ALIGNMENT: ("toe", "camber", "caster", "castor"),
    KnowledgeDomain.BRAKE_BALANCE: ("brake_bias", "brake_balance", "brakebias"),
    KnowledgeDomain.AERODYNAMICS: ("aero", "wing", "downforce", "splitter"),
    KnowledgeDomain.GEARBOX: ("gear", "final_drive", "ratio"),
    KnowledgeDomain.TYRES: ("tyre", "tire", "compound", "pressure"),
    KnowledgeDomain.FUEL: ("fuel",),
    KnowledgeDomain.WEIGHT_TRANSFER: ("ballast", "weight", "mass"),
}

FAMILY_DOMAIN_KEYWORDS = {
    KnowledgeDomain.VEHICLE_BALANCE: ("rotation", "understeer", "oversteer", "balance", "turn"),
    KnowledgeDomain.WEIGHT_TRANSFER: ("traction", "wheelspin"),
    KnowledgeDomain.BRAKE_BALANCE: ("braking", "lockup", "instability_under_braking"),
    KnowledgeDomain.SUSPENSION: ("bottoming", "kerb", "compliance", "ride"),
    KnowledgeDomain.AERODYNAMICS: ("aero", "high_speed_stability"),
}

MECHANISM_DOMAIN_KEYWORDS = {
    KnowledgeDomain.WEIGHT_TRANSFER: ("load_transfer", "weight_transfer", "load"),
    KnowledgeDomain.DIFFERENTIAL: ("differential", "lsd", "locking"),
    KnowledgeDomain.AERODYNAMICS: ("aero", "downforce"),
    KnowledgeDomain.TYRES: ("tyre", "tire", "grip"),
    KnowledgeDomain.DAMPERS: ("damper", "transient"),
    KnowledgeDomain.SPRINGS: ("spring", "stiffness"),
    KnowledgeDomain.VEHICLE_BALANCE: ("balance", "rotation"),
    KnowledgeDomain.TRACK_SEGMENTS: ("segment", "corner_specific"),
    KnowledgeDomain.TRACK_SURFACE: ("surface", "grip_level"),
    KnowledgeDomain.DRIVER_TECHNIQUE: ("driver", "technique", "input", "throttle_application"),
}


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


def _int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _round(v) -> float:
    try:
        return round(float(v), 4)
    except (TypeError, ValueError):
        return 0.0


@dataclass(frozen=True)
class DomainKnowledge:
    domain: str
    knowledge_state: dict           # value + reason + source
    confidence: dict                # value + reason + source + calculation
    maturity: dict                  # value + reason + source
    remaining_uncertainty: dict     # value + reason + source
    supporting_campaigns: Tuple[str, ...]
    supporting_experiments: Tuple[str, ...]
    supporting_mechanisms: Tuple[str, ...]
    supporting_evidence: dict       # counts + source
    known_limitations: Tuple[str, ...]

    def to_dict(self) -> dict:
        return {"domain": self.domain, "knowledge_state": dict(self.knowledge_state),
                "confidence": dict(self.confidence), "maturity": dict(self.maturity),
                "remaining_uncertainty": dict(self.remaining_uncertainty),
                "supporting_campaigns": list(self.supporting_campaigns),
                "supporting_experiments": list(self.supporting_experiments),
                "supporting_mechanisms": list(self.supporting_mechanisms),
                "supporting_evidence": dict(self.supporting_evidence),
                "known_limitations": list(self.known_limitations)}


@dataclass(frozen=True)
class KnowledgeGraph:
    domains: Tuple[dict, ...]
    domain_maturity_counts: dict
    known_domains: Tuple[str, ...]
    missing_domains: Tuple[str, ...]
    eval_version: str = ENGINEERING_KNOWLEDGE_GRAPH_VERSION

    def to_dict(self) -> dict:
        return {"domains": [dict(d) for d in self.domains],
                "domain_maturity_counts": dict(self.domain_maturity_counts),
                "known_domains": list(self.known_domains),
                "missing_domains": list(self.missing_domains),
                "eval_version": self.eval_version}


def _domains_for_campaign(rec: Mapping) -> set:
    """Every domain a campaign contributes to, from its fields + family + mechanisms.
    Deterministic keyword match against the VISIBLE maps; unmapped -> no domain."""
    domains = set()
    for f in (rec.get("fields") or []):
        fl = _lc(f)
        for dom, kws in FIELD_DOMAIN_KEYWORDS.items():
            if any(kw in fl for kw in kws):
                domains.add(dom)
    fam = _lc(rec.get("family"))
    if fam:
        for dom, kws in FAMILY_DOMAIN_KEYWORDS.items():
            if any(kw in fam for kw in kws):
                domains.add(dom)
    for m in (rec.get("mechanisms") or []):
        ml = _lc(m)
        for dom, kws in MECHANISM_DOMAIN_KEYWORDS.items():
            if any(kw in ml for kw in kws):
                domains.add(dom)
    return domains


def build_knowledge_graph(campaigns: Sequence[Mapping]) -> KnowledgeGraph:
    """Aggregate a list of enriched, normalised campaign records (with an attached Phase-21
    ``knowledge_state``) into the per-domain knowledge graph. Deterministic; enumerates ALL
    domains (empty ones are reported as missing); never raises."""
    try:
        return _build([c for c in (campaigns or []) if isinstance(c, Mapping)])
    except Exception:   # never raise into the caller
        return KnowledgeGraph(domains=(), domain_maturity_counts={}, known_domains=(),
                              missing_domains=tuple(d.value for d in _DOMAIN_ORDER))


def _build(records: List[Mapping]) -> KnowledgeGraph:
    # bucket campaign indices per domain (deterministic — preserve input order)
    buckets = {d: [] for d in _DOMAIN_ORDER}
    for rec in records:
        for dom in _domains_for_campaign(rec):
            buckets[dom].append(rec)

    domains: List[dict] = []
    maturity_counts: dict = {}
    known: List[str] = []
    missing: List[str] = []
    for dom in _DOMAIN_ORDER:
        contributors = buckets[dom]
        dk = _domain_knowledge(dom, contributors)
        domains.append(dk.to_dict())
        mat = dk.maturity["value"]
        maturity_counts[mat] = maturity_counts.get(mat, 0) + 1
        if contributors and mat != "unknown":
            known.append(dom.value)
        else:
            missing.append(dom.value)

    return KnowledgeGraph(domains=tuple(domains), domain_maturity_counts=maturity_counts,
                          known_domains=tuple(known), missing_domains=tuple(missing))


def _domain_knowledge(dom: KnowledgeDomain, contributors: List[Mapping]) -> DomainKnowledge:
    cids = _sorted_unique(str(c.get("campaign_id") or "") for c in contributors)
    fields = _sorted_unique(_lc(f) for c in contributors for f in (c.get("fields") or []))
    mechanisms = _sorted_unique(_lc(m) for c in contributors for m in (c.get("mechanisms") or []))
    conf_levels = [_lc(c.get("confidence_level")) for c in contributors]
    states = [_lc(c.get("knowledge_state")) for c in contributors]

    confirmations = sum(_int(c.get("confirmations")) for c in contributors)
    regressions = sum(_int(c.get("regressions")) for c in contributors)
    executed = sum(_int(c.get("executed")) for c in contributors)
    unresolved = sum(_int(c.get("unresolved_mechanisms")) for c in contributors)
    conflicting_any = any(bool(c.get("conflicting")) for c in contributors)
    testable_any = any(bool(c.get("testable")) for c in contributors)

    best = best_confidence(conf_levels)
    dominant_state = _dominant_state(states)
    remaining_gain = _dominant_remaining(contributors)

    maturity = classify_maturity({
        "contributing_campaigns": len(contributors), "executed_total": executed,
        "confirmations_total": confirmations, "regressions_total": regressions,
        "conflicting_any": conflicting_any, "unresolved_total": unresolved,
        "testable_any": testable_any, "confidence_levels": conf_levels,
        "knowledge_states": states}).to_dict()

    tracks = _sorted_unique(_lc(c.get("track")) for c in contributors)
    limitations = _limitations(contributors, conflicting_any, unresolved, best, tracks)

    src_campaigns = "Phase 18 campaigns (mapped to this domain)"
    return DomainKnowledge(
        domain=dom.value,
        knowledge_state={"value": dominant_state,
                         "reason": (f"dominant state across {len(contributors)} contributing "
                                    f"campaign(s)" if contributors
                                    else "no campaign maps to this domain yet"),
                         "source": "Phase 21 knowledge map"},
        confidence={"value": best,
                    "reason": (f"best-known confidence among contributors ({', '.join(cids) or '-'})"
                               if contributors else "no evidence"),
                    "source": "Phase 20 knowledge confidence",
                    "calculation": "strongest confidence level present among contributing campaigns"},
        maturity={"value": maturity["maturity"], "reason": maturity["reason"],
                  "source": maturity["source"]},
        remaining_uncertainty={"value": remaining_gain,
                               "reason": ("highest remaining information gain across contributors"
                                          if contributors else "unknown - no evidence"),
                               "source": "Phase 19 evidence saturation"},
        supporting_campaigns=tuple(cids), supporting_experiments=tuple(fields),
        supporting_mechanisms=tuple(mechanisms),
        supporting_evidence={"contributing_campaigns": len(contributors),
                             "confirmations": confirmations, "regressions": regressions,
                             "executed": executed, "source": src_campaigns},
        known_limitations=tuple(limitations))


def _dominant_state(states: List[str]) -> str:
    present = [s for s in states if s]
    if not present:
        return "unknown"
    for st in _STATE_ORDER:            # most-understood first
        if st in present:
            return st
    return "unknown"


def _dominant_remaining(contributors: List[Mapping]) -> str:
    order = {"high": 3, "moderate": 2, "low": 1, "none": 0}
    best_label, best_rank = "unknown", -1
    for c in contributors:
        lab = _lc(c.get("remaining_information_gain"))
        if lab in order and order[lab] > best_rank:
            best_label, best_rank = lab, order[lab]
    return best_label


def _limitations(contributors, conflicting_any, unresolved, best, tracks) -> List[str]:
    lims: List[str] = []
    if not contributors:
        lims.append("no campaign has produced evidence in this domain")
        return lims
    if conflicting_any:
        lims.append("conflicting evidence present (both confirmed and regressed)")
    if unresolved > 0:
        lims.append(f"{unresolved} mechanism(s) still unresolved")
    if best not in _CONFIDENT:
        lims.append(f"confidence only reaches {best} - conclusions are not yet fully trustworthy")
    if len(tracks) > 1:
        lims.append(f"evidence spans {len(tracks)} track(s) ({', '.join(t for t in tracks if t)}) "
                    "- domain knowledge is aggregated across them")
    return lims


def _sorted_unique(items) -> List[str]:
    return sorted({str(x) for x in items if str(x)})


def graph_versions() -> dict:
    return {"engineering_knowledge_graph": ENGINEERING_KNOWLEDGE_GRAPH_VERSION,
            "knowledge_maturity": KNOWLEDGE_MATURITY_VERSION}
