"""Assumption Classification — the visible taxonomy of engineering assumptions (Phase 30).

Enumerates the kinds of assumption the knowledge stack can rely on and their verification status. An
assumption is something a conclusion DEPENDS ON that is not itself directly established by evidence.
A directly-evidenced conclusion (independent, confirmed, current, in-context) is a FACT, not an
assumption, and must never be listed here.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic.
"""
from __future__ import annotations

from enum import Enum

ASSUMPTION_CLASSIFICATION_VERSION = "assumption_classification_v1"


class AssumptionType(str, Enum):
    TRANSFER_ASSUMED = "transfer_assumed"
    GENERALISATION_FROM_SINGLE_CONTEXT = "generalisation_from_single_context"
    INDEPENDENCE_ASSUMED = "independence_assumed"
    CURRENCY_ASSUMED = "currency_assumed"
    CONTEXT_COMPARABILITY_ASSUMED = "context_comparability_assumed"
    UNKNOWN_VEHICLE_ATTRIBUTE_ASSUMED = "unknown_vehicle_attribute_assumed"
    UNVERIFIED_PROXY_ASSUMED = "unverified_proxy_assumed"
    CONFIRMED_GOOD_PERSISTS_ASSUMED = "confirmed_good_persists_assumed"
    VERSION_STABILITY_ASSUMED = "version_stability_assumed"
    DRIVER_CONSISTENCY_ASSUMED = "driver_consistency_assumed"
    COMPOUND_EQUIVALENCE_ASSUMED = "compound_equivalence_assumed"
    BASELINE_EQUIVALENCE_ASSUMED = "baseline_equivalence_assumed"
    NO_INTERACTION_ASSUMED = "no_interaction_assumed"
    MONOTONIC_RESPONSE_ASSUMED = "monotonic_response_assumed"
    CONTRADICTION_SIDE_ASSUMED = "contradiction_side_assumed"
    MEASUREMENT_RELIABILITY_ASSUMED = "measurement_reliability_assumed"


class AssumptionStatus(str, Enum):
    EXPLICIT_AND_LABELLED = "explicit_and_labelled"
    EVIDENCE_BACKED_PARTIALLY = "evidence_backed_partially"
    UNVERIFIED = "unverified"
    AT_RISK = "at_risk"
    CONTRADICTED = "contradicted"
    CONSERVATIVE_BOUND = "conservative_bound"
    RESOLVED = "resolved"
    UNKNOWN = "unknown"


# display / ordering priority (lower = shown first): riskier assumptions first.
ASSUMPTION_STATUS_PRIORITY = {
    "contradicted": 0, "at_risk": 1, "unverified": 2, "evidence_backed_partially": 3,
    "conservative_bound": 4, "explicit_and_labelled": 5, "resolved": 6, "unknown": 7,
}

_TYPE_TEXT = {
    AssumptionType.TRANSFER_ASSUMED: "knowledge is assumed to transfer to another context "
                                     "(a hypothesis, not a confirmed transfer)",
    AssumptionType.GENERALISATION_FROM_SINGLE_CONTEXT: "a single-context result is assumed to "
                                                       "generalise beyond where it was observed",
    AssumptionType.INDEPENDENCE_ASSUMED: "dependent evidence is being relied on as if independent",
    AssumptionType.CURRENCY_ASSUMED: "the knowledge is assumed to still hold although it has not "
                                     "been re-validated",
    AssumptionType.CONTEXT_COMPARABILITY_ASSUMED: "two contexts are assumed comparable",
    AssumptionType.UNKNOWN_VEHICLE_ATTRIBUTE_ASSUMED: "an unknown vehicle attribute is assumed "
                                                      "(it is not recorded and never inferred)",
    AssumptionType.UNVERIFIED_PROXY_ASSUMED: "an unverified proxy is assumed to stand in for the "
                                             "real quantity",
    AssumptionType.CONFIRMED_GOOD_PERSISTS_ASSUMED: "a confirmed-good behaviour is assumed to still "
                                                    "hold without a current re-observation",
    AssumptionType.VERSION_STABILITY_ASSUMED: "the result is assumed stable across the GT7 version",
    AssumptionType.DRIVER_CONSISTENCY_ASSUMED: "the result is assumed consistent across drivers",
    AssumptionType.COMPOUND_EQUIVALENCE_ASSUMED: "the result is assumed equivalent across tyre "
                                                 "compounds",
    AssumptionType.BASELINE_EQUIVALENCE_ASSUMED: "the result is assumed to hold off a comparable "
                                                 "baseline",
    AssumptionType.NO_INTERACTION_ASSUMED: "the change is assumed not to interact with other setup "
                                           "areas",
    AssumptionType.MONOTONIC_RESPONSE_ASSUMED: "the response is assumed monotonic (no reversal "
                                               "beyond a point)",
    AssumptionType.CONTRADICTION_SIDE_ASSUMED: "one side of an unresolved contradiction is assumed "
                                               "to be the correct one",
    AssumptionType.MEASUREMENT_RELIABILITY_ASSUMED: "the observation is assumed to be above "
                                                    "measurement noise",
}


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


def type_text(t) -> str:
    for a in AssumptionType:
        if a.value == _lc(t):
            return _TYPE_TEXT.get(a, a.value)
    return _lc(t)


def assumption_classification_versions() -> dict:
    return {"assumption_classification": ASSUMPTION_CLASSIFICATION_VERSION}
