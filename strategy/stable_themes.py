"""Stable Engineering Themes — recurring engineering knowledge across the stable (Phase 24).

A deterministic, READ-ONLY record of a recurring engineering theme: an ESTABLISHED domain of
knowledge in the source programme (Phase 22) together with the compatible programmes it is
transfer-eligible for (Phase 23). A theme is grounded in structured Phase-22/23 authorities - it
NEVER groups by matching words, and it carries NO setup values (only domains, mechanisms and
transfer levels).

A SUPPORTED transfer means the mechanism may be used as a hypothesis / investigation aid in the
target - never "copy the source setup / LSD / suspension / gearbox / numbers".

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; no ML /
optimisation; deterministic; never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import List, Mapping, Sequence, Tuple

from strategy.knowledge_transfer import TransferLevel

STABLE_THEMES_VERSION = "stable_themes_v1"

# Transfer levels (Phase 23) in ascending strength — reused verbatim, never reinterpreted.
_TRANSFER_ORDER = [lvl.value for lvl in TransferLevel]
# Levels Phase 23 treats as reusable (mirrors engineering_reuse._REUSABLE).
REUSABLE_LEVELS = ("high", "supported")
_NOT_TRANSFERABLE = "not_transferable"

# The engineering meaning of a transfer level (so the theme never implies a setup copy).
TRANSFER_MEANING = ("A reusable transfer level means the mechanism may be used only as a "
                    "hypothesis or investigation aid in the target context - it never means copy "
                    "the source setup, LSD, suspension, gearbox or numerical values.")


@dataclass(frozen=True)
class StableEngineeringTheme:
    theme_id: str
    engineering_domain: str
    mechanism: str
    source_programme: dict
    compatible_target_programmes: Tuple[dict, ...]
    recurrence_count: int
    evidence_count: int
    maturity_summary: str
    confidence_summary: str
    transfer_eligibility_summary: dict
    confirmed_good_protections: Tuple[dict, ...]
    known_negative_outcomes: Tuple[str, ...]
    applicability_boundaries: Tuple[str, ...]
    exclusions: Tuple[dict, ...]
    rationale: str
    source_authorities: Tuple[str, ...]
    calculation_inputs: dict
    eval_version: str = STABLE_THEMES_VERSION

    def to_dict(self) -> dict:
        return {"theme_id": self.theme_id, "engineering_domain": self.engineering_domain,
                "mechanism": self.mechanism, "source_programme": dict(self.source_programme),
                "compatible_target_programmes": [dict(t) for t in self.compatible_target_programmes],
                "recurrence_count": self.recurrence_count, "evidence_count": self.evidence_count,
                "maturity_summary": self.maturity_summary,
                "confidence_summary": self.confidence_summary,
                "transfer_eligibility_summary": dict(self.transfer_eligibility_summary),
                "confirmed_good_protections": [dict(p) for p in self.confirmed_good_protections],
                "known_negative_outcomes": list(self.known_negative_outcomes),
                "applicability_boundaries": list(self.applicability_boundaries),
                "exclusions": [dict(e) for e in self.exclusions], "rationale": self.rationale,
                "source_authorities": list(self.source_authorities),
                "calculation_inputs": dict(self.calculation_inputs),
                "eval_version": self.eval_version}


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


def _int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _theme_id(domain: str, mechanism: str, source_key: dict) -> str:
    payload = {"domain": _lc(domain), "mechanism": _lc(mechanism),
               "car": _lc(source_key.get("car")), "discipline": _lc(source_key.get("discipline")),
               "gt7_version": _lc(source_key.get("gt7_version")),
               "driver": _lc(source_key.get("driver"))}
    return ("theme_" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16])


def build_stable_themes(domain_records: Sequence[Mapping], source_programme: Mapping
                        ) -> Tuple[dict, ...]:
    """Build a stable theme for every ESTABLISHED source domain. Deterministic; grounded in the
    Phase-22/23 records (never keyword grouping); carries no setup values. Never raises."""
    try:
        return _build([d for d in (domain_records or []) if isinstance(d, Mapping)],
                      dict(source_programme or {}))
    except Exception:   # never raise into the caller
        return ()


def _build(records: List[Mapping], source_programme: Mapping) -> Tuple[dict, ...]:
    themes: List[StableEngineeringTheme] = []
    for r in records:
        if not r.get("established"):
            continue
        domain = _lc(r.get("domain"))
        mechs = [_lc(m) for m in (r.get("mechanisms") or []) if _lc(m)]
        mechanism = ", ".join(mechs) if mechs else f"{domain} behaviour"

        transfers = [t for t in (r.get("transfers") or []) if isinstance(t, Mapping)]
        reusable = [t for t in transfers if _lc(t.get("transfer_level")) in REUSABLE_LEVELS]
        exclusions = [{"target": dict(t.get("target") or {}),
                       "transfer_level": _lc(t.get("transfer_level")),
                       "reason": t.get("reason")}
                      for t in transfers if _lc(t.get("transfer_level")) == _NOT_TRANSFERABLE]

        # transfer eligibility summary (reused verbatim from Phase 23; never reinterpreted).
        levels = [_lc(t.get("transfer_level")) for t in transfers]
        best = _best_level(levels)
        worst = _worst_level(levels)
        elig = {"best_level": best, "worst_level": worst, "reusable_targets": len(reusable),
                "blocked_targets": len(exclusions), "total_targets": len(transfers),
                "meaning": TRANSFER_MEANING,
                "level_counts": {lv: levels.count(lv) for lv in sorted(set(levels))}}

        confirmed_good = tuple(_confirmed_good(r)) if r.get("confirmed_good") else ()
        negatives = tuple(_negatives(r))
        boundaries = tuple(_applicability(r))

        recurrence = 1 + len(reusable)      # source programme + compatible target programmes
        evidence = _int(r.get("confirmations"))

        theme = StableEngineeringTheme(
            theme_id=_theme_id(domain, mechanism, source_programme),
            engineering_domain=domain, mechanism=mechanism,
            source_programme=_prog(source_programme),
            compatible_target_programmes=tuple(_prog(t.get("target") or {}) for t in reusable),
            recurrence_count=recurrence, evidence_count=evidence,
            maturity_summary=_lc(r.get("maturity")), confidence_summary=_lc(r.get("confidence")),
            transfer_eligibility_summary=elig, confirmed_good_protections=confirmed_good,
            known_negative_outcomes=negatives, applicability_boundaries=boundaries,
            exclusions=tuple(exclusions),
            rationale=(f"established '{domain}' knowledge ({_lc(r.get('maturity'))}, confidence "
                       f"{_lc(r.get('confidence'))}, {evidence} confirmation(s)); reusable in "
                       f"{len(reusable)} compatible programme(s), blocked in {len(exclusions)}."),
            source_authorities=("Phase 22 knowledge graph", "Phase 23 transfer eligibility",
                                "Phase 17 value", "Phase 18 campaigns"),
            calculation_inputs={"maturity": _lc(r.get("maturity")),
                                "confidence": _lc(r.get("confidence")),
                                "confirmations": evidence,
                                "regressions": _int(r.get("regressions")),
                                "conflicting": bool(r.get("conflicting")),
                                "reusable_targets": len(reusable),
                                "blocked_targets": len(exclusions),
                                "supporting_campaigns": list(r.get("supporting_campaigns") or [])})
        themes.append(theme)

    return tuple(t.to_dict() for t in themes)


def _prog(ctx: Mapping) -> dict:
    return {"car": str((ctx or {}).get("car", "") or ""),
            "discipline": str((ctx or {}).get("discipline", "") or ""),
            "gt7_version": str((ctx or {}).get("gt7_version", "") or ""),
            "driver": str((ctx or {}).get("driver", "") or "")}


def _confirmed_good(r: Mapping) -> List[dict]:
    return [{"behaviour": f"confirmed '{_lc(r.get('domain'))}' behaviour "
             f"({_lc(r.get('knowledge_state'))})",
             "confirmed_in": _prog(r.get("source_programme") or {}),
             "supporting_campaigns": list(r.get("supporting_campaigns") or []),
             "confidence": _lc(r.get("confidence")),
             "note": "domain-level confirmed-good proxy (Phase 22 knowledge state + confidence); "
                     "protect during any related investigation.",
             "source": "Phase 22 knowledge graph"}]


def _negatives(r: Mapping) -> List[str]:
    out = []
    if _int(r.get("regressions")) > 0:
        out.append(f"{_int(r.get('regressions'))} regression(s) recorded in this domain - a "
                   "historically harmful direction; do not repeat it as if proven.")
    if r.get("conflicting"):
        out.append("conflicting evidence present (both confirmed and regressed) - certainty is "
                   "reduced; do not average into false confidence.")
    return out


def _applicability(r: Mapping) -> List[str]:
    dcls = _lc(r.get("domain_transfer_class"))
    out = []
    reason = {
        "architecture_dependent": "applies only between architecturally similar cars "
                                  "(manufacturer + drivetrain + category).",
        "handling_drivetrain": "applies between cars sharing drivetrain and layout.",
        "car_track_specific": "car & track specific - does not transfer without explicit shared "
                              "evidence.",
        "context_bound": "track / event specific - does not transfer across cars.",
        "driver_specific": "specific to the driver - transfers only to the same driver.",
    }.get(dcls)
    if reason:
        out.append(reason)
    return out


def _best_level(levels: List[str]) -> str:
    present = [lv for lv in levels if lv in _TRANSFER_ORDER]
    return max(present, key=_TRANSFER_ORDER.index) if present else "not_transferable"


def _worst_level(levels: List[str]) -> str:
    present = [lv for lv in levels if lv in _TRANSFER_ORDER]
    return min(present, key=_TRANSFER_ORDER.index) if present else "not_transferable"


def theme_versions() -> dict:
    return {"stable_themes": STABLE_THEMES_VERSION}
