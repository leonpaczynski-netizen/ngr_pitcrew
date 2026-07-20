"""Canonical activity truth & consistency (Program 2, Phase 54).

Replaces the Command Centre's defaulted flags with canonical, deterministically-derived truth. For each
activity it derives the live state and the pending-binding / pending-debrief truth from PERSISTED facts
(the activity's stored state, whether a canonical binding exists, whether a canonical outcome/debrief
exists, whether candidate telemetry sessions exist). It never auto-binds, never auto-completes, and never
silently repairs an inconsistency — a read-only consistency report surfaces impossible/conflicting states.

Purity: Qt-free, DB-free, offline, deterministic, no wall-clock, never raises. No setup values.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Sequence, Tuple

from strategy.event_preparation_cycle import PreparationActivityType, PreparationActivityState
from strategy.live_activity import LiveActivityState, requires_telemetry

CANONICAL_ACTIVITY_STATE_VERSION = "canonical_activity_state_v1"


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{CANONICAL_ACTIVITY_STATE_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


# persisted activity states considered abandoned / invalid (no evidence contribution)
_ABANDONED_STATES = frozenset({PreparationActivityState.CANCELLED})
_SKIPPED_STATES = frozenset({PreparationActivityState.SKIPPED})


@dataclass(frozen=True)
class ActivityFact:
    """Persisted, canonical facts about one activity. Built from real DB rows. ``session_ended`` is set
    only when the app has detected the live run ended (never inferred from telemetry presence alone).
    ``has_binding`` / ``has_debrief_outcome`` reflect canonical rows, not defaults."""
    activity_id: str
    activity_type: PreparationActivityType
    state: PreparationActivityState = PreparationActivityState.PLANNED
    session_ended: bool = False
    has_binding: bool = False
    has_debrief_outcome: bool = False
    feedback_present: bool = False
    invalidated: bool = False
    candidate_session_count: int = 0

    @property
    def requires_telemetry(self) -> bool:
        return requires_telemetry(self.activity_type)

    @property
    def is_abandoned(self) -> bool:
        return self.state in _ABANDONED_STATES

    @property
    def is_invalid(self) -> bool:
        return bool(self.invalidated)


@dataclass(frozen=True)
class PendingBindingState:
    activity_id: str
    pending: bool
    reason: str

    def as_payload(self) -> dict:
        return {"activity_id": _norm(self.activity_id), "pending": bool(self.pending),
                "reason": _norm(self.reason)}


@dataclass(frozen=True)
class PendingDebriefState:
    activity_id: str
    pending: bool
    reason: str

    def as_payload(self) -> dict:
        return {"activity_id": _norm(self.activity_id), "pending": bool(self.pending),
                "reason": _norm(self.reason)}


def derive_pending_binding(fact: ActivityFact) -> PendingBindingState:
    """Pending binding = the run ended, candidate sessions exist, no canonical binding exists, the
    activity requires telemetry, and it was not abandoned/invalidated. Telemetry existing alone is NOT
    enough; there is no auto-bind."""
    if fact.is_abandoned or fact.is_invalid:
        return PendingBindingState(fact.activity_id, False, "activity abandoned/invalid")
    if not fact.requires_telemetry:
        return PendingBindingState(fact.activity_id, False, "activity does not require telemetry")
    if fact.has_binding:
        return PendingBindingState(fact.activity_id, False, "already bound")
    if not fact.session_ended:
        return PendingBindingState(fact.activity_id, False, "run has not ended")
    if fact.candidate_session_count <= 0:
        return PendingBindingState(fact.activity_id, False, "no candidate telemetry session")
    return PendingBindingState(fact.activity_id, True,
                               "run ended with candidate session(s) and no explicit binding")


def derive_pending_debrief(fact: ActivityFact) -> PendingDebriefState:
    """Pending debrief = a canonical binding exists, the activity requires a debrief, no canonical
    outcome/debrief exists yet, and it was not abandoned/invalidated."""
    if fact.is_abandoned or fact.is_invalid:
        return PendingDebriefState(fact.activity_id, False, "activity abandoned/invalid")
    if not fact.requires_telemetry:
        return PendingDebriefState(fact.activity_id, False, "activity requires no debrief")
    if not fact.has_binding:
        return PendingDebriefState(fact.activity_id, False, "no binding yet (binding is pending first)")
    if fact.has_debrief_outcome:
        return PendingDebriefState(fact.activity_id, False, "debrief/outcome already recorded")
    return PendingDebriefState(fact.activity_id, True, "bound session awaits an explicit debrief")


@dataclass(frozen=True)
class CanonicalActivityState:
    activity_id: str
    live_state: LiveActivityState
    pending_binding: bool
    pending_debrief: bool
    provenance: Tuple[str, ...]
    fingerprint: str = ""

    def as_payload(self) -> dict:
        return {"activity_id": _norm(self.activity_id), "live_state": self.live_state.value,
                "pending_binding": bool(self.pending_binding), "pending_debrief": bool(self.pending_debrief),
                "provenance": list(self.provenance)}


def derive_activity_state(fact: ActivityFact) -> CanonicalActivityState:
    """Deterministic live state from persisted facts. Never advances or completes; COMPLETED requires the
    persisted COMPLETED state AND a binding AND a recorded outcome AND (where relevant) feedback."""
    pb = derive_pending_binding(fact)
    pd = derive_pending_debrief(fact)
    prov: List[str] = []

    if fact.is_abandoned:
        state = LiveActivityState.ABANDONED; prov.append("persisted:cancelled")
    elif fact.is_invalid:
        state = LiveActivityState.INVALID; prov.append("persisted:invalidated")
    elif pb.pending:
        state = LiveActivityState.BINDING_REQUIRED; prov.append("derived:pending_binding")
    elif pd.pending:
        state = LiveActivityState.DEBRIEF_REQUIRED; prov.append("derived:pending_debrief")
    elif (fact.state == PreparationActivityState.COMPLETED and fact.has_binding
          and fact.has_debrief_outcome):
        state = LiveActivityState.COMPLETED; prov.append("persisted:completed+bound+outcome")
    elif fact.session_ended:
        state = LiveActivityState.SESSION_ENDED; prov.append("derived:session_ended")
    elif fact.state == PreparationActivityState.IN_PROGRESS:
        state = LiveActivityState.ACTIVE; prov.append("persisted:in_progress")
    elif fact.state == PreparationActivityState.READY:
        state = LiveActivityState.READY; prov.append("persisted:ready")
    else:
        state = LiveActivityState.PLANNED; prov.append("persisted:planned")

    cas = CanonicalActivityState(fact.activity_id, state, pb.pending, pd.pending, tuple(prov), "")
    return CanonicalActivityState(cas.activity_id, cas.live_state, cas.pending_binding, cas.pending_debrief,
                                  cas.provenance, _fp(cas.as_payload()))


# ---------------------------------------------------------------------------
# Consistency report (read-only; never repairs)
# ---------------------------------------------------------------------------

class ConsistencySeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class ConsistencyFinding:
    kind: str
    severity: ConsistencySeverity
    message: str
    activity_id: str = ""

    def as_payload(self) -> dict:
        return {"kind": _norm(self.kind), "severity": self.severity.value, "message": _norm(self.message),
                "activity_id": _norm(self.activity_id)}


@dataclass(frozen=True)
class ActivityStateConsistencyReport:
    findings: Tuple[ConsistencyFinding, ...]
    consistent: bool
    fingerprint: str = ""

    def as_payload(self) -> dict:
        return {"findings": [f.as_payload() for f in
                             sorted(self.findings, key=lambda f: (f.kind, f.activity_id))],
                "consistent": bool(self.consistent)}


@dataclass(frozen=True)
class ConsistencyInputs:
    """Cross-cutting facts for the consistency checks. All from canonical rows."""
    cycle_complete: bool = False
    selected_cycle_exists: bool = True
    setup_locked: bool = False
    has_explicit_lock_record: bool = False
    strategy_finalised: bool = False
    race_setup_locked: bool = False
    race_setup_required_for_strategy: bool = True
    binding_cross_cycle_activity_ids: Tuple[str, ...] = field(default_factory=tuple)
    debrief_wrong_discipline_activity_ids: Tuple[str, ...] = field(default_factory=tuple)


def check_consistency(facts: Sequence[ActivityFact],
                      inputs: ConsistencyInputs) -> ActivityStateConsistencyReport:
    """Detect impossible/conflicting states. Read-only — NEVER repairs. Deterministic."""
    S = ConsistencySeverity
    findings: List[ConsistencyFinding] = []

    active = [f for f in facts if f.state == PreparationActivityState.IN_PROGRESS]
    for f in facts:
        # completed activity without a required binding
        if (f.state == PreparationActivityState.COMPLETED and f.requires_telemetry and not f.has_binding):
            findings.append(ConsistencyFinding("completed_without_binding", S.CRITICAL,
                                               "activity is COMPLETED but requires a binding it does not have",
                                               f.activity_id))
        # debrief/outcome recorded without a session binding
        if f.has_debrief_outcome and f.requires_telemetry and not f.has_binding:
            findings.append(ConsistencyFinding("debrief_without_session", S.CRITICAL,
                                               "a debrief/outcome exists without a bound session", f.activity_id))
        # active activity after event completion
        if inputs.cycle_complete and f.state == PreparationActivityState.IN_PROGRESS:
            findings.append(ConsistencyFinding("active_after_event_complete", S.WARNING,
                                               "an activity is active after the event is complete", f.activity_id))

    if len(active) >= 2:
        findings.append(ConsistencyFinding("two_active_activities", S.CRITICAL,
                                           f"{len(active)} activities are simultaneously active in one cycle"))
    if inputs.setup_locked and not inputs.has_explicit_lock_record:
        findings.append(ConsistencyFinding("locked_without_record", S.CRITICAL,
                                           "setup reports LOCKED without an explicit lock record"))
    if inputs.strategy_finalised and inputs.race_setup_required_for_strategy and not inputs.race_setup_locked:
        findings.append(ConsistencyFinding("strategy_final_without_race_lock", S.CRITICAL,
                                           "strategy is finalised while the required Race setup is unlocked"))
    if not inputs.selected_cycle_exists:
        findings.append(ConsistencyFinding("selected_cycle_missing", S.CRITICAL,
                                           "the selected active cycle references a missing record"))
    for aid in inputs.binding_cross_cycle_activity_ids:
        findings.append(ConsistencyFinding("binding_cross_cycle", S.CRITICAL,
                                           "an activity is bound to a session from another cycle", aid))
    for aid in inputs.debrief_wrong_discipline_activity_ids:
        findings.append(ConsistencyFinding("debrief_wrong_discipline", S.WARNING,
                                           "a debrief is linked to another setup discipline", aid))

    consistent = not any(f.severity == S.CRITICAL for f in findings)
    r = ActivityStateConsistencyReport(tuple(findings), consistent, "")
    return ActivityStateConsistencyReport(r.findings, r.consistent, _fp(r.as_payload()))
