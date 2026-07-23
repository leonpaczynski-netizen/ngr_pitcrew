"""Explicit practice-run recording decisions (Program 2 — UAT-2 remediation).

The Event Preparation Cycle spine (Phases 48-50) reads activities and their BOUND
telemetry sessions to build cumulative evidence, readiness and the next objective.
Until now nothing in the product ever wrote an activity or bound a session, so the
programme could never accumulate evidence: every run the driver completed was
invisible and the engineer's objective was frozen forever on the same domain.

This module supplies the deterministic DECISIONS for that write path. It is pure —
no Qt, no DB, no I/O, never raises — and it deliberately does NOT perform the write.
Two rules from the existing doctrine are preserved exactly:

  * **Sessions are never auto-bound.** ``evaluate_run_binding`` describes whether an
    explicit binding is legitimate; the user's action is what triggers it.
  * **Unknown stays unknown.** A session whose car/track do not match the cycle is
    reported as incompatible rather than silently counted as event evidence; the
    preparation report already classifies it that way downstream.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

from strategy.event_preparation_cycle import (
    PreparationActivityState, PreparationActivityType, PreparationPhase,
)


def _norm(v) -> str:
    return "" if v is None else str(v).strip()


#: Evidence domain (as named in a command-centre objective) → the activity type whose
#: VALID sessions contribute to it. Inverted from ``preparation_evidence._TYPE_DOMAINS``
#: and pinned here so a domain always resolves to ONE run type — where several types
#: feed a domain, this names the one whose purpose IS that domain.
DOMAIN_RUN_TYPE: dict[str, PreparationActivityType] = {
    "setup_base": PreparationActivityType.BASELINE_PRACTICE,
    "setup_qualifying": PreparationActivityType.QUALIFYING_SIMULATION,
    "setup_race": PreparationActivityType.LONG_RACE_RUN,
    "working_window": PreparationActivityType.SETUP_EXPERIMENT,
    "driver_coaching": PreparationActivityType.COACHING_RUN,
    "tyre_model": PreparationActivityType.TYRE_TEST,
    "fuel_model": PreparationActivityType.FUEL_TEST,
    "race_pace": PreparationActivityType.LONG_RACE_RUN,
    "consistency": PreparationActivityType.FREE_PRACTICE,
    "strategy": PreparationActivityType.STRATEGY_VALIDATION_RUN,
    "convergence": PreparationActivityType.FINAL_SETUP_CONFIRMATION,
}

#: Run type → the preparation phase it belongs to (display/ordering only).
_TYPE_PHASE: dict[PreparationActivityType, PreparationPhase] = {
    PreparationActivityType.BASELINE_PRACTICE: PreparationPhase.BASELINE_ESTABLISHMENT,
    PreparationActivityType.SETUP_EXPERIMENT: PreparationPhase.SETUP_DEVELOPMENT,
    PreparationActivityType.COACHING_RUN: PreparationPhase.DRIVER_DEVELOPMENT,
    PreparationActivityType.TYRE_TEST: PreparationPhase.TYRE_AND_FUEL_MODELLING,
    PreparationActivityType.FUEL_TEST: PreparationPhase.TYRE_AND_FUEL_MODELLING,
    PreparationActivityType.QUALIFYING_SIMULATION: PreparationPhase.QUALIFYING_DEVELOPMENT,
    PreparationActivityType.LONG_RACE_RUN: PreparationPhase.RACE_SIMULATION,
    PreparationActivityType.STRATEGY_VALIDATION_RUN: PreparationPhase.RACE_SIMULATION,
}

#: Human titles for the run types this module can plan.
_TYPE_TITLE: dict[PreparationActivityType, str] = {
    PreparationActivityType.BASELINE_PRACTICE: "Baseline practice run",
    PreparationActivityType.SETUP_EXPERIMENT: "Setup experiment run",
    PreparationActivityType.COACHING_RUN: "Coaching run",
    PreparationActivityType.TYRE_TEST: "Tyre test run",
    PreparationActivityType.FUEL_TEST: "Fuel test run",
    PreparationActivityType.QUALIFYING_SIMULATION: "Qualifying simulation",
    PreparationActivityType.LONG_RACE_RUN: "Long race run",
    PreparationActivityType.STRATEGY_VALIDATION_RUN: "Strategy validation run",
    PreparationActivityType.FINAL_SETUP_CONFIRMATION: "Final setup confirmation",
    PreparationActivityType.FREE_PRACTICE: "Free practice run",
}

#: An activity in one of these states is still the "current" run.
OPEN_STATES = frozenset({
    PreparationActivityState.IN_PROGRESS.value,
    PreparationActivityState.AWAITING_CONFIRMATION.value,
})


def domain_from_objective_headline(headline: str) -> str:
    """Recover the evidence domain named in a command-centre objective headline.

    ``to_objective`` renders "Build {domain} evidence" (or a convergence confirmation),
    and the next-action payload carries no separate domain field — parsing the headline
    keeps the domain available to the run planner without changing the payload, whose
    shape is part of the Command Centre fingerprint.
    """
    h = _norm(headline).lower()
    if not h:
        return ""
    # Longest first so "setup_base" is not shadowed by a shorter overlapping key.
    for domain in sorted(DOMAIN_RUN_TYPE, key=len, reverse=True):
        if domain in h:
            return domain
    if "confirm" in h:
        return "convergence"
    return ""


def run_type_for_domain(domain: str) -> PreparationActivityType:
    """The run type that builds evidence for ``domain``. Unknown → free practice.

    Free practice is the honest fallback: it contributes only consistency and race
    pace, so an unrecognised objective can never be credited as setup evidence.
    """
    return DOMAIN_RUN_TYPE.get(_norm(domain).lower(), PreparationActivityType.FREE_PRACTICE)


@dataclass(frozen=True)
class PlannedRun:
    """What starting a run should write. ``ok`` False means do not write anything."""
    ok: bool = False
    reason: str = ""
    reused: bool = False              # an already-open run was found, not a new one
    activity_id: str = ""
    cycle_id: str = ""
    activity_type: str = ""
    title: str = ""
    objective: str = ""
    order_index: int = 0
    phase: str = ""
    state: str = PreparationActivityState.IN_PROGRESS.value

    def as_activity_row(self, *, now_iso: str = "", created_at: str = "") -> dict:
        """The dict ``SessionDB.upsert_preparation_activity`` expects."""
        return {
            "activity_id": self.activity_id, "cycle_id": self.cycle_id,
            "activity_type": self.activity_type, "title": self.title,
            "objective": self.objective, "planned_date": "",
            "state": self.state, "order_index": int(self.order_index),
            "optional": False, "phase": self.phase, "notes": "",
            "created_at": _norm(created_at) or _norm(now_iso),
            "updated_at": _norm(now_iso),
        }


def plan_practice_run(
    *,
    cycle_id: str,
    objective_domain: str = "",
    objective_headline: str = "",
    existing_activities: Sequence[Mapping] = (),
) -> PlannedRun:
    """Decide the activity that "Start practice run" should open.

    An already-open run of the SAME type is reused rather than duplicated (pressing
    Start twice must not create two runs). Otherwise a new activity is planned with a
    deterministic id derived from the cycle, the run type and how many runs of that
    type already exist — so the same call on the same state always yields the same id.
    """
    cid = _norm(cycle_id)
    if not cid:
        return PlannedRun(reason="No active event — activate one before starting a run.")

    rtype = run_type_for_domain(objective_domain)
    rows = [a for a in (existing_activities or ()) if isinstance(a, Mapping)]

    # Reuse any run already open — of any type. Two concurrent runs cannot be told
    # apart by one telemetry session, so the product allows exactly one at a time.
    for a in rows:
        if _norm(a.get("state")).lower() in OPEN_STATES:
            return PlannedRun(
                ok=True, reused=True, reason="A run is already open.",
                activity_id=_norm(a.get("activity_id")), cycle_id=cid,
                activity_type=_norm(a.get("activity_type")) or rtype.value,
                title=_norm(a.get("title")) or _TYPE_TITLE.get(rtype, "Practice run"),
                objective=_norm(a.get("objective")) or _norm(objective_headline),
                order_index=int(a.get("order_index") or 0),
                phase=_norm(a.get("phase")),
            )

    same_type = sum(1 for a in rows if _norm(a.get("activity_type")) == rtype.value)
    phase = _TYPE_PHASE.get(rtype)
    return PlannedRun(
        ok=True, reused=False, reason="",
        activity_id=f"{cid}::{rtype.value}::{same_type + 1}",
        cycle_id=cid,
        activity_type=rtype.value,
        title=f"{_TYPE_TITLE.get(rtype, 'Practice run')} {same_type + 1}",
        objective=_norm(objective_headline) or f"Build {_norm(objective_domain)} evidence",
        order_index=len(rows) + 1,
        phase=phase.value if phase is not None else "",
    )


@dataclass(frozen=True)
class RunBindingDecision:
    """Whether an explicit "record this run" is legitimate, and what it means."""
    ok: bool = False
    reason: str = ""
    activity_id: str = ""
    session_id: str = ""
    cycle_id: str = ""
    laps: int = 0
    compatible: bool = False          # session car+track match the cycle context
    warning: str = ""

    @property
    def contributes_event_evidence(self) -> bool:
        """An incompatible session is recorded but must not read as event evidence."""
        return bool(self.ok and self.compatible and self.laps > 0)


def evaluate_run_binding(
    *,
    activity_id: str,
    cycle_id: str,
    session_id,
    session_meta: Optional[Mapping] = None,
    cycle: Optional[Mapping] = None,
) -> RunBindingDecision:
    """Decide whether the driver's completed run can be bound to the open activity.

    Rejects only what is genuinely unrecordable — no run open, no telemetry session,
    or a session with zero completed laps (nothing to learn from). A session recorded
    in a different car or at a different track is ALLOWED but flagged incompatible:
    the preparation report classifies it that way and it cannot strengthen this
    event's confidence, which is more honest than refusing to record what happened.
    """
    aid = _norm(activity_id)
    sid = _norm(session_id if session_id is not None else "")
    cid = _norm(cycle_id)
    if not aid:
        return RunBindingDecision(reason="No run is open — press Start practice run first.")
    if not sid or sid == "0":
        return RunBindingDecision(
            activity_id=aid, cycle_id=cid,
            reason="No telemetry session was recorded — was the game connected?")

    meta = session_meta if isinstance(session_meta, Mapping) else {}
    try:
        laps = int(meta.get("total_laps") or 0)
    except (TypeError, ValueError):
        laps = 0
    if laps <= 0:
        return RunBindingDecision(
            activity_id=aid, session_id=sid, cycle_id=cid, laps=0,
            reason="That run recorded no completed laps, so there is nothing to learn from.")

    cyc = cycle if isinstance(cycle, Mapping) else {}
    s_track, s_car = _norm(meta.get("track")).lower(), _norm(meta.get("car_name")).lower()
    c_track, c_car = _norm(cyc.get("track")).lower(), _norm(cyc.get("car")).lower()
    # Unknown context on either side is NOT a mismatch claim — it stays unknown, and
    # an unknown side cannot assert compatibility either.
    known = bool(s_track and s_car and c_track and c_car)
    compatible = known and s_track == c_track and s_car == c_car
    warning = ""
    if known and not compatible:
        warning = (f"Recorded in {meta.get('car_name')} at {meta.get('track')}, which is not this "
                   f"event's car/track — it will not count as evidence for this event.")
    elif not known:
        warning = ("The car or track for this run is unknown, so it cannot count as evidence "
                   "for this event.")

    return RunBindingDecision(
        ok=True, activity_id=aid, session_id=sid, cycle_id=cid, laps=laps,
        compatible=compatible, warning=warning,
        reason=f"{laps} lap{'s' if laps != 1 else ''} recorded.")


def completed_activity_row(activity: Mapping, *, now_iso: str = "") -> dict:
    """The activity row that marks an open run COMPLETED, preserving its identity."""
    a = activity if isinstance(activity, Mapping) else {}
    return {
        "activity_id": _norm(a.get("activity_id")), "cycle_id": _norm(a.get("cycle_id")),
        "activity_type": _norm(a.get("activity_type")), "title": _norm(a.get("title")),
        "objective": _norm(a.get("objective")), "planned_date": _norm(a.get("planned_date")),
        "state": PreparationActivityState.COMPLETED.value,
        "order_index": int(a.get("order_index") or 0),
        "optional": bool(a.get("optional")), "phase": _norm(a.get("phase")),
        "notes": _norm(a.get("notes")), "created_at": _norm(a.get("created_at")),
        "updated_at": _norm(now_iso),
    }


def discarded_activity_row(activity: Mapping, *, now_iso: str = "") -> dict:
    """The activity row that abandons an open run without recording evidence."""
    row = completed_activity_row(activity, now_iso=now_iso)
    row["state"] = PreparationActivityState.CANCELLED.value
    return row
