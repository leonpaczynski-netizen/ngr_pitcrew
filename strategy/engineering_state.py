"""Canonical current engineering-state snapshot (Engineering Brain Phase 6).

A deterministic, immutable snapshot of the engineering state for the active setup
context after an experiment review: the residual-issue set (from
`engineering_issue`), grouped by state, plus confirmed-good/damaged-good behaviours,
evidence gaps, the canonical setup-decision state, and working-window references.

The pure builder NEVER reads the clock — the caller supplies `generated_at`. It has
a deterministic `content_fingerprint` so identical inputs reproduce an identical
snapshot (restart determinism). It reuses the Phase-3 outcome, Phase-4 assembly and
Phase-4 `resolve_setup_decision` — it does not re-evaluate them.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Optional, Sequence, Tuple

from strategy.engineering_issue import (
    ResidualIssue, ResidualState, residual_issues_from_outcome,
    residual_severity_rank,
)


ENGINEERING_STATE_VERSION = "engineering_state_v1"


@dataclass(frozen=True)
class ValidLapSummary:
    valid_lap_count: int = 0
    rejected_lap_count: int = 0
    median_lap_ms: int = 0
    rejection_distribution: Mapping[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"valid_lap_count": self.valid_lap_count,
                "rejected_lap_count": self.rejected_lap_count,
                "median_lap_ms": self.median_lap_ms,
                "rejection_distribution": dict(self.rejection_distribution)}


@dataclass(frozen=True)
class EngineeringStateSnapshot:
    scope_fingerprint: str
    driver: str
    car: str
    track: str
    layout_id: str
    discipline: str
    applied_checkpoint_id: str
    experiment_id: str
    outcome_status: str
    association_status: str
    decision_state: str
    valid_laps: ValidLapSummary
    residual_issues: Tuple[ResidualIssue, ...]
    resolved: Tuple[str, ...]
    improved: Tuple[str, ...]
    unchanged: Tuple[str, ...]
    worsened: Tuple[str, ...]
    new_issues: Tuple[str, ...]
    confirmed_good: Tuple[str, ...]
    damaged_good: Tuple[str, ...]
    insufficient: Tuple[str, ...]
    evidence_gaps: Tuple[str, ...]
    contradictions: Tuple[str, ...]
    working_window_fields: Tuple[str, ...]
    content_fingerprint: str
    generated_at: str = ""
    eval_version: str = ENGINEERING_STATE_VERSION

    @property
    def has_regression(self) -> bool:
        return bool(self.worsened or self.new_issues or self.damaged_good)

    def to_dict(self) -> dict:
        return {
            "scope_fingerprint": self.scope_fingerprint, "driver": self.driver,
            "car": self.car, "track": self.track, "layout_id": self.layout_id,
            "discipline": self.discipline,
            "applied_checkpoint_id": self.applied_checkpoint_id,
            "experiment_id": self.experiment_id, "outcome_status": self.outcome_status,
            "association_status": self.association_status,
            "decision_state": self.decision_state, "valid_laps": self.valid_laps.to_dict(),
            "residual_issues": [r.to_dict() for r in self.residual_issues],
            "resolved": list(self.resolved), "improved": list(self.improved),
            "unchanged": list(self.unchanged), "worsened": list(self.worsened),
            "new_issues": list(self.new_issues),
            "confirmed_good": list(self.confirmed_good),
            "damaged_good": list(self.damaged_good),
            "insufficient": list(self.insufficient),
            "evidence_gaps": list(self.evidence_gaps),
            "contradictions": list(self.contradictions),
            "working_window_fields": list(self.working_window_fields),
            "content_fingerprint": self.content_fingerprint,
            "generated_at": self.generated_at, "eval_version": self.eval_version,
        }


_STATE_BUCKET = {
    ResidualState.RESOLVED: "resolved",
    ResidualState.IMPROVED_BUT_PRESENT: "improved",
    ResidualState.UNCHANGED: "unchanged",
    ResidualState.WORSENED: "worsened",
    ResidualState.NEW: "new_issues",
    ResidualState.CONFIRMED_GOOD: "confirmed_good",
    ResidualState.GOOD_BEHAVIOUR_DAMAGED: "damaged_good",
    ResidualState.INSUFFICIENT_EVIDENCE: "insufficient",
    ResidualState.INVALID_COMPARISON: "insufficient",
    ResidualState.AMBIGUOUS: "insufficient",
}


def build_engineering_state(
    *,
    outcome: Mapping,
    scope_fingerprint: str = "",
    driver: str = "",
    car: str = "",
    track: str = "",
    layout_id: str = "",
    discipline: str = "",
    applied_checkpoint_id: str = "",
    experiment_id: str = "",
    association_status: str = "resolved",
    decision_state: str = "",
    valid_laps: Optional[ValidLapSummary] = None,
    working_window_fields: Sequence[str] = (),
    generated_at: str = "",
) -> EngineeringStateSnapshot:
    """Build the deterministic snapshot from a persisted Phase-3 outcome dict.
    ``generated_at`` is caller-supplied (the pure builder never reads the clock)."""
    scope = scope_fingerprint or str((outcome or {}).get("scope_fingerprint") or "")
    issues = residual_issues_from_outcome(
        outcome or {}, discipline=discipline, scope=scope,
        association_status=association_status)
    buckets: dict = {b: [] for b in ("resolved", "improved", "unchanged", "worsened",
                                     "new_issues", "confirmed_good", "damaged_good",
                                     "insufficient")}
    for ri in issues:
        bucket = _STATE_BUCKET.get(ri.residual_state)
        if bucket:
            buckets[bucket].append(ri.key)

    evidence_gaps = tuple(dict.fromkeys(
        str(m) for m in (json.loads((outcome or {}).get("missing_evidence_json") or "[]")
                         if isinstance((outcome or {}).get("missing_evidence_json"), str)
                         else (outcome or {}).get("missing_evidence") or [])))
    contradictions = tuple(
        f"{ri.identity.issue_type}: {'; '.join(ri.warnings)}"
        for ri in issues if ri.residual_state == ResidualState.AMBIGUOUS)

    vls = valid_laps or ValidLapSummary()
    # deterministic content fingerprint over the salient, order-independent content
    payload = {
        "scope": scope, "checkpoint": applied_checkpoint_id,
        "outcome_status": str((outcome or {}).get("status") or ""),
        "association": association_status, "decision": decision_state,
        "valid_laps": vls.valid_lap_count,
        "issues": sorted((ri.key, ri.residual_state.value) for ri in issues),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    fingerprint = f"{ENGINEERING_STATE_VERSION}:{hashlib.sha256(raw).hexdigest()[:24]}"

    return EngineeringStateSnapshot(
        scope_fingerprint=scope, driver=driver, car=car, track=track,
        layout_id=layout_id, discipline=discipline,
        applied_checkpoint_id=applied_checkpoint_id, experiment_id=str(experiment_id),
        outcome_status=str((outcome or {}).get("status") or ""),
        association_status=association_status, decision_state=decision_state,
        valid_laps=vls, residual_issues=issues,
        resolved=tuple(buckets["resolved"]), improved=tuple(buckets["improved"]),
        unchanged=tuple(buckets["unchanged"]), worsened=tuple(buckets["worsened"]),
        new_issues=tuple(buckets["new_issues"]),
        confirmed_good=tuple(buckets["confirmed_good"]),
        damaged_good=tuple(buckets["damaged_good"]),
        insufficient=tuple(buckets["insufficient"]),
        evidence_gaps=evidence_gaps, contradictions=contradictions,
        working_window_fields=tuple(dict.fromkeys(working_window_fields)),
        content_fingerprint=fingerprint, generated_at=generated_at)
