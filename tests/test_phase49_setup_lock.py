"""Phase 49 — setup lock & restriction policy tests.

Covers task test items: setup lock (24), setup restriction (25), and the invariants (lock cannot occur
without explicit confirmation; a refresh cannot lock/unlock; lock is not an Apply bypass).
"""
from __future__ import annotations

from strategy.setup_convergence import SetupConvergenceState as St, SetupDiscipline as Disc
from strategy.setup_lock import (
    SetupLockPolicy, SetupRestrictionState as R, AllowedPostLockChange as Ch,
    build_lock_decision, lock_permitted, post_lock_change_allowed,
)


def test_lock_requires_explicit_confirmation():
    unconfirmed = build_lock_decision(Disc.RACE, St.LOCK_READY, confirmed=False)
    assert unconfirmed.locked is False
    assert "confirmation required" in unconfirmed.reason
    confirmed = build_lock_decision(Disc.RACE, St.LOCK_READY, confirmed=True)
    assert confirmed.locked is True
    assert confirmed.restriction_state == R.LOCKED


def test_lock_not_permitted_from_insufficient_convergence():
    d = build_lock_decision(Disc.RACE, St.INSUFFICIENT_EVIDENCE, confirmed=True)
    assert d.locked is False
    assert "not permitted" in d.reason
    assert not lock_permitted(St.INSUFFICIENT_EVIDENCE)
    assert not lock_permitted(St.EXPLORING)
    assert lock_permitted(St.LOCK_READY)


def test_refresh_semantics_pure_confirmed_flag_gates_lock():
    # calling the builder repeatedly with confirmed=False never locks (a refresh cannot lock)
    for _ in range(5):
        d = build_lock_decision(Disc.QUALIFYING, St.LOCK_READY, confirmed=False)
        assert d.locked is False


def test_restriction_after_lock_yields_parc_ferme_style_state():
    pol = SetupLockPolicy(has_lock_deadline=True, mandatory=True, restriction_after_lock=True,
                          allowed_post_lock_changes=(Ch.TYRE_PRESSURE, Ch.BRAKE_BIAS))
    d = build_lock_decision(Disc.RACE, St.LOCK_READY, confirmed=True, policy=pol)
    assert d.restriction_state == R.RESTRICTED_AFTER_LOCK
    assert post_lock_change_allowed(d, Ch.TYRE_PRESSURE) is True
    assert post_lock_change_allowed(d, Ch.RIDE_HEIGHT) is False


def test_plain_lock_permits_nothing_extra_without_reopening():
    d = build_lock_decision(Disc.RACE, St.LOCK_READY, confirmed=True)  # no policy -> plain LOCKED
    assert d.restriction_state == R.LOCKED
    assert post_lock_change_allowed(d, Ch.TYRE_PRESSURE) is False


def test_advisory_lock_when_deadline_but_unconfirmed():
    pol = SetupLockPolicy(has_lock_deadline=True, mandatory=False)
    d = build_lock_decision(Disc.RACE, St.LOCK_READY, confirmed=False, policy=pol)
    assert d.restriction_state == R.ADVISORY_LOCK
    assert d.locked is False


def test_stable_with_uncertainty_can_lock_with_warning():
    d = build_lock_decision(Disc.RACE, St.STABLE_WITH_UNCERTAINTY, confirmed=True,
                            known_compromises=("mid-corner understeer",))
    assert d.locked is True
    assert "mid-corner understeer" in d.known_compromises


def test_lock_decision_fingerprint_is_deterministic():
    a = build_lock_decision(Disc.RACE, St.LOCK_READY, confirmed=True, selected_fingerprint="fp1",
                            supporting_evidence=("3 long runs",))
    b = build_lock_decision(Disc.RACE, St.LOCK_READY, confirmed=True, selected_fingerprint="fp1",
                            supporting_evidence=("3 long runs",))
    assert a.fingerprint == b.fingerprint
