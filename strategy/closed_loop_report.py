"""Closed-Loop Engineering Report — knowledge-update proposal + next action (Program 2, Phase 41).

The deterministic closure of the engineering loop. Given the run plan and the reconciled run outcome it
produces a READ-ONLY proposal of what the existing authorities WOULD learn if the outcome is explicitly
recorded (it writes nothing through a new path), and it recommends exactly ONE primary next engineering
action, with non-conflicting secondary actions.

Doctrine:
  * An invalid / confounded / insufficient run cannot modify a proven working window.
  * A coaching-only run may update driver-development knowledge but never setup working windows.
  * A multi-field regression proposes "isolate a field", not field-level causal confirmation.
  * The report never applies a setup, creates an experiment, or persists an outcome; it references the
    existing explicit workflows and the frozen Apply gate.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import List, Mapping, Optional, Sequence, Tuple

CLOSED_LOOP_REPORT_VERSION = "closed_loop_report_v1"
CLOSED_LOOP_REPORT_SCHEMA = 1

_ADVISORY = ("Read-only, advisory-only closed-loop report. The knowledge-update items are a PROPOSAL of "
             "what the existing authorities would learn IF the outcome is explicitly recorded through "
             "the existing user-controlled workflow - nothing is written, applied, promoted or created "
             "here. A setup is only ever the current best-known for an exact context, never ultimate.")


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{CLOSED_LOOP_REPORT_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


class NextAction(str, Enum):
    CONFIRM = "confirm"
    REPEAT = "repeat"
    REFINE = "refine"
    REVERSE = "reverse"
    ROLL_BACK = "roll_back"
    ISOLATE_FIELD = "isolate_field"
    TEST_COMPETING_MECHANISM = "test_competing_mechanism"
    COLLECT_TELEMETRY = "collect_missing_telemetry"
    COACHING_ONLY_RUN = "coaching_only_run"
    FREEZE_AND_STRATEGY = "freeze_setup_and_prepare_strategy"
    STOP_EVENT_TOO_CLOSE = "stop_development_event_too_close"
    ACCEPT_BEST_KNOWN = "accept_current_best_known"
    COLLECT_BASELINE = "collect_controlled_baseline"


@dataclass(frozen=True)
class KnowledgeUpdateItem:
    kind: str
    detail: str
    applies_only_if_recorded: bool = True

    def to_dict(self) -> dict:
        return {"kind": self.kind, "detail": self.detail,
                "applies_only_if_recorded": self.applies_only_if_recorded}


@dataclass(frozen=True)
class ClosedLoopEngineeringReport:
    context_fingerprint: str
    run_plan_fingerprint: str
    outcome_fingerprint: str
    validity: str
    outcome_state: str
    promotion_eligibility: str
    knowledge_update_proposal: Tuple[dict, ...]
    primary_next_action: dict
    secondary_actions: Tuple[dict, ...]
    empty_state: str
    advisory_statement: str
    content_fingerprint: str
    schema_version: int = CLOSED_LOOP_REPORT_SCHEMA
    eval_version: str = CLOSED_LOOP_REPORT_VERSION

    def to_dict(self) -> dict:
        return {"context_fingerprint": self.context_fingerprint,
                "run_plan_fingerprint": self.run_plan_fingerprint,
                "outcome_fingerprint": self.outcome_fingerprint, "validity": self.validity,
                "outcome_state": self.outcome_state,
                "promotion_eligibility": self.promotion_eligibility,
                "knowledge_update_proposal": [dict(k) for k in self.knowledge_update_proposal],
                "primary_next_action": dict(self.primary_next_action),
                "secondary_actions": [dict(a) for a in self.secondary_actions],
                "empty_state": self.empty_state, "advisory_statement": self.advisory_statement,
                "content_fingerprint": self.content_fingerprint,
                "schema_version": self.schema_version, "eval_version": self.eval_version}


def _knowledge_update(outcome: Mapping, run_plan: Mapping, attribution: Optional[Mapping],
                      counts_for_learning: bool, coaching_only: bool) -> List[KnowledgeUpdateItem]:
    items: List[KnowledgeUpdateItem] = []
    comparison = outcome.get("comparison") or {}
    promotion = outcome.get("promotion") or {}
    state = _lc(comparison.get("outcome_state"))
    cc = run_plan.get("controlled_change") or {}
    is_bundle = bool(cc.get("is_bundle"))
    changes = cc.get("changes") or []

    if coaching_only:
        items.append(KnowledgeUpdateItem("driver_coaching_priority_changed",
                                         "update driver-development / coaching progression only - a "
                                         "coaching-only run does NOT change any setup working window."))
        return items

    if not counts_for_learning:
        items.append(KnowledgeUpdateItem("no_window_change",
                                         "the run did not count for learning - it cannot modify any "
                                         "proven working window; collect a valid run instead.",
                                         applies_only_if_recorded=False))
        return items

    if state == "improved":
        for c in changes:
            items.append(KnowledgeUpdateItem("working_window_addition",
                                             f"add the tested value of '{c.get('field')}' to the "
                                             f"proven working window (exact context)."))
        if changes and not is_bundle:
            items.append(KnowledgeUpdateItem("field_direction_confirmed",
                                             f"confirm the direction of '{changes[0].get('field')}' "
                                             f"(single-field controlled improvement)."))
        elif is_bundle:
            items.append(KnowledgeUpdateItem("interaction_suspected",
                                             "the coupled bundle improved - record an interaction; do "
                                             "not confirm individual field effects yet."))
        items.append(KnowledgeUpdateItem("protected_behaviour_strengthened",
                                         "reinforce the confirmed-good behaviours that held."))
        items.append(KnowledgeUpdateItem("prediction_calibration_updated",
                                         "feed the observed-vs-expected result to prediction calibration."))
        if _lc(promotion.get("eligibility")) == "best_known_eligible":
            items.append(KnowledgeUpdateItem("candidate_retired",
                                             "retire the candidate as validated for this context."))
        else:
            items.append(KnowledgeUpdateItem("candidate_repeated",
                                             "repeat the candidate independently to confirm."))
    elif state == "regressed":
        for c in changes:
            items.append(KnowledgeUpdateItem("working_window_avoidance",
                                             f"mark the tested value/direction of '{c.get('field')}' "
                                             f"as avoidance evidence."))
        if is_bundle:
            items.append(KnowledgeUpdateItem("field_direction_suspected",
                                             "block the bundle; individual fields are SUSPECT, not "
                                             "confirmed - isolate to attribute."))
        elif changes:
            items.append(KnowledgeUpdateItem("field_direction_confirmed",
                                             f"confirm '{changes[0].get('field')}' direction as "
                                             f"causally harmful (single-field)."))
        items.append(KnowledgeUpdateItem("rollback_recommended",
                                         "recommend rolling back to the parent setup."))
        items.append(KnowledgeUpdateItem("candidate_retired",
                                         "retire or reverse the candidate."))
    elif state == "mixed":
        items.append(KnowledgeUpdateItem("transfer_limitation_added",
                                         "record the trade-off (e.g. faster lap but worse tyres/fuel/"
                                         "consistency) as a limitation."))
        items.append(KnowledgeUpdateItem("candidate_repeated",
                                         "refine and repeat to resolve the trade-off."))
    else:
        items.append(KnowledgeUpdateItem("next_experiment_recommended",
                                         "no clear directional learning - recommend the next controlled "
                                         "experiment or more evidence."))
    return items


def _primary_action(outcome: Mapping, run_plan: Mapping, counts_for_learning: bool,
                    coaching_only: bool, event_is_near: bool, no_candidate: bool) -> KnowledgeUpdateItem:
    comparison = outcome.get("comparison") or {}
    promotion = _lc((outcome.get("promotion") or {}).get("eligibility"))
    validity = _lc((outcome.get("validity") or {}).get("validity"))
    state = _lc(comparison.get("outcome_state"))
    cc = run_plan.get("controlled_change") or {}
    is_bundle = bool(cc.get("is_bundle"))

    def act(a: NextAction, detail):
        return KnowledgeUpdateItem(a.value, detail, applies_only_if_recorded=False)

    if coaching_only:
        return act(NextAction.COACHING_ONLY_RUN, "continue the coaching-only test; hold the setup "
                   "constant and verify the technique change.")
    # a completed run (any outcome state present) is reconciled by its outcome, even if no candidate
    # was formally linked; only a genuinely empty review falls back to collect-a-baseline.
    if no_candidate and not state:
        return act(NextAction.COLLECT_BASELINE, "collect a controlled baseline / validate the current "
                   "best-known setup - no candidate to test.")
    if validity in ("invalid", "context_mismatch"):
        return act(NextAction.COLLECT_TELEMETRY, "the run was not a valid test - repeat it correctly "
                   "(right setup/context) and collect complete telemetry.")
    if validity in ("confounded", "insufficient_evidence"):
        return act(NextAction.REPEAT, "repeat the run cleanly - the last run was "
                   + validity.replace("_", " ") + ".")
    if promotion == "rollback_recommended" or state == "regressed":
        if is_bundle:
            return act(NextAction.ISOLATE_FIELD, "the multi-field change regressed - roll back, then "
                       "isolate one field at a time to attribute the cause.")
        return act(NextAction.ROLL_BACK, "roll back / reverse the failed change to the parent setup.")
    if state == "mixed":
        return act(NextAction.REFINE, "refine the change to keep the gain without the trade-off, then "
                   "re-test.")
    if promotion == "best_known_eligible":
        if event_is_near:
            return act(NextAction.FREEZE_AND_STRATEGY, "the improvement is validated - freeze the setup "
                       "as current best-known and move to strategy preparation.")
        return act(NextAction.CONFIRM, "confirm and record the tested setup as the current best-known "
                   "for this exact context (through the explicit workflow; not applied automatically).")
    if promotion in ("provisional",):
        return act(NextAction.REPEAT, "repeat independently to confirm the single-session improvement.")
    if promotion in ("requires_confirmation",):
        return act(NextAction.CONFIRM, "confirm under clean conditions / the correct baseline before "
                   "promotion.")
    if state == "unchanged":
        return act(NextAction.TEST_COMPETING_MECHANISM, "no measured effect - test a competing "
                   "mechanism or collect more evidence.")
    return act(NextAction.COLLECT_TELEMETRY, "collect more evidence before deciding.")


def build_closed_loop_report(scope: Optional[Mapping], run_plan: Optional[Mapping],
                             run_outcome: Optional[Mapping], *,
                             regression_attribution: Optional[Mapping] = None,
                             event_is_near: bool = False, coaching_only: bool = False
                             ) -> ClosedLoopEngineeringReport:
    """Assemble the closed-loop report from the run plan + reconciled outcome. Deterministic; never
    raises. Writes/creates/applies/promotes NOTHING."""
    try:
        sc = scope if isinstance(scope, Mapping) else {}
        rp = run_plan if isinstance(run_plan, Mapping) else {}
        ro = run_outcome if isinstance(run_outcome, Mapping) else {}
        validity_d = ro.get("validity") or {}
        counts = bool(validity_d.get("counts_for_learning"))
        no_candidate = not ((rp.get("candidate_link") or {}).get("is_existing"))
        ku = _knowledge_update(ro, rp, regression_attribution, counts, coaching_only)
        primary = _primary_action(ro, rp, counts, coaching_only, event_is_near, no_candidate)

        # secondary actions (non-conflicting with the primary)
        secondary: List[dict] = []
        if not coaching_only and (rp.get("controlled_change") or {}).get("changes"):
            secondary.append(KnowledgeUpdateItem("protect_confirmed_good",
                                                 "keep protecting confirmed-good behaviours regardless "
                                                 "of this outcome.", applies_only_if_recorded=False)
                             .to_dict())
        if primary.kind != NextAction.FREEZE_AND_STRATEGY.value and event_is_near:
            secondary.append(KnowledgeUpdateItem("watch_deadline",
                                                 "the event is near - prefer low-risk evidence over "
                                                 "high-interaction experiments.",
                                                 applies_only_if_recorded=False).to_dict())

        empty = "" if (rp or ro) else "No run to reconcile yet."
        fp = _fp({"ctx": _norm(sc.get("context_fingerprint")),
                  "plan": _norm(rp.get("content_fingerprint")),
                  "outcome": _norm(ro.get("content_fingerprint")),
                  "validity": _lc(validity_d.get("validity")),
                  "state": _lc((ro.get("comparison") or {}).get("outcome_state")),
                  "promotion": _lc((ro.get("promotion") or {}).get("eligibility")),
                  "primary": primary.kind,
                  "knowledge": [k.kind for k in ku]})
        return ClosedLoopEngineeringReport(
            context_fingerprint=_norm(sc.get("context_fingerprint")),
            run_plan_fingerprint=_norm(rp.get("content_fingerprint")),
            outcome_fingerprint=_norm(ro.get("content_fingerprint")),
            validity=_lc(validity_d.get("validity")),
            outcome_state=_lc((ro.get("comparison") or {}).get("outcome_state")),
            promotion_eligibility=_lc((ro.get("promotion") or {}).get("eligibility")),
            knowledge_update_proposal=tuple(k.to_dict() for k in ku),
            primary_next_action=primary.to_dict(), secondary_actions=tuple(secondary),
            empty_state=empty, advisory_statement=_ADVISORY, content_fingerprint=fp)
    except Exception:  # pragma: no cover - defensive
        return ClosedLoopEngineeringReport(
            context_fingerprint="", run_plan_fingerprint="", outcome_fingerprint="", validity="",
            outcome_state="", promotion_eligibility="", knowledge_update_proposal=(),
            primary_next_action={}, secondary_actions=(), empty_state="Closed-loop report unavailable.",
            advisory_statement=_ADVISORY, content_fingerprint=_fp({"e": 1}))


def closed_loop_versions() -> dict:
    return {"closed_loop_report": CLOSED_LOOP_REPORT_VERSION, "schema": CLOSED_LOOP_REPORT_SCHEMA}
