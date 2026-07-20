"""Live Programme Activity execution & start-readiness (Program 2, Phase 52).

Connects an Event Preparation activity to real setup state, telemetry, and the live workflow. It is a
deterministic READ-ONLY view of an activity's execution readiness and lifecycle — it advances no state
automatically, applies no setup, binds no session, records no outcome. Completion is gated on EXPLICIT
confirmations (session binding where telemetry is required, evidence classification, driver feedback,
debrief confirmation) — this module only reports whether those gates are satisfied.

Purity: Qt-free, DB-free, offline, deterministic, no wall-clock, never raises. No setup values.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

from strategy.event_preparation_cycle import PreparationActivityType

LIVE_ACTIVITY_VERSION = "live_activity_v1"
LIVE_ACTIVITY_SCHEMA = 1


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{LIVE_ACTIVITY_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


class LiveActivityState(str, Enum):
    PLANNED = "planned"
    PREFLIGHT = "preflight"
    READY = "ready"
    ACTIVE = "active"
    INTERRUPTED = "interrupted"
    TELEMETRY_LOST = "telemetry_lost"
    SESSION_ENDED = "session_ended"
    BINDING_REQUIRED = "binding_required"
    DEBRIEF_REQUIRED = "debrief_required"
    COMPLETED = "completed"
    INVALID = "invalid"
    ABANDONED = "abandoned"


class StartCheckStatus(str, Enum):
    OK = "ok"
    MISSING = "missing"
    MISMATCH = "mismatch"
    STALE = "stale"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class StartCheck:
    name: str
    status: StartCheckStatus
    detail: str = ""
    blocking: bool = True

    def as_payload(self) -> dict:
        return {"name": _norm(self.name), "status": self.status.value, "detail": _norm(self.detail),
                "blocking": bool(self.blocking)}


@dataclass(frozen=True)
class ActivityExecutionContext:
    """The observed execution context for one activity. Built from the cycle, applied-setup authority and
    run plan. Fields left empty/False mean 'unknown/absent' — never fabricated."""
    cycle_id: str
    activity_id: str
    activity_type: PreparationActivityType
    track: str = ""
    layout: str = ""
    car: str = ""
    discipline: str = ""
    applied_setup_fingerprint: str = ""
    expected_setup_fingerprint: str = ""     # what this activity requires (for a mismatch check)
    selected_tyre: str = ""
    target_laps: int = 0
    run_plan_present: bool = False
    telemetry_available: bool = False
    setup_restrictions_ok: bool = True
    voice_ready: bool = False
    plan_stale: bool = False
    deadline_ok: bool = True
    # activity-type specifics (only the relevant ones are consulted)
    setup_delta_present: bool = False
    preflight_done: bool = False
    held_constant: bool = False
    coaching_objective_count: int = 0
    compound_compatible: bool = False
    tyre_multiplier_known: bool = False
    fuel_multiplier_known: bool = False
    starting_fuel_window_ok: bool = False
    strategy_objective_present: bool = False

    def as_payload(self) -> dict:
        return {"cycle_id": _norm(self.cycle_id), "activity_id": _norm(self.activity_id),
                "activity_type": self.activity_type.value, "track": _norm(self.track),
                "layout": _norm(self.layout), "car": _norm(self.car), "discipline": _norm(self.discipline),
                "applied_setup_fingerprint": _norm(self.applied_setup_fingerprint),
                "expected_setup_fingerprint": _norm(self.expected_setup_fingerprint),
                "selected_tyre": _norm(self.selected_tyre), "target_laps": int(self.target_laps),
                "run_plan_present": bool(self.run_plan_present),
                "telemetry_available": bool(self.telemetry_available),
                "setup_restrictions_ok": bool(self.setup_restrictions_ok),
                "voice_ready": bool(self.voice_ready), "plan_stale": bool(self.plan_stale),
                "deadline_ok": bool(self.deadline_ok)}


@dataclass(frozen=True)
class ActivityStartReadiness:
    activity_id: str
    checks: Tuple[StartCheck, ...]
    can_start: bool
    blocking_reasons: Tuple[str, ...]
    fingerprint: str = ""

    def as_payload(self) -> dict:
        return {"activity_id": _norm(self.activity_id),
                "checks": [c.as_payload() for c in sorted(self.checks, key=lambda c: _norm(c.name))],
                "can_start": bool(self.can_start),
                "blocking_reasons": sorted(_norm(r) for r in self.blocking_reasons if _norm(r))}


# activity types that require a telemetry session (and thus binding) to complete
_TELEMETRY_REQUIRED = frozenset({
    PreparationActivityType.INSTALLATION_RUN, PreparationActivityType.BASELINE_PRACTICE,
    PreparationActivityType.SETUP_EXPERIMENT, PreparationActivityType.COACHING_RUN,
    PreparationActivityType.TYRE_TEST, PreparationActivityType.FUEL_TEST,
    PreparationActivityType.GEARING_TEST, PreparationActivityType.QUALIFYING_SIMULATION,
    PreparationActivityType.LONG_RACE_RUN, PreparationActivityType.STRATEGY_VALIDATION_RUN,
    PreparationActivityType.FINAL_SETUP_CONFIRMATION, PreparationActivityType.FREE_PRACTICE,
    PreparationActivityType.OFFICIAL_PRACTICE, PreparationActivityType.QUALIFYING,
    PreparationActivityType.RACE,
})


def requires_telemetry(activity_type: PreparationActivityType) -> bool:
    return activity_type in _TELEMETRY_REQUIRED


def assess_start_readiness(ctx: ActivityExecutionContext) -> ActivityStartReadiness:
    """Deterministic start-readiness. Produces one check per requirement; ``can_start`` is True only when
    every BLOCKING check is OK. Voice readiness and a known selected tyre are informational (non-blocking)
    — voice is off by default and a tyre may legitimately be unknown for some runs."""
    T = PreparationActivityType
    S = StartCheckStatus
    checks: List[StartCheck] = []

    def add(name, ok, detail="", blocking=True, status_when_bad=S.MISSING):
        checks.append(StartCheck(name, S.OK if ok else status_when_bad, detail, blocking))

    # universal gates
    add("active_cycle", bool(_norm(ctx.cycle_id)), "an active preparation cycle is required")
    add("activity_bound", bool(_norm(ctx.activity_id)), "the activity must belong to the cycle")
    add("event_context", bool(_norm(ctx.track) and _norm(ctx.car)), "track + car context required")
    add("discipline", bool(_norm(ctx.discipline)), "setup discipline required")
    add("run_plan", ctx.run_plan_present, "a run plan is required")
    add("setup_restrictions", ctx.setup_restrictions_ok, "setup restriction violated", True, S.MISMATCH)
    add("deadline", ctx.deadline_ok, "activity deadline passed", True, S.STALE)
    add("plan_fresh", not ctx.plan_stale, "the plan is stale — refresh before starting", True, S.STALE)
    if requires_telemetry(ctx.activity_type):
        add("telemetry", ctx.telemetry_available, "telemetry feed required for this run")
    # applied setup fingerprint (required when the activity expects a specific setup)
    if _norm(ctx.expected_setup_fingerprint):
        matches = (_norm(ctx.applied_setup_fingerprint) == _norm(ctx.expected_setup_fingerprint))
        add("applied_setup", matches, "applied setup does not match the expected fingerprint", True,
            S.MISMATCH if _norm(ctx.applied_setup_fingerprint) else S.MISSING)
    # informational (non-blocking)
    checks.append(StartCheck("voice_ready", S.OK if ctx.voice_ready else S.NOT_APPLICABLE,
                             "voice disabled by default", blocking=False))
    checks.append(StartCheck("selected_tyre", S.OK if _norm(ctx.selected_tyre) else S.NOT_APPLICABLE,
                             "tyre selection", blocking=False))

    # activity-type specifics
    at = ctx.activity_type
    if at == T.SETUP_EXPERIMENT:
        add("setup_delta", ctx.setup_delta_present, "a setup delta is required for an experiment")
        add("preflight", ctx.preflight_done, "experiment preflight required")
    elif at == T.COACHING_RUN:
        add("held_constant_setup", ctx.held_constant, "setup must be held constant for coaching", True,
            S.MISMATCH)
        add("coaching_objective", ctx.coaching_objective_count == 1,
            "exactly one active coaching objective required")
    elif at == T.TYRE_TEST:
        add("compound_compatible", ctx.compound_compatible, "compatible compound required", True, S.MISMATCH)
        add("tyre_multiplier_known", ctx.tyre_multiplier_known, "tyre multiplier must be known")
    elif at == T.FUEL_TEST:
        add("fuel_multiplier_known", ctx.fuel_multiplier_known, "fuel multiplier must be known")
        add("starting_fuel_window", ctx.starting_fuel_window_ok, "useful starting-fuel window required")
    elif at == T.QUALIFYING_SIMULATION:
        add("qualifying_setup", bool(_norm(ctx.expected_setup_fingerprint)),
            "a qualifying setup is required")
    elif at in (T.LONG_RACE_RUN, T.STRATEGY_VALIDATION_RUN):
        add("race_setup", bool(_norm(ctx.expected_setup_fingerprint)), "a race setup is required")
        add("strategy_objective", ctx.strategy_objective_present, "a strategy-evidence objective required")

    blocking_reasons = tuple(c.name for c in checks if c.blocking and c.status != S.OK)
    can_start = not blocking_reasons
    r = ActivityStartReadiness(activity_id=ctx.activity_id, checks=tuple(checks), can_start=can_start,
                               blocking_reasons=blocking_reasons, fingerprint="")
    return ActivityStartReadiness(activity_id=r.activity_id, checks=r.checks, can_start=r.can_start,
                                  blocking_reasons=r.blocking_reasons, fingerprint=_fp(r.as_payload()))


# ---------------------------------------------------------------------------
# Completion gate (explicit confirmations only)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ActivityCompletionDecision:
    can_complete: bool
    resulting_state: LiveActivityState
    missing: Tuple[str, ...]
    reason: str

    def as_payload(self) -> dict:
        return {"can_complete": bool(self.can_complete), "resulting_state": self.resulting_state.value,
                "missing": sorted(_norm(m) for m in self.missing if _norm(m)), "reason": _norm(self.reason)}


def assess_completion(
    activity_type: PreparationActivityType,
    *,
    session_bound: bool,
    evidence_classified: bool,
    feedback_present: bool,
    debrief_confirmed: bool,
    abandoned: bool = False,
    invalid: bool = False,
) -> ActivityCompletionDecision:
    """An activity may only reach COMPLETED with explicit confirmations. It is NEVER completed
    automatically. Abandoned/invalid short-circuit to their terminal states."""
    if abandoned:
        return ActivityCompletionDecision(False, LiveActivityState.ABANDONED, (), "explicitly abandoned")
    if invalid:
        return ActivityCompletionDecision(False, LiveActivityState.INVALID, (),
                                          "session invalid — cannot strengthen confidence")
    missing: List[str] = []
    if requires_telemetry(activity_type) and not session_bound:
        missing.append("explicit session binding")
    if not evidence_classified:
        missing.append("evidence classification (valid or limited)")
    if not feedback_present:
        missing.append("driver feedback")
    if not debrief_confirmed:
        missing.append("explicit debrief / outcome confirmation")
    if missing:
        # deterministic next state: what is the activity waiting on?
        if "explicit session binding" in missing:
            state = LiveActivityState.BINDING_REQUIRED
        else:
            state = LiveActivityState.DEBRIEF_REQUIRED
        return ActivityCompletionDecision(False, state, tuple(missing),
                                          "completion blocked — explicit confirmation required")
    return ActivityCompletionDecision(True, LiveActivityState.COMPLETED, (),
                                      "all completion gates satisfied by explicit confirmation")
