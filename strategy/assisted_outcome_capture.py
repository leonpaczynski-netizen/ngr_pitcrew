"""Assisted Outcome Capture (Program 2, Phase 43).

Builds a structured outcome review from a bound session's observation, reusing the canonical Phase-41
run-outcome + closed-loop authorities. It requires an EXPLICIT user confirmation before an existing
canonical outcome record would be written - it introduces NO alternative outcome table or persistence
path and writes nothing itself. Provides structured driver-feedback options aligned with canonical
findings, and a reference audit trail (no wall-clock in fingerprints).

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises. Records NOTHING.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import List, Mapping, Optional, Tuple

ASSISTED_OUTCOME_CAPTURE_VERSION = "assisted_outcome_capture_v1"
ASSISTED_OUTCOME_CAPTURE_SCHEMA = 1

# structured driver-feedback options aligned with the canonical outcome model.
FEEDBACK_OPTIONS = ("improved", "worse", "unchanged", "mixed", "could_not_judge", "not_tested")


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{ASSISTED_OUTCOME_CAPTURE_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


class CaptureReadiness(str, Enum):
    NOT_READY = "not_ready"              # no valid bound session/observation
    REVIEW_REQUIRED = "review_required"  # review present; awaiting explicit confirmation
    READY_TO_RECORD = "ready_to_record"  # user has explicitly confirmed
    BLOCKED = "blocked"                  # invalid run - cannot record as a result


@dataclass(frozen=True)
class AssistedOutcomeReview:
    readiness: str
    review: dict
    feedback_options: Tuple[str, ...]
    canonical_write_path: str
    explicit_confirmation_required: bool
    audit_trail: dict
    empty_state: str
    advisory_statement: str
    content_fingerprint: str
    schema_version: int = ASSISTED_OUTCOME_CAPTURE_SCHEMA
    eval_version: str = ASSISTED_OUTCOME_CAPTURE_VERSION

    def to_dict(self) -> dict:
        return {"readiness": self.readiness, "review": dict(self.review),
                "feedback_options": list(self.feedback_options),
                "canonical_write_path": self.canonical_write_path,
                "explicit_confirmation_required": self.explicit_confirmation_required,
                "audit_trail": dict(self.audit_trail), "empty_state": self.empty_state,
                "advisory_statement": self.advisory_statement,
                "content_fingerprint": self.content_fingerprint,
                "schema_version": self.schema_version, "eval_version": self.eval_version}


_ADVISORY = ("Read-only outcome review. Nothing is recorded until you explicitly confirm; the confirmed "
             "result is written ONLY through the existing canonical experiment-outcome workflow. No "
             "alternative outcome table or persistence path is introduced. No setup values.")


def build_assisted_outcome_review(observation: Optional[Mapping], run_plan: Optional[Mapping],
                                  scope: Optional[Mapping], *, session_bound: bool = False,
                                  outcome_confirmed: bool = False,
                                  confirmed_by: str = "", material_trust: Optional[Mapping] = None
                                  ) -> AssistedOutcomeReview:
    """Build the structured outcome review from a bound session's observation, reusing the canonical
    Phase-41 authorities. Deterministic; never raises; writes nothing."""
    try:
        from strategy.engineering_run_outcome import build_run_outcome
        from strategy.closed_loop_report import build_closed_loop_report
    except Exception:  # pragma: no cover - defensive
        return _empty("Phase-41 authorities unavailable.")
    try:
        o = observation if isinstance(observation, Mapping) else {}
        rp = run_plan if isinstance(run_plan, Mapping) else {}
        sc = scope if isinstance(scope, Mapping) else {}
        mt = material_trust if isinstance(material_trust, Mapping) else {}
        if not (session_bound and o):
            return _empty("Bind a session first - no outcome to review until a session is confirmed.")

        exact_ctx = bool(mt.get("exact_eligible")) if mt else bool(o.get("exact_context", True))
        outcome = build_run_outcome(o, rp, discipline=_lc(sc.get("discipline")),
                                    independent_repeat=bool(o.get("independent_repeat")),
                                    correct_baseline=bool(o.get("correct_baseline", True)),
                                    exact_context=exact_ctx).to_dict()
        closed = build_closed_loop_report(sc, rp, outcome,
                                          event_is_near=bool(o.get("event_is_near")),
                                          coaching_only=bool(o.get("coaching_only"))).to_dict()
        comparison = outcome.get("comparison") or {}
        validity = outcome.get("validity") or {}
        promotion = outcome.get("promotion") or {}
        review = {
            "target_problem": _norm(rp.get("controlled_change", {}).get("changes", [{}])[0].get("why")
                                    if (rp.get("controlled_change") or {}).get("changes") else
                                    "collection / validation"),
            "expected_result": (rp.get("expected_result") or {}).get("primary_expected_outcome"),
            "observed_outcome_state": comparison.get("outcome_state"),
            "driver_feedback": comparison.get("driver_feedback"),
            "protected_regressions": comparison.get("protected_regressions") or [],
            "lap_time_effect": comparison.get("lap_time_effect"),
            "consistency_effect": comparison.get("consistency_effect"),
            "tyre_effect": comparison.get("tyre_effect"), "fuel_effect": comparison.get("fuel_effect"),
            "new_regressions": comparison.get("new_regressions") or [],
            "run_validity": validity.get("validity"),
            "attribution_limitations": (mt.get("limitation_explanation") if mt else ""),
            "rollback_recommendation": (outcome.get("promotion") or {}).get("eligibility")
            == "rollback_recommended",
            "promotion_eligibility": promotion.get("eligibility"),
            "next_action": (closed.get("primary_next_action") or {}).get("kind"),
            "knowledge_update_proposal": closed.get("knowledge_update_proposal") or [],
        }
        counts_for_learning = bool(validity.get("counts_for_learning"))
        if not counts_for_learning:
            readiness = CaptureReadiness.BLOCKED
        elif outcome_confirmed:
            readiness = CaptureReadiness.READY_TO_RECORD
        else:
            readiness = CaptureReadiness.REVIEW_REQUIRED

        audit = {"confirmed_by": _norm(confirmed_by),
                 "context_fingerprint": _norm(sc.get("context_fingerprint")),
                 "applied_setup_fingerprint": _norm(o.get("applied_setup_fingerprint")),
                 "run_plan_fingerprint": _norm(rp.get("content_fingerprint")),
                 "linked_experiment": _norm(o.get("candidate_id") or o.get("experiment_id")),
                 "linked_telemetry_session": _norm(o.get("telemetry_session")),
                 "explicit_outcome_confirmation": bool(outcome_confirmed)}
        fp = _fp({"readiness": readiness.value, "outcome": outcome.get("content_fingerprint"),
                  "closed": closed.get("content_fingerprint"),
                  "audit": {k: audit[k] for k in sorted(audit)}})
        return AssistedOutcomeReview(
            readiness=readiness.value, review=review, feedback_options=FEEDBACK_OPTIONS,
            canonical_write_path=("existing experiment-outcome workflow (record_setup_experiment_outcome "
                                  "/ record_engineering_development)"),
            explicit_confirmation_required=True, audit_trail=audit, empty_state="",
            advisory_statement=_ADVISORY, content_fingerprint=fp)
    except Exception:  # pragma: no cover - defensive
        return _empty("outcome review unavailable.")


def _empty(msg: str) -> AssistedOutcomeReview:
    return AssistedOutcomeReview(
        readiness=CaptureReadiness.NOT_READY.value, review={}, feedback_options=FEEDBACK_OPTIONS,
        canonical_write_path="existing experiment-outcome workflow",
        explicit_confirmation_required=True, audit_trail={}, empty_state=msg,
        advisory_statement=_ADVISORY, content_fingerprint=_fp({"empty": msg}))


def outcome_capture_versions() -> dict:
    return {"assisted_outcome_capture": ASSISTED_OUTCOME_CAPTURE_VERSION,
            "schema": ASSISTED_OUTCOME_CAPTURE_SCHEMA}
