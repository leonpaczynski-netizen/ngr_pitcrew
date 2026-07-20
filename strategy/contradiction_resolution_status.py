"""Contradiction Resolution Status — how (or whether) a contradiction is resolved (Phase 29).

The resolution vocabulary and the deterministic ladder that assigns it. The doctrine is strict and
enforced by tests:
- A contradiction is NEVER resolved by majority vote or averaging - counting how many records fall
  on each side decides nothing.
- Dependent evidence can NEVER defeat independent evidence, regardless of how many dependent
  observations exist.
- Newer evidence does NOT automatically win: supersession requires STRONGER later evidence, not
  merely later evidence.
- A version / context mismatch is always surfaced (as the cause) and is what resolves a
  context-explained disagreement - both conclusions can be true in their own contexts.
- A contradiction is allowed to remain UNRESOLVED - the report must be willing to say the evidence
  does not tell us which conclusion is right.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises.
"""
from __future__ import annotations

from enum import Enum
from typing import Mapping, Tuple

from strategy.contradiction_cause import (
    ContradictionCause, CONTEXT_RESOLVING_CAUSES, make_cause,
)

CONTRADICTION_RESOLUTION_STATUS_VERSION = "contradiction_resolution_status_v1"


class ContradictionStatus(str, Enum):
    NOT_A_CONTRADICTION = "not_a_contradiction"
    RESOLVED_BY_CONTEXT = "resolved_by_context"
    RESOLVED_BY_INDEPENDENCE = "resolved_by_independence"
    RESOLVED_BY_SUPERSESSION = "resolved_by_supersession"
    RESOLVED_WITHIN_NOISE = "resolved_within_noise"
    PARTIALLY_RESOLVED = "partially_resolved"
    UNRESOLVED = "unresolved"
    UNRESOLVED_INSUFFICIENT_EVIDENCE = "unresolved_insufficient_evidence"
    UNKNOWN = "unknown"


# display / ordering priority (lower = shown first): open contradictions before resolved ones.
CONTRADICTION_STATUS_PRIORITY = {
    "unresolved": 0, "unresolved_insufficient_evidence": 1, "partially_resolved": 2,
    "resolved_within_noise": 3, "resolved_by_supersession": 4, "resolved_by_independence": 5,
    "resolved_by_context": 6, "not_a_contradiction": 7, "unknown": 8,
}

RESOLVED_STATUSES = frozenset({
    "resolved_by_context", "resolved_by_independence", "resolved_by_supersession",
    "resolved_within_noise", "not_a_contradiction",
})

_NO_ACTION = ("Contradiction status only - it explains whether the evidence disagreement is "
              "context-explained, resolved by stronger independent evidence, or genuinely open. It "
              "never resolves by majority or recency, creates no test/experiment/setup, and applies "
              "nothing.")


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


def resolve(signals: Mapping) -> dict:
    """Assign a resolution status + the standing conclusion (if any) from the contradiction signals.
    Deterministic ladder; never resolves by majority or by recency alone; never raises.

    ``signals`` (all already computed, none derived by counting records for a majority):
      context_causes: tuple of context-difference cause dicts
      pos_side / neg_side: {"sessions", "high_confidence", "latest_date", "record_count"}
      independent_side: "positive" / "negative" / "" (which side is genuinely independent, if any)
      later_side / earlier_side: "positive" / "negative" / "" by date
      later_side_stronger: bool (the later side is ALSO stronger, not merely later)
      both_weak: bool (both sides single-observation / low-confidence)
    """
    try:
        return _resolve(signals if isinstance(signals, Mapping) else {})
    except Exception:
        return {"status": ContradictionStatus.UNKNOWN.value, "standing_conclusion": "",
                "resolving_causes": (), "rationale": "", "no_action_statement": _NO_ACTION}


def _resolve(s: Mapping) -> dict:
    context_causes = tuple(c for c in (s.get("context_causes") or ())
                           if isinstance(c, Mapping) and _lc(c.get("cause")) in CONTEXT_RESOLVING_CAUSES)
    independent_side = _lc(s.get("independent_side"))
    later_side = _lc(s.get("later_side"))
    later_stronger = bool(s.get("later_side_stronger"))
    both_weak = bool(s.get("both_weak"))
    pos = s.get("pos_side") or {}
    neg = s.get("neg_side") or {}

    def standing(side):
        return {"positive": "the confirming conclusion", "negative": "the regressing conclusion"}.get(
            side, "")

    # 1) context difference -> both can be true in their own contexts (version mismatch surfaced).
    if context_causes:
        fields = ", ".join(_lc(c.get("cause")).replace("different_", "").replace("_", " ")
                           for c in context_causes)
        return {"status": ContradictionStatus.RESOLVED_BY_CONTEXT.value,
                "standing_conclusion": "both conclusions hold within their own context",
                "resolving_causes": context_causes,
                "rationale": f"the sides differ in {fields}; each conclusion applies within its own "
                             "context, so this is not a single contradiction",
                "no_action_statement": _NO_ACTION}

    # 2) later AND stronger -> supersession (later alone never wins; a clear temporal order plus
    #    greater strength is what supersedes, so this is checked before the concurrent independence
    #    case below).
    if later_side in ("positive", "negative") and later_stronger:
        return {"status": ContradictionStatus.RESOLVED_BY_SUPERSESSION.value,
                "standing_conclusion": standing(later_side),
                "resolving_causes": (make_cause(ContradictionCause.SUPERSEDED_BY_LATER_EVIDENCE,
                                                f"the {later_side} side is later AND stronger"),),
                "rationale": "a later observation that is ALSO stronger supersedes the earlier one; "
                             "recency alone would not have decided this",
                "no_action_statement": _NO_ACTION}

    # 3) same context: independent evidence outweighs dependent (NEVER by count).
    if independent_side in ("positive", "negative"):
        dep_side = "negative" if independent_side == "positive" else "positive"
        return {"status": ContradictionStatus.RESOLVED_BY_INDEPENDENCE.value,
                "standing_conclusion": standing(independent_side),
                "resolving_causes": (make_cause(ContradictionCause.DEPENDENT_EVIDENCE_ON_ONE_SIDE,
                                                f"the {dep_side} side is dependent / low-confidence"),),
                "rationale": "genuinely independent evidence outweighs dependent evidence - the "
                             "independent side stands (this is not a majority vote)",
                "no_action_statement": _NO_ACTION}

    # 4) both sides weak -> within-noise / insufficient (not a genuine established contradiction).
    if both_weak:
        return {"status": ContradictionStatus.UNRESOLVED_INSUFFICIENT_EVIDENCE.value,
                "standing_conclusion": "",
                "resolving_causes": (make_cause(ContradictionCause.INSUFFICIENT_EVIDENCE_TO_EXPLAIN),),
                "rationale": "both sides are single / low-confidence observations - there is not "
                             "enough evidence to say which is right",
                "no_action_statement": _NO_ACTION}

    if not pos or not neg:
        return {"status": ContradictionStatus.UNRESOLVED_INSUFFICIENT_EVIDENCE.value,
                "standing_conclusion": "",
                "resolving_causes": (make_cause(ContradictionCause.INSUFFICIENT_EVIDENCE_TO_EXPLAIN),),
                "rationale": "one side has no comparable evidence",
                "no_action_statement": _NO_ACTION}

    # 5) same context, both comparably strong -> a genuine open contradiction.
    return {"status": ContradictionStatus.UNRESOLVED.value, "standing_conclusion": "",
            "resolving_causes": (make_cause(ContradictionCause.GENUINE_UNEXPLAINED_CONTRADICTION),),
            "rationale": "the sides share the same context and are comparably supported, yet "
                         "disagree - the evidence does not tell us which conclusion is right",
            "no_action_statement": _NO_ACTION}


def contradiction_resolution_status_versions() -> dict:
    return {"contradiction_resolution_status": CONTRADICTION_RESOLUTION_STATUS_VERSION}
