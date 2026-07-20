"""Controlled Practice-Run & Experiment Execution Plan (Program 2, Phase 40).

A deterministic, advisory execution plan for testing ONE existing engineering candidate in a controlled
practice run. It states exactly what changes, what is held constant, how to run and measure it, the
expected result and falsification criteria, the validity gate and stop conditions, and the rollback
plan - as READ-ONLY advice. It selects/links to an existing candidate but NEVER creates or persists an
experiment, applies a setup, bypasses preflight, schedules a campaign, or mutates canonical state.

Doctrine:
  * Minimum effective intervention - prefer one independently testable mechanism; a coupled bundle is
    labelled, its causal confidence reduced, and individual field conclusions are not promoted.
  * Base / Qualifying / Race objectives are distinct; a qualifying experiment is not transferred to the
    race setup.
  * Near an event deadline with little practice time, prefer protecting the current best-known setup and
    collecting low-risk evidence over a high-interaction experiment.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises. Authors NO setup value; applies NOTHING.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

ENGINEERING_RUN_PLAN_VERSION = "engineering_run_plan_v1"
ENGINEERING_RUN_PLAN_SCHEMA = 1

_ADVISORY = ("Read-only, advisory-only practice-run plan. It links to an EXISTING candidate and states "
             "how to test it - it creates no experiment, persists nothing, applies no setup, bypasses "
             "no preflight, and mutates no canonical state. Any actual change still goes through the "
             "existing explicit experiment workflow and the frozen Apply gate. No setup values.")


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return f"{ENGINEERING_RUN_PLAN_VERSION}:" + hashlib.sha256(_dumps(payload).encode()).hexdigest()[:24]


class CausalConfidence(str, Enum):
    SINGLE_MECHANISM = "single_mechanism"     # one field -> clean attribution
    COUPLED_BUNDLE = "coupled_bundle"         # must move together -> reduced causal confidence
    NONE = "none"


# discipline objective templates (Base/Qualifying/Race are distinct).
_OBJECTIVE = {
    "qualifying": {"primary_goal": "maximise one-lap pace",
                   "optimise": ["one-lap pace", "tyre preparation", "peak grip",
                                "braking & rotation confidence", "acceleration onto major straights",
                                "one-lap gearing"],
                   "avoid": ["assuming the result transfers to the Race setup"]},
    "race": {"primary_goal": "minimise total race time with repeatable, tyre- and fuel-sustainable pace",
             "optimise": ["total race time", "repeatability", "tyre life", "traction", "fuel use",
                          "stint stability", "traffic behaviour", "pit / refuelling implications",
                          "race gearing"],
             "avoid": ["chasing a single fast lap at the cost of consistency, tyres or fuel"]},
    "base": {"primary_goal": "establish a stable, well-understood baseline",
             "optimise": ["predictable balance", "protected confirmed-good behaviour",
                          "evidence coverage"],
             "avoid": ["large coupled changes before the baseline is understood"]},
}


@dataclass(frozen=True)
class ExperimentCandidateLink:
    candidate_id: str
    source: str
    is_existing: bool
    preflight_required: bool
    note: str

    def to_dict(self) -> dict:
        return {"candidate_id": self.candidate_id, "source": self.source,
                "is_existing": self.is_existing, "preflight_required": self.preflight_required,
                "note": self.note}


@dataclass(frozen=True)
class EngineeringRunPlan:
    context: dict
    objective: dict
    controlled_change: dict
    held_constant: dict
    run_structure: dict
    expected_result: dict
    validity_gate: Tuple[str, ...]
    stop_conditions: dict
    safety_rollback: dict
    candidate_link: dict
    deadline_posture: str
    empty_state: str
    advisory_statement: str
    content_fingerprint: str
    schema_version: int = ENGINEERING_RUN_PLAN_SCHEMA
    eval_version: str = ENGINEERING_RUN_PLAN_VERSION

    def to_dict(self) -> dict:
        return {"context": dict(self.context), "objective": dict(self.objective),
                "controlled_change": dict(self.controlled_change),
                "held_constant": dict(self.held_constant), "run_structure": dict(self.run_structure),
                "expected_result": dict(self.expected_result),
                "validity_gate": list(self.validity_gate), "stop_conditions": dict(self.stop_conditions),
                "safety_rollback": dict(self.safety_rollback),
                "candidate_link": dict(self.candidate_link), "deadline_posture": self.deadline_posture,
                "empty_state": self.empty_state, "advisory_statement": self.advisory_statement,
                "content_fingerprint": self.content_fingerprint,
                "schema_version": self.schema_version, "eval_version": self.eval_version}


def _candidate_changes(candidate: Mapping, applied: Mapping) -> List[dict]:
    """Normalise the candidate's proposed change(s) into controlled-change rows with current values."""
    fields = candidate.get("changes")
    if not fields:
        f = _norm(candidate.get("field"))
        fields = [{"field": f, "direction": _norm(candidate.get("direction"))}] if f else []
    applied_fields = (applied.get("fields") if isinstance(applied.get("fields"), Mapping) else {}) \
        if isinstance(applied, Mapping) else {}
    out = []
    for c in fields:
        fld = _norm(c.get("field"))
        if not fld:
            continue
        out.append({
            "field": fld, "current_value": _norm(applied_fields.get(fld)),
            "proposed_direction": _lc(c.get("direction")) or _lc(candidate.get("direction")),
            "proposed_value": _norm(c.get("to_value") or c.get("proposed_value")),
            "why": _norm(candidate.get("hypothesis") or candidate.get("why")
                         or "test the candidate's expected mechanism"),
            "expected_mechanism": _norm(candidate.get("expected_mechanism") or c.get("mechanism")),
            "interactions": list(c.get("interactions") or candidate.get("interactions") or []),
            "rollback_value": _norm(applied_fields.get(fld)) or "prior applied value"})
    return out


def build_engineering_run_plan(scope: Optional[Mapping], *, candidate: Optional[Mapping] = None,
                               applied_setup: Optional[Mapping] = None,
                               parent_setup: Optional[Mapping] = None,
                               working_windows: Optional[Mapping] = None,
                               coaching_plan: Optional[Mapping] = None,
                               protected_behaviours: Optional[Sequence] = None,
                               available_practice_laps: Optional[int] = None,
                               event_is_near: bool = False) -> EngineeringRunPlan:
    """Build the advisory run plan for testing ``candidate`` in the current ``scope``. Deterministic;
    never raises. With no candidate it produces a truthful collection/validation posture."""
    try:
        return _build(scope or {}, candidate if isinstance(candidate, Mapping) else None,
                      applied_setup if isinstance(applied_setup, Mapping) else {},
                      parent_setup if isinstance(parent_setup, Mapping) else {},
                      working_windows if isinstance(working_windows, Mapping) else {},
                      coaching_plan if isinstance(coaching_plan, Mapping) else {},
                      list(protected_behaviours or []), available_practice_laps, bool(event_is_near))
    except Exception:  # pragma: no cover - defensive
        return EngineeringRunPlan(context={}, objective={}, controlled_change={}, held_constant={},
                                  run_structure={}, expected_result={}, validity_gate=(),
                                  stop_conditions={}, safety_rollback={}, candidate_link={},
                                  deadline_posture="", empty_state="Run plan unavailable.",
                                  advisory_statement=_ADVISORY, content_fingerprint=_fp({"e": 1}))


def _build(scope, candidate, applied, parent, windows, coaching, protected, laps, near):
    discipline = _lc(scope.get("discipline")) or "unknown"
    objective = dict(_OBJECTIVE.get(discipline, {"primary_goal": "collect evidence in this context",
                                                 "optimise": [], "avoid": []}))
    objective["discipline"] = discipline

    context = {"driver": scope.get("driver"), "car": scope.get("car"),
               "car_variant": scope.get("car_variant"), "track": scope.get("track"),
               "layout_id": scope.get("layout_id"), "event_id": scope.get("event_id"),
               "discipline": discipline, "compound": scope.get("compound"),
               "tyre_multiplier": scope.get("tyre_multiplier"),
               "fuel_multiplier": scope.get("fuel_multiplier"),
               "applied_setup": _norm((applied or {}).get("name") or (applied or {}).get("setup_id")),
               "parent_setup": _norm((parent or {}).get("name") or (parent or {}).get("setup_id")),
               "context_fingerprint": scope.get("context_fingerprint")}

    # deadline posture: near an event with little practice time -> protect + low-risk only.
    interaction_risk = _lc((candidate or {}).get("interaction_risk"))
    low_time = laps is not None and laps <= 6
    deadline_posture = ""
    if near and (low_time or interaction_risk in ("high", "medium")):
        deadline_posture = ("Event is near with limited practice time - PROTECT the current best-known "
                            "setup and collect only low-risk evidence; do NOT start a high-interaction "
                            "experiment now.")

    if candidate is None:
        empty = ("No existing candidate supplied - the plan is to validate the current best-known "
                 "setup and collect a controlled baseline, not to invent an experiment.")
        run_structure = _run_structure(discipline, [], coaching, laps)
        gate = _validity_gate(scope, [], discipline)
        return EngineeringRunPlan(
            context=context, objective=objective,
            controlled_change={"changes": [], "is_bundle": False, "bundle_reason": "",
                               "causal_confidence": CausalConfidence.NONE.value,
                               "note": "collection run - no controlled change."},
            held_constant=_held_constant(scope, applied, []), run_structure=run_structure,
            expected_result=_expected_result(None, protected), validity_gate=gate,
            stop_conditions=_stop_conditions(protected),
            safety_rollback=_safety_rollback(parent, applied, None),
            candidate_link={"candidate_id": "", "source": "none", "is_existing": False,
                            "preflight_required": False,
                            "note": "no candidate - collection/validation run."},
            deadline_posture=deadline_posture, empty_state=empty, advisory_statement=_ADVISORY,
            content_fingerprint=_fp({"ctx": context.get("context_fingerprint"), "candidate": None,
                                     "posture": deadline_posture}))

    changes = _candidate_changes(candidate, applied)
    is_bundle = len(changes) > 1
    if is_bundle:
        causal = CausalConfidence.COUPLED_BUNDLE
        bundle_reason = _norm(candidate.get("bundle_reason")
                              or "the candidate's mechanism requires these fields to move together; "
                                 "individual field effects cannot be attributed from this run alone.")
    elif changes:
        causal = CausalConfidence.SINGLE_MECHANISM
        bundle_reason = ""
    else:
        causal = CausalConfidence.NONE
        bundle_reason = ""

    controlled_change = {"changes": changes, "is_bundle": is_bundle, "bundle_reason": bundle_reason,
                         "causal_confidence": causal.value,
                         "note": ("minimum effective intervention: one testable mechanism."
                                  if not is_bundle else
                                  "coupled bundle: causal confidence reduced; do not promote individual "
                                  "field conclusions until independently isolated.")}
    changed_fields = [c["field"] for c in changes]
    cand_link = ExperimentCandidateLink(
        candidate_id=_norm(candidate.get("id") or candidate.get("candidate_id")),
        source=_norm(candidate.get("source") or "existing portfolio candidate"),
        is_existing=True, preflight_required=True,
        note="existing candidate - reference only; run it through the explicit experiment workflow "
             "and preflight; nothing is created or applied here.").to_dict()

    return EngineeringRunPlan(
        context=context, objective=objective, controlled_change=controlled_change,
        held_constant=_held_constant(scope, applied, changed_fields),
        run_structure=_run_structure(discipline, candidate.get("target_corners") or [], coaching, laps),
        expected_result=_expected_result(candidate, protected),
        validity_gate=_validity_gate(scope, changed_fields, discipline),
        stop_conditions=_stop_conditions(protected),
        safety_rollback=_safety_rollback(parent, applied, changes),
        candidate_link=cand_link, deadline_posture=deadline_posture, empty_state="",
        advisory_statement=_ADVISORY,
        content_fingerprint=_fp({"ctx": context.get("context_fingerprint"),
                                 "candidate": cand_link["candidate_id"],
                                 "changes": [(c["field"], c["proposed_direction"]) for c in changes],
                                 "bundle": is_bundle, "discipline": discipline,
                                 "posture": deadline_posture}))


def _held_constant(scope, applied, changed_fields) -> dict:
    changed = set(changed_fields)
    applied_fields = (applied.get("fields") if isinstance(applied, Mapping)
                      and isinstance(applied.get("fields"), Mapping) else {})
    held = sorted(f for f in applied_fields if f not in changed)
    return {"setup_fields_held": held,
            "technique_variables": ["braking point", "line", "throttle application", "gear usage"],
            "compound": _norm(scope.get("compound")) or "as-planned",
            "fuel_load_window": "keep within the planned fuel-load window",
            "tyre_age_window": "compare like-for-like tyre age",
            "weather_track_state": "stable, comparable grip",
            "assists": "unchanged (ABS/TC/other assists as configured)",
            "brake_balance_fuel_map": ("hold unless it IS the controlled change"),
            "note": "any unlisted setup field that moves invalidates the run."}


def _run_structure(discipline, target_corners, coaching, laps) -> dict:
    min_clean = 3
    metrics = ["lap time", "consistency (lap-time spread)", "target-corner speed", "throttle trace",
               "braking stability", "steering corrections", "gear usage"]
    if discipline == "race":
        metrics += ["tyre degradation", "fuel per lap", "stint pace stability"]
    elif discipline == "qualifying":
        metrics += ["peak single-lap grip", "out-lap tyre preparation"]
    return {"warm_up_laps": 2, "valid_measurement_laps": max(min_clean, 4),
            "minimum_clean_laps": min_clean, "maximum_run_laps": (int(laps) if laps else 12),
            "target_corners": [str(c) for c in (target_corners or [])] or ["(no specific corner)"],
            "target_metrics": metrics,
            "required_driver_feedback": ["balance on entry/mid/exit", "confidence under braking",
                                         "traction on exit", "any unexpected behaviour"],
            "comparison_baseline": "the current applied setup (parent) under matched conditions"}


def _expected_result(candidate, protected) -> dict:
    prot = [(_norm(p.get("behaviour")) if isinstance(p, Mapping) else _norm(p)) for p in (protected or [])]
    prot = [p for p in prot if p]
    primary = _norm((candidate or {}).get("expected_mechanism")
                    or (candidate or {}).get("hypothesis")) or "the targeted behaviour improves"
    return {"primary_expected_outcome": primary,
            "protected_behaviours": prot,
            "tolerated_trade_offs": ["a small, understood trade-off that does not touch a protected "
                                     "strength"],
            "unacceptable_regressions": ["any regression of a protected confirmed-good behaviour",
                                         "a new instability or safety-relevant behaviour"],
            "success_threshold": "the target metric improves over >=3 clean laps without an "
                                 "unacceptable regression",
            "failure_threshold": "the target metric worsens, or a protected behaviour regresses",
            "inconclusive_conditions": ["too few clean laps", "confounding change", "mismatched "
                                        "conditions"],
            "falsifying_observation": _norm((candidate or {}).get("falsifier")
                                            or "the expected mechanism does not appear in telemetry "
                                               "or driver feedback")}


def _validity_gate(scope, changed_fields, discipline) -> Tuple[str, ...]:
    return (
        f"the planned tyre compound ({_norm(scope.get('compound')) or 'as-planned'}) was used",
        "only the controlled field(s) changed; no other setup field moved unexpectedly",
        "at least the minimum clean-lap count was completed",
        "fuel load and tyre age stayed within the planned windows",
        "weather / grip did not change materially during the run",
        "the driver did not test a different technique simultaneously without disclosure",
        "telemetry is complete and the run was not interrupted",
        f"the setup discipline is {discipline} (a qualifying run does not validate a race setup)")


def _stop_conditions(protected) -> dict:
    return {"immediate_stop": ["a protected confirmed-good behaviour clearly regresses",
                               "a new instability or unsafe behaviour appears",
                               "conditions change materially (weather, grip, traffic)"],
            "review_rather_than_continue": ["the result looks confounded",
                                            "an unplanned field appears to have changed",
                                            "telemetry is incomplete"],
            "disposition_options": ["abandon", "reverse", "repeat", "refine"]}


def _safety_rollback(parent, applied, changes) -> dict:
    target = _norm((parent or {}).get("name") or (parent or {}).get("setup_id")) or \
        "the prior applied setup"
    return {"rollback_target": target,
            "rollback_changes": [{"field": c["field"], "restore_to": c["rollback_value"]}
                                 for c in (changes or [])],
            "immediate_stop_conditions": ["protected-behaviour regression", "new instability"],
            "review_conditions": ["confounded result", "unplanned change", "incomplete telemetry"],
            "recommended_disposition": "reverse or roll back if a protected behaviour regresses; "
                                       "otherwise repeat/refine per the outcome."}


def run_plan_versions() -> dict:
    return {"engineering_run_plan": ENGINEERING_RUN_PLAN_VERSION, "schema": ENGINEERING_RUN_PLAN_SCHEMA}
