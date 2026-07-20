"""Knowledge Timeline — ordered evidence transitions per engineering domain (Phase 25).

A deterministic, READ-ONLY reconstruction of how each domain's engineering understanding evolved:
one ``TimelinePoint`` per material evidence transition, in a fully explicit order (evidence date
as data, then a stable event/session sequence, then domain / transition enum order, then stable
source and point ids). Dates are evidence data - a newer record never automatically overrides an
older stronger finding.

It reuses ``evidence_independence`` (is this a genuinely new line?) and ``knowledge_transition``
(what did this evidence change?). It carries NO setup values. Purity: Qt-free, DB-free, UI-free,
network-free, AI-free; no random, no wall-clock; deterministic; never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import List, Mapping, Optional, Sequence, Tuple

from strategy.engineering_knowledge_graph import KnowledgeDomain
from strategy.evidence_independence import assess_independence, independence_summary
from strategy.knowledge_transition import (
    KNOWLEDGE_TRANSITION_VERSION, TRANSITION_ORDER, classify_transition, outcome_kind, _CONF_RANK,
)

KNOWLEDGE_TIMELINE_VERSION = "knowledge_timeline_v1"

_DOMAIN_ORDER = [d.value for d in KnowledgeDomain]
# Visible thresholds — how much independent evidence the narrative needs to call a domain
# confirmed-good at a point (the AUTHORITATIVE confirmed-good still comes from Phase 24).
CONFIRMED_GOOD_MIN_INDEPENDENT = 2
_UNKNOWN_DATE = "unknown"
# Sort sentinel so unknown dates order deterministically AFTER known ones.
_UNKNOWN_DATE_SORT = "9999-99-99"


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _conf_label(rank: int) -> str:
    return {0: "unknown", 1: "low", 2: "medium", 3: "high"}.get(int(rank or 0), "unknown")


@dataclass(frozen=True)
class TimelinePoint:
    point_id: str
    programme: dict
    event: dict
    evidence_date: str
    sequence_key: int
    knowledge_domain: str
    prior_state: str
    resulting_state: str
    transition_type: str
    evidence_references: Tuple[str, ...]
    evidence_independence: str
    confidence_before: str
    confidence_after: str
    maturity_before: str
    maturity_after: str
    confirmed_good_before: bool
    confirmed_good_after: bool
    negative_learning: bool
    context_limitations: Tuple[str, ...]
    transfer_limitations: Tuple[str, ...]
    rationale: str
    unknown_fields: Tuple[str, ...]

    def to_dict(self) -> dict:
        return {"point_id": self.point_id, "programme": dict(self.programme),
                "event": dict(self.event), "evidence_date": self.evidence_date,
                "sequence_key": self.sequence_key, "knowledge_domain": self.knowledge_domain,
                "prior_state": self.prior_state, "resulting_state": self.resulting_state,
                "transition_type": self.transition_type,
                "evidence_references": list(self.evidence_references),
                "evidence_independence": self.evidence_independence,
                "confidence_before": self.confidence_before,
                "confidence_after": self.confidence_after,
                "maturity_before": self.maturity_before, "maturity_after": self.maturity_after,
                "confirmed_good_before": self.confirmed_good_before,
                "confirmed_good_after": self.confirmed_good_after,
                "negative_learning": self.negative_learning,
                "context_limitations": list(self.context_limitations),
                "transfer_limitations": list(self.transfer_limitations),
                "rationale": self.rationale, "unknown_fields": list(self.unknown_fields)}


def _point_id(programme: Mapping, domain: str, record_ref: str, seq: int, transition: str) -> str:
    payload = {"car": _lc((programme or {}).get("car")),
               "discipline": _lc((programme or {}).get("discipline")),
               "gt7_version": _lc((programme or {}).get("gt7_version")),
               "driver": _lc((programme or {}).get("driver")),
               "domain": _lc(domain), "ref": _lc(record_ref), "seq": int(seq),
               "transition": _lc(transition)}
    return ("tp_" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16])


def build_timeline(domains: Sequence[Mapping], source_programme: Mapping
                   ) -> Tuple[Tuple[dict, ...], dict]:
    """Build the ordered timeline points across all domains + per-domain independence summaries.
    Each ``domains`` entry: ``{"domain": str, "evidence": [ordered evidence dicts], "authority":
    {confirmed_good, transfer_limitations, context_limitations}}``. Deterministic; never raises.
    Returns ``(points, independence_by_domain)``.
    """
    try:
        return _build([d for d in (domains or []) if isinstance(d, Mapping)],
                      dict(source_programme or {}))
    except Exception:   # never raise into the caller
        return ((), {})


def _build(domains: List[Mapping], programme: Mapping) -> Tuple[Tuple[dict, ...], dict]:
    points: List[TimelinePoint] = []
    indep_by_domain: dict = {}

    for d in domains:
        domain = _lc(d.get("domain"))
        # sort evidence deterministically here (date/seq, then stable record ref) so the timeline
        # is INSERTION-ORDER INDEPENDENT regardless of the order the caller supplied.
        evidence = sorted(
            [e for e in (d.get("evidence") or []) if isinstance(e, Mapping)],
            key=lambda e: (_norm(e.get("evidence_date")) or _UNKNOWN_DATE_SORT,
                           int(e.get("sequence_key") or 0), _lc(e.get("record_ref"))))
        authority = d.get("authority") or {}
        # independence is assessed in the deterministic evidence order.
        assessments = [a.to_dict() for a in assess_independence(evidence)]
        indep_by_domain[domain] = independence_summary(assessments)

        state = {"observed": False, "positive_count": 0, "independent_lines": 0,
                 "conflicted": False, "retired": False, "confirmed_good": False,
                 "best_conf_rank": 0, "local_state": "none", "independent_scopes": set()}
        for i, ev in enumerate(evidence):
            indep = assessments[i]["independence"] if i < len(assessments) else "unknown"
            kind = outcome_kind(ev.get("outcome_status"))
            conf_rank = _CONF_RANK.get(_lc(ev.get("confidence_level")), 0)
            # decide confirmed_good_now for the narrative (Phase-24 authority gates it).
            would_be_cg = (bool(authority.get("confirmed_good")) and kind == "positive"
                           and not state["conflicted"] and not state["retired"]
                           and (state["independent_lines"] + (1 if indep == "independent" else 0))
                           >= CONFIRMED_GOOD_MIN_INDEPENDENT)
            rec = {"outcome_status": ev.get("outcome_status"),
                   "confidence_level": ev.get("confidence_level"),
                   "is_failed_direction": bool(ev.get("is_failed_direction")),
                   "confirmed_good_now": would_be_cg}
            before_conf = _conf_label(state["best_conf_rank"])
            before_state = state["local_state"]
            before_cg = state["confirmed_good"]
            tr = classify_transition(state, rec, indep)

            unknown_fields = []
            date = _norm(ev.get("evidence_date")) or _UNKNOWN_DATE
            if date == _UNKNOWN_DATE:
                unknown_fields.append("evidence_date")
            ctx = ev.get("event") or {}
            for k in ("car", "track", "discipline"):
                if not _norm(ctx.get(k)):
                    unknown_fields.append(f"event_{k}")

            after_conf_rank = max(state["best_conf_rank"], conf_rank) if kind == "positive" \
                else state["best_conf_rank"]
            points.append(TimelinePoint(
                point_id=_point_id(programme, domain, ev.get("record_ref"),
                                    int(ev.get("sequence_key") or 0), tr.transition_type),
                programme=_prog(programme), event=dict(ctx), evidence_date=date,
                sequence_key=int(ev.get("sequence_key") or 0), knowledge_domain=domain,
                prior_state=tr.prior_state, resulting_state=tr.resulting_state,
                transition_type=tr.transition_type,
                evidence_references=(_norm(ev.get("record_ref")),) if ev.get("record_ref") else (),
                evidence_independence=indep, confidence_before=before_conf,
                confidence_after=_conf_label(after_conf_rank),
                maturity_before=before_state, maturity_after=tr.resulting_state,
                confirmed_good_before=before_cg,
                confirmed_good_after=(before_cg or would_be_cg),
                negative_learning=(kind == "negative"),
                context_limitations=tuple(authority.get("context_limitations") or ()),
                transfer_limitations=tuple(authority.get("transfer_limitations") or ()),
                rationale=tr.rationale, unknown_fields=tuple(dict.fromkeys(unknown_fields))))

            # update running state.
            state["observed"] = True
            state["local_state"] = tr.resulting_state
            if kind == "positive":
                state["positive_count"] += 1
                state["best_conf_rank"] = max(state["best_conf_rank"], conf_rank)
                scope = _lc(ev.get("scope_fingerprint"))
                if indep == "independent" and scope and scope not in state["independent_scopes"]:
                    state["independent_scopes"].add(scope)
                    state["independent_lines"] += 1
                elif indep == "independent":
                    state["independent_lines"] += 1
            if tr.transition_type == "conflict_introduced":
                state["conflicted"] = True
            if tr.transition_type == "conflict_resolved":
                state["conflicted"] = False
            if tr.transition_type == "direction_retired":
                state["retired"] = True
            if tr.transition_type in ("confirmed_good_established",):
                state["confirmed_good"] = True

    ordered = sorted(points, key=_order_key)
    return tuple(p.to_dict() for p in ordered), indep_by_domain


def _order_key(p: TimelinePoint):
    date = p.evidence_date if p.evidence_date and p.evidence_date != _UNKNOWN_DATE \
        else _UNKNOWN_DATE_SORT
    return (date, int(p.sequence_key),
            _DOMAIN_ORDER.index(p.knowledge_domain) if p.knowledge_domain in _DOMAIN_ORDER else 99,
            TRANSITION_ORDER.index(p.transition_type) if p.transition_type in TRANSITION_ORDER
            else 99,
            p.evidence_references[0] if p.evidence_references else "",
            p.point_id)


def _prog(ctx: Mapping) -> dict:
    return {"car": _norm((ctx or {}).get("car")), "discipline": _norm((ctx or {}).get("discipline")),
            "gt7_version": _norm((ctx or {}).get("gt7_version")),
            "driver": _norm((ctx or {}).get("driver"))}


def timeline_versions() -> dict:
    return {"knowledge_timeline": KNOWLEDGE_TIMELINE_VERSION,
            "knowledge_transition": KNOWLEDGE_TRANSITION_VERSION}
