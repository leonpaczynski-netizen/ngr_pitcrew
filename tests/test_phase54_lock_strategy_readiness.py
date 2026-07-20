"""Phase 54 — setup-lock + strategy-finalisation readiness (task items 9-10)."""
from __future__ import annotations

from strategy.setup_convergence import SetupConvergenceState as CS
from strategy.strategy_maturity import StrategyMaturity as M
from strategy.setup_strategy_readiness import (
    derive_setup_lock_readiness, derive_strategy_finalisation_readiness, build_setup_strategy_readiness,
)


# --- lock readiness --------------------------------------------------------

def test_lock_ready_is_eligible_but_not_locked():
    r = derive_setup_lock_readiness("race", CS.LOCK_READY.value)
    assert r.lock_eligible is True and r.is_locked is False


def test_insufficient_convergence_not_lock_eligible():
    r = derive_setup_lock_readiness("race", CS.INSUFFICIENT_EVIDENCE.value)
    assert r.lock_eligible is False
    assert any("does not yet permit" in b for b in r.blockers)


def test_already_locked_is_not_eligible():
    r = derive_setup_lock_readiness("race", CS.LOCK_READY.value, is_locked=True)
    assert r.lock_eligible is False and r.is_locked is True
    assert "already locked" in r.blockers


def test_lock_ready_never_means_locked():
    # readiness derivation never sets is_locked from the convergence state
    r = derive_setup_lock_readiness("qualifying", CS.LOCK_READY.value)
    assert r.is_locked is False


# --- strategy finalisation readiness ---------------------------------------

def test_finalisation_ready_is_eligible_but_not_finalised():
    r = derive_strategy_finalisation_readiness(M.FINALISATION_READY.value)
    assert r.finalisation_eligible is True and r.is_finalised is False


def test_developing_strategy_not_finalisation_eligible():
    r = derive_strategy_finalisation_readiness(M.DEVELOPING.value, missing_evidence=("validated long run",))
    assert r.finalisation_eligible is False
    assert "validated long run" in r.missing_evidence


def test_finalised_strategy_not_eligible():
    r = derive_strategy_finalisation_readiness(M.FINALISATION_READY.value, is_finalised=True)
    assert r.finalisation_eligible is False and r.is_finalised is True


# --- combined --------------------------------------------------------------

def test_build_readiness_reports_lock_ready_disciplines():
    r = build_setup_strategy_readiness(
        {"base": CS.IMPROVING.value, "qualifying": CS.LOCK_READY.value, "race": CS.READY_FOR_CONFIRMATION.value},
        M.FINALISATION_READY.value)
    assert set(r.lock_ready_disciplines) == {"qualifying", "race"}
    assert r.strategy_final_ready is True


def test_build_readiness_respects_persisted_locks_and_finalisation():
    r = build_setup_strategy_readiness(
        {"race": CS.LOCK_READY.value}, M.FINALISATION_READY.value,
        locked_disciplines=("race",), strategy_finalised=True)
    assert r.lock_ready_disciplines == ()  # race already locked
    assert r.strategy_final_ready is False  # already finalised


def test_readiness_deterministic():
    a = build_setup_strategy_readiness({"race": CS.LOCK_READY.value}, M.PROVISIONAL.value)
    b = build_setup_strategy_readiness({"race": CS.LOCK_READY.value}, M.PROVISIONAL.value)
    assert a.fingerprint == b.fingerprint
