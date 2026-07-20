"""Programme Re-validation Report — pure orchestration (Program 2, Phase 26).

Assembles the read-only knowledge decay / re-validation view from the Phase-25 knowledge timeline
(the convergence authority) + the Phase-22 programme compatibility (for version/context changes).
It reuses those products verbatim - it re-derives no diagnosis, transfer, timeline or convergence
logic - and reports re-validation status only: it schedules nothing, creates no future dates, and
authors no setup or test.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import List, Mapping, Optional, Tuple

from strategy.engineering_knowledge_graph import KnowledgeDomain
from strategy.knowledge_decay import (
    KNOWLEDGE_DECAY_VERSION, programme_context_changes, decay_signals,
)
from strategy.revalidation_status import (
    REVALIDATION_STATUS_VERSION, FRESHNESS_PRIORITY, classify_revalidation,
)
from strategy.revalidation_reason import REVALIDATION_REASON_VERSION

PROGRAMME_REVALIDATION_REPORT_VERSION = "programme_revalidation_report_v1"
PROGRAMME_REVALIDATION_REPORT_SCHEMA = 1

_DOMAIN_ORDER = [d.value for d in KnowledgeDomain]
_MATURITY_RANK = {"unknown": 0, "emerging": 1, "developing": 2, "established": 3, "mature": 4,
                  "complete": 5, "plateaued": 3}
_CONFIDENCE_RANK = {"unknown": 0, "very_low": 1, "low": 2, "medium": 3, "high": 4, "very_high": 5}

_SAFETY = ("Read-only re-validation status. It reports which knowledge remains current and which "
           "may need re-validation because context / version changed or evidence weakened - dates "
           "are evidence data, never an automatic expiry; a newer record is never automatically "
           "more correct. It schedules nothing, creates no reminders or future dates, generates no "
           "test plan, and authors / applies no setup. Completion stays governed by Phase 18 and "
           "the frozen Apply gate remains the sole route to the car.")


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


@dataclass(frozen=True)
class ProgrammeRevalidationReport:
    schema_version: int
    source_programme: dict
    generated_from: dict
    items: Tuple[dict, ...]
    current_protected: Tuple[dict, ...]
    revalidation_advised: Tuple[dict, ...]
    revalidation_required: Tuple[dict, ...]
    version_invalidated: Tuple[dict, ...]
    conflict_weakened: Tuple[dict, ...]
    regression_weakened: Tuple[dict, ...]
    superseded_retired: Tuple[dict, ...]
    unknown_insufficient: Tuple[dict, ...]
    totals: dict
    empty_state: str
    safety_statement: str
    content_fingerprint: str
    knowledge_versions: dict
    eval_version: str = PROGRAMME_REVALIDATION_REPORT_VERSION

    def to_dict(self) -> dict:
        return {"schema_version": self.schema_version,
                "source_programme": dict(self.source_programme),
                "generated_from": dict(self.generated_from),
                "items": [dict(i) for i in self.items],
                "current_protected": [dict(i) for i in self.current_protected],
                "revalidation_advised": [dict(i) for i in self.revalidation_advised],
                "revalidation_required": [dict(i) for i in self.revalidation_required],
                "version_invalidated": [dict(i) for i in self.version_invalidated],
                "conflict_weakened": [dict(i) for i in self.conflict_weakened],
                "regression_weakened": [dict(i) for i in self.regression_weakened],
                "superseded_retired": [dict(i) for i in self.superseded_retired],
                "unknown_insufficient": [dict(i) for i in self.unknown_insufficient],
                "totals": dict(self.totals), "empty_state": self.empty_state,
                "safety_statement": self.safety_statement,
                "content_fingerprint": self.content_fingerprint,
                "knowledge_versions": dict(self.knowledge_versions),
                "eval_version": self.eval_version}


def build_revalidation_report(timeline: Optional[Mapping], programme_knowledge: Optional[Mapping]
                              ) -> ProgrammeRevalidationReport:
    """Assemble the re-validation report from the Phase-25 timeline + Phase-22 programme.
    Deterministic; never raises."""
    try:
        return _build(timeline or {}, programme_knowledge or {})
    except Exception as exc:   # never raise into the caller
        kv = knowledge_versions()
        return ProgrammeRevalidationReport(
            schema_version=PROGRAMME_REVALIDATION_REPORT_SCHEMA, source_programme={},
            generated_from={}, items=(), current_protected=(), revalidation_advised=(),
            revalidation_required=(), version_invalidated=(), conflict_weakened=(),
            regression_weakened=(), superseded_retired=(), unknown_insufficient=(), totals={},
            empty_state="Re-validation report unavailable.", safety_statement=_SAFETY,
            content_fingerprint=_fp({"error": type(exc).__name__, "kv": kv}),
            knowledge_versions=kv)


def _build(timeline: Mapping, programme: Mapping) -> ProgrammeRevalidationReport:
    source = dict(timeline.get("source_programme") or {})
    compatibility = programme.get("compatibility") or {}
    pc = programme_context_changes(compatibility)

    points_by_domain: dict = {}
    for p in (timeline.get("timeline_points") or []):
        if isinstance(p, Mapping):
            points_by_domain.setdefault(_lc(p.get("knowledge_domain")), []).append(p)

    items: List[dict] = []
    for c in (timeline.get("convergence_summaries") or []):
        if not isinstance(c, Mapping):
            continue
        domain = _lc(c.get("domain"))
        sig = decay_signals(c, points_by_domain.get(domain, []), pc)
        sig = dict(sig)
        sig["domain"] = domain
        items.append(classify_revalidation(sig, source).to_dict())

    items.sort(key=_order)

    def bucket(*statuses):
        return tuple(i for i in items if i["freshness_status"] in statuses)

    current_protected = bucket("current", "current_but_context_bound")
    advised = bucket("revalidation_advised")
    required = bucket("revalidation_required")
    version_inv = bucket("invalidated_by_version_change")
    conflict = bucket("weakened_by_conflict")
    regression = bucket("weakened_by_regression")
    supers = bucket("superseded", "retired")
    unknown = bucket("insufficient_date_evidence", "insufficient_context_evidence", "unknown")

    totals = {"domains": len(items),
              "current_protected": len(current_protected), "advised": len(advised),
              "required": len(required), "version_invalidated": len(version_inv),
              "conflict_weakened": len(conflict), "regression_weakened": len(regression),
              "superseded_retired": len(supers), "unknown_insufficient": len(unknown),
              "programme_version_changed": bool(pc.get("version_changed")),
              "programme_context_changed_fields": list(pc.get("changed_fields") or [])}

    kv = knowledge_versions()
    fp = _fp({"src": {k: _lc(source.get(k)) for k in ("car", "discipline", "gt7_version", "driver")},
              "items": [(i["domain"], i["freshness_status"], i["confirmed_good"],
                         [r["reason"] for r in i["reasons"]]) for i in items],
              "pc": [pc.get("version_changed"), list(pc.get("changed_fields") or [])], "kv": kv})
    empty = "" if items else ("No knowledge to assess for re-validation yet - the report appears "
                              "once the programme has recorded evidence.")
    return ProgrammeRevalidationReport(
        schema_version=PROGRAMME_REVALIDATION_REPORT_SCHEMA,
        source_programme={k: str(source.get(k, "") or "")
                          for k in ("car", "discipline", "gt7_version", "driver")},
        generated_from={"phase25_fingerprint": _lc(timeline.get("content_fingerprint")),
                        "phase22_fingerprint": _lc(programme.get("content_fingerprint")),
                        "authorities": ["Phase 22 knowledge graph", "Phase 25 convergence/timeline"]},
        items=tuple(items), current_protected=current_protected, revalidation_advised=advised,
        revalidation_required=required, version_invalidated=version_inv, conflict_weakened=conflict,
        regression_weakened=regression, superseded_retired=supers, unknown_insufficient=unknown,
        totals=totals, empty_state=empty, safety_statement=_SAFETY, content_fingerprint=fp,
        knowledge_versions=kv)


def _order(i: Mapping):
    return (FRESHNESS_PRIORITY.get(_lc(i.get("freshness_status")), 99),
            0 if i.get("confirmed_good") else 1,
            -_MATURITY_RANK.get(_lc(i.get("current_maturity")), 0),
            -_CONFIDENCE_RANK.get(_lc(i.get("current_confidence")), 0),
            _DOMAIN_ORDER.index(_lc(i.get("domain"))) if _lc(i.get("domain")) in _DOMAIN_ORDER
            else 99, _lc(i.get("domain")))


def knowledge_versions() -> dict:
    return {"programme_revalidation_report": PROGRAMME_REVALIDATION_REPORT_VERSION,
            "knowledge_decay": KNOWLEDGE_DECAY_VERSION,
            "revalidation_status": REVALIDATION_STATUS_VERSION,
            "revalidation_reason": REVALIDATION_REASON_VERSION,
            "schema": PROGRAMME_REVALIDATION_REPORT_SCHEMA}


def _fp(payload: dict) -> str:
    return (f"{PROGRAMME_REVALIDATION_REPORT_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        default=str).encode()).hexdigest()[:24])
