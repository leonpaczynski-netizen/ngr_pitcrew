"""Binding, debrief & Command Centre return workflow (Program 2, Phase 61).

Presents candidate telemetry sessions for EXPLICIT binding (reusing the canonical ranker — never defaults
to the newest), routes a bound activity to the correct debrief (reusing the canonical debrief handover),
and returns to the Event Command Centre by refreshing from canonical truth (no manually-maintained UI
flags). Cumulative event knowledge updates only after an explicitly-confirmed outcome (reusing the
Phase-52 cumulative-update gate).

Purity: Qt-free, DB-free, offline, deterministic, no wall-clock, never raises. Binds nothing itself.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional, Sequence, Tuple

from strategy.event_preparation_cycle import PreparationActivityType
from strategy.activity_binding import (
    rank_activity_sessions, assess_debrief_readiness, debrief_kind_for, plan_cumulative_update,
    DebriefKind, EvidenceClassification)

BINDING_DEBRIEF_WORKFLOW_VERSION = "binding_debrief_workflow_v1"


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _fp(payload) -> str:
    return (f"{BINDING_DEBRIEF_WORKFLOW_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        ensure_ascii=True, default=str).encode()).hexdigest()[:24])


@dataclass(frozen=True)
class BindingWorkflowViewModel:
    """Candidate sessions ranked for EXPLICIT selection. ``requires_explicit_selection`` is always True;
    the newest is never auto-selected; ``ambiguous`` flags equal top matches."""
    candidates: Tuple[dict, ...]
    requires_explicit_selection: bool
    auto_bind_forbidden: bool
    ambiguous: bool
    note: str
    fingerprint: str = ""

    def as_payload(self) -> dict:
        return {"candidates": [dict(c) for c in self.candidates],
                "requires_explicit_selection": bool(self.requires_explicit_selection),
                "auto_bind_forbidden": bool(self.auto_bind_forbidden), "ambiguous": bool(self.ambiguous),
                "note": _norm(self.note)}


def build_binding_workflow(candidate_sessions, run_plan_context, *, expected_setup_fingerprint: str = "",
                           min_clean_laps: int = 0) -> BindingWorkflowViewModel:
    """Rank candidates via the canonical ranker (context+setup match; recency only a tie-breaker; auto-bind
    forbidden). Requires explicit selection."""
    ranking = rank_activity_sessions(candidate_sessions, run_plan_context,
                                     expected_setup_fingerprint=expected_setup_fingerprint,
                                     min_clean_laps=min_clean_laps)
    vm = BindingWorkflowViewModel(
        candidates=tuple(ranking.candidates), requires_explicit_selection=ranking.requires_explicit_selection,
        auto_bind_forbidden=ranking.auto_bind_forbidden, ambiguous=ranking.ambiguous, note=ranking.note,
        fingerprint="")
    return BindingWorkflowViewModel(**{**vm.__dict__, "fingerprint": _fp(vm.as_payload())})


@dataclass(frozen=True)
class DebriefLaunchDecision:
    ready: bool
    debrief_kind: DebriefKind
    reason: str

    def as_payload(self) -> dict:
        return {"ready": bool(self.ready), "debrief_kind": self.debrief_kind.value, "reason": _norm(self.reason)}


def decide_debrief_launch(activity_type: PreparationActivityType, *, session_bound: bool) -> DebriefLaunchDecision:
    """A debrief may launch only after an explicit binding (where telemetry is required). Reuses the
    canonical handover to determine the correct debrief kind."""
    r = assess_debrief_readiness(activity_type, session_bound)
    return DebriefLaunchDecision(r.ready, r.debrief_kind, r.reason)


@dataclass(frozen=True)
class CumulativeUpdatePlan:
    can_update: bool
    updated_domains: Tuple[str, ...]
    reason: str

    def as_payload(self) -> dict:
        return {"can_update": bool(self.can_update), "updated_domains": sorted(self.updated_domains),
                "reason": _norm(self.reason)}


def plan_cumulative_event_update(activity_type: PreparationActivityType, *, debrief_confirmed: bool,
                                 classification: EvidenceClassification) -> CumulativeUpdatePlan:
    """Cumulative event knowledge updates ONLY after an explicitly-confirmed outcome AND only for
    VALID/LIMITED evidence (reuses the Phase-52 gate). An unconfirmed debrief updates nothing."""
    if not debrief_confirmed:
        return CumulativeUpdatePlan(False, (), "outcome not explicitly confirmed — no cumulative update")
    u = plan_cumulative_update(activity_type, classification)
    return CumulativeUpdatePlan(u.can_update, u.updated_domains, u.reason)


@dataclass(frozen=True)
class CommandCentreReturnDecision:
    refresh_required: bool
    note: str

    def as_payload(self) -> dict:
        return {"refresh_required": bool(self.refresh_required), "note": _norm(self.note)}


def resolve_command_centre_return(*, debrief_complete: bool) -> CommandCentreReturnDecision:
    """After the debrief, return to the Event Command Centre by REFRESHING FROM CANONICAL TRUTH (no
    manually-maintained UI flags). The refresh recomputes the primary next action."""
    if debrief_complete:
        return CommandCentreReturnDecision(True, "refresh the Command Centre from canonical truth")
    return CommandCentreReturnDecision(False, "debrief not complete — stay in the debrief")
