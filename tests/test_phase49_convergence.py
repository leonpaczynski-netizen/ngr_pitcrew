"""Phase 49 — setup convergence & candidate comparison tests.

Covers task test items: setup convergence (23), Base/Qualifying/Race separation (22), setup comparison
(commit 5), and the invariants (one lap never LOCK_READY; one noisy lap never auto-reopens).
"""
from __future__ import annotations

from strategy.setup_convergence import (
    SetupDiscipline as Disc, SetupConvergenceState as St, OutcomeDirection as Out,
    DisciplineConvergenceInput, assess_convergence_state, build_setup_convergence,
    SetupCandidate, build_setup_comparison, COMPARISON_DIMENSIONS,
)


def _inp(disc=Disc.RACE, **kw):
    return DisciplineConvergenceInput(discipline=disc, **kw)


def test_no_evidence_is_insufficient():
    assert assess_convergence_state(_inp(confirming_samples=0)) == St.INSUFFICIENT_EVIDENCE


def test_single_confirming_run_never_lock_ready():
    s = assess_convergence_state(_inp(confirming_samples=1, latest_outcome=Out.IMPROVED,
                                      has_final_confirmation=True))
    assert s != St.LOCK_READY
    assert s == St.IMPROVING


def test_several_valid_confirming_runs_reach_lock_ready():
    s = assess_convergence_state(_inp(confirming_samples=3, latest_outcome=Out.IMPROVED,
                                      has_final_confirmation=True, outstanding_experiments=0))
    assert s == St.LOCK_READY


def test_ready_for_confirmation_without_final_run():
    s = assess_convergence_state(_inp(confirming_samples=3, outstanding_experiments=0,
                                      has_final_confirmation=False))
    assert s == St.READY_FOR_CONFIRMATION


def test_outstanding_experiment_blocks_lock_ready():
    s = assess_convergence_state(_inp(confirming_samples=4, has_final_confirmation=True,
                                      outstanding_experiments=1))
    assert s not in (St.LOCK_READY, St.READY_FOR_CONFIRMATION)


def test_regression_recommends_rollback_when_target_exists():
    assert assess_convergence_state(_inp(confirming_samples=3, regression_detected=True,
                                         has_rollback_target=True)) == St.ROLLBACK_RECOMMENDED
    assert assess_convergence_state(_inp(confirming_samples=3, regression_detected=True,
                                         has_rollback_target=False)) == St.REOPENED


def test_one_noisy_lap_does_not_reopen_stable_setup():
    # a stable setup with an inconclusive (noisy) latest lap stays stable, not reopened
    s = assess_convergence_state(_inp(confirming_samples=4, latest_outcome=Out.INCONCLUSIVE,
                                      has_final_confirmation=True, outstanding_experiments=0))
    assert s not in (St.REOPENED, St.ROLLBACK_RECOMMENDED)
    assert s == St.LOCK_READY


def test_unresolved_weakness_yields_stable_with_uncertainty():
    s = assess_convergence_state(_inp(confirming_samples=3, unresolved_weaknesses=("mid-corner push",)))
    assert s == St.STABLE_WITH_UNCERTAINTY


def test_locked_setup_stays_locked_until_regression():
    assert assess_convergence_state(_inp(confirming_samples=5, is_locked=True)) == St.LOCKED
    assert assess_convergence_state(_inp(confirming_samples=5, is_locked=True,
                                         regression_detected=True, has_rollback_target=True)) \
        == St.ROLLBACK_RECOMMENDED


def test_convergence_fingerprint_is_deterministic():
    a = build_setup_convergence(_inp(confirming_samples=3, has_final_confirmation=True))
    b = build_setup_convergence(_inp(confirming_samples=3, has_final_confirmation=True))
    assert a.fingerprint == b.fingerprint
    assert a.state == St.LOCK_READY


def test_disciplines_are_independent():
    q = build_setup_convergence(_inp(disc=Disc.QUALIFYING, confirming_samples=1))
    r = build_setup_convergence(_inp(disc=Disc.RACE, confirming_samples=3, has_final_confirmation=True))
    assert q.discipline == Disc.QUALIFYING and r.discipline == Disc.RACE
    assert q.state != r.state
    assert q.fingerprint != r.fingerprint


# --- comparison ------------------------------------------------------------

def test_comparison_is_order_independent_and_surfaces_protected_strengths():
    cands = [
        SetupCandidate("Current", "current", "fp-cur", {"consistency": "high"},
                       protected_strengths=("stable rear",), unresolved_risks=("warm-up",)),
        SetupCandidate("Rollback", "rollback", "fp-roll", {"consistency": "moderate"},
                       protected_strengths=("traction",)),
    ]
    a = build_setup_comparison(Disc.RACE, cands)
    b = build_setup_comparison(Disc.RACE, list(reversed(cands)))
    assert a.fingerprint == b.fingerprint
    assert set(a.protected_strengths_union) == {"stable rear", "traction"}
    assert "warm-up" in a.unresolved_risks_union


def test_comparison_missing_dimensions_are_unknown_not_fabricated():
    c = SetupCandidate("Cand", "current", "fp", {"tyres": "MR"})
    cmp = build_setup_comparison(Disc.QUALIFYING, [c])
    payload = cmp.candidates[0].as_payload()
    assert payload["dimensions"]["fuel"] == "unknown"
    assert set(payload["dimensions"].keys()) == set(COMPARISON_DIMENSIONS)
