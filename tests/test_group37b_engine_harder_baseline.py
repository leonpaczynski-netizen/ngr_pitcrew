"""
Group 37b — Engine integration: harder-baseline tyre degradation alert

Tests for RaceStrategyEngine._check_tyre_degradation with and without a
populated degradation cache (set via set_degradation_cache).

All tests use the same MagicMock-based setup as the existing engine tests
in test_strategy_engine.py.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.engine import RaceStrategyEngine, Stint


# ---------------------------------------------------------------------------
# Helpers — mirrors test_strategy_engine.py patterns exactly
# ---------------------------------------------------------------------------

def _make_stint(stint_num=1, laps=15, compound="RS",
                ref_lap_ms=90000, pace_threshold_ms=2000):
    return Stint(
        stint_num=stint_num,
        laps=laps,
        compound=compound,
        ref_lap_ms=ref_lap_ms,
        pace_threshold_ms=pace_threshold_ms,
    )


def _make_engine(stints=None):
    tracker = MagicMock()
    tracker.laps_recorded = 5
    tracker.best_lap_ms = 90000
    tracker.avg_fuel_per_lap = 3.0
    tracker.last_fuel = 50.0
    tracker.tyre_states = {}

    announcer = MagicMock()
    config = {"fuel": {"strategy": "balanced"}, "strategy": {}}
    bridge = MagicMock()

    engine = RaceStrategyEngine(tracker, announcer, config, bridge, db=None)
    if stints:
        engine.set_plan(stints)
    return engine, tracker, announcer, bridge


def _make_record(lap_time_ms: int = 90000):
    record = MagicMock()
    record.lap_time_ms = lap_time_ms
    record.fuel_used = 3.0
    record.lock_up_count = 0
    record.wheelspin_count = 0
    record.oversteer_count = 0
    return record


# ---------------------------------------------------------------------------
# Test: set_degradation_cache stores and overwrites
# ---------------------------------------------------------------------------

class TestSetDegradationCache:
    def test_cache_initialised_empty_in_init(self):
        engine, *_ = _make_engine()
        with engine._lock:
            assert engine._degradation_cache == {}

    def test_cache_stored_correctly(self):
        engine, *_ = _make_engine()
        cache = {
            "RS": {
                "harder_baseline_ms": 97000.0,
                "degradation_method": "relative_baseline",
                "optimal_stint_race": 7,
                "confidence": "high",
                "not_yet_degraded": False,
            }
        }
        engine.set_degradation_cache(cache)
        with engine._lock:
            assert engine._degradation_cache["RS"]["harder_baseline_ms"] == 97000.0

    def test_cache_overwritten_on_second_call(self):
        engine, *_ = _make_engine()
        engine.set_degradation_cache({"RS": {"harder_baseline_ms": 97000.0}})
        engine.set_degradation_cache({"RM": {"harder_baseline_ms": 99000.0}})
        with engine._lock:
            assert "RS" not in engine._degradation_cache
            assert "RM" in engine._degradation_cache

    def test_none_cache_clears(self):
        engine, *_ = _make_engine()
        engine.set_degradation_cache({"RS": {"harder_baseline_ms": 97000.0}})
        engine.set_degradation_cache(None)
        with engine._lock:
            assert engine._degradation_cache == {}

    def test_empty_dict_cache_clears(self):
        engine, *_ = _make_engine()
        engine.set_degradation_cache({"RS": {"harder_baseline_ms": 97000.0}})
        engine.set_degradation_cache({})
        with engine._lock:
            assert engine._degradation_cache == {}


# ---------------------------------------------------------------------------
# Test: harder_baseline_ms path fires the alert at the right threshold
# ---------------------------------------------------------------------------

class TestHarderBaselineAlert:
    """When cache has harder_baseline_ms, the alert fires when rolling 3-lap
    average >= harder_baseline_ms (not ref + pace_threshold_ms).
    """

    def _setup_engine_with_cache(self, compound="RS", harder_baseline_ms=97000.0):
        stint = _make_stint(
            stint_num=1, laps=15, compound=compound,
            ref_lap_ms=90000,         # well below baseline
            pace_threshold_ms=2000,   # ref + threshold = 92000 — NOT 97000
        )
        engine, tracker, announcer, bridge = _make_engine(stints=[stint])
        engine.set_degradation_cache({
            compound: {"harder_baseline_ms": harder_baseline_ms}
        })
        # Activate the engine
        engine._active = True
        stint.start_lap = 1
        stint.end_lap = 15
        return engine, tracker, announcer, stint

    def test_alert_fires_when_rolling_avg_meets_baseline(self):
        """Rolling 3-lap average exactly at harder_baseline_ms triggers alert."""
        engine, tracker, announcer, stint = self._setup_engine_with_cache(
            compound="RS", harder_baseline_ms=97000.0
        )
        # Provide 3 laps all at exactly 97000ms (== baseline)
        engine._recent_lap_times = [97000, 97000, 97000]
        record = _make_record(97000)

        with engine._lock:
            engine._check_tyre_degradation(stint, record, laps_recorded=5)

        assert announcer.announce.called
        assert stint.tyre_alert_issued is True

    def test_alert_fires_when_rolling_avg_above_baseline(self):
        """Rolling average above harder_baseline_ms also triggers alert."""
        engine, tracker, announcer, stint = self._setup_engine_with_cache(
            compound="RS", harder_baseline_ms=97000.0
        )
        engine._recent_lap_times = [97500, 98000, 97200]
        record = _make_record(97200)

        with engine._lock:
            engine._check_tyre_degradation(stint, record, laps_recorded=5)

        assert announcer.announce.called
        assert stint.tyre_alert_issued is True

    def test_no_alert_when_rolling_avg_below_baseline(self):
        """Rolling average below harder_baseline_ms must NOT trigger alert."""
        engine, tracker, announcer, stint = self._setup_engine_with_cache(
            compound="RS", harder_baseline_ms=97000.0
        )
        # Rolling avg = 91000ms — well below 97000ms baseline
        engine._recent_lap_times = [90500, 91000, 91500]
        record = _make_record(91500)

        with engine._lock:
            engine._check_tyre_degradation(stint, record, laps_recorded=5)

        assert not announcer.announce.called
        assert stint.tyre_alert_issued is False

    def test_alert_issued_only_once(self):
        """Once the alert fires, tyre_alert_issued=True guards against repeats."""
        engine, tracker, announcer, stint = self._setup_engine_with_cache(
            compound="RS", harder_baseline_ms=97000.0
        )
        engine._recent_lap_times = [97000, 97000, 97000]
        record = _make_record(97000)

        with engine._lock:
            engine._check_tyre_degradation(stint, record, laps_recorded=5)

        count_after_first = announcer.announce.call_count

        # Call again — guard must prevent second announcement
        with engine._lock:
            engine._check_tyre_degradation(stint, record, laps_recorded=6)

        assert announcer.announce.call_count == count_after_first

    def test_alert_requires_3_laps(self):
        """Alert must NOT fire when fewer than 3 recent laps available."""
        engine, tracker, announcer, stint = self._setup_engine_with_cache(
            compound="RS", harder_baseline_ms=97000.0
        )
        engine._recent_lap_times = [97000, 97000]  # only 2
        record = _make_record(97000)

        with engine._lock:
            engine._check_tyre_degradation(stint, record, laps_recorded=5)

        assert not announcer.announce.called
        assert stint.tyre_alert_issued is False


# ---------------------------------------------------------------------------
# Test: fallback to ref + pace_threshold_ms when harder_baseline_ms is None
# ---------------------------------------------------------------------------

class TestFallbackToRefPlusThreshold:
    """When harder_baseline_ms is None (or cache has no entry), the original
    ref + pace_threshold_ms logic must fire — backward compat preserved.
    """

    def _setup_engine_no_cache(self, compound="RM"):
        stint = _make_stint(
            stint_num=1, laps=15, compound=compound,
            ref_lap_ms=90000,
            pace_threshold_ms=2000,
        )
        engine, tracker, announcer, bridge = _make_engine(stints=[stint])
        # No cache set — falls back to fallback logic
        engine._active = True
        stint.start_lap = 1
        stint.end_lap = 15
        return engine, tracker, announcer, stint

    def test_alert_fires_when_rolling_avg_above_ref_plus_threshold(self):
        """ref=90000, threshold=2000 → alert fires when rolling avg > 92000."""
        engine, tracker, announcer, stint = self._setup_engine_no_cache(compound="RM")
        # Rolling avg = 93000ms > ref + threshold (92000)
        engine._recent_lap_times = [93000, 93000, 93000]
        record = _make_record(93000)

        with engine._lock:
            engine._check_tyre_degradation(stint, record, laps_recorded=5)

        assert announcer.announce.called
        assert stint.tyre_alert_issued is True

    def test_no_alert_when_rolling_avg_equals_ref_plus_threshold(self):
        """ref=90000, threshold=2000 → rolling avg exactly at 92000 does NOT alert
        (condition is strictly >, not >=).
        """
        engine, tracker, announcer, stint = self._setup_engine_no_cache(compound="RM")
        engine._recent_lap_times = [92000, 92000, 92000]
        record = _make_record(92000)

        with engine._lock:
            engine._check_tyre_degradation(stint, record, laps_recorded=5)

        assert not announcer.announce.called
        assert stint.tyre_alert_issued is False

    def test_no_alert_when_rolling_avg_below_threshold(self):
        """Rolling avg below ref + threshold → no alert."""
        engine, tracker, announcer, stint = self._setup_engine_no_cache(compound="RM")
        engine._recent_lap_times = [90500, 91000, 91500]
        record = _make_record(91500)

        with engine._lock:
            engine._check_tyre_degradation(stint, record, laps_recorded=5)

        assert not announcer.announce.called
        assert stint.tyre_alert_issued is False

    def test_fallback_when_cache_has_none_baseline(self):
        """Explicit harder_baseline_ms=None in cache → use fallback path."""
        stint = _make_stint(
            stint_num=1, laps=15, compound="RM",
            ref_lap_ms=90000,
            pace_threshold_ms=2000,
        )
        engine, tracker, announcer, bridge = _make_engine(stints=[stint])
        engine.set_degradation_cache({
            "RM": {"harder_baseline_ms": None, "degradation_method": "cliff_detection"}
        })
        engine._active = True
        stint.start_lap = 1
        stint.end_lap = 15

        # Rolling avg = 93000 > ref + threshold (92000) → alert via fallback
        engine._recent_lap_times = [93000, 93000, 93000]
        record = _make_record(93000)

        with engine._lock:
            engine._check_tyre_degradation(stint, record, laps_recorded=5)

        assert announcer.announce.called
        assert stint.tyre_alert_issued is True

    def test_fallback_when_compound_not_in_cache(self):
        """Compound absent from cache → use fallback ref + threshold path."""
        stint = _make_stint(
            stint_num=1, laps=15, compound="RH",
            ref_lap_ms=97000,
            pace_threshold_ms=3000,
        )
        engine, tracker, announcer, bridge = _make_engine(stints=[stint])
        # Cache has RS but not RH
        engine.set_degradation_cache({"RS": {"harder_baseline_ms": 97000.0}})
        engine._active = True
        stint.start_lap = 1
        stint.end_lap = 15

        # Rolling avg = 101000 > ref(97000) + threshold(3000) = 100000 → alert
        engine._recent_lap_times = [101000, 101000, 101000]
        record = _make_record(101000)

        with engine._lock:
            engine._check_tyre_degradation(stint, record, laps_recorded=5)

        assert announcer.announce.called
        assert stint.tyre_alert_issued is True


# ---------------------------------------------------------------------------
# Test: announcement text for harder-baseline path
# ---------------------------------------------------------------------------

class TestHarderBaselineAlertText:
    """The announcement text for the harder-baseline path must mention
    the harder-compound baseline pace.
    """

    def test_announcement_mentions_baseline_pace(self):
        stint = _make_stint(
            stint_num=1, laps=15, compound="RS",
            ref_lap_ms=90000, pace_threshold_ms=2000,
        )
        engine, tracker, announcer, bridge = _make_engine(stints=[stint])
        harder_baseline_ms = 97000.0
        engine.set_degradation_cache({
            "RS": {"harder_baseline_ms": harder_baseline_ms}
        })
        engine._active = True
        stint.start_lap = 1
        stint.end_lap = 15

        engine._recent_lap_times = [97000, 97100, 97200]
        record = _make_record(97200)

        with engine._lock:
            engine._check_tyre_degradation(stint, record, laps_recorded=5)

        assert announcer.announce.called
        # The tyre-deg alert is the FIRST announce call; _request_replan may add a second.
        # Use call_args_list[0] to capture the tyre alert message specifically.
        first_call_args = announcer.announce.call_args_list[0]
        msg = first_call_args[0][0]  # first positional arg of the first call
        # Message should reference the baseline or harder-compound context
        assert "baseline" in msg.lower() or "97.000" in msg or "harder" in msg.lower()
