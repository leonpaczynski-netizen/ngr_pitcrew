"""Context-Scoped Knowledge Chain — classify-before-aggregate (Program 2, Phase 39; Audit A fix).

The shared Phase-22 chain aggregates evidence across a compatibility group (car/discipline/gt7/driver)
that EXCLUDES track/layout/compound, so its maturity/convergence/assurance/priority are cross-track.
This module is the remediation: it classifies every raw record against the current
``EngineeringContextScope`` FIRST (reusing the Phase-36 activation), then builds exact-context
conclusions from exact records ONLY, keeps an explicitly-transferable overlay separately, and never
lets reference-only / excluded / unverifiable evidence enter an exact-context aggregate.

Guarantees (metamorphic): adding incompatible (e.g. Daytona) records cannot change any exact-context
(Fuji) evidence count, convergence, working-window input or best-known-eligibility input - those are
pure functions of the exact record set, which incompatible records are never members of. Transferred
evidence is labelled and never counted as independent exact evidence.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from strategy.engineering_context_scope import (
    EngineeringContextScope, build_engineering_context_scope, ENGINEERING_CONTEXT_SCOPE_VERSION,
)
from strategy.contextual_knowledge_activation import (
    activate_context_knowledge, EvidenceClass, CONTEXTUAL_KNOWLEDGE_ACTIVATION_VERSION,
)

CONTEXT_SCOPED_CHAIN_VERSION = "context_scoped_chain_v1"
CONTEXT_SCOPED_CHAIN_SCHEMA = 1

_EXACT = EvidenceClass.EXACT_CONTEXT.value
_TRANSFER = EvidenceClass.EXPLICITLY_TRANSFERABLE.value
_REFERENCE = EvidenceClass.REFERENCE_ONLY.value
_EXCLUDED = EvidenceClass.EXCLUDED.value
_UNVERIFIABLE = EvidenceClass.UNVERIFIABLE.value

_IMPROVED = ("confirmed_improvement", "partial_improvement", "improvement", "improved")


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{CONTEXT_SCOPED_CHAIN_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


class ConvergenceState(str, Enum):
    CONVERGED = "converged"              # >=2 independent confirmations, no unresolved regression
    EMERGING = "emerging"               # some exact evidence, not yet independent-repeated
    CONTESTED = "contested"             # improvements and regressions both present, unresolved
    SINGLE_CONTEXT = "single_context"    # only one session/experiment of evidence
    INSUFFICIENT = "insufficient"


@dataclass(frozen=True)
class ContextScopedEvidenceSet:
    exact: Tuple[dict, ...]
    transferable: Tuple[dict, ...]
    reference_only: Tuple[dict, ...]
    excluded: Tuple[dict, ...]
    unverifiable: Tuple[dict, ...]

    def to_dict(self) -> dict:
        return {"exact": [dict(r) for r in self.exact],
                "transferable": [dict(r) for r in self.transferable],
                "reference_only": [dict(r) for r in self.reference_only],
                "excluded": [dict(r) for r in self.excluded],
                "unverifiable": [dict(r) for r in self.unverifiable]}


@dataclass(frozen=True)
class ContextScopedKnowledgeChain:
    scope: dict
    completeness: str
    counts: dict
    exact_domain_summary: Tuple[dict, ...]
    transfer_overlay: Tuple[dict, ...]
    provenance: Tuple[dict, ...]
    exact_record_keys: Tuple[str, ...]
    independence: dict
    doctrine: str
    exact_content_fingerprint: str
    content_fingerprint: str
    schema_version: int = CONTEXT_SCOPED_CHAIN_SCHEMA
    eval_version: str = CONTEXT_SCOPED_CHAIN_VERSION

    def to_dict(self) -> dict:
        return {"scope": dict(self.scope), "completeness": self.completeness,
                "counts": dict(self.counts),
                "exact_domain_summary": [dict(d) for d in self.exact_domain_summary],
                "transfer_overlay": [dict(t) for t in self.transfer_overlay],
                "provenance": [dict(p) for p in self.provenance],
                "exact_record_keys": list(self.exact_record_keys),
                "independence": dict(self.independence), "doctrine": self.doctrine,
                "exact_content_fingerprint": self.exact_content_fingerprint,
                "content_fingerprint": self.content_fingerprint,
                "schema_version": self.schema_version, "eval_version": self.eval_version}


_DOCTRINE = ("Raw records are classified against the current context BEFORE any aggregate reasoning. "
             "Exact-context conclusions use exact records only; transferable evidence is a separate, "
             "lower-confidence overlay with visible limitations and is never counted as independent "
             "exact evidence; reference-only/excluded/unverifiable evidence never strengthens exact "
             "confidence.")


def _domain_summary(exact_items: Sequence[Mapping],
                    exact_records_by_key: Mapping) -> List[dict]:
    """Per exact-context engineering domain: evidence count, independent sessions, improvements and
    regressions, and a convergence state derived ONLY from exact records."""
    by_domain: "Dict[str, dict]" = {}
    for it in exact_items:
        rec = exact_records_by_key.get(it.get("record_key")) or {}
        status = _lc(rec.get("outcome_status"))
        improved = status in _IMPROVED and not (rec.get("new_regressions") or [])
        worsened = status == "regression" or bool(rec.get("new_regressions") or [])
        session = _norm(rec.get("test_session_id")) or _norm(rec.get("session_date")) \
            or _norm(rec.get("record_key"))
        for dom in (it.get("domains") or ["(unmapped)"]):
            d = by_domain.setdefault(dom, {"domain": dom, "evidence_count": 0, "sessions": set(),
                                           "improvements": 0, "regressions": 0})
            d["evidence_count"] += 1
            d["sessions"].add(session)
            if improved:
                d["improvements"] += 1
            if worsened:
                d["regressions"] += 1
    out = []
    for dom in sorted(by_domain):
        d = by_domain[dom]
        indep = len(d["sessions"])
        if d["evidence_count"] == 0:
            conv = ConvergenceState.INSUFFICIENT
        elif d["regressions"] and d["improvements"]:
            conv = ConvergenceState.CONTESTED
        elif indep >= 2 and d["improvements"] and not d["regressions"]:
            conv = ConvergenceState.CONVERGED
        elif indep <= 1:
            conv = ConvergenceState.SINGLE_CONTEXT
        else:
            conv = ConvergenceState.EMERGING
        out.append({"domain": dom, "evidence_count": d["evidence_count"],
                    "independent_sessions": indep, "improvements": d["improvements"],
                    "regressions": d["regressions"], "convergence": conv.value})
    return out


def build_context_scoped_chain(scope, raw_records: Optional[Sequence[Mapping]]
                               ) -> ContextScopedKnowledgeChain:
    """Classify raw records vs the current scope, then bucket + summarise. ``scope`` may be an
    ``EngineeringContextScope`` or a context mapping. Deterministic; order-independent; never raises."""
    try:
        sc = scope if isinstance(scope, EngineeringContextScope) else build_engineering_context_scope(
            scope if isinstance(scope, Mapping) else {})
        recs = [r for r in (raw_records or []) if isinstance(r, Mapping)]
        activation = activate_context_knowledge(sc, recs)
        items = activation.items
        by_key = {_norm(r.get("record_key")): r for r in recs}

        buckets: "Dict[str, List[dict]]" = {c: [] for c in
                                            (_EXACT, _TRANSFER, _REFERENCE, _EXCLUDED, _UNVERIFIABLE)}
        for it in items:
            buckets.setdefault(it.get("classification"), []).append(it)
        exact_items = buckets[_EXACT]
        exact_keys = tuple(it["record_key"] for it in exact_items)
        exact_records = {k: by_key[k] for k in exact_keys if k in by_key}

        domain_summary = _domain_summary(exact_items, exact_records)
        transfer_overlay = [{"record_key": it["record_key"], "context": it["context"],
                             "domains": it["domains"], "transfer_level": it["transfer_level"],
                             "limitations": it["limitations"], "reason": it["reason"]}
                            for it in buckets[_TRANSFER]]
        provenance = [{"record_key": it["record_key"], "classification": it["classification"],
                       "relation": it["relation"], "reason": it["reason"]} for it in items]
        counts = dict(activation.counts)
        independence = {"exact_records": len(exact_items),
                        "exact_independent_sessions": len({
                            _norm((exact_records.get(it["record_key"]) or {}).get("test_session_id"))
                            or _norm((exact_records.get(it["record_key"]) or {}).get("session_date"))
                            or it["record_key"] for it in exact_items}),
                        "transferable_records": len(buckets[_TRANSFER]),
                        "excluded_records": len(buckets[_EXCLUDED]),
                        "note": "transferable evidence is NOT counted in exact independence."}

        # the EXACT-context fingerprint is a pure function of the exact record set + scope identity
        # only. It is INVARIANT to any quantity of incompatible/transferable evidence (Audit A proof).
        exact_fp = _fp({"scope": sc.context_fingerprint(), "exact": sorted(exact_keys),
                        "summary": [(d["domain"], d["evidence_count"], d["independent_sessions"],
                                     d["improvements"], d["regressions"], d["convergence"])
                                    for d in domain_summary],
                        "exact_independent": independence["exact_independent_sessions"]})
        # the FULL fingerprint additionally reflects history visibility (transfer/excluded membership,
        # counts) - it may change when incompatible evidence is added, but the exact fp cannot.
        fp = _fp({"exact_fp": exact_fp,
                  "transfer": sorted(t["record_key"] for t in transfer_overlay),
                  "counts": counts})
        return ContextScopedKnowledgeChain(
            scope=sc.to_dict(), completeness=sc.completeness().value, counts=counts,
            exact_domain_summary=tuple(domain_summary), transfer_overlay=tuple(transfer_overlay),
            provenance=tuple(provenance), exact_record_keys=exact_keys, independence=independence,
            doctrine=_DOCTRINE, exact_content_fingerprint=exact_fp, content_fingerprint=fp)
    except Exception:  # pragma: no cover - defensive
        return ContextScopedKnowledgeChain(
            scope={}, completeness="insufficient", counts={}, exact_domain_summary=(),
            transfer_overlay=(), provenance=(), exact_record_keys=(), independence={},
            doctrine=_DOCTRINE, exact_content_fingerprint=_fp({"e": 1}),
            content_fingerprint=_fp({"e": 1}))


def exact_records(raw_records: Optional[Sequence[Mapping]],
                  chain: ContextScopedKnowledgeChain) -> List[dict]:
    """Return the raw record dicts whose keys are exact-context for the given chain (helper for the
    downstream Phase 40/41 authorities, which reason over exact records only)."""
    keys = set(chain.exact_record_keys)
    return [r for r in (raw_records or []) if isinstance(r, Mapping)
            and _norm(r.get("record_key")) in keys]


def scoped_chain_versions() -> dict:
    return {"context_scoped_chain": CONTEXT_SCOPED_CHAIN_VERSION,
            "engineering_context_scope": ENGINEERING_CONTEXT_SCOPE_VERSION,
            "contextual_knowledge_activation": CONTEXTUAL_KNOWLEDGE_ACTIVATION_VERSION,
            "schema": CONTEXT_SCOPED_CHAIN_SCHEMA}
