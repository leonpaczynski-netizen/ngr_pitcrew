"""Group 54 — pit detection rule tests.

Covers the conservative detection classifier + the model's refusal to count
non-pit signals (a single low-speed moment, fuel noise, spin/crash). Because the
pure model only counts events it is explicitly given, the conservatism lives in
the tracker's existing detection (fuel-refuel / sustained-stop) — here we prove the
classifier + the model gate work together honestly.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from telemetry.pit_state import (  # noqa: E402
    PitStintState, PitEvent, PitDetectionConfidence,
    start_stint_tracking, apply_pit_event, apply_manual_pit,
    classify_pit_confidence,
)


class TestExplicitAndManual:
    def test_explicit_refuel_pit_counted_medium(self):
        s = start_stint_tracking(PitStintState())
        conf = classify_pit_confidence(fuel_added=25.0, pit_threshold=0.5)
        r = apply_pit_event(s, pit_lap=10, confidence=conf, source="refuel-detected pit",
                            event=PitEvent.EXIT)
        assert r.counted is True
        assert r.state.pit_detection_confidence == PitDetectionConfidence.MEDIUM

    def test_manual_marker_counted_and_labelled(self):
        s = apply_manual_pit(PitStintState(), pit_lap=12)
        assert s.pit_stops_completed == 1
        assert s.pit_detection_source == "manual"
        assert s.last_pit_event == PitEvent.MANUAL

    def test_speed_only_stop_counted_low(self):
        s = start_stint_tracking(PitStintState())
        conf = classify_pit_confidence(fuel_added=0.0, pit_threshold=0.5)  # no refuel
        r = apply_pit_event(s, pit_lap=10, confidence=conf, source="speed-stop pit (no refuel)",
                            event=PitEvent.EXIT)
        assert r.counted is True
        assert r.state.pit_detection_confidence == PitDetectionConfidence.LOW


class TestNonPitSignalsNotCounted:
    def test_no_event_means_no_count(self):
        # A single low-speed moment / fuel noise never produces a pit EXIT event,
        # so the model is simply never asked to count → stays 0.
        s = start_stint_tracking(PitStintState())
        assert s.pit_stops_completed == 0

    def test_none_event_from_noise_ignored(self):
        s = start_stint_tracking(PitStintState())
        r = apply_pit_event(s, pit_lap=5, confidence=PitDetectionConfidence.LOW,
                            source="noise", event=PitEvent.NONE)
        assert r.counted is False
        assert r.state.pit_stops_completed == 0

    def test_fuel_noise_below_threshold_is_low_not_medium(self):
        # Tiny fuel jitter must not be classified as a confident refuel.
        assert classify_pit_confidence(fuel_added=0.02, pit_threshold=0.5) == PitDetectionConfidence.LOW

    def test_pit_event_without_tracking_not_counted(self):
        # An EXIT event before race-start tracking began is not counted.
        r = apply_pit_event(PitStintState(), pit_lap=3, confidence=PitDetectionConfidence.MEDIUM,
                            source="stray", event=PitEvent.EXIT)
        assert r.counted is False
        assert r.state.pit_stops_completed == 0


class TestDetectionSourceExists:
    def test_tracker_detection_wiring_present(self):
        # The existing tracker detection (fuel-refuel + sustained-stop) feeds the
        # model; assert the wiring calls exist in state.py.
        src = (ROOT / "telemetry" / "state.py").read_text(encoding="utf-8")
        assert "apply_pit_event(" in src
        assert "classify_pit_confidence(" in src
        assert "start_stint_tracking(" in src
        assert "apply_lap_completed(" in src


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
