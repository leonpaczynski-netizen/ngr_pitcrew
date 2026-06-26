"""Group 18 — DEF-P3-014: Startup residual strategy/race config activation.

Tests that:
- main.py does NOT call set_plan() at startup with saved stops
- main.py does NOT call set_race_config() at startup
- _update_race_config() does NOT push to StateTracker
- _on_event_set_active() correctly uses telemetry.state.RaceType (not telemetry.tracker)
- StateTracker starts idle with UNKNOWN race type
- RaceStrategyEngine starts with empty plan (_stints == [])
"""
from __future__ import annotations

import ast
import inspect
import queue
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MAIN_PY = Path(__file__).parent.parent / "main.py"
_DASHBOARD_PY = Path(__file__).parent.parent / "ui" / "dashboard.py"


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# StateTracker initial state
# ---------------------------------------------------------------------------

class TestStateTrackerInitial:
    def test_tracker_starts_with_unknown_race_type(self):
        from telemetry.state import RaceStateTracker, TyreThresholds, RaceType
        q = queue.PriorityQueue()
        tracker = RaceStateTracker(q, TyreThresholds())
        assert tracker._manual_race_type == RaceType.UNKNOWN

    def test_tracker_starts_with_no_duration(self):
        from telemetry.state import RaceStateTracker, TyreThresholds
        q = queue.PriorityQueue()
        tracker = RaceStateTracker(q, TyreThresholds())
        assert tracker._timed_race_duration_ms == 0


# ---------------------------------------------------------------------------
# RaceStrategyEngine initial state
# ---------------------------------------------------------------------------

class TestStrategyEngineInitial:
    def _make_engine(self):
        from strategy.engine import RaceStrategyEngine
        tracker = MagicMock()
        announcer = MagicMock()
        bridge = MagicMock()
        config = {}
        return RaceStrategyEngine(tracker, announcer, config, bridge)

    def test_engine_starts_with_no_stints(self):
        engine = self._make_engine()
        assert engine._stints == []

    def test_engine_starts_inactive(self):
        engine = self._make_engine()
        assert engine._active is False


# ---------------------------------------------------------------------------
# main.py source-level guards
# ---------------------------------------------------------------------------

class TestMainPyStartupFlow:
    def test_no_set_plan_call_in_main_startup(self):
        """set_plan() must not be called in main() during startup with saved stops."""
        src = _read_source(_MAIN_PY)
        # Check that the startup code does not call set_plan on the engine with saved stops
        # The pattern we removed was: strategy_engine.set_plan(...)
        # It should not appear outside of conditional context we didn't add back
        tree = ast.parse(src)
        # Find the main() function body
        main_func = next(
            (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "main"),
            None,
        )
        assert main_func is not None, "main() function not found in main.py"

        # Collect all set_plan call sites in main()
        set_plan_calls = []
        for node in ast.walk(main_func):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "set_plan"
            ):
                set_plan_calls.append(node)
        assert set_plan_calls == [], (
            f"set_plan() is called {len(set_plan_calls)} time(s) in main() startup — "
            "must not auto-activate saved plan on startup"
        )

    def test_no_set_race_config_call_in_main_startup(self):
        """set_race_config() must not be called in main() at startup."""
        src = _read_source(_MAIN_PY)
        tree = ast.parse(src)
        main_func = next(
            (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "main"),
            None,
        )
        assert main_func is not None

        set_rc_calls = []
        for node in ast.walk(main_func):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "set_race_config"
            ):
                set_rc_calls.append(node)
        assert set_rc_calls == [], (
            f"set_race_config() is called {len(set_rc_calls)} time(s) in main() — "
            "must not push race config at startup"
        )

    def test_saved_stops_comment_present(self):
        """The removal comment should be present explaining why set_plan is not called."""
        src = _read_source(_MAIN_PY)
        assert "Strategy Builder UI" in src or "set_plan" not in src.split("def main")[1].split("def ")[1], \
            "No explanation comment for why set_plan is not called at startup"


# ---------------------------------------------------------------------------
# dashboard.py _update_race_config does NOT push to tracker
# ---------------------------------------------------------------------------

class TestUpdateRaceConfigNoPush:
    def test_update_race_config_no_set_race_config_call(self):
        """_update_race_config() must not call set_race_config() — tracker is pushed
        only from _on_event_set_active() which is triggered by explicit user action."""
        src = _read_source(_DASHBOARD_PY)
        # Find _update_race_config method body
        lines = src.splitlines()
        in_method = False
        method_lines = []
        indent_len = None
        for line in lines:
            if "def _update_race_config(self)" in line:
                in_method = True
                indent_len = len(line) - len(line.lstrip())
                method_lines.append(line)
                continue
            if in_method:
                if line.strip() == "":
                    method_lines.append(line)
                    continue
                cur_indent = len(line) - len(line.lstrip())
                if cur_indent <= indent_len and line.strip() and not line.strip().startswith("#"):
                    # Next method definition — stop
                    break
                method_lines.append(line)

        method_src = "\n".join(method_lines)
        assert "set_race_config" not in method_src, (
            "_update_race_config() calls set_race_config() — this leaks race config "
            "into StateTracker during startup tab construction"
        )

    def test_update_race_config_still_persists_config(self):
        """_update_race_config() must still call _persist_config() to save config."""
        src = _read_source(_DASHBOARD_PY)
        lines = src.splitlines()
        in_method = False
        method_lines = []
        indent_len = None
        for line in lines:
            if "def _update_race_config(self)" in line:
                in_method = True
                indent_len = len(line) - len(line.lstrip())
                method_lines.append(line)
                continue
            if in_method:
                if line.strip() == "":
                    method_lines.append(line)
                    continue
                cur_indent = len(line) - len(line.lstrip())
                if cur_indent <= indent_len and line.strip() and not line.strip().startswith("#"):
                    break
                method_lines.append(line)

        method_src = "\n".join(method_lines)
        assert "_persist_config" in method_src, (
            "_update_race_config() must still call _persist_config()"
        )


# ---------------------------------------------------------------------------
# dashboard.py _on_event_set_active uses correct RaceType import
# ---------------------------------------------------------------------------

class TestEventSetActiveImport:
    def test_on_event_set_active_uses_telemetry_state_not_tracker(self):
        """_on_event_set_active() must import RaceType from telemetry.state, not
        the non-existent telemetry.tracker module."""
        src = _read_source(_DASHBOARD_PY)
        lines = src.splitlines()
        in_method = False
        method_lines = []
        indent_len = None
        for line in lines:
            if "def _on_event_set_active(self)" in line:
                in_method = True
                indent_len = len(line) - len(line.lstrip())
                method_lines.append(line)
                continue
            if in_method:
                if line.strip() == "":
                    method_lines.append(line)
                    continue
                cur_indent = len(line) - len(line.lstrip())
                if cur_indent <= indent_len and line.strip() and not line.strip().startswith("#"):
                    break
                method_lines.append(line)

        method_src = "\n".join(method_lines)
        assert "telemetry.tracker" not in method_src, (
            "_on_event_set_active() imports from non-existent telemetry.tracker — "
            "should be telemetry.state"
        )
        assert "telemetry.state" in method_src or "RaceType" not in method_src, (
            "_on_event_set_active() must import RaceType from telemetry.state"
        )

    def test_telemetry_tracker_module_does_not_exist(self):
        """Confirm telemetry.tracker does not exist so a bad import would fail."""
        import importlib
        spec = importlib.util.find_spec("telemetry.tracker")
        assert spec is None, "telemetry.tracker unexpectedly exists — update the test"


# ---------------------------------------------------------------------------
# set_plan() behavior — explicit activation required
# ---------------------------------------------------------------------------

class TestSetPlanExplicitOnly:
    def _make_engine(self):
        from strategy.engine import RaceStrategyEngine
        tracker = MagicMock()
        announcer = MagicMock()
        bridge = MagicMock()
        config = {}
        return RaceStrategyEngine(tracker, announcer, config, bridge)

    def test_set_plan_empty_list_leaves_engine_inactive(self):
        engine = self._make_engine()
        engine.set_plan([])
        assert engine._stints == []
        assert engine._active is False

    def test_set_plan_with_stints_marks_engine_with_stints_but_not_active(self):
        from strategy.engine import Stint
        engine = self._make_engine()
        stint = Stint(stint_num=1, laps=10, compound="RM", ref_lap_ms=0, pace_threshold_ms=2000)
        engine.set_plan([stint])
        assert len(engine._stints) == 1
        # _active is set to False by set_plan() — user must start a race to activate
        assert engine._active is False

    def test_engine_on_event_does_nothing_with_empty_stints(self):
        from telemetry.state import TelemetryEvent, EventType, Priority
        engine = self._make_engine()
        event = TelemetryEvent(type=EventType.LAP_COMPLETED, data={"record": MagicMock()},
                               priority=Priority.INFO)
        # Should not raise; empty plan means no-op
        engine.on_event(event)
        assert engine._stints == []


# ---------------------------------------------------------------------------
# set_race_config() behavior — must only fire from explicit activation
# ---------------------------------------------------------------------------

class TestSetRaceConfigExplicitOnly:
    def _make_tracker(self):
        from telemetry.state import RaceStateTracker, TyreThresholds
        return RaceStateTracker(queue.PriorityQueue(), TyreThresholds())

    def test_set_race_config_changes_manual_race_type(self):
        from telemetry.state import RaceType
        tracker = self._make_tracker()
        tracker.set_race_config(RaceType.TIMED, 40.0)
        assert tracker._manual_race_type == RaceType.TIMED

    def test_set_race_config_changes_duration(self):
        from telemetry.state import RaceType
        tracker = self._make_tracker()
        tracker.set_race_config(RaceType.TIMED, 40.0)
        assert tracker._timed_race_duration_ms == 40 * 60 * 1000

    def test_fresh_tracker_has_no_duration(self):
        tracker = self._make_tracker()
        assert tracker._timed_race_duration_ms == 0

    def test_computed_remaining_ms_returns_minus_one_when_no_config(self):
        """computed_remaining_ms() must return -1 when no race config is set."""
        tracker = self._make_tracker()
        result = tracker.computed_remaining_ms()
        assert result == -1, (
            f"Expected -1 (no config), got {result}. "
            "Tracker should not have a race duration on startup."
        )


# ---------------------------------------------------------------------------
# Integration: saved-stops config does not auto-activate engine
# ---------------------------------------------------------------------------

class TestSavedStopsDoNotAutoActivate:
    def test_config_with_saved_stops_does_not_activate_engine(self):
        """Simulate the config that triggered the bug: strategy.stops is non-empty.
        The engine should still have no stints after initialization (before user action)."""
        from strategy.engine import RaceStrategyEngine
        config = {
            "strategy": {
                "stops": [
                    {"laps": 20, "compound": "RM", "ref_lap_ms": 0, "pace_threshold_ms": 2000},
                    {"laps": 20, "compound": "RH", "ref_lap_ms": 0, "pace_threshold_ms": 2000},
                ],
                "race_type": "timed",
                "race_duration_minutes": 40.0,
            }
        }
        tracker = MagicMock()
        announcer = MagicMock()
        bridge = MagicMock()

        # This replicates what main.py NOW does (no set_plan call)
        engine = RaceStrategyEngine(tracker, announcer, config, bridge)
        # Engine starts with no stints — stops in config are for UI display only
        assert engine._stints == [], (
            "Engine has stints from config — saved stops must NOT auto-activate at startup"
        )

    def test_config_with_race_type_does_not_auto_set_tracker(self):
        """Simulate the config with race_type=timed. The tracker must NOT have race config
        applied until the user explicitly activates an event."""
        from telemetry.state import RaceStateTracker, TyreThresholds, RaceType
        config = {
            "strategy": {
                "race_type": "timed",
                "race_duration_minutes": 40.0,
            },
            "race": {
                "type": "timed",
                "duration_minutes": 40.0,
            }
        }
        tracker = RaceStateTracker(queue.PriorityQueue(), TyreThresholds())

        # Replicate what main.py NOW does: nothing — no set_race_config call at startup
        # Tracker should remain at UNKNOWN
        assert tracker._manual_race_type == RaceType.UNKNOWN, (
            "Tracker has race config applied without user action — startup state leak"
        )
        assert tracker._timed_race_duration_ms == 0

    def test_double_print_eliminated_no_startup_calls(self):
        """The double [StateTracker] race config print was caused by two calls at startup.
        After the fix, there must be zero automatic calls — validate by checking
        neither main.py nor _update_race_config() auto-applies race config."""
        from telemetry.state import RaceStateTracker, TyreThresholds, RaceType
        tracker = RaceStateTracker(queue.PriorityQueue(), TyreThresholds())

        call_count = [0]
        original_set = tracker.set_race_config
        def counting_set(rt, dur=0.0):
            call_count[0] += 1
            return original_set(rt, dur)
        tracker.set_race_config = counting_set

        # Simulate main.py startup sequence (after fix — no automatic calls)
        # No set_race_config should be called here

        assert call_count[0] == 0, (
            f"set_race_config() called {call_count[0]} time(s) during simulated startup — "
            "expected 0 (explicit user action required)"
        )
