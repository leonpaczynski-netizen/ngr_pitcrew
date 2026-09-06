"""The tyre split's direction: per lap, and only where five laps say so.

The split itself is the one reading on the dashboard with evidence behind it -
absolute temperatures are endogenous and GT7 has no published window, while
the rear-front and RR-RL gaps are monotone and match the measured wear map at
r=+0.82. What it could not say was whether the split was growing or shrinking,
which is the difference between a tyre that is going and one that has settled.
"""
from __future__ import annotations

import pytest

from pitcrew.race.tyre_split import (
    MIN_LAPS_FOR_TREND,
    RATE_WORTH_SAYING_C,
    SplitHistory,
)


def _lap(rr: float, rl: float = 91.0, fl: float = 84.0, fr: float = 85.0):
    return {"fl": fl, "fr": fr, "rl": rl, "rr": rr}


def a_history(rears) -> SplitHistory:
    history = SplitHistory()
    for rr in rears:
        history.note_lap(_lap(rr))
    return history


# ------------------------------------------------------------------ the slope

def test_a_widening_split_is_positive_and_a_settling_one_negative():
    widening = a_history([95, 98, 101, 104, 107, 110])
    rate, laps = widening.rate("rr")
    assert rate is not None and rate > 0
    assert laps == 6

    settling = a_history([110, 107, 104, 101, 98, 95])
    rate, _ = settling.rate("rr")
    assert rate is not None and rate < 0


def test_movement_inside_the_instrument_is_no_answer_and_not_a_zero():
    """**Rule 3 where it would be easiest to write a zero.** A rate of zero
    says the split has settled, which is a claim; no rate says nobody can
    tell yet, which is the truth. The board renders those differently."""
    steady = a_history([100, 99.6, 100.4, 100, 99.8, 100.2])
    rate, laps = steady.rate("rr")
    assert rate is None
    assert laps == 6, "the lap count is still worth returning"


def test_the_threshold_is_where_the_docstring_says_it_is():
    """Derived from the measured per-corner noise floor, not measured. A
    drift just under it says nothing; just over it says something."""
    step = RATE_WORTH_SAYING_C
    under = a_history([100 + i * (step * 0.6) for i in range(6)])
    over = a_history([100 + i * (step * 1.6) for i in range(6)])
    assert under.rate("rr")[0] is None
    assert over.rate("rr")[0] is not None


def test_four_laps_is_not_a_trend():
    """Three points is a slope through noise; five is a trend."""
    short = a_history([95, 99, 103, 107])
    assert len(short.laps) == MIN_LAPS_FOR_TREND - 1
    assert short.rate("rr")[0] is None


# ------------------------------------------------------------ what it samples

def test_a_lap_missing_a_corner_is_dropped_rather_than_part_filled():
    """A gap in the middle of a series would be fitted straight through as
    though the lap had been measured."""
    history = SplitHistory()
    history.note_lap(_lap(100))
    history.note_lap({"fl": 84.0, "fr": None, "rl": 91.0, "rr": 104.0})
    history.note_lap(None)
    history.note_lap({})
    assert len(history.laps) == 1


def test_only_the_hotter_side_of_a_pair_states_a_split():
    """"13 degrees cooler" is the same finding said about the wrong corner."""
    history = a_history([104])
    assert history.split_now("rr") == pytest.approx(13.0)
    assert history.split_now("rl") is None


def test_a_new_session_forgets_the_last_one():
    """**CLAUDE.md rule 11.** A race once opened judging its fresh tyres
    against practice's worn ones, and the reset that would have prevented it
    existed and was called only from a test file."""
    history = a_history([95, 98, 101, 104, 107, 110])
    assert history.rate("rr")[0] is not None
    history.new_session()
    assert history.laps == pytest.approx([]) or len(history.laps) == 0
    assert history.rate("rr") == (None, 0)


def test_the_window_forgets_laps_too_old_to_describe_these_tyres():
    history = a_history(range(90, 130))
    assert len(history.laps) <= 8


# --------------------------------------------------- the controller's own seam

def test_the_bridge_takes_and_clears_in_one_call(qt_app=None):
    """A lap counted twice, or a lap's frames leaking into the next lap's
    mean, are both a wrong split - so taking the means is also what resets
    them, and there is exactly one caller."""
    pytest.importorskip("PyQt6.QtWidgets")
    from PyQt6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from pitcrew.controller import TelemetryBridge

    from pitcrew.controller import new_temp_window

    bridge = TelemetryBridge.__new__(TelemetryBridge)
    bridge._corner_sums = {"fl": 200.0, "fr": 200.0, "rl": 200.0, "rr": 240.0}
    bridge._corner_frames = 2
    # Taking the means is now locked against the telemetry thread that fills
    # them - see `note_corner_temps`.
    bridge._temp_window, bridge._temp_lock = new_temp_window()
    means = bridge.take_corner_means()
    assert means["rr"] == pytest.approx(120.0)
    assert bridge.take_corner_means() is None, "the accumulator was not cleared"


# ------------------------------------------------- what the board actually reads

def _a_bridge():
    from PyQt6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from pitcrew.controller import TelemetryBridge, new_temp_window

    bridge = TelemetryBridge.__new__(TelemetryBridge)
    # **Through the same factory the real one uses.** These built a bare
    # deque, so when the window gained a lock on 6 Sep 2026 three tests here
    # failed on an attribute the bridge was now expected to have.
    bridge._temp_window, bridge._temp_lock = new_temp_window()
    return bridge


def test_the_board_reads_a_three_second_mean_not_a_frame():
    """**The docstring claimed this for months and the controller returned a
    single packet.** Four numbers jittering at 60 Hz against a per-lap signal
    of about 10 °C is not a reading anybody can use."""
    pytest.importorskip("PyQt6.QtWidgets")
    from pitcrew.controller import _monotonic

    bridge = _a_bridge()
    now = _monotonic()
    for offset in range(5):
        bridge._temp_window.append((now, (80.0 + offset, 84.0, 90.0, 100.0)))
    means = bridge.recent_corner_means()
    assert means["fl"] == pytest.approx(82.0)
    assert means["rr"] == pytest.approx(100.0)


def test_frames_older_than_the_window_are_dropped():
    """A stale frame from before the last corner is not this straight."""
    pytest.importorskip("PyQt6.QtWidgets")
    from pitcrew.controller import _monotonic
    from pitcrew.race.tyre_split import BOARD_SMOOTHING_S

    bridge = _a_bridge()
    now = _monotonic()
    bridge._temp_window.append(
        (now - BOARD_SMOOTHING_S - 5, (999.0, 999.0, 999.0, 999.0)))
    bridge._temp_window.append((now, (80.0, 84.0, 90.0, 100.0)))
    assert bridge.recent_corner_means()["fl"] == pytest.approx(80.0)


def test_nothing_recent_is_none_and_never_a_zero():
    pytest.importorskip("PyQt6.QtWidgets")
    assert _a_bridge().recent_corner_means() is None


def test_the_display_filter_is_not_the_trend_window():
    """The split trend runs on WHOLE-LAP means, which is the unit the r=+0.82
    against the wear map was measured in. A three-second mean is a display
    filter and is never used as evidence."""
    from pitcrew.race.tyre_split import BOARD_SMOOTHING_S, WINDOW_LAPS

    assert BOARD_SMOOTHING_S == 3.0
    assert WINDOW_LAPS >= MIN_LAPS_FOR_TREND
