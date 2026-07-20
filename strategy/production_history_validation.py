"""Production-history validation — read-only health check of a real engineering history (Phase 39).

Evaluates a real production development history WITHOUT modifying it: it counts records by context
scope, and flags structural and evidential problems (missing context, orphan/broken links,
contradictory outcomes, ambiguous multi-field regressions, thin fields, coaching dimensions without
telemetry, evidence that cannot be attributed safely). It performs NO repair and NO migration.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from strategy.context_scoped_chain import build_context_scoped_chain
from strategy.regression_attribution import build_regression_attribution

PRODUCTION_HISTORY_VALIDATION_VERSION = "production_history_validation_v1"
PRODUCTION_HISTORY_VALIDATION_SCHEMA = 1

_CORE_CTX = ("driver", "car", "track", "layout_id", "discipline", "gt7_version")
_IMPROVED = ("confirmed_improvement", "partial_improvement", "improvement", "improved")


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{PRODUCTION_HISTORY_VALIDATION_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


@dataclass(frozen=True)
class ProductionHistoryValidation:
    raw_records: int
    exact_records: int
    transferable_records: int
    reference_records: int
    excluded_records: int
    unverifiable_records: int
    missing_context_fields: Tuple[dict, ...]
    orphan_setup_references: Tuple[str, ...]
    broken_lineage: Tuple[str, ...]
    missing_applied_setup_links: Tuple[str, ...]
    missing_experiment_links: Tuple[str, ...]
    missing_outcome_links: Tuple[str, ...]
    contradictory_outcomes: Tuple[dict, ...]
    ambiguous_multi_field_regressions: Tuple[dict, ...]
    fields_with_insufficient_evidence: Tuple[str, ...]
    coaching_dimensions_lacking_telemetry: Tuple[str, ...]
    unsafe_attribution: Tuple[str, ...]
    performed_repair: bool
    content_fingerprint: str
    schema_version: int = PRODUCTION_HISTORY_VALIDATION_SCHEMA
    eval_version: str = PRODUCTION_HISTORY_VALIDATION_VERSION

    def to_dict(self) -> dict:
        return {"raw_records": self.raw_records, "exact_records": self.exact_records,
                "transferable_records": self.transferable_records,
                "reference_records": self.reference_records, "excluded_records": self.excluded_records,
                "unverifiable_records": self.unverifiable_records,
                "missing_context_fields": [dict(m) for m in self.missing_context_fields],
                "orphan_setup_references": list(self.orphan_setup_references),
                "broken_lineage": list(self.broken_lineage),
                "missing_applied_setup_links": list(self.missing_applied_setup_links),
                "missing_experiment_links": list(self.missing_experiment_links),
                "missing_outcome_links": list(self.missing_outcome_links),
                "contradictory_outcomes": [dict(c) for c in self.contradictory_outcomes],
                "ambiguous_multi_field_regressions": [dict(a) for a in
                                                      self.ambiguous_multi_field_regressions],
                "fields_with_insufficient_evidence": list(self.fields_with_insufficient_evidence),
                "coaching_dimensions_lacking_telemetry": list(
                    self.coaching_dimensions_lacking_telemetry),
                "unsafe_attribution": list(self.unsafe_attribution),
                "performed_repair": self.performed_repair,
                "content_fingerprint": self.content_fingerprint,
                "schema_version": self.schema_version, "eval_version": self.eval_version}


def validate_production_history(scope, raw_records: Optional[Sequence[Mapping]]
                                ) -> ProductionHistoryValidation:
    """Read-only validation of a production history. Never modifies the input; deterministic; never
    raises."""
    try:
        recs = [r for r in (raw_records or []) if isinstance(r, Mapping)]
        chain = build_context_scoped_chain(scope, recs)
        counts = chain.counts
        exact = [r for r in recs if _norm(r.get("record_key")) in set(chain.exact_record_keys)]

        missing_ctx: List[dict] = []
        orphan: List[str] = []
        broken: List[str] = []
        no_applied: List[str] = []
        no_exp: List[str] = []
        no_outcome: List[str] = []
        for r in recs:
            rk = _norm(r.get("record_key")) or "(no key)"
            ctx = r.get("context") or {}
            miss = [f for f in _CORE_CTX if not _norm(ctx.get(f))]
            if miss:
                missing_ctx.append({"record_key": rk, "missing": miss})
            if not (r.get("changes") or []):
                orphan.append(rk)
            if not _norm(r.get("scope_fingerprint")):
                no_applied.append(rk)
            if not _norm(r.get("experiment_id")):
                no_exp.append(rk)
            if not _norm(r.get("outcome_id")):
                no_outcome.append(rk)
            # broken lineage: an outcome status that is neither a known verdict nor empty
            st = _lc(r.get("outcome_status"))
            if st and st not in _IMPROVED + ("regression", "no_change", "neutral", "unchanged",
                                             "insufficient_evidence", "confounded", "inconclusive"):
                broken.append(rk)

        # contradictory outcomes: same (field,direction) with both improvement and regression (exact)
        fd_states: "Dict[Tuple[str, str], set]" = {}
        field_counts: "Dict[str, int]" = {}
        for r in exact:
            improved = _lc(r.get("outcome_status")) in _IMPROVED and not (r.get("new_regressions") or [])
            worsened = _lc(r.get("outcome_status")) == "regression" or bool(r.get("new_regressions")
                                                                            or [])
            for c in (r.get("changes") or []):
                f, d = _norm(c.get("field")), _lc(c.get("direction"))
                if not f:
                    continue
                field_counts[f] = field_counts.get(f, 0) + 1
                s = fd_states.setdefault((f, d), set())
                if improved:
                    s.add("improved")
                if worsened:
                    s.add("worsened")
        contradictory = tuple({"field": f, "direction": d} for (f, d), s in sorted(fd_states.items())
                              if "improved" in s and "worsened" in s)
        thin_fields = tuple(sorted(f for f, n in field_counts.items() if n == 1))

        # ambiguous multi-field regressions + unsafe attribution (from the Phase-39 attribution)
        attr = build_regression_attribution(exact)
        ambiguous = tuple({"fields": b["fields"], "state": b["state"]} for b in attr.bundles
                          if len(b["fields"]) > 1
                          and b["state"] in ("bundle_regression_confirmed", "interaction_suspected"))
        unsafe = tuple(sorted({f"{f['field']}:{f['direction']}" for f in attr.suspect_field_directions}))

        # coaching dimensions lacking telemetry: exact records with a change but no residual telemetry
        no_telemetry = tuple(sorted({_norm(r.get("record_key")) for r in exact
                                     if (r.get("changes") or []) and not (r.get("residual_states")
                                                                          or [])}))

        fp = _fp({"raw": len(recs), "counts": counts, "missing": missing_ctx, "orphan": sorted(orphan),
                  "contradictory": list(contradictory), "ambiguous": list(ambiguous),
                  "thin": list(thin_fields), "unsafe": list(unsafe)})
        return ProductionHistoryValidation(
            raw_records=len(recs), exact_records=int(counts.get("exact_context", 0) or 0),
            transferable_records=int(counts.get("explicitly_transferable", 0) or 0),
            reference_records=int(counts.get("reference_only", 0) or 0),
            excluded_records=int(counts.get("excluded", 0) or 0),
            unverifiable_records=int(counts.get("unverifiable", 0) or 0),
            missing_context_fields=tuple(missing_ctx), orphan_setup_references=tuple(sorted(orphan)),
            broken_lineage=tuple(sorted(broken)), missing_applied_setup_links=tuple(sorted(no_applied)),
            missing_experiment_links=tuple(sorted(no_exp)),
            missing_outcome_links=tuple(sorted(no_outcome)), contradictory_outcomes=contradictory,
            ambiguous_multi_field_regressions=ambiguous,
            fields_with_insufficient_evidence=thin_fields,
            coaching_dimensions_lacking_telemetry=no_telemetry, unsafe_attribution=unsafe,
            performed_repair=False, content_fingerprint=fp)
    except Exception:  # pragma: no cover - defensive
        return ProductionHistoryValidation(
            raw_records=0, exact_records=0, transferable_records=0, reference_records=0,
            excluded_records=0, unverifiable_records=0, missing_context_fields=(),
            orphan_setup_references=(), broken_lineage=(), missing_applied_setup_links=(),
            missing_experiment_links=(), missing_outcome_links=(), contradictory_outcomes=(),
            ambiguous_multi_field_regressions=(), fields_with_insufficient_evidence=(),
            coaching_dimensions_lacking_telemetry=(), unsafe_attribution=(), performed_repair=False,
            content_fingerprint=_fp({"e": 1}))


def production_validation_versions() -> dict:
    return {"production_history_validation": PRODUCTION_HISTORY_VALIDATION_VERSION,
            "schema": PRODUCTION_HISTORY_VALIDATION_SCHEMA}
