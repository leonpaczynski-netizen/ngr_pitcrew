"""Permanent cross-session engineering memory (Engineering Brain Phase 8).

A deterministic FOLD over an immutable ``DevelopmentHistory`` (one memory context)
into the durable engineering knowledge the crew has accumulated over every session:
which issues recur, which fixes worked and which failed, how each learned working
window evolved, which behaviours are protected, and the hard constraints that must
never be forgotten (learned minimums, failed directions, known-unstable changes).

Doctrine:
  * Phase 8 makes NO engineering decision. This module only re-projects
    already-authoritative development records — it authors nothing, evaluates no lap,
    recommends no change, and mutates no evidence.
  * Memory is per FULL context (driver/car/track/layout/discipline/gt7/compound).
    Incompatible contexts never mix (the history is already single-context).
  * A missing observation is never a resolution; resolution is only what the canonical
    residual evidence recorded as RESOLVED.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; never raises; no random,
no wall-clock.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

from strategy.development_history import (
    DEVELOPMENT_HISTORY_VERSION, ConstraintKind, DevelopmentHistory, MemoryContextKey,
)

ENGINEERING_MEMORY_VERSION = "engineering_memory_v1"


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


# --------------------------------------------------------------------------- #
# Per-issue long-term memory
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class IssueMemory:
    """What we have learned about ONE engineering issue over every session."""

    issue_key: str
    family: str
    issue_type: str
    axle: str
    phase: str
    corner: str
    times_observed: int                 # records in which the issue appeared
    sessions_seen: int
    first_seen_date: str
    last_seen_date: str
    times_resolved: int
    times_regressed: int
    currently_resolved: bool
    recurring: bool                     # still-present in >= 2 records
    latest_state: str
    successful_fix_experiments: Tuple[str, ...]
    failed_fix_experiments: Tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "issue_key": self.issue_key, "family": self.family,
            "issue_type": self.issue_type, "axle": self.axle, "phase": self.phase,
            "corner": self.corner, "times_observed": self.times_observed,
            "sessions_seen": self.sessions_seen,
            "first_seen_date": self.first_seen_date,
            "last_seen_date": self.last_seen_date,
            "times_resolved": self.times_resolved,
            "times_regressed": self.times_regressed,
            "currently_resolved": self.currently_resolved, "recurring": self.recurring,
            "latest_state": self.latest_state,
            "successful_fix_experiments": list(self.successful_fix_experiments),
            "failed_fix_experiments": list(self.failed_fix_experiments),
        }


@dataclass(frozen=True)
class WorkingWindowEvolution:
    """How ONE field's learned working window changed across sessions."""

    field: str
    snapshots: Tuple[dict, ...]         # chronological {date, min, max, confidence, ...}
    latest_min: Optional[float]
    latest_max: Optional[float]
    latest_confidence: str
    converged: bool                     # stable window at medium/high confidence

    def to_dict(self) -> dict:
        return {"field": self.field, "snapshots": [dict(s) for s in self.snapshots],
                "latest_min": self.latest_min, "latest_max": self.latest_max,
                "latest_confidence": self.latest_confidence,
                "converged": self.converged}


@dataclass(frozen=True)
class ProtectedKnowledgeItem:
    """A hard constraint that must never be forgotten."""

    kind: str                           # ConstraintKind value
    field: str
    direction: str
    value: str
    confidence: str
    source: str
    times_reinforced: int

    def to_dict(self) -> dict:
        return {"kind": self.kind, "field": self.field, "direction": self.direction,
                "value": self.value, "confidence": self.confidence,
                "source": self.source, "times_reinforced": self.times_reinforced}


@dataclass(frozen=True)
class EngineeringMemory:
    """The permanent engineering knowledge for ONE context."""

    context: MemoryContextKey
    issues: Tuple[IssueMemory, ...]
    window_evolution: Tuple[WorkingWindowEvolution, ...]
    protected_behaviours: Tuple[dict, ...]
    protected_knowledge: Tuple[ProtectedKnowledgeItem, ...]
    successful_fix_count: int
    failed_fix_count: int
    review_count: int
    session_count: int
    content_fingerprint: str
    eval_version: str = ENGINEERING_MEMORY_VERSION

    @property
    def recurring_issues(self) -> Tuple[IssueMemory, ...]:
        return tuple(i for i in self.issues if i.recurring and not i.currently_resolved)

    @property
    def resolved_issues(self) -> Tuple[IssueMemory, ...]:
        return tuple(i for i in self.issues if i.currently_resolved)

    def issue_for(self, issue_key: str) -> Optional[IssueMemory]:
        for i in self.issues:
            if i.issue_key == issue_key:
                return i
        return None

    def to_dict(self) -> dict:
        return {
            "context": self.context.to_dict(),
            "issues": [i.to_dict() for i in self.issues],
            "window_evolution": [w.to_dict() for w in self.window_evolution],
            "protected_behaviours": [dict(p) for p in self.protected_behaviours],
            "protected_knowledge": [k.to_dict() for k in self.protected_knowledge],
            "successful_fix_count": self.successful_fix_count,
            "failed_fix_count": self.failed_fix_count,
            "review_count": self.review_count, "session_count": self.session_count,
            "content_fingerprint": self.content_fingerprint,
            "eval_version": self.eval_version,
        }


# --------------------------------------------------------------------------- #
# Fold
# --------------------------------------------------------------------------- #
class _IssueAcc:
    __slots__ = ("family", "issue_type", "axle", "phase", "corner", "observed",
                 "sessions", "first_date", "last_date", "resolved", "regressed",
                 "states", "good_fixes", "bad_fixes")

    def __init__(self):
        self.family = self.issue_type = self.axle = self.phase = self.corner = ""
        self.observed = 0
        self.sessions = set()
        self.first_date = self.last_date = ""
        self.resolved = self.regressed = 0
        self.states: List[Tuple[str, str]] = []   # (recorded_at, state)
        self.good_fixes: List[str] = []
        self.bad_fixes: List[str] = []


def build_engineering_memory(history: DevelopmentHistory) -> EngineeringMemory:
    """Fold an immutable ``DevelopmentHistory`` into permanent engineering memory.
    Deterministic: the same history (order-independent by construction, since the
    history is already canonically ordered) yields the same fingerprint."""
    issues: Dict[str, _IssueAcc] = {}
    window_by_field: Dict[str, List[dict]] = {}
    protected_by_behaviour: Dict[str, dict] = {}
    knowledge: Dict[Tuple[str, str, str, str], dict] = {}
    good_fix = bad_fix = 0

    for rec in history.records:
        improved = rec.improved
        regressed = rec.regressed
        good_fix += 1 if improved else 0
        bad_fix += 1 if regressed else 0
        # per-issue accumulation
        for r in rec.residual_states:
            k = r.get("issue_key") or ""
            if not k:
                continue
            acc = issues.get(k)
            if acc is None:
                acc = issues[k] = _IssueAcc()
                acc.family = r.get("family", ""); acc.issue_type = r.get("issue_type", "")
                acc.axle = r.get("axle", ""); acc.phase = r.get("phase", "")
                acc.corner = r.get("corner_name") or r.get("segment_id") or ""
                acc.first_date = rec.session_date or rec.recorded_at
            acc.observed += 1
            if rec.test_session_id:
                acc.sessions.add(rec.test_session_id)
            acc.last_date = rec.session_date or rec.recorded_at
            acc.states.append((rec.recorded_at, r.get("residual_state", "")))
            if r.get("residual_state") == "resolved":
                acc.resolved += 1
                if rec.experiment_id:
                    acc.good_fixes.append(rec.experiment_id)
            if r.get("is_regression") or r.get("is_new"):
                acc.regressed += 1
                if rec.experiment_id:
                    acc.bad_fixes.append(rec.experiment_id)
        # working-window evolution
        for w in rec.working_window_snapshot:
            fld = w.get("field") or ""
            if not fld:
                continue
            snap = dict(w)
            snap["date"] = rec.session_date or rec.recorded_at
            window_by_field.setdefault(fld, []).append(snap)
        # protected behaviours (latest verdict wins, chronological)
        for p in rec.protected_behaviours:
            b = p.get("behaviour") or ""
            if b:
                protected_by_behaviour[b] = dict(p)
        # protected knowledge (reinforced across records)
        for c in rec.protected_knowledge:
            key = (c.get("kind", ""), c.get("field", ""), c.get("direction", ""),
                   c.get("value", ""))
            prev = knowledge.get(key)
            if prev is None:
                knowledge[key] = {**c, "times_reinforced": 1}
            else:
                prev["times_reinforced"] += 1
                if _conf_rank(c.get("confidence")) > _conf_rank(prev.get("confidence")):
                    prev["confidence"] = c.get("confidence")

    issue_memories = tuple(sorted(
        (_finalise_issue(k, acc) for k, acc in issues.items()),
        key=lambda im: im.issue_key))
    windows = tuple(sorted((_finalise_window(f, snaps)
                            for f, snaps in window_by_field.items()),
                           key=lambda w: w.field))
    prot_behaviours = tuple(protected_by_behaviour[b]
                            for b in sorted(protected_by_behaviour))
    # promote protected behaviours into the knowledge set
    for p in prot_behaviours:
        key = (ConstraintKind.PROTECTED_BEHAVIOUR.value, p.get("field", ""), "",
               p.get("behaviour", ""))
        if key not in knowledge:
            knowledge[key] = {"kind": ConstraintKind.PROTECTED_BEHAVIOUR.value,
                              "field": p.get("field", ""), "direction": "",
                              "value": p.get("behaviour", ""),
                              "confidence": p.get("confidence", ""),
                              "source": "protected_behaviour", "times_reinforced": 1}
    knowledge_items = tuple(sorted(
        (ProtectedKnowledgeItem(
            kind=v.get("kind", ""), field=v.get("field", ""),
            direction=v.get("direction", ""), value=v.get("value", ""),
            confidence=v.get("confidence", ""), source=v.get("source", ""),
            times_reinforced=int(v.get("times_reinforced", 1)))
         for v in knowledge.values()),
        key=lambda it: (it.kind, it.field, it.direction, it.value)))

    payload = {
        "ctx": history.context.key(),
        "issues": [i.to_dict() for i in issue_memories],
        "windows": [w.to_dict() for w in windows],
        "protected": [dict(p) for p in prot_behaviours],
        "knowledge": [k.to_dict() for k in knowledge_items],
        "good": good_fix, "bad": bad_fix,
    }
    fp = (f"{ENGINEERING_MEMORY_VERSION}:"
          + hashlib.sha256(_dumps(payload).encode()).hexdigest()[:24])
    return EngineeringMemory(
        context=history.context, issues=issue_memories, window_evolution=windows,
        protected_behaviours=prot_behaviours, protected_knowledge=knowledge_items,
        successful_fix_count=good_fix, failed_fix_count=bad_fix,
        review_count=history.review_count, session_count=history.session_count,
        content_fingerprint=fp)


_STILL_PRESENT = {"unchanged", "worsened", "new", "improved_but_present",
                  "good_behaviour_damaged"}


def _finalise_issue(key: str, acc: _IssueAcc) -> IssueMemory:
    latest_state = acc.states[-1][1] if acc.states else ""
    currently_resolved = latest_state == "resolved"
    present_records = sum(1 for _, s in acc.states if s in _STILL_PRESENT)
    recurring = present_records >= 2
    return IssueMemory(
        issue_key=key, family=acc.family, issue_type=acc.issue_type, axle=acc.axle,
        phase=acc.phase, corner=acc.corner, times_observed=acc.observed,
        sessions_seen=len(acc.sessions), first_seen_date=acc.first_date,
        last_seen_date=acc.last_date, times_resolved=acc.resolved,
        times_regressed=acc.regressed, currently_resolved=currently_resolved,
        recurring=recurring, latest_state=latest_state,
        successful_fix_experiments=tuple(dict.fromkeys(acc.good_fixes)),
        failed_fix_experiments=tuple(dict.fromkeys(acc.bad_fixes)))


def _finalise_window(field: str, snaps: List[dict]) -> WorkingWindowEvolution:
    latest = snaps[-1]
    lo, hi = latest.get("min"), latest.get("max")
    conf = str(latest.get("confidence") or "")
    converged = (conf in ("high", "medium") and lo is not None and hi is not None
                 and _window_stable(snaps))
    return WorkingWindowEvolution(
        field=field, snapshots=tuple(snaps),
        latest_min=(float(lo) if lo is not None else None),
        latest_max=(float(hi) if hi is not None else None),
        latest_confidence=conf, converged=converged)


def _window_stable(snaps: List[dict]) -> bool:
    if len(snaps) < 2:
        return True
    a, b = snaps[-2], snaps[-1]
    return a.get("min") == b.get("min") and a.get("max") == b.get("max")


def _conf_rank(conf) -> int:
    return {"high": 3, "medium": 2, "low": 1, "provisional": 1}.get(
        str(conf or "").lower(), 0)
