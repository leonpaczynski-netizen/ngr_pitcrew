"""Knowledge Contradiction — detect and characterise a domain's evidence disagreement (Phase 29).

Given the positive (confirming) and negative (regressing) evidence records for ONE domain, it
computes the visible per-side signals - context spread, distinct sessions, confidence, dates - and
hands them to the resolution ladder. It counts records only to describe each side; it never uses a
record count to decide the outcome (no majority vote), and it treats independence and context, not
recency, as what can resolve a disagreement.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Mapping, Sequence, Tuple

from strategy.contradiction_cause import (
    context_difference_causes, CONTRADICTION_CAUSE_VERSION,
)
from strategy.contradiction_resolution_status import (
    CONTRADICTION_RESOLUTION_STATUS_VERSION, RESOLVED_STATUSES, resolve,
)

KNOWLEDGE_CONTRADICTION_VERSION = "knowledge_contradiction_v1"

_CONTEXT_FIELDS = ("car", "track", "layout_id", "driver", "compound", "gt7_version", "discipline")
_HIGH_CONF = ("high", "very_high")
_POSITIVE = ("confirmed_improvement", "partial_improvement")


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


@dataclass(frozen=True)
class KnowledgeContradiction:
    domain: str
    status: str
    is_open: bool
    standing_conclusion: str
    causes: Tuple[dict, ...]
    resolving_causes: Tuple[dict, ...]
    positive_summary: dict
    negative_summary: dict
    rationale: str
    no_action_statement: str
    eval_version: str = KNOWLEDGE_CONTRADICTION_VERSION

    def to_dict(self) -> dict:
        return {"domain": self.domain, "status": self.status, "is_open": self.is_open,
                "standing_conclusion": self.standing_conclusion,
                "causes": [dict(c) for c in self.causes],
                "resolving_causes": [dict(c) for c in self.resolving_causes],
                "positive_summary": dict(self.positive_summary),
                "negative_summary": dict(self.negative_summary), "rationale": self.rationale,
                "no_action_statement": self.no_action_statement, "eval_version": self.eval_version}


def _side_signals(records: Sequence[Mapping]) -> dict:
    recs = [r for r in (records or []) if isinstance(r, Mapping)]
    contexts = {f: set() for f in _CONTEXT_FIELDS}
    sessions = set()
    high_conf = False
    latest = ""
    for r in recs:
        ctx = r.get("context") or {}
        for f in _CONTEXT_FIELDS:
            v = _lc(ctx.get(f))
            if v:
                contexts[f].add(v)
        sid = _lc(r.get("test_session_id"))
        if sid:
            sessions.add(sid)
        if _lc(r.get("confidence_level")) in _HIGH_CONF:
            high_conf = True
        d = _norm(r.get("session_date"))
        if d and d > latest:
            latest = d
    return {"contexts": contexts, "sessions": len(sessions), "high_confidence": high_conf,
            "latest_date": latest, "record_count": len(recs)}


def _independent(side: dict) -> bool:
    # a side is treated as genuinely independent when it spans >= 2 distinct sessions AND carries a
    # high-confidence observation. This is an independence test, NOT a majority/count comparison.
    return int(side.get("sessions") or 0) >= 2 and bool(side.get("high_confidence"))


def _weak(side: dict) -> bool:
    return int(side.get("sessions") or 0) <= 1 and not bool(side.get("high_confidence"))


def detect_contradiction(domain: str, positive_records: Sequence[Mapping],
                         negative_records: Sequence[Mapping]) -> KnowledgeContradiction:
    """Detect and resolve ONE domain's contradiction from its confirming vs regressing records.
    Deterministic; never raises."""
    try:
        return _detect(_lc(domain), positive_records or [], negative_records or [])
    except Exception:
        return KnowledgeContradiction(
            domain=_lc(domain), status="unknown", is_open=False, standing_conclusion="", causes=(),
            resolving_causes=(), positive_summary={}, negative_summary={}, rationale="",
            no_action_statement="")


def _detect(domain: str, pos: Sequence[Mapping], neg: Sequence[Mapping]) -> KnowledgeContradiction:
    pos_sig = _side_signals(pos)
    neg_sig = _side_signals(neg)

    context_causes = context_difference_causes(pos_sig["contexts"], neg_sig["contexts"])

    pos_ind, neg_ind = _independent(pos_sig), _independent(neg_sig)
    independent_side = ""
    if pos_ind and not neg_ind:
        independent_side = "positive"
    elif neg_ind and not pos_ind:
        independent_side = "negative"

    later_side, earlier = "", ""
    if pos_sig["latest_date"] and neg_sig["latest_date"] \
            and pos_sig["latest_date"] != neg_sig["latest_date"]:
        if pos_sig["latest_date"] > neg_sig["latest_date"]:
            later_side, earlier = "positive", "negative"
        else:
            later_side, earlier = "negative", "positive"
    later_stronger = False
    if later_side:
        late = pos_sig if later_side == "positive" else neg_sig
        early = neg_sig if later_side == "positive" else pos_sig
        later_stronger = (int(late["sessions"]) > int(early["sessions"])
                          and bool(late["high_confidence"]))

    both_weak = _weak(pos_sig) and _weak(neg_sig)

    signals = {"context_causes": context_causes,
               "pos_side": pos_sig, "neg_side": neg_sig,
               "independent_side": independent_side, "later_side": later_side,
               "later_side_stronger": later_stronger, "both_weak": both_weak}
    res = resolve(signals)

    causes: List[dict] = list(context_causes)
    for c in (res.get("resolving_causes") or []):
        if c not in causes:
            causes.append(c)

    status = _lc(res.get("status"))
    is_open = status not in RESOLVED_STATUSES

    def _summ(sig):
        return {"record_count": sig["record_count"], "distinct_sessions": sig["sessions"],
                "has_high_confidence": sig["high_confidence"], "latest_date": sig["latest_date"],
                "contexts": {f: sorted(v) for f, v in sig["contexts"].items() if v}}

    return KnowledgeContradiction(
        domain=domain, status=status, is_open=is_open,
        standing_conclusion=str(res.get("standing_conclusion") or ""), causes=tuple(causes),
        resolving_causes=tuple(res.get("resolving_causes") or ()),
        positive_summary=_summ(pos_sig), negative_summary=_summ(neg_sig),
        rationale=str(res.get("rationale") or ""),
        no_action_statement=str(res.get("no_action_statement") or ""))


def knowledge_contradiction_versions() -> dict:
    return {"knowledge_contradiction": KNOWLEDGE_CONTRADICTION_VERSION,
            "contradiction_cause": CONTRADICTION_CAUSE_VERSION,
            "contradiction_resolution_status": CONTRADICTION_RESOLUTION_STATUS_VERSION}
