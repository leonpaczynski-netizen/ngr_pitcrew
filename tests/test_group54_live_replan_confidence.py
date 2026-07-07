"""Group 54 — live replan confidence-lift tests.

Proves that knowing tyre age + pit count (from the new tracker pit state) can move
replan confidence above LOW when other critical state is present — while unknown
tyre age still caps at LOW and missing fuel/distance stays INSUFFICIENT.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.race_strategy_uat import run_fuji_uat  # noqa: E402
from strategy.race_strategy_replan import RaceReplanState, ReplanConfidence  # noqa: E402
from strategy.race_strategy_live_replan import build_live_replan_snapshot  # noqa: E402
from strategy.race_strategy_live_state import build_replan_state_from_tracker  # noqa: E402


@pytest.fixture(scope="module")
def pre_race():
    return run_fuji_uat()


class _Tracker:
    def __init__(self, *, conf, tyre_age, pit_stops):
        self.laps_recorded = 12
        self.laps_remaining = 0
        self._current_compound = "RM"
        self.avg_fuel_per_lap = 4.0
        self.timed_duration_minutes = 50.0
        self.pit_state_confidence = conf
        self.tyre_age_laps = tyre_age
        self.pit_stops_completed = pit_stops

    def computed_remaining_ms(self):
        return 1800000


class _Packet:
    fuel_level = 60.0
    fuel_capacity = 100.0


def _snapshot(pre_race, tracker):
    st = build_replan_state_from_tracker(tracker, packet=_Packet()).state
    return build_live_replan_snapshot(pre_race_result=pre_race, live_state=st)


class TestConfidenceLift:
    def test_known_tyre_and_pit_moves_above_low(self, pre_race):
        # HIGH pit state (tyre age + pit count known) → confidence rises to MEDIUM.
        r = _snapshot(pre_race, _Tracker(conf="HIGH", tyre_age=12, pit_stops=0))
        assert r.confidence == ReplanConfidence.MEDIUM
        assert r.confidence != ReplanConfidence.LOW

    def test_medium_pit_state_also_lifts(self, pre_race):
        r = _snapshot(pre_race, _Tracker(conf="MEDIUM", tyre_age=2, pit_stops=1))
        assert r.confidence == ReplanConfidence.MEDIUM


class TestConfidenceCaps:
    def test_unknown_tyre_caps_at_low(self, pre_race):
        r = _snapshot(pre_race, _Tracker(conf="UNKNOWN", tyre_age=None, pit_stops=0))
        assert r.confidence == ReplanConfidence.LOW

    def test_low_confidence_pit_does_not_lift(self, pre_race):
        # A LOW-confidence pit estimate is not used → tyre age unknown → LOW.
        r = _snapshot(pre_race, _Tracker(conf="LOW", tyre_age=7, pit_stops=1))
        assert r.confidence == ReplanConfidence.LOW

    def test_not_forced_high(self, pre_race):
        # Even with tyre age known, live confidence is capped at MEDIUM (proxies).
        r = _snapshot(pre_race, _Tracker(conf="HIGH", tyre_age=12, pit_stops=0))
        assert r.confidence != ReplanConfidence.__members__.get("HIGH", object())


class TestCriticalStateStillGoverns:
    def test_missing_fuel_stays_insufficient(self, pre_race):
        st = RaceReplanState(current_lap=12, current_compound="RM", remaining_laps=18,
                             tyre_age_laps=12, pit_stops_completed=0)  # no fuel
        r = build_live_replan_snapshot(pre_race_result=pre_race, live_state=st)
        assert r.confidence == ReplanConfidence.INSUFFICIENT_EVIDENCE

    def test_missing_distance_stays_insufficient(self, pre_race):
        st = RaceReplanState(current_lap=12, fuel_remaining_pct=60.0, current_compound="RM",
                             tyre_age_laps=12, pit_stops_completed=0)  # no remaining distance
        r = build_live_replan_snapshot(pre_race_result=pre_race, live_state=st)
        assert r.confidence == ReplanConfidence.INSUFFICIENT_EVIDENCE

    def test_pit_uncertainty_prevents_false_high(self, pre_race):
        r = _snapshot(pre_race, _Tracker(conf="LOW", tyre_age=7, pit_stops=1))
        assert r.confidence in (ReplanConfidence.LOW, ReplanConfidence.INSUFFICIENT_EVIDENCE)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
