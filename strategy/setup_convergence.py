"""Setup convergence & final comparison (Program 2, Phase 49).

Turns cumulative Practice evidence into a controlled view of how each setup discipline (Base /
Qualifying / Race) is maturing, and provides a deterministic side-by-side comparison of candidate
setups before the official race. It NEVER authors a setup value, never auto-applies, never declares a
setup "ultimate" or universally optimal, and never treats "newer" as "better".

Doctrine:
  * A setup must not become LOCK_READY from one quick lap alone — LOCK_READY requires several valid
    confirming sessions plus an explicit final-confirmation run and no outstanding experiments.
  * One noisy lap does not automatically REOPEN a stable setup; only a genuine regression (a validated
    worse outcome) recommends rollback / reopen.
  * Base, Qualifying and Race setups converge independently and need not converge to the same values.
  * Comparison is descriptive: no timestamp authority, protected strengths are surfaced, unresolved
    risks are surfaced, and nothing is graded "best" in the absolute.

Purity: Qt-free, DB-free, offline, deterministic, no wall-clock, never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

SETUP_CONVERGENCE_VERSION = "setup_convergence_v1"
SETUP_CONVERGENCE_SCHEMA = 1


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{SETUP_CONVERGENCE_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


class SetupDiscipline(str, Enum):
    BASE = "base"
    QUALIFYING = "qualifying"
    RACE = "race"


class SetupConvergenceState(str, Enum):
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    EXPLORING = "exploring"
    DIVERGING = "diverging"
    IMPROVING = "improving"
    STABLE_WITH_UNCERTAINTY = "stable_with_uncertainty"
    PROVISIONAL = "provisional"
    READY_FOR_CONFIRMATION = "ready_for_confirmation"
    LOCK_READY = "lock_ready"
    LOCKED = "locked"
    REOPENED = "reopened"
    ROLLBACK_RECOMMENDED = "rollback_recommended"


class OutcomeDirection(str, Enum):
    IMPROVED = "improved"
    WORSE = "worse"
    INCONCLUSIVE = "inconclusive"
    NONE = "none"


_MIN_CONFIRMING_FOR_LOCK = 3


@dataclass(frozen=True)
class DisciplineConvergenceInput:
    """Normalised, context-safe evidence for one setup discipline. Built from the cumulative evidence +
    outcome/working-window authorities. ``confirming_samples`` counts EXACT-context valid confirming
    runs only (partial/incompatible evidence never counts as confirming)."""
    discipline: SetupDiscipline
    confirming_samples: int = 0
    latest_outcome: OutcomeDirection = OutcomeDirection.NONE
    regression_detected: bool = False       # a VALIDATED worse outcome (not a noisy lap)
    diverging: bool = False                 # experiments pull the window in conflicting directions
    has_final_confirmation: bool = False    # an explicit final-setup-confirmation run completed
    outstanding_experiments: int = 0
    has_rollback_target: bool = False
    is_locked: bool = False
    proven_strengths: Tuple[str, ...] = field(default_factory=tuple)
    unresolved_weaknesses: Tuple[str, ...] = field(default_factory=tuple)
    failed_directions: Tuple[str, ...] = field(default_factory=tuple)
    interaction_risks: Tuple[str, ...] = field(default_factory=tuple)
    current_best_fingerprint: str = ""
    parent_fingerprint: str = ""
    rollback_fingerprint: str = ""
    provenance: str = ""


@dataclass(frozen=True)
class SetupConvergence:
    discipline: SetupDiscipline
    state: SetupConvergenceState
    confidence: str                         # "none"|"low"|"moderate"|"high" (rule-based)
    current_best_fingerprint: str
    parent_fingerprint: str
    rollback_fingerprint: str
    provenance: str
    proven_strengths: Tuple[str, ...]
    unresolved_weaknesses: Tuple[str, ...]
    failed_directions: Tuple[str, ...]
    interaction_risks: Tuple[str, ...]
    outstanding_experiments: int
    fingerprint: str = ""

    def as_payload(self) -> dict:
        return {
            "discipline": self.discipline.value,
            "state": self.state.value,
            "confidence": self.confidence,
            "current_best": _norm(self.current_best_fingerprint),
            "parent": _norm(self.parent_fingerprint),
            "rollback": _norm(self.rollback_fingerprint),
            "provenance": _norm(self.provenance),
            "proven_strengths": sorted(_norm(s) for s in self.proven_strengths if _norm(s)),
            "unresolved_weaknesses": sorted(_norm(s) for s in self.unresolved_weaknesses if _norm(s)),
            "failed_directions": sorted(_norm(s) for s in self.failed_directions if _norm(s)),
            "interaction_risks": sorted(_norm(s) for s in self.interaction_risks if _norm(s)),
            "outstanding_experiments": int(self.outstanding_experiments),
        }


def _confidence_for(state: SetupConvergenceState, confirming: int) -> str:
    if state in (SetupConvergenceState.INSUFFICIENT_EVIDENCE, SetupConvergenceState.EXPLORING,
                 SetupConvergenceState.ROLLBACK_RECOMMENDED, SetupConvergenceState.REOPENED,
                 SetupConvergenceState.DIVERGING):
        return "low" if confirming >= 1 else "none"
    if state in (SetupConvergenceState.LOCK_READY, SetupConvergenceState.LOCKED,
                 SetupConvergenceState.READY_FOR_CONFIRMATION):
        return "high"
    return "moderate"


def assess_convergence_state(inp: DisciplineConvergenceInput) -> SetupConvergenceState:
    """Deterministic convergence ladder. Regression dominates; a locked setup stays locked unless a
    regression reopens it; LOCK_READY needs several confirming runs + a final confirmation and no
    outstanding experiments; a single noisy/inconclusive lap never reopens a stable setup."""
    S = SetupConvergenceState
    if inp.is_locked and not inp.regression_detected:
        return S.LOCKED
    if inp.regression_detected:
        return S.ROLLBACK_RECOMMENDED if inp.has_rollback_target else S.REOPENED
    if inp.confirming_samples <= 0:
        return S.INSUFFICIENT_EVIDENCE
    if inp.diverging:
        return S.DIVERGING
    if inp.confirming_samples == 1:
        # a single confirming run is exploration, never lock-ready
        return S.EXPLORING if inp.latest_outcome != OutcomeDirection.IMPROVED else S.IMPROVING
    # >= 2 confirming samples
    stable = inp.confirming_samples >= 2 and inp.latest_outcome != OutcomeDirection.WORSE
    if inp.unresolved_weaknesses:
        return S.STABLE_WITH_UNCERTAINTY if stable else S.EXPLORING
    if (inp.confirming_samples >= _MIN_CONFIRMING_FOR_LOCK and inp.has_final_confirmation
            and inp.outstanding_experiments == 0):
        return S.LOCK_READY
    if inp.confirming_samples >= _MIN_CONFIRMING_FOR_LOCK and inp.outstanding_experiments == 0:
        return S.READY_FOR_CONFIRMATION
    if inp.latest_outcome == OutcomeDirection.IMPROVED:
        return S.IMPROVING
    return S.PROVISIONAL


def build_setup_convergence(inp: DisciplineConvergenceInput) -> SetupConvergence:
    state = assess_convergence_state(inp)
    conf = _confidence_for(state, inp.confirming_samples)
    sc = SetupConvergence(
        discipline=inp.discipline, state=state, confidence=conf,
        current_best_fingerprint=_norm(inp.current_best_fingerprint),
        parent_fingerprint=_norm(inp.parent_fingerprint),
        rollback_fingerprint=_norm(inp.rollback_fingerprint),
        provenance=_norm(inp.provenance),
        proven_strengths=inp.proven_strengths, unresolved_weaknesses=inp.unresolved_weaknesses,
        failed_directions=inp.failed_directions, interaction_risks=inp.interaction_risks,
        outstanding_experiments=int(inp.outstanding_experiments), fingerprint="")
    return SetupConvergence(
        discipline=sc.discipline, state=sc.state, confidence=sc.confidence,
        current_best_fingerprint=sc.current_best_fingerprint, parent_fingerprint=sc.parent_fingerprint,
        rollback_fingerprint=sc.rollback_fingerprint, provenance=sc.provenance,
        proven_strengths=sc.proven_strengths, unresolved_weaknesses=sc.unresolved_weaknesses,
        failed_directions=sc.failed_directions, interaction_risks=sc.interaction_risks,
        outstanding_experiments=sc.outstanding_experiments, fingerprint=_fp(sc.as_payload()))


# ---------------------------------------------------------------------------
# Candidate comparison (descriptive, never "best in the absolute")
# ---------------------------------------------------------------------------

COMPARISON_DIMENSIONS: Tuple[str, ...] = (
    "target_performance", "representative_pace", "consistency", "tyres", "fuel", "braking",
    "rotation", "traction", "stability", "gearing", "protected_strengths", "driver_confidence",
    "evidence_quality",
)


@dataclass(frozen=True)
class SetupCandidate:
    """One candidate in the comparison (base / qualifying / race / previous-best / current / rollback).
    ``dimensions`` maps a COMPARISON_DIMENSIONS key to a short label/value string; missing keys are
    treated as 'unknown' (never fabricated)."""
    label: str
    role: str                                # e.g. "current" | "previous_best" | "rollback"
    fingerprint: str = ""
    dimensions: Mapping[str, str] = field(default_factory=dict)
    protected_strengths: Tuple[str, ...] = field(default_factory=tuple)
    unresolved_risks: Tuple[str, ...] = field(default_factory=tuple)

    def as_payload(self) -> dict:
        return {"label": _norm(self.label), "role": _lc(self.role), "fingerprint": _norm(self.fingerprint),
                "dimensions": {k: _norm(self.dimensions.get(k, "unknown")) for k in COMPARISON_DIMENSIONS},
                "protected_strengths": sorted(_norm(s) for s in self.protected_strengths if _norm(s)),
                "unresolved_risks": sorted(_norm(s) for s in self.unresolved_risks if _norm(s))}


@dataclass(frozen=True)
class SetupCandidateComparison:
    discipline: SetupDiscipline
    candidates: Tuple[SetupCandidate, ...]
    dimensions: Tuple[str, ...]
    protected_strengths_union: Tuple[str, ...]
    unresolved_risks_union: Tuple[str, ...]
    fingerprint: str = ""

    def as_payload(self) -> dict:
        return {"discipline": self.discipline.value,
                "candidates": [c.as_payload() for c in self.candidates],
                "dimensions": list(self.dimensions),
                "protected_strengths_union": list(self.protected_strengths_union),
                "unresolved_risks_union": list(self.unresolved_risks_union)}


def build_setup_comparison(
    discipline: SetupDiscipline,
    candidates: Sequence[SetupCandidate],
) -> SetupCandidateComparison:
    """Deterministic, order-independent side-by-side comparison across the fixed dimension set. Surfaces
    the union of protected strengths (which must be preserved by any change) and unresolved risks. Does
    NOT declare a winner — a human makes the final selection with these facts."""
    ordered = tuple(sorted(candidates, key=lambda c: (_lc(c.role), _norm(c.label))))
    strengths = tuple(sorted({_norm(s) for c in ordered for s in c.protected_strengths if _norm(s)}))
    risks = tuple(sorted({_norm(r) for c in ordered for r in c.unresolved_risks if _norm(r)}))
    cmp = SetupCandidateComparison(discipline=discipline, candidates=ordered,
                                   dimensions=COMPARISON_DIMENSIONS,
                                   protected_strengths_union=strengths, unresolved_risks_union=risks,
                                   fingerprint="")
    return SetupCandidateComparison(discipline=cmp.discipline, candidates=cmp.candidates,
                                    dimensions=cmp.dimensions,
                                    protected_strengths_union=cmp.protected_strengths_union,
                                    unresolved_risks_union=cmp.unresolved_risks_union,
                                    fingerprint=_fp(cmp.as_payload()))
