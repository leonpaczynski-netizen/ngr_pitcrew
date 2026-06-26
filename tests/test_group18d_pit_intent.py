"""Tests for Group 18D — build_pit_window_response() on RaceStrategyEngine."""
from __future__ import annotations

import os
import sys

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


class _FakeAnnouncer:
    def announce(self, *a, **kw): pass


def _make_engine(stints=None):
    engine = RaceStrategyEngine(
        tracker=_FakeTracker(),
        announcer=_FakeAnnouncer(),
        config={},
        bridge=None,
    )
    if stints is not None:
        # Set plan directly without calling set_plan (which resets active state)
        with engine._lock:
            engine._stints = stints
            engine._assign_lap_ranges()
    return engine


def _make_stint(stint_num=1, laps=10, compound="Medium"):
    return Stint(stint_num=stint_num, laps=laps, compound=compound,
                 ref_lap_ms=0, pace_threshold_ms=2000)


# ---------------------------------------------------------------------------
# Test 1 — future stop (laps_recorded < end_lap)
# ---------------------------------------------------------------------------

def test_future_stop_response():
    s1 = _make_stint(stint_num=1, laps=10, compound="Soft")
    s2 = _make_stint(stint_num=2, laps=10, compound="Medium")
    engine = _make_engine([s1, s2])
    # s1.end_lap = 10; record 5 laps
    result = engine.build_pit_window_response(laps_recorded=5)
    assert "Box on lap 10" in result
    assert "5 lap(s)" in result


# ---------------------------------------------------------------------------
# Test 2 — overdue (laps_recorded > end_lap)
# ---------------------------------------------------------------------------

def test_overdue_stop_response():
    s1 = _make_stint(stint_num=1, laps=10, compound="Soft")
    s2 = _make_stint(stint_num=2, laps=10, compound="Hard")
    engine = _make_engine([s1, s2])
    # s1.end_lap = 10; driver is on lap 12
    result = engine.build_pit_window_response(laps_recorded=12)
    assert "overdue" in result.lower()
    assert "Box now" in result


# ---------------------------------------------------------------------------
# Test 3 — no strategy loaded
# ---------------------------------------------------------------------------

def test_no_strategy_loaded():
    engine = _make_engine(stints=[])
    result = engine.build_pit_window_response(laps_recorded=5)
    assert result == "No strategy loaded. Pit when you judge."


# ---------------------------------------------------------------------------
# Test 4 — all stints completed
# ---------------------------------------------------------------------------

def test_all_stints_completed():
    s1 = _make_stint(stint_num=1, laps=10, compound="Soft")
    engine = _make_engine([s1])
    with engine._lock:
        engine._stints[0].completed = True
    result = engine.build_pit_window_response(laps_recorded=11)
    assert "All planned stops done" in result
