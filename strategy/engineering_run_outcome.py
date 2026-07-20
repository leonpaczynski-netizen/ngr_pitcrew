"""Engineering Run Outcome — run validity, expected-vs-observed, promotion eligibility (Phase 41).

The deterministic post-run reconciliation of the engineering loop. It binds the observed session to the
run plan, classifies whether the run was a valid test, compares the expected mechanism/telemetry to what
was observed, and decides whether the tested setup is eligible to be recorded as the current best-known
for this exact context. It reuses the existing experiment-outcome / reconciliation doctrine; it creates
no competing outcome record, applies nothing, and promotes nothing automatically.

Key doctrine:
  * Only ``VALID`` or ``VALID_WITH_LIMITATIONS`` runs may influence working windows, calibration or
    promotion.
  * A faster single lap ALONE never establishes improvement when consistency, tyres, fuel, a protected
    behaviour, or test validity contradict it.
  * A setup may only be "current best-known for an exact context", never universally optimal / ultimate.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import List, Mapping, Optional, Tuple

ENGINEERING_RUN_OUTCOME_VERSION = "engineering_run_outcome_v1"
ENGINEERING_RUN_OUTCOME_SCHEMA = 1


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _b(v) -> bool:
    return bool(v)


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{ENGINEERING_RUN_OUTCOME_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


class RunValidity(str, Enum):
    VALID = "valid"
    VALID_WITH_LIMITATIONS = "valid_with_limitations"
    INVALID = "invalid"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CONFOUNDED = "confounded"
    CONTEXT_MISMATCH = "context_mismatch"


class OutcomeState(str, Enum):
    IMPROVED = "improved"
    REGRESSED = "regressed"
    UNCHANGED = "unchanged"
    MIXED = "mixed"
    INCONCLUSIVE = "inconclusive"
    NOT_TESTED = "not_tested"


class PromotionEligibility(str, Enum):
    BEST_KNOWN_ELIGIBLE = "best_known_eligible"
    PROVISIONAL = "provisional"
    REQUIRES_CONFIRMATION = "requires_confirmation"
    NOT_ELIGIBLE = "not_eligible"
    ROLLBACK_RECOMMENDED = "rollback_recommended"
    SUPERSEDED = "superseded"
    CONTEXT_LIMITED = "context_limited"


@dataclass(frozen=True)
class RunValidityAssessment:
    validity: str
    failed_gates: Tuple[str, ...]
    limitations: Tuple[str, ...]
    counts_for_learning: bool
    reason: str

    def to_dict(self) -> dict:
        return {"validity": self.validity, "failed_gates": list(self.failed_gates),
                "limitations": list(self.limitations), "counts_for_learning": self.counts_for_learning,
                "reason": self.reason}


@dataclass(frozen=True)
class ExpectedObservedComparison:
    outcome_state: str
    mechanism_match: str
    lap_time_effect: str
    consistency_effect: str
    tyre_effect: str
    fuel_effect: str
    protected_regressions: Tuple[str, ...]
    new_regressions: Tuple[str, ...]
    driver_feedback: str
    reason: str

    def to_dict(self) -> dict:
        return {"outcome_state": self.outcome_state, "mechanism_match": self.mechanism_match,
                "lap_time_effect": self.lap_time_effect, "consistency_effect": self.consistency_effect,
                "tyre_effect": self.tyre_effect, "fuel_effect": self.fuel_effect,
                "protected_regressions": list(self.protected_regressions),
                "new_regressions": list(self.new_regressions), "driver_feedback": self.driver_feedback,
                "reason": self.reason}


@dataclass(frozen=True)
class SetupPromotionEligibility:
    eligibility: str
    considerations: Tuple[dict, ...]
    reason: str

    def to_dict(self) -> dict:
        return {"eligibility": self.eligibility,
                "considerations": [dict(c) for c in self.considerations], "reason": self.reason}


@dataclass(frozen=True)
class EngineeringRunOutcome:
    session_binding: dict
    validity: dict
    comparison: dict
    promotion: dict
    content_fingerprint: str
    schema_version: int = ENGINEERING_RUN_OUTCOME_SCHEMA
    eval_version: str = ENGINEERING_RUN_OUTCOME_VERSION

    def to_dict(self) -> dict:
        return {"session_binding": dict(self.session_binding), "validity": dict(self.validity),
                "comparison": dict(self.comparison), "promotion": dict(self.promotion),
                "content_fingerprint": self.content_fingerprint,
                "schema_version": self.schema_version, "eval_version": self.eval_version}


def assess_run_validity(observation: Mapping, run_plan: Optional[Mapping] = None
                        ) -> RunValidityAssessment:
    """Classify whether the observed session is a valid test of the run plan. Deterministic; the most
    severe failed gate decides the state. Never raises."""
    o = observation if isinstance(observation, Mapping) else {}
    failed: List[str] = []
    limitations: List[str] = []

    if not _b(o.get("candidate_tested", True)):
        failed.append("the candidate was never actually tested")
        return RunValidityAssessment(RunValidity.INVALID.value, tuple(failed), (), False,
                                     "the candidate was not tested - not a result.")
    # wrong setup applied -> INVALID
    if o.get("applied_setup_matches_plan") is False:
        failed.append("the setup that was applied did not match the run plan")
        return RunValidityAssessment(RunValidity.INVALID.value, tuple(failed), (), False,
                                     "the wrong setup was applied - this session is not the "
                                     "experiment's result.")
    # material context mismatch -> CONTEXT_MISMATCH
    if o.get("context_matches_plan") is False:
        failed.append("the context differed materially from the plan")
        return RunValidityAssessment(RunValidity.CONTEXT_MISMATCH.value, tuple(failed), (), False,
                                     "the context differed materially - not comparable.")
    # confounders
    confounders = []
    if _b(o.get("unplanned_field_changed")):
        confounders.append("an unplanned setup field changed")
    if _b(o.get("different_technique_undisclosed")):
        confounders.append("the driver tested a different technique without disclosure")
    if _b(o.get("weather_changed")):
        confounders.append("weather / grip changed materially")
    if o.get("compound_used") and o.get("planned_compound") \
            and _lc(o.get("compound_used")) != _lc(o.get("planned_compound")):
        confounders.append("the wrong tyre compound was used")
    if confounders:
        return RunValidityAssessment(RunValidity.CONFOUNDED.value, tuple(confounders), (), False,
                                     "confounded run: " + "; ".join(confounders) + ".")
    # insufficient evidence
    insufficient = []
    if not _b(o.get("telemetry_complete", True)):
        insufficient.append("telemetry is incomplete")
    if _b(o.get("interrupted")):
        insufficient.append("the run was interrupted")
    clean = int(o.get("clean_laps") or 0)
    min_clean = int(o.get("min_clean_required") or 0)
    if min_clean and clean < min_clean:
        insufficient.append(f"only {clean} clean lap(s) (min {min_clean})")
    if insufficient:
        return RunValidityAssessment(RunValidity.INSUFFICIENT_EVIDENCE.value, tuple(insufficient), (),
                                     False, "insufficient evidence: " + "; ".join(insufficient) + ".")
    # minor limitations -> valid with limitations
    if o.get("tyre_within_window") is False:
        limitations.append("tyre age outside the planned window")
    if o.get("fuel_within_window") is False:
        limitations.append("fuel load outside the planned window")
    if limitations:
        return RunValidityAssessment(RunValidity.VALID_WITH_LIMITATIONS.value, (), tuple(limitations),
                                     True, "valid with limitations: " + "; ".join(limitations) + ".")
    return RunValidityAssessment(RunValidity.VALID.value, (), (), True,
                                 "valid controlled run - counts for learning.")


def _effect(delta, better_is_negative=True) -> str:
    try:
        d = float(delta)
    except (TypeError, ValueError):
        return "unknown"
    if abs(d) < 1e-9:
        return "unchanged"
    improved = d < 0 if better_is_negative else d > 0
    return "better" if improved else "worse"


def compare_expected_observed(observation: Mapping, validity: RunValidityAssessment, *,
                              discipline: str = "") -> ExpectedObservedComparison:
    """Compare expected vs observed. A faster lap alone never establishes IMPROVED when consistency,
    tyres, fuel or a protected behaviour contradict. Deterministic; never raises."""
    o = observation if isinstance(observation, Mapping) else {}
    disc = _lc(discipline) or _lc(o.get("discipline"))
    protected = tuple(sorted({_norm(f) for f in (o.get("protected_regressed") or []) if _norm(f)}))
    new_reg = tuple(sorted({_norm(r) for r in (o.get("new_regressions") or []) if _norm(r)}))
    lap = _effect(o.get("lap_time_delta"))
    cons = _lc(o.get("consistency_effect")) or _effect(o.get("consistency_delta"))
    tyre = _lc(o.get("tyre_effect")) or "unknown"
    fuel = _lc(o.get("fuel_effect")) or "unknown"
    feedback = _lc(o.get("driver_feedback")) or "unknown"
    mech = ("matched" if _b(o.get("expected_mechanism_observed")) else
            "not_observed" if o.get("expected_mechanism_observed") is False else "unknown")

    if not validity.counts_for_learning:
        state = OutcomeState.NOT_TESTED if validity.validity in (RunValidity.INVALID.value,
                                                                 RunValidity.CONTEXT_MISMATCH.value) \
            else OutcomeState.INCONCLUSIVE
        return ExpectedObservedComparison(state.value, mech, lap, cons, tyre, fuel, protected, new_reg,
                                          feedback, "run did not count for learning (" +
                                          validity.validity + ").")

    target_improved = _b(o.get("target_metric_improved"))
    # any protected regression or critical new regression dominates.
    if protected or new_reg:
        state = OutcomeState.REGRESSED
        reason = "a protected behaviour or a new regression appeared - regressed regardless of lap time."
    else:
        # for race, consistency/tyre/fuel must not be worse for a genuine improvement.
        race_tradeoff = disc == "race" and (cons == "worse" or tyre == "worse" or fuel == "worse")
        if target_improved and lap != "worse" and not race_tradeoff:
            state = OutcomeState.IMPROVED
            reason = "the target improved without a protected regression or a material trade-off."
        elif target_improved and (race_tradeoff or lap == "worse"):
            state = OutcomeState.MIXED
            reason = ("the target (or a single lap) improved but consistency / tyres / fuel worsened - "
                      "a faster lap alone does not establish improvement for this discipline.")
        elif lap == "worse" or cons == "worse":
            state = OutcomeState.REGRESSED
            reason = "the measured pace or consistency worsened."
        elif lap == "unchanged" and not target_improved:
            state = OutcomeState.UNCHANGED
            reason = "no material change was measured."
        else:
            state = OutcomeState.INCONCLUSIVE
            reason = "the evidence does not clearly establish a direction."
    return ExpectedObservedComparison(state.value, mech, lap, cons, tyre, fuel, protected, new_reg,
                                      feedback, reason)


def assess_promotion(observation: Mapping, validity: RunValidityAssessment,
                     comparison: ExpectedObservedComparison, *, discipline: str = "",
                     independent_repeat: bool = False, correct_baseline: bool = True,
                     exact_context: bool = True) -> SetupPromotionEligibility:
    """Decide best-known promotion eligibility. Deterministic; never mutates; never raises."""
    o = observation if isinstance(observation, Mapping) else {}
    cons: List[dict] = []

    def note(k, ok, detail):
        cons.append({"factor": k, "ok": bool(ok), "detail": detail})

    valid = validity.validity in (RunValidity.VALID.value, RunValidity.VALID_WITH_LIMITATIONS.value)
    improved = comparison.outcome_state == OutcomeState.IMPROVED.value
    regressed = comparison.outcome_state == OutcomeState.REGRESSED.value
    mixed = comparison.outcome_state == OutcomeState.MIXED.value
    clean = int(o.get("clean_laps") or 0)
    min_clean = int(o.get("min_clean_required") or 0)
    protected_ok = not comparison.protected_regressions and not comparison.new_regressions

    note("exact_context", exact_context, "evaluated for the exact current context")
    note("valid_run", valid, validity.validity)
    note("clean_laps", not min_clean or clean >= min_clean, f"{clean}/{min_clean or '-'} clean laps")
    note("target_improved", improved, comparison.outcome_state)
    note("protected_intact", protected_ok, "no protected regression / new critical regression")
    note("independent_repeat", independent_repeat, "repeated with independent evidence")
    note("correct_baseline", correct_baseline, "compared against the correct baseline")

    if not exact_context:
        elig = PromotionEligibility.CONTEXT_LIMITED
        reason = "evidence is not for the exact context - context-limited, not promotable here."
    elif regressed or comparison.protected_regressions:
        elig = PromotionEligibility.ROLLBACK_RECOMMENDED
        reason = "a regression or protected-behaviour loss - roll back / reverse; not promotable."
    elif not valid:
        elig = PromotionEligibility.NOT_ELIGIBLE
        reason = "the run did not count for learning - not promotable."
    elif mixed:
        elig = PromotionEligibility.NOT_ELIGIBLE
        reason = ("mixed outcome (e.g. faster lap but worse consistency/tyres/fuel) - not the best-known "
                  "setup for this discipline.")
    elif not improved:
        elig = PromotionEligibility.NOT_ELIGIBLE
        reason = "no clear improvement - not promotable."
    elif not correct_baseline:
        elig = PromotionEligibility.REQUIRES_CONFIRMATION
        reason = "improved but the baseline comparison was not the correct one - confirm first."
    elif not protected_ok:
        elig = PromotionEligibility.ROLLBACK_RECOMMENDED
        reason = "a protected behaviour was damaged - not promotable."
    elif independent_repeat and (not min_clean or clean >= min_clean) \
            and validity.validity == RunValidity.VALID.value:
        elig = PromotionEligibility.BEST_KNOWN_ELIGIBLE
        reason = ("valid, improved, protected-intact and independently repeated - eligible to be "
                  "recorded as the current best-known for this exact context (still not applied "
                  "automatically; not ultimate).")
    elif validity.validity == RunValidity.VALID_WITH_LIMITATIONS.value:
        elig = PromotionEligibility.REQUIRES_CONFIRMATION
        reason = "valid-with-limitations improvement - confirm under clean conditions before promotion."
    else:
        elig = PromotionEligibility.PROVISIONAL
        reason = "valid single-session improvement - provisional; repeat independently to confirm."
    return SetupPromotionEligibility(elig.value, tuple(cons), reason)


def build_run_outcome(observation: Optional[Mapping], run_plan: Optional[Mapping] = None, *,
                      discipline: str = "", independent_repeat: bool = False,
                      correct_baseline: bool = True, exact_context: bool = True
                      ) -> EngineeringRunOutcome:
    """Full post-run reconciliation: session binding + validity + comparison + promotion. Deterministic;
    never raises."""
    try:
        o = observation if isinstance(observation, Mapping) else {}
        disc = _lc(discipline) or _lc(o.get("discipline")) or _lc((run_plan or {}).get("context", {})
                                                                  .get("discipline"))
        validity = assess_run_validity(o, run_plan)
        comparison = compare_expected_observed(o, validity, discipline=disc)
        promotion = assess_promotion(o, validity, comparison, discipline=disc,
                                     independent_repeat=independent_repeat,
                                     correct_baseline=correct_baseline, exact_context=exact_context)
        binding = {"candidate_id": _norm(o.get("candidate_id")),
                   "applied_setup": _norm(o.get("applied_setup")),
                   "parent_setup": _norm(o.get("parent_setup")),
                   "telemetry_session": _norm(o.get("telemetry_session")),
                   "clean_laps": int(o.get("clean_laps") or 0), "discipline": disc,
                   "compound_used": _norm(o.get("compound_used")),
                   "candidate_tested": _b(o.get("candidate_tested", True))}
        fp = _fp({"binding": binding, "validity": validity.validity,
                  "outcome": comparison.outcome_state, "promotion": promotion.eligibility})
        return EngineeringRunOutcome(session_binding=binding, validity=validity.to_dict(),
                                     comparison=comparison.to_dict(), promotion=promotion.to_dict(),
                                     content_fingerprint=fp)
    except Exception:  # pragma: no cover - defensive
        return EngineeringRunOutcome(session_binding={}, validity={}, comparison={}, promotion={},
                                     content_fingerprint=_fp({"e": 1}))


def run_outcome_versions() -> dict:
    return {"engineering_run_outcome": ENGINEERING_RUN_OUTCOME_VERSION,
            "schema": ENGINEERING_RUN_OUTCOME_SCHEMA}
