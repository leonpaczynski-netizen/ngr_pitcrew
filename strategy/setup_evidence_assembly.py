"""Canonical setup-experiment evidence assembly (Engineering Brain Phase 4).

Pure selection + assembly logic that turns raw persisted evidence (sessions, lap
rows, `corner_issue_occurrences`) into the exact form the Phase 3 evaluator
consumes — WITHOUT deciding the outcome itself and WITHOUT silently choosing
among equally plausible sessions.

The DB-reading orchestrator lives on SessionDB
(`assemble_setup_experiment_evidence` / `review_experiment_outcome`); this module
holds the deterministic, testable core: baseline/test SELECTION and whole-lap
summarisation.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; never raises.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from statistics import median as _median, pstdev as _pstdev
from typing import Mapping, Optional, Sequence, Tuple


EVIDENCE_ASSEMBLY_VERSION = "evidence_assembly_v1"


class SelectionStatus(str, Enum):
    RESOLVED = "resolved"
    PARTIAL = "partial"
    AMBIGUOUS = "ambiguous"
    MISSING = "missing"
    INCOMPATIBLE = "incompatible"


@dataclass(frozen=True)
class SessionCandidate:
    """A candidate session for baseline or test evidence."""

    session_id: str
    date_utc: str = ""
    checkpoint_ids: Tuple[str, ...] = ()   # checkpoints tagged on this session's evidence
    valid_lap_count: int = 0
    track: str = ""
    layout_id: str = ""
    scope_fingerprint: str = ""


@dataclass(frozen=True)
class SelectionResult:
    status: SelectionStatus
    session_id: Optional[str] = None
    reasons: Tuple[str, ...] = ()
    candidate_session_ids: Tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status in (SelectionStatus.RESOLVED, SelectionStatus.PARTIAL)

    def to_dict(self) -> dict:
        return {"status": self.status.value, "session_id": self.session_id,
                "reasons": list(self.reasons),
                "candidate_session_ids": list(self.candidate_session_ids)}


def select_test_session(
    candidates: Sequence[SessionCandidate],
    *,
    applied_checkpoint_id: str,
    scope_fingerprint: str = "",
    min_valid_laps: int = 3,
    explicit_session_id: Optional[str] = None,
) -> SelectionResult:
    """Select the session that carries TEST evidence for the applied checkpoint.

    Test evidence must be tagged with the experiment's applied checkpoint and share
    the scope. If an explicit session is given, it is validated (not overridden).
    Multiple equally-plausible checkpoint-tagged sessions → AMBIGUOUS (never the
    newest silently)."""
    if explicit_session_id is not None:
        match = [c for c in candidates if c.session_id == str(explicit_session_id)]
        if not match:
            return SelectionResult(SelectionStatus.MISSING,
                                   reasons=("explicit test session not found",))
        c = match[0]
        if applied_checkpoint_id and applied_checkpoint_id not in c.checkpoint_ids:
            return SelectionResult(
                SelectionStatus.INCOMPATIBLE, session_id=c.session_id,
                reasons=("test session evidence is not tagged with the applied "
                         "checkpoint",))
        status = (SelectionStatus.RESOLVED if c.valid_lap_count >= min_valid_laps
                  else SelectionStatus.PARTIAL)
        reasons = () if status == SelectionStatus.RESOLVED else (
            f"only {c.valid_lap_count} valid laps",)
        return SelectionResult(status, session_id=c.session_id, reasons=reasons)

    tagged = [c for c in candidates
              if applied_checkpoint_id and applied_checkpoint_id in c.checkpoint_ids
              and (not scope_fingerprint or not c.scope_fingerprint
                   or c.scope_fingerprint == scope_fingerprint)]
    if not tagged:
        return SelectionResult(SelectionStatus.MISSING,
                               reasons=("no session carries evidence tagged with the "
                                        "applied checkpoint",))
    usable = [c for c in tagged if c.valid_lap_count >= min_valid_laps]
    pool = usable or tagged
    if len(pool) > 1:
        return SelectionResult(
            SelectionStatus.AMBIGUOUS,
            reasons=("multiple sessions carry checkpoint-tagged test evidence",),
            candidate_session_ids=tuple(sorted(c.session_id for c in pool)))
    c = pool[0]
    status = (SelectionStatus.RESOLVED if c.valid_lap_count >= min_valid_laps
              else SelectionStatus.PARTIAL)
    return SelectionResult(status, session_id=c.session_id,
                           reasons=() if status == SelectionStatus.RESOLVED
                           else (f"only {c.valid_lap_count} valid laps",))


def select_baseline_session(
    candidates: Sequence[SessionCandidate],
    *,
    applied_checkpoint_id: str,
    parent_checkpoint_id: str = "",
    scope_fingerprint: str = "",
    min_valid_laps: int = 3,
    explicit_session_id: Optional[str] = None,
) -> SelectionResult:
    """Select the AUTHORITATIVE parent/rollback baseline session — never simply the
    most recent previous one. Baseline must NOT carry the experiment's applied
    checkpoint (that is test evidence); it should carry the parent checkpoint when
    known. Multiple plausible baselines → AMBIGUOUS."""
    if explicit_session_id is not None:
        match = [c for c in candidates if c.session_id == str(explicit_session_id)]
        if not match:
            return SelectionResult(SelectionStatus.MISSING,
                                   reasons=("explicit baseline session not found",))
        c = match[0]
        if applied_checkpoint_id and applied_checkpoint_id in c.checkpoint_ids:
            return SelectionResult(
                SelectionStatus.INCOMPATIBLE, session_id=c.session_id,
                reasons=("baseline session carries the experiment's OWN applied "
                         "checkpoint (that is test evidence, not baseline)",))
        status = (SelectionStatus.RESOLVED if c.valid_lap_count >= min_valid_laps
                  else SelectionStatus.PARTIAL)
        return SelectionResult(status, session_id=c.session_id,
                               reasons=() if status == SelectionStatus.RESOLVED
                               else (f"only {c.valid_lap_count} valid laps",))

    # Prefer the parent checkpoint's evidence; otherwise any non-experiment-checkpoint
    # session in scope.
    def _in_scope(c):
        return (not scope_fingerprint or not c.scope_fingerprint
                or c.scope_fingerprint == scope_fingerprint)

    if parent_checkpoint_id:
        parent_sessions = [c for c in candidates
                           if parent_checkpoint_id in c.checkpoint_ids and _in_scope(c)]
    else:
        parent_sessions = []
    pool = parent_sessions or [
        c for c in candidates
        if applied_checkpoint_id not in c.checkpoint_ids and _in_scope(c)
        and c.valid_lap_count >= min_valid_laps]
    if not pool:
        return SelectionResult(SelectionStatus.MISSING,
                               reasons=("no authoritative parent/baseline session in "
                                        "scope",))
    if len(pool) > 1:
        return SelectionResult(
            SelectionStatus.AMBIGUOUS,
            reasons=("multiple plausible baseline sessions — not auto-selecting the "
                     "newest",),
            candidate_session_ids=tuple(sorted(c.session_id for c in pool)))
    c = pool[0]
    status = (SelectionStatus.RESOLVED if c.valid_lap_count >= min_valid_laps
              else SelectionStatus.PARTIAL)
    return SelectionResult(status, session_id=c.session_id,
                           reasons=() if status == SelectionStatus.RESOLVED
                           else (f"only {c.valid_lap_count} valid laps",))


# --------------------------------------------------------------------------- #
# Whole-lap summary (valid laps only; median, never fastest)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class WholeLapSummary:
    valid_lap_count: int
    rejected_lap_count: int
    rejection_distribution: Mapping[str, int]
    median_lap_ms: int
    lap_time_stdev_ms: float
    incident_count: int
    compound: str
    setup_identity_confidence: str
    track_identity_confidence: str
    eval_version: str = EVIDENCE_ASSEMBLY_VERSION

    def to_dict(self) -> dict:
        return {
            "valid_lap_count": self.valid_lap_count,
            "rejected_lap_count": self.rejected_lap_count,
            "rejection_distribution": dict(self.rejection_distribution),
            "median_lap_ms": self.median_lap_ms,
            "lap_time_stdev_ms": self.lap_time_stdev_ms,
            "incident_count": self.incident_count, "compound": self.compound,
            "setup_identity_confidence": self.setup_identity_confidence,
            "track_identity_confidence": self.track_identity_confidence,
            "eval_version": self.eval_version,
        }


def summarise_valid_laps(
    lap_rows: Sequence[Mapping],
    validity_summary,
    *,
    setup_identity_confidence: str = "unknown",
    track_identity_confidence: str = "unknown",
) -> WholeLapSummary:
    """Median-based whole-lap summary over VALID laps only (never fastest alone).

    ``validity_summary`` is an engineering_lap_validity.LapValiditySummary; its
    ``valid_lap_numbers`` select which rows count."""
    valid_nums = set(getattr(validity_summary, "valid_lap_numbers", ()) or ())
    times = []
    incidents = 0
    compound_votes: dict = {}
    for r in (lap_rows or []):
        try:
            if r.get("lap_num") not in valid_nums:
                continue
            t = int(r.get("lap_time_ms") or 0)
            if t > 0:
                times.append(t)
            incidents += int(r.get("off_track_count") or 0)
            c = (r.get("compound") or "").strip()
            if c:
                compound_votes[c] = compound_votes.get(c, 0) + 1
        except Exception:
            continue
    med = int(_median(times)) if times else 0
    sd = float(_pstdev(times)) if len(times) >= 2 else 0.0
    compound = max(compound_votes, key=compound_votes.get) if compound_votes else ""
    return WholeLapSummary(
        valid_lap_count=int(getattr(validity_summary, "usable_laps", len(times))),
        rejected_lap_count=int(getattr(validity_summary, "rejected_laps", 0)),
        rejection_distribution=dict(getattr(validity_summary,
                                            "rejection_distribution", {}) or {}),
        median_lap_ms=med, lap_time_stdev_ms=round(sd, 1), incident_count=incidents,
        compound=compound, setup_identity_confidence=setup_identity_confidence,
        track_identity_confidence=track_identity_confidence)
