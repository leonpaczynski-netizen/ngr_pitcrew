"""Tests for data.practice_analysis.compute_practice_tips.

No Qt dependency, no dashboard import.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from data.practice_analysis import PracticeTips, compute_practice_tips


# ---------------------------------------------------------------------------
# Minimal stubs
# ---------------------------------------------------------------------------

class _Packet:
    def __init__(self, fl=80.0, fr=80.0, rl=80.0, rr=80.0):
        self.tyre_temp_fl = fl
        self.tyre_temp_fr = fr
        self.tyre_temp_rl = rl
        self.tyre_temp_rr = rr


class _Thresholds:
    def __init__(self, cold_max=70.0, hot_max=110.0):
        self.cold_max = cold_max
        self.hot_max = hot_max


class _LapStats:
    def __init__(
        self,
        lock_up_count=0,
        wheelspin_count=0,
        oversteer_count=0,
        oversteer_throttle_on_count=0,
        snap_throttle_count=0,
        brake_consistency_m=-1.0,
    ):
        self.lock_up_count = lock_up_count
        self.wheelspin_count = wheelspin_count
        self.oversteer_count = oversteer_count
        self.oversteer_throttle_on_count = oversteer_throttle_on_count
        self.snap_throttle_count = snap_throttle_count
        self.brake_consistency_m = brake_consistency_m


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_consistency_bad():
    laps = [90_000.0, 88_000.0, 92_500.0]
    result = compute_practice_tips(laps, std_ms=2000.0, last_packet=None,
                                   thresholds=None, last_lap_stats=None)
    assert "High variation" in result.consistency_tip
    assert "±2.00s" in result.consistency_tip


def test_consistency_good():
    laps = [90_000.0, 90_200.0, 90_400.0]
    result = compute_practice_tips(laps, std_ms=500.0, last_packet=None,
                                   thresholds=None, last_lap_stats=None)
    assert "Excellent" in result.consistency_tip


def test_no_laps_returns_empty_tips():
    result = compute_practice_tips([], std_ms=0.0, last_packet=None,
                                   thresholds=None, last_lap_stats=None)
    assert result.consistency_tip == ""
    assert result.gap_tip == ""
    assert result.trend_tip == ""
    assert result.tyre_tips == []
    assert result.telemetry_tip == ""


def test_one_lap_no_crash():
    """Single lap: gap_tip should work (gap_ms == 0)."""
    result = compute_practice_tips([90_000.0], std_ms=0.0, last_packet=None,
                                   thresholds=None, last_lap_stats=None)
    assert "Within" in result.gap_tip
    assert result.trend_tip == ""  # not enough laps for trend


def test_last_packet_none_skips_tyre_tips():
    laps = [90_000.0, 90_200.0]
    result = compute_practice_tips(laps, std_ms=500.0, last_packet=None,
                                   thresholds=_Thresholds(), last_lap_stats=None)
    assert result.tyre_tips == []


def test_last_lap_stats_none_skips_telemetry():
    laps = [90_000.0, 90_200.0]
    result = compute_practice_tips(laps, std_ms=500.0, last_packet=None,
                                   thresholds=None, last_lap_stats=None)
    assert result.telemetry_tip == ""


def test_std_zero_no_division_error():
    """std_ms == 0 must not raise ZeroDivisionError."""
    laps = [90_000.0, 90_000.0]
    result = compute_practice_tips(laps, std_ms=0.0, last_packet=None,
                                   thresholds=None, last_lap_stats=None)
    assert "Excellent" in result.consistency_tip


def test_no_qt_dependency():
    """Importing practice_analysis must not pull in any Qt module."""
    import importlib
    import sys as _sys
    qt_modules_before = {k for k in _sys.modules if "PyQt" in k or "PySide" in k}
    import data.practice_analysis  # noqa: F401
    qt_modules_after = {k for k in _sys.modules if "PyQt" in k or "PySide" in k}
    new_qt = qt_modules_after - qt_modules_before
    assert not new_qt, f"practice_analysis imported Qt modules: {new_qt}"
