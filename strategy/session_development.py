"""Append-only Session Development Ledger (Engineering Brain Phase 7).

An immutable, deterministic timeline of engineering EVENTS for one session: when an
issue was first detected, when its status or trend changed, when it resolved, when a
protected behaviour was damaged, and when the whole-car health band moved. It is a
pure record — it decides nothing, recommends nothing, and mutates nothing.

The ledger is DERIVED by diffing consecutive ``LiveEngineeringState`` snapshots (from
``live_engineering_state``). Building the ledger from scratch over an ordered snapshot
sequence and appending snapshots one at a time produce the SAME events in the SAME
order — that is the append-only + determinism contract. Events are never rewritten or
deleted; a later snapshot only ever appends.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; never raises; no random,
no wall-clock (sequence numbers are positional, not timestamps).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence, Tuple

from strategy.live_engineering_state import LiveEngineeringState, LiveIssueState
from strategy.state_transitions import IssueStatus, Trend

SESSION_DEVELOPMENT_VERSION = "session_development_v1"


class LedgerEventType(str, Enum):
    ISSUE_DETECTED = "issue_detected"
    STATUS_CHANGED = "status_changed"
    TREND_CHANGED = "trend_changed"
    ISSUE_RESOLVED = "issue_resolved"
    ISSUE_REGRESSED = "issue_regressed"          # went WORSENING / re-appeared
    PROTECTED_DAMAGED = "protected_damaged"
    PROTECTED_RESTORED = "protected_restored"
    HEALTH_BAND_CHANGED = "health_band_changed"


# Emission order within a single lap step (deterministic, session events last).
_EVENT_ORDER = {
    LedgerEventType.ISSUE_DETECTED: 0,
    LedgerEventType.ISSUE_REGRESSED: 1,
    LedgerEventType.PROTECTED_DAMAGED: 2,
    LedgerEventType.STATUS_CHANGED: 3,
    LedgerEventType.TREND_CHANGED: 4,
    LedgerEventType.ISSUE_RESOLVED: 5,
    LedgerEventType.PROTECTED_RESTORED: 6,
    LedgerEventType.HEALTH_BAND_CHANGED: 7,
}


@dataclass(frozen=True)
class LedgerEvent:
    """One immutable timeline entry. ``sequence_no`` is positional (0-based)."""

    sequence_no: int
    lap_number: Optional[int]
    event_type: LedgerEventType
    issue_key: str                      # '' for session-level events
    issue_family: str
    issue_type: str
    corner: str
    from_value: str                     # prior status/trend/band ('' when new)
    to_value: str
    detail: str

    def to_dict(self) -> dict:
        return {"sequence_no": self.sequence_no, "lap_number": self.lap_number,
                "event_type": self.event_type.value, "issue_key": self.issue_key,
                "issue_family": self.issue_family, "issue_type": self.issue_type,
                "corner": self.corner, "from_value": self.from_value,
                "to_value": self.to_value, "detail": self.detail}


@dataclass(frozen=True)
class SessionDevelopmentLedger:
    """Immutable append-only ledger. ``append_snapshot`` returns a NEW ledger; the
    existing events are never mutated."""

    session_id: Optional[str]
    scope_fingerprint: str
    events: Tuple[LedgerEvent, ...]
    last_lap_number: Optional[int]
    content_fingerprint: str
    eval_version: str = SESSION_DEVELOPMENT_VERSION

    @property
    def event_count(self) -> int:
        return len(self.events)

    def events_for(self, issue_key: str) -> Tuple[LedgerEvent, ...]:
        return tuple(e for e in self.events if e.issue_key == issue_key)

    def to_dict(self) -> dict:
        return {"session_id": self.session_id,
                "scope_fingerprint": self.scope_fingerprint,
                "events": [e.to_dict() for e in self.events],
                "last_lap_number": self.last_lap_number,
                "content_fingerprint": self.content_fingerprint,
                "eval_version": self.eval_version}


def empty_ledger(*, session_id: Optional[str] = None,
                 scope_fingerprint: str = "") -> SessionDevelopmentLedger:
    return SessionDevelopmentLedger(
        session_id=(str(session_id) if session_id is not None else None),
        scope_fingerprint=scope_fingerprint, events=(), last_lap_number=None,
        content_fingerprint=_fingerprint(()))


def _fingerprint(events: Sequence[LedgerEvent]) -> str:
    raw = json.dumps([e.to_dict() for e in events], sort_keys=True,
                     separators=(",", ":"))
    return f"{SESSION_DEVELOPMENT_VERSION}:{hashlib.sha256(raw.encode()).hexdigest()[:24]}"


def _diff_events(prev: Optional[LiveEngineeringState], new: LiveEngineeringState,
                 lap_number: Optional[int]) -> Tuple[Tuple[LedgerEventType, LiveIssueState, str, str, str], ...]:
    """Deterministic (unordered) event tuples between two snapshots for ONE lap step.

    Returns (event_type, issue, from_value, to_value, detail). Session-level band
    changes carry a synthetic issue-less marker (issue is None)."""
    prev_issues = {i.key: i for i in prev.issues} if prev else {}
    out = []
    for issue in new.issues:
        was = prev_issues.get(issue.key)
        # --- newly tracked issue -------------------------------------------------
        if was is None:
            if issue.status != IssueStatus.UNKNOWN:
                et = (LedgerEventType.PROTECTED_DAMAGED
                      if (issue.is_protected and issue.status == IssueStatus.DAMAGED)
                      else LedgerEventType.ISSUE_DETECTED)
                out.append((et, issue, "", issue.status.value,
                            f"{issue.trend.value}"))
            continue
        # --- status change -------------------------------------------------------
        if was.status != issue.status:
            frm, to = was.status.value, issue.status.value
            if issue.status == IssueStatus.RESOLVED:
                et = LedgerEventType.ISSUE_RESOLVED
            elif issue.is_protected and issue.status == IssueStatus.DAMAGED:
                et = LedgerEventType.PROTECTED_DAMAGED
            elif (issue.is_protected and issue.status == IssueStatus.PROTECTED
                  and was.status == IssueStatus.DAMAGED):
                et = LedgerEventType.PROTECTED_RESTORED
            elif (issue.status in (IssueStatus.ACTIVE, IssueStatus.NEW)
                  and was.status in (IssueStatus.RECOVERING, IssueStatus.STABLE,
                                     IssueStatus.RESOLVED)):
                et = LedgerEventType.ISSUE_REGRESSED
            else:
                et = LedgerEventType.STATUS_CHANGED
            out.append((et, issue, frm, to, ""))
        # --- trend change (only meaningful, non-insufficient) --------------------
        if (was.trend != issue.trend
                and issue.trend != Trend.INSUFFICIENT_EVIDENCE):
            out.append((LedgerEventType.TREND_CHANGED, issue,
                        was.trend.value, issue.trend.value, ""))
    return tuple(out)


def append_snapshot(
    ledger: SessionDevelopmentLedger,
    new_state: LiveEngineeringState,
    *,
    prev_state: Optional[LiveEngineeringState] = None,
    lap_number: Optional[int] = None,
    prev_band: Optional[str] = None,
) -> SessionDevelopmentLedger:
    """Append the events implied by moving from ``prev_state`` to ``new_state`` at
    ``lap_number``. Returns a NEW ledger; the input ledger is never mutated.

    ``prev_band`` is the health band before this snapshot (defaults to
    ``prev_state.health.band`` when a prev snapshot is supplied)."""
    diffs = list(_diff_events(prev_state, new_state, lap_number))
    # session-level band change
    new_band = new_state.health.band.value
    old_band = prev_band
    if old_band is None and prev_state is not None:
        old_band = prev_state.health.band.value
    band_events = []
    if old_band is not None and old_band != new_band:
        band_events.append((LedgerEventType.HEALTH_BAND_CHANGED, None,
                            old_band, new_band, ""))

    # stable deterministic ordering: (event-order, issue-key)
    def _sort_key(item):
        et, issue, _frm, _to, _d = item
        return (_EVENT_ORDER[et], issue.key if issue is not None else "")

    ordered = sorted(diffs + band_events, key=_sort_key)
    seq = len(ledger.events)
    new_events = list(ledger.events)
    for et, issue, frm, to, detail in ordered:
        new_events.append(LedgerEvent(
            sequence_no=seq, lap_number=lap_number, event_type=et,
            issue_key=(issue.key if issue is not None else ""),
            issue_family=(issue.identity.issue_family.value if issue is not None else ""),
            issue_type=(issue.identity.issue_type if issue is not None else ""),
            corner=(issue.last_observed_corner if issue is not None else ""),
            from_value=frm, to_value=to, detail=detail))
        seq += 1
    ev = tuple(new_events)
    return SessionDevelopmentLedger(
        session_id=ledger.session_id or new_state.session_id,
        scope_fingerprint=ledger.scope_fingerprint or new_state.scope_fingerprint,
        events=ev, last_lap_number=lap_number,
        content_fingerprint=_fingerprint(ev))


def build_session_ledger(
    snapshots: Sequence[Tuple[Optional[int], LiveEngineeringState]],
    *,
    session_id: Optional[str] = None,
    scope_fingerprint: str = "",
) -> SessionDevelopmentLedger:
    """Fold an ordered ``(lap_number, LiveEngineeringState)`` sequence into the ledger.

    Equivalent (byte-for-byte) to appending each snapshot in turn — this is the
    from-scratch rebuild used for restart-determinism proofs."""
    ledger = empty_ledger(session_id=session_id, scope_fingerprint=scope_fingerprint)
    prev: Optional[LiveEngineeringState] = None
    for lap_number, state in snapshots:
        ledger = append_snapshot(ledger, state, prev_state=prev,
                                 lap_number=lap_number)
        prev = state
    return ledger
