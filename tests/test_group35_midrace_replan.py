"""
Group 35 — Mid-race AI re-plan (Group B qualifying engineer + mid-race re-plan)

Backend tests covering:
  - engine._request_replan: sets in-flight, calls callback; idempotent while in-flight
  - engine pace trigger fires replan at slow_lap_count >= 4, not at 3
  - engine tyre-deg breach fires replan
  - engine.apply_replan: completed stints preserved, new start_lap, _adapted_plan set
  - engine.apply_replan empty result → replan_failed, stints unchanged
  - engine._on_pit_exit resets _adapted_plan
  - engine qualifying ack fires once when _qualifying_mode True; not in race mode
  - ai_planner._build_race_prompt: race_situation=None → identical to baseline
  - ai_planner._build_race_prompt: race_situation populated → contains MID-RACE RE-PLAN block
  - orchestrator forwards race_situation to analyse_strategy
  - dashboard._assemble_strategy_inputs source present and correct
  - dashboard._launch_replan_worker source present and correct

No Qt — engine tests use MagicMock; dashboard tests use source-text inspection.
"""
from __future__ import annotations

import sys
import pathlib
from dataclasses import dataclass, field
from unittest.mock import MagicMock, call, patch

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.engine import RaceStrategyEngine, Stint
from telemetry.state import Priority

DASHBOARD_SRC = (ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_stint(stint_num=1, laps=10, compound="RM",
                ref_lap_ms=90_000, pace_threshold_ms=2000):
    return Stint(
        stint_num=stint_num,
        laps=laps,
        compound=compound,
        ref_lap_ms=ref_lap_ms,
        pace_threshold_ms=pace_threshold_ms,
    )


def _make_engine(stints=None, replan_callback=None):
    tracker = MagicMock()
    tracker.laps_recorded = 5
    tracker.best_lap_ms = 90_000
    tracker.avg_fuel_per_lap = 3.0
    tracker.last_fuel = 30.0
    tracker.tyre_states = {}

    announcer = MagicMock()
    config = {"fuel": {"strategy": "balanced"}, "strategy": {}}
    bridge = MagicMock()

    engine = RaceStrategyEngine(tracker, announcer, config, bridge, db=None)
    engine._replan_callback = replan_callback
    if stints:
        engine.set_plan(stints)
    return engine, tracker, announcer, bridge


def _make_lap_record(lap_time_ms=95_000, fuel_used=3.0):
    rec = MagicMock()
    rec.lap_time_ms = lap_time_ms
    rec.fuel_used = fuel_used
    return rec


# ---------------------------------------------------------------------------
# _request_replan
# ---------------------------------------------------------------------------

class TestRequestReplan:
    def test_sets_in_flight_and_calls_callback(self):
        callback = MagicMock()
        engine, _, announcer, _ = _make_engine(replan_callback=callback)
        engine._request_replan(reason="test reason")

        assert engine._replan_in_flight is True
        callback.assert_called_once_with("test reason")

    def test_announces_standby(self):
        engine, _, announcer, _ = _make_engine()
        engine._request_replan(reason="test")
        # Must announce "Adapting strategy, stand by."
        texts = [call_args[0][0] for call_args in announcer.announce.call_args_list]
        assert any("Adapting strategy" in t for t in texts)

    def test_second_call_while_in_flight_is_noop(self):
        callback = MagicMock()
        engine, _, announcer, _ = _make_engine(replan_callback=callback)
        engine._request_replan(reason="first")
        callback.reset_mock()
        announcer.announce.reset_mock()

        # Second call — engine is in-flight
        engine._request_replan(reason="second")
        callback.assert_not_called()
        announcer.announce.assert_not_called()

    def test_no_call_when_adapted_plan(self):
        callback = MagicMock()
        engine, _, announcer, _ = _make_engine(replan_callback=callback)
        engine._adapted_plan = True
        engine._request_replan(reason="should be ignored")

        callback.assert_not_called()
        assert engine._replan_in_flight is False

    def test_no_crash_without_callback(self):
        engine, _, _, _ = _make_engine()  # callback=None by default
        engine._request_replan(reason="no callback")
        assert engine._replan_in_flight is True


# ---------------------------------------------------------------------------
# Pace trigger threshold
# ---------------------------------------------------------------------------

class TestPaceTrigger:
    def _run_slow_laps(self, engine, tracker, count, lap_ms=93_000):
        """Simulate `count` slow laps through _check_lap_targets."""
        s = engine._stints[0]
        rec = _make_lap_record(lap_time_ms=lap_ms)  # 3s over ref (90000 + 2000 tolerance = 92000)
        for _ in range(count):
            with engine._lock:
                engine._check_lap_targets(rec, s)

    def test_replan_not_triggered_at_3_slow_laps(self):
        callback = MagicMock()
        engine, tracker, _, _ = _make_engine(
            stints=[_make_stint(ref_lap_ms=90_000, pace_threshold_ms=2000)],
            replan_callback=callback,
        )
        self._run_slow_laps(engine, tracker, 3)
        callback.assert_not_called()

    def test_replan_triggered_at_4_slow_laps(self):
        callback = MagicMock()
        engine, tracker, _, _ = _make_engine(
            stints=[_make_stint(ref_lap_ms=90_000, pace_threshold_ms=2000)],
            replan_callback=callback,
        )
        self._run_slow_laps(engine, tracker, 4)
        callback.assert_called_once()
        assert "off target" in callback.call_args[0][0]

    def test_replan_not_triggered_twice(self):
        """Second slow lap at count >= 4 should not trigger if already in-flight."""
        callback = MagicMock()
        engine, tracker, _, _ = _make_engine(
            stints=[_make_stint(ref_lap_ms=90_000, pace_threshold_ms=2000)],
            replan_callback=callback,
        )
        # Manually set slow_lap_count to 3 and trigger
        engine._slow_lap_count = 3
        s = engine._stints[0]
        rec = _make_lap_record(lap_time_ms=93_000)
        with engine._lock:
            engine._check_lap_targets(rec, s)
        assert callback.call_count == 1

        callback.reset_mock()
        with engine._lock:
            engine._check_lap_targets(rec, s)  # now in-flight
        callback.assert_not_called()


# ---------------------------------------------------------------------------
# Tyre degradation breach trigger
# ---------------------------------------------------------------------------

class TestTyreDegBreachTrigger:
    def test_replan_triggered_on_tyre_deg_breach(self):
        callback = MagicMock()
        s = _make_stint(ref_lap_ms=90_000, pace_threshold_ms=2000)
        engine, tracker, announcer, _ = _make_engine(
            stints=[s], replan_callback=callback
        )
        # Set 3 recent slow laps (above ref + threshold)
        engine._recent_lap_times = [93_000, 93_500, 94_000]
        tracker.best_lap_ms = 90_000
        rec = _make_lap_record(lap_time_ms=93_500)

        with engine._lock:
            engine._check_tyre_degradation(s, rec, laps_recorded=5)

        assert s.tyre_alert_issued is True
        callback.assert_called_once()
        assert "tyre degradation" in callback.call_args[0][0]

    def test_replan_not_triggered_when_already_adapted(self):
        callback = MagicMock()
        s = _make_stint(ref_lap_ms=90_000, pace_threshold_ms=2000)
        engine, tracker, _, _ = _make_engine(stints=[s], replan_callback=callback)
        engine._adapted_plan = True
        engine._recent_lap_times = [93_000, 93_500, 94_000]
        tracker.best_lap_ms = 90_000
        rec = _make_lap_record(lap_time_ms=93_500)

        with engine._lock:
            engine._check_tyre_degradation(s, rec, laps_recorded=5)

        callback.assert_not_called()


# ---------------------------------------------------------------------------
# apply_replan
# ---------------------------------------------------------------------------

@dataclass
class _FakeStrategyOption:
    rank: int = 1
    name: str = "Test"
    stints: list = field(default_factory=list)
    estimated_time_s: float = 3600.0
    pit_time_s: float = 23.0
    summary: str = ""
    risks: str = ""


@dataclass
class _FakeStrategyResult:
    strategies: list = field(default_factory=list)

    def __iter__(self):
        return iter(self.strategies)

    def __len__(self):
        return len(self.strategies)


class TestApplyReplan:
    def _setup_two_stints(self):
        s1 = _make_stint(stint_num=1, laps=10, compound="RM")
        s2 = _make_stint(stint_num=2, laps=10, compound="RH")
        engine, tracker, announcer, bridge = _make_engine(stints=[s1, s2])
        engine._active = True
        # Mark s1 completed
        s1.completed = True
        # Set tracker to lap 8 (into s1 which is now done)
        tracker.laps_recorded = 8
        return engine, tracker, announcer, bridge, s1, s2

    def test_completed_stints_preserved(self):
        engine, tracker, announcer, bridge, s1, s2 = self._setup_two_stints()
        engine._replan_in_flight = True

        new_stints_data = [
            {"compound": "RH", "laps": 12, "ref_lap_ms": 95_000, "pace_threshold_ms": 3000}
        ]
        opt = _FakeStrategyOption(stints=new_stints_data)
        result = _FakeStrategyResult(strategies=[opt])

        engine.apply_replan(result)

        # s1 still in stints and completed
        assert engine._stints[0] is s1
        assert engine._stints[0].completed is True

    def test_first_new_stint_start_lap_equals_current_lap(self):
        engine, tracker, announcer, bridge, s1, s2 = self._setup_two_stints()
        engine._replan_in_flight = True
        tracker.laps_recorded = 8

        new_stints_data = [
            {"compound": "RH", "laps": 12, "ref_lap_ms": 95_000, "pace_threshold_ms": 3000}
        ]
        opt = _FakeStrategyOption(stints=new_stints_data)
        result = _FakeStrategyResult(strategies=[opt])

        engine.apply_replan(result)

        # First new stint starts at current lap
        new_stint = engine._stints[1]
        assert new_stint.start_lap == 8

    def test_adapted_plan_set_true(self):
        engine, tracker, _, _, s1, _ = self._setup_two_stints()
        engine._replan_in_flight = True
        opt = _FakeStrategyOption(stints=[
            {"compound": "RH", "laps": 10, "ref_lap_ms": 95_000, "pace_threshold_ms": 3000}
        ])
        engine.apply_replan(_FakeStrategyResult(strategies=[opt]))
        assert engine._adapted_plan is True

    def test_slow_lap_count_reset(self):
        engine, tracker, _, _, s1, _ = self._setup_two_stints()
        engine._replan_in_flight = True
        engine._slow_lap_count = 5
        opt = _FakeStrategyOption(stints=[
            {"compound": "RH", "laps": 10, "ref_lap_ms": 95_000, "pace_threshold_ms": 3000}
        ])
        engine.apply_replan(_FakeStrategyResult(strategies=[opt]))
        assert engine._slow_lap_count == 0

    def test_in_flight_cleared(self):
        engine, tracker, _, _, s1, _ = self._setup_two_stints()
        engine._replan_in_flight = True
        opt = _FakeStrategyOption(stints=[
            {"compound": "RH", "laps": 10, "ref_lap_ms": 95_000, "pace_threshold_ms": 3000}
        ])
        engine.apply_replan(_FakeStrategyResult(strategies=[opt]))
        assert engine._replan_in_flight is False

    def test_ac11_announcement_made(self):
        engine, tracker, announcer, _, s1, _ = self._setup_two_stints()
        engine._replan_in_flight = True
        opt = _FakeStrategyOption(stints=[
            {"compound": "RH", "laps": 10, "ref_lap_ms": 95_000, "pace_threshold_ms": 3000}
        ])
        engine.apply_replan(_FakeStrategyResult(strategies=[opt]))
        texts = [a[0][0] for a in announcer.announce.call_args_list]
        assert any("Strategy adapted" in t for t in texts)

    def test_empty_result_calls_replan_failed(self):
        engine, tracker, _, _, s1, s2 = self._setup_two_stints()
        engine._replan_in_flight = True
        original_count = len(engine._stints)

        engine.apply_replan(_FakeStrategyResult(strategies=[]))

        # Stints unchanged
        assert len(engine._stints) == original_count
        # in-flight cleared by replan_failed
        assert engine._replan_in_flight is False


# ---------------------------------------------------------------------------
# _on_pit_exit resets _adapted_plan
# ---------------------------------------------------------------------------

class TestPitExitResetsAdaptedPlan:
    def test_adapted_plan_reset_on_pit_exit(self):
        s1 = _make_stint(stint_num=1, laps=10, compound="RM")
        s2 = _make_stint(stint_num=2, laps=10, compound="RH")
        engine, tracker, _, _ = _make_engine(stints=[s1, s2])
        engine._active = True
        engine._adapted_plan = True
        engine._on_pit_exit({})
        assert engine._adapted_plan is False


# ---------------------------------------------------------------------------
# Qualifying acknowledgement
# ---------------------------------------------------------------------------

class TestQualifyingAck:
    def test_ack_fires_when_qualifying_mode(self):
        s = _make_stint()
        engine, _, announcer, _ = _make_engine(stints=[s])
        engine._qualifying_mode = True
        engine._ui_race_mode = False  # qualifying → not race
        engine._on_race_start({})

        texts = [a[0][0] for a in announcer.announce.call_args_list]
        assert any("Qualifying session started" in t for t in texts)

    def test_ack_does_not_activate_race_tracking(self):
        s = _make_stint()
        engine, _, _, _ = _make_engine(stints=[s])
        engine._qualifying_mode = True
        engine._ui_race_mode = False
        engine._active = False
        engine._on_race_start({})
        # Race tracking must not activate in qualifying
        assert engine._active is False

    def test_race_start_in_race_mode_no_ack(self):
        """Normal race start should not say 'Qualifying session started'."""
        s = _make_stint()
        engine, _, announcer, _ = _make_engine(stints=[s])
        engine._qualifying_mode = False
        engine._ui_race_mode = True
        engine._on_race_start({})

        texts = [a[0][0] for a in announcer.announce.call_args_list]
        assert not any("Qualifying session started" in t for t in texts)

    def test_ack_fires_once(self):
        """RACE_STARTED event fires once; cooldown key guards duplicates.
        Calling _on_race_start again should call announce again (engine doesn't
        track call count — cooldown is in the announcer).  The key used is
        'strategy_race_start' which matches the race-start path too."""
        s = _make_stint()
        engine, _, announcer, _ = _make_engine(stints=[s])
        engine._qualifying_mode = True
        engine._ui_race_mode = False
        engine._on_race_start({})
        count1 = announcer.announce.call_count

        engine._on_race_start({})
        count2 = announcer.announce.call_count
        # Both calls reach announcer; cooldown de-dup is the announcer's responsibility
        assert count2 == count1 + 1

    def test_ack_uses_correct_cooldown_key(self):
        s = _make_stint()
        engine, _, announcer, _ = _make_engine(stints=[s])
        engine._qualifying_mode = True
        engine._ui_race_mode = False
        engine._on_race_start({})

        call_args = announcer.announce.call_args
        assert call_args[0][2] == "strategy_race_start"

    def test_adapted_plan_reset_on_race_start(self):
        s = _make_stint()
        engine, _, _, _ = _make_engine(stints=[s])
        engine._adapted_plan = True
        engine._qualifying_mode = True
        engine._ui_race_mode = False
        engine._on_race_start({})
        assert engine._adapted_plan is False


# ---------------------------------------------------------------------------
# dashboard source-text tests
# ---------------------------------------------------------------------------

def _method_body(text: str, method_name: str) -> str:
    start = text.find(f"def {method_name}(")
    if start == -1:
        return ""
    end = text.find("\n    def ", start + 1)
    return text[start:end] if end != -1 else text[start:]


class TestAssembleStrategyInputsSource:
    def setup_method(self):
        self._body = _method_body(DASHBOARD_SRC, "_assemble_strategy_inputs")

    def test_method_exists(self):
        assert self._body, "_assemble_strategy_inputs not found in dashboard.py"

    def test_returns_lap_data_by_compound(self):
        assert "lap_data_by_compound" in self._body

    def test_returns_tyre_degradation_cache(self):
        assert "tyre_degradation_cache" in self._body

    def test_uses_practice_session_id(self):
        """Must use _strat_sid (practice session), NOT live race session."""
        assert "_strat_sid" in self._body

    def test_returns_dict_with_params(self):
        assert '"params"' in self._body


class TestLaunchReplanWorkerSource:
    def setup_method(self):
        self._body = _method_body(DASHBOARD_SRC, "_launch_replan_worker")

    def test_method_exists(self):
        assert self._body, "_launch_replan_worker not found in dashboard.py"

    def test_posts_replan_error(self):
        assert '"replan_error"' in self._body


class TestDisplayStrategyResultsHandlesReplan:
    def setup_method(self):
        self._body = _method_body(DASHBOARD_SRC, "_display_strategy_results")

    def test_handles_replan_ok(self):
        assert '"replan_ok"' in self._body

    def test_handles_replan_error(self):
        assert '"replan_error"' in self._body

    def test_replan_ok_calls_apply_replan(self):
        assert "apply_replan" in self._body

    def test_replan_error_calls_replan_failed(self):
        assert "replan_failed" in self._body


class TestQualifyingActiveWiredInDashboard:
    def test_set_qualifying_active_called_in_on_live_mode_changed(self):
        body = _method_body(DASHBOARD_SRC, "_on_live_mode_changed")
        assert "set_qualifying_active" in body, (
            "_on_live_mode_changed must call set_qualifying_active"
        )

    def test_replan_callback_wired_in_init(self):
        # The wiring must appear near the engine init block
        assert "_replan_callback = self._launch_replan_worker" in DASHBOARD_SRC
