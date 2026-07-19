"""Contradiction Cause — the visible reasons two conclusions can disagree (Program 2, Phase 29).

Enumerates the deterministic causes of an evidence contradiction and derives the applicable causes
from the compared evidence sides. A cause is emitted only when its explicit signal is present - a
context difference is read from the record contexts (never inferred), and a version / context
mismatch is always surfaced as a visible cause, never silently ignored.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises.
"""
from __future__ import annotations

from enum import Enum
from typing import List, Mapping, Tuple

CONTRADICTION_CAUSE_VERSION = "contradiction_cause_v1"


class ContradictionCause(str, Enum):
    # --- context differences (read from record contexts) ---
    DIFFERENT_CAR = "different_car"
    DIFFERENT_TRACK = "different_track"
    DIFFERENT_LAYOUT = "different_layout"
    DIFFERENT_DRIVER = "different_driver"
    DIFFERENT_COMPOUND = "different_compound"
    DIFFERENT_GT7_VERSION = "different_gt7_version"
    DIFFERENT_DISCIPLINE = "different_discipline"
    DIFFERENT_FUEL_OR_TYRE_RULE = "different_fuel_or_tyre_rule"
    DIFFERENT_BASELINE_SETUP = "different_baseline_setup"
    # --- evidence-quality differences ---
    DEPENDENT_EVIDENCE_ON_ONE_SIDE = "dependent_evidence_on_one_side"
    LOW_CONFIDENCE_EVIDENCE = "low_confidence_evidence"
    SINGLE_OBSERVATION = "single_observation"
    WITHIN_MEASUREMENT_NOISE = "within_measurement_noise"
    SUPERSEDED_BY_LATER_EVIDENCE = "superseded_by_later_evidence"
    # --- directional / structural ---
    REGRESSION_VS_CONFIRMATION = "regression_vs_confirmation"
    NON_MONOTONIC_RESPONSE = "non_monotonic_response"
    # --- residual / unexplained ---
    UNKNOWN_CONTEXT_DIFFERENCE = "unknown_context_difference"
    INSUFFICIENT_EVIDENCE_TO_EXPLAIN = "insufficient_evidence_to_explain"
    GENUINE_UNEXPLAINED_CONTRADICTION = "genuine_unexplained_contradiction"


# context field -> cause (differences are read verbatim from the record contexts).
_CONTEXT_FIELD_CAUSE = {
    "car": ContradictionCause.DIFFERENT_CAR,
    "track": ContradictionCause.DIFFERENT_TRACK,
    "layout_id": ContradictionCause.DIFFERENT_LAYOUT,
    "layout": ContradictionCause.DIFFERENT_LAYOUT,
    "driver": ContradictionCause.DIFFERENT_DRIVER,
    "compound": ContradictionCause.DIFFERENT_COMPOUND,
    "gt7_version": ContradictionCause.DIFFERENT_GT7_VERSION,
    "discipline": ContradictionCause.DIFFERENT_DISCIPLINE,
}

# context differences that let both conclusions be simultaneously true in their own contexts.
CONTEXT_RESOLVING_CAUSES = frozenset(c.value for c in (
    ContradictionCause.DIFFERENT_CAR, ContradictionCause.DIFFERENT_TRACK,
    ContradictionCause.DIFFERENT_LAYOUT, ContradictionCause.DIFFERENT_DRIVER,
    ContradictionCause.DIFFERENT_COMPOUND, ContradictionCause.DIFFERENT_GT7_VERSION,
    ContradictionCause.DIFFERENT_DISCIPLINE, ContradictionCause.DIFFERENT_FUEL_OR_TYRE_RULE))

_CAUSE_TEXT = {
    ContradictionCause.DIFFERENT_CAR: "the two sides were observed on different cars",
    ContradictionCause.DIFFERENT_TRACK: "the two sides were observed at different tracks",
    ContradictionCause.DIFFERENT_LAYOUT: "the two sides were observed on different layouts",
    ContradictionCause.DIFFERENT_DRIVER: "the two sides were observed with different drivers",
    ContradictionCause.DIFFERENT_COMPOUND: "the two sides used different tyre compounds",
    ContradictionCause.DIFFERENT_GT7_VERSION: "the two sides were observed on different GT7 versions",
    ContradictionCause.DIFFERENT_DISCIPLINE: "the two sides were observed in different disciplines",
    ContradictionCause.DIFFERENT_FUEL_OR_TYRE_RULE: "the two sides ran different fuel / tyre rules",
    ContradictionCause.DIFFERENT_BASELINE_SETUP: "the two sides started from different baselines",
    ContradictionCause.DEPENDENT_EVIDENCE_ON_ONE_SIDE: "one side rests on dependent evidence only",
    ContradictionCause.LOW_CONFIDENCE_EVIDENCE: "one or both sides are low-confidence observations",
    ContradictionCause.SINGLE_OBSERVATION: "one or both sides rest on a single observation",
    ContradictionCause.WITHIN_MEASUREMENT_NOISE: "the difference may be within measurement noise",
    ContradictionCause.SUPERSEDED_BY_LATER_EVIDENCE: "a later, stronger observation corrected an "
                                                     "earlier one",
    ContradictionCause.REGRESSION_VS_CONFIRMATION: "a confirmation and a regression were both "
                                                   "recorded for the direction",
    ContradictionCause.NON_MONOTONIC_RESPONSE: "the response may reverse beyond a point "
                                               "(non-monotonic)",
    ContradictionCause.UNKNOWN_CONTEXT_DIFFERENCE: "the contexts differ in an unrecorded way",
    ContradictionCause.INSUFFICIENT_EVIDENCE_TO_EXPLAIN: "there is too little evidence to explain "
                                                         "the disagreement",
    ContradictionCause.GENUINE_UNEXPLAINED_CONTRADICTION: "the disagreement has no contextual "
                                                          "explanation - it is a genuine open "
                                                          "contradiction",
}


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


def cause_text(cause: str) -> str:
    for c in ContradictionCause:
        if c.value == _lc(cause):
            return _CAUSE_TEXT.get(c, c.value)
    return _lc(cause)


def context_difference_causes(pos_contexts: Mapping, neg_contexts: Mapping) -> Tuple[dict, ...]:
    """Given the distinct context values on each side (``{field: set(values)}``), return the causes
    for every context field whose value sets are disjoint (a genuine difference), each with its
    visible text. Deterministic order. Never raises."""
    out: List[dict] = []
    pos = pos_contexts if isinstance(pos_contexts, Mapping) else {}
    neg = neg_contexts if isinstance(neg_contexts, Mapping) else {}
    for field in sorted(_CONTEXT_FIELD_CAUSE):
        cause = _CONTEXT_FIELD_CAUSE[field]
        pv = {v for v in (pos.get(field) or set()) if v}
        nv = {v for v in (neg.get(field) or set()) if v}
        if pv and nv and pv.isdisjoint(nv):
            out.append({"cause": cause.value, "text": _CAUSE_TEXT.get(cause, cause.value),
                        "positive_values": sorted(pv), "negative_values": sorted(nv)})
    # de-dupe by cause, keep first (deterministic).
    seen, deduped = set(), []
    for c in out:
        if c["cause"] in seen:
            continue
        seen.add(c["cause"])
        deduped.append(c)
    return tuple(deduped)


def make_cause(cause: ContradictionCause, detail: str = "") -> dict:
    return {"cause": cause.value,
            "text": _CAUSE_TEXT.get(cause, cause.value) + (f" ({detail})" if detail else "")}


def contradiction_cause_versions() -> dict:
    return {"contradiction_cause": CONTRADICTION_CAUSE_VERSION}
