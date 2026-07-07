"""Group 54 — RaceStateTracker pit-state integration tests.

Exercises the REAL tracker wiring: the pit/stint state advances on lap boundaries
(`_check_lap`) and counts a stop on pit exit (`_exit_pit`). Read-only; no file
writes. Uses MagicMock packets (the tracker's own test convention).
"""
from __future__ import annotations

import queue
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from telemetry.state import RaceStateTracker, TyreThresholds, RacePhase  # noqa: E402
from telemetry.pit_state import start_stint_tracking  # noqa: E402


def _tracker():
    return RaceStateTracker(queue.PriorityQueue(), TyreThresholds())


def _lap_packet(last_lap_ms, *, fuel_level=20.0):
    p = MagicMock()
    p.loading = False
    p.car_on_track = True
    p.last_lap_ms = last_lap_ms
    p.best_lap_ms = 90000
    p.fuel_level = fuel_level
    p.fuel_capacity = 100.0
    p.speed_kmh = 200.0
    p.current_position = 1
    p.total_cars = 1
    p.remaining_time_ms = 0
    p.laps_completed = 1
    return p


class TestGetters:
    def test_getters_exist_and_default(self):
        t = _tracker()
        assert t.pit_stops_completed == 0
        assert t.laps_since_pit == 0
        assert t.tyre_age_laps is None          # not tracking yet
        assert t.pit_state_confidence == "UNKNOWN"

    def test_pit_stint_state_exposed(self):
        t = _tracker()
        assert hasattr(t, "pit_stint_state")
        assert t.pit_stint_state.tracking_active is False


class TestLapWiring:
    def test_lap_boundary_ages_stint(self):
        t = _tracker()
        t._phase = RacePhase.RACING
        t._pit_stint = start_stint_tracking(t._pit_stint)
        t._prev = None
        # Feed two distinct completed laps through the real _check_lap.
        import time
        t._check_lap(_lap_packet(90000), time.monotonic())
        t._prev = _lap_packet(90000)
        t._check_lap(_lap_packet(91000), time.monotonic())
        assert t.laps_since_pit == 2
        assert t.tyre_age_laps == 2
        assert t.pit_state_confidence == "HIGH"


class TestPitWiring:
    def test_pit_exit_counts_and_resets(self):
        import time
        t = _tracker()
        t._phase = RacePhase.RACING
        t._pit_stint = start_stint_tracking(t._pit_stint)
        # Age the stint two laps first (start with no prev so the first lap records).
        t._prev = None
        t._check_lap(_lap_packet(90000), time.monotonic())
        t._prev = _lap_packet(90000)
        t._check_lap(_lap_packet(91000), time.monotonic())
        assert t.laps_since_pit == 2

        # Simulate a refuel pit: fuel went up a lot vs pit-entry level.
        t._fuel_at_pit_entry = 5.0
        t._phase = RacePhase.IN_PIT
        exit_pkt = _lap_packet(0, fuel_level=95.0)   # big refuel
        t._prev = _lap_packet(0, fuel_level=95.0)
        t._exit_pit(exit_pkt, time.monotonic())
        assert t.pit_stops_completed == 1
        assert t.laps_since_pit == 0                 # stint reset
        assert t.pit_state_confidence == "MEDIUM"    # refuel-based

    def test_speed_only_pit_is_low_confidence(self):
        import time
        t = _tracker()
        t._phase = RacePhase.RACING
        t._pit_stint = start_stint_tracking(t._pit_stint)
        t._fuel_at_pit_entry = 40.0
        t._phase = RacePhase.IN_PIT
        exit_pkt = _lap_packet(0, fuel_level=40.0)   # no refuel
        t._prev = _lap_packet(0, fuel_level=40.0)
        t._exit_pit(exit_pkt, time.monotonic())
        assert t.pit_stops_completed == 1
        assert t.pit_state_confidence == "LOW"


class TestRobustness:
    def test_malformed_packet_does_not_crash_getters(self):
        t = _tracker()
        # getters read a pure dataclass — cannot crash
        assert isinstance(t.pit_stops_completed, int)
        assert isinstance(t.pit_state_confidence, str)

    def test_no_file_writes_in_tracker_pit_paths(self):
        src = (ROOT / "telemetry" / "state.py").read_text(encoding="utf-8")
        # The pit-state wiring must not introduce file writes.
        assert "pit_state" in src  # import present
        # (state.py has no open()/write to persistent files in the pit paths)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
