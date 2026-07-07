"""Group 53 — live current-state adapter tests.

Covers strategy/race_strategy_live_state.py: converts read-only live telemetry /
dashboard state into a Group 52 RaceReplanState — populating only real fields,
recording everything else as missing, never inventing, never raising.

All tests are pure/offline (duck-typed mocks; no Qt, no DB).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.race_strategy_live_state import (  # noqa: E402
    LiveReplanStateResult,
    build_replan_state_from_tracker,
    build_replan_state_from_live_packet,
    build_replan_state_from_dashboard_context,
    extract_live_replan_state,
    summarise_live_state_sources,
    SRC_LIVE, SRC_STRATEGY_TAG, SRC_MISSING,
)


class MockTracker:
    def __init__(self, laps_recorded=12, remaining_ms=1800000, laps_remaining=0,
                 compound="RM", avg_fuel=4.0, duration_min=50.0):
        self.laps_recorded = laps_recorded
        self._remaining_ms = remaining_ms
        self.laps_remaining = laps_remaining
        self._current_compound = compound
        self.avg_fuel_per_lap = avg_fuel
        self.timed_duration_minutes = duration_min

    def computed_remaining_ms(self):
        return self._remaining_ms


class MockPacket:
    def __init__(self, fuel_level=60.0, fuel_capacity=100.0):
        self.fuel_level = fuel_level
        self.fuel_capacity = fuel_capacity


class MockDashboard:
    def __init__(self, tracker=None, packet=None):
        self._tracker = tracker
        self._last_packet = packet


class TestTrackerExtraction:
    def test_extracts_current_lap(self):
        r = build_replan_state_from_tracker(MockTracker(laps_recorded=7), packet=MockPacket())
        assert r.state.current_lap == 7
        assert r.state_sources["current_lap"] == SRC_LIVE

    def test_extracts_elapsed_and_remaining_time(self):
        r = build_replan_state_from_tracker(MockTracker(remaining_ms=1800000), packet=MockPacket())
        assert r.state.remaining_time_seconds == pytest.approx(1800.0)
        # 50 min = 3000 s; elapsed = 3000 - 1800 = 1200
        assert r.state.elapsed_time_seconds == pytest.approx(1200.0)

    def test_extracts_fuel_from_packet(self):
        r = build_replan_state_from_tracker(MockTracker(), packet=MockPacket(60.0, 100.0))
        assert r.state.fuel_remaining_pct == pytest.approx(60.0)
        assert r.state_sources["fuel_remaining_pct"] == SRC_LIVE

    def test_compound_from_strategy_tag(self):
        r = build_replan_state_from_tracker(MockTracker(compound="RM"), packet=MockPacket())
        assert r.state.current_compound == "RM"
        assert r.state_sources["current_compound"] == SRC_STRATEGY_TAG

    def test_live_fuel_per_lap_surfaced(self):
        r = build_replan_state_from_tracker(MockTracker(avg_fuel=4.2), packet=MockPacket())
        assert r.live_fuel_per_lap == pytest.approx(4.2)


class TestMissingAndInvalid:
    def test_fuel_missing_without_packet(self):
        r = build_replan_state_from_tracker(MockTracker(), packet=None)
        assert r.state.fuel_remaining_pct is None
        assert "fuel_remaining_pct" in r.missing_state

    def test_tyre_age_and_pit_stops_always_missing(self):
        r = build_replan_state_from_tracker(MockTracker(), packet=MockPacket())
        assert r.state.tyre_age_laps is None
        assert r.state.pit_stops_completed is None
        assert "tyre_age_laps" in r.missing_state
        assert "pit_stops_completed" in r.missing_state

    def test_compound_missing_when_untagged(self):
        r = build_replan_state_from_tracker(MockTracker(compound=""), packet=MockPacket())
        assert r.state.current_compound is None
        assert r.state_sources["current_compound"] == SRC_MISSING

    def test_impossible_fuel_ignored(self):
        # fuel_level > capacity → impossible % → dropped, not clamped-and-pretended.
        r = build_replan_state_from_live_packet(MockPacket(fuel_level=150.0, fuel_capacity=100.0),
                                                current_lap=5)
        assert r.state.fuel_remaining_pct is None

    def test_zero_capacity_ignored(self):
        r = build_replan_state_from_live_packet(MockPacket(fuel_level=10.0, fuel_capacity=0.0),
                                                current_lap=5)
        assert r.state.fuel_remaining_pct is None

    def test_negative_lap_rejected(self):
        r = build_replan_state_from_live_packet(MockPacket(), current_lap=-3)
        assert r.state.current_lap is None


class TestPacketPath:
    def test_packet_laps_not_trusted(self):
        # A packet has no reliable lap count → current_lap only from explicit arg.
        r = build_replan_state_from_live_packet(MockPacket(50.0, 100.0))
        assert r.state.current_lap is None
        assert r.state.fuel_remaining_pct == pytest.approx(50.0)

    def test_explicit_lap_used(self):
        r = build_replan_state_from_live_packet(MockPacket(), current_lap=9, remaining_laps=20)
        assert r.state.current_lap == 9
        assert r.state.remaining_laps == 20


class TestDashboardPath:
    def test_reads_tracker_and_packet(self):
        d = MockDashboard(tracker=MockTracker(), packet=MockPacket(60.0, 100.0))
        r = build_replan_state_from_dashboard_context(d)
        assert r.state.current_lap == 12
        assert r.state.fuel_remaining_pct == pytest.approx(60.0)

    def test_no_tracker_is_all_missing(self):
        r = build_replan_state_from_dashboard_context(MockDashboard(tracker=None))
        assert r.state.current_lap is None
        assert any("not available" in w.lower() for w in r.warnings)


class TestDispatcherAndSafety:
    def test_dispatch_tracker(self):
        assert isinstance(extract_live_replan_state(MockTracker()), LiveReplanStateResult)

    def test_dispatch_dashboard(self):
        r = extract_live_replan_state(MockDashboard(tracker=MockTracker(), packet=MockPacket()))
        assert r.state.current_lap == 12

    def test_dispatch_none_is_empty(self):
        r = extract_live_replan_state(None)
        assert r.state.current_lap is None
        assert r.missing_state

    def test_never_raises_on_garbage(self):
        class Bad:
            @property
            def laps_recorded(self):
                raise RuntimeError("boom")
        r = extract_live_replan_state(Bad())
        assert isinstance(r, LiveReplanStateResult)

    def test_summarise_sources(self):
        r = build_replan_state_from_tracker(MockTracker(), packet=MockPacket())
        srcs = summarise_live_state_sources(r)
        assert srcs["current_lap"] == SRC_LIVE
        assert srcs["tyre_age_laps"] == SRC_MISSING


class TestNoSideEffects:
    def test_module_has_no_io_or_setup_or_ai(self):
        src = (ROOT / "strategy" / "race_strategy_live_state.py").read_text(encoding="utf-8")
        for banned in ("open(", "write_lap", "save_entry", "insert_", "call_api",
                       "setup_plan", "setup_rule_engine", "setup_history",
                       "PyQt", "requests"):
            assert banned not in src


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
