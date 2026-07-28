"""Capture convergence detector — the deterministic "you can stop driving" judge."""

from __future__ import annotations

import types

from data.track_convergence import (
    assess_capture_convergence, convergence_coach_message, lap_modelling_callout,
    MIN_USABLE_LAPS, MAX_SPREAD_PCT,
)


def _lap(length_m, *, quality="usable", is_pit=False, reasons=()):
    return types.SimpleNamespace(
        path_length_m=length_m,
        quality=types.SimpleNamespace(value=quality),
        reasons=list(reasons),
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


class TestLapModellingCallout:
    def test_a_good_lap_counts_and_reports_progress(self):
        msg = lap_modelling_callout([_lap(4000.0)])
        assert "good lap" in msg.lower()
        assert "more clean lap" in msg.lower()

    def test_enough_good_laps_says_box(self):
        msg = lap_modelling_callout([_lap(4000.0), _lap(4001.0), _lap(3999.0)])
        assert "box this lap" in msg.lower()

    def test_an_off_track_lap_is_explained(self):
        laps = [_lap(4000.0), _lap(0.0, quality="rejected", reasons=["Off-track samples exceed limit"])]
        msg = lap_modelling_callout(laps)
        assert "doesn't count" in msg.lower()
        assert "off track" in msg.lower()
        assert "still need" in msg.lower()          # 1 usable so far, still short

    def test_a_part_lap_is_named(self):
        laps = [_lap(4000.0), _lap(500.0, quality="partial_start")]
        msg = lap_modelling_callout(laps)
        assert "part-lap" in msg.lower()

    def test_a_path_outlier_is_explained(self):
        laps = [_lap(4000.0), _lap(9000.0, quality="rejected", reasons=["Path length 9000 m is a major outlier"])]
        msg = lap_modelling_callout(laps)
        assert "line was too different" in msg.lower()

    def test_no_laps_is_silent(self):
        assert lap_modelling_callout([]) == ""
