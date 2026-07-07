"""Group 54 — pure pit/stint state model tests.

Covers telemetry/pit_state.py: the deterministic state machine that counts pit
stops and ages the current stint. Pure — no files, no AI, no actions.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from telemetry.pit_state import (  # noqa: E402
    PitStintState, PitEvent, PitDetectionConfidence,
    start_stint_tracking, apply_lap_completed, apply_pit_event, apply_manual_pit,
    classify_pit_confidence,
)


class TestInitialState:
    def test_initial_is_honest_unknown(self):
        s = PitStintState()
        assert s.pit_stops_completed == 0
        assert s.laps_since_pit == 0
        assert s.tracking_active is False
        assert s.tyre_age_laps is None          # unknown until tracking starts
        assert s.pit_detection_confidence == PitDetectionConfidence.UNKNOWN
        assert "tyre_age_laps" in s.missing_state


class TestStintTracking:
    def test_start_tracking_zero_pits_high_confidence(self):
        s = start_stint_tracking(PitStintState())
        assert s.tracking_active is True
        assert s.pit_stops_completed == 0
        assert s.tyre_age_laps == 0
        assert s.pit_detection_confidence == PitDetectionConfidence.HIGH

    def test_laps_increment_across_boundaries(self):
        s = start_stint_tracking(PitStintState())
        for i in range(5):
            s = apply_lap_completed(s, i + 1)
        assert s.laps_since_pit == 5
        assert s.tyre_age_laps == 5

    def test_lap_ignored_when_not_tracking(self):
        s = apply_lap_completed(PitStintState(), 3)
        assert s.laps_since_pit == 0
        assert s.tracking_active is False

    def test_negative_lap_ignored_with_warning(self):
        s = start_stint_tracking(PitStintState())
        s = apply_lap_completed(s, -4)
        assert s.laps_since_pit == 0
        assert any("negative" in w.lower() for w in s.warnings)


class TestPitEvents:
    def test_pit_event_increments_once(self):
        s = start_stint_tracking(PitStintState())
        for i in range(10):
            s = apply_lap_completed(s, i + 1)
        r = apply_pit_event(s, pit_lap=10, confidence=PitDetectionConfidence.MEDIUM,
                            source="refuel", event=PitEvent.EXIT)
        assert r.counted is True
        assert r.state.pit_stops_completed == 1
        assert r.state.laps_since_pit == 0          # reset
        assert r.state.current_stint_index == 1
        assert r.state.pit_detection_confidence == PitDetectionConfidence.MEDIUM

    def test_just_pitted_resets_laps_since_pit(self):
        s = start_stint_tracking(PitStintState())
        s = apply_lap_completed(s, 1)
        r = apply_pit_event(s, pit_lap=1, confidence=PitDetectionConfidence.MEDIUM,
                            source="refuel", event=PitEvent.EXIT)
        assert r.state.tyre_age_laps == 0
        s2 = apply_lap_completed(r.state, 2)
        assert s2.tyre_age_laps == 1

    def test_duplicate_pit_same_lap_not_double_counted(self):
        s = start_stint_tracking(PitStintState())
        s = apply_lap_completed(s, 8)
        r1 = apply_pit_event(s, pit_lap=8, confidence=PitDetectionConfidence.MEDIUM,
                             source="a", event=PitEvent.EXIT)
        r2 = apply_pit_event(r1.state, pit_lap=8, confidence=PitDetectionConfidence.MEDIUM,
                             source="b", event=PitEvent.EXIT)
        assert r1.counted is True
        assert r2.counted is False
        assert r2.state.pit_stops_completed == 1

    def test_none_event_never_counts(self):
        s = start_stint_tracking(PitStintState())
        r = apply_pit_event(s, pit_lap=5, confidence=PitDetectionConfidence.MEDIUM,
                            source="x", event=PitEvent.NONE)
        assert r.counted is False
        assert r.state.pit_stops_completed == 0

    def test_confidence_carried_through(self):
        s = start_stint_tracking(PitStintState())
        r = apply_pit_event(s, pit_lap=5, confidence=PitDetectionConfidence.LOW,
                            source="speed-only", event=PitEvent.EXIT)
        assert r.state.pit_detection_confidence == PitDetectionConfidence.LOW
        assert "speed-only" in r.state.pit_detection_source

    def test_manual_pit_starts_tracking_and_counts(self):
        s = apply_manual_pit(PitStintState(), pit_lap=6)
        assert s.tracking_active is True
        assert s.pit_stops_completed == 1
        assert s.last_pit_event == PitEvent.MANUAL


class TestClassify:
    def test_refuel_is_medium(self):
        assert classify_pit_confidence(30.0, 0.5) == PitDetectionConfidence.MEDIUM

    def test_no_refuel_is_low(self):
        assert classify_pit_confidence(0.0, 0.5) == PitDetectionConfidence.LOW

    def test_garbage_is_low(self):
        assert classify_pit_confidence(None, None) == PitDetectionConfidence.LOW


class TestNoSideEffects:
    def test_model_does_no_io(self):
        # Docstrings may say "writes no files"; what must be absent is a real write.
        src = (ROOT / "telemetry" / "pit_state.py").read_text(encoding="utf-8")
        for banned in ("open(", ".write(", "save_entry", "sqlite3", "requests",
                       "call_api", "setup_history", "PyQt", "QtWidgets"):
            assert banned not in src


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
