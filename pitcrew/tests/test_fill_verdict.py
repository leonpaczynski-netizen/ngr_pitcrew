"""Fill verdict for the rival monitor — Story 2, 25 Sep 2026.

`fill_verdict` answers "can this rival reach the flag on his exit fuel?" from
OUR remaining laps.  These tests hold every combination the brief requires, with
special attention to the bound semantics and rule 9 (never clamp a negative).
"""
from __future__ import annotations

import pytest

from pitcrew.race.fill_verdict import FillVerdictResult, fill_verdict


# ----------------------------------------- straight arithmetic


def test_fill_verdict_must_save_not_partial():
    """Needs 48 L, has 40: short by 8 L.  Saving = 8/6 per lap."""
    r = fill_verdict(40.0, 8.0, 6, partial=False, exit_is_a_bound=False)
    assert r.verdict == "must save"
    assert r.bound is False
    assert r.margin_l == pytest.approx(-8.0)
    assert r.saving_per_lap_l == pytest.approx(8.0 / 6)


def test_fill_verdict_spare():
    """Has more than enough."""
    r = fill_verdict(80.0, 8.0, 6, partial=False, exit_is_a_bound=False)
    assert r.verdict == "spare"
    assert r.margin_l == pytest.approx(80.0 - 48.0)
    assert r.bound is False


def test_fill_verdict_exact():
    """Within the exact tolerance → "exact"."""
    r = fill_verdict(48.5, 8.0, 6, partial=False, exit_is_a_bound=False)
    assert r.verdict == "exact"
    assert r.margin_l == pytest.approx(0.5)


def test_fill_verdict_negative_margin_not_clamped():
    """Rule 9: a negative margin is returned as-is, never zero."""
    r = fill_verdict(40.0, 8.0, 6, partial=False, exit_is_a_bound=False)
    assert r.margin_l < 0, "negative margin must not be clamped to zero"


# ----------------------------------------- partial-flag semantics


def test_fill_verdict_partial_still_short():
    """Optimistic (lower-bound) burn still says short → must save, bound=True."""
    r = fill_verdict(40.0, 8.0, 6, partial=True, exit_is_a_bound=False)
    assert r.verdict == "must save"
    assert r.bound is True


def test_fill_verdict_partial_looks_spare():
    """Optimistic burn suggests spare → can't tell (real burn ≥ computed)."""
    r = fill_verdict(60.0, 8.0, 6, partial=True, exit_is_a_bound=False)
    assert r.verdict == "can't tell"


# ----------------------------------------- exit_is_a_bound semantics


def test_fill_verdict_exit_bound_spare_holds():
    """exit_is_a_bound=True: spare holds (more fuel than read → even better)."""
    r = fill_verdict(80.0, 8.0, 6, partial=False, exit_is_a_bound=True)
    assert r.verdict == "spare"
    assert r.bound is True


def test_fill_verdict_exit_bound_must_save_becomes_cant_tell():
    """exit_is_a_bound=True: short reading → can't tell (real out could be higher)."""
    r = fill_verdict(40.0, 8.0, 6, partial=False, exit_is_a_bound=True)
    assert r.verdict == "can't tell"


def test_fill_verdict_exit_bound_exact_becomes_cant_tell():
    """exit_is_a_bound=True: exact reading → can't tell."""
    r = fill_verdict(48.5, 8.0, 6, partial=False, exit_is_a_bound=True)
    assert r.verdict == "can't tell"


def test_fill_verdict_both_bounds_cant_tell():
    """Both bounds active → opposite directions → can't tell."""
    r = fill_verdict(40.0, 8.0, 6, partial=True, exit_is_a_bound=True)
    assert r.verdict == "can't tell"


# ----------------------------------------- null inputs


def test_fill_verdict_null_fuel_out_cant_tell():
    r = fill_verdict(None, 8.0, 6, partial=False, exit_is_a_bound=False)
    assert r.verdict == "can't tell"


def test_fill_verdict_null_burn_cant_tell():
    r = fill_verdict(40.0, None, 6, partial=False, exit_is_a_bound=False)
    assert r.verdict == "can't tell"


def test_fill_verdict_null_laps_cant_tell():
    r = fill_verdict(40.0, 8.0, None, partial=False, exit_is_a_bound=False)
    assert r.verdict == "can't tell"
