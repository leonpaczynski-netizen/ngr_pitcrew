"""
Group 31 — Shift Indicator / RPM Beep backend unit tests

Covers:
  Section A — should_shift_beep pure helper
  Section B — resolve_threshold pure helper
  Section C — _parse_setup_recommendation: new shift_rpm_qual/race fields
  Section D — Prompt text contains both shift_rpm_qual and shift_rpm_race (source-scan)

No Qt, no audio — play_beep_direct is never called (pure functions tested only).
Matches patterns from test_group26_setup_overhaul.py.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Import the two pure helpers directly from main (no Qt widgets needed at
# import time because only module-level names are accessed, not the Qt app).
# ---------------------------------------------------------------------------

from main import resolve_threshold, should_shift_beep  # noqa: E402

from strategy.ai_planner import (  # noqa: E402
    _parse_setup_recommendation,
    _build_setup_from_scratch_prompt,
)


# ---------------------------------------------------------------------------
# Minimal JSON for _parse_setup_recommendation
# ---------------------------------------------------------------------------

def _make_setup_json(**overrides) -> str:
    """Return a valid minimal setup JSON with optional field overrides."""
    base = {
        "ride_height_front": 80,
        "ride_height_rear": 82,
        "springs_front": 3.50,
        "springs_rear": 3.00,
        "dampers_front_comp": 30,
        "dampers_front_ext": 40,
        "dampers_rear_comp": 25,
        "dampers_rear_ext": 35,
        "arb_front": 4,
        "arb_rear": 3,
        "camber_front": 1.0,
        "camber_rear": 1.5,
        "toe_front": 0.00,
        "toe_rear": 0.05,
        "aero_front": 400,
        "aero_rear": 600,
        "lsd_initial": 10,
        "lsd_accel": 15,
        "lsd_decel": 5,
        "lsd_front_initial": 0,
        "lsd_front_accel": 0,
        "lsd_front_decel": 0,
        "brake_bias": 0,
        "ballast_kg": 0.0,
        "ballast_position": 0,
        "power_restrictor": 100.0,
        "final_drive": 3.5,
        "transmission_max_speed_kmh": 270.0,
        "gear_ratios": [3.2, 2.3, 1.75, 1.40, 1.15, 0.95],
        "ecu_recommendation": "Stock ECU",
        "shift_rpm_qual": 7400,
        "shift_rpm_race": 7000,
        "reasoning": "Some reasoning text.",
    }
    base.update(overrides)
    return json.dumps(base)


_MINIMAL_PROMPT_KWARGS = dict(
    car="Test Car",
    track="Suzuka",
    session_type="Race",
    race_laps=10,
    min_weight_kg=0.0,
    max_power_hp=0.0,
)


def _make_prompt(**overrides) -> str:
    kwargs = dict(_MINIMAL_PROMPT_KWARGS)
    kwargs.update(overrides)
    return _build_setup_from_scratch_prompt(**kwargs)


# ===========================================================================
# Section A — should_shift_beep
# ===========================================================================

class TestShouldShiftBeep:
    """A — Pure helper: should_shift_beep()"""

    # -----------------------------------------------------------------------
    # A1: fires on upshift at/above threshold
    # -----------------------------------------------------------------------

    def test_fires_at_threshold(self):
        """Beep fires when rpm == threshold, enabled, valid gear, not hysteresis-armed."""
        beep, new_above, new_dm = should_shift_beep(
            prev_gear=2, cur_gear=2, rpm=7000.0, threshold=7000.0,
            shift_above=False, enabled=True,
            muted_until=0.0, downshift_muted_until=0.0, now=1.0,
        )
        assert beep is True
        assert new_above is True

    def test_fires_above_threshold(self):
        beep, new_above, _ = should_shift_beep(
            prev_gear=3, cur_gear=3, rpm=7200.0, threshold=7000.0,
            shift_above=False, enabled=True,
            muted_until=0.0, downshift_muted_until=0.0, now=1.0,
        )
        assert beep is True
        assert new_above is True

    # -----------------------------------------------------------------------
    # A2: no re-fire while shift_above is True and RPM is still high
    # -----------------------------------------------------------------------

    def test_no_refire_while_shift_above_and_rpm_high(self):
        """Once fired (shift_above=True), no beep even if rpm >= threshold."""
        beep, new_above, _ = should_shift_beep(
            prev_gear=3, cur_gear=3, rpm=7200.0, threshold=7000.0,
            shift_above=True, enabled=True,
            muted_until=0.0, downshift_muted_until=0.0, now=1.0,
        )
        assert beep is False
        assert new_above is True

    # -----------------------------------------------------------------------
    # A3: re-arms after RPM < 0.95 * threshold
    # -----------------------------------------------------------------------

    def test_rearms_after_rpm_drops(self):
        """shift_above becomes False when rpm < 0.95 * threshold."""
        beep, new_above, _ = should_shift_beep(
            prev_gear=3, cur_gear=3, rpm=6600.0, threshold=7000.0,
            shift_above=True, enabled=True,
            muted_until=0.0, downshift_muted_until=0.0, now=1.0,
        )
        # rpm=6600 < 7000*0.95=6650 → re-arms
        assert beep is False
        assert new_above is False

    def test_rearms_at_exact_boundary(self):
        """RPM exactly at 0.95*threshold → re-arm (< condition, not <=)."""
        threshold = 7000.0
        rpm = threshold * 0.94  # clearly below
        beep, new_above, _ = should_shift_beep(
            prev_gear=3, cur_gear=3, rpm=rpm, threshold=threshold,
            shift_above=True, enabled=True,
            muted_until=0.0, downshift_muted_until=0.0, now=1.0,
        )
        assert new_above is False

    def test_does_not_rearm_at_0_95(self):
        """RPM == 0.95*threshold → NOT re-armed (uses strict < )."""
        threshold = 7000.0
        rpm = threshold * 0.95  # exactly at boundary — NOT below
        beep, new_above, _ = should_shift_beep(
            prev_gear=3, cur_gear=3, rpm=rpm, threshold=threshold,
            shift_above=True, enabled=True,
            muted_until=0.0, downshift_muted_until=0.0, now=1.0,
        )
        # 6650.0 is NOT < 6650.0 so hysteresis stays True
        assert new_above is True

    # -----------------------------------------------------------------------
    # A4: downshift sets ~now+0.3 mute and no beep
    # -----------------------------------------------------------------------

    def test_downshift_no_beep(self):
        now = 5.0
        beep, new_above, new_dm = should_shift_beep(
            prev_gear=4, cur_gear=3, rpm=7500.0, threshold=7000.0,
            shift_above=False, enabled=True,
            muted_until=0.0, downshift_muted_until=0.0, now=now,
        )
        assert beep is False
        assert new_dm == pytest.approx(now + 0.3, abs=1e-9)

    def test_downshift_sets_shift_above_true(self):
        """Downshift should arm shift_above to suppress throttle-blip beep."""
        now = 5.0
        beep, new_above, _ = should_shift_beep(
            prev_gear=5, cur_gear=3, rpm=6000.0, threshold=7000.0,
            shift_above=False, enabled=True,
            muted_until=0.0, downshift_muted_until=0.0, now=now,
        )
        assert new_above is True

    # -----------------------------------------------------------------------
    # A5: beep suppressed while downshift_muted_until > now
    # -----------------------------------------------------------------------

    def test_suppressed_while_downshift_muted(self):
        now = 5.0
        beep, _, _ = should_shift_beep(
            prev_gear=3, cur_gear=3, rpm=7200.0, threshold=7000.0,
            shift_above=False, enabled=True,
            muted_until=0.0, downshift_muted_until=now + 0.2, now=now,
        )
        assert beep is False

    def test_fires_after_downshift_mute_expires(self):
        now = 5.5
        beep, _, _ = should_shift_beep(
            prev_gear=3, cur_gear=3, rpm=7200.0, threshold=7000.0,
            shift_above=False, enabled=True,
            muted_until=0.0, downshift_muted_until=5.0, now=now,
        )
        assert beep is True

    # -----------------------------------------------------------------------
    # A6: enabled=False → no beep
    # -----------------------------------------------------------------------

    def test_enabled_false_no_beep(self):
        beep, new_above, new_dm = should_shift_beep(
            prev_gear=3, cur_gear=3, rpm=8000.0, threshold=7000.0,
            shift_above=False, enabled=False,
            muted_until=0.0, downshift_muted_until=0.0, now=1.0,
        )
        assert beep is False
        # State is left unchanged when disabled
        assert new_above is False
        assert new_dm == 0.0

    # -----------------------------------------------------------------------
    # A7: neutral gear (0) → no beep
    # -----------------------------------------------------------------------

    def test_neutral_gear_no_beep(self):
        beep, _, _ = should_shift_beep(
            prev_gear=1, cur_gear=0, rpm=8000.0, threshold=7000.0,
            shift_above=False, enabled=True,
            muted_until=0.0, downshift_muted_until=0.0, now=1.0,
        )
        assert beep is False

    # -----------------------------------------------------------------------
    # A8: reverse gear (>=9, e.g. 15 in GT7) → no beep
    # -----------------------------------------------------------------------

    def test_reverse_gear_15_no_beep(self):
        beep, _, _ = should_shift_beep(
            prev_gear=0, cur_gear=15, rpm=2000.0, threshold=7000.0,
            shift_above=False, enabled=True,
            muted_until=0.0, downshift_muted_until=0.0, now=1.0,
        )
        assert beep is False

    def test_gear_9_no_beep(self):
        beep, _, _ = should_shift_beep(
            prev_gear=8, cur_gear=9, rpm=8000.0, threshold=7000.0,
            shift_above=False, enabled=True,
            muted_until=0.0, downshift_muted_until=0.0, now=1.0,
        )
        assert beep is False

    # -----------------------------------------------------------------------
    # A9: muted_until guard (race-finish mute)
    # -----------------------------------------------------------------------

    def test_muted_until_suppresses_beep(self):
        now = 5.0
        beep, _, _ = should_shift_beep(
            prev_gear=3, cur_gear=3, rpm=7200.0, threshold=7000.0,
            shift_above=False, enabled=True,
            muted_until=now + 60.0, downshift_muted_until=0.0, now=now,
        )
        assert beep is False

    # -----------------------------------------------------------------------
    # A10: first gear is a valid drive gear (boundary)
    # -----------------------------------------------------------------------

    def test_gear_1_valid(self):
        beep, _, _ = should_shift_beep(
            prev_gear=0, cur_gear=1, rpm=7200.0, threshold=7000.0,
            shift_above=False, enabled=True,
            muted_until=0.0, downshift_muted_until=0.0, now=1.0,
        )
        # cur_gear=1 > prev_gear=0, not a downshift
        assert beep is True

    def test_gear_8_valid(self):
        beep, _, _ = should_shift_beep(
            prev_gear=7, cur_gear=8, rpm=7200.0, threshold=7000.0,
            shift_above=False, enabled=True,
            muted_until=0.0, downshift_muted_until=0.0, now=1.0,
        )
        # upshift from 7→8 is NOT a downshift; rpm >= threshold → beep
        assert beep is True


# ===========================================================================
# Section B — resolve_threshold
# ===========================================================================

class TestResolveThreshold:
    """B — Pure helper: resolve_threshold()"""

    # -----------------------------------------------------------------------
    # B1: race / is_racing → race_rpm
    # -----------------------------------------------------------------------

    def test_is_racing_returns_race_rpm(self):
        sb = {"enabled": True, "qual_rpm": 7000, "race_rpm": 6500}
        key, thresh = resolve_threshold("Race", is_racing=True,
                                        practice_is_qual=False, sb=sb)
        assert key == "race_rpm"
        assert thresh == 6500.0

    def test_is_racing_overrides_live_mode(self):
        """Even if live_mode='Qualifying', is_racing=True selects race_rpm."""
        sb = {"enabled": True, "qual_rpm": 7000, "race_rpm": 6500}
        key, thresh = resolve_threshold("Qualifying", is_racing=True,
                                        practice_is_qual=False, sb=sb)
        assert key == "race_rpm"

    # -----------------------------------------------------------------------
    # B2: qualifying → qual_rpm
    # -----------------------------------------------------------------------

    def test_qualifying_returns_qual_rpm(self):
        sb = {"enabled": True, "qual_rpm": 7000, "race_rpm": 6500}
        key, thresh = resolve_threshold("Qualifying", is_racing=False,
                                        practice_is_qual=False, sb=sb)
        assert key == "qual_rpm"
        assert thresh == 7000.0

    # -----------------------------------------------------------------------
    # B3: practice + practice_is_qual=True → qual_rpm
    # -----------------------------------------------------------------------

    def test_practice_is_qual_true_returns_qual_rpm(self):
        sb = {"enabled": True, "qual_rpm": 7000, "race_rpm": 6500}
        key, thresh = resolve_threshold("Practice", is_racing=False,
                                        practice_is_qual=True, sb=sb)
        assert key == "qual_rpm"
        assert thresh == 7000.0

    # -----------------------------------------------------------------------
    # B4: practice + practice_is_qual=False → race_rpm
    # -----------------------------------------------------------------------

    def test_practice_is_qual_false_returns_race_rpm(self):
        sb = {"enabled": True, "qual_rpm": 7000, "race_rpm": 6500}
        key, thresh = resolve_threshold("Practice", is_racing=False,
                                        practice_is_qual=False, sb=sb)
        assert key == "race_rpm"
        assert thresh == 6500.0

    # -----------------------------------------------------------------------
    # B5: missing keys → default 7000, no KeyError
    # -----------------------------------------------------------------------

    def test_empty_sb_defaults_to_7000(self):
        key, thresh = resolve_threshold("Qualifying", is_racing=False,
                                        practice_is_qual=False, sb={})
        assert thresh == 7000.0

    def test_missing_race_rpm_defaults_to_7000(self):
        sb = {"qual_rpm": 7500}  # race_rpm absent
        key, thresh = resolve_threshold("Race", is_racing=True,
                                        practice_is_qual=False, sb=sb)
        # race_rpm missing → falls back to 7000
        assert thresh == 7000.0

    def test_missing_qual_rpm_defaults_to_7000(self):
        sb = {"race_rpm": 6500}  # qual_rpm absent
        key, thresh = resolve_threshold("Qualifying", is_racing=False,
                                        practice_is_qual=False, sb=sb)
        # qual_rpm missing → falls back to 7000
        assert thresh == 7000.0

    # -----------------------------------------------------------------------
    # B6: legacy "rpm" key fallback
    # -----------------------------------------------------------------------

    def test_legacy_rpm_fallback(self):
        sb = {"rpm": 6800}  # old config format
        key, thresh = resolve_threshold("Qualifying", is_racing=False,
                                        practice_is_qual=False, sb=sb)
        assert thresh == 6800.0

    def test_legacy_rpm_fallback_race(self):
        sb = {"rpm": 6800}
        key, thresh = resolve_threshold("Race", is_racing=True,
                                        practice_is_qual=False, sb=sb)
        assert thresh == 6800.0

    # -----------------------------------------------------------------------
    # B7: unknown live_mode (e.g. "Spectate") → qual_rpm
    # -----------------------------------------------------------------------

    def test_unknown_mode_returns_qual_rpm(self):
        sb = {"qual_rpm": 7100, "race_rpm": 6600}
        key, thresh = resolve_threshold("Spectate", is_racing=False,
                                        practice_is_qual=False, sb=sb)
        assert key == "qual_rpm"
        assert thresh == 7100.0


# ===========================================================================
# Section C — _parse_setup_recommendation new fields
# ===========================================================================

class TestParseSetupRecommendationNewFields:
    """C — Parser: shift_rpm_qual, shift_rpm_race, legacy shift_rpm."""

    def test_returns_shift_rpm_qual(self):
        rec = _parse_setup_recommendation(_make_setup_json(
            shift_rpm_qual=7400, shift_rpm_race=7000
        ))
        assert rec.shift_rpm_qual == 7400

    def test_returns_shift_rpm_race(self):
        rec = _parse_setup_recommendation(_make_setup_json(
            shift_rpm_qual=7400, shift_rpm_race=7000
        ))
        assert rec.shift_rpm_race == 7000

    def test_legacy_shift_rpm_equals_max_of_qual_race(self):
        """Legacy shift_rpm must be max(qual, race)."""
        rec = _parse_setup_recommendation(_make_setup_json(
            shift_rpm_qual=7400, shift_rpm_race=7000
        ))
        assert rec.shift_rpm == max(rec.shift_rpm_qual, rec.shift_rpm_race)
        assert rec.shift_rpm == 7400

    def test_legacy_shift_rpm_when_race_higher_than_qual(self):
        """Unusual but clamps correctly: max still picks the higher value."""
        rec = _parse_setup_recommendation(_make_setup_json(
            shift_rpm_qual=6800, shift_rpm_race=7100
        ))
        assert rec.shift_rpm == 7100

    def test_clamps_negative_qual_to_zero(self):
        rec = _parse_setup_recommendation(_make_setup_json(
            shift_rpm_qual=-100, shift_rpm_race=7000
        ))
        assert rec.shift_rpm_qual == 0

    def test_clamps_negative_race_to_zero(self):
        rec = _parse_setup_recommendation(_make_setup_json(
            shift_rpm_qual=7400, shift_rpm_race=-50
        ))
        assert rec.shift_rpm_race == 0

    def test_both_zero_anomaly_no_exception(self):
        """Electric car / unknown: both fields are 0, no exception raised."""
        rec = _parse_setup_recommendation(_make_setup_json(
            shift_rpm_qual=0, shift_rpm_race=0
        ))
        assert rec.shift_rpm_qual == 0
        assert rec.shift_rpm_race == 0
        assert rec.shift_rpm == 0

    def test_one_zero_leaves_other_intact(self):
        """If shift_rpm_qual=0 and shift_rpm_race nonzero, 0 is left as 0 (D1 rule)."""
        rec = _parse_setup_recommendation(_make_setup_json(
            shift_rpm_qual=0, shift_rpm_race=7000
        ))
        assert rec.shift_rpm_qual == 0
        assert rec.shift_rpm_race == 7000
        assert rec.shift_rpm == 7000

    def test_one_nonzero_leaves_zero_intact(self):
        """If shift_rpm_qual nonzero and shift_rpm_race=0, 0 is left as 0."""
        rec = _parse_setup_recommendation(_make_setup_json(
            shift_rpm_qual=7400, shift_rpm_race=0
        ))
        assert rec.shift_rpm_qual == 7400
        assert rec.shift_rpm_race == 0
        assert rec.shift_rpm == 7400

    def test_legacy_shift_rpm_fallback_when_both_zero(self):
        """When shift_rpm_qual=0 and shift_rpm_race=0, fall back to JSON's shift_rpm."""
        json_str = _make_setup_json(shift_rpm_qual=0, shift_rpm_race=0)
        # Inject legacy shift_rpm into the JSON
        d = json.loads(json_str)
        d["shift_rpm"] = 6800
        rec = _parse_setup_recommendation(json.dumps(d))
        assert rec.shift_rpm == 6800

    def test_clamps_above_20000(self):
        rec = _parse_setup_recommendation(_make_setup_json(
            shift_rpm_qual=25000, shift_rpm_race=22000
        ))
        assert rec.shift_rpm_qual == 20000
        assert rec.shift_rpm_race == 20000


# ===========================================================================
# Section D — Prompt text contains both new field names (source-scan)
# ===========================================================================

class TestPromptContainsBothShiftRpmFields:
    """D — Prompt builder: shift_rpm_qual and shift_rpm_race appear in output."""

    def _prompt(self, **kwargs) -> str:
        return _make_prompt(**kwargs)

    def test_prompt_contains_shift_rpm_qual_key(self):
        prompt = self._prompt(session_type="Race", race_type="lap")
        assert "shift_rpm_qual" in prompt, (
            "'shift_rpm_qual' not found in prompt output"
        )

    def test_prompt_contains_shift_rpm_race_key(self):
        prompt = self._prompt(session_type="Race", race_type="lap")
        assert "shift_rpm_race" in prompt, (
            "'shift_rpm_race' not found in prompt output"
        )

    def test_prompt_does_not_contain_single_shift_rpm_field_only(self):
        """The old single-field pattern must be replaced by both new fields."""
        prompt = self._prompt(session_type="Race", race_type="lap")
        # Both new fields must be present
        assert "shift_rpm_qual" in prompt
        assert "shift_rpm_race" in prompt

    def test_prompt_qual_session_also_has_both_fields(self):
        prompt = self._prompt(session_type="Qualifying", race_type="lap")
        assert "shift_rpm_qual" in prompt
        assert "shift_rpm_race" in prompt

    def test_example_json_shift_rpm_qual_value(self):
        """Example JSON in prompt uses shift_rpm_qual value (e.g. 7400)."""
        prompt = self._prompt(session_type="Race", race_type="lap")
        assert "7400" in prompt, (
            "Example JSON should contain shift_rpm_qual value 7400"
        )

    def test_example_json_shift_rpm_race_value(self):
        """Example JSON in prompt uses shift_rpm_race value (e.g. 7000)."""
        prompt = self._prompt(session_type="Race", race_type="lap")
        # 7000 appears at least as the shift_rpm_race example value
        assert "7000" in prompt, (
            "Example JSON should contain shift_rpm_race value 7000"
        )

    def test_prompt_instructs_peak_power_rpm(self):
        """Prompt must mention PEAK-POWER RPM guidance for shift_rpm_qual."""
        prompt = self._prompt(session_type="Race", race_type="lap")
        assert "PEAK" in prompt or "peak" in prompt, (
            "Prompt should mention peak power RPM in shift_rpm_qual instructions"
        )

    def test_prompt_instructs_energy_tyre_saving(self):
        """shift_rpm_race instruction must mention energy or tyre saving."""
        prompt = self._prompt(session_type="Race", race_type="lap")
        assert "energy" in prompt.lower() or "tyre saving" in prompt.lower(), (
            "Prompt should mention energy/tyre saving for shift_rpm_race"
        )
