"""Capture convergence detector — the deterministic "you can stop driving" judge."""

from __future__ import annotations

import types

from data.track_convergence import (
    assess_capture_convergence, convergence_coach_message,
    MIN_USABLE_LAPS, MAX_SPREAD_PCT,
)


def _lap(length_m, *, quality="usable", is_pit=False):
    return types.SimpleNamespace(
        path_length_m=length_m,
        quality=types.SimpleNamespace(value=quality),
        is_pit_lap=is_pit)


def test_too_few_laps_is_not_converged():
    r = assess_capture_convergence([_lap(4000.0), _lap(4001.0)])
    assert r.converged is False
    assert r.usable_laps == 2
    assert "at least" in r.reason.lower()
    assert r.laps_remaining_hint == MIN_USABLE_LAPS - 2


def test_three_consistent_laps_converge():
    r = assess_capture_convergence([_lap(4000.0), _lap(4002.0), _lap(3999.0)])
    assert r.converged is True
    assert r.usable_laps == 3
    assert r.laps_remaining_hint == 0


def test_a_wandering_recent_lap_blocks_convergence():
    # Three usable laps, but the spread across the last window is too wide (line moving).
    r = assess_capture_convergence([_lap(4000.0), _lap(4050.0), _lap(3950.0)])
    assert r.converged is False
    assert r.spread_pct > MAX_SPREAD_PCT
    assert "settling" in r.reason.lower()


def test_pit_and_rejected_laps_are_ignored():
    laps = [_lap(4000.0), _lap(9999.0, is_pit=True), _lap(500.0, quality="rejected"),
            _lap(4001.0), _lap(3999.0)]
    r = assess_capture_convergence(laps)
    assert r.usable_laps == 3            # only the three usable, non-pit laps count
    assert r.converged is True


def test_convergence_only_reads_the_recent_window():
    # An early wild lap must not block convergence once the recent window is clean.
    laps = [_lap(4300.0), _lap(4000.0), _lap(4001.0), _lap(3999.0)]
    r = assess_capture_convergence(laps)
    assert r.converged is True


def test_coach_message_tracks_state():
    not_enough = assess_capture_convergence([_lap(4000.0)])
    assert "keep going" in convergence_coach_message(not_enough).lower()
    done = assess_capture_convergence([_lap(4000.0), _lap(4001.0), _lap(3999.0)])
    assert "box this lap" in convergence_coach_message(done).lower()
