"""Group 54 — live adapter pit/tyre-age mapping tests.

Covers the Group 53 adapter's new mapping of the tracker pit/stint state into
RaceReplanState.tyre_age_laps + pit_stops_completed, with honest provenance.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.race_strategy_live_state import (  # noqa: E402
    build_replan_state_from_tracker,
    SRC_LIVE, SRC_LIVE_LOW, SRC_MISSING,
)


class _Tracker:
    def __init__(self, *, conf="HIGH", tyre_age=12, pit_stops=0, compound="RM"):
        self.laps_recorded = 12
        self.laps_remaining = 0
        self._current_compound = compound
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


class TestHighMediumMapping:
    def test_high_confidence_maps_tyre_and_pit(self):
        r = build_replan_state_from_tracker(_Tracker(conf="HIGH", tyre_age=12, pit_stops=0),
                                            packet=_Packet())
        assert r.state.tyre_age_laps == 12
        assert r.state.pit_stops_completed == 0
        assert r.state_sources["tyre_age_laps"] == SRC_LIVE
        assert r.state_sources["pit_stops_completed"] == SRC_LIVE
        assert r.pit_state_confidence == "HIGH"

    def test_medium_confidence_maps_tyre_and_pit(self):
        r = build_replan_state_from_tracker(_Tracker(conf="MEDIUM", tyre_age=1, pit_stops=1),
                                            packet=_Packet())
        assert r.state.tyre_age_laps == 1
        assert r.state.pit_stops_completed == 1
        assert r.state_sources["tyre_age_laps"] == SRC_LIVE


class TestLowConfidence:
    def test_low_confidence_not_populated_but_labelled(self):
        r = build_replan_state_from_tracker(_Tracker(conf="LOW", tyre_age=7, pit_stops=1),
                                            packet=_Packet())
        # Value NOT populated (can't lift readiness on a guess) …
        assert r.state.tyre_age_laps is None
        assert r.state.pit_stops_completed is None
        # … but the low-confidence estimate is surfaced honestly.
        assert r.state_sources["tyre_age_laps"] == SRC_LIVE_LOW
        assert any("low confidence" in w.lower() for w in r.warnings)


class TestUnknown:
    def test_unknown_is_missing(self):
        r = build_replan_state_from_tracker(_Tracker(conf="UNKNOWN", tyre_age=None, pit_stops=0),
                                            packet=_Packet())
        assert r.state.tyre_age_laps is None
        assert r.state.pit_stops_completed is None
        assert r.state_sources["tyre_age_laps"] == SRC_MISSING
        assert "tyre_age_laps" in r.missing_state


class TestSourceSummary:
    def test_summary_shows_pit_and_tyre_provenance(self):
        from strategy.race_strategy_live_state import summarise_live_state_sources
        r = build_replan_state_from_tracker(_Tracker(conf="HIGH"), packet=_Packet())
        s = summarise_live_state_sources(r)
        assert "tyre_age_laps" in s
        assert "pit_stops_completed" in s

    def test_dashboard_path_carries_pit_state(self):
        from strategy.race_strategy_live_state import build_replan_state_from_dashboard_context

        class D:
            _tracker = _Tracker(conf="HIGH", tyre_age=12, pit_stops=0)
            _last_packet = _Packet()

        r = build_replan_state_from_dashboard_context(D())
        assert r.state.tyre_age_laps == 12
        assert r.state.pit_stops_completed == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
