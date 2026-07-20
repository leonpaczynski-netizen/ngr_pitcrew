"""New Programme Brief — a read-only engineering brief for a target context (Program 2, Phase 24).

For one target programme (car / discipline / version / driver), it states what established
knowledge exists, what is eligible for CAUTIOUS reuse (as a hypothesis, never a setup to copy),
what must be protected, what needs early validation, what evidence must be recollected, what must
not be reused, the known negative directions to avoid, the unresolved uncertainties and the limits
of the available knowledge.

It explicitly states that NO setup values have been transferred and that all knowledge requires
validation in the target context. Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no
random, no wall-clock; no ML / optimisation; deterministic; never raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Mapping, Sequence, Tuple

NEW_PROGRAMME_BRIEF_VERSION = "new_programme_brief_v1"

_REUSABLE = ("high", "supported")
_NOT_TRANSFERABLE = "not_transferable"

_NO_SETUP_STATEMENT = ("No setup values have been transferred. Every item below is engineering "
                       "KNOWLEDGE (a mechanism or hypothesis), not a setup to copy - it must be "
                       "validated in this target context before it is trusted.")


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


def _int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _prog(ctx: Mapping) -> dict:
    return {"car": str((ctx or {}).get("car", "") or ""),
            "discipline": str((ctx or {}).get("discipline", "") or ""),
            "gt7_version": str((ctx or {}).get("gt7_version", "") or ""),
            "driver": str((ctx or {}).get("driver", "") or "")}


@dataclass(frozen=True)
class NewProgrammeBrief:
    target_programme: dict
    source_programme: dict
    established_knowledge: Tuple[dict, ...]
    eligible_for_cautious_reuse: Tuple[dict, ...]
    protect: Tuple[dict, ...]
    needs_early_validation: Tuple[dict, ...]
    recollect_evidence: Tuple[dict, ...]
    must_not_reuse: Tuple[dict, ...]
    negative_directions_to_avoid: Tuple[str, ...]
    unresolved_uncertainties: Tuple[str, ...]
    knowledge_limits: Tuple[dict, ...]
    no_setup_statement: str
    eval_version: str = NEW_PROGRAMME_BRIEF_VERSION

    def to_dict(self) -> dict:
        return {"target_programme": dict(self.target_programme),
                "source_programme": dict(self.source_programme),
                "established_knowledge": [dict(x) for x in self.established_knowledge],
                "eligible_for_cautious_reuse": [dict(x) for x in self.eligible_for_cautious_reuse],
                "protect": [dict(x) for x in self.protect],
                "needs_early_validation": [dict(x) for x in self.needs_early_validation],
                "recollect_evidence": [dict(x) for x in self.recollect_evidence],
                "must_not_reuse": [dict(x) for x in self.must_not_reuse],
                "negative_directions_to_avoid": list(self.negative_directions_to_avoid),
                "unresolved_uncertainties": list(self.unresolved_uncertainties),
                "knowledge_limits": [dict(x) for x in self.knowledge_limits],
                "no_setup_statement": self.no_setup_statement, "eval_version": self.eval_version}


def build_briefs(domain_records: Sequence[Mapping], source_programme: Mapping,
                 targets: Sequence[Mapping], boundaries: Sequence[Mapping]) -> Tuple[dict, ...]:
    """Build one read-only brief per target programme. Deterministic; carries no setup values;
    never raises."""
    try:
        recs = [d for d in (domain_records or []) if isinstance(d, Mapping)]
        tgts = [t for t in (targets or []) if isinstance(t, Mapping)]
        bnds = [b for b in (boundaries or []) if isinstance(b, Mapping)]
        return tuple(_brief(recs, source_programme, t, bnds).to_dict() for t in tgts)
    except Exception:   # never raise into the caller
        return ()


def _transfer_for(record: Mapping, target_car: str):
    for tr in (record.get("transfers") or []):
        if isinstance(tr, Mapping) and _lc((tr.get("target") or {}).get("car")) == target_car:
            return tr
    return None


def _brief(records: List[Mapping], source_programme: Mapping, target: Mapping,
           boundaries: List[Mapping]) -> NewProgrammeBrief:
    tcar = _lc(target.get("car"))
    established, reusable, protect, validate, recollect, not_reuse = [], [], [], [], [], []
    negatives: List[str] = []
    uncertainties: List[str] = []

    for r in records:
        domain = _lc(r.get("domain"))
        mechs = ", ".join(_lc(m) for m in (r.get("mechanisms") or []) if _lc(m)) or f"{domain} behaviour"
        item = {"domain": domain, "mechanism": mechs, "maturity": _lc(r.get("maturity")),
                "confidence": _lc(r.get("confidence"))}
        tr = _transfer_for(r, tcar)
        level = _lc(tr.get("transfer_level")) if tr else "not_transferable"

        if r.get("established"):
            established.append(dict(item))
        if r.get("confirmed_good"):
            protect.append({**item, "note": "confirmed-good behaviour - preserve it during any "
                            "validation.", "source": "Phase 22 knowledge graph"})
        if r.get("established") and level in _REUSABLE:
            reusable.append({**item, "transfer_level": level,
                             "note": "reuse only as a hypothesis / investigation aid - not a "
                             "setup to copy.", "reason": tr.get("reason") if tr else ""})
            validate.append({**item, "transfer_level": level,
                             "note": "validate early in this target before relying on it."})
        if r.get("established") and level in ("not_transferable",):
            not_reuse.append({**item, "transfer_level": level,
                              "reason": tr.get("reason") if tr else "not transferable to this "
                              "target"})
        if r.get("established") and level in ("very_low", "low", "medium"):
            recollect.append({**item, "transfer_level": level,
                              "note": "weak transfer - recollect evidence in this target rather "
                              "than reuse."})
        if _int(r.get("regressions")) > 0:
            negatives.append(f"{domain}: a historically harmful direction was recorded - do not "
                             "repeat it.")
        if r.get("conflicting"):
            uncertainties.append(f"{domain}: conflicting evidence - certainty is reduced.")
        if _lc(r.get("remaining_uncertainty")) in ("high", "moderate"):
            uncertainties.append(f"{domain}: {_lc(r.get('remaining_uncertainty'))} remaining "
                                 "uncertainty.")

    limits = [dict(b) for b in boundaries
              if _lc(b.get("target_car")) in ("", tcar)]

    return NewProgrammeBrief(
        target_programme=_prog(target), source_programme=_prog(source_programme),
        established_knowledge=tuple(established), eligible_for_cautious_reuse=tuple(reusable),
        protect=tuple(protect), needs_early_validation=tuple(validate),
        recollect_evidence=tuple(recollect), must_not_reuse=tuple(not_reuse),
        negative_directions_to_avoid=tuple(dict.fromkeys(negatives)),
        unresolved_uncertainties=tuple(dict.fromkeys(uncertainties)),
        knowledge_limits=tuple(limits), no_setup_statement=_NO_SETUP_STATEMENT)


def brief_versions() -> dict:
    return {"new_programme_brief": NEW_PROGRAMME_BRIEF_VERSION}
