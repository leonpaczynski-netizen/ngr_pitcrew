"""Assisted Practice-Run Workflow (Program 2, Phase 43).

A deterministic, user-controlled state machine that turns a Phase-40 run plan into a real practice
workflow. It ASSISTS and VALIDATES; it never autonomously applies a setup, creates an experiment, binds
a session or records an outcome. The canonical Apply gate and the existing explicit experiment/outcome
workflows remain the sole mutation routes.

States: PLAN_READY, PREFLIGHT_REQUIRED, SETUP_CONFIRMATION_REQUIRED, READY_TO_RUN, RUN_ACTIVE,
RUN_COMPLETED, SESSION_BINDING_REQUIRED, OUTCOME_REVIEW_REQUIRED, READY_TO_RECORD, RECORDED, INVALID,
ABANDONED.

READY_TO_RUN is blocked when: the wrong setup is active (fingerprint mismatch), context materially
differs, a protected-good field changed unexpectedly, preflight has unresolved blockers, session
identity is missing, the candidate is stale/superseded, or the run-plan fingerprint no longer matches.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises. Applies NOTHING; a canonical setup fingerprint is trusted over a button click.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

ASSISTED_RUN_WORKFLOW_VERSION = "assisted_run_workflow_v1"
ASSISTED_RUN_WORKFLOW_SCHEMA = 1


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return f"{ASSISTED_RUN_WORKFLOW_VERSION}:" + hashlib.sha256(_dumps(payload).encode()).hexdigest()[:24]


class WorkflowState(str, Enum):
    PLAN_READY = "plan_ready"
    PREFLIGHT_REQUIRED = "preflight_required"
    SETUP_CONFIRMATION_REQUIRED = "setup_confirmation_required"
    READY_TO_RUN = "ready_to_run"
    RUN_ACTIVE = "run_active"
    RUN_COMPLETED = "run_completed"
    SESSION_BINDING_REQUIRED = "session_binding_required"
    OUTCOME_REVIEW_REQUIRED = "outcome_review_required"
    READY_TO_RECORD = "ready_to_record"
    RECORDED = "recorded"
    INVALID = "invalid"
    ABANDONED = "abandoned"


# canonical lifecycle order (semantic; fingerprint-material where the plan's meaning depends on it).
_ORDER = [WorkflowState.PLAN_READY, WorkflowState.PREFLIGHT_REQUIRED,
          WorkflowState.SETUP_CONFIRMATION_REQUIRED, WorkflowState.READY_TO_RUN,
          WorkflowState.RUN_ACTIVE, WorkflowState.RUN_COMPLETED,
          WorkflowState.SESSION_BINDING_REQUIRED, WorkflowState.OUTCOME_REVIEW_REQUIRED,
          WorkflowState.READY_TO_RECORD, WorkflowState.RECORDED]


class SetupVerification(str, Enum):
    MATCH = "match"
    MISMATCH = "mismatch"                    # wrong setup active
    UNEXPECTED_CHANGE = "unexpected_change"  # a protected/unplanned field also changed
    UNVERIFIABLE = "unverifiable"            # no canonical fingerprint to compare


@dataclass(frozen=True)
class SetupCheck:
    verification: str
    expected_fingerprint: str
    current_fingerprint: str
    unexpected_changed_fields: Tuple[str, ...]
    missing_expected_changes: Tuple[str, ...]
    reason: str

    def to_dict(self) -> dict:
        return {"verification": self.verification, "expected_fingerprint": self.expected_fingerprint,
                "current_fingerprint": self.current_fingerprint,
                "unexpected_changed_fields": list(self.unexpected_changed_fields),
                "missing_expected_changes": list(self.missing_expected_changes), "reason": self.reason}


def verify_setup(expected_setup: Optional[Mapping], current_setup: Optional[Mapping],
                 controlled_fields: Optional[Sequence[str]] = None,
                 parent_setup: Optional[Mapping] = None,
                 protected_fields: Optional[Sequence[str]] = None) -> SetupCheck:
    """Compare the expected active setup to the current canonical applied setup. A canonical fingerprint
    is trusted over any click. Detects a wrong setup (fingerprint mismatch) and an unexpected change (a
    protected/unplanned field also moved from the parent). Deterministic; never raises."""
    exp = expected_setup if isinstance(expected_setup, Mapping) else {}
    cur = current_setup if isinstance(current_setup, Mapping) else {}
    par = parent_setup if isinstance(parent_setup, Mapping) else {}
    controlled = {_norm(f) for f in (controlled_fields or [])}
    protected = {_norm(f) for f in (protected_fields or [])}
    exp_fp = _norm(exp.get("setup_hash") or exp.get("setup_fingerprint"))
    cur_fp = _norm(cur.get("setup_hash") or cur.get("setup_fingerprint"))

    cur_fields = cur.get("fields") if isinstance(cur.get("fields"), Mapping) else {}
    par_fields = par.get("fields") if isinstance(par.get("fields"), Mapping) else {}
    # fields that actually changed from the parent to the current setup
    changed = tuple(sorted({f for f in set(cur_fields) | set(par_fields)
                            if _norm(cur_fields.get(f)) != _norm(par_fields.get(f))}))
    unexpected = tuple(f for f in changed if f not in controlled)
    missing = tuple(sorted(controlled - set(changed)))
    unexpected_protected = tuple(f for f in unexpected if not protected or f in protected or True)

    if exp_fp and cur_fp and exp_fp != cur_fp:
        return SetupCheck(SetupVerification.MISMATCH.value, exp_fp, cur_fp, unexpected, missing,
                          "the active setup fingerprint does not match the expected setup - wrong setup.")
    if unexpected:
        return SetupCheck(SetupVerification.UNEXPECTED_CHANGE.value, exp_fp, cur_fp, unexpected, missing,
                          "an unplanned field also changed from the parent: " + ", ".join(unexpected)
                          + " - the run would be confounded.")
    if not (exp_fp and cur_fp):
        return SetupCheck(SetupVerification.UNVERIFIABLE.value, exp_fp, cur_fp, unexpected, missing,
                          "no canonical setup fingerprint available to verify - do not trust a click "
                          "alone; confirm the setup manually.")
    return SetupCheck(SetupVerification.MATCH.value, exp_fp, cur_fp, unexpected, missing,
                      "the active setup matches the expected setup.")


@dataclass(frozen=True)
class AssistedRunWorkflow:
    state: str
    blockers: Tuple[str, ...]
    setup_check: dict
    gates: dict
    next_user_action: str
    allowed_next_states: Tuple[str, ...]
    content_fingerprint: str
    schema_version: int = ASSISTED_RUN_WORKFLOW_SCHEMA
    eval_version: str = ASSISTED_RUN_WORKFLOW_VERSION

    def to_dict(self) -> dict:
        return {"state": self.state, "blockers": list(self.blockers),
                "setup_check": dict(self.setup_check), "gates": dict(self.gates),
                "next_user_action": self.next_user_action,
                "allowed_next_states": list(self.allowed_next_states),
                "content_fingerprint": self.content_fingerprint,
                "schema_version": self.schema_version, "eval_version": self.eval_version}


def evaluate_assisted_run_workflow(*, run_plan: Optional[Mapping] = None,
                                   applied_setup: Optional[Mapping] = None,
                                   expected_setup: Optional[Mapping] = None,
                                   parent_setup: Optional[Mapping] = None,
                                   preflight: Optional[Mapping] = None,
                                   material_trust: Optional[Mapping] = None,
                                   session_identity: Optional[Mapping] = None,
                                   candidate_stale: bool = False, plan_fingerprint_current: str = "",
                                   confirmations: Optional[Mapping] = None,
                                   lifecycle: str = "plan_ready") -> AssistedRunWorkflow:
    """Compute the current workflow state + blockers + setup verification from the run situation and the
    user's explicit confirmations. Deterministic; never raises. Never advances past a gate the user has
    not confirmed, and never enters READY_TO_RUN while any blocker holds."""
    try:
        rp = run_plan if isinstance(run_plan, Mapping) else {}
        conf = confirmations if isinstance(confirmations, Mapping) else {}
        life = _lc(lifecycle)

        if life == "abandoned":
            return _result(WorkflowState.ABANDONED, (), _unverifiable_check(),
                           {}, "none - run abandoned.", ())

        controlled = [c.get("field") for c in ((rp.get("controlled_change") or {}).get("changes") or [])]
        protected = [_norm(p) for p in (rp.get("_protected_fields") or [])]
        setup_check = verify_setup(expected_setup, applied_setup, controlled, parent_setup, protected)

        # ---- blockers (prevent READY_TO_RUN) ----
        blockers: List[str] = []
        pf = preflight if isinstance(preflight, Mapping) else {}
        pf_blockers = [_norm(b) for b in (pf.get("blockers") or []) if _norm(b)]
        preflight_ok = bool(pf) and pf.get("ok") is True and not pf_blockers
        if pf_blockers:
            blockers.append("preflight blocker(s): " + "; ".join(pf_blockers))
        if setup_check.verification == SetupVerification.MISMATCH.value:
            blockers.append("wrong setup active (fingerprint mismatch)")
        if setup_check.verification == SetupVerification.UNEXPECTED_CHANGE.value:
            blockers.append("an unplanned/protected field changed - the run would be confounded")
        mt = material_trust if isinstance(material_trust, Mapping) else {}
        if mt and _lc(mt.get("overall_trust")) in ("incompatible", "reference_only"):
            blockers.append("context materially differs (" + _lc(mt.get("overall_trust")) + ")")
        if not (session_identity or {}):
            blockers.append("required session identity is missing")
        if candidate_stale:
            blockers.append("the selected candidate is stale / superseded")
        plan_fp = _norm(rp.get("content_fingerprint"))
        if plan_fingerprint_current and plan_fp and _norm(plan_fingerprint_current) != plan_fp:
            blockers.append("the run-plan fingerprint no longer matches the current plan")

        setup_confirmed = bool(conf.get("setup_confirmed"))
        session_confirmed = bool(conf.get("session_confirmed"))
        outcome_confirmed = bool(conf.get("outcome_confirmed"))

        gates = {"preflight_ok": preflight_ok,
                 "setup_verified": setup_check.verification == SetupVerification.MATCH.value,
                 "setup_confirmed": setup_confirmed, "context_ok": not any(
                     b.startswith("context materially") for b in blockers),
                 "no_blockers": not blockers,
                 "session_identity": bool(session_identity or {})}

        # ---- state selection (never advance past an unconfirmed gate) ----
        if not rp:
            state = WorkflowState.PLAN_READY
            action = "no run plan yet."
        elif life in ("run_active",) and not blockers:
            state = WorkflowState.RUN_ACTIVE
            action = "run in progress - collecting clean laps."
        elif life in ("run_completed", "session_binding_required") and not blockers:
            state = (WorkflowState.SESSION_BINDING_REQUIRED if life != "run_completed"
                     else WorkflowState.RUN_COMPLETED)
            action = "select and confirm the telemetry session that represents this run."
        elif life == "outcome_review_required" and session_confirmed:
            state = (WorkflowState.READY_TO_RECORD if outcome_confirmed
                     else WorkflowState.OUTCOME_REVIEW_REQUIRED)
            action = ("confirm to record the outcome via the existing experiment workflow."
                      if outcome_confirmed else "review the outcome; nothing is recorded until you "
                      "confirm.")
        elif life == "recorded":
            state = WorkflowState.RECORDED
            action = "outcome recorded through the canonical workflow."
        elif blockers and life in ("ready_to_run", "run_active", "run_completed",
                                   "session_binding_required", "outcome_review_required"):
            state = WorkflowState.INVALID
            action = "resolve the blocker(s) before running."
        elif not preflight_ok:
            state = WorkflowState.PREFLIGHT_REQUIRED
            action = "run the canonical experiment preflight and resolve any blockers."
        elif not setup_confirmed or setup_check.verification != SetupVerification.MATCH.value:
            state = WorkflowState.SETUP_CONFIRMATION_REQUIRED
            action = ("explicitly confirm the intended setup is active (fingerprint verified); "
                      "no setup is applied here.")
        elif blockers:
            state = WorkflowState.INVALID
            action = "resolve the blocker(s) before running."
        else:
            state = WorkflowState.READY_TO_RUN
            action = "begin the run when ready; hold everything else constant."

        allowed = _allowed_next(state)
        fp = _fp({"state": state.value, "blockers": sorted(blockers),
                  "setup": setup_check.verification, "gates": {k: gates[k] for k in sorted(gates)},
                  "plan": plan_fp})
        return _result(state, tuple(blockers), setup_check.to_dict(), gates, action, allowed, fp)
    except Exception:  # pragma: no cover - defensive
        return _result(WorkflowState.INVALID, ("workflow unavailable",), _unverifiable_check(), {},
                       "unavailable.", ())


def _allowed_next(state: WorkflowState) -> Tuple[str, ...]:
    common = (WorkflowState.ABANDONED.value, WorkflowState.INVALID.value)
    try:
        i = _ORDER.index(state)
        nxt = (_ORDER[i + 1].value,) if i + 1 < len(_ORDER) else ()
    except ValueError:
        nxt = ()
    return tuple(dict.fromkeys(nxt + common))


def _unverifiable_check() -> dict:
    return SetupCheck(SetupVerification.UNVERIFIABLE.value, "", "", (), (), "not evaluated.").to_dict()


def _result(state, blockers, setup_check, gates, action, allowed, fp=None) -> AssistedRunWorkflow:
    if fp is None:
        fp = _fp({"state": state.value if isinstance(state, WorkflowState) else state})
    return AssistedRunWorkflow(
        state=state.value if isinstance(state, WorkflowState) else state, blockers=tuple(blockers),
        setup_check=setup_check, gates=dict(gates), next_user_action=action,
        allowed_next_states=tuple(allowed), content_fingerprint=fp)


def workflow_versions() -> dict:
    return {"assisted_run_workflow": ASSISTED_RUN_WORKFLOW_VERSION,
            "schema": ASSISTED_RUN_WORKFLOW_SCHEMA}
