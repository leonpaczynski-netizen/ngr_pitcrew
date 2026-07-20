"""Knowledge Boundary — the explicit limits of the existing engineering knowledge (Phase 24).

A deterministic, READ-ONLY record of *why* a piece of knowledge cannot be reused or must be
revalidated in another context. Every boundary is grounded in an existing authority (Phase-22
knowledge graph maturity/evidence, Phase-23 transfer domain-class + visible rules) — it never
infers an unknown vehicle attribute (an unknown attribute becomes an UNKNOWN_VEHICLE_ATTRIBUTE
boundary, it is never guessed).

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; no ML /
optimisation; deterministic; never raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Mapping, Sequence, Tuple

KNOWLEDGE_BOUNDARY_VERSION = "knowledge_boundary_v1"


class BoundaryType(str, Enum):
    CAR_SPECIFIC = "car_specific"
    MANUFACTURER_SPECIFIC = "manufacturer_specific"
    DRIVETRAIN_SPECIFIC = "drivetrain_specific"
    CATEGORY_SPECIFIC = "category_specific"
    TRACK_SPECIFIC = "track_specific"
    TRACK_LAYOUT_SPECIFIC = "track_layout_specific"
    DISCIPLINE_SPECIFIC = "discipline_specific"
    DRIVER_SPECIFIC = "driver_specific"
    GT7_VERSION_SPECIFIC = "gt7_version_specific"
    TYRE_RULE_SPECIFIC = "tyre_rule_specific"
    FUEL_RULE_SPECIFIC = "fuel_rule_specific"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    UNKNOWN_VEHICLE_ATTRIBUTE = "unknown_vehicle_attribute"
    FAILED_HISTORICAL_OUTCOME = "failed_historical_outcome"
    UNVERIFIED_TRANSFER_PROXY = "unverified_transfer_proxy"


# Fixed order for deterministic output.
_BOUNDARY_ORDER = [b.value for b in BoundaryType]


@dataclass(frozen=True)
class KnowledgeBoundary:
    boundary_type: str
    scope: str                          # "domain" | "target"
    domain: str
    target_car: str
    reason: str
    source_authority: str

    def to_dict(self) -> dict:
        return {"boundary_type": self.boundary_type, "scope": self.scope, "domain": self.domain,
                "target_car": self.target_car, "reason": self.reason,
                "source_authority": self.source_authority}


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


def _int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def build_boundaries(domain_records: Sequence[Mapping]) -> Tuple[dict, ...]:
    """Build the deterministic, de-duplicated list of knowledge boundaries from the normalised
    Phase-24 domain records (each already joins Phase-22 domain knowledge + Phase-23 transfers).
    Never raises."""
    try:
        return _build([d for d in (domain_records or []) if isinstance(d, Mapping)])
    except Exception:   # never raise into the caller
        return ()


def _build(records: List[Mapping]) -> Tuple[dict, ...]:
    seen = set()
    out: List[KnowledgeBoundary] = []

    def _add(bt: BoundaryType, scope, domain, target_car, reason, authority):
        key = (bt.value, _lc(domain), _lc(target_car))
        if key in seen:
            return
        seen.add(key)
        out.append(KnowledgeBoundary(boundary_type=bt.value, scope=scope, domain=str(domain),
                                     target_car=str(target_car), reason=reason,
                                     source_authority=authority))

    for r in records:
        domain = _lc(r.get("domain"))
        dcls = _lc(r.get("domain_transfer_class"))
        # --- domain-intrinsic boundaries (from Phase-22 evidence / Phase-23 domain class) ---
        if not r.get("established"):
            _add(BoundaryType.INSUFFICIENT_EVIDENCE, "domain", domain, "",
                 "knowledge in this domain is not yet established - it must be developed, not "
                 "reused.", "Phase 22 knowledge maturity")
        if r.get("conflicting"):
            _add(BoundaryType.CONFLICTING_EVIDENCE, "domain", domain, "",
                 "the evidence conflicts (both confirmed and regressed) - certainty is reduced "
                 "and the knowledge must be revalidated.", "Phase 22 knowledge graph limitations")
        if _int(r.get("regressions")) > 0:
            _add(BoundaryType.FAILED_HISTORICAL_OUTCOME, "domain", domain, "",
                 f"{_int(r.get('regressions'))} regression(s) recorded - a historically harmful "
                 "direction must not be presented as reusable.", "Phase 3 outcome (via Phase 22)")
        if dcls == "context_bound" and domain in ("track_segments", "track_surface"):
            _add(BoundaryType.TRACK_SPECIFIC, "domain", domain, "",
                 "this knowledge is track / event specific and does not transfer across cars.",
                 "Phase 23 domain transfer class")
        if dcls == "context_bound" and domain == "fuel":
            _add(BoundaryType.FUEL_RULE_SPECIFIC, "domain", domain, "",
                 "fuel knowledge is event / regulation specific and does not transfer across "
                 "cars.", "Phase 23 domain transfer class")
        if dcls == "car_track_specific":
            _add(BoundaryType.CAR_SPECIFIC, "domain", domain, "",
                 "gearing / final-drive knowledge is car & track specific and does not transfer "
                 "without explicit shared evidence.", "Phase 23 domain transfer class")
        if dcls == "driver_specific":
            _add(BoundaryType.DRIVER_SPECIFIC, "domain", domain, "",
                 "driver-technique knowledge is specific to the driver and transfers only to the "
                 "same driver.", "Phase 23 domain transfer class")

        # --- per-target boundaries (why a transfer to a specific target is limited) ---
        for tr in (r.get("transfers") or []):
            if not isinstance(tr, Mapping):
                continue
            tgt = tr.get("target") or {}
            car = str(tgt.get("car") or "")
            rules = set(_lc(x) for x in (tr.get("rules_satisfied") or []))
            level = _lc(tr.get("transfer_level"))
            # unknown attributes on the target -> conservative boundary
            for attr in ("manufacturer", "drivetrain", "layout", "category"):
                if _lc(tgt.get(attr)) in ("", "unknown"):
                    _add(BoundaryType.UNKNOWN_VEHICLE_ATTRIBUTE, "target", domain, car,
                         f"the target car's {attr} is unknown - it is left unknown (never "
                         "inferred) and blocks any rule that depends on it.",
                         "Phase 23 car attributes")
            if level in ("not_transferable", "very_low", "low", "medium"):
                if "same_manufacturer" not in rules:
                    _add(BoundaryType.MANUFACTURER_SPECIFIC, "target", domain, car,
                         "different manufacturer - component families may differ.",
                         "Phase 23 transfer rules")
                if "same_drivetrain" not in rules:
                    _add(BoundaryType.DRIVETRAIN_SPECIFIC, "target", domain, car,
                         "different drivetrain - load transfer differs.", "Phase 23 transfer rules")
                if "same_race_category" not in rules:
                    _add(BoundaryType.CATEGORY_SPECIFIC, "target", domain, car,
                         "different race category - aero / tyre envelope differs.",
                         "Phase 23 transfer rules")
                if "compatible_gt7_version" not in rules:
                    _add(BoundaryType.GT7_VERSION_SPECIFIC, "target", domain, car,
                         "different GT7 major version - physics / BOP may differ; evidence must "
                         "be recollected.", "Phase 1 context + Phase 23 rules")
            # a transfer that leaned on the manufacturer+category proxy is not confirmed geometry
            if "same_suspension_architecture" in rules and level in ("high", "supported"):
                _add(BoundaryType.UNVERIFIED_TRANSFER_PROXY, "target", domain, car,
                     "suspension compatibility here is a manufacturer + category PROXY, not "
                     "confirmed geometry - treat as a hypothesis only.", "Phase 23 transfer rules")

    out.sort(key=lambda b: (_BOUNDARY_ORDER.index(b.boundary_type)
                            if b.boundary_type in _BOUNDARY_ORDER else 99,
                            b.domain, b.target_car))
    return tuple(b.to_dict() for b in out)


def boundary_versions() -> dict:
    return {"knowledge_boundary": KNOWLEDGE_BOUNDARY_VERSION}
