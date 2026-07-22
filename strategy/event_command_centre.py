"""Event Command Centre domain (Program 2, Phase 51).

Assembles the Home / Event Command Centre view over EXISTING authorities: the active-cycle resolution
plus the read-only ``SessionDB.build_event_preparation_report`` dict. It is orchestration and
presentation — it creates no event state, no setup value, and writes nothing. It selects ONE primary
next action, a small set of attention items, per-dimension readiness, cumulative progress, quick-action
navigation targets and the preparation timeline.

Purity: Qt-free, DB-free, offline, deterministic, no wall-clock, never raises. ``now_date`` is injected
and only feeds the DISPLAY countdown, excluded from the fingerprint.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import List, Optional, Sequence, Tuple

from strategy.active_cycle_resolution import ActiveEventCycleResolution, ActiveCycleResolutionState

EVENT_COMMAND_CENTRE_VERSION = "event_command_centre_v1"
EVENT_COMMAND_CENTRE_SCHEMA = 1


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{EVENT_COMMAND_CENTRE_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


def _days_until(now_date: str, race_date: str) -> Optional[int]:
    try:
        a, b = date.fromisoformat(_norm(now_date)[:10]), date.fromisoformat(_norm(race_date)[:10])
    except (ValueError, TypeError):
        return None
    return (b - a).days


class NextActionCategory(str, Enum):
    CREATE_EVENT = "create_event"
    SELECT_EVENT = "select_event"
    RESOLVE_BLOCKER = "resolve_blocker"
    REVIEW_REVISION = "review_revision"
    BIND_SESSION = "bind_session"
    COMPLETE_DEBRIEF = "complete_debrief"
    FINALISE_STRATEGY = "finalise_strategy"
    LOCK_SETUP = "lock_setup"
    NEXT_ACTIVITY = "next_activity"


# specialist surfaces the Command Centre links into (never duplicates). DEF-UAT-073-014/016: ordered by the
# actual event workflow — Setup Development BEFORE Practice Programme (you build a setup, then practice it) —
# and "Telemetry" is NOT an event department (it is a raw-capture view, reachable from the tab bar).
QUICK_ACTION_SURFACES: Tuple[Tuple[str, str], ...] = (
    ("Event Briefing", "briefing"), ("Garage & Readiness", "garage"),
    ("Setup Development", "setup"), ("Practice Programme", "practice"),
    ("Driver Coaching", "coaching"), ("Strategy", "strategy"),
    ("Qualifying Preparation", "qualifying"), ("Live Engineer", "live"), ("Debrief", "debrief"),
    ("Development History", "development_history"),
)


@dataclass(frozen=True)
class EventNextAction:
    category: NextActionCategory
    headline: str
    detail: str
    target_surface: str
    tone: str

    def as_payload(self) -> dict:
        return {"category": self.category.value, "headline": _norm(self.headline),
                "detail": _norm(self.detail), "target_surface": _norm(self.target_surface),
                "tone": _norm(self.tone)}


@dataclass(frozen=True)
class EventAttentionItem:
    kind: str
    message: str
    tone: str

    def as_payload(self) -> dict:
        return {"kind": _norm(self.kind), "message": _norm(self.message), "tone": _norm(self.tone)}


@dataclass(frozen=True)
class EventReadinessSummary:
    dimensions: Tuple[Tuple[str, str, str], ...] = field(default_factory=tuple)

    def as_payload(self) -> dict:
        return {"dimensions": [[_norm(n), _norm(l), _norm(note)] for (n, l, note) in self.dimensions]}


@dataclass(frozen=True)
class EventProgressSummary:
    valid_laps: int = 0
    practice_sessions: int = 0
    setup_experiments: int = 0
    coaching_runs: int = 0
    tyre_samples: int = 0
    fuel_samples: int = 0
    race_simulations: int = 0
    setup_confidence: str = ""
    strategy_maturity: str = ""

    def as_payload(self) -> dict:
        return {"valid_laps": int(self.valid_laps), "practice_sessions": int(self.practice_sessions),
                "setup_experiments": int(self.setup_experiments), "coaching_runs": int(self.coaching_runs),
                "tyre_samples": int(self.tyre_samples), "fuel_samples": int(self.fuel_samples),
                "race_simulations": int(self.race_simulations),
                "setup_confidence": _norm(self.setup_confidence),
                "strategy_maturity": _norm(self.strategy_maturity)}


@dataclass(frozen=True)
class EventQuickAction:
    label: str
    target_surface: str

    def as_payload(self) -> dict:
        return {"label": _norm(self.label), "target_surface": _norm(self.target_surface)}


@dataclass(frozen=True)
class EventCommandCentre:
    resolution_state: ActiveCycleResolutionState
    event_identity: dict
    next_action: EventNextAction
    attention_items: Tuple[EventAttentionItem, ...]
    readiness: EventReadinessSummary
    progress: EventProgressSummary
    quick_actions: Tuple[EventQuickAction, ...]
    timeline: Tuple[dict, ...]
    recent_learning: Tuple[str, ...]
    candidates: Tuple[dict, ...]
    days_until_race: Optional[int]        # DISPLAY-only; excluded from fingerprint
    fingerprint: str = ""

    def as_semantic_payload(self) -> dict:
        return {"schema": EVENT_COMMAND_CENTRE_SCHEMA, "resolution_state": self.resolution_state.value,
                "event_identity": self.event_identity, "next_action": self.next_action.as_payload(),
                "attention_items": [a.as_payload() for a in self.attention_items],
                "readiness": self.readiness.as_payload(), "progress": self.progress.as_payload(),
                "timeline": list(self.timeline),
                "candidates": sorted(self.candidates, key=lambda c: _norm(c.get("cycle_id"))),
                "recent_learning": [_norm(r) for r in self.recent_learning]}


# required-for-race setup dimensions (a MISSING one is an attention item)
_REQUIRED_READINESS = ("base_setup", "race_setup", "qualifying_setup")


# DEF-073-018: the cumulative-evidence objective names an evidence DOMAIN; route it to the specialist
# surface that actually performs that objective. Setup domains → the Setup Builder; driver domains →
# Practice Review (coaching); pace/tyre/fuel → Practice Review (driving); strategy → Strategy Builder.
# Surface keys match MainWindow._CC_SURFACE_TABS. Unknown domains fall back to "practice".
_OBJECTIVE_DOMAIN_TO_SURFACE = {
    "setup_base": "setup", "setup_race": "setup", "setup_qualifying": "setup",
    "working_window": "setup", "convergence": "setup",
    "driver_coaching": "coaching", "consistency": "coaching",
    "race_pace": "practice", "tyre_model": "practice", "fuel_model": "practice",
    "strategy": "strategy",
}


def _primary_next_action(
    resolution: ActiveEventCycleResolution,
    report: Optional[dict],
    *,
    pending_binding: bool,
    pending_debrief: bool,
    strategy_final_ready: bool,
    lock_ready_disciplines: Sequence[str],
) -> EventNextAction:
    """Deterministic single primary action. Priority: resolution problems first, then in-cycle
    operational needs (bind → debrief → finalise → lock), then the cumulative-evidence objective."""
    A = NextActionCategory
    st = resolution.state
    if st == ActiveCycleResolutionState.NO_ACTIVE_EVENT:
        return EventNextAction(A.CREATE_EVENT, "Create or import an NGR event",
                               "No active preparation cycle. Create an event or view upcoming events.",
                               "no_event", "info")
    if st in (ActiveCycleResolutionState.EVENT_REQUIRES_SELECTION,
              ActiveCycleResolutionState.MULTIPLE_ACTIVE_EVENTS):
        return EventNextAction(A.SELECT_EVENT, "Select the active NGR event",
                               "Several preparation cycles are open — choose one explicitly.",
                               "event_selector", "warn")
    if st == ActiveCycleResolutionState.EVENT_BLOCKED:
        return EventNextAction(A.RESOLVE_BLOCKER, "Resolve the event blocker",
                               "This event cannot proceed until its blocker is resolved.", "garage", "warn")
    if st == ActiveCycleResolutionState.EVENT_CONTEXT_CHANGED:
        return EventNextAction(A.REVIEW_REVISION, "Review the event revision impact",
                               "Event settings changed — review which evidence remains valid.",
                               "development_history", "warn")
    # active / upcoming / paused event: operational needs
    if pending_binding:
        return EventNextAction(A.BIND_SESSION, "Bind the latest Practice session",
                               "A telemetry session is waiting to be explicitly bound to an activity.",
                               "binding", "warn")
    if pending_debrief:
        return EventNextAction(A.COMPLETE_DEBRIEF, "Complete the session debrief",
                               "Confirm the outcome and driver feedback before it counts as evidence.",
                               "debrief", "warn")
    if strategy_final_ready:
        return EventNextAction(A.FINALISE_STRATEGY, "Finalise the race strategy",
                               "Strategy evidence is ready — confirm the plan explicitly.", "strategy", "info")
    discs = [d for d in lock_ready_disciplines if _norm(d)]
    if discs:
        d = sorted(discs)[0]
        return EventNextAction(A.LOCK_SETUP, f"Lock the {d} setup",
                               "A setup is lock-ready — confirm the lock explicitly.", "setup", "info")
    na = (report or {}).get("next_action") or {}
    headline = _norm(na.get("headline")) or "Prepare for the next activity"
    # DEF-073-018: route the cumulative-evidence objective to the surface that ACTUALLY performs it.
    # Building a setup domain's evidence starts in the Setup Builder, not Practice Review (the old
    # hardcoded "practice" sent "Build setup_base evidence" to the wrong tab). Fall back to "practice"
    # for pace/tyre/fuel objectives that are gathered by driving.
    surface = _OBJECTIVE_DOMAIN_TO_SURFACE.get(_norm(na.get("domain")), "practice")
    return EventNextAction(A.NEXT_ACTIVITY, headline, _norm(na.get("rationale")), surface, "info")


def _attention_items(report: Optional[dict], resolution: ActiveEventCycleResolution,
                     pending_binding: bool, pending_debrief: bool) -> Tuple[EventAttentionItem, ...]:
    items: List[EventAttentionItem] = []
    if resolution.state == ActiveCycleResolutionState.EVENT_CONTEXT_CHANGED:
        items.append(EventAttentionItem("event_revision", "Event settings changed since preparation began.",
                                        "warn"))
    if pending_binding:
        items.append(EventAttentionItem("pending_binding", "A Practice session is awaiting binding.", "warn"))
    if pending_debrief:
        items.append(EventAttentionItem("pending_debrief", "A session debrief is outstanding.", "warn"))
    for row in ((report or {}).get("readiness") or []):
        try:
            name, level, _note = row[0], row[1], row[2]
        except (IndexError, TypeError, KeyError):
            continue
        if _norm(level) == "missing" and _norm(name) in _REQUIRED_READINESS:
            items.append(EventAttentionItem("missing_evidence",
                                            f"{_norm(name).replace('_', ' ').title()} has no evidence yet.",
                                            "warn"))
    return tuple(items)


def build_event_command_centre(
    resolution: ActiveEventCycleResolution,
    report: Optional[dict] = None,
    *,
    now_date: str = "",
    pending_binding: bool = False,
    pending_debrief: bool = False,
    strategy_final_ready: bool = False,
    lock_ready_disciplines: Sequence[str] = (),
    recent_learning: Sequence[str] = (),
) -> EventCommandCentre:
    """Assemble the Command Centre view. Pure/view-only; nothing is written. When there is no active
    event (``report is None`` or resolution NO_ACTIVE_EVENT) the view still renders a create/select
    next action and the candidate list."""
    rep = report if isinstance(report, dict) and report.get("ok") else None
    cyc = (rep or {}).get("cycle") or {}
    identity = {"event_name": _norm(cyc.get("event_name")), "series": _norm(cyc.get("series")),
                "round": _norm(cyc.get("round")), "state": _norm(cyc.get("state")),
                "current_phase": _norm(cyc.get("current_phase"))}

    next_action = _primary_next_action(resolution, rep, pending_binding=pending_binding,
                                       pending_debrief=pending_debrief,
                                       strategy_final_ready=strategy_final_ready,
                                       lock_ready_disciplines=lock_ready_disciplines)
    attention = _attention_items(rep, resolution, pending_binding, pending_debrief)

    rdy_rows = tuple((_norm(r[0]), _norm(r[1]), _norm(r[2])) for r in ((rep or {}).get("readiness") or [])
                     if isinstance(r, (list, tuple)) and len(r) >= 3)
    readiness = EventReadinessSummary(dimensions=rdy_rows)

    p = (rep or {}).get("progress") or {}
    setup = (rep or {}).get("setup") or {}
    strat = (rep or {}).get("strategy") or {}
    progress = EventProgressSummary(
        valid_laps=int(p.get("valid_laps", 0)), practice_sessions=int(p.get("practice_sessions", 0)),
        setup_experiments=int(p.get("setup_experiments", 0)), coaching_runs=int(p.get("coaching_runs", 0)),
        tyre_samples=int(p.get("tyre_samples", 0)), fuel_samples=int(p.get("fuel_samples", 0)),
        race_simulations=int(p.get("race_simulations", 0)),
        setup_confidence=_norm(setup.get("race")), strategy_maturity=_norm(strat.get("maturity")))

    quick = tuple(EventQuickAction(label, surf) for (label, surf) in QUICK_ACTION_SURFACES)
    timeline = tuple((rep or {}).get("timeline") or [])
    candidates = tuple(c.as_payload() for c in resolution.candidates)
    # prefer the report's already-computed countdown; else recompute from an explicit race date
    days = cyc.get("days_until_race")
    if days is None and cyc:
        days = _days_until(now_date, cyc.get("official_race_date", ""))

    cc = EventCommandCentre(
        resolution_state=resolution.state, event_identity=identity, next_action=next_action,
        attention_items=attention, readiness=readiness, progress=progress, quick_actions=quick,
        timeline=timeline, recent_learning=tuple(_norm(r) for r in recent_learning if _norm(r)),
        candidates=candidates, days_until_race=days, fingerprint="")
    return EventCommandCentre(
        resolution_state=cc.resolution_state, event_identity=cc.event_identity, next_action=cc.next_action,
        attention_items=cc.attention_items, readiness=cc.readiness, progress=cc.progress,
        quick_actions=cc.quick_actions, timeline=cc.timeline, recent_learning=cc.recent_learning,
        candidates=cc.candidates, days_until_race=cc.days_until_race, fingerprint=_fp(cc.as_semantic_payload()))


def command_centre_to_dict(cc: EventCommandCentre, *, loading: bool = False) -> dict:
    """Serialise the Command Centre to the immutable view dict the UI worker hands to the panel. Includes
    the display countdown + resolution state (runtime display), which are NOT in the fingerprint."""
    return {
        "ok": True, "loading": bool(loading), "resolution_state": cc.resolution_state.value,
        "event": cc.event_identity, "days_until_race": cc.days_until_race,
        "next_action": cc.next_action.as_payload(),
        "attention": [a.as_payload() for a in cc.attention_items],
        "readiness": [[n, l, note] for (n, l, note) in cc.readiness.dimensions],
        "progress": cc.progress.as_payload(),
        "timeline": list(cc.timeline),
        "quick_actions": [q.as_payload() for q in cc.quick_actions],
        "candidates": list(cc.candidates),
        "recent_learning": list(cc.recent_learning),
        "fingerprint": cc.fingerprint,
    }
