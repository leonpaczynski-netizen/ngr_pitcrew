"""Engineering Brain Phase 7 — state-transition + trend rule tests.

These lock the deterministic classification rules that turn a per-valid-lap affected
sequence into a Trend and an IssueStatus. Critically: a single exceptional lap must
never flip a trend, and the rules are pure (no clock/random, never raise).
"""
import inspect

import pytest

from strategy import state_transitions as ST
from strategy.state_transitions import (
    IssueStatus, Trend, detect_trend, next_status,
)

T, F = True, False


# --------------------------------------------------------------------------- #
# Trend classification
# --------------------------------------------------------------------------- #
def test_insufficient_evidence_below_min_laps():
    assert detect_trend([T, F]) == Trend.INSUFFICIENT_EVIDENCE
    assert detect_trend([]) == Trend.INSUFFICIENT_EVIDENCE
    assert detect_trend([T]) == Trend.INSUFFICIENT_EVIDENCE


def test_improving_when_recent_clears():
    assert detect_trend([T, T, T, F, F, F]) == Trend.IMPROVING
    assert detect_trend([T, T, T, F, F]) == Trend.IMPROVING


def test_worsening_when_recent_recurs():
    assert detect_trend([F, F, F, T, T, T]) == Trend.WORSENING
    assert detect_trend([F, F, F, T, T]) == Trend.WORSENING


def test_unchanged_when_steady():
    assert detect_trend([T, T, T, T]) == Trend.UNCHANGED
    assert detect_trend([F, F, F, F]) == Trend.UNCHANGED


def test_fluctuating_when_alternating():
    assert detect_trend([T, F, T, F, T, F]) == Trend.FLUCTUATING
    assert detect_trend([F, T, F, T, F]) == Trend.FLUCTUATING


def test_single_bad_lap_never_worsens():
    # One late affected lap after a clear run is NOT a worsening trend.
    assert detect_trend([F, F, F, F, T]) != Trend.WORSENING
    assert detect_trend([F, F, F, F, F, T]) != Trend.WORSENING


def test_single_good_lap_never_improves():
    # One late clear lap after a fully-affected run is NOT an improving trend.
    assert detect_trend([T, T, T, T, F]) != Trend.IMPROVING
    assert detect_trend([T, T, T, T, T, F]) != Trend.IMPROVING


def test_trend_is_deterministic():
    seq = [T, T, F, T, F, F]
    assert detect_trend(seq) == detect_trend(list(seq))


# --------------------------------------------------------------------------- #
# Status transitions
# --------------------------------------------------------------------------- #
def test_unknown_when_never_observed():
    assert next_status(IssueStatus.UNKNOWN, Trend.INSUFFICIENT_EVIDENCE,
                       present_now=False, affected=[F, F]) == IssueStatus.UNKNOWN


def test_new_when_just_appeared():
    assert next_status(IssueStatus.UNKNOWN, Trend.INSUFFICIENT_EVIDENCE,
                       present_now=True, affected=[T], total_valid_laps=1) == IssueStatus.NEW


def test_active_when_present_and_steady():
    assert next_status(IssueStatus.NEW, Trend.UNCHANGED, present_now=True,
                       affected=[T, T, T, T]) == IssueStatus.ACTIVE


def test_recovering_when_present_but_improving():
    assert next_status(IssueStatus.ACTIVE, Trend.IMPROVING, present_now=True,
                       affected=[T, T, T, F, F]) == IssueStatus.RECOVERING


def test_resolved_when_clear_for_n_laps():
    assert next_status(IssueStatus.RECOVERING, Trend.IMPROVING, present_now=False,
                       affected=[T, T, F, F, F]) == IssueStatus.RESOLVED


def test_not_resolved_on_a_single_clear_lap():
    # only one clear lap at the end → not enough to resolve
    assert next_status(IssueStatus.ACTIVE, Trend.UNCHANGED, present_now=False,
                       affected=[T, T, T, T, F]) != IssueStatus.RESOLVED


def test_protected_intact_when_never_recurs():
    assert next_status(IssueStatus.PROTECTED, Trend.INSUFFICIENT_EVIDENCE,
                       present_now=False, affected=[F, F, F],
                       is_protected=True) == IssueStatus.PROTECTED


def test_protected_damaged_when_recurs():
    assert next_status(IssueStatus.PROTECTED, Trend.UNCHANGED, present_now=True,
                       affected=[F, F, T], is_protected=True) == IssueStatus.DAMAGED


def test_protected_damaged_to_active_when_worsening():
    assert next_status(IssueStatus.DAMAGED, Trend.WORSENING, present_now=True,
                       affected=[F, T, T, T], is_protected=True) == IssueStatus.ACTIVE


# --------------------------------------------------------------------------- #
# Purity
# --------------------------------------------------------------------------- #
def test_module_is_pure_no_io_or_clock():
    src = inspect.getsource(ST)
    for banned in ("import random", "random.", "time.time", "datetime.now",
                   "import sqlite3", "PyQt", "requests", "urllib", "openai"):
        assert banned not in src, banned


def test_functions_never_raise_on_garbage():
    # None/garbage sequences must not raise (best-effort classification).
    assert detect_trend([None, 0, 1, "", "x"]) in set(Trend)
    assert next_status(IssueStatus.UNKNOWN, Trend.UNCHANGED, present_now=False,
                       affected=[None, 1, 0]) in set(IssueStatus)
