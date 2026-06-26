"""Tests for Group 18D — _check_pit_window() warning message update."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, call

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from strategy.engine import RaceStrategyEngine, Stint


# ---------------------------------------------------------------------------
# Minimal stubs
# ---------------------------------------------------------------------------

class _FakeTracker:
    laps_recorded = 0
    best_lap_ms = 0
    avg_fuel_per_lap = 0.0
    last_fuel = 0.0
    tyre_states = {}


def _make_engine_with_mock_announcer():
    mock_announcer = MagicMock()
    tracker = _FakeTracker()
    engine = RaceStrategyEngine(
        tracker=tracker,
        announcer=mock_announcer,
        config={},
        bridge=None,
    )
    return engine, mock_announcer, tracker


def _make_stint(stint_num=1, laps=10, compound="Medium"):
    return Stint(stint_num=stint_num, laps=laps, compound=compound,
                 ref_lap_ms=0, pace_threshold_ms=2000)


# ---------------------------------------------------------------------------
# Test 7 — warn fires at end_lap - 2, message contains new text
# ---------------------------------------------------------------------------

def test_warn_message_contains_pit_window_opens():
    engine, mock_announcer, _ = _make_engine_with_mock_announcer()
    s1 = _make_stint(stint_num=1, laps=10, compound="Soft")
    s2 = _make_stint(stint_num=2, laps=10, compound="Hard")
    with engine._lock:
        engine._stints = [s1, s2]
        engine._assign_lap_ranges()
    # s1.end_lap = 10; warn should fire at lap 8
    with engine._lock:
        engine._check_pit_window(engine._stints[0], laps_recorded=8)

    assert mock_announcer.announce.called
    all_calls = mock_announcer.announce.call_args_list
    warn_calls = [c for c in all_calls if "Pit window opens in 2 laps" in str(c)]
    assert len(warn_calls) == 1
    # Also check "Box on lap" is in the message
    msg_arg = warn_calls[0].args[0]
    assert "Pit window opens in 2 laps" in msg_arg
    assert "Box on lap 10" in msg_arg


# ---------------------------------------------------------------------------
# Test 8 — warn does NOT fire again when warn_issued=True
# ---------------------------------------------------------------------------

def test_warn_not_repeated_when_warn_issued():
    engine, mock_announcer, _ = _make_engine_with_mock_announcer()
    s1 = _make_stint(stint_num=1, laps=10, compound="Soft")
    s2 = _make_stint(stint_num=2, laps=10, compound="Hard")
    with engine._lock:
        engine._stints = [s1, s2]
        engine._assign_lap_ranges()
        engine._stints[0].warn_issued = True  # already issued

    with engine._lock:
        engine._check_pit_window(engine._stints[0], laps_recorded=8)

    # The warn block should NOT fire; only box/overdue blocks may fire (neither at lap 8)
    all_calls = mock_announcer.announce.call_args_list
    warn_calls = [c for c in all_calls if "Pit window opens in 2 laps" in str(c)]
    assert len(warn_calls) == 0
