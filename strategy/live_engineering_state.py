"""Live Engineering State Monitor (Engineering Brain Phase 7).

A READ-ONLY OBSERVER that answers "what is happening to the car right now?" It folds
the per-valid-lap per-corner observations already produced by the mature evidence
pipeline (Phase 4 ``CornerObservationRecord`` over the canonical ``corner_issue_occurrences``
store) into a deterministic per-issue live state: identity, current confidence, current
recurrence, last-observed lap/corner, TREND and STATUS (from ``state_transitions``),
plus engineering consistency measurements and a session-health summary.

Doctrine (identical to the rest of the Engineering Brain):
  * It makes NO engineering decision — it selects no experiment, authors no setup
    value, scores no evidence, evaluates no lap, changes no candidate ordering. It
    observes canonical outputs and classifies them.
  * Trend / status use ONLY comparable (valid) laps; a single exceptional lap can
    never flip a trend (``state_transitions`` owns those rules).
  * A missing observation is never treated as a resolution by itself — resolution
    needs sustained clear valid laps.
  * Recurrence is the SINGLE existing authority (``corner_evidence.classify_recurrence``
    → ``practice_pattern_analysis.RecurrenceThresholds``); this module never invents a
    second recurrence rule.
  * Consistency numbers are ENGINEERING measurements (how repeatable a symptom is),
    never driver ratings.
  * Identity never depends on display text (reuses Phase 6 ``EngineeringIssueIdentity``).

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; never raises; no random,
no wall-clock. The whole state is a deterministic function of its inputs, so a live
recompute and a from-scratch restart produce byte-identical fingerprints.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Optional, Sequence, Tuple

from strategy.corner_evidence import (
    CornerObservationRecord,
    RecurrenceResult,
    classify_recurrence,
)
from strategy.engineering_issue import (
    EngineeringIssueIdentity,
    issue_family_for,
)
from strategy.practice_pattern_analysis import RecurrenceClass, RecurrenceThresholds
from strategy.state_transitions import (
    STATE_TRANSITIONS_VERSION,
    IssueStatus,
    Trend,
    detect_trend,
    next_status,
)

LIVE_ENGINEERING_STATE_VERSION = "live_engineering_state_v1"


class SessionHealthBand(str, Enum):
    """Deterministic coarse band for the whole car right now (NOT a score/rating)."""

    NOMINAL = "nominal"                  # nothing active
    SETTLING = "settling"               # issues present but improving / recovering
    DEVELOPING = "developing"           # active issues, none worsening
    DEGRADING = "degrading"             # something worsening or a good behaviour damaged
    UNKNOWN = "unknown"                 # not enough comparable laps yet


def identity_from_record(
    rec: CornerObservationRecord, *, discipline: str = "", scope: str = "",
) -> EngineeringIssueIdentity:
    """Build the canonical (display-text-free) issue identity from a per-corner
    observation. Mirrors ``engineering_issue._identity_from_corner`` but reads the
    canonical record shape."""
    issue = str(rec.issue_type or "")
    return EngineeringIssueIdentity(
        issue_family=issue_family_for(issue), issue_type=issue,
        axle=str(rec.axle or ""), phase=rec.phase.value,
        segment_id=str(rec.segment_id or ""),
        corner_name=str(rec.corner_name or ""),
        discipline=discipline, scope_fingerprint=scope,
        source_type="live_observation")


@dataclass(frozen=True)
class ConsistencyMeasures:
    """Engineering repeatability measurements for ONE issue (never a driver rating).

    * ``recurrence_ratio``  — affected valid laps / total valid laps.
    * ``repeatability``     — 1 - (present↔absent flips / possible flips): how steady
                              the symptom is lap-to-lap (1.0 = perfectly consistent,
                              present or absent; low = jittery/noisy).
    * ``affected_valid_laps`` / ``total_valid_laps`` — the raw comparable counts.
    """

    affected_valid_laps: int
    total_valid_laps: int
    recurrence_ratio: float
    repeatability: float

    def to_dict(self) -> dict:
        return {"affected_valid_laps": self.affected_valid_laps,
                "total_valid_laps": self.total_valid_laps,
                "recurrence_ratio": self.recurrence_ratio,
                "repeatability": self.repeatability}


@dataclass(frozen=True)
class LiveIssueState:
    """The live state of ONE engineering issue, recomputed deterministically from the
    full valid-lap history each update (no hidden mutable memory)."""

    identity: EngineeringIssueIdentity
    status: IssueStatus
    trend: Trend
    recurrence_class: RecurrenceClass
    confidence: str
    present_now: bool
    is_protected: bool
    first_observed_lap: Optional[int]
    last_observed_lap: Optional[int]
    last_observed_corner: str
    affected_lap_numbers: Tuple[int, ...]
    consistency: ConsistencyMeasures
    severity: str
    eval_version: str = LIVE_ENGINEERING_STATE_VERSION

    @property
    def key(self) -> str:
        return self.identity.key()

    @property
    def is_active(self) -> bool:
        return self.status in (IssueStatus.ACTIVE, IssueStatus.RECOVERING,
                               IssueStatus.NEW, IssueStatus.DAMAGED)

    @property
    def is_resolved(self) -> bool:
        return self.status == IssueStatus.RESOLVED

    def to_dict(self) -> dict:
        return {
            "identity": self.identity.to_dict(),
            "status": self.status.value, "trend": self.trend.value,
            "recurrence_class": self.recurrence_class.value,
            "confidence": self.confidence, "present_now": self.present_now,
            "is_protected": self.is_protected,
            "first_observed_lap": self.first_observed_lap,
            "last_observed_lap": self.last_observed_lap,
            "last_observed_corner": self.last_observed_corner,
            "affected_lap_numbers": list(self.affected_lap_numbers),
            "consistency": self.consistency.to_dict(),
            "severity": self.severity, "eval_version": self.eval_version,
        }


@dataclass(frozen=True)
class SessionHealth:
    """Deterministic whole-car summary for the current comparable-lap window."""

    total_valid_laps: int
    comparable_laps: int
    clean_valid_laps: int               # valid laps with no active issue present
    active_issue_count: int
    new_issue_count: int
    worsening_issue_count: int
    recovering_issue_count: int
    resolved_issue_count: int
    protected_intact_count: int
    protected_damaged_count: int
    lap_cleanliness: float              # clean_valid_laps / total_valid_laps
    band: SessionHealthBand

    def to_dict(self) -> dict:
        return {
            "total_valid_laps": self.total_valid_laps,
            "comparable_laps": self.comparable_laps,
            "clean_valid_laps": self.clean_valid_laps,
            "active_issue_count": self.active_issue_count,
            "new_issue_count": self.new_issue_count,
            "worsening_issue_count": self.worsening_issue_count,
            "recovering_issue_count": self.recovering_issue_count,
            "resolved_issue_count": self.resolved_issue_count,
            "protected_intact_count": self.protected_intact_count,
            "protected_damaged_count": self.protected_damaged_count,
            "lap_cleanliness": self.lap_cleanliness, "band": self.band.value,
        }


@dataclass(frozen=True)
class LiveEngineeringState:
    """Immutable snapshot of the live engineering state at one point in a session."""

    scope_fingerprint: str
    discipline: str
    session_id: Optional[str]
    issues: Tuple[LiveIssueState, ...]
    health: SessionHealth
    valid_lap_numbers: Tuple[int, ...]
    content_fingerprint: str
    eval_version: str = LIVE_ENGINEERING_STATE_VERSION
    transitions_version: str = STATE_TRANSITIONS_VERSION

    @property
    def active_issues(self) -> Tuple[LiveIssueState, ...]:
        return tuple(i for i in self.issues if i.is_active)

    @property
    def resolved_issues(self) -> Tuple[LiveIssueState, ...]:
        return tuple(i for i in self.issues if i.is_resolved)

    @property
    def protected_behaviours(self) -> Tuple[LiveIssueState, ...]:
        return tuple(i for i in self.issues if i.is_protected)

    def issue_for(self, key: str) -> Optional[LiveIssueState]:
        for i in self.issues:
            if i.key == key:
                return i
        return None

    def to_dict(self) -> dict:
        return {
            "scope_fingerprint": self.scope_fingerprint,
            "discipline": self.discipline, "session_id": self.session_id,
            "issues": [i.to_dict() for i in self.issues],
            "health": self.health.to_dict(),
            "valid_lap_numbers": list(self.valid_lap_numbers),
            "content_fingerprint": self.content_fingerprint,
            "eval_version": self.eval_version,
            "transitions_version": self.transitions_version,
        }


# --------------------------------------------------------------------------- #
# Pure fold
# --------------------------------------------------------------------------- #
def _group_key(rec: CornerObservationRecord) -> Tuple[str, str, str, str]:
    return (rec.segment_id or rec.corner_name, rec.phase.value,
            rec.issue_type, rec.axle)


def _repeatability(affected: Sequence[bool]) -> float:
    n = len(affected)
    if n < 2:
        return 1.0
    flips = sum(1 for i in range(1, n) if affected[i] != affected[i - 1])
    return round(1.0 - flips / (n - 1), 4)


def update_live_state(
    records: Sequence[CornerObservationRecord],
    valid_lap_numbers: Sequence[int],
    *,
    scope_fingerprint: str = "",
    discipline: str = "",
    session_id: Optional[str] = None,
    protected_keys: Optional[Sequence[str]] = None,
    thresholds: Optional[RecurrenceThresholds] = None,
    new_recent_laps: int = 3,
) -> LiveEngineeringState:
    """Fold ordered per-valid-lap per-corner observations into the live state.

    ``records`` are canonical ``CornerObservationRecord``s (any laps; only those on a
    valid lap are counted). ``valid_lap_numbers`` is the ORDERED set of comparable
    valid laps (formation/pit/invalid/outlier laps already removed upstream by Phase 4
    lap validity — this observer trusts that authority, it does not re-judge laps).

    The result is a pure deterministic function of the inputs: recomputing every lap
    and rebuilding from scratch on restart yield identical ``content_fingerprint``s.
    """
    th = thresholds or RecurrenceThresholds()
    protected = set(protected_keys or ())
    # Ordered, de-duplicated valid lap numbers define the comparable window.
    valid_order = [int(l) for l in valid_lap_numbers]
    valid_seen: dict = {}
    for l in valid_order:
        valid_seen.setdefault(l, len(valid_seen))
    valid_sorted = tuple(sorted(valid_seen))
    valid_set = set(valid_sorted)
    total_valid = len(valid_sorted)

    # Group admissible on-lap observations by issue identity (segment/phase/issue/axle).
    groups: dict = {}
    for r in records:
        if r.excluded:
            continue                       # kerb/airborne/noise never counts
        if r.lap_number is None or r.lap_number not in valid_set:
            continue                       # evidence from a non-comparable lap is ignored
        groups.setdefault(_group_key(r), []).append(r)

    issues = []
    clean_flags = {l: True for l in valid_sorted}
    for gkey in sorted(groups):
        recs = groups[gkey]
        identity = identity_from_record(recs[0], discipline=discipline,
                                        scope=scope_fingerprint)
        # affected[i] over the ordered valid-lap window
        affected_laps = {r.lap_number for r in recs if r.occurred_on_lap}
        affected = [l in affected_laps for l in valid_sorted]
        recurrence = classify_recurrence(recs, total_valid_laps=total_valid,
                                         thresholds=th)
        trend = detect_trend(affected)
        present_now = bool(affected and affected[-1])
        is_prot = identity.key() in protected
        first_lap = min(affected_laps) if affected_laps else None
        last_lap = max(affected_laps) if affected_laps else None
        # most-recent affected record's corner label (deterministic tie-break by segment)
        last_corner = ""
        if last_lap is not None:
            same = sorted((r for r in recs if r.lap_number == last_lap
                           and r.occurred_on_lap),
                          key=lambda r: (r.segment_id, r.corner_name))
            if same:
                last_corner = same[0].corner_name or same[0].segment_id
        status = next_status(
            IssueStatus.PROTECTED if is_prot else IssueStatus.UNKNOWN,
            trend, present_now=present_now, affected=affected,
            is_protected=is_prot, total_valid_laps=total_valid,
            first_seen_valid_lap=first_lap, latest_valid_lap=last_lap,
            new_recent_laps=new_recent_laps)
        # severity = most-recent affected record's severity (deterministic)
        severity = ""
        if last_lap is not None:
            sev_recs = sorted((r for r in recs if r.lap_number == last_lap
                               and r.occurred_on_lap and r.severity),
                              key=lambda r: (r.segment_id, r.corner_name))
            if sev_recs:
                severity = sev_recs[0].severity
        consistency = ConsistencyMeasures(
            affected_valid_laps=len(affected_laps), total_valid_laps=total_valid,
            recurrence_ratio=recurrence.recurrence_ratio,
            repeatability=_repeatability(affected))
        issue = LiveIssueState(
            identity=identity, status=status, trend=trend,
            recurrence_class=recurrence.classification,
            confidence=recurrence.confidence, present_now=present_now,
            is_protected=is_prot, first_observed_lap=first_lap,
            last_observed_lap=last_lap, last_observed_corner=last_corner,
            affected_lap_numbers=tuple(sorted(affected_laps)),
            consistency=consistency, severity=severity)
        issues.append(issue)
        # a lap is "clean" when no ACTIVE issue is present on it
        if issue.is_active:
            for l in affected_laps:
                if l in clean_flags:
                    clean_flags[l] = False

    issues.sort(key=lambda i: i.key)
    health = _session_health(issues, valid_sorted, clean_flags)
    fingerprint = _fingerprint(scope_fingerprint, discipline, issues, health,
                               valid_sorted)
    return LiveEngineeringState(
        scope_fingerprint=scope_fingerprint, discipline=discipline,
        session_id=(str(session_id) if session_id is not None else None),
        issues=tuple(issues), health=health, valid_lap_numbers=valid_sorted,
        content_fingerprint=fingerprint)


def _session_health(issues, valid_sorted, clean_flags) -> SessionHealth:
    total = len(valid_sorted)
    active = [i for i in issues if i.is_active and not i.is_protected]
    new = [i for i in active if i.status == IssueStatus.NEW]
    worsening = [i for i in issues if i.trend == Trend.WORSENING
                 and i.present_now and not i.is_protected]
    recovering = [i for i in issues if i.status == IssueStatus.RECOVERING]
    resolved = [i for i in issues if i.is_resolved]
    prot_damaged = [i for i in issues if i.is_protected
                    and i.status == IssueStatus.DAMAGED]
    prot_intact = [i for i in issues if i.is_protected
                   and i.status == IssueStatus.PROTECTED]
    clean = sum(1 for l in valid_sorted if clean_flags.get(l, True))
    cleanliness = round(clean / total, 4) if total else 0.0

    if total < RecurrenceThresholds().min_clean_laps_for_persistence:
        band = SessionHealthBand.UNKNOWN
    elif worsening or prot_damaged:
        band = SessionHealthBand.DEGRADING
    elif active:
        band = (SessionHealthBand.SETTLING
                if all(i.status == IssueStatus.RECOVERING for i in active)
                else SessionHealthBand.DEVELOPING)
    else:
        band = SessionHealthBand.NOMINAL
    return SessionHealth(
        total_valid_laps=total, comparable_laps=total, clean_valid_laps=clean,
        active_issue_count=len(active), new_issue_count=len(new),
        worsening_issue_count=len(worsening), recovering_issue_count=len(recovering),
        resolved_issue_count=len(resolved),
        protected_intact_count=len(prot_intact),
        protected_damaged_count=len(prot_damaged),
        lap_cleanliness=cleanliness, band=band)


def _fingerprint(scope, discipline, issues, health, valid_sorted) -> str:
    payload = {
        "v": LIVE_ENGINEERING_STATE_VERSION,
        "t": STATE_TRANSITIONS_VERSION,
        "scope": scope, "discipline": discipline,
        "valid": list(valid_sorted),
        "issues": [i.to_dict() for i in issues],
        "health": health.to_dict(),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"{LIVE_ENGINEERING_STATE_VERSION}:{hashlib.sha256(raw.encode()).hexdigest()[:24]}"
