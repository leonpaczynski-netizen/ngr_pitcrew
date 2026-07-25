"""Unit tests for strategy.engine.RaceStrategyEngine (AC3).

Uses MagicMock for tracker, announcer, bridge, and db=None so no real
telemetry or audio subsystem is required.
"""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from strategy.engine import RaceStrategyEngine, Stint


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_stint(stint_num=1, laps=10, compound="RM",
                ref_lap_ms=0, pace_threshold_ms=2000):
    return Stint(
        stint_num=stint_num,
        laps=laps,
        compound=compound,
        ref_lap_ms=ref_lap_ms,
        pace_threshold_ms=pace_threshold_ms,
    )


def _make_engine(stints=None):
    tracker = MagicMock()
    tracker.laps_recorded = 1
    tracker.best_lap_ms = 90000
    tracker.avg_fuel_per_lap = 3.0
    tracker.last_fuel = 30.0
    tracker.tyre_states = {}

    announcer = MagicMock()
    config = {"fuel": {"strategy": "balanced"}, "strategy": {}}
    bridge = MagicMock()

    engine = RaceStrategyEngine(tracker, announcer, config, bridge, db=None)
    if stints:
        engine.set_plan(stints)
    return engine, tracker, announcer, bridge


# ---------------------------------------------------------------------------
# _assign_lap_ranges
# ---------------------------------------------------------------------------

class TestAssignLapRanges:
    def test_single_stint_starts_at_1(self):
        engine, *_ = _make_engine()
        s = _make_stint(stint_num=1, laps=15)
        engine.set_plan([s])
        assert s.start_lap == 1
        assert s.end_lap == 15

    def test_two_stints_consecutive(self):
        engine, *_ = _make_engine()
        s1 = _make_stint(stint_num=1, laps=10)
        s2 = _make_stint(stint_num=2, laps=8)
        engine.set_plan([s1, s2])
        assert s1.start_lap == 1
        assert s1.end_lap == 10
        assert s2.start_lap == s1.end_lap + 1
        assert s2.end_lap == 18


# ---------------------------------------------------------------------------
# _active_stint
# ---------------------------------------------------------------------------

class TestActiveStint:
    def test_returns_first_non_completed(self):
        engine, *_ = _make_engine()
        s1 = _make_stint(stint_num=1, laps=10)
        s2 = _make_stint(stint_num=2, laps=10)
        engine.set_plan([s1, s2])
        s1.completed = True
        with engine._lock:
            result = engine._active_stint()
        assert result is s2

    def test_returns_none_when_all_complete(self):
        engine, *_ = _make_engine()
        s1 = _make_stint(stint_num=1, laps=10)
        engine.set_plan([s1])
        s1.completed = True
        with engine._lock:
            result = engine._active_stint()
        assert result is None


# ---------------------------------------------------------------------------
# Pit window logic via _check_pit_window
# ---------------------------------------------------------------------------

class TestPitWindowWarning:
    def test_warn_announced_once_at_warn_lap(self):
        engine, tracker, announcer, _ = _make_engine()
        s = _make_stint(stint_num=1, laps=10)
        engine.set_plan([s])
        engine._active = True
        # warn_lap = end_lap - 2 = 8
        with engine._lock:
            engine._check_pit_window(s, laps_recorded=8)
        assert announcer.announce.called
        assert s.warn_issued is True
        call_count_after_first = announcer.announce.call_count

        # Call again at same lap — should NOT announce again
        with engine._lock:
            engine._check_pit_window(s, laps_recorded=8)
        assert announcer.announce.call_count == call_count_after_first

    def test_box_announced_once_at_end_lap(self):
        engine, tracker, announcer, _ = _make_engine()
        s = _make_stint(stint_num=1, laps=10)
        engine.set_plan([s])
        engine._active = True
        s.warn_issued = True  # skip warn

        with engine._lock:
            engine._check_pit_window(s, laps_recorded=10)
        assert s.box_announced is True
        count = announcer.announce.call_count

        # Call again — no extra announce
        with engine._lock:
            engine._check_pit_window(s, laps_recorded=10)
        assert announcer.announce.call_count == count

    def test_overdue_triggers_replan(self):
        engine, tracker, announcer, _ = _make_engine()
        s = _make_stint(stint_num=1, laps=10)
        engine.set_plan([s])
        engine._active = True
        s.warn_issued = True
        s.box_announced = True

        original_end = s.end_lap  # 10
        with engine._lock:
            engine._check_pit_window(s, laps_recorded=original_end + 3)

        # end_lap should have been extended
        assert s.end_lap > original_end


# ---------------------------------------------------------------------------
# build_pit_window_response
# ---------------------------------------------------------------------------

class TestBuildPitWindowResponse:
    def test_no_plan_contains_no_strategy(self):
        engine, *_ = _make_engine()
        resp = engine.build_pit_window_response(laps_recorded=5)
        assert "no strategy" in resp.lower()

    def test_active_plan_contains_box_lap(self):
        engine, tracker, *_ = _make_engine()
        s = _make_stint(stint_num=1, laps=10)
        engine.set_plan([s])
        engine._active = True
        tracker.laps_recorded = 5
        resp = engine.build_pit_window_response(laps_recorded=5)
        assert "10" in resp  # end_lap


# ---------------------------------------------------------------------------
# build_strategy_response
# ---------------------------------------------------------------------------

class TestBuildStrategyResponse:
    def test_all_done_contains_all_and_done(self):
        engine, *_ = _make_engine()
        s = _make_stint(stint_num=1, laps=10)
        engine.set_plan([s])
        engine._active = True
        s.completed = True
        resp = engine.build_strategy_response()
        lower = resp.lower()
        assert "all" in lower and ("done" in lower or "complete" in lower or "finished" in lower)


# ---------------------------------------------------------------------------
# build_fuel_check_response
# ---------------------------------------------------------------------------

class TestBuildFuelCheckResponse:
    def test_over_target_indicates_over_consuming(self):
        engine, tracker, *_ = _make_engine()
        s = _make_stint(stint_num=1, laps=10)
        engine.set_plan([s])
        engine._active = True
        # avg_fuel_per_lap * remaining_laps * multiplier > fuel_have
        # Set fuel_have very low so surplus < -avg → over-consuming message
        tracker.avg_fuel_per_lap = 3.0
        tracker.last_fuel = 5.0   # far less than needed
        resp = engine.build_fuel_check_response()
        lower = resp.lower()
        assert "short" in lower or "warning" in lower or "over" in lower


# ---------------------------------------------------------------------------
# build_pace_response
# ---------------------------------------------------------------------------

class TestBuildPaceResponse:
    def test_fewer_than_3_laps_not_enough(self):
        engine, *_ = _make_engine()
        s = _make_stint(stint_num=1, laps=10)
        engine.set_plan([s])
        engine._active = True
        engine._recent_lap_times = [90000, 90500]  # only 2
        resp = engine.build_pace_response()
        assert "not enough" in resp.lower()

    def test_states_delta_against_the_plan_target_lap(self):
        # With a loaded plan the driver's core need is the lap-time delta vs the plan.
        engine, tracker, *_ = _make_engine()
        s = _make_stint(stint_num=1, laps=10, ref_lap_ms=90000)
        engine.set_plan([s])
        engine._active = True
        tracker.best_lap_ms = 90000
        engine._recent_lap_times = [91000, 91000, 91000]  # 1.0s off the 90.0s target
        resp = engine.build_pace_response()
        lower = resp.lower()
        assert "plan" in lower and "target" in lower
        assert "second" in lower  # the delta is stated in seconds


# ---------------------------------------------------------------------------
# build_fuel_check_response — fuel-to-leave for the next stop
# ---------------------------------------------------------------------------

class TestFuelCheckLeaveWith:
    def test_names_the_fuel_to_leave_the_next_stop_with(self):
        engine, tracker, *_ = _make_engine()
        s = _make_stint(stint_num=1, laps=10)
        engine.set_plan([s])
        engine._active = True
        tracker.laps_recorded = 1
        tracker.avg_fuel_per_lap = 3.0
        tracker.last_fuel = 40.0
        resp = engine.build_fuel_check_response()
        assert "leave with" in resp.lower()
        assert "litre" in resp.lower()


# ---------------------------------------------------------------------------
# build_fuel_delta_response — per-lap over/under the plan's affordable rate
# ---------------------------------------------------------------------------

class TestBuildFuelDeltaResponse:
    def test_no_plan_says_so(self):
        engine, *_ = _make_engine()
        resp = engine.build_fuel_delta_response()
        assert "no strategy" in resp.lower()

    def test_burning_too_much_reports_heavy_delta_and_laps_short(self):
        engine, tracker, *_ = _make_engine()
        s = _make_stint(stint_num=1, laps=10)  # end_lap = 10
        engine.set_plan([s])
        engine._active = True
        tracker.laps_recorded = 0            # 10 laps remaining in plan
        tracker.avg_fuel_per_lap = 4.0       # burning 4.0
        tracker.last_fuel = 30.0             # affordable = 3.0 / lap
        resp = engine.build_fuel_delta_response()
        lower = resp.lower()
        assert "heavy" in lower               # burning more than affordable
        assert "a lap" in lower               # the delta is per-lap
        assert "short" in lower               # finishing short at this rate

    def test_saving_fuel_reports_margin_to_the_good(self):
        engine, tracker, *_ = _make_engine()
        s = _make_stint(stint_num=1, laps=10)
        engine.set_plan([s])
        engine._active = True
        tracker.laps_recorded = 0
        tracker.avg_fuel_per_lap = 2.5       # burning less than affordable
        tracker.last_fuel = 30.0             # affordable = 3.0 / lap
        resp = engine.build_fuel_delta_response()
        lower = resp.lower()
        assert "good" in lower or "in hand" in lower
        assert "a lap" in lower


# ---------------------------------------------------------------------------
# Proactive per-lap status cue
# ---------------------------------------------------------------------------

class TestProactiveCue:
    def test_speaks_a_concise_status_every_third_settled_lap(self):
        engine, tracker, announcer, _ = _make_engine()
        s = _make_stint(stint_num=1, laps=20, ref_lap_ms=90000)
        engine.set_plan([s])
        engine._active = True
        tracker.laps_recorded = 5            # far from the lap-20 stop
        tracker.best_lap_ms = 90000
        tracker.avg_fuel_per_lap = 3.0
        tracker.last_fuel = 45.0
        engine._recent_lap_times = [90200, 90200, 90200]
        rec = MagicMock()

        with engine._lock:
            engine._check_proactive_cue(rec, s, 5)  # counter 1 — silent
            engine._check_proactive_cue(rec, s, 5)  # counter 2 — silent
            first_calls = announcer.announce.call_count
            engine._check_proactive_cue(rec, s, 5)  # counter 3 — speaks
        assert announcer.announce.call_count == first_calls + 1
        spoken_keys = [c.args[2] for c in announcer.announce.call_args_list]
        assert "strategy_proactive_status" in spoken_keys

    def test_stays_silent_near_the_pit_window(self):
        engine, tracker, announcer, _ = _make_engine()
        s = _make_stint(stint_num=1, laps=20, ref_lap_ms=90000)
        engine.set_plan([s])
        engine._active = True
        engine._recent_lap_times = [90200, 90200, 90200]
        rec = MagicMock()
        with engine._lock:
            for _ in range(6):  # would otherwise fire twice
                engine._check_proactive_cue(rec, s, 19)  # 1 lap from the stop
        keys = [c.args[2] for c in announcer.announce.call_args_list]
        assert "strategy_proactive_status" not in keys


# ---------------------------------------------------------------------------
# _replan_after_overdue
# ---------------------------------------------------------------------------

class TestReplanAfterOverdue:
    def test_extends_current_stint_and_adjusts_subsequent(self):
        engine, tracker, *_ = _make_engine()
        s1 = _make_stint(stint_num=1, laps=10)
        s2 = _make_stint(stint_num=2, laps=10)
        engine.set_plan([s1, s2])
        engine._active = True
        s1.warn_issued = True
        s1.box_announced = True

        laps_recorded = 15  # 5 past s1.end_lap (10)
        with engine._lock:
            new_end = engine._replan_after_overdue(s1, laps_recorded)

        # new_end = laps_recorded + 2 = 17
        assert new_end == 17
        assert s1.end_lap == 17
        # s2 start should now be 18
        assert s2.start_lap == 18
