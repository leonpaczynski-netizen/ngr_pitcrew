"""Cross-Campaign Map — engineering relationships between campaigns (Program 2, Phase 21).

A deterministic, READ-ONLY detector of the ENGINEERING relationships between campaigns - NOT
execution dependencies, NOT a scheduler. Every relationship is grounded in a concrete, visible
shared attribute drawn from existing authorities (Phase-18 identity / objective / experiments +
Phase-19/20 evidence state). It infers no hidden relationships: if no rule's evidence is
present, the pair has no relationship.

This is plain deterministic pairwise aggregation - NOT graph search, clustering, ML or network
optimisation. Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no
wall-clock; deterministic; never raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Mapping, Sequence, Tuple

CROSS_CAMPAIGN_MAP_VERSION = "cross_campaign_map_v1"

_CONFIDENT = ("high", "very_high")
_NEEDY_OPPORTUNITY = ("worth_another_confirmation", "worth_mechanism_isolation",
                      "worth_contradiction_testing", "knowledge_plateau")


class CampaignRelationship(str, Enum):
    NONE = "none"
    RELATED = "related"
    OVERLAPS = "overlaps"
    SUPPORTS = "supports"
    DEPENDS_ON = "depends_on"
    DUPLICATES = "duplicates"
    CONTRADICTS = "contradicts"
    BLOCKED_BY = "blocked_by"
    ISOLATED = "isolated"


@dataclass(frozen=True)
class CampaignRelationshipEdge:
    from_campaign_id: str
    to_campaign_id: str
    from_objective: str
    to_objective: str
    relationship: str
    directional: bool
    reason: str
    supporting_evidence: Tuple[str, ...]
    authority: str
    eval_version: str = CROSS_CAMPAIGN_MAP_VERSION

    def to_dict(self) -> dict:
        return {"from_campaign_id": self.from_campaign_id,
                "to_campaign_id": self.to_campaign_id, "from_objective": self.from_objective,
                "to_objective": self.to_objective, "relationship": self.relationship,
                "directional": self.directional, "reason": self.reason,
                "supporting_evidence": list(self.supporting_evidence),
                "authority": self.authority, "eval_version": self.eval_version}


@dataclass(frozen=True)
class CrossCampaignMap:
    edges: Tuple[dict, ...]
    isolated_campaign_ids: Tuple[str, ...]
    relationship_counts: dict
    eval_version: str = CROSS_CAMPAIGN_MAP_VERSION

    def to_dict(self) -> dict:
        return {"edges": [dict(e) for e in self.edges],
                "isolated_campaign_ids": list(self.isolated_campaign_ids),
                "relationship_counts": dict(self.relationship_counts),
                "eval_version": self.eval_version}


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


def _fields(r: Mapping) -> set:
    return {_lc(f) for f in (r.get("fields") or []) if _lc(f)}


def _mech(r: Mapping) -> set:
    return {_lc(m) for m in (r.get("mechanisms") or []) if _lc(m)}


def _confident(r: Mapping) -> bool:
    return _lc(r.get("confidence_level")) in _CONFIDENT


def _needy(r: Mapping) -> bool:
    return (_lc(r.get("opportunity")) in _NEEDY_OPPORTUNITY
            or _lc(r.get("confidence_level")) in ("unknown", "very_low", "low", "medium"))


def _contradictory(r: Mapping) -> bool:
    return bool(r.get("conflicting")) or _lc(r.get("opportunity")) == "worth_contradiction_testing"


def _needs_mechanism(r: Mapping) -> bool:
    try:
        return int(r.get("unresolved_mechanisms") or 0) > 0 \
            or _lc(r.get("opportunity")) == "worth_mechanism_isolation"
    except (TypeError, ValueError):
        return _lc(r.get("opportunity")) == "worth_mechanism_isolation"


def build_cross_campaign_map(campaigns: Sequence[Mapping]) -> CrossCampaignMap:
    """Detect the engineering relationships across a list of normalised season-campaign records.
    Deterministic O(n^2) pairwise scan in the given (stable) order; every edge is evidence-
    grounded. Ranks/schedules nothing. Never raises."""
    try:
        return _build([c for c in (campaigns or []) if isinstance(c, Mapping)])
    except Exception:   # never raise into the caller
        return CrossCampaignMap(edges=(), isolated_campaign_ids=(), relationship_counts={})


def _build(records: List[Mapping]) -> CrossCampaignMap:
    edges: List[dict] = []
    related_ids = set()
    for i in range(len(records)):
        for j in range(i + 1, len(records)):
            a, b = records[i], records[j]
            edge = _relate(a, b)
            if edge is not None:
                edges.append(edge.to_dict())
                related_ids.add(str(a.get("campaign_id") or ""))
                related_ids.add(str(b.get("campaign_id") or ""))

    isolated = tuple(str(r.get("campaign_id") or "") for r in records
                     if str(r.get("campaign_id") or "") not in related_ids)
    counts: dict = {}
    for e in edges:
        counts[e["relationship"]] = counts.get(e["relationship"], 0) + 1
    if isolated:
        counts[CampaignRelationship.ISOLATED.value] = len(isolated)
    return CrossCampaignMap(edges=tuple(edges), isolated_campaign_ids=isolated,
                            relationship_counts=counts)


def _edge(a, b, rel: CampaignRelationship, directional, reason, evidence, authority):
    return CampaignRelationshipEdge(
        from_campaign_id=str(a.get("campaign_id") or ""),
        to_campaign_id=str(b.get("campaign_id") or ""),
        from_objective=str(a.get("objective") or ""), to_objective=str(b.get("objective") or ""),
        relationship=rel.value, directional=directional, reason=reason,
        supporting_evidence=tuple(evidence), authority=authority)


def _relate(a: Mapping, b: Mapping):
    """Return the single strongest evidence-grounded relationship for the ordered pair (a, b),
    or None. Directional relationships set from/to to the meaningful direction."""
    fam_a, fam_b = _lc(a.get("family")), _lc(b.get("family"))
    reg_a, reg_b = _lc(a.get("region")), _lc(b.get("region"))
    same_family = bool(fam_a) and fam_a == fam_b
    same_fr = same_family and bool(reg_a) and reg_a == reg_b
    fields_a, fields_b = _fields(a), _fields(b)
    shared_fields = fields_a & fields_b
    shared_mech = _mech(a) & _mech(b)

    # 1. DUPLICATES — same objective (family+region) AND the same setup change, both testable.
    if same_fr and fields_a and fields_a == fields_b and a.get("testable") and b.get("testable"):
        return _edge(a, b, CampaignRelationship.DUPLICATES, False,
                     "both campaigns pursue the same objective with the same setup change - "
                     "engineering effort is duplicated.",
                     [f"objective family/region '{fam_a}/{reg_a}'",
                      f"identical target fields {sorted(fields_a)}"],
                     "Phase 18 campaign identity + experiments")

    # 2. CONTRADICTS — same family, one confirmed-good and the other contradictory.
    if same_family and ((_confident(a) and _contradictory(b))
                        or (_confident(b) and _contradictory(a))):
        return _edge(a, b, CampaignRelationship.CONTRADICTS, False,
                     "the two campaigns reach conflicting conclusions in the same vehicle "
                     "system - one is confident, the other shows contradictory evidence.",
                     [f"shared family '{fam_a}'",
                      f"confidence {a.get('confidence_level')} vs {b.get('confidence_level')}"],
                     "Phase 18 identity + Phase 20 confidence")

    # 3. shared mechanism with a confidence asymmetry — dependency / support (directional,
    #    a strong specific relationship regardless of family/region).
    if shared_mech:
        if _needs_mechanism(a) and _confident(b):
            return _edge(a, b, CampaignRelationship.DEPENDS_ON, True,
                         "this campaign still needs a mechanism that the other has already "
                         "validated with confidence.",
                         [f"shared mechanism(s) {sorted(shared_mech)}",
                          f"other confidence {b.get('confidence_level')}"],
                         "Phase 18 objective mechanisms + Phase 20 confidence")
        if _needs_mechanism(b) and _confident(a):
            return _edge(b, a, CampaignRelationship.DEPENDS_ON, True,
                         "this campaign still needs a mechanism that the other has already "
                         "validated with confidence.",
                         [f"shared mechanism(s) {sorted(shared_mech)}",
                          f"other confidence {a.get('confidence_level')}"],
                         "Phase 18 objective mechanisms + Phase 20 confidence")
        if _confident(a) and _needy(b):
            return _edge(a, b, CampaignRelationship.SUPPORTS, True,
                         "this campaign's confirmed mechanism supports the other, which is "
                         "still building confidence.",
                         [f"shared mechanism(s) {sorted(shared_mech)}"],
                         "Phase 18 objective mechanisms + Phase 20 confidence")
        if _confident(b) and _needy(a):
            return _edge(b, a, CampaignRelationship.SUPPORTS, True,
                         "this campaign's confirmed mechanism supports the other, which is "
                         "still building confidence.",
                         [f"shared mechanism(s) {sorted(shared_mech)}"],
                         "Phase 18 objective mechanisms + Phase 20 confidence")

    # 4. OVERLAPS — same objective (family+region), concurrent but not identical. Preferred over
    #    a plain shared-mechanism RELATED because the shared objective is the stronger signal.
    if same_fr:
        return _edge(a, b, CampaignRelationship.OVERLAPS, False,
                     "both campaigns target the same engineering objective (same system and "
                     "region) - their work overlaps.",
                     [f"objective family/region '{fam_a}/{reg_a}'"],
                     "Phase 18 campaign identity")

    # 5. BLOCKED_BY — same family, the other is contradictory and this one needs progress.
    if same_family and _contradictory(b) and _needy(a) and not _contradictory(a):
        return _edge(a, b, CampaignRelationship.BLOCKED_BY, True,
                     "progress here is held back by unresolved conflicting evidence in a "
                     "related campaign in the same system.",
                     [f"shared family '{fam_a}'", "other campaign has conflicting evidence"],
                     "Phase 18 identity + Phase 19 saturation")
    if same_family and _contradictory(a) and _needy(b) and not _contradictory(b):
        return _edge(b, a, CampaignRelationship.BLOCKED_BY, True,
                     "progress here is held back by unresolved conflicting evidence in a "
                     "related campaign in the same system.",
                     [f"shared family '{fam_a}'", "other campaign has conflicting evidence"],
                     "Phase 18 identity + Phase 19 saturation")

    # 6. RELATED — same family, different region.
    if same_family:
        return _edge(a, b, CampaignRelationship.RELATED, False,
                     "the campaigns work on the same vehicle system in different regions.",
                     [f"shared family '{fam_a}'",
                      f"regions '{reg_a}' vs '{reg_b}'"], "Phase 18 campaign identity")

    # 7. RELATED — a shared physical mechanism with no confidence asymmetry.
    if shared_mech:
        return _edge(a, b, CampaignRelationship.RELATED, False,
                     "the two campaigns share a physical mechanism.",
                     [f"shared mechanism(s) {sorted(shared_mech)}"],
                     "Phase 18 objective mechanisms")

    # 8. OVERLAPS — different systems but the same setup field is being changed.
    if shared_fields:
        return _edge(a, b, CampaignRelationship.OVERLAPS, False,
                     "different objectives, but both change the same setup field - the changes "
                     "may interact.",
                     [f"shared field(s) {sorted(shared_fields)}"],
                     "Phase 18 campaign experiments")

    return None


def relationship_versions() -> dict:
    return {"cross_campaign_map": CROSS_CAMPAIGN_MAP_VERSION}
