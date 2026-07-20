"""Evidence Independence — is apparent supporting evidence genuinely independent? (Phase 25).

A deterministic, READ-ONLY classification of whether repeated supporting evidence is truly
independent or merely duplicated / dependent. Repeated evidence from the same source chain must
NOT count as multiple independent confirmations. Every rule is visible and deterministic - there
is no probabilistic or opaque inference.

Independence unit hierarchy (finest dependency first):
  same record_key           -> SAME_SOURCE_RECORD  (one record, never double-counted)
  same test_session_id      -> SAME_SESSION        (dependent — one session)
  same scope_fingerprint    -> SAME_CAMPAIGN       (partially independent — separate session,
                                                    same investigation scope)
  different scope + session -> INDEPENDENT         (a genuinely separate evidence line)
  no session and no scope   -> UNKNOWN             (lineage cannot be established; left unknown)

The Phase-22/23/24 products that RE-STATE a conclusion are ONE lineage, not extra confirmations:
callers mark those DERIVED_FROM_EXISTING_CONCLUSION and never count them as independent support.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; no ML /
optimisation; deterministic; never raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Mapping, Sequence, Tuple

EVIDENCE_INDEPENDENCE_VERSION = "evidence_independence_v1"


class EvidenceIndependence(str, Enum):
    INDEPENDENT = "independent"
    PARTIALLY_INDEPENDENT = "partially_independent"
    SAME_SESSION = "same_session"
    SAME_CAMPAIGN = "same_campaign"
    SAME_SOURCE_RECORD = "same_source_record"
    DERIVED_FROM_EXISTING_CONCLUSION = "derived_from_existing_conclusion"
    UNKNOWN = "unknown"


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


@dataclass(frozen=True)
class IndependenceAssessment:
    record_ref: str                     # stable source id (record_key)
    session_id: str
    scope_fingerprint: str
    independence: str
    group_key: str                      # the independence group this record belongs to
    reason: str

    def to_dict(self) -> dict:
        return {"record_ref": self.record_ref, "session_id": self.session_id,
                "scope_fingerprint": self.scope_fingerprint, "independence": self.independence,
                "group_key": self.group_key, "reason": self.reason}


def assess_independence(records: Sequence[Mapping]) -> Tuple[IndependenceAssessment, ...]:
    """Classify each record's independence relative to the records BEFORE it (in the given
    order). The caller supplies records already ordered deterministically. Never raises.

    Each record needs: ``record_ref`` (stable id), ``session_id``, ``scope_fingerprint``.
    """
    try:
        return _assess([r for r in (records or []) if isinstance(r, Mapping)])
    except Exception:   # never raise into the caller
        return ()


def _assess(records: List[Mapping]) -> Tuple[IndependenceAssessment, ...]:
    seen_records = set()
    seen_sessions = set()
    seen_scopes = set()
    out: List[IndependenceAssessment] = []
    for r in records:
        ref = _lc(r.get("record_ref"))
        session = _lc(r.get("session_id"))
        scope = _lc(r.get("scope_fingerprint"))
        # group key = the independence line this record contributes to (scope first, else session).
        group = scope or session or "unknown"
        if ref and ref in seen_records:
            indep, reason = EvidenceIndependence.SAME_SOURCE_RECORD, \
                "identical source record - never counted twice"
        elif session and session in seen_sessions:
            indep, reason = EvidenceIndependence.SAME_SESSION, \
                "same test session as earlier evidence - dependent, not a new confirmation"
        elif scope and scope in seen_scopes:
            indep, reason = EvidenceIndependence.SAME_CAMPAIGN, \
                "same investigation scope, a separate session - partially independent"
        elif not session and not scope:
            indep, reason = EvidenceIndependence.UNKNOWN, \
                "no session or scope recorded - independence cannot be established"
        elif not scope and session:
            indep, reason = EvidenceIndependence.PARTIALLY_INDEPENDENT, \
                "a separate session with no recorded scope - only partially independent"
        else:
            indep, reason = EvidenceIndependence.INDEPENDENT, \
                "a separate session and separate investigation scope - a genuinely independent line"
        out.append(IndependenceAssessment(record_ref=ref, session_id=session,
                                          scope_fingerprint=scope, independence=indep.value,
                                          group_key=group, reason=reason))
        if ref:
            seen_records.add(ref)
        if session:
            seen_sessions.add(session)
        if scope:
            seen_scopes.add(scope)
    return tuple(out)


def independence_summary(assessments: Sequence[Mapping]) -> dict:
    """Summarise a set of independence assessments into counts used by convergence.
    ``independent_groups`` = distinct scope lines; ``partial_sessions`` = extra separate sessions
    within a scope; ``dependent`` = same-session / same-record repeats. Never raises."""
    a = [x for x in (assessments or []) if isinstance(x, Mapping)]
    scopes = set()
    sessions = set()
    partial = same_session = same_record = unknown = 0
    for x in a:
        ind = _lc(x.get("independence"))
        if _lc(x.get("scope_fingerprint")):
            scopes.add(_lc(x.get("scope_fingerprint")))
        if _lc(x.get("session_id")):
            sessions.add(_lc(x.get("session_id")))
        if ind == EvidenceIndependence.SAME_CAMPAIGN.value:
            partial += 1
        elif ind == EvidenceIndependence.PARTIALLY_INDEPENDENT.value:
            partial += 1
        elif ind == EvidenceIndependence.SAME_SESSION.value:
            same_session += 1
        elif ind == EvidenceIndependence.SAME_SOURCE_RECORD.value:
            same_record += 1
        elif ind == EvidenceIndependence.UNKNOWN.value:
            unknown += 1
    independent_groups = len(scopes) if scopes else (
        1 if any(_lc(x.get("independence")) == EvidenceIndependence.PARTIALLY_INDEPENDENT.value
                 for x in a) else 0)
    return {"independent_groups": independent_groups,
            "distinct_sessions": len(sessions),
            "partially_independent": partial, "same_session": same_session,
            "same_source_record": same_record, "unknown": unknown, "total": len(a)}


def independence_versions() -> dict:
    return {"evidence_independence": EVIDENCE_INDEPENDENCE_VERSION}
