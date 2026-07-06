"""Group 51 — event settings validation tests.

Covers `validate_event_settings`:
  • missing race duration / refuel / pit loss / car / track are warned
  • valid Porsche/Fuji settings pass
  • invalid values never crash; manual/default labelled honestly

All tests are pure/offline.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.race_strategy_readiness_vm import (  # noqa: E402
    validate_event_settings,
    CheckStatus,
    EventSettingsValidation,
)


def _es(**over):
    es = dict(
        car_id=911, track="Fuji Speedway", layout_id="fuji__full",
        race_duration_minutes=50.0, race_laps=0,
        fuel_multiplier=3.0, tyre_multiplier=8.0,
        refuel_rate_lps=1.0, pit_loss_seconds=22.0, starting_fuel_pct=100.0,
        required_compounds=(), mandatory_pit_stops=0,
    )
    es.update(over)
    return es


class TestValid:
    def test_porsche_fuji_passes(self):
        v = validate_event_settings(_es())
        assert isinstance(v, EventSettingsValidation)
        assert v.can_run
        assert v.field_status["race_length"] == CheckStatus.OK
        assert v.field_status["refuel_rate_lps"] == CheckStatus.OK
        assert v.field_status["pit_loss_seconds"] == CheckStatus.OK

    def test_lap_race_passes(self):
        v = validate_event_settings(_es(race_duration_minutes=0.0, race_laps=30))
        assert v.can_run
        assert v.field_status["race_length"] == CheckStatus.OK


class TestWarnings:
    def test_missing_race_length_warns_and_blocks(self):
        v = validate_event_settings(_es(race_duration_minutes=0.0, race_laps=0))
        assert not v.can_run
        assert any("race duration" in w.lower() for w in v.warnings)
        assert v.field_status["race_length"] == CheckStatus.MISSING

    def test_missing_refuel_warns(self):
        v = validate_event_settings(_es(refuel_rate_lps=0.0))
        assert any("refuel rate" in w.lower() for w in v.warnings)
        assert v.field_status["refuel_rate_lps"] == CheckStatus.MISSING
        # still runnable — race length present
        assert v.can_run

    def test_missing_pit_loss_warns(self):
        v = validate_event_settings(_es(pit_loss_seconds=0.0))
        assert any("pit loss" in w.lower() for w in v.warnings)
        assert v.field_status["pit_loss_seconds"] == CheckStatus.MISSING

    def test_missing_car_and_track_warns(self):
        v = validate_event_settings(_es(car_id=0, track=""))
        assert v.field_status["car_id"] == CheckStatus.MISSING
        assert v.field_status["track"] == CheckStatus.MISSING
        assert any("car" in w.lower() for w in v.warnings)
        assert any("track" in w.lower() for w in v.warnings)


class TestManualLabelling:
    def test_manual_pit_loss_labelled_manual(self):
        v = validate_event_settings(_es(pit_loss_is_manual=True))
        assert v.field_status["pit_loss_seconds"] == CheckStatus.MANUAL
        assert any("manual" in w.lower() for w in v.warnings)

    def test_event_pit_loss_labelled_ok(self):
        v = validate_event_settings(_es(pit_loss_is_manual=False))
        assert v.field_status["pit_loss_seconds"] == CheckStatus.OK

    def test_layout_absent_is_na(self):
        v = validate_event_settings(_es(layout_id=""))
        assert v.field_status["layout_id"] == CheckStatus.NA


class TestNoCrash:
    def test_garbage_does_not_crash(self):
        v = validate_event_settings({"race_laps": "x", "refuel_rate_lps": None, "car_id": object()})
        assert isinstance(v, EventSettingsValidation)
        assert not v.can_run  # no valid race length

    def test_empty_dict(self):
        v = validate_event_settings({})
        assert isinstance(v, EventSettingsValidation)
        assert not v.can_run

    def test_none(self):
        v = validate_event_settings(None)
        assert isinstance(v, EventSettingsValidation)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
