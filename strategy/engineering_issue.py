"""Canonical engineering issue identity + residual-issue state (Engineering Brain Phase 6).

Answers "what remains after an experiment?" deterministically, by RE-CLASSIFYING the
canonical Phase-3 `SetupExperimentOutcome` corner comparisons + protected-behaviour
verdicts into a richer residual taxonomy. It NEVER re-runs telemetry comparison or
decides the overall experiment outcome (Phase 3 owns that) — it derives the state of
each individual engineering issue from evidence Phase 3/4 already produced.

Doctrine:
  * A missing observation is never automatically RESOLVED — resolution needs
    adequate comparable evidence.
  * Repeated valid evidence outweighs one-offs (recurrence classes from Phase 4).
  * A new issue is not created merely because a weak baseline lacked it.
  * Confirmed-good behaviour is first-class; damage to it is surfaced.
  * Issue identity never depends on display text.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Optional, Sequence, Tuple


ENGINEERING_ISSUE_VERSION = "engineering_issue_v1"

# Recurrence classes that mean "a setup-relevant repeatable problem" (Phase 4).
_AUTHORABLE = frozenset({"recurring", "strongly_recurring"})
_MIN_RESOLVE_SAMPLES = 3


class IssueFamily(str, Enum):
    BRAKING = "braking"
    ROTATION = "rotation"           # entry / mid-corner balance
    TRACTION = "traction"           # exit / power-down
    PLATFORM = "platform"           # bottoming / kerb / ride
    GEARING = "gearing"
    DRIVE_OUT = "drive_out"
    TYRE = "tyre"
    FUEL = "fuel"
    CONSISTENCY = "consistency"
    AERO = "aero"
    UNKNOWN = "unknown"


_ISSUE_FAMILY = {
    "front_lock": IssueFamily.BRAKING, "lockup": IssueFamily.BRAKING,
    "rear_loose_under_braking": IssueFamily.BRAKING,
    "braking_instability": IssueFamily.BRAKING,
    "understeer": IssueFamily.ROTATION, "mid_corner_understeer": IssueFamily.ROTATION,
    "entry_understeer": IssueFamily.ROTATION, "front_push": IssueFamily.ROTATION,
    "oversteer": IssueFamily.ROTATION, "snap_oversteer": IssueFamily.ROTATION,
    "wheelspin": IssueFamily.TRACTION, "rear_wheelspin": IssueFamily.TRACTION,
    "rear_loose_on_exit": IssueFamily.TRACTION, "poor_traction": IssueFamily.TRACTION,
    "bottoming": IssueFamily.PLATFORM, "kerb": IssueFamily.PLATFORM,
    "wrong_gear": IssueFamily.GEARING, "gearing_too_long": IssueFamily.GEARING,
    "poor_drive_out": IssueFamily.DRIVE_OUT,
    "tyre_deg": IssueFamily.TYRE, "tyre_wear": IssueFamily.TYRE,
    "fuel_use_high": IssueFamily.FUEL,
}


def issue_family_for(issue_type: str) -> IssueFamily:
    return _ISSUE_FAMILY.get(str(issue_type or "").strip().lower(), IssueFamily.UNKNOWN)


class ResidualState(str, Enum):
    RESOLVED = "resolved"
    IMPROVED_BUT_PRESENT = "improved_but_present"
    UNCHANGED = "unchanged"
    WORSENED = "worsened"
    NEW = "new"
    CONFIRMED_GOOD = "confirmed_good"
    GOOD_BEHAVIOUR_DAMAGED = "good_behaviour_damaged"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    INVALID_COMPARISON = "invalid_comparison"
    AMBIGUOUS = "ambiguous"
    NOT_OBSERVED = "not_observed"
    OUT_OF_SCOPE = "out_of_scope"


class IssueRelevance(str, Enum):
    SETUP = "setup"
    DRIVER_TECHNIQUE = "driver_technique"
    GEARING = "gearing"
    DRIVE_OUT = "drive_out"
    TRACK = "track"
    TYRE_FUEL = "tyre_fuel"
    EVIDENCE_LIMITED = "evidence_limited"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class EngineeringIssueIdentity:
    """Immutable issue identity that distinguishes problems WITHOUT display text."""

    issue_family: IssueFamily
    issue_type: str
    axle: str = ""
    phase: str = ""
    segment_id: str = ""
    corner_name: str = ""
    discipline: str = ""
    scope_fingerprint: str = ""
    source_type: str = ""            # corner_comparison / protected / new / practice

    def key(self) -> str:
        raw = "|".join((self.issue_family.value, self.issue_type.lower(),
                        self.axle.lower(), self.phase.lower(),
                        self.segment_id.lower(), self.discipline.lower(),
                        self.scope_fingerprint))
        return f"{ENGINEERING_ISSUE_VERSION}:{hashlib.sha256(raw.encode()).hexdigest()[:20]}"

    def to_dict(self) -> dict:
        return {"issue_family": self.issue_family.value, "issue_type": self.issue_type,
                "axle": self.axle, "phase": self.phase, "segment_id": self.segment_id,
                "corner_name": self.corner_name, "discipline": self.discipline,
                "scope_fingerprint": self.scope_fingerprint,
                "source_type": self.source_type, "key": self.key()}


def _relevance(identity: EngineeringIssueIdentity) -> IssueRelevance:
    fam = identity.issue_family
    if fam in (IssueFamily.GEARING,):
        return IssueRelevance.GEARING
    if fam == IssueFamily.DRIVE_OUT:
        return IssueRelevance.DRIVE_OUT
    if fam in (IssueFamily.TYRE, IssueFamily.FUEL):
        return IssueRelevance.TYRE_FUEL
    if fam in (IssueFamily.BRAKING, IssueFamily.ROTATION, IssueFamily.TRACTION,
               IssueFamily.PLATFORM, IssueFamily.AERO):
        return IssueRelevance.SETUP
    return IssueRelevance.UNKNOWN


@dataclass(frozen=True)
class ResidualIssue:
    identity: EngineeringIssueIdentity
    residual_state: ResidualState
    baseline_class: str
    test_class: str
    baseline_affected: int
    test_affected: int
    sample_count: int
    recurrence_change: str          # decreased/increased/unchanged/n-a
    confidence: str
    comparison_status: str          # comparable/ambiguous/invalid/insufficient
    protected_good: bool
    setup_relevance: str            # IssueRelevance value
    is_new: bool
    is_regression: bool
    warnings: Tuple[str, ...]
    reasoning: str
    supporting: Tuple[str, ...] = ()
    excluded: Tuple[str, ...] = ()
    eval_version: str = ENGINEERING_ISSUE_VERSION

    @property
    def key(self) -> str:
        return self.identity.key()

    @property
    def still_present(self) -> bool:
        return self.residual_state in (ResidualState.IMPROVED_BUT_PRESENT,
                                       ResidualState.UNCHANGED, ResidualState.WORSENED,
                                       ResidualState.NEW,
                                       ResidualState.GOOD_BEHAVIOUR_DAMAGED)

    def to_dict(self) -> dict:
        return {
            "identity": self.identity.to_dict(),
            "residual_state": self.residual_state.value,
            "baseline_class": self.baseline_class, "test_class": self.test_class,
            "baseline_affected": self.baseline_affected,
            "test_affected": self.test_affected, "sample_count": self.sample_count,
            "recurrence_change": self.recurrence_change, "confidence": self.confidence,
            "comparison_status": self.comparison_status,
            "protected_good": self.protected_good,
            "setup_relevance": self.setup_relevance, "is_new": self.is_new,
            "is_regression": self.is_regression, "warnings": list(self.warnings),
            "reasoning": self.reasoning, "supporting": list(self.supporting),
            "excluded": list(self.excluded), "eval_version": self.eval_version,
        }


def _authorable(cls: str) -> bool:
    return str(cls or "").lower() in _AUTHORABLE


def _identity_from_corner(row: Mapping, discipline: str, scope: str,
                          source: str = "corner_comparison") -> EngineeringIssueIdentity:
    issue = str(row.get("issue_type") or "")
    return EngineeringIssueIdentity(
        issue_family=issue_family_for(issue), issue_type=issue,
        axle=str(row.get("axle") or ""), phase=str(row.get("phase") or ""),
        segment_id=str(row.get("segment_id") or ""),
        corner_name=str(row.get("corner_name") or ""), discipline=discipline,
        scope_fingerprint=scope, source_type=source)


def classify_corner_residual(
    row: Mapping, *, discipline: str = "", scope: str = "",
    association_ok: bool = True, min_resolve_samples: int = _MIN_RESOLVE_SAMPLES,
) -> ResidualIssue:
    """Re-classify ONE Phase-3 outcome corner-comparison row into a residual state."""
    identity = _identity_from_corner(row, discipline, scope)
    verdict = str(row.get("verdict") or "").lower()
    b_cls = str(row.get("baseline_class") or "")
    t_cls = str(row.get("test_class") or "")
    b_aff = int(row.get("baseline_affected") or 0)
    t_aff = int(row.get("test_affected") or 0)
    samples = int(row.get("sample_count") or 0)
    conf = str(row.get("confidence") or "")
    is_protected = bool(int(row.get("is_protected") or 0))
    warnings = []

    recurrence_change = ("decreased" if t_aff < b_aff else
                         "increased" if t_aff > b_aff else "unchanged")
    comparison_status = "comparable"
    if not association_ok:
        return ResidualIssue(
            identity=identity, residual_state=ResidualState.INVALID_COMPARISON,
            baseline_class=b_cls, test_class=t_cls, baseline_affected=b_aff,
            test_affected=t_aff, sample_count=samples, recurrence_change="n-a",
            confidence=conf, comparison_status="invalid", protected_good=is_protected,
            setup_relevance=_relevance(identity).value, is_new=False,
            is_regression=False, warnings=("evidence association not resolved",),
            reasoning="comparison invalid: evidence association not resolved")

    if verdict == "unmeasurable" or samples <= 0:
        state = ResidualState.INSUFFICIENT_EVIDENCE
        comparison_status = "insufficient"
        reasoning = "not enough comparable per-corner evidence"
    elif verdict == "regressed":
        if is_protected:
            state = ResidualState.GOOD_BEHAVIOUR_DAMAGED
            reasoning = "a confirmed-good behaviour regressed"
        elif not _authorable(b_cls):
            state = ResidualState.NEW
            reasoning = "a new repeatable issue appeared (absent/weak at baseline)"
        else:
            state = ResidualState.WORSENED
            reasoning = "the issue worsened (higher recurrence/severity)"
    elif verdict == "improved":
        if not _authorable(t_cls) and samples >= min_resolve_samples and conf != "low":
            state = ResidualState.RESOLVED
            reasoning = ("the issue no longer meets its recurrence threshold with "
                         "adequate comparable evidence")
        else:
            state = ResidualState.IMPROVED_BUT_PRESENT
            reasoning = "recurrence decreased but the issue is still present"
            if samples < min_resolve_samples:
                warnings.append("too few valid laps to prove resolution")
    else:  # unchanged
        if _authorable(t_cls) or _authorable(b_cls):
            state = ResidualState.UNCHANGED
            reasoning = "the issue is unchanged and still recurring"
        elif is_protected:
            state = ResidualState.CONFIRMED_GOOD
            reasoning = "a protected behaviour remained good"
        else:
            state = ResidualState.NOT_OBSERVED
            reasoning = "no meaningful recurrence in either window"

    return ResidualIssue(
        identity=identity, residual_state=state, baseline_class=b_cls,
        test_class=t_cls, baseline_affected=b_aff, test_affected=t_aff,
        sample_count=samples, recurrence_change=recurrence_change, confidence=conf,
        comparison_status=comparison_status, protected_good=is_protected,
        setup_relevance=_relevance(identity).value,
        is_new=(state == ResidualState.NEW),
        is_regression=(state in (ResidualState.WORSENED, ResidualState.NEW,
                                 ResidualState.GOOD_BEHAVIOUR_DAMAGED)),
        warnings=tuple(warnings), reasoning=reasoning,
        supporting=(f"outcome_corner:{row.get('segment_id')}",))


def classify_protected_residual(
    row: Mapping, *, discipline: str = "", scope: str = "", association_ok: bool = True,
) -> ResidualIssue:
    """Re-classify a Phase-3 protected-behaviour verdict into a residual state."""
    corners = []
    try:
        corners = list(json.loads(row.get("corners_json") or "[]"))
    except Exception:
        corners = []
    identity = EngineeringIssueIdentity(
        issue_family=IssueFamily.UNKNOWN,
        issue_type=str(row.get("behaviour") or "protected_behaviour"),
        segment_id=(str(corners[0]) if corners else ""), discipline=discipline,
        scope_fingerprint=scope, source_type="protected")
    verdict = str(row.get("verdict") or "").lower()
    if not association_ok:
        state = ResidualState.INVALID_COMPARISON
        reasoning = "comparison invalid"
    elif verdict == "material_regression":
        state = ResidualState.GOOD_BEHAVIOUR_DAMAGED
        reasoning = "confirmed-good behaviour materially regressed"
    elif verdict == "minor_regression":
        state = ResidualState.GOOD_BEHAVIOUR_DAMAGED
        reasoning = "confirmed-good behaviour minorly regressed"
    elif verdict == "preserved":
        state = ResidualState.CONFIRMED_GOOD
        reasoning = "confirmed-good behaviour preserved"
    else:
        state = ResidualState.INSUFFICIENT_EVIDENCE
        reasoning = "protected behaviour unmeasurable"
    return ResidualIssue(
        identity=identity, residual_state=state, baseline_class="", test_class="",
        baseline_affected=0, test_affected=0, sample_count=0,
        recurrence_change="n-a", confidence=str(row.get("confidence") or ""),
        comparison_status=("comparable" if association_ok else "invalid"),
        protected_good=True, setup_relevance=IssueRelevance.SETUP.value, is_new=False,
        is_regression=(state == ResidualState.GOOD_BEHAVIOUR_DAMAGED),
        warnings=(), reasoning=reasoning,
        supporting=(f"protected:{row.get('behaviour')}",))


def residual_issues_from_outcome(
    outcome: Mapping, *, discipline: str = "", scope: str = "",
    association_status: str = "resolved",
) -> Tuple[ResidualIssue, ...]:
    """Derive the full residual-issue set from a persisted Phase-3 outcome dict
    (`get_experiment_outcome`/`get_latest_experiment_outcome`). Deterministic;
    de-duplicates by issue identity, keeping the most-severe residual state."""
    if not isinstance(outcome, Mapping):
        return ()
    assoc_ok = str(association_status or "resolved") == "resolved"
    scope = scope or str(outcome.get("scope_fingerprint") or "")
    by_key: dict = {}

    def _consider(ri: ResidualIssue):
        k = ri.key
        prev = by_key.get(k)
        if prev is None or _severity_rank(ri.residual_state) > _severity_rank(prev.residual_state):
            by_key[k] = ri

    for row in (outcome.get("corners") or []):
        _consider(classify_corner_residual(
            row, discipline=discipline, scope=scope, association_ok=assoc_ok))
    for row in (outcome.get("protected") or []):
        _consider(classify_protected_residual(
            row, discipline=discipline, scope=scope, association_ok=assoc_ok))
    return tuple(sorted(by_key.values(), key=lambda r: r.key))


# Severity ordering for de-dupe + reporting (most-severe first when sorted desc).
_SEVERITY = {
    ResidualState.GOOD_BEHAVIOUR_DAMAGED: 9, ResidualState.NEW: 8,
    ResidualState.WORSENED: 7, ResidualState.UNCHANGED: 6,
    ResidualState.IMPROVED_BUT_PRESENT: 5, ResidualState.AMBIGUOUS: 4,
    ResidualState.INVALID_COMPARISON: 4, ResidualState.INSUFFICIENT_EVIDENCE: 3,
    ResidualState.RESOLVED: 2, ResidualState.CONFIRMED_GOOD: 1,
    ResidualState.NOT_OBSERVED: 0, ResidualState.OUT_OF_SCOPE: 0,
}


def _severity_rank(state: ResidualState) -> int:
    return _SEVERITY.get(state, 0)


def residual_severity_rank(state) -> int:
    try:
        return _SEVERITY.get(ResidualState(state), 0)
    except (ValueError, TypeError):
        return 0
