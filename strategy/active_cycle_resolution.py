"""Active Event Preparation Cycle resolution (Program 2, Phase 51).

Resolves WHICH preparation cycle is the active one for the Home / Event Command Centre, using explicit
deterministic rules. It NEVER silently chooses the newest database row: when several cycles qualify it
returns EVENT_REQUIRES_SELECTION and the caller must present an explicit choice. A user-selected active
cycle is OPERATIONAL NAVIGATION STATE only — selecting a cycle never alters an engineering fingerprint or
historical evidence.

Purity: Qt-free, DB-free, offline, deterministic, no wall-clock, never raises. ``now_date`` is injected
(never the wall clock) and only classifies UPCOMING vs active; it is excluded from the fingerprint.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import List, Optional, Sequence, Tuple

ACTIVE_CYCLE_RESOLUTION_VERSION = "active_cycle_resolution_v1"
ACTIVE_CYCLE_RESOLUTION_SCHEMA = 1


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{ACTIVE_CYCLE_RESOLUTION_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


def _as_date(v) -> Optional[date]:
    if isinstance(v, date):
        return v
    s = _norm(v)
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None


class ActiveCycleResolutionState(str, Enum):
    NO_ACTIVE_EVENT = "no_active_event"
    ONE_ACTIVE_EVENT = "one_active_event"
    MULTIPLE_ACTIVE_EVENTS = "multiple_active_events"
    UPCOMING_EVENT = "upcoming_event"
    PAUSED_EVENT = "paused_event"
    EVENT_REQUIRES_SELECTION = "event_requires_selection"
    EVENT_CONTEXT_CHANGED = "event_context_changed"
    EVENT_BLOCKED = "event_blocked"


# explicit cycle lifecycle states considered "not active"
_TERMINAL_CYCLE_STATES = frozenset({"complete", "abandoned"})


@dataclass(frozen=True)
class CycleCandidate:
    """One preparation cycle offered to the resolver. Built from persisted cycle rows. ``explicit_state``
    is the stored lifecycle bucket (''/active/paused/complete/abandoned). ``context_changed`` / ``blocked``
    are explicit flags set by the caller (e.g. an event-revision detector), never inferred here."""
    cycle_id: str
    event_name: str = ""
    series: str = ""
    round_label: str = ""
    explicit_state: str = ""
    prep_open_date: str = ""
    official_race_date: str = ""
    context_digest: str = ""
    context_changed: bool = False
    blocked: bool = False

    def as_payload(self) -> dict:
        return {"cycle_id": _norm(self.cycle_id), "event_name": _norm(self.event_name),
                "series": _norm(self.series), "round": _norm(self.round_label),
                "explicit_state": _norm(self.explicit_state).lower(),
                "prep_open_date": _norm(self.prep_open_date),
                "official_race_date": _norm(self.official_race_date),
                "context_digest": _norm(self.context_digest),
                "context_changed": bool(self.context_changed), "blocked": bool(self.blocked)}

    @property
    def is_terminal(self) -> bool:
        return _norm(self.explicit_state).lower() in _TERMINAL_CYCLE_STATES

    @property
    def is_paused(self) -> bool:
        return _norm(self.explicit_state).lower() == "paused"


@dataclass(frozen=True)
class ActiveEventCycleResolution:
    state: ActiveCycleResolutionState
    resolved_cycle_id: str
    candidates: Tuple[CycleCandidate, ...]
    selection_required: bool
    reason: str
    fingerprint: str = ""

    def as_semantic_payload(self) -> dict:
        # candidate membership + explicit selection + resolved identity are semantic; now_date/state
        # bucket (which may depend on the injected now) are NOT part of the identity fingerprint.
        return {"schema": ACTIVE_CYCLE_RESOLUTION_SCHEMA,
                "candidates": [c.as_payload() for c in
                               sorted(self.candidates, key=lambda c: _norm(c.cycle_id))],
                "resolved_cycle_id": _norm(self.resolved_cycle_id),
                "selection_required": bool(self.selection_required)}

    def selectable(self) -> Tuple[CycleCandidate, ...]:
        """Non-terminal candidates the user may explicitly select."""
        return tuple(c for c in self.candidates if not c.is_terminal)


def resolve_active_cycle(
    candidates: Sequence[CycleCandidate],
    *,
    selected_cycle_id: str = "",
    now_date: str = "",
) -> ActiveEventCycleResolution:
    """Resolve the active cycle deterministically. Rules, in order:

    1. An explicit ``selected_cycle_id`` that matches a non-terminal candidate WINS (manual selection is
       operational state). Its state reflects that cycle (paused/upcoming/context-changed/blocked/active).
    2. No candidates → NO_ACTIVE_EVENT.
    3. No non-terminal candidates → NO_ACTIVE_EVENT (only completed/abandoned exist).
    4. Exactly one non-terminal candidate → its state (blocked > context_changed > paused > upcoming >
       active).
    5. More than one non-terminal candidate and no selection → EVENT_REQUIRES_SELECTION (never silently
       pick the newest row / latest timestamp).
    """
    S = ActiveCycleResolutionState
    cands = tuple(candidates)
    sel = _norm(selected_cycle_id)
    now = _as_date(now_date)

    def _single_state(c: CycleCandidate) -> ActiveCycleResolutionState:
        if c.blocked:
            return S.EVENT_BLOCKED
        if c.context_changed:
            return S.EVENT_CONTEXT_CHANGED
        if c.is_paused:
            return S.PAUSED_EVENT
        open_d = _as_date(c.prep_open_date)
        if now is not None and open_d is not None and open_d > now:
            return S.UPCOMING_EVENT
        return S.ONE_ACTIVE_EVENT

    def _resolution(state, cid, sel_req, reason):
        r = ActiveEventCycleResolution(state=state, resolved_cycle_id=cid, candidates=cands,
                                       selection_required=sel_req, reason=reason, fingerprint="")
        return ActiveEventCycleResolution(state=r.state, resolved_cycle_id=r.resolved_cycle_id,
                                          candidates=r.candidates, selection_required=r.selection_required,
                                          reason=r.reason, fingerprint=_fp(r.as_semantic_payload()))

    # rule 1 — explicit manual selection wins
    if sel:
        chosen = next((c for c in cands if _norm(c.cycle_id) == sel and not c.is_terminal), None)
        if chosen is not None:
            return _resolution(_single_state(chosen), chosen.cycle_id, False,
                               "resolved by explicit user selection")

    # rule 2 — nothing at all
    if not cands:
        return _resolution(S.NO_ACTIVE_EVENT, "", False, "no preparation cycles exist")

    non_terminal = [c for c in cands if not c.is_terminal]
    # rule 3 — only completed/abandoned
    if not non_terminal:
        return _resolution(S.NO_ACTIVE_EVENT, "", False, "all cycles are complete or abandoned")

    # rule 4 — exactly one active candidate
    if len(non_terminal) == 1:
        c = non_terminal[0]
        st = _single_state(c)
        return _resolution(st, c.cycle_id, False, f"single non-terminal cycle ({st.value})")

    # rule 5 — several active candidates → explicit selection required (never newest-by-default)
    return _resolution(S.EVENT_REQUIRES_SELECTION, "", True,
                       f"{len(non_terminal)} active cycles require explicit selection")
