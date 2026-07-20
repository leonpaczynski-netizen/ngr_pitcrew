"""Engineering Reuse — summarise which engineering knowledge is reusable (Program 2, Phase 23).

A deterministic, READ-ONLY summary over a set of Phase-23 transfer candidates. It NEVER
recommends applying knowledge or a setup; it only reports, per target context:

  * "this knowledge is reusable because ..." (transferable candidates + why)
  * "this knowledge is not reusable because ..." (blocked candidates + why)
  * "additional evidence still required ..." (borderline / low candidates + what is missing)

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; no ML /
optimisation; deterministic; never raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Mapping, Sequence, Tuple

ENGINEERING_REUSE_VERSION = "engineering_reuse_v1"

# Transfer levels (Phase 23) grouped for the reuse summary.
_REUSABLE = ("high", "supported")
_NEEDS_MORE = ("medium", "low", "very_low")
_NOT_REUSABLE = ("not_transferable",)


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


@dataclass(frozen=True)
class ReuseSummary:
    reusable: Tuple[dict, ...]           # concepts that are reusable (with why)
    needs_more_evidence: Tuple[dict, ...]  # borderline (with what is missing)
    not_reusable: Tuple[dict, ...]       # blocked (with why)
    isolated_targets: Tuple[dict, ...]   # target contexts with NO reusable knowledge at all
    counts: dict
    eval_version: str = ENGINEERING_REUSE_VERSION

    def to_dict(self) -> dict:
        return {"reusable": [dict(r) for r in self.reusable],
                "needs_more_evidence": [dict(r) for r in self.needs_more_evidence],
                "not_reusable": [dict(r) for r in self.not_reusable],
                "isolated_targets": [dict(r) for r in self.isolated_targets],
                "counts": dict(self.counts), "eval_version": self.eval_version}


def summarise_reuse(candidates: Sequence[Mapping]) -> ReuseSummary:
    """Group transfer candidates into reusable / needs-more-evidence / not-reusable and detect
    target contexts that remain isolated. Never recommends applying anything; never raises."""
    try:
        return _summarise([c for c in (candidates or []) if isinstance(c, Mapping)])
    except Exception:   # never raise into the caller
        return ReuseSummary(reusable=(), needs_more_evidence=(), not_reusable=(),
                            isolated_targets=(), counts={})


def _summarise(candidates: List[Mapping]) -> ReuseSummary:
    reusable: List[dict] = []
    needs_more: List[dict] = []
    not_reusable: List[dict] = []
    # track, per target car, whether ANY candidate is reusable
    target_any_reusable: dict = {}
    target_ctx: dict = {}

    for c in candidates:
        level = _lc(c.get("transfer_level"))
        tgt = c.get("target_context") or {}
        tkey = _lc(tgt.get("car")) + "|" + _lc(tgt.get("discipline"))
        target_ctx.setdefault(tkey, dict(tgt))
        target_any_reusable.setdefault(tkey, False)

        entry = {
            "engineering_domain": c.get("engineering_domain"),
            "knowledge_area": c.get("knowledge_area"),
            "target_context": dict(tgt), "transfer_level": level,
            "explanation": c.get("reason"),
            "limitations": list(c.get("limitations") or []),
            "supporting_mechanisms": list(c.get("supporting_mechanisms") or []),
        }
        if level in _REUSABLE:
            entry["statement"] = (f"This '{c.get('engineering_domain')}' knowledge is reusable "
                                  f"because {c.get('reason')}")
            reusable.append(entry)
            target_any_reusable[tkey] = True
        elif level in _NOT_REUSABLE:
            entry["statement"] = (f"This '{c.get('engineering_domain')}' knowledge is not reusable "
                                  f"because {c.get('reason')}")
            not_reusable.append(entry)
        else:
            entry["statement"] = (f"Additional evidence still required before reusing "
                                  f"'{c.get('engineering_domain')}' knowledge: {c.get('reason')}")
            entry["evidence_required"] = list(c.get("limitations") or []) or [
                "further confirmation on the target car"]
            needs_more.append(entry)

    isolated = tuple(target_ctx[k] for k, any_reuse in target_any_reusable.items()
                     if not any_reuse)
    counts = {"reusable": len(reusable), "needs_more_evidence": len(needs_more),
              "not_reusable": len(not_reusable), "targets": len(target_ctx),
              "isolated_targets": len(isolated)}
    return ReuseSummary(reusable=tuple(reusable), needs_more_evidence=tuple(needs_more),
                        not_reusable=tuple(not_reusable), isolated_targets=isolated,
                        counts=counts)


def reuse_versions() -> dict:
    return {"engineering_reuse": ENGINEERING_REUSE_VERSION}
